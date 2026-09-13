"""Application queries for account state and paper broker history."""
from data.persistence.persistent_paper_broker import PersistentPaperBroker, account_database_path


class AccountQueryService:
    def __init__(self, store, database_path):
        self.store = store
        self.database_path = database_path

    def _paper_broker(self, account_id):
        account = self.store.account(account_id)
        if not account:
            raise LookupError("계좌를 찾을 수 없습니다.")
        if account["mode"] != "paper":
            raise RuntimeError("현재 live 계좌 조회는 구현되지 않았습니다.")
        return account, PersistentPaperBroker(
            account_database_path(self.database_path, account_id),
            initial_cash=account["initial_cash"],
        )

    def snapshot(self, account_id):
        account, broker = self._paper_broker(account_id)
        return account, broker.snapshot()

    def orders(self, account_id):
        account, broker = self._paper_broker(account_id)
        return account, broker.snapshot()["orders"]

    def events(self, account_id):
        account, broker = self._paper_broker(account_id)
        return account, broker.snapshot()["events"]
