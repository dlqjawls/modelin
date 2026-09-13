"""Versioned paper deployment control API.

The first implementation is intentionally paper-only. Live broker adapters are
not registered until an explicit venue integration is added and tested.
"""
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from config import settings
from application.deployment_service import DeploymentConflict
from application.operations_service import (
    DeploymentNotFound, DeploymentRevisionConflict, DeploymentStateConflict,
)
from application.container import get_container

async def require_api_key(x_modelin_key: str | None = Header(default=None, alias="X-Modelin-Key")):
    """Optional protection for the operations API when deployed remotely."""
    if settings.API_ACCESS_KEY and x_modelin_key != settings.API_ACCESS_KEY:
        raise HTTPException(401, "운영 API 인증이 필요합니다.")


router = APIRouter(prefix="/api/v1", tags=["Operations"], dependencies=[Depends(require_api_key)])
_container = get_container()
_store = _container.operations_store
_accounts = _container.account_service
_deployments = _container.deployment_service
_operations = _container.operations_service
_queries = _container.operations_queries
_account_queries = _container.account_queries
_broker_queries = _container.broker_queries
_idempotency = _container.idempotency
_system_queries = _container.system_queries


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
        prior = _idempotency.lookup(endpoint, idempotency_key, request.model_dump())
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if prior:
        return prior["response"]
    result = _accounts.create_paper(request.model_dump())
    _idempotency.save(endpoint, idempotency_key, request.model_dump(), status_code=201, response=result)
    return result


@router.get("/accounts")
async def list_accounts():
    return _queries.accounts()


@router.get("/capabilities")
async def capabilities(account_id: str):
    try:
        account, capability_data = await _broker_queries.capabilities(account_id)
        return {"account_id": account_id, "mode": account["mode"], "capabilities": capability_data}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/diagnostics")
async def diagnostics():
    """Safe readiness diagnostics; secret values are never returned."""
    return _system_queries.diagnostics()


@router.get("/diagnostics/live")
async def live_diagnostics():
    """Opt-in read-only provider checks; no order endpoint is called."""
    return await _system_queries.live_diagnostics()


@router.get("/accounts/{account_id}/snapshot")
async def account_snapshot(account_id: str):
    try:
        account, snapshot = _account_queries.snapshot(account_id)
        return {"account": account, "snapshot": snapshot}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/accounts/{account_id}/orders")
async def account_orders(account_id: str):
    try:
        _account, orders = _account_queries.orders(account_id)
        return {"account_id": account_id, "orders": orders}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/accounts/{account_id}/events")
async def account_events(account_id: str):
    try:
        _account, events = _account_queries.events(account_id)
        return {"account_id": account_id, "events": events}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/deployments", status_code=201)
async def create_deployment(request: DeploymentRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    endpoint = "POST:/deployments"
    try:
        prior = _idempotency.lookup(endpoint, idempotency_key, request.model_dump())
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if prior:
        return prior["response"]
    try:
        result = _deployments.create_paper(request.model_dump())
        _idempotency.save(endpoint, idempotency_key, request.model_dump(), status_code=201, response=result)
        return result
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except DeploymentConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (AttributeError, TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/deployments")
async def list_deployments():
    return _queries.deployments()


@router.get("/deployments/{deployment_id}")
async def get_deployment(deployment_id: str):
    item = _queries.deployment(deployment_id)
    if not item:
        raise HTTPException(404, "deployment을 찾을 수 없습니다.")
    return item


@router.post("/deployments/{deployment_id}/commands", status_code=202)
async def command_deployment(deployment_id: str, request: CommandRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    endpoint = f"POST:/deployments/{deployment_id}/commands"
    payload = {"deployment_id": deployment_id, **request.model_dump()}
    try:
        prior = _idempotency.lookup(endpoint, idempotency_key, payload)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if prior:
        return prior["response"]
    try:
        result = _operations.command(deployment_id, request.type, request.expected_revision)
    except DeploymentNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except (DeploymentRevisionConflict, DeploymentStateConflict) as exc:
        raise HTTPException(409, str(exc)) from exc
    _idempotency.save(endpoint, idempotency_key, payload, status_code=202, response=result)
    return result


@router.get("/health/live")
async def live_health():
    return {"status": "alive"}


@router.get("/health/ready")
async def ready_health():
    try:
        return _system_queries.ready()
    except Exception as exc:
        raise HTTPException(503, "저장소가 준비되지 않았습니다.") from exc
