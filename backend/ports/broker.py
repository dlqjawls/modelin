"""Broker port. Concrete venues must implement this contract."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, Literal


@dataclass(frozen=True)
class BrokerCapabilities:
    market: str
    venue: str
    supports_paper: bool
    supports_live: bool
    order_types: tuple[str, ...]
    supports_client_order_id: bool


@dataclass(frozen=True)
class OrderRequest:
    account_id: str
    client_order_id: str
    symbol: str
    side: Literal["buy", "sell"]
    quantity: Decimal | None = None
    quote_amount: Decimal | None = None
    limit_price: Decimal | None = None


class BrokerAdapter(Protocol):
    """No adapter may submit live orders unless the account mode is live."""

    async def capabilities(self) -> BrokerCapabilities: ...
    async def account_snapshot(self) -> dict: ...
    async def submit(self, request: OrderRequest) -> dict: ...
    async def cancel(self, broker_order_id: str) -> dict: ...
    async def lookup_order(self, *, client_order_id: str | None = None, broker_order_id: str | None = None) -> dict: ...
    async def order_events(self, *, cursor: str | None = None) -> dict: ...
