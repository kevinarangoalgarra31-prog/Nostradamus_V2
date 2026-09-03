"""
Servicio de busqueda web via Tavily API.
Usado en el Paso 2 para obtener informacion financiera en tiempo real.
"""
import logging
import os
import asyncio
from functools import partial
from typing import Optional

from dotenv import load_dotenv
from tavily import TavilyClient

logger = logging.getLogger("nostradamus.services.search")

load_dotenv()

_TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")


class SearchService:
    """Wrapper asincrono sobre TavilyClient."""

    def __init__(self):
        self.client: Optional[TavilyClient] = None
        if _TAVILY_API_KEY:
            try:
                self.client = TavilyClient(_TAVILY_API_KEY)
                logger.info("Tavily client inicializado correctamente")
            except Exception as e:
                logger.warning(f"Error inicializando Tavily: {e}")
        else:
            logger.warning("TAVILY_API_KEY no configurada en .env")

    @property
    def disponible(self) -> bool:
        return self.client is not None

    async def search(
        self,
        query: str,
        topic: str = "finance",
        search_depth: str = "advanced",
        max_results: int = 5,
    ) -> dict:
        """
        Ejecuta una busqueda en Tavily de forma asincrona.

        Envuelve la llamada sincrona de TavilyClient en un executor
        para no bloquear el event loop.
        """
        if not self.client:
            return {
                "query": query,
                "results": [],
                "exito": False,
                "error": "Tavily no configurado",
            }

        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                partial(
                    self.client.search,
                    query=query,
                    topic=topic,
                    search_depth=search_depth,
                    max_results=max_results,
                ),
            )
            return {
                "query": query,
                "results": response.get("results", []),
                "total": len(response.get("results", [])),
                "exito": True,
            }
        except Exception as e:
            logger.error(f"Error en busqueda Tavily: {e}")
            return {
                "query": query,
                "results": [],
                "exito": False,
                "error": str(e),
            }


# Instancia singleton
search_service = SearchService()
