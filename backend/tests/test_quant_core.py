import unittest
import asyncio
from decimal import Decimal

import pandas as pd
import httpx

from core.backtester import BacktestConfig, BacktestEngine
from core.paper_broker import PaperBroker
from core.persistent_paper_broker import PersistentPaperBroker, account_database_path
from core.execution_journal import ExecutionJournal
from core.account_lease import AccountLeaseStore
from core.risk_guard import RiskGuard
from core.postgres_execution_repository import PostgresExecutionRepository
from ports.broker import OrderRequest
from adapters.brokers.disabled_live import DisabledLiveBroker
from adapters.brokers.registry import BrokerRegistry
from adapters.brokers.kis import KISBrokerAdapter, KISConfig
from core.order_state import OrderState, OrderStateMachine
from core.scheduler import PaperScheduler
from data.contracts import Bar, DataSnapshot
from datetime import datetime, timezone
from core.strategy_runtime import StrategyRuntime, validate_strategy
from core.order_planner import OrderPlanner
from adapters.brokers.paper import PaperBrokerAdapter
from workers.paper_worker import execute_once, recover_pending_submissions, readiness_result
from core.operations_store import OperationsStore
from data.normalizer import normalize_daily_frame
from adapters.market_data.provider_adapter import ProviderMarketDataAdapter
from workers.paper_worker import execute_from_market_data
from core.calendar import TradingCalendar
from core.persistent_paper_broker import PersistentPaperBroker
from core.regime_router import RegimeDetector, StrategyRouter
from core.market_context import MacroContext, NewsEventEngine
from workers.run_paper import load_deployment
from core.strategy_comparator import compare_strategies
from adapters.brokers.alpaca import AlpacaBrokerAdapter, AlpacaConfig
from core.live_gate import LiveTradingGate
from adapters.market_data.news_feed import RSSNewsContext
from adapters.market_data.official_sources import OpenDartClient, SecSubmissionsClient
from tempfile import TemporaryDirectory


class QuantCoreTests(unittest.TestCase):
    def test_strategy_comparator_uses_same_sample_and_returns_ranked_scores(self):
        index = pd.date_range("2024-01-01", periods=80)
        closes = pd.DataFrame({"A": [100 + i for i in range(80)]}, index=index)
        opens = closes.copy()
        scores = compare_strategies(opens, closes, symbols=["A"],
                                    strategies=[{"type": "equal_weight"}, {"type": "momentum", "lookback": 5}])
        self.assertEqual(len(scores), 2)
        self.assertGreaterEqual(scores[0].score, scores[1].score)
        self.assertTrue(all(item.total_trades >= 0 for item in scores))

    def test_provider_adapter_exposes_open_frame_for_strategy_selection(self):
        end = datetime(2024, 1, 1, tzinfo=timezone.utc)
        snapshot = DataSnapshot("s", datetime(2024, 1, 2, tzinfo=timezone.utc), (
            Bar("A", "1d", datetime(2023, 12, 31, tzinfo=timezone.utc), end,
                Decimal("10"), Decimal("11"), Decimal("9"), Decimal("10.5"), Decimal("100"),
                datetime(2024, 1, 2, tzinfo=timezone.utc), True, "x"),
        ))
        adapter = ProviderMarketDataAdapter(object(), "test")
        self.assertEqual(adapter.open_frame(snapshot).loc[datetime(2024, 1, 1, tzinfo=timezone.utc), "A"], 10.0)

    def test_adaptive_risk_off_blocks_before_broker_submission(self):
        class CountingBroker:
            def __init__(self): self.submissions = 0
            async def submit(self, request): self.submissions += 1; return {}
        broker = CountingBroker()
        prices = pd.DataFrame({"005930": range(100, 160)},
                              index=pd.date_range("2024-01-01", periods=60))
        deployment = {"id": "d", "account_id": "a", "mode": "paper", "observed_state": "RUNNING",
                      "strategy": {"type": "moving_average", "adaptive": True, "symbols": ["005930"],
                                   "short_window": 20, "long_window": 60, "context": {"risk_off": 1}},
                      "cash_buffer": "0.10"}
        result = asyncio.run(execute_once(deployment, close_prices=prices, prices={"005930": Decimal("159")},
                                          broker=broker, account_snapshot={"cash": "1000", "positions": []}))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(broker.submissions, 0)

    def test_paper_runner_example_is_a_valid_adaptive_strategy(self):
        deployment = load_deployment("docs/examples/kis-paper-runner.json")
        self.assertTrue(deployment["strategy"]["adaptive"])
        self.assertEqual(deployment["strategy"]["type"], "moving_average")

    def test_us_paper_runner_configuration_is_accepted_without_kis_credentials(self):
        deployment = load_deployment("docs/examples/us-paper-runner.json")
        self.assertEqual(deployment["market"], "us")

    def test_alpaca_deployment_selects_external_paper_broker(self):
        deployment = load_deployment("docs/examples/us-paper-runner.json")
        self.assertEqual(deployment.get("broker"), "local")

    def test_news_and_macro_context_is_bounded_and_risk_sensitive(self):
        engine = NewsEventEngine()
        news = engine.aggregate([engine.classify("Central bank rate hike amid financial stress", "wire")])
        context = MacroContext.build(fx_change_20d=0.12, rate_change_20d=0.5, news=news)
        self.assertEqual(news["news_count"], 1)
        self.assertGreaterEqual(context["risk_off"], 0.7)
        self.assertLessEqual(context["risk_off"], 1.0)

    def test_regime_router_blocks_risk_off_and_reduces_high_volatility(self):
        prices = pd.DataFrame({"A": range(100, 160), "B": range(100, 160)},
                              index=pd.date_range("2024-01-01", periods=60))
        detector = RegimeDetector()
        risk_off = detector.detect(prices, {"risk_off": 1})
        self.assertEqual(risk_off.name, "RISK_OFF")
        self.assertFalse(StrategyRouter().route({"type": "momentum"}, risk_off)["enabled"])
        up = detector.detect(prices)
        self.assertEqual(up.name, "TREND_UP")
        self.assertEqual(StrategyRouter().route({"type": "momentum"}, up)["risk_multiplier"], 1.0)

    def test_signal_is_executed_on_next_open(self):
        engine = object.__new__(BacktestEngine)
        prices = pd.DataFrame({"A": [100.0, 110.0, 99.0]}, index=pd.date_range("2024-01-01", periods=3))
        signals = engine._generate_signals(prices, {"type": "momentum", "lookback": 1})
        result = engine._event_backtest(prices, prices, signals, BacktestConfig(
            symbols=["A"], initial_capital=100, commission_rate=0, slippage_rate=0,
            transaction_tax_rate=0, rebalance_period="1d"))
        # The +10% move is observed before the signal. The strategy can only
        # enter on the following eligible open, so it cannot claim that move.
        self.assertEqual(result.equity_curve[-1]["value"], 100.0)

    def test_backtest_respects_quantity_step_and_does_not_create_fractional_stock(self):
        engine = object.__new__(BacktestEngine)
        prices = pd.DataFrame({"A": [100.0, 101.0, 102.0]}, index=pd.date_range("2024-01-01", periods=3))
        signals = pd.DataFrame({"A": [1.0, 1.0, 1.0]}, index=prices.index)
        result = engine._event_backtest(prices, prices, signals, BacktestConfig(
            symbols=["A"], initial_capital=150, commission_rate=0, slippage_rate=0,
            transaction_tax_rate=0, quantity_step=1, rebalance_period="1d"))
        self.assertEqual(result.equity_curve[1]["value"], 150.0)

    def test_rsi_and_bollinger_hold_state_are_sticky(self):
        engine = object.__new__(BacktestEngine)
        prices = pd.DataFrame({"A": [100.0] * 40}, index=pd.date_range("2024-01-01", periods=40))
        for strategy in ({"type": "rsi"}, {"type": "bollinger_bands"}):
            signals = engine._generate_signals(prices, strategy)
            self.assertTrue((signals == 0).all().all())

    def test_paper_broker_accounts_for_fee_and_inventory(self):
        broker = PaperBroker(Decimal("1000"), Decimal("0.01"))
        order = broker.order(symbol="A", market="krx", side="buy", quantity=9, price=100)
        self.assertEqual(order.status, "filled")
        self.assertEqual(broker.cash, Decimal("91.00"))
        self.assertEqual(broker.positions[("krx", "A")]["quantity"], Decimal("9"))
        broker.order(symbol="A", market="krx", side="sell", quantity=9, price=110)
        self.assertEqual(broker.cash, Decimal("1071.10"))
        self.assertNotIn(("krx", "A"), broker.positions)

    def test_persistent_paper_broker_survives_reopen(self):
        with TemporaryDirectory() as directory:
            path = f"{directory}/paper.sqlite3"
            first = PersistentPaperBroker(path, Decimal("1000"), Decimal("0.01"))
            first.order(symbol="A", market="krx", side="buy", quantity=1, price=100, client_order_id="same")
            duplicate = first.order(symbol="A", market="krx", side="buy", quantity=1, price=100, client_order_id="same")
            self.assertEqual(duplicate["client_order_id"], "same")
            reopened = PersistentPaperBroker(path, Decimal("999"), Decimal("0.5"))
            snapshot = reopened.snapshot()
            self.assertEqual(snapshot["cash"], "899.00")
            self.assertEqual(snapshot["positions"][0]["quantity"], "1")
            self.assertEqual(len(snapshot["events"]), 1)

    def test_paper_accounts_have_isolated_database_paths(self):
        with TemporaryDirectory() as directory:
            base = f"{directory}/paper.sqlite3"
            first = account_database_path(base, "account-a")
            second = account_database_path(base, "account-b")
            self.assertNotEqual(first, second)
            broker_a = PersistentPaperBroker(first, Decimal("100"))
            broker_b = PersistentPaperBroker(second, Decimal("200"))
            self.assertEqual(broker_a.snapshot()["cash"], "100")
            self.assertEqual(broker_b.snapshot()["cash"], "200")

    def test_execution_journal_is_idempotent_and_tracks_outbox_completion(self):
        class Intent:
            client_order_id = "client-1"
            symbol = "A"
            side = "buy"
            quantity = Decimal("2")
            reference_price = Decimal("10")
        with TemporaryDirectory() as directory:
            journal = ExecutionJournal(f"{directory}/journal.sqlite3")
            run_id, first = journal.commit_plan(deployment_id="d1", schedule_key="2026-01-01", decision={"kind": "TARGET"}, intents=[Intent()])
            same_run, second = journal.commit_plan(deployment_id="d1", schedule_key="2026-01-01", decision={"kind": "TARGET"}, intents=[Intent()])
            self.assertEqual(run_id, same_run)
            self.assertEqual(len(first), len(second))
            self.assertEqual(len(journal.pending()), 1)
            journal.mark_submitted("client-1", {"status": "filled"})
            self.assertEqual(journal.pending(), [])

    def test_recovery_looks_up_pending_orders_without_resubmitting(self):
        class Intent:
            client_order_id = "client-recovery"
            symbol = "A"
            side = "buy"
            quantity = Decimal("1")
            reference_price = Decimal("10")
        with TemporaryDirectory() as directory:
            journal = ExecutionJournal(f"{directory}/journal.sqlite3")
            journal.commit_plan(deployment_id="d1", schedule_key="run", decision={}, intents=[Intent()])
            class Broker:
                def __init__(self): self.submits = 0
                async def lookup_order(self, **kwargs): return {"client_order_id": kwargs["client_order_id"], "status": "filled"}
                async def submit(self, request): self.submits += 1
            broker = Broker()
            result = asyncio.run(recover_pending_submissions(journal, broker))
            self.assertEqual(result["resolved"], ["client-recovery"])
            self.assertEqual(result["resubmitted"], [])
            self.assertEqual(broker.submits, 0)

    def test_account_lease_fences_old_worker(self):
        with TemporaryDirectory() as directory:
            leases = AccountLeaseStore(f"{directory}/leases.sqlite3")
            first = leases.acquire("a", "worker-1", now=datetime(2026, 1, 1, tzinfo=timezone.utc))
            self.assertEqual(first["fencing_token"], 1)
            self.assertIsNone(leases.acquire("a", "worker-2", now=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc)))
            second = leases.acquire("a", "worker-2", now=datetime(2026, 1, 1, 0, 0, 31, tzinfo=timezone.utc))
            self.assertEqual(second["fencing_token"], 2)
            self.assertFalse(leases.valid("a", "worker-1", 1, now=datetime(2026, 1, 1, 0, 0, 31, tzinfo=timezone.utc)))

    def test_snapshot_rejects_future_or_unavailable_bars(self):
        as_of = datetime(2024, 1, 2, tzinfo=timezone.utc)
        bar = Bar("a", "1d", datetime(2024, 1, 1, tzinfo=timezone.utc),
                  datetime(2024, 1, 2, tzinfo=timezone.utc), Decimal("1"), Decimal("2"),
                  Decimal("1"), Decimal("2"), Decimal("10"), as_of)
        snapshot = DataSnapshot("s", as_of, (bar,))
        self.assertEqual(len(snapshot.usable_bars()), 1)

    def test_bar_rejects_non_finite_ohlcv(self):
        with self.assertRaises(ValueError):
            Bar("a", "1d", datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 2, tzinfo=timezone.utc), Decimal("NaN"), Decimal("2"),
                Decimal("1"), Decimal("2"), Decimal("10"), datetime(2024, 1, 2, tzinfo=timezone.utc))

    def test_strategy_runtime_returns_targets_without_broker_access(self):
        prices = pd.DataFrame({"A": [100.0, 110.0], "B": [100.0, 90.0]})
        decision = StrategyRuntime().evaluate(prices, {"type": "momentum", "lookback": 1})
        self.assertEqual(decision.kind, "TARGET")
        self.assertEqual(decision.target_weights, {"A": Decimal("1")})

    def test_strategy_validator_rejects_invalid_contracts(self):
        with self.assertRaises(ValueError): validate_strategy({"type": "unknown"}, ["A"])
        with self.assertRaises(ValueError): validate_strategy({"type": "momentum", "lookback": 0}, ["A"])
        with self.assertRaises(ValueError): validate_strategy({"type": "equal_weight"}, ["A", "A"])

    def test_strategy_runtime_uses_only_configured_symbols(self):
        prices = pd.DataFrame({"A": [100.0, 110.0], "UNCONFIGURED": [100.0, 200.0]})
        decision = StrategyRuntime().evaluate(prices, {"type": "equal_weight", "symbols": ["A"]})
        self.assertEqual(decision.target_weights, {"A": Decimal("1")})
        blocked = StrategyRuntime().evaluate(prices, {"type": "equal_weight", "symbols": ["MISSING"]})
        self.assertEqual(blocked.kind, "BLOCKED")

    def test_strategy_runtime_reports_no_change_for_existing_target(self):
        prices = pd.DataFrame({"A": [100.0, 110.0]})
        decision = StrategyRuntime().evaluate(prices, {"type": "equal_weight", "symbols": ["A"]}, {"A": Decimal("1")})
        self.assertEqual(decision.kind, "NO_CHANGE")

    def test_strategy_runtime_applies_cash_buffer_before_no_change(self):
        prices = pd.DataFrame({"A": [100.0, 110.0]})
        decision = StrategyRuntime().evaluate(prices, {"type": "equal_weight", "symbols": ["A"]},
                                               {"A": Decimal("0.9")}, cash_buffer=Decimal("0.10"))
        self.assertEqual(decision.kind, "NO_CHANGE")

    def test_postgres_repository_commits_plan_in_one_transaction(self):
        class Cursor:
            def __init__(self): self.sql = []; self.row = ("run-1",)
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, sql, params): self.sql.append((sql, params))
            def fetchone(self): return self.row
        class Transaction:
            def __init__(self, conn): self.conn = conn
            def __enter__(self): self.conn.entered += 1; return self
            def __exit__(self, *args): self.conn.exited += 1; return False
        class Connection:
            def __init__(self): self.entered = 0; self.exited = 0; self.cursor_obj = Cursor()
            def transaction(self): return Transaction(self)
            def cursor(self): return self.cursor_obj
            def close(self): pass
        connection = Connection()
        class Intent:
            account_id = "a"; client_order_id = "c1"; symbol = "A"; side = "buy"
            quantity = Decimal("1"); reference_price = Decimal("10"); pause_epoch = 0
        result = PostgresExecutionRepository(lambda: connection).commit_plan(
            deployment_id="d", schedule_key="s", decision={"kind": "TARGET"}, intents=[Intent()])
        self.assertEqual(result["run_id"], "run-1")
        self.assertEqual(connection.entered, 1)
        self.assertEqual(connection.exited, 1)
        self.assertEqual(len(connection.cursor_obj.sql), 3)

    def test_worker_only_promotes_starting_after_data_and_reconciliation(self):
        self.assertEqual(readiness_result({"mode": "paper"}, has_data=False)["observed_state"], "STARTING")
        self.assertEqual(readiness_result({"mode": "paper"}, has_data=True, reconciled=False)["observed_state"], "STARTING")
        self.assertEqual(readiness_result({"mode": "paper"}, has_data=True)["observed_state"], "RUNNING")

    def test_risk_guard_blocks_drawdown_and_daily_loss(self):
        guard = RiskGuard()
        blocked = guard.evaluate(current_nav=90, peak_nav=100, policy={"max_drawdown": "0.10"})
        self.assertFalse(blocked.allowed)
        self.assertIn("MAX_DRAWDOWN", blocked.reason_codes)
        passed = guard.evaluate(current_nav=99, day_start_nav=100, policy={"daily_loss_limit": "0.02"})
        self.assertTrue(passed.allowed)

    def test_order_planner_respects_cash_buffer_and_sells_first(self):
        planner = OrderPlanner(cash_buffer=Decimal("0.10"), quantity_step=Decimal("1"))
        intents = planner.plan(cash=1000, target_weights={"A": Decimal("0.9"), "B": Decimal("0.9")},
                               positions={"A": {"quantity": Decimal("10")}}, prices={"A": 100, "B": 100})
        self.assertEqual([i.side for i in intents], ["sell", "buy"])
        self.assertLessEqual(sum(i.notional for i in intents if i.side == "buy"), Decimal("900"))

    def test_order_planner_does_not_overspend_multiple_buys(self):
        planner = OrderPlanner(cash_buffer=Decimal("0"), quantity_step=Decimal("1"), fee_rate=Decimal("0"))
        intents = planner.plan(cash=100, target_weights={"A": Decimal("1"), "B": Decimal("1")},
                               positions={}, prices={"A": 10, "B": 10})
        self.assertEqual(sum(i.notional for i in intents if i.side == "buy"), Decimal("100"))

    def test_paper_worker_executes_strategy_through_injected_paper_adapter(self):
        with TemporaryDirectory() as directory:
            adapter = PaperBrokerAdapter("acct", f"{directory}/paper.sqlite3", "krx")
            prices = pd.DataFrame({"A": [100.0, 110.0], "B": [100.0, 90.0]})
            snapshot = asyncio.run(adapter.account_snapshot())
            result = asyncio.run(execute_once(
                {"id": "dep", "account_id": "acct", "mode": "paper", "observed_state": "RUNNING",
                 "strategy": {"type": "momentum", "lookback": 1}, "cash_buffer": "0.10"},
                close_prices=prices, prices={"A": 110, "B": 90}, broker=adapter,
                account_snapshot=snapshot))
            self.assertEqual(result["status"], "executed")
            self.assertEqual(len(result["orders"]), 1)

    def test_operations_store_persists_and_rejects_duplicate_active_deployment(self):
        with TemporaryDirectory() as directory:
            store = OperationsStore(f"{directory}/ops.sqlite3")
            account = {"id": "a", "name": "paper", "mode": "paper", "market": "krx", "currency": "KRW",
                       "initial_cash": "1000", "status": "READY", "created_at": "now"}
            store.create_account(account)
            deployment = {"id": "d", "account_id": "a", "mode": "paper", "strategy": {"type": "equal_weight"},
                          "allocation_amount": "1000", "cash_buffer": "0.1", "desired_state": "DRAFT",
                          "observed_state": "DRAFT", "pause_epoch": 0, "revision": 1, "last_error": None}
            store.create_deployment(deployment)
            self.assertEqual(store.deployment("d")["strategy"]["type"], "equal_weight")
            with self.assertRaises(ValueError):
                store.create_deployment({**deployment, "id": "d2"})

    def test_operations_store_control_update_is_revision_atomic(self):
        with TemporaryDirectory() as directory:
            store = OperationsStore(f"{directory}/ops.sqlite3")
            store.create_account({"id": "a", "name": "A", "mode": "paper", "market": "krx", "currency": "KRW", "initial_cash": "100", "status": "READY", "created_at": "2026-01-01"})
            deployment = {"id": "d", "account_id": "a", "mode": "paper", "strategy": {"type": "equal_weight", "symbols": ["A"]}, "allocation_amount": "100", "cash_buffer": "0.1", "desired_state": "DRAFT", "observed_state": "DRAFT", "pause_epoch": 0, "revision": 1, "last_error": None}
            store.create_deployment(deployment)
            changed = {**deployment, "desired_state": "RUNNING", "observed_state": "STARTING", "revision": 2}
            self.assertTrue(store.update_deployment_if_revision(changed, 1))
            self.assertFalse(store.update_deployment_if_revision({**changed, "revision": 3}, 1))

    def test_provider_frame_normalizer_drops_unfinished_bar(self):
        frame = pd.DataFrame({"open": [1, 2], "high": [2, 3], "low": [1, 2], "close": [2, 3], "volume": [10, 20]},
                             index=pd.to_datetime(["2024-01-01", "2024-01-03"]))
        snapshot = normalize_daily_frame(frame, instrument_id="A", source="fixture",
                                         as_of=datetime(2024, 1, 3, tzinfo=timezone.utc))
        self.assertEqual(len(snapshot.bars), 1)
        self.assertEqual(snapshot.bars[0].close, Decimal("2"))

    def test_provider_adapter_feeds_normalized_data_to_paper_worker(self):
        class FixtureProvider:
            async def get_ohlcv(self, symbol, start, end, interval):
                return pd.DataFrame({"open": [100, 110], "high": [110, 120], "low": [90, 100],
                                     "close": [105, 115], "volume": [100, 100]},
                                    index=pd.to_datetime(["2024-01-01", "2024-01-02"]))
        with TemporaryDirectory() as directory:
            adapter = ProviderMarketDataAdapter(FixtureProvider(), "fixture")
            broker = PaperBrokerAdapter("acct", f"{directory}/paper.sqlite3", "krx")
            deployment = {"id": "dep", "account_id": "acct", "mode": "paper", "observed_state": "RUNNING",
                          "strategy": {"type": "equal_weight", "symbols": ["A"]}, "cash_buffer": "0.10"}
            result = asyncio.run(execute_from_market_data(deployment, data_adapter=adapter, broker=broker,
                                                           as_of=datetime(2024, 1, 3, tzinfo=timezone.utc)))
            self.assertEqual(result["status"], "executed")

    def test_calendar_blocks_weekends_for_stocks_but_not_crypto(self):
        cal = TradingCalendar()
        saturday = datetime(2024, 1, 6, tzinfo=timezone.utc)
        self.assertFalse(cal.is_trading_day("krx", saturday))
        self.assertFalse(cal.is_trading_day("us", saturday))
        self.assertTrue(cal.is_trading_day("crypto", saturday))

    def test_paper_adapter_snapshot_is_read_only(self):
        with TemporaryDirectory() as directory:
            broker = PersistentPaperBroker(f"{directory}/paper.sqlite3", Decimal("1000"))
            before = broker.snapshot()
            _ = broker.snapshot()
            after = broker.snapshot()
            self.assertEqual(before["cash"], after["cash"])
            self.assertEqual(before["orders"], after["orders"])

    def test_paper_adapter_exposes_event_cursor_contract(self):
        with TemporaryDirectory() as directory:
            adapter = PaperBrokerAdapter("a", f"{directory}/paper.sqlite3", "crypto")
            asyncio.run(adapter.submit(OrderRequest(account_id="a", client_order_id="event-1",
                                                     symbol="BTC", side="buy", quantity=Decimal("1"),
                                                     limit_price=Decimal("10"))))
            page = asyncio.run(adapter.order_events())
            self.assertEqual(len(page["events"]), 1)

    def test_unconfigured_live_adapter_fails_closed(self):
        adapter = DisabledLiveBroker()
        capabilities = asyncio.run(adapter.capabilities())
        self.assertFalse(capabilities.supports_live)
        with self.assertRaises(RuntimeError):
            asyncio.run(adapter.submit(None))

    def test_broker_registry_never_implicitly_enables_live(self):
        with TemporaryDirectory() as directory:
            registry = BrokerRegistry()
            paper = registry.resolve(mode="paper", venue="unknown", account_id="a", market="krx",
                                     paper_path=f"{directory}/paper.sqlite3")
            live = registry.resolve(mode="live", venue="unknown", account_id="a", market="krx",
                                    paper_path=f"{directory}/paper.sqlite3")
            self.assertTrue(asyncio.run(paper.capabilities()).supports_paper)
            self.assertFalse(asyncio.run(live.capabilities()).supports_live)

    def test_kis_paper_adapter_maps_token_and_domestic_order(self):
        calls = []
        def handler(request):
            calls.append(request)
            if request.url.path == "/oauth2/tokenP":
                return httpx.Response(200, json={"access_token": "token", "rt_cd": "0"})
            if request.url.path == "/uapi/hashkey":
                return httpx.Response(200, json={"HASH": "hash", "rt_cd": "0"})
            return httpx.Response(200, json={"rt_cd": "0", "output": {"ODNO": "123"}})
        async def scenario():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                adapter = KISBrokerAdapter(KISConfig("key", "secret", "12345678", environment="paper"), client)
                result = await adapter.submit(OrderRequest("12345678", "client-1", "005930", "buy", Decimal("1"), limit_price=Decimal("70000")))
                return result
        result = asyncio.run(scenario())
        self.assertEqual(result["broker_order_id"], "123")
        self.assertEqual(calls[-1].headers["tr_id"], "VTTC0802U")
        self.assertEqual(calls[-1].headers["hashkey"], "hash")

    def test_kis_order_events_polls_daily_orders_with_cursor(self):
        def handler(request):
            if request.url.path == "/oauth2/tokenP":
                return httpx.Response(200, json={"access_token": "token", "rt_cd": "0"})
            return httpx.Response(200, json={"rt_cd": "0", "output1": [{
                "odno": "123", "tot_ccld_qty": "1", "ord_qty": "1", "ord_tmd": "101010", "avg_prvs": "70000"
            }]})
        async def scenario():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                adapter = KISBrokerAdapter(KISConfig("key", "secret", "12345678"), client)
                first = await adapter.order_events()
                second = await adapter.order_events(cursor=first["next_cursor"])
                return first, second
        first, second = asyncio.run(scenario())
        self.assertEqual(first["events"][0]["status"], "filled")
        self.assertEqual(second["events"], [])

    def test_kis_websocket_subscription_is_paper_safe(self):
        def handler(request):
            return httpx.Response(200, json={"approval_key": "approval", "rt_cd": "0"})
        async def scenario():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                adapter = KISBrokerAdapter(KISConfig("key", "secret", "12345678"), client)
                return await adapter.websocket_subscription(["005930"])
        subscription = asyncio.run(scenario())
        self.assertIn("31000", subscription["url"])
        self.assertEqual(subscription["subscriptions"][0]["tr_id"], "H0STCNI0")

    def test_alpaca_paper_order_mapping_never_enables_live(self):
        calls = []
        def handler(request):
            calls.append(request)
            if request.url.path == "/v2/orders" and request.method == "POST":
                return httpx.Response(200, json={"id": "alpaca-1", "status": "accepted"})
            return httpx.Response(200, json=[])
        async def scenario():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                adapter = AlpacaBrokerAdapter(AlpacaConfig("key", "secret"), client)
                capabilities = await adapter.capabilities()
                result = await adapter.submit(OrderRequest("key", "client-1", "AAPL", "buy", Decimal("1"), Decimal("100")))
                return capabilities, result
        capabilities, result = asyncio.run(scenario())
        self.assertFalse(capabilities.supports_live)
        self.assertEqual(result["broker_order_id"], "alpaca-1")

    def test_live_gate_fails_closed_until_every_condition_is_explicit(self):
        paper_capabilities = type("Capabilities", (), {"supports_live": False})()
        gate = LiveTradingGate("wrong")
        allowed, reason = gate.authorize(deployment={"mode": "live"},
                                         capabilities=paper_capabilities, order_notional=Decimal("1"))
        self.assertFalse(allowed)
        self.assertEqual(reason, "EXPLICIT_APPROVAL_REQUIRED")
        live_capabilities = type("Capabilities", (), {"supports_live": True})()
        gate = LiveTradingGate("I_UNDERSTAND_LIVE_TRADING")
        allowed, reason = gate.authorize(
            deployment={"mode": "live", "live_confirmed": True, "max_order_notional": "100"},
            capabilities=live_capabilities, order_notional=Decimal("10"))
        self.assertTrue(allowed)
        self.assertEqual(reason, "AUTHORIZED")

    def test_news_feed_failure_enters_degraded_risk_mode(self):
        result = asyncio.run(RSSNewsContext(["http://127.0.0.1:1/unavailable"], 0.1).collect())
        self.assertEqual(result["feed_failures"], 1)
        self.assertEqual(result["risk_off"], 1.0)

    def test_official_sources_fail_closed_without_credentials(self):
        self.assertEqual(asyncio.run(OpenDartClient("").filings(corp_code="001")), [])
        self.assertEqual(asyncio.run(SecSubmissionsClient("").filings("320193")), [])

    def test_registry_requires_explicit_kis_paper_registration(self):
        registry = BrokerRegistry()
        class Marker:
            async def capabilities(self):
                return type("Capabilities", (), {"supports_paper": True, "supports_live": False})()
        registry.register_paper("kis", lambda **kwargs: Marker())
        selected = registry.resolve(mode="paper", venue="kis", account_id="a", market="krx", paper_path="unused")
        self.assertTrue(asyncio.run(selected.capabilities()).supports_paper)

    def test_order_state_machine_preserves_partial_fill_and_cancel_race(self):
        machine = OrderStateMachine(OrderState("o", Decimal("10")))
        machine.submitting(); machine.acknowledged(); machine.fill(4); machine.request_cancel()
        machine.canceled()
        state = machine.state
        self.assertEqual(state.lifecycle, "CANCELED")
        self.assertEqual(state.filled_quantity, Decimal("4"))
        machine2 = OrderStateMachine(OrderState("o2", Decimal("10")))
        machine2.submitting(); machine2.unknown()
        self.assertEqual(machine2.state.resolution, "UNKNOWN")
        machine2.acknowledged(); machine2.fill(10)
        self.assertEqual(machine2.state.lifecycle, "FILLED")

    def test_scheduler_blocks_duplicate_ticks_and_closed_sessions(self):
        scheduler = PaperScheduler()
        deployment = {"id": "d", "mode": "paper", "market": "crypto", "observed_state": "RUNNING"}
        entered = asyncio.Event()
        release = asyncio.Event()

        async def slow_execute(item, now):
            entered.set(); await release.wait(); return {"status": "done"}

        async def scenario():
            first = asyncio.create_task(scheduler.tick(deployment, now=datetime(2024, 1, 6, tzinfo=timezone.utc), execute=slow_execute))
            await entered.wait()
            duplicate = await scheduler.tick(deployment, now=datetime(2024, 1, 6, tzinfo=timezone.utc), execute=slow_execute)
            release.set()
            result = await first
            closed = await scheduler.tick({**deployment, "market": "krx"}, now=datetime(2024, 1, 6, tzinfo=timezone.utc), execute=slow_execute)
            return result, duplicate, closed

        result, duplicate, closed = asyncio.run(scenario())
        self.assertEqual(result["status"], "done")
        self.assertEqual(duplicate["reason"], "RUN_ALREADY_IN_PROGRESS")
        self.assertEqual(closed["reason"], "MARKET_CLOSED")


if __name__ == "__main__":
    unittest.main()
