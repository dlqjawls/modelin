"""Single-process paper scheduler with per-deployment execution guards."""
from datetime import datetime, timezone
from threading import Lock

from core.calendar import TradingCalendar


class PaperScheduler:
    def __init__(self, calendar=None):
        self.calendar = calendar or TradingCalendar()
        self._locks: dict[str, Lock] = {}

    async def tick(self, deployment: dict, *, now: datetime, execute):
        if deployment.get("mode") != "paper":
            return {"status": "blocked", "reason": "LIVE_ADAPTER_NOT_CONFIGURED"}
        if deployment.get("observed_state") != "RUNNING":
            return {"status": "skipped", "reason": "DEPLOYMENT_NOT_RUNNING"}
        market = deployment.get("market", "crypto")
        if not self.calendar.is_trading_day(market, now):
            return {"status": "skipped", "reason": "MARKET_CLOSED"}
        lock = self._locks.setdefault(deployment["id"], Lock())
        if not lock.acquire(blocking=False):
            return {"status": "skipped", "reason": "RUN_ALREADY_IN_PROGRESS"}
        try:
            return await execute(deployment, now)
        finally:
            lock.release()
