"""Contratos HTTP y utilidades compartidas por las fuentes MCP."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping, Protocol

import requests


UTC = timezone.utc
DEFAULT_TIMEOUT_SECONDS = 20
USER_AGENT = "NostradamusResearchMCP/1.0 (academic research; read-only)"


class SourceRequestError(RuntimeError):
    """Error explícito de una fuente externa, sin incluir credenciales."""


@dataclass(frozen=True)
class FetchResult:
    """Respuesta JSON con material suficiente para calcular trazabilidad."""

    payload: Any
    raw_content: bytes
    source_url: str
    status_code: int = 200

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.raw_content).hexdigest()


class HttpJsonClient(Protocol):
    """Interfaz inyectable para que las pruebas no necesiten Internet."""

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> FetchResult:
        """Obtiene JSON desde una URL HTTPS controlada."""


class RequestsJsonClient:
    """Cliente HTTP pequeño con timeout, identificación y errores acotados."""

    def __init__(self, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS):
        if timeout_seconds <= 0 or timeout_seconds > 120:
            raise ValueError("timeout_seconds debe estar entre 1 y 120.")
        self.timeout_seconds = timeout_seconds

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> FetchResult:
        if not url.startswith("https://"):
            raise ValueError("Las fuentes MCP deben usar HTTPS.")
        request_headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        request_headers.update(dict(headers or {}))
        try:
            response = requests.get(
                url,
                params=dict(params or {}),
                headers=request_headers,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            suffix = f" (HTTP {status})" if status is not None else ""
            raise SourceRequestError(
                f"La fuente externa no respondió correctamente{suffix}."
            ) from exc
        try:
            payload = response.json()
        except requests.JSONDecodeError as exc:
            raise SourceRequestError("La fuente externa devolvió JSON inválido.") from exc
        return FetchResult(
            payload=payload,
            raw_content=response.content,
            source_url=response.url,
            status_code=response.status_code,
        )


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def parse_date_range(
    start_date: str,
    end_date: str,
    *,
    max_days: int,
) -> tuple[date, date]:
    """Valida un intervalo de fechas con fin exclusivo."""
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError as exc:
        raise ValueError("Las fechas deben usar el formato YYYY-MM-DD.") from exc
    if end <= start:
        raise ValueError("end_date debe ser posterior a start_date.")
    if (end - start).days > max_days:
        raise ValueError(f"El intervalo no puede superar {max_days} días.")
    return start, end


def sha256_json(value: Any) -> str:
    material = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def source_envelope(
    *,
    source: str,
    source_urls: list[str],
    query: Mapping[str, Any],
    payload_hashes: list[str],
    records: list[Mapping[str, Any]],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Construye una salida estable, trazable y libre de secretos."""
    return {
        "source": source,
        "requested_at": utc_now_iso(),
        "source_urls": source_urls,
        "query": dict(query),
        "payload_sha256": sha256_json(payload_hashes),
        "record_count": len(records),
        "records": records,
        "warnings": list(warnings or []),
    }
