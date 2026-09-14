"""Build bounded macro/news context for a paper deployment."""
from collections.abc import Callable
import logging

from config import settings as default_settings
from core.market_context import MacroContext, NewsEventEngine

logger = logging.getLogger("modelin.paper_context")


class PaperContextService:
    def __init__(self, config=default_settings, *, news_factory: Callable | None = None,
                 macro_factory: Callable | None = None, dart_factory: Callable | None = None,
                 sec_factory: Callable | None = None):
        self.config = config
        self.news_factory = news_factory
        self.macro_factory = macro_factory
        self.dart_factory = dart_factory
        self.sec_factory = sec_factory

    async def enrich(self, deployment: dict) -> dict:
        current = deployment
        if self.config.NEWS_FEEDS:
            try:
                if self.news_factory is None:
                    raise RuntimeError("뉴스 context provider가 구성되지 않았습니다.")
                news_context = await self.news_factory(self.config.NEWS_FEEDS).collect()
                current = self._with_context(current, news_context)
            except Exception as exc:
                logger.warning("news context unavailable; continuing without it: %s", exc)
        if self.config.FRED_API_KEY or self.config.PAPER_WORKER_ENABLED:
            try:
                if self.macro_factory is None:
                    raise RuntimeError("macro context provider가 구성되지 않았습니다.")
                macro = await self.macro_factory(self.config.FRED_API_KEY).collect()
                strategy = current["strategy"]
                context = MacroContext.build(
                    fx_change_20d=macro.get("fx_change_20d", 0.0),
                    rate_change_20d=macro.get("rate_change_20d", 0.0),
                    volatility=macro.get("vix_latest", 0.0) / 100.0,
                    news=strategy.get("context", {}),
                )
                context.update(macro)
                current = self._with_context(current, context)
            except Exception as exc:
                logger.warning("macro context unavailable; continuing with prior context: %s", exc)
        try:
            official_events = await self._official_events(current)
        except Exception as exc:
            logger.warning("official disclosure context unavailable; continuing without it: %s", exc)
            official_events = []
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
            if self.dart_factory is None:
                raise RuntimeError("OpenDART provider가 구성되지 않았습니다.")
            dart = self.dart_factory(self.config.OPENDART_API_KEY)
            for corp_code in deployment.get("corp_codes", []):
                events.extend(await dart.filings(corp_code=corp_code))
        if self.config.SEC_USER_AGENT:
            if self.sec_factory is None:
                raise RuntimeError("SEC provider가 구성되지 않았습니다.")
            sec = self.sec_factory(self.config.SEC_USER_AGENT)
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
