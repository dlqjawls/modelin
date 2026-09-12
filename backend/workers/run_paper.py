"""Run one configured KRX paper deployment continuously.

This process is deliberately fail-closed: only KRX + KIS paper mode is
accepted, and an incomplete strategy configuration exits before any order.
"""
import argparse
import asyncio
import json
import logging
from datetime import datetime, timezone

from adapters.brokers.kis import KISBrokerAdapter, KISConfig
from adapters.market_data.provider_adapter import ProviderMarketDataAdapter
from config import settings
from data.providers.krx_provider import KRXProvider
from workers.paper_worker import execute_from_market_data
from core.strategy_runtime import validate_strategy

logger = logging.getLogger("modelin.paper-runner")


def load_deployment(path):
    with open(path, encoding="utf-8") as stream:
        deployment = json.load(stream)
    if deployment.get("mode") != "paper" or deployment.get("market") != "krx":
        raise ValueError("paper runner는 KRX paper deployment만 허용합니다.")
    strategy = deployment.get("strategy") or {}
    if not deployment.get("account_id") or not strategy.get("symbols"):
        raise ValueError("account_id와 strategy.symbols가 필요합니다.")
    if strategy.get("timeframe", "1d") != "1d":
        raise ValueError("현재 자동 paper runner는 1d 전략만 지원합니다.")
    validate_strategy(strategy, strategy["symbols"])
    deployment.setdefault("observed_state", "RUNNING")
    return deployment


async def run(deployment, interval_seconds, once=False):
    broker = KISBrokerAdapter(KISConfig(
        app_key=settings.KIS_APP_KEY,
        app_secret=settings.KIS_APP_SECRET,
        account_no=settings.KIS_ACCOUNT_NO,
        environment="paper",
    ))
    data = ProviderMarketDataAdapter(KRXProvider(), "krx")
    while True:
        try:
            result = await execute_from_market_data(
                deployment, data_adapter=data, broker=broker,
                as_of=datetime.now(timezone.utc),
            )
            logger.info("paper cycle result=%s", result)
        except Exception:
            logger.exception("paper cycle failed; no retry order is submitted")
        if once:
            return
        await asyncio.sleep(interval_seconds)


def main():
    parser = argparse.ArgumentParser(description="Modelin KRX KIS paper runner")
    parser.add_argument("deployment", help="JSON deployment configuration")
    parser.add_argument("--interval", type=int, default=300, help="cycle interval in seconds")
    parser.add_argument("--once", action="store_true", help="run one cycle and exit")
    args = parser.parse_args()
    if not settings.KIS_APP_KEY or not settings.KIS_APP_SECRET or not settings.KIS_ACCOUNT_NO:
        raise SystemExit("KIS paper credentials are missing in backend/.env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    deployment = load_deployment(args.deployment)
    asyncio.run(run(deployment, max(60, args.interval), once=args.once))


if __name__ == "__main__":
    main()
