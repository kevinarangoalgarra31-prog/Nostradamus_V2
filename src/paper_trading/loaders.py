"""Carga auditable del modelo V3, su dataset y la señal V4 más reciente."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import xgboost as xgb

from .engine import calibrate_probability


def _safe_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.]+", "_", value.strip())
    return normalized.strip("_") or "asset"


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass(frozen=True)
class ModelBundle:
    ticker: str
    model: xgb.XGBClassifier
    features: tuple[str, ...]
    calibration: dict[str, Any]
    manifest: dict[str, Any]
    model_path: Path
    manifest_path: Path

    def predict(self, row: pd.Series) -> tuple[float, float]:
        missing = [feature for feature in self.features if feature not in row.index]
        if missing:
            raise ValueError("Faltan características para inferencia: " + ", ".join(missing))
        frame = pd.DataFrame([[float(row[name]) for name in self.features]], columns=self.features)
        raw = float(self.model.predict_proba(frame)[:, 1][0])
        return raw, calibrate_probability(raw, self.calibration)


def load_model_bundle(
    ticker: str, model_root: str | Path = "output/v3"
) -> ModelBundle:
    directory = Path(model_root) / _safe_name(ticker)
    manifest_path = directory / "model_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"No existe el manifiesto V3 para {ticker}: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("ticker") != ticker:
        raise ValueError(f"El manifiesto V3 no corresponde a {ticker}.")
    artifacts = manifest.get("artifacts", {})
    model_path = directory / str(artifacts.get("model", "xgboost_v3.json"))
    calibrator_path = directory / str(artifacts.get("calibrator", "calibrator.json"))
    if not model_path.is_file() or not calibrator_path.is_file():
        raise FileNotFoundError(f"Faltan modelo o calibrador V3 para {ticker}.")
    calibration = json.loads(calibrator_path.read_text(encoding="utf-8"))
    if calibration != manifest.get("calibration"):
        raise ValueError("El calibrador no coincide con el manifiesto V3.")
    features = tuple(str(value) for value in manifest.get("features", ()))
    if not features:
        raise ValueError("El manifiesto V3 no declara características.")
    model = xgb.XGBClassifier()
    model.load_model(model_path)
    return ModelBundle(
        ticker=ticker,
        model=model,
        features=features,
        calibration=calibration,
        manifest=manifest,
        model_path=model_path,
        manifest_path=manifest_path,
    )


def load_training_frame(
    dataset_sha256: str,
    *,
    data_dir: str | Path = "data/processed",
) -> tuple[pd.DataFrame, Path]:
    directory = Path(data_dir)
    for manifest_path in directory.glob("*.manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if manifest.get("sha256") != dataset_sha256:
            continue
        data_path = manifest_path.with_name(manifest_path.name.replace(".manifest.json", ".csv"))
        if not data_path.is_file() or sha256_file(data_path) != dataset_sha256:
            raise ValueError(f"El dataset de entrenamiento no supera SHA-256: {data_path}")
        frame = pd.read_csv(data_path, index_col="Date", parse_dates=["Date"])
        return frame.sort_index(), data_path
    raise FileNotFoundError(
        "No se encontró el dataset exacto usado para entrenar el modelo V3."
    )


def load_latest_sentiment_signal(
    root: str | Path,
    *,
    ticker: str,
    analyzer: str,
    decision_at: datetime,
) -> dict[str, Any] | None:
    """Devuelve la última señal registrada que ya existía al decidir."""
    candidates: list[tuple[pd.Timestamp, Path, dict[str, Any]]] = []
    ticker_dir = _safe_name(ticker)
    decision = pd.Timestamp(decision_at)
    if decision.tzinfo is None:
        raise ValueError("decision_at debe incluir zona horaria.")
    decision = decision.tz_convert("UTC")
    for path in Path(root).rglob("signals.json") if Path(root).exists() else ():
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
                timestamp = pd.Timestamp(signal["decision_at"])
                if timestamp.tzinfo is None:
                    continue
                timestamp = timestamp.tz_convert("UTC")
            except (KeyError, TypeError, ValueError):
                continue
            if timestamp <= decision:
                candidates.append((timestamp, path, signal))
    if not candidates:
        return None
    timestamp, path, signal = max(candidates, key=lambda item: item[0])
    return {
        **signal,
        "decision_at": timestamp.isoformat(),
        "artifact": str(path),
        "artifact_sha256": sha256_file(path),
    }
