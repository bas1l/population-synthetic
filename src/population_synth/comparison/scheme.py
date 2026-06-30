"""Per-country comparison scheme: the in-scope attributes and DB-exact category
sets that drive population comparison.

The scheme is the single source of truth for *what the comparison scores*: which
demographic properties are compared for a country and, per property, the exact
category set the country's reference database emits. It is curated empirically --
each category list is the distinct non-None values the reference mapper produces
over that country's real reference population -- so the comparison axis has no
empty buckets, no DB-absent properties, and no mapper-synthesized categories.

This is deliberately separate from the per-attribute ``config/mapping/{scb,istat}``
mapping files (which define the broader set of labels the *mappers* may emit/accept).
The scheme narrows that to the DB-grounded comparison axis.

``age_group`` appears as a comparison dimension even though populations store only
the raw integer ``age``; the evaluator derives the age bin on the fly (see
``evaluator.attr_value``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from population_synth._paths import PROJECT_ROOT
from population_synth.comparison.reference_mapper.factory import _mapper_class

_MAPPINGS_ROOT = PROJECT_ROOT / "config" / "mapping"
_SCHEME_FILENAME = "_scheme.json"


@dataclass(frozen=True)
class ComparisonScheme:
    """In-scope attributes and DB-exact category sets for one country."""

    attributes: list[str]
    categories: dict[str, list[str]]
    joint_pairs: list[tuple[str, str]]
    coherence_attributes: tuple[str, ...]


def _scheme_dir(country: str, mappings_path: Path | None) -> Path:
    if mappings_path is not None:
        return mappings_path
    # Reuse the reference-mapper country dispatch (raises for unknown country).
    subdir = _mapper_class(country).MAPPINGS_SUBDIR
    return _MAPPINGS_ROOT / subdir


def load_scheme(country: str = "swedish", mappings_path: Path | None = None) -> ComparisonScheme:
    """Load the comparison scheme for *country* (``"swedish"`` or ``"italian"``).

    Reads ``_scheme.json`` from the country's mapping directory (or *mappings_path*
    if given). Fails loudly on a missing file, missing required keys, or an attribute
    declared in-scope without a category list.
    """
    scheme_path = _scheme_dir(country, mappings_path) / _SCHEME_FILENAME
    if not scheme_path.is_file():
        raise FileNotFoundError(f"No comparison scheme for country {country!r}: {scheme_path} not found")

    with open(scheme_path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)

    for key in ("attributes", "categories", "joint_pairs", "coherence_attributes"):
        if key not in raw:
            raise KeyError(f"Comparison scheme {scheme_path} is missing required key {key!r}")

    attributes: list[str] = list(raw["attributes"])
    categories: dict[str, list[str]] = {attr: list(vals) for attr, vals in raw["categories"].items()}

    missing = [attr for attr in attributes if attr not in categories]
    if missing:
        raise KeyError(f"Comparison scheme {scheme_path} declares attributes without categories: {missing}")

    joint_pairs = [tuple(pair) for pair in raw["joint_pairs"]]
    coherence_attributes = tuple(raw["coherence_attributes"])

    return ComparisonScheme(
        attributes=attributes,
        categories=categories,
        joint_pairs=joint_pairs,
        coherence_attributes=coherence_attributes,
    )
