from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from src.config import DataConfig, FeatureConfig, TargetConfig, load_experiment_config
from src.data_pipeline import (
    DataValidationError,
    calcular_caracteristicas,
    comparar_con_coingecko,
    descargar_datos,
    feature_columns,
    normalizar_ohlcv,
    obtener_datos_mercado,
    validar_ohlcv,
)
from src.research_mcp.common import FetchResult


def synthetic_ohlcv(rows: int = 140) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=rows, freq="D")
    trend = np.linspace(100.0, 135.0, rows)
    close = trend + np.sin(np.arange(rows) / 2.7) * 2.0
    open_price = close + np.cos(np.arange(rows) / 4.0) * 0.5
    high = np.maximum(open_price, close) + 1.5
    low = np.minimum(open_price, close) - 1.5
    return pd.DataFrame(
        {
            "Open": open_price,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": np.arange(rows, dtype=float) + 1_000.0,
        },
        index=index,
    )


class ExperimentConfigTests(unittest.TestCase):
    def test_repository_config_is_valid_and_explicit(self) -> None:
        config = load_experiment_config("config/experiment.yaml")
        self.assertEqual(config.data.interval, "1d")
        self.assertEqual(config.target.horizon_days, 1)
        self.assertIn("BTC-USD", config.data.tickers)
        self.assertGreaterEqual(config.validation.min_rows, 252)

    def test_market_source_contract_accepts_only_declared_providers(self) -> None:
        base = {
            "tickers": ("BTC-USD",),
            "start_date": pd.Timestamp("2024-01-01").date(),
        }
        self.assertEqual(DataConfig(source="binance", **base).source, "binance")
        with self.assertRaisesRegex(ValueError, "yfinance.*binance"):
            DataConfig(source="fallback", **base)


class MarketDataTests(unittest.TestCase):
    def test_binance_provider_is_normalized_and_keeps_provenance(self) -> None:
        envelope = {
            "source": "binance_spot",
            "source_urls": ["https://api.binance.com/api/v3/klines?fixture=1"],
            "payload_sha256": "abc123",
            "query": {"symbol": "BTCUSDT"},
            "records": [
                {
                    "date": "2026-01-01",
                    "open_time": "2026-01-01T00:00:00+00:00",
                    "close_time": "2026-01-01T23:59:59.999000+00:00",
                    "open": 100.0,
                    "high": 103.0,
                    "low": 99.0,
                    "close": 102.0,
                    "volume": 25.0,
                }
            ],
        }
        with patch(
            "src.data_pipeline.market_data.get_binance_ohlcv",
            return_value=envelope,
        ) as fetch:
            result = obtener_datos_mercado(
                "BTC-USD",
                fecha_inicio="2026-01-01",
                fecha_fin="2026-01-02",
                fuente="binance",
            )
        fetch.assert_called_once_with("BTC-USD", "2026-01-01", "2026-01-02")
        self.assertEqual(list(result.columns), ["Open", "High", "Low", "Close", "Volume"])
        self.assertEqual(result.attrs["source"], "binance")
        self.assertEqual(result.attrs["source_payload_sha256"], "abc123")

    def test_coingecko_reference_never_modifies_primary_series(self) -> None:
        frame = synthetic_ohlcv(2)
        original = frame.copy(deep=True)
        timestamps = [
            int(pd.Timestamp(day, tz="UTC").timestamp() * 1_000)
            for day in ("2024-01-01", "2024-01-02")
        ]

        class ReferenceClient:
            def get_json(self, *_args: object, **_kwargs: object) -> FetchResult:
                payload = {
                    "prices": [
                        [timestamps[0], float(frame["Close"].iloc[0])],
                        [timestamps[1], float(frame["Close"].iloc[1]) * 0.90],
                    ],
                    "market_caps": [],
                    "total_volumes": [],
                }
                return FetchResult(
                    payload=payload,
                    raw_content=b"fixture",
                    source_url="https://api.coingecko.com/fixture",
                )

        report = comparar_con_coingecko(
            frame,
            ticker="BTC-USD",
            fecha_inicio="2024-01-01",
            fecha_fin="2024-01-03",
            difference_threshold=0.02,
            client=ReferenceClient(),
        )
        pd.testing.assert_frame_equal(frame, original)
        self.assertEqual(report.status, "warning")
        self.assertEqual(report.overlap_days, 2)
        self.assertEqual(report.warning_days, 1)

    def test_normalizes_lowercase_columns_and_sorts_dates(self) -> None:
        frame = synthetic_ohlcv(5).rename(columns=str.lower).sort_index(ascending=False)
        normalized = normalizar_ohlcv(frame)
        self.assertEqual(list(normalized.columns), ["Open", "High", "Low", "Close", "Volume"])
        self.assertTrue(normalized.index.is_monotonic_increasing)
        self.assertEqual(normalized.index.name, "Date")

    def test_rejects_incoherent_ohlc(self) -> None:
        frame = synthetic_ohlcv(5)
        frame.loc[frame.index[0], "High"] = frame.loc[frame.index[0], "Low"] - 1.0
        with self.assertRaises(DataValidationError):
            validar_ohlcv(frame, min_rows=2)

    def test_download_provider_creates_versioned_artifact_and_manifest(self) -> None:
        def provider(_ticker: str, **_kwargs: object) -> pd.DataFrame:
            return synthetic_ohlcv(20)

        directory = Path("tmp/test_artifacts")
        directory.mkdir(parents=True, exist_ok=True)
        result = descargar_datos(
            ticker="TEST-USD",
            fecha_inicio="2024-01-01",
            guardar_csv=True,
            directorio_salida=str(directory),
            min_filas=10,
            proveedor=provider,
        )
        data_path = Path(result.attrs["artifact_path"])
        manifest_path = Path(result.attrs["manifest_path"])
        self.assertTrue(data_path.is_file())
        self.assertTrue(manifest_path.is_file())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["rows"], 20)
        self.assertEqual(
            manifest["sha256"], hashlib.sha256(data_path.read_bytes()).hexdigest()
        )
        self.assertTrue(manifest["quality"]["valid"])


class FeatureEngineeringTests(unittest.TestCase):
    def test_target_has_no_synthetic_label_at_end(self) -> None:
        raw = synthetic_ohlcv()
        processed = calcular_caracteristicas(
            raw,
            feature_config=FeatureConfig(sma_windows=(10, 20, 50)),
            target_config=TargetConfig(horizon_days=1, min_return=0.0),
        )
        self.assertLess(processed.index.max(), raw.index.max())
        self.assertNotIn(raw.index[-1], processed.index)
        self.assertFalse(processed.isna().any().any())
        self.assertTrue(set(processed["Target"].unique()).issubset({0, 1}))

        for timestamp, row in processed.tail(10).iterrows():
            position = raw.index.get_loc(timestamp)
            expected = int(raw["Close"].iloc[position + 1] > raw["Close"].iloc[position])
            self.assertEqual(int(row["Target"]), expected)

    def test_model_features_exclude_target_and_future_return(self) -> None:
        processed = calcular_caracteristicas(synthetic_ohlcv())
        columns = feature_columns(processed)
        self.assertNotIn("Target", columns)
        self.assertNotIn("Target_Return", columns)
        self.assertIn("RSI_14", columns)
        self.assertIn("MACD", columns)


if __name__ == "__main__":
    unittest.main()
