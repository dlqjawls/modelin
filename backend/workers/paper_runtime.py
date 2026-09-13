"""Infrastructure composition for the paper runner."""
from dataclasses import dataclass

from adapters.brokers.kis import KISBrokerAdapter, KISConfig
from adapters.market_data.provider_adapter import ProviderMarketDataAdapter
from config import settings
from data.providers.krx_provider import KRXProvider
from data.providers.us_provider import USProvider


@dataclass(frozen=True)
class PaperRuntime:
    broker: object
    data: object


def build_paper_runtime(deployment: dict) -> PaperRuntime:
    """Build the explicitly paper-only runtime for a KRX or US deployment."""
    market = deployment.get("market")
    if market not in {"krx", "us"}:
        raise ValueError("paper runtime은 KRX 또는 US 시장만 지원합니다.")
    broker = KISBrokerAdapter(KISConfig(
        app_key=settings.KIS_APP_KEY,
        app_secret=settings.KIS_APP_SECRET,
        account_no=settings.KIS_ACCOUNT_NO,
        environment="paper",
        market=market,
        exchange=deployment.get("exchange", "NASD"),
    ))
    provider = KRXProvider() if market == "krx" else USProvider()
    return PaperRuntime(broker=broker, data=ProviderMarketDataAdapter(provider, market))
