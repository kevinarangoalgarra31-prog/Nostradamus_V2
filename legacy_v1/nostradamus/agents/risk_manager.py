"""
Paso 4: Gestor de Riesgo y Ejecucion
=====================================
Implementa Criterio de Kelly para dimensionar la posicion.
Gestiona una cartera simulada y decide si invertir o no.
"""
import asyncio
import logging
import random
from copy import deepcopy
from typing import Callable, Optional

from ..services.ai_service import ai_service

logger = logging.getLogger("nostradamus.risk_manager")

CAPITAL_INICIAL = 10_000.0  # USD
RATIO_GANANCIA_PERDIDA = 2.0  # b en Kelly
FACTOR_SEGURIDAD = 0.5  # Half-Kelly (conservador)

# Precios mock para calcular tamano en unidades del activo
PRECIOS_MOCK = {
    "NVDA": 200.0, "TSLA": 175.0, "BTC": 67500.0, "ETH": 3450.0,
    "AAPL": 210.0, "MSFT": 430.0, "GOOGL": 165.0, "AMZN": 195.0,
}


def _kelly_criterion(p: float, b: float) -> float:
    """f* = (p * b - q) / b  donde q = 1-p"""
    q = 1.0 - p
    f_star = (p * b - q) / b
    return max(0.0, f_star)


async def evaluate_risk_and_execute(
    estado: dict,
    on_log: Optional[Callable[[str, str], None]] = None,
) -> dict:
    """
    Evalua riesgo con Kelly y genera decision de inversion.

    Args:
        estado: Diccionario con prediccion del Paso 3.
        on_log: Callback para la GUI.

    Returns:
        Estado final con decision de ejecucion.
    """

    def _log(msg: str, level: str = "INFO"):
        getattr(logger, level.lower(), logger.info)(msg)
        if on_log:
            on_log(msg, level)

    activo = estado["activo"]
    nombre = estado["nombre"]
    prediccion = estado.get("prediccion", {})
    confidence = prediccion.get("confidence_score", 0.5)
    senal = prediccion.get("senal", "mantener")

    _log(f"[RISK] Iniciando Gestion de Riesgo para {nombre} ({activo})...")
    _log(f"   Capital disponible: ${CAPITAL_INICIAL:,.2f} USD")
    _log(f"   Senal recibida: {senal.upper()} | Confidence: {confidence:.4f}")

    await asyncio.sleep(0.3)  # Simular procesamiento

    # Calcular Kelly puro matemático
    p = confidence
    b = RATIO_GANANCIA_PERDIDA
    f_star = _kelly_criterion(p, b)

    _log(f"   [CALC] Criterio de Kelly Matemático (f*): {f_star:.4f} ({f_star*100:.2f}%)")

    # Solicitar ajuste de la IA de Groq
    _log(f"   [AI] Solicitando ajuste dinámico a Groq IA...")
    ajuste_ia = ai_service.adjust_risk_parameters(
        activo=activo, 
        prediccion=prediccion, 
        base_kelly=f_star, 
        capital=CAPITAL_INICIAL
    )

    f_ajustado = float(ajuste_ia.get("adjusted_kelly_pct", f_star * 0.5))
    stop_loss = float(ajuste_ia.get("stop_loss_pct", random.uniform(2.0, 4.0)))
    take_profit = float(ajuste_ia.get("take_profit_pct", stop_loss * b))
    razonamiento_ia = ajuste_ia.get("razonamiento", "Sin razonamiento")

    # Límite estricto de seguridad: máximo 80% del capital
    LIMITE_MAXIMO = 0.80
    if f_ajustado > LIMITE_MAXIMO:
        _log(f"   [ALERT] La IA sugirió arriesgar más del {LIMITE_MAXIMO*100}% ({f_ajustado*100}%). Aplicando límite de seguridad.", "WARNING")
        f_ajustado = LIMITE_MAXIMO

    _log(f"   [AI-RISK] Kelly Ajustado por IA: {f_ajustado:.4f} ({f_ajustado*100:.2f}%)")
    _log(f"   [AI-REASON] {razonamiento_ia}")

    await asyncio.sleep(0.2)

    nuevo_estado = deepcopy(estado)
    precio = PRECIOS_MOCK.get(activo, 100.0)

    # Decidir si invertir
    if f_ajustado <= 0 or senal == "vender":
        decision = "NO INVERTIR"
        razon = "kelly_negativo" if f_ajustado <= 0 else "senal_venta"
        _log(f"   [STOP] Kelly negativo o senal de venta -- NO INVERTIR", "WARNING")
        _log(f"[WARN] Paso 4 completado -- Decision: {decision}", "WARNING")
        nuevo_estado["ejecucion"] = {
            "estado": "rechazado",
            "decision": decision,
            "criterio_kelly": round(f_star, 6),
            "kelly_ajustado": round(f_ajustado, 6),
            "razon": razon,
            "capital_disponible": CAPITAL_INICIAL,
            "tamano_posicion_usd": 0.0,
        }
        return nuevo_estado

    # Calcular posicion
    tamano_usd = round(CAPITAL_INICIAL * f_ajustado, 2)
    tamano_activo = round(tamano_usd / precio, 6)
    stop_loss = round(stop_loss, 2)
    take_profit = round(take_profit, 2)
    riesgo_max = round(f_ajustado * 100, 2)

    decision = "INVERTIR"

    _log(f"   [POS] Tamano de posicion: ${tamano_usd:,.2f} USD ({tamano_activo} {activo})")
    _log(f"   [DOWN] Stop Loss: -{stop_loss}% | [UP] Take Profit: +{take_profit}%")
    _log(f"   [RISK%] Riesgo maximo del capital: {riesgo_max}%")

    nuevo_estado["ejecucion"] = {
        "estado": "completado",
        "decision": decision,
        "criterio_kelly": round(f_star, 6),
        "kelly_ajustado": round(f_ajustado, 6),
        "capital_disponible": CAPITAL_INICIAL,
        "tamano_posicion_usd": tamano_usd,
        "tamano_posicion_activo": tamano_activo,
        "activo": activo,
        "precio_entrada_mock": precio,
        "riesgo_maximo_pct": riesgo_max,
        "stop_loss_pct": stop_loss,
        "take_profit_pct": take_profit,
        "senal_ejecutada": senal,
        "razonamiento_riesgo": razonamiento_ia,
    }

    _log(
        f"[OK] Paso 4 completado -- Decision: {decision} | "
        f"Posicion: ${tamano_usd:,.2f}",
        "SUCCESS",
    )
    return nuevo_estado
