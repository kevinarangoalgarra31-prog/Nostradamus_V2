"""Artefactos, gráfica e informe reproducible del backtesting V5."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.config import BacktestingConfig

from .engine import BacktestSuite


def _safe_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.]+", "_", value.strip())
    return normalized.strip("_") or "asset"


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


@dataclass(frozen=True)
class BacktestArtifacts:
    timeseries: Path
    metrics: Path
    cost_sensitivity: Path
    threshold_sensitivity: Path
    window_metrics: Path
    regime_metrics: Path
    figure: Path
    manifest: Path


def save_backtest_suite(
    suite: BacktestSuite,
    output_dir: str | Path,
    *,
    ticker: str,
    config: BacktestingConfig,
    commission_bps: float,
    slippage_bps: float,
    input_metadata: Mapping[str, Any],
) -> BacktestArtifacts:
    directory = Path(output_dir) / _safe_name(ticker)
    directory.mkdir(parents=True, exist_ok=True)
    paths = BacktestArtifacts(
        timeseries=directory / "backtest_timeseries.csv",
        metrics=directory / "metrics.json",
        cost_sensitivity=directory / "cost_sensitivity.csv",
        threshold_sensitivity=directory / "threshold_sensitivity.csv",
        window_metrics=directory / "window_metrics.csv",
        regime_metrics=directory / "regime_metrics.csv",
        figure=directory / "equity_curves.png",
        manifest=directory / "backtest_manifest.json",
    )

    timeseries = suite.base_frame[
        [
            "fold",
            "entry_open",
            "exit_open",
            "execution_return",
            "probability_raw",
            "probability_calibrated",
            "sentiment",
            "sentiment_status",
        ]
    ].copy()
    for name, result in suite.results.items():
        timeseries[f"{name}_position"] = result.frame["position"]
        timeseries[f"{name}_net_return"] = result.frame["net_return"]
        timeseries[f"{name}_equity"] = result.frame["equity"]
    timeseries.to_csv(paths.timeseries, index=True, lineterminator="\n")

    metrics = {
        "strategies": {name: dict(result.metrics) for name, result in suite.results.items()},
        "hybrid_status": dict(suite.hybrid_status),
    }
    _write_json(paths.metrics, metrics)
    suite.cost_sensitivity.to_csv(paths.cost_sensitivity, index=False, lineterminator="\n")
    suite.threshold_sensitivity.to_csv(
        paths.threshold_sensitivity, index=False, lineterminator="\n"
    )
    suite.window_metrics.to_csv(paths.window_metrics, index=False, lineterminator="\n")
    suite.regime_metrics.to_csv(paths.regime_metrics, index=False, lineterminator="\n")

    figure, axis = plt.subplots(figsize=(12, 6), constrained_layout=True)
    for name, result in suite.results.items():
        axis.plot(result.frame.index, result.frame["equity"], label=name, linewidth=1.2)
    axis.axhline(1.0, color="#555555", linewidth=0.8, linestyle="--")
    axis.set_title(f"Nostradamus V5 — capital acumulado OOS — {ticker}")
    axis.set_ylabel("Capital (inicio = 1.0)")
    axis.set_xlabel("Fecha de decisión")
    axis.legend(fontsize=8)
    figure.savefig(paths.figure, dpi=160)
    plt.close(figure)

    artifacts = {
        path.name: _hash(path)
        for path in (
            paths.timeseries,
            paths.metrics,
            paths.cost_sensitivity,
            paths.threshold_sensitivity,
            paths.window_metrics,
            paths.regime_metrics,
            paths.figure,
        )
    }
    _write_json(
        paths.manifest,
        {
            "schema_version": "5.0.0",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "ticker": ticker,
            "execution_convention": (
                "Señal al cierre t; entrada en apertura t+1; salida o rebalanceo en apertura t+2."
            ),
            "commission_bps_one_way": commission_bps,
            "slippage_bps_one_way": slippage_bps,
            "config": config.to_dict(),
            "inputs": dict(input_metadata),
            "hybrid_status": dict(suite.hybrid_status),
            "artifact_sha256": artifacts,
        },
    )
    return paths


def _format_metric(value: Any) -> str:
    return "N/D" if value is None or pd.isna(value) else f"{float(value):.4f}"


def build_v5_report(
    items: list[Mapping[str, Any]], output_path: str | Path
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Demostración Nostradamus V5",
        "",
        "## Alcance",
        "",
        "Backtesting fuera de muestra con ejecución causal en la siguiente apertura, costos por cambio de posición y liquidación final. No representa rentabilidad futura ni autoriza operar capital real.",
        "",
        "## Estrategias",
        "",
        "- B0: exposición larga continua en las ventanas OOS.",
        "- B1: regla Close > SMA-20 y RSI >= 50.",
        "- M1: probabilidad calibrada de XGBoost.",
        "- M2: M1 filtrado por sentimiento no negativo.",
        "- M3: Kelly fraccional limitado y modulado por sentimiento.",
        "",
    ]
    for item in items:
        lines.extend(
            [
                f"## {item['ticker']}",
                "",
                "| Estrategia | Retorno total | Sharpe | Sortino | Drawdown máximo | Exposición | Entradas | Costos |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for strategy, metrics in item["metrics"].items():
            lines.append(
                f"| {strategy} | {_format_metric(metrics['total_return'])} | "
                f"{_format_metric(metrics['sharpe'])} | {_format_metric(metrics['sortino'])} | "
                f"{_format_metric(metrics['max_drawdown'])} | {_format_metric(metrics['exposure'])} | "
                f"{int(metrics['entries'])} | {_format_metric(metrics['total_cost'])} |"
            )
        hybrid = item["hybrid_status"]
        lines.extend(
            [
                "",
                f"Cobertura de sentimiento alineada: {_format_metric(hybrid['coverage'])} "
                f"({hybrid['valid_rows']} de {hybrid['total_rows']} filas).",
                "",
            ]
        )
        if hybrid["status"] != "evaluable":
            lines.extend([f"M2 y M3: **no evaluables**. {hybrid['reason']}", ""])
        lines.extend(
            [
                f"![Curvas de capital de {item['ticker']}]({item['figure_relative']})",
                "",
            ]
        )
    lines.extend(
        [
            "## Lectura obligatoria",
            "",
            "Las comparaciones híbridas solo se publican cuando alcanzan la cobertura mínima configurada. La ausencia de noticias no se transforma en sentimiento neutral. Los archivos de sensibilidad muestran el efecto de costos, umbrales, calibración y ventanas walk-forward.",
            "",
        ]
    )
    output.write_text("\n".join(lines), encoding="utf-8")
    return output
