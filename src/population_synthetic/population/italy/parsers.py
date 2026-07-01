"""Parsers turning raw ISTAT/Eurostat responses into distributions.

Converts ISTAT SDMX CSV rows and Eurostat JSON-stat 2.0 payloads into the
normalised probability dictionaries consumed by the Italy fetch service.
Includes helpers for extracting observation values and selecting the
latest annual time period from SDMX rows.
"""
from __future__ import annotations

import logging

from population_synthetic.population.helpers import VALID_AGE_GROUPS, resolve_age_group  # noqa: F401

from .constants import (
    CIVIL_STATUS_MAP,
    NUTS2_REGION_CODES,
    SEX_LABEL_MAP,
)

logger = logging.getLogger(__name__)


def _csv_obs_value(row: dict) -> float | None:
    """Extract OBS_VALUE from a CSV row, returning None if missing/empty/NaN."""
    val = row.get("OBS_VALUE", "").strip()
    if not val or val.lower() == "nan":
        return None
    try:
        return float(val)
    except ValueError:
        return None


def _csv_latest_year_rows(
    rows: list[dict], time_col: str = "TIME_PERIOD", freq: str = "A",
) -> list[dict]:
    """Filter rows to only the latest annual TIME_PERIOD value.

    Pre-filters to ``FREQ == freq`` so quarterly periods (e.g. ``2020-Q4``)
    don't shadow annual ones when selecting ``max(TIME_PERIOD)``.
    """
    if freq:
        rows = [r for r in rows if r.get("FREQ", "").strip() == freq]
    years: set[str] = set()
    for row in rows:
        tp = row.get(time_col, "").strip()
        if tp:
            years.add(tp)
    if not years:
        return rows
    latest = max(years)
    return [r for r in rows if r.get(time_col, "").strip() == latest]


# ---------------------------------------------------------------------------
# Internal helpers for Eurostat JSON-stat 2.0 parsing
# ---------------------------------------------------------------------------

def _compute_strides(id_list: list[str], size: list[int]) -> dict[str, int]:
    """Compute row-major strides for each dimension from the id/size lists."""
    strides: dict[str, int] = {}
    s = 1
    for dim_id, dim_size in zip(reversed(id_list), reversed(size)):
        strides[dim_id] = s
        s *= dim_size
    return strides


def _latest_time_index(dims: dict) -> int:
    """Return the positional index of the latest time period in the time dimension."""
    time_key = next((k for k in dims if k == "time"), None)
    if time_key is None:
        return 0
    time_codes = list(dims[time_key]["category"]["label"].keys())
    return len(time_codes) - 1


def _get_value(values: dict | list, idx: int) -> float | None:
    """Retrieve a value from either a sparse dict or a dense list by flat index."""
    if isinstance(values, dict):
        v = values.get(str(idx))
    else:
        v = values[idx] if idx < len(values) else None
    if v is None:
        return None
    return float(v)


# ---------------------------------------------------------------------------
# Eurostat JSON-stat 2.0 public parsers
# ---------------------------------------------------------------------------

def parse_age_sex(raw: dict) -> dict[tuple[int, str], float]:
    """Parse ``demo_pjan`` response into ``{(age, sex): probability}``.

    Filters to ages 18–85 and biological sexes (M/F). Uses the latest
    available year. geo=IT is fixed (size=1 in the response).
    """
    dims = raw.get("dimension", {})
    id_list: list[str] = raw.get("id", list(dims.keys()))
    size: list[int] = raw.get("size", [len(dims[k]["category"]["label"]) for k in id_list])
    values = raw.get("value", {})

    age_key = next((k for k in id_list if k == "age"), None)
    sex_key = next((k for k in id_list if k == "sex"), None)
    time_key = next((k for k in id_list if k == "time"), None)

    if age_key is None or sex_key is None:
        raise ValueError(
            f"Could not identify age/sex dimensions in Eurostat demo_pjan response; id={id_list}"
        )

    age_cats = list(dims[age_key]["category"]["label"].keys())
    sex_cats = list(dims[sex_key]["category"]["label"].keys())

    strides = _compute_strides(id_list, size)
    time_idx = _latest_time_index(dims) if time_key else 0

    counts: dict[tuple[int, str], float] = {}
    for ai, age_code in enumerate(age_cats):
        if not age_code.startswith("Y") or age_code.startswith("Y_"):
            continue
        try:
            age = int(age_code[1:])
        except ValueError:
            continue
        if not (18 <= age <= 85):
            continue

        for si, sex_code in enumerate(sex_cats):
            sex_label = SEX_LABEL_MAP.get(sex_code)
            if sex_label is None or sex_label == "Total":
                continue

            base = (
                ai * strides[age_key]
                + si * strides[sex_key]
            )
            if time_key:
                base += time_idx * strides[time_key]

            v = _get_value(values, base)
            if v is None:
                continue
            key: tuple[int, str] = (age, sex_label)
            counts[key] = counts.get(key, 0.0) + v

    if not counts:
        raise ValueError("No age/sex data parsed from Eurostat demo_pjan response")
    total = sum(counts.values()) or 1.0
    return {k: v / total for k, v in counts.items()}


def parse_region(raw: dict) -> dict[str, float]:
    """Parse ``demo_r_pjangrp3`` response into ``{region_name: probability}``.

    Filters geo dimension to Italian NUTS2 codes only. Sums over all age
    groups and sexes. Uses latest available year.

    Raises ``ValueError`` if no Italian NUTS2 codes are found in the geo
    dimension — suggesting ``demo_r_d2jan`` as alternative.
    """
    dims = raw.get("dimension", {})
    id_list: list[str] = raw.get("id", list(dims.keys()))
    size: list[int] = raw.get("size", [len(dims[k]["category"]["label"]) for k in id_list])
    values = raw.get("value", {})

    geo_key = next((k for k in id_list if k == "geo"), None)
    time_key = next((k for k in id_list if k == "time"), None)

    if geo_key is None:
        raise ValueError(
            f"No geo dimension in Eurostat region response; id={id_list}. "
            "Try dataset 'demo_r_d2jan' as alternative."
        )

    geo_cats = list(dims[geo_key]["category"]["label"].keys())
    nuts2_indices = [(i, geo) for i, geo in enumerate(geo_cats) if geo in NUTS2_REGION_CODES]

    if not nuts2_indices:
        raise ValueError(
            f"No Italian NUTS2 codes found in geo dimension of Eurostat region response "
            f"(got {len(geo_cats)} geo codes: {geo_cats[:10]}...). "
            "Try dataset 'demo_r_d2jan' as alternative."
        )

    strides = _compute_strides(id_list, size)
    time_idx = _latest_time_index(dims) if time_key else 0

    # Sum over all dimensions except geo (and time fixed to latest)
    extra_keys = [k for k in id_list if k not in (geo_key,) and k != "time"]

    counts: dict[str, float] = {}
    for gi, nuts2_code in nuts2_indices:
        region_name = NUTS2_REGION_CODES[nuts2_code]
        base = gi * strides[geo_key]
        if time_key:
            base += time_idx * strides[time_key]

        # Enumerate all combinations of extra dimensions and sum
        if extra_keys:
            extra_sizes = [size[id_list.index(k)] for k in extra_keys]
            total_extra = 1
            for es in extra_sizes:
                total_extra *= es

            region_total = 0.0
            for ei in range(total_extra):
                extra_offset = 0
                remainder = ei
                for k, es in zip(reversed(extra_keys), reversed(extra_sizes)):
                    extra_offset += (remainder % es) * strides[k]
                    remainder //= es
                v = _get_value(values, base + extra_offset)
                if v is not None:
                    region_total += v
        else:
            v = _get_value(values, base)
            region_total = v if v is not None else 0.0

        counts[region_name] = counts.get(region_name, 0.0) + region_total

    if not counts:
        raise ValueError("No region data parsed from Eurostat region response")
    grand_total = sum(counts.values()) or 1.0
    return {k: v / grand_total for k, v in counts.items()}


def parse_housing_tenure(raw: dict) -> dict[str, float]:
    """Parse ``ilc_lvho02`` response into ``{tenure_label: probability}``.

    Filters to incgrp=TOTAL and hhcomp=TOTAL. Maps tenure codes to schema
    labels (Owner-occupied / Rental). Uses latest available year.
    """
    _TENURE_SCHEMA_MAP: dict[str, str] = {
        "OWN": "Owner-occupied",
        "OWN_L": "Owner-occupied",
        "OWN_NL": "Owner-occupied",
        "RENT": "Rental",
        "RENT_MKT": "Rental",
        "RENT_FR": "Rental",
    }

    dims = raw.get("dimension", {})
    id_list: list[str] = raw.get("id", list(dims.keys()))
    size: list[int] = raw.get("size", [len(dims[k]["category"]["label"]) for k in id_list])
    values = raw.get("value", {})

    tenure_key = next((k for k in id_list if k == "tenure"), None)
    incgrp_key = next((k for k in id_list if k == "incgrp"), None)
    hhcomp_key = next((k for k in id_list if k == "hhcomp"), None)
    time_key = next((k for k in id_list if k == "time"), None)

    if tenure_key is None or incgrp_key is None or hhcomp_key is None:
        raise ValueError(
            f"Could not identify tenure/incgrp/hhcomp dimensions in Eurostat ilc_lvho02 response; id={id_list}"
        )

    tenure_cats = list(dims[tenure_key]["category"]["label"].keys())
    incgrp_cats = list(dims[incgrp_key]["category"]["label"].keys())
    hhcomp_cats = list(dims[hhcomp_key]["category"]["label"].keys())

    incgrp_total_idx = next((i for i, c in enumerate(incgrp_cats) if c == "TOTAL"), None)
    hhcomp_total_idx = next((i for i, c in enumerate(hhcomp_cats) if c == "TOTAL"), None)

    if incgrp_total_idx is None or hhcomp_total_idx is None:
        raise ValueError(
            "Could not find TOTAL in incgrp or hhcomp dimensions of Eurostat ilc_lvho02 response"
        )

    strides = _compute_strides(id_list, size)
    time_idx = _latest_time_index(dims) if time_key else 0

    base = (
        incgrp_total_idx * strides[incgrp_key]
        + hhcomp_total_idx * strides[hhcomp_key]
    )
    if time_key:
        base += time_idx * strides[time_key]

    counts: dict[str, float] = {}
    for ti, tenure_code in enumerate(tenure_cats):
        schema_label = _TENURE_SCHEMA_MAP.get(tenure_code)
        if schema_label is None:
            continue
        v = _get_value(values, base + ti * strides[tenure_key])
        if v is None:
            continue
        counts[schema_label] = counts.get(schema_label, 0.0) + v

    if not counts:
        raise ValueError("No housing tenure data parsed from Eurostat ilc_lvho02 response")
    total = sum(counts.values()) or 1.0
    return {k: v / total for k, v in counts.items()}


# ---------------------------------------------------------------------------
# ISTAT age-band code helpers
# ---------------------------------------------------------------------------

_ISTAT_EDU_AGE_MAP: dict[str, str] = {
    "Y15-19": "18-24",
    "Y20-24": "18-24",
    "Y25-29": "25-34",
    "Y30-34": "25-34",
    "Y35-39": "35-44",
    "Y40-44": "35-44",
    "Y45-49": "45-54",
    "Y50-54": "45-54",
    "Y55-59": "55-64",
    "Y60-64": "55-64",
    "Y_GE65": "65-74",
}

_SKIP_EDU_AGE_CODES = frozenset({
    "Y_GE15", "Y15-24", "Y15-64", "Y15-74", "Y14-29",
    "Y25-34", "Y25-64", "Y35-64",
})

_ISTAT_EMP_AGE_MAP: dict[str, str] = {
    "Y15-24": "18-24",
    "Y20-24": "18-24",
    "Y25-34": "25-34",
    "Y35-44": "35-44",
    "Y45-54": "45-54",
    "Y55-64": "55-64",
    "Y65-74": "65-74",
}

_SKIP_EMP_AGE_CODES = frozenset({
    "Y15-29", "Y15-34", "Y15-64", "Y15-74", "Y_GE65",
})

_ISTAT_HOUSEHOLD_AGE_MAP: dict[str, list[str]] = {
    "Y_UN35": ["18-24", "25-34"],
    "Y35-44": ["35-44"],
    "Y45-54": ["45-54"],
    "Y55-64": ["55-64"],
    "Y_GE65": ["65-74", "75-85"],
    "TOTAL":  list(VALID_AGE_GROUPS),
}

# ---------------------------------------------------------------------------
# ISTAT SDMX education parser
# ---------------------------------------------------------------------------

_ISCED_CODE_MAP: dict[str, str] = {
    "11": "University Degree",
    "7": "University Degree",
    "3": "No Formal Education",
    "4": "No Formal Education",
    "5": "High School (Liceo/Professionale)",
    "6": "High School (Liceo/Professionale)",
}


def parse_education_by_age(rows: list[dict]) -> dict[tuple[str, str], dict[str, float]]:
    """Parse ``52_1194`` CSV rows into ``{(age_group, sex): {edu_label: prob}}``.

    Filters: annual, Italy (IT), total citizenship.
    Raises ``ValueError`` if no data is found.
    """
    istat_sex_map = {"1": "Male", "2": "Female"}
    latest = _csv_latest_year_rows(rows)

    accumulator: dict[tuple[str, str], dict[str, float]] = {}

    for row in latest:
        if row.get("FREQ", "").strip() != "A":
            continue
        if row.get("REF_AREA", "").strip() != "IT":
            continue
        citizenship = row.get("CITIZENSHIP", "").strip()
        if citizenship and citizenship not in ("TOTAL", "0", "99"):
            continue

        sex_label = istat_sex_map.get(row.get("SEX", "").strip())
        if sex_label is None:
            continue

        age_code = row.get("AGE", "").strip()
        if age_code in _SKIP_EDU_AGE_CODES:
            continue
        age_group = _ISTAT_EDU_AGE_MAP.get(age_code)
        if age_group is None:
            continue

        edu_code = row.get("EDU_LEV_HIGHEST", "").strip()
        edu_label = _ISCED_CODE_MAP.get(edu_code)
        if edu_label is None:
            continue

        obs_value = _csv_obs_value(row)
        if obs_value is None:
            continue

        cell = accumulator.setdefault((age_group, sex_label), {})
        cell[edu_label] = cell.get(edu_label, 0.0) + obs_value

    if not accumulator:
        raise ValueError(
            "No education data parsed from ISTAT 52_1194 CSV response. "
            "Clear config/database/caches/istat/ and re-run to fetch live data."
        )

    result: dict[tuple[str, str], dict[str, float]] = {}
    for key, dist in accumulator.items():
        total = sum(dist.values()) or 1.0
        result[key] = {k: v / total for k, v in dist.items()}
    return result


# ---------------------------------------------------------------------------
# ISTAT SDMX employment parser
# ---------------------------------------------------------------------------

_EMP_EDU_CODE_MAP: dict[str, str] = {
    "11": "University Degree",
    "13": "No Formal Education",
    "7": "High School (Liceo/Professionale)",
}

_NATIONAL_AGE_CODES = frozenset({"Y15-74", "Y15-64", "Y15-89"})

_EMP_ISTAT_SEX_MAP = {"1": "Male", "2": "Female"}


def parse_employment_by_sex_education(
    emp_rows: list[dict],
    edu_rows: list[dict],
) -> dict[str, dict[str, dict[str, float]]]:
    """Parse employment rates by sex × education from two ISTAT datasets.

    Derives per-(sex, education) employment rate from the ratio of employed
    persons (``150_938_17``) to total population (``52_1194``).  Categories:
    Employed, Not Employed.
    Raises ``ValueError`` if either dataset yields no usable data.
    """
    istat_sex_map = {"1": "Male", "2": "Female"}

    edu_latest = _csv_latest_year_rows(edu_rows)
    total_by_sex_edu: dict[str, dict[str, float]] = {}
    for row in edu_latest:
        if row.get("FREQ", "").strip() != "A":
            continue
        if row.get("REF_AREA", "").strip() != "IT":
            continue
        citizenship = row.get("CITIZENSHIP", "").strip()
        if citizenship and citizenship not in ("TOTAL", "0", "99"):
            continue
        sex_label = istat_sex_map.get(row.get("SEX", "").strip())
        if sex_label is None:
            continue
        age_code = row.get("AGE", "").strip()
        if age_code in _SKIP_EDU_AGE_CODES:
            continue
        if _ISTAT_EDU_AGE_MAP.get(age_code) is None:
            continue
        edu_code = row.get("EDU_LEV_HIGHEST", "").strip()
        edu_label = _ISCED_CODE_MAP.get(edu_code)
        if edu_label is None:
            continue
        obs_value = _csv_obs_value(row)
        if obs_value is None:
            continue
        sex_dict = total_by_sex_edu.setdefault(sex_label, {})
        sex_dict[edu_label] = sex_dict.get(edu_label, 0.0) + obs_value

    emp_latest = _csv_latest_year_rows(emp_rows)
    employed_by_sex_edu: dict[str, dict[str, float]] = {}
    for row in emp_latest:
        if row.get("FREQ", "").strip() != "A":
            continue
        ref_area = row.get("REF_AREA", "").strip()
        if ref_area and ref_area != "IT":
            continue
        sex_label = _EMP_ISTAT_SEX_MAP.get(row.get("SEX", "").strip())
        if sex_label is None:
            continue
        edu_code = row.get("EDU_LEV_HIGHEST", "").strip()
        edu_label = _EMP_EDU_CODE_MAP.get(edu_code)
        if edu_label is None:
            continue
        obs_value = _csv_obs_value(row)
        if obs_value is None:
            continue
        sex_dict = employed_by_sex_edu.setdefault(sex_label, {})
        sex_dict[edu_label] = sex_dict.get(edu_label, 0.0) + obs_value

    if not total_by_sex_edu:
        raise ValueError(
            "No total population data parsed from ISTAT 52_1194 for employment "
            "rate derivation. Clear config/database/caches/istat/ and re-run."
        )
    if not employed_by_sex_edu:
        raise ValueError(
            "No employed data parsed from ISTAT 150_938 for employment rate "
            "derivation. Clear config/database/caches/istat/ and re-run."
        )

    result: dict[str, dict[str, dict[str, float]]] = {}
    for sex in ("Male", "Female"):
        sex_totals = total_by_sex_edu.get(sex, {})
        sex_employed = employed_by_sex_edu.get(sex, {})
        if not sex_totals:
            raise ValueError(f"No total population data for sex={sex!r}")
        sex_result: dict[str, dict[str, float]] = {}
        for edu_label, total in sex_totals.items():
            if total <= 0:
                continue
            employed = sex_employed.get(edu_label, 0.0)
            emp_rate = min(employed / total, 1.0)
            sex_result[edu_label] = {
                "Employed": emp_rate,
                "Not Employed": 1.0 - emp_rate,
            }
        if not sex_result:
            raise ValueError(f"No valid employment rates computed for sex={sex!r}")
        result[sex] = sex_result

    return result


# ---------------------------------------------------------------------------
# ISTAT SDMX socioeconomic parser
# ---------------------------------------------------------------------------

def parse_socioeconomic(rows: list[dict]) -> dict[tuple[str, str], dict[str, float]]:
    """Parse ``32_292_DF_*_6`` CSV rows into ``{(age_group, sex): {class_label: prob}}``.

    Classifies observed income values into four socioeconomic classes using
    Eurostat AROP (0.60x) and OECD/Pew (1.00x, 2.00x) thresholds relative
    to the global median income across all cells.
    Raises ``ValueError`` if no income data is found.
    """
    latest = _csv_latest_year_rows(rows)
    istat_sex_map = {"1": "Male", "2": "Female"}

    income_by_age_sex: dict[tuple[str, str], list[float]] = {}
    all_incomes: list[float] = []

    for row in latest:
        sex_code = row.get("SEX_MAIN_PERCEPTOR", row.get("SEX", "")).strip()
        sex_label = istat_sex_map.get(sex_code)
        sex_labels = [sex_label] if sex_label else ["Male", "Female"]

        age_code = row.get("AGE_MAIN_EARNIER", row.get("AGE", "")).strip()
        age_groups = _ISTAT_HOUSEHOLD_AGE_MAP.get(age_code)
        if age_groups is None:
            continue
        age_groups_to_use = [g for g in age_groups if g in VALID_AGE_GROUPS]
        if not age_groups_to_use:
            continue

        obs_value = _csv_obs_value(row)
        if obs_value is None or obs_value <= 0:
            continue

        all_incomes.append(obs_value)
        for ag in age_groups_to_use:
            for sl in sex_labels:
                bucket = income_by_age_sex.setdefault((ag, sl), [])
                bucket.append(obs_value)

    if not all_incomes:
        raise ValueError(
            "No income data parsed from ISTAT 32_292 CSV response. "
            "Clear config/database/caches/istat/ and re-run to fetch live data."
        )

    global_median = sorted(all_incomes)[len(all_incomes) // 2]
    if global_median <= 0:
        raise ValueError("Global median income is non-positive — cannot classify")

    poverty_upper = 0.60 * global_median
    working_upper = 1.00 * global_median
    middle_upper = 2.00 * global_median

    def _classify(income: float) -> str:
        if income < poverty_upper:
            return "Poverty"
        if income < working_upper:
            return "Working Class"
        if income < middle_upper:
            return "Middle Class"
        return "Wealthy"

    result: dict[tuple[str, str], dict[str, float]] = {}
    for ag in VALID_AGE_GROUPS:
        for sex in ("Male", "Female"):
            incomes = income_by_age_sex.get((ag, sex))
            if not incomes:
                raise ValueError(
                    f"No income data for age_group={ag!r}, sex={sex!r}"
                )
            class_counts: dict[str, float] = {
                "Poverty": 0.0,
                "Working Class": 0.0,
                "Middle Class": 0.0,
                "Wealthy": 0.0,
            }
            for inc in incomes:
                class_counts[_classify(inc)] += 1.0
            total = sum(class_counts.values())
            result[(ag, sex)] = {k: v / total for k, v in class_counts.items()}

    return result


# ---------------------------------------------------------------------------
# ISTAT SDMX civil status parser
# ---------------------------------------------------------------------------

def parse_civil_status_by_age_sex(rows: list[dict]) -> dict[tuple[str, str], dict[str, float]]:
    """Parse ``22_289_DF_DCIS_POPRES1_25`` CSV rows into ``{(age_group, sex): {status: prob}}``.

    Searches defensively for marital status column using several possible names.
    Raises ``ValueError`` if no data is found.
    """
    latest = _csv_latest_year_rows(rows)

    _MARITAL_COL_CANDIDATES = ("MARITAL_STATUS", "CIVIL_STATUS", "STATO_CIVILE", "CONIUG")
    _IT_CODES = frozenset({"IT", "TOTAL", "0", "ITA"})
    istat_sex_map = {"1": "Male", "2": "Female", "M": "Male", "F": "Female"}

    marital_col: str | None = None
    if latest:
        cols = set(latest[0].keys())
        for candidate in _MARITAL_COL_CANDIDATES:
            if candidate in cols:
                marital_col = candidate
                break
        if marital_col is None:
            for col in cols:
                up = col.upper()
                if any(kw in up for kw in ("MARITAL", "CIVIL", "STATO", "CONIUG")):
                    marital_col = col
                    break

    if marital_col is None:
        raise ValueError(
            "Cannot find marital/civil status column in ISTAT 22_289 CSV response. "
            f"Available columns: {list(latest[0].keys()) if latest else '(empty)'}"
        )

    accumulator: dict[tuple[str, str], dict[str, float]] = {}

    for row in latest:
        freq = row.get("FREQ", "").strip()
        if freq and freq != "A":
            continue

        ref_area = row.get("REF_AREA", "").strip()
        if ref_area and ref_area not in _IT_CODES:
            continue

        sex_code = row.get("SEX", "").strip()
        sex_label = istat_sex_map.get(sex_code)
        if sex_label is None:
            continue

        age_code = row.get("AGE", "").strip()
        age_group = _ISTAT_EDU_AGE_MAP.get(age_code) or _ISTAT_EMP_AGE_MAP.get(age_code)
        if age_group is None:
            mapped = _ISTAT_HOUSEHOLD_AGE_MAP.get(age_code, [])
            if mapped and mapped[0] in VALID_AGE_GROUPS:
                age_group = mapped[0]
        if age_group is None or age_group not in VALID_AGE_GROUPS:
            continue

        marital_code = row.get(marital_col, "").strip()
        status_label = CIVIL_STATUS_MAP.get(marital_code)
        if status_label is None:
            continue

        obs_value = _csv_obs_value(row)
        if obs_value is None:
            continue

        cell = accumulator.setdefault((age_group, sex_label), {})
        cell[status_label] = cell.get(status_label, 0.0) + obs_value

    if not accumulator:
        raise ValueError(
            "No civil status data parsed from ISTAT 22_289 CSV response. "
            "Clear the cache and retry."
        )

    result: dict[tuple[str, str], dict[str, float]] = {}
    for key, dist in accumulator.items():
        total = sum(dist.values()) or 1.0
        result[key] = {k: v / total for k, v in dist.items()}
    return result


# ---------------------------------------------------------------------------
# ISTAT SDMX industry sector parser
# ---------------------------------------------------------------------------

_OCCUPATION_2011_SCHEMA_MAP: dict[str, str] = {
    "10": "Professional & Managerial",
    "20": "Clerical & Administrative",
    "30": "Craft & Technical",
    "40": "Elementary Occupations",
}


def parse_industry_sector(rows: list[dict]) -> dict[str, float]:
    """Parse OCCUPATION_2011 from ``150_938_DF_*_14`` CSV into ``{sector_label: probability}``.

    Filters: annual, REF_AREA=IT, SEX=total. Skips OCCUPATION_2011 code '99'
    (total). Raises ``ValueError`` if no data found.
    """
    latest = _csv_latest_year_rows(rows)

    accumulator: dict[str, float] = {}
    found_any = False

    for row in latest:
        if row.get("FREQ", "").strip() != "A":
            continue
        ref_area = row.get("REF_AREA", "").strip()
        if ref_area and ref_area != "IT":
            continue

        sex_code = row.get("SEX", "").strip()
        if sex_code != "9":
            continue

        occ2011_code = row.get("OCCUPATION_2011", "").strip()
        if occ2011_code == "99":
            continue
        schema_label = _OCCUPATION_2011_SCHEMA_MAP.get(occ2011_code)
        if schema_label is None:
            continue

        obs_value = _csv_obs_value(row)
        if obs_value is None:
            continue

        found_any = True
        accumulator[schema_label] = accumulator.get(schema_label, 0.0) + obs_value

    if not found_any:
        raise ValueError(
            "No industry sector data parsed from ISTAT 150_938 OCCUPATION_2011 CSV. "
            "Clear config/database/caches/istat/ and re-run to fetch live data."
        )

    total = sum(accumulator.values()) or 1.0
    return {k: v / total for k, v in accumulator.items()}


# ---------------------------------------------------------------------------
# ISTAT SDMX employment type parser
# ---------------------------------------------------------------------------

def parse_employment_type_by_age(rows: list[dict]) -> dict[tuple[str, str], dict[str, float]]:
    """Parse FULL_PART_TIME × PERM_TEMP_EMPLOYEES from ``150_938_DF_*_18`` CSV.

    Returns ``{(age_group, sex): {composite_key: probability}}`` where
    composite_key is ``"{contract}|{hours}"``, e.g. ``"Permanent|Full-time"``.

    Child dataflow ``_18`` provides prof_status × FT/PT. If both FT/PT and
    PERM_TEMP columns are present, composite keys are used. If only FT/PT
    is meaningful (PERM_TEMP fixed at total), FT/PT-only labels are used with
    Italian census perm/temp splits applied.

    Raises ``ValueError`` if no data found.
    """
    latest = _csv_latest_year_rows(rows)
    istat_sex_map = {"1": "Male", "2": "Female"}
    fpt_label_map = {"1": "Full-time", "2": "Part-time"}
    perm_temp_label_map = {"1": "Temporary", "2": "Permanent"}

    has_perm_temp_variation = False
    if latest:
        perm_temp_vals = {r.get("PERM_TEMP_EMPLOYEES", "").strip() for r in latest}
        perm_temp_vals.discard("")
        perm_temp_vals.discard("9")
        perm_temp_vals.discard("99")
        has_perm_temp_variation = len(perm_temp_vals) > 1

    accumulator: dict[tuple[str, str], dict[str, float]] = {}
    found_any = False

    for row in latest:
        if row.get("FREQ", "").strip() != "A":
            continue
        ref_area = row.get("REF_AREA", "").strip()
        if ref_area and ref_area != "IT":
            continue

        fpt_code = row.get("FULL_PART_TIME", "").strip()
        if fpt_code in ("9", "99", ""):
            continue
        fpt_label = fpt_label_map.get(fpt_code)
        if fpt_label is None:
            continue

        if has_perm_temp_variation:
            perm_temp_code = row.get("PERM_TEMP_EMPLOYEES", "").strip()
            if perm_temp_code in ("9", "99", ""):
                continue
            perm_temp_label = perm_temp_label_map.get(perm_temp_code)
            if perm_temp_label is None:
                continue
            composite = f"{perm_temp_label}|{fpt_label}"
        else:
            composite = f"Unspecified|{fpt_label}"

        sex_code = row.get("SEX", "").strip()
        sex_label = istat_sex_map.get(sex_code)
        if sex_label is None:
            continue

        age_code = row.get("AGE", "").strip()
        if age_code in _SKIP_EMP_AGE_CODES or age_code in _NATIONAL_AGE_CODES:
            age_group = "ALL"
        else:
            age_group = _ISTAT_EMP_AGE_MAP.get(age_code)
            if age_group is None:
                continue

        obs_value = _csv_obs_value(row)
        if obs_value is None:
            continue

        found_any = True
        cell_key = (age_group, sex_label)
        cell = accumulator.setdefault(cell_key, {})
        cell[composite] = cell.get(composite, 0.0) + obs_value

    if not found_any:
        raise ValueError(
            "No employment type data parsed from ISTAT 150_938 CSV. "
            "Clear config/database/caches/istat/ and re-run to fetch live data."
        )

    normalized: dict[tuple[str, str], dict[str, float]] = {}
    agg_by_sex: dict[str, dict[str, float]] = {}

    for (age_group, sex_label), dist in accumulator.items():
        total = sum(dist.values()) or 1.0
        norm_dist = {k: v / total for k, v in dist.items()}
        normalized[(age_group, sex_label)] = norm_dist
        if age_group == "ALL":
            agg_by_sex[sex_label] = norm_dist

    result: dict[tuple[str, str], dict[str, float]] = {}
    for ag in VALID_AGE_GROUPS:
        for sex in ("Male", "Female"):
            specific = normalized.get((ag, sex))
            if specific:
                result[(ag, sex)] = specific
            elif sex in agg_by_sex:
                result[(ag, sex)] = agg_by_sex[sex]
    return result


# ---------------------------------------------------------------------------
# Eurostat household size parser
# ---------------------------------------------------------------------------


def parse_household_size(raw: dict) -> dict[str, float]:
    """Parse ``ilc_lvph03`` response into ``{size_label: probability}``.

    Uses the ``n_person`` dimension (codes: 1, 2, 3, 4, 5, GE6).
    Unit is percentage (PC). Uses latest available year.
    Raises ``ValueError`` if no data found.
    """
    dims = raw.get("dimension", {})
    id_list: list[str] = raw.get("id", list(dims.keys()))
    size: list[int] = raw.get("size", [len(dims[k]["category"]["label"]) for k in id_list])
    values = raw.get("value", {})

    nperson_key = next((k for k in id_list if k == "n_person"), None)
    time_key = next((k for k in id_list if k == "time"), None)

    if nperson_key is None:
        raise ValueError(
            f"No 'n_person' dimension in Eurostat ilc_lvph03 response; id={id_list}"
        )

    nperson_cats = list(dims[nperson_key]["category"]["label"].keys())
    nperson_labels = dims[nperson_key]["category"]["label"]

    strides = _compute_strides(id_list, size)
    time_idx = _latest_time_index(dims) if time_key else 0

    extra_keys = [k for k in id_list if k not in (nperson_key,) and k != "time"]

    counts: dict[str, float] = {}
    for ni, np_code in enumerate(nperson_cats):
        label = nperson_labels.get(np_code, np_code)
        base = ni * strides[nperson_key]
        if time_key:
            base += time_idx * strides[time_key]

        if extra_keys:
            extra_sizes = [size[id_list.index(k)] for k in extra_keys]
            total_extra = 1
            for es in extra_sizes:
                total_extra *= es
            np_total = 0.0
            for ei in range(total_extra):
                extra_offset = 0
                remainder = ei
                for k, es in zip(reversed(extra_keys), reversed(extra_sizes)):
                    extra_offset += (remainder % es) * strides[k]
                    remainder //= es
                v = _get_value(values, base + extra_offset)
                if v is not None:
                    np_total += v
        else:
            v = _get_value(values, base)
            np_total = v if v is not None else 0.0

        if np_total > 0:
            counts[label] = counts.get(label, 0.0) + np_total

    if not counts:
        raise ValueError("No household size data parsed from Eurostat ilc_lvph03 response")
    total = sum(counts.values()) or 1.0
    return {k: v / total for k, v in counts.items()}




_EU27_CODES = frozenset({
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES",
    "FI", "FR", "HR", "HU", "IE", "LT", "LU", "LV", "MT", "NL",
    "PL", "PT", "RO", "SE", "SI", "SK",
})


def _is_country_code(code: str) -> bool:
    return len(code) == 2 and code.isalpha() and code.isupper()


def parse_birth_location(raw: dict) -> dict[str, float]:
    """Parse ``migr_pop1ctz`` response into ``{location_label: probability}``.

    Derives a 3-category birth-location proxy from citizenship dimension:
    - 'IT' → "Italy"
    - EU27 member codes → "Europe (Other)"
    - all other non-aggregate country codes → "Outside Europe"
    Aggregate codes ('TOTAL', 'EU27_2020', etc.) are skipped.
    Raises ``ValueError`` if result is empty.
    """

    dims = raw.get("dimension", {})
    id_list: list[str] = raw.get("id", list(dims.keys()))
    size: list[int] = raw.get("size", [len(dims[k]["category"]["label"]) for k in id_list])
    values = raw.get("value", {})

    citizen_key = next((k for k in id_list if k == "citizen"), None)
    time_key = next((k for k in id_list if k == "time"), None)

    if citizen_key is None:
        raise ValueError(
            f"No 'citizen' dimension found in Eurostat migr_pop1ctz response; id={id_list}"
        )

    citizen_cats = list(dims[citizen_key]["category"]["label"].keys())
    strides = _compute_strides(id_list, size)
    time_idx = _latest_time_index(dims) if time_key else 0

    # Use TOTAL for non-citizen dimensions where available, or sum all
    extra_keys = [k for k in id_list if k not in (citizen_key,) and k != "time"]

    counts: dict[str, float] = {}
    for ci, ctz_code in enumerate(citizen_cats):
        if not _is_country_code(ctz_code):
            continue
        if ctz_code == "IT":
            label = "Italy"
        elif ctz_code in _EU27_CODES:
            label = "Europe (Other)"
        else:
            label = "Outside Europe"

        base = ci * strides[citizen_key]
        if time_key:
            base += time_idx * strides[time_key]

        if extra_keys:
            extra_sizes = [size[id_list.index(k)] for k in extra_keys]
            total_extra = 1
            for es in extra_sizes:
                total_extra *= es

            ctz_total = 0.0
            for ei in range(total_extra):
                extra_offset = 0
                remainder = ei
                for k, es in zip(reversed(extra_keys), reversed(extra_sizes)):
                    extra_offset += (remainder % es) * strides[k]
                    remainder //= es
                v = _get_value(values, base + extra_offset)
                if v is not None:
                    ctz_total += v
        else:
            v = _get_value(values, base)
            ctz_total = v if v is not None else 0.0

        counts[label] = counts.get(label, 0.0) + ctz_total

    if not counts:
        raise ValueError("No birth location data parsed from Eurostat migr_pop1ctz response")
    total = sum(counts.values()) or 1.0
    return {k: v / total for k, v in counts.items()}


_EUROSTAT_COUNTRY_CODES: dict[str, str] = {
    "RO": "Romania", "AL": "Albania", "MA": "Morocco", "CN": "China",
    "UA": "Ukraine", "PH": "Philippines", "MD": "Moldova", "IN": "India",
    "BD": "Bangladesh", "PK": "Pakistan", "NG": "Nigeria", "EG": "Egypt",
    "SN": "Senegal", "TN": "Tunisia", "RS": "Serbia", "MK": "North Macedonia",
    "SR": "Suriname", "PE": "Peru", "EC": "Ecuador", "BR": "Brazil",
    "DE": "Germany", "FR": "France", "ES": "Spain", "PL": "Poland",
    "RU": "Russia", "TR": "Turkey",
}

_BIRTH_COUNTRY_AGGREGATE_CODES = frozenset({
    "TOTAL", "EU27_2020", "EU28", "NEU28", "NEU27_2020_EFTA", "EEA31", "OTH", "UNK",
})


def parse_birth_country_detail(raw: dict) -> dict[tuple[str, str], dict[str, float]]:
    """Parse ``migr_pop1ctz`` response into ``{(age_group, sex): {country: probability}}``.

    Extracts top non-IT citizenships as birth country proxy. Countries not in
    ``_EUROSTAT_COUNTRY_CODES`` are aggregated to "Other". Excludes 'IT' and
    aggregate codes. Expands the marginal distribution to all
    ``VALID_AGE_GROUPS × {Male, Female}``.
    Raises ``ValueError`` if no data found after parsing.
    """
    dims = raw.get("dimension", {})
    id_list: list[str] = raw.get("id", list(dims.keys()))
    size: list[int] = raw.get("size", [len(dims[k]["category"]["label"]) for k in id_list])
    values = raw.get("value", {})

    citizen_key = next((k for k in id_list if k == "citizen"), None)
    time_key = next((k for k in id_list if k == "time"), None)

    if citizen_key is None:
        raise ValueError(
            f"No 'citizen' dimension found in Eurostat migr_pop1ctz response; id={id_list}"
        )

    citizen_cats = list(dims[citizen_key]["category"]["label"].keys())
    strides = _compute_strides(id_list, size)
    time_idx = _latest_time_index(dims) if time_key else 0

    extra_keys = [k for k in id_list if k not in (citizen_key,) and k != "time"]

    marginal: dict[str, float] = {}
    for ci, ctz_code in enumerate(citizen_cats):
        if not _is_country_code(ctz_code) or ctz_code == "IT":
            continue

        country_name = _EUROSTAT_COUNTRY_CODES.get(ctz_code, "Other")

        base = ci * strides[citizen_key]
        if time_key:
            base += time_idx * strides[time_key]

        if extra_keys:
            extra_sizes = [size[id_list.index(k)] for k in extra_keys]
            total_extra = 1
            for es in extra_sizes:
                total_extra *= es

            ctz_total = 0.0
            for ei in range(total_extra):
                extra_offset = 0
                remainder = ei
                for k, es in zip(reversed(extra_keys), reversed(extra_sizes)):
                    extra_offset += (remainder % es) * strides[k]
                    remainder //= es
                v = _get_value(values, base + extra_offset)
                if v is not None:
                    ctz_total += v
        else:
            v = _get_value(values, base)
            ctz_total = v if v is not None else 0.0

        marginal[country_name] = marginal.get(country_name, 0.0) + ctz_total

    if not marginal:
        raise ValueError("No birth country detail data parsed from Eurostat migr_pop1ctz response")
    total = sum(marginal.values()) or 1.0
    marginal_norm = {k: v / total for k, v in marginal.items()}

    return {
        (age_group, sex): dict(marginal_norm)
        for age_group in VALID_AGE_GROUPS
        for sex in ("Male", "Female")
    }


def parse_parental_structure(raw: dict) -> dict[str, float]:
    """Parse ``ilc_lvph02`` response into ``{household_type_label: probability}``.

    Uses the ``hhcomp`` dimension. Maps Eurostat household composition codes
    to schema labels. Uses latest available year.
    Raises ``ValueError`` if no data found.
    """
    _HHCOMP_SCHEMA_MAP: dict[str, str] = {
        "A1": "Living Alone",
        "A1_DCH": "Single Parent",
        "A2": "Couple without Children",
        "A2_DCH1": "Nuclear Family",
        "A2_DCH2": "Nuclear Family",
        "A2_DCH_GE3": "Nuclear Family",
        "A_GE3": "Extended Family",
        "A_GE3_DCH": "Extended Family",
    }

    dims = raw.get("dimension", {})
    id_list: list[str] = raw.get("id", list(dims.keys()))
    size_list: list[int] = raw.get("size", [len(dims[k]["category"]["label"]) for k in id_list])
    values = raw.get("value", {})

    hhcomp_key = next((k for k in id_list if k == "hhcomp"), None)
    time_key = next((k for k in id_list if k == "time"), None)

    if hhcomp_key is None:
        raise ValueError(
            f"No 'hhcomp' dimension in Eurostat ilc_lvph02 response; id={id_list}"
        )

    hhcomp_cats = list(dims[hhcomp_key]["category"]["label"].keys())

    strides = _compute_strides(id_list, size_list)
    time_idx = _latest_time_index(dims) if time_key else 0

    extra_keys = [k for k in id_list if k not in (hhcomp_key,) and k != "time"]

    counts: dict[str, float] = {}
    for hi, hh_code in enumerate(hhcomp_cats):
        schema_label = _HHCOMP_SCHEMA_MAP.get(hh_code)
        if schema_label is None:
            continue
        base = hi * strides[hhcomp_key]
        if time_key:
            base += time_idx * strides[time_key]

        if extra_keys:
            extra_sizes = [size_list[id_list.index(k)] for k in extra_keys]
            total_extra = 1
            for es in extra_sizes:
                total_extra *= es
            hh_total = 0.0
            for ei in range(total_extra):
                extra_offset = 0
                remainder = ei
                for k, es in zip(reversed(extra_keys), reversed(extra_sizes)):
                    extra_offset += (remainder % es) * strides[k]
                    remainder //= es
                v = _get_value(values, base + extra_offset)
                if v is not None:
                    hh_total += v
        else:
            v = _get_value(values, base)
            hh_total = v if v is not None else 0.0

        if hh_total > 0:
            counts[schema_label] = counts.get(schema_label, 0.0) + hh_total

    if not counts:
        raise ValueError("No parental structure data parsed from Eurostat ilc_lvph02 response")
    total = sum(counts.values()) or 1.0
    return {k: v / total for k, v in counts.items()}
