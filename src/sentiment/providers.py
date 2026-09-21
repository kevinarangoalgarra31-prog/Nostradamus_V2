"""Proveedores intercambiables de titulares para la Fase 4."""

from __future__ import annotations

import csv
import json
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .domain import NewsItem, content_hash, parse_datetime_utc


@dataclass(frozen=True)
class ProviderCollection:
    """Resultado de adquisición con errores de filas preservados."""

    items: tuple[NewsItem, ...]
    issues: tuple[Mapping[str, Any], ...] = ()


class NewsProvider(ABC):
    """Interfaz estable; el análisis no depende del mecanismo de adquisición."""

    name: str

    @abstractmethod
    def collect(self, asset: str, captured_at: datetime | None) -> ProviderCollection:
        """Adquiere titulares y registra fallos sin ocultarlos."""


class CsvNewsProvider(NewsProvider):
    """Proveedor reproducible para datasets históricos o etiquetados."""

    name = "csv"

    REQUIRED_COLUMNS = {
        "asset",
        "title",
        "source",
        "url",
        "language",
        "published_at",
    }

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(f"No existe el CSV de titulares: {self.path}")

    def collect(self, asset: str, captured_at: datetime | None) -> ProviderCollection:
        requested = asset.strip().upper()
        fallback_capture = captured_at or datetime.now(timezone.utc)
        items: list[NewsItem] = []
        issues: list[Mapping[str, Any]] = []
        with self.path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            missing = self.REQUIRED_COLUMNS - set(reader.fieldnames or ())
            if missing:
                raise ValueError(
                    "Faltan columnas obligatorias en el CSV: " + ", ".join(sorted(missing))
                )
            for row_number, row in enumerate(reader, start=2):
                if str(row.get("asset", "")).strip().upper() != requested:
                    continue
                try:
                    row_capture = row.get("captured_at") or fallback_capture.isoformat()
                    known = {
                        "asset", "title", "source", "url", "language", "published_at",
                        "captured_at", "provider", "query",
                    }
                    metadata = {
                        key: value
                        for key, value in row.items()
                        if key not in known and value not in (None, "")
                    }
                    raw_hash = content_hash(
                        json.dumps(row, sort_keys=True, ensure_ascii=False)
                    )
                    items.append(
                        NewsItem(
                            asset=requested,
                            title=str(row.get("title", "")),
                            source=str(row.get("source", "")),
                            url=str(row.get("url", "")),
                            language=str(row.get("language", "")),
                            published_at=str(row.get("published_at", "")),
                            captured_at=str(row_capture),
                            provider=str(row.get("provider") or self.name),
                            query=str(row.get("query") or requested),
                            raw_payload_sha256=raw_hash,
                            metadata=metadata,
                        )
                    )
                except (TypeError, ValueError) as exc:
                    issues.append(
                        {
                            "row": row_number,
                            "reason": "invalid_provider_record",
                            "error": str(exc),
                            "raw_sha256": content_hash(
                                json.dumps(row, sort_keys=True, ensure_ascii=False)
                            ),
                        }
                    )
        return ProviderCollection(tuple(items), tuple(issues))


class GoogleNewsRssProvider(NewsProvider):
    """Adquisición en vivo; conserva fechas y huellas del payload RSS."""

    name = "google_news_rss"

    def __init__(
        self,
        *,
        query_terms: Mapping[str, str] | None = None,
        language: str = "en",
        max_items: int = 100,
        lookback_hours: int = 168,
        parser: Any = None,
    ):
        self.query_terms = {str(k).upper(): str(v) for k, v in (query_terms or {}).items()}
        self.language = language.lower()
        self.max_items = max_items
        self.lookback_hours = lookback_hours
        self._parser = parser

    def _feed_url(self, asset: str) -> tuple[str, str]:
        query = self.query_terms.get(asset.upper(), asset)
        days = max(1, (self.lookback_hours + 23) // 24)
        locale = ("es-419", "CO", "CO:es-419") if self.language == "es" else (
            "en-US", "US", "US:en"
        )
        encoded = urllib.parse.quote(f'"{query}" when:{days}d')
        url = (
            f"https://news.google.com/rss/search?q={encoded}"
            f"&hl={locale[0]}&gl={locale[1]}&ceid={locale[2]}"
        )
        return query, url

    def collect(self, asset: str, captured_at: datetime | None = None) -> ProviderCollection:
        if self._parser is None:
            try:
                import feedparser  # Importación diferida: el proveedor CSV funciona sin RSS.
            except ImportError as exc:
                raise RuntimeError(
                    "Google News RSS requiere instalar 'feedparser'."
                ) from exc
            parser = feedparser.parse
        else:
            parser = self._parser

        query, url = self._feed_url(asset)
        feed = parser(url)
        # La captura se marca después de recibir el feed. Una fecha inyectada se
        # reserva para pruebas deterministas y recolecciones controladas.
        capture = (
            parse_datetime_utc(captured_at)
            if captured_at is not None
            else datetime.now(timezone.utc)
        )
        issues: list[Mapping[str, Any]] = []
        items: list[NewsItem] = []
        if getattr(feed, "bozo", False):
            issues.append(
                {
                    "reason": "rss_parse_warning",
                    "error": str(getattr(feed, "bozo_exception", "RSS inválido")),
                    "feed_url": url,
                }
            )
        for position, entry in enumerate(getattr(feed, "entries", ())[: self.max_items], 1):
            try:
                raw = dict(entry)
            except (TypeError, ValueError):
                raw = dict(vars(entry))
            try:
                source_obj = getattr(entry, "source", {}) or {}
                source = (
                    source_obj.get("title", "")
                    if hasattr(source_obj, "get")
                    else str(source_obj)
                )
                published = getattr(entry, "published", None) or getattr(
                    entry, "updated", None
                )
                if not published:
                    raise ValueError("El RSS no incluye fecha de publicación.")
                items.append(
                    NewsItem(
                        asset=asset,
                        title=str(getattr(entry, "title", "")),
                        source=str(source or "Google News source unavailable"),
                        url=str(getattr(entry, "link", "")),
                        language=self.language,
                        published_at=str(published),
                        captured_at=capture,
                        provider=self.name,
                        query=query,
                        raw_payload_sha256=content_hash(
                            json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str)
                        ),
                        metadata={"feed_url": url, "position": position},
                    )
                )
            except (TypeError, ValueError) as exc:
                issues.append(
                    {
                        "position": position,
                        "reason": "invalid_provider_record",
                        "error": str(exc),
                        "raw_sha256": content_hash(
                            json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str)
                        ),
                    }
                )
        return ProviderCollection(tuple(items), tuple(issues))
