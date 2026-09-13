"""Versioned paper deployment control API.

The first implementation is intentionally paper-only. Live broker adapters are
not registered until an explicit venue integration is added and tested.
"""
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from config import settings
from core.strategy_runtime import validate_strategy
from application.deployment_service import DeploymentConflict
from application.operations_service import (
    DeploymentNotFound, DeploymentRevisionConflict, DeploymentStateConflict,
)
from application.container import get_container
from adapters.brokers.kis import KISBrokerAdapter, KISConfig
from adapters.market_data.fred_macro import FredMacroContext

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
    result = _accounts.create_paper(request.model_dump())
    _store.save_idempotent_response(scope="anonymous", endpoint=endpoint, key=idempotency_key,
                                    payload=request.model_dump(), status_code=201, response=result)
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
    return {
        "paper_worker": "configured" if settings.PAPER_WORKER_ENABLED and settings.PAPER_DEPLOYMENT_FILE else "disabled",
        "sources": {
            "kis_paper": "configured" if all((settings.KIS_APP_KEY, settings.KIS_APP_SECRET, settings.KIS_ACCOUNT_NO)) else "missing_credentials",
            "kis_overseas_paper": "configured" if all((settings.KIS_APP_KEY, settings.KIS_APP_SECRET, settings.KIS_ACCOUNT_NO)) else "missing_credentials",
            "rss": "configured" if settings.NEWS_FEEDS else "not_configured",
            "opendart": "configured" if settings.OPENDART_API_KEY else "missing_api_key",
            "sec_edgar": "configured" if settings.SEC_USER_AGENT and settings.SEC_CIKS else "missing_user_agent_or_cik",
            "fred_macro": "configured_public_csv" if not settings.FRED_API_KEY else "configured_api",
        },
        "live_trading": "disabled_by_default",
        "crypto_trading": "paused",
    }


@router.get("/diagnostics/live")
async def live_diagnostics():
    """Opt-in read-only provider checks; no order endpoint is called."""
    result = {"kis_krx": {}, "kis_us": {}, "fred": {}}
    credentials = (settings.KIS_APP_KEY, settings.KIS_APP_SECRET, settings.KIS_ACCOUNT_NO)
    if not all(credentials):
        result["kis_krx"] = result["kis_us"] = {"status": "missing_credentials"}
    else:
        for market, key in (("krx", "kis_krx"), ("us", "kis_us")):
            try:
                snapshot = await KISBrokerAdapter(KISConfig(
                    app_key=settings.KIS_APP_KEY, app_secret=settings.KIS_APP_SECRET,
                    account_no=settings.KIS_ACCOUNT_NO, environment="paper", market=market,
                )).account_snapshot()
                result[key] = {"status": "ok", "source": snapshot.get("source")}
            except Exception as exc:  # noqa: BLE001 - safe provider status only
                result[key] = {"status": "error", "error": type(exc).__name__}
    try:
        macro = await FredMacroContext(settings.FRED_API_KEY).collect(days=7)
        result["fred"] = {"status": "ok" if macro.get("macro_data_available") else "error",
                           "source": macro.get("macro_source"), "failures": macro.get("macro_failures")}
    except Exception as exc:  # noqa: BLE001 - safe provider status only
        result["fred"] = {"status": "error", "error": type(exc).__name__}
    return result


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
        prior = _store.idempotent_response(scope="anonymous", endpoint=endpoint,
                                           key=idempotency_key, payload=request.model_dump())
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if prior:
        return prior["response"]
    try:
        result = _deployments.create_paper(request.model_dump())
        _store.save_idempotent_response(scope="anonymous", endpoint=endpoint, key=idempotency_key,
                                        payload=request.model_dump(), status_code=201, response=result)
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
        prior = _store.idempotent_response(scope="anonymous", endpoint=endpoint,
                                           key=idempotency_key, payload=payload)
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
