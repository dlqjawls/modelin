"""
Modelin - 기술적 분석 모듈

ta 라이브러리를 활용한 기술적 지표 계산.
"""
import pandas as pd

try:
    import ta as ta_lib
    HAS_TA = True
except ImportError:
    HAS_TA = False


class TechnicalAnalysis:
    """기술적 분석 엔진"""

    @staticmethod
    def add_indicators(
        df: pd.DataFrame,
        indicators: list[str] | None = None,
    ) -> pd.DataFrame:
        """
        OHLCV DataFrame에 기술적 지표를 추가합니다.

        Args:
            df: OHLCV DataFrame (columns: open, high, low, close, volume)
            indicators: 추가할 지표 리스트. None이면 기본 지표 세트 추가.

        Returns:
            지표가 추가된 DataFrame
        """
        if df.empty:
            return df

        result = df.copy()

        if not HAS_TA:
            return TechnicalAnalysis._manual_indicators(result)

        default_indicators = indicators or [
            "sma_20", "sma_60", "sma_120",
            "ema_12", "ema_26",
            "rsi_14",
            "macd",
            "bbands_20",
            "atr_14",
            "obv",
        ]

        for ind in default_indicators:
            try:
                if ind.startswith("sma_"):
                    period = int(ind.split("_")[1])
                    result[ind] = ta_lib.trend.sma_indicator(result["close"], window=period)
                elif ind.startswith("ema_"):
                    period = int(ind.split("_")[1])
                    result[ind] = ta_lib.trend.ema_indicator(result["close"], window=period)
                elif ind.startswith("rsi_"):
                    period = int(ind.split("_")[1])
                    result[ind] = ta_lib.momentum.rsi(result["close"], window=period)
                elif ind == "macd":
                    macd_obj = ta_lib.trend.MACD(result["close"])
                    result["macd"] = macd_obj.macd()
                    result["macd_signal"] = macd_obj.macd_signal()
                    result["macd_hist"] = macd_obj.macd_diff()
                elif ind.startswith("bbands_"):
                    period = int(ind.split("_")[1])
                    bb = ta_lib.volatility.BollingerBands(result["close"], window=period)
                    result["bb_upper"] = bb.bollinger_hband()
                    result["bb_middle"] = bb.bollinger_mavg()
                    result["bb_lower"] = bb.bollinger_lband()
                elif ind.startswith("atr_"):
                    period = int(ind.split("_")[1])
                    result[ind] = ta_lib.volatility.average_true_range(
                        result["high"], result["low"], result["close"], window=period
                    )
                elif ind == "obv":
                    result["obv"] = ta_lib.volume.on_balance_volume(
                        result["close"], result["volume"]
                    )
                elif ind == "vwap":
                    result["vwap"] = ta_lib.volume.volume_weighted_average_price(
                        result["high"], result["low"], result["close"], result["volume"]
                    )
                elif ind.startswith("stoch_"):
                    period = int(ind.split("_")[1])
                    stoch = ta_lib.momentum.StochasticOscillator(
                        result["high"], result["low"], result["close"], window=period
                    )
                    result["stoch_k"] = stoch.stoch()
                    result["stoch_d"] = stoch.stoch_signal()
                elif ind.startswith("adx_"):
                    period = int(ind.split("_")[1])
                    result[ind] = ta_lib.trend.adx(
                        result["high"], result["low"], result["close"], window=period
                    )
                elif ind.startswith("cci_"):
                    period = int(ind.split("_")[1])
                    result[ind] = ta_lib.trend.cci(
                        result["high"], result["low"], result["close"], window=period
                    )
                elif ind.startswith("willr_"):
                    period = int(ind.split("_")[1])
                    result[ind] = ta_lib.momentum.williams_r(
                        result["high"], result["low"], result["close"], lbp=period
                    )
            except Exception:
                continue

        return result

    @staticmethod
    def _manual_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """ta 라이브러리 없을 때 수동 계산 (기본 지표만)"""
        result = df.copy()

        # SMA
        result["sma_20"] = result["close"].rolling(20).mean()
        result["sma_60"] = result["close"].rolling(60).mean()
        result["sma_120"] = result["close"].rolling(120).mean()

        # EMA
        result["ema_12"] = result["close"].ewm(span=12).mean()
        result["ema_26"] = result["close"].ewm(span=26).mean()

        # RSI
        delta = result["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        result["rsi_14"] = 100 - (100 / (1 + rs))

        # MACD
        ema12 = result["close"].ewm(span=12).mean()
        ema26 = result["close"].ewm(span=26).mean()
        result["macd"] = ema12 - ema26
        result["macd_signal"] = result["macd"].ewm(span=9).mean()
        result["macd_hist"] = result["macd"] - result["macd_signal"]

        # Bollinger Bands
        sma20 = result["close"].rolling(20).mean()
        std20 = result["close"].rolling(20).std()
        result["bb_upper"] = sma20 + 2 * std20
        result["bb_middle"] = sma20
        result["bb_lower"] = sma20 - 2 * std20

        return result
