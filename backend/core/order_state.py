"""Broker-independent order lifecycle reducer."""
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class OrderState:
    order_id: str
    requested_quantity: Decimal
    filled_quantity: Decimal = Decimal("0")
    lifecycle: str = "CREATED"
    resolution: str = "KNOWN"
    cancel_state: str = "NONE"


class OrderStateMachine:
    def __init__(self, state: OrderState):
        self.state = state

    def submitting(self):
        if self.state.lifecycle not in {"CREATED", "SUBMITTING"}:
            raise ValueError("현재 주문 상태에서 제출할 수 없습니다.")
        self.state.lifecycle = "SUBMITTING"
        return self.state

    def acknowledged(self):
        if self.state.lifecycle not in {"SUBMITTING", "OPEN"}:
            raise ValueError("접수할 수 없는 주문 상태입니다.")
        self.state.lifecycle = "OPEN"
        self.state.resolution = "KNOWN"
        return self.state

    def unknown(self):
        self.state.resolution = "UNKNOWN"
        return self.state

    def fill(self, quantity):
        qty = Decimal(str(quantity))
        if qty <= 0 or self.state.filled_quantity + qty > self.state.requested_quantity:
            raise ValueError("체결 수량이 주문 수량을 초과합니다.")
        self.state.filled_quantity += qty
        self.state.resolution = "KNOWN"
        self.state.lifecycle = "FILLED" if self.state.filled_quantity == self.state.requested_quantity else "PARTIALLY_FILLED"
        return self.state

    def request_cancel(self):
        if self.state.lifecycle in {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}:
            raise ValueError("취소할 수 없는 주문 상태입니다.")
        self.state.cancel_state = "REQUESTED"
        return self.state

    def canceled(self):
        if self.state.filled_quantity == self.state.requested_quantity:
            self.state.lifecycle = "FILLED"
            self.state.cancel_state = "REJECTED"
        else:
            self.state.lifecycle = "CANCELED"
            self.state.cancel_state = "CONFIRMED"
        return self.state

    def rejected(self):
        if self.state.filled_quantity:
            raise ValueError("부분 체결된 주문을 rejected로 덮을 수 없습니다.")
        self.state.lifecycle = "REJECTED"
        self.state.resolution = "KNOWN"
        return self.state
