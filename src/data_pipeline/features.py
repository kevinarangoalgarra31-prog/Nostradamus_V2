"""
Módulo de ingeniería de características (Data Pipeline).
Calcula indicadores técnicos (SMA, Retorno Diario) y la variable objetivo (Target).
"""

from pathlib import Path
import pandas as pd


def calcular_caracteristicas(
    df: pd.DataFrame,
    sma_window: int = 20,
    guardar_csv: bool = False,
    directorio_salida: str = "data/processed",
    nombre_archivo: str = "btc_features.csv"
) -> pd.DataFrame:
    """
    Calcula indicadores técnicos básicos y la variable objetivo para Machine Learning.

    Args:
        df: DataFrame con columna 'Close' y 'Volume'.
        sma_window: Ventana temporal para la media móvil simple (por defecto: 20 días).
        guardar_csv: Si es True, guarda el DataFrame procesado en formato CSV.
        directorio_salida: Directorio donde guardar los datos procesados.
        nombre_archivo: Nombre del archivo de salida.

    Returns:
        pd.DataFrame enriquecido con 'SMA_{sma_window}', 'Retorno_Diario' y 'Target', sin NaNs.
    """
    datos = df.copy()

    # 1. Promedio Móvil Simple (SMA)
    sma_col = f"SMA_{sma_window}"
    datos[sma_col] = datos["Close"].rolling(window=sma_window).mean()

    # 2. Retorno Diario porcentual
    datos["Retorno_Diario"] = datos["Close"].pct_change()

    # 3. Variable Objetivo (Target): 1 si el precio de mañana sube respecto a hoy, 0 si baja o igual
    datos["Target"] = (datos["Close"].shift(-1) > datos["Close"]).astype(int)

    # Eliminar filas con NaN introducidas por rolling() y shift(-1)
    filas_iniciales = len(datos)
    datos = datos.dropna()
    filas_limpias = len(datos)
    print(f"Ingeniería de características lista: {filas_limpias} filas útiles (descartadas {filas_iniciales - filas_limpias} con NaN).")

    # Guardar en data/processed si se solicita
    if guardar_csv:
        path_dir = Path(directorio_salida)
        path_dir.mkdir(parents=True, exist_ok=True)
        ruta_archivo = path_dir / nombre_archivo
        datos.to_csv(ruta_archivo)
        print(f"Datos procesados guardados en: {ruta_archivo}")

    return datos

