"""
Servicio de IA via Groq Cloud.
Usado en el Paso 3 para analizar resultados de Tavily.
"""
import json
import logging
import os
import time
import warnings

from dotenv import load_dotenv

warnings.filterwarnings("ignore")

logger = logging.getLogger("nostradamus.services.ai")

load_dotenv()

_GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
_GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


class AIService:
    """Servicio de analisis con LLaMA 3.3 via Groq."""

    def __init__(self):
        self.client = None
        self.model_name = _GROQ_MODEL

        if not _GROQ_API_KEY:
            logger.warning("GROQ_API_KEY no configurada en .env")
            return

        try:
            from groq import Groq
            self.client = Groq(api_key=_GROQ_API_KEY)
            logger.info(f"Groq client inicializado (modelo: {self.model_name})")
        except Exception as e:
            logger.warning(f"Error inicializando Groq: {e}")

    @property
    def disponible(self) -> bool:
        return self.client is not None

    def analyze_market_data(self, activo: str, nombre: str, tavily_results: list[dict]) -> dict:
        """
        Envia los resultados de Tavily a Groq para analisis financiero.

        Args:
            activo: Ticker del activo (ej. "NVDA")
            nombre: Nombre completo (ej. "NVIDIA Corporation")
            tavily_results: Lista de busquedas de Tavily con sus resultados

        Returns:
            Diccionario con prediccion, confidence_score, senal, razonamiento
        """
        if not self.client:
            return self._fallback_response(activo)

        # Construir el contexto de busqueda para el prompt
        contexto_busqueda = ""
        for busqueda in tavily_results:
            if not busqueda.get("exito"):
                continue
            contexto_busqueda += f"\n--- Busqueda: {busqueda['query']} ---\n"
            for resultado in busqueda.get("results", []):
                contexto_busqueda += (
                    f"\nFuente: {resultado.get('title', 'N/A')}\n"
                    f"URL: {resultado.get('url', 'N/A')}\n"
                    f"Contenido: {resultado.get('content', 'N/A')[:800]}\n"
                )

        prompt = f"""Eres un analista financiero experto. Analiza la siguiente informacion 
recopilada de multiples fuentes web sobre {nombre} ({activo}) y genera una prediccion de mercado.

INFORMACION RECOPILADA:
{contexto_busqueda}

INSTRUCCIONES:
1. Analiza el sentimiento general de las fuentes (alcista, bajista, neutral)
2. Evalua el consenso de analistas si hay datos disponibles
3. Identifica los factores clave que influyen en el precio
4. Genera un confidence_score entre 0.0 y 1.0 (que tan seguro estas de tu prediccion)
5. Decide la senal: "comprar", "vender" o "mantener"
6. Proporciona un razonamiento breve

Responde UNICAMENTE con un JSON valido con esta estructura exacta:
{{
    "confidence_score": 0.82,
    "senal": "comprar",
    "sentimiento_mercado": "alcista",
    "razonamiento": "El consenso de analistas...",
    "factores_clave": ["factor1", "factor2", "factor3"],
    "riesgo_identificado": "descripcion breve del riesgo principal"
}}"""

        max_retries = 5
        retry_delay = 3

        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that outputs only JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )

                text = response.choices[0].message.content.strip()
                parsed = json.loads(text)

                # Validar campos requeridos
                required = ["confidence_score", "senal", "razonamiento"]
                for field in required:
                    if field not in parsed:
                        raise ValueError(f"Campo faltante en respuesta: {field}")

                # Normalizar confidence_score
                score = float(parsed["confidence_score"])
                parsed["confidence_score"] = max(0.0, min(1.0, score))

                # Normalizar senal
                senal = parsed["senal"].lower().strip()
                if senal not in ("comprar", "vender", "mantener"):
                    parsed["senal"] = "mantener"
                else:
                    parsed["senal"] = senal

                parsed["modelo"] = f"groq-{self.model_name}"
                return parsed

            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "rate limit" in error_str.lower():
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Rate limit en Groq. Reintentando en {retry_delay}s... "
                            f"(Intento {attempt + 1}/{max_retries})"
                        )
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue

                logger.error(f"Error en Groq (intento {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    logger.warning("Todos los reintentos fallaron. Usando fallback.")
                    return self._fallback_response(activo)

        return self._fallback_response(activo)

    def _fallback_response(self, activo: str) -> dict:
        """Respuesta mock cuando la API no esta disponible."""
        return {
            "modelo": "fallback_mock",
            "confidence_score": 0.50,
            "senal": "mantener",
            "sentimiento_mercado": "neutral",
            "razonamiento": (
                f"API no disponible. Datos insuficientes para generar "
                f"prediccion confiable sobre {activo}."
            ),
            "factores_clave": ["api_no_disponible"],
            "riesgo_identificado": "Sin analisis de IA disponible",
        }

    def adjust_risk_parameters(
        self, activo: str, prediccion: dict, base_kelly: float, capital: float
    ) -> dict:
        """
        Envia el contexto de mercado y el calculo matematico a Groq para ajustar el riesgo.
        
        Args:
            activo: Ticker del activo
            prediccion: Datos del Paso 3 (sentimiento, confianza, etc.)
            base_kelly: El f_star matemático puro (0.0 a 1.0)
            capital: Capital disponible en USD
            
        Returns:
            Dict con adjusted_kelly_pct, stop_loss_pct, take_profit_pct, razonamiento
        """
        if not self.client:
            return self._fallback_risk(base_kelly)

        prompt = f"""Eres un Gestor de Riesgos Financiero experto. Acabamos de decidir operar {activo}.
Tenemos un calculo matematico base usando el Criterio de Kelly, pero queremos que lo ajustes dinamicamente basado en el contexto cualitativo.

CONTEXTO DEL ACTIVO:
- Sentimiento: {prediccion.get('sentimiento_mercado', 'neutral')}
- Confianza de la IA (Score): {prediccion.get('confidence_score', 0.5):.2f}
- Senal: {prediccion.get('senal', 'mantener')}
- Riesgo Identificado: {prediccion.get('riesgo_identificado', 'Desconocido')}

CALCULO MATEMATICO (BASE):
- Kelly Criterion Puro (f_star): {base_kelly:.4f} ({base_kelly*100:.2f}% del capital)
- Capital Total: ${capital:,.2f} USD

INSTRUCCIONES:
1. Ajusta el Kelly_pct base. Si el riesgo cualitativo es alto, reducelo agresivamente (ej. a 0.1 o 0.2). Si el entorno es muy seguro y el sentimiento fuerte, puedes mantenerlo cerca del base o ajustarlo segun tu experiencia.
2. Define un Stop Loss dinamico (stop_loss_pct) razonable para la volatilidad que infieres del contexto (usualmente entre 1.0 y 5.0).
3. Define un Take Profit dinamico (take_profit_pct) con una relacion Riesgo:Beneficio razonable (ej. 1:2 o 1:3).
4. Explica tu razonamiento para los ajustes realizados.

Responde UNICAMENTE con un JSON valido con esta estructura exacta:
{{
    "adjusted_kelly_pct": 0.25,
    "stop_loss_pct": 3.5,
    "take_profit_pct": 7.0,
    "razonamiento": "Debido al alto riesgo identificado sobre regulaciones, he reducido el Kelly base de 0.5 a 0.25 (Quarter-Kelly) para proteger el capital. El Stop Loss se amplia a 3.5% debido a la volatilidad esperada."
}}"""

        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that outputs only JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,
                )

                text = response.choices[0].message.content.strip()
                parsed = json.loads(text)

                # Validar campos
                required = ["adjusted_kelly_pct", "stop_loss_pct", "take_profit_pct", "razonamiento"]
                for field in required:
                    if field not in parsed:
                        raise ValueError(f"Campo faltante: {field}")

                return parsed

            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "rate limit" in error_str.lower():
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue

                logger.error(f"Error en Groq Risk Adjustment (intento {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    return self._fallback_risk(base_kelly)

        return self._fallback_risk(base_kelly)

    def _fallback_risk(self, base_kelly: float) -> dict:
        return {
            "adjusted_kelly_pct": base_kelly * 0.5, # Half kelly fallback
            "stop_loss_pct": 3.0,
            "take_profit_pct": 6.0,
            "razonamiento": "Ajuste fallback Half-Kelly estándar (API no disponible)."
        }


# Instancia singleton
ai_service = AIService()
