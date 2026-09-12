"""Explicit Alpaca US paper trading adapter.

Live mode is intentionally unsupported until a separate production review.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from ports.broker import BrokerCapabilities, OrderRequest


@dataclass(frozen=True)
class AlpacaConfig:
    api_key: str
    api_secret: str
    environment: str = "paper"
    timeout_seconds: float = 10.0

    @property
    def base_url(self):
        if self.environment != "paper":
            raise ValueError("Alpaca live adapter는 현재 비활성화되어 있습니다.")
        return "https://paper-api.alpaca.markets"

    def __post_init__(self):
        if self.environment != "paper":
            raise ValueError("Alpaca adapter는 paper 환경만 지원합니다.")
        if not self.api_key or not self.api_secret:
            raise ValueError("Alpaca paper API 자격증명이 필요합니다.")


class AlpacaBrokerAdapter:
    def __init__(self, config: AlpacaConfig, client: httpx.AsyncClient | None = None):
        self.config, self._client = config, client

    def _headers(self):
        return {"APCA-API-KEY-ID": self.config.api_key,
                "APCA-API-SECRET-KEY": self.config.api_secret,
                "content-type": "application/json"}

    async def _request(self, method, path, *, json=None, params=None):
        own = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.config.timeout_seconds)
        try:
            response = await client.request(method, self.config.base_url + path,
                                            headers=self._headers(), json=json, params=params)
            response.raise_for_status()
            return response.json() if response.content else {}
        finally:
            if own:
                await client.aclose()

    async def capabilities(self):
        return BrokerCapabilities("us", "alpaca", True, False, ("market", "limit"), True)

    async def account_snapshot(self):
        account = await self._request("GET", "/v2/account")
        positions = await self._request("GET", "/v2/positions")
        return {"cash": account.get("cash", "0"), "positions": positions, "source": "alpaca-paper"}

    async def submit(self, request: OrderRequest):
        if request.account_id != self.config.api_key:
            raise ValueError("Alpaca account 식별자가 일치하지 않습니다.")
        body = {"symbol": request.symbol, "qty": str(request.quantity), "side": request.side,
                "type": "limit" if request.limit_price is not None else "market",
                "time_in_force": "day", "client_order_id": request.client_order_id}
        if request.limit_price is not None:
            body["limit_price"] = str(request.limit_price)
        result = await self._request("POST", "/v2/orders", json=body)
        return {"broker_order_id": result.get("id"), "client_order_id": request.client_order_id,
                "status": result.get("status", "acknowledged"), "raw": result}

    async def lookup_order(self, *, client_order_id=None, broker_order_id=None):
        if broker_order_id:
            result = await self._request("GET", f"/v2/orders/{broker_order_id}")
        else:
            result = await self._request("GET", "/v2/orders", params={"status": "all", "limit": 100})
            result = next((item for item in result if item.get("client_order_id") == client_order_id), None)
        return result

    async def order_events(self, *, cursor=None):
        orders = await self._request("GET", "/v2/orders", params={"status": "all", "limit": 100})
        events = []
        for order in orders:
            event_id = str(order.get("id", "")) + ":" + str(order.get("updated_at", ""))
            if cursor and event_id <= cursor:
                continue
            events.append({"event_id": event_id, "broker_order_id": order.get("id"),
                           "status": order.get("status"), "raw": order})
        events.sort(key=lambda item: item["event_id"])
        return {"events": events, "next_cursor": events[-1]["event_id"] if events else cursor}

    async def cancel(self, broker_order_id: str):
        await self._request("DELETE", f"/v2/orders/{broker_order_id}")
        return {"broker_order_id": broker_order_id, "status": "cancel_requested"}
