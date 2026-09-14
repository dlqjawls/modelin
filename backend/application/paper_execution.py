"""Application service for submitting approved paper orders."""
from ports.broker import BrokerAdapter, OrderRequest


class PaperExecutionService:
    async def submit_intents(self, *, deployment, intents, broker: BrokerAdapter, client_ids, on_submitted=None):
        submitted = []
        for intent in intents:
            request = OrderRequest(
                account_id=deployment["account_id"],
                client_order_id=client_ids[intent.symbol],
                symbol=intent.symbol,
                side=intent.side,
                quantity=intent.quantity,
                limit_price=intent.reference_price,
            )
            result = await broker.submit(request)
            submitted.append(result)
            if on_submitted is not None:
                callback_result = on_submitted(request.client_order_id, result)
                if hasattr(callback_result, "__await__"):
                    await callback_result
        return submitted

    async def liquidate(self, *, deployment, positions, prices, broker: BrokerAdapter, schedule_key):
        submitted = []
        for position in positions:
            symbol = position.get("symbol")
            quantity = position.get("quantity", "0")
            price = prices.get(symbol)
            if not symbol or price is None or price <= 0:
                continue
            request = OrderRequest(
                account_id=deployment["account_id"],
                client_order_id=f"liquidate-{deployment['id']}-{schedule_key}-{symbol}",
                symbol=symbol, side="sell", quantity=quantity, limit_price=price,
            )
            submitted.append(await broker.submit(request))
        return submitted
