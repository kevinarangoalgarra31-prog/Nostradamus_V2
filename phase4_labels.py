"""Construye una cola de etiquetado humano y calcula métricas cuando haya etiquetas."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.sentiment import (
    build_labeling_queue,
    evaluate_labeling_queue,
    save_label_evaluation,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gestiona etiquetas humanas de la Fase 4.")
    parser.add_argument("--history-root", default="output/v4_history")
    parser.add_argument("--queue", default="data/labels/phase4_labeling_queue.csv")
    parser.add_argument("--evaluation", default="output/v4_history/label_evaluation.json")
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    return parser


def main() -> int:
    args = _parser().parse_args()
    queue = build_labeling_queue(
        args.history_root,
        args.queue,
        sample_size=args.sample_size,
        random_seed=args.seed,
    )
    evaluation = evaluate_labeling_queue(queue)
    save_label_evaluation(queue, args.evaluation)
    print(
        json.dumps(
            {"queue": str(Path(queue)), "evaluation": args.evaluation, **evaluation},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
