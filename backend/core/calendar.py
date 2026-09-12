"""Conservative trading-session calendar used by the paper scheduler."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class Session:
    market: str
    start: datetime
    end: datetime


class TradingCalendar:
    def session_for(self, market: str, at: datetime) -> Session | None:
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        if market == "crypto":
            start = at.replace(hour=0, minute=0, second=0, microsecond=0)
            return Session(market, start, start + timedelta(days=1))
        # This is a weekday baseline. Venue holidays must be supplied by a
        # market-specific calendar before live scheduling is enabled.
        if at.weekday() >= 5:
            return None
        if market == "krx":
            start = at.replace(hour=0, minute=0, second=0, microsecond=0)
            return Session(market, start, start + timedelta(days=1))
        if market == "us":
            start = at.replace(hour=0, minute=0, second=0, microsecond=0)
            return Session(market, start, start + timedelta(days=1))
        raise ValueError(f"지원하지 않는 시장: {market}")

    def is_trading_day(self, market: str, at: datetime) -> bool:
        return self.session_for(market, at) is not None
