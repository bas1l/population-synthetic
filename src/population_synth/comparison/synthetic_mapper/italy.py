"""Italian synthetic-population mapper (ISTAT schema).

Implements the Italian arm of every country-divergent attribute.  Calls the
Italian normalizers and ``_IT`` label sets.  Italy has no income_source,
ethnicity, or environment attributes in the pipeline, and the narrative/batch
format is not supported.
"""

from __future__ import annotations

from typing import Any

from population_synth.comparison.extract.mappings import _json_lookup_it
from population_synth.comparison.extract.normalizers_it import (
    _normalize_birth_location_it,
    _normalize_civil_status_it,
    _normalize_education_it,
    _normalize_employment_it,
    _normalize_housing_tenure_it,
)
from population_synth.comparison.extract.normalizers_se import _fuzzy_match
from population_synth.comparison.extract.schema_labels import (
    _CITY_TO_REGION_IT,
    EMPLOYMENT_TYPE_LABELS_IT,
    HOUSEHOLD_SIZE_LABELS_IT,
    INDUSTRY_SECTOR_LABELS_IT,
    REGION_LABELS_IT,
)
from population_synth.comparison.synthetic_mapper.base import (
    _EUROPEAN_COUNTRIES,
    _NON_EUROPEAN_COUNTRIES,
    BaseSyntheticMapper,
    match_common_sex,
)


def _birth_location_from_flat_it(raw: str) -> str:
    """Map flat birth_location (city name or country) to Italian schema category."""
    raw_lower = raw.lower().strip()
    if any(k in raw_lower for k in ("domestic", "italy", "italia", "nato in italia", "italian")):
        return "Italy"
    if raw_lower in _CITY_TO_REGION_IT:
        return "Italy"
    if any(c.lower() == raw_lower for c in REGION_LABELS_IT):
        return "Italy"
    if any(k in raw_lower for k in _NON_EUROPEAN_COUNTRIES):
        return "Outside Europe"
    if any(k in raw_lower for k in _EUROPEAN_COUNTRIES):
        return "Europe (Other)"
    result = _normalize_birth_location_it(raw)
    if result:
        return result
    return "Non-standard label"


class ItalianSyntheticMapper(BaseSyntheticMapper):
    """Maps Italian (ISTAT) pipeline identities to the canonical schema."""

    SILENT_UNMAPPED = {"ethnicity", "current_environment_type"}

    def map_biological_sex(self, raw: str, unmapped: list[str]) -> str:
        sex_lower = raw.lower().strip()
        result = match_common_sex(sex_lower)
        if result is None and any(k in sex_lower for k in ("femmina", "femminile", "donna")):
            result = "Female"
        elif result is None and any(k in sex_lower for k in ("maschio", "maschile", "uomo")):
            result = "Male"
        if result is None:
            unmapped.append(f"biological_sex={raw!r}")
            return "Non-standard label"
        return result

    def map_education(self, raw: str, unmapped: list[str]) -> str:
        value = _normalize_education_it(raw) or "Non-standard label"
        if value == "Non-standard label":
            unmapped.append(f"education_level={raw!r}")
        return value

    def map_employment_status(self, raw: str, unmapped: list[str]) -> str:
        value = _normalize_employment_it(raw) or "Non-standard label"
        if value == "Non-standard label":
            unmapped.append(f"employment_status={raw!r}")
        return value

    def map_birth_location(self, identity: dict, unmapped: list[str]) -> str:
        raw_birth = str(identity.get("birth_location") or "")
        birth_location = _birth_location_from_flat_it(raw_birth) if raw_birth else "Non-standard label"
        bcd_normalized = str(identity.get("birth_country_detail") or "")
        bcd_lower = bcd_normalized.lower()
        if any(k in bcd_lower for k in ("italy", "italia", "italiana")):
            birth_location = "Italy"
        elif birth_location == "Non-standard label" and bcd_normalized:
            if any(k in bcd_lower for k in _EUROPEAN_COUNTRIES):
                birth_location = "Europe (Other)"
            elif any(k in bcd_lower for k in _NON_EUROPEAN_COUNTRIES):
                birth_location = "Outside Europe"
        if birth_location == "Non-standard label":
            unmapped.append(f"birth_location={raw_birth!r}")
        return birth_location

    def map_region(self, identity: dict) -> str:
        region = str(identity.get("region") or "Non-standard label")
        if region not in REGION_LABELS_IT:
            region = (_json_lookup_it("region", region)
                      or _fuzzy_match(region, REGION_LABELS_IT)
                      or "Non-standard label")
            # Attempt city-to-region lookup for Italian cities
            if region == "Non-standard label":
                region = _CITY_TO_REGION_IT.get(str(identity.get("region") or "").lower().strip(),
                                                "Non-standard label")
        return region

    def map_birth_country_detail(self, raw: str) -> str:
        if raw:
            bcd_lower = raw.lower()
            if any(k in bcd_lower for k in ("italy", "italia", "italiana")):
                return "Italy"
            js_bcd = _json_lookup_it("birth_country_detail", raw)
            return js_bcd if js_bcd is not None else raw
        return "Non-standard label"

    def map_civil_status(self, raw: str, unmapped: list[str]) -> str:
        return _normalize_civil_status_it(raw)

    def map_household_size(self, raw: Any) -> str:
        if isinstance(raw, int):
            if raw >= 6:
                return "GE6"
            return str(raw)
        if isinstance(raw, str) and raw in HOUSEHOLD_SIZE_LABELS_IT:
            return raw
        return _fuzzy_match(str(raw or ""), HOUSEHOLD_SIZE_LABELS_IT) or "Non-standard label"

    def map_housing_tenure(self, raw: str, unmapped: list[str]) -> str:
        return _normalize_housing_tenure_it(raw) if raw else "Non-standard label"

    def map_industry_sector(self, raw: str) -> str:
        if raw in INDUSTRY_SECTOR_LABELS_IT:
            return raw
        js_ind_it = _json_lookup_it("industry_sector", raw)
        if js_ind_it is not None:
            return js_ind_it
        return _fuzzy_match(raw, INDUSTRY_SECTOR_LABELS_IT) or "Not Applicable"

    def map_employment_type(self, raw: str, unmapped: list[str]) -> str:
        # Italian pipe-separated format passes through directly
        if raw in EMPLOYMENT_TYPE_LABELS_IT:
            return raw
        if "|" in raw:
            return raw
        js_et_it = _json_lookup_it("employment_type", raw)
        if js_et_it is not None:
            return js_et_it
        if not raw or raw.lower() in ("not applicable", "n/a", "non applicabile"):
            return "Not Applicable"
        return _fuzzy_match(raw, EMPLOYMENT_TYPE_LABELS_IT) or "Not Applicable"

    def map_income_source(self, raw: str) -> str:
        # Italy does not have income_source in the pipeline
        return raw if raw else "Non-standard label"

    def parse_narrative(self, identity: dict, persona_id: str) -> dict[str, Any] | None:
        raise NotImplementedError("Italian narrative (batch) identity format is not supported")
