"""Conservative trading-session calendar used by the paper scheduler."""
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

try:
    import exchange_calendars as xcals
except ImportError:  # optional until the deployment installs the calendar extra
    xcals = None


@dataclass(frozen=True)
class Session:
    market: str
    start: datetime
    end: datetime


class TradingCalendar:
    _EXCHANGE_NAMES = {"krx": "XKRX", "us": "XNYS"}

    @classmethod
    def _official_session_open(cls, market: str, at: datetime) -> bool | None:
        if xcals is None:
            return None
        try:
            calendar = xcals.get_calendar(cls._EXCHANGE_NAMES[market])
            return bool(calendar.is_open_on_minute(at, ignore_breaks=True))
        except Exception:
            return None

    def session_for(self, market: str, at: datetime) -> Session | None:
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        if market == "crypto":
            start = at.replace(hour=0, minute=0, second=0, microsecond=0)
            return Session(market, start, start + timedelta(days=1))
        zones = {"krx": "Asia/Seoul", "us": "America/New_York"}
        hours = {"krx": (time(9, 0), time(15, 30)), "us": (time(9, 30), time(16, 0))}
        if market not in zones:
            raise ValueError(f"지원하지 않는 시장: {market}")
        official_open = self._official_session_open(market, at)
        if official_open is False:
            return None
        local = at.astimezone(ZoneInfo(zones[market]))
        # This is a weekday baseline. Venue holidays must be supplied by a
        # market-specific holiday calendar before live scheduling is enabled.
        if local.weekday() >= 5:
            return None
        open_time, close_time = hours[market]
        if official_open is not True and not (open_time <= local.time() < close_time):
            return None
        start = datetime.combine(local.date(), open_time, tzinfo=local.tzinfo)
        end = datetime.combine(local.date(), close_time, tzinfo=local.tzinfo)
        return Session(market, start, end)

    def is_trading_day(self, market: str, at: datetime) -> bool:
        return self.session_for(market, at) is not None
