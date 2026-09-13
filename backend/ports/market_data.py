"""Market-data port used by strategies and workers."""
from datetime import datetime
from typing import Protocol

from core.contracts import DataSnapshot


class MarketDataAdapter(Protocol):
    async def snapshot(self, symbols: list[str], timeframe: str, as_of: datetime) -> DataSnapshot: ...
