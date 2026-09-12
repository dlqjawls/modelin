"""
Modelin - 포트폴리오 API 라우터
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import numpy as np
import pandas as pd
from data.providers.krx_provider import KRXProvider
from data.providers.us_provider import USProvider
from data.providers.crypto_provider import CryptoProvider

router = APIRouter(prefix="/api/portfolio", tags=["Portfolio"])
_providers = {"krx": KRXProvider, "us": USProvider, "crypto": CryptoProvider}


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
    """가격 기반의 명시적 포트폴리오 배분."""
    if request.market not in _providers:
        raise HTTPException(400, "지원하지 않는 시장입니다.")
    method = "inverse_volatility" if request.method == "max_sharpe" else request.method
    if method not in {"equal_weight", "inverse_volatility", "min_volatility"}:
        raise HTTPException(400, "지원 방법: equal_weight, inverse_volatility, min_volatility")
    if not request.symbols:
        raise HTTPException(422, "종목을 하나 이상 입력해주세요.")
    provider = _providers[request.market]()
    frames = {}
    for symbol in dict.fromkeys(request.symbols):
        frame = await provider.get_ohlcv(symbol, request.start_date, request.end_date, "1d")
        if not frame.empty and "close" in frame:
            frames[symbol] = frame["close"]
    if not frames:
        raise HTTPException(422, "가격 데이터가 없습니다.")
    prices = pd.DataFrame(frames).ffill().dropna(axis=1, how="all")
    returns = prices.pct_change().dropna(how="all").fillna(0)
    symbols = list(prices.columns)
    if method == "equal_weight":
        raw = np.ones(len(symbols))
    elif method == "inverse_volatility":
        vol = returns.std().replace(0, np.nan).fillna(np.inf).to_numpy()
        raw = 1 / vol
    else:
        cov = returns.cov().to_numpy()
        raw = np.maximum(np.linalg.pinv(cov + np.eye(len(symbols)) * 1e-8) @ np.ones(len(symbols)), 0)
    if not np.isfinite(raw).all() or raw.sum() <= 0:
        raise HTTPException(422, "최적화에 충분한 유효 데이터가 없습니다.")
    weights = raw / raw.sum()
    daily = returns.to_numpy() @ weights
    expected_return = float(np.mean(daily) * 252)
    expected_volatility = float(np.std(daily, ddof=1) * np.sqrt(252)) if len(daily) > 1 else 0.0
    sharpe = expected_return / expected_volatility if expected_volatility else 0.0
    return OptimizeResponse(weights={s: round(float(w), 8) for s, w in zip(symbols, weights)},
                            expected_return=expected_return, expected_volatility=expected_volatility,
                            sharpe_ratio=sharpe, efficient_frontier=None)
