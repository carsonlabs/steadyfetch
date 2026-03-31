"""Simple disk-based cache for fetch results."""

import hashlib
import json
import os

import diskcache


CACHE_DIR = os.environ.get("STEADYFETCH_CACHE_DIR", "/tmp/steadyfetch_cache")
DEFAULT_TTL = int(os.environ.get("STEADYFETCH_CACHE_TTL", "3600"))  # 1 hour


class FetchCache:
    """Disk-backed cache keyed by URL + options hash."""

    def __init__(self, directory: str = CACHE_DIR, ttl: int = DEFAULT_TTL):
        self.cache = diskcache.Cache(directory, size_limit=500 * 1024 * 1024)  # 500MB
        self.ttl = ttl

    def _key(self, url: str, extract_schema: str | None = None) -> str:
        raw = f"{url}:{extract_schema or ''}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, url: str, extract_schema: str | None = None) -> dict | None:
        key = self._key(url, extract_schema)
        raw = self.cache.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    def set(self, url: str, data: dict, extract_schema: str | None = None) -> None:
        key = self._key(url, extract_schema)
        self.cache.set(key, json.dumps(data), expire=self.ttl)

    def clear(self) -> None:
        self.cache.clear()

    def stats(self) -> dict:
        return {
            "size_bytes": self.cache.volume(),
            "item_count": len(self.cache),
        }
