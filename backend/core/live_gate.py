"""Fail-closed gate for any future live deployment."""
from decimal import Decimal


class LiveTradingGate:
    def __init__(self, approval_token: str = ""):
        self.approval_token = approval_token

    def authorize(self, *, deployment: dict, capabilities, order_notional: Decimal) -> tuple[bool, str]:
        if deployment.get("mode") != "live":
            return False, "MODE_IS_NOT_LIVE"
        if self.approval_token != "I_UNDERSTAND_LIVE_TRADING":
            return False, "EXPLICIT_APPROVAL_REQUIRED"
        if not getattr(capabilities, "supports_live", False):
            return False, "BROKER_LIVE_CAPABILITY_MISSING"
        if deployment.get("live_confirmed") is not True:
            return False, "DEPLOYMENT_NOT_CONFIRMED"
        limit = Decimal(str(deployment.get("max_order_notional", "0")))
        if limit <= 0 or order_notional > limit:
            return False, "ORDER_NOTIONAL_LIMIT"
        return True, "AUTHORIZED"
