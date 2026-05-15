"""
SSBPxWebClient — cached HTTP client for Norway's Statistics Bureau (SSB) PxWebApi v2.

SSB PxWebApi v2 uses GET requests with query parameters for table data.
If the constructed URL exceeds 2100 characters, the client falls back to a POST
request with the query in the request body (SSB v2 supports both).

Base URL: https://data.ssb.no/api/pxwebapi/v2/

Rate limiting: SSB enforces a soft limit of 30 requests/min. This client uses
a token-bucket approach enforcing ≥2.1 seconds between outgoing HTTP requests
(≈28.5 req/min with headroom).

Cache prefix: all SSB cache files are prefixed with ``ssb_`` to avoid collisions
with SCB cache files when a shared cache directory is used.
"""

import time
from pathlib import Path

import requests

from population_synth._paths import PROJECT_ROOT

from .pxweb_client import BasePxWebClient

_DEFAULT_CACHE_DIR = PROJECT_ROOT / "config" / "assets" / "ssb_cache"
_BASE_URL = "https://data.ssb.no/api/pxwebapi/v2/"
_CACHE_PREFIX = "ssb"
_MIN_REQUEST_INTERVAL = 2.1  # seconds between outgoing HTTP calls
_URL_LENGTH_LIMIT = 2100     # chars; fall back to POST if exceeded


class SSBPxWebClient(BasePxWebClient):
    """Cached GET-based client for the SSB PxWebApi v2.

    Parameters
    ----------
    cache_dir:
        Directory for JSON cache files. Defaults to
        ``config/assets/ssb_cache/`` relative to the project root.
    cache_ttl_days:
        How long cached responses are considered fresh. Defaults to 90 days.
    """

    def __init__(
        self,
        cache_dir: Path = _DEFAULT_CACHE_DIR,
        cache_ttl_days: int = 90,
    ) -> None:
        super().__init__(cache_dir=cache_dir, cache_ttl_days=cache_ttl_days)
        self._last_request_time: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_table(self, table_id: str, query_params: dict) -> dict:
        """Fetch data for ``table_id`` using ``query_params``.

        Parameters
        ----------
        table_id:
            SSB table identifier, e.g. ``"07459"``.
        query_params:
            Mapping of variable codes to lists of selected values, plus any
            response-format keys understood by PxWebApi v2.  Example::

                {
                    "Kjonn": ["1", "2"],
                    "Alder": ["20", "25", "30"],
                    "ContentsCode": ["Befolkning"],
                    "Tid": ["2023"],
                }

        Returns
        -------
        dict
            Parsed json-stat2 response body.
        """
        cache_key = self._cache_key(f"{_CACHE_PREFIX}_data", table_id, query_params)
        cached = self._load_from_cache(cache_key)
        if cached is not None:
            return cached

        data = self._http_fetch(table_id, query_params)
        self._save_to_cache(cache_key, data)
        return data

    def get_table_metadata(self, table_id: str) -> dict:
        """Return the metadata (variable codes, value labels) for ``table_id``.

        The metadata endpoint is a plain GET with no query parameters.

        Parameters
        ----------
        table_id:
            SSB table identifier, e.g. ``"07459"``.

        Returns
        -------
        dict
            Parsed JSON metadata response from SSB.
        """
        cache_key = self._cache_key(f"{_CACHE_PREFIX}_meta", table_id)
        cached = self._load_from_cache(cache_key)
        if cached is not None:
            return cached

        url = _BASE_URL + "tables/" + table_id.strip("/")
        self._rate_limit()
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        self._save_to_cache(cache_key, data)
        return data

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _http_fetch(self, table_id: str, query_params: dict) -> dict:
        """Execute a POST request for table data using the SSB PxWebApi v2 Selection format.

        SSB PxWebApi v2 requires POST with body:
          {"Selection": [{"variableCode": "<var>", "valueCodes": ["<val>", ...]}, ...]}
        GET with query-string parameters does not filter dimensions and returns
        aggregated/incorrect results.
        """
        url = _BASE_URL + "tables/" + table_id.strip("/") + "/data"
        body = {
            "Selection": [
                {"variableCode": k, "valueCodes": v if isinstance(v, list) else [v]}
                for k, v in query_params.items()
            ]
        }
        self._rate_limit()
        response = requests.post(url, json=body, timeout=30)
        response.raise_for_status()
        return response.json()

    def _rate_limit(self) -> None:
        """Block until ≥ ``_MIN_REQUEST_INTERVAL`` seconds have elapsed since
        the last outgoing HTTP request, then record the current time."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < _MIN_REQUEST_INTERVAL:
            time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.monotonic()
