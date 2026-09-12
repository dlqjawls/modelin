"""Broker-port wrapper around the persistent local paper broker."""
from decimal import Decimal

from core.persistent_paper_broker import PersistentPaperBroker
from ports.broker import BrokerCapabilities, OrderRequest


class PaperBrokerAdapter:
    def __init__(self, account_id: str, path: str, market: str, venue: str = "paper"):
        self.account_id, self.market, self.venue = account_id, market, venue
        self._broker = PersistentPaperBroker(path)

    async def capabilities(self):
        return BrokerCapabilities(self.market, self.venue, True, False, ("market", "limit"), True)

    async def account_snapshot(self):
        return self._broker.snapshot()

    async def submit(self, request: OrderRequest):
        if request.account_id != self.account_id:
            raise ValueError("계좌 식별자가 일치하지 않습니다.")
        if request.quantity is None or request.limit_price is None:
            raise ValueError("paper adapter는 현재 수량과 가격을 요구합니다.")
        return self._broker.order(symbol=request.symbol, market=self.market, side=request.side,
                                  quantity=request.quantity, price=request.limit_price,
                                  client_order_id=request.client_order_id)

    async def cancel(self, broker_order_id: str):
        raise ValueError("이미 즉시 체결된 paper 주문은 취소할 수 없습니다.")

    async def lookup_order(self, *, client_order_id=None, broker_order_id=None):
        snapshot = self._broker.snapshot()
        return next((o for o in snapshot["orders"]
                     if (broker_order_id and o["id"] == broker_order_id)
                     or (client_order_id and o["client_order_id"] == client_order_id)), None)

    async def order_events(self, *, cursor=None):
        events = self._broker.snapshot()["events"]
        start = int(cursor or 0)
        page = events[start:]
        return {"events": page, "next_cursor": str(start + len(page)) if page else None}
