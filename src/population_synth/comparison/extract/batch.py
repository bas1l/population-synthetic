"""Batch (free-text narrative) identity extractor.

``_extract_batch`` turns a single ``narrative`` blob into the canonical
demographic attribute dict, combining bullet-template fields, prose inference,
and the Swedish normalizers, with coherence-driven fallbacks for household
size, parental structure, and socioeconomic class.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from population_synth.comparison.extract.normalizers_se import (
    _age_to_group,
    _fuzzy_match,
    _normalize_birth_country_detail,
    _normalize_birth_location,
    _normalize_civil_status,
    _normalize_education,
    _normalize_employment,
    _normalize_employment_type,
    _normalize_environment,
    _normalize_ethnicity,
    _normalize_housing_tenure,
    _normalize_income_source,
    _normalize_industry_sector,
    _normalize_parental_structure,
    _normalize_socioeconomic,
)
from population_synth.comparison.extract.prose_inference import (
    _education_from_occupation,
    _employment_type_from_prose,
    _extract_city_from_location,
    _income_source_from_context,
    _industry_from_occupation,
    _parse_template_fields,
)
from population_synth.comparison.extract.schema_labels import (
    _CITY_TO_COUNTY,
    _LARGE_CITIES,
    _METRO_CITIES,
    BIRTH_COUNTRY_DETAIL_LABELS,
    BIRTH_LOCATION_LABELS,
    CIVIL_STATUS_LABELS,
    EDUCATION_LABELS,
    EMPLOYMENT_LABELS,
    ENVIRONMENT_LABELS,
    ETHNICITY_LABELS,
    HOUSEHOLD_SIZE_LABELS,
    HOUSING_TENURE_LABELS,
    INDUSTRY_SECTOR_LABELS,
    PARENTAL_STRUCTURE_LABELS,
    REGION_LABELS,
    SOCIOECONOMIC_LABELS,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Batch format extractor (narrative text)
# ---------------------------------------------------------------------------

_AGE_RE = re.compile(
    r"\b(\d{1,3})[- ]?year[s]?[- ]?old\b"
    r"|\bage[d]?\s+(\d{1,3})\b"
    r"|\b(\d{1,3})-årig\b",
    re.IGNORECASE,
)


def _extract_batch(identity: dict, persona_id: str) -> dict[str, Any] | None:
    """Extract attributes from the batch identity.json format (free-text narrative)."""
    text = identity.get("narrative", "")
    if not text:
        logger.warning("%s: batch identity has empty narrative -- skipping", persona_id)
        return None

    text_lower = text.lower()
    unmapped: list[str] = []
    template = _parse_template_fields(text)

    tpl: dict[str, str] = {}

    def _accept(attr: str, value: Any, valid: set[str] | None) -> None:
        if value is None:
            return
        sv = str(value).strip()
        if not sv:
            return
        if valid is None or sv in valid:
            tpl[attr] = sv

    _civil_valid = {"Single/Never Married", "Married", "Divorced", "Widowed"}
    _housing_valid = set(HOUSING_TENURE_LABELS)
    _household_valid = set(HOUSEHOLD_SIZE_LABELS)
    _parental_valid = set(PARENTAL_STRUCTURE_LABELS)
    _education_valid = set(EDUCATION_LABELS)
    _employment_status_valid = set(EMPLOYMENT_LABELS)
    _birth_location_valid = set(BIRTH_LOCATION_LABELS)
    _ethnicity_valid = set(ETHNICITY_LABELS)
    _environment_valid = set(ENVIRONMENT_LABELS)
    _socio_valid = set(SOCIOECONOMIC_LABELS)
    _region_valid = set(REGION_LABELS)

    if (r := template.get("civil_status")):
        _accept("civil_status", _normalize_civil_status(r), _civil_valid)
    if (r := template.get("housing_tenure")):
        _accept("housing_tenure", _fuzzy_match(r, HOUSING_TENURE_LABELS), _housing_valid)
    if (r := template.get("household_size")):
        _accept("household_size", _fuzzy_match(r, HOUSEHOLD_SIZE_LABELS), _household_valid)
    if (r := template.get("parental_structure")):
        _accept("parental_structure", _normalize_parental_structure(r), _parental_valid)
    if (r := template.get("education_level")):
        _accept("education_level", _normalize_education(r), _education_valid)
    if (r := template.get("employment_status")):
        _accept("employment_status", _normalize_employment(r), _employment_status_valid)
    if (r := template.get("birth_location")):
        _accept("birth_location", _normalize_birth_location(r), _birth_location_valid)
    if (r := template.get("birth_country_detail")):
        _accept("birth_country_detail", _normalize_birth_country_detail(r),
                set(BIRTH_COUNTRY_DETAIL_LABELS))
    if (r := template.get("ethnicity")):
        _accept("ethnicity", _normalize_ethnicity(r), _ethnicity_valid)
    if (r := template.get("current_environment_type")):
        _accept("current_environment_type", _normalize_environment(r), _environment_valid)
    if (r := template.get("socioeconomic_class")):
        _accept("socioeconomic_class", _normalize_socioeconomic(r), _socio_valid)
    if (r := template.get("industry_sector")):
        _accept("industry_sector", _normalize_industry_sector(r), None)
    if (r := template.get("employment_type")):
        _accept("employment_type", _normalize_employment_type(r), None)
    if (r := template.get("income_source")):
        _accept("income_source", _normalize_income_source(r), None)
    if (r := template.get("region")):
        if r in REGION_LABELS:
            _accept("region", r, _region_valid)
        else:
            _accept("region", _fuzzy_match(r, REGION_LABELS), _region_valid)

    # --- Age ---
    age_group = "Non-standard label"
    if "age" in template:
        try:
            age_group = _age_to_group(int(template["age"]))
        except ValueError:
            pass
    if age_group == "Non-standard label":
        m = _AGE_RE.search(text)
        if m:
            raw_age = int(next(g for g in m.groups() if g is not None))
            age_group = _age_to_group(raw_age)
    if age_group == "Non-standard label":
        unmapped.append("age=<not found>")

    # --- Biological sex ---
    biological_sex = "Non-standard label"
    if "gender" in template:
        g = template["gender"].strip().lower()
        if g in ("kvinna", "female", "flicka", "tjej", "f"):
            biological_sex = "Female"
        elif g in ("man", "male", "pojke", "kille", "m"):
            biological_sex = "Male"
    if biological_sex == "Non-standard label":
        if any(k in text_lower for k in ("female", "woman", "she/her", "kvinna", " hon ", "flicka")):
            biological_sex = "Female"
        elif any(k in text_lower for k in (" male", " man ", "he/him", " han ", "pojke")):
            biological_sex = "Male"
    if biological_sex == "Non-standard label":
        unmapped.append("biological_sex=<not found>")

    # --- Region ---
    region = tpl.get("region", "Non-standard label")
    city_name: str | None = None
    if region != "Non-standard label":
        pass
    elif "location" in template:
        city_name = _extract_city_from_location(template["location"])
        if city_name:
            region = _CITY_TO_COUNTY.get(city_name.lower(), "Non-standard label")
        if region == "Non-standard label":
            loc_lower = template["location"].lower()
            for county in REGION_LABELS:
                if county.lower() in loc_lower:
                    region = county
                    break
    if region == "Non-standard label":
        for candidate in REGION_LABELS:
            if candidate.lower() in text_lower:
                region = candidate
                break
    if region == "Non-standard label":
        for c_name, county in _CITY_TO_COUNTY.items():
            if c_name in text_lower:
                region = county
                city_name = city_name or c_name
                break
    if region == "Non-standard label":
        unmapped.append("region=<not found>")

    # --- Current environment type ---
    current_environment_type = tpl.get("current_environment_type", "Non-standard label")
    if current_environment_type != "Non-standard label":
        pass
    elif city_name:
        cl = city_name.lower()
        if cl in _METRO_CITIES:
            current_environment_type = "Urban Metropolis"
        elif cl in _LARGE_CITIES:
            current_environment_type = "Suburban"
        elif cl in _CITY_TO_COUNTY:
            current_environment_type = "Rural/Countryside"
    if current_environment_type == "Non-standard label":
        current_environment_type = _normalize_environment(text) or "Non-standard label"
    if current_environment_type == "Non-standard label":
        unmapped.append("current_environment_type=<not found>")

    # --- Employment status ---
    employment_status = tpl.get("employment_status", "Non-standard label")
    if employment_status != "Non-standard label":
        pass
    elif "occupation" in template:
        occ_lower = template["occupation"].lower()
        if any(k in occ_lower for k in ("student", "studerande")):
            employment_status = "Student"
        elif any(k in occ_lower for k in ("pensionär", "pensionerad", "retired")):
            employment_status = "Retired"
        elif any(k in occ_lower for k in ("arbetslös", "unemployed", "arbetssökande")):
            employment_status = "Unemployed"
        else:
            employment_status = "Employed"
    if employment_status == "Non-standard label":
        employment_status = _normalize_employment(text) or "Non-standard label"
    if employment_status == "Non-standard label":
        if any(k in text_lower for k in ("arbetar", "anställd", "anställning", "tjänst")):
            employment_status = "Employed"
        elif any(k in text_lower for k in ("arbetslös", "arbetssökande")):
            employment_status = "Unemployed"
        elif any(k in text_lower for k in ("studerande", "studerar")):
            employment_status = "Student"
        elif any(k in text_lower for k in ("pensionär", "pensionerad")):
            employment_status = "Retired"
    if employment_status == "Non-standard label":
        unmapped.append("employment_status=<not found>")

    # --- Education level ---
    education_level = tpl.get("education_level", "Non-standard label")
    if education_level != "Non-standard label":
        pass
    elif "occupation" in template:
        education_level = _education_from_occupation(template["occupation"]) or "Non-standard label"
    if education_level == "Non-standard label":
        if any(k in text_lower for k in ("doktorsexamen", "ph.d", "phd", "doctoral degree", "research degree")):
            education_level = "Post-Graduate (ISCED 6)"
        elif any(k in text_lower for k in (
            "university", "universitet", "högskola", "hogskola",
            "bachelor", "master", "kandidatexamen", "magisterexamen",
            "masterexamen", "universitetsutbildning", "högskoleutbildning", "akademisk",
        )):
            education_level = "Post-Secondary 3+ yrs (ISCED 5A)"
        elif any(k in text_lower for k in ("vocational", "yrkeshögskola", "yrkeshogskola", "yrkes", "yh-")):
            education_level = "Post-Secondary < 3 yrs (ISCED 4+5B)"
        elif any(k in text_lower for k in ("gymnasium", "gymnasieskola", "high school", "gymnasie")):
            education_level = "Upper Secondary 3 yrs (ISCED 3A)"
        elif any(k in text_lower for k in ("grundskola", "folkskola", "primary school", "compulsory school")):
            education_level = "Pre-Secondary 9-10 yrs (ISCED 2)"
        elif any(k in text_lower for k in ("no formal", "ingen utbildning")):
            education_level = "Pre-Secondary < 9 yrs (ISCED 1)"
    if education_level == "Non-standard label":
        education_level = _normalize_education(text) or "Non-standard label"
    if education_level == "Non-standard label":
        unmapped.append("education_level=<not found>")

    # --- Industry sector ---
    industry_sector = tpl.get("industry_sector", "Non-standard label")
    if industry_sector != "Non-standard label":
        pass
    elif "occupation" in template:
        raw_industry = _industry_from_occupation(template["occupation"])
        if raw_industry:
            industry_sector = _normalize_industry_sector(raw_industry)
    if industry_sector == "Non-standard label":
        for candidate in INDUSTRY_SECTOR_LABELS:
            if candidate.lower() in text_lower:
                industry_sector = _normalize_industry_sector(candidate)
                break
    if industry_sector == "Non-standard label" and employment_status in ("Student", "Retired", "Unemployed"):
        industry_sector = "Not Applicable"
    if industry_sector == "Non-standard label":
        unmapped.append("industry_sector=<not found>")

    # --- Shared indicators ---
    has_children = any(k in text_lower for k in ("children", "barn", " son ", " sons ", "daughter", "dotter"))
    lives_alone = any(k in text_lower for k in ("lives alone", "bor ensam", "bor själv"))
    has_partner = any(k in text_lower for k in (
        "sambo", "partner", "wife", "husband", "fru", " make ", " makes ",
    ))

    # --- Civil status ---
    civil_status = tpl.get("civil_status", "Non-standard label")
    if civil_status != "Non-standard label":
        pass
    elif any(k in text_lower for k in ("divorced", "divorce", "skild", "frånskild", "separated", "separerad")):
        civil_status = "Divorced"
    elif any(k in text_lower for k in (" gift ", " gift,", " gift.", "married")):
        civil_status = "Married"
    elif any(k in text_lower for k in ("sambo", "cohabiting", "live-in partner", "sammanboende", "särbo")):
        civil_status = "Married"
    elif any(k in text_lower for k in ("änka", "änkling", "widow")):
        civil_status = "Widowed"
    elif any(k in text_lower for k in ("singel", "single", "ogift", "ensamstående", "unmarried",
                                        "ended a relationship", "ended her relationship",
                                        "ended his relationship", "ended a cohabitation")):
        civil_status = "Single/Never Married"
    elif lives_alone and not has_children and not has_partner:
        civil_status = "Single/Never Married"
    if civil_status == "Non-standard label":
        for candidate in CIVIL_STATUS_LABELS:
            if candidate.lower() in text_lower:
                civil_status = _normalize_civil_status(candidate)
                break
    if civil_status == "Non-standard label":
        unmapped.append("civil_status=<not found>")

    # --- Housing tenure ---
    housing_tenure = tpl.get("housing_tenure", "Non-standard label")
    if housing_tenure != "Non-standard label":
        pass
    elif any(k in text_lower for k in ("hyresrätt", "hyreslägenhet", "rental apartment", "rented apartment", "rented")):
        housing_tenure = "Rental apartment"
    elif any(k in text_lower for k in ("bostadsrätt", "bostadsrätts", "condominium", "tenant-owned")):
        housing_tenure = "Tenant-owned apartment (bostadsrätt)"
    elif any(k in text_lower for k in ("villa", "radhus", "house", "detached", "owner-occupied", "owns a home")):
        housing_tenure = "Owner-occupied (villa/house)"
    if housing_tenure == "Non-standard label":
        for candidate in HOUSING_TENURE_LABELS:
            if candidate.lower() in text_lower:
                housing_tenure = _normalize_housing_tenure(candidate)
                break
    if housing_tenure == "Non-standard label":
        unmapped.append("housing_tenure=<not found>")

    # --- Birth location ---
    birth_location = tpl.get("birth_location", "Non-standard label")
    if birth_location != "Non-standard label":
        pass
    elif any(k in text_lower for k in ("born in sweden", "född i sverige")):
        birth_location = "Sweden"
    elif any(k in text_lower for k in ("immigrant", "invandrat", "flykting", "refugee",
                                        "moved to sweden", "flyttade till sverige",
                                        "bakgrund från", "ursprung")):
        birth_location = _normalize_birth_location(text) or "Non-standard label"
    else:
        birth_location = "Sweden"
    if birth_location == "Non-standard label":
        unmapped.append("birth_location=<not found>")

    # --- Birth country detail ---
    birth_country_detail = tpl.get("birth_country_detail", "Non-standard label")
    if birth_country_detail != "Non-standard label":
        pass
    elif birth_location == "Sweden":
        birth_country_detail = "Sweden"
    else:
        for candidate in BIRTH_COUNTRY_DETAIL_LABELS:
            if candidate.lower() in text_lower:
                birth_country_detail = _normalize_birth_country_detail(candidate)
                break
    if birth_country_detail == "Non-standard label":
        unmapped.append("birth_country_detail=<not found>")

    # --- Ethnicity ---
    ethnicity = tpl.get("ethnicity") or _normalize_ethnicity(text)
    if ethnicity is None:
        eth_from_birth = {
            "Sweden": "Swedish",
            "Nordic Country": "European",
            "Europe (Other)": "European",
            "Outside Europe": "Non-European",
        }
        ethnicity = eth_from_birth.get(birth_location, "Non-standard label")
    if ethnicity == "Non-standard label":
        unmapped.append("ethnicity=<not found>")

    # --- Household size ---
    household_size = tpl.get("household_size", "Non-standard label")
    if civil_status == "Married":
        has_partner = True

    child_count = 0
    for pat, n in [("four children", 4), ("fyra barn", 4), ("4 children", 4),
                   ("three children", 3), ("tre barn", 3), ("3 children", 3),
                   ("two children", 2), ("två barn", 2), ("2 children", 2),
                   ("one child", 1), ("ett barn", 1), ("a child", 1), ("1 child", 1)]:
        if pat in text_lower:
            child_count = max(child_count, n)
            break

    if household_size != "Non-standard label":
        pass
    elif lives_alone and not has_children:
        household_size = "1 person"
    elif has_partner and has_children:
        total = 2 + max(child_count, 1)
        if total >= 7:
            household_size = "7+ persons"
        elif total == 6:
            household_size = "6 persons"
        elif total == 5:
            household_size = "5 persons"
        elif total == 4:
            household_size = "4 persons"
        else:
            household_size = "3 persons"
    elif has_partner and not has_children:
        household_size = "2 persons"
    elif has_children and not has_partner:
        total = 1 + max(child_count, 1)
        if total >= 7:
            household_size = "7+ persons"
        elif total == 6:
            household_size = "6 persons"
        elif total == 5:
            household_size = "5 persons"
        elif total == 4:
            household_size = "4 persons"
        elif total == 3:
            household_size = "3 persons"
        else:
            household_size = "2 persons"
    elif lives_alone or civil_status == "Single/Never Married":
        household_size = "1 person"
    if household_size == "Non-standard label":
        unmapped.append("household_size=<not found>")

    # --- Socioeconomic class ---
    socioeconomic_class = tpl.get("socioeconomic_class", "Non-standard label")
    if socioeconomic_class != "Non-standard label":
        pass
    elif any(k in text_lower for k in ("financial strain", "ekonomiska svårigheter", "economic hardship",
                                      "tight budget", "skulder", "debt")):
        socioeconomic_class = "Working Class"
    elif education_level in ("Post-Secondary 3+ yrs (ISCED 5A)", "Post-Graduate (ISCED 6)"):
        socioeconomic_class = "Middle Class"
    elif education_level in ("Pre-Secondary < 9 yrs (ISCED 1)", "Pre-Secondary 9-10 yrs (ISCED 2)",
                             "Upper Secondary ≤ 2 yrs (ISCED 3C)", "Upper Secondary 3 yrs (ISCED 3A)",
                             "Post-Secondary < 3 yrs (ISCED 4+5B)"):
        socioeconomic_class = "Working Class"
    elif employment_status == "Retired":
        socioeconomic_class = "Middle Class"
    elif employment_status == "Employed":
        socioeconomic_class = "Middle Class"
    else:
        socioeconomic_class = _normalize_socioeconomic(text) or "Working Class"
    if socioeconomic_class == "Non-standard label":
        unmapped.append("socioeconomic_class=<not found>")

    # --- Parental structure ---
    parental_structure = tpl.get("parental_structure", "Non-standard label")
    if parental_structure != "Non-standard label":
        pass
    elif any(k in text_lower for k in ("single mother", "single father", "ensamstående med barn",
                                      "ensamstående mamma", "ensamstående pappa",
                                      "solo parent", "ensam vårdnad")):
        parental_structure = "Single Parent"
    elif civil_status == "Divorced" and has_children:
        parental_structure = "Single Parent"
    elif civil_status == "Married" and has_children:
        parental_structure = "Nuclear Family"
    elif civil_status == "Married" and not has_children:
        parental_structure = "Couple without Children"
    elif has_children:
        parental_structure = "Single Parent"
    elif lives_alone or civil_status == "Single/Never Married":
        parental_structure = "Living Alone"
    if parental_structure == "Non-standard label":
        parental_structure = _normalize_parental_structure(text) or "Non-standard label"
    if parental_structure == "Non-standard label":
        unmapped.append("parental_structure=<not found>")

    # --- Employment type ---
    employment_type = tpl.get("employment_type") or _normalize_employment_type(
        _employment_type_from_prose(text_lower, employment_status)
    )

    # --- Income source ---
    income_source = tpl.get("income_source") or _normalize_income_source(
        _income_source_from_context(employment_status, text_lower)
    )

    if unmapped:
        logger.warning("%s: unmapped values (batch): %s", persona_id, ", ".join(unmapped))

    return {
        "age_group": age_group,
        "biological_sex": biological_sex,
        "education_level": education_level,
        "employment_status": employment_status,
        "birth_location": birth_location,
        "ethnicity": ethnicity,
        "current_environment_type": current_environment_type,
        "socioeconomic_class": socioeconomic_class,
        "parental_structure": parental_structure,
        "region": region,
        "birth_country_detail": birth_country_detail,
        "civil_status": civil_status,
        "household_size": household_size,
        "housing_tenure": housing_tenure,
        "industry_sector": industry_sector,
        "employment_type": employment_type,
        "income_source": income_source,
    }
