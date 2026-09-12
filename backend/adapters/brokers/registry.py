"""Explicit broker selection boundary.

No credential presence or environment variable can implicitly enable live
orders. A venue adapter must be registered deliberately in a later change.
"""
from adapters.brokers.disabled_live import DisabledLiveBroker
from adapters.brokers.paper import PaperBrokerAdapter


class BrokerRegistry:
    def __init__(self):
        self._live = {}
        self._paper = {}

    def register_live(self, venue: str, factory):
        if not venue or not callable(factory):
            raise ValueError("live adapter 등록 정보가 올바르지 않습니다.")
        self._live[venue] = factory

    def register_paper(self, venue: str, factory):
        if not venue or not callable(factory):
            raise ValueError("paper adapter 등록 정보가 올바르지 않습니다.")
        self._paper[venue] = factory

    def resolve(self, *, mode: str, venue: str, account_id: str, market: str, paper_path: str):
        if mode == "paper":
            if venue in self._paper:
                return self._paper[venue](account_id=account_id, market=market, paper_path=paper_path)
            return PaperBrokerAdapter(account_id, paper_path, market, venue="paper")
        if mode != "live":
            raise ValueError("mode는 paper 또는 live여야 합니다.")
        factory = self._live.get(venue)
        return factory(account_id=account_id, market=market) if factory else DisabledLiveBroker()
