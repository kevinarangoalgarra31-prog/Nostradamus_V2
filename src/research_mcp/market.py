"""Consultas de mercado públicas y comparación entre fuentes."""

from __future__ import annotations

import os
from datetime import datetime, time, timezone
from statistics import fmean
from typing import Any

from .common import (
    HttpJsonClient,
    RequestsJsonClient,
    parse_date_range,
    source_envelope,
)


UTC = timezone.utc
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
COINGECKO_RANGE_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart/range"
MAX_MARKET_DAYS = 3_660
DAY_MILLISECONDS = 86_400_000

ASSETS = {
    "BTC": {"binance": "BTCUSDT", "coingecko": "bitcoin"},
    "BTC-USD": {"binance": "BTCUSDT", "coingecko": "bitcoin"},
    "BTC-USDT": {"binance": "BTCUSDT", "coingecko": "bitcoin"},
    "ETH": {"binance": "ETHUSDT", "coingecko": "ethereum"},
    "ETH-USD": {"binance": "ETHUSDT", "coingecko": "ethereum"},
    "ETH-USDT": {"binance": "ETHUSDT", "coingecko": "ethereum"},
}


def _asset_symbols(asset: str) -> dict[str, str]:
    key = asset.strip().upper()
    if key not in ASSETS:
        raise ValueError("Activo no soportado. Usa BTC-USD o ETH-USD.")
    return ASSETS[key]


def _utc_milliseconds(value: datetime) -> int:
    return int(value.timestamp() * 1_000)


def _validate_kline(row: list[Any]) -> dict[str, Any]:
    if len(row) < 7:
        raise ValueError("Binance devolvió una vela incompleta.")
    open_value, high, low, close, volume = map(float, row[1:6])
    if high < max(open_value, close) or low > min(open_value, close) or high < low:
        raise ValueError("Binance devolvió relaciones OHLC inválidas.")
    if min(open_value, high, low, close, volume) < 0:
        raise ValueError("Binance devolvió precios o volumen negativos.")
    return {
        "date": datetime.fromtimestamp(int(row[0]) / 1_000, UTC).date().isoformat(),
        "open_time": datetime.fromtimestamp(int(row[0]) / 1_000, UTC).isoformat(),
        "close_time": datetime.fromtimestamp(int(row[6]) / 1_000, UTC).isoformat(),
        "open": open_value,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def get_binance_ohlcv(
    asset: str,
    start_date: str,
    end_date: str,
    *,
    client: HttpJsonClient | None = None,
) -> dict[str, Any]:
    """Obtiene velas diarias; ``end_date`` es exclusivo y puede incluir la abierta."""
    start, end = parse_date_range(start_date, end_date, max_days=MAX_MARKET_DAYS)
    symbol = _asset_symbols(asset)["binance"]
    http = client or RequestsJsonClient()
    start_ms = _utc_milliseconds(datetime.combine(start, time.min, tzinfo=UTC))
    end_ms = _utc_milliseconds(datetime.combine(end, time.min, tzinfo=UTC))
    cursor = start_ms
    records: list[dict[str, Any]] = []
    urls: list[str] = []
    hashes: list[str] = []

    while cursor < end_ms:
        result = http.get_json(
            BINANCE_KLINES_URL,
            params={
                "symbol": symbol,
                "interval": "1d",
                "startTime": cursor,
                "endTime": end_ms - 1,
                "limit": 1_000,
            },
        )
        if not isinstance(result.payload, list):
            raise ValueError("Binance devolvió un contrato inesperado.")
        page = [_validate_kline(list(row)) for row in result.payload]
        records.extend(page)
        urls.append(result.source_url)
        hashes.append(result.sha256)
        if not result.payload or len(result.payload) < 1_000:
            break
        next_cursor = int(result.payload[-1][0]) + DAY_MILLISECONDS
        if next_cursor <= cursor:
            raise RuntimeError("La paginación de Binance no avanzó.")
        cursor = next_cursor

    unique = {record["open_time"]: record for record in records}
    ordered = [unique[key] for key in sorted(unique)]
    return source_envelope(
        source="binance_spot",
        source_urls=urls,
        query={
            "asset": asset.strip().upper(),
            "symbol": symbol,
            "interval": "1d",
            "start_date": start.isoformat(),
            "end_date_exclusive": end.isoformat(),
        },
        payload_hashes=hashes,
        records=ordered,
    )


def get_coingecko_reference(
    asset: str,
    start_date: str,
    end_date: str,
    *,
    client: HttpJsonClient,
) -> dict[str, Any]:
    start, end = parse_date_range(start_date, end_date, max_days=MAX_MARKET_DAYS)
    coin_id = _asset_symbols(asset)["coingecko"]
    start_at = datetime.combine(start, time.min, tzinfo=UTC)
    end_at = datetime.combine(end, time.min, tzinfo=UTC)
    headers: dict[str, str] = {}
    api_key = os.environ.get("COINGECKO_API_KEY", "").strip()
    if api_key:
        headers["x-cg-demo-api-key"] = api_key
    result = client.get_json(
        COINGECKO_RANGE_URL.format(coin_id=coin_id),
        params={
            "vs_currency": "usd",
            "from": int(start_at.timestamp()),
            "to": int(end_at.timestamp()),
        },
        headers=headers,
    )
    if not isinstance(result.payload, dict):
        raise ValueError("CoinGecko devolvió un contrato inesperado.")

    daily: dict[str, dict[str, Any]] = {}
    for timestamp, price in result.payload.get("prices", []):
        date_key = datetime.fromtimestamp(float(timestamp) / 1_000, UTC).date().isoformat()
        daily[date_key] = {
            "date": date_key,
            "timestamp": datetime.fromtimestamp(float(timestamp) / 1_000, UTC).isoformat(),
            "price": float(price),
            "market_cap": None,
            "total_volume": None,
        }
    for field, output_name in (("market_caps", "market_cap"), ("total_volumes", "total_volume")):
        for timestamp, value in result.payload.get(field, []):
            date_key = datetime.fromtimestamp(float(timestamp) / 1_000, UTC).date().isoformat()
            if date_key in daily:
                daily[date_key][output_name] = float(value)

    return source_envelope(
        source="coingecko",
        source_urls=[result.source_url],
        query={
            "asset": asset.strip().upper(),
            "coin_id": coin_id,
            "vs_currency": "usd",
            "start_date": start.isoformat(),
            "end_date_exclusive": end.isoformat(),
        },
        payload_hashes=[result.sha256],
        records=[daily[key] for key in sorted(daily)],
        warnings=[
            "CoinGecko es una referencia agregada; no representa una ejecución de exchange."
        ],
    )


def compare_market_sources(
    asset: str,
    start_date: str,
    end_date: str,
    *,
    difference_threshold: float = 0.02,
    client: HttpJsonClient | None = None,
) -> dict[str, Any]:
    """Compara cierres Binance con precios diarios agregados de CoinGecko."""
    if not 0.0 < difference_threshold <= 0.25:
        raise ValueError("difference_threshold debe estar entre 0 y 0.25.")
    http = client or RequestsJsonClient()
    binance = get_binance_ohlcv(asset, start_date, end_date, client=http)
    coingecko = get_coingecko_reference(
        asset, start_date, end_date, client=http
    )
    binance_by_date = {row["date"]: row for row in binance["records"]}
    coingecko_by_date = {row["date"]: row for row in coingecko["records"]}
    rows: list[dict[str, Any]] = []
    for date_key in sorted(binance_by_date.keys() & coingecko_by_date.keys()):
        close = float(binance_by_date[date_key]["close"])
        reference = float(coingecko_by_date[date_key]["price"])
        difference = abs(close - reference) / reference if reference else float("inf")
        rows.append(
            {
                "date": date_key,
                "binance_close": close,
                "coingecko_price": reference,
                "absolute_relative_difference": difference,
                "warning": difference > difference_threshold,
            }
        )
    differences = [row["absolute_relative_difference"] for row in rows]
    return {
        "source": "binance_spot+coingecko",
        "requested_at": binance["requested_at"],
        "query": {
            "asset": asset.strip().upper(),
            "start_date": start_date,
            "end_date_exclusive": end_date,
            "difference_threshold": difference_threshold,
        },
        "payload_sha256": {
            "binance": binance["payload_sha256"],
            "coingecko": coingecko["payload_sha256"],
        },
        "overlap_days": len(rows),
        "mean_absolute_relative_difference": fmean(differences) if differences else None,
        "max_absolute_relative_difference": max(differences) if differences else None,
        "warning_days": sum(bool(row["warning"]) for row in rows),
        "records": rows,
        "warnings": [
            "La comparación detecta divergencias; no sustituye la validación OHLCV del pipeline."
        ],
    }
