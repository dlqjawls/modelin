"""Application queries for account state and paper broker history."""
from ports.paper_account import PaperAccountBrokerFactory


class AccountQueryService:
    def __init__(self, store, broker_factory: PaperAccountBrokerFactory):
        self.store = store
        self.broker_factory = broker_factory

    def _paper_broker(self, account_id):
        account = self.store.account(account_id)
        if not account:
            raise LookupError("계좌를 찾을 수 없습니다.")
        if account["mode"] != "paper":
            raise RuntimeError("현재 live 계좌 조회는 구현되지 않았습니다.")
        return account, self.broker_factory(account_id, account["initial_cash"])

    def snapshot(self, account_id):
        account, broker = self._paper_broker(account_id)
        return account, broker.snapshot()

    def orders(self, account_id):
        account, broker = self._paper_broker(account_id)
        return account, broker.snapshot()["orders"]

    def events(self, account_id):
        account, broker = self._paper_broker(account_id)
        return account, broker.snapshot()["events"]
