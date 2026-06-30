"""Abstract and base reference-population mappers.

The *reference mapper* turns one raw-format reference record (nested
``RawCategory`` dicts produced by a national statistics API, e.g. SCB/ISTAT)
into the flat canonical schema dict the ``StatisticalEvaluator`` consumes.
``AbstractReferenceMapper`` declares the per-country contract;
``BaseReferenceMapper`` provides the orchestration plus all the mappings-driven
attribute logic, which is identical across countries.  Country specificities
(the domestic country name / birth-label tokens and the default mappings
directory) live in the ``SwedishReferenceMapper`` / ``ItalianReferenceMapper``
subclasses as class attributes, so the two countries are never interleaved in a
single function.

This mirrors the synthetic side (``synthetic_mapper/``): there, country
divergence is behaviour expressed by method overrides; here it is data expressed
by class attributes -- the reference input is already cleanly coded, so a single
mappings-driven loop serves every country.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Abstract contract
# ---------------------------------------------------------------------------

class AbstractReferenceMapper(ABC):
    """Per-country contract for normalizing a raw reference population to schema.

    Subclasses supply the three country class attributes below; the per-record
    behaviour lives in :class:`BaseReferenceMapper`.
    """

    #: Domestic country name in the schema (e.g. ``"Sweden"`` / ``"Italy"``).
    DOMESTIC_NAME: ClassVar[str]
    #: Lowercased birth-label tokens that resolve to the domestic country.
    DOMESTIC_BIRTH_LABELS: ClassVar[frozenset[str]]
    #: Default category-mappings sub-directory under ``config/mapping/``.
    MAPPINGS_SUBDIR: ClassVar[str]

    @abstractmethod
    def normalize_individual(self, record: dict[str, Any]) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Base implementation: orchestration + mappings-driven attributes
# ---------------------------------------------------------------------------

class BaseReferenceMapper(AbstractReferenceMapper):
    """Shared orchestration and the attribute logic identical across countries.

    Not instantiated directly -- a country subclass supplies the class
    attributes :data:`DOMESTIC_NAME`, :data:`DOMESTIC_BIRTH_LABELS` and
    :data:`MAPPINGS_SUBDIR`.
    """

    def __init__(self, mappings: dict) -> None:
        """Pre-compute every category lookup once from *mappings*."""
        self.mappings = mappings
        self._edu_map = _ci_map(mappings.get("education", {}).get("sun2020_level_mappings", {}))
        self._emp_map = _ci_map(mappings.get("employment", {}).get("aku_label_mappings", {}))
        self._birth_loc_map = _ci_map(mappings.get("birth_location", {}).get("region_label_mappings", {}))
        self._region_map = _ci_map(mappings.get("region", {}).get("scb_label_mappings", {}))
        self._cs_map = _ci_map(mappings.get("civil_status", {}).get("scb_label_mappings", {}))
        self._industry_map = _ci_map(mappings.get("industry_sector", {}).get("scb_label_mappings", {}))
        self._att_map = _ci_map(mappings.get("employment_type", {}).get("attachment_label_mappings", {}))
        self._hrs_map = _ci_map(mappings.get("employment_type", {}).get("hours_label_mappings", {}))
        self._housing_map = _ci_map(mappings.get("housing_tenure", {}).get("scb_label_mappings", {}))
        self._hh_size_map = _ci_map(mappings.get("household_size", {}).get("scb_label_mappings", {}))
        self._income_map = _ci_map(mappings.get("income_source", {}).get("scb_label_mappings", {}))
        self._bc_detail_map: dict[str, str] = mappings.get("birth_country_detail", {}).get("scb_label_mappings", {})

        self._socio_code_to_schema: dict[str, str] = {}
        for entry in mappings.get("socioeconomic", {}).get("mappings", {}).values():
            schema_label = entry.get("schema_label", "")
            for code in entry.get("scb_codes", []):
                self._socio_code_to_schema[str(code)] = schema_label
        # Decile labels (legacy SCB-format populations like scb02) -> 4-class schema
        socio_decile_map: dict[str, str] = mappings.get("socioeconomic", {}).get("scb_decile_mappings", {})
        self._socio_decile_ci: dict[str, str] = {k.lower(): v for k, v in socio_decile_map.items()}
        self._socio_decile_num: dict[str, str] = {}
        for k, v in socio_decile_map.items():
            if k.lower().startswith("decile "):
                self._socio_decile_num[k.split()[-1]] = v

        self._parental_raw_to_schema: dict[str, str] = {}
        for entry in mappings.get("parental_structure", {}).get("mappings", {}).values():
            schema_label = entry.get("schema_label", "")
            for code in entry.get("scb_codes", []):
                self._parental_raw_to_schema[code.lower()] = schema_label

    # -- orchestrator -------------------------------------------------------

    def normalize_individual(self, record: dict[str, Any]) -> dict[str, Any]:
        """Convert one raw-format record (nested RawCategory dicts) to flat schema strings."""
        rec: dict[str, Any] = {"id": record.get("id")}

        age = record.get("age")
        rec["age"] = age
        if age is not None:
            rec["age_group"] = self.map_age_group(age)

        rec["biological_sex"] = self.map_biological_sex(record)
        rec["education_level"] = self.map_education(record)
        rec["employment_status"] = self.map_employment_status(record)
        rec["birth_location"] = self.map_birth_location(record)
        rec["region"] = self.map_region(record)
        rec["socioeconomic_class"] = self.map_socioeconomic(record)
        rec["parental_structure"] = self.map_parental_structure(record)
        rec["civil_status"] = self.map_civil_status(record)
        rec["industry_sector"] = self.map_industry_sector(record)
        rec["employment_type"] = self.map_employment_type(record)
        rec["housing_tenure"] = self.map_housing_tenure(record)
        rec["household_size"] = self.map_household_size(record)
        rec["income_source"] = self.map_income_source(record)
        rec["birth_country_detail"] = self.map_birth_country_detail(record, rec.get("birth_location"))
        return rec

    # -- mappings-driven attributes (identical across countries) ------------

    def map_age_group(self, age: Any) -> str | None:
        try:
            return _age_to_group(int(age))
        except (ValueError, TypeError):
            return None

    def map_biological_sex(self, record: dict) -> str | None:
        sex_raw = _label(record.get("biological_sex"))
        if sex_raw is None:
            return None
        sex_lower = sex_raw.lower()
        if sex_lower in ("men", "male", "1"):
            return "Male"
        if sex_lower in ("women", "female", "2"):
            return "Female"
        return sex_raw

    def map_education(self, record: dict) -> str | None:
        edu_raw = _label(record.get("education_level"))
        return _ci_get(self._edu_map, edu_raw) if edu_raw else None

    def map_employment_status(self, record: dict) -> str | None:
        emp_raw = _label(record.get("employment_status"))
        return _ci_get(self._emp_map, emp_raw) if emp_raw else None

    def map_birth_location(self, record: dict) -> str | None:
        birth_raw = _label(record.get("birth_location"))
        return _ci_get(self._birth_loc_map, birth_raw) if birth_raw else None

    def map_region(self, record: dict) -> str | None:
        region_raw = _label(record.get("region"))
        return _ci_get(self._region_map, region_raw) if region_raw else None

    def map_socioeconomic(self, record: dict) -> str | None:
        socio_raw = record.get("socioeconomic_class")
        if isinstance(socio_raw, dict):
            raw_val = str(socio_raw.get("label") or socio_raw.get("decile", ""))
            raw_val_l = raw_val.lower()
            if raw_val_l in self._socio_decile_ci:
                return self._socio_decile_ci[raw_val_l]
            if raw_val_l.startswith("decile "):
                token = raw_val.split()[-1]
                return (self._socio_decile_num.get(token)
                        or self._socio_code_to_schema.get(token) or raw_val)
            return self._socio_code_to_schema.get(raw_val) or (raw_val if raw_val else None)
        if socio_raw is not None:
            return self._socio_code_to_schema.get(str(socio_raw), str(socio_raw))
        return None

    def _match_parental(self, raw_lower: str) -> str | None:
        exact = self._parental_raw_to_schema.get(raw_lower)
        if exact is not None:
            return exact
        for code, schema_label in self._parental_raw_to_schema.items():
            if code in raw_lower:
                return schema_label
        return None

    def map_parental_structure(self, record: dict) -> str | None:
        par_raw = _label(record.get("parental_structure"))
        if par_raw is not None:
            return self._match_parental(par_raw.lower()) or par_raw
        return None

    def map_civil_status(self, record: dict) -> str | None:
        cs_raw = _label(record.get("civil_status"))
        return _ci_get(self._cs_map, cs_raw) if cs_raw else None

    def map_industry_sector(self, record: dict) -> str | None:
        industry_raw = _label(record.get("industry_sector"))
        return _ci_get(self._industry_map, industry_raw) if industry_raw else "Not Applicable"

    def map_employment_type(self, record: dict) -> str | None:
        emp_type_raw = record.get("employment_type")
        if isinstance(emp_type_raw, dict) and "attachment" in emp_type_raw:
            att_label = _label(emp_type_raw.get("attachment")) or ""
            hrs_label = _label(emp_type_raw.get("hours")) or ""
            att_schema = self._att_map.get(att_label.lower(), att_label)
            hrs_schema = self._hrs_map.get(hrs_label.lower(), hrs_label)
            if att_schema == "permanent" and hrs_schema == "full_time":
                return "Permanent Full-time"
            if att_schema == "permanent" and hrs_schema == "part_time":
                return "Permanent Part-time"
            if att_schema == "temporary" and hrs_schema == "full_time":
                return "Temporary Full-time"
            if att_schema == "temporary" and hrs_schema == "part_time":
                return "Temporary Part-time"
            if att_schema == "self_employed":
                return "Self-Employed"
            return f"{att_schema}/{hrs_schema}"
        if isinstance(emp_type_raw, str) and "|" in emp_type_raw:
            # Italian pipe-separated format (e.g. "Permanent|Full-time")
            return emp_type_raw
        if emp_type_raw is None:
            return "Not Applicable"
        return _label(emp_type_raw)

    def map_housing_tenure(self, record: dict) -> str | None:
        housing_raw = _label(record.get("housing_tenure"))
        return _ci_get(self._housing_map, housing_raw) if housing_raw else None

    def map_household_size(self, record: dict) -> str | None:
        hh_raw = _label(record.get("household_size"))
        return _ci_get(self._hh_size_map, hh_raw) if hh_raw else None

    def map_income_source(self, record: dict) -> str | None:
        income_raw = _label(record.get("income_source"))
        return _ci_get(self._income_map, income_raw) if income_raw else None

    # -- country-divergent attribute (data-driven via class attributes) -----

    def map_birth_country_detail(self, record: dict, birth_location: str | None) -> str | None:
        """Resolve birth-country detail, collapsing domestic-born to ``DOMESTIC_NAME``."""
        bc_raw = record.get("birth_country_detail")
        if birth_location == self.DOMESTIC_NAME:
            return self.DOMESTIC_NAME
        if isinstance(bc_raw, dict):
            code = bc_raw.get("code")
            label_val = bc_raw.get("label")
            if code and code in self._bc_detail_map:
                return self._bc_detail_map[code]
            if label_val and label_val.lower() in self.DOMESTIC_BIRTH_LABELS:
                return self.DOMESTIC_NAME
            if label_val:
                return self._bc_detail_map.get(label_val, label_val)
            return None
        if bc_raw is not None:
            return str(bc_raw)
        return None
