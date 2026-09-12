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
from adapters.brokers.paper import PaperBrokerAdapter
from adapters.brokers.alpaca import AlpacaBrokerAdapter, AlpacaConfig
from adapters.market_data.provider_adapter import ProviderMarketDataAdapter
from config import settings
from data.providers.krx_provider import KRXProvider
from data.providers.us_provider import USProvider
from adapters.market_data.news_feed import RSSNewsContext
from adapters.market_data.official_sources import OpenDartClient, SecSubmissionsClient
from core.market_context import NewsEventEngine
from workers.paper_worker import execute_from_market_data
from core.strategy_runtime import validate_strategy
from core.execution_journal import ExecutionJournal
from workers.paper_worker import recover_pending_submissions

logger = logging.getLogger("modelin.paper-runner")


def load_deployment(path):
    with open(path, encoding="utf-8") as stream:
        deployment = json.load(stream)
    if deployment.get("mode") != "paper" or deployment.get("market") not in {"krx", "us"}:
        raise ValueError("paper runner는 KRX 또는 US paper deployment만 허용합니다.")
    strategy = deployment.get("strategy") or {}
    if not deployment.get("account_id") or not strategy.get("symbols"):
        raise ValueError("account_id와 strategy.symbols가 필요합니다.")
    deployment.setdefault("id", f"{deployment['account_id']}-{deployment['market']}-paper")
    if strategy.get("timeframe", "1d") != "1d":
        raise ValueError("현재 자동 paper runner는 1d 전략만 지원합니다.")
    validate_strategy(strategy, strategy["symbols"])
    deployment.setdefault("observed_state", "RUNNING")
    return deployment


async def run(deployment, interval_seconds, once=False, deployment_loader=None):
    if deployment["market"] == "krx":
        broker = KISBrokerAdapter(KISConfig(
            app_key=settings.KIS_APP_KEY, app_secret=settings.KIS_APP_SECRET,
            account_no=settings.KIS_ACCOUNT_NO, environment="paper"))
        data = ProviderMarketDataAdapter(KRXProvider(), "krx")
    else:
        if deployment.get("broker", settings.US_PAPER_BROKER) == "alpaca":
            if not settings.ALPACA_API_KEY or not settings.ALPACA_API_SECRET:
                raise RuntimeError("Alpaca paper 자격증명이 없어 US worker를 시작할 수 없습니다.")
            broker = AlpacaBrokerAdapter(AlpacaConfig(
                settings.ALPACA_API_KEY, settings.ALPACA_API_SECRET,
                account_id=deployment["account_id"]))
        else:
            broker = PaperBrokerAdapter(deployment["account_id"], settings.PAPER_DB_PATH, "us",
                                        initial_cash=deployment.get("initial_cash", "10000000"))
        data = ProviderMarketDataAdapter(USProvider(), "us")
    journal = ExecutionJournal(settings.PAPER_DB_PATH)
    recovery = await recover_pending_submissions(journal, broker)
    if recovery["unknown"]:
        logger.warning("unresolved execution intents remain pending: %s", recovery["unknown"])
    while True:
        try:
            if deployment_loader is not None:
                deployment = await deployment_loader()
            if deployment.get("observed_state") in {"PAUSED", "ARCHIVED", "CANCELING"}:
                logger.info("paper cycle skipped: state=%s", deployment.get("observed_state"))
                if once:
                    return
                await asyncio.sleep(interval_seconds)
                continue
            if settings.NEWS_FEEDS:
                news_context = await RSSNewsContext(settings.NEWS_FEEDS).collect()
                strategy = dict(deployment.get("strategy", {}))
                context = dict(strategy.get("context", {}))
                context.update(news_context)
                strategy["context"] = context
                deployment = {**deployment, "strategy": strategy}
            if settings.OPENDART_API_KEY or settings.SEC_CIKS:
                official_events = []
                if settings.OPENDART_API_KEY:
                    dart = OpenDartClient(settings.OPENDART_API_KEY)
                    for corp_code in deployment.get("corp_codes", []):
                        official_events.extend(await dart.filings(corp_code=corp_code))
                if settings.SEC_USER_AGENT:
                    sec = SecSubmissionsClient(settings.SEC_USER_AGENT)
                    for cik in settings.SEC_CIKS:
                        official_events.extend(await sec.filings(cik))
                if official_events:
                    context = dict(deployment["strategy"].get("context", {}))
                    official_news = NewsEventEngine().aggregate(
                        NewsEventEngine().classify(item.title, item.source, item.published_at)
                        for item in official_events)
                    context.update(official_news)
                    deployment = {**deployment, "strategy": {**deployment["strategy"], "context": context}}
            result = await execute_from_market_data(
                deployment, data_adapter=data, broker=broker,
                as_of=datetime.now(timezone.utc), journal=journal,
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
    deployment = load_deployment(args.deployment)
    if deployment["market"] == "krx" and (not settings.KIS_APP_KEY or not settings.KIS_APP_SECRET or not settings.KIS_ACCOUNT_NO):
        raise SystemExit("KIS paper credentials are missing in backend/.env")
    if deployment["market"] == "us" and deployment.get("broker", settings.US_PAPER_BROKER) == "alpaca" and (not settings.ALPACA_API_KEY or not settings.ALPACA_API_SECRET):
        raise SystemExit("Alpaca paper credentials are missing in backend/.env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run(deployment, max(60, args.interval), once=args.once))


if __name__ == "__main__":
    main()
