"""Motor causal y comparativo de backtesting de Nostradamus V5."""

from .artifacts import BacktestArtifacts, save_backtest_suite
from .engine import BacktestResult, BacktestSuite, prepare_backtest_frame, run_backtest_suite
from .loaders import InputBundle, load_sentiment_history, load_v5_inputs

__all__ = [
    "BacktestArtifacts",
    "BacktestResult",
    "BacktestSuite",
    "InputBundle",
    "load_sentiment_history",
    "load_v5_inputs",
    "prepare_backtest_frame",
    "run_backtest_suite",
    "save_backtest_suite",
]
