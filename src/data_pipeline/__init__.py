"""
Data Pipeline: Módulos de descarga de datos, ingeniería de características y noticias.
"""

from .market_data import descargar_datos
from .features import calcular_caracteristicas
from .news_fetcher import obtener_titulares_rss

__all__ = [
    "descargar_datos",
    "calcular_caracteristicas",
    "obtener_titulares_rss",
]

