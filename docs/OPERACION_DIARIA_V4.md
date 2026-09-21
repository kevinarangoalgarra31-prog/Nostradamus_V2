# Operación diaria de la señal textual V4

## Propósito

Recolectar evidencia prospectiva sin mantener una terminal abierta y sin
sobrescribir ejecuciones. La tarea solo descarga titulares y calcula señales; no
envía órdenes ni se conecta a capital real.

## Requisitos

1. Dependencias instaladas en `venv`.
2. `GROQ_API_KEY` y `GROQ_MODEL` definidos en `.env` o en el entorno.
3. Modelo, prompt y configuración congelados durante el periodo de observación.

## Prueba manual acumulativa

```powershell
.\scripts\run_phase4_daily.ps1
```

Los resultados quedan en:

```text
output/v4_history/YYYY/MM/DD/run_id/
```

Cada ejecución conserva logs, titulares, exclusiones, evaluaciones, señales,
manifiestos y SHA-256. `collection_index.jsonl` permite enumerar las corridas.

## Instalar la tarea de Windows

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install_phase4_task.ps1
```

El horario predeterminado es 18:55 en la zona horaria local. Puede cambiarse:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install_phase4_task.ps1 `
  -DailyAt "18:55"
```

Instalar esta tarea autoriza llamadas diarias a Groq y el consumo asociado de su
cuenta. Por esa razón el proyecto entrega el instalador, pero no registra la
tarea silenciosamente.

La ejecución cercana al cierre diario UTC facilita alinear la señal textual con
la vela diaria sin usar noticias posteriores al instante de decisión.

## Etiquetado humano

```powershell
python phase4_labels.py --sample-size 100
```

Edite únicamente `manual_label` y `label_notes` en
`data/labels/phase4_labeling_queue.csv`. Valores permitidos:

- `-1`: negativo;
- `0`: neutral;
- `1`: positivo.

Ejecute nuevamente el mismo comando para incorporar titulares nuevos y producir
`output/v4_history/label_evaluation.json`. Las etiquetas ya ingresadas se
conservan.

## Supervisión

Revise semanalmente los logs, `coverage_status`, respuestas inválidas y número de
fuentes. Una falla diaria no debe rellenarse como neutral; permanece como falta
de cobertura.
