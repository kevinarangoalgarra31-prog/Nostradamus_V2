"""Búsqueda de noticias con límites temporales y trazabilidad explícita."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from src.sentiment.domain import canonical_url, parse_datetime_utc

from .common import HttpJsonClient, RequestsJsonClient, source_envelope


UTC = timezone.utc
NEWSAPI_URL = "https://newsapi.org/v2/everything"
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


def _validate_window(start_at: str, end_at: str, *, max_days: int) -> tuple[datetime, datetime]:
    start = parse_datetime_utc(start_at)
    end = parse_datetime_utc(end_at)
    if end <= start:
        raise ValueError("end_at debe ser posterior a start_at.")
    if end - start > timedelta(days=max_days):
        raise ValueError(f"La ventana no puede superar {max_days} días.")
    return start, end


def _deduplicate(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        key = (record["title"].casefold().strip(), canonical_url(record["url"]))
        unique.setdefault(key, record)
    return sorted(unique.values(), key=lambda item: item["published_at"])


def search_newsapi(
    query: str,
    start_at: str,
    end_at: str,
    *,
    language: str = "en",
    limit: int = 50,
    client: HttpJsonClient | None = None,
) -> dict[str, Any]:
    """Busca noticias publicadas en una ventana UTC mediante NewsAPI."""
    if not query.strip():
        raise ValueError("query no puede estar vacío.")
    if language not in {"en", "es"}:
        raise ValueError("language debe ser 'en' o 'es'.")
    if not 1 <= limit <= 100:
        raise ValueError("limit debe estar entre 1 y 100.")
    start, end = _validate_window(start_at, end_at, max_days=1_826)
    api_key = os.environ.get("NEWSAPI_KEY", "").strip()
    if not api_key:
        raise RuntimeError("NEWSAPI_KEY no está configurada para el proceso MCP.")
    http = client or RequestsJsonClient()
    result = http.get_json(
        NEWSAPI_URL,
        params={
            "q": query.strip(),
            "searchIn": "title,description",
            "from": start.isoformat(),
            "to": end.isoformat(),
            "language": language,
            "sortBy": "publishedAt",
            "pageSize": limit,
            "page": 1,
        },
        headers={"X-Api-Key": api_key},
    )
    if not isinstance(result.payload, dict) or not isinstance(
        result.payload.get("articles", []), list
    ):
        raise ValueError("NewsAPI devolvió un contrato inesperado.")
    captured_at = datetime.now(UTC).isoformat()
    records: list[dict[str, Any]] = []
    for item in result.payload.get("articles", []):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        published_raw = item.get("publishedAt")
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        if not title or not url or not published_raw:
            continue
        published = parse_datetime_utc(str(published_raw))
        if not start <= published <= end:
            continue
        records.append(
            {
                "title": title,
                "source": str(source.get("name") or "NewsAPI source unavailable"),
                "url": canonical_url(url),
                "language": language,
                "published_at": published.isoformat(),
                "captured_at": captured_at,
                "description": str(item.get("description") or ""),
                "author": str(item.get("author") or ""),
            }
        )
    return source_envelope(
        source="newsapi",
        source_urls=[result.source_url],
        query={
            "query": query.strip(),
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "language": language,
            "limit": limit,
        },
        payload_hashes=[result.sha256],
        records=_deduplicate(records),
        warnings=[
            "La licencia y el plan de NewsAPI determinan el histórico disponible "
            "y su reutilización."
        ],
    )


def _parse_gdelt_seen_date(value: str) -> datetime:
    text = value.strip()
    for pattern in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=UTC)
        except ValueError:
            continue
    return parse_datetime_utc(text)


def search_gdelt_news(
    query: str,
    start_at: str,
    end_at: str,
    *,
    limit: int = 50,
    client: HttpJsonClient | None = None,
) -> dict[str, Any]:
    """Busca noticias recientes en GDELT DOC; la ventana máxima es 90 días."""
    if not query.strip():
        raise ValueError("query no puede estar vacío.")
    if not 1 <= limit <= 250:
        raise ValueError("limit debe estar entre 1 y 250.")
    start, end = _validate_window(start_at, end_at, max_days=90)
    http = client or RequestsJsonClient()
    result = http.get_json(
        GDELT_URL,
        params={
            "query": query.strip(),
            "mode": "ArtList",
            "format": "json",
            "maxrecords": limit,
            "sort": "DateAsc",
            "startdatetime": start.strftime("%Y%m%d%H%M%S"),
            "enddatetime": end.strftime("%Y%m%d%H%M%S"),
        },
    )
    if not isinstance(result.payload, dict) or not isinstance(
        result.payload.get("articles", []), list
    ):
        raise ValueError("GDELT devolvió un contrato inesperado.")
    captured_at = datetime.now(UTC).isoformat()
    records: list[dict[str, Any]] = []
    for item in result.payload.get("articles", []):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        seen_date = str(item.get("seendate") or "").strip()
        if not title or not url or not seen_date:
            continue
        seen_at = _parse_gdelt_seen_date(seen_date)
        if not start <= seen_at <= end:
            continue
        records.append(
            {
                "title": title,
                "source": str(item.get("domain") or "GDELT source unavailable"),
                "url": canonical_url(url),
                "language": str(item.get("language") or "").lower(),
                "published_at": seen_at.isoformat(),
                "captured_at": captured_at,
                "source_country": str(item.get("sourcecountry") or ""),
                "time_semantics": "gdelt_seen_date",
            }
        )
    return source_envelope(
        source="gdelt_doc_2",
        source_urls=[result.source_url],
        query={
            "query": query.strip(),
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "limit": limit,
        },
        payload_hashes=[result.sha256],
        records=_deduplicate(records),
        warnings=[
            "GDELT seendate no demuestra por sí sola la fecha de publicación; "
            "verifica el artículo antes de usarlo como evidencia temporal.",
            "GDELT DOC está orientado a cobertura reciente y limita la ventana consultable."
        ],
    )
