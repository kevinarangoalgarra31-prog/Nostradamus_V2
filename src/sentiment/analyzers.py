"""Analizadores de sentimiento con salidas explícitas y versionadas."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Callable, Iterable, Mapping

from .domain import NewsItem, SentimentAssessment, canonical_text


POSITIVE_TERMS = (
    "approval", "approved", "adoption", "adopts", "gain", "gains", "growth",
    "rally", "record high", "surge", "upgrade successful", "inflows", "bullish",
    "aprobación", "aprobado", "adopción", "sube", "ganancias", "crecimiento",
    "máximo histórico", "repunte", "entradas", "alcista", "actualización exitosa",
)

NEGATIVE_TERMS = (
    "ban", "banned", "breach", "hack", "hacked", "lawsuit", "outflows", "plunge",
    "rejection", "rejected", "scam", "sell-off", "shutdown", "fraud", "bearish",
    "prohibición", "prohibido", "ataque", "hackeo", "demanda", "salidas", "cae",
    "rechazo", "rechazado", "estafa", "fraude", "bajista", "retiros suspendidos",
)

FINANCIAL_TERMS = (
    "bitcoin", "btc", "ethereum", "ether", "eth", "crypto", "cryptocurrency",
    "blockchain", "etf", "exchange", "market", "price", "network", "token",
    "cripto", "mercado", "precio", "red", "bolsa", "activo", "inversión",
)

ASSET_ALIASES: Mapping[str, tuple[str, ...]] = {
    "BTC-USD": ("bitcoin", "btc"),
    "ETH-USD": ("ethereum", "ether", "eth"),
}


def _matched_phrases(text: str, terms: Iterable[str]) -> list[str]:
    matches: list[str] = []
    for term in terms:
        pattern = rf"(?<!\w){re.escape(canonical_text(term))}(?!\w)"
        if re.search(pattern, text):
            matches.append(term)
    return matches


class LexiconSentimentAnalyzer:
    """Línea base bilingüe, determinista y completamente auditable."""

    name = "lexicon_baseline"
    model_name = "financial_bilingual_lexicon"

    def __init__(
        self,
        *,
        version: str = "financial-bilingual-1.0",
        positive_threshold: float = 0.15,
        negative_threshold: float = -0.15,
    ):
        self.model_version = version
        self.positive_threshold = positive_threshold
        self.negative_threshold = negative_threshold

    def analyze(self, item: NewsItem, *, created_at: datetime) -> SentimentAssessment:
        text = canonical_text(item.title)
        positive = _matched_phrases(text, POSITIVE_TERMS)
        negative = _matched_phrases(text, NEGATIVE_TERMS)
        aliases = ASSET_ALIASES.get(item.asset, (item.asset.casefold(),))
        asset_hits = _matched_phrases(text, aliases)
        context_hits = _matched_phrases(text, FINANCIAL_TERMS)
        relevance = min(1.0, 0.65 * bool(asset_hits) + 0.15 * min(len(context_hits), 2))
        if not asset_hits and not context_hits:
            return SentimentAssessment(
                news_id=item.news_id,
                asset=item.asset,
                analyzer=self.name,
                model_name=self.model_name,
                model_version=self.model_version,
                created_at=created_at,
                status="irrelevant",
                sentiment=None,
                score=None,
                confidence=0.0,
                relevance=0.0,
                evidence=(),
                error="El titular no contiene referencias al activo ni al mercado.",
            )
        hits = len(positive) + len(negative)
        score = (len(positive) - len(negative)) / max(1, hits)
        if score >= self.positive_threshold:
            sentiment = 1
        elif score <= self.negative_threshold:
            sentiment = -1
        else:
            sentiment = 0
        confidence = min(0.95, 0.35 + 0.20 * hits)
        evidence = tuple(
            [f"positive:{term}" for term in positive]
            + [f"negative:{term}" for term in negative]
            + [f"asset:{term}" for term in asset_hits]
        )
        return SentimentAssessment(
            news_id=item.news_id,
            asset=item.asset,
            analyzer=self.name,
            model_name=self.model_name,
            model_version=self.model_version,
            created_at=created_at,
            status="ok",
            sentiment=sentiment,
            score=float(score),
            confidence=float(confidence),
            relevance=float(relevance),
            evidence=evidence,
        )


class StructuredLLMSentimentAnalyzer:
    """Adaptador LLM estricto; una respuesta inválida conserva su error."""

    name = "structured_llm"

    def __init__(
        self,
        completion: Callable[[str], str],
        *,
        model_name: str,
        model_version: str,
        prompt_version: str = "sentiment-json-v1",
    ):
        self.completion = completion
        self.model_name = model_name
        self.model_version = model_version
        self.prompt_version = prompt_version

    def _prompt(self, item: NewsItem) -> str:
        return (
            "Classify the financial impact of the headline for the specified asset. "
            "Use only information explicitly present in the headline. Return one JSON object "
            "with exactly these fields: sentiment (-1, 0, or 1), score (-1.0 to 1.0), "
            "confidence (0.0 to 1.0), relevance (0.0 to 1.0), evidence (a non-empty list "
            "of exact substrings copied from the headline). Do not add Markdown.\n"
            f"prompt_version={self.prompt_version}\n"
            f"asset={item.asset}\nheadline={json.dumps(item.title, ensure_ascii=False)}"
        )

    def analyze(self, item: NewsItem, *, created_at: datetime) -> SentimentAssessment:
        raw = ""
        try:
            raw = str(self.completion(self._prompt(item))).strip()
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("La respuesta debe ser un objeto JSON.")
            required = {"sentiment", "score", "confidence", "relevance", "evidence"}
            if set(payload) != required:
                raise ValueError("La respuesta no contiene exactamente los campos requeridos.")
            sentiment = payload["sentiment"]
            score = float(payload["score"])
            confidence = float(payload["confidence"])
            relevance = float(payload["relevance"])
            evidence = payload["evidence"]
            if type(sentiment) is not int or sentiment not in {-1, 0, 1}:
                raise ValueError("sentiment debe ser el entero -1, 0 o 1.")
            if not -1.0 <= score <= 1.0:
                raise ValueError("score está fuera de rango.")
            if not 0.0 <= confidence <= 1.0 or not 0.0 <= relevance <= 1.0:
                raise ValueError("confidence o relevance están fuera de rango.")
            if not isinstance(evidence, list) or not evidence or not all(
                isinstance(part, str) and part.strip() for part in evidence
            ):
                raise ValueError("evidence debe ser una lista no vacía de textos.")
            normalized_title = canonical_text(item.title)
            if any(canonical_text(part) not in normalized_title for part in evidence):
                raise ValueError("La evidencia debe copiar fragmentos exactos del titular.")
            return SentimentAssessment(
                news_id=item.news_id,
                asset=item.asset,
                analyzer=self.name,
                model_name=self.model_name,
                model_version=f"{self.model_version}|{self.prompt_version}",
                created_at=created_at,
                status="ok",
                sentiment=sentiment,
                score=score,
                confidence=confidence,
                relevance=relevance,
                evidence=tuple(part.strip() for part in evidence),
                raw_response_sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            return SentimentAssessment(
                news_id=item.news_id,
                asset=item.asset,
                analyzer=self.name,
                model_name=self.model_name,
                model_version=f"{self.model_version}|{self.prompt_version}",
                created_at=created_at,
                status="invalid_response",
                sentiment=None,
                score=None,
                confidence=None,
                relevance=None,
                evidence=(),
                raw_response_sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                error=str(exc),
            )
        except Exception as exc:  # El fallo del proveedor queda explícito y auditable.
            return SentimentAssessment(
                news_id=item.news_id,
                asset=item.asset,
                analyzer=self.name,
                model_name=self.model_name,
                model_version=f"{self.model_version}|{self.prompt_version}",
                created_at=created_at,
                status="error",
                sentiment=None,
                score=None,
                confidence=None,
                relevance=None,
                evidence=(),
                raw_response_sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                error=f"{type(exc).__name__}: {exc}",
            )


class GroqCompletionClient:
    """Cliente diferido de Groq para no imponer red ni credenciales al modo CSV."""

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
        max_completion_tokens: int = 256,
    ):
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass
        self.model = model or os.getenv("GROQ_MODEL")
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.model:
            raise ValueError("Configure GROQ_MODEL o llm.model antes de usar el LLM.")
        if not self.api_key:
            raise ValueError("Configure GROQ_API_KEY antes de usar el LLM.")
        if timeout_seconds <= 0.0:
            raise ValueError("timeout_seconds debe ser positivo.")
        if max_completion_tokens < 64:
            raise ValueError("max_completion_tokens debe ser mayor o igual a 64.")
        self.timeout_seconds = float(timeout_seconds)
        self.max_completion_tokens = int(max_completion_tokens)
        try:
            from groq import Groq
        except ImportError as exc:
            raise RuntimeError("El analizador Groq requiere instalar el paquete 'groq'.") from exc
        self._client = Groq(api_key=self.api_key)

    def __call__(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"},
            max_completion_tokens=self.max_completion_tokens,
            timeout=self.timeout_seconds,
        )
        return str(response.choices[0].message.content or "")
