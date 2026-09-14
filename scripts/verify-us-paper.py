"""Read-only preflight for the separately configured KIS US paper runner."""
import asyncio
import collections
import json
from datetime import datetime, timezone

from adapters.brokers.kis import KISBrokerAdapter, KISConfig
from config import settings
from core.calendar import TradingCalendar
from data.providers.us_provider import USProvider


async def main():
    result = {
        "environment": settings.KIS_ENVIRONMENT,
        "paper_allowed": "us" in settings.PAPER_ALLOWED_MARKETS,
        "credentials": bool(settings.KIS_APP_KEY and settings.KIS_APP_SECRET and settings.KIS_US_ACCOUNT_NO),
        "session_open": TradingCalendar().is_trading_day("us", datetime.now(timezone.utc)),
    }
    if result["credentials"] and settings.KIS_ENVIRONMENT == "paper":
        adapter = KISBrokerAdapter(KISConfig(
            app_key=settings.KIS_APP_KEY, app_secret=settings.KIS_APP_SECRET,
            account_no=settings.KIS_US_ACCOUNT_NO, environment="paper", market="us",
            exchange="NASD"))
        snapshot = await adapter.account_snapshot()
        result["account"] = {"status": "ok", "cash_present": snapshot.get("cash_present", False),
                              "positions": len(snapshot.get("positions", []))}
    else:
        result["account"] = {"status": "skipped"}
    tickers = await USProvider().get_tickers()
    exchanges = collections.Counter(t.extra.get("exchange") for t in tickers)
    result["universe"] = {"symbols": len(tickers), "exchanges": dict(exchanges)}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
