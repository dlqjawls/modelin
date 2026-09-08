"""
Modelin - Vectorized 백테스팅 엔진

벡터화 연산을 사용한 고속 백테스팅 엔진.
"""
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from data.providers.krx_provider import KRXProvider
from data.providers.us_provider import USProvider
from data.providers.crypto_provider import CryptoProvider


@dataclass
class BacktestConfig:
    """백테스팅 설정"""
    symbols: list[str]
    market: str = "krx"
    start_date: str = ""
    end_date: str = ""
    strategy: dict = field(default_factory=dict)
    initial_capital: float = 10_000_000
    commission_rate: float = 0.00015   # 0.015% (한국 주식 기준)
    slippage_rate: float = 0.001       # 0.1%
    rebalance_period: str = "1M"       # 리밸런싱 주기


@dataclass
class BacktestResult:
    """백테스팅 결과"""
    total_return: float = 0.0
    cagr: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0
    total_trades: int = 0
    equity_curve: list[dict] = field(default_factory=list)
    monthly_returns: list[dict] = field(default_factory=list)
    benchmark_comparison: dict | None = None


class BacktestEngine:
    """Vectorized 백테스팅 엔진"""

    def __init__(self):
        self._providers = {
            "krx": KRXProvider(),
            "us": USProvider(),
            "crypto": CryptoProvider(),
        }

    async def run(self, config: BacktestConfig) -> BacktestResult:
        """
        백테스팅 실행.

        Args:
            config: 백테스팅 설정

        Returns:
            BacktestResult: 백테스팅 결과
        """
        provider = self._providers.get(config.market)
        if not provider:
            raise ValueError(f"지원하지 않는 시장: {config.market}")

        # 1. 가격 데이터 수집
        price_data = {}
        for symbol in config.symbols:
            df = await provider.get_ohlcv(
                symbol, config.start_date, config.end_date, "1d"
            )
            if not df.empty:
                price_data[symbol] = df

        if not price_data:
            raise ValueError("사용 가능한 가격 데이터가 없습니다.")

        # 2. 종가 기준 통합 DataFrame
        close_prices = pd.DataFrame({
            symbol: df["close"] for symbol, df in price_data.items()
        })
        close_prices = close_prices.dropna()

        if close_prices.empty:
            raise ValueError("공통 기간의 데이터가 없습니다.")

        # 3. 전략에 따른 시그널 생성
        strategy_type = config.strategy.get("type", "equal_weight")
        signals = self._generate_signals(close_prices, config.strategy)

        # 4. 벡터화 백테스팅 실행
        result = self._vectorized_backtest(
            close_prices, signals, config
        )

        return result

    def _generate_signals(
        self, prices: pd.DataFrame, strategy: dict
    ) -> pd.DataFrame:
        """
        전략에 따른 매매 시그널 생성.

        Args:
            prices: 종가 DataFrame
            strategy: 전략 설정

        Returns:
            시그널 DataFrame (1: 매수, -1: 매도, 0: 홀드)
        """
        strategy_type = strategy.get("type", "equal_weight")

        if strategy_type == "equal_weight":
            # 동일 가중 매수 후 보유
            signals = pd.DataFrame(1, index=prices.index, columns=prices.columns)
            return signals

        elif strategy_type == "momentum":
            # 모멘텀 전략: N일 수익률 기반
            lookback = strategy.get("lookback", 20)
            returns = prices.pct_change(lookback)
            signals = pd.DataFrame(0, index=prices.index, columns=prices.columns)
            signals[returns > 0] = 1
            signals[returns <= 0] = -1
            return signals

        elif strategy_type == "moving_average":
            # 이동평균 크로스오버
            short_window = strategy.get("short_window", 20)
            long_window = strategy.get("long_window", 60)

            signals = pd.DataFrame(0, index=prices.index, columns=prices.columns)
            for col in prices.columns:
                short_ma = prices[col].rolling(window=short_window).mean()
                long_ma = prices[col].rolling(window=long_window).mean()
                signals.loc[short_ma > long_ma, col] = 1
                signals.loc[short_ma <= long_ma, col] = -1
            return signals

        elif strategy_type == "rsi":
            # RSI 전략
            period = strategy.get("period", 14)
            oversold = strategy.get("oversold", 30)
            overbought = strategy.get("overbought", 70)

            signals = pd.DataFrame(0, index=prices.index, columns=prices.columns)
            for col in prices.columns:
                rsi = self._calc_rsi(prices[col], period)
                signals.loc[rsi < oversold, col] = 1
                signals.loc[rsi > overbought, col] = -1
            return signals

        elif strategy_type == "bollinger_bands":
            # 볼린저 밴드 전략
            window = strategy.get("window", 20)
            num_std = strategy.get("num_std", 2)

            signals = pd.DataFrame(0, index=prices.index, columns=prices.columns)
            for col in prices.columns:
                ma = prices[col].rolling(window=window).mean()
                std = prices[col].rolling(window=window).std()
                upper = ma + num_std * std
                lower = ma - num_std * std
                signals.loc[prices[col] < lower, col] = 1   # 하단 돌파 → 매수
                signals.loc[prices[col] > upper, col] = -1  # 상단 돌파 → 매도
            return signals

        else:
            # 기본: 동일 가중
            return pd.DataFrame(1, index=prices.index, columns=prices.columns)

    def _calc_rsi(self, series: pd.Series, period: int = 14) -> pd.Series:
        """RSI 계산"""
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def _vectorized_backtest(
        self,
        prices: pd.DataFrame,
        signals: pd.DataFrame,
        config: BacktestConfig,
    ) -> BacktestResult:
        """
        벡터화 백테스팅 실행.

        수수료와 슬리피지를 반영한 포트폴리오 수익률 계산.
        """
        # 일간 수익률
        daily_returns = prices.pct_change().fillna(0)

        # 시그널 기반 포지션 (1: 롱, 0: 미보유)
        positions = signals.clip(lower=0)  # 매도 시그널은 포지션 0으로

        # 포지션 변경 시점 (수수료 발생)
        position_changes = positions.diff().fillna(0).abs()
        transaction_costs = position_changes * (config.commission_rate + config.slippage_rate)

        # 종목별 동일 가중
        n_assets = positions.sum(axis=1).replace(0, 1)
        weights = positions.div(n_assets, axis=0)

        # 포트폴리오 수익률 = 가중 수익률 - 거래비용
        portfolio_returns = (weights * daily_returns).sum(axis=1) - transaction_costs.sum(axis=1)

        # 에퀴티 커브
        equity_curve = (1 + portfolio_returns).cumprod() * config.initial_capital
        equity_list = [
            {"date": str(idx), "value": round(float(val), 0)}
            for idx, val in equity_curve.items()
        ]

        # 성과 지표 계산
        total_return = float(equity_curve.iloc[-1] / config.initial_capital - 1)

        n_days = len(equity_curve)
        n_years = n_days / 252
        cagr = float((equity_curve.iloc[-1] / config.initial_capital) ** (1 / max(n_years, 0.01)) - 1)

        # 샤프 비율 (연율화)
        if portfolio_returns.std() > 0:
            sharpe_ratio = float(
                portfolio_returns.mean() / portfolio_returns.std() * np.sqrt(252)
            )
        else:
            sharpe_ratio = 0.0

        # 소르티노 비율
        downside_returns = portfolio_returns[portfolio_returns < 0]
        if len(downside_returns) > 0 and downside_returns.std() > 0:
            sortino_ratio = float(
                portfolio_returns.mean() / downside_returns.std() * np.sqrt(252)
            )
        else:
            sortino_ratio = 0.0

        # 최대 낙폭 (MDD)
        running_max = equity_curve.cummax()
        drawdown = (equity_curve - running_max) / running_max
        max_drawdown = float(drawdown.min())

        # 승률 & 손익비
        winning_days = portfolio_returns[portfolio_returns > 0]
        losing_days = portfolio_returns[portfolio_returns < 0]
        win_rate = float(len(winning_days) / max(len(winning_days) + len(losing_days), 1))

        avg_win = float(winning_days.mean()) if len(winning_days) > 0 else 0
        avg_loss = float(abs(losing_days.mean())) if len(losing_days) > 0 else 0.0001
        profit_loss_ratio = avg_win / max(avg_loss, 0.0001)

        # 총 거래 횟수
        total_trades = int(position_changes.sum().sum())

        # 월별 수익률
        monthly_equity = equity_curve.resample("ME").last()
        monthly_rets = monthly_equity.pct_change().dropna()
        monthly_returns_list = [
            {"date": str(idx), "return": round(float(val), 4)}
            for idx, val in monthly_rets.items()
        ]

        return BacktestResult(
            total_return=round(total_return, 4),
            cagr=round(cagr, 4),
            sharpe_ratio=round(sharpe_ratio, 2),
            sortino_ratio=round(sortino_ratio, 2),
            max_drawdown=round(max_drawdown, 4),
            win_rate=round(win_rate, 4),
            profit_loss_ratio=round(profit_loss_ratio, 2),
            total_trades=total_trades,
            equity_curve=equity_list,
            monthly_returns=monthly_returns_list,
        )
