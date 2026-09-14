"""Infrastructure composition for the paper runner."""
from dataclasses import dataclass

from adapters.brokers.kis import KISBrokerAdapter, KISConfig
from adapters.market_data.provider_adapter import ProviderMarketDataAdapter
from config import settings
from data.providers.krx_provider import KRXProvider
from data.providers.us_provider import USProvider
from data.persistent_ohlcv_cache import PersistentOHLCVCache


class KISFallbackMarketProvider:
    """Use public history first, then KIS candles when public feeds are empty."""

    def __init__(self, public_provider, broker, *, allow_kis_fallback=True, cache_dir=".market-data-cache"):
        self.public_provider = public_provider
        self.broker = broker
        self.allow_kis_fallback = allow_kis_fallback
        self.disk_cache = PersistentOHLCVCache(cache_dir, public_provider.market.value)

    async def get_tickers(self):
        return await self.public_provider.get_tickers()

    async def get_ohlcv(self, symbol, start_date, end_date, interval="1d"):
        cached = self.disk_cache.get(symbol, start_date, end_date, interval)
        if cached is not None:
            return cached
        frame = await self.public_provider.get_ohlcv(symbol, start_date, end_date, interval)
        if frame is not None and not frame.empty:
            self.disk_cache.set(symbol, start_date, end_date, interval, frame)
            return frame
        if not self.allow_kis_fallback:
            return frame
        return await self.broker.get_ohlcv(symbol, start_date, end_date)


class ExchangeRoutingBroker:
    """Route US paper orders to the KIS exchange selected for each symbol."""

    def __init__(self, brokers, exchange_map):
        self.brokers = brokers
        self.exchange_map = exchange_map
        self.order_brokers = {}

    def _broker_for_symbol(self, symbol):
        exchange = self.exchange_map.get(symbol.upper())
        if exchange not in self.brokers:
            raise ValueError(f"미국 종목 거래소 정보가 없어 주문을 차단합니다: {symbol}")
        return self.brokers[exchange]

    async def get_ohlcv(self, symbol, start_date, end_date):
        return await self._broker_for_symbol(symbol).get_ohlcv(symbol, start_date, end_date)

    async def capabilities(self):
        return await self.brokers["NASD"].capabilities()

    async def account_snapshot(self):
        return await self.brokers["NASD"].account_snapshot()

    async def submit(self, request):
        broker = self._broker_for_symbol(request.symbol)
        result = await broker.submit(request)
        if result.get("broker_order_id"):
            self.order_brokers[str(result["broker_order_id"])] = broker
        return result

    async def cancel(self, broker_order_id):
        broker = self.order_brokers.get(str(broker_order_id))
        if broker is None:
            raise ValueError("재시작 후 거래소를 확인할 수 없는 주문은 취소를 차단합니다.")
        return await broker.cancel(broker_order_id)

    async def lookup_order(self, *, client_order_id=None, broker_order_id=None):
        broker = self.order_brokers.get(str(broker_order_id)) if broker_order_id else None
        if broker is None:
            raise ValueError("주문 거래소를 확인할 수 없어 조회를 차단합니다.")
        return await broker.lookup_order(client_order_id=client_order_id, broker_order_id=broker_order_id)

    async def order_events(self, *, cursor=None):
        # KIS cursor streams are exchange-specific; poll the configured
        # account through the default exchange until persistent routing state
        # is available.
        return await self.brokers["NASD"].order_events(cursor=cursor)


@dataclass(frozen=True)
class PaperRuntime:
    broker: object
    data: object


def build_paper_runtime(deployment: dict) -> PaperRuntime:
    """Build the explicitly paper-only runtime for a KRX or US deployment."""
    market = deployment.get("market")
    if market not in {"krx", "us"}:
        raise ValueError("paper runtime은 KRX 또는 US 시장만 지원합니다.")
    if market not in settings.PAPER_ALLOWED_MARKETS:
        raise ValueError(f"{market} paper 실행은 비활성화되어 있습니다. PAPER_ALLOWED_MARKETS를 확인하세요.")
    account_no = settings.KIS_US_ACCOUNT_NO if market == "us" else settings.KIS_KRX_ACCOUNT_NO
    def make_broker(exchange):
        return KISBrokerAdapter(KISConfig(
            app_key=settings.KIS_APP_KEY,
            app_secret=settings.KIS_APP_SECRET,
            account_no=account_no,
            environment="paper",
            market=market,
            exchange=exchange,
        ))

    if market == "us" and deployment.get("exchange_map"):
        brokers = {exchange: make_broker(exchange) for exchange in ("NASD", "NYSE", "AMEX")}
        broker = ExchangeRoutingBroker(brokers, deployment["exchange_map"])
    else:
        broker = make_broker(deployment.get("exchange", "NASD"))
    public_provider = KRXProvider() if market == "krx" else USProvider()
    provider = KISFallbackMarketProvider(
        public_provider,
        broker,
        # KIS historical endpoints are per-symbol and rate-limited. A full
        # market universe must use the bulk/public history provider; KIS is a
        # safe fallback only for explicit small symbol lists.
        allow_kis_fallback=deployment.get("strategy", {}).get("universe") != "market",
        cache_dir=settings.MARKET_DATA_CACHE_DIR,
    )
    return PaperRuntime(broker=broker, data=ProviderMarketDataAdapter(provider, market))
