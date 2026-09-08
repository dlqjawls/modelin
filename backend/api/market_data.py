"""
Modelin - 시장 데이터 API 라우터
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from data.providers.base import Market
from data.providers.krx_provider import KRXProvider
from data.providers.us_provider import USProvider
from data.providers.crypto_provider import CryptoProvider

router = APIRouter(prefix="/api/market", tags=["Market Data"])

# 프로바이더 인스턴스
_providers = {
    Market.KRX: KRXProvider(),
    Market.US: USProvider(),
    Market.CRYPTO: CryptoProvider(),
}


def _get_provider(market: str):
    """시장 코드로 프로바이더 반환"""
    try:
        m = Market(market.lower())
    except ValueError:
        raise HTTPException(400, f"지원하지 않는 시장: {market}. 사용 가능: krx, us, crypto")
    return _providers[m]


# === Response Models ===

class AssetInfoResponse(BaseModel):
    symbol: str
    name: str
    market: str
    sector: str = ""
    market_cap: float = 0
    currency: str = ""


class OHLCVItem(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class FundamentalResponse(BaseModel):
    symbol: str
    per: float | None = None
    pbr: float | None = None
    psr: float | None = None
    eps: float | None = None
    bps: float | None = None
    roe: float | None = None
    roa: float | None = None
    dividend_yield: float | None = None
    operating_margin: float | None = None
    debt_ratio: float | None = None


# === Endpoints ===

@router.get("/search", response_model=list[AssetInfoResponse])
async def search_assets(
    q: str = Query(..., description="검색어 (종목명 또는 코드)"),
    market: str = Query("krx", description="시장 (krx, us, crypto)"),
):
    """종목 검색"""
    provider = _get_provider(market)
    results = await provider.search(q)
    return [
        AssetInfoResponse(
            symbol=r.symbol,
            name=r.name,
            market=r.market.value,
            sector=r.sector,
            market_cap=r.market_cap,
            currency=r.currency,
        )
        for r in results
    ]


@router.get("/ohlcv", response_model=list[OHLCVItem])
async def get_ohlcv(
    symbol: str = Query(..., description="종목 코드"),
    market: str = Query("krx", description="시장 (krx, us, crypto)"),
    start: str = Query(..., description="시작일 (YYYY-MM-DD)"),
    end: str = Query(..., description="종료일 (YYYY-MM-DD)"),
    interval: str = Query("1d", description="봉 간격 (1m, 5m, 15m, 1h, 1d, 1w, 1M)"),
):
    """OHLCV 데이터 조회"""
    provider = _get_provider(market)

    try:
        df = await provider.get_ohlcv(symbol, start, end, interval)
    except Exception as e:
        raise HTTPException(500, f"데이터 조회 실패: {str(e)}")

    if df.empty:
        return []

    result = []
    for idx, row in df.iterrows():
        date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
        result.append(OHLCVItem(
            date=date_str,
            open=float(row.get("open", 0)),
            high=float(row.get("high", 0)),
            low=float(row.get("low", 0)),
            close=float(row.get("close", 0)),
            volume=float(row.get("volume", 0)),
        ))
    return result


@router.get("/info", response_model=AssetInfoResponse)
async def get_asset_info(
    symbol: str = Query(..., description="종목 코드"),
    market: str = Query("krx", description="시장"),
):
    """종목 기본 정보 조회"""
    provider = _get_provider(market)

    try:
        info = await provider.get_info(symbol)
    except Exception as e:
        raise HTTPException(500, f"정보 조회 실패: {str(e)}")

    return AssetInfoResponse(
        symbol=info.symbol,
        name=info.name,
        market=info.market.value,
        sector=info.sector,
        market_cap=info.market_cap,
        currency=info.currency,
    )


@router.get("/fundamental", response_model=FundamentalResponse)
async def get_fundamental(
    symbol: str = Query(..., description="종목 코드"),
    market: str = Query("krx", description="시장"),
):
    """펀더멘털 데이터 조회"""
    provider = _get_provider(market)

    try:
        data = await provider.get_fundamental(symbol)
    except Exception as e:
        raise HTTPException(500, f"펀더멘털 조회 실패: {str(e)}")

    return FundamentalResponse(
        symbol=data.symbol,
        per=data.per,
        pbr=data.pbr,
        psr=data.psr,
        eps=data.eps,
        bps=data.bps,
        roe=data.roe,
        roa=data.roa,
        dividend_yield=data.dividend_yield,
        operating_margin=data.operating_margin,
        debt_ratio=data.debt_ratio,
    )


@router.get("/tickers", response_model=list[AssetInfoResponse])
async def get_tickers(
    market: str = Query("krx", description="시장 (krx, us, crypto)"),
):
    """전체 종목 목록 조회"""
    provider = _get_provider(market)

    try:
        tickers = await provider.get_tickers()
    except Exception as e:
        raise HTTPException(500, f"종목 목록 조회 실패: {str(e)}")

    return [
        AssetInfoResponse(
            symbol=t.symbol,
            name=t.name,
            market=t.market.value,
            sector=t.sector,
            market_cap=t.market_cap,
            currency=t.currency,
        )
        for t in tickers
    ]
