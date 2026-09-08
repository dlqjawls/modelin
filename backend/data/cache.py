"""
Modelin - 인메모리 데이터 캐시

API 호출 부담을 줄이기 위한 TTL 기반 캐시.
"""
import time
from typing import Any
from config import settings


class DataCache:
    """TTL 기반 인메모리 캐시"""

    def __init__(self, default_ttl: int | None = None):
        self._cache: dict[str, dict[str, Any]] = {}
        self._default_ttl = default_ttl or settings.CACHE_TTL_SECONDS

    def get(self, key: str) -> Any | None:
        """캐시에서 값을 가져옵니다. 만료되었으면 None 반환."""
        if key not in self._cache:
            return None
        entry = self._cache[key]
        if time.time() > entry["expires_at"]:
            del self._cache[key]
            return None
        return entry["value"]

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """캐시에 값을 저장합니다."""
        expires_at = time.time() + (ttl or self._default_ttl)
        self._cache[key] = {"value": value, "expires_at": expires_at}

    def invalidate(self, key: str) -> None:
        """특정 키의 캐시를 무효화합니다."""
        self._cache.pop(key, None)

    def clear(self) -> None:
        """모든 캐시를 초기화합니다."""
        self._cache.clear()

    def cleanup(self) -> int:
        """만료된 캐시 항목을 정리합니다. 정리된 항목 수 반환."""
        now = time.time()
        expired_keys = [k for k, v in self._cache.items() if now > v["expires_at"]]
        for key in expired_keys:
            del self._cache[key]
        return len(expired_keys)


# 전역 캐시 인스턴스
cache = DataCache()
