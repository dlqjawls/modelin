"""Read-only broker capability queries."""


class BrokerQueryService:
    def __init__(self, store, registry, paper_path_factory):
        self.store = store
        self.registry = registry
        self.paper_path_factory = paper_path_factory

    async def capabilities(self, account_id):
        account = self.store.account(account_id)
        if not account:
            raise LookupError("계좌를 찾을 수 없습니다.")
        broker = self.registry.resolve(
            mode=account["mode"], venue="unconfigured", account_id=account_id,
            market=account["market"],
            paper_path=self.paper_path_factory(account_id),
        )
        return account, (await broker.capabilities()).__dict__
