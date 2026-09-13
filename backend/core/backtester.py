"""Event-aware long-only backtesting engine used by paper and research flows."""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from core.strategy_signals import SUPPORTED_STRATEGIES, generate_signals

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
        """Pure calculation engine; market data is supplied to ``run_frames``."""
        pass

    def run_frames(self, config: BacktestConfig, opens: pd.DataFrame, closes: pd.DataFrame) -> BacktestResult:
        self._validate_config(config)
        if opens.empty or closes.empty:
            raise ValueError("사용 가능한 가격 데이터가 없습니다.")
        return self._event_backtest(opens, closes, generate_signals(closes, config.strategy), config)

    @staticmethod
    def _generate_signals(prices, strategy):
        """Compatibility wrapper for callers migrating to strategy_signals."""
        return generate_signals(prices, strategy)

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
