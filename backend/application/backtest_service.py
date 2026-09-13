"""Application service for backtest execution and strategy comparison."""
import pandas as pd

from core.backtester import BacktestEngine, BacktestConfig
from core.strategy_comparator import compare_strategies


class BacktestService:
    def __init__(self, market_data, engine=None):
        self.market_data = market_data
        self.engine = engine or BacktestEngine()

    async def run(self, config: BacktestConfig):
        return await self.engine.run(config)

    async def compare(self, *, market, symbols, start_date, end_date,
                      strategies=None, initial_capital=10_000_000):
        provider = self.market_data.provider(market)
        frames = {}
        for symbol in dict.fromkeys(symbols):
            frame = await provider.get_ohlcv(symbol, start_date, end_date, "1d")
            if not frame.empty and {"open", "close"}.issubset(frame.columns):
                frames[symbol] = frame[["open", "close"]].copy()
        if not frames:
            raise ValueError("전략 비교에 사용할 가격 데이터가 없습니다.")
        opens = pd.DataFrame({symbol: frame["open"] for symbol, frame in frames.items()}).sort_index().ffill()
        closes = pd.DataFrame({symbol: frame["close"] for symbol, frame in frames.items()}).sort_index().ffill()
        return compare_strategies(
            opens, closes, symbols=list(frames), market=market,
            strategies=strategies, initial_capital=initial_capital,
        )
