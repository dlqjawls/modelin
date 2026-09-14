"""Read-only current quote queries for supported KIS stock markets."""


class QuoteService:
    def __init__(self, broker_factory):
        self.broker_factory = broker_factory

    async def quote(self, market: str, symbol: str):
        market = market.lower()
        if market not in {"krx", "us"}:
            raise ValueError("현재가 조회는 KIS 국내·해외 주식만 지원합니다.")
        if not symbol.strip():
            raise ValueError("종목코드가 필요합니다.")
        return await self.broker_factory(market).quote(symbol.strip())

    async def account_snapshot(self, market: str = "krx"):
        market = market.lower()
        if market not in {"krx", "us"}:
            raise ValueError("계좌 조회는 KIS 국내·해외 주식만 지원합니다.")
        return await self.broker_factory(market).account_snapshot()
