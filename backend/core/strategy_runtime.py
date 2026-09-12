"""Pure strategy-to-target runtime shared by backtest and paper execution."""
from dataclasses import dataclass
from decimal import Decimal

import pandas as pd

from core.backtester import BacktestEngine
from core.backtester import SUPPORTED_STRATEGIES
from core.regime_router import RegimeDetector, StrategyRouter


@dataclass(frozen=True)
class StrategyDecision:
    kind: str
    target_weights: dict[str, Decimal]
    reason_codes: tuple[str, ...]


def validate_strategy(strategy: dict, symbols=None) -> dict:
    """Validate and normalize the strategy contract shared by API/backtest/runtime."""
    if not isinstance(strategy, dict):
        raise ValueError("strategy는 객체여야 합니다.")
    normalized = dict(strategy)
    kind = normalized.get("type", "equal_weight")
    if kind not in SUPPORTED_STRATEGIES:
        raise ValueError(f"지원하지 않는 전략: {kind}")
    if symbols is not None:
        if not symbols or any(not isinstance(s, str) or not s.strip() for s in symbols):
            raise ValueError("symbols는 비어 있지 않은 문자열 목록이어야 합니다.")
        if len(set(symbols)) != len(symbols):
            raise ValueError("symbols에 중복 종목이 있습니다.")
        normalized["symbols"] = list(symbols)
    integer_fields = {"lookback": 1, "period": 2, "window": 2, "short_window": 1, "long_window": 2}
    for field, minimum in integer_fields.items():
        if field in normalized:
            try: value = int(normalized[field])
            except (TypeError, ValueError) as exc: raise ValueError(f"{field}는 정수여야 합니다.") from exc
            if value < minimum: raise ValueError(f"{field}는 {minimum} 이상이어야 합니다.")
            normalized[field] = value
    if "short_window" in normalized and "long_window" in normalized and normalized["short_window"] >= normalized["long_window"]:
        raise ValueError("short_window은 long_window보다 작아야 합니다.")
    if "num_std" in normalized and float(normalized["num_std"]) <= 0:
        raise ValueError("num_std는 양수여야 합니다.")
    if "oversold" in normalized or "overbought" in normalized:
        oversold, overbought = float(normalized.get("oversold", 30)), float(normalized.get("overbought", 70))
        if not 0 < oversold < overbought < 100: raise ValueError("RSI 구간이 올바르지 않습니다.")
    return normalized


class StrategyRuntime:
    def __init__(self):
        self._signals = object.__new__(BacktestEngine)
        self._regimes = RegimeDetector()
        self._router = StrategyRouter()

    def evaluate(self, close_prices: pd.DataFrame, strategy: dict, current_weights=None, cash_buffer=Decimal("0")) -> StrategyDecision:
        configured_symbols = strategy.get("symbols") if isinstance(strategy, dict) else None
        strategy = validate_strategy(strategy, configured_symbols or list(close_prices.columns))
        if strategy.get("adaptive", False):
            routed = self._router.route(strategy, self._regimes.detect(close_prices, strategy.get("context")))
            if not routed.get("enabled", False):
                return StrategyDecision("BLOCKED", {}, ("REGIME_RISK_OFF",))
            strategy = routed
        if configured_symbols:
            available = [symbol for symbol in configured_symbols if symbol in close_prices.columns]
            if not available:
                return StrategyDecision("BLOCKED", {}, ("NO_CONFIGURED_SYMBOL_DATA",))
            close_prices = close_prices[available]
        if close_prices.empty:
            return StrategyDecision("BLOCKED", {}, ("NO_DATA",))
        signals = self._signals._generate_signals(close_prices, strategy)
        latest = signals.iloc[-1].fillna(0).clip(0, 1)
        active = latest[latest > 0]
        if active.empty:
            return StrategyDecision("TARGET", {}, ("NO_ELIGIBLE_ASSET",))
        weight = Decimal("1") / Decimal(str(len(active)))
        target = {str(symbol): weight for symbol in active.index}
        cash_buffer = Decimal(str(cash_buffer))
        if cash_buffer < 0 or cash_buffer >= 1:
            raise ValueError("cash_buffer는 0 이상 1 미만이어야 합니다.")
        target = {symbol: value * (Decimal("1") - cash_buffer) for symbol, value in target.items()}
        risk_multiplier = Decimal(str(strategy.get("risk_multiplier", "1")))
        if risk_multiplier < 0 or risk_multiplier > 1:
            raise ValueError("risk_multiplier는 0 이상 1 이하여야 합니다.")
        target = {symbol: value * risk_multiplier for symbol, value in target.items()}
        if current_weights is not None:
            symbols = set(target) | set(current_weights)
            unchanged = all(abs(Decimal(str(current_weights.get(symbol, 0))) - target.get(symbol, Decimal("0"))) <= Decimal("0.00000001") for symbol in symbols)
            if unchanged:
                return StrategyDecision("NO_CHANGE", target, ("TARGET_ALREADY_HELD",))
        return StrategyDecision("TARGET", target, ("SIGNAL_EVALUATED",))
