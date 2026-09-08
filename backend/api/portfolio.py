"""
Modelin - 포트폴리오 API 라우터
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
    """포트폴리오 최적화 (Phase 5에서 구현)"""
    raise HTTPException(501, "포트폴리오 최적화는 Phase 5에서 구현 예정입니다.")
