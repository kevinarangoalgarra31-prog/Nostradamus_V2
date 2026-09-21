"""CLI reproducible para adquirir, auditar y analizar titulares (Fase 4)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.config import load_experiment_config, load_sentiment_config
from src.sentiment import (
    CsvNewsProvider,
    GoogleNewsRssProvider,
    GroqCompletionClient,
    LexiconSentimentAnalyzer,
    StructuredLLMSentimentAnalyzer,
    aggregate_signal,
    audit_news,
    evaluate_assessments,
    parse_datetime_utc,
    save_sentiment_run,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Genera señales textuales auditables para Nostradamus V4."
    )
    parser.add_argument("--config", default="config/experiment.yaml")
    parser.add_argument("--sentiment-config", default="config/sentiment_v4.yaml")
    parser.add_argument("--ticker", action="append", help="Ticker declarado; se puede repetir.")
    parser.add_argument("--provider", choices=("csv", "google_news"))
    parser.add_argument("--input-csv", help="CSV histórico o etiquetado; implica proveedor csv.")
    parser.add_argument(
        "--decision-at",
        help="Instante ISO-8601 con zona horaria. Por defecto se usa el inicio de la ejecución.",
    )
    parser.add_argument(
        "--with-llm",
        action="store_true",
        help="Evalúa además con Groq; requiere GROQ_API_KEY y GROQ_MODEL o llm.model.",
    )
    parser.add_argument("--output-dir", default="output/v4")
    parser.add_argument(
        "--archive-run",
        action="store_true",
        help="Guarda en una carpeta UTC única y añade una entrada al índice acumulativo.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        help="Sobrescribe provider.max_items_per_asset para esta ejecución.",
    )
    parser.add_argument(
        "--llm-timeout",
        type=float,
        help="Tiempo máximo en segundos por solicitud LLM.",
    )
    parser.add_argument("--no-save", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    experiment = load_experiment_config(args.config)
    sentiment_config = load_sentiment_config(args.sentiment_config)
    tickers = tuple(args.ticker or experiment.data.tickers)
    unknown = sorted(set(tickers) - set(experiment.data.tickers))
    if unknown:
        raise ValueError("Tickers fuera del universo declarado: " + ", ".join(unknown))

    started_at = datetime.now(timezone.utc)
    requested_decision = parse_datetime_utc(args.decision_at) if args.decision_at else None
    provider_name = args.provider or ("csv" if args.input_csv else sentiment_config.provider)
    if provider_name == "csv":
        csv_path = args.input_csv or sentiment_config.csv_path
        if not csv_path:
            raise ValueError("El proveedor CSV requiere --input-csv o provider.csv_path.")
        provider = CsvNewsProvider(csv_path)
    else:
        max_items = args.max_items or sentiment_config.max_items_per_asset
        if max_items < 1:
            raise ValueError("--max-items debe ser mayor o igual a 1.")
        provider = GoogleNewsRssProvider(
            query_terms=sentiment_config.query_terms,
            max_items=max_items,
            lookback_hours=sentiment_config.lookback_hours,
        )

    analyzers: list[object] = [
        LexiconSentimentAnalyzer(
            version=sentiment_config.lexicon_version,
            positive_threshold=sentiment_config.positive_threshold,
            negative_threshold=sentiment_config.negative_threshold,
        )
    ]
    if args.with_llm:
        if sentiment_config.llm_provider != "groq":
            raise ValueError("Esta versión solo implementa el proveedor LLM 'groq'.")
        completion = GroqCompletionClient(
            model=sentiment_config.llm_model,
            timeout_seconds=args.llm_timeout or sentiment_config.request_timeout_seconds,
            max_completion_tokens=sentiment_config.max_completion_tokens,
        )
        analyzers.append(
            StructuredLLMSentimentAnalyzer(
                completion,
                model_name=completion.model,
                model_version=completion.model,
                prompt_version=sentiment_config.prompt_version,
            )
        )

    collections = {}
    for ticker in tickers:
        print(f"[Fase 4] Adquiriendo titulares para {ticker}...", file=sys.stderr, flush=True)
        collections[ticker] = provider.collect(
            ticker, started_at if provider_name == "csv" else None
        )
    # En vivo, la decisión se fija después de recibir todos los feeds. Así una
    # captura nunca queda artificialmente fechada antes de la consulta de red.
    decision_at = requested_decision or datetime.now(timezone.utc)

    run_id = started_at.strftime("%Y%m%dT%H%M%S_%fZ")
    output_root = Path(args.output_dir)
    run_output = (
        output_root
        / started_at.strftime("%Y")
        / started_at.strftime("%m")
        / started_at.strftime("%d")
        / run_id
        if args.archive_run
        else output_root
    )
    run_summary: dict[str, object] = {
        "phase": 4,
        "version": sentiment_config.version,
        "run_id": run_id,
        "decision_at": decision_at.isoformat(),
        "provider": provider_name,
        "output_dir": str(run_output),
        "assets": {},
    }
    for ticker in tickers:
        collection = collections[ticker]
        batch = audit_news(
            collection.items,
            asset=ticker,
            decision_at=decision_at,
            lookback_hours=sentiment_config.lookback_hours,
            allowed_languages=sentiment_config.allowed_languages,
            provider_issues=collection.issues,
        )
        assessments = []
        signals = []
        for analyzer in analyzers:
            analyzer_name = getattr(analyzer, "name")
            current = []
            for position, item in enumerate(batch.accepted, 1):
                print(
                    f"[Fase 4] {ticker} · {analyzer_name} · {position}/{len(batch.accepted)}",
                    file=sys.stderr,
                    flush=True,
                )
                current.append(analyzer.analyze(item, created_at=started_at))
            assessments.extend(current)
            model_version = getattr(analyzer, "model_version")
            if hasattr(analyzer, "prompt_version"):
                model_version = f"{model_version}|{getattr(analyzer, 'prompt_version')}"
            signals.append(
                aggregate_signal(
                    batch.accepted,
                    current,
                    asset=ticker,
                    decision_at=decision_at,
                    analyzer=analyzer_name,
                    model_version=model_version,
                    min_headlines=sentiment_config.min_headlines,
                    min_relevance=sentiment_config.min_relevance,
                    positive_threshold=sentiment_config.positive_threshold,
                    negative_threshold=sentiment_config.negative_threshold,
                )
            )
        evaluation = evaluate_assessments(batch.accepted, assessments)
        artifacts = None
        if not args.no_save:
            artifacts = save_sentiment_run(
                run_output,
                batch=batch,
                assessments=assessments,
                signals=signals,
                evaluation=evaluation,
                config=sentiment_config.to_dict(),
                provider=provider_name,
            )
        run_summary["assets"][ticker] = {
            "audit": dict(batch.metrics),
            "signals": [signal.to_dict() for signal in signals],
            "evaluation": evaluation,
            "artifacts": (
                {name: str(path) for name, path in vars(artifacts).items()}
                if artifacts
                else None
            ),
        }

    if not args.no_save:
        run_output.mkdir(parents=True, exist_ok=True)
        (run_output / "run_summary.json").write_text(
            json.dumps(run_summary, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        if args.archive_run:
            output_root.mkdir(parents=True, exist_ok=True)
            index_entry = {
                "run_id": run_id,
                "created_at": started_at.isoformat(),
                "decision_at": decision_at.isoformat(),
                "provider": provider_name,
                "with_llm": args.with_llm,
                "tickers": list(tickers),
                "run_summary": str(run_output / "run_summary.json"),
            }
            with (output_root / "collection_index.jsonl").open(
                "a", encoding="utf-8", newline=""
            ) as stream:
                stream.write(json.dumps(index_entry, ensure_ascii=False) + "\n")
    print(json.dumps(run_summary, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
