"""
Modelin - 종목 스크리닝 API 라우터
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.screener import ScreenerEngine, ScreenerCondition, ScreenerResult

router = APIRouter(prefix="/api/screener", tags=["Screener"])

_engine = ScreenerEngine()


class ScreenerRequest(BaseModel):
    """스크리닝 요청"""
    market: str = "krx"
    conditions: list[dict]  # [{"factor": "per", "operator": "<", "value": 15}, ...]
    sort_by: str = "market_cap"
    sort_desc: bool = True
    limit: int = 50


class ScreenerResponse(BaseModel):
    """스크리닝 결과"""
    results: list[dict]
    total_count: int
    applied_conditions: list[dict]


@router.post("/run", response_model=ScreenerResponse)
async def run_screener(request: ScreenerRequest):
    """종목 스크리닝 실행"""
    try:
        conditions = [
            ScreenerCondition(
                factor=c["factor"],
                operator=c["operator"],
                value=c["value"],
            )
            for c in request.conditions
        ]

        results = await _engine.screen(
            market=request.market,
            conditions=conditions,
            sort_by=request.sort_by,
            sort_desc=request.sort_desc,
            limit=request.limit,
        )

        return ScreenerResponse(
            results=[r.__dict__ for r in results],
            total_count=len(results),
            applied_conditions=request.conditions,
        )
    except Exception as e:
        raise HTTPException(500, f"스크리닝 실패: {str(e)}")
