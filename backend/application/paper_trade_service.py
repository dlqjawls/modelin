"""Application service for the legacy immediate-fill paper trading API."""
from decimal import Decimal

from core.persistent_paper_broker import PersistentPaperBroker


class PaperTradeService:
    def __init__(self, database_path):
        self._broker = PersistentPaperBroker(database_path)

    def place_order(self, *, symbol: str, market: str, side: str,
                    quantity: Decimal, price: Decimal) -> dict:
        return self._broker.order(
            symbol=symbol, market=market, side=side,
            quantity=quantity, price=price,
        )

    def snapshot(self) -> dict:
        return self._broker.snapshot()
