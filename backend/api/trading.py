"""
Modelin - 자동매매 API 라우터
"""
from fastapi import APIRouter, HTTPException
from decimal import Decimal
from pydantic import BaseModel, Field

from config import settings
from core.persistent_paper_broker import PersistentPaperBroker

router = APIRouter(prefix="/api/trading", tags=["Trading"])


class PaperTradeRequest(BaseModel):
    """모의투자 요청"""
    symbol: str
    market: str = "krx"
    side: str = Field(pattern="^(buy|sell)$")
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)


_paper = PersistentPaperBroker(settings.PAPER_DB_PATH)


@router.post("/paper/order")
async def paper_trade_order(request: PaperTradeRequest):
    """실제 거래소를 호출하지 않는 즉시체결 모의 주문."""
    if request.market == "crypto":
        raise HTTPException(409, "코인 자동매매는 현재 보류 상태입니다.")
    if request.market not in {"krx", "us"}:
        raise HTTPException(400, "지원 시장은 krx 또는 us입니다.")
    try:
        order = _paper.order(symbol=request.symbol, market=request.market, side=request.side,
                             quantity=request.quantity, price=request.price)
        return {"order": order, "mode": "paper"}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/paper/positions")
async def get_paper_positions():
    """모의투자 계좌 상태."""
    return {"mode": "paper", **_paper.snapshot()}
