"""Read-only preflight for the domestic KRX paper worker.

This command validates the deployment, KIS account access, KRX session state,
and the market universe. It never submits, cancels, or liquidates an order.
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config import settings
from core.calendar import TradingCalendar
from workers.run_paper import load_deployment
from workers.paper_runtime import build_paper_runtime


async def main(deployment_path: str) -> int:
    if settings.KIS_ENVIRONMENT != "paper":
        print(json.dumps({"status": "error", "reason": "KIS_ENVIRONMENT_NOT_PAPER"}))
        return 1
    if "krx" not in settings.PAPER_ALLOWED_MARKETS:
        print(json.dumps({"status": "error", "reason": "KRX_NOT_ALLOWED"}))
        return 1
    deployment = load_deployment(deployment_path)
    runtime = build_paper_runtime(deployment)
    now = datetime.now(timezone.utc)
    snapshot = await runtime.broker.account_snapshot()
    tickers = await runtime.data.provider.get_tickers()
    session_open = TradingCalendar().is_trading_day("krx", now)
    result = {
        "status": "ready" if snapshot and tickers else "error",
        "market": "krx",
        "environment": settings.KIS_ENVIRONMENT,
        "paper_allowed": True,
        "session_open": session_open,
        "account": {
            "cash_present": bool(snapshot.get("cash")),
            "positions": len(snapshot.get("positions", [])),
        },
        "universe": {"symbols": len({ticker.symbol for ticker in tickers if ticker.symbol})},
        "orders_submitted": 0,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ready" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read-only KRX paper worker preflight")
    parser.add_argument("deployment", nargs="?", default="docs/examples/kis-paper-runner.json")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.deployment)))
