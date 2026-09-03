"""
Módulo de descarga de datos de mercado (Data Pipeline).
Obtiene datos históricos OHLCV mediante yfinance y normaliza el DataFrame.
"""

import os
from pathlib import Path
import pandas as pd
import yfinance as yf


def descargar_datos(
    ticker: str = "BTC-USD",
    fecha_inicio: str = "2022-01-01",
    fecha_fin: str = None,
    guardar_csv: bool = False,
    directorio_salida: str = "data/raw"
) -> pd.DataFrame:
    """
    Descarga datos históricos de mercado para un activo dado.

    Args:
        ticker: Símbolo del activo (por defecto: 'BTC-USD').
        fecha_inicio: Fecha de inicio en formato 'YYYY-MM-DD'.
        fecha_fin: Fecha de fin en formato 'YYYY-MM-DD' (opcional).
        guardar_csv: Si es True, guarda el DataFrame en formato CSV.
        directorio_salida: Directorio donde guardar el archivo raw.

    Returns:
        pd.DataFrame con columnas estandarizadas (Open, High, Low, Close, Volume).
    """
    print(f"Descargando datos históricos para {ticker} desde {fecha_inicio}...")
    kwargs = {"start": fecha_inicio}
    if fecha_fin:
        kwargs["end"] = fecha_fin

    datos = yf.download(ticker, **kwargs)

    if datos.empty:
        raise ValueError(f"No se obtuvieron datos para el ticker '{ticker}'. Revisa el símbolo o las fechas.")

    # yfinance reciente puede devolver MultiIndex en columnas (ej. ('Close', 'BTC-USD'))
    if isinstance(datos.columns, pd.MultiIndex):
        datos.columns = datos.columns.get_level_values(0)

    # Asegurar que el índice temporal esté limpio y ordenado
    datos.index = pd.to_datetime(datos.index)
    datos = datos.sort_index()

    # Guardar en data/raw si se solicita
    if guardar_csv:
        path_dir = Path(directorio_salida)
        path_dir.mkdir(parents=True, exist_ok=True)
        nombre_archivo = f"{ticker.replace('-', '_')}_{fecha_inicio}.csv"
        ruta_archivo = path_dir / nombre_archivo
        datos.to_csv(ruta_archivo)
        print(f"Datos crudos guardados en: {ruta_archivo}")

    return datos

