"""Safe paper deployment worker entry point.

It contains no live broker import. A deployment must explicitly be a paper
account; live execution is intentionally unavailable until a reviewed adapter
is registered.
"""
import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd

from application.paper_decision import PaperDecisionService
from application.paper_execution import PaperExecutionService
from application.market_snapshot import PaperMarketSnapshotService
from core.scheduler import PaperScheduler
from data.persistence.execution_journal import ExecutionJournal
from core.risk_guard import RiskGuard
from core.strategy_comparator import compare_strategies
from application.paper_cycle import PaperCycleRequest, PaperCycleService

logger = logging.getLogger("modelin.paper_worker")


async def recover_pending_submissions(journal: ExecutionJournal, broker) -> dict:
    """Resolve pending intents by lookup; never blindly resend them."""
    resolved = []
    unknown = []
    for intent in journal.pending():
        try:
            # A broker can only reconcile an intent when it has a broker-side
            # order id. Never let an incomplete pending row stop the worker.
            broker_order_id = intent.get("broker_order_id")
            if not broker_order_id:
                journal.mark_recovery_unknown(intent["client_order_id"])
                unknown.append(intent["client_order_id"])
                continue
            found = await broker.lookup_order(
                client_order_id=intent["client_order_id"],
                broker_order_id=broker_order_id,
            )
        except Exception:
            logger.exception("pending order recovery failed; order remains blocked")
            journal.mark_recovery_unknown(intent["client_order_id"])
            unknown.append(intent["client_order_id"])
            continue
        if found is None:
            journal.mark_recovery_unknown(intent["client_order_id"])
            unknown.append(intent["client_order_id"])
            continue
        journal.mark_submitted(intent["client_order_id"], found)
        resolved.append(intent["client_order_id"])
    return {"resolved": resolved, "unknown": unknown, "resubmitted": []}


async def run_once(deployment: dict) -> dict:
    if deployment.get("mode") != "paper":
        raise RuntimeError("live deployment은 아직 지원되지 않습니다.")
    if deployment.get("observed_state") != "RUNNING":
        return {"status": "skipped", "reason": "deployment is not running"}
    # Data acquisition and persistence are injected by the production worker.
    # Keeping this guard explicit prevents a deployment without a feed from
    # silently placing orders.
    snapshot = deployment.get("close_prices")
    if snapshot is None:
        return {"status": "blocked", "reason": "paper data feed is not configured"}
    return {"status": "ready", "reason": "strategy evaluation must be committed through the order planner"}


def readiness_result(deployment: dict, *, has_data: bool, reconciled: bool = True) -> dict:
    """Return the only safe observed state for a paper deployment startup."""
    if deployment.get("mode") != "paper":
        return {"observed_state": "BLOCKED", "reason": "LIVE_ADAPTER_NOT_CONFIGURED"}
    if not has_data:
        return {"observed_state": "STARTING", "reason": "NO_FINAL_MARKET_DATA"}
    if not reconciled:
        return {"observed_state": "STARTING", "reason": "RECONCILIATION_REQUIRED"}
    return {"observed_state": "RUNNING", "reason": "READY"}


async def execute_once(deployment: dict, *, close_prices: pd.DataFrame, prices: dict, broker,
                       account_snapshot: dict, journal=None, schedule_key=None,
                       decision_service=None, execution_service=None) -> dict:
    """Evaluate one paper deployment and submit only paper-port orders.

    The broker is dependency-injected; this function never discovers or
    creates a live adapter.  A production worker must persist the decision and
    intent before calling the broker, then persist the returned fill event.
    """
    if deployment.get("mode") != "paper" or deployment.get("observed_state") != "RUNNING":
        return {"status": "skipped", "orders": []}
    account_nav = Decimal(str(account_snapshot["cash"])) + sum(
        Decimal(str(item.get("quantity", 0))) * Decimal(str(prices.get(item["symbol"], 0)))
        for item in account_snapshot.get("positions", [])
    )
    account_nav = account_nav if account_nav > 0 else Decimal("1")
    current_weights = {
        item["symbol"]: Decimal(str(item.get("quantity", 0))) * Decimal(str(prices.get(item["symbol"], 0))) / account_nav
        for item in account_snapshot.get("positions", [])
        if Decimal(str(prices.get(item["symbol"], 0))) > 0
    }
    decision_service = decision_service or PaperDecisionService()
    execution_service = execution_service or PaperExecutionService()
    decision = decision_service.evaluate(close_prices, deployment["strategy"], current_weights,
                                         deployment.get("cash_buffer", "0.10"))
    if decision.kind == "BLOCKED":
        return {"status": "blocked", "reason_codes": decision.reason_codes, "orders": []}
    if decision.kind == "NO_CHANGE":
        return {"status": "no_change", "reason_codes": decision.reason_codes, "orders": []}
    positions = {f"{p['symbol']}": p for p in account_snapshot.get("positions", [])}

    # A market-wide strategy has already evaluated the complete universe from
    # the historical snapshot. Refresh only held and selected symbols before
    # planning; this keeps the request count bounded by the portfolio size
    # while preventing orders at stale historical closing prices.
    quote_symbols = set(positions) | set(decision.target_weights)
    if hasattr(broker, "quote") and quote_symbols:
        async def refresh_quote(symbol):
            try:
                result = await broker.quote(symbol)
                if result.get("price") not in (None, ""):
                    prices[symbol] = result["price"]
            except Exception:
                return
        # KIS applies an app-level interval limit to quote requests. Serialise
        # the small selected/held set instead of bursting concurrent calls.
        for index, symbol in enumerate(sorted(quote_symbols)):
            if index:
                await asyncio.sleep(1.1)
            await refresh_quote(symbol)

    nav = Decimal(str(account_snapshot["cash"])) + sum(
        Decimal(str(item.get("quantity", 0))) * Decimal(str(prices.get(item["symbol"], 0)))
        for item in account_snapshot.get("positions", [])
    )
    risk = RiskGuard().evaluate(current_nav=nav, peak_nav=deployment.get("peak_nav"),
                                day_start_nav=deployment.get("day_start_nav"),
                                policy=deployment.get("risk_policy"))
    if not risk.allowed:
        return {"status": "blocked", "reason_codes": risk.reason_codes, "orders": []}
    allocation = Decimal(str(deployment.get("allocation_amount", nav)))
    planning_nav = min(nav, allocation)
    intents = decision_service.plan_orders(
        cash=account_snapshot["cash"], target_weights=decision.target_weights,
        positions=positions, prices=prices, nav=planning_nav, deployment=deployment,
    )
    last_index = close_prices.index[-1]
    default_schedule_key = last_index.isoformat() if hasattr(last_index, "isoformat") else str(last_index)
    schedule_key = schedule_key or default_schedule_key
    run_token = hashlib.sha256(schedule_key.encode("utf-8")).hexdigest()[:12]
    client_ids = {intent.symbol: f"paper-{deployment['id']}-{run_token}-{intent.symbol}-{intent.side}" for intent in intents}
    if journal is not None:
        existing_run = journal.has_run(deployment["id"], schedule_key)
        _, journal_rows = journal.commit_plan(deployment_id=deployment["id"], schedule_key=schedule_key,
                                              decision={"kind": decision.kind, "reason_codes": decision.reason_codes,
                                                        "target_weights": decision.target_weights}, intents=[
                                                  type("JournalIntent", (), {"client_order_id": client_ids[intent.symbol],
                                                                              "symbol": intent.symbol, "side": intent.side,
                                                                              "quantity": intent.quantity, "reference_price": intent.reference_price})()
                                                  for intent in intents])
        if existing_run:
            return {"status": "already_journaled", "reason_codes": decision.reason_codes, "orders": journal_rows}
    def record_submission(client_order_id, result):
        if journal is not None:
            journal.mark_submitted(client_order_id, result)

    submitted = await execution_service.submit_intents(
        deployment=deployment, intents=intents, broker=broker, client_ids=client_ids,
        on_submitted=record_submission,
    )
    return {"status": "executed", "reason_codes": decision.reason_codes, "orders": submitted}


async def execute_from_market_data(deployment: dict, *, data_adapter, broker, as_of, journal=None,
                                   decision_service=None, execution_service=None, snapshot_service=None):
    """Fetch a normalized snapshot and execute one safe paper cycle."""
    if deployment.get("mode") != "paper":
        raise RuntimeError("live deployment은 아직 지원되지 않습니다.")
    snapshot_service = snapshot_service or PaperMarketSnapshotService()
    if isinstance(snapshot_service, PaperMarketSnapshotService):
        prepared, early_result = await snapshot_service.collect(
        deployment, data_adapter=data_adapter, as_of=as_of,
        )
    else:
        # Preserve the small test/delivery seam used by external adapters.
        prepared, early_result = await snapshot_service.collect(
            deployment, data_adapter=data_adapter, as_of=as_of,
        )
    if early_result is not None:
        return early_result
    snapshot, usable, close_prices = prepared.snapshot, prepared.usable_bars, prepared.close_prices
    symbols = deployment.get("strategy", {}).get("symbols", [])
    if deployment.get("strategy", {}).get("auto_select"):
        candidates = deployment["strategy"].get("candidates", [])
        if not candidates:
            return {"status": "blocked", "reason": "NO_STRATEGY_CANDIDATES", "orders": []}
        rankings = compare_strategies(data_adapter.open_frame(snapshot), close_prices,
                                      symbols=symbols, market=deployment.get("market", "krx"),
                                      strategies=candidates)
        selected = dict(rankings[0].strategy)
        selected["symbols"] = symbols
        selected["context"] = deployment["strategy"].get("context", {})
        selected["adaptive"] = deployment["strategy"].get("adaptive", False)
        selected["universe"] = deployment["strategy"].get("universe")
        selected["max_positions"] = deployment["strategy"].get("max_positions")
        deployment = {**deployment, "strategy": selected}
    latest = prepared.latest_prices
    account = await broker.account_snapshot()
    schedule_key = prepared.schedule_key
    if deployment.get("observed_state") == "LIQUIDATING":
        execution_service = execution_service or PaperExecutionService()
        liquidation_orders = await execution_service.liquidate(
            deployment=deployment, positions=account.get("positions", []),
            prices=latest, broker=broker, schedule_key=schedule_key,
        )
        return {"status": "liquidated", "orders": liquidation_orders}
    return await execute_once(deployment, close_prices=close_prices,
                               prices=latest, broker=broker, account_snapshot=account,
                               journal=journal, schedule_key=schedule_key,
                               decision_service=decision_service,
                               execution_service=execution_service)


def paper_cycle_service():
    """Return the application boundary used by external worker entry points."""
    from application.container import get_container
    container = get_container()
    return PaperCycleService(
        execute_from_market_data,
        container.paper_decisions,
        container.paper_execution,
        container.market_snapshots,
    )


async def serve(deployment_loader, interval_seconds: int = 60, execute=None, scheduler=None):
    """Run a deployment loop with explicit dependency injection.

    ``execute`` must be an async callable accepting ``(deployment, now)`` and
    is intentionally optional so a misconfigured process cannot place orders.
    The scheduler owns session checks and duplicate-run protection.
    """
    scheduler = scheduler or PaperScheduler()
    while True:
        deployment = await deployment_loader()
        try:
            now = datetime.now(timezone.utc)
            if execute is None:
                result = await run_once(deployment)
            else:
                result = await scheduler.tick(deployment, now=now, execute=execute)
            logger.info("paper worker tick: %s", result)
        except Exception:
            logger.exception("paper worker tick failed")
        await asyncio.sleep(interval_seconds)
