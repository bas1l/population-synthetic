"""Prose / template inference helpers for the batch narrative format.

Parses bullet-template fields out of free-text narratives and infers
demographic attributes from prose context: city from a location string,
industry / education from an occupation title, and employment-type / income
source from the surrounding narrative text plus the resolved employment status.
"""

from __future__ import annotations

from population_synth.comparison.extract.schema_labels import (
    _BULLET_LINE_RE,
    _OCCUPATION_TO_INDUSTRY,
    _TEMPLATE_LABEL_ALIASES,
    _UNIVERSITY_OCCUPATIONS,
)


def _parse_template_fields(text: str) -> dict[str, str]:
    """Parse bullet lines ``- Label: value`` into a dict keyed by canonical attribute name."""
    fields: dict[str, str] = {}
    for m in _BULLET_LINE_RE.finditer(text):
        label_raw = m.group("label").strip().lower()
        value = m.group("value").strip()
        if not value:
            continue
        if value.startswith("(Paragraph") or value.startswith("(paragraph"):
            continue
        key = _TEMPLATE_LABEL_ALIASES.get(label_raw)
        if key and key not in fields:
            fields[key] = value
    return fields


def _extract_city_from_location(location_raw: str) -> str | None:
    if not location_raw:
        return None
    city = location_raw.split(",")[0].strip()
    return city if city else None


def _industry_from_occupation(occupation_raw: str) -> str | None:
    occ_lower = occupation_raw.lower()
    for keyword, industry in _OCCUPATION_TO_INDUSTRY.items():
        if keyword in occ_lower:
            return industry
    return None


def _education_from_occupation(occupation_raw: str) -> str | None:
    occ_lower = occupation_raw.lower()
    for keyword in _UNIVERSITY_OCCUPATIONS:
        if keyword in occ_lower:
            return "Post-Secondary 3+ yrs (ISCED 5A)"
    return None


def _employment_type_from_prose(text_lower: str, employment_status: str) -> str:
    if employment_status in ("Unemployed", "Student", "Retired"):
        return "Not Applicable"
    if any(k in text_lower for k in ("self-employed", "egenföretagare", "freelance", "frilans", "egen firma")):
        return "Self-Employed/Freelance"
    if any(k in text_lower for k in ("part-time", "deltid", "halvtid")):
        if any(k in text_lower for k in ("temporary", "tillfällig", "vikariat", "visstid")):
            return "Temporary Part-Time"
        return "Permanent Part-Time"
    if any(k in text_lower for k in ("temporary", "tillfällig", "vikariat", "visstid")):
        return "Temporary Full-Time"
    if employment_status == "Employed":
        return "Permanent Full-Time"
    return "Not Applicable"


def _income_source_from_context(employment_status: str, text_lower: str) -> str:
    if employment_status == "Retired":
        return "Pension"
    _SICK_BENEFIT = ("sjukersättning", "aktivitetsersättning",
                      "sickness benefit", "activity compensation")
    if any(k in text_lower for k in _SICK_BENEFIT):
        return "Sickness / Activity Compensation"
    if employment_status == "Unemployed":
        if any(k in text_lower for k in ("socialbidrag", "försörjningsstöd", "social assistance")):
            return "Social Assistance"
        return "Insurance / Allowance"
    if employment_status == "Student":
        return "Insurance / Allowance"
    if any(k in text_lower for k in ("egenföretagare", "self-employed", "egen firma", "freelance", "frilans")):
        return "Wage / Business"
    return "Wage / Business"
