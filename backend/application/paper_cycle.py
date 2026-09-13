"""Application boundary for one paper execution cycle.

The worker owns timing and retry policy. This service owns the application
boundary between a loaded deployment and the injected market-data/broker
ports. The callback keeps the existing execution implementation compatible
while the domain execution steps are migrated incrementally.
"""
from dataclasses import dataclass
from typing import Awaitable, Callable

from ports.broker import BrokerAdapter


@dataclass(frozen=True)
class PaperCycleRequest:
    deployment: dict
    as_of: object


class PaperCycleService:
    """Coordinate a single paper cycle without constructing adapters."""

    def __init__(self, execute_cycle: Callable[..., Awaitable[dict]], decision_service=None,
                 execution_service=None, snapshot_service=None):
        self._execute_cycle = execute_cycle
        self._decision_service = decision_service
        self._execution_service = execution_service
        self._snapshot_service = snapshot_service

    async def execute(self, request: PaperCycleRequest, *, data_adapter, broker: BrokerAdapter, journal=None) -> dict:
        if request.deployment.get("mode") != "paper":
            raise RuntimeError("paper cycle은 paper deployment만 허용합니다.")
        return await self._execute_cycle(
            request.deployment,
            data_adapter=data_adapter,
            broker=broker,
            as_of=request.as_of,
            journal=journal,
            decision_service=self._decision_service,
            execution_service=self._execution_service,
            snapshot_service=self._snapshot_service,
        )
