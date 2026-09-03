"""
Módulo de Gestión de Riesgo: Criterio de Kelly.
Calcula el dimensionamiento óptimo teórico de la posición en función de la probabilidad de éxito.
"""


def calcular_criterio_kelly(
    probabilidad_exito: float,
    ratio_ganancia_perdida: float = 1.0,
    fraccion_kelly: float = 1.0
) -> float:
    """
    Calcula el porcentaje de capital a invertir según el Criterio de Kelly.

    Fórmula:
        Kelly% = p - (q / b)
        donde:
            p = probabilidad de éxito (0.0 a 1.0)
            q = 1.0 - p (probabilidad de pérdida)
            b = ratio ganancia / pérdida (payoff ratio)

    Args:
        probabilidad_exito: Probabilidad estadística de ganar (de 0.0 a 1.0).
        ratio_ganancia_perdida: Relación entre beneficio potencial y pérdida potencial (b).
        fraccion_kelly: Multiplicador de prudencia (ej. 0.5 para Half-Kelly). Por defecto: 1.0.

    Returns:
        float: Fracción recomendada del capital (entre 0.0 y 1.0).
    """
    if not (0.0 <= probabilidad_exito <= 1.0):
        raise ValueError(f"La probabilidad debe estar entre 0.0 y 1.0. Recibido: {probabilidad_exito}")

    if ratio_ganancia_perdida <= 0.0:
        raise ValueError("El ratio ganancia/pérdida debe ser mayor a 0.")

    p = probabilidad_exito
    q = 1.0 - p
    kelly = p - (q / ratio_ganancia_perdida)

    # Si Kelly es negativo o cero, no se debe arriesgar capital
    if kelly <= 0:
        return 0.0

    # Aplicar factor fraccional de Kelly y restringir al 100% (1.0)
    asignacion = min(1.0, kelly * fraccion_kelly)
    return round(float(asignacion), 4)

