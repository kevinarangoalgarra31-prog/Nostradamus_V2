# Demostración Nostradamus V4

## Alcance

Esta demostración valida de forma offline la mecánica de la señal textual:
lectura de titulares, auditoría temporal, análisis léxico, agregación,
evaluación y persistencia. No usa el modelo cuantitativo, no simula operaciones
y no demuestra rentabilidad.

## Datos

- Instante de decisión: `2026-01-08T00:00:00Z`.
- Ventana retrospectiva: 168 horas.
- Activos: BTC-USD y ETH-USD.
- Titulares por activo: 6.
- Etiquetas: dos positivas, dos neutrales y dos negativas por activo.
- Naturaleza: datos sintéticos de desarrollo, no evidencia empírica.

## Resultado de la línea base

El conjunto está diseñado para comprobar las tres clases del léxico, por lo que
la línea base alcanza cobertura 1.0, accuracy 1.0 y macro-F1 1.0. Estas métricas
solo son una prueba funcional. No deben reportarse como desempeño sobre noticias
reales.

## Criterios comprobados

- fechas normalizadas a UTC;
- rechazo de publicación o captura posterior a la decisión;
- deduplicación de títulos y enlaces;
- estados `no_data`, `insufficient_data`, `invalid_response` y `error`;
- respuesta estructurada con confianza, relevancia y evidencia;
- comparación con etiquetas manuales y entre analizadores;
- manifiestos con modelos y huellas SHA-256.

La comparación real LLM versus línea base requiere fijar `GROQ_MODEL`, congelar
un corpus real verificable y ejecutar `phase4_sentiment.py --with-llm`.
