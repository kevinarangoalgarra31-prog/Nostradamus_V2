"""
Módulo del Cerebro Cuantitativo (XGBoost).
Maneja la división temporal de datos, entrenamiento del clasificador,
evaluación de métricas y estimación de probabilidades para el Árbitro.
"""

from typing import List, Tuple, Dict, Any, Optional
from pathlib import Path
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.metrics import accuracy_score, classification_report


class XGBoostTrader:
    """
    Clasificador cuantitativo basado en XGBoost para predicción direccional de precios.
    """

    DEFAULT_FEATURES = ["Close", "Volume", "SMA_20", "Retorno_Diario"]

    def __init__(
        self,
        n_estimators: int = 100,
        learning_rate: float = 0.1,
        max_depth: int = 3,
        random_state: int = 42,
        **kwargs
    ):
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.random_state = random_state
        self.model = xgb.XGBClassifier(
            n_estimators=n_estimators,
            learning_rate=learning_rate,
            max_depth=max_depth,
            random_state=random_state,
            eval_metric="logloss",
            **kwargs
        )
        self.feature_names: List[str] = self.DEFAULT_FEATURES
        self.is_fitted = False

    def preparar_datos(
        self,
        df: pd.DataFrame,
        features: Optional[List[str]] = None,
        target_col: str = "Target",
        split_ratio: float = 0.8
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
        """
        Divide cronológicamente el DataFrame en conjuntos de entrenamiento y prueba
        para evitar el sesgo de anticipación (lookahead bias).

        Args:
            df: DataFrame enriquecido con indicadores y columna Target.
            features: Lista de nombres de columnas a usar como features (opcional).
            target_col: Nombre de la columna objetivo.
            split_ratio: Proporción para el conjunto de entrenamiento (ej. 0.8 = 80%).

        Returns:
            Tuple con (X_train, X_test, y_train, y_test).
        """
        if features is not None:
            self.feature_names = features
        else:
            # Asegurar que las columnas existan en el DataFrame
            self.feature_names = [col for col in self.DEFAULT_FEATURES if col in df.columns]

        if not self.feature_names:
            raise ValueError("No se encontraron columnas de características válidas en el DataFrame.")

        if target_col not in df.columns:
            raise ValueError(f"Columna objetivo '{target_col}' no existe en el DataFrame.")

        X = df[self.feature_names]
        y = df[target_col]

        split_index = int(len(df) * split_ratio)
        X_train, X_test = X.iloc[:split_index], X.iloc[split_index:]
        y_train, y_test = y.iloc[:split_index], y.iloc[split_index:]

        print(f"División de datos: {len(X_train)} registros para entrenamiento | {len(X_test)} registros para test.")
        return X_train, X_test, y_train, y_test

    def entrenar(self, X_train: pd.DataFrame, y_train: pd.Series) -> None:
        """
        Entrena el modelo XGBoost con los datos proporcionados.
        """
        print("Entrenando Cerebro Cuantitativo (XGBoost)...")
        self.model.fit(X_train, y_train)
        self.is_fitted = True
        print("¡Entrenamiento completado exitosamente!")

    def evaluar(self, X_test: pd.DataFrame, y_test: pd.Series) -> Dict[str, Any]:
        """
        Evalúa el desempeño del modelo sobre datos no observados.

        Returns:
            Dict con 'accuracy', 'report_dict' y 'report_text'.
        """
        if not self.is_fitted:
            raise RuntimeError("El modelo debe ser entrenado antes de evaluar.")

        predicciones = self.model.predict(X_test)
        precision = accuracy_score(y_test, predicciones)
        reporte_str = classification_report(y_test, predicciones)
        reporte_dict = classification_report(y_test, predicciones, output_dict=True)

        print("-" * 50)
        print(f"Precisión del Modelo XGBoost: {precision * 100:.2f}%")
        print("-" * 50)
        print("Reporte detallado de clasificación:")
        print(reporte_str)

        return {
            "accuracy": float(precision),
            "report_dict": reporte_dict,
            "report_text": reporte_str
        }

    def predecir_probabilidad(self, X: pd.DataFrame | np.ndarray) -> float | np.ndarray:
        """
        Estima la probabilidad de que la variable objetivo sea 1 (subida de precio).
        Si se pasa una única fila, devuelve un único float entre 0.0 y 1.0.

        Args:
            X: Vector o matriz de características.

        Returns:
            float si se pasó una sola fila, o np.ndarray de probabilidades.
        """
        if not self.is_fitted:
            raise RuntimeError("El modelo debe ser entrenado antes de predecir.")

        # Si X es una sola fila (Series), convertir a DataFrame de 1 fila
        if isinstance(X, pd.Series):
            X = X.to_frame().T

        probs = self.model.predict_proba(X)[:, 1]

        if len(probs) == 1:
            return float(probs[0])
        return probs

    def guardar_modelo(self, ruta_archivo: str = "models/xgboost_trader.json") -> None:
        """Guarda el modelo entrenado en formato JSON nativo de XGBoost."""
        if not self.is_fitted:
            raise RuntimeError("No hay un modelo entrenado para guardar.")
        path = Path(ruta_archivo)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.model.save_model(str(path))
        print(f"Modelo guardado en: {path}")

    def cargar_modelo(self, ruta_archivo: str = "models/xgboost_trader.json") -> None:
        """Carga un modelo guardado en formato JSON nativo de XGBoost."""
        path = Path(ruta_archivo)
        if not path.exists():
            raise FileNotFoundError(f"No existe el archivo de modelo en: {path}")
        self.model.load_model(str(path))
        self.is_fitted = True
        print(f"Modelo cargado desde: {path}")

