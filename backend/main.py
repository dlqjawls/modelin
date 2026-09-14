"""
Modelin - 퀀트 투자 플랫폼 API 서버

FastAPI 기반 백엔드 서버 진입점.
"""
from contextlib import asynccontextmanager
import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from api.market_data import router as market_router
from api.screener import router as screener_router
from api.backtest import router as backtest_router
from api.portfolio import router as portfolio_router
from api.trading import router as trading_router
from api.v1 import router as operations_router
from workers.run_paper import load_deployment, run as run_paper_worker
from application.container import get_container

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 생명주기 관리"""
    worker_task = None
    if settings.PAPER_WORKER_ENABLED and settings.PAPER_DEPLOYMENT_FILE:
        deployment_path = Path(settings.PAPER_DEPLOYMENT_FILE)
        if not deployment_path.exists():
            deployment_path = Path(__file__).resolve().parent.parent / settings.PAPER_DEPLOYMENT_FILE
        deployment = load_deployment(str(deployment_path))
        operations = get_container().operations_store

        async def current_deployment():
            stored = operations.deployment(deployment["id"])
            if not stored:
                candidates = []
                for item in operations.deployments():
                    account = operations.account(item["account_id"]) or {}
                    if (account.get("market") == deployment.get("market")
                            and item.get("desired_state") in {"RUNNING", "PAUSED"}
                            and item.get("observed_state") != "ARCHIVED"):
                        candidates.append(item)
                if len(candidates) == 1:
                    stored = candidates[0]
            if not stored:
                return deployment
            account = operations.account(stored["account_id"]) or {}
            return {
                **deployment,
                **stored,
                # Keep the runner's validated strategy/universe. The
                # operations record controls state and allocation, but an old
                # UI strategy must not silently shrink a market-wide runner to
                # one hard-coded symbol.
                "strategy": deployment.get("strategy", stored.get("strategy")),
                "market": account.get("market", deployment.get("market")),
                "initial_cash": account.get("initial_cash", deployment.get("initial_cash", settings.PAPER_DEFAULT_INITIAL_CASH)),
            }

        app.state.paper_worker_last_result = None

        def record_worker_status(item, error, result=None):
            app.state.paper_worker_last_result = {"error": error, "result": result}
            app.state.paper_worker = "degraded" if error else "running"
            stored = operations.deployment(item["id"])
            if stored:
                stored["last_error"] = error
                operations.update_deployment(stored)

        worker_task = asyncio.create_task(run_paper_worker(
            deployment, max(60, settings.PAPER_WORKER_INTERVAL_SECONDS),
            deployment_loader=current_deployment, status_callback=record_worker_status))
        app.state.paper_worker_task = worker_task
        app.state.paper_worker = "running"
        app.state.paper_worker_deployment_id = deployment["id"]
        print(f"[Modelin] paper worker started: {deployment['id']}")
    else:
        app.state.paper_worker_task = None
        app.state.paper_worker = "disabled"
        app.state.paper_worker_deployment_id = None
        app.state.paper_worker_last_result = None
    # Startup
    print(f"[Modelin] {settings.APP_NAME} v{settings.APP_VERSION} server started")
    print(f"[Modelin] Debug: {settings.DEBUG}")
    yield
    if worker_task:
        worker_task.cancel()
        await asyncio.gather(worker_task, return_exceptions=True)
        app.state.paper_worker_task = None
        print("[Modelin] paper worker stopped")
    # Shutdown
    print(f"[Modelin] {settings.APP_NAME} server stopped")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="퀀트 투자 플랫폼 - 종목 스크리닝, 백테스팅, 포트폴리오 최적화, 자동 매매",
    lifespan=lifespan,
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(market_router)
app.include_router(screener_router)
app.include_router(backtest_router)
app.include_router(portfolio_router)
app.include_router(trading_router)
app.include_router(operations_router)


@app.get("/")
async def root():
    """서버 상태 확인"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/api/health")
async def health_check():
    """헬스 체크"""
    return {
        "status": "healthy",
        "paper_worker": getattr(app.state, "paper_worker", "unknown"),
        "paper_worker_deployment_id": getattr(app.state, "paper_worker_deployment_id", None),
        "paper_worker_last_result": getattr(app.state, "paper_worker_last_result", None),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
