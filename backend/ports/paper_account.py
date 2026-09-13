"""Ports for paper account persistence used by application services."""
from decimal import Decimal
from typing import Protocol


class PaperAccountBroker(Protocol):
    def order(self, *, symbol: str, market: str, side: str, quantity: Decimal, price: Decimal) -> dict: ...
    def snapshot(self) -> dict: ...


class PaperAccountBrokerFactory(Protocol):
    def __call__(self, account_id: str, initial_cash: str | Decimal) -> PaperAccountBroker: ...
