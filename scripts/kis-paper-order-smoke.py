"""Explicitly-confirmed KIS paper order/cancel smoke test.

This is the only repository script that can submit a broker order. It refuses
to run without the exact confirmation flag and always requests cancellation
immediately after acknowledgement. Use only with a KIS paper account.
"""
import argparse
import asyncio
import json
from decimal import Decimal
from uuid import uuid4

from adapters.brokers.kis import KISBrokerAdapter, KISConfig
from config import settings
from ports.broker import OrderRequest


async def main(market: str, symbol: str, quantity: str, confirm: str) -> None:
    if confirm != "I_CONFIRM_KIS_PAPER_ORDER":
        raise SystemExit("주문을 실행하려면 --confirm I_CONFIRM_KIS_PAPER_ORDER가 필요합니다.")
    if settings.KIS_ENVIRONMENT != "paper":
        raise SystemExit("KIS_ENVIRONMENT는 paper여야 합니다.")
    adapter = KISBrokerAdapter(KISConfig(
        app_key=settings.KIS_APP_KEY, app_secret=settings.KIS_APP_SECRET,
        account_no=settings.KIS_ACCOUNT_NO, environment="paper", market=market,
        exchange="NASD" if market == "us" else "NASD"))
    request = OrderRequest(settings.KIS_ACCOUNT_NO, f"smoke-{uuid4()}", symbol, "buy", Decimal(quantity))
    submitted = await adapter.submit(request)
    broker_id = submitted.get("broker_order_id")
    if not broker_id:
        raise RuntimeError("주문 접수 ID를 받지 못해 취소를 진행하지 않습니다.")
    canceled = await adapter.cancel(str(broker_id))
    lookup = await adapter.lookup_order(broker_order_id=str(broker_id))
    snapshot = await adapter.account_snapshot()
    print(json.dumps({"submitted": {"status": submitted.get("status"), "broker_order_id": broker_id},
                      "canceled": {"status": canceled.get("status")},
                      "lookup": {"status": lookup.get("status"), "filled_quantity": lookup.get("filled_quantity")},
                      "account": {"source": snapshot.get("source"), "positions": len(snapshot.get("positions", []))}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KIS paper order/cancel smoke test")
    parser.add_argument("--market", choices=("krx", "us"), required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--quantity", required=True)
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    asyncio.run(main(args.market, args.symbol, args.quantity, args.confirm))
