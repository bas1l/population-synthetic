"""
test_istat_discovery.py -- Systematic discovery of working ISTAT SDMX dataflows.

Parses the cached ISTAT dataflow catalog (~4,850 dataflows), searches for
demographic-relevant dataflows by keyword, and probes each candidate to find
parameter combinations that return non-null observation data.

KEY FINDING (2026-05-26): The ISTAT SDMX REST API's JSON serializer
(format=jsondata) is broken — it returns data structure with null observation
values. The CSV serializer (format=csv) returns the same data correctly.
This script tests both formats and confirms the CSV workaround works for
all critical dataflows.

Usage:
    python scripts/test_istat_discovery.py                 # full discovery
    python scripts/test_istat_discovery.py --cache-only     # only use cached responses
    python scripts/test_istat_discovery.py --field education # single field
    python scripts/test_istat_discovery.py --field all --max-per-field 5
    python scripts/test_istat_discovery.py --keyword "marital status"
    python scripts/test_istat_discovery.py --skip-probes    # catalog search only
    python scripts/test_istat_discovery.py --csv-only       # only test CSV format
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import requests

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CACHE_DIR = _PROJECT_ROOT / "config" / "assets" / "istat_cache"
_CATALOG_FILE = _CACHE_DIR / "dataflow_IT1.txt"

ISTAT_BASE = "https://esploradati.istat.it/SDMXWS/rest"
EUROSTAT_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0"

_RATE_LIMIT_SECONDS = 15.0
_RATE_LIMIT_FILE = _CACHE_DIR / ".istat_last_request"

_cache_only = False
_no_cache = False

# XML namespaces used in the ISTAT dataflow catalog
NS = {
    "message": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message",
    "structure": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure",
    "common": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common",
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DataflowInfo:
    id: str
    name_en: str
    name_it: str
    dsd_id: str
    last_update: str
    keywords_en: str
    keywords_it: str
    layout_row: str
    layout_column: str
    layout_filter: str
    is_file_only: bool


@dataclass
class ProbeResult:
    dataflow_id: str
    name: str
    key_filter: str
    params: dict
    status: str  # "ok", "null_obs", "error", "timeout", "cached"
    n_series: int
    n_non_null_obs: int
    n_total_obs: int
    dimensions: list[str]
    sample_values: list[float | None]
    error_msg: str
    elapsed_s: float


@dataclass
class FieldDiscovery:
    field_name: str
    keywords: list[str]
    candidates: list[DataflowInfo] = field(default_factory=list)
    probe_results: list[ProbeResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Keyword sets for each demographic field
# ---------------------------------------------------------------------------

FIELD_KEYWORDS: dict[str, list[str]] = {
    "education": [
        "education", "titolo di studio", "istruzione", "ISCED",
        "laurea", "diploma", "livello di istruzione",
        "highest level of education", "educational attainment",
    ],
    "employment": [
        "employment", "occupati", "occupazione", "labour force",
        "forza lavoro", "disoccupazione", "unemployment",
        "labour status", "condizione professionale",
        "employment rate", "tasso di occupazione",
    ],
    "income": [
        "income", "reddito", "EU-SILC", "povertà", "poverty",
        "net family income", "reddito netto", "household income",
    ],
    "civil_status": [
        "civil status", "stato civile", "marital status",
        "matrimoni", "nuzialità", "legal marital",
        "celibe", "coniugato", "divorziato", "vedovo",
    ],
    "household": [
        "household", "famiglia", "nucleo familiare",
        "household size", "componenti", "numero componenti",
        "private household", "tipo di famiglia",
    ],
    "occupation": [
        "occupation", "professione", "ISCO", "ATECO",
        "settore", "economic activity", "NACE",
        "attività economica", "posizione professionale",
    ],
    "birth_migration": [
        "birth", "nascita", "citizenship", "cittadinanza",
        "stranieri", "foreign", "migration",
        "country of birth", "luogo di nascita",
    ],
    "population_age_sex": [
        "resident population", "popolazione residente",
        "population by age", "population by sex",
        "età", "sesso", "demografic",
    ],
}


# ---------------------------------------------------------------------------
# Catalog parsing
# ---------------------------------------------------------------------------

def parse_catalog(catalog_path: Path) -> list[DataflowInfo]:
    """Parse the ISTAT XML dataflow catalog into structured records."""
    print(f"Parsing catalog: {catalog_path} ({catalog_path.stat().st_size / 1e6:.1f} MB)")

    tree = ET.parse(catalog_path)
    root = tree.getroot()

    dataflows_el = root.find(".//structure:Dataflows", NS)
    if dataflows_el is None:
        raise RuntimeError("No <structure:Dataflows> element found in catalog XML")

    results: list[DataflowInfo] = []

    for df_el in dataflows_el.findall("structure:Dataflow", NS):
        df_id = df_el.attrib.get("id", "")

        name_en = ""
        name_it = ""
        for name_el in df_el.findall("common:Name", NS):
            lang = name_el.attrib.get("{http://www.w3.org/XML/1998/namespace}lang", "")
            if lang == "en":
                name_en = name_el.text or ""
            elif lang == "it":
                name_it = name_el.text or ""

        dsd_id = ""
        ref_el = df_el.find(".//structure:Structure/Ref", NS)
        if ref_el is not None:
            dsd_id = ref_el.attrib.get("id", "")

        last_update = ""
        keywords_en = ""
        keywords_it = ""
        layout_row = ""
        layout_column = ""
        layout_filter = ""
        is_file_only = False

        for ann_el in df_el.findall(".//common:Annotation", NS):
            ann_type_el = ann_el.find("common:AnnotationType", NS)
            ann_title_el = ann_el.find("common:AnnotationTitle", NS)
            if ann_type_el is None:
                continue
            ann_type = ann_type_el.text or ""

            if ann_type == "LAST_UPDATE" and ann_title_el is not None:
                last_update = ann_title_el.text or ""
            elif ann_type == "LAYOUT_ROW" and ann_title_el is not None:
                layout_row = ann_title_el.text or ""
            elif ann_type == "LAYOUT_COLUMN" and ann_title_el is not None:
                layout_column = ann_title_el.text or ""
            elif ann_type == "LAYOUT_FILTER" and ann_title_el is not None:
                layout_filter = ann_title_el.text or ""
            elif ann_type == "DATAFLOW_CATALOG_TYPE" and ann_title_el is not None:
                if ann_title_el.text == "ONLY_FILE":
                    is_file_only = True
            elif ann_type == "LAYOUT_DATAFLOW_KEYWORDS":
                for ann_text_el in ann_el.findall("common:AnnotationText", NS):
                    lang = ann_text_el.attrib.get("{http://www.w3.org/XML/1998/namespace}lang", "")
                    text = ann_text_el.text or ""
                    if lang == "en":
                        keywords_en = text
                    elif lang == "it":
                        keywords_it = text

        results.append(DataflowInfo(
            id=df_id,
            name_en=name_en,
            name_it=name_it,
            dsd_id=dsd_id,
            last_update=last_update,
            keywords_en=keywords_en,
            keywords_it=keywords_it,
            layout_row=layout_row,
            layout_column=layout_column,
            layout_filter=layout_filter,
            is_file_only=is_file_only,
        ))

    print(f"  Parsed {len(results)} dataflows ({sum(1 for d in results if d.is_file_only)} file-only)")
    return results


def search_catalog(
    catalog: list[DataflowInfo],
    keywords: list[str],
    *,
    exclude_file_only: bool = True,
    exclude_old_regulation: bool = False,
) -> list[tuple[DataflowInfo, int]]:
    """Search catalog for dataflows matching any keyword. Returns (info, score) sorted by score desc."""
    results: list[tuple[DataflowInfo, int]] = []

    for df in catalog:
        if exclude_file_only and df.is_file_only:
            continue

        searchable = " ".join([
            df.name_en, df.name_it, df.keywords_en, df.keywords_it,
            df.layout_row, df.layout_column, df.layout_filter,
        ]).lower()

        if exclude_old_regulation and "until 2020" in searchable:
            continue

        score = 0
        for kw in keywords:
            if kw.lower() in searchable:
                score += 1
                if kw.lower() in df.name_en.lower() or kw.lower() in df.name_it.lower():
                    score += 2

        if score > 0:
            results.append((df, score))

    results.sort(key=lambda x: (-x[1], x[0].id))
    return results


# ---------------------------------------------------------------------------
# Fetching and probing
# ---------------------------------------------------------------------------

def _safe_key(raw: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", raw)


def _load_cache(key: str) -> dict | None:
    path = _CACHE_DIR / f"{_safe_key(key)}.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _save_cache(key: str, data: dict) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _CACHE_DIR / f"{_safe_key(key)}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _enforce_rate_limit() -> None:
    """Cross-process rate limiter using shared timestamp file.

    Reads/writes the same file as ISTATSDMXClient so concurrent scripts
    cannot exceed the ~5 req/min ISTAT hard limit.
    """
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    last_time = 0.0
    if _RATE_LIMIT_FILE.exists():
        try:
            last_time = float(_RATE_LIMIT_FILE.read_text().strip())
        except (ValueError, OSError):
            pass
    elapsed = time.time() - last_time
    if elapsed < _RATE_LIMIT_SECONDS:
        wait = _RATE_LIMIT_SECONDS - elapsed
        print(f"      [rate limit] sleeping {wait:.1f}s ...")
        time.sleep(wait)
    try:
        _RATE_LIMIT_FILE.write_text(str(time.time()))
    except OSError:
        pass


def _analyze_observations(data: dict) -> tuple[int, int, int, list[str], list[float | None]]:
    """Analyze SDMX-JSON response for observation data quality.

    Returns: (n_series, n_non_null_obs, n_total_obs, dimension_ids, sample_values)
    """
    dim_ids: list[str] = []
    datasets = data.get("data", {}).get("dataSets", [])

    structures = data.get("data", {}).get("structures", [])
    structure = data.get("data", {}).get("structure", {})

    dims_block = None
    if structures:
        dims_block = structures[0].get("dimensions", {})
    elif structure:
        dims_block = structure.get("dimensions", {})

    if dims_block:
        for dim in dims_block.get("series", []) + dims_block.get("observation", []):
            dim_ids.append(dim.get("id", "?"))

    if not datasets:
        return 0, 0, 0, dim_ids, []

    series = datasets[0].get("series", {})
    n_series = len(series)
    n_total = 0
    n_non_null = 0
    sample_vals: list[float | None] = []

    for _sk, sv in series.items():
        obs = sv.get("observations", {})
        for _ok, ov in obs.items():
            n_total += 1
            val = ov[0] if isinstance(ov, list) and len(ov) > 0 else ov
            if val is not None:
                n_non_null += 1
                if len(sample_vals) < 10:
                    sample_vals.append(float(val))
            elif len(sample_vals) < 10:
                sample_vals.append(None)

    return n_series, n_non_null, n_total, dim_ids, sample_vals


def probe_istat_dataflow(
    dataflow_id: str,
    name: str,
    key_filter: str = "",
    params: dict | None = None,
    timeout: int = 45,
) -> ProbeResult:
    """Fetch a single ISTAT dataflow and analyze whether it returns real data."""
    if params is None:
        params = {"startPeriod": "2021", "endPeriod": "2023"}

    merged_params = {"format": "jsondata"}
    merged_params.update(params)

    cache_key = f"discovery_{dataflow_id}_{_safe_key(key_filter)}_{merged_params.get('startPeriod', '')}_{merged_params.get('endPeriod', '')}"

    if not _no_cache:
        cached = _load_cache(cache_key)
        if cached is not None:
            print(f"      [cache hit] {dataflow_id}/{key_filter or 'all'}")
            n_series, n_non_null, n_total, dims, samples = _analyze_observations(cached)
            status = "ok" if n_non_null > 0 else "null_obs"
            return ProbeResult(
                dataflow_id=dataflow_id, name=name, key_filter=key_filter,
                params=merged_params, status=status, n_series=n_series,
                n_non_null_obs=n_non_null, n_total_obs=n_total,
                dimensions=dims, sample_values=samples,
                error_msg="", elapsed_s=0.0,
            )

    if _cache_only:
        return ProbeResult(
            dataflow_id=dataflow_id, name=name, key_filter=key_filter,
            params=merged_params, status="error", n_series=0,
            n_non_null_obs=0, n_total_obs=0, dimensions=[], sample_values=[],
            error_msg="cache miss (--cache-only)", elapsed_s=0.0,
        )

    url = f"{ISTAT_BASE}/data/{dataflow_id}"
    if key_filter:
        url += f"/{key_filter}"

    _enforce_rate_limit()
    print(f"      [fetch] GET {url}")
    t0 = time.time()

    try:
        resp = requests.get(url, params=merged_params, timeout=timeout)
        elapsed = time.time() - t0
        resp.raise_for_status()
        data = resp.json()
        _save_cache(cache_key, data)
    except requests.Timeout:
        elapsed = time.time() - t0
        return ProbeResult(
            dataflow_id=dataflow_id, name=name, key_filter=key_filter,
            params=merged_params, status="timeout", n_series=0,
            n_non_null_obs=0, n_total_obs=0, dimensions=[], sample_values=[],
            error_msg=f"Timeout after {elapsed:.1f}s", elapsed_s=elapsed,
        )
    except Exception as exc:
        elapsed = time.time() - t0
        return ProbeResult(
            dataflow_id=dataflow_id, name=name, key_filter=key_filter,
            params=merged_params, status="error", n_series=0,
            n_non_null_obs=0, n_total_obs=0, dimensions=[], sample_values=[],
            error_msg=str(exc), elapsed_s=elapsed,
        )

    n_series, n_non_null, n_total, dims, samples = _analyze_observations(data)
    status = "ok" if n_non_null > 0 else "null_obs"

    return ProbeResult(
        dataflow_id=dataflow_id, name=name, key_filter=key_filter,
        params=merged_params, status=status, n_series=n_series,
        n_non_null_obs=n_non_null, n_total_obs=n_total,
        dimensions=dims, sample_values=samples,
        error_msg="", elapsed_s=elapsed,
    )


def probe_istat_csv(
    dataflow_id: str,
    name: str,
    key_filter: str = "",
    params: dict | None = None,
    timeout: int = 60,
) -> ProbeResult:
    """Fetch an ISTAT dataflow as CSV and analyze data quality.

    The ISTAT SDMX REST API JSON serializer is broken (null observations),
    but the CSV serializer returns actual values. This probe tests CSV format.
    """
    if params is None:
        params = {"startPeriod": "2021", "endPeriod": "2023"}

    merged_params = {"format": "csv"}
    merged_params.update(params)

    cache_key = f"discovery_csv_{dataflow_id}_{_safe_key(key_filter)}_{merged_params.get('startPeriod', '')}_{merged_params.get('endPeriod', '')}"

    csv_cache_path = _CACHE_DIR / f"{_safe_key(cache_key)}.csv"
    if not _no_cache and csv_cache_path.exists():
        print(f"      [cache hit] {dataflow_id}/{key_filter or 'all'} (csv)")
        text = csv_cache_path.read_text(encoding="utf-8")
        n_rows, n_non_null, columns, sample_vals = _analyze_csv(text)
        status = "ok" if n_non_null > 0 else "null_obs"
        return ProbeResult(
            dataflow_id=f"{dataflow_id}[csv]", name=name, key_filter=key_filter,
            params=merged_params, status=status, n_series=n_rows,
            n_non_null_obs=n_non_null, n_total_obs=n_rows,
            dimensions=columns, sample_values=sample_vals,
            error_msg="", elapsed_s=0.0,
        )

    if _cache_only:
        return ProbeResult(
            dataflow_id=f"{dataflow_id}[csv]", name=name, key_filter=key_filter,
            params=merged_params, status="error", n_series=0,
            n_non_null_obs=0, n_total_obs=0, dimensions=[], sample_values=[],
            error_msg="cache miss (--cache-only)", elapsed_s=0.0,
        )

    url = f"{ISTAT_BASE}/data/{dataflow_id}"
    if key_filter:
        url += f"/{key_filter}"

    _enforce_rate_limit()
    print(f"      [fetch csv] GET {url}")
    t0 = time.time()

    try:
        resp = requests.get(url, params=merged_params, timeout=timeout)
        elapsed = time.time() - t0
        resp.raise_for_status()
        text = resp.text
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        csv_cache_path.write_text(text, encoding="utf-8")
    except requests.Timeout:
        elapsed = time.time() - t0
        return ProbeResult(
            dataflow_id=f"{dataflow_id}[csv]", name=name, key_filter=key_filter,
            params=merged_params, status="timeout", n_series=0,
            n_non_null_obs=0, n_total_obs=0, dimensions=[], sample_values=[],
            error_msg=f"Timeout after {elapsed:.1f}s", elapsed_s=elapsed,
        )
    except Exception as exc:
        elapsed = time.time() - t0
        return ProbeResult(
            dataflow_id=f"{dataflow_id}[csv]", name=name, key_filter=key_filter,
            params=merged_params, status="error", n_series=0,
            n_non_null_obs=0, n_total_obs=0, dimensions=[], sample_values=[],
            error_msg=str(exc), elapsed_s=elapsed,
        )

    n_rows, n_non_null, columns, sample_vals = _analyze_csv(text)
    status = "ok" if n_non_null > 0 else "null_obs"

    return ProbeResult(
        dataflow_id=f"{dataflow_id}[csv]", name=name, key_filter=key_filter,
        params=merged_params, status=status, n_series=n_rows,
        n_non_null_obs=n_non_null, n_total_obs=n_rows,
        dimensions=columns, sample_values=sample_vals,
        error_msg="", elapsed_s=elapsed,
    )


def _analyze_csv(text: str) -> tuple[int, int, list[str], list[float | None]]:
    """Analyze SDMX CSV response for data quality.

    Returns: (n_rows, n_non_null_values, column_names, sample_values)
    """
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return 0, 0, [], []

    obs_value_idx = None
    for i, h in enumerate(header):
        if h == "OBS_VALUE":
            obs_value_idx = i
            break

    n_rows = 0
    n_non_null = 0
    sample_vals: list[float | None] = []

    for row in reader:
        n_rows += 1
        if obs_value_idx is not None and obs_value_idx < len(row):
            cell = row[obs_value_idx].strip()
            if cell and cell != "NaN":
                try:
                    val = float(cell)
                    n_non_null += 1
                    if len(sample_vals) < 10:
                        sample_vals.append(val)
                except ValueError:
                    pass
            elif len(sample_vals) < 10:
                sample_vals.append(None)
        else:
            for cell in row:
                try:
                    val = float(cell.strip())
                    n_non_null += 1
                    if len(sample_vals) < 10:
                        sample_vals.append(val)
                    break
                except (ValueError, AttributeError):
                    pass

    relevant_cols = [h for h in header if h not in (
        "DATAFLOW", "FREQ", "OBS_STATUS", "OBS_STATUS_H",
    ) and not h.startswith("NOTE_")]
    return n_rows, n_non_null, relevant_cols, sample_vals


def probe_eurostat_dataset(
    dataset_code: str,
    name: str,
    params: dict | None = None,
) -> ProbeResult:
    """Fetch a Eurostat JSON-stat dataset and check if Italy data exists."""
    if params is None:
        params = {}

    merged_params = {"format": "JSON", "geo": "IT"}
    merged_params.update(params)

    cache_key = f"discovery_eurostat_{dataset_code}_{merged_params.get('sinceTimePeriod', '')}"

    if not _no_cache:
        cached = _load_cache(cache_key)
        if cached is not None:
            print(f"      [cache hit] eurostat/{dataset_code}")
            values = cached.get("value", {})
            n_vals = len(values) if isinstance(values, (dict, list)) else 0
            n_non_null = sum(1 for v in (values.values() if isinstance(values, dict) else values) if v is not None) if n_vals else 0
            dims = list(cached.get("dimension", {}).keys())
            status = "ok" if n_non_null > 0 else "null_obs"
            return ProbeResult(
                dataflow_id=f"eurostat:{dataset_code}", name=name,
                key_filter="geo=IT", params=merged_params, status=status,
                n_series=n_vals, n_non_null_obs=n_non_null, n_total_obs=n_vals,
                dimensions=dims, sample_values=[], error_msg="", elapsed_s=0.0,
            )

    if _cache_only:
        return ProbeResult(
            dataflow_id=f"eurostat:{dataset_code}", name=name,
            key_filter="geo=IT", params=merged_params, status="error",
            n_series=0, n_non_null_obs=0, n_total_obs=0,
            dimensions=[], sample_values=[],
            error_msg="cache miss (--cache-only)", elapsed_s=0.0,
        )

    url = f"{EUROSTAT_BASE}/data/{dataset_code}"
    print(f"      [fetch] GET {url}")
    t0 = time.time()

    try:
        resp = requests.get(url, params=merged_params, timeout=30)
        elapsed = time.time() - t0
        resp.raise_for_status()
        data = resp.json()
        _save_cache(cache_key, data)
    except Exception as exc:
        elapsed = time.time() - t0
        return ProbeResult(
            dataflow_id=f"eurostat:{dataset_code}", name=name,
            key_filter="geo=IT", params=merged_params, status="error",
            n_series=0, n_non_null_obs=0, n_total_obs=0,
            dimensions=[], sample_values=[],
            error_msg=str(exc), elapsed_s=elapsed,
        )

    values = data.get("value", {})
    n_vals = len(values) if isinstance(values, (dict, list)) else 0
    n_non_null = sum(1 for v in (values.values() if isinstance(values, dict) else values) if v is not None) if n_vals else 0
    dims = list(data.get("dimension", {}).keys())
    status = "ok" if n_non_null > 0 else "null_obs"

    return ProbeResult(
        dataflow_id=f"eurostat:{dataset_code}", name=name,
        key_filter="geo=IT", params=merged_params, status=status,
        n_series=n_vals, n_non_null_obs=n_non_null, n_total_obs=n_vals,
        dimensions=dims, sample_values=[], error_msg="", elapsed_s=elapsed,
    )


# ---------------------------------------------------------------------------
# Discovery strategies per field
# ---------------------------------------------------------------------------

# Known parent IDs and their sub-dataflow patterns for targeted probing
KNOWN_PARENTS: dict[str, dict] = {
    "education": {
        "parent_prefix": "52_1194",
        "description": "Population by education level",
    },
    "employment": {
        "parent_prefix": "150_938",
        "description": "Employment (thousands) — current regulation",
    },
    "income": {
        "parent_prefix": "32_292",
        "description": "Net family income by source",
    },
    "civil_status": {
        "parent_prefix": "22_289",
        "description": "Resident population (incl. civil status)",
    },
}

# Eurostat alternatives to test (from Phase 8 plan)
EUROSTAT_ALTERNATIVES: dict[str, list[tuple[str, str, dict]]] = {
    "education": [
        ("edat_lfs_9911", "Population by education level, sex and age (%)", {"sinceTimePeriod": "2021"}),
        ("edat_lfse_03", "Population by education level, sex (15-64)", {"sinceTimePeriod": "2021"}),
    ],
    "employment": [
        ("lfsa_pganws", "Employment by sex, age and professional status", {"sinceTimePeriod": "2021"}),
        ("lfsa_urgaed", "Unemployment rates by sex, age and education", {"sinceTimePeriod": "2021"}),
        ("lfsa_egised", "Employment by sex, age and economic activity (NACE)", {"sinceTimePeriod": "2021"}),
        ("lfsa_epgaed", "Employment rates by sex, age and education", {"sinceTimePeriod": "2021"}),
        ("lfsa_ergan", "Employment rates by sex, age and citizenship", {"sinceTimePeriod": "2021"}),
    ],
    "income": [
        ("ilc_di03", "Mean equivalised net income by age and sex", {"sinceTimePeriod": "2020"}),
        ("ilc_di01", "Distribution of income by quantiles", {"sinceTimePeriod": "2020"}),
        ("ilc_di04", "Mean equivalised net income by household type", {"sinceTimePeriod": "2020"}),
        ("ilc_di11", "Median equivalised net income", {"sinceTimePeriod": "2020"}),
    ],
    "civil_status": [
        ("demo_pjanmarst", "Population by marital status and sex (discontinued?)", {"sinceTimePeriod": "2020"}),
        ("cens_01rms", "Census: population by marital status", {"sinceTimePeriod": "2011"}),
    ],
    "household": [
        ("ilc_lvph01", "Distribution of population by household type", {"sinceTimePeriod": "2020"}),
        ("lfst_hhnhtych", "Households by type", {"sinceTimePeriod": "2020"}),
        ("ilc_lvph02", "Distribution of households by household size", {"sinceTimePeriod": "2020"}),
    ],
    "occupation": [
        ("lfsa_eisn2", "Employment by occupation (ISCO-08)", {"sinceTimePeriod": "2021"}),
        ("lfsa_egised", "Employment by NACE sector", {"sinceTimePeriod": "2021"}),
    ],
}

# Key filters to try on ISTAT sub-dataflows
ISTAT_KEY_FILTERS: list[tuple[str, str]] = [
    ("", "no filter"),
    ("A.IT............", "annual, Italy only (broad)"),
    ("A...............", "annual only (broadest)"),
]


def discover_child_dataflows(
    catalog: list[DataflowInfo], parent_prefix: str
) -> list[DataflowInfo]:
    """Find all child dataflows with IDs starting with the parent prefix."""
    children = [
        df for df in catalog
        if df.id.startswith(parent_prefix + "_DF_")
        and not df.is_file_only
    ]
    children.sort(key=lambda d: d.id)
    return children


def run_field_discovery(
    field_name: str,
    catalog: list[DataflowInfo],
    *,
    max_per_field: int = 10,
    skip_probes: bool = False,
    csv_only: bool = False,
) -> FieldDiscovery:
    """Run full discovery for a single demographic field."""
    keywords = FIELD_KEYWORDS.get(field_name, [])
    disc = FieldDiscovery(field_name=field_name, keywords=keywords)

    print(f"\n{'='*70}")
    print(f"FIELD: {field_name}")
    print(f"Keywords: {keywords}")
    print(f"{'='*70}")

    # Step 1: Find known child dataflows
    parent_info = KNOWN_PARENTS.get(field_name)
    if parent_info:
        prefix = parent_info["parent_prefix"]
        children = discover_child_dataflows(catalog, prefix)
        print(f"\n  Known parent: {prefix} ({parent_info['description']})")
        print(f"  Found {len(children)} child dataflows:")
        for ch in children:
            print(f"    {ch.id:55s}  {ch.name_en}")
        disc.candidates.extend(children)

    # Step 2: Keyword search for additional candidates
    kw_results = search_catalog(
        catalog, keywords,
        exclude_file_only=True,
        exclude_old_regulation=True,
    )
    new_candidates = [
        (df, score) for df, score in kw_results
        if df not in disc.candidates
    ]
    if new_candidates:
        print(f"\n  Keyword search found {len(new_candidates)} additional candidates (top {max_per_field}):")
        for df, score in new_candidates[:max_per_field]:
            print(f"    [{score:2d}] {df.id:55s}  {df.name_en}")
            disc.candidates.append(df)

    if skip_probes:
        return disc

    # Step 3: Probe known child dataflows
    if parent_info:
        children_to_probe = disc.candidates[:max_per_field]

        if csv_only:
            # CSV-only mode: skip JSON probes, only test CSV format (much faster)
            print(f"\n  Probing {len(children_to_probe)} child dataflows (CSV format)...")
            for ch in children_to_probe:
                print(f"    CSV probe: {ch.id}")
                result = probe_istat_csv(ch.id, ch.name_en)
                disc.probe_results.append(result)
                _print_probe_result(result)
        else:
            # Full mode: test JSON with key filters, then CSV for comparison
            print(f"\n  Probing {len(children_to_probe)} child dataflows (JSON + CSV)...")
            for ch in children_to_probe:
                # JSON probe (no filter only — key filters rarely help)
                print(f"    JSON probe: {ch.id}")
                json_result = probe_istat_dataflow(ch.id, ch.name_en, key_filter="")
                disc.probe_results.append(json_result)
                _print_probe_result(json_result)

                # CSV probe (the workaround)
                print(f"    CSV probe:  {ch.id}")
                csv_result = probe_istat_csv(ch.id, ch.name_en)
                disc.probe_results.append(csv_result)
                _print_probe_result(csv_result)

    # Step 4: Probe Eurostat alternatives
    eurostat_alts = EUROSTAT_ALTERNATIVES.get(field_name, [])
    if eurostat_alts:
        print(f"\n  Probing {len(eurostat_alts)} Eurostat alternatives...")
        for ds_code, ds_name, ds_params in eurostat_alts:
            print(f"    Probing eurostat:{ds_code} — {ds_name}")
            result = probe_eurostat_dataset(ds_code, ds_name, params=ds_params)
            disc.probe_results.append(result)
            _print_probe_result(result)

    return disc


def _print_probe_result(r: ProbeResult) -> None:
    """Print a single probe result with color-coded status."""
    status_icon = {
        "ok": "OK",
        "null_obs": "NULL",
        "error": "ERR",
        "timeout": "TIMEOUT",
        "cached": "CACHE",
    }.get(r.status, "???")

    obs_info = f"{r.n_non_null_obs}/{r.n_total_obs} non-null obs" if r.n_total_obs > 0 else "no observations"

    print(f"      [{status_icon:7s}] {r.n_series:5d} series, {obs_info}", end="")
    if r.elapsed_s > 0:
        print(f"  ({r.elapsed_s:.1f}s)", end="")
    if r.error_msg:
        print(f"  ERROR: {r.error_msg}", end="")
    if r.dimensions:
        print(f"\n               dims: {r.dimensions}", end="")
    if r.sample_values:
        print(f"\n               sample: {r.sample_values[:5]}", end="")
    print()


# ---------------------------------------------------------------------------
# Summary and reporting
# ---------------------------------------------------------------------------

def print_summary(discoveries: list[FieldDiscovery]) -> None:
    """Print a final summary matrix of all discoveries."""
    print("\n")
    print("=" * 80)
    print("DISCOVERY SUMMARY")
    print("=" * 80)

    col_w = [18, 40, 10, 12, 20]
    header = (
        f"{'Field':<{col_w[0]}}  "
        f"{'Best Source':<{col_w[1]}}  "
        f"{'Status':<{col_w[2]}}  "
        f"{'Non-null Obs':<{col_w[3]}}  "
        f"{'Dimensions':<{col_w[4]}}"
    )
    sep = "-" * (sum(col_w) + 8)
    print(sep)
    print(header)
    print(sep)

    for disc in discoveries:
        ok_results = [r for r in disc.probe_results if r.status == "ok"]
        null_results = [r for r in disc.probe_results if r.status == "null_obs"]
        err_results = [r for r in disc.probe_results if r.status in ("error", "timeout")]

        if ok_results:
            best = max(ok_results, key=lambda r: r.n_non_null_obs)
            src = f"{best.dataflow_id}"
            if best.key_filter:
                src += f" [{best.key_filter}]"
            status = "OK"
            obs = f"{best.n_non_null_obs}/{best.n_total_obs}"
            dims = ",".join(best.dimensions[:4])
        elif null_results:
            best = null_results[0]
            src = f"{best.dataflow_id} (null)"
            status = "NULL"
            obs = f"0/{best.n_total_obs}"
            dims = ",".join(best.dimensions[:4])
        elif err_results:
            best = err_results[0]
            src = best.dataflow_id
            status = best.status.upper()
            obs = "-"
            dims = best.error_msg[:20] if best.error_msg else "-"
        else:
            src = "(no probes run)"
            status = "-"
            obs = "-"
            dims = "-"

        print(
            f"{disc.field_name:<{col_w[0]}}  "
            f"{src:<{col_w[1]}}  "
            f"{status:<{col_w[2]}}  "
            f"{obs:<{col_w[3]}}  "
            f"{dims:<{col_w[4]}}"
        )

    print(sep)

    # Per-field detail for OK results
    print("\n--- WORKING SOURCES (non-null observations) ---")
    any_ok = False
    for disc in discoveries:
        ok_results = [r for r in disc.probe_results if r.status == "ok"]
        if ok_results:
            any_ok = True
            print(f"\n  {disc.field_name}:")
            for r in sorted(ok_results, key=lambda x: -x.n_non_null_obs):
                filt = f" [{r.key_filter}]" if r.key_filter else ""
                print(f"    {r.dataflow_id}{filt}: {r.n_non_null_obs} non-null / {r.n_total_obs} total obs")
                print(f"      name: {r.name}")
                if r.sample_values:
                    print(f"      sample: {r.sample_values[:5]}")
    if not any_ok:
        print("  (none found)")


def save_results(discoveries: list[FieldDiscovery], output_path: Path) -> None:
    """Save discovery results as JSON for later analysis."""
    results = {}
    for disc in discoveries:
        results[disc.field_name] = {
            "keywords": disc.keywords,
            "n_candidates": len(disc.candidates),
            "candidates": [{"id": c.id, "name_en": c.name_en, "dsd_id": c.dsd_id} for c in disc.candidates],
            "probe_results": [
                {
                    "dataflow_id": r.dataflow_id,
                    "name": r.name,
                    "key_filter": r.key_filter,
                    "status": r.status,
                    "n_series": r.n_series,
                    "n_non_null_obs": r.n_non_null_obs,
                    "n_total_obs": r.n_total_obs,
                    "dimensions": r.dimensions,
                    "sample_values": r.sample_values,
                    "error_msg": r.error_msg,
                    "elapsed_s": r.elapsed_s,
                }
                for r in disc.probe_results
            ],
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Systematic discovery of working ISTAT SDMX dataflows for Italian "
            "demographic data. Parses the cached dataflow catalog, searches by "
            "keyword, and probes candidates for non-null observation data."
        ),
    )
    parser.add_argument(
        "--field",
        choices=list(FIELD_KEYWORDS.keys()) + ["all"],
        default="all",
        help="Which demographic field to discover (default: all).",
    )
    parser.add_argument(
        "--keyword",
        type=str,
        default=None,
        help="Free-text keyword search (overrides --field).",
    )
    parser.add_argument(
        "--max-per-field",
        type=int,
        default=10,
        help="Max candidates to probe per field (default: 10).",
    )
    parser.add_argument(
        "--cache-only",
        action="store_true",
        help="Only use cached API responses; skip real API calls.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Always fetch fresh; ignore and overwrite cache.",
    )
    parser.add_argument(
        "--skip-probes",
        action="store_true",
        help="Only run catalog search; don't probe any endpoints.",
    )
    parser.add_argument(
        "--csv-only",
        action="store_true",
        help="Only probe ISTAT with CSV format (fast; skips broken JSON probes).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Save results as JSON to this path.",
    )
    return parser.parse_args()


def main() -> None:
    global _cache_only, _no_cache

    args = _parse_args()
    _cache_only = args.cache_only
    _no_cache = args.no_cache

    print("=" * 70)
    print("ISTAT / Eurostat Dataflow Discovery")
    print(f"Catalog  : {_CATALOG_FILE}")
    print(f"Cache dir: {_CACHE_DIR}")
    print(f"Mode     : {'cache-only' if _cache_only else 'no-cache' if _no_cache else 'cache-first'}")
    print("=" * 70)

    if not _CATALOG_FILE.exists():
        print(f"\nERROR: Catalog file not found: {_CATALOG_FILE}")
        print("Run `python scripts/prototype_istat_api.py` first to fetch the catalog.")
        return

    catalog = parse_catalog(_CATALOG_FILE)

    # Free-text keyword search mode
    if args.keyword:
        keywords = [kw.strip() for kw in args.keyword.split(",")]
        print(f"\nFree-text search: {keywords}")
        results = search_catalog(catalog, keywords, exclude_file_only=True)
        print(f"Found {len(results)} matches:")
        for df, score in results[:30]:
            print(f"  [{score:2d}] {df.id:55s}  {df.name_en}")
            if df.name_it and df.name_it != df.name_en:
                print(f"        IT: {df.name_it}")
            if df.layout_row:
                print(f"        row={df.layout_row}  col={df.layout_column}")
        return

    # Field-based discovery
    if args.field == "all":
        fields = list(FIELD_KEYWORDS.keys())
    else:
        fields = [args.field]

    discoveries: list[FieldDiscovery] = []
    for field_name in fields:
        disc = run_field_discovery(
            field_name,
            catalog,
            max_per_field=args.max_per_field,
            skip_probes=args.skip_probes,
            csv_only=args.csv_only,
        )
        discoveries.append(disc)

    print_summary(discoveries)

    if args.output:
        save_results(discoveries, Path(args.output))
    else:
        default_output = _PROJECT_ROOT / "data" / "istat_discovery" / "discovery_results.json"
        save_results(discoveries, default_output)

    print("\nDone.")


if __name__ == "__main__":
    main()
