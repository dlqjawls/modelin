"""Pure signal generation shared by backtests and paper execution."""
import numpy as np
import pandas as pd

SUPPORTED_STRATEGIES = {"equal_weight", "momentum", "moving_average", "rsi", "bollinger_bands"}


def generate_signals(prices: pd.DataFrame, strategy: dict) -> pd.DataFrame:
    kind = strategy.get("type", "equal_weight")
    if kind == "equal_weight":
        return pd.DataFrame(1.0, index=prices.index, columns=prices.columns)
    if kind == "momentum":
        lookback = int(strategy.get("lookback", 20))
        if lookback < 1:
            raise ValueError("lookback은 1 이상이어야 합니다.")
        return (prices.pct_change(lookback, fill_method=None) > 0).astype(float)
    if kind == "moving_average":
        short, long = int(strategy.get("short_window", 20)), int(strategy.get("long_window", 60))
        if short < 1 or short >= long:
            raise ValueError("short_window은 long_window보다 작아야 합니다.")
        result = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        for symbol in prices:
            fast = prices[symbol].rolling(short, min_periods=short).mean()
            slow = prices[symbol].rolling(long, min_periods=long).mean()
            result[symbol] = (fast > slow).astype(float)
        return result
    if kind == "rsi":
        period = int(strategy.get("period", 14))
        oversold, overbought = float(strategy.get("oversold", 30)), float(strategy.get("overbought", 70))
        if period < 2 or not 0 < oversold < overbought < 100:
            raise ValueError("RSI 설정이 올바르지 않습니다.")
        result = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        for symbol in prices:
            rsi = calculate_rsi(prices[symbol], period)
            state = pd.Series(np.nan, index=prices.index)
            state[rsi < oversold], state[rsi > overbought] = 1.0, 0.0
            result[symbol] = state.ffill().fillna(0.0)
        return result
    window, num_std = int(strategy.get("window", 20)), float(strategy.get("num_std", 2))
    if window < 2 or num_std <= 0:
        raise ValueError("볼린저 설정이 올바르지 않습니다.")
    result = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    for symbol in prices:
        ma = prices[symbol].rolling(window, min_periods=window).mean()
        std = prices[symbol].rolling(window, min_periods=window).std()
        state = pd.Series(np.nan, index=prices.index)
        state[prices[symbol] < ma - num_std * std] = 1.0
        state[prices[symbol] > ma + num_std * std] = 0.0
        result[symbol] = state.ffill().fillna(0.0)
    return result


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = -delta.clip(upper=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))
