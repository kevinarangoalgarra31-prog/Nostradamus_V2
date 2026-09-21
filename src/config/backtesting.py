"""Configuración validada del backtesting comparativo de Nostradamus V5."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml


@dataclass(frozen=True)
class BacktestingConfig:
    """Contrato de ejecución y riesgo común para todas las estrategias."""

    version: str
    annualization_periods: int
    probability_threshold: float
    technical_sma_column: str
    technical_rsi_column: str
    technical_rsi_threshold: float
    fractional_kelly: float
    max_exposure: float
    sentiment_analyzer: str
    minimum_sentiment_coverage: float
    minimum_hybrid_rows: int
    cost_multipliers: tuple[float, ...]
    threshold_grid: tuple[float, ...]
    regime_volatility_column: str

    def __post_init__(self) -> None:
        if self.version != "5.0.0":
            raise ValueError("La configuración de backtesting debe declarar la versión 5.0.0.")
        if self.annualization_periods < 2:
            raise ValueError("annualization_periods debe ser mayor o igual a 2.")
        if not 0.0 < self.probability_threshold < 1.0:
            raise ValueError("probability_threshold debe estar entre 0 y 1.")
        if not self.technical_sma_column or not self.technical_rsi_column:
            raise ValueError("Las columnas de la regla técnica son obligatorias.")
        if not 0.0 < self.fractional_kelly <= 1.0:
            raise ValueError("fractional_kelly debe estar entre 0 y 1.")
        if not 0.0 < self.max_exposure <= 1.0:
            raise ValueError("max_exposure debe estar entre 0 y 1.")
        if not 0.0 <= self.minimum_sentiment_coverage <= 1.0:
            raise ValueError("minimum_sentiment_coverage debe estar entre 0 y 1.")
        if self.minimum_hybrid_rows < 1:
            raise ValueError("minimum_hybrid_rows debe ser positivo.")
        if not self.cost_multipliers or any(value < 0 for value in self.cost_multipliers):
            raise ValueError("Los multiplicadores de costos deben ser no negativos.")
        if not self.threshold_grid or any(not 0.0 < value < 1.0 for value in self.threshold_grid):
            raise ValueError("Los umbrales de sensibilidad deben estar entre 0 y 1.")
        if not self.regime_volatility_column.strip():
            raise ValueError("regime_volatility_column es obligatoria.")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "BacktestingConfig":
        backtest = payload.get("backtest", {})
        technical = payload.get("technical_baseline", {})
        risk = payload.get("risk", {})
        sentiment = payload.get("sentiment", {})
        sensitivity = payload.get("sensitivity", {})
        return cls(
            version=str(backtest.get("version", "5.0.0")),
            annualization_periods=int(backtest.get("annualization_periods", 365)),
            probability_threshold=float(backtest.get("probability_threshold", 0.50)),
            technical_sma_column=str(technical.get("sma_column", "SMA_20")),
            technical_rsi_column=str(technical.get("rsi_column", "RSI_14")),
            technical_rsi_threshold=float(technical.get("rsi_threshold", 50.0)),
            fractional_kelly=float(risk.get("fractional_kelly", 0.25)),
            max_exposure=float(risk.get("max_exposure", 0.25)),
            sentiment_analyzer=str(sentiment.get("analyzer", "structured_llm")),
            minimum_sentiment_coverage=float(sentiment.get("minimum_coverage", 0.80)),
            minimum_hybrid_rows=int(sentiment.get("minimum_rows", 30)),
            cost_multipliers=tuple(
                float(value) for value in sensitivity.get("cost_multipliers", (0.0, 1.0, 2.0))
            ),
            threshold_grid=tuple(
                float(value) for value in sensitivity.get("probability_thresholds", (0.45, 0.50, 0.55))
            ),
            regime_volatility_column=str(
                sensitivity.get("regime_volatility_column", "Volatilidad_20")
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["cost_multipliers"] = list(self.cost_multipliers)
        result["threshold_grid"] = list(self.threshold_grid)
        return result


def load_backtesting_config(path: str | Path) -> BacktestingConfig:
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"No existe la configuración de backtesting: {config_path}")
    with config_path.open("r", encoding="utf-8") as stream:
        payload = yaml.safe_load(stream) or {}
    if not isinstance(payload, Mapping):
        raise ValueError("La raíz de backtesting debe ser un objeto YAML.")
    return BacktestingConfig.from_mapping(payload)
