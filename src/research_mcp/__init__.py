"""Fuentes externas de solo lectura expuestas mediante MCP."""

from .market import (
    compare_market_sources,
    get_binance_ohlcv,
    get_coingecko_reference,
)
from .news import search_gdelt_news, search_newsapi
from .papers import search_crossref
from .service import describe_sources, source_health

__all__ = [
    "compare_market_sources",
    "describe_sources",
    "get_binance_ohlcv",
    "get_coingecko_reference",
    "search_crossref",
    "search_gdelt_news",
    "search_newsapi",
    "source_health",
]
