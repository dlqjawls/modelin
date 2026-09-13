"""Application wrapper for request idempotency persistence."""


class IdempotencyService:
    def __init__(self, store, scope="anonymous"):
        self.store = store
        self.scope = scope

    def lookup(self, endpoint, key, payload):
        return self.store.idempotent_response(
            scope=self.scope, endpoint=endpoint, key=key, payload=payload,
        )

    def save(self, endpoint, key, payload, *, status_code, response):
        return self.store.save_idempotent_response(
            scope=self.scope, endpoint=endpoint, key=key, payload=payload,
            status_code=status_code, response=response,
        )
