"""Reconnectable KIS execution-notice consumer.

The consumer only translates broker messages into the existing order-event
shape. Persistence and duplicate handling remain owned by the execution
journal, so reconnects cannot silently create a second fill.
"""
import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

import websockets

from adapters.brokers.kis import KISBrokerAdapter

logger = logging.getLogger("modelin.kis_websocket")
EventHandler = Callable[[dict], Awaitable[None]]


def parse_execution_message(message: str | bytes) -> dict | None:
    """Parse JSON or KIS pipe-delimited execution notices without secrets."""
    if isinstance(message, bytes):
        message = message.decode("utf-8", errors="replace")
    try:
        payload = json.loads(message)
        if isinstance(payload, dict) and payload.get("header", {}).get("tr_id") in {"PINGPONG", "H0STCNI0", "H0STCNI9"}:
            if payload.get("header", {}).get("tr_id") == "PINGPONG":
                return {"type": "heartbeat"}
            return {"type": "execution", "raw": payload.get("body", payload)}
    except json.JSONDecodeError:
        pass
    parts = message.split("|")
    if len(parts) < 4 or parts[0] != "0":
        return None
    fields = parts[3].split("^")
    if len(fields) < 3:
        return None
    return {"type": "execution", "event_id": fields[2], "broker_order_id": fields[1], "raw_fields": fields}


class KISExecutionConsumer:
    def __init__(self, adapter: KISBrokerAdapter, *, reconnect_delay: float = 2.0):
        self.adapter = adapter
        self.reconnect_delay = reconnect_delay

    async def run(self, symbols: list[str], on_event: EventHandler, stop_event: asyncio.Event) -> None:
        """Consume until stopped; reconnect transport failures with backoff."""
        subscription = await self.adapter.websocket_subscription(symbols)
        while not stop_event.is_set():
            try:
                async with websockets.connect(subscription["url"], ping_interval=20, ping_timeout=20) as socket:
                    for item in subscription["subscriptions"]:
                        await socket.send(json.dumps({"header": {
                            "approval_key": subscription["approval_key"], "custtype": "P",
                            "tr_type": "1", "content-type": "utf-8"}, "body": {
                            "input": {"tr_id": item["tr_id"], "tr_key": item["tr_key"]}}}))
                    while not stop_event.is_set():
                        try:
                            raw = await asyncio.wait_for(socket.recv(), timeout=1.0)
                        except asyncio.TimeoutError:
                            continue
                        event = parse_execution_message(raw)
                        if event and event["type"] == "execution":
                            await on_event(event)
            except (OSError, asyncio.TimeoutError, websockets.WebSocketException) as exc:
                if not stop_event.is_set():
                    logger.warning("KIS execution websocket disconnected: %s", type(exc).__name__)
                    await asyncio.sleep(self.reconnect_delay)
