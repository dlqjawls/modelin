"""Preview one domestic paper cycle without sending an order.

The script uses the real KRX data and KIS account/quote reads, then replaces
the broker submission port with a recorder. It is useful for validating the
strategy and order plan without changing the account.
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
from workers.run_paper import load_deployment, resolve_market_universe
from workers.paper_runtime import build_paper_runtime
from workers.paper_worker import execute_from_market_data


class PreviewBroker:
    def __init__(self, real_broker):
        self.real_broker = real_broker
        self.submissions = []

    async def account_snapshot(self):
        return await self.real_broker.account_snapshot()

    async def quote(self, symbol):
        return await self.real_broker.quote(symbol)

    async def submit(self, request):
        item = {
            "symbol": request.symbol,
            "side": request.side,
            "quantity": str(request.quantity),
            "limit_price": str(request.limit_price) if request.limit_price is not None else None,
        }
        self.submissions.append(item)
        return {"status": "preview", "client_order_id": request.client_order_id, **item}


async def main(deployment_path: str) -> int:
    if settings.KIS_ENVIRONMENT != "paper" or "krx" not in settings.PAPER_ALLOWED_MARKETS:
        print(json.dumps({"status": "error", "reason": "KRX_PAPER_NOT_ALLOWED"}))
        return 1
    deployment = load_deployment(deployment_path)
    runtime = build_paper_runtime(deployment)
    deployment = await resolve_market_universe(deployment, runtime.data.provider)
    broker = PreviewBroker(runtime.broker)
    result = await execute_from_market_data(
        deployment, data_adapter=runtime.data, broker=broker,
        as_of=datetime.now(timezone.utc), journal=None,
    )
    print(json.dumps({
        "status": result.get("status"),
        "reason_codes": result.get("reason_codes", []),
        "planned_orders": broker.submissions,
        "orders_submitted": 0,
    }, ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Preview domestic paper orders without submission")
    parser.add_argument("deployment", nargs="?", default="docs/examples/kis-paper-runner.json")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.deployment)))
