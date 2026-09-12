"""
Modelin - 미국 주식 데이터 프로바이더

yfinance를 사용하여 미국 주식 데이터를 수집합니다.
"""
import asyncio
from functools import partial

import pandas as pd
import yfinance as yf

from data.providers.base import (
    AssetInfo,
    BaseProvider,
    FundamentalData,
    Market,
)
from data.cache import cache


# 주요 미국 주식 목록 (전체 목록은 별도 API 필요)
# 실제 운영 시 Supabase에 종목 마스터 테이블 관리
_POPULAR_US_TICKERS = [
    ("AAPL", "Apple Inc."), ("MSFT", "Microsoft Corp."),
    ("SPCX", "Space Exploration Technologies Corp."),
    ("GOOGL", "Alphabet Inc."), ("AMZN", "Amazon.com Inc."),
    ("NVDA", "NVIDIA Corp."), ("META", "Meta Platforms Inc."),
    ("TSLA", "Tesla Inc."), ("BRK-B", "Berkshire Hathaway"),
    ("JPM", "JPMorgan Chase"), ("V", "Visa Inc."),
    ("JNJ", "Johnson & Johnson"), ("WMT", "Walmart Inc."),
    ("PG", "Procter & Gamble"), ("MA", "Mastercard Inc."),
    ("UNH", "UnitedHealth Group"), ("HD", "Home Depot"),
    ("DIS", "Walt Disney"), ("PYPL", "PayPal Holdings"),
    ("NFLX", "Netflix Inc."), ("ADBE", "Adobe Inc."),
    ("CRM", "Salesforce Inc."), ("INTC", "Intel Corp."),
    ("AMD", "AMD Inc."), ("QCOM", "Qualcomm Inc."),
    ("T", "AT&T Inc."), ("VZ", "Verizon"),
    ("PFE", "Pfizer Inc."), ("KO", "Coca-Cola Co."),
    ("PEP", "PepsiCo Inc."), ("MRK", "Merck & Co."),
    ("COST", "Costco Wholesale"), ("ABBV", "AbbVie Inc."),
    ("AVGO", "Broadcom Inc."), ("TMO", "Thermo Fisher"),
    ("NKE", "Nike Inc."), ("ACN", "Accenture plc"),
    ("LLY", "Eli Lilly"), ("MCD", "McDonald's Corp."),
    ("TXN", "Texas Instruments"), ("UPS", "United Parcel Service"),
    ("BA", "Boeing Co."), ("CAT", "Caterpillar Inc."),
    ("GS", "Goldman Sachs"), ("MS", "Morgan Stanley"),
    ("SPY", "SPDR S&P 500 ETF"), ("QQQ", "Invesco QQQ Trust"),
    ("IWM", "iShares Russell 2000"), ("VOO", "Vanguard S&P 500"),
    ("VTI", "Vanguard Total Market"), ("ARKK", "ARK Innovation ETF"),
]


class USProvider(BaseProvider):
    """미국 주식 데이터 프로바이더 (yfinance 기반)"""

    @property
    def market(self) -> Market:
        return Market.US

    async def _run_sync(self, func, *args, **kwargs):
        """동기 함수를 비동기로 실행"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def search(self, query: str) -> list[AssetInfo]:
        """종목 검색"""
        cache_key = f"us_search_{query}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        query_upper = query.upper()
        query_lower = query.lower()

        # 로컬 목록에서 먼저 검색
        results = [
            AssetInfo(symbol=sym, name=name, market=Market.US, currency="USD")
            for sym, name in _POPULAR_US_TICKERS
            if query_upper in sym or query_lower in name.lower()
        ]

        # yfinance로 추가 검색 시도
        if not results:
            try:
                ticker = yf.Ticker(query_upper)
                info = ticker.info
                if info and info.get("shortName"):
                    results.append(AssetInfo(
                        symbol=query_upper,
                        name=info.get("shortName", query_upper),
                        market=Market.US,
                        sector=info.get("sector", ""),
                        market_cap=info.get("marketCap", 0),
                        currency="USD",
                    ))
            except Exception:
                pass

        cache.set(cache_key, results, ttl=600)
        return results

    async def get_ohlcv(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """OHLCV 데이터"""
        cache_key = f"us_ohlcv_{symbol}_{start_date}_{end_date}_{interval}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        # yfinance 인터벌 매핑
        interval_map = {
            "1m": "1m", "5m": "5m", "15m": "15m",
            "1h": "1h", "1d": "1d", "1w": "1wk", "1M": "1mo",
        }
        yf_interval = interval_map.get(interval, "1d")

        # 날짜 형식 통일
        start = start_date.replace(".", "-") if "." in start_date else start_date
        end = end_date.replace(".", "-") if "." in end_date else end_date

        if len(start) == 8:  # YYYYMMDD -> YYYY-MM-DD
            start = f"{start[:4]}-{start[4:6]}-{start[6:]}"
        if len(end) == 8:
            end = f"{end[:4]}-{end[4:6]}-{end[6:]}"

        def _fetch():
            ticker = yf.Ticker(symbol)
            return ticker.history(start=start, end=end, interval=yf_interval)

        df = await self._run_sync(_fetch)

        if df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        # 컬럼명 소문자 통일
        df.columns = [c.lower() for c in df.columns]
        cols = ["open", "high", "low", "close", "volume"]
        existing_cols = [c for c in cols if c in df.columns]
        df = df[existing_cols]
        df.index.name = "date"

        cache.set(cache_key, df, ttl=300)
        return df

    async def get_info(self, symbol: str) -> AssetInfo:
        """종목 기본 정보"""
        cache_key = f"us_info_{symbol}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        def _fetch():
            ticker = yf.Ticker(symbol)
            return ticker.info

        try:
            info = await self._run_sync(_fetch)
            asset = AssetInfo(
                symbol=symbol,
                name=info.get("shortName", info.get("longName", symbol)),
                market=Market.US,
                sector=info.get("sector", ""),
                market_cap=info.get("marketCap", 0),
                currency="USD",
                extra={
                    "industry": info.get("industry", ""),
                    "country": info.get("country", ""),
                    "website": info.get("website", ""),
                    "description": info.get("longBusinessSummary", "")[:200],
                },
            )
        except Exception:
            asset = AssetInfo(symbol=symbol, name=symbol, market=Market.US, currency="USD")

        cache.set(cache_key, asset, ttl=3600)
        return asset

    async def get_fundamental(self, symbol: str) -> FundamentalData:
        """펀더멘털 데이터"""
        cache_key = f"us_fundamental_{symbol}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        def _fetch():
            ticker = yf.Ticker(symbol)
            return ticker.info

        try:
            info = await self._run_sync(_fetch)
            data = FundamentalData(
                symbol=symbol,
                per=info.get("trailingPE"),
                pbr=info.get("priceToBook"),
                psr=info.get("priceToSalesTrailing12Months"),
                eps=info.get("trailingEps"),
                bps=info.get("bookValue"),
                roe=info.get("returnOnEquity"),
                roa=info.get("returnOnAssets"),
                dividend_yield=info.get("dividendYield"),
                operating_margin=info.get("operatingMargins"),
                extra={
                    "revenue": info.get("totalRevenue"),
                    "net_income": info.get("netIncomeToCommon"),
                    "free_cashflow": info.get("freeCashflow"),
                    "beta": info.get("beta"),
                },
            )
        except Exception:
            data = FundamentalData(symbol=symbol)

        cache.set(cache_key, data, ttl=3600)
        return data

    async def get_tickers(self) -> list[AssetInfo]:
        """주요 미국 주식 목록"""
        return [
            AssetInfo(symbol=sym, name=name, market=Market.US, currency="USD")
            for sym, name in _POPULAR_US_TICKERS
        ]
