"""Fail-closed placeholder used until a venue is explicitly selected."""
from ports.broker import BrokerCapabilities, OrderRequest


class DisabledLiveBroker:
    """A live-shaped adapter that can never send an external order."""

    async def capabilities(self):
        return BrokerCapabilities("unknown", "unconfigured", False, False, (), False)

    async def account_snapshot(self):
        raise RuntimeError("증권사·거래소가 설정되지 않아 live 계좌를 사용할 수 없습니다.")

    async def submit(self, request: OrderRequest):
        raise RuntimeError("live broker adapter가 설정되지 않았습니다. 주문은 차단되었습니다.")

    async def cancel(self, broker_order_id: str):
        raise RuntimeError("live broker adapter가 설정되지 않았습니다.")

    async def lookup_order(self, *, client_order_id=None, broker_order_id=None):
        raise RuntimeError("live broker adapter가 설정되지 않았습니다.")

    async def order_events(self, *, cursor=None):
        raise RuntimeError("live broker adapter가 설정되지 않았습니다.")
