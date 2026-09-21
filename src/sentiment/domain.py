"""Objetos de dominio inmutables para titulares y señales textuales."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit


UTC = timezone.utc


def parse_datetime_utc(value: datetime | str) -> datetime:
    """Interpreta ISO-8601 o RFC-2822 y normaliza a UTC."""
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            raise ValueError("La fecha no puede estar vacía.")
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(text)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Fecha inválida: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Las fechas deben incluir zona horaria explícita.")
    return parsed.astimezone(UTC)


def canonical_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def canonical_url(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("El enlace de la noticia es obligatorio.")
    parts = urlsplit(text)
    if parts.scheme.lower() not in {"http", "https", "urn"}:
        raise ValueError("El enlace debe usar http, https o urn.")
    if parts.scheme.lower() in {"http", "https"} and not parts.netloc:
        raise ValueError("El enlace HTTP requiere un dominio.")
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, "")
    )


def content_hash(*values: object) -> str:
    material = "\x1f".join(str(value) for value in values).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


@dataclass(frozen=True)
class NewsItem:
    """Titular normalizado con evidencia suficiente para reconstruirlo."""

    asset: str
    title: str
    source: str
    url: str
    language: str
    published_at: datetime | str
    captured_at: datetime | str
    provider: str
    query: str = ""
    raw_payload_sha256: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    news_id: str = ""

    def __post_init__(self) -> None:
        asset = self.asset.strip().upper()
        title = re.sub(r"\s+", " ", self.title).strip()
        source = re.sub(r"\s+", " ", self.source).strip()
        language = self.language.strip().lower()
        provider = self.provider.strip()
        if not asset or not title or not source or not language or not provider:
            raise ValueError("Activo, titular, fuente, idioma y proveedor son obligatorios.")
        published_at = parse_datetime_utc(self.published_at)
        captured_at = parse_datetime_utc(self.captured_at)
        url = canonical_url(self.url)
        digest = self.news_id or content_hash(
            provider,
            asset,
            canonical_text(title),
            canonical_text(source),
            published_at.isoformat(),
            url,
        )
        object.__setattr__(self, "asset", asset)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "language", language)
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "published_at", published_at)
        object.__setattr__(self, "captured_at", captured_at)
        object.__setattr__(self, "news_id", digest)
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def duplicate_keys(self) -> tuple[str, str]:
        return canonical_text(self.title), canonical_url(self.url)

    def to_dict(self) -> dict[str, Any]:
        return {
            "news_id": self.news_id,
            "asset": self.asset,
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "language": self.language,
            "published_at": self.published_at.isoformat(),
            "captured_at": self.captured_at.isoformat(),
            "provider": self.provider,
            "query": self.query,
            "raw_payload_sha256": self.raw_payload_sha256,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SentimentAssessment:
    """Resultado individual; los errores nunca se convierten en neutral."""

    news_id: str
    asset: str
    analyzer: str
    model_name: str
    model_version: str
    created_at: datetime | str
    status: str
    sentiment: int | None
    score: float | None
    confidence: float | None
    relevance: float | None
    evidence: tuple[str, ...] = ()
    raw_response_sha256: str = ""
    error: str | None = None

    def __post_init__(self) -> None:
        allowed = {"ok", "irrelevant", "invalid_response", "error"}
        if self.status not in allowed:
            raise ValueError(f"Estado de evaluación inválido: {self.status}")
        created_at = parse_datetime_utc(self.created_at)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "evidence", tuple(self.evidence))
        if self.status == "ok":
            if self.sentiment not in {-1, 0, 1}:
                raise ValueError("Una evaluación válida requiere sentimiento -1, 0 o 1.")
            if self.score is None or not -1.0 <= self.score <= 1.0:
                raise ValueError("score debe estar entre -1 y 1.")
            for name, value in (("confidence", self.confidence), ("relevance", self.relevance)):
                if value is None or not 0.0 <= value <= 1.0:
                    raise ValueError(f"{name} debe estar entre 0 y 1.")
        elif any(value is not None for value in (self.sentiment, self.score)):
            raise ValueError("Una evaluación no válida no puede contener sentimiento ni score.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "news_id": self.news_id,
            "asset": self.asset,
            "analyzer": self.analyzer,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "sentiment": self.sentiment,
            "score": self.score,
            "confidence": self.confidence,
            "relevance": self.relevance,
            "evidence": list(self.evidence),
            "raw_response_sha256": self.raw_response_sha256,
            "error": self.error,
        }


@dataclass(frozen=True)
class SentimentSignal:
    """Señal agregada para un activo en un instante de decisión."""

    asset: str
    decision_at: datetime | str
    analyzer: str
    model_version: str
    status: str
    sentiment: int | None
    score: float | None
    confidence: float | None
    relevant_headlines: int
    total_headlines: int
    unique_sources: int
    coverage_ratio: float
    source_agreement: float | None
    evidence_news_ids: tuple[str, ...]
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"ok", "insufficient_data", "no_data"}:
            raise ValueError(f"Estado de señal inválido: {self.status}")
        object.__setattr__(self, "decision_at", parse_datetime_utc(self.decision_at))
        object.__setattr__(self, "evidence_news_ids", tuple(self.evidence_news_ids))
        if self.status == "ok" and self.sentiment not in {-1, 0, 1}:
            raise ValueError("Una señal válida requiere sentimiento -1, 0 o 1.")
        if self.status != "ok" and self.sentiment is not None:
            raise ValueError("Una señal sin datos suficientes no puede inventar sentimiento.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "decision_at": self.decision_at.isoformat(),
            "analyzer": self.analyzer,
            "model_version": self.model_version,
            "status": self.status,
            "sentiment": self.sentiment,
            "score": self.score,
            "confidence": self.confidence,
            "relevant_headlines": self.relevant_headlines,
            "total_headlines": self.total_headlines,
            "unique_sources": self.unique_sources,
            "coverage_ratio": self.coverage_ratio,
            "source_agreement": self.source_agreement,
            "evidence_news_ids": list(self.evidence_news_ids),
            "reason": self.reason,
        }
