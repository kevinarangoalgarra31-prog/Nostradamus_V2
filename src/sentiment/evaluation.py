"""Métricas de cobertura, consistencia y comparación contra etiquetas manuales."""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from typing import Any, Iterable

from .domain import NewsItem, SentimentAssessment


def _macro_f1(truth: list[int], predicted: list[int]) -> float | None:
    if not truth:
        return None
    scores: list[float] = []
    for label in (-1, 0, 1):
        tp = sum(a == label and b == label for a, b in zip(truth, predicted))
        fp = sum(a != label and b == label for a, b in zip(truth, predicted))
        fn = sum(a == label and b != label for a, b in zip(truth, predicted))
        denominator = 2 * tp + fp + fn
        scores.append((2 * tp / denominator) if denominator else 0.0)
    return sum(scores) / len(scores)


def _manual_label(item: NewsItem) -> int | None:
    value = item.metadata.get("manual_label")
    if value in (None, ""):
        return None
    try:
        label = int(value)
    except (TypeError, ValueError):
        return None
    return label if label in {-1, 0, 1} else None


def evaluate_assessments(
    items: Iterable[NewsItem], assessments: Iterable[SentimentAssessment]
) -> dict[str, Any]:
    """Compara analizadores sobre el mismo universo sin imputar fallos como neutral."""
    item_by_id = {item.news_id: item for item in items}
    grouped: dict[str, dict[str, SentimentAssessment]] = defaultdict(dict)
    for assessment in assessments:
        grouped[assessment.analyzer][assessment.news_id] = assessment

    analyzers: dict[str, Any] = {}
    for analyzer, rows in sorted(grouped.items()):
        ok = {key: row for key, row in rows.items() if row.status == "ok"}
        truth: list[int] = []
        predicted: list[int] = []
        for news_id, row in ok.items():
            item = item_by_id.get(news_id)
            label = _manual_label(item) if item else None
            if label is not None:
                truth.append(label)
                predicted.append(int(row.sentiment))
        analyzers[analyzer] = {
            "total_items": len(item_by_id),
            "assessed": len(rows),
            "valid": len(ok),
            "coverage": len(ok) / len(item_by_id) if item_by_id else 0.0,
            "status_counts": {
                status: sum(row.status == status for row in rows.values())
                for status in sorted({row.status for row in rows.values()})
            },
            "manually_labeled_overlap": len(truth),
            "accuracy": (
                sum(a == b for a, b in zip(truth, predicted)) / len(truth)
                if truth
                else None
            ),
            "macro_f1": _macro_f1(truth, predicted),
        }

    agreement: dict[str, Any] = {}
    for first, second in combinations(sorted(grouped), 2):
        first_valid = {
            key: row for key, row in grouped[first].items() if row.status == "ok"
        }
        second_valid = {
            key: row for key, row in grouped[second].items() if row.status == "ok"
        }
        overlap = sorted(set(first_valid) & set(second_valid))
        agreement[f"{first}__vs__{second}"] = {
            "overlap": len(overlap),
            "agreement": (
                sum(
                    first_valid[key].sentiment == second_valid[key].sentiment
                    for key in overlap
                )
                / len(overlap)
                if overlap
                else None
            ),
        }
    return {
        "items": len(item_by_id),
        "manually_labeled": sum(_manual_label(item) is not None for item in item_by_id.values()),
        "analyzers": analyzers,
        "analyzer_agreement": agreement,
    }
