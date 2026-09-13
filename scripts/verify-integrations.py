"""Read-only smoke check for configured market and macro integrations.

This script only requests account snapshots and public macro observations. It
never creates, edits, cancels, or liquidates an order.
"""
import asyncio
import json
import sys

from adapters.brokers.kis import KISBrokerAdapter, KISConfig
from adapters.market_data.fred_macro import FredMacroContext
from config import settings


def _kis_config(market: str) -> KISConfig:
    return KISConfig(
        app_key=settings.KIS_APP_KEY,
        app_secret=settings.KIS_APP_SECRET,
        account_no=settings.KIS_ACCOUNT_NO,
        environment=settings.KIS_ENVIRONMENT,
        market=market,
    )


async def _check_kis(market: str) -> dict:
    if not all((settings.KIS_APP_KEY, settings.KIS_APP_SECRET, settings.KIS_ACCOUNT_NO)):
        return {"status": "missing_credentials"}
    try:
        snapshot = await KISBrokerAdapter(_kis_config(market)).account_snapshot()
        return {"status": "ok", "source": snapshot.get("source"), "cash_present": bool(snapshot.get("cash_present"))}
    except Exception as exc:  # noqa: BLE001 - report provider failure without secrets
        return {"status": "error", "error": type(exc).__name__}


async def main() -> int:
    result = {
        "kis_krx": await _check_kis("krx"),
        "kis_us": await _check_kis("us"),
        "fred": {},
    }
    try:
        result["fred"] = await FredMacroContext(settings.FRED_API_KEY).collect(days=7)
        result["fred"] = {
            "status": "ok" if result["fred"].get("macro_data_available") else "error",
            "source": result["fred"].get("macro_source"),
            "failures": result["fred"].get("macro_failures"),
        }
    except Exception as exc:  # noqa: BLE001 - report provider failure without secrets
        result["fred"] = {"status": "error", "error": type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if all(item.get("status") == "ok" for item in result.values()) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
