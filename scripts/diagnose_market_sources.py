"""Diagnóstico de solo lectura para las fuentes de mercado del MCP."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from src.data_pipeline import normalizar_ohlcv, validar_ohlcv
from src.research_mcp import compare_market_sources, get_binance_ohlcv, source_health


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Valida Binance y lo contrasta con CoinGecko sin escribir artefactos."
    )
    parser.add_argument("--asset", default="BTC-USD", choices=("BTC-USD", "ETH-USD"))
    parser.add_argument("--start-date", help="Inicio inclusivo YYYY-MM-DD.")
    parser.add_argument("--end-date", help="Fin exclusivo YYYY-MM-DD.")
    parser.add_argument("--difference-threshold", type=float, default=0.02)
    return parser


def _binance_frame(envelope: dict[str, object]) -> pd.DataFrame:
    records = list(envelope["records"])
    frame = pd.DataFrame.from_records(records).set_index("open_time")
    return normalizar_ohlcv(frame)


def main() -> int:
    args = _parser().parse_args()
    end = (
        date.fromisoformat(args.end_date)
        if args.end_date
        else datetime.now(timezone.utc).date()
    )
    start = (
        date.fromisoformat(args.start_date)
        if args.start_date
        else end - timedelta(days=7)
    )
    start_text = start.isoformat()
    end_text = end.isoformat()

    binance = get_binance_ohlcv(args.asset, start_text, end_text)
    quality = validar_ohlcv(
        _binance_frame(binance),
        min_rows=1,
        max_missing_ratio=0.0,
    )
    comparison = compare_market_sources(
        args.asset,
        start_text,
        end_text,
        difference_threshold=args.difference_threshold,
    )
    result = {
        "asset": args.asset,
        "start_date": start_text,
        "end_date_exclusive": end_text,
        "configuration": source_health(probe_external=False)["configuration"],
        "binance": {
            "record_count": binance["record_count"],
            "payload_sha256": binance["payload_sha256"],
            "quality": quality.to_dict(),
        },
        "coingecko_cross_validation": {
            "overlap_days": comparison["overlap_days"],
            "warning_days": comparison["warning_days"],
            "mean_absolute_relative_difference": comparison[
                "mean_absolute_relative_difference"
            ],
            "max_absolute_relative_difference": comparison[
                "max_absolute_relative_difference"
            ],
            "payload_sha256": comparison["payload_sha256"],
        },
        "verdict": (
            "warning"
            if comparison["warning_days"] or not comparison["overlap_days"]
            else "ok"
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
