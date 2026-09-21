from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtesting import (
    load_sentiment_history,
    prepare_backtest_frame,
    run_backtest_suite,
    save_backtest_suite,
)
from src.config import BacktestingConfig, load_backtesting_config


def quick_config(*, minimum_coverage: float = 0.8, minimum_rows: int = 5) -> BacktestingConfig:
    return BacktestingConfig(
        version="5.0.0",
        annualization_periods=365,
        probability_threshold=0.5,
        technical_sma_column="SMA_20",
        technical_rsi_column="RSI_14",
        technical_rsi_threshold=50.0,
        fractional_kelly=0.25,
        max_exposure=0.25,
        sentiment_analyzer="structured_llm",
        minimum_sentiment_coverage=minimum_coverage,
        minimum_hybrid_rows=minimum_rows,
        cost_multipliers=(0.0, 1.0, 2.0),
        threshold_grid=(0.45, 0.5, 0.55),
        regime_volatility_column="Volatilidad_20",
    )


def synthetic_inputs(rows: int = 30) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.date_range("2026-01-01", periods=rows + 2, freq="D")
    opens = 100.0 + np.arange(rows + 2, dtype=float)
    market = pd.DataFrame(
        {
            "Open": opens,
            "Close": opens + np.sin(np.arange(rows + 2)),
            "SMA_20": opens - 0.5,
            "RSI_14": np.where(np.arange(rows + 2) % 3 == 0, 45.0, 55.0),
            "Volatilidad_20": np.linspace(0.1, 0.9, rows + 2),
        },
        index=dates,
    )
    probability = np.where(np.arange(rows) % 2 == 0, 0.60, 0.40)
    predictions = pd.DataFrame(
        {
            "fold": np.repeat([1, 2, 3], repeats=[10, 10, rows - 20]),
            "y_true": (probability >= 0.5).astype(int),
            "probability_raw": probability + 0.02,
            "probability_calibrated": probability,
        },
        index=dates[:rows],
    )
    return market, predictions


class BacktestingConfigTests(unittest.TestCase):
    def test_repository_v5_config_is_valid(self) -> None:
        config = load_backtesting_config("config/backtesting_v5.yaml")
        self.assertEqual(config.version, "5.0.0")
        self.assertEqual(config.annualization_periods, 365)
        self.assertLessEqual(config.max_exposure, 0.25)


class BacktestingEngineTests(unittest.TestCase):
    def test_execution_return_uses_next_two_opens(self) -> None:
        market, predictions = synthetic_inputs()
        frame = prepare_backtest_frame(market, predictions)
        expected = market["Open"].iloc[2] / market["Open"].iloc[1] - 1.0
        self.assertAlmostEqual(frame["execution_return"].iloc[0], expected)
        self.assertEqual(frame["entry_open"].iloc[0], market["Open"].iloc[1])
        self.assertEqual(frame["exit_open"].iloc[0], market["Open"].iloc[2])

    def test_hybrid_is_not_scored_without_real_coverage(self) -> None:
        market, predictions = synthetic_inputs()
        frame = prepare_backtest_frame(market, predictions)
        suite = run_backtest_suite(
            frame, quick_config(), commission_bps=10, slippage_bps=5
        )
        self.assertEqual(suite.hybrid_status["status"], "not_evaluable")
        self.assertEqual(
            set(suite.results), {"B0_buy_and_hold", "B1_technical", "M1_xgboost"}
        )

    def test_hybrid_strategies_use_sentiment_and_capped_kelly(self) -> None:
        market, predictions = synthetic_inputs()
        sentiment = pd.DataFrame(
            {
                "sentiment": np.resize(np.array([1, 0, -1]), len(predictions)),
                "sentiment_status": "ok",
                "sentiment_score": 0.0,
                "sentiment_confidence": 0.9,
                "sentiment_coverage": 1.0,
                "sentiment_decision_at": "2026-01-01T00:00:00+00:00",
                "sentiment_artifact": "fixture",
            },
            index=predictions.index,
        )
        frame = prepare_backtest_frame(market, predictions, sentiment)
        suite = run_backtest_suite(
            frame, quick_config(), commission_bps=10, slippage_bps=5
        )
        self.assertEqual(suite.hybrid_status["status"], "evaluable")
        self.assertIn("M2_xgboost_sentiment", suite.results)
        self.assertIn("M3_risk_arbiter", suite.results)
        m3 = suite.results["M3_risk_arbiter"].frame["position"]
        self.assertLessEqual(float(m3.max()), 0.25)
        negative_dates = frame.index[frame["sentiment"] == -1]
        self.assertTrue((m3.loc[negative_dates] == 0.0).all())

    def test_cost_sensitivity_penalizes_turnover(self) -> None:
        market, predictions = synthetic_inputs()
        frame = prepare_backtest_frame(market, predictions)
        suite = run_backtest_suite(
            frame, quick_config(), commission_bps=10, slippage_bps=5
        )
        rows = suite.cost_sensitivity
        zero = rows.loc[
            (rows["strategy"] == "M1_xgboost") & (rows["cost_multiplier"] == 0.0),
            "total_return",
        ].iloc[0]
        double = rows.loc[
            (rows["strategy"] == "M1_xgboost") & (rows["cost_multiplier"] == 2.0),
            "total_return",
        ].iloc[0]
        self.assertGreater(zero, double)


class PhaseFiveArtifactTests(unittest.TestCase):
    def test_sentiment_history_keeps_last_signal_per_day(self) -> None:
        root = Path("tmp/test_v5_sentiment")
        first = root / "run_a" / "BTC_USD"
        second = root / "run_b" / "BTC_USD"
        first.mkdir(parents=True, exist_ok=True)
        second.mkdir(parents=True, exist_ok=True)
        base = {
            "asset": "BTC-USD",
            "analyzer": "structured_llm",
            "model_version": "fixture",
            "status": "ok",
            "score": 0.5,
            "confidence": 0.9,
            "coverage_ratio": 1.0,
        }
        (first / "signals.json").write_text(
            json.dumps([{**base, "decision_at": "2026-01-01T10:00:00Z", "sentiment": -1}]),
            encoding="utf-8",
        )
        (second / "signals.json").write_text(
            json.dumps([{**base, "decision_at": "2026-01-01T12:00:00Z", "sentiment": 1}]),
            encoding="utf-8",
        )
        history = load_sentiment_history(
            root, ticker="BTC-USD", analyzer="structured_llm"
        )
        self.assertEqual(len(history), 1)
        self.assertEqual(int(history.iloc[0]["sentiment"]), 1)

    def test_v5_manifest_hashes_generated_artifacts(self) -> None:
        market, predictions = synthetic_inputs()
        frame = prepare_backtest_frame(market, predictions)
        config = quick_config()
        suite = run_backtest_suite(frame, config, commission_bps=10, slippage_bps=5)
        output = Path("tmp/test_v5_artifacts")
        paths = save_backtest_suite(
            suite,
            output,
            ticker="BTC-USD",
            config=config,
            commission_bps=10,
            slippage_bps=5,
            input_metadata={"fixture": True},
        )
        manifest = json.loads(paths.manifest.read_text(encoding="utf-8"))
        expected = hashlib.sha256(paths.metrics.read_bytes()).hexdigest()
        self.assertEqual(manifest["artifact_sha256"]["metrics.json"], expected)
        self.assertEqual(manifest["schema_version"], "5.0.0")


if __name__ == "__main__":
    unittest.main()
