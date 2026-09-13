"""
Modelin - 종목 스크리닝 API 라우터
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from application.container import get_container

router = APIRouter(prefix="/api/screener", tags=["Screener"])

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
    screener = get_container().screener
    """종목 스크리닝 실행"""
    try:
        results = await screener.screen(
            market=request.market,
            conditions=request.conditions,
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
