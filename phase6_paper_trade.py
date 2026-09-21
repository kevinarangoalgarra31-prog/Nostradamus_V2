"""CLI prospectivo de Nostradamus V6; simula decisiones sin conectar un broker."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import yfinance as yf

from src.config import (
    load_experiment_config,
    load_paper_trading_config,
)
from src.data_pipeline import calcular_caracteristicas, normalizar_ohlcv, validar_ohlcv
from src.paper_trading import (
    append_hash_record,
    assess_feature_drift,
    decide_position,
    load_latest_sentiment_signal,
    load_model_bundle,
    load_training_frame,
    read_hash_chain,
    settle_decision,
    sha256_file,
    summarize_portfolio,
)
from src.sentiment import parse_datetime_utc


UTC = timezone.utc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ejecuta una decisión diaria de paper trading sin órdenes reales."
    )
    parser.add_argument("--config", default="config/experiment.yaml")
    parser.add_argument("--paper-config", default="config/paper_trading_v6.yaml")
    parser.add_argument("--ticker", action="append", help="Ticker; se puede repetir.")
    parser.add_argument("--decision-at", help="ISO-8601 con zona; por defecto, ahora UTC.")
    parser.add_argument("--sentiment-root", default="output/v4_history")
    parser.add_argument("--model-root", default="output/v3")
    parser.add_argument("--data-dir", default="data/processed")
    parser.add_argument("--output-dir", default="output/v6")
    parser.add_argument(
        "--market-csv",
        action="append",
        default=[],
        metavar="TICKER=PATH",
        help="Fuente OHLCV local por ticker para una ejecución reproducible sin red.",
    )
    return parser


def _safe_name(value: str) -> str:
    return "".join(character if character.isalnum() or character in "_." else "_" for character in value)


def _json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _identifier(*parts: object) -> str:
    material = "|".join(str(part) for part in parts).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _download_market(ticker: str, experiment: Any, decision_at: datetime) -> pd.DataFrame:
    end = (decision_at.date() + timedelta(days=1)).isoformat()
    cache_dir = PROJECT_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(cache_dir.resolve()))
    raw = yf.download(
        tickers=ticker,
        start=experiment.data.start_date.isoformat(),
        end=end,
        interval=experiment.data.interval,
        auto_adjust=experiment.data.auto_adjust,
        progress=False,
        threads=False,
    )
    return normalizar_ohlcv(raw, ticker=ticker)


PROJECT_CACHE_DIR = Path("data/cache/yfinance")


def _market_csv_mapping(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        ticker, separator, raw_path = value.partition("=")
        if not separator or not ticker.strip() or not raw_path.strip():
            raise ValueError("--market-csv debe usar TICKER=PATH.")
        result[ticker.strip()] = Path(raw_path.strip())
    return result


def _load_market_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"No existe el CSV de mercado: {path}")
    return pd.read_csv(path, index_col=0, parse_dates=[0])


def _normalize_index(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    index = pd.to_datetime(result.index)
    if index.tz is not None:
        index = index.tz_convert("UTC").tz_localize(None)
    result.index = index.normalize()
    result.index.name = "Date"
    return result.sort_index()


def _validate_live_market(
    frame: pd.DataFrame, *, experiment: Any, decision_at: datetime
) -> None:
    """Valida velas cerradas y trata la vela abierta únicamente como cotización."""
    if frame.index.duplicated().any():
        raise ValueError("El mercado vivo contiene fechas duplicadas.")
    decision_day = pd.Timestamp(decision_at.date())
    completed = frame.loc[frame.index < decision_day]
    validar_ohlcv(
        completed,
        min_rows=experiment.validation.min_rows,
        max_missing_ratio=experiment.validation.max_missing_ratio,
    )
    live = frame.loc[frame.index >= decision_day]
    if live.empty:
        return
    # High/Low de la vela abierta pueden llegar transitoriamente inconsistentes
    # desde Yahoo. No participan en las características; para paper trading solo
    # exigimos una apertura y un último precio finitos y positivos.
    for column in ("Open", "Close"):
        values = pd.to_numeric(live[column], errors="coerce")
        if values.isna().any() or (values <= 0.0).any():
            raise ValueError(f"La cotización viva contiene {column} inválido.")


def _existing_daily_decision(
    decisions: list[dict[str, Any]], ticker: str, decision_day: str
) -> dict[str, Any] | None:
    matches = [
        record
        for record in decisions
        if record.get("asset") == ticker and record.get("decision_day") == decision_day
    ]
    return matches[-1] if matches else None


def _settle_pending(
    *,
    decisions: list[dict[str, Any]],
    settlements_path: Path,
    markets: Mapping[str, pd.DataFrame],
    decision_at: datetime,
    one_way_cost_rate: float,
) -> list[dict[str, Any]]:
    settlements = read_hash_chain(settlements_path)
    settled_ids = {record.get("trade_id") for record in settlements}
    for decision in decisions:
        trade_id = decision.get("decision_id")
        if decision.get("action") != "operate" or trade_id in settled_ids:
            continue
        ticker = str(decision.get("asset"))
        market = markets.get(ticker)
        if market is None:
            continue
        exit_date = pd.Timestamp(str(decision["planned_exit_date"]))
        if exit_date.date() > decision_at.date() or exit_date not in market.index:
            continue
        exit_price = float(market.loc[exit_date, "Open"])
        if not math.isfinite(exit_price) or exit_price <= 0.0:
            continue
        payload = settle_decision(
            decision,
            exit_price=exit_price,
            settled_at=exit_date.tz_localize("UTC").isoformat(),
            one_way_cost_rate=one_way_cost_rate,
        )
        payload["recorded_at"] = decision_at.isoformat()
        append_hash_record(settlements_path, payload)
        settled_ids.add(trade_id)
    return read_hash_chain(settlements_path)


def _open_exposure(
    decisions: list[dict[str, Any]], settlements: list[dict[str, Any]]
) -> float:
    settled = {record.get("trade_id") for record in settlements}
    return float(
        sum(
            float(record.get("exposure", 0.0))
            for record in decisions
            if record.get("action") == "operate"
            and record.get("decision_id") not in settled
        )
    )


def _failed_decision(
    *,
    ticker: str,
    decision_at: datetime,
    run_id: str,
    reason: str,
    supersedes: str | None,
) -> dict[str, Any]:
    day = decision_at.date().isoformat()
    return {
        "event": "decision",
        "schema_version": "6.0.0",
        "decision_id": _identifier("v6", ticker, day, run_id),
        "decision_key": f"{ticker}|{day}",
        "run_id": run_id,
        "asset": ticker,
        "decision_day": day,
        "decision_at": decision_at.isoformat(),
        "supersedes_decision_id": supersedes,
        "action": "abstain",
        "exposure": 0.0,
        "reason": reason,
        "blockers": [reason],
        "probability_raw": None,
        "probability_calibrated": None,
        "sentiment": None,
        "entry_price": None,
        "planned_exit_date": None,
    }


def _build_decision(
    *,
    ticker: str,
    market: pd.DataFrame,
    experiment: Any,
    config: Any,
    decision_at: datetime,
    run_id: str,
    sentiment_root: str,
    model_root: str,
    data_dir: str,
    current_total_exposure: float,
    portfolio: Mapping[str, Any],
    supersedes: str | None,
) -> dict[str, Any]:
    decision_day = pd.Timestamp(decision_at.date())
    completed = market.loc[market.index < decision_day]
    if completed.empty:
        raise ValueError("No existe una vela diaria cerrada antes de la decisión.")
    features = calcular_caracteristicas(
        completed,
        feature_config=experiment.features,
        target_config=experiment.target,
        ticker=ticker,
        intervalo=experiment.data.interval,
        include_target=False,
    )
    feature_date = pd.Timestamp(features.index[-1])
    feature_close_at = feature_date.tz_localize("UTC") + pd.Timedelta(days=1)
    decision_stamp = pd.Timestamp(decision_at).tz_convert("UTC")
    delay_minutes = float((decision_stamp - feature_close_at).total_seconds() / 60.0)

    bundle = load_model_bundle(ticker, model_root)
    feature_row = features.iloc[-1]
    raw_probability, calibrated_probability = bundle.predict(feature_row)
    training, training_path = load_training_frame(
        str(bundle.manifest["dataset_sha256"]), data_dir=data_dir
    )
    drift = assess_feature_drift(
        feature_row.loc[list(bundle.features)],
        training.loc[:, list(bundle.features)],
        warning_zscore=config.drift_warning_zscore,
        stop_zscore=config.drift_stop_zscore,
    )

    signal = load_latest_sentiment_signal(
        sentiment_root,
        ticker=ticker,
        analyzer=config.sentiment_analyzer,
        decision_at=decision_at,
    )
    blockers: list[str] = []
    if delay_minutes < 0.0:
        blockers.append("La vela seleccionada todavía no estaba cerrada.")
    elif delay_minutes > config.max_decision_delay_minutes:
        blockers.append(
            f"Decisión fuera de ventana: {delay_minutes:.1f} minutos después del cierre."
        )
    sentiment_age_hours: float | None = None
    sentiment_value: int | None = None
    if signal is None:
        blockers.append("No existe una señal V4 anterior a la decisión.")
    else:
        signal_at = pd.Timestamp(signal["decision_at"]).tz_convert("UTC")
        sentiment_age_hours = float((decision_stamp - signal_at).total_seconds() / 3600.0)
        if signal.get("status") != "ok" or signal.get("sentiment") not in {-1, 0, 1}:
            blockers.append("La última señal V4 no es válida.")
        elif sentiment_age_hours > config.max_sentiment_age_hours:
            blockers.append(
                f"La señal V4 tiene {sentiment_age_hours:.2f} horas de antigüedad."
            )
        elif signal_at < feature_close_at:
            blockers.append("La señal V4 fue calculada antes del cierre diario evaluado.")
        else:
            sentiment_value = int(signal["sentiment"])
    if drift["status"] == "blocked":
        blockers.append("Deriva severa de características.")
    if float(portfolio["max_drawdown"]) <= -config.max_drawdown:
        blockers.append("El límite de drawdown del paper portfolio fue alcanzado.")
    settled_count = int(portfolio["settled_trades"])
    recent_brier = portfolio.get("recent_brier")
    if (
        settled_count >= config.minimum_calibration_rows
        and recent_brier is not None
        and float(recent_brier) > config.max_recent_brier
    ):
        blockers.append("La calibración reciente superó el Brier máximo permitido.")

    quote_rows = market.loc[market.index >= decision_day]
    entry_price = float(quote_rows["Close"].iloc[-1]) if not quote_rows.empty else None
    if entry_price is None or entry_price <= 0.0:
        blockers.append("No existe un precio observable posterior al cierre para simular entrada.")

    outcome = decide_position(
        calibrated_probability,
        sentiment=sentiment_value,
        blockers=blockers,
        current_total_exposure=current_total_exposure,
        config=config,
    )
    planned_exit = (feature_date + pd.Timedelta(days=2)).date().isoformat()
    day = decision_at.date().isoformat()
    model_age_days = int((feature_date - pd.Timestamp(bundle.manifest["training_end"])).days)
    record = {
        "event": "decision",
        "schema_version": "6.0.0",
        "decision_id": _identifier("v6", ticker, day, run_id),
        "decision_key": f"{ticker}|{day}",
        "run_id": run_id,
        "asset": ticker,
        "decision_day": day,
        "decision_at": decision_at.isoformat(),
        "supersedes_decision_id": supersedes,
        "feature_date": feature_date.isoformat(),
        "feature_close_at": feature_close_at.isoformat(),
        "decision_delay_minutes": delay_minutes,
        "feature_values": {
            name: float(feature_row[name]) for name in bundle.features
        },
        "market_close": float(feature_row["Close"]),
        "technical_context": {
            "close": float(feature_row["Close"]),
            "sma_20": float(feature_row["SMA_20"]),
            "rsi_14": float(feature_row["RSI_14"]),
        },
        "model": {
            "project_version": bundle.manifest.get("project_version"),
            "training_start": bundle.manifest.get("training_start"),
            "training_end": bundle.manifest.get("training_end"),
            "age_days": model_age_days,
            "dataset_sha256": bundle.manifest.get("dataset_sha256"),
            "model_path": str(bundle.model_path),
            "model_sha256": sha256_file(bundle.model_path),
            "manifest_path": str(bundle.manifest_path),
            "manifest_sha256": sha256_file(bundle.manifest_path),
            "training_data_path": str(training_path),
        },
        "probability_raw": raw_probability,
        "probability_calibrated": calibrated_probability,
        "probability_threshold": config.probability_threshold,
        "sentiment": sentiment_value,
        "sentiment_signal": signal,
        "sentiment_age_hours": sentiment_age_hours,
        "drift": drift,
        "portfolio_before_decision": dict(portfolio),
        "current_total_exposure": current_total_exposure,
        "action": outcome.action,
        "exposure": outcome.exposure,
        "raw_kelly": outcome.raw_kelly,
        "sentiment_multiplier": outcome.sentiment_multiplier,
        "reason": outcome.reason,
        "blockers": blockers,
        "entry_price": entry_price if outcome.action == "operate" else None,
        "entry_price_reference": (
            "yfinance_daily_incomplete_close_captured_at_decision"
            if outcome.action == "operate"
            else None
        ),
        "entry_price_captured_at": (
            decision_at.isoformat() if outcome.action == "operate" else None
        ),
        "planned_exit_date": planned_exit if outcome.action == "operate" else None,
        "commission_bps_one_way": experiment.commission_bps,
        "slippage_bps_one_way": experiment.slippage_bps,
    }
    return record


def _save_status(
    output_root: Path,
    *,
    decisions: list[dict[str, Any]],
    settlements: list[dict[str, Any]],
    portfolio: Mapping[str, Any],
    equity: pd.DataFrame,
) -> None:
    equity.to_csv(output_root / "portfolio_equity.csv", index=False, lineterminator="\n")
    latest: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        latest[str(decision["asset"])] = decision
    status = {
        "schema_version": "6.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "paper_only": True,
        "broker_connected": False,
        "portfolio": dict(portfolio),
        "decision_records": len(decisions),
        "settlement_records": len(settlements),
        "latest_decisions": {
            ticker: {
                "decision_at": item.get("decision_at"),
                "action": item.get("action"),
                "exposure": item.get("exposure"),
                "probability_calibrated": item.get("probability_calibrated"),
                "sentiment": item.get("sentiment"),
                "reason": item.get("reason"),
            }
            for ticker, item in latest.items()
        },
        "decision_chain_head": decisions[-1]["record_hash"] if decisions else None,
        "settlement_chain_head": settlements[-1]["record_hash"] if settlements else None,
    }
    _json_write(output_root / "status.json", status)
    lines = [
        "# Nostradamus V6 — estado de paper trading",
        "",
        "> Simulación educativa. No existe conexión con un broker ni capital real.",
        "",
        f"- Capital inicial: {portfolio['initial_capital']:.2f}",
        f"- Capital simulado actual: {portfolio['current_capital']:.2f}",
        f"- Retorno acumulado: {portfolio['total_return']:.4f}",
        f"- Drawdown máximo: {portfolio['max_drawdown']:.4f}",
        f"- Operaciones liquidadas: {portfolio['settled_trades']}",
        f"- Brier reciente: {portfolio['recent_brier'] if portfolio['recent_brier'] is not None else 'N/D'}",
        "",
        "## Últimas decisiones",
        "",
        "| Activo | Instante | Acción | Exposición | Probabilidad | Sentimiento | Motivo |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for ticker, item in sorted(latest.items()):
        probability = item.get("probability_calibrated")
        probability_text = "N/D" if probability is None else f"{float(probability):.4f}"
        lines.append(
            f"| {ticker} | {item.get('decision_at')} | {item.get('action')} | "
            f"{float(item.get('exposure', 0.0)):.4f} | {probability_text} | "
            f"{item.get('sentiment', 'N/D')} | {item.get('reason')} |"
        )
    (output_root / "PAPER_TRADING_STATUS.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main() -> int:
    args = _parser().parse_args()
    experiment = load_experiment_config(args.config)
    config = load_paper_trading_config(args.paper_config)
    decision_at = (
        parse_datetime_utc(args.decision_at)
        if args.decision_at
        else datetime.now(UTC)
    )
    tickers = tuple(args.ticker or experiment.data.tickers)
    unknown = sorted(set(tickers) - set(experiment.data.tickers))
    if unknown:
        raise ValueError("Tickers fuera del universo declarado: " + ", ".join(unknown))
    market_csv = _market_csv_mapping(args.market_csv)
    unknown_market = sorted(set(market_csv) - set(tickers))
    if unknown_market:
        raise ValueError(
            "--market-csv contiene tickers no solicitados: " + ", ".join(unknown_market)
        )

    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    decisions_path = output_root / "decisions.jsonl"
    settlements_path = output_root / "settlements.jsonl"
    run_id = decision_at.strftime("%Y%m%dT%H%M%S_%fZ")
    run_dir = (
        output_root
        / "runs"
        / decision_at.strftime("%Y")
        / decision_at.strftime("%m")
        / decision_at.strftime("%d")
        / run_id
    )
    run_dir.mkdir(parents=True, exist_ok=False)

    markets: dict[str, pd.DataFrame] = {}
    market_errors: dict[str, str] = {}
    for ticker in tickers:
        print(f"[Fase 6] Preparando mercado para {ticker}...", flush=True)
        try:
            markets[ticker] = _normalize_index(
                _load_market_csv(market_csv[ticker])
                if ticker in market_csv
                else _download_market(ticker, experiment, decision_at)
            )
            _validate_live_market(
                markets[ticker], experiment=experiment, decision_at=decision_at
            )
        except Exception as exc:
            market_errors[ticker] = f"{type(exc).__name__}: {exc}"

    decisions = read_hash_chain(decisions_path)
    one_way_cost = (experiment.commission_bps + experiment.slippage_bps) / 10_000.0
    settlements = _settle_pending(
        decisions=decisions,
        settlements_path=settlements_path,
        markets=markets,
        decision_at=decision_at,
        one_way_cost_rate=one_way_cost,
    )
    portfolio, equity = summarize_portfolio(
        settlements,
        initial_capital=config.initial_capital,
        calibration_window=config.calibration_window,
    )
    current_exposure = _open_exposure(decisions, settlements)
    run_records: list[dict[str, Any]] = []
    day = decision_at.date().isoformat()

    for ticker in tickers:
        previous = _existing_daily_decision(decisions, ticker, day)
        if previous is not None and previous.get("action") != "abstain":
            run_records.append(
                {
                    "asset": ticker,
                    "status": "already_decided",
                    "decision_id": previous.get("decision_id"),
                    "action": previous.get("action"),
                }
            )
            print(f"[Fase 6] {ticker}: decisión del día ya registrada.", flush=True)
            continue
        supersedes = previous.get("decision_id") if previous is not None else None
        try:
            if ticker in market_errors:
                raise RuntimeError(market_errors[ticker])
            record = _build_decision(
                ticker=ticker,
                market=markets[ticker],
                experiment=experiment,
                config=config,
                decision_at=decision_at,
                run_id=run_id,
                sentiment_root=args.sentiment_root,
                model_root=args.model_root,
                data_dir=args.data_dir,
                current_total_exposure=current_exposure,
                portfolio=portfolio,
                supersedes=supersedes,
            )
        except Exception as exc:
            record = _failed_decision(
                ticker=ticker,
                decision_at=decision_at,
                run_id=run_id,
                reason=f"{type(exc).__name__}: {exc}",
                supersedes=supersedes,
            )
        stored = append_hash_record(decisions_path, record)
        decisions.append(stored)
        if stored["action"] == "operate":
            current_exposure += float(stored["exposure"])
        _json_write(run_dir / f"{_safe_name(ticker)}_decision.json", stored)
        run_records.append(
            {
                "asset": ticker,
                "status": "recorded",
                "decision_id": stored["decision_id"],
                "action": stored["action"],
                "exposure": stored["exposure"],
                "probability_calibrated": stored.get("probability_calibrated"),
                "sentiment": stored.get("sentiment"),
                "reason": stored["reason"],
            }
        )
        print(
            f"[Fase 6] {ticker}: {stored['action']} | exposición={stored['exposure']:.4f}",
            flush=True,
        )

    decisions = read_hash_chain(decisions_path)
    settlements = read_hash_chain(settlements_path)
    portfolio, equity = summarize_portfolio(
        settlements,
        initial_capital=config.initial_capital,
        calibration_window=config.calibration_window,
    )
    _save_status(
        output_root,
        decisions=decisions,
        settlements=settlements,
        portfolio=portfolio,
        equity=equity,
    )
    summary = {
        "phase": 6,
        "version": config.version,
        "run_id": run_id,
        "decision_at": decision_at.isoformat(),
        "paper_only": True,
        "broker_connected": False,
        "records": run_records,
        "settlements_total": len(settlements),
        "portfolio": portfolio,
        "journals": {
            "decisions": str(decisions_path),
            "settlements": str(settlements_path),
        },
    }
    summary_path = run_dir / "run_summary.json"
    _json_write(summary_path, summary)
    artifact_hashes = {
        path.name: sha256_file(path)
        for path in run_dir.iterdir()
        if path.is_file()
    }
    _json_write(
        run_dir / "run_manifest.json",
        {
            "schema_version": "6.0.0",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "run_id": run_id,
            "paper_only": True,
            "broker_connected": False,
            "config": config.to_dict(),
            "artifacts_sha256": artifact_hashes,
        },
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
