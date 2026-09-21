# Protocolo operativo — Fase 6

## Objetivo

Observar prospectivamente el sistema híbrido sin enviar órdenes ni conectarse a
un broker. Cada decisión conserva datos, modelo, calibrador, señal textual,
reglas, precio de referencia y huellas criptográficas.

## Convención temporal

Las velas diarias de cripto cierran a las 00:00 UTC. El proceso debe iniciarse
poco después de ese cierre. En Colombia corresponde a partir de las 19:00 del
día anterior; la ventana configurada termina 90 minutos después del cierre.

1. V4 captura titulares y fija una señal textual posterior al cierre.
2. V6 usa exclusivamente la última vela diaria completa.
3. El precio observado durante la consulta se conserva como entrada simulada.
4. La posición se liquida en la apertura UTC del día siguiente.

Una ejecución tardía se registra como `abstain`. No se reutiliza una predicción
diaria cuando la mayor parte de su horizonte ya transcurrió.

## Ejecución manual recomendada

Entre las 19:05 y 20:15, hora de Colombia:

1. Abra `INICIAR_NOSTRADAMUS.bat` con doble clic.
2. Seleccione `1. Ejecutar ciclo diario completo (V4 + V6)`.
3. Confirme el consumo de Groq y espere el resumen final.

El mismo menú puede abrirse desde PowerShell:

```powershell
python .\nostradamus_cli.py
```

La opción 1 ejecuta primero V4 y después V6. Consume hasta diez solicitudes de
Groq por corrida con la configuración actual. No instala tareas de Windows.

Como alternativa no interactiva permanece disponible:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_daily_paper_trading.ps1
```

También puede ejecutarse únicamente V6 si ya existe una señal V4 reciente:

```powershell
python .\phase6_paper_trade.py
```

## Árbitro

- Probabilidad inferior al umbral: `no_trade`.
- Sentimiento negativo: `no_trade`.
- Sentimiento neutral: Kelly fraccional multiplicado por 0.5.
- Sentimiento positivo: Kelly fraccional sin penalización textual.
- Datos faltantes, señal vieja, ejecución tardía, deriva severa, drawdown o
  degradación de calibración: `abstain`.

La exposición máxima es 25% por activo y 50% total. La ausencia de sentimiento
nunca se interpreta como neutral.

## Auditoría y resultados

`output/v6/decisions.jsonl` y `output/v6/settlements.jsonl` son diarios
append-only con una cadena SHA-256. Alterar o reordenar una línea rompe la
validación antes de añadir nuevos registros.

Otros artefactos:

- `output/v6/PAPER_TRADING_STATUS.md`: estado legible más reciente;
- `output/v6/status.json`: estado estructurado;
- `output/v6/portfolio_equity.csv`: capital reconstruido desde liquidaciones;
- `output/v6/runs/...`: decisión y manifiesto inmutable de cada corrida;
- `output/v6/logs`: salida de las ejecuciones manuales.

El precio de entrada es una referencia capturada desde Yahoo Finance, no una
ejecución de mercado. Comisión y slippage configurados se descuentan en la
liquidación simulada.

## Criterios de reentrenamiento

El sistema se detiene ante una característica con z-score absoluto de 8 o más,
drawdown simulado de 20%, o Brier reciente superior a 0.35 después de al menos
20 operaciones liquidadas. Un z-score de 4 o más queda como advertencia. Estos
eventos no entrenan automáticamente el modelo: primero requieren revisión y un
nuevo experimento versionado.
