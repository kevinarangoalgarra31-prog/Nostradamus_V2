"""Genera la demostración cuantitativa reproducible de Nostradamus V3."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.config import load_experiment_config, load_modeling_config
from src.data_pipeline import feature_columns
from src.models.demo import (
    build_demo_report,
    create_demo_figure,
    load_latest_processed_dataset,
)
from src.models.walk_forward import WalkForwardEvaluator, save_walk_forward_result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Entrena y evalúa Nostradamus V3 mediante walk-forward temporal."
    )
    parser.add_argument("--config", default="config/experiment.yaml")
    parser.add_argument("--modeling-config", default="config/modeling_v3.yaml")
    parser.add_argument("--ticker", action="append", help="Ticker declarado; se puede repetir.")
    parser.add_argument("--output-dir", default="output/v3")
    return parser


def main() -> int:
    args = _parser().parse_args()
    experiment = load_experiment_config(args.config)
    modeling = load_modeling_config(args.modeling_config)
    tickers = tuple(args.ticker or experiment.data.tickers)
    unknown = sorted(set(tickers) - set(experiment.data.tickers))
    if unknown:
        raise ValueError("Tickers fuera del universo declarado: " + ", ".join(unknown))

    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    report_items = []
    summary = {"version": modeling.version, "tickers": {}}

    for ticker in tickers:
        print(f"\n=== Nostradamus V3: {ticker} ===")
        frame, dataset_manifest, data_path = load_latest_processed_dataset(
            ticker, interval=experiment.data.interval
        )
        features = feature_columns(frame)
        X = frame[features].astype(float)
        y = frame["Target"].astype(int)
        print(
            f"Dataset verificado: {data_path} | {len(frame)} filas | "
            f"{len(features)} características"
        )
        result = WalkForwardEvaluator(
            modeling, random_state=experiment.random_seed
        ).evaluate(X, y)

        ticker_dir = output_root / ticker.replace("-", "_")
        artifacts = save_walk_forward_result(
            result,
            ticker_dir,
            ticker=ticker,
            dataset_sha256=str(dataset_manifest["sha256"]),
            modeling_config=modeling,
        )
        figure = create_demo_figure(
            result,
            ticker_dir / "diagnostic.png",
            ticker=ticker,
            threshold=modeling.decision_threshold,
        )
        calibrated = result.metrics["xgboost_calibrated"]
        baseline = result.metrics["constant_baseline"]
        print(
            f"OOS: accuracy={calibrated['accuracy']:.4f} | "
            f"AUC={calibrated['roc_auc']:.4f} | Brier={calibrated['brier_score']:.4f} | "
            f"baseline Brier={baseline['brier_score']:.4f}"
        )
        report_items.append(
            {
                "ticker": ticker,
                "result": result,
                "figure_relative": figure.relative_to(output_root).as_posix(),
                "artifact_dir_relative": ticker_dir.relative_to(output_root).as_posix(),
            }
        )
        summary["tickers"][ticker] = {
            "dataset": str(data_path),
            "dataset_sha256": dataset_manifest["sha256"],
            "features": features,
            "metrics": result.metrics,
            "artifacts": {key: str(path) for key, path in artifacts.items()},
            "figure": str(figure),
        }

    report = build_demo_report(
        report_items,
        experiment=experiment,
        modeling=modeling,
        output_path=output_root / "DEMO_V3.md",
    )
    summary["report"] = str(report)
    (output_root / "run_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"\nDemostración generada en: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
