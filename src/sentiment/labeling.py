"""Cola reproducible de etiquetado humano y evaluación de analizadores."""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path
from typing import Any


QUEUE_FIELDS = (
    "news_id",
    "asset",
    "published_at",
    "source",
    "title",
    "url",
    "lexicon_sentiment",
    "llm_sentiment",
    "manual_label",
    "label_notes",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return [dict(row) for row in csv.DictReader(stream)]


def _valid_label(value: Any) -> int | None:
    try:
        label = int(value)
    except (TypeError, ValueError):
        return None
    return label if label in {-1, 0, 1} else None


def build_labeling_queue(
    history_root: str | Path,
    output_path: str | Path,
    *,
    sample_size: int = 100,
    random_seed: int = 42,
) -> Path:
    """Muestrea titulares únicos y conserva etiquetas humanas ya ingresadas."""
    if sample_size < 1:
        raise ValueError("sample_size debe ser positivo.")
    root = Path(history_root)
    output = Path(output_path)
    previous = {row.get("news_id", ""): row for row in _read_csv(output)}
    news: dict[str, dict[str, str]] = {}
    assessments: dict[str, dict[str, str]] = {}
    for path in root.rglob("headlines.csv") if root.exists() else ():
        for row in _read_csv(path):
            news_id = row.get("news_id", "")
            if news_id:
                news[news_id] = row
    for path in root.rglob("assessments.csv") if root.exists() else ():
        for row in _read_csv(path):
            news_id = row.get("news_id", "")
            analyzer = row.get("analyzer", "")
            if news_id and analyzer:
                assessments.setdefault(news_id, {})[analyzer] = row.get("sentiment", "")
    identifiers = sorted(set(news) | set(previous))
    generator = random.Random(random_seed)
    retained = list(previous)
    candidates = [news_id for news_id in identifiers if news_id not in previous]
    generator.shuffle(candidates)
    chosen = (retained + candidates)[: min(sample_size, len(identifiers))]
    rows: list[dict[str, str]] = []
    for news_id in chosen:
        item = news[news_id] if news_id in news else previous[news_id]
        old = previous.get(news_id, {})
        predictions = assessments.get(news_id, {})
        rows.append(
            {
                "news_id": news_id,
                "asset": item.get("asset", ""),
                "published_at": item.get("published_at", ""),
                "source": item.get("source", ""),
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "lexicon_sentiment": predictions.get(
                    "lexicon_baseline", old.get("lexicon_sentiment", "")
                ),
                "llm_sentiment": predictions.get(
                    "structured_llm", old.get("llm_sentiment", "")
                ),
                "manual_label": old.get("manual_label", ""),
                "label_notes": old.get("label_notes", ""),
            }
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=QUEUE_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return output


def _macro_f1(truth: list[int], predicted: list[int]) -> float | None:
    if not truth:
        return None
    scores = []
    for label in (-1, 0, 1):
        tp = sum(a == label and b == label for a, b in zip(truth, predicted))
        fp = sum(a != label and b == label for a, b in zip(truth, predicted))
        fn = sum(a == label and b != label for a, b in zip(truth, predicted))
        denominator = 2 * tp + fp + fn
        scores.append(2 * tp / denominator if denominator else 0.0)
    return sum(scores) / len(scores)


def evaluate_labeling_queue(path: str | Path) -> dict[str, Any]:
    rows = _read_csv(Path(path))
    labeled = [row for row in rows if _valid_label(row.get("manual_label")) is not None]
    analyzers: dict[str, Any] = {}
    for column in ("lexicon_sentiment", "llm_sentiment"):
        pairs = [
            (_valid_label(row.get("manual_label")), _valid_label(row.get(column)))
            for row in labeled
        ]
        pairs = [(truth, predicted) for truth, predicted in pairs if predicted is not None]
        truth = [int(pair[0]) for pair in pairs]
        predicted = [int(pair[1]) for pair in pairs]
        analyzers[column] = {
            "labeled_overlap": len(pairs),
            "coverage": len(pairs) / len(labeled) if labeled else 0.0,
            "accuracy": (
                sum(a == b for a, b in zip(truth, predicted)) / len(truth)
                if truth
                else None
            ),
            "macro_f1": _macro_f1(truth, predicted),
        }
    return {
        "queue_rows": len(rows),
        "manually_labeled": len(labeled),
        "remaining": len(rows) - len(labeled),
        "analyzers": analyzers,
    }


def save_label_evaluation(path: str | Path, output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(evaluate_labeling_queue(path), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output
