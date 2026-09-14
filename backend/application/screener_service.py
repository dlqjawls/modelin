"""Application service for factor-based screening."""
import asyncio

from core.screener import ScreenerCondition, ScreenerEngine


class ScreenerService:
    def __init__(self, market_data):
        self.market_data = market_data
        self.engine = ScreenerEngine()

    async def screen(self, *, market, conditions, sort_by, sort_desc, limit):
        parsed = [ScreenerCondition(
            factor=item["factor"], operator=item["operator"], value=item["value"],
        ) for item in conditions]
        provider = self.market_data.provider(market)
        tickers = await provider.get_tickers()
        semaphore = asyncio.Semaphore(15)

        async def collect(ticker):
            async with semaphore:
                try:
                    return ticker, await provider.get_fundamental(ticker.symbol)
                except Exception:
                    return None

        collected = await asyncio.gather(*(collect(ticker) for ticker in tickers))
        records = [record for record in collected if record is not None]
        return self.engine.screen_records(
            records, parsed, sort_by=sort_by, sort_desc=sort_desc, limit=limit,
        )
