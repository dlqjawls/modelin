"""Composition root for application dependencies.

HTTP routers and workers should consume these assembled dependencies instead
of constructing repositories and registries independently.
"""
from dataclasses import dataclass
from functools import lru_cache

from config import settings
from adapters.brokers.registry import BrokerRegistry
from adapters.brokers.kis import KISBrokerAdapter, KISConfig
from adapters.market_data.fred_macro import FredMacroContext
from adapters.market_data.news_feed import RSSNewsContext
from adapters.market_data.official_sources import OpenDartClient, SecSubmissionsClient
from core.contracts import Market
from data.providers.krx_provider import KRXProvider
from data.providers.us_provider import USProvider
from data.providers.crypto_provider import CryptoProvider
from data.persistence.operations_store import OperationsStore
from data.persistence.persistent_paper_broker import PersistentPaperBroker, account_database_path

from application.deployment_service import DeploymentService
from application.account_service import AccountService
from application.operations_service import OperationsService
from application.operations_query_service import OperationsQueryService
from application.account_query_service import AccountQueryService
from application.broker_query_service import BrokerQueryService
from application.idempotency_service import IdempotencyService
from application.paper_decision import PaperDecisionService
from application.paper_execution import PaperExecutionService
from application.market_snapshot import PaperMarketSnapshotService
from application.paper_context import PaperContextService
from application.system_query_service import SystemQueryService
from application.paper_trade_service import PaperTradeService
from application.market_data_service import MarketDataService
from application.backtest_service import BacktestService
from application.portfolio_service import PortfolioService
from application.screener_service import ScreenerService
from application.quote_service import QuoteService


@dataclass(frozen=True)
class ApplicationContainer:
    operations_store: OperationsStore
    broker_registry: BrokerRegistry
    account_service: AccountService
    deployment_service: DeploymentService
    operations_service: OperationsService
    operations_queries: OperationsQueryService
    account_queries: AccountQueryService
    broker_queries: BrokerQueryService
    idempotency: IdempotencyService
    paper_decisions: PaperDecisionService
    paper_execution: PaperExecutionService
    market_snapshots: PaperMarketSnapshotService
    paper_context: PaperContextService
    system_queries: SystemQueryService
    paper_trading: PaperTradeService
    market_data: MarketDataService
    backtests: BacktestService
    portfolio: PortfolioService
    screener: ScreenerService
    quotes: QuoteService


@lru_cache(maxsize=1)
def get_container() -> ApplicationContainer:
    store = OperationsStore(settings.PAPER_DB_PATH)
    registry = BrokerRegistry()
    def paper_broker_factory(account_id, initial_cash):
        return PersistentPaperBroker(
            account_database_path(settings.PAPER_DB_PATH, account_id),
            initial_cash=initial_cash,
        )
    def broker_factory(market):
        return KISBrokerAdapter(KISConfig(
            app_key=settings.KIS_APP_KEY,
            app_secret=settings.KIS_APP_SECRET,
            account_no=settings.KIS_US_ACCOUNT_NO if market == "us" else settings.KIS_KRX_ACCOUNT_NO,
            environment="paper",
            market=market,
        ))
    market_data = MarketDataService({
        Market.KRX: KRXProvider(), Market.US: USProvider(), Market.CRYPTO: CryptoProvider(),
    })
    return ApplicationContainer(
        operations_store=store,
        broker_registry=registry,
        account_service=AccountService(store),
        deployment_service=DeploymentService(store),
        operations_service=OperationsService(store),
        operations_queries=OperationsQueryService(store),
        account_queries=AccountQueryService(store, paper_broker_factory),
        broker_queries=BrokerQueryService(store, registry, lambda account_id: account_database_path(settings.PAPER_DB_PATH, account_id)),
        idempotency=IdempotencyService(store),
        paper_decisions=PaperDecisionService(),
        paper_execution=PaperExecutionService(),
        market_snapshots=PaperMarketSnapshotService(),
        paper_context=PaperContextService(
            news_factory=RSSNewsContext,
            macro_factory=FredMacroContext,
            dart_factory=OpenDartClient,
            sec_factory=SecSubmissionsClient,
        ),
        system_queries=SystemQueryService(
            settings, store, broker_factory=broker_factory, macro_factory=FredMacroContext,
            news_factory=RSSNewsContext,
        ),
        paper_trading=PaperTradeService(paper_broker_factory),
        market_data=market_data,
        backtests=BacktestService(market_data),
        portfolio=PortfolioService(market_data),
        screener=ScreenerService(market_data),
        quotes=QuoteService(broker_factory),
    )
