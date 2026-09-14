"""Read-only smoke check for configured market and macro integrations.

This script only requests account snapshots and public macro observations. It
never creates, edits, cancels, or liquidates an order.
"""
import asyncio
import json
import os
import sys

import httpx

from adapters.brokers.kis import KISBrokerAdapter, KISConfig
from adapters.market_data.fred_macro import FredMacroContext
from config import settings


def _kis_config(market: str) -> KISConfig:
    return KISConfig(
        app_key=settings.KIS_APP_KEY,
        app_secret=settings.KIS_APP_SECRET,
        account_no=settings.KIS_US_ACCOUNT_NO if market == "us" else settings.KIS_KRX_ACCOUNT_NO,
        environment=settings.KIS_ENVIRONMENT,
        market=market,
    )


async def _check_kis(market: str) -> dict:
    account_no = settings.KIS_US_ACCOUNT_NO if market == "us" else settings.KIS_KRX_ACCOUNT_NO
    if not all((settings.KIS_APP_KEY, settings.KIS_APP_SECRET, account_no)):
        return {"status": "missing_credentials"}
    try:
        snapshot = await KISBrokerAdapter(_kis_config(market)).account_snapshot()
        return {"status": "ok", "source": snapshot.get("source"), "cash_present": bool(snapshot.get("cash_present"))}
    except httpx.HTTPStatusError as exc:
        detail = ""
        try:
            body = exc.response.json()
            detail = body.get("msg1") or body.get("message") or body.get("error_description") or ""
        except ValueError:
            try:
                body = json.loads(exc.response.content.decode("cp949"))
                detail = body.get("msg1") or body.get("message") or body.get("error_description") or ""
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
        return {"status": "error", "error": type(exc).__name__, "http_status": exc.response.status_code,
                "provider_message": str(detail)[:200]}
    except Exception as exc:  # noqa: BLE001 - report provider failure without secrets
        return {"status": "error", "error": type(exc).__name__, "provider_message": str(exc)[:200]}


async def _check_quote(market: str) -> dict:
    account_no = settings.KIS_US_ACCOUNT_NO if market == "us" else settings.KIS_KRX_ACCOUNT_NO
    if not all((settings.KIS_APP_KEY, settings.KIS_APP_SECRET, account_no)):
        return {"status": "missing_credentials"}
    symbol = os.getenv("KIS_TEST_SYMBOL_KRX" if market == "krx" else "KIS_TEST_SYMBOL_US",
                       "005930" if market == "krx" else "AAPL")
    try:
        quote = await KISBrokerAdapter(_kis_config(market)).quote(symbol)
        return {"status": "ok" if quote.get("price") not in (None, "") else "error",
                "source": quote.get("source"), "symbol": quote.get("symbol"),
                "price_present": quote.get("price") not in (None, "")}
    except httpx.HTTPStatusError as exc:
        return {"status": "error", "error": type(exc).__name__, "http_status": exc.response.status_code}
    except Exception as exc:  # noqa: BLE001 - report provider failure without secrets
        return {"status": "error", "error": type(exc).__name__, "provider_message": str(exc)[:200]}


async def main() -> int:
    # KIS paper REST APIs enforce a per-app request interval. Keep the
    # read-only smoke check from turning a healthy integration into a false
    # failure by spacing sequential calls.
    await asyncio.sleep(1.1)
    result = {"kis_krx": await _check_kis("krx")}
    await asyncio.sleep(1.1)
    result["kis_us"] = await _check_kis("us")
    await asyncio.sleep(1.1)
    result["kis_quote_krx"] = await _check_quote("krx")
    # US quote verification is opt-in because KIS overseas quotes are
    # session-dependent and may be unavailable while the US market is closed.
    if os.getenv("KIS_VERIFY_US_QUOTE", "false").lower() == "true":
        await asyncio.sleep(1.1)
        result["kis_quote_us"] = await _check_quote("us")
    else:
        result["kis_quote_us"] = {"status": "skipped", "reason": "US_MARKET_SESSION_OR_OPT_IN_REQUIRED"}
    result["fred"] = {}
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
    required = ("kis_krx", "kis_us", "kis_quote_krx", "fred")
    return 0 if all(result[name].get("status") == "ok" for name in required) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
