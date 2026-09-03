"""
Módulo de extracción de noticias RSS (Data Pipeline).
Obtiene los titulares más recientes sobre activos financieros vía Google News RSS.
"""

from typing import List, Dict
import urllib.parse
import feedparser


def obtener_titulares_rss(
    activo: str = "Bitcoin",
    max_noticias: int = 5,
    idioma: str = "en"
) -> List[Dict[str, str]]:
    """
    Obtiene los titulares más recientes (últimas 24 horas) de un activo vía Google News RSS.

    Args:
        activo: Nombre del activo a buscar (ej. 'Bitcoin', 'Ethereum', 'S&P500').
        max_noticias: Número máximo de noticias a retornar.
        idioma: 'en' para inglés (mayor cobertura global) o 'es' para español.

    Returns:
        Lista de diccionarios con claves: 'titulo', 'fuente', 'fecha', 'enlace'.
    """
    hl = "es-419" if idioma == "es" else "en-US"
    gl = "CO" if idioma == "es" else "US"
    ceid = "CO:es-419" if idioma == "es" else "US:en"

    # Búsqueda exacta del activo para evitar ruido de otros activos
    query_encoded = urllib.parse.quote(f'"{activo}" when:1d')
    url = f"https://news.google.com/rss/search?q={query_encoded}&hl={hl}&gl={gl}&ceid={ceid}"

    feed = feedparser.parse(url)
    noticias = []

    for entrada in feed.entries[:max_noticias]:
        fuente = entrada.source.get("title", "Fuente Web") if hasattr(entrada, "source") else "Desconocida"
        titulo = getattr(entrada, "title", "Sin título")
        fecha = getattr(entrada, "published", "Reciente")
        enlace = getattr(entrada, "link", "")

        noticias.append({
            "titulo": titulo,
            "fuente": fuente,
            "fecha": fecha,
            "enlace": enlace
        })

    return noticias

