"""Application service for price-based portfolio allocation."""
import numpy as np
import pandas as pd


class PortfolioService:
    SUPPORTED_METHODS = {"equal_weight", "inverse_volatility", "min_volatility"}

    def __init__(self, market_data):
        self.market_data = market_data

    async def optimize(self, *, market, symbols, start_date, end_date, method):
        if method == "max_sharpe":
            method = "inverse_volatility"
        if method not in self.SUPPORTED_METHODS:
            raise ValueError("지원 방법: equal_weight, inverse_volatility, min_volatility")
        if not symbols:
            raise ValueError("종목을 하나 이상 입력해주세요.")
        provider = self.market_data.provider(market)
        frames = {}
        for symbol in dict.fromkeys(symbols):
            frame = await provider.get_ohlcv(symbol, start_date, end_date, "1d")
            if not frame.empty and "close" in frame:
                frames[symbol] = frame["close"]
        if not frames:
            raise ValueError("가격 데이터가 없습니다.")
        prices = pd.DataFrame(frames).ffill().dropna(axis=1, how="all")
        returns = prices.pct_change(fill_method=None).dropna(how="all").fillna(0)
        symbols = list(prices.columns)
        if method == "equal_weight":
            raw = np.ones(len(symbols))
        elif method == "inverse_volatility":
            vol = returns.std().replace(0, np.nan).fillna(np.inf).to_numpy()
            raw = 1 / vol
        else:
            cov = returns.cov().to_numpy()
            raw = np.maximum(np.linalg.pinv(cov + np.eye(len(symbols)) * 1e-8) @ np.ones(len(symbols)), 0)
        if not np.isfinite(raw).all() or raw.sum() <= 0:
            raise ValueError("최적화에 충분한 유효 데이터가 없습니다.")
        weights = raw / raw.sum()
        daily = returns.to_numpy() @ weights
        expected_return = float(np.mean(daily) * 252)
        expected_volatility = float(np.std(daily, ddof=1) * np.sqrt(252)) if len(daily) > 1 else 0.0
        return {
            "weights": {s: round(float(w), 8) for s, w in zip(symbols, weights)},
            "expected_return": expected_return,
            "expected_volatility": expected_volatility,
            "sharpe_ratio": expected_return / expected_volatility if expected_volatility else 0.0,
            "efficient_frontier": None,
        }
