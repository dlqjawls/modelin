"""Application queries for readiness and provider configuration status."""


class SystemQueryService:
    def __init__(self, settings, store):
        self.settings = settings
        self.store = store

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
