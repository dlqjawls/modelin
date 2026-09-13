import asyncio
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pandas as pd

from application.backtest_service import BacktestService
from application.market_snapshot import PaperMarketSnapshotService
from application.paper_decision import PaperDecisionService
from application.paper_execution import PaperExecutionService
from workers.paper_worker import execute_from_market_data
from workers.paper_worker import serve
from main import app, lifespan
from config import settings
from data.contracts import Bar


class FakeCalendar:
    def __init__(self, open_market=True):
        self.open_market = open_market

    def is_trading_day(self, market, as_of):
        return self.open_market


class FakeSnapshot:
    def __init__(self, bars):
        self.bars = bars

    def usable_bars(self):
        return self.bars


class FakeMarketData:
    def __init__(self, snapshot):
        self.snapshot_result = snapshot
        self.calls = []

    async def snapshot(self, symbols, timeframe, as_of):
        self.calls.append((symbols, timeframe, as_of))
        return self.snapshot_result

    def close_frame(self, snapshot):
        return "close-frame"


class RecordingBroker:
    def __init__(self):
        self.requests = []

    async def submit(self, request):
        self.requests.append(request)
        return {"client_order_id": request.client_order_id, "status": "accepted"}


class ApplicationServiceTests(unittest.TestCase):
    def test_backtest_service_loads_data_before_calling_pure_engine(self):
        class Provider:
            async def get_ohlcv(self, symbol, start, end, interval):
                index = pd.date_range("2024-01-01", periods=2, tz="UTC")
                return pd.DataFrame({
                    "open": [10, 11], "high": [11, 12], "low": [9, 10],
                    "close": [10, 12], "volume": [100, 110],
                }, index=index)

        class MarketData:
            def provider(self, market):
                self.market = market
                return Provider()

        class Engine:
            def run_frames(self, config, opens, closes):
                self.config = config
                self.opens = opens
                self.closes = closes
                return {"status": "calculated"}

        engine = Engine()
        service = BacktestService(MarketData(), engine=engine)
        result = asyncio.run(service.run(
            symbols=["A"], market="krx", start_date="2024-01-01", end_date="2024-01-03",
            strategy={"type": "equal_weight"}, initial_capital=1000,
            commission_rate=0, slippage_rate=0, rebalance_period="1M",
        ))

        self.assertEqual(result["status"], "calculated")
        self.assertEqual(engine.opens.columns.tolist(), ["A"])
        self.assertEqual(engine.closes.iloc[-1, 0], 12)
        self.assertEqual(engine.config.market, "krx")

    def test_api_lifespan_does_not_start_worker_when_disabled(self):
        async def scenario():
            with patch.object(settings, "PAPER_WORKER_ENABLED", False), patch.object(settings, "PAPER_DEPLOYMENT_FILE", ""):
                async with lifespan(app):
                    self.assertEqual(app.state.paper_worker, "disabled")
                    self.assertIsNone(app.state.paper_worker_task)

        asyncio.run(scenario())

    def test_api_lifespan_starts_and_cancels_enabled_worker(self):
        async def worker(*args, **kwargs):
            await asyncio.Event().wait()

        async def scenario():
            deployment = {"id": "d1", "account_id": "a1", "market": "krx", "mode": "paper"}
            with patch.object(settings, "PAPER_WORKER_ENABLED", True), \
                    patch.object(settings, "PAPER_DEPLOYMENT_FILE", "deployment.json"), \
                    patch("main.load_deployment", return_value=deployment), \
                    patch("main.run_paper_worker", new=worker):
                async with lifespan(app):
                    self.assertEqual(app.state.paper_worker, "running")
                    self.assertIsNotNone(app.state.paper_worker_task)
                    self.assertFalse(app.state.paper_worker_task.done())
                self.assertIsNone(app.state.paper_worker_task)

        asyncio.run(scenario())

    def test_worker_serve_can_construct_default_scheduler(self):
        async def scenario():
            async def loader():
                return {"id": "d1", "mode": "paper", "observed_state": "PAUSED"}

            task = asyncio.create_task(serve(loader, interval_seconds=0, execute=lambda *_: None))
            await asyncio.sleep(0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        asyncio.run(scenario())

    def test_market_data_cycle_passes_strategy_symbols_to_auto_selection(self):
        class SnapshotService:
            async def collect(self, deployment, *, data_adapter, as_of):
                return type("Prepared", (), {
                    "snapshot": object(),
                    "usable_bars": (),
                    "close_prices": "close-frame",
                    "latest_prices": {"A": Decimal("10")},
                    "schedule_key": "schedule-1",
                })(), None

        class DataAdapter:
            def open_frame(self, snapshot):
                return "open-frame"

        class Broker:
            async def account_snapshot(self):
                return {"cash": "100", "positions": []}

        deployment = {
            "id": "d1", "account_id": "a1", "mode": "paper", "observed_state": "RUNNING",
            "market": "krx", "strategy": {"symbols": ["A"], "auto_select": True, "candidates": [{"type": "equal_weight"}]},
        }
        with patch("workers.paper_worker.compare_strategies", return_value=[type("Rank", (), {"strategy": {"type": "equal_weight"}})()]) as compare:
            with patch("workers.paper_worker.execute_once", new_callable=AsyncMock,
                       return_value={"status": "no_change", "orders": []}):
                result = asyncio.run(execute_from_market_data(
                    deployment, data_adapter=DataAdapter(), broker=Broker(), as_of=datetime.now(timezone.utc),
                    snapshot_service=SnapshotService(), decision_service=None, execution_service=None,
                ))

        self.assertEqual(result["status"], "no_change")
        self.assertEqual(compare.call_args.kwargs["symbols"], ["A"])

    def test_market_snapshot_service_normalizes_latest_prices_and_schedule(self):
        first = datetime(2024, 1, 2, tzinfo=timezone.utc)
        second = datetime(2024, 1, 3, tzinfo=timezone.utc)
        first_start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        second_start = datetime(2024, 1, 2, tzinfo=timezone.utc)
        bars = (
            Bar("A", "1d", first_start, first, Decimal("9"), Decimal("10"), Decimal("8"), Decimal("9"), Decimal("1"), first, True, "a"),
            Bar("A", "1d", second_start, second, Decimal("10"), Decimal("12"), Decimal("9"), Decimal("11"), Decimal("1"), second, True, "b"),
            Bar("B", "1d", second_start, second, Decimal("20"), Decimal("22"), Decimal("19"), Decimal("21"), Decimal("1"), second, True, "c"),
        )
        data = FakeMarketData(FakeSnapshot(bars))
        deployment = {"market": "us", "strategy": {"symbols": ["A", "B"], "timeframe": "1d"}}

        result, blocked = asyncio.run(PaperMarketSnapshotService(FakeCalendar()).collect(
            deployment, data_adapter=data, as_of=second,
        ))

        self.assertIsNone(blocked)
        self.assertEqual(result.close_prices, "close-frame")
        self.assertEqual(result.latest_prices, {"A": Decimal("11"), "B": Decimal("21")})
        self.assertEqual(result.schedule_key, second.isoformat())
        self.assertEqual(data.calls[0][0], ["A", "B"])

    def test_market_snapshot_service_returns_closed_market_without_data_call(self):
        data = FakeMarketData(FakeSnapshot(()))
        deployment = {"market": "us", "strategy": {"symbols": ["A"]}}

        result, blocked = asyncio.run(PaperMarketSnapshotService(FakeCalendar(False)).collect(
            deployment, data_adapter=data, as_of=datetime.now(timezone.utc),
        ))

        self.assertIsNone(result)
        self.assertEqual(blocked["reason"], "MARKET_CLOSED")
        self.assertEqual(data.calls, [])

    def test_decision_service_uses_deployment_limits_when_planning(self):
        service = PaperDecisionService()
        intents = service.plan_orders(
            cash=Decimal("1000"),
            target_weights={"A": Decimal("1")},
            positions={}, prices={"A": Decimal("100")}, nav=Decimal("1000"),
            deployment={"cash_buffer": "0.10", "max_asset_weight": "0.50"},
        )

        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0].quantity, Decimal("5"))

    def test_execution_service_assigns_intent_client_ids_and_submits(self):
        service = PaperExecutionService()
        broker = RecordingBroker()
        intent = type("Intent", (), {"symbol": "A", "side": "buy", "quantity": Decimal("2"), "reference_price": Decimal("10")})()
        deployment = {"id": "d1", "account_id": "a1"}

        submitted = asyncio.run(service.submit_intents(
            deployment=deployment, intents=[intent], broker=broker, client_ids={"A": "client-1"},
        ))

        self.assertEqual(submitted[0]["status"], "accepted")
        self.assertEqual(broker.requests[0].client_order_id, "client-1")
        self.assertEqual(broker.requests[0].limit_price, Decimal("10"))

    def test_execution_service_skips_positions_without_usable_prices(self):
        service = PaperExecutionService()
        broker = RecordingBroker()
        deployment = {"id": "d1", "account_id": "a1"}

        submitted = asyncio.run(service.liquidate(
            deployment=deployment,
            positions=[{"symbol": "A", "quantity": Decimal("2")}, {"symbol": "B", "quantity": Decimal("1")}],
            prices={"A": Decimal("10"), "B": Decimal("0")}, broker=broker, schedule_key="s1",
        ))

        self.assertEqual(len(submitted), 1)
        self.assertEqual(broker.requests[0].symbol, "A")
        self.assertEqual(broker.requests[0].side, "sell")
        self.assertEqual(broker.requests[0].client_order_id, "liquidate-d1-s1-A")


if __name__ == "__main__":
    unittest.main()
