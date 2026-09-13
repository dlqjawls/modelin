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


@dataclass(frozen=True)
class ApplicationContainer:
    operations_store: OperationsStore
    broker_registry: BrokerRegistry
    account_service: AccountService
    deployment_service: DeploymentService
    operations_service: OperationsService
    operations_queries: OperationsQueryService


@lru_cache(maxsize=1)
def get_container() -> ApplicationContainer:
    store = OperationsStore(settings.PAPER_DB_PATH)
    return ApplicationContainer(
        operations_store=store,
        broker_registry=BrokerRegistry(),
        account_service=AccountService(store),
        deployment_service=DeploymentService(store),
        operations_service=OperationsService(store),
        operations_queries=OperationsQueryService(store),
    )
