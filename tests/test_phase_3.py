from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import ModelingConfig, WalkForwardConfig, load_modeling_config
from src.models.walk_forward import (
    SigmoidCalibrator,
    WalkForwardEvaluator,
    binary_metrics,
    save_walk_forward_result,
)


def quick_modeling_config() -> ModelingConfig:
    return ModelingConfig(
        version="3.0.0",
        decision_threshold=0.5,
        calibration_method="sigmoid",
        inner_splits=2,
        walk_forward=WalkForwardConfig(
            min_train_rows=100,
            calibration_rows=40,
            test_rows=40,
            step_rows=40,
            max_folds=2,
        ),
        parameter_grid={
            "n_estimators": (12,),
            "max_depth": (2,),
            "learning_rate": (0.1,),
            "subsample": (0.9,),
            "colsample_bytree": (0.9,),
            "min_child_weight": (1,),
            "reg_lambda": (1.0,),
        },
    )


def synthetic_model_data(rows: int = 240) -> tuple[pd.DataFrame, pd.Series]:
    index = pd.date_range("2022-01-01", periods=rows, freq="D")
    angle = np.arange(rows) / 5.0
    first = np.sin(angle)
    second = np.cos(angle / 2.0)
    third = np.sin(angle / 3.0) + np.cos(angle / 7.0)
    X = pd.DataFrame(
        {"signal": first, "context": second, "momentum": third}, index=index
    )
    y = pd.Series((first + 0.35 * second > 0.0).astype(int), index=index, name="Target")
    return X, y


class PhaseThreeTests(unittest.TestCase):
    def test_repository_modeling_config_is_valid(self) -> None:
        config = load_modeling_config("config/modeling_v3.yaml")
        self.assertEqual(config.version, "3.0.0")
        self.assertGreaterEqual(config.walk_forward.max_folds, 1)
        self.assertIn("max_depth", config.parameter_grid)

    def test_sigmoid_calibrator_returns_valid_probabilities(self) -> None:
        raw = np.array([0.05, 0.15, 0.25, 0.55, 0.70, 0.85, 0.95])
        truth = np.array([0, 0, 0, 0, 1, 1, 1])
        calibrator = SigmoidCalibrator().fit(raw, truth)
        calibrated = calibrator.transform(raw)
        self.assertTrue(np.all((calibrated > 0.0) & (calibrated < 1.0)))
        self.assertEqual(calibrator.to_dict()["method"], "sigmoid")

    def test_walk_forward_is_ordered_non_overlapping_and_persistable(self) -> None:
        X, y = synthetic_model_data()
        config = quick_modeling_config()
        result = WalkForwardEvaluator(config).evaluate(X, y)
        self.assertEqual(len(result.folds), 2)
        self.assertEqual(len(result.predictions), 80)
        self.assertFalse(result.predictions.index.duplicated().any())
        self.assertTrue(result.predictions.index.is_monotonic_increasing)
        for fold in result.folds:
            self.assertLess(fold["train_end"], fold["calibration_start"])
            self.assertLess(fold["calibration_end"], fold["test_start"])
        metrics = result.metrics["xgboost_calibrated"]
        self.assertIn("brier_score", metrics)
        self.assertEqual(metrics["samples"], 80.0)

        output = Path("tmp/test_v3")
        output.mkdir(parents=True, exist_ok=True)
        paths = save_walk_forward_result(
            result,
            output,
            ticker="TEST-USD",
            dataset_sha256="abc123",
            modeling_config=config,
        )
        self.assertTrue(all(path.is_file() for path in paths.values()))
        manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
        self.assertEqual(manifest["project_version"], "3.0.0")
        self.assertEqual(manifest["dataset_sha256"], "abc123")

    def test_binary_metrics_are_complete(self) -> None:
        metrics = binary_metrics([0, 0, 1, 1], [0.1, 0.4, 0.6, 0.9])
        self.assertEqual(metrics["accuracy"], 1.0)
        self.assertIn("ece", metrics)
        self.assertIn("log_loss", metrics)


if __name__ == "__main__":
    unittest.main()
