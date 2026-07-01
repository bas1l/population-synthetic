"""ISTATSDMXClient — ISTAT SDMX REST API wrapper with rate limiting.

Defines ``ISTATSDMXClient`` for fetching CSV data and JSON datastructures
from the ISTAT SDMX API, plus ``istat_rate_limit_wait``, a cross-process
rate limiter enforcing ISTAT's ~5 req/min connection limit. Responses are
cached locally with a configurable TTL.
"""
import csv
import io
import logging
import time
from pathlib import Path

import requests

from population_synthetic._paths import PROJECT_ROOT

from .pxweb_client import BasePxWebClient

_DEFAULT_CACHE_DIR = PROJECT_ROOT / "config" / "database" / "caches" / "istat"
_BASE_URL = "https://esploradati.istat.it/SDMXWS/rest"
_MIN_REQUEST_INTERVAL = 15.0  # ISTAT enforces ~5 req/min hard limit; 15s gives safety margin
_RATE_LIMIT_FILE = _DEFAULT_CACHE_DIR / ".istat_last_request"

logger = logging.getLogger(__name__)


def istat_rate_limit_wait(interval: float = _MIN_REQUEST_INTERVAL) -> None:
    """Cross-process rate limiter for the ISTAT SDMX API.

    Reads the last request wall-clock timestamp from a shared file and sleeps
    until ``interval`` seconds have elapsed. Writes the new timestamp after
    waiting. Safe to call from any process — the file acts as coordination
    point. ISTAT enforces ~5 req/min at the connection level (IP block, not
    HTTP 429), so this must be respected across all scripts.
    """
    _RATE_LIMIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    last_time = 0.0
    if _RATE_LIMIT_FILE.exists():
        try:
            last_time = float(_RATE_LIMIT_FILE.read_text().strip())
        except (ValueError, OSError):
            pass
    elapsed = time.time() - last_time
    if elapsed < interval:
        wait = interval - elapsed
        logger.debug("ISTAT rate limit: sleeping %.1fs", wait)
        time.sleep(wait)
    try:
        _RATE_LIMIT_FILE.write_text(str(time.time()))
    except OSError:
        pass


class ISTATSDMXClient(BasePxWebClient):
    def __init__(
        self,
        cache_dir: Path = _DEFAULT_CACHE_DIR,
        cache_ttl_days: int = 90,
    ) -> None:
        super().__init__(cache_dir=cache_dir, cache_ttl_days=cache_ttl_days)

    def fetch_data(
        self, dataflow_id: str, key_filter: str = "", params: dict | None = None,
    ) -> list[dict]:
        merged_params = {"startPeriod": "2021", "endPeriod": "2023", "format": "csv"}
        if params:
            merged_params.update(params)
        cache_key = self._cache_key("istat_csv", f"{dataflow_id}_{key_filter}")
        cached = self._load_from_cache(cache_key)
        if cached is not None:
            return cached
        url = f"{_BASE_URL}/data/{dataflow_id}"
        if key_filter:
            url = f"{url}/{key_filter}"
        self._rate_limit()
        response = requests.get(url, params=merged_params, timeout=120)
        response.raise_for_status()
        rows = list(csv.DictReader(io.StringIO(response.text)))
        self._save_to_cache(cache_key, rows)
        return rows

    def get_datastructure(self, dataflow_id: str) -> dict:
        cache_key = self._cache_key("istat_dsd", dataflow_id)
        cached = self._load_from_cache(cache_key)
        if cached is not None:
            return cached
        self._rate_limit()
        response = requests.get(
            f"{_BASE_URL}/datastructure/IT1/{dataflow_id}?format=jsondata",
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        self._save_to_cache(cache_key, data)
        return data

    def _rate_limit(self) -> None:
        istat_rate_limit_wait()
