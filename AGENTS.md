# AGENTS.md — Nostradamus V2/V6

## Propósito y alcance

Este repositorio es una investigación reproducible sobre señales cuantitativas,
sentimiento y reglas deterministas de riesgo para criptoactivos. El objetivo es
producir evidencia auditable fuera de muestra; no prometer rentabilidad ni operar
capital real.

Estas instrucciones aplican a todo el repositorio. Antes de modificar una fase,
consulta su configuración en `config/` y su protocolo en `docs/`.

## Fuentes de verdad

- `README.md`: estado general, instalación y comandos de usuario.
- `config/experiment.yaml`: universo, fechas, objetivo, características, semilla y costos.
- `config/modeling_v3.yaml`: entrenamiento, calibración y walk-forward.
- `config/sentiment_v4.yaml`: adquisición y análisis textual.
- `config/backtesting_v5.yaml`: estrategias, costos y métricas de backtesting.
- `config/paper_trading_v6.yaml`: límites de tiempo, exposición y estabilidad.
- `docs/PROTOCOLO_*.md`: contratos metodológicos y criterios de aceptación.
- `docs/HOJA_DE_RUTA_POST_V3.md`: alcance implementado y siguiente fase.

Si código, documentación y configuración discrepan, no elijas silenciosamente una
interpretación: identifica la discrepancia y mantén sincronizados los archivos que
formen parte del cambio.

## Mapa del proyecto

- `src/config/`: carga y validación de configuraciones.
- `src/data_pipeline/`: OHLCV, validación, artefactos y características causales.
- `src/models/`: XGBoost, calibración y evaluación walk-forward.
- `src/sentiment/`: dominio, proveedores, auditoría, analizadores y artefactos V4.
- `src/backtesting/`: carga de insumos, simulación causal y reportes V5.
- `src/paper_trading/`: inferencia, riesgo, liquidación y diarios V6.
- `src/research_mcp/`: fuentes públicas de solo lectura para contexto exploratorio.
- `src/risk_manager/`: árbitro y Kelly fraccional.
- `tests/`: pruebas offline con `unittest`.
- `output/`: evidencia y resultados versionados de las fases.
- `legacy_v1/` y `main.py`: prototipo conservado como referencia; no son la ruta
  científica vigente y no deben extenderse salvo petición explícita.

Los puntos de entrada vigentes son `prepare_data.py`, `demo_v3.py`,
`phase4_sentiment.py`, `phase4_labels.py`, `demo_v5.py`,
`phase6_paper_trade.py`, `nostradamus_cli.py`, `nostradamus_mcp.py` y
`scripts/diagnose_market_sources.py` (mediante `python -m`).

## Entorno y comandos

El entorno local esperado es Windows/PowerShell y Python. Prefiere el intérprete
del repositorio cuando exista:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\venv\Scripts\python.exe .\nostradamus_cli.py
```

Comandos de las fases:

```powershell
.\venv\Scripts\python.exe .\prepare_data.py --config config/experiment.yaml
.\venv\Scripts\python.exe .\demo_v3.py
.\venv\Scripts\python.exe .\phase4_sentiment.py --decision-at 2026-01-08T00:00:00Z
.\venv\Scripts\python.exe .\demo_v5.py
.\venv\Scripts\python.exe .\phase6_paper_trade.py
.\venv\Scripts\python.exe .\nostradamus_mcp.py stdio
```

Las pruebas deben seguir siendo reproducibles sin Internet, claves ni servicios
externos. No ejecutes adquisición en vivo, llamadas a Groq, instalación de tareas
de Windows ni el ciclo diario salvo que la petición lo requiera expresamente.

## Invariantes que no se deben romper

1. No introduzcas lookahead. Las características en `t` solo usan información
   disponible en `t`; `Target` y `Target_Return` nunca entran al modelo.
2. La última observación sin futuro no recibe una etiqueta sintética.
3. La selección de hiperparámetros, calibración y prueba mantienen orden temporal
   y conjuntos separados; las ventanas externas de prueba no se solapan.
4. En backtesting, la señal del cierre `t` se ejecuta en la apertura `t+1` y se
   liquida o rebalancea según el protocolo en una apertura posterior. No ejecutes
   sobre el mismo precio que produjo la señal.
5. Una noticia solo es válida si publicación y captura son anteriores o iguales a
   `decision_at`. Conserva fechas con zona horaria y normaliza a UTC.
6. Ausencia de cobertura, respuesta LLM inválida o dato inconsistente permanecen
   como estados explícitos (`no_data`, `insufficient_data`, `invalid_response` o
   `abstain`); nunca los conviertas silenciosamente en neutral.
7. Comisiones, slippage, exposición y Kelly proceden de configuración y se aplican
   de forma comparable entre estrategias.
8. V6 es exclusivamente paper trading. No agregues conexiones a brokers, envío de
   órdenes ni manejo de credenciales de trading.
9. Conserva trazabilidad: manifiestos, versiones, rutas de insumos y SHA-256 deben
   seguir permitiendo reconstruir cada resultado.
10. El MCP aporta contexto exploratorio. Antes de entrenar o evaluar, congela sus
    datos como artefactos del pipeline y aplica las validaciones de la fase.
11. La fuente de mercado es única por corrida. CoinGecko es una referencia de
    contraste: nunca completa, promedia ni sustituye OHLCV del proveedor primario.

## Datos, secretos y artefactos

- No leas, muestres, edites ni confirmes `.env`; usa `.env.example` para documentar
  variables y nunca registres claves en Git, logs, pruebas o artefactos.
- `data/raw/`, `data/processed/`, `stockdata/`, `tmp/` y el entorno `venv/` son
  locales o generados. No los borres ni los incorpores al control de versiones.
- `output/` contiene evidencia rastreada. No regeneres ni sobrescribas resultados
  ajenos al cambio. Si una tarea exige regenerarlos, explica qué comando y qué
  configuración los produjo y revisa el diff resultante.
- `output/v6/decisions.jsonl` y `output/v6/settlements.jsonl` son diarios
  append-only con cadena de hashes. Nunca edites, reordenes, trunques ni fabriques
  líneas históricas.
- En `data/labels/phase4_labeling_queue.csv`, el etiquetado humano solo modifica
  `manual_label` y `label_notes`.

## Convenciones de implementación

- Mantén compatibilidad con el Python definido por el entorno del proyecto y con
  las dependencias fijadas en `requirements.txt`.
- Sigue el estilo existente: `from __future__ import annotations`, type hints,
  `dataclass` para contratos de datos, `pathlib.Path`, UTF-8 y funciones pequeñas.
- Conserva el español en mensajes, documentación y API pública existente. Usa
  inglés cuando ya sea el vocabulario del dominio o del artefacto.
- Mantén la lógica de cálculo pura separada de red, disco y CLI cuando sea posible.
- Valida entradas temprano y usa errores o estados explícitos; no ocultes fallos con
  valores por defecto que alteren la interpretación científica.
- Evita dependencias nuevas si la biblioteca estándar o una dependencia existente
  resuelve el problema. Si añades una, justifica y fija su versión.
- No reformatees archivos o artefactos no relacionados con la tarea.

## Verificación de cambios

Ejecuta primero las pruebas directamente relacionadas y, antes de entregar cambios
de código, la suite completa:

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_phase_1_2 -v
.\venv\Scripts\python.exe -m unittest tests.test_phase_3 -v
.\venv\Scripts\python.exe -m unittest tests.test_phase_4 -v
.\venv\Scripts\python.exe -m unittest tests.test_phase_5 -v
.\venv\Scripts\python.exe -m unittest tests.test_phase_6 -v
.\venv\Scripts\python.exe -m unittest tests.test_cli_menu -v
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

Para toda corrección de un defecto, añade o ajusta una prueba que falle antes del
arreglo. Las pruebas que escriben archivos deben usar directorios temporales y no
modificar `output/`, los datos locales ni los diarios reales.

## Criterio de entrega

Antes de finalizar:

1. Revisa `git diff` y confirma que el alcance sea mínimo.
2. Indica pruebas ejecutadas y resultado.
3. Señala artefactos regenerados, limitaciones o verificaciones no realizadas.
4. Actualiza README, protocolo o configuración cuando cambie un contrato observable.
5. Reporta resultados desfavorables y estados no evaluables con la misma claridad
   que los favorables.
