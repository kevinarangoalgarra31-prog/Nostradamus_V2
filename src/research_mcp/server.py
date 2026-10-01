"""Servidor MCP local de investigación para Codex."""

from __future__ import annotations

import sys
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .market import compare_market_sources, get_binance_ohlcv
from .news import search_gdelt_news, search_newsapi
from .papers import search_crossref
from .service import describe_sources, source_health


server = FastMCP(
    "nostradamus-research",
    instructions=(
        "Servidor de solo lectura para investigación de Nostradamus. Usa sources_describe "
        "antes de elegir una fuente. Sus respuestas son evidencia exploratoria: el pipeline "
        "debe congelar, validar y versionar cualquier dato usado en un experimento."
    ),
)

LOCAL_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
PUBLIC_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


@server.tool(
    title="Describir fuentes de Nostradamus",
    description="Explica las fuentes, sus usos y límites sin consultar Internet.",
    annotations=LOCAL_READ_ONLY,
    structured_output=True,
)
def sources_describe() -> dict[str, Any]:
    return describe_sources()


@server.tool(
    title="Comprobar fuentes de Nostradamus",
    description=(
        "Muestra la configuración de fuentes. Activa probe_external solo si necesitas "
        "comprobar su disponibilidad real mediante llamadas públicas."
    ),
    annotations=PUBLIC_READ_ONLY,
    structured_output=True,
)
def sources_health(probe_external: bool = False) -> dict[str, Any]:
    return source_health(probe_external=probe_external)


@server.tool(
    title="Consultar OHLCV diario en Binance",
    description=(
        "Obtiene velas diarias públicas para BTC-USD o ETH-USD. start_date es "
        "inclusiva y end_date exclusiva; el rango puede incluir la vela abierta."
    ),
    annotations=PUBLIC_READ_ONLY,
    structured_output=True,
)
def market_get_ohlcv(asset: str, start_date: str, end_date: str) -> dict[str, Any]:
    return get_binance_ohlcv(asset, start_date, end_date)


@server.tool(
    title="Comparar fuentes de mercado",
    description=(
        "Compara el cierre diario de Binance con el precio agregado de CoinGecko y "
        "marca diferencias superiores al umbral."
    ),
    annotations=PUBLIC_READ_ONLY,
    structured_output=True,
)
def market_compare_sources(
    asset: str,
    start_date: str,
    end_date: str,
    difference_threshold: float = 0.02,
) -> dict[str, Any]:
    return compare_market_sources(
        asset,
        start_date,
        end_date,
        difference_threshold=difference_threshold,
    )


@server.tool(
    title="Buscar noticias verificables",
    description=(
        "Busca noticias en NewsAPI o GDELT dentro de una ventana UTC explícita. "
        "GDELT es exploratorio: su seendate debe verificarse antes de una decisión."
    ),
    annotations=PUBLIC_READ_ONLY,
    structured_output=True,
)
def news_search(
    query: str,
    start_at: str,
    end_at: str,
    provider: Literal["newsapi", "gdelt"] = "gdelt",
    language: Literal["en", "es"] = "en",
    limit: int = 50,
) -> dict[str, Any]:
    if provider == "newsapi":
        return search_newsapi(
            query,
            start_at,
            end_at,
            language=language,
            limit=limit,
        )
    return search_gdelt_news(query, start_at, end_at, limit=limit)


@server.tool(
    title="Buscar bibliografía en Crossref",
    description=(
        "Busca metadatos académicos y DOI en Crossref. No descarga ni resume texto completo."
    ),
    annotations=PUBLIC_READ_ONLY,
    structured_output=True,
)
def papers_search(
    query: str,
    limit: int = 10,
    from_year: int | None = None,
) -> dict[str, Any]:
    return search_crossref(query, limit=limit, from_year=from_year)


def main() -> None:
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if transport not in {"stdio", "streamable-http", "sse"}:
        raise SystemExit("Transporte inválido. Usa stdio, streamable-http o sse.")
    server.run(transport=transport)


if __name__ == "__main__":
    main()
