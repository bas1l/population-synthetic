"""
Norwegian SSB json-stat2 parsers.

Each function takes a raw API response dict (json-stat2 format) and returns a
normalised distribution matching the ``PopulationDistributions`` field schema.

Label normalisation translates raw SSB codes and Norwegian strings to the
schema-level labels defined in ``config/mapping/ssb/``.
"""

from __future__ import annotations

import logging

from population_synthetic.generators.real.helpers import VALID_AGE_GROUPS, resolve_age_group
from population_synthetic.generators.real.income_class import classify_brackets, median_from_brackets

from .constants import (
    AGE_SEX_KJONN_CODES,
    ANSETTELSESFORHOLD_CODES,
    ARBEIDSTID_CODES,
    BRUTTOINN_BRACKETS,
    CIVIL_STATUS_CODES,
    EDUCATION_NIVAA_CODES,
    EIERSTATUS_CODES,
    EMPLOYMENT_NIVAA_CODES,
    EMPLOYMENT_STATUS_CODES,
    FAMILIETYPE_CODES,
    FYLKE_CODES,
    HUSHSTR_CODES,
    NACE_SECTION_TO_SCHEMA,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal normaliser helpers
# ---------------------------------------------------------------------------

_EDUCATION_LABEL_MAP: dict[str, str] = {
    "grunnskolenivå": "No Formal Education",
    "grunnskoleniå": "No Formal Education",
    "uoppgitt eller ingen fullført utdanning": "No Formal Education",
    "ingen fullført utdanning": "No Formal Education",
    "videregående skolenivå": "High School (Videregående)",
    "fagskolenivå": "Vocational (Fagskole)",
    "universitets- og høgskolenivå, kort": "University Degree",
    "universitets- og høgskolenivå, lang": "University Degree",
    "universitets- og høgskolenivå": "University Degree",
}

_EMPLOYMENT_LABEL_MAP: dict[str, str] = {
    "sysselsatte": "Employed",
    "arbeidsledige": "Unemployed",
    "personer utenfor arbeidsstyrken": "Retired",
    "employed": "Employed",
    "unemployed": "Unemployed",
    "not in the labour force": "Retired",
    "outside the labour force": "Retired",
}

_CIVIL_STATUS_LABEL_MAP: dict[str, str] = {
    "ugift": "Single/Never Married",
    "gift": "Married",
    "enke/enkemann": "Widowed",
    "skilt": "Divorced",
    "separert": "Divorced",
    "annen sivilstand": "Single/Never Married",
}

_BIRTH_LOCATION_LABEL_MAP: dict[str, str] = {
    "norge": "Norway",
    "born in norway": "Norway",
    "norden utenom norge": "Nordic Country",
    "nordic countries except norway": "Nordic Country",
    "eu/efta/storbritannia": "Europe (Other)",
    "europa utenom eu/efta og storbritannia": "Europe (Other)",
    "europa utenom eu/efta/storbritannia": "Europe (Other)",
    "den øvrige befolkningen": "Norway",
    "afrika": "Outside Europe",
    "africa": "Outside Europe",
    "asia": "Outside Europe",
    "latin-amerika og karibia": "Outside Europe",
    "nord-amerika utenom usa og canada": "Outside Europe",
    "oseania utenom australia og nz, polare områder": "Outside Europe",
}

_REGION_LABEL_MAP: dict[str, str] = {
    "østfold": "Østfold",
    "akershus": "Akershus",
    "oslo": "Oslo",
    "oslo - oslove": "Oslo",
    "innlandet": "Innlandet",
    "buskerud": "Buskerud",
    "vestfold": "Vestfold",
    "telemark": "Telemark",
    "agder": "Agder",
    "rogaland": "Rogaland",
    "vestland": "Vestland",
    "møre og romsdal": "Møre og Romsdal",
    "trøndelag - trööndelage": "Trøndelag",
    "trøndelag": "Trøndelag",
    "nordland - nordlánnda": "Nordland",
    "nordland": "Nordland",
    "troms - romsa - tromssa": "Troms",
    "troms": "Troms",
    "finnmark - finnmárku - finmarkku": "Finnmark",
    "finnmark": "Finnmark",
}

_HOUSING_LABEL_MAP: dict[str, str] = {
    "selveier": "Owner-occupied (villa/house)",
    "andels- / aksjeeier": "Cooperative apartment (andel/aksje)",
    "andels-/aksjeeier": "Cooperative apartment (andel/aksje)",
    "leier": "Rental apartment",
}

_HOUSEHOLD_SIZE_LABEL_MAP: dict[str, str] = {
    "1 person": "1 person",
    "2 personer": "2 persons",
    "3 personer": "3-4 persons",
    "4 personer": "3-4 persons",
    "5 personer +": "5+ persons",
}

_FAMILY_TYPE_LABEL_MAP: dict[str, str] = {
    "enpersonfamilie": "Living Alone",
    "par med små barn (yngste barn 0-5 år)": "Nuclear Family",
    "par med store barn (yngste barn 6-17 år)": "Nuclear Family",
    "mor/far med små barn (yngste barn 0-5 år)": "Single Parent",
    "mor/far med store barn (yngste barn 6-17 år)": "Single Parent",
    "par uten barn": "Couple without Children",
    "par med voksne barn (yngste barn 18 år og over)": "Couple without Children",
    "mor/far med voksne barn (yngste barn 18 år og over)": "Single Parent",
    "andre familier": "Living Alone",
}

_INDUSTRY_LABEL_MAP: dict[str, str] = {
    "jordbruk, skogbruk og fiske": "Agriculture & Forestry",
    "bergverksdrift og utvinning": "Manufacturing & Industry",
    "industri": "Manufacturing & Industry",
    "elektrisitet, vann og renovasjon": "Manufacturing & Industry",
    "bygge- og anleggsvirksomhet": "Manufacturing & Industry",
    "varehandel, reparasjon av motorvogner": "Retail & Service",
    "transport og lagring": "Retail & Service",
    "overnattings- og serveringsvirksomhet": "Retail & Service",
    "informasjon og kommunikasjon": "IT & Technology",
    "finansiering og forsikring": "IT & Technology",
    "teknisk tjenesteyting, eiendomsdrift": "IT & Technology",
    "forretningsmessig tjenesteyting": "Retail & Service",
    "off.adm., forsvar, sosialforsikring": "Public Administration",
    "offentlig administrasjon, forsvar, sosialforsikring": "Public Administration",
    "undervisning": "Education",
    "helse- og sosialtjenester": "Healthcare & Social",
    "personlig tjenesteyting": "Other",
    "kulturell virksomhet, underholdning og fritidsaktiviteter": "Other",
    "annen tjenesteyting": "Other",
    "aktiviteter i private husholdninger": "Other",
    "ukjent": "Other",
}


def _normalise_sex(raw: str) -> str:
    """Translate raw SSB sex code or label to schema value."""
    # numeric code
    result = AGE_SEX_KJONN_CODES.get(raw.strip())
    if result:
        return result
    r = raw.strip().lower()
    if r in ("menn", "men", "male", "m", "1"):
        return "Male"
    if r in ("kvinner", "women", "female", "f", "2"):
        return "Female"
    return raw


def _normalise_education(raw: str) -> str:
    """Translate raw SSB education code or label to schema value."""
    result = EDUCATION_NIVAA_CODES.get(raw.strip())
    if result and result != "total":
        return result
    result = EMPLOYMENT_NIVAA_CODES.get(raw.strip())
    if result:
        return result
    mapped = _EDUCATION_LABEL_MAP.get(raw.strip().lower())
    if mapped:
        return mapped
    return raw


def _normalise_employment(raw: str) -> str:
    """Translate raw SSB employment status code or label to schema value."""
    result = EMPLOYMENT_STATUS_CODES.get(raw.strip())
    if result:
        return result
    mapped = _EMPLOYMENT_LABEL_MAP.get(raw.strip().lower())
    if mapped:
        return mapped
    return raw


def _normalise_civil_status(raw: str) -> str:
    """Translate raw SSB civil status code or Norwegian label to schema value."""
    result = CIVIL_STATUS_CODES.get(raw.strip())
    if result:
        return result
    mapped = _CIVIL_STATUS_LABEL_MAP.get(raw.strip().lower())
    if mapped:
        return mapped
    return raw


def _normalise_region(raw: str) -> str:
    """Translate raw SSB fylke code or Norwegian label to schema value."""
    # Numeric 2-char code
    result = FYLKE_CODES.get(raw.strip().zfill(2))
    if result:
        return result
    mapped = _REGION_LABEL_MAP.get(raw.strip().lower())
    if mapped:
        return mapped
    return raw


def _normalise_birth_location(raw: str) -> str:
    """Translate raw SSB birth-location label to schema value."""
    mapped = _BIRTH_LOCATION_LABEL_MAP.get(raw.strip().lower())
    if mapped:
        return mapped
    return raw


def _normalise_industry(raw: str) -> str:
    """Translate raw NACE label or section code to schema value."""
    mapped = _INDUSTRY_LABEL_MAP.get(raw.strip().lower())
    if mapped:
        return mapped
    # Try NACE section code lookup
    mapped = NACE_SECTION_TO_SCHEMA.get(raw.strip())
    if mapped:
        return mapped
    return "Other"


def _normalise_housing(raw: str) -> str:
    """Translate raw SSB EierStatus label to schema value."""
    result = EIERSTATUS_CODES.get(raw.strip())
    if result:
        return result
    mapped = _HOUSING_LABEL_MAP.get(raw.strip().lower())
    if mapped:
        return mapped
    return "Other"


def _normalise_household_size(raw: str) -> str:
    """Translate raw SSB HushStr label to schema value."""
    result = HUSHSTR_CODES.get(raw.strip())
    if result:
        return result
    mapped = _HOUSEHOLD_SIZE_LABEL_MAP.get(raw.strip().lower())
    if mapped:
        return mapped
    return raw


def _normalise_family_type(raw: str) -> str:
    """Translate raw SSB FamilieType code or label to schema value."""
    result = FAMILIETYPE_CODES.get(raw.strip())
    if result:
        return result
    mapped = _FAMILY_TYPE_LABEL_MAP.get(raw.strip().lower())
    if mapped:
        return mapped
    return raw



# ---------------------------------------------------------------------------
# Public parse functions
# ---------------------------------------------------------------------------

def parse_age_sex(raw: dict) -> dict[tuple[int, str], float]:
    """Parse table 07459 (age/sex population) into ``{(age, sex): probability}``."""
    dims = raw.get("dimension", {})
    values = raw.get("value", [])

    age_key = next((k for k in dims if "alder" in k.lower() or "age" in k.lower()), None)
    sex_key = next((k for k in dims if "kjonn" in k.lower() or "kon" in k.lower() or "sex" in k.lower()), None)

    if not age_key or not sex_key:
        raise ValueError(
            f"Could not identify age/sex dimensions in response; dims={list(dims.keys())}"
        )

    age_labels_raw = list(dims[age_key]["category"]["label"].items())  # (code, label)
    sex_labels_raw = list(dims[sex_key]["category"]["label"].items())  # (code, label)

    id_list = raw.get("id", list(dims.keys()))
    age_pos = id_list.index(age_key) if age_key in id_list else 0
    sex_pos = id_list.index(sex_key) if sex_key in id_list else 1

    n_age = len(age_labels_raw)
    n_sex = len(sex_labels_raw)

    # Determine stride layout from dimension positions
    if age_pos < sex_pos:
        # age outer, sex inner: index = age_i * n_sex + sex_i
        def _idx(ai: int, si: int) -> int:
            return ai * n_sex + si
    else:
        # sex outer, age inner: index = sex_i * n_age + age_i
        def _idx(ai: int, si: int) -> int:
            return si * n_age + ai

    counts: dict[tuple[int, str], float] = {}
    for ai, (age_code, _age_label) in enumerate(age_labels_raw):
        # 07459 uses 3-digit zero-padded age codes (e.g. "018", "019", ...)
        try:
            age = int(age_code)
        except ValueError:
            # Try parsing from label
            try:
                age = int(str(_age_label).split()[0])
            except (ValueError, IndexError):
                continue
        if not (18 <= age <= 85):
            continue
        for si, (_sex_code, sex_label) in enumerate(sex_labels_raw):
            normalised_sex = _normalise_sex(sex_label)
            idx = _idx(ai, si)
            v = float(values[idx] or 0) if idx < len(values) else 0.0
            key: tuple[int, str] = (age, normalised_sex)
            counts[key] = counts.get(key, 0.0) + v

    if not counts:
        raise ValueError("No age/sex data parsed from SSB response")
    total = sum(counts.values()) or 1.0
    return {k: v / total for k, v in counts.items()}


def parse_education_by_age(
    raw: dict,
) -> dict[tuple[str, str], dict[str, float]]:
    """Parse table 08921 (education by age/sex) into
    ``{(age_group, sex): {education_label: probability}}``.

    Age-to-group mapping uses the table-08921-specific band codes from
    ``category_mappings.json``; any band not in that mapping is dropped.
    """
    dims = raw.get("dimension", {})
    values = raw.get("value", [])

    # SSB 08921 age-band code → our standard group label
    _AGE_BAND_MAP_08921 = {
        "16-19": "18-24",
        "20-24": "18-24",
        "25-29": "25-34",
        "30-39": "25-34",
        "40-49": "35-44",
        "50-59": "45-54",
        "60-66": "55-64",
        "067+": "65-74",
    }

    age_key = next((k for k in dims if "alder" in k.lower() or "age" in k.lower()), None)
    edu_key = next((k for k in dims if "utdan" in k.lower() or "utbild" in k.lower() or "educ" in k.lower()), None)
    sex_key = next((k for k in dims if "kjonn" in k.lower() or "kon" in k.lower() or "sex" in k.lower()), None)

    if not age_key or not edu_key:
        raise ValueError(
            f"Could not identify age/education dimensions in SSB 08921 response; dims={list(dims.keys())}"
        )
    if not sex_key:
        raise ValueError(
            f"Could not identify sex (Kjonn) dimension in education response; dims={list(dims.keys())}"
        )

    age_codes_raw = list(dims[age_key]["category"]["label"].items())
    edu_codes_raw = list(dims[edu_key]["category"]["label"].items())
    sex_codes_raw = list(dims[sex_key]["category"]["label"].items())

    id_list = raw.get("id", list(dims.keys()))
    edu_pos = id_list.index(edu_key) if edu_key in id_list else 0
    age_pos = id_list.index(age_key) if age_key in id_list else 1
    sex_pos = id_list.index(sex_key) if sex_key in id_list else 2

    n_edu = len(edu_codes_raw)
    n_age = len(age_codes_raw)
    n_sex = len(sex_codes_raw)

    dim_order = sorted([(edu_pos, "edu"), (age_pos, "age"), (sex_pos, "sex")])
    sizes = {"edu": n_edu, "age": n_age, "sex": n_sex}
    strides: dict[str, int] = {}
    stride = 1
    for _, name in reversed(dim_order):
        strides[name] = stride
        stride *= sizes[name]

    result: dict[tuple[str, str], dict[str, float]] = {}
    for edu_i, (edu_code, edu_label) in enumerate(edu_codes_raw):
        norm_edu = _normalise_education(edu_code) if edu_code else _normalise_education(edu_label)
        if norm_edu == "total":
            continue
        for age_i, (age_code, _age_label) in enumerate(age_codes_raw):
            age_group = _AGE_BAND_MAP_08921.get(age_code) or _AGE_BAND_MAP_08921.get(str(_age_label))
            if age_group not in VALID_AGE_GROUPS:
                continue
            for sex_i, (_sex_code, sex_label) in enumerate(sex_codes_raw):
                norm_sex = _normalise_sex(sex_label)
                flat_idx = edu_i * strides["edu"] + age_i * strides["age"] + sex_i * strides["sex"]
                v = float(values[flat_idx] or 0) if flat_idx < len(values) else 0.0
                key: tuple[str, str] = (age_group, norm_sex)
                if key not in result:
                    result[key] = {}
                result[key][norm_edu] = result[key].get(norm_edu, 0.0) + v

    if not result:
        raise ValueError("No education data parsed from SSB response")
    for key, dist in result.items():
        total = sum(dist.values()) or 1.0
        result[key] = {k: v / total for k, v in dist.items()}
    return result


def parse_employment_by_sex_education(
    raw: dict,
) -> dict[str, dict[str, dict[str, float]]]:
    """Parse table 13785 (employment status x education x sex) into
    ``{sex: {education_label: {status_label: probability}}}``.
    """
    dims = raw.get("dimension", {})
    values = raw.get("value", [])

    emp_key = next(
        (k for k in dims if "arbstyrk" in k.lower() or "arbeidsstyrk" in k.lower()
         or "labour" in k.lower() or "arb" in k.lower()),
        None,
    )
    edu_key = next(
        (k for k in dims if "utdan" in k.lower() or "utdniv" in k.lower()
         or "utbild" in k.lower() or "educ" in k.lower()),
        None,
    )
    sex_key = next(
        (k for k in dims if "kjonn" in k.lower() or "kon" in k.lower() or "sex" in k.lower()),
        None,
    )

    if not emp_key or not edu_key or not sex_key:
        raise ValueError(
            f"Could not identify employment/education/sex dimensions in SSB 13785 response; "
            f"dims={list(dims.keys())}"
        )

    emp_codes_raw = list(dims[emp_key]["category"]["label"].items())
    edu_codes_raw = list(dims[edu_key]["category"]["label"].items())
    sex_codes_raw = list(dims[sex_key]["category"]["label"].items())

    id_list = raw.get("id", list(dims.keys()))
    emp_pos = id_list.index(emp_key) if emp_key in id_list else 0
    edu_pos = id_list.index(edu_key) if edu_key in id_list else 1
    sex_pos = id_list.index(sex_key) if sex_key in id_list else 2

    n_emp = len(emp_codes_raw)
    n_edu = len(edu_codes_raw)
    n_sex = len(sex_codes_raw)

    dim_order = sorted([(emp_pos, "emp"), (edu_pos, "edu"), (sex_pos, "sex")])
    sizes = {"emp": n_emp, "edu": n_edu, "sex": n_sex}
    strides: dict[str, int] = {}
    stride = 1
    for _, name in reversed(dim_order):
        strides[name] = stride
        stride *= sizes[name]

    counts: dict[str, dict[str, dict[str, float]]] = {}
    for emp_i, (emp_code, emp_label) in enumerate(emp_codes_raw):
        norm_emp = _normalise_employment(emp_code) if emp_code else _normalise_employment(emp_label)
        for edu_i, (edu_code, edu_label) in enumerate(edu_codes_raw):
            norm_edu = _normalise_education(edu_code) if edu_code else _normalise_education(edu_label)
            if norm_edu == "total":
                continue
            for sex_i, (_sex_code, sex_label) in enumerate(sex_codes_raw):
                norm_sex = _normalise_sex(sex_label)
                flat_idx = (
                    emp_i * strides["emp"]
                    + edu_i * strides["edu"]
                    + sex_i * strides["sex"]
                )
                raw_val = values[flat_idx] if flat_idx < len(values) else None
                if raw_val is None or raw_val == ".." or raw_val == ":":
                    v = 0.0
                else:
                    v = float(raw_val)

                if norm_sex not in counts:
                    counts[norm_sex] = {}
                if norm_edu not in counts[norm_sex]:
                    counts[norm_sex][norm_edu] = {}
                counts[norm_sex][norm_edu][norm_emp] = (
                    counts[norm_sex][norm_edu].get(norm_emp, 0.0) + v
                )

    if not counts:
        raise ValueError("No employment-by-education data parsed from SSB response")

    for sex, edu_dict in counts.items():
        for edu, emp_dict in edu_dict.items():
            if sum(emp_dict.values()) == 0.0:
                raise ValueError(
                    f"Fully suppressed employment subgroup for sex={sex!r}, "
                    f"education={edu!r} — all cells are zero or suppressed"
                )

    for sex in counts:
        for edu in counts[sex]:
            total = sum(counts[sex][edu].values()) or 1.0
            counts[sex][edu] = {k: v / total for k, v in counts[sex][edu].items()}
    return counts


def parse_region(raw: dict) -> dict[str, float]:
    """Parse table 07459 (age/sex by fylke) — sum across age/sex to get regional distribution."""
    dims = raw.get("dimension", {})
    values = raw.get("value", [])

    region_key = next((k for k in dims if "region" in k.lower()), None)
    age_key = next((k for k in dims if "alder" in k.lower() or "age" in k.lower()), None)
    sex_key = next((k for k in dims if "kjonn" in k.lower() or "kon" in k.lower() or "sex" in k.lower()), None)

    if not region_key:
        raise ValueError(f"Could not identify Region dimension in SSB response; dims={list(dims.keys())}")

    region_labels_raw = list(dims[region_key]["category"]["label"].items())

    if age_key and sex_key:
        n_age = len(dims[age_key]["category"]["label"])
        n_sex = len(dims[sex_key]["category"]["label"])
    else:
        n_age, n_sex = 1, 1

    counts: dict[str, float] = {}
    for ri, (_code, region_label) in enumerate(region_labels_raw):
        norm_region = _normalise_region(region_label)
        total = 0.0
        for ai in range(n_age):
            for si in range(n_sex):
                idx = ri * n_age * n_sex + ai * n_sex + si
                v = float(values[idx] or 0) if idx < len(values) else 0.0
                total += v
        counts[norm_region] = counts.get(norm_region, 0.0) + total

    if not counts:
        raise ValueError("No region data parsed from SSB response")
    grand_total = sum(counts.values()) or 1.0
    return {k: v / grand_total for k, v in counts.items()}


def parse_birth_location(raw: dict) -> dict[str, float]:
    """Parse table 09817 (InnvandrKat + Landbakgrunn) into
    ``{birth_location_label: probability}``.

    The non-immigrant population is injected as "Norway" using the total minus
    the immigrant count.
    """
    dims = raw.get("dimension", {})
    values = raw.get("value", [])

    country_key = next(
        (k for k in dims if "land" in k.lower() or "bakgrunn" in k.lower() or "country" in k.lower()),
        None,
    )
    if not country_key:
        raise ValueError(
            f"Could not identify country-background dimension in SSB 09817 response; dims={list(dims.keys())}"
        )

    country_labels_raw = list(dims[country_key]["category"]["label"].values())

    counts: dict[str, float] = {}
    for i, label_raw in enumerate(country_labels_raw):
        v = float(values[i] or 0) if i < len(values) else 0.0
        norm = _normalise_birth_location(label_raw)
        counts[norm] = counts.get(norm, 0.0) + v

    if not counts:
        raise ValueError("No birth_location data parsed from SSB response")
    total = sum(counts.values()) or 1.0
    return {k: v / total for k, v in counts.items()}


def parse_civil_status_by_age_sex(
    raw: dict,
) -> dict[tuple[str, str], dict[str, float]]:
    """Parse table 03031 (civil status x decade age band x sex) into
    ``{(age_group, sex): {civil_status_label: probability}}``.

    03031 Alder codes are single-digit decade numbers: "0"=0-9, "1"=10-19, ...
    """
    # Table-03031-specific decade-band mapping
    _AGE_DECADE_MAP_03031 = {
        "0": "18-24",  # 0-9 (only relevant for 18-19 — included in 18-24 bin)
        "1": "18-24",  # 10-19
        "2": "18-24",  # 20-29
        "3": "25-34",  # 30-39
        "4": "35-44",  # 40-49
        "5": "45-54",  # 50-59
        "6": "55-64",  # 60-69
        "7": "65-74",  # 70-79
        "8": "75-85",  # 80-89
        "9": "75-85",  # 90+
    }

    dims = raw.get("dimension", {})
    values = raw.get("value", [])

    cs_key = next(
        (k for k in dims if "ektesk" in k.lower() or "sivilstand" in k.lower() or "civil" in k.lower()),
        None,
    )
    age_key = next((k for k in dims if "alder" in k.lower() or "age" in k.lower()), None)
    sex_key = next((k for k in dims if "kjonn" in k.lower() or "kon" in k.lower() or "sex" in k.lower()), None)

    if not cs_key or not age_key or not sex_key:
        raise ValueError(
            f"Could not identify civil status/age/sex dimensions in SSB 03031 response; "
            f"dims={list(dims.keys())}"
        )

    cs_codes_raw = list(dims[cs_key]["category"]["label"].items())
    age_codes_raw = list(dims[age_key]["category"]["label"].items())
    sex_codes_raw = list(dims[sex_key]["category"]["label"].items())

    id_list = raw.get("id", list(dims.keys()))

    # Compute strides from the full dimension order so Region (and any other
    # extra dimensions) are handled correctly via summing.
    full_strides: dict[str, int] = {}
    s = 1
    for k in reversed(id_list):
        full_strides[k] = s
        s *= len(dims[k]["category"]["label"])

    # Other dimensions we will sum over (e.g. Region)
    extra_keys = [k for k in id_list if k not in (cs_key, age_key, sex_key)]
    extra_sizes = [len(dims[k]["category"]["label"]) for k in extra_keys]
    extra_total = 1
    for sz in extra_sizes:
        extra_total *= sz

    counts: dict[tuple[str, str], dict[str, float]] = {}
    for cs_i, (cs_code, cs_label) in enumerate(cs_codes_raw):
        norm_cs = _normalise_civil_status(cs_code) if cs_code else _normalise_civil_status(cs_label)
        for age_i, (age_code, _age_label) in enumerate(age_codes_raw):
            age_group = _AGE_DECADE_MAP_03031.get(age_code)
            if age_group not in VALID_AGE_GROUPS:
                continue
            for sex_i, (_sex_code, sex_label) in enumerate(sex_codes_raw):
                norm_sex = _normalise_sex(sex_label)
                base_idx = (
                    cs_i * full_strides[cs_key]
                    + age_i * full_strides[age_key]
                    + sex_i * full_strides[sex_key]
                )
                # Sum over all extra dimension values (e.g. all Region codes)
                v = 0.0
                for ei in range(extra_total):
                    # Compute extra offset by decomposing ei across extra_keys
                    extra_offset = 0
                    remainder = ei
                    for ek, esz in zip(reversed(extra_keys), reversed(extra_sizes)):
                        extra_offset += (remainder % esz) * full_strides[ek]
                        remainder //= esz
                    idx = base_idx + extra_offset
                    v += float(values[idx] or 0) if idx < len(values) else 0.0
                key: tuple[str, str] = (age_group, norm_sex)
                if key not in counts:
                    counts[key] = {}
                counts[key][norm_cs] = counts[key].get(norm_cs, 0.0) + v

    if not counts:
        raise ValueError("No civil_status data parsed from SSB response")
    for key, dist in counts.items():
        total = sum(dist.values()) or 1.0
        counts[key] = {k: v / total for k, v in dist.items()}
    return counts


def parse_industry_sector(raw: dict) -> dict[str, float]:
    """Parse table 09315 (employed by NACE2007 sector) into
    ``{industry_label: probability}``.
    """
    dims = raw.get("dimension", {})
    values = raw.get("value", [])

    nace_key = next(
        (k for k in dims if "nace" in k.lower() or "sn2007" in k.lower() or "næring" in k.lower()),
        None,
    )
    if not nace_key:
        raise ValueError(
            f"Could not identify NACE dimension in SSB 09315 response; dims={list(dims.keys())}"
        )

    nace_labels_raw = list(dims[nace_key]["category"]["label"].items())

    counts: dict[str, float] = {}
    for i, (_code, label_raw) in enumerate(nace_labels_raw):
        v = float(values[i] or 0) if i < len(values) else 0.0
        norm = _normalise_industry(label_raw)
        counts[norm] = counts.get(norm, 0.0) + v

    if not counts:
        raise ValueError("No industry_sector data parsed from SSB response")
    total = sum(counts.values()) or 1.0
    return {k: v / total for k, v in counts.items()}


def parse_employment_type(raw: dict) -> dict[tuple[str, str], dict[str, float]]:
    """Parse table 13878 (Ansettelsesforhold x ArbeidsTidRen x age x sex) into
    ``{(age_group, sex): {employment_type_label: probability}}``.

    Employment type labels are composite strings combining contract type and
    working hours, e.g. ``"permanent|full_time"``.
    """
    dims = raw.get("dimension", {})
    values = raw.get("value", [])

    attach_key = next(
        (k for k in dims if "ansett" in k.lower() or "attachment" in k.lower()),
        None,
    )
    hours_key = next(
        (k for k in dims if "arbeidstid" in k.lower() or "hours" in k.lower()),
        None,
    )
    age_key = next((k for k in dims if "alder" in k.lower() or "age" in k.lower()), None)
    sex_key = next((k for k in dims if "kjonn" in k.lower() or "kon" in k.lower() or "sex" in k.lower()), None)

    if not attach_key:
        raise ValueError(
            f"Could not identify Ansettelsesforhold dimension in SSB 13878 response; dims={list(dims.keys())}"
        )
    if not hours_key or not age_key or not sex_key:
        raise ValueError(
            f"Could not identify hours/age/sex dimensions in SSB 13878 response; dims={list(dims.keys())}"
        )

    attach_codes = list(dims[attach_key]["category"]["label"].items())
    hours_codes = list(dims[hours_key]["category"]["label"].items())
    age_codes = list(dims[age_key]["category"]["label"].items())
    sex_codes = list(dims[sex_key]["category"]["label"].items())

    id_list = raw.get("id", list(dims.keys()))
    attach_pos = id_list.index(attach_key) if attach_key in id_list else 0
    hours_pos = id_list.index(hours_key) if hours_key in id_list else 1
    age_pos = id_list.index(age_key) if age_key in id_list else 2
    sex_pos = id_list.index(sex_key) if sex_key in id_list else 3

    n_attach = len(attach_codes)
    n_hours = len(hours_codes)
    n_age = len(age_codes)
    n_sex = len(sex_codes)

    dim_order = sorted([
        (attach_pos, "attach"), (hours_pos, "hours"),
        (age_pos, "age"), (sex_pos, "sex"),
    ])
    sizes = {"attach": n_attach, "hours": n_hours, "age": n_age, "sex": n_sex}
    strides: dict[str, int] = {}
    stride = 1
    for _, name in reversed(dim_order):
        strides[name] = stride
        stride *= sizes[name]

    counts: dict[tuple[str, str], dict[str, float]] = {}
    for att_i, (att_code, att_label) in enumerate(attach_codes):
        norm_att = ANSETTELSESFORHOLD_CODES.get(att_code.strip().upper())
        if not norm_att:
            norm_att = ANSETTELSESFORHOLD_CODES.get(att_label.strip().lower(), att_label)
        for hr_i, (hr_code, hr_label) in enumerate(hours_codes):
            norm_hr = ARBEIDSTID_CODES.get(hr_code.strip().upper())
            if not norm_hr:
                norm_hr = ARBEIDSTID_CODES.get(hr_label.strip().lower(), hr_label)
            composite = f"{norm_att}|{norm_hr}"
            for age_i, (age_code, age_label) in enumerate(age_codes):
                age_group = resolve_age_group(age_code, {}) or resolve_age_group(str(age_label), {})
                if age_group not in VALID_AGE_GROUPS:
                    continue
                for sex_i, (_sex_code, sex_label) in enumerate(sex_codes):
                    norm_sex = _normalise_sex(sex_label)
                    flat_idx = (
                        att_i * strides["attach"]
                        + hr_i * strides["hours"]
                        + age_i * strides["age"]
                        + sex_i * strides["sex"]
                    )
                    v = float(values[flat_idx] or 0) if flat_idx < len(values) else 0.0
                    key: tuple[str, str] = (age_group, norm_sex)
                    if key not in counts:
                        counts[key] = {}
                    counts[key][composite] = counts[key].get(composite, 0.0) + v

    if not counts:
        raise ValueError("No employment_type data parsed from SSB response")
    for key in counts:
        total = sum(counts[key].values()) or 1.0
        counts[key] = {k: v / total for k, v in counts[key].items()}
    return counts


def parse_housing_tenure(raw: dict) -> dict[str, float]:
    """Parse table 11081 (EierStatus by household/building type) into
    ``{housing_tenure_label: probability}``.
    """
    dims = raw.get("dimension", {})
    values = raw.get("value", [])

    tenure_key = next(
        (k for k in dims if "eierst" in k.lower() or "tenure" in k.lower() or "eier" in k.lower()),
        None,
    )
    if not tenure_key:
        raise ValueError(
            f"Could not identify EierStatus dimension in SSB 11081 response; dims={list(dims.keys())}"
        )

    tenure_labels_raw = list(dims[tenure_key]["category"]["label"].items())

    # Identify if there are other dims we need to flatten over
    other_dims = [k for k in dims if k != tenure_key]
    n_other = 1
    for k in other_dims:
        n_other *= len(dims[k]["category"]["label"])

    id_list = raw.get("id", list(dims.keys()))
    tenure_pos = id_list.index(tenure_key) if tenure_key in id_list else -1

    n_tenure = len(tenure_labels_raw)

    counts: dict[str, float] = {}
    if tenure_pos == len(id_list) - 1:
        # Tenure is innermost — iterate outer dims, pick tenure values
        for oi in range(n_other):
            for ti, (_code, label_raw) in enumerate(tenure_labels_raw):
                idx = oi * n_tenure + ti
                v = float(values[idx] or 0) if idx < len(values) else 0.0
                norm = _normalise_housing(label_raw)
                counts[norm] = counts.get(norm, 0.0) + v
    else:
        # Tenure is outermost or somewhere else — iterate tenure x other
        for ti, (_code, label_raw) in enumerate(tenure_labels_raw):
            total = 0.0
            for oi in range(n_other):
                idx = ti * n_other + oi
                v = float(values[idx] or 0) if idx < len(values) else 0.0
                total += v
            norm = _normalise_housing(label_raw)
            counts[norm] = counts.get(norm, 0.0) + total

    if not counts:
        raise ValueError("No housing_tenure data parsed from SSB response")
    grand_total = sum(counts.values()) or 1.0
    return {k: v / grand_total for k, v in counts.items()}


def parse_household_size(raw: dict) -> dict[str, float]:
    """Parse table 06079 (HushStr household size) into
    ``{household_size_label: probability}``.
    """
    dims = raw.get("dimension", {})
    values = raw.get("value", [])

    size_key = next(
        (k for k in dims if "hushstr" in k.lower() or "hush" in k.lower() or "household" in k.lower()),
        None,
    )
    if not size_key:
        raise ValueError(
            f"Could not identify HushStr dimension in SSB 06079 response; dims={list(dims.keys())}"
        )

    size_labels_raw = list(dims[size_key]["category"]["label"].items())

    counts: dict[str, float] = {}
    for i, (_code, label_raw) in enumerate(size_labels_raw):
        v = float(values[i] or 0) if i < len(values) else 0.0
        norm = _normalise_household_size(label_raw)
        counts[norm] = counts.get(norm, 0.0) + v

    if not counts:
        raise ValueError("No household_size data parsed from SSB response")
    total = sum(counts.values()) or 1.0
    return {k: v / total for k, v in counts.items()}


def parse_parental_structure(raw: dict) -> dict[str, float]:
    """Parse table 06083 (FamilieType) into
    ``{family_type_label: probability}``.
    """
    dims = raw.get("dimension", {})
    values = raw.get("value", [])

    family_key = next(
        (k for k in dims if "familie" in k.lower() or "family" in k.lower() or "familje" in k.lower()),
        None,
    )
    if not family_key:
        raise ValueError(
            f"Could not identify FamilieType dimension in SSB 06083 response; dims={list(dims.keys())}"
        )

    labels_raw = list(dims[family_key]["category"]["label"].items())

    counts: dict[str, float] = {}
    for i, (_code, label_raw) in enumerate(labels_raw):
        v = float(values[i] or 0) if i < len(values) else 0.0
        norm = _normalise_family_type(label_raw)
        counts[norm] = counts.get(norm, 0.0) + v

    if not counts:
        raise ValueError("No family structure data parsed from SSB response")
    total = sum(counts.values()) or 1.0
    return {k: v / total for k, v in counts.items()}


def parse_socioeconomic(
    raw: dict,
) -> dict[tuple[str, str], dict[str, float]]:
    """Parse table 06655 (BruttoInn x Alder x Kjonn) into
    ``{(age_group, sex_label): {class_label: probability}}``.

    SSB age-band to pipeline VALID_AGE_GROUPS mapping:
      17-24 -> "18-24"           (pipeline floor is 18; 17-year-olds are a small fraction)
      25-34 -> "25-34"
      35-44 -> "35-44"
      45-54 -> "45-54"
      55-66 -> "55-64"           (closest pipeline band; 65-66 are a small over-count)
      67+   -> "65-74", "75-85"  (open-ended band covers both pipeline groups; same distribution)
    """
    # SSB age-band code -> pipeline group label(s).
    # 67+ is open-ended and covers the pipeline's "65-74" and "75-85" bands.
    # We assign both pipeline bands the same distribution (accepted limitation).
    _AGE_BAND_MAP: dict[str, list[str]] = {
        "17-24": ["18-24"],
        "25-34": ["25-34"],
        "35-44": ["35-44"],
        "45-54": ["45-54"],
        "55-66": ["55-64"],
        "67+":   ["65-74", "75-85"],
    }

    # Build code->(low, high) lookup from BRUTTOINN_BRACKETS
    _BRACKET_EDGES: dict[str, tuple[float, float]] = {
        code: (lo, hi) for code, lo, hi in BRUTTOINN_BRACKETS
    }
    _BRACKET_MIDPOINTS: dict[str, float] = {
        code: (lo + hi) / 2.0 for code, lo, hi in BRUTTOINN_BRACKETS
    }

    dims = raw.get("dimension", {})
    values = raw.get("value", [])

    bracket_key = next(
        (k for k in dims if "bruttoinn" in k.lower() or "income" in k.lower()),
        None,
    )
    age_key = next((k for k in dims if "alder" in k.lower() or "age" in k.lower()), None)
    sex_key = next(
        (k for k in dims if "kjonn" in k.lower() or "kon" in k.lower() or "sex" in k.lower()),
        None,
    )

    if not bracket_key:
        raise ValueError(
            f"Could not identify BruttoInn dimension in SSB 06655 response; dims={list(dims.keys())}"
        )
    if not age_key:
        raise ValueError(
            f"Could not identify Alder dimension in SSB 06655 response; dims={list(dims.keys())}"
        )
    if not sex_key:
        raise ValueError(
            f"Could not identify Kjonn dimension in SSB 06655 response; dims={list(dims.keys())}"
        )

    bracket_codes_raw = list(dims[bracket_key]["category"]["label"].items())
    age_codes_raw = list(dims[age_key]["category"]["label"].items())
    sex_codes_raw = list(dims[sex_key]["category"]["label"].items())

    id_list = raw.get("id", list(dims.keys()))

    full_strides: dict[str, int] = {}
    s = 1
    for k in reversed(id_list):
        full_strides[k] = s
        s *= len(dims[k]["category"]["label"])

    # Accumulate per (age_group, sex): {bracket_code: count}.
    # Each SSB age band maps to one or more pipeline groups (67+ covers both
    # "65-74" and "75-85" — both receive the same distribution).
    cell_counts: dict[tuple[str, str], dict[str, float]] = {}

    for age_i, (age_code, _age_label) in enumerate(age_codes_raw):
        age_groups = _AGE_BAND_MAP.get(age_code)
        if age_groups is None:
            continue
        for sex_i, (sex_code, _sex_label) in enumerate(sex_codes_raw):
            if sex_code == "0":
                # Skip the "both sexes" aggregate — we use individual sex rows only
                continue
            sex_label = "Male" if sex_code == "1" else "Female"
            for age_group in age_groups:
                key: tuple[str, str] = (age_group, sex_label)
                if key not in cell_counts:
                    cell_counts[key] = {}
                for br_i, (br_code, _br_label) in enumerate(bracket_codes_raw):
                    if br_code not in _BRACKET_EDGES:
                        continue
                    flat_idx = (
                        br_i * full_strides[bracket_key]
                        + age_i * full_strides[age_key]
                        + sex_i * full_strides[sex_key]
                    )
                    raw_val = values[flat_idx] if flat_idx < len(values) else None
                    if raw_val is None or raw_val == ".." or raw_val == ":":
                        v = 0.0
                    else:
                        v = float(raw_val)
                    cell_counts[key][br_code] = cell_counts[key].get(br_code, 0.0) + v

    if not cell_counts:
        raise ValueError("No socioeconomic data parsed from SSB 06655 response")

    # Compute a single national median from summed counts across all cells
    national_counts: dict[str, float] = {}
    for dist in cell_counts.values():
        for br_code, cnt in dist.items():
            national_counts[br_code] = national_counts.get(br_code, 0.0) + cnt

    ordered_codes = [code for code, _, _ in BRUTTOINN_BRACKETS if code in national_counts]
    midpoints = [_BRACKET_MIDPOINTS[c] for c in ordered_codes]
    counts_list = [national_counts[c] for c in ordered_codes]
    national_median = median_from_brackets(midpoints, counts_list)

    result: dict[tuple[str, str], dict[str, float]] = {}
    for key, br_dist in cell_counts.items():
        if sum(br_dist.values()) == 0:
            raise ValueError(
                f"All bracket counts are zero for cell {key!r} in SSB 06655 response"
            )
        ordered = [code for code, _, _ in BRUTTOINN_BRACKETS if code in br_dist]
        edges = [_BRACKET_EDGES[c] for c in ordered]
        cnts = [br_dist[c] for c in ordered]
        result[key] = classify_brackets(edges, cnts, national_median)

    return result


def parse_birth_country_detail(
    raw: dict,
) -> dict[tuple[str, str], dict[str, float]]:
    """Parse table 09817 (Landbakgrunn by age/sex) into
    ``{(age_group, sex): {country_label: probability}}``.
    """
    # Code-to-output-label mapping from category_mappings.json
    _CODE_TO_COUNTRY = {
        "131": "Poland", "106": "Sweden", "148": "Other", "136": "Lithuania",
        "564": "Syria", "346": "Somalia", "144": "Other", "534": "Pakistan",
        "452": "Iraq", "456": "Other", "444": "India", "103": "Other",
        "410": "Other", "424": "Other", "575": "Other", "101": "Other",
        "159": "Other", "241": "Other", "684": "Other", "140": "Other",
    }

    dims = raw.get("dimension", {})
    values = raw.get("value", [])

    country_key = next(
        (k for k in dims if "land" in k.lower() or "bakgrunn" in k.lower() or "country" in k.lower()),
        None,
    )
    age_key = next((k for k in dims if "alder" in k.lower() or "age" in k.lower()), None)
    sex_key = next((k for k in dims if "kjonn" in k.lower() or "kon" in k.lower() or "sex" in k.lower()), None)

    if not country_key or not age_key or not sex_key:
        raise ValueError(
            f"Could not identify country/age/sex dimensions in SSB 09817 response; dims={list(dims.keys())}"
        )

    country_codes_raw = list(dims[country_key]["category"]["label"].items())  # (code, label)
    age_codes_raw = list(dims[age_key]["category"]["label"].items())
    sex_codes_raw = list(dims[sex_key]["category"]["label"].items())

    id_list = raw.get("id", list(dims.keys()))
    country_pos = id_list.index(country_key) if country_key in id_list else 0
    age_pos = id_list.index(age_key) if age_key in id_list else 1
    sex_pos = id_list.index(sex_key) if sex_key in id_list else 2

    n_country = len(country_codes_raw)
    n_age = len(age_codes_raw)
    n_sex = len(sex_codes_raw)

    dim_order = sorted([(country_pos, "country"), (age_pos, "age"), (sex_pos, "sex")])
    sizes = {"country": n_country, "age": n_age, "sex": n_sex}
    strides: dict[str, int] = {}
    stride = 1
    for _, name in reversed(dim_order):
        strides[name] = stride
        stride *= sizes[name]

    counts: dict[tuple[str, str], dict[str, float]] = {}
    for ci, (c_code, c_label) in enumerate(country_codes_raw):
        country_label = _CODE_TO_COUNTRY.get(c_code, "Other")
        for ai, (age_code, _age_label) in enumerate(age_codes_raw):
            # 09817 also uses 3-digit zero-padded age codes
            try:
                age = int(age_code)
            except ValueError:
                try:
                    age = int(str(_age_label).split()[0])
                except (ValueError, IndexError):
                    continue
            age_group = None
            from population_synthetic.generators.real.helpers import age_to_group
            try:
                age_group = age_to_group(age)
            except ValueError:
                continue
            if age_group not in VALID_AGE_GROUPS:
                continue
            for si, (_sex_code, sex_label) in enumerate(sex_codes_raw):
                norm_sex = _normalise_sex(sex_label)
                flat_idx = ci * strides["country"] + ai * strides["age"] + si * strides["sex"]
                v = float(values[flat_idx] or 0) if flat_idx < len(values) else 0.0
                key: tuple[str, str] = (age_group, norm_sex)
                if key not in counts:
                    counts[key] = {}
                counts[key][country_label] = counts[key].get(country_label, 0.0) + v

    if not counts:
        raise ValueError("No birth_country_detail data parsed from SSB response")
    for key, dist in counts.items():
        total = sum(dist.values()) or 1.0
        counts[key] = {k: v / total for k, v in dist.items()}
    return counts
