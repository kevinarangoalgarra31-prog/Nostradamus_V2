"""Ingeniería causal de características y construcción de la variable objetivo."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from src.config import FeatureConfig, TargetConfig

from .artifacts import guardar_dataset_versionado
from .validation import REQUIRED_OHLCV_COLUMNS, normalizar_ohlcv, validar_ohlcv


FEATURE_DICTIONARY = {
    "Open": "Precio de apertura del periodo.",
    "High": "Precio máximo observado durante el periodo.",
    "Low": "Precio mínimo observado durante el periodo.",
    "Close": "Precio de cierre del periodo.",
    "Volume": "Volumen reportado para el periodo.",
    "Retorno_Diario": "Variación porcentual del cierre respecto al periodo anterior.",
    "Retorno_5": "Retorno acumulado de los últimos cinco periodos.",
    "Rango_HL": "Rango máximo-mínimo normalizado por el cierre.",
    "RSI": "Índice de fuerza relativa calculado únicamente con observaciones pasadas.",
    "MACD": "Diferencia entre las medias exponenciales rápida y lenta.",
    "MACD_Signal": "Media exponencial de la línea MACD.",
    "MACD_Hist": "Diferencia entre MACD y su línea de señal.",
    "Volatilidad": "Desviación estándar móvil anualizada de los retornos.",
    "Momentum": "Cambio porcentual del cierre en la ventana de momentum.",
    "Volumen_Relativo": "Volumen dividido por su media móvil.",
    "Target_Return": "Retorno futuro usado exclusivamente para construir Target.",
    "Target": "1 si Target_Return supera el umbral; 0 en caso contrario.",
}


def _rsi(close: pd.Series, window: int) -> pd.Series:
    delta = close.diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    average_gain = gains.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    average_loss = losses.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    relative_strength = average_gain / average_loss.replace(0.0, np.nan)
    result = 100.0 - (100.0 / (1.0 + relative_strength))
    return result.mask((average_loss == 0.0) & (average_gain > 0.0), 100.0)


def calcular_caracteristicas(
    df: pd.DataFrame,
    sma_window: int = 20,
    guardar_csv: bool = False,
    directorio_salida: str = "data/processed",
    nombre_archivo: str = "features.csv",
    *,
    feature_config: FeatureConfig | None = None,
    target_config: TargetConfig | None = None,
    ticker: str = "dataset",
    source: str = "derived",
    intervalo: str = "1d",
    include_target: bool = True,
) -> pd.DataFrame:
    """
    Calcula características técnicas causales y una etiqueta futura sin lookahead.

    ``sma_window`` se conserva por compatibilidad con el prototipo. Cuando se entrega
    ``feature_config``, sus ventanas constituyen la definición experimental oficial.
    """
    parent_sha256 = df.attrs.get("sha256")
    parent_artifact = df.attrs.get("artifact_path")
    features = feature_config or FeatureConfig(sma_windows=(sma_window,))
    target = target_config or TargetConfig()

    data = normalizar_ohlcv(df, ticker=ticker)
    quality = validar_ohlcv(data, min_rows=2, max_missing_ratio=0.0)
    close = data["Close"]
    daily_return = close.pct_change()

    data["Retorno_Diario"] = daily_return
    data["Retorno_5"] = close.pct_change(5)
    data["Rango_HL"] = (data["High"] - data["Low"]) / close

    for window in features.sma_windows:
        column = f"SMA_{window}"
        data[column] = close.rolling(window=window, min_periods=window).mean()
        data[f"Dist_{column}"] = close / data[column] - 1.0

    ema_fast = close.ewm(span=features.ema_fast, adjust=False).mean()
    ema_slow = close.ewm(span=features.ema_slow, adjust=False).mean()
    data[f"EMA_{features.ema_fast}"] = ema_fast
    data[f"EMA_{features.ema_slow}"] = ema_slow
    data["MACD"] = ema_fast - ema_slow
    data["MACD_Signal"] = data["MACD"].ewm(
        span=features.ema_signal, adjust=False
    ).mean()
    data["MACD_Hist"] = data["MACD"] - data["MACD_Signal"]
    data[f"RSI_{features.rsi_window}"] = _rsi(close, features.rsi_window)
    data[f"Volatilidad_{features.volatility_window}"] = (
        daily_return.rolling(features.volatility_window).std() * np.sqrt(252.0)
    )
    data[f"Momentum_{features.momentum_window}"] = close.pct_change(
        features.momentum_window
    )
    volume_average = data["Volume"].rolling(features.volume_window).mean()
    data[f"Volumen_Relativo_{features.volume_window}"] = (
        data["Volume"] / volume_average.replace(0.0, np.nan)
    )

    if include_target:
        future_close = close.shift(-target.horizon_days)
        data["Target_Return"] = future_close / close - 1.0
        labels = pd.Series(pd.NA, index=data.index, dtype="Int8")
        available = data["Target_Return"].notna()
        labels.loc[available] = (
            data.loc[available, "Target_Return"] > target.min_return
        ).astype("int8")
        data["Target"] = labels

    data = data.replace([np.inf, -np.inf], np.nan)
    rows_before = len(data)
    data = data.dropna().copy()
    if include_target:
        data["Target"] = data["Target"].astype("int8")
    discarded = rows_before - len(data)
    print(
        f"Ingeniería de características lista: {len(data)} filas útiles "
        f"(descartadas {discarded} por ventanas o futuro no disponible)."
    )

    if data.empty:
        raise ValueError(
            "No quedaron observaciones después de construir características. "
            "Amplía el periodo o reduce las ventanas."
        )

    if guardar_csv:
        artifact = guardar_dataset_versionado(
            data,
            output_dir=directorio_salida,
            dataset_kind="processed",
            ticker=ticker,
            source=source,
            interval=intervalo,
            quality_report=quality,
            metadata={
                "legacy_output_name": nombre_archivo,
                "feature_config": {
                    "sma_windows": list(features.sma_windows),
                    "rsi_window": features.rsi_window,
                    "volatility_window": features.volatility_window,
                    "momentum_window": features.momentum_window,
                    "volume_window": features.volume_window,
                    "ema_fast": features.ema_fast,
                    "ema_slow": features.ema_slow,
                    "ema_signal": features.ema_signal,
                },
                "target_config": {
                    "horizon_days": target.horizon_days,
                    "min_return": target.min_return,
                },
                "parent_raw_sha256": parent_sha256,
                "parent_raw_artifact": parent_artifact,
            },
        )
        data.attrs["artifact_path"] = str(artifact.data_path)
        data.attrs["manifest_path"] = str(artifact.manifest_path)
        data.attrs["sha256"] = artifact.sha256
        print(f"Datos procesados versionados en: {artifact.data_path}")

    return data


def feature_columns(frame: pd.DataFrame) -> list[str]:
    """Devuelve columnas aptas para el modelo, excluyendo precios futuros y etiqueta."""
    excluded = {*REQUIRED_OHLCV_COLUMNS, "Target_Return", "Target"}
    return [column for column in frame.columns if column not in excluded]


def exportar_diccionario_datos(
    path: str | Path,
    extra_columns: Iterable[str] = (),
) -> Path:
    """Exporta un diccionario legible de variables derivadas."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Diccionario de datos", ""]
    for column, description in FEATURE_DICTIONARY.items():
        lines.append(f"- **{column}**: {description}")
    def describe_parameterized(column: str) -> str:
        if column.startswith("SMA_"):
            return "Media móvil simple del cierre para la ventana indicada."
        if column.startswith("Dist_SMA_"):
            return "Distancia porcentual del cierre frente a la SMA indicada."
        if column.startswith("EMA_"):
            return "Media móvil exponencial del cierre para la ventana indicada."
        if column.startswith("RSI_"):
            return FEATURE_DICTIONARY["RSI"]
        if column.startswith("Volatilidad_"):
            return FEATURE_DICTIONARY["Volatilidad"]
        if column.startswith("Momentum_"):
            return FEATURE_DICTIONARY["Momentum"]
        if column.startswith("Volumen_Relativo_"):
            return FEATURE_DICTIONARY["Volumen_Relativo"]
        return "Variable parametrizada del experimento."

    for column in extra_columns:
        if column not in FEATURE_DICTIONARY:
            lines.append(f"- **{column}**: {describe_parameterized(column)}")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output
