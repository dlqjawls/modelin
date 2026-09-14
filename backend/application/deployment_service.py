"""Use cases for creating and validating paper deployments.

The HTTP layer supplies validated request data and translates exceptions into
HTTP responses. Persistence and strategy validation stay behind this service so
other entry points, such as a worker or CLI, can use the same rules.
"""
from uuid import uuid4

from config import settings
from core.strategy_runtime import validate_strategy


class DeploymentConflict(ValueError):
    """The request is valid but conflicts with current account state."""


class DeploymentService:
    def __init__(self, store):
        self.store = store

    def create_paper(self, request: dict) -> dict:
        account = self.store.account(request["account_id"])
        if not account:
            raise LookupError("계좌를 찾을 수 없습니다.")
        if request.get("mode", "paper") != account["mode"]:
            raise ValueError("계좌와 deployment 모드가 다릅니다.")
        market = account["market"]
        if market not in settings.PAPER_ALLOWED_MARKETS:
            raise ValueError(
                f"{market} paper 운영은 현재 비활성화되어 있습니다. "
                "PAPER_ALLOWED_MARKETS에 시장을 명시한 뒤 별도 deployment로 활성화하세요."
            )

        strategy = validate_strategy(request["strategy"], request["strategy"].get("symbols"))
        item = {
            "id": str(uuid4()),
            "account_id": request["account_id"],
            "mode": "paper",
            "strategy": strategy,
            "allocation_amount": request["allocation_amount"],
            "cash_buffer": request.get("cash_buffer", "0.10"),
            "desired_state": "DRAFT",
            "observed_state": "DRAFT",
            "pause_epoch": 0,
            "revision": 1,
            "last_error": None,
        }
        try:
            return self.store.create_deployment(item)
        except ValueError as exc:
            raise DeploymentConflict(str(exc)) from exc
