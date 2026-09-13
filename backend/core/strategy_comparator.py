"""Comparable strategy evaluation with an out-of-sample holdout."""
from dataclasses import dataclass

import pandas as pd

from core.backtester import BacktestConfig, BacktestEngine
from core.strategy_signals import generate_signals


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
    """Rank candidates on the final holdout portion of the supplied sample.

    Signals are calculated on the complete history so indicators have their
    required warm-up period, but performance is measured only after the 70/30
    split. This prevents auto-selection from choosing a strategy solely from
    the same observations it was evaluated on.
    """
    candidates = strategies or [
        {"type": "equal_weight"}, {"type": "momentum", "lookback": 20},
        {"type": "moving_average", "short_window": 20, "long_window": 60},
        {"type": "rsi", "period": 14},
    ]
    engine = object.__new__(BacktestEngine)
    if len(closes) < 10:
        raise ValueError("전략 비교에는 최소 10개의 가격 바가 필요합니다.")
    split = min(len(closes) - 1, max(1, int(len(closes) * 0.70)))
    results = []
    for strategy in candidates:
        config = BacktestConfig(symbols=symbols, market=market, strategy=strategy,
                                initial_capital=initial_capital)
        signals = generate_signals(closes, strategy)
        result = engine._event_backtest(opens.iloc[split:], closes.iloc[split:], signals.iloc[split:], config)
        score = result.cagr + (0.05 * result.sharpe_ratio) - (0.5 * abs(result.max_drawdown))
        results.append(StrategyScore(strategy, result.total_return, result.cagr,
                                     result.sharpe_ratio, result.max_drawdown,
                                     result.total_trades, score))
    return sorted(results, key=lambda item: item.score, reverse=True)
