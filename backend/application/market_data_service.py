"""Application queries for normalized market data provider access."""
from core.contracts import Market
from ports.market_data import ResearchMarketDataProvider


class MarketDataService:
    def __init__(self, providers: dict[Market, ResearchMarketDataProvider]):
        self.providers = providers

    def provider(self, market: str):
        try:
            key = Market(market.lower())
        except ValueError as exc:
            raise ValueError(f"지원하지 않는 시장: {market}. 사용 가능: krx, us, crypto") from exc
        return self.providers[key]

    async def search(self, market: str, query: str):
        return await self.provider(market).search(query)

    async def ohlcv(self, market: str, symbol: str, start: str, end: str, interval: str):
        return await self.provider(market).get_ohlcv(symbol, start, end, interval)

    async def info(self, market: str, symbol: str):
        return await self.provider(market).get_info(symbol)

    async def fundamental(self, market: str, symbol: str):
        return await self.provider(market).get_fundamental(symbol)

    async def tickers(self, market: str):
        return await self.provider(market).get_tickers()
