from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from phase6_paper_trade import _build_decision, _validate_live_market
from src.config import (
    PaperTradingConfig,
    load_experiment_config,
    load_paper_trading_config,
)
from src.data_pipeline import calcular_caracteristicas
from src.paper_trading import (
    append_hash_record,
    assess_feature_drift,
    calibrate_probability,
    decide_position,
    load_latest_sentiment_signal,
    load_model_bundle,
    load_training_frame,
    read_hash_chain,
    settle_decision,
    summarize_portfolio,
)


UTC = timezone.utc


def quick_config() -> PaperTradingConfig:
    return PaperTradingConfig(
        version="6.0.0",
        initial_capital=10_000.0,
        probability_threshold=0.50,
        sentiment_analyzer="structured_llm",
        max_sentiment_age_hours=6.0,
        max_decision_delay_minutes=90.0,
        fractional_kelly=0.25,
        max_asset_exposure=0.25,
        max_total_exposure=0.50,
        drift_warning_zscore=4.0,
        drift_stop_zscore=8.0,
        max_drawdown=0.20,
        calibration_window=30,
        minimum_calibration_rows=20,
        max_recent_brier=0.35,
    )


class PaperTradingConfigTests(unittest.TestCase):
    def test_repository_config_is_safe_and_paper_only(self) -> None:
        config = load_paper_trading_config("config/paper_trading_v6.yaml")
        self.assertEqual(config.version, "6.0.0")
        self.assertLessEqual(config.max_asset_exposure, 0.25)
        self.assertLessEqual(config.max_total_exposure, 0.50)


class LiveFeatureTests(unittest.TestCase):
    def test_open_daily_candle_is_not_validated_as_a_closed_ohlc_bar(self) -> None:
        experiment = load_experiment_config("config/experiment.yaml")
        dates = pd.date_range("2025-12-01", periods=300, freq="D")
        close = 100.0 + np.arange(300, dtype=float)
        market = pd.DataFrame(
            {
                "Open": close,
                "High": close + 1.0,
                "Low": close - 1.0,
                "Close": close + 0.2,
                "Volume": 1_000.0,
            },
            index=dates,
        )
        decision_day = dates[-1] + pd.Timedelta(days=1)
        # La fila abierta tiene High menor que Close y fallaría el contrato OHLC
        # histórico, pero Open/Close siguen siendo una cotización utilizable.
        market.loc[decision_day] = {
            "Open": 400.0,
            "High": 399.0,
            "Low": 398.0,
            "Close": 401.0,
            "Volume": 10.0,
        }
        _validate_live_market(
            market,
            experiment=experiment,
            decision_at=decision_day.tz_localize("UTC").to_pydatetime(),
        )

    def test_inference_features_keep_latest_closed_row_without_target(self) -> None:
        dates = pd.date_range("2026-01-01", periods=90, freq="D")
        close = 100.0 + np.arange(90, dtype=float)
        raw = pd.DataFrame(
            {
                "Open": close - 0.2,
                "High": close + 1.0,
                "Low": close - 1.0,
                "Close": close,
                "Volume": 1_000.0 + np.arange(90),
            },
            index=dates,
        )
        features = calcular_caracteristicas(raw, include_target=False)
        self.assertEqual(features.index[-1], dates[-1])
        self.assertNotIn("Target", features)
        self.assertNotIn("Target_Return", features)

    def test_repository_models_load_with_their_exact_training_dataset(self) -> None:
        for ticker in ("BTC-USD", "ETH-USD"):
            bundle = load_model_bundle(ticker)
            training, _ = load_training_frame(bundle.manifest["dataset_sha256"])
            raw, calibrated = bundle.predict(training.iloc[-1])
            self.assertGreaterEqual(raw, 0.0)
            self.assertLessEqual(raw, 1.0)
            self.assertGreaterEqual(calibrated, 0.0)
            self.assertLessEqual(calibrated, 1.0)

    def test_live_decision_uses_closed_candle_and_post_close_sentiment(self) -> None:
        experiment = load_experiment_config("config/experiment.yaml")
        config = quick_config()
        bundle = load_model_bundle("BTC-USD")
        training, _ = load_training_frame(bundle.manifest["dataset_sha256"])
        market = training.loc[:, ["Open", "High", "Low", "Close", "Volume"]].copy()
        feature_date = pd.Timestamp(market.index[-1])
        decision_day = feature_date + pd.Timedelta(days=1)
        last_close = float(market["Close"].iloc[-1])
        market.loc[decision_day] = {
            "Open": last_close,
            "High": last_close * 1.01,
            "Low": last_close * 0.99,
            "Close": last_close * 1.002,
            "Volume": float(market["Volume"].iloc[-1]),
        }
        sentiment_dir = Path("tmp/test_phase6_live/BTC_USD")
        sentiment_dir.mkdir(parents=True, exist_ok=True)
        signal_at = decision_day.tz_localize("UTC") + pd.Timedelta(minutes=3)
        (sentiment_dir / "signals.json").write_text(
            json.dumps(
                [
                    {
                        "asset": "BTC-USD",
                        "analyzer": "structured_llm",
                        "decision_at": signal_at.isoformat(),
                        "status": "ok",
                        "sentiment": 1,
                        "score": 0.4,
                        "confidence": 0.9,
                        "coverage_ratio": 1.0,
                    }
                ]
            ),
            encoding="utf-8",
        )
        decision = _build_decision(
            ticker="BTC-USD",
            market=market,
            experiment=experiment,
            config=config,
            decision_at=(signal_at + pd.Timedelta(minutes=2)).to_pydatetime(),
            run_id="fixture-run",
            sentiment_root=str(sentiment_dir.parent),
            model_root="output/v3",
            data_dir="data/processed",
            current_total_exposure=0.0,
            portfolio={
                "max_drawdown": 0.0,
                "settled_trades": 0,
                "recent_brier": None,
            },
            supersedes=None,
        )
        self.assertNotEqual(decision["action"], "abstain")
        self.assertEqual(decision["blockers"], [])
        self.assertEqual(decision["feature_date"], feature_date.isoformat())


class PaperTradingEngineTests(unittest.TestCase):
    def test_persisted_sigmoid_calibration_is_reproduced(self) -> None:
        probability = calibrate_probability(
            0.8,
            {"method": "sigmoid", "coefficient": 1.0, "intercept": 0.0},
        )
        self.assertAlmostEqual(probability, 0.8)

    def test_arbiter_abstains_on_blocker_and_caps_kelly(self) -> None:
        config = quick_config()
        blocked = decide_position(
            0.9,
            sentiment=1,
            blockers=["datos atrasados"],
            current_total_exposure=0.0,
            config=config,
        )
        self.assertEqual(blocked.action, "abstain")
        approved = decide_position(
            0.9,
            sentiment=1,
            blockers=[],
            current_total_exposure=0.4,
            config=config,
        )
        self.assertEqual(approved.action, "operate")
        self.assertAlmostEqual(approved.exposure, 0.1)
        negative = decide_position(
            0.9,
            sentiment=-1,
            blockers=[],
            current_total_exposure=0.0,
            config=config,
        )
        self.assertEqual(negative.action, "no_trade")

    def test_point_drift_can_stop_a_decision(self) -> None:
        training = pd.DataFrame({"feature": [-1.0, 0.0, 1.0]})
        drift = assess_feature_drift(
            pd.Series({"feature": 20.0}),
            training,
            warning_zscore=4.0,
            stop_zscore=8.0,
        )
        self.assertEqual(drift["status"], "blocked")

    def test_settlement_reconstructs_capital_and_brier(self) -> None:
        decision = {
            "decision_id": "trade-1",
            "asset": "BTC-USD",
            "decision_at": "2026-01-01T00:05:00+00:00",
            "planned_exit_date": "2026-01-02",
            "action": "operate",
            "entry_price": 100.0,
            "exposure": 0.25,
            "probability_calibrated": 0.8,
        }
        settlement = settle_decision(
            decision,
            exit_price=110.0,
            settled_at="2026-01-02T00:00:00+00:00",
            one_way_cost_rate=0.0015,
        )
        self.assertGreater(settlement["net_return_contribution"], 0.0)
        summary, equity = summarize_portfolio(
            [settlement], initial_capital=10_000.0, calibration_window=30
        )
        self.assertGreater(summary["current_capital"], 10_000.0)
        self.assertEqual(summary["settled_trades"], 1)
        self.assertEqual(len(equity), 1)


class PaperTradingAuditTests(unittest.TestCase):
    def test_hash_chain_detects_tampering(self) -> None:
        path = Path("tmp/test_phase6_hash/decisions.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        append_hash_record(path, {"event": "decision", "value": 1})
        append_hash_record(path, {"event": "decision", "value": 2})
        self.assertEqual(len(read_hash_chain(path)), 2)
        content = path.read_text(encoding="utf-8").replace('"value": 1', '"value": 9')
        path.write_text(content, encoding="utf-8")
        with self.assertRaises(ValueError):
            read_hash_chain(path)

    def test_latest_sentiment_never_reads_the_future(self) -> None:
        root = Path("tmp/test_phase6_sentiment")
        first = root / "a" / "BTC_USD"
        second = root / "b" / "BTC_USD"
        first.mkdir(parents=True, exist_ok=True)
        second.mkdir(parents=True, exist_ok=True)
        base = {
            "asset": "BTC-USD",
            "analyzer": "structured_llm",
            "status": "ok",
            "score": 0.5,
            "confidence": 0.9,
            "coverage_ratio": 1.0,
        }
        (first / "signals.json").write_text(
            json.dumps(
                [{**base, "decision_at": "2026-01-01T00:05:00Z", "sentiment": 1}]
            ),
            encoding="utf-8",
        )
        (second / "signals.json").write_text(
            json.dumps(
                [{**base, "decision_at": "2026-01-02T00:05:00Z", "sentiment": -1}]
            ),
            encoding="utf-8",
        )
        result = load_latest_sentiment_signal(
            root,
            ticker="BTC-USD",
            analyzer="structured_llm",
            decision_at=datetime(2026, 1, 1, 1, 0, tzinfo=UTC),
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["sentiment"], 1)


if __name__ == "__main__":
    unittest.main()
