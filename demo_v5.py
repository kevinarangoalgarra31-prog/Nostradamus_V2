"""CLI de la Fase 5: backtesting comparativo, ablaciones y sensibilidad."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.backtesting import (
    load_v5_inputs,
    prepare_backtest_frame,
    run_backtest_suite,
    save_backtest_suite,
)
from src.backtesting.artifacts import build_v5_report
from src.config import load_backtesting_config, load_experiment_config


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ejecuta el backtesting causal y comparativo de Nostradamus V5."
    )
    parser.add_argument("--config", default="config/experiment.yaml")
    parser.add_argument("--backtesting-config", default="config/backtesting_v5.yaml")
    parser.add_argument("--ticker", action="append", help="Ticker declarado; se puede repetir.")
    parser.add_argument("--sentiment-root", default="output/v4_history")
    parser.add_argument("--output-dir", default="output/v5")
    return parser


def main() -> int:
    args = _parser().parse_args()
    experiment = load_experiment_config(args.config)
    config = load_backtesting_config(args.backtesting_config)
    tickers = tuple(args.ticker or experiment.data.tickers)
    unknown = sorted(set(tickers) - set(experiment.data.tickers))
    if unknown:
        raise ValueError("Tickers fuera del universo declarado: " + ", ".join(unknown))

    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    report_items = []
    summary: dict[str, object] = {"version": config.version, "tickers": {}}
    for ticker in tickers:
        print(f"\n=== Nostradamus V5: {ticker} ===", flush=True)
        bundle = load_v5_inputs(
            ticker,
            interval=experiment.data.interval,
            sentiment_root=args.sentiment_root,
            sentiment_analyzer=config.sentiment_analyzer,
        )
        frame = prepare_backtest_frame(bundle.market, bundle.predictions, bundle.sentiment)
        suite = run_backtest_suite(
            frame,
            config,
            commission_bps=experiment.commission_bps,
            slippage_bps=experiment.slippage_bps,
        )
        artifacts = save_backtest_suite(
            suite,
            output_root,
            ticker=ticker,
            config=config,
            commission_bps=experiment.commission_bps,
            slippage_bps=experiment.slippage_bps,
            input_metadata=bundle.metadata,
        )
        metrics = {name: dict(result.metrics) for name, result in suite.results.items()}
        print(
            f"OOS={len(frame)} | sentimiento={suite.hybrid_status['coverage']:.1%} | "
            f"híbrido={suite.hybrid_status['status']}",
            flush=True,
        )
        report_items.append(
            {
                "ticker": ticker,
                "metrics": metrics,
                "hybrid_status": dict(suite.hybrid_status),
                "figure_relative": artifacts.figure.relative_to(output_root).as_posix(),
            }
        )
        summary["tickers"][ticker] = {
            "metrics": metrics,
            "hybrid_status": dict(suite.hybrid_status),
            "inputs": bundle.metadata,
            "artifacts": {name: str(path) for name, path in vars(artifacts).items()},
        }
    report = build_v5_report(report_items, output_root / "DEMO_V5.md")
    summary["report"] = str(report)
    (output_root / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"\nInforme generado: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
