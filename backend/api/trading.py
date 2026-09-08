"""
Modelin - 자동매매 API 라우터
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/trading", tags=["Trading"])


class PaperTradeRequest(BaseModel):
    """모의투자 요청"""
    symbol: str
    market: str = "crypto"
    side: str  # "buy" or "sell"
    amount: float
    price: float | None = None  # None이면 시장가


@router.post("/paper/order")
async def paper_trade_order(request: PaperTradeRequest):
    """모의투자 주문 (Phase 6에서 구현)"""
    raise HTTPException(501, "자동매매는 Phase 6에서 구현 예정입니다.")


@router.get("/paper/positions")
async def get_paper_positions():
    """모의투자 포지션 조회 (Phase 6에서 구현)"""
    raise HTTPException(501, "자동매매는 Phase 6에서 구현 예정입니다.")
