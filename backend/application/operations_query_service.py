"""Read-only application queries for operations screens."""


class OperationsQueryService:
    def __init__(self, store):
        self.store = store

    def accounts(self):
        return self.store.accounts()

    def account(self, account_id):
        return self.store.account(account_id)

    def deployments(self):
        return self.store.deployments()

    def deployment(self, deployment_id):
        return self.store.deployment(deployment_id)
