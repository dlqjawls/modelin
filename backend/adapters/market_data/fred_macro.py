"""FRED macro context collector used by the adaptive risk router."""
from datetime import date, timedelta

import httpx


class FredMacroContext:
    SERIES = {"fx": "DEXKOUS", "rate": "DFF", "vix": "VIXCLS", "dxy": "DTWEXBGS", "oil": "DCOILWTICO"}

    def __init__(self, api_key: str, timeout_seconds: float = 5.0):
        self.api_key, self.timeout_seconds = api_key, timeout_seconds

    async def collect(self, days: int = 30) -> dict:
        if not self.api_key:
            return {"macro_configured": False, "macro_failures": 0}
        start = (date.today() - timedelta(days=days)).isoformat()
        values, failures = {}, 0
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for name, series_id in self.SERIES.items():
                try:
                    response = await client.get("https://api.stlouisfed.org/fred/series/observations",
                        params={"api_key": self.api_key, "file_type": "json", "series_id": series_id,
                                "observation_start": start, "sort_order": "asc"})
                    response.raise_for_status()
                    observations = [item for item in response.json().get("observations", [])
                                    if item.get("value") not in {None, ".", ""}]
                    if not observations:
                        raise ValueError("empty FRED series")
                    first, latest = float(observations[0]["value"]), float(observations[-1]["value"])
                    values[name] = {"latest": latest, "change": (latest - first) / first if first else 0.0}
                except (httpx.HTTPError, KeyError, TypeError, ValueError):
                    failures += 1
        result = {"macro_configured": True, "macro_failures": failures,
                  "macro_data_available": bool(values)}
        for name, item in values.items():
            result[f"{name}_latest"], result[f"{name}_change_20d"] = item["latest"], item["change"]
        if failures == len(self.SERIES):
            result["risk_off"] = 1.0
        return result
