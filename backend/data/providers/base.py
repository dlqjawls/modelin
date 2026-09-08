"""
Modelin - 데이터 프로바이더 베이스 클래스

모든 시장별 프로바이더가 구현해야 할 통합 인터페이스를 정의합니다.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import pandas as pd


class Market(str, Enum):
    """지원하는 시장 종류"""
    KRX = "krx"           # 한국 주식
    US = "us"             # 미국 주식
    CRYPTO = "crypto"     # 암호화폐


@dataclass
class AssetInfo:
    """종목/자산 기본 정보"""
    symbol: str           # 종목 코드 (예: "005930", "AAPL", "BTC/KRW")
    name: str             # 종목명 (예: "삼성전자", "Apple Inc.", "Bitcoin")
    market: Market        # 시장 구분
    sector: str = ""      # 섹터/업종
    market_cap: float = 0 # 시가총액
    currency: str = "KRW" # 통화
    extra: dict = field(default_factory=dict)  # 추가 메타데이터


@dataclass
class FundamentalData:
    """재무/펀더멘털 데이터"""
    symbol: str
    per: float | None = None       # 주가수익비율
    pbr: float | None = None       # 주가순자산비율
    psr: float | None = None       # 주가매출비율
    eps: float | None = None       # 주당순이익
    bps: float | None = None       # 주당순자산
    roe: float | None = None       # 자기자본이익률
    roa: float | None = None       # 총자산이익률
    dividend_yield: float | None = None  # 배당수익률
    operating_margin: float | None = None  # 영업이익률
    debt_ratio: float | None = None  # 부채비율
    extra: dict = field(default_factory=dict)


class BaseProvider(ABC):
    """
    데이터 프로바이더 추상 베이스 클래스.

    모든 시장별 프로바이더(KRX, US, Crypto)는 이 클래스를 상속하여
    동일한 인터페이스를 구현합니다.
    """

    @property
    @abstractmethod
    def market(self) -> Market:
        """이 프로바이더가 담당하는 시장"""
        ...

    @abstractmethod
    async def search(self, query: str) -> list[AssetInfo]:
        """
        종목 검색. 종목명 또는 코드로 검색합니다.

        Args:
            query: 검색어 (종목명 또는 코드)

        Returns:
            매칭되는 종목 정보 리스트
        """
        ...

    @abstractmethod
    async def get_ohlcv(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """
        OHLCV (시가, 고가, 저가, 종가, 거래량) 데이터를 가져옵니다.

        Args:
            symbol: 종목 코드
            start_date: 시작일 (YYYY-MM-DD 또는 YYYYMMDD)
            end_date: 종료일
            interval: 봉 간격 ('1m', '5m', '15m', '1h', '1d', '1w', '1M')

        Returns:
            DataFrame - columns: [open, high, low, close, volume]
                        index: DatetimeIndex
        """
        ...

    @abstractmethod
    async def get_info(self, symbol: str) -> AssetInfo:
        """종목 기본 정보를 가져옵니다."""
        ...

    @abstractmethod
    async def get_fundamental(self, symbol: str) -> FundamentalData:
        """재무/펀더멘털 데이터를 가져옵니다."""
        ...

    @abstractmethod
    async def get_tickers(self) -> list[AssetInfo]:
        """전체 종목 목록을 가져옵니다."""
        ...
