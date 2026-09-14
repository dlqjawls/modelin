"""Run the KIS paper execution notice listener until Ctrl+C.

The listener is read-only: it subscribes to execution notices and does not
submit, cancel, or liquidate orders.
"""
import argparse
import asyncio
import json
import logging

from adapters.brokers.kis import KISBrokerAdapter, KISConfig
from adapters.brokers.kis_websocket import KISExecutionConsumer
from config import settings


async def main(symbols: list[str]) -> None:
    if not settings.KIS_APP_KEY or not settings.KIS_APP_SECRET or not settings.KIS_KRX_ACCOUNT_NO:
        raise SystemExit("국내 KIS paper 체결 리스너에 KIS_APP_KEY, KIS_APP_SECRET, KIS_KRX_ACCOUNT_NO가 필요합니다.")
    adapter = KISBrokerAdapter(KISConfig(
        app_key=settings.KIS_APP_KEY, app_secret=settings.KIS_APP_SECRET,
        account_no=settings.KIS_KRX_ACCOUNT_NO, environment="paper", market="krx"))
    stop_event = asyncio.Event()

    async def on_event(event: dict) -> None:
        print(json.dumps(event, ensure_ascii=False), flush=True)

    try:
        await KISExecutionConsumer(adapter).run(symbols, on_event, stop_event)
    except KeyboardInterrupt:
        stop_event.set()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="KIS paper execution notice listener")
    parser.add_argument("symbols", nargs="+", help="KRX numeric symbols, e.g. 005930")
    args = parser.parse_args()
    asyncio.run(main(args.symbols))
