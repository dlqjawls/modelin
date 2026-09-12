"""Comparable, cost-aware strategy evaluation on one price sample."""
from dataclasses import dataclass

import pandas as pd

from core.backtester import BacktestConfig, BacktestEngine


@dataclass(frozen=True)
class StrategyScore:
    strategy: dict
    total_return: float
    cagr: float
    sharpe_ratio: float
    max_drawdown: float
    total_trades: int
    score: float


def compare_strategies(opens: pd.DataFrame, closes: pd.DataFrame, *, symbols: list[str], market="krx",
                       strategies: list[dict] | None = None, initial_capital=10_000_000) -> list[StrategyScore]:
    """Run candidates against identical data and rank risk-adjusted results.

    The score penalizes drawdown and never treats the best historical return
    alone as the winner.
    """
    candidates = strategies or [
        {"type": "equal_weight"}, {"type": "momentum", "lookback": 20},
        {"type": "moving_average", "short_window": 20, "long_window": 60},
        {"type": "rsi", "period": 14},
    ]
    engine = object.__new__(BacktestEngine)
    results = []
    for strategy in candidates:
        config = BacktestConfig(symbols=symbols, market=market, strategy=strategy,
                                initial_capital=initial_capital)
        result = engine._event_backtest(opens, closes, engine._generate_signals(closes, strategy), config)
        score = result.cagr + (0.05 * result.sharpe_ratio) - (0.5 * abs(result.max_drawdown))
        results.append(StrategyScore(strategy, result.total_return, result.cagr,
                                     result.sharpe_ratio, result.max_drawdown,
                                     result.total_trades, score))
    return sorted(results, key=lambda item: item.score, reverse=True)
