"""Convert macro and news observations into bounded risk context values."""
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class NewsEvent:
    title: str
    source: str
    published_at: str
    category: str
    impact: float
    confidence: float


class NewsEventEngine:
    _rules = {
        "geopolitical": ("war", "전쟁", "제재", "sanction", "missile", "침공"),
        "financial_stress": ("bank failure", "default", "파산", "디폴트", "유동성 위기"),
        "rate_shock": ("rate hike", "금리 인상", "긴축", "hawkish", "금리 급등"),
        "earnings_positive": ("beat", "호실적", "상향", "record profit", "어닝 서프라이즈"),
        "earnings_negative": ("miss", "어닝 쇼크", "하향", "profit warning", "실적 악화"),
    }

    def classify(self, title: str, source: str = "unknown", published_at: str = "") -> NewsEvent:
        text = (title or "").lower()
        category = "neutral"
        for candidate, keywords in self._rules.items():
            if any(keyword in text for keyword in keywords):
                category = candidate
                break
        impact = {"geopolitical": 1.0, "financial_stress": 1.0, "rate_shock": 0.7,
                  "earnings_positive": -0.25, "earnings_negative": 0.5}.get(category, 0.0)
        confidence = 0.8 if category != "neutral" else 0.2
        return NewsEvent(title, source, published_at, category, impact, confidence)

    def aggregate(self, events: Iterable[NewsEvent]) -> dict:
        events = list(events)
        if not events:
            return {"risk_off": 0.0, "news_confidence": 0.0, "news_count": 0}
        weighted = sum(max(0.0, event.impact) * event.confidence for event in events)
        confidence = min(1.0, sum(event.confidence for event in events) / max(3, len(events)))
        return {"risk_off": min(1.0, weighted / 2.0), "news_confidence": confidence,
                "news_count": len(events)}


class MacroContext:
    """Bounded numerical context; data providers can be swapped later."""

    @staticmethod
    def build(*, fx_change_20d=0.0, rate_change_20d=0.0, volatility=0.0,
              news: dict | None = None) -> dict:
        news = news or {}
        return {"fx_change_20d": float(fx_change_20d), "rate_change_20d": float(rate_change_20d),
                "volatility": float(volatility), "risk_off": min(1.0, max(float(news.get("risk_off", 0.0)),
                                                                           abs(float(rate_change_20d)) / 2.0,
                                                                           abs(float(fx_change_20d)) / 0.16)),
                "news_confidence": float(news.get("news_confidence", 0.0))}
