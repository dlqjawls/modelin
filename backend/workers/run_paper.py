"""Run one configured KRX paper deployment continuously.

This process is deliberately fail-closed: only KRX + KIS paper mode is
accepted, and an incomplete strategy configuration exits before any order.
"""
import argparse
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from config import settings
from workers.paper_worker import paper_cycle_service
from application.paper_cycle import PaperCycleRequest
from workers.paper_runtime import build_paper_runtime
from application.container import get_container
from core.strategy_runtime import validate_strategy
from data.persistence.execution_journal import ExecutionJournal
from workers.paper_worker import recover_pending_submissions

logger = logging.getLogger("modelin.paper-runner")


def load_deployment(path):
    deployment_path = Path(path)
    if not deployment_path.is_absolute():
        repo_root = Path(__file__).resolve().parents[2]
        candidates = (Path.cwd() / deployment_path, repo_root / deployment_path)
        deployment_path = next((candidate for candidate in candidates if candidate.is_file()), candidates[-1])
    with deployment_path.open(encoding="utf-8") as stream:
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
    runtime = build_paper_runtime(deployment)
    broker, data = runtime.broker, runtime.data
    journal = ExecutionJournal(settings.PAPER_DB_PATH)
    cycle_service = paper_cycle_service()
    context_service = get_container().paper_context
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
            deployment = await context_service.enrich(deployment)
            result = await cycle_service.execute(
                PaperCycleRequest(deployment, datetime.now(timezone.utc)),
                data_adapter=data, broker=broker, journal=journal,
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
