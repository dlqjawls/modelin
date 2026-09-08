"""
Modelin - 팩터 기반 종목 스크리닝 엔진
"""
import operator
from dataclasses import dataclass, field

from data.providers.base import Market, FundamentalData
from data.providers.krx_provider import KRXProvider
from data.providers.us_provider import USProvider
from data.providers.crypto_provider import CryptoProvider


@dataclass
class ScreenerCondition:
    """스크리닝 조건"""
    factor: str       # per, pbr, roe, eps, market_cap, ...
    operator: str     # <, <=, >, >=, ==, !=
    value: float


@dataclass
class ScreenerResult:
    """스크리닝 결과 항목"""
    symbol: str
    name: str
    market: str
    per: float | None = None
    pbr: float | None = None
    roe: float | None = None
    eps: float | None = None
    bps: float | None = None
    market_cap: float = 0
    dividend_yield: float | None = None
    operating_margin: float | None = None
    sector: str = ""
    extra: dict = field(default_factory=dict)


# 연산자 매핑
_OPS = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
}


class ScreenerEngine:
    """팩터 기반 종목 스크리닝 엔진"""

    def __init__(self):
        self._providers = {
            "krx": KRXProvider(),
            "us": USProvider(),
            "crypto": CryptoProvider(),
        }

    async def screen(
        self,
        market: str,
        conditions: list[ScreenerCondition],
        sort_by: str = "market_cap",
        sort_desc: bool = True,
        limit: int = 50,
    ) -> list[ScreenerResult]:
        """
        팩터 기반 종목 스크리닝 실행.

        Args:
            market: 시장 코드 (krx, us, crypto)
            conditions: 스크리닝 조건 리스트
            sort_by: 정렬 기준 팩터
            sort_desc: 내림차순 여부
            limit: 최대 결과 수

        Returns:
            필터링된 종목 리스트
        """
        provider = self._providers.get(market)
        if not provider:
            raise ValueError(f"지원하지 않는 시장: {market}")

        # 1. 전체 종목 목록 가져오기
        tickers = await provider.get_tickers()

        import asyncio

        # 2. 각 종목의 펀더멘털 데이터 병렬 수집 + 필터링
        results: list[ScreenerResult] = []
        sem = asyncio.Semaphore(15)

        async def _process_ticker(ticker):
            async with sem:
                try:
                    fundamental = await provider.get_fundamental(ticker.symbol)
                    res = self._to_result(ticker, fundamental)
                    if self._matches_conditions(res, conditions):
                        return res
                except Exception:
                    pass
                return None

        # 상위 종목 중심 병렬 조회
        target_tickers = tickers[:100]
        processed = await asyncio.gather(*[_process_ticker(t) for t in target_tickers], return_exceptions=True)
        for item in processed:
            if isinstance(item, ScreenerResult):
                results.append(item)

        # 4. 정렬
        results.sort(
            key=lambda r: getattr(r, sort_by, 0) or 0,
            reverse=sort_desc,
        )

        # 5. 결과 수 제한
        return results[:limit]

    def _to_result(self, ticker, fundamental: FundamentalData) -> ScreenerResult:
        """AssetInfo + FundamentalData를 ScreenerResult로 변환"""
        return ScreenerResult(
            symbol=ticker.symbol,
            name=ticker.name,
            market=ticker.market.value,
            per=fundamental.per,
            pbr=fundamental.pbr,
            roe=fundamental.roe,
            eps=fundamental.eps,
            bps=fundamental.bps,
            market_cap=ticker.market_cap,
            dividend_yield=fundamental.dividend_yield,
            operating_margin=fundamental.operating_margin,
            sector=ticker.sector,
        )

    def _matches_conditions(
        self, result: ScreenerResult, conditions: list[ScreenerCondition]
    ) -> bool:
        """결과가 모든 조건을 만족하는지 확인"""
        for cond in conditions:
            value = getattr(result, cond.factor, None)
            if value is None:
                return False  # 데이터가 없으면 필터 아웃

            op_func = _OPS.get(cond.operator)
            if not op_func:
                continue

            if not op_func(value, cond.value):
                return False

        return True
