"""
Nostradamus V2: Orquestador Principal.
Ejecuta el pipeline completo de los 3 pilares:
1. Cerebro Cuantitativo (Descarga de datos, indicadores y modelo XGBoost)
2. Cerebro Cualitativo (Radar RSS y análisis de sentimiento con LLM)
3. El Árbitro (Gestión de Riesgo Dinámica con Criterio de Kelly)
"""

import sys
import argparse

# Asegurar compatibilidad de caracteres y emojis en terminales de Windows
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from src.data_pipeline import descargar_datos, calcular_caracteristicas, obtener_titulares_rss
from src.models import XGBoostTrader
from src.llm_agent import SentimentAnalyzer
from src.risk_manager import ArbitroRiesgo


def ejecutar_pipeline(
    ticker: str = "BTC-USD",
    activo_noticias: str = "Bitcoin",
    fecha_inicio: str = "2022-01-01",
    max_noticias: int = 3,
    guardar_datos: bool = True
):
    print("=" * 60)
    print(f"🚀 INICIANDO SISTEMA HÍBRIDO NOSTRADAMUS V2")
    print(f"Activo: {ticker} | Fecha Inicio: {fecha_inicio}")
    print("=" * 60)

    # -------------------------------------------------------------
    # PILAR 1: CEREBRO CUANTITATIVO (Datos técnicos + XGBoost)
    # -------------------------------------------------------------
    print("\n--- [PILAR 1] PROCESAMIENTO CUANTITATIVO ---")
    df_raw = descargar_datos(
        ticker=ticker,
        fecha_inicio=fecha_inicio,
        guardar_csv=guardar_datos
    )

    nombre_features = f"{ticker.replace('-', '_')}_features.csv"
    df_features = calcular_caracteristicas(
        df=df_raw,
        sma_window=20,
        guardar_csv=guardar_datos,
        nombre_archivo=nombre_features
    )

    modelo = XGBoostTrader(n_estimators=100, learning_rate=0.1, random_state=42)
    X_train, X_test, y_train, y_test = modelo.preparar_datos(df_features, split_ratio=0.8)

    modelo.entrenar(X_train, y_train)
    evaluacion = modelo.evaluar(X_test, y_test)

    # Predecir la probabilidad matemática con la vela más reciente
    ultima_fila = X_test.iloc[[-1]]
    prob_exito = modelo.predecir_probabilidad(ultima_fila)
    print(f"\n📊 Probabilidad matemática de subida estimada para hoy: {prob_exito * 100:.2f}%")

    # -------------------------------------------------------------
    # PILAR 2: CEREBRO CUALITATIVO (Noticias RSS + Groq LLM)
    # -------------------------------------------------------------
    print("\n--- [PILAR 2] RADAR DE NOTICIAS Y ANÁLISIS CUALITATIVO ---")
    print(f"📡 Buscando titulares en vivo para '{activo_noticias}'...")
    noticias = obtener_titulares_rss(activo=activo_noticias, max_noticias=max_noticias)
    print(f"Se obtuvieron {len(noticias)} titulares recientes.")

    analyzer = SentimentAnalyzer()
    sentimiento_consenso = 0
    resumen_noticia = "Sin titulares disponibles"

    if analyzer.cliente is not None and noticias:
        noticias_analizadas = []
        for n in noticias:
            try:
                score = analyzer.analizar_titular(n["titulo"])
                n["sentimiento"] = score
                noticias_analizadas.append(n)
                print(f"  • [{score:+d}] {n['titulo']} ({n['fuente']})")
            except Exception as e:
                print(f"  • [Error] {n['titulo']}: {e}")

        if noticias_analizadas:
            sentimiento_consenso = analyzer.obtener_consenso_sentimiento(noticias_analizadas)
            resumen_noticia = analyzer.generar_resumen_contexto(noticias_analizadas)
    else:
        print("⚠️ Modo simulado / sin API key de Groq para Pilar 2.")
        if noticias:
            resumen_noticia = noticias[0]["titulo"]
            print(f"Titular principal: {resumen_noticia}")
        sentimiento_consenso = 0  # Neutral por defecto

    # -------------------------------------------------------------
    # PILAR 3: EL ÁRBITRO DE RIESGO
    # -------------------------------------------------------------
    print("\n--- [PILAR 3] EL ÁRBITRO Y GESTIÓN DE RIESGO ---")
    arbitro = ArbitroRiesgo(ratio_ganancia_perdida=1.0, verbose=True)
    decision = arbitro.evaluar(
        probabilidad_xgb=prob_exito,
        sentimiento_llm=sentimiento_consenso,
        contexto_noticia=resumen_noticia
    )

    return decision


def main():
    parser = argparse.ArgumentParser(description="Nostradamus V2 - Trading Híbrido IA")
    parser.add_argument("--ticker", type=str, default="BTC-USD", help="Ticker del activo (ej. BTC-USD)")
    parser.add_argument("--activo", type=str, default="Bitcoin", help="Nombre del activo para noticias RSS")
    parser.add_argument("--inicio", type=str, default="2022-01-01", help="Fecha inicial YYYY-MM-DD")
    parser.add_argument("--max-noticias", type=int, default=3, help="Cantidad de noticias a evaluar")

    args = parser.parse_args()
    ejecutar_pipeline(
        ticker=args.ticker,
        activo_noticias=args.activo,
        fecha_inicio=args.inicio,
        max_noticias=args.max_noticias
    )


if __name__ == "__main__":
    main()
