"""
normalizer.py -- Normalize raw-format SCB/SSB population records to flat schema strings.

Applies category_mappings.json at comparison time so statistical tests work
against pipeline-format populations that use schema-aligned labels.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from population_synth._paths import PROJECT_ROOT

_SCB_MAPPINGS_PATH = PROJECT_ROOT / "config" / "assets" / "scb_reference" / "category_mappings.json"

_SWEDEN_BIRTH_LABELS: frozenset[str] = frozenset({
    "born in sweden", "sverige", "sweden", "födda i sverige",
})


def load_mappings(path: Path | None = None) -> dict:
    """Load category_mappings.json from *path* (defaults to SCB reference)."""
    p = path or _SCB_MAPPINGS_PATH
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _ci_map(d: dict[str, str]) -> dict[str, str]:
    """Build a case-insensitive lookup dict (lowercased keys, original values)."""
    return {k.lower(): v for k, v in d.items()}


def _label(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, dict):
        return v.get("label") or v.get("code") or v.get("decile")
    return str(v)


def _ci_get(ci_dict: dict[str, str], raw: str, default: str | None = None) -> str | None:
    return ci_dict.get(raw.lower(), default if default is not None else raw)


def _age_to_group(age: int) -> str:
    if age < 25:
        return "18-24"
    if age < 35:
        return "25-34"
    if age < 45:
        return "35-44"
    if age < 55:
        return "45-54"
    if age < 65:
        return "55-64"
    if age < 75:
        return "65-74"
    return "75-85"


# ------------------------------------------------------------------
# Raw-format detection
# ------------------------------------------------------------------

def is_raw_format(individuals: list[dict]) -> bool:
    """Return True if the population uses raw nested-dict format (Phase 4+ SCB output)."""
    if not individuals:
        return False
    first = individuals[0]
    return any(isinstance(v, dict) for v in first.values())


# ------------------------------------------------------------------
# Main normalization
# ------------------------------------------------------------------

def normalize_scb_to_schema(records: list[dict], mappings: dict) -> list[dict]:
    """Convert raw-format SCB records (nested RawCategory dicts) to flat schema strings.

    Applies category_mappings.json at comparison time so statistical tests work
    against pipeline-format populations that use schema-aligned labels.
    """
    edu_map = _ci_map(mappings.get("education", {}).get("sun2020_level_mappings", {}))
    emp_map = _ci_map(mappings.get("employment", {}).get("aku_label_mappings", {}))
    birth_loc_map = _ci_map(mappings.get("birth_location", {}).get("region_label_mappings", {}))
    region_map = _ci_map(mappings.get("region", {}).get("scb_label_mappings", {}))
    cs_map = _ci_map(mappings.get("civil_status", {}).get("scb_label_mappings", {}))
    industry_map = _ci_map(mappings.get("industry_sector", {}).get("scb_label_mappings", {}))
    att_map = _ci_map(mappings.get("employment_type", {}).get("attachment_label_mappings", {}))
    hrs_map = _ci_map(mappings.get("employment_type", {}).get("hours_label_mappings", {}))
    housing_map = _ci_map(mappings.get("housing_tenure", {}).get("scb_label_mappings", {}))
    hh_size_map = _ci_map(mappings.get("household_size", {}).get("scb_label_mappings", {}))
    income_map = _ci_map(mappings.get("income_source", {}).get("scb_label_mappings", {}))
    bc_detail_map: dict[str, str] = mappings.get("birth_country_detail", {}).get("scb_label_mappings", {})

    socio_code_to_schema: dict[str, str] = {}
    for entry in mappings.get("socioeconomic", {}).get("mappings", {}).values():
        schema_label = entry.get("schema_label", "")
        for code in entry.get("scb_codes", []):
            socio_code_to_schema[str(code)] = schema_label
    # Decile labels (legacy SCB-format populations like scb02) -> 4-class schema
    socio_decile_map: dict[str, str] = mappings.get("socioeconomic", {}).get("scb_decile_mappings", {})
    socio_decile_ci: dict[str, str] = {k.lower(): v for k, v in socio_decile_map.items()}
    socio_decile_num: dict[str, str] = {}
    for k, v in socio_decile_map.items():
        if k.lower().startswith("decile "):
            socio_decile_num[k.split()[-1]] = v

    parental_raw_to_schema: dict[str, str] = {}
    for entry in mappings.get("parental_structure", {}).get("mappings", {}).values():
        schema_label = entry.get("schema_label", "")
        for code in entry.get("scb_codes", []):
            parental_raw_to_schema[code.lower()] = schema_label

    def _match_parental(raw_lower: str) -> str | None:
        exact = parental_raw_to_schema.get(raw_lower)
        if exact is not None:
            return exact
        for code, schema_label in parental_raw_to_schema.items():
            if code in raw_lower:
                return schema_label
        return None

    normalized = []
    for ind in records:
        rec: dict[str, Any] = {"id": ind.get("id")}

        age = ind.get("age")
        rec["age"] = age
        if age is not None:
            try:
                rec["age_group"] = _age_to_group(int(age))
            except (ValueError, TypeError):
                rec["age_group"] = None

        sex_raw = _label(ind.get("biological_sex"))
        if sex_raw is not None:
            sex_lower = sex_raw.lower()
            if sex_lower in ("men", "male", "1"):
                rec["biological_sex"] = "Male"
            elif sex_lower in ("women", "female", "2"):
                rec["biological_sex"] = "Female"
            else:
                rec["biological_sex"] = sex_raw
        else:
            rec["biological_sex"] = None

        edu_raw = _label(ind.get("education_level"))
        rec["education_level"] = _ci_get(edu_map, edu_raw) if edu_raw else None

        emp_raw = _label(ind.get("employment_status"))
        rec["employment_status"] = _ci_get(emp_map, emp_raw) if emp_raw else None

        birth_raw = _label(ind.get("birth_location"))
        birth_schema = _ci_get(birth_loc_map, birth_raw) if birth_raw else None
        rec["birth_location"] = birth_schema

        region_raw = _label(ind.get("region"))
        region_schema = _ci_get(region_map, region_raw) if region_raw else None
        rec["region"] = region_schema

        socio_raw = ind.get("socioeconomic_class")
        socio_label: str | None = None
        if isinstance(socio_raw, dict):
            raw_val = str(socio_raw.get("label") or socio_raw.get("decile", ""))
            raw_val_l = raw_val.lower()
            if raw_val_l in socio_decile_ci:
                socio_label = socio_decile_ci[raw_val_l]
            elif raw_val_l.startswith("decile "):
                token = raw_val.split()[-1]
                socio_label = (socio_decile_num.get(token)
                               or socio_code_to_schema.get(token) or raw_val)
            else:
                socio_label = socio_code_to_schema.get(raw_val) or (raw_val if raw_val else None)
        elif socio_raw is not None:
            socio_label = socio_code_to_schema.get(str(socio_raw), str(socio_raw))
        rec["socioeconomic_class"] = socio_label

        par_raw = _label(ind.get("parental_structure"))
        if par_raw is not None:
            rec["parental_structure"] = _match_parental(par_raw.lower()) or par_raw
        else:
            rec["parental_structure"] = None

        cs_raw = _label(ind.get("civil_status"))
        rec["civil_status"] = _ci_get(cs_map, cs_raw) if cs_raw else None

        industry_raw = _label(ind.get("industry_sector"))
        rec["industry_sector"] = _ci_get(industry_map, industry_raw) if industry_raw else "Not Applicable"

        emp_type_raw = ind.get("employment_type")
        if isinstance(emp_type_raw, dict) and "attachment" in emp_type_raw:
            att_label = _label(emp_type_raw.get("attachment")) or ""
            hrs_label = _label(emp_type_raw.get("hours")) or ""
            att_schema = att_map.get(att_label.lower(), att_label)
            hrs_schema = hrs_map.get(hrs_label.lower(), hrs_label)
            if att_schema == "permanent" and hrs_schema == "full_time":
                rec["employment_type"] = "Permanent Full-time"
            elif att_schema == "permanent" and hrs_schema == "part_time":
                rec["employment_type"] = "Permanent Part-time"
            elif att_schema == "temporary" and hrs_schema == "full_time":
                rec["employment_type"] = "Temporary Full-time"
            elif att_schema == "temporary" and hrs_schema == "part_time":
                rec["employment_type"] = "Temporary Part-time"
            elif att_schema == "self_employed":
                rec["employment_type"] = "Self-Employed"
            else:
                rec["employment_type"] = f"{att_schema}/{hrs_schema}"
        elif emp_type_raw is None:
            rec["employment_type"] = "Not Applicable"
        else:
            rec["employment_type"] = _label(emp_type_raw)

        housing_raw = _label(ind.get("housing_tenure"))
        rec["housing_tenure"] = _ci_get(housing_map, housing_raw) if housing_raw else None

        hh_raw = _label(ind.get("household_size"))
        rec["household_size"] = _ci_get(hh_size_map, hh_raw) if hh_raw else None

        income_raw = _label(ind.get("income_source"))
        rec["income_source"] = _ci_get(income_map, income_raw) if income_raw else None

        bc_raw = ind.get("birth_country_detail")
        if rec.get("birth_location") == "Sweden":
            rec["birth_country_detail"] = "Sweden"
        elif isinstance(bc_raw, dict):
            code = bc_raw.get("code")
            label_val = bc_raw.get("label")
            if code and code in bc_detail_map:
                rec["birth_country_detail"] = bc_detail_map[code]
            elif label_val and label_val.lower() in _SWEDEN_BIRTH_LABELS:
                rec["birth_country_detail"] = "Sweden"
            elif label_val:
                rec["birth_country_detail"] = bc_detail_map.get(label_val, label_val)
            else:
                rec["birth_country_detail"] = None
        elif bc_raw is not None:
            rec["birth_country_detail"] = str(bc_raw)
        else:
            rec["birth_country_detail"] = None

        normalized.append(rec)

    return normalized


def normalize_if_raw(pop: dict, mappings: dict) -> dict:
    """Return a copy of pop with individuals normalized if raw-format, else return pop unchanged."""
    individuals = pop.get("individuals", [])
    if not is_raw_format(individuals):
        return pop
    normalized_individuals = normalize_scb_to_schema(individuals, mappings)
    return {**pop, "individuals": normalized_individuals}
