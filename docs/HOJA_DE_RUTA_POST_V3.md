# Hoja de ruta posterior a Nostradamus V3

## Punto de partida

La versión 3.0.0 cierra el cerebro cuantitativo como una demostración reproducible. Incluye datos versionados, características causales, XGBoost, selección temporal de hiperparámetros, calibración sigmoid, evaluación walk-forward y comparación con una línea base.

Los resultados actuales son una línea base científica, no una prueba de rentabilidad. La calibración reduce el error de las probabilidades crudas, pero el modelo técnico todavía no supera de manera consistente la probabilidad histórica simple. Las siguientes fases deben intentar aportar información nueva y medirla mediante ablaciones, sin ocultar resultados desfavorables.

## Fase 4 — señal textual verificable

### Objetivo

Construir una señal de sentimiento que solo utilice titulares disponibles antes de cada decisión y que pueda auditarse posteriormente.

### Implementaciones previstas

1. Definir una interfaz de proveedores independiente del mecanismo de adquisición.
2. Almacenar titular, fuente, enlace, idioma, fecha de publicación y fecha de captura.
3. Normalizar zonas horarias, eliminar duplicados y registrar periodos sin cobertura.
4. Rechazar contenido publicado después del instante de decisión.
5. Producir una salida estructurada: sentimiento, confianza, relevancia y evidencia.
6. Comparar el LLM con una línea base léxica o un modelo financiero especializado.
7. Crear un conjunto pequeño de titulares etiquetados manualmente para comprobar consistencia.

### Criterios de aceptación

- Toda señal puede reconstruirse desde su titular, fuente, fecha y versión del modelo.
- Las respuestas inválidas no se transforman silenciosamente en señales neutrales.
- Existe un estado explícito de datos insuficientes.
- La cobertura y el acuerdo entre fuentes se reportan como métricas.

## Fase 5 — arquitectura híbrida y backtesting

### Objetivo

Determinar qué componente agrega valor mediante configuraciones comparables:

- B0: comprar y mantener.
- B1: regla técnica simple.
- M1: XGBoost V3.
- M2: XGBoost más sentimiento.
- M3: M2 más árbitro determinista de riesgo.

### Implementaciones previstas

1. Motor de backtesting que ejecute la señal en el siguiente precio disponible.
2. Comisión, slippage, límites de exposición y reglas de salida configurables.
3. Estados del árbitro: operar, no operar y abstenerse.
4. Kelly fraccional limitado por activo y por operación.
5. Ablaciones que retiren uno a uno sentimiento, calibración y gestión de riesgo.
6. Sensibilidad a costos, umbrales, horizontes y cambios de régimen.
7. Métricas: retorno, volatilidad, Sharpe, Sortino, máximo drawdown, profit factor, exposición y número de operaciones.

### Criterios de aceptación

- Todas las configuraciones utilizan las mismas ventanas y costos.
- Ninguna señal usa información futura ni ejecuta sobre el mismo cierre que la produjo.
- Se reportan resultados favorables y desfavorables.
- Una mejora debe repetirse en varias ventanas y no depender de una sola operación.

## Fase 6 — paper trading y estabilidad

### Objetivo

Observar el sistema prospectivamente sin comprometer capital real.

### Implementaciones previstas

1. Ejecución programada con datos cerrados y registro inmutable de cada decisión.
2. Monitoreo de calidad de datos, deriva de variables y calibración reciente.
3. Comparación entre precio esperado, precio simulado y slippage observado.
4. Alertas por datos faltantes, degradación del modelo o límites de riesgo.
5. Informe post-mortem periódico y criterios explícitos para reentrenar.

### Criterios de aceptación

- Cada decisión conserva entradas, versiones, probabilidad, evidencia y regla aplicada.
- El sistema puede abstenerse y detenerse automáticamente.
- No existe conexión con una cuenta real durante el proyecto de grado.

## Fase 7 — cierre académico

1. Consolidar resultados, amenazas a la validez y limitaciones.
2. Actualizar los capítulos metodológicos con los experimentos ejecutados.
3. Preparar anexos de reproducibilidad y manual de usuario.
4. Elaborar presentación y demostración de sustentación.

## Orden obligatorio

La fase 4 debe terminar antes de integrar el árbitro. La fase 5 debe aprobar sus controles de lookahead y costos antes del paper trading. La conexión a capital real queda fuera del alcance del proyecto de grado.
