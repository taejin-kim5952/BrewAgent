from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class CacheEntry:
    value: str
    expires_at: float


class ResponseCache:
    """TTL 기반 인메모리 응답 캐시 (동일 쿼리 재실행 방지)."""

    def __init__(self, ttl_seconds: int = 300):
        self.ttl = ttl_seconds
        self._cache: dict[str, CacheEntry] = {}

    def get(self, key: str) -> str | None:
        entry = self._cache.get(key)
        if entry and time.time() < entry.expires_at:
            return entry.value
        if entry:
            del self._cache[key]
        return None

    def set(self, key: str, value: str) -> None:
        self._cache[key] = CacheEntry(value=value, expires_at=time.time() + self.ttl)

    def make_key(self, query: str, namespace: str) -> str:
        import hashlib
        return hashlib.md5(f"{namespace}:{query}".encode()).hexdigest()

    def clear(self) -> None:
        self._cache.clear()
