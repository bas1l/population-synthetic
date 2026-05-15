"""
SCBPxWebClient — cached HTTP client for Sweden's Statistics Bureau (SCB) PxWeb API.

PxWeb POST query body format:
    {
        "query": [
            {"code": "var_code", "selection": {"filter": "item", "values": ["v1", "v2"]}}
        ],
        "response": {"format": "json-stat2"}
    }

Base URL: https://api.scb.se/OV0104/v1/doris/en/ssd/
"""

from pathlib import Path

import requests

from population_synth._paths import PROJECT_ROOT

from .pxweb_client import BasePxWebClient

_DEFAULT_CACHE_DIR = PROJECT_ROOT / "config" / "assets" / "scb_cache"
_BASE_URL = "https://api.scb.se/OV0104/v1/doris/en/ssd/"


class SCBPxWebClient(BasePxWebClient):
    def __init__(
        self,
        cache_dir: Path = _DEFAULT_CACHE_DIR,
        cache_ttl_days: int = 90,
    ):
        super().__init__(cache_dir=cache_dir, cache_ttl_days=cache_ttl_days)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_table(self, table_path: str, query: dict) -> dict:
        cache_key = self._cache_key("data", table_path, query)
        cached = self._load_from_cache(cache_key)
        if cached is not None:
            return cached

        url = _BASE_URL + table_path.lstrip("/")
        response = requests.post(url, json=query, timeout=30)
        response.raise_for_status()
        data = response.json()

        self._save_to_cache(cache_key, data)
        return data

    def get_table_metadata(self, table_path: str) -> dict:
        cache_key = self._cache_key("meta", table_path)
        cached = self._load_from_cache(cache_key)
        if cached is not None:
            return cached

        url = _BASE_URL + table_path.lstrip("/")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        self._save_to_cache(cache_key, data)
        return data
