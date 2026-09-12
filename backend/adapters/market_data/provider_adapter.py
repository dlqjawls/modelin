"""Adapter from existing market providers to the normalized data contract."""
from datetime import datetime, timedelta, timezone

import pandas as pd

from data.contracts import DataSnapshot
from data.normalizer import normalize_daily_frame


class ProviderMarketDataAdapter:
    def __init__(self, provider, source: str, instrument_ids: dict[str, str] | None = None):
        self.provider = provider
        self.source = source
        self.instrument_ids = instrument_ids or {}

    async def snapshot(self, symbols: list[str], timeframe: str, as_of: datetime) -> DataSnapshot:
        if timeframe != "1d":
            raise ValueError("현재 표준 provider adapter는 1d만 지원합니다.")
        frames = {}
        start = (as_of - timedelta(days=400)).date().isoformat()
        end = as_of.date().isoformat()
        for symbol in dict.fromkeys(symbols):
            frame = await self.provider.get_ohlcv(symbol, start, end, "1d")
            if not frame.empty:
                frames[symbol] = frame
        if not frames:
            return DataSnapshot(f"{self.source}-{as_of.isoformat()}", as_of, ())
        bars = []
        for symbol, frame in frames.items():
            snapshot = normalize_daily_frame(frame, instrument_id=self.instrument_ids.get(symbol, symbol),
                                             source=self.source, as_of=as_of)
            bars.extend(snapshot.bars)
        return DataSnapshot(f"{self.source}-{as_of.isoformat()}", as_of, tuple(bars), {self.source: "provider-v1"})

    @staticmethod
    def close_frame(snapshot: DataSnapshot) -> pd.DataFrame:
        rows = [{"symbol": bar.instrument_id, "date": bar.end, "close": float(bar.close)}
                for bar in snapshot.usable_bars()]
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).pivot(index="date", columns="symbol", values="close").sort_index()
