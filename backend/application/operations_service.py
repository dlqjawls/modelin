"""Application services for deployment reads and state transitions."""
from uuid import uuid4

from config import settings


class DeploymentNotFound(LookupError):
    pass


class DeploymentRevisionConflict(ValueError):
    pass


class DeploymentStateConflict(ValueError):
    pass


class OperationsService:
    def __init__(self, store):
        self.store = store

    def get_deployment(self, deployment_id):
        item = self.store.deployment(deployment_id)
        if not item:
            raise DeploymentNotFound("deployment을 찾을 수 없습니다.")
        return item

    def command(self, deployment_id, command, expected_revision=None):
        item = self.get_deployment(deployment_id)
        if expected_revision is not None and expected_revision != item["revision"]:
            raise DeploymentRevisionConflict("deployment revision이 오래되었습니다.")
        if command in {"START", "RESUME"}:
            account = self.store.account(item["account_id"])
            if account and account["market"] not in settings.PAPER_ALLOWED_MARKETS:
                raise DeploymentStateConflict(
                    f"{account['market']} paper 운영은 현재 비활성화되어 있어 재개할 수 없습니다."
                )
            item["desired_state"] = "RUNNING"
            item["observed_state"] = "STARTING"
        elif command == "PAUSE":
            item["pause_epoch"] += 1
            item["desired_state"] = item["observed_state"] = "PAUSED"
        elif command == "CANCEL_OPEN":
            item["pause_epoch"] += 1
            item["desired_state"] = "PAUSED"
            item["observed_state"] = "CANCELING"
        elif command == "LIQUIDATE":
            item["pause_epoch"] += 1
            item["desired_state"] = item["observed_state"] = "LIQUIDATING"
        elif command == "ARCHIVE":
            item["desired_state"] = item["observed_state"] = "ARCHIVED"
        expected = item["revision"]
        item["revision"] += 1
        if not self.store.update_deployment_if_revision(item, expected):
            raise DeploymentStateConflict("deployment 상태가 동시에 변경되었습니다.")
        return {"command_id": str(uuid4()), "status": "ACCEPTED", "command": command, **item}
