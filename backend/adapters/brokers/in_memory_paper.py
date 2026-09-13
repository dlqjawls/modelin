"""Deterministic in-memory paper broker.

It is intentionally isolated from live credentials.  A future broker adapter
must implement the same operations without changing the strategy layer.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from threading import RLock
from uuid import uuid4


@dataclass
class PaperOrder:
    id: str
    symbol: str
    market: str
    side: str
    quantity: Decimal
    requested_price: Decimal
    filled_quantity: Decimal = Decimal("0")
    average_price: Decimal = Decimal("0")
    status: str = "filled"
    fee: Decimal = Decimal("0")
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class PaperBroker:
    def __init__(self, initial_cash: Decimal = Decimal("10000000"), fee_rate: Decimal = Decimal("0.00015")):
        if initial_cash < 0 or fee_rate < 0:
            raise ValueError("초기자금과 수수료는 음수일 수 없습니다.")
        self.cash = initial_cash
        self.fee_rate = fee_rate
        self.positions: dict[tuple[str, str], dict[str, Decimal]] = {}
        self.orders: dict[str, PaperOrder] = {}
        self._lock = RLock()

    @staticmethod
    def _decimal(value) -> Decimal:
        result = Decimal(str(value))
        if not result.is_finite() or result <= 0:
            raise ValueError("금액과 수량은 유한한 양수여야 합니다.")
        return result

    def order(self, *, symbol: str, market: str, side: str, quantity, price) -> PaperOrder:
        if side not in {"buy", "sell"}:
            raise ValueError("side는 buy 또는 sell이어야 합니다.")
        qty, px = self._decimal(quantity), self._decimal(price)
        with self._lock:
            key = (market, symbol)
            current = self.positions.get(key, {"quantity": Decimal("0"), "avg_price": Decimal("0")})
            gross, fee = qty * px, qty * px * self.fee_rate
            if side == "buy":
                if self.cash < gross + fee:
                    raise ValueError("주문가능 현금이 부족합니다.")
                total_qty = current["quantity"] + qty
                avg = ((current["quantity"] * current["avg_price"]) + gross + fee) / total_qty
                self.cash -= gross + fee
                self.positions[key] = {"quantity": total_qty, "avg_price": avg}
            else:
                if current["quantity"] < qty:
                    raise ValueError("보유 수량보다 많이 매도할 수 없습니다.")
                self.cash += gross - fee
                remaining = current["quantity"] - qty
                if remaining == 0:
                    self.positions.pop(key, None)
                else:
                    self.positions[key] = current
            result = PaperOrder(str(uuid4()), symbol, market, side, qty, px, qty, px, "filled", fee)
            self.orders[result.id] = result
            return result

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cash": str(self.cash),
                "positions": [
                    {"symbol": symbol, "market": market, **{k: str(v) for k, v in value.items()}}
                    for (market, symbol), value in self.positions.items()
                ],
                "orders": [self._order_dict(order) for order in self.orders.values()],
            }

    @staticmethod
    def _order_dict(order: PaperOrder) -> dict:
        return {"id": order.id, "symbol": order.symbol, "market": order.market, "side": order.side,
                "quantity": str(order.quantity), "requested_price": str(order.requested_price),
                "filled_quantity": str(order.filled_quantity), "average_price": str(order.average_price),
                "status": order.status, "fee": str(order.fee), "created_at": order.created_at}
