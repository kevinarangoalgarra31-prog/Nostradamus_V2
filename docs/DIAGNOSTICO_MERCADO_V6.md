# Diagnóstico de mercado V6 — 2026-10-01

## Incidente observado

La corrida del 2026-09-21 registró `abstain` para BTC-USD y ETH-USD antes de la
inferencia. En ambos casos, la descarga de Yahoo Finance contenía una fila que
incumplía las relaciones OHLC. Los diarios solo conservaron el error agregado:

```text
DataValidationError: Hay 1 filas con relaciones OHLC inválidas.
```

No se puede reconstruir cuál fue la fila exacta porque aquella corrida no
congeló la respuesta cruda del proveedor. Sí se puede aislar el fallo a la etapa
de adquisición/validación primaria: ocurrió antes de cargar sentimiento, aplicar
el árbitro o simular una posición.

## Contraste de fuentes

El 2026-10-01 se ejecutó el diagnóstico de solo lectura para el periodo
2026-09-24 a 2026-10-01, con fin exclusivo:

```powershell
python -m scripts.diagnose_market_sources --asset BTC-USD `
  --start-date 2026-09-24 --end-date 2026-10-01
python -m scripts.diagnose_market_sources --asset ETH-USD `
  --start-date 2026-09-24 --end-date 2026-10-01
```

| Activo | Velas Binance | OHLC inválido | Solape CoinGecko | Alertas > 2% | Diferencia máxima |
|---|---:|---:|---:|---:|---:|
| BTC-USD | 7 | 0 | 7 | 0 | 0.3574% |
| ETH-USD | 7 | 0 | 7 | 0 | 0.5122% |

Huellas de las respuestas Binance:

- BTC-USD: `b1d94850a7e6cddd1b959d720ff21cfed6319e8a367f0f2f0f3f197f43b68517`.
- ETH-USD: `fe9d1746944bc1dffe4e15418abb4867c9ee1b762744ea74465379a019416442`.

## Corrección aplicada

- El pipeline admite `yfinance` y `binance` como fuentes explícitas.
- V6 usa Binance sin fallback; una falla permanece como estado explícito.
- CoinGecko solo contrasta cierres recientes y no modifica la serie primaria.
- Una divergencia superior al umbral bloquea la decisión.
- Una indisponibilidad de CoinGecko se registra y solo bloquea cuando la
  configuración declara la referencia como obligatoria.
- Cada decisión conserva fuente, huella de la respuesta y reporte de contraste.

## Corrida controlada

Se ejecutó V6 a `2026-10-01T00:10:00Z` con salida aislada en
`tmp/v6_milestone_1_2`. Ambos activos completaron adquisición, validación,
características e inferencia usando Binance; el contraste CoinGecko fue `ok` con
siete días de solape y cero alertas. Las decisiones terminaron en `abstain`
únicamente porque la señal V4 disponible tenía 219.70 horas de antigüedad.

No se modificaron los diarios reales de `output/v6` ni se enviaron órdenes.
