"""Utilidades para producir la demostración reproducible de Nostradamus V3."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.metrics import confusion_matrix

from src.config import ExperimentConfig, ModelingConfig
from src.data_pipeline.artifacts import safe_name
from src.data_pipeline.features import feature_columns

from .walk_forward import WalkForwardResult


def load_latest_processed_dataset(
    ticker: str,
    *,
    data_dir: str | Path = "data/processed",
    interval: str = "1d",
) -> tuple[pd.DataFrame, dict[str, Any], Path]:
    """Localiza el último dataset procesado válido y verifica su SHA-256."""
    directory = Path(data_dir)
    prefix = safe_name(f"{ticker}_{interval}_processed")
    candidates: list[tuple[str, Path, dict[str, Any]]] = []
    for manifest_path in directory.glob(f"{prefix}_*.manifest.json"):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("ticker") != ticker or manifest.get("dataset_kind") != "processed":
            continue
        candidates.append((str(manifest.get("created_at_utc", "")), manifest_path, manifest))
    if not candidates:
        raise FileNotFoundError(
            f"No hay un dataset procesado con manifiesto para {ticker}. Ejecuta prepare_data.py."
        )

    _, manifest_path, manifest = max(candidates, key=lambda item: item[0])
    data_path = manifest_path.with_name(manifest_path.name.replace(".manifest.json", ".csv"))
    if not data_path.is_file():
        raise FileNotFoundError(f"El manifiesto apunta a un CSV inexistente: {data_path}")
    digest = hashlib.sha256(data_path.read_bytes()).hexdigest()
    if digest != manifest.get("sha256"):
        raise ValueError(f"La huella SHA-256 no coincide para {data_path}.")

    frame = pd.read_csv(data_path, index_col=0, parse_dates=True)
    frame.index = pd.to_datetime(frame.index)
    frame.index.name = "Date"
    if "Target" not in frame.columns:
        raise ValueError(f"El dataset {data_path} no contiene Target.")
    frame["Target"] = frame["Target"].astype(int)
    return frame.sort_index(), manifest, data_path


def create_demo_figure(
    result: WalkForwardResult,
    output_path: str | Path,
    *,
    ticker: str,
    threshold: float,
) -> Path:
    """Genera un panel de diagnóstico exclusivamente fuera de muestra."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    predictions = result.predictions
    truth = predictions["y_true"].to_numpy(dtype=int)
    calibrated = predictions["probability_calibrated"].to_numpy(dtype=float)
    raw = predictions["probability_raw"].to_numpy(dtype=float)
    predicted = (calibrated >= threshold).astype(int)

    figure, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    figure.suptitle(f"Nostradamus V3 — diagnóstico fuera de muestra — {ticker}", fontsize=15)

    axes[0, 0].plot(predictions.index, calibrated, color="#1f4e78", linewidth=1.2)
    axes[0, 0].scatter(
        predictions.index,
        truth,
        c=np.where(truth == 1, "#2e8b57", "#b22222"),
        s=8,
        alpha=0.45,
        label="Resultado",
    )
    axes[0, 0].axhline(threshold, color="#555555", linestyle="--", linewidth=1)
    axes[0, 0].set_title("Probabilidad calibrada y resultado")
    axes[0, 0].set_ylim(-0.05, 1.05)
    axes[0, 0].set_ylabel("Probabilidad / clase")
    axes[0, 0].xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    axes[0, 0].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    axes[0, 0].tick_params(axis="x", rotation=30)

    for probabilities, label, color in (
        (raw, "XGBoost sin calibrar", "#d97904"),
        (calibrated, "XGBoost calibrado", "#1f4e78"),
    ):
        observed, predicted_probability = calibration_curve(
            truth, probabilities, n_bins=10, strategy="quantile"
        )
        axes[0, 1].plot(
            predicted_probability, observed, marker="o", linewidth=1.5, label=label, color=color
        )
    axes[0, 1].plot([0, 1], [0, 1], linestyle="--", color="#555555", label="Ideal")
    axes[0, 1].set_title("Curva de calibración")
    axes[0, 1].set_xlabel("Probabilidad estimada")
    axes[0, 1].set_ylabel("Frecuencia observada")
    axes[0, 1].legend(fontsize=8)

    matrix = confusion_matrix(truth, predicted, labels=[0, 1])
    axes[1, 0].imshow(matrix, cmap="Blues")
    axes[1, 0].set_title("Matriz de confusión")
    axes[1, 0].set_xlabel("Predicción")
    axes[1, 0].set_ylabel("Real")
    axes[1, 0].set_xticks([0, 1])
    axes[1, 0].set_yticks([0, 1])
    for row in range(2):
        for column in range(2):
            axes[1, 0].text(column, row, str(matrix[row, column]), ha="center", va="center")

    importances = pd.Series(
        result.final_model.feature_importances_, index=result.feature_names
    ).sort_values().tail(12)
    axes[1, 1].barh(importances.index, importances.values, color="#1f4e78")
    axes[1, 1].set_title("Importancia del modelo final")
    axes[1, 1].set_xlabel("Importancia XGBoost")

    figure.savefig(output, dpi=160)
    plt.close(figure)
    return output


def _metric(value: float | None) -> str:
    return "N/D" if value is None else f"{value:.4f}"


def build_demo_report(
    results: list[dict[str, Any]],
    *,
    experiment: ExperimentConfig,
    modeling: ModelingConfig,
    output_path: str | Path,
) -> Path:
    """Construye un informe Markdown autocontenido de la demostración V3."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    walk = modeling.walk_forward
    lines = [
        "# Demostración Nostradamus V3",
        "",
        "## Alcance",
        "",
        "Esta demostración evalúa exclusivamente el cerebro cuantitativo. No ejecuta operaciones, no usa sentimiento y no afirma rentabilidad. Las probabilidades se evalúan fuera de muestra mediante ventanas temporales sin mezcla aleatoria.",
        "",
        "## Diseño experimental",
        "",
        f"- Versión: `{modeling.version}`.",
        f"- Periodo solicitado: {experiment.data.start_date.isoformat()} a {(experiment.data.end_date.isoformat() if experiment.data.end_date else 'abierto')} (límite final exclusivo).",
        f"- Entrenamiento inicial: {walk.min_train_rows} observaciones.",
        f"- Calibración: {walk.calibration_rows} observaciones posteriores.",
        f"- Prueba: {walk.test_rows} observaciones posteriores por ventana.",
        f"- Máximo de ventanas: {walk.max_folds}.",
        f"- Selección interna: {modeling.inner_splits} particiones temporales.",
        f"- Umbral de clasificación: {modeling.decision_threshold:.2f}.",
        "",
    ]

    for item in results:
        ticker = item["ticker"]
        result: WalkForwardResult = item["result"]
        calibrated = result.metrics["xgboost_calibrated"]
        raw = result.metrics["xgboost_raw"]
        baseline = result.metrics["constant_baseline"]
        brier_better = calibrated["brier_score"] < baseline["brier_score"]
        calibration_better = calibrated["brier_score"] < raw["brier_score"]
        lines.extend(
            [
                f"## {ticker}",
                "",
                f"Evaluación agregada sobre {int(calibrated['samples'] or 0)} observaciones y {len(result.folds)} ventanas.",
                f"Periodo fuera de muestra: {result.predictions.index.min().date().isoformat()} a {result.predictions.index.max().date().isoformat()}.",
                "",
                "| Modelo | Accuracy | Accuracy balanceada | F1 | MCC | ROC AUC | Brier | Log loss | ECE |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
                f"| XGBoost calibrado | {_metric(calibrated['accuracy'])} | {_metric(calibrated['balanced_accuracy'])} | {_metric(calibrated['f1'])} | {_metric(calibrated['mcc'])} | {_metric(calibrated['roc_auc'])} | {_metric(calibrated['brier_score'])} | {_metric(calibrated['log_loss'])} | {_metric(calibrated['ece'])} |",
                f"| XGBoost sin calibrar | {_metric(raw['accuracy'])} | {_metric(raw['balanced_accuracy'])} | {_metric(raw['f1'])} | {_metric(raw['mcc'])} | {_metric(raw['roc_auc'])} | {_metric(raw['brier_score'])} | {_metric(raw['log_loss'])} | {_metric(raw['ece'])} |",
                f"| Línea base constante | {_metric(baseline['accuracy'])} | {_metric(baseline['balanced_accuracy'])} | {_metric(baseline['f1'])} | {_metric(baseline['mcc'])} | {_metric(baseline['roc_auc'])} | {_metric(baseline['brier_score'])} | {_metric(baseline['log_loss'])} | {_metric(baseline['ece'])} |",
                "",
                f"- Frente a la línea base, el Brier score del modelo calibrado {'mejora' if brier_better else 'no mejora'}.",
                f"- La calibración sigmoid {'reduce' if calibration_better else 'no reduce'} el Brier score respecto a la probabilidad cruda.",
                "- Estos resultados miden calidad predictiva; todavía no incluyen costos, posiciones ni métricas de trading.",
                "",
                f"![Diagnóstico {ticker}]({item['figure_relative']})",
                "",
                f"Artefactos: `{item['artifact_dir_relative']}`.",
                "",
            ]
        )

    lines.extend(
        [
            "## Criterio de lectura",
            "",
            "Una mejora aislada no basta para declarar superioridad. La fase 5 deberá comprobar estabilidad entre activos, sensibilidad a costos y efecto sobre retorno y drawdown. La V3 deja esas conclusiones abiertas deliberadamente.",
            "",
        ]
    )
    output.write_text("\n".join(lines), encoding="utf-8")
    return output
