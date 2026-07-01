"""Generic raw-to-flat normalizer for population JSON files.

Converts nested ``{"label": "...", "code": "..."}`` dicts to flat strings, works
for all three country pipelines (Sweden, Norway, Italy). It does **not** canonicalize
category labels -- it unwraps them -- with two exceptions that are computed, not
guessed: ``age_group`` is derived from the integer ``age`` (numeric binning), and
``biological_sex`` is harmonized through the caller-supplied biological-sex mapping
config (``config/mapping/{scb,istat}/biological_sex.json``) via the shared
:func:`mapping_engine.resolve`. There are deliberately no in-code attribute-name or
sex-value literals: the fields flattened come from each record's own keys, and the
sex vocabulary comes from config.
"""

from __future__ import annotations

from population_synthetic.analysis.mapping import mapping_engine
from population_synthetic.generators.real.helpers import age_to_group

#: Keys handled explicitly by :func:`flatten_individual`; every other key is
#: unwrapped generically from the record itself (no hardcoded field list).
_SPECIAL_KEYS = frozenset({"id", "age", "age_group", "biological_sex", "employment_type"})


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


def _harmonize_sex(sex_raw: str, sex_config: dict) -> str:
    """Resolve a raw sex token to the canonical value via the biological-sex config.

    Uses the config's ``real`` rules (raw national-statistics side). Falls back to
    the raw label when the token is outside the config's vocabulary, mirroring how the
    other fields keep their native label rather than inventing a value.
    """
    resolved = mapping_engine.resolve(sex_raw, sex_config["real"], sex_config["values"])
    return resolved if resolved is not None else sex_raw


def flatten_individual(raw: dict, *, sex_config: dict) -> dict:
    """Convert one raw individual record to flat-string format.

    *sex_config* is the ``biological_sex`` mapping block (``values`` + ``real``),
    supplied by the caller so the sex vocabulary lives in config, not in code.
    """
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
    flat["biological_sex"] = _harmonize_sex(sex_raw, sex_config) if sex_raw else None

    flat["employment_type"] = _flatten_employment_type(raw.get("employment_type"))

    # Every remaining field is unwrapped generically -- the field set comes from the
    # record itself, not a hardcoded attribute list.
    for key, value in raw.items():
        if key in _SPECIAL_KEYS:
            continue
        flat[key] = _extract_label(value)

    return flat


def flatten_raw_population(pop: dict, *, sex_config: dict, country_label: str = "Unknown") -> dict:
    """Flatten an entire raw population dict to flat-string format.

    *sex_config* is the ``biological_sex`` mapping block used to harmonize the sex
    field (see :func:`flatten_individual`). Returns a new dict with the same
    ``metadata`` plus flattened ``individuals``.
    """
    individuals = pop.get("individuals", [])
    flat_individuals = [flatten_individual(ind, sex_config=sex_config) for ind in individuals]

    metadata = dict(pop.get("metadata", {}))
    metadata["country_label"] = country_label
    metadata["flatten_note"] = "generic raw-to-flat (labels unwrapped; sex harmonized via config)"

    return {"metadata": metadata, "individuals": flat_individuals}
