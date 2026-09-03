"""
Paso 3: Agente de Prediccion — Groq (LLaMA 3.3)
=================================================
Envia los resultados de Tavily a Groq para analisis financiero.
Genera confidence_score, senal, y razonamiento.
Solo avanza al Paso 4 si confidence_score > 0.68.
"""
import asyncio
import logging
from copy import deepcopy
from functools import partial
from typing import Callable, Optional

from ..services.ai_service import ai_service

logger = logging.getLogger("nostradamus.prediction")

UMBRAL_CONFIANZA = 0.68


async def run_prediction(
    estado: dict,
    on_log: Optional[Callable[[str, str], None]] = None,
) -> Optional[dict]:
    """
    Envia datos de Tavily a Groq y genera prediccion.

    Args:
        estado: Diccionario con resultados de Tavily del Paso 2.
        on_log: Callback para la GUI.

    Returns:
        Estado enriquecido con prediccion, o None si score < umbral.
    """

    def _log(msg: str, level: str = "INFO"):
        getattr(logger, level.lower(), logger.info)(msg)
        if on_log:
            on_log(msg, level)

    activo = estado["activo"]
    nombre = estado["nombre"]
    analisis = estado.get("analisis_agente_2", {})

    _log(f"[PRED] Iniciando Agente de Prediccion para {nombre} ({activo})...")

    if not ai_service.disponible:
        _log("   [WARN] Groq no disponible. Usando respuesta fallback.", "WARNING")

    _log(f"   Modelo: {ai_service.model_name}")
    _log(f"   Datos de entrada: {analisis.get('total_resultados', 0)} resultados de Tavily")

    # Extraer resultados de busqueda
    busquedas = analisis.get("busquedas", [])

    _log("   [PROC] Enviando datos a Groq para analisis...")

    # Ejecutar analisis de IA en un executor (es sincrono por los retries/sleep)
    loop = asyncio.get_event_loop()
    resultado_ia = await loop.run_in_executor(
        None,
        partial(
            ai_service.analyze_market_data,
            activo,
            nombre,
            busquedas,
        ),
    )

    confidence_score = resultado_ia.get("confidence_score", 0.5)
    senal = resultado_ia.get("senal", "mantener")
    modelo = resultado_ia.get("modelo", "desconocido")

    _log(f"   [INFO] Modelo utilizado: {modelo}")
    _log(f"   [INFO] Sentimiento: {resultado_ia.get('sentimiento_mercado', 'N/A')}")
    _log(f"   [TARGET] Confidence Score: {confidence_score:.4f}")
    _log(f"   [SIGNAL] Senal generada: {senal.upper()}")

    # Mostrar razonamiento
    razonamiento = resultado_ia.get("razonamiento", "")
    if razonamiento:
        # Truncar para el log
        razon_corta = razonamiento[:150] + "..." if len(razonamiento) > 150 else razonamiento
        _log(f"   [INFO] Razonamiento: {razon_corta}")

    # Mostrar factores clave
    factores = resultado_ia.get("factores_clave", [])
    if factores:
        _log(f"   [INFO] Factores clave: {', '.join(factores[:5])}")

    # Construir nuevo estado
    nuevo_estado = deepcopy(estado)
    nuevo_estado["prediccion"] = {
        "modelo": modelo,
        "confidence_score": confidence_score,
        "senal": senal,
        "umbral_requerido": UMBRAL_CONFIANZA,
        "sentimiento_mercado": resultado_ia.get("sentimiento_mercado", "neutral"),
        "razonamiento": razonamiento,
        "factores_clave": factores,
        "riesgo_identificado": resultado_ia.get("riesgo_identificado", ""),
    }

    # Evaluar umbral
    if confidence_score < UMBRAL_CONFIANZA:
        _log(
            f"   [WARN] Score {confidence_score:.4f} < umbral {UMBRAL_CONFIANZA} -- NO PROCEDE",
            "WARNING",
        )
        _log(
            f"[WARN] Paso 3 completado -- Score: {confidence_score:.4f} (INSUFICIENTE)",
            "WARNING",
        )
        return None

    _log(
        f"[OK] Paso 3 completado -- Senal: {senal.upper()} | "
        f"Score: {confidence_score:.4f} (APROBADO)",
        "SUCCESS",
    )

    return nuevo_estado
