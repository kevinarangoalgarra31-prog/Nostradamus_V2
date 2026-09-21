# Protocolo experimental — Fase 4

## Propósito

La Fase 4 produce una señal textual auditable sin integrarla todavía con el
modelo cuantitativo ni interpretar su resultado como rentabilidad. La unidad de
evidencia es un titular asociado a activo, fuente, enlace, idioma, fecha de
publicación y fecha de captura.

## Contrato temporal

Para una decisión en el instante `t`, un titular solo se acepta cuando:

1. `published_at <= t`;
2. `captured_at <= t`;
3. `published_at <= captured_at`;
4. está dentro de la ventana retrospectiva configurada;
5. pertenece al activo e idioma declarados;
6. no repite un título o enlace ya aceptado.

Las fechas sin zona horaria se rechazan. Internamente todas las fechas se
normalizan a UTC. Un registro excluido conserva una causa explícita; nunca se
elimina silenciosamente.

## Proveedores

- `CsvNewsProvider`: reproduce corpus históricos y conjuntos etiquetados.
- `GoogleNewsRssProvider`: adquiere titulares en vivo y conserva la huella del
  payload recibido.

Ambos implementan la misma interfaz y separan adquisición de análisis. Una fila
malformada genera un incidente de proveedor que aparece en la auditoría.

## Analizadores

### Línea base léxica

El léxico bilingüe produce sentimiento `-1`, `0` o `1`, puntaje continuo,
confianza, relevancia y términos coincidentes. Su versión queda registrada en
cada evaluación.

### LLM estructurado

El adaptador solicita un objeto JSON estricto con sentimiento, puntaje,
confianza, relevancia y evidencia literal copiada del titular. Faltantes, campos
adicionales, rangos inválidos o evidencia inventada producen
`invalid_response`. Errores de red o proveedor producen `error`. Ninguno de esos
estados se imputa como neutral.

## Agregación y cobertura

Solo participan evaluaciones `ok` cuya relevancia alcance el umbral. El puntaje
se pondera por confianza y relevancia. Si no existen observaciones válidas se
emite `no_data`; si son menos que el mínimo configurado se emite
`insufficient_data`. Una señal válida reporta cobertura, fuentes únicas, acuerdo
entre fuentes e identificadores de los titulares usados.

La evaluación compara cobertura, accuracy y macro-F1 contra etiquetas manuales,
además del acuerdo entre analizadores sobre observaciones comunes. Las métricas
no imputan fallos del LLM.

## Artefactos

Cada activo genera:

- `headlines.csv`: evidencia aceptada;
- `rejected.json`: exclusiones e incidentes;
- `assessments.csv`: salidas individuales con versión del modelo;
- `signals.json`: señal agregada y estado de cobertura;
- `evaluation.json`: métricas y acuerdo;
- `run_manifest.json`: configuración y SHA-256 de los artefactos.

## Ejecución

Demostración offline:

```powershell
python phase4_sentiment.py --decision-at 2026-01-08T00:00:00Z
```

Noticias en vivo:

```powershell
python phase4_sentiment.py --provider google_news --ticker BTC-USD
```

Comparación con LLM:

```powershell
$env:GROQ_API_KEY = "su_clave"
$env:GROQ_MODEL = "modelo_fijado_para_el_experimento"
python phase4_sentiment.py --provider google_news --with-llm
```

Recolección acumulativa:

```powershell
python phase4_sentiment.py --provider google_news --with-llm `
  --archive-run --output-dir output/v4_history
```

Cada corrida usa una ruta UTC única y añade una entrada a
`collection_index.jsonl`. `scripts/install_phase4_task.ps1` instala el ejecutor
diario y `phase4_labels.py` crea una muestra que conserva etiquetas humanas.

## Limitación del conjunto incluido

`data/reference/headlines_v4_labeled_seed.csv` contiene titulares sintéticos
etiquetados manualmente. Sirve para probar el flujo offline y sus métricas, pero
su accuracy no es evidencia empírica. Antes de la Fase 5 debe congelarse un
corpus real con enlaces y capturas verificables y ejecutar la comparación contra
el modelo LLM fijado.
