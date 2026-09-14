"""Adapter from existing market providers to the normalized data contract."""
from datetime import datetime, timedelta, timezone
import asyncio
import logging

import pandas as pd

from core.contracts import DataSnapshot
from data.normalizer import normalize_daily_frame

logger = logging.getLogger(__name__)


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
        unique_symbols = list(dict.fromkeys(symbols))
        semaphore = asyncio.Semaphore(20)

        async def fetch(symbol):
            async with semaphore:
                try:
                    return symbol, await self.provider.get_ohlcv(symbol, start, end, "1d")
                except Exception:
                    return symbol, None

        # Keep the active request set bounded even when a full exchange
        # universe contains several thousand symbols.
        results = []
        for offset in range(0, len(unique_symbols), 250):
            batch = unique_symbols[offset:offset + 250]
            results.extend(await asyncio.gather(*(fetch(symbol) for symbol in batch)))
            logger.info(
                "market snapshot progress: source=%s completed=%d/%d",
                self.source, min(offset + len(batch), len(unique_symbols)), len(unique_symbols),
            )
        frames = {symbol: frame for symbol, frame in results if frame is not None and not frame.empty}
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

    @staticmethod
    def open_frame(snapshot: DataSnapshot) -> pd.DataFrame:
        rows = [{"symbol": bar.instrument_id, "date": bar.end, "open": float(bar.open)}
                for bar in snapshot.usable_bars()]
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).pivot(index="date", columns="symbol", values="open").sort_index()
