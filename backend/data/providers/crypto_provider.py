"""
Modelin - 암호화폐 데이터 프로바이더

ccxt를 사용하여 Upbit 암호화폐 데이터를 수집합니다.
"""
import asyncio
from functools import partial
from datetime import datetime

import pandas as pd
import ccxt

from data.providers.base import (
    AssetInfo,
    BaseProvider,
    FundamentalData,
    Market,
)
from data.cache import cache
from config import settings


class CryptoProvider(BaseProvider):
    """암호화폐 데이터 프로바이더 (ccxt/Upbit 기반)"""

    def __init__(self):
        self._exchange: ccxt.upbit | None = None

    def _get_exchange(self) -> ccxt.upbit:
        """Upbit 거래소 인스턴스"""
        if self._exchange is None:
            config = {"enableRateLimit": True}
            if settings.UPBIT_ACCESS_KEY and settings.UPBIT_SECRET_KEY:
                config["apiKey"] = settings.UPBIT_ACCESS_KEY
                config["secret"] = settings.UPBIT_SECRET_KEY
            self._exchange = ccxt.upbit(config)
        return self._exchange

    @property
    def market(self) -> Market:
        return Market.CRYPTO

    async def _run_sync(self, func, *args, **kwargs):
        """동기 함수를 비동기로 실행"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def search(self, query: str) -> list[AssetInfo]:
        """종목 검색"""
        cache_key = f"crypto_search_{query}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        tickers = await self.get_tickers()
        query_upper = query.upper()

        results = [
            t for t in tickers
            if query_upper in t.symbol.upper() or query_upper in t.name.upper()
        ]

        cache.set(cache_key, results, ttl=300)
        return results

    async def get_ohlcv(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """OHLCV 데이터"""
        cache_key = f"crypto_ohlcv_{symbol}_{start_date}_{end_date}_{interval}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        exchange = self._get_exchange()

        # ccxt 타임프레임 매핑
        timeframe_map = {
            "1m": "1m", "5m": "5m", "15m": "15m",
            "1h": "1h", "1d": "1d", "1w": "1w", "1M": "1M",
        }
        timeframe = timeframe_map.get(interval, "1d")

        # 날짜를 밀리초 타임스탬프로 변환
        start_str = start_date.replace("-", "")
        if len(start_str) == 8:
            start_dt = datetime.strptime(start_str, "%Y%m%d")
        else:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        since = int(start_dt.timestamp() * 1000)

        def _fetch():
            all_ohlcv = []
            current_since = since
            while True:
                bars = exchange.fetch_ohlcv(
                    symbol, timeframe=timeframe, since=current_since, limit=200
                )
                if not bars:
                    break
                all_ohlcv.extend(bars)
                current_since = bars[-1][0] + 1

                # 종료일 체크
                end_str = end_date.replace("-", "")
                if len(end_str) == 8:
                    end_dt = datetime.strptime(end_str, "%Y%m%d")
                else:
                    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

                if bars[-1][0] >= int(end_dt.timestamp() * 1000):
                    break
                if len(bars) < 200:
                    break
            return all_ohlcv

        ohlcv_data = await self._run_sync(_fetch)

        if not ohlcv_data:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        df = pd.DataFrame(
            ohlcv_data,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df.set_index("date").drop(columns=["timestamp"])

        # 종료일까지만 필터
        end_str = end_date.replace("-", "")
        if len(end_str) == 8:
            end_filter = f"{end_str[:4]}-{end_str[4:6]}-{end_str[6:]}"
        else:
            end_filter = end_date
        df = df[df.index <= end_filter]

        cache.set(cache_key, df, ttl=60)  # 암호화폐는 짧은 TTL
        return df

    async def get_info(self, symbol: str) -> AssetInfo:
        """종목 기본 정보"""
        cache_key = f"crypto_info_{symbol}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        exchange = self._get_exchange()

        def _fetch():
            exchange.load_markets()
            return exchange.markets.get(symbol)

        market_info = await self._run_sync(_fetch)

        if market_info:
            base = market_info.get("base", symbol.split("/")[0])
            quote = market_info.get("quote", "KRW")
            info = AssetInfo(
                symbol=symbol,
                name=base,
                market=Market.CRYPTO,
                currency=quote,
                extra={
                    "active": market_info.get("active", True),
                    "precision": market_info.get("precision", {}),
                },
            )
        else:
            info = AssetInfo(
                symbol=symbol,
                name=symbol,
                market=Market.CRYPTO,
                currency="KRW",
            )

        cache.set(cache_key, info, ttl=3600)
        return info

    async def get_fundamental(self, symbol: str) -> FundamentalData:
        """암호화폐는 전통적 펀더멘털 데이터가 없으므로 빈 데이터 반환"""
        return FundamentalData(symbol=symbol)

    async def get_tickers(self) -> list[AssetInfo]:
        """Upbit 거래 가능 종목 목록"""
        cache_key = "crypto_tickers"
        cached = cache.get(cache_key)
        if cached:
            return cached

        exchange = self._get_exchange()

        def _fetch():
            exchange.load_markets()
            return exchange.markets

        markets = await self._run_sync(_fetch)

        tickers = []
        for symbol, info in markets.items():
            if info.get("active", False) and info.get("quote") == "KRW":
                tickers.append(AssetInfo(
                    symbol=symbol,
                    name=info.get("base", symbol),
                    market=Market.CRYPTO,
                    currency="KRW",
                ))

        cache.set(cache_key, tickers, ttl=3600)
        return tickers

    async def get_ticker_price(self, symbol: str) -> dict:
        """현재 시세 조회"""
        exchange = self._get_exchange()

        def _fetch():
            return exchange.fetch_ticker(symbol)

        ticker = await self._run_sync(_fetch)
        return {
            "symbol": symbol,
            "last": ticker.get("last"),
            "bid": ticker.get("bid"),
            "ask": ticker.get("ask"),
            "high": ticker.get("high"),
            "low": ticker.get("low"),
            "volume": ticker.get("baseVolume"),
            "change_pct": ticker.get("percentage"),
            "timestamp": ticker.get("timestamp"),
        }
