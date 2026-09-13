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
from data.providers.us_provider import USProvider
from adapters.market_data.news_feed import RSSNewsContext
from adapters.market_data.official_sources import OpenDartClient, SecSubmissionsClient
from adapters.market_data.fred_macro import FredMacroContext
from core.market_context import NewsEventEngine
from core.market_context import MacroContext
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


async def run(deployment, interval_seconds, once=False, deployment_loader=None, status_callback=None):
    if deployment["market"] in {"krx", "us"}:
        broker = KISBrokerAdapter(KISConfig(
            app_key=settings.KIS_APP_KEY, app_secret=settings.KIS_APP_SECRET,
            account_no=settings.KIS_ACCOUNT_NO, environment="paper",
            market=deployment["market"], exchange=deployment.get("exchange", "NASD")))
        data = ProviderMarketDataAdapter(KRXProvider(), "krx") if deployment["market"] == "krx" else ProviderMarketDataAdapter(USProvider(), "us")
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
            if settings.FRED_API_KEY or settings.PAPER_WORKER_ENABLED:
                macro = await FredMacroContext(settings.FRED_API_KEY).collect()
                strategy = dict(deployment.get("strategy", {}))
                context = MacroContext.build(
                    fx_change_20d=macro.get("fx_change_20d", 0.0),
                    rate_change_20d=macro.get("rate_change_20d", 0.0),
                    volatility=macro.get("vix_latest", 0.0) / 100.0,
                    news=strategy.get("context", {}),
                )
                context.update(macro)
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
            if status_callback is not None:
                status_callback(deployment, None)
        except Exception as exc:
            logger.exception("paper cycle failed; no retry order is submitted")
            if status_callback is not None:
                status_callback(deployment, str(exc))
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
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run(deployment, max(60, args.interval), once=args.once))


if __name__ == "__main__":
    main()
