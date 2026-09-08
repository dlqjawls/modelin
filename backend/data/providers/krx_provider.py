"""
Modelin - 한국 주식(KRX) 데이터 프로바이더

FinanceDataReader 및 Naver Finance / yfinance를 활용한 안정적인 실시간 데이터 수집
"""
import asyncio
from datetime import datetime, timedelta
from functools import partial

import pandas as pd
import requests
import FinanceDataReader as fdr

from data.providers.base import (
    AssetInfo,
    BaseProvider,
    FundamentalData,
    Market,
)
from data.cache import cache

# 기본 주요 종목 리스트 (네트워크 장애 대비 fallback)
_DEFAULT_KRX_TICKERS = [
    ("005930", "삼성전자", "KOSPI"),
    ("000660", "SK하이닉스", "KOSPI"),
    ("373220", "LG에너지솔루션", "KOSPI"),
    ("207940", "삼성바이오로직스", "KOSPI"),
    ("005380", "현대차", "KOSPI"),
    ("000270", "기아", "KOSPI"),
    ("068270", "셀트리온", "KOSPI"),
    ("105560", "KB금융", "KOSPI"),
    ("055550", "신한지주", "KOSPI"),
    ("035420", "NAVER", "KOSPI"),
    ("035720", "카카오", "KOSPI"),
    ("006400", "삼성SDI", "KOSPI"),
    ("051910", "LG화학", "KOSPI"),
    ("012330", "현대모비스", "KOSPI"),
    ("028260", "삼성물산", "KOSPI"),
    ("086520", "에코프로", "KOSDAQ"),
    ("247540", "에코프로비엠", "KOSDAQ"),
    ("091990", "셀트리온헬스케어", "KOSDAQ"),
    ("196170", "알테오젠", "KOSDAQ"),
    ("058470", "리노공업", "KOSDAQ"),
]


class KRXProvider(BaseProvider):
    """한국 주식 데이터 프로바이더 (FinanceDataReader + Naver Finance)"""

    @property
    def market(self) -> Market:
        return Market.KRX

    async def _run_sync(self, func, *args, **kwargs):
        """동기 함수를 비동기 executor에서 실행"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def search(self, query: str) -> list[AssetInfo]:
        """종목 검색 (종목명 또는 코드)"""
        cache_key = f"krx_search_{query}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        tickers = await self.get_tickers()
        query_lower = query.lower().strip()

        results = [
            t for t in tickers
            if query_lower in t.name.lower() or query_lower in t.symbol.lower()
        ]

        cache.set(cache_key, results, ttl=600)
        return results

    async def get_ohlcv(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """OHLCV 데이터 (일봉/주봉/월봉)"""
        cache_key = f"krx_ohlcv_{symbol}_{start_date}_{end_date}_{interval}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        def _fetch_fdr():
            df = fdr.DataReader(symbol, start_date, end_date)
            if df.empty:
                return pd.DataFrame()
            df.columns = [c.lower() for c in df.columns]
            rename_map = {
                "시가": "open",
                "고가": "high",
                "저가": "low",
                "종가": "close",
                "거래량": "volume",
            }
            df = df.rename(columns=rename_map)
            cols = ["open", "high", "low", "close", "volume"]
            existing_cols = [c for c in cols if c in df.columns]
            df = df[existing_cols]
            df.index.name = "date"
            return df

        try:
            df = await self._run_sync(_fetch_fdr)
        except Exception:
            # Fallback: yfinance
            try:
                import yfinance as yf
                yf_symbol = f"{symbol}.KS" if not symbol.endswith(".KS") and not symbol.endswith(".KQ") else symbol
                def _fetch_yf():
                    ticker = yf.Ticker(yf_symbol)
                    hist = ticker.history(start=start_date, end=end_date)
                    if hist.empty:
                        return pd.DataFrame()
                    hist.columns = [c.lower() for c in hist.columns]
                    cols = ["open", "high", "low", "close", "volume"]
                    existing = [c for c in cols if c in hist.columns]
                    return hist[existing]
                df = await self._run_sync(_fetch_yf)
            except Exception:
                df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        if df.empty:
            df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        cache.set(cache_key, df, ttl=300)
        return df

    async def get_info(self, symbol: str) -> AssetInfo:
        """종목 기본 정보"""
        cache_key = f"krx_info_{symbol}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        # Naver finance integration API로 빠른 정보 조회
        def _fetch_naver_info():
            url = f"https://m.stock.naver.com/api/stock/{symbol}/integration"
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json()
                name = data.get("stockName", symbol)
                # 시가총액 추출
                marcap = 0
                for item in data.get("totalInfos", []):
                    if item.get("code") == "marketValue":
                        val_str = item.get("value", "").replace(",", "").replace(" ", "")
                        # e.g. "1조 5,000억" 형식 처리
                        marcap = 0
                return AssetInfo(
                    symbol=symbol,
                    name=name,
                    market=Market.KRX,
                    currency="KRW",
                )
            return None

        try:
            info = await self._run_sync(_fetch_naver_info)
        except Exception:
            info = None

        if not info:
            # fallback
            found = [t for t in _DEFAULT_KRX_TICKERS if t[0] == symbol]
            name = found[0][1] if found else symbol
            info = AssetInfo(
                symbol=symbol,
                name=name,
                market=Market.KRX,
                currency="KRW",
            )

        cache.set(cache_key, info, ttl=3600)
        return info

    async def get_fundamental(self, symbol: str) -> FundamentalData:
        """펀더멘털 데이터 (PER, PBR, EPS, BPS, 배당수익률 등)"""
        cache_key = f"krx_fundamental_{symbol}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        def _fetch_fundamental():
            url = f"https://m.stock.naver.com/api/stock/{symbol}/integration"
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=headers, timeout=5)
            fund = FundamentalData(symbol=symbol)
            if r.status_code == 200:
                data = r.json()
                for item in data.get("totalInfos", []):
                    code = item.get("code")
                    val = item.get("value", "")
                    clean_val = val.replace(",", "").replace("배", "").replace("%", "").replace("원", "").strip()
                    try:
                        fval = float(clean_val)
                    except ValueError:
                        continue

                    if code == "per":
                        fund.per = fval
                    elif code == "pbr":
                        fund.pbr = fval
                    elif code == "eps":
                        fund.eps = fval
                    elif code == "bps":
                        fund.bps = fval
                    elif code == "dividendYieldRatio":
                        fund.dividend_yield = fval
                # ROE 추정: PBR / PER * 100
                if fund.pbr and fund.per and fund.per > 0:
                    fund.roe = round((fund.pbr / fund.per) * 100, 2)
            return fund

        try:
            data = await self._run_sync(_fetch_fundamental)
        except Exception:
            data = FundamentalData(symbol=symbol)

        cache.set(cache_key, data, ttl=3600)
        return data

    async def get_tickers(self) -> list[AssetInfo]:
        """KRX 주요 종목 목록"""
        cache_key = "krx_tickers"
        cached = cache.get(cache_key)
        if cached:
            return cached

        def _fetch_tickers():
            tickers: list[AssetInfo] = []
            headers = {"User-Agent": "Mozilla/5.0"}
            for market_name, count in [("KOSPI", 100), ("KOSDAQ", 50)]:
                try:
                    url = f"https://m.stock.naver.com/api/stocks/marketValue/{market_name}?page=1&pageSize={count}"
                    r = requests.get(url, headers=headers, timeout=5)
                    if r.status_code == 200:
                        stocks = r.json().get("stocks", [])
                        for s in stocks:
                            tickers.append(AssetInfo(
                                symbol=s.get("itemCode", ""),
                                name=s.get("stockName", ""),
                                market=Market.KRX,
                                sector=market_name,
                                market_cap=float(s.get("marketValueRaw", 0)),
                                currency="KRW",
                            ))
                except Exception:
                    pass

            if not tickers:
                # Fallback to default list
                for sym, nm, sec in _DEFAULT_KRX_TICKERS:
                    tickers.append(AssetInfo(
                        symbol=sym,
                        name=nm,
                        market=Market.KRX,
                        sector=sec,
                        currency="KRW",
                    ))
            return tickers

        try:
            tickers = await self._run_sync(_fetch_tickers)
        except Exception:
            tickers = [
                AssetInfo(symbol=s, name=n, market=Market.KRX, sector=sec, currency="KRW")
                for s, n, sec in _DEFAULT_KRX_TICKERS
            ]

        cache.set(cache_key, tickers, ttl=86400)
        return tickers
