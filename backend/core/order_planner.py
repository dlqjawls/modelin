"""Convert target weights into deterministic, risk-checked order intents."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: str
    quantity: Decimal
    reference_price: Decimal
    notional: Decimal
    reason: str


class OrderPlanner:
    def __init__(self, *, cash_buffer=Decimal("0.10"), max_asset_weight=Decimal("1"), max_order_notional=None,
                 fee_rate=Decimal("0.00015"), quantity_step=Decimal("0.00000001")):
        self.cash_buffer = Decimal(str(cash_buffer))
        self.max_asset_weight = Decimal(str(max_asset_weight))
        self.max_order_notional = Decimal(str(max_order_notional)) if max_order_notional is not None else None
        self.fee_rate = Decimal(str(fee_rate))
        self.quantity_step = Decimal(str(quantity_step))
        if not 0 <= self.cash_buffer < 1 or not 0 < self.max_asset_weight <= 1:
            raise ValueError("위험 한도 설정이 올바르지 않습니다.")

    def plan(self, *, cash, target_weights, positions, prices, nav=None):
        cash, prices = Decimal(str(cash)), {k: Decimal(str(v)) for k, v in prices.items()}
        if nav is None:
            nav = cash + sum(Decimal(str(v.get("quantity", 0))) * prices.get(k, 0) for k, v in positions.items())
        nav = Decimal(str(nav))
        if nav <= 0:
            return []
        weights = {symbol: min(Decimal(str(weight)), self.max_asset_weight) for symbol, weight in target_weights.items()}
        if sum(weights.values(), Decimal("0")) > 1 - self.cash_buffer:
            scale = (1 - self.cash_buffer) / sum(weights.values())
            weights = {k: v * scale for k, v in weights.items()}
        intents = []
        symbols = set(positions) | set(weights)
        for symbol in sorted(symbols):
            price = prices.get(symbol)
            if price is None or price <= 0:
                continue
            current_qty = Decimal(str(positions.get(symbol, {}).get("quantity", 0)))
            target_qty = (nav * weights.get(symbol, Decimal("0")) / price).quantize(self.quantity_step, rounding=ROUND_DOWN)
            delta = target_qty - current_qty
            if delta == 0:
                continue
            side = "buy" if delta > 0 else "sell"
            qty = abs(delta)
            notional = qty * price
            if self.max_order_notional is not None:
                qty = min(qty, self.max_order_notional / price).quantize(self.quantity_step, rounding=ROUND_DOWN)
                notional = qty * price
            if qty > 0:
                intents.append(OrderIntent(symbol, side, qty, price, notional, "TARGET_REBALANCE"))
        sells = [i for i in intents if i.side == "sell"]
        buys = [i for i in intents if i.side == "buy"]
        # Sells are sent first, so their net proceeds can fund buys. Cap each
        # buy against the remaining cash after fees; this prevents a basket of
        # individually valid intents from overspending the account together.
        available_cash = cash + sum(i.notional * (Decimal("1") - self.fee_rate) for i in sells)
        affordable_buys = []
        for intent in buys:
            unit_cost = intent.reference_price * (Decimal("1") + self.fee_rate)
            affordable_qty = (available_cash / unit_cost).quantize(self.quantity_step, rounding=ROUND_DOWN)
            qty = min(intent.quantity, affordable_qty)
            if qty <= 0:
                continue
            notional = qty * intent.reference_price
            affordable_buys.append(OrderIntent(intent.symbol, intent.side, qty, intent.reference_price,
                                               notional, intent.reason))
            available_cash -= notional * (Decimal("1") + self.fee_rate)
        return sells + affordable_buys
