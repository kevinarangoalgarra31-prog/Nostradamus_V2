"""Configuración validada del paper trading prospectivo de Nostradamus V6."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml


@dataclass(frozen=True)
class PaperTradingConfig:
    """Contrato operativo y límites de seguridad de la Fase 6."""

    version: str
    initial_capital: float
    probability_threshold: float
    sentiment_analyzer: str
    max_sentiment_age_hours: float
    max_decision_delay_minutes: float
    fractional_kelly: float
    max_asset_exposure: float
    max_total_exposure: float
    drift_warning_zscore: float
    drift_stop_zscore: float
    max_drawdown: float
    calibration_window: int
    minimum_calibration_rows: int
    max_recent_brier: float

    def __post_init__(self) -> None:
        if self.version != "6.0.0":
            raise ValueError("La configuración de paper trading debe declarar 6.0.0.")
        if self.initial_capital <= 0.0:
            raise ValueError("initial_capital debe ser positivo.")
        if not 0.0 < self.probability_threshold < 1.0:
            raise ValueError("probability_threshold debe estar entre 0 y 1.")
        if not self.sentiment_analyzer.strip():
            raise ValueError("sentiment_analyzer es obligatorio.")
        if self.max_sentiment_age_hours <= 0.0:
            raise ValueError("max_sentiment_age_hours debe ser positivo.")
        if self.max_decision_delay_minutes <= 0.0:
            raise ValueError("max_decision_delay_minutes debe ser positivo.")
        if not 0.0 < self.fractional_kelly <= 1.0:
            raise ValueError("fractional_kelly debe estar entre 0 y 1.")
        if not 0.0 < self.max_asset_exposure <= 1.0:
            raise ValueError("max_asset_exposure debe estar entre 0 y 1.")
        if not self.max_asset_exposure <= self.max_total_exposure <= 1.0:
            raise ValueError("max_total_exposure debe cubrir al menos un activo y no superar 1.")
        if not 0.0 < self.drift_warning_zscore < self.drift_stop_zscore:
            raise ValueError("Los umbrales de deriva deben ser positivos y crecientes.")
        if not 0.0 < self.max_drawdown < 1.0:
            raise ValueError("max_drawdown debe estar entre 0 y 1.")
        if self.calibration_window < 1 or self.minimum_calibration_rows < 1:
            raise ValueError("Las ventanas de calibración deben ser positivas.")
        if self.minimum_calibration_rows > self.calibration_window:
            raise ValueError("minimum_calibration_rows no puede superar calibration_window.")
        if not 0.0 < self.max_recent_brier <= 1.0:
            raise ValueError("max_recent_brier debe estar entre 0 y 1.")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "PaperTradingConfig":
        paper = payload.get("paper_trading", {})
        timing = payload.get("timing", {})
        risk = payload.get("risk", {})
        monitoring = payload.get("monitoring", {})
        return cls(
            version=str(paper.get("version", "6.0.0")),
            initial_capital=float(paper.get("initial_capital", 10_000.0)),
            probability_threshold=float(paper.get("probability_threshold", 0.50)),
            sentiment_analyzer=str(paper.get("sentiment_analyzer", "structured_llm")),
            max_sentiment_age_hours=float(timing.get("max_sentiment_age_hours", 6.0)),
            max_decision_delay_minutes=float(
                timing.get("max_decision_delay_minutes", 90.0)
            ),
            fractional_kelly=float(risk.get("fractional_kelly", 0.25)),
            max_asset_exposure=float(risk.get("max_asset_exposure", 0.25)),
            max_total_exposure=float(risk.get("max_total_exposure", 0.50)),
            drift_warning_zscore=float(monitoring.get("drift_warning_zscore", 4.0)),
            drift_stop_zscore=float(monitoring.get("drift_stop_zscore", 8.0)),
            max_drawdown=float(monitoring.get("max_drawdown", 0.20)),
            calibration_window=int(monitoring.get("calibration_window", 30)),
            minimum_calibration_rows=int(
                monitoring.get("minimum_calibration_rows", 20)
            ),
            max_recent_brier=float(monitoring.get("max_recent_brier", 0.35)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_paper_trading_config(path: str | Path) -> PaperTradingConfig:
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"No existe la configuración de paper trading: {config_path}")
    with config_path.open("r", encoding="utf-8") as stream:
        payload = yaml.safe_load(stream) or {}
    if not isinstance(payload, Mapping):
        raise ValueError("La raíz de paper trading debe ser un objeto YAML.")
    return PaperTradingConfig.from_mapping(payload)
