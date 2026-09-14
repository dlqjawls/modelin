"""Korea Investment Open API adapter boundary.

The adapter defaults to the KIS paper endpoint. It never becomes live merely
because credentials exist; production registration must be explicit in the
broker registry after a separate review.
"""
from dataclasses import dataclass
from decimal import Decimal
from datetime import date
import asyncio
import time
import json
import hashlib
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from ports.broker import BrokerCapabilities, OrderRequest


@dataclass(frozen=True)
class KISConfig:
    app_key: str
    app_secret: str
    account_no: str
    product_code: str = "01"
    environment: str = "paper"
    timeout_seconds: float = 10.0
    market: str = "krx"
    exchange: str = "NASD"
    currency: str = "USD"
    token_cache_path: str = ".kis-token-cache.json"

    @property
    def base_url(self):
        return "https://openapivts.koreainvestment.com:29443" if self.environment == "paper" else "https://openapi.koreainvestment.com:9443"

    @property
    def websocket_url(self):
        return "ws://ops.koreainvestment.com:31000" if self.environment == "paper" else "ws://ops.koreainvestment.com:21000"

    @property
    def quote_exchange(self):
        """Exchange codes used by overseas price APIs (orders use NASD/NYSE/AMEX)."""
        return {"NASD": "NAS", "NYSE": "NYS", "AMEX": "AMS"}.get(self.exchange, self.exchange)

    def __post_init__(self):
        if self.environment not in {"paper", "live"}:
            raise ValueError("KIS environment는 paper 또는 live여야 합니다.")
        if len(self.account_no) != 8 or not self.account_no.isdigit():
            raise ValueError("KIS account_no는 8자리 숫자여야 합니다.")
        if len(self.product_code) != 2 or not self.product_code.isdigit():
            raise ValueError("KIS product_code는 2자리 숫자여야 합니다.")
        if self.market not in {"krx", "us"}:
            raise ValueError("KIS market은 krx 또는 us여야 합니다.")
        if self.market == "us" and self.exchange not in {"NASD", "NYSE", "AMEX"}:
            raise ValueError("미국 KIS exchange는 NASD, NYSE 또는 AMEX여야 합니다.")


class KISBrokerAdapter:
    """REST adapter for KIS domestic and US overseas cash orders."""

    def __init__(self, config: KISConfig, client: httpx.AsyncClient | None = None):
        self.config = config
        self._client = client
        self._access_token = None
        self._token_lock = asyncio.Lock()
        self._last_token_request_at = 0.0

    @staticmethod
    def _actionable_error(detail: str) -> str:
        """Keep the broker code while adding the next operator action."""
        actions = {
            "EGW00123": "KIS access token이 만료되었거나 무효입니다. 잠시 후 토큰을 재발급하세요.",
            "EGW00133": "KIS 토큰 발급 요청 한도를 초과했습니다. 반복 실행을 멈추고 잠시 후 다시 시도하세요.",
            "IGW00013": "KIS 주문 가능 여부를 확인하세요. 모의계좌 권한·예수금·주문 가능 수량을 확인해야 합니다.",
        }
        for code, action in actions.items():
            if code in detail:
                return f"{detail} | 조치: {action}"
        return detail

    @staticmethod
    def _order_price(value) -> str:
        """Format domestic order prices as KIS-compatible decimal strings."""
        if value is None:
            return "0"
        number = Decimal(str(value))
        if not number.is_finite() or number < 0:
            raise ValueError("주문 가격은 0 이상 유한수여야 합니다.")
        formatted = format(number, "f")
        if "." in formatted:
            formatted = formatted.rstrip("0").rstrip(".")
        return formatted or "0"

    @staticmethod
    def _domestic_order_quantity(value) -> str:
        """Domestic stock orders accept whole shares only."""
        quantity = Decimal(str(value))
        whole = int(quantity)
        if quantity <= 0 or whole < 1:
            raise ValueError("국내 주식 주문 수량은 1주 이상의 정수여야 합니다.")
        return str(whole)

    async def _request(self, method: str, path: str, *, headers=None, params=None, json=None,
                       _retry_token=True, _retry_rate_limit=False, _rate_limit_attempt=0):
        own_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.config.timeout_seconds)
        try:
            response = await client.request(method, self.config.base_url + path, headers=headers, params=params, json=json)
            if response.is_error:
                # Preserve KIS's response code/message; httpx's generic
                # exception otherwise hides the broker's actionable reason.
                detail = self._actionable_error(response.text[:500])
                if (_retry_token and headers and "EGW00123" in detail
                        and headers.get("authorization")):
                    # KIS can invalidate a persisted token before its nominal
                    # expiry. Refresh once, then replay the read/order request.
                    self._invalidate_token()
                    await asyncio.sleep(1.1)
                    refreshed = await self._token()
                    retry_headers = dict(headers)
                    retry_headers["authorization"] = f"Bearer {refreshed}"
                    return await self._request(method, path, headers=retry_headers,
                                               params=params, json=json, _retry_token=False)
                if (_retry_rate_limit and "EGW00201" in detail and _rate_limit_attempt < 3):
                    # The domestic buyability endpoint can be throttled even
                    # when the surrounding order loop is serialized. Retry
                    # only this preflight read; never replay an order request.
                    await asyncio.sleep(2 ** _rate_limit_attempt)
                    return await self._request(
                        method, path, headers=headers, params=params, json=json,
                        _retry_token=_retry_token, _retry_rate_limit=True,
                        _rate_limit_attempt=_rate_limit_attempt + 1,
                    )
                raise RuntimeError(f"KIS HTTP {response.status_code} {path}: {detail}")
            payload = response.json()
            if payload.get("rt_cd") not in (None, "0", 0):
                detail = f"{payload.get('msg_cd', '')} {payload.get('msg1', 'unknown')}".strip()
                raise RuntimeError(f"KIS API 오류: {self._actionable_error(detail)}")
            return payload
        finally:
            if own_client:
                await client.aclose()

    def _invalidate_token(self):
        self._access_token = None
        self._TOKEN_CACHE.pop(self.config.app_key, None)
        path = Path(self.config.token_cache_path)
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            data.pop(hashlib.sha256(self.config.app_key.encode()).hexdigest(), None)
            path.write_text(json.dumps(data), encoding="utf-8")
        except (OSError, ValueError, TypeError):
            pass

    async def _token(self):
        cache_key = self.config.app_key
        cached = self._TOKEN_CACHE.get(cache_key)
        if cached and cached[1] > time.monotonic():
            self._access_token = cached[0]
        if not self._access_token and self._client is None:
            persisted = self._read_persisted_token(cache_key)
            if persisted and persisted[1] > time.time():
                self._access_token = persisted[0]
                self._TOKEN_CACHE[cache_key] = (self._access_token, time.monotonic() + min(persisted[1] - time.time(), 23 * 60 * 60))
        if not self._access_token:
            async with self._token_lock:
                # Another concurrent request may have obtained the token while
                # this coroutine was waiting for the app-level rate limit.
                cached = self._TOKEN_CACHE.get(cache_key)
                if cached and cached[1] > time.monotonic():
                    self._access_token = cached[0]
                if not self._access_token:
                    wait = 1.1 - (time.monotonic() - self._last_token_request_at)
                    if wait > 0:
                        await asyncio.sleep(wait)
                    self._last_token_request_at = time.monotonic()
                    payload = await self._request("POST", "/oauth2/tokenP", json={
                        "grant_type": "client_credentials", "appkey": self.config.app_key, "appsecret": self.config.app_secret,
                    })
                    self._access_token = payload["access_token"]
                    expires_in = int(payload.get("expires_in", 86400))
                    self._TOKEN_CACHE[cache_key] = (self._access_token, time.monotonic() + min(expires_in, 23 * 60 * 60))
                    if self._client is None:
                        self._write_persisted_token(cache_key, self._access_token, time.time() + min(expires_in, 23 * 60 * 60))
        return self._access_token

    def _read_persisted_token(self, cache_key):
        try:
            data = json.loads(Path(self.config.token_cache_path).read_text(encoding="utf-8"))
            item = data.get(hashlib.sha256(cache_key.encode()).hexdigest())
            if item and item.get("token") and float(item.get("expires_at", 0)) > time.time():
                return item["token"], float(item["expires_at"])
        except (OSError, ValueError, TypeError):
            return None
        return None

    def _write_persisted_token(self, cache_key, token, expires_at):
        path = Path(self.config.token_cache_path)
        try:
            data = {}
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
            data[hashlib.sha256(cache_key.encode()).hexdigest()] = {"token": token, "expires_at": expires_at}
            path.write_text(json.dumps(data), encoding="utf-8")
        except (OSError, ValueError, TypeError):
            # Token persistence is an optimization; a read-only cache failure
            # must never change broker behavior.
            return

    async def _hashkey(self, body):
        payload = await self._request("POST", "/uapi/hashkey", headers={
            "content-type": "application/json; charset=utf-8",
            "appkey": self.config.app_key, "appsecret": self.config.app_secret,
        }, json=body)
        return payload["HASH"]

    async def websocket_subscription(self, symbols: list[str]) -> dict:
        """Return an authenticated subscription payload for execution notices.

        The websocket consumer owns reconnects and feeds the same journal as
        REST polling; this method only prepares connection credentials.
        """
        if not symbols or any(not symbol.isdigit() for symbol in symbols):
            raise ValueError("KIS 국내주식 웹소켓 종목코드가 필요합니다.")
        approval = await self._request("POST", "/oauth2/Approval", json={
            "grant_type": "client_credentials", "appkey": self.config.app_key,
            "secretkey": self.config.app_secret,
        })
        approval_key = approval.get("approval_key")
        if not approval_key:
            raise RuntimeError("KIS websocket approval key가 없습니다.")
        return {
            "url": self.config.websocket_url,
            "approval_key": approval_key,
            "subscriptions": [{"tr_id": "H0STCNI0", "tr_key": symbol} for symbol in symbols],
        }

    async def capabilities(self):
        return BrokerCapabilities(self.config.market, "kis", self.config.environment == "paper", False,
                                   ("market", "limit"), True)

    async def quote(self, symbol: str) -> dict:
        """Read the current KIS quote without creating or changing an order."""
        if not symbol or not symbol.strip():
            raise ValueError("KIS 현재가 조회에는 종목코드가 필요합니다.")
        token = await self._token()
        if self.config.market == "us":
            payload = await self._request(
                "GET", "/uapi/overseas-price/v1/quotations/price",
                headers=self._headers(token, "HHDFS00000300"),
                params={"AUTH": "", "EXCD": self.config.quote_exchange, "SYMB": symbol.upper()},
            )
            row = payload.get("output", {})
            return {
                "symbol": symbol.upper(), "market": "us", "source": "kis-overseas",
                "price": row.get("last") or row.get("ovrs_nmix_prpr"),
                "change": row.get("diff") or row.get("ovrs_nmix_prdy_vrss"),
                "change_rate": row.get("rate") or row.get("prdy_ctrt"),
                "raw": row,
            }
        payload = await self._request(
            "GET", "/uapi/domestic-stock/v1/quotations/inquire-price",
            headers=self._headers(token, "FHKST01010100"),
            params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol},
        )
        row = payload.get("output", {})
        return {
            "symbol": symbol, "market": "krx", "source": "kis",
            "price": row.get("stck_prpr"),
            "change": row.get("prdy_vrss"),
            "change_rate": row.get("prdy_ctrt"),
            "raw": row,
        }

    async def get_ohlcv(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Read daily candles from the KIS paper market-data endpoints."""
        token = await self._token()
        if self.config.market == "us":
            payload = await self._request(
                "GET", "/uapi/overseas-price/v1/quotations/inquire-daily-chartprice",
                headers=self._headers(token, "HHDFS76240000"),
                params={
                    "AUTH": "", "EXCD": self.config.quote_exchange, "SYMB": symbol.upper(),
                    "GUBN": "0", "BYMD": end_date.replace("-", ""), "MODP": "1",
                },
            )
            rows = payload.get("output2", [])
            records = [{
                "date": row.get("xymd") or row.get("stck_bsop_date"),
                "open": row.get("open") or row.get("ovrs_oprc"),
                "high": row.get("high") or row.get("ovrs_hgpr"),
                "low": row.get("low") or row.get("ovrs_lwpr"),
                "close": row.get("clos") or row.get("ovrs_prpr"),
                "volume": row.get("tvol") or row.get("acml_vol", 0),
            } for row in rows]
        else:
            payload = await self._request(
                "GET", "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
                headers=self._headers(token, "FHKST03010100"),
                params={
                    "FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol,
                    "FID_INPUT_DATE_1": start_date.replace("-", ""),
                    "FID_INPUT_DATE_2": end_date.replace("-", ""),
                    "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "1",
                },
            )
            rows = payload.get("output2", [])
            records = [{
                "date": row.get("stck_bsop_date"), "open": row.get("stck_oprc"),
                "high": row.get("stck_hgpr"), "low": row.get("stck_lwpr"),
                "close": row.get("stck_clpr"), "volume": row.get("acml_vol", 0),
            } for row in rows]
        if not records:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        frame = pd.DataFrame(records)
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        for column in ("open", "high", "low", "close", "volume"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.dropna(subset=["date", "open", "high", "low", "close"])
        frame = frame[(frame["date"] >= pd.Timestamp(start_date)) & (frame["date"] <= pd.Timestamp(end_date))]
        return frame.set_index("date")[["open", "high", "low", "close", "volume"]].sort_index()

    def _headers(self, token, tr_id):
        return {"content-type": "application/json; charset=utf-8", "authorization": f"Bearer {token}",
                "appkey": self.config.app_key, "appsecret": self.config.app_secret, "tr_id": tr_id, "custtype": "P"}

    async def account_snapshot(self):
        token = await self._token()
        if self.config.market == "us":
            tr_id = "VTTS3012R" if self.config.environment == "paper" else "TTTS3012R"
            payload = await self._request("GET", "/uapi/overseas-stock/v1/trading/inquire-balance",
                headers=self._headers(token, tr_id), params={
                    "CANO": self.config.account_no, "ACNT_PRDT_CD": self.config.product_code,
                    "OVRS_EXCG_CD": self.config.exchange, "TR_CRCY_CD": self.config.currency,
                    "CTX_AREA_FK200": "", "CTX_AREA_NK200": ""})
            output2 = payload.get("output2", {})
            if isinstance(output2, list):
                output2 = output2[0] if output2 else {}
            raw_positions = payload.get("output1", [])
            if isinstance(raw_positions, dict):
                raw_positions = [raw_positions]
            positions = []
            position_value = Decimal("0")
            for row in raw_positions:
                quantity = row.get("ovrs_cblc_qty") or row.get("cblc_qty", "0")
                evaluated = row.get("ovrs_stck_evlu_amt") or row.get("evlu_amt") or "0"
                try:
                    position_value += Decimal(str(evaluated or "0"))
                except Exception:
                    pass
                positions.append({
                    "symbol": row.get("ovrs_pdno") or row.get("pdno"),
                    "quantity": quantity,
                    "avg_price": row.get("pchs_avg_pric") or row.get("avg_unpr3", "0"),
                    "market_value": evaluated,
                    "market": "us",
                })
            cash = (output2.get("frcr_dncl_amt") or output2.get("frcr_dncl_amt_2")
                    or output2.get("ord_psbl_frcr_amt") or "0")
            reported_total = (output2.get("ovrs_tot_evlu_amt") or output2.get("ovrs_tot_amt")
                              or output2.get("tot_evlu_amt") or "0")
            try:
                total_assets = Decimal(str(reported_total or "0"))
                if total_assets <= 0:
                    total_assets = Decimal(str(cash or "0")) + position_value
            except Exception:
                total_assets = Decimal(str(cash or "0")) + position_value
            return {"cash": cash,
                    "total_assets": str(total_assets),
                    "positions": positions, "source": "kis-overseas",
                    "cash_present": cash not in (None, ""),
                    "total_assets_present": total_assets is not None}
        tr_id = "VTTC8434R" if self.config.environment == "paper" else "TTTC8434R"
        payload = await self._request("GET", "/uapi/domestic-stock/v1/trading/inquire-balance",
                                      headers=self._headers(token, tr_id),
                                      params={"CANO": self.config.account_no, "ACNT_PRDT_CD": self.config.product_code,
                                              "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": "01", "UNPR_DVSN": "01",
                                              "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00",
                                              "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""})
        output2 = payload.get("output2", [{}])[0]
        cash = output2.get("dnca_tot_amt", "0")
        total_assets = output2.get("tot_evlu_amt", output2.get("nass_amt", cash))
        raw_positions = payload.get("output1", [])
        if isinstance(raw_positions, dict):
            raw_positions = [raw_positions]
        positions = [{
            "symbol": row.get("pdno") or row.get("stck_shrn_iscd"),
            "quantity": row.get("hldg_qty") or row.get("ord_psbl_qty", "0"),
            "avg_price": row.get("pchs_avg_pric") or row.get("pchs_avg_pric2", "0"),
            "market_value": row.get("evlu_amt") or row.get("evlu_amt2", "0"),
            "market": "krx",
        } for row in raw_positions if row.get("pdno") or row.get("stck_shrn_iscd")]
        return {"cash": cash, "total_assets": total_assets,
                "positions": positions, "source": "kis",
                "cash_present": cash not in (None, ""),
                "total_assets_present": total_assets not in (None, "")}

    async def submit(self, request: OrderRequest):
        if request.account_id != self.config.account_no:
            raise ValueError("KIS 계좌 식별자가 일치하지 않습니다.")
        if request.side not in {"buy", "sell"} or request.quantity is None:
            raise ValueError("KIS 국내주식 주문은 side와 quantity가 필요합니다.")
        token = await self._token()
        buy = request.side == "buy"
        if self.config.market == "us":
            tr_id = ("VTTT1002U" if buy else "VTTT1006U") if self.config.environment == "paper" else ("TTTT1002U" if buy else "TTTT1006U")
            body = {"CANO": self.config.account_no, "ACNT_PRDT_CD": self.config.product_code,
                    "OVRS_EXCG_CD": self.config.exchange, "PDNO": request.symbol,
                    "ORD_DVSN": "00" if request.limit_price is not None else "01",
                    "ORD_QTY": str(request.quantity), "OVRS_ORD_UNPR": str(request.limit_price or "0"),
                    "SLL_TYPE": "" if buy else "00", "ORD_SVR_DVSN_CD": "0"}
            headers = self._headers(token, tr_id)
            headers["hashkey"] = await self._hashkey(body)
            payload = await self._request("POST", "/uapi/overseas-stock/v1/trading/order",
                                          headers=headers, json=body)
            output = payload.get("output", {})
            return {"broker_order_id": output.get("ODNO"), "client_order_id": request.client_order_id,
                    "status": "acknowledged", "raw": payload}
        tr_id = ("VTTC0802U" if buy else "VTTC0801U") if self.config.environment == "paper" else ("TTTC0802U" if buy else "TTTC0801U")
        order_quantity = self._domestic_order_quantity(request.quantity)
        # Ask KIS for the account's current buyable amount before submitting.
        # This turns opaque order rejections into a deterministic blocked
        # decision and avoids sending an order the account cannot accept.
        if buy:
            order_price = self._order_price(request.limit_price)
            check_tr_id = "VTTC8908R" if self.config.environment == "paper" else "TTTC8908R"
            check = await self._request(
                "GET", "/uapi/domestic-stock/v1/trading/inquire-psbl-order",
                headers=self._headers(token, check_tr_id),
                params={
                    "CANO": self.config.account_no,
                    "ACNT_PRDT_CD": self.config.product_code,
                    "PDNO": request.symbol,
                    "ORD_UNPR": order_price,
                    "ORD_DVSN": "00" if request.limit_price is not None else "01",
                    "CMA_EVLU_AMT_ICLD_YN": "N",
                    "OVRS_ICLD_YN": "N",
                },
                _retry_rate_limit=True,
            )
            output = check.get("output", {})
            available = output.get("ord_psbl_cash")
            if available not in (None, "") and Decimal(str(available)) < Decimal(order_quantity) * Decimal(str(request.limit_price or 0)):
                raise RuntimeError(f"KIS 주문 차단: 주문가능금액 부족 (가능금액={available})")
        body = {"CANO": self.config.account_no, "ACNT_PRDT_CD": self.config.product_code, "PDNO": request.symbol,
                "ORD_DVSN": "01" if request.limit_price is None else "00", "ORD_QTY": order_quantity,
                "ORD_UNPR": self._order_price(request.limit_price),
                # Required by the current domestic stock order contract.
                "EXCG_ID_DVSN_CD": "KRX",
                "SLL_TYPE": "" if buy else "01",
                "CNDT_PRIC": "0"}
        headers = self._headers(token, tr_id)
        headers["hashkey"] = await self._hashkey(body)
        payload = await self._request("POST", "/uapi/domestic-stock/v1/trading/order-cash",
                                      headers=headers, json=body)
        output = payload.get("output", {})
        return {"broker_order_id": output.get("ODNO"), "client_order_id": request.client_order_id,
                "status": "acknowledged", "raw": payload}

    async def lookup_order(self, *, client_order_id=None, broker_order_id=None):
        if not broker_order_id:
            raise ValueError("KIS 주문조회에는 broker_order_id가 필요합니다.")
        token = await self._token()
        today = date.today().strftime("%Y%m%d")
        if self.config.market == "us":
            tr_id = "VTTS3035R" if self.config.environment == "paper" else "TTTS3035R"
            payload = await self._request("GET", "/uapi/overseas-stock/v1/trading/inquire-ccnl",
                headers=self._headers(token, tr_id), params={
                    "CANO": self.config.account_no, "ACNT_PRDT_CD": self.config.product_code,
                    "PDNO": "", "ORD_STRT_DT": today, "ORD_END_DT": today,
                    "SLL_BUY_DVSN": "00", "CCLD_NCCS_DVSN": "00",
                    "OVRS_EXCG_CD": self.config.exchange, "SORT_SQN": "DS",
                    "ORD_DT": today, "ORD_GNO_BRNO": "", "ODNO": broker_order_id,
                    "CTX_AREA_NK200": "", "CTX_AREA_FK200": ""})
            rows = payload.get("output", payload.get("output1", []))
            row = next((item for item in rows if self._same_order_id(item.get("odno"), broker_order_id)), rows[0] if rows else {})
            return {"broker_order_id": broker_order_id, "client_order_id": client_order_id,
                    "status": self._status_from_overseas_row(row),
                    "filled_quantity": row.get("ft_ccld_qty", row.get("ccld_qty", "0")),
                    "average_price": row.get("ft_ccld_unpr3", row.get("ccld_unpr", "0")), "raw": row}
        tr_id = "VTTC8001R" if self.config.environment == "paper" else "TTTC8001R"
        payload = await self._request("GET", "/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
            headers=self._headers(token, tr_id), params={
                "CANO": self.config.account_no, "ACNT_PRDT_CD": self.config.product_code,
                "INQR_STRT_DT": today, "INQR_END_DT": today, "SLL_BUY_DVSN_CD": "00",
                "INQR_DVSN": "00", "PDNO": "", "CCLD_DVSN": "00", "ORD_GNO_BRNO": "",
                "ODNO": broker_order_id, "INQR_DVSN_3": "00", "INQR_DVSN_1": "",
                "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""})
        rows = payload.get("output1", [])
        row = next((item for item in rows if self._same_order_id(item.get("odno"), broker_order_id)), rows[0] if rows else {})
        return {"broker_order_id": broker_order_id, "client_order_id": client_order_id,
                "status": self._status_from_row(row), "filled_quantity": row.get("tot_ccld_qty", "0"),
                "average_price": row.get("avg_prvs", "0"), "raw": row}

    @staticmethod
    def _same_order_id(left, right):
        """KIS may pad overseas order numbers with leading zeroes."""
        left_text, right_text = str(left or "").strip(), str(right or "").strip()
        if left_text.isdigit() and right_text.isdigit():
            return int(left_text) == int(right_text)
        return left_text == right_text

    @staticmethod
    def _status_from_row(row):
        if not row:
            return "unknown"
        if str(row.get("tot_ccld_qty", "0")) == str(row.get("ord_qty", "-1")):
            return "filled"
        if str(row.get("ord_tmd", "")) and str(row.get("rmn_qty", "0")) not in {"0", "0.0", ""}:
            return "partially_filled"
        return "acknowledged"

    @staticmethod
    def _status_from_overseas_row(row):
        if not row:
            return "unknown"
        filled = row.get("ft_ccld_qty", row.get("ccld_qty", "0"))
        ordered = row.get("ft_ord_qty", row.get("ord_qty", "-1"))
        if str(filled) == str(ordered):
            return "filled"
        if str(filled) not in {"0", "0.0", ""}:
            return "partially_filled"
        return "acknowledged"

    async def order_events(self, *, cursor=None):
        """Poll today's order/contract records as a restart-safe event page.

        WebSocket execution notices can be added later; REST polling remains
        the reconciliation source of truth when a process reconnects.
        """
        token = await self._token()
        today = date.today().strftime("%Y%m%d")
        if self.config.market == "us":
            tr_id = "VTTS3035R" if self.config.environment == "paper" else "TTTS3035R"
            payload = await self._request("GET", "/uapi/overseas-stock/v1/trading/inquire-ccnl",
                headers=self._headers(token, tr_id), params={
                    "CANO": self.config.account_no, "ACNT_PRDT_CD": self.config.product_code,
                    "PDNO": "", "ORD_STRT_DT": today, "ORD_END_DT": today,
                    "SLL_BUY_DVSN": "00", "CCLD_NCCS_DVSN": "00",
                    "OVRS_EXCG_CD": self.config.exchange, "SORT_SQN": "DS",
                    "ORD_DT": today, "ORD_GNO_BRNO": "", "ODNO": "",
                    "CTX_AREA_NK200": "", "CTX_AREA_FK200": ""})
            events = []
            for row in payload.get("output", payload.get("output1", [])):
                order_id = str(row.get("odno", ""))
                event_id = f"{order_id}:{row.get('ft_ccld_qty', row.get('ccld_qty', '0'))}:{row.get('ord_tmd', '')}"
                if cursor and event_id <= cursor:
                    continue
                events.append({"event_id": event_id, "broker_order_id": order_id,
                               "status": self._status_from_overseas_row(row),
                               "filled_quantity": row.get("ft_ccld_qty", row.get("ccld_qty", "0")),
                               "average_price": row.get("ft_ccld_unpr3", row.get("ccld_unpr", "0")), "raw": row})
            events.sort(key=lambda item: item["event_id"])
            return {"events": events, "next_cursor": events[-1]["event_id"] if events else cursor}
        tr_id = "VTTC8001R" if self.config.environment == "paper" else "TTTC8001R"
        payload = await self._request("GET", "/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
            headers=self._headers(token, tr_id), params={
                "CANO": self.config.account_no, "ACNT_PRDT_CD": self.config.product_code,
                "INQR_STRT_DT": today, "INQR_END_DT": today, "SLL_BUY_DVSN_CD": "00",
                "INQR_DVSN": "00", "PDNO": "", "CCLD_DVSN": "00", "ORD_GNO_BRNO": "",
                "ODNO": "", "INQR_DVSN_3": "00", "INQR_DVSN_1": "",
                "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""})
        events = []
        for row in payload.get("output1", []):
            order_id = str(row.get("odno", ""))
            event_id = f"{order_id}:{row.get('tot_ccld_qty', '0')}:{row.get('ord_tmd', '')}"
            if cursor and event_id <= cursor:
                continue
            events.append({"event_id": event_id, "broker_order_id": order_id,
                           "status": self._status_from_row(row),
                           "filled_quantity": row.get("tot_ccld_qty", "0"),
                           "average_price": row.get("avg_prvs", "0"), "raw": row})
        events.sort(key=lambda item: item["event_id"])
        return {"events": events, "next_cursor": events[-1]["event_id"] if events else cursor}

    async def cancel(self, broker_order_id: str):
        if not broker_order_id:
            raise ValueError("KIS 취소에는 broker_order_id가 필요합니다.")
        token = await self._token()
        if self.config.market == "us":
            tr_id = "VTTT1004U" if self.config.environment == "paper" else "TTTT1004U"
            body = {"CANO": self.config.account_no, "ACNT_PRDT_CD": self.config.product_code,
                    "OVRS_EXCG_CD": self.config.exchange, "PDNO": "",
                    "ORGN_ODNO": broker_order_id, "RVSE_CNCL_DVSN_CD": "02",
                    "ORD_QTY": "0", "OVRS_ORD_UNPR": "0", "MGCO_APTM_ODNO": "",
                    "ORD_SVR_DVSN_CD": "0"}
            headers = self._headers(token, tr_id)
            headers["hashkey"] = await self._hashkey(body)
            payload = await self._request("POST", "/uapi/overseas-stock/v1/trading/order-rvsecncl",
                                          headers=headers, json=body)
            return {"broker_order_id": payload.get("output", {}).get("ODNO", broker_order_id),
                    "status": "cancel_requested", "raw": payload}
        body = {"CANO": self.config.account_no, "ACNT_PRDT_CD": self.config.product_code,
                "KRX_FWDG_ORD_ORGNO": "", "ORGN_ODNO": broker_order_id,
                "ORD_DVSN": "01", "RVSE_CNCL_DVSN_CD": "02", "ORD_QTY": "0",
                "ORD_UNPR": "0", "QTY_ALL_ORD_YN": "Y"}
        tr_id = "VTTC0803U" if self.config.environment == "paper" else "TTTC0803U"
        headers = self._headers(token, tr_id)
        headers["hashkey"] = await self._hashkey(body)
        payload = await self._request("POST", "/uapi/domestic-stock/v1/trading/order-rvsecncl",
                                      headers=headers, json=body)
        return {"broker_order_id": payload.get("output", {}).get("ODNO", broker_order_id),
                "status": "cancel_requested", "raw": payload}
    _TOKEN_CACHE: dict[str, tuple[str, float]] = {}
