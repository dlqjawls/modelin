"""Build bounded macro/news context for a paper deployment."""
from adapters.market_data.fred_macro import FredMacroContext
from adapters.market_data.news_feed import RSSNewsContext
from adapters.market_data.official_sources import OpenDartClient, SecSubmissionsClient
from config import settings as default_settings
from core.market_context import MacroContext, NewsEventEngine


class PaperContextService:
    def __init__(self, config=default_settings):
        self.config = config

    async def enrich(self, deployment: dict) -> dict:
        current = deployment
        if self.config.NEWS_FEEDS:
            news_context = await RSSNewsContext(self.config.NEWS_FEEDS).collect()
            current = self._with_context(current, news_context)
        if self.config.FRED_API_KEY or self.config.PAPER_WORKER_ENABLED:
            macro = await FredMacroContext(self.config.FRED_API_KEY).collect()
            strategy = current["strategy"]
            context = MacroContext.build(
                fx_change_20d=macro.get("fx_change_20d", 0.0),
                rate_change_20d=macro.get("rate_change_20d", 0.0),
                volatility=macro.get("vix_latest", 0.0) / 100.0,
                news=strategy.get("context", {}),
            )
            context.update(macro)
            current = self._with_context(current, context)
        official_events = await self._official_events(current)
        if official_events:
            engine = NewsEventEngine()
            official_news = engine.aggregate(
                engine.classify(item.title, item.source, item.published_at)
                for item in official_events
            )
            current = self._with_context(current, official_news)
        return current

    async def _official_events(self, deployment):
        if not (self.config.OPENDART_API_KEY or self.config.SEC_CIKS):
            return []
        events = []
        if self.config.OPENDART_API_KEY:
            dart = OpenDartClient(self.config.OPENDART_API_KEY)
            for corp_code in deployment.get("corp_codes", []):
                events.extend(await dart.filings(corp_code=corp_code))
        if self.config.SEC_USER_AGENT:
            sec = SecSubmissionsClient(self.config.SEC_USER_AGENT)
            for cik in self.config.SEC_CIKS:
                events.extend(await sec.filings(cik))
        return events

    @staticmethod
    def _with_context(deployment, context):
        strategy = dict(deployment.get("strategy", {}))
        merged = dict(strategy.get("context", {}))
        merged.update(context)
        strategy["context"] = merged
        return {**deployment, "strategy": strategy}
