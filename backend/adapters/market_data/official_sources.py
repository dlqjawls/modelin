"""Official disclosure/event sources with normalized provenance."""
from dataclasses import dataclass
from datetime import date, timedelta

import httpx


@dataclass(frozen=True)
class ExternalEvent:
    event_id: str
    source: str
    title: str
    published_at: str
    url: str
    form: str = ""


class OpenDartClient:
    def __init__(self, api_key: str, timeout_seconds: float = 5.0):
        self.api_key, self.timeout_seconds = api_key, timeout_seconds

    async def filings(self, *, corp_code: str, days: int = 3) -> list[ExternalEvent]:
        if not self.api_key or not corp_code:
            return []
        end = date.today()
        params = {"crtfc_key": self.api_key, "corp_code": corp_code,
                  "bgn_de": (end - timedelta(days=days)).strftime("%Y%m%d"),
                  "end_de": end.strftime("%Y%m%d"), "page_no": 1, "page_count": 100}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get("https://opendart.fss.or.kr/api/list.json", params=params)
            response.raise_for_status()
            payload = response.json()
        if str(payload.get("status")) not in {"000", "0"}:
            return []
        return [ExternalEvent(str(item.get("rcept_no")), "opendart", item.get("report_nm", ""),
                              item.get("rcept_dt", ""), "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + str(item.get("rcept_no")),
                              item.get("pblntf_ty", "")) for item in payload.get("list", [])]


class SecSubmissionsClient:
    def __init__(self, user_agent: str, timeout_seconds: float = 5.0):
        self.user_agent, self.timeout_seconds = user_agent, timeout_seconds

    async def filings(self, cik: str, limit: int = 40) -> list[ExternalEvent]:
        cik10 = str(cik).zfill(10)
        if not self.user_agent or not cik:
            return []
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout_seconds, headers=headers) as client:
            response = await client.get(f"https://data.sec.gov/submissions/CIK{cik10}.json")
            response.raise_for_status()
            payload = response.json()
        recent = payload.get("filings", {}).get("recent", {})
        events = []
        for i, accession in enumerate(recent.get("accessionNumber", [])[:limit]):
            form = recent.get("form", [""] * (i + 1))[i]
            filed = recent.get("filingDate", [""] * (i + 1))[i]
            primary = recent.get("primaryDocument", [""] * (i + 1))[i]
            events.append(ExternalEvent(accession, "sec", f"{form} filing", filed,
                                        f"https://www.sec.gov/Archives/edgar/data/{int(cik10)}/{accession.replace('-', '')}/{primary}", form))
        return events
