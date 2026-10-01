"""Búsqueda bibliográfica pública mediante Crossref."""

from __future__ import annotations

import os
from typing import Any

from .common import HttpJsonClient, RequestsJsonClient, USER_AGENT, source_envelope


CROSSREF_WORKS_URL = "https://api.crossref.org/works"


def _published_year(item: dict[str, Any]) -> int | None:
    for field in ("published-print", "published-online", "issued", "created"):
        value = item.get(field)
        if not isinstance(value, dict):
            continue
        parts = value.get("date-parts")
        if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
            try:
                return int(parts[0][0])
            except (TypeError, ValueError):
                continue
    return None


def search_crossref(
    query: str,
    *,
    limit: int = 10,
    from_year: int | None = None,
    client: HttpJsonClient | None = None,
) -> dict[str, Any]:
    """Busca metadatos académicos; no descarga texto completo."""
    if not query.strip():
        raise ValueError("query no puede estar vacío.")
    if not 1 <= limit <= 50:
        raise ValueError("limit debe estar entre 1 y 50.")
    if from_year is not None and not 1900 <= from_year <= 2100:
        raise ValueError("from_year debe estar entre 1900 y 2100.")
    params: dict[str, Any] = {
        "query.bibliographic": query.strip(),
        "rows": limit,
        "select": (
            "DOI,title,author,published-print,published-online,issued,created,"
            "container-title,URL,type,is-referenced-by-count,update-to"
        ),
    }
    if from_year is not None:
        params["filter"] = f"from-pub-date:{from_year}-01-01"
    headers = {"User-Agent": USER_AGENT}
    mailto = os.environ.get("CROSSREF_MAILTO", "").strip()
    if mailto:
        headers["User-Agent"] = f"{USER_AGENT} (mailto:{mailto})"
    http = client or RequestsJsonClient()
    result = http.get_json(CROSSREF_WORKS_URL, params=params, headers=headers)
    message = result.payload.get("message", {}) if isinstance(result.payload, dict) else {}
    items = message.get("items", []) if isinstance(message, dict) else []
    if not isinstance(items, list):
        raise ValueError("Crossref devolvió un contrato inesperado.")
    records: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        titles = item.get("title") if isinstance(item.get("title"), list) else []
        containers = (
            item.get("container-title") if isinstance(item.get("container-title"), list) else []
        )
        authors = []
        for author in item.get("author", []):
            if not isinstance(author, dict):
                continue
            full_name = " ".join(
                part for part in (str(author.get("given") or ""), str(author.get("family") or ""))
                if part
            ).strip()
            if full_name:
                authors.append(full_name)
        records.append(
            {
                "doi": str(item.get("DOI") or ""),
                "title": str(titles[0]) if titles else "",
                "authors": authors,
                "published_year": _published_year(item),
                "container_title": str(containers[0]) if containers else "",
                "type": str(item.get("type") or ""),
                "url": str(item.get("URL") or ""),
                "citation_count": int(item.get("is-referenced-by-count") or 0),
                "updates": item.get("update-to", []),
            }
        )
    return source_envelope(
        source="crossref",
        source_urls=[result.source_url],
        query={"query": query.strip(), "limit": limit, "from_year": from_year},
        payload_hashes=[result.sha256],
        records=records,
        warnings=[
            "Crossref aporta metadatos bibliográficos; verifica el texto y la "
            "versión publicada antes de citar conclusiones."
        ],
    )
