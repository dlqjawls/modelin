"""Pure pre-trade risk checks for paper and future live workers."""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason_codes: tuple[str, ...]


class RiskGuard:
    def evaluate(self, *, current_nav, peak_nav=None, day_start_nav=None, policy=None) -> RiskDecision:
        policy = policy or {}
        nav = Decimal(str(current_nav))
        if not nav.is_finite() or nav <= 0:
            return RiskDecision(False, ("INVALID_NAV",))
        reasons = []
        if peak_nav is not None:
            peak = Decimal(str(peak_nav))
            max_drawdown = Decimal(str(policy.get("max_drawdown", "1")))
            if peak > 0 and (peak - nav) / peak >= max_drawdown:
                reasons.append("MAX_DRAWDOWN")
        if day_start_nav is not None:
            start = Decimal(str(day_start_nav))
            daily_loss = Decimal(str(policy.get("daily_loss_limit", "1")))
            if start > 0 and (start - nav) / start >= daily_loss:
                reasons.append("DAILY_LOSS_LIMIT")
        return RiskDecision(not reasons, tuple(reasons) or ("RISK_CHECK_PASSED",))
