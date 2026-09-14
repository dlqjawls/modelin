"""Application queries for readiness and provider configuration status."""

import asyncio
from core import calendar as market_calendar


class SystemQueryService:
    def __init__(self, settings, store, *, broker_factory=None, macro_factory=None, news_factory=None):
        self.settings = settings
        self.store = store
        self.broker_factory = broker_factory
        self.macro_factory = macro_factory
        self.news_factory = news_factory

    def diagnostics(self):
        settings = self.settings
        return {
            "paper_worker": "configured" if settings.PAPER_WORKER_ENABLED and settings.PAPER_DEPLOYMENT_FILE else "disabled",
            "paper_allowed_markets": list(settings.PAPER_ALLOWED_MARKETS),
            "sources": {
                "kis_paper": "configured" if all((settings.KIS_APP_KEY, settings.KIS_APP_SECRET, settings.KIS_KRX_ACCOUNT_NO)) else "missing_credentials",
                "kis_overseas_paper": ("disabled_by_config" if "us" not in settings.PAPER_ALLOWED_MARKETS else
                                       ("configured" if all((settings.KIS_APP_KEY, settings.KIS_APP_SECRET, settings.KIS_US_ACCOUNT_NO)) else "missing_credentials")),
                "rss": "configured" if settings.NEWS_FEEDS else "not_configured",
                "opendart": "configured" if settings.OPENDART_API_KEY else "missing_api_key",
                "sec_edgar": "configured" if settings.SEC_USER_AGENT and settings.SEC_CIKS else "missing_user_agent_or_cik",
                "fred_macro": "configured_public_csv" if not settings.FRED_API_KEY else "configured_api",
                "market_calendar": ("official_xkrx_xnys" if market_calendar.xcals is not None
                                    else "fallback_weekday_session"),
            },
            "live_trading": "disabled_by_default",
            "crypto_trading": "paused",
        }

    def ready(self):
        # Opening the configured store validates its path and schema.
        type(self.store)(self.settings.PAPER_DB_PATH)
        return {"status": "ready", "mode": "paper_only"}

    async def live_diagnostics(self):
        """Run read-only provider checks without exposing secrets or order APIs."""
        result = {"kis_krx": {}, "kis_us": {}, "fred": {}, "rss": {}}
        settings = self.settings
        async def check_market(market, key, account_no):
            if market == "us" and "us" not in settings.PAPER_ALLOWED_MARKETS:
                return key, {"status": "disabled_by_config"}
            if not settings.KIS_APP_KEY or not settings.KIS_APP_SECRET or not account_no:
                return key, {"status": "missing_credentials"}
            if self.broker_factory is None:
                return key, {"status": "provider_not_configured"}
            try:
                snapshot = await self.broker_factory(market).account_snapshot()
                return key, {"status": "ok", "source": snapshot.get("source")}
            except Exception as exc:  # noqa: BLE001 - safe provider status only
                response = getattr(exc, "response", None)
                status_code = getattr(response, "status_code", None)
                detail = type(exc).__name__
                if status_code:
                    detail = f"{detail} ({status_code})"
                return key, {"status": "error", "error": detail}

        # KIS paper REST calls share an app-level interval limit. A
        # concurrent diagnostic makes a healthy account look broken with
        # EGW00201, so keep the market checks sequential. Each market has its
        # own account credential check so one missing account cannot mask the
        # other market's actual status.
        markets = (("krx", "kis_krx", settings.KIS_KRX_ACCOUNT_NO),
                   ("us", "kis_us", settings.KIS_US_ACCOUNT_NO))
        for index, (market, key, account_no) in enumerate(markets):
            if index:
                await asyncio.sleep(1.1)
            result[key] = (await check_market(market, key, account_no))[1]
        if self.macro_factory is None:
            result["fred"] = {"status": "provider_not_configured"}
        else:
            try:
                macro = await self.macro_factory(settings.FRED_API_KEY).collect(days=7)
                result["fred"] = {"status": "ok" if macro.get("macro_data_available") else "error",
                                   "source": macro.get("macro_source"), "failures": macro.get("macro_failures")}
            except Exception as exc:  # noqa: BLE001 - safe provider status only
                result["fred"] = {"status": "error", "error": type(exc).__name__}
        if self.news_factory is None or not settings.NEWS_FEEDS:
            result["rss"] = {"status": "not_configured"}
        else:
            try:
                news = await self.news_factory(settings.NEWS_FEEDS).collect()
                result["rss"] = {
                    "status": "ok" if not news.get("feed_failures") else "degraded",
                    "failures": news.get("feed_failures", 0),
                    "events": news.get("news_count", 0),
                }
            except Exception as exc:  # noqa: BLE001 - safe provider status only
                result["rss"] = {"status": "error", "error": type(exc).__name__}
        return result
