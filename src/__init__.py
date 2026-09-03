"""
Nostradamus V2: Sistema Híbrido de Trading Basado en IA (XGBoost + LLMs).
"""

from .data_pipeline import descargar_datos, calcular_caracteristicas, obtener_titulares_rss
from .models import XGBoostTrader
from .llm_agent import SentimentAnalyzer
from .risk_manager import calcular_criterio_kelly, ArbitroRiesgo, DecisionArbitro, el_arbitro

__all__ = [
    "descargar_datos",
    "calcular_caracteristicas",
    "obtener_titulares_rss",
    "XGBoostTrader",
    "SentimentAnalyzer",
    "calcular_criterio_kelly",
    "ArbitroRiesgo",
    "DecisionArbitro",
    "el_arbitro",
]
