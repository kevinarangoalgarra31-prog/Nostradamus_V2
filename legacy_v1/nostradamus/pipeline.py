"""
Pipeline Orquestador -- Tuberia de Estado Inmutable
===================================================
Ejecuta los 4 pasos secuencialmente, enriqueciendo el estado
progresivamente. Maneja abortos por consenso y umbral de confianza.
"""
import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import Callable, Optional

from .agents.market_scanner import scan_market
from .agents.osint_forensics import run_osint_analysis
from .agents.prediction import run_prediction
from .agents.risk_manager import evaluate_risk_and_execute

logger = logging.getLogger("nostradamus.pipeline")


async def run_pipeline(
    on_log: Optional[Callable[[str, str], None]] = None,
    on_step: Optional[Callable[[int, str], None]] = None,
) -> Optional[dict]:
    """
    Ejecuta el pipeline completo de 4 pasos.

    Args:
        on_log: Callback (mensaje, nivel) para emitir logs a la GUI.
        on_step: Callback (paso_num, estado) para actualizar indicadores.
                 estado puede ser: "running", "completed", "failed", "skipped"
    Returns:
        Diccionario final completo o None si se aborto.
    """

    def _log(msg: str, level: str = "INFO"):
        getattr(logger, level.lower(), logger.info)(msg)
        if on_log:
            on_log(msg, level)

    def _step(num: int, status: str):
        if on_step:
            on_step(num, status)

    inicio = datetime.now(timezone.utc)
    _log("=" * 60)
    _log("[>>] NOSTRADAMUS V1.1 -- Iniciando Pipeline de Trading")
    _log(f"   Timestamp: {inicio.isoformat()}")
    _log("=" * 60)

    # -- PASO 1: Stock Selector -----------------------------------------
    _log("")
    _log("-" * 50)
    _log("[*] PASO 1/4: Stock Selector")
    _log("-" * 50)
    _step(1, "running")
    try:
        estado = await scan_market(on_log)
        _step(1, "completed")
    except Exception as e:
        _log(f"[ERROR] Error fatal en Paso 1: {e}", "ERROR")
        _step(1, "failed")
        return None

    # -- PASO 2: Tavily Search ------------------------------------------
    _log("")
    _log("-" * 50)
    _log("[*] PASO 2/4: Tavily Web Search")
    _log("-" * 50)
    _step(2, "running")
    try:
        estado = await run_osint_analysis(estado, on_log)
        if estado is None:
            _log("[STOP] Pipeline ABORTADO -- Consenso insuficiente en Paso 2", "ERROR")
            _step(2, "failed")
            _step(3, "skipped")
            _step(4, "skipped")
            return None
        _step(2, "completed")
    except Exception as e:
        _log(f"[ERROR] Error fatal en Paso 2: {e}", "ERROR")
        _step(2, "failed")
        return None

    # -- PASO 3: Groq Analysis ----------------------------------------
    _log("")
    _log("-" * 50)
    _log("[*] PASO 3/4: Agente de Prediccion (Groq)")
    _log("-" * 50)
    _step(3, "running")
    try:
        estado = await run_prediction(estado, on_log)
        if estado is None:
            _log("[STOP] Pipeline ABORTADO -- Confidence score insuficiente", "WARNING")
            _step(3, "failed")
            _step(4, "skipped")
            return None
        _step(3, "completed")
    except Exception as e:
        _log(f"[ERROR] Error fatal en Paso 3: {e}", "ERROR")
        _step(3, "failed")
        return None

    # -- PASO 4: Risk Management ----------------------------------------
    _log("")
    _log("-" * 50)
    _log("[*] PASO 4/4: Gestion de Riesgo y Ejecucion")
    _log("-" * 50)
    _step(4, "running")
    try:
        estado = await evaluate_risk_and_execute(estado, on_log)
        _step(4, "completed")
    except Exception as e:
        _log(f"[ERROR] Error fatal en Paso 4: {e}", "ERROR")
        _step(4, "failed")
        return None

    # -- Resumen final --------------------------------------------------
    fin = datetime.now(timezone.utc)
    duracion = (fin - inicio).total_seconds()

    estado["pipeline_metadata"] = {
        "version": "1.1.0",
        "inicio": inicio.isoformat(),
        "fin": fin.isoformat(),
        "duracion_total_s": round(duracion, 3),
    }

    _log("")
    _log("=" * 60)
    ejecucion_estado = estado.get("ejecucion", {}).get("estado", "desconocido")
    decision = estado.get("ejecucion", {}).get("decision", "N/A")
    if ejecucion_estado == "completado":
        _log(f"[DONE] PIPELINE COMPLETADO -- Decision: {decision}", "SUCCESS")
        pos = estado["ejecucion"]["tamano_posicion_usd"]
        _log(f"   Posicion: ${pos:,.2f} USD en {estado['activo']}", "SUCCESS")
    else:
        _log(f"[WARN] PIPELINE COMPLETADO -- Decision: {decision}", "WARNING")
    _log(f"   Duracion total: {duracion:.2f}s")
    # -- Guardar Historial en CSV ---------------------------------------
    import os
    import csv

    # Crear dir si no existe
    os.makedirs("data", exist_ok=True)
    history_file = "data/history.csv"
    file_exists = os.path.isfile(history_file)

    try:
        with open(history_file, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow([
                    "timestamp", "activo", "modelo_ia", "senal", 
                    "confidence_score", "kelly_ajustado", "decision_final", 
                    "precio_entrada_mock"
                ])
            
            # Extraer campos
            ts = fin.isoformat()
            activo = estado.get("activo", "N/A")
            modelo = estado.get("prediccion", {}).get("modelo", "N/A")
            senal = estado.get("prediccion", {}).get("senal", "N/A")
            conf_score = estado.get("prediccion", {}).get("confidence_score", 0.0)
            
            ejecucion = estado.get("ejecucion", {})
            kelly = ejecucion.get("kelly_ajustado", 0.0)
            decision_final = ejecucion.get("decision", "N/A")
            precio_mock = ejecucion.get("precio_entrada_mock", 0.0)

            writer.writerow([
                ts, activo, modelo, senal, 
                conf_score, kelly, decision_final, 
                precio_mock
            ])
            _log(f"   [INFO] Historial guardado en {history_file}")
    except Exception as e:
        _log(f"   [ERROR] No se pudo guardar historial: {e}", "ERROR")

    _log("=" * 60)

    return estado
