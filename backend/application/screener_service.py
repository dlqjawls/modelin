"""Application service for factor-based screening."""
from core.screener import ScreenerCondition, ScreenerEngine


class ScreenerService:
    def __init__(self, market_data):
        self.engine = ScreenerEngine(providers={
            market.value: provider for market, provider in market_data.providers.items()
        })

    async def screen(self, *, market, conditions, sort_by, sort_desc, limit):
        parsed = [ScreenerCondition(
            factor=item["factor"], operator=item["operator"], value=item["value"],
        ) for item in conditions]
        return await self.engine.screen(
            market=market, conditions=parsed, sort_by=sort_by,
            sort_desc=sort_desc, limit=limit,
        )
