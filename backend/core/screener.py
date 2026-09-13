"""
Modelin - 팩터 기반 종목 스크리닝 엔진
"""
import operator
from dataclasses import dataclass, field



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
        pass

    def screen_records(
        self, records, conditions: list[ScreenerCondition],
        sort_by: str = "market_cap", sort_desc: bool = True, limit: int = 50,
    ) -> list[ScreenerResult]:
        """Filter and rank already collected ticker/fundamental records."""
        results: list[ScreenerResult] = []
        for ticker, fundamental in records:
            result = self._to_result(ticker, fundamental)
            if self._matches_conditions(result, conditions):
                results.append(result)
        results.sort(
            key=lambda r: getattr(r, sort_by, 0) or 0,
            reverse=sort_desc,
        )
        return results[:limit]

    def _to_result(self, ticker, fundamental) -> ScreenerResult:
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
