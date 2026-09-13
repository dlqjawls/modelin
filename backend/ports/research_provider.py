"""Abstract contract implemented by market research providers."""
from abc import ABC, abstractmethod

import pandas as pd

from core.contracts import AssetInfo, FundamentalData, Market


class BaseProvider(ABC):
    @property
    @abstractmethod
    def market(self) -> Market: ...

    @abstractmethod
    async def search(self, query: str) -> list[AssetInfo]: ...

    @abstractmethod
    async def get_ohlcv(self, symbol: str, start_date: str, end_date: str, interval: str = "1d") -> pd.DataFrame: ...

    @abstractmethod
    async def get_info(self, symbol: str) -> AssetInfo: ...

    @abstractmethod
    async def get_fundamental(self, symbol: str) -> FundamentalData: ...

    @abstractmethod
    async def get_tickers(self) -> list[AssetInfo]: ...
