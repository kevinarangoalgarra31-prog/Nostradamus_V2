"""Adquisición, normalización, validación y versionado de datos OHLCV."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Callable

import pandas as pd
import yfinance as yf

from .artifacts import guardar_dataset_versionado
from .validation import DataQualityReport, normalizar_ohlcv, validar_ohlcv


MarketDataProvider = Callable[..., pd.DataFrame]


def _validate_dates(fecha_inicio: str, fecha_fin: str | None) -> None:
    try:
        start = date.fromisoformat(fecha_inicio)
        end = date.fromisoformat(fecha_fin) if fecha_fin else None
    except ValueError as exc:
        raise ValueError("Las fechas deben usar el formato YYYY-MM-DD.") from exc
    if end is not None and end <= start:
        raise ValueError("fecha_fin debe ser posterior a fecha_inicio.")


def _yfinance_provider(ticker: str, **kwargs: object) -> pd.DataFrame:
    cache_dir = Path("data/cache/yfinance")
    cache_dir.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(cache_dir.resolve()))
    return yf.download(tickers=ticker, progress=False, threads=False, **kwargs)


def descargar_datos(
    ticker: str = "BTC-USD",
    fecha_inicio: str = "2022-01-01",
    fecha_fin: str | None = None,
    guardar_csv: bool = False,
    directorio_salida: str = "data/raw",
    *,
    intervalo: str = "1d",
    auto_adjust: bool = False,
    min_filas: int = 2,
    max_missing_ratio: float = 0.0,
    proveedor: MarketDataProvider | None = None,
) -> pd.DataFrame:
    """
    Descarga y valida datos OHLCV; opcionalmente crea un CSV versionado y su manifiesto.

    ``proveedor`` permite inyectar una fuente controlada durante pruebas sin usar red.
    La función conserva la interfaz original y continúa devolviendo un DataFrame.
    """
    if not ticker.strip():
        raise ValueError("El ticker no puede estar vacío.")
    if intervalo != "1d":
        raise ValueError("La fase 2 está acotada inicialmente a datos diarios ('1d').")
    _validate_dates(fecha_inicio, fecha_fin)

    print(f"Descargando datos históricos para {ticker} desde {fecha_inicio}...")
    kwargs: dict[str, object] = {
        "start": fecha_inicio,
        "interval": intervalo,
        "auto_adjust": auto_adjust,
    }
    if fecha_fin:
        kwargs["end"] = fecha_fin

    provider = proveedor or _yfinance_provider
    raw = provider(ticker, **kwargs)
    data = normalizar_ohlcv(raw, ticker=ticker)
    report = validar_ohlcv(
        data,
        min_rows=min_filas,
        max_missing_ratio=max_missing_ratio,
    )
    data.attrs["quality_report"] = report.to_dict()

    if guardar_csv:
        artifact = guardar_dataset_versionado(
            data,
            output_dir=directorio_salida,
            dataset_kind="raw",
            ticker=ticker,
            source="yfinance" if proveedor is None else "injected_provider",
            interval=intervalo,
            quality_report=report,
            metadata={
                "requested_start": fecha_inicio,
                "requested_end": fecha_fin,
                "auto_adjust": auto_adjust,
            },
        )
        data.attrs["artifact_path"] = str(artifact.data_path)
        data.attrs["manifest_path"] = str(artifact.manifest_path)
        data.attrs["sha256"] = artifact.sha256
        print(f"Datos crudos versionados en: {artifact.data_path}")

    return data


def cargar_datos_locales(
    ruta_csv: str | Path,
    *,
    ticker: str | None = None,
    min_filas: int = 2,
    max_missing_ratio: float = 0.0,
) -> tuple[pd.DataFrame, DataQualityReport]:
    """Carga un CSV OHLCV local y aplica los mismos controles del proveedor remoto."""
    path = Path(ruta_csv)
    if not path.is_file():
        raise FileNotFoundError(f"No existe el dataset local: {path}")
    raw = pd.read_csv(path, index_col=0)
    data = normalizar_ohlcv(raw, ticker=ticker)
    report = validar_ohlcv(
        data,
        min_rows=min_filas,
        max_missing_ratio=max_missing_ratio,
    )
    data.attrs["quality_report"] = report.to_dict()
    data.attrs["source_path"] = str(path.resolve())
    return data, report
