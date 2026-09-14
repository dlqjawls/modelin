"""
Modelin - 시장 데이터 API 라우터
"""
import math

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from application.container import get_container

router = APIRouter(prefix="/api/market", tags=["Market Data"])

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


class QuoteResponse(BaseModel):
    symbol: str
    market: str
    source: str
    price: float | None = None
    change: float | None = None
    change_rate: float | None = None


# === Endpoints ===

@router.get("/quote", response_model=QuoteResponse)
async def get_quote(
    symbol: str = Query(..., description="종목 코드"),
    market: str = Query("krx", description="시장 (krx, us)"),
):
    """KIS 현재가 조회. 주문을 생성하지 않는 읽기 전용 API."""
    try:
        quote = await get_container().quotes.quote(market, symbol)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"현재가 조회 실패: {type(exc).__name__}") from exc
    return QuoteResponse(
        symbol=quote["symbol"], market=quote["market"], source=quote["source"],
        price=float(quote["price"]) if quote.get("price") not in (None, "") else None,
        change=float(quote["change"]) if quote.get("change") not in (None, "") else None,
        change_rate=float(quote["change_rate"]) if quote.get("change_rate") not in (None, "") else None,
    )

@router.get("/search", response_model=list[AssetInfoResponse])
async def search_assets(
    q: str = Query(..., description="검색어 (종목명 또는 코드)"),
    market: str = Query("krx", description="시장 (krx, us, crypto)"),
):
    """종목 검색"""
    market_data = get_container().market_data
    try:
        results = await market_data.search(market, q)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
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
    market_data = get_container().market_data
    try:
        df = await market_data.ohlcv(market, symbol, start, end, interval)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as e:
        raise HTTPException(500, f"데이터 조회 실패: {str(e)}")

    if df.empty:
        return []

    result = []
    for idx, row in df.iterrows():
        date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
        try:
            values = {name: float(row.get(name, 0)) for name in ("open", "high", "low", "close", "volume")}
        except (TypeError, ValueError):
            continue
        prices = (values["open"], values["high"], values["low"], values["close"])
        if (not all(math.isfinite(value) for value in values.values())
                or any(value <= 0 for value in prices)
                or values["volume"] < 0
                or values["high"] < max(values["open"], values["close"])
                or values["low"] > min(values["open"], values["close"])):
            continue
        result.append(OHLCVItem(
            date=date_str,
            open=values["open"], high=values["high"],
            low=values["low"], close=values["close"], volume=values["volume"],
        ))
    return result


@router.get("/info", response_model=AssetInfoResponse)
async def get_asset_info(
    symbol: str = Query(..., description="종목 코드"),
    market: str = Query("krx", description="시장"),
):
    """종목 기본 정보 조회"""
    market_data = get_container().market_data
    try:
        info = await market_data.info(market, symbol)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
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
    market_data = get_container().market_data
    try:
        data = await market_data.fundamental(market, symbol)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
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
    market_data = get_container().market_data
    try:
        tickers = await market_data.tickers(market)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
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
