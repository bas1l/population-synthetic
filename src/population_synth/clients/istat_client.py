import time
from pathlib import Path

import requests

from population_synth._paths import PROJECT_ROOT

from .pxweb_client import BasePxWebClient

_DEFAULT_CACHE_DIR = PROJECT_ROOT / "config" / "assets" / "istat_cache"
_BASE_URL = "https://esploradati.istat.it/SDMXWS/rest"
_MIN_REQUEST_INTERVAL = 12.0  # ISTAT enforces ~5 req/min hard limit


class ISTATSDMXClient(BasePxWebClient):
    def __init__(
        self,
        cache_dir: Path = _DEFAULT_CACHE_DIR,
        cache_ttl_days: int = 90,
    ) -> None:
        super().__init__(cache_dir=cache_dir, cache_ttl_days=cache_ttl_days)
        self._last_request_time: float = 0.0

    def fetch_data(self, dataflow_id: str, key_filter: str = "", params: dict | None = None) -> dict:
        merged_params = {"startPeriod": "2021", "endPeriod": "2023", "format": "jsondata"}
        if params:
            merged_params.update(params)
        cache_key = self._cache_key("istat", f"{dataflow_id}_{key_filter}")
        cached = self._load_from_cache(cache_key)
        if cached is not None:
            return cached
        url = f"{_BASE_URL}/data/{dataflow_id}"
        if key_filter:
            url = f"{url}/{key_filter}"
        self._rate_limit()
        response = requests.get(url, params=merged_params, timeout=30)
        response.raise_for_status()
        data = response.json()
        self._save_to_cache(cache_key, data)
        return data

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
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < _MIN_REQUEST_INTERVAL:
            time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.monotonic()
