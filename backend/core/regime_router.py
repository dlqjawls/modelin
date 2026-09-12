"""Market-regime detection and conservative strategy routing.

News and macro inputs are optional observations. They can restrict risk, but
cannot create an order without a price-based strategy signal.
"""
from dataclasses import dataclass
from typing import Mapping

import pandas as pd


@dataclass(frozen=True)
class Regime:
    name: str
    confidence: float
    risk_multiplier: float
    reasons: tuple[str, ...]


class RegimeDetector:
    def detect(self, close_prices: pd.DataFrame, context: Mapping[str, float] | None = None) -> Regime:
        context = context or {}
        if close_prices.empty or len(close_prices) < 60:
            return Regime("INSUFFICIENT_DATA", 0.0, 0.0, ("NEED_60_BARS",))
        # Absolute prices make a 100,000 KRW asset dominate a 1,000 KRW
        # asset. Normalize each instrument first so the regime represents the
        # cross-sectional market move rather than the price scale.
        normalized = close_prices.astype(float).replace([float("inf"), float("-inf")], pd.NA)
        normalized = normalized.div(normalized.ffill().iloc[0]).replace([float("inf"), float("-inf")], pd.NA)
        market = normalized.mean(axis=1, skipna=True).dropna()
        fast = market.rolling(20).mean().iloc[-1]
        slow = market.rolling(60).mean().iloc[-1]
        volatility = market.pct_change().rolling(20).std().iloc[-1]
        if pd.isna(fast) or pd.isna(slow) or pd.isna(volatility):
            return Regime("INSUFFICIENT_DATA", 0.0, 0.0, ("FEATURES_NOT_READY",))
        risk_off = float(context.get("risk_off", 0.0)) >= 0.7
        fx_shock = abs(float(context.get("fx_change_20d", 0.0))) >= 0.08
        high_vol = float(volatility) >= float(context.get("high_volatility", 0.035))
        if risk_off or fx_shock:
            reasons = ("EXTERNAL_RISK_EVENT",) if risk_off else ("FX_SHOCK",)
            return Regime("RISK_OFF", 0.9, 0.0, reasons)
        if float(fast) > float(slow):
            return Regime("TREND_UP_HIGH_VOL" if high_vol else "TREND_UP", 0.75, 0.5 if high_vol else 1.0,
                          ("FAST_ABOVE_SLOW", "HIGH_VOLATILITY") if high_vol else ("FAST_ABOVE_SLOW",))
        return Regime("TREND_DOWN", 0.75, 0.0, ("FAST_BELOW_SLOW",))


class StrategyRouter:
    """Map regimes to pre-validated strategy templates."""

    def route(self, requested: dict, regime: Regime) -> dict:
        result = dict(requested)
        if regime.name == "INSUFFICIENT_DATA" or regime.name == "RISK_OFF" or regime.name == "TREND_DOWN":
            result["enabled"] = False
            result["risk_multiplier"] = 0.0
            return result
        result["enabled"] = True
        result["risk_multiplier"] = regime.risk_multiplier
        result.setdefault("type", "momentum")
        result.setdefault("lookback", 20)
        return result
