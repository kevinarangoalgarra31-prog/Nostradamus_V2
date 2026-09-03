"""
Paso 2: OSINT con Tavily — Busqueda Web Financiera
====================================================
Ejecuta 3 busquedas concurrentes en Tavily para recopilar
informacion financiera sobre el activo seleccionado.
Regla de consenso: >= 2/3 busquedas exitosas para consolidar.
"""
import asyncio
import logging
from copy import deepcopy
from typing import Callable, Optional

from ..services.search_service import search_service

logger = logging.getLogger("nostradamus.osint_forensics")

# Umbral de consenso: al menos 2 de 3 busquedas deben ser exitosas
UMBRAL_CONSENSO = 2 / 3


async def run_osint_analysis(
    estado: dict,
    on_log: Optional[Callable[[str, str], None]] = None,
) -> Optional[dict]:
    """
    Ejecuta busquedas concurrentes en Tavily y consolida resultados.

    Args:
        estado: Diccionario de estado del Paso 1.
        on_log: Callback para la GUI.

    Returns:
        Estado enriquecido con resultados de busqueda, o None si fallo.
    """

    def _log(msg: str, level: str = "INFO"):
        getattr(logger, level.lower(), logger.info)(msg)
        if on_log:
            on_log(msg, level)

    activo = estado["activo"]
    nombre = estado["nombre"]
    tipo = estado.get("tipo", "stock")

    _log(f"[OSINT] Iniciando busqueda web para {nombre} ({activo})...")

    if not search_service.disponible:
        _log("   [ERROR] Tavily no configurado. Abortando Paso 2.", "ERROR")
        return None

    # Definir las 3 queries de busqueda
    if tipo == "crypto":
        queries = [
            (f"{nombre} {activo} price forecast opinion buy sell 2026", "finance"),
            (f"{nombre} {activo} analyst prediction market outlook", "finance"),
            (f"{nombre} {activo} latest news market sentiment", "news"),
        ]
    else:
        queries = [
            (f"{nombre} stock price forecast opinion buy sell 2026", "finance"),
            (f"{nombre} stock analyst rating prediction", "finance"),
            (f"{nombre} latest news market sentiment", "news"),
        ]

    _log(f"   Lanzando {len(queries)} busquedas concurrentes (umbral: {UMBRAL_CONSENSO*100:.0f}%)")

    # Ejecutar busquedas concurrentes
    async def _buscar(query: str, topic: str, idx: int) -> dict:
        _log(f"   [~] Busqueda {idx+1}: {query[:60]}...")
        result = await search_service.search(
            query=query,
            topic=topic,
            search_depth="advanced",
            max_results=5,
        )
        if result.get("exito"):
            _log(
                f"   [OK] Busqueda {idx+1}: {result.get('total', 0)} resultados",
                "INFO",
            )
        else:
            _log(
                f"   [ERROR] Busqueda {idx+1}: {result.get('error', 'desconocido')}",
                "ERROR",
            )
        return result

    resultados = await asyncio.gather(
        *[_buscar(q, t, i) for i, (q, t) in enumerate(queries)]
    )

    # Evaluar consenso
    exitosos = [r for r in resultados if r.get("exito", False)]
    fallidos = [r for r in resultados if not r.get("exito", False)]
    ratio_exito = len(exitosos) / len(resultados)

    total_resultados = sum(r.get("total", 0) for r in exitosos)

    _log(
        f"   [DATA] Resultados: {len(exitosos)}/{len(resultados)} busquedas exitosas "
        f"({total_resultados} resultados totales)",
        "INFO",
    )

    if ratio_exito < UMBRAL_CONSENSO:
        _log(
            f"   [STOP] CONSENSO NO ALCANZADO ({len(exitosos)}/{len(resultados)}). "
            f"Operacion ABORTADA.",
            "ERROR",
        )
        return None

    # Consolidar resultados
    nuevo_estado = deepcopy(estado)
    nuevo_estado["analisis_agente_2"] = {
        "busquedas": resultados,
        "total_resultados": total_resultados,
        "consenso_fuentes": f"{len(exitosos)}/{len(resultados)}",
        "tareas_fallidas": [
            r.get("query", "desconocido") for r in fallidos
        ],
    }

    _log(
        f"[OK] Paso 2 completado -- Consenso: {len(exitosos)}/{len(resultados)} | "
        f"Resultados: {total_resultados}",
        "SUCCESS",
    )

    return nuevo_estado
