"""Controles temporales, deduplicación y agregación de la Fase 4."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping

from .domain import NewsItem, SentimentAssessment, SentimentSignal, parse_datetime_utc


@dataclass(frozen=True)
class NewsAuditBatch:
    """Titulares aceptados y exclusiones documentadas."""

    asset: str
    decision_at: datetime
    accepted: tuple[NewsItem, ...]
    rejected: tuple[Mapping[str, Any], ...]
    metrics: Mapping[str, Any]


def audit_news(
    items: Iterable[NewsItem],
    *,
    asset: str,
    decision_at: datetime | str,
    lookback_hours: int,
    allowed_languages: Iterable[str] = ("en", "es"),
    provider_issues: Iterable[Mapping[str, Any]] = (),
) -> NewsAuditBatch:
    """Impide lookahead, limita antigüedad y elimina duplicados."""
    decision = parse_datetime_utc(decision_at)
    lower_bound = decision - timedelta(hours=lookback_hours)
    expected_asset = asset.strip().upper()
    languages = {item.lower() for item in allowed_languages}
    accepted: list[NewsItem] = []
    rejected: list[Mapping[str, Any]] = [dict(issue) for issue in provider_issues]
    seen_titles: set[str] = set()
    seen_urls: set[str] = set()

    ordered = sorted(
        items,
        key=lambda item: (item.captured_at, item.published_at, item.news_id),
    )
    for item in ordered:
        reason: str | None = None
        title_key, url_key = item.duplicate_keys
        if item.asset != expected_asset:
            reason = "wrong_asset"
        elif item.language not in languages:
            reason = "language_not_allowed"
        elif item.published_at > decision:
            reason = "published_after_decision"
        elif item.captured_at > decision:
            reason = "captured_after_decision"
        elif item.captured_at < item.published_at:
            reason = "captured_before_publication"
        elif item.published_at < lower_bound:
            reason = "outside_lookback"
        elif title_key in seen_titles or url_key in seen_urls:
            reason = "duplicate"

        if reason:
            rejected.append(
                {
                    "news_id": item.news_id,
                    "asset": item.asset,
                    "title": item.title,
                    "source": item.source,
                    "published_at": item.published_at.isoformat(),
                    "captured_at": item.captured_at.isoformat(),
                    "reason": reason,
                }
            )
            continue
        seen_titles.add(title_key)
        seen_urls.add(url_key)
        accepted.append(item)

    reasons = Counter(str(row.get("reason", "unknown")) for row in rejected)
    metrics = {
        "decision_at": decision.isoformat(),
        "lookback_start": lower_bound.isoformat(),
        "received": len(ordered),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "rejection_reasons": dict(sorted(reasons.items())),
        "unique_sources": len({item.source for item in accepted}),
        "languages": dict(sorted(Counter(item.language for item in accepted).items())),
        "coverage_status": "covered" if accepted else "no_coverage",
    }
    return NewsAuditBatch(
        asset=expected_asset,
        decision_at=decision,
        accepted=tuple(accepted),
        rejected=tuple(rejected),
        metrics=metrics,
    )


def aggregate_signal(
    items: Iterable[NewsItem],
    assessments: Iterable[SentimentAssessment],
    *,
    asset: str,
    decision_at: datetime | str,
    analyzer: str,
    model_version: str,
    min_headlines: int,
    min_relevance: float,
    positive_threshold: float,
    negative_threshold: float,
) -> SentimentSignal:
    """Agrega noticias con ponderación por confianza y relevancia."""
    item_by_id = {item.news_id: item for item in items}
    selected = [
        assessment
        for assessment in assessments
        if assessment.analyzer == analyzer
        and assessment.status == "ok"
        and assessment.relevance is not None
        and assessment.relevance >= min_relevance
        and assessment.news_id in item_by_id
    ]
    total = len(item_by_id)
    coverage = len(selected) / total if total else 0.0
    sources = {item_by_id[item.news_id].source for item in selected}
    if not selected:
        return SentimentSignal(
            asset=asset,
            decision_at=decision_at,
            analyzer=analyzer,
            model_version=model_version,
            status="no_data",
            sentiment=None,
            score=None,
            confidence=None,
            relevant_headlines=0,
            total_headlines=total,
            unique_sources=0,
            coverage_ratio=coverage,
            source_agreement=None,
            evidence_news_ids=(),
            reason="No existen evaluaciones válidas y relevantes.",
        )
    if len(selected) < min_headlines:
        return SentimentSignal(
            asset=asset,
            decision_at=decision_at,
            analyzer=analyzer,
            model_version=model_version,
            status="insufficient_data",
            sentiment=None,
            score=None,
            confidence=None,
            relevant_headlines=len(selected),
            total_headlines=total,
            unique_sources=len(sources),
            coverage_ratio=coverage,
            source_agreement=None,
            evidence_news_ids=tuple(item.news_id for item in selected),
            reason=f"Se requieren {min_headlines} titulares relevantes.",
        )

    weights = [float(item.confidence) * float(item.relevance) for item in selected]
    weight_sum = sum(weights)
    if weight_sum == 0.0:
        return SentimentSignal(
            asset=asset,
            decision_at=decision_at,
            analyzer=analyzer,
            model_version=model_version,
            status="insufficient_data",
            sentiment=None,
            score=None,
            confidence=None,
            relevant_headlines=len(selected),
            total_headlines=total,
            unique_sources=len(sources),
            coverage_ratio=coverage,
            source_agreement=None,
            evidence_news_ids=tuple(item.news_id for item in selected),
            reason="Las evaluaciones no tienen peso de confianza suficiente.",
        )
    score = sum(float(item.score) * weight for item, weight in zip(selected, weights)) / weight_sum
    if score >= positive_threshold:
        sentiment = 1
    elif score <= negative_threshold:
        sentiment = -1
    else:
        sentiment = 0

    by_source: dict[str, list[float]] = defaultdict(list)
    for assessment in selected:
        by_source[item_by_id[assessment.news_id].source].append(float(assessment.score))
    source_labels = []
    for values in by_source.values():
        source_score = sum(values) / len(values)
        source_labels.append(
            1
            if source_score >= positive_threshold
            else -1
            if source_score <= negative_threshold
            else 0
        )
    agreement = (
        sum(label == sentiment for label in source_labels) / len(source_labels)
        if len(source_labels) >= 2
        else None
    )
    confidence = sum(float(item.confidence) for item in selected) / len(selected)
    return SentimentSignal(
        asset=asset,
        decision_at=decision_at,
        analyzer=analyzer,
        model_version=model_version,
        status="ok",
        sentiment=sentiment,
        score=float(score),
        confidence=float(confidence),
        relevant_headlines=len(selected),
        total_headlines=total,
        unique_sources=len(sources),
        coverage_ratio=coverage,
        source_agreement=agreement,
        evidence_news_ids=tuple(item.news_id for item in selected),
    )
