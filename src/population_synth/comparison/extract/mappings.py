"""Pipeline label-mapping lookups and text-repair helpers for extraction.

Loads the per-attribute ``pipeline_label_mappings`` from the SCB and ISTAT
category-mapping directories (the JSON files are the source of truth for
free-form label -> schema-label translation) and exposes separator-insensitive,
case-insensitive lookup helpers plus a UTF-8 double-encoding repair pass.
"""

from __future__ import annotations

import re
from pathlib import Path

from population_synth._paths import PROJECT_ROOT
from population_synth.comparison.normalizer import load_mappings

# ---------------------------------------------------------------------------
# Pipeline label mappings -- loaded from the per-attribute category-mapping
# directories so the JSON files are the source of truth for free-form label ->
# schema-label translations.
# ---------------------------------------------------------------------------

_MAPPINGS_PATH = PROJECT_ROOT / "config" / "mapping" / "scb"
_ISTAT_MAPPINGS_PATH = PROJECT_ROOT / "config" / "mapping" / "istat"

_SEP_RE = re.compile(r"[\s_\-]+")


def _sep_norm(s: str) -> str:
    """Collapse underscores, hyphens, and whitespace runs to single spaces.

    Applied symmetrically to mapping keys and lookup inputs so snake_case /
    kebab-case LLM output (e.g. ``two_biological_parents``, ``upper-middle``)
    matches the space-form keys curated in category_mappings.json.
    """
    return _SEP_RE.sub(" ", s).strip()


def _load_pipeline_mappings(path: Path | None = None) -> dict[str, dict[str, str]]:
    """Return {category: {separator_normalized_label: schema_label}} for fast lookup."""
    m = load_mappings(path or _MAPPINGS_PATH)
    out: dict[str, dict[str, str]] = {}
    for key in (
        "education", "employment", "civil_status", "industry_sector",
        "employment_type", "income_source", "housing_tenure",
        "parental_structure", "socioeconomic", "region", "birth_country_detail",
        "ethnicity",
    ):
        section = m.get(key, {}) or {}
        plm = section.get("pipeline_label_mappings", {}) or {}
        out[key] = {_sep_norm(k.lower()): v for k, v in plm.items()}
    return out


_PIPELINE_MAPPINGS: dict[str, dict[str, str]] = _load_pipeline_mappings()
_PIPELINE_MAPPINGS_IT: dict[str, dict[str, str]] | None = None


_UTF8_DOUBLE_ENCODING_REPAIRS: dict[str, str] = {
    "√§": "ä", "√∂": "ö", "√•": "å",
    "√Ñ": "Ä", "√ñ": "Ö", "√Ö": "Å",
    "Ã¤": "ä", "Ã¶": "ö", "Ã¥": "å",
    "Ã": "Ä", "Ã": "Ö", "Ã": "Å",
}


def _repair_utf8_double_encoding(text: str) -> str:
    for bad, good in _UTF8_DOUBLE_ENCODING_REPAIRS.items():
        text = text.replace(bad, good)
    return text


def _json_lookup(category: str, raw: str) -> str | None:
    """Separator-insensitive, case-insensitive lookup against pipeline_label_mappings."""
    if not raw:
        return None
    return _PIPELINE_MAPPINGS.get(category, {}).get(_sep_norm(raw.lower()))


def _get_it_mappings() -> dict[str, dict[str, str]]:
    global _PIPELINE_MAPPINGS_IT
    if _PIPELINE_MAPPINGS_IT is None:
        _PIPELINE_MAPPINGS_IT = _load_pipeline_mappings(_ISTAT_MAPPINGS_PATH)
    return _PIPELINE_MAPPINGS_IT


def _json_lookup_it(category: str, raw: str) -> str | None:
    """Separator-insensitive, case-insensitive lookup against Italian pipeline_label_mappings."""
    if not raw:
        return None
    return _get_it_mappings().get(category, {}).get(_sep_norm(raw.lower()))
