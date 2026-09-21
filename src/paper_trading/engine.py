"""Reglas puras de inferencia, riesgo, deriva y liquidación simulada."""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, log
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from src.config import PaperTradingConfig


EPSILON = 1e-6


@dataclass(frozen=True)
class DecisionOutcome:
    action: str
    exposure: float
    reason: str
    raw_kelly: float
    sentiment_multiplier: float


def calibrate_probability(raw_probability: float, calibration: Mapping[str, Any]) -> float:
    """Aplica exactamente el calibrador persistido por V3."""
    raw = float(np.clip(raw_probability, EPSILON, 1.0 - EPSILON))
    method = calibration.get("method")
    if method == "identity":
        return raw
    if method != "sigmoid":
        raise ValueError(f"Método de calibración no soportado: {method!r}")
    coefficient = float(calibration["coefficient"])
    intercept = float(calibration["intercept"])
    transformed = coefficient * log(raw / (1.0 - raw)) + intercept
    return float(1.0 / (1.0 + exp(-transformed)))


def assess_feature_drift(
    live_features: pd.Series,
    training_features: pd.DataFrame,
    *,
    warning_zscore: float,
    stop_zscore: float,
) -> dict[str, Any]:
    """Compara el punto vivo con media/desviación de entrenamiento."""
    missing = [column for column in live_features.index if column not in training_features]
    if missing:
        raise ValueError("La línea base no contiene: " + ", ".join(missing))
    details: list[dict[str, Any]] = []
    for feature in live_features.index:
        baseline = training_features[feature].astype(float).dropna()
        mean = float(baseline.mean())
        std = float(baseline.std(ddof=0))
        value = float(live_features[feature])
        zscore = 0.0 if std <= EPSILON else (value - mean) / std
        details.append(
            {
                "feature": feature,
                "value": value,
                "training_mean": mean,
                "training_std": std,
                "zscore": float(zscore),
                "absolute_zscore": float(abs(zscore)),
            }
        )
    maximum = max((item["absolute_zscore"] for item in details), default=0.0)
    if maximum >= stop_zscore:
        status = "blocked"
    elif maximum >= warning_zscore:
        status = "warning"
    else:
        status = "ok"
    flagged = [item for item in details if item["absolute_zscore"] >= warning_zscore]
    return {
        "status": status,
        "max_absolute_zscore": float(maximum),
        "warning_threshold": float(warning_zscore),
        "stop_threshold": float(stop_zscore),
        "flagged_features": flagged,
    }


def decide_position(
    probability: float,
    *,
    sentiment: int | None,
    blockers: Sequence[str],
    current_total_exposure: float,
    config: PaperTradingConfig,
) -> DecisionOutcome:
    """Árbitro determinista M3; nunca convierte ausencia en neutral."""
    if blockers:
        return DecisionOutcome(
            action="abstain",
            exposure=0.0,
            reason="; ".join(blockers),
            raw_kelly=0.0,
            sentiment_multiplier=0.0,
        )
    probability = float(probability)
    if probability < config.probability_threshold:
        return DecisionOutcome(
            action="no_trade",
            exposure=0.0,
            reason="La probabilidad calibrada no alcanza el umbral.",
            raw_kelly=0.0,
            sentiment_multiplier=0.0,
        )
    if sentiment not in {-1, 0, 1}:
        return DecisionOutcome(
            action="abstain",
            exposure=0.0,
            reason="No existe una señal textual válida.",
            raw_kelly=0.0,
            sentiment_multiplier=0.0,
        )
    multiplier = {-1: 0.0, 0: 0.5, 1: 1.0}[int(sentiment)]
    raw_kelly = max(0.0, 2.0 * probability - 1.0)
    exposure = min(
        raw_kelly * config.fractional_kelly,
        config.max_asset_exposure,
        max(0.0, config.max_total_exposure - current_total_exposure),
    ) * multiplier
    if sentiment == -1:
        reason = "El sentimiento negativo bloquea la operación."
    elif exposure <= EPSILON:
        reason = "Kelly o el límite total no permiten una exposición positiva."
    else:
        reason = "XGBoost, sentimiento y límites de riesgo permiten la simulación."
    return DecisionOutcome(
        action="operate" if exposure > EPSILON else "no_trade",
        exposure=float(exposure),
        reason=reason,
        raw_kelly=float(raw_kelly),
        sentiment_multiplier=float(multiplier),
    )


def settle_decision(
    decision: Mapping[str, Any],
    *,
    exit_price: float,
    settled_at: str,
    one_way_cost_rate: float,
) -> dict[str, Any]:
    """Liquida una operación de un periodo usando el precio simulado observado."""
    if decision.get("action") != "operate":
        raise ValueError("Solo se liquidan decisiones con action='operate'.")
    entry_price = float(decision["entry_price"])
    exposure = float(decision["exposure"])
    if entry_price <= 0.0 or exit_price <= 0.0:
        raise ValueError("Los precios de entrada y salida deben ser positivos.")
    asset_return = float(exit_price / entry_price - 1.0)
    cost = float(exposure * 2.0 * one_way_cost_rate)
    contribution = float(exposure * asset_return - cost)
    actual_direction = int(asset_return > 0.0)
    probability = float(decision["probability_calibrated"])
    return {
        "event": "settlement",
        "trade_id": decision["decision_id"],
        "asset": decision["asset"],
        "decision_at": decision["decision_at"],
        "settled_at": settled_at,
        "planned_exit_date": decision["planned_exit_date"],
        "entry_price": entry_price,
        "exit_price": float(exit_price),
        "exposure": exposure,
        "asset_return": asset_return,
        "gross_return_contribution": float(exposure * asset_return),
        "transaction_cost": cost,
        "net_return_contribution": contribution,
        "probability_calibrated": probability,
        "predicted_direction": int(probability >= 0.5),
        "actual_direction": actual_direction,
        "brier": float((probability - actual_direction) ** 2),
    }


def summarize_portfolio(
    settlements: Sequence[Mapping[str, Any]],
    *,
    initial_capital: float,
    calibration_window: int,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Reconstruye capital y calibración exclusivamente desde eventos liquidados."""
    if not settlements:
        empty = pd.DataFrame(columns=["date", "net_return", "equity", "drawdown"])
        return {
            "initial_capital": float(initial_capital),
            "current_capital": float(initial_capital),
            "total_return": 0.0,
            "max_drawdown": 0.0,
            "settled_trades": 0,
            "recent_brier": None,
        }, empty
    rows = pd.DataFrame([dict(item) for item in settlements])
    rows["date"] = pd.to_datetime(rows["settled_at"], utc=True).dt.normalize()
    daily = rows.groupby("date", as_index=False)["net_return_contribution"].sum()
    daily = daily.rename(columns={"net_return_contribution": "net_return"}).sort_values("date")
    daily["equity_factor"] = (1.0 + daily["net_return"]).cumprod()
    daily["equity"] = initial_capital * daily["equity_factor"]
    daily["drawdown"] = daily["equity"] / daily["equity"].cummax() - 1.0
    recent_brier = float(rows["brier"].tail(calibration_window).mean())
    summary = {
        "initial_capital": float(initial_capital),
        "current_capital": float(daily["equity"].iloc[-1]),
        "total_return": float(daily["equity_factor"].iloc[-1] - 1.0),
        "max_drawdown": float(daily["drawdown"].min()),
        "settled_trades": int(len(rows)),
        "recent_brier": recent_brier,
    }
    return summary, daily.drop(columns=["equity_factor"])
