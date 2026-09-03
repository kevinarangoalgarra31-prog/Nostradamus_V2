# Hoja de Ruta - Proyecto Nostradamus (Arquitectura Híbrida)

## 1. Visión General
El proyecto Nostradamus evolucionará de un prototipo conceptual a un sistema cuantitativo híbrido. La arquitectura combinará el poder estadístico de algoritmos tradicionales (XGBoost) para procesar números, con la capacidad de comprensión de texto de los Modelos de Lenguaje Grande (LLMs) para procesar contexto y mitigar riesgo.

## 2. Arquitectura de 3 Pilares

### Pilar 1: Cerebro Cuantitativo (Machine Learning Clásico - XGBoost)
- **Función:** Analizar el histórico de precios y generar una probabilidad matemática de éxito.
- **Datos de Entrada:** OHLCV (Apertura, Máximo, Mínimo, Cierre, Volumen) e indicadores técnicos (RSI, MACD, Medias Móviles).
- **Salida:** Probabilidad estadística base (ej. 65% de probabilidad de subida).

### Pilar 2: Cerebro Cualitativo (LLM - Análisis de Sentimiento y Contexto)
- **Función:** Actuar como analista fundamental leyendo el contexto del mundo real que los números no ven.
- **Datos de Entrada:** Titulares de noticias financieras, publicaciones clave de Reddit o reportes económicos recientes.
- **Salida:** Puntaje numérico de sentimiento (-1 a +1) y resumen cualitativo de riesgos inminentes.

### Pilar 3: El Árbitro (Gestión de Riesgo Dinámica y Decisión)
- **Función:** Tomar la decisión final de inversión combinando el Pilar 1 y Pilar 2.
- **Lógica:** Se utiliza el **Criterio de Kelly** para definir cuánto capital invertir basándose en la probabilidad generada por el XGBoost. Sin embargo, el **LLM ajusta este riesgo**: si el LLM detecta un sentimiento extremadamente negativo o noticias catastróficas, penaliza el tamaño de la posición o aborta la operación por completo. El LLM actúa como un freno de emergencia cualitativo.

---

## 3. Plan de Acción (Desarrollo Iterativo en Jupyter Notebooks)

Para construir esto paso a paso, asegurar el aprendizaje, y validar cada pieza estadísticamente antes de integrarla, el desarrollo se dividirá en las siguientes fases interactivas:

- [ ] **Fase 1: Recolección de Datos Reales (Data Fetching).**
  - Aprender a descargar datos históricos de precios usando APIs gratuitas (como `yfinance`).
  - Exploración y visualización inicial de los datos (gráficas de velas, volumen).
  
- [ ] **Fase 2: Ingeniería de Características (Feature Engineering).**
  - Calcular indicadores matemáticos (RSI, MACD, Volatilidad).
  - Preparar y limpiar la tabla de datos para que un modelo de Machine Learning pueda consumirla.

- [ ] **Fase 3: Entrenamiento del Cerebro Cuantitativo (XGBoost).**
  - Entrenar el modelo con datos del pasado.
  - Evaluar la precisión del modelo aislando datos recientes que el modelo nunca ha visto (Train/Test split).

- [ ] **Fase 4: Integración del LLM para Análisis Cualitativo.**
  - Conectar el sistema a Groq (LLaMA) u otro LLM.
  - Crear los "prompts" (instrucciones) adecuados para que el LLM lea titulares de un día específico y devuelva un puntaje estructurado (JSON).

- [ ] **Fase 5: Backtesting Combinado (La Prueba de Fuego).**
  - Simular operaciones históricas combinando las señales de XGBoost y el filtro de riesgo del LLM.
  - Evaluar el desempeño final utilizando métricas profesionales (Sharpe Ratio, Retorno Total, Drawdown Máximo) frente a una estrategia simple de "Comprar y Mantener".

