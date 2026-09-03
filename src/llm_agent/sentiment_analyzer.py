"""
Módulo del Cerebro Cualitativo (LLM Agent).
Interactúa con la API de Groq para analizar noticias de mercado y clasificar
su sentimiento e impacto en el riesgo (-1: Pánico, 0: Neutral, 1: Euforia).
"""

import os
import re
from typing import List, Dict, Optional
from dotenv import load_dotenv
from groq import Groq


class SentimentAnalyzer:
    """
    Analizador cualitativo de noticias financieras utilizando modelos LLM a través de Groq.
    """

    DEFAULT_MODEL = "qwen/qwen3.8-27b"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        # Cargar variables de entorno desde .env
        load_dotenv()

        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model or os.getenv("GROQ_MODEL") or self.DEFAULT_MODEL

        if not self.api_key or self.api_key.startswith("gsk_aqui_va"):
            self.cliente = None
            print("⚠️ ADVERTENCIA: No se configuró una GROQ_API_KEY válida en el entorno o .env.")
        else:
            self.cliente = Groq(api_key=self.api_key)
            print(f"✅ Conexión con Groq inicializada (Modelo: {self.model}).")

    def analizar_titular(self, titular: str) -> int:
        """
        Analiza el sentimiento de un titular y devuelve:
        -1 = Pánico / Riesgo alto / Vender
         0 = Neutral
         1 = Euforia / Positivo / Comprar

        Args:
            titular: Texto del titular o noticia.

        Returns:
            int (-1, 0, o 1).
        """
        if not self.cliente:
            raise RuntimeError(
                "No hay un cliente de Groq activo. Por favor configura tu GROQ_API_KEY en el archivo .env."
            )

        prompt = f"""Eres un analista de riesgo financiero experto en criptomonedas y mercados.
Lee este titular y califica el sentimiento del mercado con un número:
-1 (Pánico/Vender/Riesgo extremo)
 0 (Neutral/Informativo)
 1 (Euforia/Comprar/Catalizador positivo)

TITULAR: "{titular}"

Responde ÚNICAMENTE con el número (-1, 0, o 1), sin explicaciones ni texto adicional."""

        try:
            respuesta = self.cliente.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )

            contenido = respuesta.choices[0].message.content.strip()

            # Extracción robusta con regex para soportar respuestas con espacios o formato Markdown
            match = re.search(r"(-1|0|1)", contenido)
            if match:
                return int(match.group(1))

            # Si no coincide exactamente, clasificar por defecto como neutral
            print(f"⚠️ Advertencia: No se pudo interpretar el número en la respuesta del LLM ('{contenido}'). Se asume 0.")
            return 0

        except Exception as e:
            print(f"❌ Error al consultar la API de Groq: {e}")
            raise

    def analizar_titulares(self, noticias: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Analiza una lista de noticias y añade la clave 'sentimiento' a cada una.

        Args:
            noticias: Lista de diccionarios con la clave 'titulo'.

        Returns:
            Lista de noticias con la clave 'sentimiento' agregada.
        """
        resultados = []
        for noticia in noticias:
            titulo = noticia.get("titulo", "")
            sentimiento = self.analizar_titular(titulo)
            n_copia = dict(noticia)
            n_copia["sentimiento"] = sentimiento
            resultados.append(n_copia)
        return resultados

    def obtener_consenso_sentimiento(self, noticias_analizadas: List[Dict[str, Any]]) -> int:
        """
        Calcula la postura cualitativa consolidada a partir de una lista de noticias ya evaluadas:
        - Si alguna noticia es de pánico extremo (-1), se prioriza la alerta defensiva.
        - De lo contrario, se calcula por mayoría o promedio.

        Returns:
            int (-1, 0, o 1).
        """
        if not noticias_analizadas:
            return 0

        sentimientos = [n.get("sentimiento", 0) for n in noticias_analizadas]

        # Filosofía de preservación de capital: si hay pánico extremo en alguna noticia, alarma
        if -1 in sentimientos:
            return -1

        promedio = sum(sentimientos) / len(sentimientos)
        if promedio > 0.3:
            return 1
        elif promedio < -0.3:
            return -1
        return 0

