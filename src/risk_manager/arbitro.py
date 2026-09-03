"""
Módulo de Gestión de Riesgo: El Árbitro.
Fusión del cerebro cuantitativo (XGBoost) y el cerebro cualitativo (LLM)
para tomar decisiones finales de aprobación y dimensionamiento de capital.
"""
import sys
from dataclasses import dataclass
from typing import Optional, Dict, Any
from .kelly_criterion import calcular_criterio_kelly

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


@dataclass
class DecisionArbitro:
    """Estructura de datos para la decisión final emitida por El Árbitro."""
    aprobada: bool
    asignacion_capital: float
    probabilidad_xgb: float
    kelly_base: float
    sentimiento_llm: int
    contexto_noticia: str
    justificacion: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "aprobada": self.aprobada,
            "asignacion_capital": self.asignacion_capital,
            "porcentaje_capital": f"{self.asignacion_capital * 100:.1f}%",
            "probabilidad_xgb": self.probabilidad_xgb,
            "kelly_base": self.kelly_base,
            "sentimiento_llm": self.sentimiento_llm,
            "contexto_noticia": self.contexto_noticia,
            "justificacion": self.justificacion
        }


class ArbitroRiesgo:
    """
    Toma la decisión final de inversión coordinando las señales estadísticas y cualitativas.
    """

    def __init__(self, ratio_ganancia_perdida: float = 1.0, verbose: bool = True):
        self.ratio_ganancia_perdida = ratio_ganancia_perdida
        self.verbose = verbose

    def evaluar(
        self,
        probabilidad_xgb: float,
        sentimiento_llm: int,
        contexto_noticia: str = "Sin noticia específica"
    ) -> DecisionArbitro:
        """
        Evalúa y emite el veredicto del Árbitro.

        Args:
            probabilidad_xgb: Probabilidad calculada por el modelo XGBoost (0.0 a 1.0).
            sentimiento_llm: Sentimiento calificado por el LLM (-1, 0, 1).
            contexto_noticia: Titular o resumen analizado.

        Returns:
            DecisionArbitro con la asignación final y estado de aprobación.
        """
        kelly_base = calcular_criterio_kelly(
            probabilidad_exito=probabilidad_xgb,
            ratio_ganancia_perdida=self.ratio_ganancia_perdida
        )

        # Reglas del Árbitro de 3 Pilares:
        if sentimiento_llm == 1:
            estado_llm = "EUFORIA (+1). El contexto apoya a la matemática."
            decision_final = kelly_base
            justificacion = "Confirmación cruzada alcista (matemática + contexto de mercado)."
        elif sentimiento_llm == 0:
            estado_llm = "NEUTRAL (0). Todo normal, operamos con precaución."
            decision_final = kelly_base * 0.5
            justificacion = "Contexto neutral. Se aplica reducción prudente al 50% de Kelly."
        elif sentimiento_llm == -1:
            estado_llm = "¡ALERTA! El sentimiento es PÁNICO (-1). Las matemáticas no ven esto."
            decision_final = 0.0
            justificacion = "Freno de emergencia cualitativo activado ante pánico o noticias catastróficas."
        else:
            estado_llm = f"DESCONOCIDO ({sentimiento_llm}). Operación preventiva neutralizada."
            decision_final = 0.0
            justificacion = "Sentimiento no reconocido; se aborta por política de seguridad."

        aprobada = decision_final > 0.0

        if self.verbose:
            self._imprimir_veredicto(
                probabilidad_xgb=probabilidad_xgb,
                kelly_base=kelly_base,
                contexto_noticia=contexto_noticia,
                estado_llm=estado_llm,
                decision_final=decision_final,
                aprobada=aprobada
            )

        return DecisionArbitro(
            aprobada=aprobada,
            asignacion_capital=round(decision_final, 4),
            probabilidad_xgb=probabilidad_xgb,
            kelly_base=round(kelly_base, 4),
            sentimiento_llm=sentimiento_llm,
            contexto_noticia=contexto_noticia,
            justificacion=justificacion
        )

    def _imprimir_veredicto(
        self,
        probabilidad_xgb: float,
        kelly_base: float,
        contexto_noticia: str,
        estado_llm: str,
        decision_final: float,
        aprobada: bool
    ) -> None:
        print("=" * 50)
        print("🤖 EL ÁRBITRO DE NOSTRADAMUS")
        print("=" * 50)
        print(f"📊 XGBoost: Mi probabilidad matemática de éxito es del {probabilidad_xgb * 100:.1f}%")
        print(f"🧮 Criterio Kelly recomienda invertir el {kelly_base * 100:.1f}% de nuestro capital.")
        print(f"\n📰 CONTEXTO NOTICIA: {contexto_noticia}")
        print(f"🧠 LLM: {estado_llm}")
        print("\n⚖️ DECISIÓN FINAL DEL ÁRBITRO:")
        if aprobada:
            print(f"✅ OPERACIÓN APROBADA. Arriesgaremos el {decision_final * 100:.1f}% de la cuenta.")
        else:
            print("❌ OPERACIÓN RECHAZADA. Se aborta para proteger el capital.")
        print("=" * 50)


def el_arbitro(
    probabilidad_xgb: float,
    titular_noticia: str,
    sentimiento_llm: Optional[int] = None,
    analizador_llm: Any = None
) -> DecisionArbitro:
    """
    Función de acceso directo equivalente a la celda original del notebook.
    Si no se pasa sentimiento_llm, intenta utilizar el analizador_llm provisto.
    """
    if sentimiento_llm is None:
        if analizador_llm is not None:
            sentimiento_llm = analizador_llm.analizar_titular(titular_noticia)
        else:
            raise ValueError("Debes proporcionar 'sentimiento_llm' o un 'analizador_llm' instanciado.")

    arbitro = ArbitroRiesgo(verbose=True)
    return arbitro.evaluar(
        probabilidad_xgb=probabilidad_xgb,
        sentimiento_llm=sentimiento_llm,
        contexto_noticia=titular_noticia
    )
