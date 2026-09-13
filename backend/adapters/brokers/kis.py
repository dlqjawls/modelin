"""Korea Investment Open API adapter boundary.

The adapter defaults to the KIS paper endpoint. It never becomes live merely
because credentials exist; production registration must be explicit in the
broker registry after a separate review.
"""
from dataclasses import dataclass
from decimal import Decimal
from datetime import date
import time
from typing import Any

import httpx

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

    @property
    def base_url(self):
        return "https://openapivts.koreainvestment.com:29443" if self.environment == "paper" else "https://openapi.koreainvestment.com:9443"

    @property
    def websocket_url(self):
        return "ws://ops.koreainvestment.com:31000" if self.environment == "paper" else "ws://ops.koreainvestment.com:21000"

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

    async def _request(self, method: str, path: str, *, headers=None, params=None, json=None):
        own_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.config.timeout_seconds)
        try:
            response = await client.request(method, self.config.base_url + path, headers=headers, params=params, json=json)
            response.raise_for_status()
            payload = response.json()
            if payload.get("rt_cd") not in (None, "0", 0):
                raise RuntimeError(f"KIS API 오류: {payload.get('msg1', 'unknown')}")
            return payload
        finally:
            if own_client:
                await client.aclose()

    async def _token(self):
        cache_key = self.config.app_key
        cached = self._TOKEN_CACHE.get(cache_key)
        if cached and cached[1] > time.monotonic():
            self._access_token = cached[0]
        if not self._access_token:
            payload = await self._request("POST", "/oauth2/tokenP", json={
                "grant_type": "client_credentials", "appkey": self.config.app_key, "appsecret": self.config.app_secret,
            })
            self._access_token = payload["access_token"]
            self._TOKEN_CACHE[cache_key] = (self._access_token, time.monotonic() + 23 * 60 * 60)
        return self._access_token

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
            positions = []
            for row in payload.get("output1", []):
                positions.append({
                    "symbol": row.get("ovrs_pdno") or row.get("pdno"),
                    "quantity": row.get("ovrs_cblc_qty") or row.get("cblc_qty", "0"),
                    "avg_price": row.get("pchs_avg_pric") or row.get("avg_unpr3", "0"),
                    "market": "us",
                })
            return {"cash": output2.get("frcr_dncl_amt", output2.get("ovrs_tot_amt", "0")),
                    "positions": positions, "source": "kis-overseas"}
        tr_id = "VTTC8434R" if self.config.environment == "paper" else "TTTC8434R"
        payload = await self._request("GET", "/uapi/domestic-stock/v1/trading/inquire-balance",
                                      headers=self._headers(token, tr_id),
                                      params={"CANO": self.config.account_no, "ACNT_PRDT_CD": self.config.product_code,
                                              "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": "01", "UNPR_DVSN": "01",
                                              "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00",
                                              "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""})
        output2 = payload.get("output2", [{}])[0]
        return {"cash": output2.get("dnca_tot_amt", "0"), "positions": payload.get("output1", []), "source": "kis"}

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
        body = {"CANO": self.config.account_no, "ACNT_PRDT_CD": self.config.product_code, "PDNO": request.symbol,
                "ORD_DVSN": "01" if request.limit_price is None else "00", "ORD_QTY": str(request.quantity),
                "ORD_UNPR": "0" if request.limit_price is None else str(request.limit_price)}
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
            row = next((item for item in rows if str(item.get("odno")) == str(broker_order_id)), rows[0] if rows else {})
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
        row = next((item for item in rows if str(item.get("odno")) == str(broker_order_id)), rows[0] if rows else {})
        return {"broker_order_id": broker_order_id, "client_order_id": client_order_id,
                "status": self._status_from_row(row), "filled_quantity": row.get("tot_ccld_qty", "0"),
                "average_price": row.get("avg_prvs", "0"), "raw": row}

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
