"""Generic raw-to-flat normalizer for population JSON files.

Converts nested ``{"label": "...", "code": "..."}`` dicts to flat strings.
Works for all three country pipelines (Sweden, Norway, Italy) without
country-specific category mappings.
"""

from __future__ import annotations

from population_synth.population.helpers import age_to_group

_SEX_HARMONIZE: dict[str, str] = {
    "men": "Male",
    "women": "Female",
    "male": "Male",
    "female": "Female",
}


def _extract_label(value: object) -> str | None:
    """Extract the label string from a raw field value."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get("label") or value.get("code") or value.get("decile")
    if isinstance(value, str):
        return value
    return None


def _flatten_employment_type(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        return None
    attachment = _extract_label(value.get("attachment"))
    hours = _extract_label(value.get("hours"))
    if attachment and hours:
        return f"{attachment} / {hours}"
    return attachment or hours


_SIMPLE_FIELDS = (
    "education_level",
    "employment_status",
    "socioeconomic_class",
    "birth_location",
    "region",
    "civil_status",
    "industry_sector",
    "housing_tenure",
    "household_size",
    "income_source",
    "birth_country_detail",
    "parental_structure",
)


def flatten_individual(raw: dict) -> dict:
    """Convert one raw individual record to flat-string format."""
    flat: dict = {"id": raw.get("id")}

    age = raw.get("age")
    flat["age"] = age
    if isinstance(age, int):
        try:
            flat["age_group"] = age_to_group(age)
        except ValueError:
            flat["age_group"] = None
    else:
        flat["age_group"] = None

    sex_raw = _extract_label(raw.get("biological_sex"))
    if sex_raw:
        flat["biological_sex"] = _SEX_HARMONIZE.get(sex_raw.lower(), sex_raw)
    else:
        flat["biological_sex"] = None

    for field in _SIMPLE_FIELDS:
        flat[field] = _extract_label(raw.get(field))

    flat["employment_type"] = _flatten_employment_type(raw.get("employment_type"))

    return flat


def flatten_raw_population(pop: dict, *, country_label: str = "Unknown") -> dict:
    """Flatten an entire raw population dict to flat-string format.

    Returns a new dict with the same ``metadata`` plus flattened ``individuals``.
    """
    individuals = pop.get("individuals", [])
    flat_individuals = [flatten_individual(ind) for ind in individuals]

    metadata = dict(pop.get("metadata", {}))
    metadata["country_label"] = country_label
    metadata["flatten_note"] = "generic raw-to-flat (no category mapping)"

    return {"metadata": metadata, "individuals": flat_individuals}
