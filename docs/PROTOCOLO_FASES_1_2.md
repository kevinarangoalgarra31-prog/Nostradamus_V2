# Protocolo experimental — fases 1 y 2

## Propósito

Estas fases convierten la idea de investigación en un contrato ejecutable y producen un dataset auditable. No entrenan XGBoost ni evalúan rentabilidad; esas actividades pertenecen a las fases siguientes.

## Fase 1 — definición

- Universo inicial: `BTC-USD` y `ETH-USD`.
- Fuente: Yahoo Finance mediante `yfinance`.
- Frecuencia: diaria.
- Periodo congelado: desde 2020-01-01 hasta 2026-09-16. En `yfinance`, el límite configurado como 2026-09-17 es exclusivo.
- Variable objetivo: dirección del retorno del siguiente periodo, con umbral configurable.
- Costos declarados: 10 puntos básicos de comisión y 5 de slippage por operación simulada.
- Semilla: 42.
- La configuración canónica está en `config/experiment.yaml`.

Los activos, fechas, ventanas y costos no deben cambiarse después de observar el resultado final sin crear una nueva versión del experimento.

## Fase 2 — datos y características

El pipeline realiza los siguientes controles antes de aceptar un dataset:

1. Presencia de `Open`, `High`, `Low`, `Close` y `Volume`.
2. Fechas válidas, únicas y ordenadas.
3. Precios positivos y volumen no negativo.
4. Coherencia entre máximo, mínimo, apertura y cierre.
5. Umbral explícito de valores faltantes y mínimo de observaciones.
6. Manifiesto JSON con fuente, periodo observado, esquema, controles y SHA-256.

Las variables técnicas utilizan únicamente la información disponible hasta cada instante: retornos rezagados, SMA, distancia a SMA, EMA, MACD, RSI, volatilidad, momentum, rango y volumen relativo. `Target_Return` y `Target` se reservan para supervisión y nunca se incluyen como entradas del modelo.

## Ejecución

Con descarga remota:

```powershell
python prepare_data.py --config config/experiment.yaml
```

Con un CSV local y un solo activo:

```powershell
python prepare_data.py --config config/experiment.yaml --ticker BTC-USD --input-csv data/raw/archivo.csv
```

Validación sin escribir artefactos:

```powershell
python prepare_data.py --config config/experiment.yaml --ticker BTC-USD --input-csv data/raw/archivo.csv --no-save
```

## Criterios de aceptación

- La configuración se carga sin errores y contiene todas las decisiones previas al modelado.
- Un dataset inválido se rechaza con una causa explícita.
- Cada archivo aceptado tiene un manifiesto y una huella reproducible.
- La última observación sin futuro disponible no recibe una etiqueta artificial.
- Las pruebas automatizadas terminan satisfactoriamente.
