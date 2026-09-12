"""Small provider-neutral RSS context collector.

Feed failures never create a positive trade signal. They return a degraded
context so the regime router can reduce risk or block a cycle.
"""
import xml.etree.ElementTree as ET

import httpx

from core.market_context import NewsEventEngine


class RSSNewsContext:
    def __init__(self, feeds: list[str], timeout_seconds: float = 5.0):
        self.feeds = feeds
        self.timeout_seconds = timeout_seconds
        self.engine = NewsEventEngine()

    async def collect(self) -> dict:
        events = []
        failures = 0
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            for url in self.feeds:
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    root = ET.fromstring(response.text)
                    for item in root.findall(".//item")[:20]:
                        title = (item.findtext("title") or "").strip()
                        if title:
                            events.append(self.engine.classify(title, url, item.findtext("pubDate", "")))
                except (httpx.HTTPError, ET.ParseError):
                    failures += 1
        result = self.engine.aggregate(events)
        result["feed_failures"] = failures
        if failures and not events:
            result["risk_off"] = 1.0
            result["news_confidence"] = 0.0
        return result
