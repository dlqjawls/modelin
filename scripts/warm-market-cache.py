"""Warm the persistent OHLCV cache without submitting orders."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, "backend")
from config import settings
from data.persistent_ohlcv_cache import PersistentOHLCVCache
from data.providers.krx_provider import KRXProvider
from data.providers.us_provider import USProvider


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", choices=("krx", "us"), default="krx")
    parser.add_argument("--days", type=int, default=400)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    provider = KRXProvider() if args.market == "krx" else USProvider()
    cache = PersistentOHLCVCache(settings.MARKET_DATA_CACHE_DIR, args.market)
    end = date.today()
    start = end - timedelta(days=args.days)
    assets = await provider.get_tickers()
    semaphore = asyncio.Semaphore(max(1, args.concurrency))
    counts = {"cached": 0, "downloaded": 0, "failed": 0}

    async def warm(asset):
        async with semaphore:
            if cache.get(asset.symbol, start.isoformat(), end.isoformat(), "1d") is not None:
                counts["cached"] += 1
                return
            try:
                frame = await asyncio.wait_for(
                    provider.get_ohlcv(asset.symbol, start.isoformat(), end.isoformat(), "1d"),
                    timeout=max(1, args.timeout),
                )
                if frame is None or frame.empty:
                    counts["failed"] += 1
                    return
                cache.set(asset.symbol, start.isoformat(), end.isoformat(), "1d", frame)
                counts["downloaded"] += 1
            except Exception:
                counts["failed"] += 1
            total = sum(counts.values())
            if total % 50 == 0 or total == len(assets):
                print(f"progress={total}/{len(assets)} {counts}", flush=True)

    # Keep the number of outstanding provider calls bounded. A single stalled
    # third-party request must not hold thousands of tasks in memory.
    batch_size = max(1, args.concurrency * 5)
    for offset in range(0, len(assets), batch_size):
        await asyncio.gather(*(warm(asset) for asset in assets[offset:offset + batch_size]))
    print(f"complete market={args.market} total={len(assets)} {counts}")
    return 0 if counts["cached"] + counts["downloaded"] else 1


if __name__ == "__main__":
    # Third-party data libraries may leave executor threads alive after a
    # timed-out request. The cache writes are complete at this point, so do
    # not keep the operator's shell waiting for those abandoned requests.
    exit_code = asyncio.run(main())
    sys.stdout.flush()
    os._exit(exit_code)
