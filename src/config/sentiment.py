"""Configuración validada de la señal textual de Nostradamus V4."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml


@dataclass(frozen=True)
class SentimentConfig:
    """Contrato experimental para adquisición y análisis de titulares."""

    version: str
    lookback_hours: int
    min_headlines: int
    min_relevance: float
    positive_threshold: float
    negative_threshold: float
    allowed_languages: tuple[str, ...]
    provider: str
    csv_path: str | None
    max_items_per_asset: int
    query_terms: Mapping[str, str]
    lexicon_version: str
    llm_provider: str
    llm_model: str | None
    prompt_version: str
    request_timeout_seconds: float
    max_completion_tokens: int

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("La configuración de sentimiento requiere una versión.")
        if self.lookback_hours < 1:
            raise ValueError("lookback_hours debe ser mayor o igual a 1.")
        if self.min_headlines < 1:
            raise ValueError("min_headlines debe ser mayor o igual a 1.")
        if not 0.0 <= self.min_relevance <= 1.0:
            raise ValueError("min_relevance debe estar entre 0 y 1.")
        if not -1.0 <= self.negative_threshold < self.positive_threshold <= 1.0:
            raise ValueError("Los umbrales de sentimiento son inválidos.")
        if not self.allowed_languages:
            raise ValueError("Debe declararse al menos un idioma permitido.")
        if self.provider not in {"csv", "google_news"}:
            raise ValueError("provider debe ser 'csv' o 'google_news'.")
        if self.max_items_per_asset < 1:
            raise ValueError("max_items_per_asset debe ser mayor o igual a 1.")
        if not self.lexicon_version.strip() or not self.prompt_version.strip():
            raise ValueError("Las versiones del léxico y del prompt son obligatorias.")
        if self.request_timeout_seconds <= 0.0:
            raise ValueError("request_timeout_seconds debe ser positivo.")
        if self.max_completion_tokens < 64:
            raise ValueError("max_completion_tokens debe ser mayor o igual a 64.")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "SentimentConfig":
        sentiment = payload.get("sentiment", {})
        provider = payload.get("provider", {})
        lexicon = payload.get("lexicon", {})
        llm = payload.get("llm", {})
        query_terms = provider.get("query_terms", {})
        if not isinstance(query_terms, Mapping):
            raise ValueError("provider.query_terms debe ser un objeto ticker: consulta.")
        model = llm.get("model")
        return cls(
            version=str(sentiment.get("version", "4.0.0")),
            lookback_hours=int(sentiment.get("lookback_hours", 168)),
            min_headlines=int(sentiment.get("min_headlines", 3)),
            min_relevance=float(sentiment.get("min_relevance", 0.25)),
            positive_threshold=float(sentiment.get("positive_threshold", 0.15)),
            negative_threshold=float(sentiment.get("negative_threshold", -0.15)),
            allowed_languages=tuple(
                str(item).lower() for item in sentiment.get("allowed_languages", ("en", "es"))
            ),
            provider=str(provider.get("type", "csv")),
            csv_path=(str(provider["csv_path"]) if provider.get("csv_path") else None),
            max_items_per_asset=int(provider.get("max_items_per_asset", 100)),
            query_terms={str(key): str(value) for key, value in query_terms.items()},
            lexicon_version=str(lexicon.get("version", "financial-bilingual-1.0")),
            llm_provider=str(llm.get("provider", "groq")),
            llm_model=str(model) if model else None,
            prompt_version=str(llm.get("prompt_version", "sentiment-json-v1")),
            request_timeout_seconds=float(llm.get("request_timeout_seconds", 60.0)),
            max_completion_tokens=int(llm.get("max_completion_tokens", 256)),
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["allowed_languages"] = list(self.allowed_languages)
        result["query_terms"] = dict(self.query_terms)
        return result


def load_sentiment_config(path: str | Path) -> SentimentConfig:
    """Carga una definición YAML de la Fase 4."""
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"No existe la configuración: {config_path}")
    with config_path.open("r", encoding="utf-8") as stream:
        payload = yaml.safe_load(stream) or {}
    if not isinstance(payload, Mapping):
        raise ValueError("La raíz de la configuración debe ser un objeto YAML.")
    return SentimentConfig.from_mapping(payload)
