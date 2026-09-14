"""Explicitly-confirmed KIS US paper order/cancel smoke test.

This tool is separate from the domestic KRX smoke test and is disabled unless
the operator explicitly enables ``us`` in ``PAPER_ALLOWED_MARKETS``.
"""
import argparse
import asyncio
import json
from decimal import Decimal
from uuid import uuid4

from adapters.brokers.kis import KISBrokerAdapter, KISConfig
from config import settings
from ports.broker import OrderRequest


async def main(symbol: str, exchange: str, quantity: str, price: str, confirm: str) -> None:
    if confirm != "I_CONFIRM_KIS_US_PAPER_ORDER":
        raise SystemExit("주문을 실행하려면 --confirm I_CONFIRM_KIS_US_PAPER_ORDER가 필요합니다.")
    if settings.KIS_ENVIRONMENT != "paper":
        raise SystemExit("KIS_ENVIRONMENT는 paper여야 합니다.")
    if "us" not in settings.PAPER_ALLOWED_MARKETS:
        raise SystemExit("us paper 주문은 backend/.env의 PAPER_ALLOWED_MARKETS에 us가 필요합니다.")
    if not settings.KIS_US_ACCOUNT_NO:
        raise SystemExit("KIS_US_ACCOUNT_NO가 필요합니다.")
    adapter = KISBrokerAdapter(KISConfig(
        app_key=settings.KIS_APP_KEY, app_secret=settings.KIS_APP_SECRET,
        account_no=settings.KIS_US_ACCOUNT_NO, environment="paper", market="us",
        exchange=exchange))
    request = OrderRequest(settings.KIS_US_ACCOUNT_NO, f"us-smoke-{uuid4()}",
                           symbol.upper(), "buy", Decimal(quantity), Decimal(price))
    submitted = await adapter.submit(request)
    broker_id = submitted.get("broker_order_id")
    if not broker_id:
        raise RuntimeError("미국 주문 접수 ID를 받지 못해 취소를 진행하지 않습니다.")
    cancel_error = None
    canceled = None
    try:
        canceled = await adapter.cancel(str(broker_id))
    except Exception as exc:
        cancel_error = str(exc)
    lookup = await adapter.lookup_order(broker_order_id=str(broker_id))
    snapshot = await adapter.account_snapshot()
    print(json.dumps({
        "submitted": {"status": submitted.get("status"), "broker_order_id": broker_id},
        "canceled": ({"status": canceled.get("status")} if canceled else
                     {"status": "rejected", "error": cancel_error}),
        "lookup": {"status": lookup.get("status"), "filled_quantity": lookup.get("filled_quantity")},
        "account": {"source": snapshot.get("source"), "positions": len(snapshot.get("positions", []))},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KIS US paper order/cancel smoke test")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--exchange", choices=("NASD", "NYSE", "AMEX"), required=True)
    parser.add_argument("--quantity", required=True)
    parser.add_argument("--price", required=True)
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    asyncio.run(main(args.symbol, args.exchange, args.quantity, args.price, args.confirm))
