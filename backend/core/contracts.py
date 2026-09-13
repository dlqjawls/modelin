"""Domain contracts shared by market-data ports and infrastructure."""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

Timeframe = Literal["1m", "5m", "15m", "1h", "1d", "1w", "1M"]

class Market(str, Enum):
    """Supported market identifiers shared by strategies and providers."""
    KRX = "krx"
    US = "us"
    CRYPTO = "crypto"

@dataclass(frozen=True)
class Instrument:
    id: str
    symbol: str
    market: str
    venue: str
    currency: str
    asset_type: str = "spot"
    timezone: str = "UTC"

@dataclass(frozen=True)
class Bar:
    instrument_id: str
    timeframe: Timeframe
    start: datetime
    end: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    available_at: datetime
    is_final: bool = True
    source: str = ""

    def __post_init__(self):
        values = (self.open, self.high, self.low, self.close, self.volume)
        if any(not value.is_finite() for value in values):
            raise ValueError("OHLCV는 유한한 숫자여야 합니다.")
        if self.end <= self.start or self.open <= 0 or self.high <= 0 or self.low <= 0 or self.close <= 0:
            raise ValueError("봉 시간과 가격이 올바르지 않습니다.")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("OHLC 가격 관계가 올바르지 않습니다.")
        if self.volume < 0:
            raise ValueError("거래량은 음수일 수 없습니다.")
        if self.available_at < self.end:
            raise ValueError("봉 종료 전에는 확정 데이터가 공개될 수 없습니다.")

@dataclass(frozen=True)
class DataSnapshot:
    snapshot_id: str
    as_of: datetime
    bars: tuple[Bar, ...] = field(default_factory=tuple)
    source_versions: dict[str, str] = field(default_factory=dict)

    def usable_bars(self) -> tuple[Bar, ...]:
        return tuple(b for b in self.bars if b.is_final and b.available_at <= self.as_of and b.end <= self.as_of)
