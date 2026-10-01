"""Adquisición, normalización, validación y versionado de datos OHLCV."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Callable

import pandas as pd
import yfinance as yf

from src.research_mcp.common import HttpJsonClient, RequestsJsonClient
from src.research_mcp.market import (
    get_binance_ohlcv,
    get_coingecko_reference,
)

from .artifacts import guardar_dataset_versionado
from .validation import DataQualityReport, normalizar_ohlcv, validar_ohlcv


MarketDataProvider = Callable[..., pd.DataFrame]
UTC = timezone.utc


@dataclass(frozen=True)
class MarketReferenceReport:
    """Contraste informativo que nunca modifica la serie OHLCV primaria."""

    source: str
    status: str
    threshold: float
    overlap_days: int
    warning_days: int
    mean_absolute_relative_difference: float | None
    max_absolute_relative_difference: float | None
    checked_start: str
    checked_end_exclusive: str
    payload_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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


def _binance_provider(ticker: str, **kwargs: object) -> pd.DataFrame:
    """Adapta el contrato público de Binance al DataFrame OHLCV del pipeline."""
    interval = str(kwargs.get("interval", "1d"))
    if interval != "1d":
        raise ValueError("Binance solo está habilitado con intervalo diario ('1d').")
    if bool(kwargs.get("auto_adjust", False)):
        raise ValueError("Binance no admite auto_adjust=True.")
    start = str(kwargs["start"])
    end_value = kwargs.get("end")
    end = (
        str(end_value)
        if end_value is not None
        else datetime.now(UTC).date().isoformat()
    )
    envelope = get_binance_ohlcv(ticker, start, end)
    records = envelope["records"]
    frame = pd.DataFrame.from_records(records)
    if frame.empty:
        return frame
    frame = frame.set_index("open_time").rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    frame = frame.loc[:, ["Open", "High", "Low", "Close", "Volume"]]
    frame.attrs["source"] = "binance"
    frame.attrs["source_urls"] = list(envelope["source_urls"])
    frame.attrs["source_payload_sha256"] = envelope["payload_sha256"]
    frame.attrs["source_query"] = dict(envelope["query"])
    return frame


MARKET_PROVIDERS: dict[str, MarketDataProvider] = {
    "yfinance": _yfinance_provider,
    "binance": _binance_provider,
}


def obtener_datos_mercado(
    ticker: str,
    *,
    fecha_inicio: str,
    fecha_fin: str | None,
    fuente: str = "yfinance",
    intervalo: str = "1d",
    auto_adjust: bool = False,
    proveedor: MarketDataProvider | None = None,
) -> pd.DataFrame:
    """Obtiene y normaliza una única fuente sin aplicar fallback entre proveedores."""
    if not ticker.strip():
        raise ValueError("El ticker no puede estar vacío.")
    source = fuente.strip().lower()
    if source not in MARKET_PROVIDERS:
        raise ValueError("La fuente debe ser 'yfinance' o 'binance'.")
    if intervalo != "1d":
        raise ValueError("La fase 2 está acotada a datos diarios ('1d').")
    _validate_dates(fecha_inicio, fecha_fin)

    kwargs: dict[str, object] = {
        "start": fecha_inicio,
        "interval": intervalo,
        "auto_adjust": auto_adjust,
    }
    if fecha_fin:
        kwargs["end"] = fecha_fin
    selected_provider = proveedor or MARKET_PROVIDERS[source]
    raw = selected_provider(ticker, **kwargs)
    provenance = dict(getattr(raw, "attrs", {}))
    data = normalizar_ohlcv(raw, ticker=ticker)
    data.attrs.update(provenance)
    data.attrs["source"] = source if proveedor is None else "injected_provider"
    data.attrs["requested_source"] = source
    return data


def comparar_con_coingecko(
    frame: pd.DataFrame,
    *,
    ticker: str,
    fecha_inicio: str,
    fecha_fin: str,
    difference_threshold: float = 0.02,
    client: HttpJsonClient | None = None,
) -> MarketReferenceReport:
    """Contrasta cierres con CoinGecko sin alterar ni completar la fuente primaria."""
    if not 0.0 < difference_threshold <= 0.25:
        raise ValueError("difference_threshold debe estar entre 0 y 0.25.")
    primary = normalizar_ohlcv(frame, ticker=ticker)
    reference = get_coingecko_reference(
        ticker,
        fecha_inicio,
        fecha_fin,
        client=client or RequestsJsonClient(),
    )
    primary_by_date = {
        timestamp.date().isoformat(): float(value)
        for timestamp, value in primary["Close"].items()
        if fecha_inicio <= timestamp.date().isoformat() < fecha_fin
    }
    reference_by_date = {
        str(row["date"]): float(row["price"])
        for row in reference["records"]
    }
    differences: list[float] = []
    for day in sorted(primary_by_date.keys() & reference_by_date.keys()):
        reference_price = reference_by_date[day]
        difference = (
            abs(primary_by_date[day] - reference_price) / reference_price
            if reference_price
            else float("inf")
        )
        differences.append(difference)
    warning_days = sum(value > difference_threshold for value in differences)
    status = "no_overlap" if not differences else ("warning" if warning_days else "ok")
    return MarketReferenceReport(
        source="coingecko",
        status=status,
        threshold=difference_threshold,
        overlap_days=len(differences),
        warning_days=warning_days,
        mean_absolute_relative_difference=(
            fmean(differences) if differences else None
        ),
        max_absolute_relative_difference=max(differences) if differences else None,
        checked_start=fecha_inicio,
        checked_end_exclusive=fecha_fin,
        payload_sha256=str(reference["payload_sha256"]),
    )


def descargar_datos(
    ticker: str = "BTC-USD",
    fecha_inicio: str = "2022-01-01",
    fecha_fin: str | None = None,
    guardar_csv: bool = False,
    directorio_salida: str = "data/raw",
    *,
    intervalo: str = "1d",
    auto_adjust: bool = False,
    fuente: str = "yfinance",
    min_filas: int = 2,
    max_missing_ratio: float = 0.0,
    proveedor: MarketDataProvider | None = None,
) -> pd.DataFrame:
    """
    Descarga y valida datos OHLCV; opcionalmente crea un CSV versionado y su manifiesto.

    ``proveedor`` permite inyectar una fuente controlada durante pruebas sin usar red.
    La función conserva la interfaz original y continúa devolviendo un DataFrame.
    """
    print(
        f"Descargando datos históricos para {ticker} desde {fecha_inicio} "
        f"con {fuente}..."
    )
    data = obtener_datos_mercado(
        ticker,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        fuente=fuente,
        intervalo=intervalo,
        auto_adjust=auto_adjust,
        proveedor=proveedor,
    )
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
            source=str(data.attrs["source"]),
            interval=intervalo,
            quality_report=report,
            metadata={
                "requested_start": fecha_inicio,
                "requested_end": fecha_fin,
                "auto_adjust": auto_adjust,
                "requested_source": fuente,
                "source_urls": data.attrs.get("source_urls"),
                "source_payload_sha256": data.attrs.get("source_payload_sha256"),
                "source_query": data.attrs.get("source_query"),
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
