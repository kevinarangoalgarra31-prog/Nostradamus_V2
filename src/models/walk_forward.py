"""Entrenamiento, calibración y evaluación walk-forward de Nostradamus V3."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
    matthews_corrcoef,
)
from sklearn.model_selection import ParameterGrid, TimeSeriesSplit

from src.config import ModelingConfig


EPSILON = 1e-6


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def expected_calibration_error(
    y_true: Iterable[int], probabilities: Iterable[float], bins: int = 10
) -> float:
    """Calcula ECE con intervalos uniformes de probabilidad."""
    truth = np.asarray(list(y_true), dtype=int)
    probs = np.asarray(list(probabilities), dtype=float)
    boundaries = np.linspace(0.0, 1.0, bins + 1)
    total = len(truth)
    if total == 0:
        raise ValueError("No se puede calcular ECE sin observaciones.")
    error = 0.0
    for index in range(bins):
        lower, upper = boundaries[index], boundaries[index + 1]
        mask = (probs >= lower) & (probs < upper if index < bins - 1 else probs <= upper)
        if not mask.any():
            continue
        error += mask.mean() * abs(probs[mask].mean() - truth[mask].mean())
    return float(error)


def binary_metrics(
    y_true: Iterable[int],
    probabilities: Iterable[float],
    *,
    threshold: float = 0.5,
) -> dict[str, float | None]:
    """Métricas predictivas y probabilísticas para una secuencia fuera de muestra."""
    truth = np.asarray(list(y_true), dtype=int)
    probs = np.clip(np.asarray(list(probabilities), dtype=float), EPSILON, 1.0 - EPSILON)
    predicted = (probs >= threshold).astype(int)
    auc = roc_auc_score(truth, probs) if len(np.unique(truth)) == 2 else None
    return {
        "accuracy": _as_float(accuracy_score(truth, predicted)),
        "balanced_accuracy": _as_float(balanced_accuracy_score(truth, predicted)),
        "precision": _as_float(precision_score(truth, predicted, zero_division=0)),
        "recall": _as_float(recall_score(truth, predicted, zero_division=0)),
        "f1": _as_float(f1_score(truth, predicted, zero_division=0)),
        "mcc": _as_float(matthews_corrcoef(truth, predicted)),
        "roc_auc": _as_float(auc),
        "brier_score": _as_float(brier_score_loss(truth, probs)),
        "log_loss": _as_float(log_loss(truth, probs, labels=[0, 1])),
        "ece": expected_calibration_error(truth, probs),
        "positive_rate": float(truth.mean()),
        "predicted_positive_rate": float(predicted.mean()),
        "samples": float(len(truth)),
    }


class SigmoidCalibrator:
    """Calibración de Platt sobre el logit de la probabilidad base."""

    def __init__(self, random_state: int = 42):
        self.random_state = random_state
        self.model: LogisticRegression | None = None
        self.identity = False

    @staticmethod
    def _logit(probabilities: np.ndarray) -> np.ndarray:
        clipped = np.clip(probabilities, EPSILON, 1.0 - EPSILON)
        return np.log(clipped / (1.0 - clipped)).reshape(-1, 1)

    def fit(self, probabilities: Iterable[float], y_true: Iterable[int]) -> "SigmoidCalibrator":
        probs = np.asarray(list(probabilities), dtype=float)
        truth = np.asarray(list(y_true), dtype=int)
        if len(probs) != len(truth) or len(probs) == 0:
            raise ValueError("Probabilidades y etiquetas de calibración deben tener igual longitud.")
        if len(np.unique(truth)) < 2:
            self.identity = True
            self.model = None
            return self
        self.model = LogisticRegression(
            solver="lbfgs",
            random_state=self.random_state,
            max_iter=1_000,
        )
        self.model.fit(self._logit(probs), truth)
        self.identity = False
        return self

    def transform(self, probabilities: Iterable[float]) -> np.ndarray:
        probs = np.asarray(list(probabilities), dtype=float)
        if self.identity:
            return np.clip(probs, EPSILON, 1.0 - EPSILON)
        if self.model is None:
            raise RuntimeError("El calibrador debe ajustarse antes de transformar probabilidades.")
        return self.model.predict_proba(self._logit(probs))[:, 1]

    def to_dict(self) -> dict[str, Any]:
        if self.identity:
            return {"method": "identity", "reason": "single_class_calibration_window"}
        if self.model is None:
            raise RuntimeError("No hay un calibrador ajustado.")
        return {
            "method": "sigmoid",
            "coefficient": float(self.model.coef_[0, 0]),
            "intercept": float(self.model.intercept_[0]),
            "input": "logit(raw_probability)",
        }


@dataclass
class WalkForwardResult:
    predictions: pd.DataFrame
    folds: list[dict[str, Any]]
    metrics: dict[str, dict[str, float | None]]
    final_model: xgb.XGBClassifier
    final_calibrator: SigmoidCalibrator
    final_parameters: dict[str, Any]
    feature_names: list[str]
    training_start: str
    training_end: str


class WalkForwardEvaluator:
    """Ejecuta selección interna, calibración posterior y prueba temporal externa."""

    def __init__(self, config: ModelingConfig, random_state: int = 42):
        self.config = config
        self.random_state = random_state

    def _new_model(self, parameters: dict[str, Any]) -> xgb.XGBClassifier:
        return xgb.XGBClassifier(
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=self.random_state,
            n_jobs=1,
            tree_method="hist",
            verbosity=0,
            **parameters,
        )

    def _select_parameters(
        self, X_train: pd.DataFrame, y_train: pd.Series
    ) -> tuple[dict[str, Any], float]:
        splitter = TimeSeriesSplit(n_splits=self.config.inner_splits)
        best_parameters: dict[str, Any] | None = None
        best_loss = float("inf")

        for parameters in ParameterGrid(self.config.parameter_grid):
            losses: list[float] = []
            for fit_indices, validation_indices in splitter.split(X_train):
                y_fit = y_train.iloc[fit_indices].astype(int)
                if y_fit.nunique() < 2:
                    continue
                model = self._new_model(parameters)
                model.fit(X_train.iloc[fit_indices], y_fit)
                probabilities = model.predict_proba(X_train.iloc[validation_indices])[:, 1]
                losses.append(
                    float(
                        log_loss(
                            y_train.iloc[validation_indices].astype(int),
                            probabilities,
                            labels=[0, 1],
                        )
                    )
                )
            if losses:
                mean_loss = float(np.mean(losses))
                if mean_loss < best_loss:
                    best_loss = mean_loss
                    best_parameters = dict(parameters)

        if best_parameters is None:
            raise ValueError("No fue posible seleccionar hiperparámetros con las ventanas disponibles.")
        return best_parameters, best_loss

    def _windows(self, rows: int) -> list[tuple[slice, slice, slice]]:
        walk = self.config.walk_forward
        windows: list[tuple[slice, slice, slice]] = []
        train_end = walk.min_train_rows
        while len(windows) < walk.max_folds:
            calibration_end = train_end + walk.calibration_rows
            test_end = calibration_end + walk.test_rows
            if test_end > rows:
                break
            windows.append(
                (
                    slice(0, train_end),
                    slice(train_end, calibration_end),
                    slice(calibration_end, test_end),
                )
            )
            train_end += walk.step_rows
        if not windows:
            required = walk.min_train_rows + walk.calibration_rows + walk.test_rows
            raise ValueError(f"Se requieren al menos {required} filas para una ventana walk-forward.")
        return windows

    def evaluate(
        self,
        X: pd.DataFrame,
        y: pd.Series,
    ) -> WalkForwardResult:
        if len(X) != len(y) or not X.index.equals(y.index):
            raise ValueError("Características y objetivo deben compartir longitud e índice.")
        if X.isna().any().any() or y.isna().any():
            raise ValueError("El modelado no admite valores faltantes.")
        if y.astype(int).nunique() < 2:
            raise ValueError("El objetivo debe contener ambas clases.")

        fold_records: list[dict[str, Any]] = []
        prediction_frames: list[pd.DataFrame] = []
        for fold_number, (train_slice, calibration_slice, test_slice) in enumerate(
            self._windows(len(X)), start=1
        ):
            X_train, y_train = X.iloc[train_slice], y.iloc[train_slice].astype(int)
            X_cal, y_cal = X.iloc[calibration_slice], y.iloc[calibration_slice].astype(int)
            X_test, y_test = X.iloc[test_slice], y.iloc[test_slice].astype(int)

            parameters, tuning_loss = self._select_parameters(X_train, y_train)
            model = self._new_model(parameters)
            model.fit(X_train, y_train)
            raw_calibration = model.predict_proba(X_cal)[:, 1]
            calibrator = SigmoidCalibrator(self.random_state).fit(raw_calibration, y_cal)

            raw_test = model.predict_proba(X_test)[:, 1]
            calibrated_test = calibrator.transform(raw_test)
            baseline_probability = float(y_train.mean())
            baseline_test = np.full(len(y_test), baseline_probability)
            predictions = pd.DataFrame(
                {
                    "fold": fold_number,
                    "y_true": y_test.to_numpy(dtype=int),
                    "probability_raw": raw_test,
                    "probability_calibrated": calibrated_test,
                    "probability_baseline": baseline_test,
                    "prediction": (
                        calibrated_test >= self.config.decision_threshold
                    ).astype(int),
                },
                index=X_test.index,
            )
            predictions.index.name = "Date"
            prediction_frames.append(predictions)
            fold_records.append(
                {
                    "fold": fold_number,
                    "train_start": X_train.index.min().isoformat(),
                    "train_end": X_train.index.max().isoformat(),
                    "calibration_start": X_cal.index.min().isoformat(),
                    "calibration_end": X_cal.index.max().isoformat(),
                    "test_start": X_test.index.min().isoformat(),
                    "test_end": X_test.index.max().isoformat(),
                    "train_rows": len(X_train),
                    "calibration_rows": len(X_cal),
                    "test_rows": len(X_test),
                    "tuning_log_loss": tuning_loss,
                    "parameters": parameters,
                    "calibrator": calibrator.to_dict(),
                    "metrics_raw": binary_metrics(y_test, raw_test),
                    "metrics_calibrated": binary_metrics(
                        y_test,
                        calibrated_test,
                        threshold=self.config.decision_threshold,
                    ),
                }
            )

        all_predictions = pd.concat(prediction_frames).sort_index()
        if all_predictions.index.duplicated().any():
            raise RuntimeError("Las ventanas de prueba walk-forward se solapan.")
        metrics = {
            "xgboost_calibrated": binary_metrics(
                all_predictions["y_true"],
                all_predictions["probability_calibrated"],
                threshold=self.config.decision_threshold,
            ),
            "xgboost_raw": binary_metrics(
                all_predictions["y_true"], all_predictions["probability_raw"]
            ),
            "constant_baseline": binary_metrics(
                all_predictions["y_true"], all_predictions["probability_baseline"]
            ),
        }

        final_calibration_rows = self.config.walk_forward.calibration_rows
        final_train_end = len(X) - final_calibration_rows
        X_final_train, y_final_train = X.iloc[:final_train_end], y.iloc[:final_train_end].astype(int)
        X_final_cal = X.iloc[final_train_end:]
        y_final_cal = y.iloc[final_train_end:].astype(int)
        final_parameters, _ = self._select_parameters(X_final_train, y_final_train)
        final_model = self._new_model(final_parameters)
        final_model.fit(X_final_train, y_final_train)
        final_raw_cal = final_model.predict_proba(X_final_cal)[:, 1]
        final_calibrator = SigmoidCalibrator(self.random_state).fit(final_raw_cal, y_final_cal)

        return WalkForwardResult(
            predictions=all_predictions,
            folds=fold_records,
            metrics=metrics,
            final_model=final_model,
            final_calibrator=final_calibrator,
            final_parameters=final_parameters,
            feature_names=list(X.columns),
            training_start=X.index.min().isoformat(),
            training_end=X.index.max().isoformat(),
        )


def save_walk_forward_result(
    result: WalkForwardResult,
    output_dir: str | Path,
    *,
    ticker: str,
    dataset_sha256: str,
    modeling_config: ModelingConfig,
) -> dict[str, Path]:
    """Persiste predicciones, métricas, modelo y calibración de una ejecución V3."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    predictions_path = directory / "predictions_oos.csv"
    folds_path = directory / "folds.json"
    metrics_path = directory / "metrics.json"
    model_path = directory / "xgboost_v3.json"
    calibrator_path = directory / "calibrator.json"
    manifest_path = directory / "model_manifest.json"

    result.predictions.to_csv(predictions_path, lineterminator="\n")
    folds_path.write_text(
        json.dumps(result.folds, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    metrics_path.write_text(
        json.dumps(result.metrics, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    result.final_model.save_model(model_path)
    calibrator_path.write_text(
        json.dumps(result.final_calibrator.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "project_version": "3.0.0",
        "ticker": ticker,
        "dataset_sha256": dataset_sha256,
        "training_start": result.training_start,
        "training_end": result.training_end,
        "features": result.feature_names,
        "final_parameters": result.final_parameters,
        "calibration": result.final_calibrator.to_dict(),
        "modeling_config": modeling_config.to_dict(),
        "artifacts": {
            "predictions": predictions_path.name,
            "folds": folds_path.name,
            "metrics": metrics_path.name,
            "model": model_path.name,
            "calibrator": calibrator_path.name,
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    return {
        "predictions": predictions_path,
        "folds": folds_path,
        "metrics": metrics_path,
        "model": model_path,
        "calibrator": calibrator_path,
        "manifest": manifest_path,
    }
