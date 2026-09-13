"""Application service for the legacy immediate-fill paper trading API."""
from decimal import Decimal

from ports.paper_account import PaperAccountBroker, PaperAccountBrokerFactory


class PaperTradeService:
    def __init__(self, broker_factory: PaperAccountBrokerFactory):
        self._broker_factory = broker_factory
        self._broker: PaperAccountBroker | None = None

    def _get_broker(self) -> PaperAccountBroker:
        if self._broker is None:
            self._broker = self._broker_factory("legacy", "10000000")
        return self._broker

    def place_order(self, *, symbol: str, market: str, side: str,
                    quantity: Decimal, price: Decimal) -> dict:
        return self._get_broker().order(
            symbol=symbol, market=market, side=side,
            quantity=quantity, price=price,
        )

    def snapshot(self) -> dict:
        return self._get_broker().snapshot()
