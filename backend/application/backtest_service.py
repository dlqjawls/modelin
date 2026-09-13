"""Application service for backtest execution and strategy comparison."""
import pandas as pd

from core.backtester import BacktestEngine, BacktestConfig
from core.strategy_comparator import compare_strategies


class BacktestService:
    def __init__(self, market_data, engine=None):
        self.market_data = market_data
        self.engine = engine or BacktestEngine()

    async def run(self, *, symbols, market, start_date, end_date, strategy,
                  initial_capital, commission_rate, slippage_rate, rebalance_period):
        config = BacktestConfig(
            symbols=symbols, market=market, start_date=start_date, end_date=end_date,
            strategy=strategy, initial_capital=initial_capital,
            commission_rate=commission_rate, slippage_rate=slippage_rate,
            rebalance_period=rebalance_period,
        )
        provider = self.market_data.provider(market)
        frames = await self._load_frames(provider, symbols, start_date, end_date)
        if not frames:
            raise ValueError("사용 가능한 가격 데이터가 없습니다.")
        opens = pd.DataFrame({s: f["open"] for s, f in frames.items()}).sort_index()
        closes = pd.DataFrame({s: f["close"] for s, f in frames.items()}).sort_index()
        return self.engine.run_frames(config, opens, closes)

    @staticmethod
    async def _load_frames(provider, symbols, start_date, end_date):
        frames = {}
        for symbol in dict.fromkeys(symbols):
            frame = await provider.get_ohlcv(symbol, start_date, end_date, "1d")
            if not frame.empty and {"open", "close"}.issubset(frame.columns):
                frame = frame[["open", "high", "low", "close", "volume"]].copy()
                frame.index = pd.to_datetime(frame.index, utc=True).tz_convert(None)
                frames[symbol] = frame.sort_index()
        return frames

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
