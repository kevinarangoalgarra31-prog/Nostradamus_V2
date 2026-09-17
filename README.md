# Nostradamus V3

Arquitectura experimental para estudiar si XGBoost, una señal textual y reglas deterministas de riesgo aportan valor fuera de muestra en decisiones de trading. El proyecto prioriza trazabilidad y evaluación reproducible; no promete rentabilidad ni constituye asesoría financiera.

## Estado

- [x] Fase 1: definición experimental.
- [x] Fase 2: adquisición, validación, versionado e ingeniería causal de datos.
- [x] Fase 3: entrenamiento, calibración y validación walk-forward de XGBoost.
- [ ] Fase 4: señal de sentimiento con titulares fechados y verificables.
- [ ] Fase 5: árbitro de riesgo, backtesting comparativo y ablaciones.
- [ ] Fase 6: paper trading y análisis de estabilidad.

El código RSS conservado del prototipo no forma parte del alcance científico actual.

## Fases 1 y 2

La configuración canónica está en `config/experiment.yaml`. Allí se fijan universo, periodo, frecuencia, horizonte objetivo, ventanas, semilla y costos antes de entrenar un modelo.

El pipeline:

1. descarga o carga OHLCV;
2. normaliza columnas y fechas;
3. rechaza duplicados, precios incoherentes, volumen negativo o faltantes excesivos;
4. guarda CSV versionado y manifiesto JSON con SHA-256;
5. calcula retornos, SMA, EMA, MACD, RSI, volatilidad, momentum, rango y volumen relativo;
6. construye la etiqueta futura sin asignar un valor artificial a la última observación.

## Instalación

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Preparar datos

Descarga los activos declarados en la configuración:

```powershell
python prepare_data.py --config config/experiment.yaml
```

Prueba reproducible con un CSV local, sin escribir artefactos:

```powershell
python prepare_data.py --config config/experiment.yaml `
  --ticker BTC-USD `
  --input-csv data/raw/BTC_USD_2023-01-01.csv `
  --no-save
```

Los datos aceptados se guardan en `data/raw` y `data/processed`. Cada CSV tiene un manifiesto adyacente con metadatos, controles de calidad y huella del contenido.

## Demostración V3

La V3 selecciona hiperparámetros mediante particiones temporales internas, calibra las probabilidades sobre un bloque posterior y evalúa en un tercer bloque completamente fuera de muestra. Las ventanas de prueba no se solapan.

```powershell
python demo_v3.py `
  --config config/experiment.yaml `
  --modeling-config config/modeling_v3.yaml
```

La ejecución genera en `output/v3`:

- informe comparativo en Markdown;
- predicciones fuera de muestra;
- métricas por activo y por ventana;
- modelo XGBoost final y parámetros del calibrador;
- manifiesto que enlaza el modelo con la huella del dataset;
- gráficos de probabilidades, calibración, confusión e importancia de variables.

La demostración actual es deliberadamente honesta: muestra que la calibración mejora las probabilidades crudas, pero que el modelo técnico todavía no supera de forma consistente la línea base probabilística. Este resultado es válido como evidencia experimental y evita presentar una precisión inflada.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

Las pruebas no dependen de Internet: verifican configuración, validación OHLCV, manifiestos, hash, ausencia de lookahead, separación temporal, calibración y persistencia del modelo.

## Documentación

- `docs/PROTOCOLO_FASES_1_2.md`: decisiones, ejecución y criterios de aceptación.
- `docs/DICCIONARIO_DATOS.md`: significado de las variables derivadas.
- `config/modeling_v3.yaml`: protocolo de entrenamiento y búsqueda de hiperparámetros.
- `output/v3/DEMO_V3.md`: resultados reproducibles de la demostración.
- `docs/HOJA_DE_RUTA_POST_V3.md`: trabajo planificado para las fases posteriores.
- `output/docx` y `output/pdf`: propuesta y capítulos 1 a 3 reformulados.

`main.py` conserva el orquestador del prototipo para referencia. Los experimentos formales deben utilizar `prepare_data.py` y `demo_v3.py` con sus configuraciones versionadas.
