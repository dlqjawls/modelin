"""
Modelin - 포트폴리오 API 라우터
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from application.container import get_container

router = APIRouter(prefix="/api/portfolio", tags=["Portfolio"])
class OptimizeRequest(BaseModel):
    """포트폴리오 최적화 요청"""
    symbols: list[str]
    market: str = "krx"
    start_date: str
    end_date: str
    method: str = "max_sharpe"  # max_sharpe, min_volatility, efficient_risk, hrp
    target_return: float | None = None
    target_volatility: float | None = None
    constraints: dict | None = None  # 가중치 제약 등


class OptimizeResponse(BaseModel):
    """포트폴리오 최적화 결과"""
    weights: dict[str, float]
    expected_return: float
    expected_volatility: float
    sharpe_ratio: float
    efficient_frontier: list[dict] | None = None


@router.post("/optimize", response_model=OptimizeResponse)
async def optimize_portfolio(request: OptimizeRequest):
    portfolio = get_container().portfolio
    """가격 기반의 명시적 포트폴리오 배분."""
    if request.market not in {"krx", "us", "crypto"}:
        raise HTTPException(400, "지원하지 않는 시장입니다.")
    try:
        result = await portfolio.optimize(
            market=request.market, symbols=request.symbols,
            start_date=request.start_date, end_date=request.end_date, method=request.method,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return OptimizeResponse(**result)
