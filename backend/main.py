"""
Modelin - 퀀트 투자 플랫폼 API 서버

FastAPI 기반 백엔드 서버 진입점.
"""
from contextlib import asynccontextmanager
import asyncio

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 생명주기 관리"""
    worker_task = None
    if settings.PAPER_WORKER_ENABLED and settings.PAPER_DEPLOYMENT_FILE:
        deployment = load_deployment(settings.PAPER_DEPLOYMENT_FILE)
        worker_task = asyncio.create_task(run_paper_worker(
            deployment, max(60, settings.PAPER_WORKER_INTERVAL_SECONDS)))
        app.state.paper_worker = "running"
        print(f"[Modelin] paper worker started: {deployment['id']}")
    else:
        app.state.paper_worker = "disabled"
    # Startup
    print(f"[Modelin] {settings.APP_NAME} v{settings.APP_VERSION} server started")
    print(f"[Modelin] Debug: {settings.DEBUG}")
    yield
    if worker_task:
        worker_task.cancel()
        await asyncio.gather(worker_task, return_exceptions=True)
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
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
