"""
BasePxWebClient — shared cache infrastructure for PxWeb API clients.

Subclasses (SCBPxWebClient, SSBPxWebClient) inherit cache management and
implement their own fetch strategies (POST vs GET, rate limiting, etc.).
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Any


class BasePxWebClient:
    """Base class providing filesystem-backed JSON cache for PxWeb API responses.

    Cache entries expire after ``cache_ttl_days`` days (based on file mtime).
    Subclasses call ``_load_from_cache`` / ``_save_to_cache`` using a cache key
    produced by ``_cache_key``.
    """

    def __init__(
        self,
        cache_dir: Path,
        cache_ttl_days: int = 90,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_ttl_seconds = cache_ttl_days * 86400
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Cache helpers (intended for use by subclasses)
    # ------------------------------------------------------------------

    def _cache_key(
        self,
        prefix: str,
        table_id: str,
        query: dict | None = None,
    ) -> str:
        """Return a filename-safe cache key for the given table + optional query."""
        slug = table_id.strip("/").replace("/", "_")
        if query is not None:
            query_hash = hashlib.md5(
                json.dumps(query, sort_keys=True).encode()
            ).hexdigest()[:8]
            return f"{prefix}_{slug}_{query_hash}.json"
        return f"{prefix}_{slug}.json"

    def _cache_path(self, cache_key: str) -> Path:
        """Return the full path for a given cache key."""
        return self.cache_dir / cache_key

    def _load_from_cache(self, cache_key: str) -> Any | None:
        """Return cached data if it exists and has not expired; otherwise None."""
        path = self._cache_path(cache_key)
        if not path.exists():
            return None
        age = time.time() - path.stat().st_mtime
        if age > self.cache_ttl_seconds:
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_to_cache(self, cache_key: str, data: Any) -> None:
        """Write ``data`` to the cache file identified by ``cache_key``."""
        path = self._cache_path(cache_key)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
