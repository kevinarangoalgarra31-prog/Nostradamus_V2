"""
Paso 1: Stock Selector — Seleccion Aleatoria de Activo
======================================================
Selecciona un activo aleatorio de una lista predefinida.
Sin IA, sin llamadas de red. Solo seleccion aleatoria.
"""
import logging
import random
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger("nostradamus.market_scanner")

# Lista de activos faciles de buscar con buena cobertura de analistas
STOCKS = [
    {"ticker": "NVDA", "nombre": "NVIDIA Corporation", "tipo": "stock"},
    {"ticker": "TSLA", "nombre": "Tesla Inc", "tipo": "stock"},
    {"ticker": "BTC", "nombre": "Bitcoin", "tipo": "crypto"},
    {"ticker": "ETH", "nombre": "Ethereum", "tipo": "crypto"},
    {"ticker": "AAPL", "nombre": "Apple Inc", "tipo": "stock"},
    {"ticker": "MSFT", "nombre": "Microsoft Corporation", "tipo": "stock"},
    {"ticker": "GOOGL", "nombre": "Alphabet Inc", "tipo": "stock"},
    {"ticker": "AMZN", "nombre": "Amazon.com Inc", "tipo": "stock"},
]


async def scan_market(
    on_log: Optional[Callable[[str, str], None]] = None,
) -> dict:
    """
    Selecciona un activo aleatorio para analizar.
    No requiere IA ni conexion de red.

    Returns:
        Diccionario de estado inicial con el activo seleccionado.
    """

    def _log(msg: str, level: str = "INFO"):
        getattr(logger, level.lower(), logger.info)(msg)
        if on_log:
            on_log(msg, level)

    _log("[SCAN] Iniciando seleccion de activo...")
    _log(f"   Pool de activos disponibles: {len(STOCKS)}")

    # Seleccionar activo aleatorio
    seleccionado = random.choice(STOCKS)

    _log(f"   Activos en pool: {', '.join(s['ticker'] for s in STOCKS)}")
    _log(
        f"   [ALERT] Activo seleccionado: {seleccionado['nombre']} "
        f"({seleccionado['ticker']})",
        "WARNING",
    )

    estado_inicial = {
        "activo": seleccionado["ticker"],
        "nombre": seleccionado["nombre"],
        "tipo": seleccionado["tipo"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    _log(
        f"[OK] Paso 1 completado -- Activo: {seleccionado['ticker']} | "
        f"Tipo: {seleccionado['tipo']}",
        "SUCCESS",
    )

    return estado_inicial
