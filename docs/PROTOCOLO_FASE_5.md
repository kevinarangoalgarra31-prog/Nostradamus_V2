# Protocolo experimental — Fase 5

## Objetivo

Comparar decisiones de trading fuera de muestra sin ejecutar sobre el mismo
cierre que produjo la señal y sin conceder información inexistente a las
estrategias híbridas.

## Convención temporal

Para una predicción indexada en el cierre del día `t`:

1. la posición se decide con información disponible hasta `t`;
2. se entra en la apertura `t+1`;
3. se liquida o rebalancea en la apertura `t+2`.

El retorno ejecutable es `Open[t+2] / Open[t+1] - 1`. Esta convención impide
comprar retrospectivamente en el cierre que generó la señal.

## Estrategias

- B0: exposición larga continua.
- B1: largo cuando `Close > SMA_20` y `RSI_14 >= 50`.
- M1: largo cuando la probabilidad calibrada de XGBoost alcanza el umbral.
- M2: M1 solo con señal textual válida y no negativa.
- M3: Kelly fraccional limitado, multiplicado por 1.0 con sentimiento positivo,
  0.5 con neutral y 0.0 con negativo.

La falta de sentimiento implica abstención. M2/M3 solo se reportan cuando la
cobertura alcanza los mínimos configurados.

## Costos y métricas

Cada variación absoluta de exposición paga comisión más slippage en un solo
sentido. La entrada inicial y liquidación final también pagan costos. Se reportan
retorno total y anualizado, volatilidad, Sharpe, Sortino, drawdown máximo, profit
factor, exposición, entradas, transacciones, rotación, costos y tasa de acierto
durante periodos activos.

## Robustez

La V5 produce:

- sensibilidad a 0x, 1x y 2x costos;
- sensibilidad a umbrales de probabilidad;
- ablación de probabilidad calibrada contra probabilidad cruda;
- métricas por fold walk-forward;
- métricas condicionadas a volatilidad baja y alta.

El horizonte permanece en un día porque es el objetivo entrenado. Evaluar otro
horizonte exige reentrenar y versionar el modelo; cambiar solo el retorno del
backtest introduciría una comparación metodológicamente inválida.

## Ejecución

```powershell
python demo_v5.py
```

Para indicar un archivo acumulativo distinto:

```powershell
python demo_v5.py --sentiment-root output/v4_history
```

## Limitación actual

Las ventanas OOS V3 abarcan 2023–2025, mientras que la recolección real comenzó
en 2026. Por eso B0, B1 y M1 son evaluables, pero M2/M3 permanecen
`not_evaluable`. No se fabrican noticias históricas ni se usan titulares
capturados después de la decisión.
