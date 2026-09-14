"""Normalize provider DataFrames into point-in-time bar contracts."""
from datetime import datetime, timezone
from decimal import Decimal
import math
from uuid import uuid4

import pandas as pd

from core.contracts import Bar, DataSnapshot


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
    ordered = frame.sort_index()
    # itertuples(index=True) places the index at position zero.
    columns = [ordered.columns.get_loc(name) + 1 for name in ("open", "high", "low", "close", "volume")]
    # itertuples avoids the per-row Series allocation performed by iterrows;
    # this matters when a market-wide snapshot contains several hundred bars
    # for thousands of instruments.
    for row in ordered.itertuples(index=True, name=None):
        stamp = row[0]
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
        try:
            values = {
                "open": float(row[columns[0]]),
                "high": float(row[columns[1]]),
                "low": float(row[columns[2]]),
                "close": float(row[columns[3]]),
                "volume": float(row[columns[4]]),
            }
        except (IndexError, TypeError, ValueError):
            continue
        prices = (values["open"], values["high"], values["low"], values["close"])
        if (not all(math.isfinite(value) for value in values.values())
                or any(value <= 0 for value in prices)
                or values["volume"] < 0
                or values["high"] < max(values["open"], values["close"])
                or values["low"] > min(values["open"], values["close"])):
            continue
        bars.append(Bar(instrument_id, "1d", start_dt, end_dt,
                        Decimal(str(values["open"])), Decimal(str(values["high"])),
                        Decimal(str(values["low"])), Decimal(str(values["close"])),
                        Decimal(str(values["volume"])), available_at, True, source))
    return DataSnapshot(str(uuid4()), as_of, tuple(bars), {source: "provider-normalized-v1"})
