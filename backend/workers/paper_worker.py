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

from core.order_planner import OrderPlanner
from core.strategy_runtime import StrategyRuntime
from ports.broker import OrderRequest
from core.calendar import TradingCalendar
from core.scheduler import PaperScheduler
from core.execution_journal import ExecutionJournal
from core.risk_guard import RiskGuard
from core.strategy_comparator import compare_strategies
from application.paper_cycle import PaperCycleRequest, PaperCycleService

logger = logging.getLogger("modelin.paper_worker")
calendar = TradingCalendar()


async def recover_pending_submissions(journal: ExecutionJournal, broker) -> dict:
    """Resolve pending intents by lookup; never blindly resend them."""
    resolved = []
    unknown = []
    for intent in journal.pending():
        found = await broker.lookup_order(client_order_id=intent["client_order_id"])
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
                       account_snapshot: dict, journal=None, schedule_key=None) -> dict:
    """Evaluate one paper deployment and submit only paper-port orders.

    The broker is dependency-injected; this function never discovers or
    creates a live adapter.  A production worker must persist the decision and
    intent before calling the broker, then persist the returned fill event.
    """
    if deployment.get("mode") != "paper" or deployment.get("observed_state") != "RUNNING":
        return {"status": "skipped", "orders": []}
    nav = Decimal(str(account_snapshot["cash"])) + sum(
        Decimal(str(item.get("quantity", 0))) * Decimal(str(prices.get(item["symbol"], 0)))
        for item in account_snapshot.get("positions", [])
    )
    risk = RiskGuard().evaluate(current_nav=nav, peak_nav=deployment.get("peak_nav"),
                                day_start_nav=deployment.get("day_start_nav"),
                                policy=deployment.get("risk_policy"))
    if not risk.allowed:
        return {"status": "blocked", "reason_codes": risk.reason_codes, "orders": []}
    account_nav = nav if nav > 0 else Decimal("1")
    current_weights = {
        item["symbol"]: Decimal(str(item.get("quantity", 0))) * Decimal(str(prices.get(item["symbol"], 0))) / account_nav
        for item in account_snapshot.get("positions", [])
        if Decimal(str(prices.get(item["symbol"], 0))) > 0
    }
    decision = StrategyRuntime().evaluate(close_prices, deployment["strategy"], current_weights,
                                          deployment.get("cash_buffer", "0.10"))
    if decision.kind == "BLOCKED":
        return {"status": "blocked", "reason_codes": decision.reason_codes, "orders": []}
    if decision.kind == "NO_CHANGE":
        return {"status": "no_change", "reason_codes": decision.reason_codes, "orders": []}
    positions = {f"{p['symbol']}": p for p in account_snapshot.get("positions", [])}
    planner = OrderPlanner(cash_buffer=deployment.get("cash_buffer", "0.10"),
                           max_asset_weight=deployment.get("max_asset_weight", "1"))
    allocation = Decimal(str(deployment.get("allocation_amount", nav)))
    planning_nav = min(nav, allocation)
    intents = planner.plan(cash=account_snapshot["cash"], target_weights=decision.target_weights,
                           positions=positions, prices=prices, nav=planning_nav)
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
    submitted = []
    for intent in intents:
        client_order_id = client_ids[intent.symbol]
        request = OrderRequest(account_id=deployment["account_id"], client_order_id=client_order_id,
                               symbol=intent.symbol, side=intent.side, quantity=intent.quantity,
                               limit_price=intent.reference_price)
        result = await broker.submit(request)
        if journal is not None:
            journal.mark_submitted(request.client_order_id, result)
        submitted.append(result)
    return {"status": "executed", "reason_codes": decision.reason_codes, "orders": submitted}


async def execute_from_market_data(deployment: dict, *, data_adapter, broker, as_of, journal=None):
    """Fetch a normalized snapshot and execute one safe paper cycle."""
    if deployment.get("mode") != "paper":
        raise RuntimeError("live deployment은 아직 지원되지 않습니다.")
    if not calendar.is_trading_day(deployment.get("market", "crypto"), as_of):
        return {"status": "skipped", "reason": "MARKET_CLOSED", "orders": []}
    symbols = deployment["strategy"].get("symbols", [])
    snapshot = await data_adapter.snapshot(symbols, deployment["strategy"].get("timeframe", "1d"), as_of)
    usable = snapshot.usable_bars()
    if not usable:
        return {"status": "blocked", "reason": "NO_FINAL_MARKET_DATA", "orders": []}
    close_prices = data_adapter.close_frame(snapshot)
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
        deployment = {**deployment, "strategy": selected}
    latest_end = max(item.end for item in usable)
    latest = {bar.instrument_id: bar.close for bar in usable if bar.end == latest_end}
    account = await broker.account_snapshot()
    schedule_key = latest_end.isoformat()
    if deployment.get("observed_state") == "LIQUIDATING":
        liquidation_orders = []
        for position in account.get("positions", []):
            symbol = position.get("symbol")
            quantity = Decimal(str(position.get("quantity", "0")))
            price = latest.get(symbol)
            if not symbol or quantity <= 0 or price is None or price <= 0:
                continue
            request = OrderRequest(
                account_id=deployment["account_id"],
                client_order_id=f"liquidate-{deployment['id']}-{schedule_key}-{symbol}",
                symbol=symbol, side="sell", quantity=quantity, limit_price=price,
            )
            liquidation_orders.append(await broker.submit(request))
        return {"status": "liquidated", "orders": liquidation_orders}
    return await execute_once(deployment, close_prices=close_prices,
                               prices=latest, broker=broker, account_snapshot=account,
                               journal=journal, schedule_key=schedule_key)


def paper_cycle_service():
    """Return the application boundary used by external worker entry points."""
    return PaperCycleService(execute_from_market_data)


async def serve(deployment_loader, interval_seconds: int = 60, execute=None, scheduler=None):
    """Run a deployment loop with explicit dependency injection.

    ``execute`` must be an async callable accepting ``(deployment, now)`` and
    is intentionally optional so a misconfigured process cannot place orders.
    The scheduler owns session checks and duplicate-run protection.
    """
    scheduler = scheduler or PaperScheduler(calendar)
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
