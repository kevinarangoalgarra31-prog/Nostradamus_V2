# Nostradamus V6

Arquitectura experimental para estudiar si XGBoost, una señal textual y reglas deterministas de riesgo aportan valor fuera de muestra en decisiones de trading. El proyecto prioriza trazabilidad y evaluación reproducible; no promete rentabilidad ni constituye asesoría financiera.

## Estado

- [x] Fase 1: definición experimental.
- [x] Fase 2: adquisición, validación, versionado e ingeniería causal de datos.
- [x] Fase 3: entrenamiento, calibración y validación walk-forward de XGBoost.
- [x] Fase 4: señal de sentimiento con titulares fechados y verificables.
- [x] Fase 5: motor de backtesting, árbitro, costos, ablaciones y sensibilidad. M2/M3 esperan cobertura histórica real.
- [x] Fase 6: paper trading prospectivo, diario inmutable y controles de estabilidad.
- [ ] Fase 7: cierre académico y sustentación.

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

## Menú interactivo

En Windows puede abrirse `INICIAR_NOSTRADAMUS.bat` con doble clic. El menú
permite ejecutar el ciclo diario, consultar el paper portfolio, revisar el
historial, actualizar etiquetas y lanzar las pruebas sin recordar parámetros.

También puede iniciarse desde una terminal:

```powershell
python .\nostradamus_cli.py
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

## Señal textual V4

La Fase 4 incorpora proveedores intercambiables de titulares, normalización UTC,
deduplicación y controles que rechazan una noticia si fue publicada o capturada
después de la decisión. Cada evaluación conserva fuente, enlace, fechas, modelo,
versión, confianza, relevancia y evidencia textual.

Demostración offline reproducible con el conjunto etiquetado de desarrollo:

```powershell
python phase4_sentiment.py `
  --decision-at 2026-01-08T00:00:00Z
```

Adquisición en vivo mediante Google News RSS:

```powershell
python phase4_sentiment.py --provider google_news --ticker BTC-USD
```

Comparación entre el LLM estructurado y la línea base léxica:

```powershell
$env:GROQ_API_KEY = "su_clave"
$env:GROQ_MODEL = "modelo_fijado_para_el_experimento"
python phase4_sentiment.py --provider google_news --with-llm
```

Recolección acumulativa manual, sin sobrescribir ejecuciones anteriores:

```powershell
python phase4_sentiment.py `
  --provider google_news `
  --with-llm `
  --archive-run `
  --output-dir output/v4_history
```

Para instalar la tarea diaria de Windows a las 18:55, hora local:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install_phase4_task.ps1
```

La tarea ejecuta `scripts/run_phase4_daily.ps1`, conserva un log por ejecución y
añade cada corrida a `output/v4_history/collection_index.jsonl`. No se conecta a
una cuenta de trading. Cada ejecución sí consume llamadas de la cuenta Groq
configurada; el instalador no se ejecuta automáticamente.

Después de acumular titulares, crea o actualiza una muestra para etiquetado:

```powershell
python phase4_labels.py --sample-size 100
```

El archivo `data/labels/phase4_labeling_queue.csv` conserva las etiquetas humanas
existentes al incorporar noticias nuevas. Solo se deben editar `manual_label`
(`-1`, `0`, `1`) y `label_notes`.

Una respuesta LLM inválida queda marcada como `invalid_response`; nunca se
convierte silenciosamente en neutral. Si la cobertura es insuficiente, la señal
queda en `no_data` o `insufficient_data`.

## Backtesting V5

La Fase 5 compara B0 comprar y mantener, B1 regla técnica y M1 XGBoost sobre las
mismas 900 observaciones fuera de muestra por activo. La señal se genera en el
cierre `t`, se ejecuta en la apertura `t+1` y se liquida o rebalancea en la
apertura `t+2`. Cada cambio de posición paga los mismos costos configurados.

```powershell
python demo_v5.py
```

La ejecución genera en `output/v5` métricas, curvas de capital, resultados por
ventana, sensibilidad a costos y umbrales, ablación de calibración y análisis por
régimen de volatilidad.

M2 y M3 solo se calculan si las señales LLM cubren al menos el 80% y 30 filas de
la ventana común. Actualmente aparecen como `not_evaluable`: las noticias reales
recogidas en 2026 no se imputan artificialmente sobre predicciones OOS de
2023–2025.

## Paper trading V6

La Fase 6 carga el modelo y calibrador V3, usa la última vela diaria cerrada,
enlaza la señal V4 más reciente y aplica el árbitro M3. No se conecta a un
broker. Las decisiones y liquidaciones simuladas forman diarios append-only con
hash encadenado.

Ejecución manual completa, recomendada entre las 19:05 y 20:15 de Colombia:

```powershell
python .\nostradamus_cli.py
```

En el menú seleccione la opción **1. Ejecutar ciclo diario completo**. El script
PowerShell `scripts/run_daily_paper_trading.ps1` permanece disponible como
alternativa no interactiva.

El sistema se abstiene ante ejecución tardía, señal ausente o vieja, deriva
severa, drawdown excesivo o degradación del Brier reciente. Una decisión válida
del mismo activo no se duplica durante el mismo día.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

Las pruebas no dependen de Internet: verifican configuración, validación OHLCV,
manifiestos, hash, ausencia de lookahead, separación temporal, calibración,
persistencia del modelo, auditoría de titulares, validación estricta del LLM,
archivado acumulativo, backtesting causal, inferencia viva, diarios encadenados,
deriva, límites de riesgo y liquidación simulada.

## Documentación

- `docs/PROTOCOLO_FASES_1_2.md`: decisiones, ejecución y criterios de aceptación.
- `docs/DICCIONARIO_DATOS.md`: significado de las variables derivadas.
- `config/modeling_v3.yaml`: protocolo de entrenamiento y búsqueda de hiperparámetros.
- `output/v3/DEMO_V3.md`: resultados reproducibles de la demostración.
- `docs/PROTOCOLO_FASE_4.md`: contrato, controles y ejecución de la señal textual.
- `config/sentiment_v4.yaml`: parámetros versionados de adquisición y análisis.
- `output/v4/DEMO_V4.md`: alcance y resultados de la demostración offline.
- `docs/OPERACION_DIARIA_V4.md`: recolección automática y etiquetado humano.
- `docs/PROTOCOLO_FASE_5.md`: ejecución, estrategias, costos y limitaciones.
- `config/backtesting_v5.yaml`: contrato del backtesting.
- `output/v5/DEMO_V5.md`: resultados comparativos fuera de muestra.
- `docs/PROTOCOLO_FASE_6.md`: horario, controles, diarios y operación manual.
- `config/paper_trading_v6.yaml`: límites temporales, riesgo y estabilidad.
- `docs/HOJA_DE_RUTA_POST_V3.md`: trabajo planificado para las fases posteriores.
- `output/docx` y `output/pdf`: propuesta y capítulos 1 a 3 reformulados.

`main.py` conserva el orquestador del prototipo para referencia. Los experimentos
formales deben utilizar `prepare_data.py`, `demo_v3.py`,
`phase4_sentiment.py`, `demo_v5.py` y `phase6_paper_trade.py` con sus
configuraciones versionadas.
