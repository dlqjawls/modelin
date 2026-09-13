"""Event-aware long-only backtesting engine used by paper and research flows."""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

ANNUALIZATION = {"krx": 252, "us": 252, "crypto": 365}
SUPPORTED_STRATEGIES = {"equal_weight", "momentum", "moving_average", "rsi", "bollinger_bands"}


@dataclass
class BacktestConfig:
    symbols: list[str]
    market: str = "krx"
    start_date: str = ""
    end_date: str = ""
    strategy: dict = field(default_factory=dict)
    initial_capital: float = 10_000_000
    commission_rate: float = 0.00015
    slippage_rate: float = 0.001
    transaction_tax_rate: float = 0.0
    rebalance_period: str = "1M"
    execution: str = "next_open"
    benchmark_symbol: str | None = None
    quantity_step: float = 1.0


@dataclass
class BacktestResult:
    total_return: float = 0.0
    cagr: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0
    total_trades: int = 0
    equity_curve: list[dict] = field(default_factory=list)
    monthly_returns: list[dict] = field(default_factory=list)
    benchmark_comparison: dict | None = None


class BacktestEngine:
    def __init__(self):
        from data.providers.crypto_provider import CryptoProvider
        from data.providers.krx_provider import KRXProvider
        from data.providers.us_provider import USProvider
        self._providers = {"krx": KRXProvider(), "us": USProvider(), "crypto": CryptoProvider()}

    async def run(self, config: BacktestConfig) -> BacktestResult:
        self._validate_config(config)
        provider = self._providers[config.market]
        frames = {}
        for symbol in dict.fromkeys(config.symbols):
            frame = await provider.get_ohlcv(symbol, config.start_date, config.end_date, "1d")
            if not frame.empty and {"open", "close"}.issubset(frame.columns):
                frame = frame[["open", "high", "low", "close", "volume"]].copy()
                frame.index = pd.to_datetime(frame.index, utc=True).tz_convert(None)
                frames[symbol] = frame.sort_index()
        if not frames:
            raise ValueError("사용 가능한 가격 데이터가 없습니다.")
        opens = pd.DataFrame({s: f["open"] for s, f in frames.items()}).sort_index()
        closes = pd.DataFrame({s: f["close"] for s, f in frames.items()}).sort_index()
        return self._event_backtest(opens, closes, self._generate_signals(closes, config.strategy), config)

    @staticmethod
    def _validate_config(config):
        if config.market not in ANNUALIZATION:
            raise ValueError(f"지원하지 않는 시장: {config.market}")
        if not config.symbols or config.initial_capital <= 0:
            raise ValueError("종목과 초기자금은 양수여야 합니다.")
        if config.execution != "next_open":
            raise ValueError("현재 체결 방식은 next_open만 지원합니다.")
        from core.strategy_runtime import validate_strategy
        validate_strategy(config.strategy, config.symbols)
        if min(config.commission_rate, config.slippage_rate, config.transaction_tax_rate) < 0:
            raise ValueError("거래비용은 음수일 수 없습니다.")
        if config.quantity_step <= 0:
            raise ValueError("quantity_step은 양수여야 합니다.")

    def _generate_signals(self, prices, strategy):
        kind = strategy.get("type", "equal_weight")
        if kind == "equal_weight":
            return pd.DataFrame(1.0, index=prices.index, columns=prices.columns)
        if kind == "momentum":
            lookback = int(strategy.get("lookback", 20))
            if lookback < 1:
                raise ValueError("lookback은 1 이상이어야 합니다.")
            return (prices.pct_change(lookback) > 0).astype(float)
        if kind == "moving_average":
            short, long = int(strategy.get("short_window", 20)), int(strategy.get("long_window", 60))
            if short < 1 or short >= long:
                raise ValueError("short_window은 long_window보다 작아야 합니다.")
            result = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
            for symbol in prices:
                # The fast average becomes valid after its own window. Requiring
                # the slow window here makes the valid default (20/60) fail.
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
                rsi = self._calc_rsi(prices[symbol], period)
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

    @staticmethod
    def _calc_rsi(series, period=14):
        delta = series.diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        loss = -delta.clip(upper=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        return 100 - 100 / (1 + gain / loss.replace(0, np.nan))

    @staticmethod
    def _is_rebalance(date, index, period):
        if period in {"1d", "1D", "daily"}:
            return True
        if period in {"1w", "1W", "weekly"}:
            return date.weekday() == 4 or date == index[-1]
        return date == date + pd.offsets.MonthEnd(0) or date == index[-1]

    def _event_backtest(self, opens, closes, signals, config):
        index = closes.index.intersection(opens.index).sort_values()
        opens, closes, signals = opens.reindex(index), closes.reindex(index), signals.reindex(index)
        symbols = list(closes.columns)
        cash, holdings, pending = float(config.initial_capital), pd.Series(0.0, index=symbols), pd.Series(0.0, index=symbols)
        rows, returns, trades, previous_equity = [], [], 0, float(config.initial_capital)
        for i, date in enumerate(index):
            if i > 0:
                prices = opens.loc[date].reindex(symbols)
                equity = cash + float((holdings * prices.fillna(0)).sum())
                desired = pending * equity
                current = holdings * prices.fillna(0)
                for symbol in symbols:
                    price = prices[symbol]
                    if pd.isna(price) or price <= 0:
                        continue
                    delta = desired[symbol] - current[symbol]
                    if delta > 0:
                        qty = min(delta / price, max(cash, 0) / (price * (1 + config.commission_rate + config.slippage_rate)))
                        qty = np.floor(qty / config.quantity_step) * config.quantity_step
                        gross, fee = qty * price, qty * price * (config.commission_rate + config.slippage_rate)
                        holdings[symbol] += qty; cash -= gross + fee; trades += int(qty > 0)
                    elif delta < 0:
                        qty = min(holdings[symbol], -delta / price)
                        qty = np.floor(qty / config.quantity_step) * config.quantity_step
                        gross, fee = qty * price, qty * price * (config.commission_rate + config.slippage_rate + config.transaction_tax_rate)
                        holdings[symbol] -= qty; cash += gross - fee; trades += int(qty > 0)
            close = closes.loc[date].reindex(symbols)
            equity = cash + float((holdings * close.ffill().fillna(0)).sum())
            if previous_equity > 0 and i > 0:
                returns.append(equity / previous_equity - 1)
            previous_equity = equity
            rows.append({"date": date.isoformat(), "value": round(equity, 2)})
            raw = signals.loc[date].reindex(symbols).fillna(0).clip(0, 1)
            if i == 0 or self._is_rebalance(date, index, config.rebalance_period):
                pending = raw / raw.sum() if raw.sum() > 0 else raw
        equity = pd.Series([r["value"] for r in rows], index=index)
        ret = pd.Series(returns, index=index[1:]).replace([np.inf, -np.inf], np.nan).dropna()
        annual = ANNUALIZATION[config.market]
        years = max((index[-1] - index[0]).total_seconds() / 86400 / 365.25, 1 / 365.25)
        total = float(equity.iloc[-1] / config.initial_capital - 1)
        cagr = float((equity.iloc[-1] / config.initial_capital) ** (1 / years) - 1)
        std = ret.std(ddof=1)
        sharpe = float(ret.mean() / std * np.sqrt(annual)) if std and not np.isnan(std) else 0.0
        downside = np.minimum(ret, 0.0)
        ddv = float(np.sqrt(np.mean(np.square(downside)))) if len(ret) else 0.0
        sortino = float(ret.mean() / ddv * np.sqrt(annual)) if ddv else 0.0
        drawdown = equity / equity.cummax() - 1
        wins, losses = ret[ret > 0], ret[ret < 0]
        monthly = equity.resample("ME").last().pct_change(fill_method=None)
        month_end = equity.resample("ME").last()
        if len(month_end):
            monthly.iloc[0] = month_end.iloc[0] / config.initial_capital - 1
        return BacktestResult(total, cagr, sharpe, sortino, float(drawdown.min()),
            float(len(wins) / max(len(wins) + len(losses), 1)),
            float(wins.mean() / abs(losses.mean())) if len(wins) and len(losses) else 0.0, trades, rows,
            [{"date": str(d.date()), "return": round(float(v), 6)} for d, v in monthly.dropna().items()])
