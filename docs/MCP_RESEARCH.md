# MCP de investigación de Nostradamus

## Objetivo

El servidor local `nostradamus-research` ofrece contexto externo verificable a
Codex mediante herramientas de solo lectura. No sustituye al pipeline de datos,
no escribe artefactos y no contiene operaciones de trading.

## Herramientas

| Herramienta | Fuente | Uso |
|---|---|---|
| `sources_describe` | Local | Capacidades, límites y reglas de uso. |
| `sources_health` | Todas | Configuración y prueba externa opcional. |
| `market_get_ohlcv` | Binance Spot | Velas diarias de BTC y ETH. |
| `market_compare_sources` | Binance + CoinGecko | Detección de divergencias. |
| `news_search` | GDELT o NewsAPI | Descubrimiento temporal de noticias. |
| `papers_search` | Crossref | DOI y metadatos bibliográficos. |

Todas las respuestas incluyen fuente, instante de consulta, parámetros, huella
SHA-256, registros y advertencias. Las claves se envían únicamente en cabeceras y
nunca se devuelven al cliente MCP.

## Instalación

Instala las dependencias del proyecto:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

El punto de entrada es:

```powershell
.\venv\Scripts\python.exe .\nostradamus_mcp.py stdio
```

Para registrarlo manualmente en Codex desde la raíz del proyecto:

```powershell
codex mcp add nostradamusResearch -- `
  "$PWD\venv\Scripts\python.exe" `
  "$PWD\nostradamus_mcp.py" `
  stdio
```

Comprueba la configuración con:

```powershell
codex mcp list
```

Valida el protocolo `stdio` de extremo a extremo con:

```powershell
.\venv\Scripts\python.exe .\scripts\verify_research_mcp.py
```

Codex debe reiniciar o comenzar una conversación nueva para descubrir herramientas
añadidas después de iniciar la sesión actual.

## Variables opcionales

El punto de entrada carga `.env` sin sobrescribir variables ya presentes en el
proceso. Parte de `.env.example` y no registres el archivo real:

- `NEWSAPI_KEY`: habilita `provider="newsapi"`.
- `COINGECKO_API_KEY`: aumenta la cuota de la API demo cuando corresponda.
- `CROSSREF_MAILTO`: identifica las consultas en el pool público de Crossref.

Binance, GDELT y Crossref funcionan sin claves. CoinGecko se intenta sin clave y
puede exigirla según sus límites vigentes.

## Contrato temporal

- `market_get_ohlcv` interpreta `start_date` como inclusiva y `end_date` como
  exclusiva. Solo consulta velas diarias. Si el rango alcanza el día UTC actual,
  la última vela puede seguir abierta; V6 la usa como cotización, no como
  característica cerrada.
- `news_search` exige fechas con zona horaria y normaliza a UTC.
- NewsAPI conserva `publishedAt` y registra un `captured_at` posterior a la consulta.
- GDELT expone `seendate`; el servidor la marca como `gdelt_seen_date`. No debe
  tratarse como fecha de publicación verificada sin revisar el artículo original.
- Una consulta MCP nunca constituye por sí sola un dataset experimental congelado.

## Flujo para evidencia científica

```text
Fuente externa
    -> consulta MCP
    -> revisión de cobertura y calidad
    -> captura versionada por el pipeline
    -> validación causal
    -> entrenamiento o backtesting
```

## Seguridad y límites

- Todas las herramientas declaran `readOnlyHint=true` y
  `destructiveHint=false`.
- El servidor no implementa cuentas, balances, órdenes ni endpoints privados.
- Los activos de mercado se limitan inicialmente a BTC-USD y ETH-USD.
- Binance representa un exchange; CoinGecko representa una referencia agregada.
- V6 consume Binance mediante el mismo adaptador normalizado del pipeline.
  CoinGecko solo genera un reporte de contraste y nunca se mezcla con OHLCV.
- NewsAPI depende de licencia y plan. GDELT DOC está orientado a cobertura reciente.
- Crossref entrega metadatos, no el texto completo ni una validación de conclusiones.

## Pruebas

Las pruebas usan respuestas simuladas y no necesitan Internet:

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_research_mcp -v
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```
