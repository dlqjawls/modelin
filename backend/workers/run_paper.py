"""Run one configured domestic KRX paper deployment continuously.

This process is deliberately fail-closed: only KRX + KIS paper mode is
accepted. US and crypto execution require separate runners.
"""
import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow both ``python -m workers.run_paper`` from the project root and direct
# execution of this file without requiring the caller to set PYTHONPATH.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config import settings
from workers.paper_worker import paper_cycle_service
from application.paper_cycle import PaperCycleRequest
from workers.paper_runtime import build_paper_runtime
from application.container import get_container
from core.strategy_runtime import validate_strategy
from data.persistence.execution_journal import ExecutionJournal
from workers.paper_worker import recover_pending_submissions

logger = logging.getLogger("modelin.paper-runner")


def load_deployment(path, allowed_markets=None):
    allowed_markets = allowed_markets or {"krx"}
    deployment_path = Path(path)
    if not deployment_path.is_absolute():
        repo_root = Path(__file__).resolve().parents[2]
        candidates = (Path.cwd() / deployment_path, repo_root / deployment_path)
        deployment_path = next((candidate for candidate in candidates if candidate.is_file()), candidates[-1])
    with deployment_path.open(encoding="utf-8") as stream:
        deployment = json.load(stream)
    # Example deployments deliberately avoid committing an account number.
    # Resolve that placeholder from backend/.env before any broker request.
    if deployment.get("mode") != "paper" or deployment.get("market") not in allowed_markets:
        if allowed_markets == {"krx"}:
            raise ValueError("현재 paper runner는 국내 KRX paper deployment만 허용합니다.")
        allowed = ", ".join(sorted(allowed_markets))
        raise ValueError(f"현재 runner는 {allowed} paper deployment만 허용합니다.")
    if deployment.get("account_id") == "KIS_ACCOUNT_NO_FROM_ENV":
        account_no = settings.KIS_US_ACCOUNT_NO if deployment["market"] == "us" else settings.KIS_KRX_ACCOUNT_NO
        if not account_no:
            raise ValueError("시장별 KIS 계좌번호가 backend/.env에 필요합니다.")
        deployment["account_id"] = account_no
    strategy = deployment.get("strategy") or {}
    if not deployment.get("account_id"):
        raise ValueError("account_id가 필요합니다.")
    if not strategy.get("symbols") and strategy.get("universe") != "market":
        raise ValueError("strategy.symbols 또는 strategy.universe=market가 필요합니다.")
    deployment.setdefault("id", f"{deployment['account_id']}-{deployment['market']}-paper")
    if strategy.get("timeframe", "1d") != "1d":
        raise ValueError("현재 자동 paper runner는 1d 전략만 지원합니다.")
    if (deployment.get("market") == "us"
            and strategy.get("universe") != "market"
            and deployment.get("exchange") not in {"NASD", "NYSE", "AMEX"}):
        raise ValueError("미국 고정 종목 deployment는 exchange를 NASD, NYSE 또는 AMEX로 명시해야 합니다.")
    validate_strategy(strategy, strategy.get("symbols"))
    deployment.setdefault("observed_state", "RUNNING")
    return deployment


async def resolve_market_universe(deployment: dict, provider) -> dict:
    """Resolve the complete provider universe before strategy evaluation."""
    strategy = deployment.get("strategy", {})
    if strategy.get("universe") != "market":
        return deployment
    tickers = await provider.get_tickers()
    symbols = [ticker.symbol for ticker in tickers if ticker.symbol]
    if not symbols:
        raise RuntimeError("시장 종목 마스터가 비어 있어 자동매매를 시작할 수 없습니다.")
    symbols = list(dict.fromkeys(symbols))
    logger.info("market universe resolved: market=%s symbols=%d", deployment.get("market"), len(symbols))
    resolved = dict(strategy)
    resolved["symbols"] = symbols
    exchange_map = {
        ticker.symbol: ticker.extra.get("exchange")
        for ticker in tickers
        if deployment.get("market") == "us"
        and ticker.symbol and ticker.extra.get("exchange") in {"NASD", "NYSE", "AMEX"}
    }
    return {**deployment, "strategy": resolved, "exchange_map": exchange_map}


async def run(deployment, interval_seconds, once=False, deployment_loader=None, status_callback=None):
    journal = ExecutionJournal(settings.PAPER_DB_PATH)
    cycle_service = paper_cycle_service()
    context_service = get_container().paper_context
    runtime = None
    broker = data = None
    while runtime is None:
        try:
            if deployment_loader is not None:
                deployment = await deployment_loader()
            runtime = build_paper_runtime(deployment)
            deployment = await resolve_market_universe(deployment, runtime.data.provider)
            if deployment.get("market") == "us" and deployment.get("strategy", {}).get("universe") == "market" and not deployment.get("exchange_map"):
                raise RuntimeError("미국 전체 종목 거래소 목록을 확인하지 못해 주문을 시작할 수 없습니다.")
            if deployment.get("market") == "us" and deployment.get("exchange_map"):
                runtime = build_paper_runtime(deployment)
            broker, data = runtime.broker, runtime.data
            recovery = await recover_pending_submissions(journal, broker)
            if recovery["unknown"]:
                logger.warning("execution intents quarantined for manual reconciliation: %d", len(recovery["unknown"]))
        except Exception as exc:
            runtime = None
            broker = data = None
            logger.exception("paper worker initialization failed; no order is submitted")
            if status_callback is not None:
                status_callback(deployment, str(exc), None)
            if once:
                return
            await asyncio.sleep(interval_seconds)
    while True:
        try:
            if deployment_loader is not None:
                deployment = await deployment_loader()
            deployment = await resolve_market_universe(deployment, runtime.data.provider)
            if deployment.get("market") == "us" and deployment.get("strategy", {}).get("universe") == "market" and not deployment.get("exchange_map"):
                raise RuntimeError("미국 전체 종목 거래소 목록을 확인하지 못해 주문을 시작할 수 없습니다.")
            # Reuse the initialized runtime and its in-memory OHLCV cache.
            # Rebuilding every interval would reread thousands of persistent
            # cache files for a market-wide deployment.
            broker, data = runtime.broker, runtime.data
            if deployment.get("observed_state") in {"PAUSED", "ARCHIVED", "CANCELING"}:
                logger.info("paper cycle skipped: state=%s", deployment.get("observed_state"))
                if once:
                    return
                await asyncio.sleep(interval_seconds)
                continue
            deployment = await context_service.enrich(deployment)
            cycle_deployment = deployment
            if (deployment.get("desired_state") == "RUNNING"
                    and deployment.get("observed_state") == "STARTING"):
                # STARTING is a readiness gate. The cycle may proceed only
                # when final market data and the broker snapshot are usable.
                cycle_deployment = {**deployment, "observed_state": "RUNNING"}
            result = await cycle_service.execute(
                PaperCycleRequest(cycle_deployment, datetime.now(timezone.utc)),
                data_adapter=data, broker=broker, journal=journal,
            )
            if (cycle_deployment is not deployment
                    and result.get("status") not in {"blocked", "skipped"}):
                deployment = {**deployment, "observed_state": "RUNNING", "last_error": None}
            logger.info("paper cycle result=%s", result)
            if status_callback is not None:
                status_callback(deployment, None, result)
        except Exception as exc:
            logger.exception("paper cycle failed; no retry order is submitted")
            if status_callback is not None:
                status_callback(deployment, str(exc), None)
        if once:
            return
        await asyncio.sleep(interval_seconds)


def main():
    parser = argparse.ArgumentParser(description="Modelin domestic KRX KIS paper runner")
    parser.add_argument("deployment", help="JSON deployment configuration")
    parser.add_argument("--interval", type=int, default=300, help="cycle interval in seconds")
    parser.add_argument("--once", action="store_true", help="run one cycle and exit")
    args = parser.parse_args()
    deployment = load_deployment(args.deployment)
    if deployment["market"] not in settings.PAPER_ALLOWED_MARKETS:
        raise SystemExit(f"{deployment['market']} paper 실행이 비활성화되어 있습니다. backend/.env의 PAPER_ALLOWED_MARKETS를 확인하세요.")
    account_no = settings.KIS_KRX_ACCOUNT_NO
    if not settings.KIS_APP_KEY or not settings.KIS_APP_SECRET or not account_no:
        raise SystemExit("KIS paper credentials are missing in backend/.env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run(deployment, max(60, args.interval), once=args.once))


if __name__ == "__main__":
    main()
