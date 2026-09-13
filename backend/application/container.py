"""Composition root for application dependencies.

HTTP routers and workers should consume these assembled dependencies instead
of constructing repositories and registries independently.
"""
from dataclasses import dataclass
from functools import lru_cache

from config import settings
from adapters.brokers.registry import BrokerRegistry
from core.operations_store import OperationsStore

from application.deployment_service import DeploymentService
from application.account_service import AccountService
from application.operations_service import OperationsService
from application.operations_query_service import OperationsQueryService
from application.account_query_service import AccountQueryService
from application.broker_query_service import BrokerQueryService
from application.idempotency_service import IdempotencyService
from application.paper_decision import PaperDecisionService
from application.paper_execution import PaperExecutionService


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


@lru_cache(maxsize=1)
def get_container() -> ApplicationContainer:
    store = OperationsStore(settings.PAPER_DB_PATH)
    registry = BrokerRegistry()
    return ApplicationContainer(
        operations_store=store,
        broker_registry=registry,
        account_service=AccountService(store),
        deployment_service=DeploymentService(store),
        operations_service=OperationsService(store),
        operations_queries=OperationsQueryService(store),
        account_queries=AccountQueryService(store, settings.PAPER_DB_PATH),
        broker_queries=BrokerQueryService(store, registry, settings.PAPER_DB_PATH),
        idempotency=IdempotencyService(store),
        paper_decisions=PaperDecisionService(),
        paper_execution=PaperExecutionService(),
    )
