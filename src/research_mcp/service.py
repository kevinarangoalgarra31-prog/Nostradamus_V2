"""Inventario y diagnóstico seguro de fuentes del MCP."""

from __future__ import annotations

import os
from typing import Any

from .common import HttpJsonClient, RequestsJsonClient, utc_now_iso
from .market import BINANCE_KLINES_URL, COINGECKO_RANGE_URL
from .news import GDELT_URL, NEWSAPI_URL
from .papers import CROSSREF_WORKS_URL


SOURCE_DESCRIPTIONS = {
    "binance_spot": {
        "purpose": "Velas OHLCV diarias públicas de BTCUSDT y ETHUSDT.",
        "authentication": "none",
        "role": "primary_exchange_market_data",
        "limitations": ["Datos de un exchange concreto", "No equivale exactamente a BTC-USD"],
    },
    "coingecko": {
        "purpose": "Precio, capitalización y volumen agregados para contraste.",
        "authentication": "optional_COINGECKO_API_KEY",
        "role": "aggregated_market_reference",
        "limitations": ["No representa un precio de ejecución", "Puede aplicar límites de cuota"],
    },
    "newsapi": {
        "purpose": "Descubrimiento histórico de noticias con fecha UTC.",
        "authentication": "NEWSAPI_KEY",
        "role": "historical_news_discovery",
        "limitations": ["Cobertura y reutilización dependen del plan", "No entrega texto completo"],
    },
    "gdelt_doc_2": {
        "purpose": "Noticias recientes, globales y multilingües.",
        "authentication": "none",
        "role": "prospective_news_discovery",
        "limitations": ["Ventana reciente", "seendate requiere verificación temporal"],
    },
    "crossref": {
        "purpose": "Metadatos bibliográficos, DOI y actualizaciones de publicaciones.",
        "authentication": "optional_CROSSREF_MAILTO",
        "role": "academic_metadata",
        "limitations": ["No garantiza texto completo", "Los metadatos pueden estar incompletos"],
    },
}


def describe_sources() -> dict[str, Any]:
    """Describe capacidades sin realizar llamadas de red."""
    return {
        "server": "nostradamus-research",
        "version": "1.0.0",
        "read_only": True,
        "broker_connected": False,
        "generated_at": utc_now_iso(),
        "sources": SOURCE_DESCRIPTIONS,
        "rules": [
            "El MCP consulta; el pipeline científico debe congelar y validar snapshots.",
            "Ninguna herramienta envía órdenes ni modifica cuentas externas.",
            "Las claves nunca se incluyen en parámetros, resultados o logs.",
        ],
    }


def _probe_source(
    name: str,
    client: HttpJsonClient,
) -> dict[str, Any]:
    try:
        if name == "binance_spot":
            result = client.get_json("https://api.binance.com/api/v3/ping")
        elif name == "coingecko":
            headers = {}
            api_key = os.environ.get("COINGECKO_API_KEY", "").strip()
            if api_key:
                headers["x-cg-demo-api-key"] = api_key
            result = client.get_json("https://api.coingecko.com/api/v3/ping", headers=headers)
        elif name == "newsapi":
            api_key = os.environ.get("NEWSAPI_KEY", "").strip()
            if not api_key:
                return {"status": "not_configured", "credential": "NEWSAPI_KEY"}
            result = client.get_json(
                NEWSAPI_URL,
                params={"q": "bitcoin", "pageSize": 1, "page": 1},
                headers={"X-Api-Key": api_key},
            )
        elif name == "gdelt_doc_2":
            result = client.get_json(
                GDELT_URL,
                params={
                    "query": "bitcoin",
                    "mode": "ArtList",
                    "format": "json",
                    "maxrecords": 1,
                },
            )
        elif name == "crossref":
            result = client.get_json(CROSSREF_WORKS_URL, params={"rows": 0})
        else:
            raise ValueError(f"Fuente desconocida: {name}")
        return {
            "status": "available",
            "http_status": result.status_code,
            "payload_sha256": result.sha256,
        }
    except Exception as exc:  # El diagnóstico debe preservar el estado de cada fuente.
        return {"status": "unavailable", "error_type": type(exc).__name__, "error": str(exc)}


def source_health(
    *,
    probe_external: bool = False,
    client: HttpJsonClient | None = None,
) -> dict[str, Any]:
    """Informa configuración local y, opcionalmente, disponibilidad externa."""
    configuration = {
        "binance_spot": {"configured": True, "credential_required": False},
        "coingecko": {
            "configured": True,
            "credential_required": False,
            "credential_present": bool(os.environ.get("COINGECKO_API_KEY", "").strip()),
        },
        "newsapi": {
            "configured": bool(os.environ.get("NEWSAPI_KEY", "").strip()),
            "credential_required": True,
        },
        "gdelt_doc_2": {"configured": True, "credential_required": False},
        "crossref": {
            "configured": True,
            "credential_required": False,
            "polite_contact_present": bool(os.environ.get("CROSSREF_MAILTO", "").strip()),
        },
    }
    result: dict[str, Any] = {
        "checked_at": utc_now_iso(),
        "probe_external": probe_external,
        "configuration": configuration,
    }
    if probe_external:
        http = client or RequestsJsonClient()
        result["external"] = {
            name: _probe_source(name, http) for name in SOURCE_DESCRIPTIONS
        }
    return result
