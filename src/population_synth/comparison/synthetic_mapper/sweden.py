"""Swedish synthetic-population mapper (SCB schema).

Implements the Swedish arm of every country-divergent attribute and the
narrative/batch parsing path.  Calls the Swedish normalizers and label sets.
"""

from __future__ import annotations

from typing import Any

from population_synth.comparison.extract.batch import _extract_batch
from population_synth.comparison.extract.mappings import _json_lookup
from population_synth.comparison.extract.normalizers_se import (
    _fuzzy_match,
    _normalize_birth_country_detail,
    _normalize_birth_location,
    _normalize_civil_status,
    _normalize_education,
    _normalize_employment,
    _normalize_employment_type,
    _normalize_income_source,
    _normalize_industry_sector,
)
from population_synth.comparison.extract.schema_labels import (
    _CITY_TO_COUNTY,
    _CIVIL_STATUS_OUTPUT,
    _EMPLOYMENT_TYPE_OUTPUT,
    HOUSEHOLD_SIZE_LABELS,
    HOUSING_TENURE_LABELS,
    INCOME_SOURCE_LABELS,
    INDUSTRY_SECTOR_LABELS,
    REGION_LABELS,
)
from population_synth.comparison.synthetic_mapper.base import (
    _EUROPEAN_COUNTRIES,
    _NON_EUROPEAN_COUNTRIES,
    BaseSyntheticMapper,
    match_common_sex,
)


def _birth_location_from_flat(raw: str) -> str:
    """Map flat birth_location (city name or country) to schema category."""
    raw_lower = raw.lower().strip()
    stripped = raw_lower.removesuffix(" kommun").removesuffix(" stad").strip()
    if (stripped in _CITY_TO_COUNTY
            or raw_lower in _CITY_TO_COUNTY
            or any(c.lower() == raw_lower for c in REGION_LABELS)):
        return "Sweden"
    if any(c.lower() in raw_lower for c in REGION_LABELS) or stripped in _CITY_TO_COUNTY:
        return "Sweden"
    if any(k in raw_lower for k in _NON_EUROPEAN_COUNTRIES):
        return "Outside Europe"
    if any(k in raw_lower for k in _EUROPEAN_COUNTRIES):
        return "Europe (Other)"
    result = _normalize_birth_location(raw)
    if result:
        return result
    if "sweden" in raw_lower or "sverige" in raw_lower:
        return "Sweden"
    return "Non-standard label"


class SwedishSyntheticMapper(BaseSyntheticMapper):
    """Maps Swedish (SCB) pipeline identities to the canonical schema."""

    def map_biological_sex(self, raw: str, unmapped: list[str]) -> str:
        sex_lower = raw.lower().strip()
        result = match_common_sex(sex_lower)
        if result is None:
            unmapped.append(f"biological_sex={raw!r}")
            return "Non-standard label"
        return result

    def map_education(self, raw: str, unmapped: list[str]) -> str:
        value = _normalize_education(raw) or "Non-standard label"
        if value == "Non-standard label":
            unmapped.append(f"education_level={raw!r}")
        return value

    def map_employment_status(self, raw: str, unmapped: list[str]) -> str:
        value = _normalize_employment(raw) or "Non-standard label"
        if value == "Non-standard label":
            unmapped.append(f"employment_status={raw!r}")
        return value

    def map_birth_location(self, identity: dict, unmapped: list[str]) -> str:
        raw_birth = str(identity.get("birth_location") or "")
        birth_location = _birth_location_from_flat(raw_birth) if raw_birth else "Non-standard label"
        raw_bcd_for_loc = str(identity.get("birth_country_detail") or "")
        bcd_normalized = _normalize_birth_country_detail(raw_bcd_for_loc) if raw_bcd_for_loc else ""
        if bcd_normalized == "Sweden":
            birth_location = "Sweden"
        elif birth_location == "Non-standard label" and bcd_normalized:
            nordic = {"Norway", "Denmark", "Finland"}
            european = {"Poland", "Germany", "United Kingdom", "Ukraine", "Romania",
                        "Bosnia and Herzegovina", "Yugoslavia"}
            if bcd_normalized in nordic:
                birth_location = "Europe (Other)"
            elif bcd_normalized in european:
                birth_location = "Europe (Other)"
            else:
                birth_location = "Outside Europe"
        if birth_location == "Non-standard label":
            unmapped.append(f"birth_location={raw_birth!r}")
        return birth_location

    def map_region(self, identity: dict) -> str:
        region = str(identity.get("region") or "Non-standard label")
        if region not in REGION_LABELS:
            region = _json_lookup("region", region) or _fuzzy_match(region, REGION_LABELS) or "Non-standard label"
        return region

    def map_birth_country_detail(self, raw: str) -> str:
        return _normalize_birth_country_detail(raw) if raw else "Non-standard label"

    def map_civil_status(self, raw: str, unmapped: list[str]) -> str:
        civil_status = _normalize_civil_status(raw)
        if civil_status not in _CIVIL_STATUS_OUTPUT:
            unmapped.append(f"civil_status={raw!r}")
            civil_status = "Non-standard label"
        return civil_status

    def map_household_size(self, raw: Any) -> str:
        if isinstance(raw, int):
            if raw == 1:
                return "1 person"
            if raw == 2:
                return "2 persons"
            if raw == 3:
                return "3 persons"
            if raw == 4:
                return "4 persons"
            if raw == 5:
                return "5 persons"
            if raw == 6:
                return "6 persons"
            return "7+ persons"
        return _fuzzy_match(str(raw or ""), HOUSEHOLD_SIZE_LABELS) or "Non-standard label"

    def map_housing_tenure(self, raw: str, unmapped: list[str]) -> str:
        js_ht = _json_lookup("housing_tenure", raw)
        if js_ht is not None:
            housing_tenure = js_ht
        else:
            ht_lower = raw.lower()
            if any(k in ht_lower for k in (
                "bostadsrätt", "bostadsratt", "cooperative", "co-op", "tenant-owned",
                "condominium", "bostadsbolag", "bostadsförening",
            )):
                housing_tenure = "Tenant-owned apartment (bostadsrätt)"
            elif any(k in ht_lower for k in (
                "villa", "radhus", "friköpt", "äganderätt", "owner", "house", "detached",
                "egendom", "eget h", "egen bostad", "egna bostad", "egen hemma", "egenhemma",
                "own home", "owning", "owned", "mortgage", "freehold",
            )):
                housing_tenure = "Owner-occupied (villa/house)"
            elif any(k in ht_lower for k in (
                "rental", "rent", "hyresrätt", "hyres", "hyra", "uthyr", "studentbostad",
                "student", "shared apartment", "shared student", "social housing",
            )):
                housing_tenure = "Rental apartment"
            else:
                housing_tenure = _fuzzy_match(raw, HOUSING_TENURE_LABELS) or "Non-standard label"
        if housing_tenure == "Non-standard label" and raw:
            unmapped.append(f"housing_tenure={raw!r}")
        return housing_tenure

    def map_industry_sector(self, raw: str) -> str:
        js_ind = _json_lookup("industry_sector", raw)
        if js_ind is not None:
            return js_ind
        ind_lower = raw.lower()
        if any(k in ind_lower for k in ("vård", "sjukvård", "omsorg", "healthcare")):
            return _normalize_industry_sector("Healthcare/Social Work")
        if any(k in ind_lower for k in ("finansiell", "bank", "finans")):
            return _normalize_industry_sector("IT/Technology")
        if any(k in ind_lower for k in ("detaljhandel", "handel")):
            return _normalize_industry_sector("Retail & Service")
        if any(k in ind_lower for k in ("utbildning", "forskning")):
            return _normalize_industry_sector("Education")
        if "offentlig förvaltning" in ind_lower:
            return _normalize_industry_sector("Public Administration/Defense")
        if any(k in ind_lower for k in ("teknik", " it", "information")):
            return _normalize_industry_sector("IT/Technology")
        if any(k in ind_lower for k in ("kultur", "kreativ")):
            return _normalize_industry_sector("Other Services")
        if any(k in ind_lower for k in ("bygg", "construction", "tillverkning", "industri")):
            return _normalize_industry_sector("Manufacturing/Industry")
        if raw in INDUSTRY_SECTOR_LABELS:
            return _normalize_industry_sector(raw)
        return _normalize_industry_sector(_fuzzy_match(raw, INDUSTRY_SECTOR_LABELS) or "Non-standard label")

    def map_employment_type(self, raw: str, unmapped: list[str]) -> str:
        js_et = _json_lookup("employment_type", raw)
        if js_et is not None:
            employment_type = js_et
        else:
            et_lower = raw.lower().replace("_", " ")
            _NA = ("not applicable", "n/a", "ej tillämpligt",
                   "ej relevant", "ingen anställning", "volontär", "arbetsträning")
            _SELF = ("self-employed", "freelance", "egenföretagare",
                     "enskild firma", "konsultanställning", "egenanställd", "aktiebolag")
            _TEMP_MISC = ("projektanställning", "visstidsanställning",
                          "provanställning", "praktik", "vikarie", "pensionsåldern")
            _PERM = ("permanent", "tillsvidare")
            _TEMP = ("temporary", "tillfällig", "visstid")
            if any(k in et_lower for k in _NA):
                employment_type = "Not Applicable"
            elif any(k in et_lower for k in _SELF):
                employment_type = "Self-Employed"
            elif any(k in et_lower for k in _TEMP_MISC):
                employment_type = "Temporary Full-time"
            elif (any(k in et_lower for k in _PERM)
                  and any(k in et_lower for k in ("full", "heltid"))):
                employment_type = "Permanent Full-time"
            elif (any(k in et_lower for k in _PERM)
                  and any(k in et_lower for k in ("part", "deltid"))):
                employment_type = "Permanent Part-time"
            elif (any(k in et_lower for k in _TEMP)
                  and any(k in et_lower for k in ("full", "heltid"))):
                employment_type = "Temporary Full-time"
            elif (any(k in et_lower for k in _TEMP)
                  and any(k in et_lower for k in ("part", "deltid"))):
                employment_type = "Temporary Part-time"
            elif "tillsvidareanställning" in et_lower or "heltidsanställning" in et_lower:
                employment_type = "Permanent Full-time"
            else:
                employment_type = _normalize_employment_type(raw)
        # Occupation titles / vague tokens that no rule resolved leak through as raw
        # strings; count them as unmapped instead of letting them pose as categories.
        if employment_type not in _EMPLOYMENT_TYPE_OUTPUT:
            unmapped.append(f"employment_type={raw!r}")
            employment_type = "Non-standard label"
        return employment_type

    def map_income_source(self, raw: str) -> str:
        income_source = _normalize_income_source(raw) if raw else "Wage / Business"
        if income_source not in INCOME_SOURCE_LABELS:
            income_source = _normalize_income_source(
                _fuzzy_match(raw, INCOME_SOURCE_LABELS) or "Wage / Business"
            )
        return income_source

    def parse_narrative(self, identity: dict, persona_id: str) -> dict[str, Any] | None:
        return _extract_batch(identity, persona_id)
