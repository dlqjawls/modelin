"""Application queries for readiness and provider configuration status."""


class SystemQueryService:
    def __init__(self, settings, store, *, broker_factory=None, macro_factory=None):
        self.settings = settings
        self.store = store
        self.broker_factory = broker_factory
        self.macro_factory = macro_factory

    def diagnostics(self):
        settings = self.settings
        return {
            "paper_worker": "configured" if settings.PAPER_WORKER_ENABLED and settings.PAPER_DEPLOYMENT_FILE else "disabled",
            "sources": {
                "kis_paper": "configured" if all((settings.KIS_APP_KEY, settings.KIS_APP_SECRET, settings.KIS_ACCOUNT_NO)) else "missing_credentials",
                "kis_overseas_paper": "configured" if all((settings.KIS_APP_KEY, settings.KIS_APP_SECRET, settings.KIS_ACCOUNT_NO)) else "missing_credentials",
                "rss": "configured" if settings.NEWS_FEEDS else "not_configured",
                "opendart": "configured" if settings.OPENDART_API_KEY else "missing_api_key",
                "sec_edgar": "configured" if settings.SEC_USER_AGENT and settings.SEC_CIKS else "missing_user_agent_or_cik",
                "fred_macro": "configured_public_csv" if not settings.FRED_API_KEY else "configured_api",
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
        result = {"kis_krx": {}, "kis_us": {}, "fred": {}}
        settings = self.settings
        credentials = (settings.KIS_APP_KEY, settings.KIS_APP_SECRET, settings.KIS_ACCOUNT_NO)
        if not all(credentials):
            result["kis_krx"] = result["kis_us"] = {"status": "missing_credentials"}
        elif self.broker_factory is None:
            result["kis_krx"] = result["kis_us"] = {"status": "provider_not_configured"}
        else:
            for market, key in (("krx", "kis_krx"), ("us", "kis_us")):
                try:
                    snapshot = await self.broker_factory(market).account_snapshot()
                    result[key] = {"status": "ok", "source": snapshot.get("source")}
                except Exception as exc:  # noqa: BLE001 - safe provider status only
                    result[key] = {"status": "error", "error": type(exc).__name__}
        if self.macro_factory is None:
            result["fred"] = {"status": "provider_not_configured"}
        else:
            try:
                macro = await self.macro_factory(settings.FRED_API_KEY).collect(days=7)
                result["fred"] = {"status": "ok" if macro.get("macro_data_available") else "error",
                                   "source": macro.get("macro_source"), "failures": macro.get("macro_failures")}
            except Exception as exc:  # noqa: BLE001 - safe provider status only
                result["fred"] = {"status": "error", "error": type(exc).__name__}
        return result
