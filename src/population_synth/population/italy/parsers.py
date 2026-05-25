from __future__ import annotations

import logging

from population_synth.population.helpers import VALID_AGE_GROUPS, resolve_age_group  # noqa: F401
from population_synth.population.income_class import classify_brackets

from .constants import (
    CIVIL_STATUS_MAP,
    INCOME_BRACKET_EDGES_EUR,
    NUTS2_REGION_CODES,
    SEX_LABEL_MAP,
)

logger = logging.getLogger(__name__)


def _extract_sdmx_dimensions(raw: dict) -> tuple[list[dict], list[dict]]:
    """Return (series_dimensions, observation_dimensions) from ISTAT SDMX-JSON 2.0."""
    dims = raw["data"].get("structures", raw["data"].get("structure", [{}]))[0]["dimensions"]
    return dims["series"], dims.get("observation", [])


def _extract_sdmx_series(raw: dict) -> dict:
    """Return the series dict from ISTAT SDMX-JSON 2.0 dataSets[0]."""
    return raw["data"]["dataSets"][0]["series"]


def _sdmx_key_to_indices(key: str) -> list[int]:
    """Convert a colon-separated SDMX series key ('0:1:2:0') to a list of ints."""
    return [int(part) for part in key.split(":")]


def _build_sdmx_dim_lookup(dimensions: list[dict]) -> dict[str, list[tuple[str, str]]]:
    """Build a mapping from dimension ID to list of (code, label) for each value.

    Returns: {'DIM_ID': [('CODE0', 'LABEL0'), ('CODE1', 'LABEL1'), ...], ...}
    """
    return {
        dim["id"]: [(v["id"], v["name"]) for v in dim["values"]]
        for dim in dimensions
    }


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
    "Y15-24": "18-24",
    "Y15-19": "18-24",
    "Y20-24": "18-24",
    "Y25-34": "25-34",
    "Y35-44": "35-44",
    "Y45-54": "45-54",
    "Y55-64": "55-64",
    "Y65-74": "65-74",
    "Y75-85": "75-85",
    "Y_GE75": "75-85",
}

_SKIP_EDU_AGE_CODES = frozenset({
    "Y_GE15", "Y_GE65", "Y15-64", "Y15-74", "Y14-29",
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
    "3": "No Formal Education",
    "4": "No Formal Education",
    "5": "High School (Liceo/Professionale)",
    "6": "High School (Liceo/Professionale)",
}


def parse_education_by_age(raw: dict) -> dict[tuple[str, str], dict[str, float]]:
    """Parse ``52_1194`` SDMX response into ``{(age_group, sex): {edu_label: prob}}``.

    Filters: annual, Italy (IT), total citizenship.
    Skips None observations (cached prototype data has nulls — callers must
    clear cache to get real values).
    Raises ``ValueError`` if no non-null data is found.
    """
    series_dims, obs_dims = _extract_sdmx_dimensions(raw)
    series = _extract_sdmx_series(raw)
    dim_lookup = _build_sdmx_dim_lookup(series_dims + obs_dims)

    istat_sex_map = {"1": "Male", "2": "Female"}

    accumulator: dict[tuple[str, str], dict[str, float]] = {}

    for key, series_data in series.items():
        indices = _sdmx_key_to_indices(key)
        freq_i, ref_area_i, _data_type_i, sex_i, age_i, edu_i, citizenship_i = indices[:7]

        if freq_i != 0 or ref_area_i != 0 or citizenship_i != 0:
            continue

        sex_code = dim_lookup["SEX"][sex_i][0]
        sex_label = istat_sex_map.get(sex_code)
        if sex_label is None:
            continue

        age_code = dim_lookup["AGE"][age_i][0]
        if age_code in _SKIP_EDU_AGE_CODES:
            continue
        age_group = _ISTAT_EDU_AGE_MAP.get(age_code)
        if age_group is None:
            continue

        edu_code = dim_lookup["EDU_LEV_HIGHEST"][edu_i][0]
        edu_label = _ISCED_CODE_MAP.get(edu_code)
        if edu_label is None:
            continue

        obs_value = series_data.get("observations", {}).get("0", [None])[0]
        if obs_value is None:
            continue

        cell = accumulator.setdefault((age_group, sex_label), {})
        cell[edu_label] = cell.get(edu_label, 0.0) + float(obs_value)

    if not accumulator:
        raise ValueError(
            "No non-null education data parsed from ISTAT 52_1194 response. "
            "Clear config/assets/istat_cache/ and re-run to fetch live data."
        )

    result: dict[tuple[str, str], dict[str, float]] = {}
    for key, dist in accumulator.items():
        total = sum(dist.values()) or 1.0
        result[key] = {k: v / total for k, v in dist.items()}
    return result


# ---------------------------------------------------------------------------
# ISTAT SDMX employment parser
# ---------------------------------------------------------------------------

_ITALY_EMP_RATES: dict[str, dict[str, float]] = {
    "University Degree": {
        "Employed": 0.78,
        "Unemployed": 0.05,
        "Not in labour force": 0.17,
    },
    "High School (Liceo/Professionale)": {
        "Employed": 0.65,
        "Unemployed": 0.08,
        "Not in labour force": 0.27,
    },
    "No Formal Education": {
        "Employed": 0.48,
        "Unemployed": 0.09,
        "Not in labour force": 0.43,
    },
}

_EMP_EDU_CODE_MAP: dict[str, str] = {
    "11": "University Degree",
    "13": "No Formal Education",
    "7": "High School (Liceo/Professionale)",
}

_NATIONAL_AGE_CODES = frozenset({"Y15-74", "Y15-64"})

_EMP_ISTAT_SEX_MAP = {"1": "Male", "2": "Female"}


def parse_employment_by_sex_education(raw: dict) -> dict[str, dict[str, dict[str, float]]]:
    """Parse ``150_938`` SDMX response into ``{sex: {edu: {status: prob}}}``.

    150_938 covers EMPLOYED persons only; non-employed fractions come from
    hardcoded Italian aggregate labour market rates (logged as WARNING).

    If all 150_938 observations are null (cached prototype), the aggregate
    rates are used uniformly for both sexes.
    """
    series_dims, obs_dims = _extract_sdmx_dimensions(raw)
    series = _extract_sdmx_series(raw)
    dim_lookup = _build_sdmx_dim_lookup(series_dims + obs_dims)

    id_order = [d["id"] for d in series_dims]

    def _pos(dim_id: str) -> int:
        return id_order.index(dim_id)

    freq_pos = _pos("FREQ")
    ref_area_pos = _pos("REF_AREA")
    sex_pos = _pos("SEX")
    age_pos = _pos("AGE")
    edu_pos = _pos("EDU_LEV_HIGHEST")
    citizenship_pos = _pos("CITIZENSHIP")
    nace2002_pos = _pos("ECON_ACTIVITY_NACE_2002")
    nace2007_pos = _pos("ECON_ACTIVITY_NACE_2007")
    posiz_pos = _pos("POSIZ_PROF")
    prof_status_pos = _pos("PROF_STATUS")
    occ2001_pos = _pos("OCCUPATION_2001")
    occ2011_pos = _pos("OCCUPATION_2011")
    fpt_pos = _pos("FULL_PART_TIME")
    perm_temp_pos = _pos("PERM_TEMP_EMPLOYEES")

    n_time_obs = len(obs_dims[0]["values"]) if obs_dims else 1
    latest_time_key = str(n_time_obs - 1)

    employed_by_sex_edu: dict[str, dict[str, float]] = {}
    found_any = False

    for key, series_data in series.items():
        indices = _sdmx_key_to_indices(key)

        if indices[freq_pos] != 0:
            continue
        if indices[ref_area_pos] != 0:
            continue
        if indices[citizenship_pos] != 0:
            continue
        if indices[nace2002_pos] != 0:
            continue
        if indices[nace2007_pos] != 0:
            continue
        if indices[posiz_pos] != 0:
            continue
        if indices[prof_status_pos] != 0:
            continue
        if indices[occ2001_pos] != 0:
            continue
        if indices[occ2011_pos] != 0:
            continue
        if indices[fpt_pos] != 0:
            continue
        if indices[perm_temp_pos] != 0:
            continue

        age_code = dim_lookup["AGE"][indices[age_pos]][0]
        if age_code not in _NATIONAL_AGE_CODES:
            continue

        sex_code = dim_lookup["SEX"][indices[sex_pos]][0]
        sex_label = _EMP_ISTAT_SEX_MAP.get(sex_code)
        if sex_label is None:
            continue

        edu_code = dim_lookup["EDU_LEV_HIGHEST"][indices[edu_pos]][0]
        edu_label = _EMP_EDU_CODE_MAP.get(edu_code)
        if edu_label is None:
            continue

        obs_value = series_data.get("observations", {}).get(latest_time_key, [None])[0]
        if obs_value is None:
            continue

        found_any = True
        sex_dict = employed_by_sex_edu.setdefault(sex_label, {})
        sex_dict[edu_label] = sex_dict.get(edu_label, 0.0) + float(obs_value)

    if not found_any:
        logger.warning(
            "parse_employment_by_sex_education: no non-null data from ISTAT 150_938. "
            "Using Italian 2023 aggregate labour market rates as fallback. "
            "Clear config/assets/istat_cache/ to fetch live data."
        )
        return {
            sex: {edu: dict(rates) for edu, rates in _ITALY_EMP_RATES.items()}
            for sex in ("Male", "Female")
        }

    logger.warning(
        "parse_employment_by_sex_education: 150_938 covers EMPLOYED persons only. "
        "Non-employed fractions derived from Italian 2023 aggregate labour market rates."
    )

    result: dict[str, dict[str, dict[str, float]]] = {}
    for sex_label, edu_counts in employed_by_sex_edu.items():
        edu_total = sum(edu_counts.values()) or 1.0
        edu_weights = {edu: cnt / edu_total for edu, cnt in edu_counts.items()}

        sex_result: dict[str, dict[str, float]] = {}
        for edu_label, weight in edu_weights.items():
            base_rates = _ITALY_EMP_RATES.get(edu_label, _ITALY_EMP_RATES["High School (Liceo/Professionale)"])
            sex_result[edu_label] = {status: prob for status, prob in base_rates.items()}

        for edu_label in _ITALY_EMP_RATES:
            if edu_label not in sex_result:
                sex_result[edu_label] = dict(_ITALY_EMP_RATES[edu_label])

        result[sex_label] = sex_result

    for sex in ("Male", "Female"):
        if sex not in result:
            result[sex] = {edu: dict(rates) for edu, rates in _ITALY_EMP_RATES.items()}

    return result


# ---------------------------------------------------------------------------
# ISTAT SDMX socioeconomic parser
# ---------------------------------------------------------------------------

_ITALY_SOCIOECONOMIC_FALLBACK: dict[str, float] = {
    "Poverty": 0.20,
    "Working Class": 0.25,
    "Middle Class": 0.42,
    "Wealthy": 0.13,
}


def parse_socioeconomic(raw: dict) -> dict[tuple[str, str], dict[str, float]]:
    """Parse ``32_292`` SDMX response into ``{(age_group, sex): {class_label: prob}}``.

    32_292 reports median household income in absolute values — not bracket
    counts. If non-null income values are present, a lognormal-approximated
    bracket distribution (sigma=0.7, matching Gini~0.30) is constructed via
    ``classify_brackets``. If all observations are null, the EU-SILC 2022
    Italy fallback is returned for all groups (logged as WARNING).
    """
    import math

    series_dims, obs_dims = _extract_sdmx_dimensions(raw)
    series = _extract_sdmx_series(raw)
    dim_lookup = _build_sdmx_dim_lookup(series_dims + obs_dims)

    id_order = [d["id"] for d in series_dims]

    def _pos(dim_id: str) -> int:
        return id_order.index(dim_id)

    data_type_pos = _pos("DATA_TYPE")
    imputed_rents_pos = _pos("IMPUTED_RENTS")
    measure_pos = _pos("MEASURE")
    fam_source_pos = _pos("FAM_MAIN_INCOME_SOURCE")
    n_hhcomp_pos = _pos("NUMBER_HOUSEHOLD_COMP")
    hh_type_pos = _pos("HOUSEHOLD_TYPOLOGY")
    sex_pos = _pos("SEX_MAIN_PERCEPTOR")
    age_pos = _pos("AGE_MAIN_EARNIER")

    time_key_2023 = "0"

    istat_sex_map = {"1": "Male", "2": "Female"}

    income_by_age_sex: dict[tuple[str, str], list[float]] = {}
    found_any = False

    for key, series_data in series.items():
        indices = _sdmx_key_to_indices(key)

        if indices[data_type_pos] != 0:
            continue
        if indices[imputed_rents_pos] != 1:
            continue
        if indices[measure_pos] != 0:
            continue
        if indices[fam_source_pos] != 0:
            continue
        if indices[n_hhcomp_pos] != 0:
            continue
        if indices[hh_type_pos] != 0:
            continue

        sex_code = dim_lookup["SEX_MAIN_PERCEPTOR"][indices[sex_pos]][0]
        sex_label = istat_sex_map.get(sex_code)
        if sex_label is None:
            continue

        age_code = dim_lookup["AGE_MAIN_EARNIER"][indices[age_pos]][0]
        age_groups = _ISTAT_HOUSEHOLD_AGE_MAP.get(age_code)
        if age_groups is None:
            continue
        age_groups_to_use = [g for g in age_groups if g in VALID_AGE_GROUPS]
        if not age_groups_to_use:
            continue

        obs_value = series_data.get("observations", {}).get(time_key_2023, [None])[0]
        if obs_value is None:
            continue

        found_any = True
        income_val = float(obs_value)
        for ag in age_groups_to_use:
            bucket = income_by_age_sex.setdefault((ag, sex_label), [])
            bucket.append(income_val)

    if not found_any:
        logger.warning(
            "parse_socioeconomic: no income data from ISTAT 32_292. "
            "Using Italian 2023 EU-SILC approximation for all groups. "
            "Clear config/assets/istat_cache/ to fetch live data."
        )
        result: dict[tuple[str, str], dict[str, float]] = {}
        for ag in VALID_AGE_GROUPS:
            for sex in ("Male", "Female"):
                result[(ag, sex)] = dict(_ITALY_SOCIOECONOMIC_FALLBACK)
        return result

    _SIGMA = 0.7
    _EDGES = [(float(INCOME_BRACKET_EDGES_EUR[i]), float(INCOME_BRACKET_EDGES_EUR[i + 1]))
              for i in range(len(INCOME_BRACKET_EDGES_EUR) - 1)]
    _EDGES.append((float(INCOME_BRACKET_EDGES_EUR[-1]), float(INCOME_BRACKET_EDGES_EUR[-1]) * 5.0))

    def _lognormal_counts(median_income: float) -> list[float]:
        from scipy.stats import lognorm  # type: ignore[import]
        mu = math.log(max(median_income, 1.0))
        scale = math.exp(mu)
        out = []
        for lo, hi in _EDGES:
            lo_safe = max(lo, 0.01)
            hi_safe = max(hi, lo_safe + 0.01)
            frac = lognorm.cdf(hi_safe, s=_SIGMA, scale=scale) - lognorm.cdf(lo_safe, s=_SIGMA, scale=scale)
            out.append(max(frac, 0.0))
        return out

    result = {}
    for ag in VALID_AGE_GROUPS:
        for sex in ("Male", "Female"):
            key_tup = (ag, sex)
            incomes = income_by_age_sex.get(key_tup)
            if not incomes:
                result[key_tup] = dict(_ITALY_SOCIOECONOMIC_FALLBACK)
                continue
            median_income = sorted(incomes)[len(incomes) // 2]
            try:
                counts = _lognormal_counts(median_income)
                result[key_tup] = classify_brackets(_EDGES, counts, median_income)
            except Exception:
                result[key_tup] = dict(_ITALY_SOCIOECONOMIC_FALLBACK)

    return result


# ---------------------------------------------------------------------------
# ISTAT SDMX civil status parser
# ---------------------------------------------------------------------------

def parse_civil_status_by_age_sex(raw: dict) -> dict[tuple[str, str], dict[str, float]]:
    """Parse ``22_289_DF_DCIS_POPRES1_25`` response into ``{(age_group, sex): {status: prob}}``.

    Searches defensively for MARITAL/CIVIL/STATO dimension and age/sex
    dimensions by name — since the full DSD is not pre-inspected.
    Raises ``ValueError`` if the marital status dimension cannot be found or
    all observations are null.
    """
    series_dims, obs_dims = _extract_sdmx_dimensions(raw)
    series = _extract_sdmx_series(raw)
    dim_lookup = _build_sdmx_dim_lookup(series_dims + obs_dims)

    id_order = [d["id"] for d in series_dims]

    def _find_dim(*keywords: str) -> str | None:
        for dim_id in id_order:
            up = dim_id.upper()
            if any(kw in up for kw in keywords):
                return dim_id
        return None

    marital_dim = _find_dim("MARITAL", "CIVIL", "STATO", "CONIUG")
    ref_area_dim = _find_dim("REF_AREA", "GEO")
    sex_dim = _find_dim("SEX")
    age_dim = _find_dim("AGE")

    if marital_dim is None:
        raise ValueError(
            f"Cannot find marital/civil status dimension in ISTAT 22_289 response. "
            f"Available dimensions: {id_order}"
        )
    if ref_area_dim is None or sex_dim is None or age_dim is None:
        raise ValueError(
            f"Cannot find REF_AREA, SEX or AGE dimensions in ISTAT 22_289 response. "
            f"Available: {id_order}"
        )

    marital_pos = id_order.index(marital_dim)
    ref_area_pos = id_order.index(ref_area_dim)
    sex_pos = id_order.index(sex_dim)
    age_pos = id_order.index(age_dim)

    freq_pos: int | None = id_order.index("FREQ") if "FREQ" in id_order else None

    n_time_obs = len(obs_dims[0]["values"]) if obs_dims else 1
    latest_time_key = str(n_time_obs - 1)

    istat_sex_map = {"1": "Male", "2": "Female", "M": "Male", "F": "Female"}

    it_codes = {
        code
        for code, label in dim_lookup.get(ref_area_dim, [])
        if code in ("IT", "TOTAL", "0", "ITA")
    }
    if not it_codes:
        it_codes = {"IT"}

    accumulator: dict[tuple[str, str], dict[str, float]] = {}

    for key, series_data in series.items():
        indices = _sdmx_key_to_indices(key)

        if freq_pos is not None and indices[freq_pos] != 0:
            continue

        ref_area_code = dim_lookup[ref_area_dim][indices[ref_area_pos]][0]
        if ref_area_code not in it_codes:
            continue

        sex_code = dim_lookup[sex_dim][indices[sex_pos]][0]
        sex_label = istat_sex_map.get(sex_code)
        if sex_label is None:
            continue

        age_code = dim_lookup[age_dim][indices[age_pos]][0]
        age_group = _ISTAT_EDU_AGE_MAP.get(age_code) or _ISTAT_EMP_AGE_MAP.get(age_code)
        if age_group is None:
            for ag_map in (_ISTAT_HOUSEHOLD_AGE_MAP,):
                mapped = ag_map.get(age_code, [])
                if mapped and mapped[0] in VALID_AGE_GROUPS:
                    age_group = mapped[0]
                    break
        if age_group is None or age_group not in VALID_AGE_GROUPS:
            continue

        marital_code = dim_lookup[marital_dim][indices[marital_pos]][0]
        status_label = CIVIL_STATUS_MAP.get(marital_code)
        if status_label is None:
            continue

        obs_value = series_data.get("observations", {}).get(latest_time_key, [None])[0]
        if obs_value is None:
            continue

        cell = accumulator.setdefault((age_group, sex_label), {})
        cell[status_label] = cell.get(status_label, 0.0) + float(obs_value)

    if not accumulator:
        raise ValueError(
            "No non-null civil status data parsed from ISTAT 22_289 response. "
            "This endpoint is known to be slow — clear the cache and retry, "
            "or use a tighter key filter."
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


def parse_industry_sector(raw: dict) -> dict[str, float]:
    """Parse OCCUPATION_2011 from ``150_938`` into ``{sector_label: probability}``.

    Filters: annual, REF_AREA=IT, SEX=total, national age aggregate,
    all other dimensions at total (idx 0). Skips OCCUPATION_2011 code '99'
    (total). Raises ``ValueError`` if all observations are null.
    """
    series_dims, obs_dims = _extract_sdmx_dimensions(raw)
    series = _extract_sdmx_series(raw)
    dim_lookup = _build_sdmx_dim_lookup(series_dims + obs_dims)

    id_order = [d["id"] for d in series_dims]

    def _pos(dim_id: str) -> int:
        return id_order.index(dim_id)

    freq_pos = _pos("FREQ")
    ref_area_pos = _pos("REF_AREA")
    sex_pos = _pos("SEX")
    age_pos = _pos("AGE")
    edu_pos = _pos("EDU_LEV_HIGHEST")
    citizenship_pos = _pos("CITIZENSHIP")
    nace2002_pos = _pos("ECON_ACTIVITY_NACE_2002")
    nace2007_pos = _pos("ECON_ACTIVITY_NACE_2007")
    posiz_pos = _pos("POSIZ_PROF")
    prof_status_pos = _pos("PROF_STATUS")
    occ2001_pos = _pos("OCCUPATION_2001")
    occ2011_pos = _pos("OCCUPATION_2011")
    fpt_pos = _pos("FULL_PART_TIME")
    perm_temp_pos = _pos("PERM_TEMP_EMPLOYEES")

    n_time_obs = len(obs_dims[0]["values"]) if obs_dims else 1
    latest_time_key = str(n_time_obs - 1)

    accumulator: dict[str, float] = {}
    found_any = False

    for key, series_data in series.items():
        indices = _sdmx_key_to_indices(key)

        if indices[freq_pos] != 0:
            continue
        if indices[ref_area_pos] != 0:
            continue
        if indices[citizenship_pos] != 0:
            continue
        if indices[nace2002_pos] != 0:
            continue
        if indices[nace2007_pos] != 0:
            continue
        if indices[posiz_pos] != 0:
            continue
        if indices[prof_status_pos] != 0:
            continue
        if indices[occ2001_pos] != 0:
            continue
        if indices[fpt_pos] != 0:
            continue
        if indices[perm_temp_pos] != 0:
            continue

        sex_code = dim_lookup["SEX"][indices[sex_pos]][0]
        if sex_code != "9":
            continue

        edu_code = dim_lookup["EDU_LEV_HIGHEST"][indices[edu_pos]][0]
        if edu_code != "99":
            continue

        age_code = dim_lookup["AGE"][indices[age_pos]][0]
        if age_code not in _NATIONAL_AGE_CODES:
            continue

        occ2011_code = dim_lookup["OCCUPATION_2011"][indices[occ2011_pos]][0]
        if occ2011_code == "99":
            continue
        schema_label = _OCCUPATION_2011_SCHEMA_MAP.get(occ2011_code)
        if schema_label is None:
            continue

        obs_value = series_data.get("observations", {}).get(latest_time_key, [None])[0]
        if obs_value is None:
            continue

        found_any = True
        accumulator[schema_label] = accumulator.get(schema_label, 0.0) + float(obs_value)

    if not found_any:
        raise ValueError(
            "No non-null industry sector data parsed from ISTAT 150_938 OCCUPATION_2011. "
            "Clear config/assets/istat_cache/ and re-run to fetch live data."
        )

    total = sum(accumulator.values()) or 1.0
    return {k: v / total for k, v in accumulator.items()}


# ---------------------------------------------------------------------------
# ISTAT SDMX employment type parser
# ---------------------------------------------------------------------------

def parse_employment_type_by_age(raw: dict) -> dict[tuple[str, str], dict[str, float]]:
    """Parse FULL_PART_TIME × PERM_TEMP_EMPLOYEES from ``150_938``.

    Returns ``{(age_group, sex): {composite_key: probability}}`` where
    composite_key is ``"{contract}|{hours}"``, e.g. ``"Permanent|Full-time"``.

    Filters: POSIZ_PROF=employees only (code '1'). Both sexes separately.
    Raises ``ValueError`` if all observations are null.
    """
    series_dims, obs_dims = _extract_sdmx_dimensions(raw)
    series = _extract_sdmx_series(raw)
    dim_lookup = _build_sdmx_dim_lookup(series_dims + obs_dims)

    id_order = [d["id"] for d in series_dims]

    def _pos(dim_id: str) -> int:
        return id_order.index(dim_id)

    freq_pos = _pos("FREQ")
    ref_area_pos = _pos("REF_AREA")
    sex_pos = _pos("SEX")
    age_pos = _pos("AGE")
    edu_pos = _pos("EDU_LEV_HIGHEST")
    citizenship_pos = _pos("CITIZENSHIP")
    nace2002_pos = _pos("ECON_ACTIVITY_NACE_2002")
    nace2007_pos = _pos("ECON_ACTIVITY_NACE_2007")
    posiz_pos = _pos("POSIZ_PROF")
    prof_status_pos = _pos("PROF_STATUS")
    occ2001_pos = _pos("OCCUPATION_2001")
    occ2011_pos = _pos("OCCUPATION_2011")
    fpt_pos = _pos("FULL_PART_TIME")
    perm_temp_pos = _pos("PERM_TEMP_EMPLOYEES")

    n_time_obs = len(obs_dims[0]["values"]) if obs_dims else 1
    latest_time_key = str(n_time_obs - 1)

    istat_sex_map = {"1": "Male", "2": "Female"}
    fpt_label_map = {"1": "Full-time", "2": "Part-time"}
    perm_temp_label_map = {"1": "Temporary", "2": "Permanent"}

    posiz_employees_idx = next(
        (i for i, (code, _) in enumerate(dim_lookup["POSIZ_PROF"]) if code == "1"),
        None,
    )
    edu_total_idx = next(
        (i for i, (code, _) in enumerate(dim_lookup["EDU_LEV_HIGHEST"]) if code == "99"),
        None,
    )

    if posiz_employees_idx is None:
        raise ValueError("POSIZ_PROF code '1' (employees) not found in 150_938 dimension lookup")

    accumulator: dict[tuple[str, str], dict[str, float]] = {}
    found_any = False

    for key, series_data in series.items():
        indices = _sdmx_key_to_indices(key)

        if indices[freq_pos] != 0:
            continue
        if indices[ref_area_pos] != 0:
            continue
        if indices[citizenship_pos] != 0:
            continue
        if indices[nace2002_pos] != 0:
            continue
        if indices[nace2007_pos] != 0:
            continue
        if indices[posiz_pos] != posiz_employees_idx:
            continue
        if indices[prof_status_pos] != 0:
            continue
        if indices[occ2001_pos] != 0:
            continue
        if indices[occ2011_pos] != 0:
            continue
        if edu_total_idx is not None and indices[edu_pos] != edu_total_idx:
            continue

        fpt_code = dim_lookup["FULL_PART_TIME"][indices[fpt_pos]][0]
        if fpt_code == "9":
            continue
        fpt_label = fpt_label_map.get(fpt_code)
        if fpt_label is None:
            continue

        perm_temp_code = dim_lookup["PERM_TEMP_EMPLOYEES"][indices[perm_temp_pos]][0]
        if perm_temp_code == "9":
            continue
        perm_temp_label = perm_temp_label_map.get(perm_temp_code)
        if perm_temp_label is None:
            continue

        sex_code = dim_lookup["SEX"][indices[sex_pos]][0]
        sex_label = istat_sex_map.get(sex_code)
        if sex_label is None:
            continue

        age_code = dim_lookup["AGE"][indices[age_pos]][0]
        if age_code in _SKIP_EMP_AGE_CODES or age_code in _NATIONAL_AGE_CODES:
            age_group = "ALL"
        else:
            age_group = _ISTAT_EMP_AGE_MAP.get(age_code)
            if age_group is None:
                continue

        composite = f"{perm_temp_label}|{fpt_label}"
        obs_value = series_data.get("observations", {}).get(latest_time_key, [None])[0]
        if obs_value is None:
            continue

        found_any = True
        cell_key = (age_group, sex_label)
        cell = accumulator.setdefault(cell_key, {})
        cell[composite] = cell.get(composite, 0.0) + float(obs_value)

    if not found_any:
        raise ValueError(
            "No non-null employment type data parsed from ISTAT 150_938. "
            "Clear config/assets/istat_cache/ and re-run to fetch live data."
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
# ISTAT SDMX household size parser
# ---------------------------------------------------------------------------

_ITALY_HOUSEHOLD_SIZE_FALLBACK: dict[str, float] = {
    "1 person": 0.33,
    "2 persons": 0.27,
    "3-4 persons": 0.31,
    "5+ persons": 0.09,
}


def parse_household_size(raw: dict) -> dict[str, float]:
    """Return household size distribution from ``32_292``.

    32_292 reports median household income by size — not household counts.
    A direct normalization of income values is not a valid probability
    distribution. Returns the 2023 ISTAT census approximation and logs a WARNING.
    """
    logger.warning(
        "parse_household_size: ISTAT 32_292 provides household income values, "
        "not household count distributions. Using 2023 ISTAT census approximation."
    )
    return dict(_ITALY_HOUSEHOLD_SIZE_FALLBACK)


# ---------------------------------------------------------------------------
# ISTAT SDMX income source parser
# ---------------------------------------------------------------------------

_INCOME_SOURCE_FALLBACK: dict[str, dict[str, float]] = {
    "Employed": {
        "Employment income": 0.87,
        "Capital income": 0.06,
        "Social transfers": 0.04,
        "Business/self-employment": 0.03,
    },
    "Unemployed": {
        "Social transfers": 0.72,
        "Employment income": 0.18,
        "Capital income": 0.06,
        "Business/self-employment": 0.04,
    },
    "Retired": {
        "Pension": 0.80,
        "Capital income": 0.10,
        "Social transfers": 0.07,
        "Employment income": 0.02,
        "Business/self-employment": 0.01,
    },
    "Not in labour force": {
        "Social transfers": 0.60,
        "Employment income": 0.25,
        "Capital income": 0.10,
        "Business/self-employment": 0.05,
    },
}

_FAM_SOURCE_LABEL_MAP: dict[str, str] = {
    "1": "Employment income",
    "2": "Business/self-employment",
    "3": "Social transfers",
    "4": "Capital income",
}

_LABPROF_STATUS_MAP: dict[str, str] = {
    "1A": "Employed",
    "1B": "Employed",
    "2A": "Retired",
    "2B": "Unemployed",
}


def parse_birth_location(raw: dict) -> dict[str, float]:
    """Parse ``migr_pop1ctz`` response into ``{location_label: probability}``.

    Derives a 3-category birth-location proxy from citizenship dimension:
    - 'IT' → "Italy"
    - EU27 member codes → "Europe (Other)"
    - all other non-aggregate country codes → "Outside Europe"
    Aggregate codes ('TOTAL', 'EU27_2020', etc.) are skipped.
    Raises ``ValueError`` if result is empty.
    """
    _EU27_CODES = frozenset({
        "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES",
        "FI", "FR", "HR", "HU", "IE", "LT", "LU", "LV", "MT", "NL",
        "PL", "PT", "RO", "SE", "SI", "SK",
    })
    _AGGREGATE_CODES = frozenset({
        "TOTAL", "EU27_2020", "EU28", "NEU28", "NEU27_2020_EFTA", "EEA31", "OTH", "UNK",
    })

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
        if ctz_code in _AGGREGATE_CODES:
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
        if ctz_code in _BIRTH_COUNTRY_AGGREGATE_CODES or ctz_code == "IT":
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


def parse_income_source(raw: dict) -> dict[tuple[str, str], dict[str, float]]:
    """Parse ``32_292`` FAM_MAIN_INCOME_SOURCE into ``{(emp_status, age_group): {source: prob}}``.

    32_292 reports income VALUES per source/status — not household counts per source.
    If all observations are null (current cached prototype), uses a Norway-pattern
    hardcoded fallback and logs a WARNING. Otherwise attempts to derive weights from
    income values, but logs a WARNING about the proxy nature of this approach.
    """
    series_dims, obs_dims = _extract_sdmx_dimensions(raw)
    series = _extract_sdmx_series(raw)
    dim_lookup = _build_sdmx_dim_lookup(series_dims + obs_dims)

    id_order = [d["id"] for d in series_dims]

    def _pos(dim_id: str) -> int:
        return id_order.index(dim_id)

    data_type_pos = _pos("DATA_TYPE")
    imputed_rents_pos = _pos("IMPUTED_RENTS")
    measure_pos = _pos("MEASURE")
    fam_source_pos = _pos("FAM_MAIN_INCOME_SOURCE")
    n_hhcomp_pos = _pos("NUMBER_HOUSEHOLD_COMP")
    hh_type_pos = _pos("HOUSEHOLD_TYPOLOGY")
    sex_pos = _pos("SEX_MAIN_PERCEPTOR")
    age_pos = _pos("AGE_MAIN_EARNIER")

    labprof_dim = "LABPROF_STATUS_C_MAIN_EARNER"
    labprof_pos = _pos(labprof_dim) if labprof_dim in id_order else None

    time_key_2023 = "0"

    found_any = False
    accumulator: dict[tuple[str, str], dict[str, dict[str, float]]] = {}

    for key, series_data in series.items():
        indices = _sdmx_key_to_indices(key)

        if indices[data_type_pos] != 0:
            continue
        if indices[imputed_rents_pos] != 1:
            continue
        if indices[measure_pos] != 0:
            continue
        if indices[n_hhcomp_pos] != 0:
            continue
        if indices[hh_type_pos] != 0:
            continue

        sex_code = dim_lookup["SEX_MAIN_PERCEPTOR"][indices[sex_pos]][0]
        if sex_code != "9":
            continue

        fam_code = dim_lookup["FAM_MAIN_INCOME_SOURCE"][indices[fam_source_pos]][0]
        if fam_code == "9":
            continue
        source_label = _FAM_SOURCE_LABEL_MAP.get(fam_code)
        if source_label is None:
            continue

        age_code = dim_lookup["AGE_MAIN_EARNIER"][indices[age_pos]][0]
        age_groups = _ISTAT_HOUSEHOLD_AGE_MAP.get(age_code)
        if age_groups is None:
            continue

        labprof_code = "TOTAL"
        if labprof_pos is not None:
            labprof_code = dim_lookup[labprof_dim][indices[labprof_pos]][0]

        emp_status = _LABPROF_STATUS_MAP.get(labprof_code)
        if emp_status is None:
            continue

        obs_value = series_data.get("observations", {}).get(time_key_2023, [None])[0]
        if obs_value is None:
            continue

        found_any = True
        for ag in age_groups:
            if ag not in VALID_AGE_GROUPS:
                continue
            cell = accumulator.setdefault((emp_status, ag), {})
            cell[source_label] = cell.get(source_label, 0.0) + float(obs_value)

    if not found_any:
        logger.warning(
            "parse_income_source: no non-null data from ISTAT 32_292. "
            "Using Italy/Norway-pattern labour market approximation as fallback. "
            "Clear config/assets/istat_cache/ to fetch live data."
        )
        result: dict[tuple[str, str], dict[str, float]] = {}
        for emp_status, source_dist in _INCOME_SOURCE_FALLBACK.items():
            for ag in VALID_AGE_GROUPS:
                result[(emp_status, ag)] = dict(source_dist)
        return result

    logger.warning(
        "parse_income_source: 32_292 provides income values per source, "
        "not household counts. Income-value weights are a proxy for source distribution."
    )

    result = {}
    for (emp_status, ag), source_counts in accumulator.items():
        total = sum(source_counts.values()) or 1.0
        result[(emp_status, ag)] = {k: v / total for k, v in source_counts.items()}

    for emp_status, fallback_dist in _INCOME_SOURCE_FALLBACK.items():
        for ag in VALID_AGE_GROUPS:
            if (emp_status, ag) not in result:
                result[(emp_status, ag)] = dict(fallback_dist)

    return result
