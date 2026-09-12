"""Normalize provider DataFrames into point-in-time bar contracts."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pandas as pd

from data.contracts import Bar, DataSnapshot


def normalize_daily_frame(frame: pd.DataFrame, *, instrument_id: str, source: str,
                          as_of: datetime | None = None) -> DataSnapshot:
    """Convert a provider frame to final daily bars without inventing data."""
    if frame.empty:
        return DataSnapshot(str(uuid4()), as_of or datetime.now(timezone.utc), ())
    as_of = as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    bars = []
    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(frame.columns):
        raise ValueError(f"가격 데이터 컬럼이 부족합니다: {required - set(frame.columns)}")
    for stamp, row in frame.sort_index().iterrows():
        start = pd.Timestamp(stamp)
        if start.tzinfo is None:
            start = start.tz_localize("UTC")
        else:
            start = start.tz_convert("UTC")
        start_dt = start.to_pydatetime()
        end_dt = (start + pd.Timedelta(days=1)).to_pydatetime()
        available_at = max(end_dt, as_of)
        # A provider may return a current unfinished daily bar. It is omitted
        # unless its timestamp has actually ended by as_of.
        if end_dt > as_of:
            continue
        bars.append(Bar(instrument_id, "1d", start_dt, end_dt,
                        Decimal(str(row["open"])), Decimal(str(row["high"])),
                        Decimal(str(row["low"])), Decimal(str(row["close"])),
                        Decimal(str(row["volume"])), available_at, True, source))
    return DataSnapshot(str(uuid4()), as_of, tuple(bars), {source: "provider-normalized-v1"})
