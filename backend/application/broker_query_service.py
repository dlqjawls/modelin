"""Read-only broker capability queries."""
from data.persistence.persistent_paper_broker import account_database_path


class BrokerQueryService:
    def __init__(self, store, registry, paper_db_path):
        self.store = store
        self.registry = registry
        self.paper_db_path = paper_db_path

    async def capabilities(self, account_id):
        account = self.store.account(account_id)
        if not account:
            raise LookupError("계좌를 찾을 수 없습니다.")
        broker = self.registry.resolve(
            mode=account["mode"], venue="unconfigured", account_id=account_id,
            market=account["market"],
            paper_path=account_database_path(self.paper_db_path, account_id),
        )
        return account, (await broker.capabilities()).__dict__
