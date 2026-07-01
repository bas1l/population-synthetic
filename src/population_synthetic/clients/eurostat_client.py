"""EurostatClient — Eurostat dissemination API wrapper with caching.

Defines ``EurostatClient``, a ``BasePxWebClient`` subclass that fetches
JSON-stat datasets from the Eurostat statistics API (defaulting to Italian
geo scope) and caches responses locally with a configurable TTL.
"""
from pathlib import Path

import requests

from population_synthetic._paths import PROJECT_ROOT

from .pxweb_client import BasePxWebClient

_DEFAULT_CACHE_DIR = PROJECT_ROOT / "config" / "database" / "caches" / "eurostat"
_BASE_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"


class EurostatClient(BasePxWebClient):
    def __init__(
        self,
        cache_dir: Path = _DEFAULT_CACHE_DIR,
        cache_ttl_days: int = 90,
    ) -> None:
        super().__init__(cache_dir=cache_dir, cache_ttl_days=cache_ttl_days)

    def fetch_dataset(self, dataset_code: str, params: dict | None = None) -> dict:
        merged_params = {"format": "JSON", "geo": "IT"}
        if params:
            merged_params.update(params)
        cache_key = self._cache_key("eurostat_data", dataset_code, merged_params)
        cached = self._load_from_cache(cache_key)
        if cached is not None:
            return cached
        response = requests.get(_BASE_URL + dataset_code, params=merged_params, timeout=30)
        response.raise_for_status()
        data = response.json()
        self._save_to_cache(cache_key, data)
        return data
