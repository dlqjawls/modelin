"""Application use cases for paper account creation."""
from datetime import datetime, timezone
from uuid import uuid4


class AccountService:
    def __init__(self, store):
        self.store = store

    def create_paper(self, request: dict) -> dict:
        account = {
            "id": str(uuid4()),
            "name": request["name"],
            "mode": "paper",
            "market": request["market"],
            "currency": request["currency"],
            "initial_cash": request["initial_cash"],
            "status": "READY",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return self.store.create_account(account)
