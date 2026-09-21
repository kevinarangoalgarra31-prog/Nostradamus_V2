"""Simulación causal de B0, B1, M1, M2 y M3 con costos homogéneos."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any, Mapping

import numpy as np
import pandas as pd

from src.config import BacktestingConfig


@dataclass(frozen=True)
class BacktestResult:
    strategy: str
    frame: pd.DataFrame
    metrics: Mapping[str, float | int | None]


@dataclass(frozen=True)
class BacktestSuite:
    base_frame: pd.DataFrame
    results: Mapping[str, BacktestResult]
    hybrid_status: Mapping[str, Any]
    cost_sensitivity: pd.DataFrame
    threshold_sensitivity: pd.DataFrame
    window_metrics: pd.DataFrame
    regime_metrics: pd.DataFrame


def prepare_backtest_frame(
    market: pd.DataFrame,
    predictions: pd.DataFrame,
    sentiment: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Alinea decisiones OOS y retorno ejecutable de apertura t+1 a apertura t+2."""
    required_market = {"Open", "Close", "SMA_20", "RSI_14"}
    missing = required_market - set(market.columns)
    if missing:
        raise ValueError("Faltan columnas de mercado: " + ", ".join(sorted(missing)))
    enriched = market.copy().sort_index()
    enriched["entry_open"] = enriched["Open"].shift(-1)
    enriched["exit_open"] = enriched["Open"].shift(-2)
    enriched["execution_return"] = enriched["exit_open"] / enriched["entry_open"] - 1.0
    frame = predictions.join(enriched, how="inner")
    if sentiment is not None and not sentiment.empty:
        frame = frame.join(sentiment, how="left")
    else:
        frame["sentiment"] = np.nan
        frame["sentiment_status"] = None
        frame["sentiment_score"] = np.nan
        frame["sentiment_confidence"] = np.nan
        frame["sentiment_coverage"] = np.nan
        frame["sentiment_decision_at"] = None
        frame["sentiment_artifact"] = None
    frame = frame.dropna(subset=["execution_return", "probability_calibrated"])
    frame.index.name = "Date"
    if frame.empty:
        raise ValueError("No existen fechas comunes con retorno de ejecución disponible.")
    return frame.sort_index()


def _metrics(
    returns: pd.Series,
    position: pd.Series,
    turnover: pd.Series,
    costs: pd.Series,
    *,
    annualization_periods: int,
) -> dict[str, float | int | None]:
    equity = (1.0 + returns).cumprod()
    total_return = float(equity.iloc[-1] - 1.0)
    periods = len(returns)
    annualized_return = (
        float(equity.iloc[-1] ** (annualization_periods / periods) - 1.0)
        if equity.iloc[-1] > 0.0 and periods > 0
        else None
    )
    standard_deviation = float(returns.std(ddof=1)) if periods > 1 else 0.0
    volatility = standard_deviation * sqrt(annualization_periods)
    sharpe = (
        float(returns.mean() / standard_deviation * sqrt(annualization_periods))
        if standard_deviation > 0.0
        else None
    )
    downside = returns[returns < 0.0]
    downside_deviation = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
    sortino = (
        float(returns.mean() / downside_deviation * sqrt(annualization_periods))
        if downside_deviation > 0.0
        else None
    )
    drawdown = equity / equity.cummax() - 1.0
    gains = float(returns[returns > 0.0].sum())
    losses = float(-returns[returns < 0.0].sum())
    active = position > 0.0
    entries = (active & ~active.shift(1, fill_value=False)).sum()
    return {
        "observations": int(periods),
        "total_return": total_return,
        "annualized_return": annualized_return,
        "annualized_volatility": float(volatility),
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": float(drawdown.min()),
        "profit_factor": (gains / losses if losses > 0.0 else None),
        "exposure": float(position.abs().mean()),
        "entries": int(entries),
        "transactions": int((turnover > 1e-12).sum()),
        "turnover": float(turnover.sum()),
        "total_cost": float(costs.sum()),
        "win_rate_active": (
            float((returns[active] > 0.0).mean()) if active.any() else None
        ),
    }


def simulate_strategy(
    base: pd.DataFrame,
    position: pd.Series,
    *,
    strategy: str,
    one_way_cost_rate: float,
    annualization_periods: int,
) -> BacktestResult:
    position = position.reindex(base.index).fillna(0.0).astype(float).clip(0.0, 1.0)
    previous = position.shift(1, fill_value=0.0)
    turnover = (position - previous).abs()
    if len(turnover) and position.iloc[-1] > 0.0:
        turnover.iloc[-1] += position.iloc[-1]
    gross = position * base["execution_return"].astype(float)
    costs = turnover * one_way_cost_rate
    net = gross - costs
    frame = pd.DataFrame(
        {
            "position": position,
            "execution_return": base["execution_return"].astype(float),
            "gross_return": gross,
            "turnover": turnover,
            "transaction_cost": costs,
            "net_return": net,
            "equity": (1.0 + net).cumprod(),
        },
        index=base.index,
    )
    return BacktestResult(
        strategy=strategy,
        frame=frame,
        metrics=_metrics(
            net,
            position,
            turnover,
            costs,
            annualization_periods=annualization_periods,
        ),
    )


def _principal_positions(
    frame: pd.DataFrame, config: BacktestingConfig
) -> tuple[dict[str, pd.Series], dict[str, Any]]:
    probability = frame["probability_calibrated"].astype(float)
    m1 = (probability >= config.probability_threshold).astype(float)
    positions: dict[str, pd.Series] = {
        "B0_buy_and_hold": pd.Series(1.0, index=frame.index),
        "B1_technical": (
            (frame[config.technical_sma_column].astype(float) < frame["Close"].astype(float))
            & (frame[config.technical_rsi_column].astype(float) >= config.technical_rsi_threshold)
        ).astype(float),
        "M1_xgboost": m1,
    }
    valid_sentiment = frame["sentiment_status"].eq("ok") & frame["sentiment"].notna()
    valid_count = int(valid_sentiment.sum())
    coverage = valid_count / len(frame)
    eligible = (
        coverage >= config.minimum_sentiment_coverage
        and valid_count >= config.minimum_hybrid_rows
    )
    hybrid_status: dict[str, Any] = {
        "status": "evaluable" if eligible else "not_evaluable",
        "valid_rows": valid_count,
        "total_rows": len(frame),
        "coverage": coverage,
        "minimum_coverage": config.minimum_sentiment_coverage,
        "minimum_rows": config.minimum_hybrid_rows,
        "reason": None,
    }
    if not eligible:
        hybrid_status["reason"] = (
            "No existe suficiente historia de sentimiento real alineada con las "
            "predicciones OOS; M2 y M3 no se puntúan ni se comparan."
        )
        return positions, hybrid_status

    sentiment = frame["sentiment"].fillna(-1).astype(int)
    positions["M2_xgboost_sentiment"] = (
        m1 * valid_sentiment.astype(float) * sentiment.ge(0).astype(float)
    )
    raw_kelly = (2.0 * probability - 1.0).clip(lower=0.0)
    fractional = (raw_kelly * config.fractional_kelly).clip(upper=config.max_exposure)
    sentiment_multiplier = sentiment.map({1: 1.0, 0: 0.5, -1: 0.0}).fillna(0.0)
    positions["M3_risk_arbiter"] = (
        fractional * sentiment_multiplier * valid_sentiment.astype(float)
    )
    return positions, hybrid_status


def run_backtest_suite(
    frame: pd.DataFrame,
    config: BacktestingConfig,
    *,
    commission_bps: float,
    slippage_bps: float,
) -> BacktestSuite:
    """Ejecuta estrategias, ablaciones y sensibilidades sobre ventanas idénticas."""
    one_way_cost = (commission_bps + slippage_bps) / 10_000.0
    positions, hybrid_status = _principal_positions(frame, config)
    results = {
        name: simulate_strategy(
            frame,
            position,
            strategy=name,
            one_way_cost_rate=one_way_cost,
            annualization_periods=config.annualization_periods,
        )
        for name, position in positions.items()
    }

    cost_rows: list[dict[str, Any]] = []
    for multiplier in config.cost_multipliers:
        for name, position in positions.items():
            result = simulate_strategy(
                frame,
                position,
                strategy=name,
                one_way_cost_rate=one_way_cost * multiplier,
                annualization_periods=config.annualization_periods,
            )
            cost_rows.append(
                {"cost_multiplier": multiplier, "strategy": name, **result.metrics}
            )

    threshold_rows: list[dict[str, Any]] = []
    for threshold in config.threshold_grid:
        position = (frame["probability_calibrated"].astype(float) >= threshold).astype(float)
        result = simulate_strategy(
            frame,
            position,
            strategy="M1_xgboost",
            one_way_cost_rate=one_way_cost,
            annualization_periods=config.annualization_periods,
        )
        threshold_rows.append({"probability_threshold": threshold, **result.metrics})
    raw_result = simulate_strategy(
        frame,
        (frame["probability_raw"].astype(float) >= config.probability_threshold).astype(float),
        strategy="M1_raw_probability_ablation",
        one_way_cost_rate=one_way_cost,
        annualization_periods=config.annualization_periods,
    )
    threshold_rows.append(
        {
            "probability_threshold": config.probability_threshold,
            "ablation": "uncalibrated_probability",
            **raw_result.metrics,
        }
    )

    window_rows: list[dict[str, Any]] = []
    for fold in sorted(frame["fold"].dropna().unique()):
        fold_frame = frame.loc[frame["fold"] == fold]
        for name, position in positions.items():
            result = simulate_strategy(
                fold_frame,
                position.loc[fold_frame.index],
                strategy=name,
                one_way_cost_rate=one_way_cost,
                annualization_periods=config.annualization_periods,
            )
            window_rows.append({"fold": int(fold), "strategy": name, **result.metrics})

    regime_rows: list[dict[str, Any]] = []
    if config.regime_volatility_column in frame.columns:
        volatility = frame[config.regime_volatility_column].astype(float)
        boundary = float(volatility.median())
        regimes = {
            "low_volatility": volatility <= boundary,
            "high_volatility": volatility > boundary,
        }
        for regime, mask in regimes.items():
            for name, result in results.items():
                subset = result.frame.loc[mask]
                if subset.empty:
                    continue
                metrics = _metrics(
                    subset["net_return"],
                    subset["position"],
                    subset["turnover"],
                    subset["transaction_cost"],
                    annualization_periods=config.annualization_periods,
                )
                regime_rows.append(
                    {
                        "regime": regime,
                        "volatility_boundary": boundary,
                        "strategy": name,
                        **metrics,
                    }
                )

    return BacktestSuite(
        base_frame=frame,
        results=results,
        hybrid_status=hybrid_status,
        cost_sensitivity=pd.DataFrame(cost_rows),
        threshold_sensitivity=pd.DataFrame(threshold_rows),
        window_metrics=pd.DataFrame(window_rows),
        regime_metrics=pd.DataFrame(regime_rows),
    )
