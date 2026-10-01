from __future__ import annotations

import asyncio
import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from src.research_mcp.common import FetchResult
from src.research_mcp.market import compare_market_sources, get_binance_ohlcv
from src.research_mcp.news import search_gdelt_news, search_newsapi
from src.research_mcp.papers import search_crossref
from src.research_mcp.service import describe_sources, source_health


UTC = timezone.utc


class FakeHttpClient:
    def __init__(self, responses: dict[str, object]):
        self.responses = {url: [value] for url, value in responses.items()}
        self.calls: list[dict[str, object]] = []

    def get_json(self, url, *, params=None, headers=None):
        self.calls.append(
            {
                "url": url,
                "params": dict(params or {}),
                "headers": dict(headers or {}),
            }
        )
        if url not in self.responses or not self.responses[url]:
            raise AssertionError(f"No existe respuesta simulada para {url}")
        payload = self.responses[url].pop(0)
        raw = json.dumps(payload, sort_keys=True).encode("utf-8")
        return FetchResult(payload=payload, raw_content=raw, source_url=url)


def _kline(day: str, open_value: float, close: float) -> list[object]:
    opened = datetime.fromisoformat(day).replace(tzinfo=UTC)
    open_ms = int(opened.timestamp() * 1_000)
    return [
        open_ms,
        str(open_value),
        str(max(open_value, close) + 1),
        str(min(open_value, close) - 1),
        str(close),
        "123.4",
        open_ms + 86_399_999,
    ]


class ResearchSourceTests(unittest.TestCase):
    def test_describe_and_local_health_do_not_require_network(self):
        description = describe_sources()
        self.assertTrue(description["read_only"])
        self.assertFalse(description["broker_connected"])
        self.assertIn("binance_spot", description["sources"])

        with patch.dict(os.environ, {}, clear=True):
            health = source_health(probe_external=False)
        self.assertFalse(health["probe_external"])
        self.assertFalse(health["configuration"]["newsapi"]["configured"])
        self.assertNotIn("external", health)

    def test_binance_ohlcv_is_normalized_and_end_is_exclusive(self):
        client = FakeHttpClient(
            {
                "https://api.binance.com/api/v3/klines": [
                    _kline("2026-01-01", 100.0, 102.0),
                    _kline("2026-01-02", 102.0, 101.0),
                ]
            }
        )
        result = get_binance_ohlcv(
            "BTC-USD", "2026-01-01", "2026-01-03", client=client
        )
        self.assertEqual(result["record_count"], 2)
        self.assertEqual(result["records"][0]["date"], "2026-01-01")
        self.assertEqual(result["records"][0]["close"], 102.0)
        params = client.calls[0]["params"]
        self.assertEqual(params["symbol"], "BTCUSDT")
        self.assertEqual(params["interval"], "1d")

    def test_binance_rejects_invalid_ohlc_before_pipeline_use(self):
        invalid = _kline("2026-01-01", 100.0, 102.0)
        invalid[2] = "99.0"
        client = FakeHttpClient(
            {"https://api.binance.com/api/v3/klines": [invalid]}
        )
        with self.assertRaisesRegex(ValueError, "OHLC inválidas"):
            get_binance_ohlcv(
                "BTC-USD", "2026-01-01", "2026-01-02", client=client
            )

    def test_market_comparison_marks_large_differences(self):
        day_one = int(datetime(2026, 1, 1, 12, tzinfo=UTC).timestamp() * 1_000)
        day_two = int(datetime(2026, 1, 2, 12, tzinfo=UTC).timestamp() * 1_000)
        client = FakeHttpClient(
            {
                "https://api.binance.com/api/v3/klines": [
                    _kline("2026-01-01", 100.0, 100.0),
                    _kline("2026-01-02", 100.0, 110.0),
                ],
                "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart/range": {
                    "prices": [[day_one, 100.0], [day_two, 100.0]],
                    "market_caps": [[day_one, 1_000.0], [day_two, 1_100.0]],
                    "total_volumes": [[day_one, 10.0], [day_two, 11.0]],
                },
            }
        )
        result = compare_market_sources(
            "BTC-USD",
            "2026-01-01",
            "2026-01-03",
            difference_threshold=0.02,
            client=client,
        )
        self.assertEqual(result["overlap_days"], 2)
        self.assertEqual(result["warning_days"], 1)
        self.assertAlmostEqual(result["max_absolute_relative_difference"], 0.10)

    def test_newsapi_requires_key_and_preserves_temporal_metadata(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "NEWSAPI_KEY"):
                search_newsapi(
                    "bitcoin",
                    "2026-01-01T00:00:00Z",
                    "2026-01-02T00:00:00Z",
                )

        payload = {
            "status": "ok",
            "articles": [
                {
                    "source": {"name": "Example"},
                    "author": "Reporter",
                    "title": "Bitcoin update",
                    "description": "Market context",
                    "url": "https://example.com/bitcoin",
                    "publishedAt": "2026-01-01T12:00:00Z",
                }
            ],
        }
        client = FakeHttpClient({"https://newsapi.org/v2/everything": payload})
        with patch.dict(os.environ, {"NEWSAPI_KEY": "secret-test-key"}, clear=True):
            result = search_newsapi(
                "bitcoin",
                "2026-01-01T00:00:00Z",
                "2026-01-02T00:00:00Z",
                client=client,
            )
        self.assertEqual(result["record_count"], 1)
        self.assertEqual(
            result["records"][0]["published_at"],
            "2026-01-01T12:00:00+00:00",
        )
        self.assertNotIn("secret-test-key", json.dumps(result))
        self.assertEqual(client.calls[0]["headers"]["X-Api-Key"], "secret-test-key")

    def test_gdelt_marks_seen_date_as_unverified(self):
        client = FakeHttpClient(
            {
                "https://api.gdeltproject.org/api/v2/doc/doc": {
                    "articles": [
                        {
                            "title": "Ethereum coverage",
                            "url": "https://example.org/eth",
                            "domain": "example.org",
                            "language": "English",
                            "sourcecountry": "United States",
                            "seendate": "20260930T120000Z",
                        }
                    ]
                }
            }
        )
        result = search_gdelt_news(
            "ethereum",
            "2026-09-30T00:00:00Z",
            "2026-10-01T00:00:00Z",
            client=client,
        )
        self.assertEqual(result["record_count"], 1)
        self.assertEqual(result["records"][0]["time_semantics"], "gdelt_seen_date")
        self.assertTrue(any("verifica" in item for item in result["warnings"]))

    def test_crossref_returns_compact_bibliographic_records(self):
        client = FakeHttpClient(
            {
                "https://api.crossref.org/works": {
                    "message": {
                        "items": [
                            {
                                "DOI": "10.1234/example",
                                "title": ["A reproducible trading experiment"],
                                "author": [{"given": "Ada", "family": "Lovelace"}],
                                "published-online": {"date-parts": [[2025, 3, 1]]},
                                "container-title": ["Journal of Tests"],
                                "URL": "https://doi.org/10.1234/example",
                                "type": "journal-article",
                                "is-referenced-by-count": 4,
                            }
                        ]
                    }
                }
            }
        )
        result = search_crossref("walk-forward trading", client=client)
        self.assertEqual(result["records"][0]["doi"], "10.1234/example")
        self.assertEqual(result["records"][0]["authors"], ["Ada Lovelace"])
        self.assertEqual(result["records"][0]["published_year"], 2025)


class McpProtocolTests(unittest.TestCase):
    def test_server_advertises_read_only_tools(self):
        from src.research_mcp.server import server, sources_describe

        tools = asyncio.run(server.list_tools())
        names = {tool.name for tool in tools}
        content = sources_describe()
        self.assertEqual(
            names,
            {
                "sources_describe",
                "sources_health",
                "market_get_ohlcv",
                "market_compare_sources",
                "news_search",
                "papers_search",
            },
        )
        for tool in tools:
            self.assertTrue(tool.annotations.readOnlyHint)
            self.assertFalse(tool.annotations.destructiveHint)
        describe_tool = next(tool for tool in tools if tool.name == "sources_describe")
        self.assertFalse(describe_tool.annotations.openWorldHint)
        self.assertTrue(content["read_only"])
        self.assertFalse(content["broker_connected"])


if __name__ == "__main__":
    unittest.main()
