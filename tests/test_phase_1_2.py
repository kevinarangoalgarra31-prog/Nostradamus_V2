from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import FeatureConfig, TargetConfig, load_experiment_config
from src.data_pipeline import (
    DataValidationError,
    calcular_caracteristicas,
    descargar_datos,
    feature_columns,
    normalizar_ohlcv,
    validar_ohlcv,
)


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


class MarketDataTests(unittest.TestCase):
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
