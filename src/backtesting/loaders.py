"""Carga verificada de datos de mercado, predicciones V3 y señales V4."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


def _safe_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.]+", "_", value.strip())
    return normalized.strip("_") or "asset"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class InputBundle:
    ticker: str
    market: pd.DataFrame
    predictions: pd.DataFrame
    sentiment: pd.DataFrame
    metadata: dict[str, Any]


def _load_latest_market(
    ticker: str, data_dir: str | Path, interval: str
) -> tuple[pd.DataFrame, dict[str, Any], Path]:
    directory = Path(data_dir)
    prefix = _safe_name(f"{ticker}_{interval}_processed")
    candidates: list[tuple[str, Path, dict[str, Any]]] = []
    for manifest_path in directory.glob(f"{prefix}_*.manifest.json"):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("ticker") == ticker and manifest.get("dataset_kind") == "processed":
            candidates.append((str(manifest.get("created_at_utc", "")), manifest_path, manifest))
    if not candidates:
        raise FileNotFoundError(
            f"No existe un dataset procesado verificable para {ticker}. Ejecuta prepare_data.py."
        )
    _, manifest_path, manifest = max(candidates, key=lambda item: item[0])
    data_path = manifest_path.with_name(manifest_path.name.replace(".manifest.json", ".csv"))
    if not data_path.is_file() or _sha256(data_path) != manifest.get("sha256"):
        raise ValueError(f"El dataset procesado no existe o su SHA-256 es inválido: {data_path}")
    frame = pd.read_csv(data_path, index_col="Date", parse_dates=["Date"])
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    frame.index.name = "Date"
    return frame.sort_index(), manifest, data_path


def load_sentiment_history(
    root: str | Path,
    *,
    ticker: str,
    analyzer: str,
) -> pd.DataFrame:
    """Consolida señales archivadas; la última ejecución válida del día prevalece."""
    directory = Path(root)
    rows: list[dict[str, Any]] = []
    if not directory.exists():
        return pd.DataFrame(
            columns=[
                "sentiment",
                "sentiment_status",
                "sentiment_score",
                "sentiment_confidence",
                "sentiment_coverage",
                "sentiment_decision_at",
                "sentiment_artifact",
            ]
        )
    ticker_dir = _safe_name(ticker)
    for path in directory.rglob("signals.json"):
        if path.parent.name != ticker_dir:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, list):
            continue
        for signal in payload:
            if not isinstance(signal, dict) or signal.get("analyzer") != analyzer:
                continue
            try:
                decision = pd.Timestamp(signal["decision_at"])
                if decision.tzinfo is None:
                    continue
                decision_utc = decision.tz_convert("UTC")
            except (KeyError, TypeError, ValueError):
                continue
            rows.append(
                {
                    "Date": decision_utc.tz_localize(None).normalize(),
                    "sentiment": signal.get("sentiment"),
                    "sentiment_status": signal.get("status"),
                    "sentiment_score": signal.get("score"),
                    "sentiment_confidence": signal.get("confidence"),
                    "sentiment_coverage": signal.get("coverage_ratio"),
                    "sentiment_decision_at": decision_utc.isoformat(),
                    "sentiment_artifact": str(path),
                }
            )
    if not rows:
        return pd.DataFrame(
            columns=[
                "sentiment",
                "sentiment_status",
                "sentiment_score",
                "sentiment_confidence",
                "sentiment_coverage",
                "sentiment_decision_at",
                "sentiment_artifact",
            ]
        )
    result = pd.DataFrame(rows).sort_values("sentiment_decision_at")
    result = result.drop_duplicates(subset=["Date"], keep="last").set_index("Date")
    result.index = pd.to_datetime(result.index)
    return result.sort_index()


def load_v5_inputs(
    ticker: str,
    *,
    interval: str = "1d",
    data_dir: str | Path = "data/processed",
    prediction_root: str | Path = "output/v3",
    sentiment_root: str | Path = "output/v4_history",
    sentiment_analyzer: str = "structured_llm",
) -> InputBundle:
    market, dataset_manifest, data_path = _load_latest_market(ticker, data_dir, interval)
    ticker_dir = Path(prediction_root) / _safe_name(ticker)
    predictions_path = ticker_dir / "predictions_oos.csv"
    model_manifest_path = ticker_dir / "model_manifest.json"
    if not predictions_path.is_file() or not model_manifest_path.is_file():
        raise FileNotFoundError(f"Faltan predicciones V3 para {ticker}: {ticker_dir}")
    model_manifest = json.loads(model_manifest_path.read_text(encoding="utf-8"))
    if model_manifest.get("dataset_sha256") != dataset_manifest.get("sha256"):
        raise ValueError("Las predicciones V3 no corresponden al dataset procesado activo.")
    predictions = pd.read_csv(predictions_path, index_col="Date", parse_dates=["Date"])
    predictions.index = pd.to_datetime(predictions.index).tz_localize(None)
    predictions.index.name = "Date"
    if predictions.index.duplicated().any() or not predictions.index.is_monotonic_increasing:
        raise ValueError("Las predicciones OOS deben ser únicas y estar ordenadas.")
    required = {"fold", "probability_raw", "probability_calibrated", "y_true"}
    missing = required - set(predictions.columns)
    if missing:
        raise ValueError("Faltan columnas en las predicciones V3: " + ", ".join(sorted(missing)))
    sentiment = load_sentiment_history(
        sentiment_root, ticker=ticker, analyzer=sentiment_analyzer
    )
    return InputBundle(
        ticker=ticker,
        market=market,
        predictions=predictions,
        sentiment=sentiment,
        metadata={
            "market_path": str(data_path),
            "market_sha256": dataset_manifest["sha256"],
            "predictions_path": str(predictions_path),
            "predictions_sha256": _sha256(predictions_path),
            "model_manifest_path": str(model_manifest_path),
            "model_version": model_manifest.get("project_version"),
            "sentiment_root": str(Path(sentiment_root)),
            "sentiment_rows": len(sentiment),
            "sentiment_analyzer": sentiment_analyzer,
        },
    )
