"""Configuración de entrenamiento y evaluación cuantitativa para Nostradamus V3."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml


@dataclass(frozen=True)
class WalkForwardConfig:
    """Tamaños de las ventanas temporales del experimento externo."""

    min_train_rows: int = 900
    calibration_rows: int = 180
    test_rows: int = 180
    step_rows: int = 180
    max_folds: int = 5

    def __post_init__(self) -> None:
        values = (
            self.min_train_rows,
            self.calibration_rows,
            self.test_rows,
            self.step_rows,
            self.max_folds,
        )
        if any(value < 1 for value in values):
            raise ValueError("Las ventanas walk-forward deben contener valores positivos.")
        if self.step_rows < self.test_rows:
            raise ValueError("step_rows debe ser mayor o igual a test_rows para evitar pruebas solapadas.")


@dataclass(frozen=True)
class ModelingConfig:
    """Contrato reproducible de modelado para la versión 3."""

    version: str
    decision_threshold: float
    calibration_method: str
    inner_splits: int
    walk_forward: WalkForwardConfig
    parameter_grid: dict[str, tuple[Any, ...]]

    def __post_init__(self) -> None:
        if self.version != "3.0.0":
            raise ValueError("La configuración de esta fase debe declarar la versión 3.0.0.")
        if not 0.0 < self.decision_threshold < 1.0:
            raise ValueError("decision_threshold debe estar entre 0 y 1.")
        if self.calibration_method != "sigmoid":
            raise ValueError("La V3 implementa calibración sigmoid (Platt scaling).")
        if self.inner_splits < 2:
            raise ValueError("inner_splits debe ser al menos 2.")
        if not self.parameter_grid or any(not values for values in self.parameter_grid.values()):
            raise ValueError("La cuadrícula de hiperparámetros no puede estar vacía.")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ModelingConfig":
        model = payload.get("modeling", {})
        walk = payload.get("walk_forward", {})
        grid = payload.get("parameter_grid", {})
        return cls(
            version=str(model.get("version", "3.0.0")),
            decision_threshold=float(model.get("decision_threshold", 0.5)),
            calibration_method=str(model.get("calibration_method", "sigmoid")),
            inner_splits=int(model.get("inner_splits", 3)),
            walk_forward=WalkForwardConfig(
                min_train_rows=int(walk.get("min_train_rows", 900)),
                calibration_rows=int(walk.get("calibration_rows", 180)),
                test_rows=int(walk.get("test_rows", 180)),
                step_rows=int(walk.get("step_rows", 180)),
                max_folds=int(walk.get("max_folds", 5)),
            ),
            parameter_grid={
                str(key): tuple(values if isinstance(values, list) else [values])
                for key, values in grid.items()
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_modeling_config(path: str | Path) -> ModelingConfig:
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"No existe la configuración de modelado: {config_path}")
    with config_path.open("r", encoding="utf-8") as stream:
        payload = yaml.safe_load(stream) or {}
    if not isinstance(payload, Mapping):
        raise ValueError("La raíz de la configuración de modelado debe ser un objeto YAML.")
    return ModelingConfig.from_mapping(payload)
