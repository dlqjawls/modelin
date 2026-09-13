"""Prepare a final, normalized market snapshot for one paper cycle."""
from dataclasses import dataclass

from core.calendar import TradingCalendar
from ports.market_data import PaperMarketDataAdapter


@dataclass(frozen=True)
class PaperMarketSnapshot:
    snapshot: object
    usable_bars: tuple
    close_prices: object
    latest_prices: dict
    schedule_key: str


class PaperMarketSnapshotService:
    def __init__(self, calendar=None):
        self.calendar = calendar or TradingCalendar()

    async def collect(self, deployment, *, data_adapter: PaperMarketDataAdapter, as_of):
        if not self.calendar.is_trading_day(deployment.get("market", "crypto"), as_of):
            return None, {"status": "skipped", "reason": "MARKET_CLOSED", "orders": []}
        symbols = deployment["strategy"].get("symbols", [])
        snapshot = await data_adapter.snapshot(
            symbols, deployment["strategy"].get("timeframe", "1d"), as_of,
        )
        usable = tuple(snapshot.usable_bars())
        if not usable:
            return None, {"status": "blocked", "reason": "NO_FINAL_MARKET_DATA", "orders": []}
        latest_end = max(item.end for item in usable)
        return PaperMarketSnapshot(
            snapshot=snapshot,
            usable_bars=usable,
            close_prices=data_adapter.close_frame(snapshot),
            latest_prices={bar.instrument_id: bar.close for bar in usable if bar.end == latest_end},
            schedule_key=latest_end.isoformat(),
        ), None
