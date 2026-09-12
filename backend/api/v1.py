"""Versioned paper deployment control API.

The first implementation is intentionally paper-only. Live broker adapters are
not registered until an explicit venue integration is added and tested.
"""
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from config import settings
from core.operations_store import OperationsStore
from core.persistent_paper_broker import PersistentPaperBroker, account_database_path
from core.strategy_runtime import validate_strategy
from adapters.brokers.registry import BrokerRegistry

router = APIRouter(prefix="/api/v1", tags=["Operations"])
_store = OperationsStore(settings.PAPER_DB_PATH)
_brokers = BrokerRegistry()


class PaperAccountRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    market: Literal["krx", "us", "crypto"]
    currency: Literal["KRW", "USD", "USDT"]
    initial_cash: str = Field(pattern=r"^\d+(\.\d+)?$")


class DeploymentRequest(BaseModel):
    account_id: str
    strategy: dict
    allocation_amount: str = Field(pattern=r"^\d+(\.\d+)?$")
    cash_buffer: str = Field(default="0.10", pattern=r"^0(\.\d+)?$|^1(\.0+)?$")
    mode: Literal["paper"] = "paper"


class CommandRequest(BaseModel):
    type: Literal["START", "PAUSE", "CANCEL_OPEN", "LIQUIDATE", "RESUME", "ARCHIVE"]
    reason: str = Field(min_length=1, max_length=500)
    expected_revision: int | None = Field(default=None, ge=1)


@router.post("/accounts/paper", status_code=201)
async def create_paper_account(request: PaperAccountRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    endpoint = "POST:/accounts/paper"
    try:
        prior = _store.idempotent_response(scope="anonymous", endpoint=endpoint,
                                           key=idempotency_key,
                                           payload=request.model_dump())
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if prior:
        return prior["response"]
    account_id = str(uuid4())
    account = {"id": account_id, "name": request.name, "mode": "paper", "market": request.market,
               "currency": request.currency, "initial_cash": request.initial_cash,
               "status": "READY", "created_at": datetime.now(timezone.utc).isoformat()}
    result = _store.create_account(account)
    _store.save_idempotent_response(scope="anonymous", endpoint=endpoint, key=idempotency_key,
                                    payload=request.model_dump(), status_code=201, response=result)
    return result


@router.get("/accounts")
async def list_accounts():
    return _store.accounts()


@router.get("/capabilities")
async def capabilities(account_id: str):
    account = _store.account(account_id)
    if not account:
        raise HTTPException(404, "계좌를 찾을 수 없습니다.")
    broker = _brokers.resolve(mode=account["mode"], venue="unconfigured", account_id=account_id,
                              market=account["market"], paper_path=account_database_path(settings.PAPER_DB_PATH, account_id))
    return {"account_id": account_id, "mode": account["mode"], "capabilities": (await broker.capabilities()).__dict__}


@router.get("/diagnostics")
async def diagnostics():
    """Safe readiness diagnostics; secret values are never returned."""
    return {
        "paper_worker": "configured" if settings.PAPER_WORKER_ENABLED and settings.PAPER_DEPLOYMENT_FILE else "disabled",
        "sources": {
            "kis_paper": "configured" if all((settings.KIS_APP_KEY, settings.KIS_APP_SECRET, settings.KIS_ACCOUNT_NO)) else "missing_credentials",
            "kis_overseas_paper": "not_implemented",
            "rss": "configured" if settings.NEWS_FEEDS else "not_configured",
            "opendart": "configured" if settings.OPENDART_API_KEY else "missing_api_key",
            "sec_edgar": "configured" if settings.SEC_USER_AGENT and settings.SEC_CIKS else "missing_user_agent_or_cik",
        },
        "live_trading": "disabled_by_default",
        "crypto_trading": "paused",
    }


@router.get("/accounts/{account_id}/snapshot")
async def account_snapshot(account_id: str):
    account = _store.account(account_id)
    if not account:
        raise HTTPException(404, "계좌를 찾을 수 없습니다.")
    if account["mode"] != "paper":
        raise HTTPException(503, "현재 live 계좌 스냅샷은 구현되지 않았습니다.")
    broker = PersistentPaperBroker(account_database_path(settings.PAPER_DB_PATH, account_id), initial_cash=account["initial_cash"])
    return {"account": account, "snapshot": broker.snapshot()}


@router.get("/accounts/{account_id}/orders")
async def account_orders(account_id: str):
    account = _store.account(account_id)
    if not account:
        raise HTTPException(404, "계좌를 찾을 수 없습니다.")
    if account["mode"] != "paper":
        raise HTTPException(503, "현재 live 계좌 주문 조회는 구현되지 않았습니다.")
    broker = PersistentPaperBroker(account_database_path(settings.PAPER_DB_PATH, account_id), initial_cash=account["initial_cash"])
    return {"account_id": account_id, "orders": broker.snapshot()["orders"]}


@router.get("/accounts/{account_id}/events")
async def account_events(account_id: str):
    account = _store.account(account_id)
    if not account:
        raise HTTPException(404, "계좌를 찾을 수 없습니다.")
    if account["mode"] != "paper":
        raise HTTPException(503, "현재 live 계좌 이벤트 조회는 구현되지 않았습니다.")
    broker = PersistentPaperBroker(account_database_path(settings.PAPER_DB_PATH, account_id), initial_cash=account["initial_cash"])
    return {"account_id": account_id, "events": broker.snapshot()["events"]}


@router.post("/deployments", status_code=201)
async def create_deployment(request: DeploymentRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    endpoint = "POST:/deployments"
    try:
        prior = _store.idempotent_response(scope="anonymous", endpoint=endpoint,
                                           key=idempotency_key, payload=request.model_dump())
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if prior:
        return prior["response"]
    account = _store.account(request.account_id)
    if not account:
        raise HTTPException(404, "계좌를 찾을 수 없습니다.")
    if request.mode != account["mode"]:
        raise HTTPException(409, "계좌와 deployment 모드가 다릅니다.")
    try:
        strategy = validate_strategy(request.strategy, request.strategy.get("symbols"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    deployment_id = str(uuid4())
    item = {"id": deployment_id, "account_id": request.account_id, "mode": "paper",
            "strategy": strategy, "allocation_amount": request.allocation_amount,
            "cash_buffer": request.cash_buffer, "desired_state": "DRAFT", "observed_state": "DRAFT",
            "pause_epoch": 0, "revision": 1, "last_error": None}
    try:
        result = _store.create_deployment(item)
        _store.save_idempotent_response(scope="anonymous", endpoint=endpoint, key=idempotency_key,
                                        payload=request.model_dump(), status_code=201, response=result)
        return result
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/deployments")
async def list_deployments():
    return _store.deployments()


@router.get("/deployments/{deployment_id}")
async def get_deployment(deployment_id: str):
    item = _store.deployment(deployment_id)
    if not item:
        raise HTTPException(404, "deployment을 찾을 수 없습니다.")
    return item


@router.post("/deployments/{deployment_id}/commands", status_code=202)
async def command_deployment(deployment_id: str, request: CommandRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    endpoint = f"POST:/deployments/{deployment_id}/commands"
    payload = {"deployment_id": deployment_id, **request.model_dump()}
    try:
        prior = _store.idempotent_response(scope="anonymous", endpoint=endpoint,
                                           key=idempotency_key, payload=payload)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if prior:
        return prior["response"]
    item = _store.deployment(deployment_id)
    if not item:
        raise HTTPException(404, "deployment을 찾을 수 없습니다.")
    if request.expected_revision is not None and request.expected_revision != item["revision"]:
        raise HTTPException(409, "deployment revision이 오래되었습니다.")
    command = request.type
    if command in {"START", "RESUME"}:
        item["desired_state"] = "RUNNING"
        # A control API request cannot prove that market data, reconciliation,
        # and broker capabilities are ready. The worker must promote STARTING
        # to RUNNING after those checks pass.
        item["observed_state"] = "STARTING"
    elif command == "PAUSE":
        item["pause_epoch"] += 1
        item["desired_state"] = item["observed_state"] = "PAUSED"
    elif command == "CANCEL_OPEN":
        item["pause_epoch"] += 1
        item["desired_state"] = "PAUSED"
        item["observed_state"] = "CANCELING"
    elif command == "LIQUIDATE":
        item["pause_epoch"] += 1
        item["desired_state"] = "LIQUIDATING"
        item["observed_state"] = "LIQUIDATING"
    elif command == "ARCHIVE":
        item["desired_state"] = item["observed_state"] = "ARCHIVED"
    expected_revision = item["revision"]
    item["revision"] += 1
    if not _store.update_deployment_if_revision(item, expected_revision):
        raise HTTPException(409, "deployment 상태가 동시에 변경되었습니다.")
    result = {"command_id": str(uuid4()), "status": "ACCEPTED", "command": command, **item}
    _store.save_idempotent_response(scope="anonymous", endpoint=endpoint, key=idempotency_key,
                                    payload=payload, status_code=202, response=result)
    return result


@router.get("/health/live")
async def live_health():
    return {"status": "alive"}


@router.get("/health/ready")
async def ready_health():
    try:
        # Opening the local repository verifies that the worker can use its
        # configured persistence path without placing an order.
        OperationsStore(settings.PAPER_DB_PATH)
        return {"status": "ready", "mode": "paper_only"}
    except Exception as exc:
        raise HTTPException(503, "저장소가 준비되지 않았습니다.") from exc
