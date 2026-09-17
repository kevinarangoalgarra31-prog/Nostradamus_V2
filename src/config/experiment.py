"""Esquema y validación de la definición experimental de Nostradamus V2."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping

import yaml


def _as_date(value: Any, field_name: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"'{field_name}' debe usar el formato YYYY-MM-DD.") from exc


@dataclass(frozen=True)
class DataConfig:
    """Universo y periodo de los datos de mercado."""

    source: str
    tickers: tuple[str, ...]
    start_date: date
    end_date: date | None = None
    interval: str = "1d"
    auto_adjust: bool = False

    def __post_init__(self) -> None:
        if self.source != "yfinance":
            raise ValueError("La fase 2 solo admite 'yfinance' como fuente por ahora.")
        if not self.tickers or any(not item.strip() for item in self.tickers):
            raise ValueError("Debe declararse al menos un ticker no vacío.")
        if self.interval != "1d":
            raise ValueError("La primera versión experimental usa frecuencia diaria ('1d').")
        if self.end_date is not None and self.end_date <= self.start_date:
            raise ValueError("La fecha final debe ser posterior a la fecha inicial.")


@dataclass(frozen=True)
class TargetConfig:
    """Definición de la variable objetivo sin fuga temporal."""

    horizon_days: int = 1
    min_return: float = 0.0

    def __post_init__(self) -> None:
        if self.horizon_days < 1:
            raise ValueError("El horizonte objetivo debe ser de al menos un periodo.")


@dataclass(frozen=True)
class FeatureConfig:
    """Parámetros de las características técnicas causales."""

    sma_windows: tuple[int, ...] = (10, 20, 50)
    rsi_window: int = 14
    volatility_window: int = 20
    momentum_window: int = 10
    volume_window: int = 20
    ema_fast: int = 12
    ema_slow: int = 26
    ema_signal: int = 9

    def __post_init__(self) -> None:
        if not self.sma_windows:
            raise ValueError("Debe declararse al menos una ventana SMA.")
        windows = (*self.sma_windows, self.rsi_window, self.volatility_window,
                   self.momentum_window, self.volume_window, self.ema_fast,
                   self.ema_slow, self.ema_signal)
        if any(window < 2 for window in windows):
            raise ValueError("Todas las ventanas de características deben ser mayores o iguales a 2.")
        if len(set(self.sma_windows)) != len(self.sma_windows):
            raise ValueError("Las ventanas SMA no pueden repetirse.")
        if self.ema_fast >= self.ema_slow:
            raise ValueError("La EMA rápida debe ser menor que la EMA lenta.")


@dataclass(frozen=True)
class ValidationConfig:
    """Umbrales mínimos de calidad del dataset."""

    min_rows: int = 252
    max_missing_ratio: float = 0.02

    def __post_init__(self) -> None:
        if self.min_rows < 2:
            raise ValueError("El mínimo de filas debe ser mayor o igual a 2.")
        if not 0.0 <= self.max_missing_ratio <= 1.0:
            raise ValueError("max_missing_ratio debe estar entre 0 y 1.")


@dataclass(frozen=True)
class ExperimentConfig:
    """Contrato completo para ejecutar las fases 1 y 2."""

    name: str
    version: str
    random_seed: int
    data: DataConfig
    target: TargetConfig
    features: FeatureConfig
    validation: ValidationConfig
    commission_bps: float = 10.0
    slippage_bps: float = 5.0

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.version.strip():
            raise ValueError("El experimento requiere nombre y versión.")
        if self.commission_bps < 0 or self.slippage_bps < 0:
            raise ValueError("Los costos y el slippage no pueden ser negativos.")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ExperimentConfig":
        experiment = payload.get("experiment", {})
        data = payload.get("data", {})
        target = payload.get("target", {})
        features = payload.get("features", {})
        validation = payload.get("validation", {})
        execution = payload.get("execution", {})

        return cls(
            name=str(experiment.get("name", "nostradamus_v2")),
            version=str(experiment.get("version", "1.0")),
            random_seed=int(experiment.get("random_seed", 42)),
            data=DataConfig(
                source=str(data.get("source", "yfinance")),
            tickers=tuple(str(item) for item in data.get("tickers", ("BTC-USD",))),
                start_date=_as_date(data.get("start_date", "2020-01-01"), "start_date"),
                end_date=(
                    _as_date(data["end_date"], "end_date")
                    if data.get("end_date") is not None
                    else None
                ),
                interval=str(data.get("interval", "1d")),
                auto_adjust=bool(data.get("auto_adjust", False)),
            ),
            target=TargetConfig(
                horizon_days=int(target.get("horizon_days", 1)),
                min_return=float(target.get("min_return", 0.0)),
            ),
            features=FeatureConfig(
                sma_windows=tuple(int(item) for item in features.get("sma_windows", (10, 20, 50))),
                rsi_window=int(features.get("rsi_window", 14)),
                volatility_window=int(features.get("volatility_window", 20)),
                momentum_window=int(features.get("momentum_window", 10)),
                volume_window=int(features.get("volume_window", 20)),
                ema_fast=int(features.get("ema_fast", 12)),
                ema_slow=int(features.get("ema_slow", 26)),
                ema_signal=int(features.get("ema_signal", 9)),
            ),
            validation=ValidationConfig(
                min_rows=int(validation.get("min_rows", 252)),
                max_missing_ratio=float(validation.get("max_missing_ratio", 0.02)),
            ),
            commission_bps=float(execution.get("commission_bps", 10.0)),
            slippage_bps=float(execution.get("slippage_bps", 5.0)),
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["data"]["start_date"] = self.data.start_date.isoformat()
        result["data"]["end_date"] = (
            self.data.end_date.isoformat() if self.data.end_date else None
        )
        return result


def load_experiment_config(path: str | Path) -> ExperimentConfig:
    """Carga y valida una definición experimental YAML."""
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"No existe la configuración: {config_path}")
    with config_path.open("r", encoding="utf-8") as stream:
        payload = yaml.safe_load(stream) or {}
    if not isinstance(payload, Mapping):
        raise ValueError("La raíz de la configuración debe ser un objeto YAML.")
    return ExperimentConfig.from_mapping(payload)
