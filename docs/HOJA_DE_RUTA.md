# Hoja de Ruta - Proyecto Nostradamus V3 (Arquitectura Híbrida)

## 1. Visión General
El proyecto Nostradamus evolucionará de un prototipo conceptual a un sistema cuantitativo híbrido. La arquitectura combinará el poder estadístico de algoritmos tradicionales (XGBoost) para procesar números, con la capacidad de comprensión de texto de los Modelos de Lenguaje Grande (LLMs) para procesar contexto y mitigar riesgo.

## 2. Arquitectura de 3 Pilares

### Pilar 1: Cerebro Cuantitativo (Machine Learning Clásico - XGBoost)
- **Función:** Analizar el histórico de precios y generar una probabilidad matemática de éxito.
- **Datos de Entrada:** OHLCV (Apertura, Máximo, Mínimo, Cierre, Volumen) e indicadores técnicos (RSI, MACD, Medias Móviles).
- **Salida:** Probabilidad calibrada de subida, acompañada por evidencia fuera de muestra.

### Pilar 2: Cerebro Cualitativo (LLM - Análisis de Sentimiento y Contexto)
- **Función:** Actuar como analista fundamental leyendo el contexto del mundo real que los números no ven.
- **Datos de Entrada:** Titulares financieros con fuente y fecha de publicación verificables.
- **Salida:** Puntaje numérico de sentimiento (-1 a +1) y resumen cualitativo de riesgos inminentes.

### Pilar 3: El Árbitro (Gestión de Riesgo Dinámica y Decisión)
- **Función:** Tomar la decisión final de inversión combinando el Pilar 1 y Pilar 2.
- **Lógica:** Se utiliza el **Criterio de Kelly** para definir cuánto capital invertir basándose en la probabilidad generada por el XGBoost. Sin embargo, el **LLM ajusta este riesgo**: si el LLM detecta un sentimiento extremadamente negativo o noticias catastróficas, penaliza el tamaño de la posición o aborta la operación por completo. El LLM actúa como un freno de emergencia cualitativo.

---

## 3. Plan de Acción (Desarrollo Iterativo en Jupyter Notebooks)

Para construir esto paso a paso, asegurar el aprendizaje, y validar cada pieza estadísticamente antes de integrarla, el desarrollo se dividirá en las siguientes fases interactivas:

- [x] **Fase 1: Definición y Recolección de Datos Reales (Data Fetching).**
  - Configuración versionada de activos, periodo, frecuencia, horizonte, costos y semilla.
  - Aprender a descargar datos históricos de precios usando APIs gratuitas (como `yfinance`).
  - Validar, versionar y generar una huella SHA-256 de cada dataset aceptado.
  
- [x] **Fase 2: Ingeniería de Características (Feature Engineering).**
  - Calcular retornos, SMA, EMA, RSI, MACD, volatilidad, momentum, rango y volumen relativo.
  - Construir la etiqueta futura sin asignar valores artificiales ni usar información posterior.
  - Preparar y documentar la tabla para que un modelo de Machine Learning pueda consumirla.

- [x] **Fase 3: Entrenamiento del Cerebro Cuantitativo (XGBoost).**
  - Seleccionar hiperparámetros con particiones temporales internas.
  - Calibrar probabilidades en una ventana posterior al entrenamiento.
  - Evaluar cinco ventanas walk-forward sin solapamiento y compararlas con una línea base.
  - Guardar modelos, calibradores, predicciones, métricas, gráficas y manifiestos reproducibles.

- [ ] **Fase 4: Integración del LLM para Análisis Cualitativo.**
  - Conectar el sistema a Groq (LLaMA) u otro LLM.
  - Crear los "prompts" (instrucciones) adecuados para que el LLM lea titulares de un día específico y devuelva un puntaje estructurado (JSON).

- [ ] **Fase 5: Backtesting Combinado (La Prueba de Fuego).**
  - Simular operaciones históricas combinando las señales de XGBoost y el filtro de riesgo del LLM.
  - Evaluar el desempeño final utilizando métricas profesionales (Sharpe Ratio, Retorno Total, Drawdown Máximo) frente a una estrategia simple de "Comprar y Mantener".
