"""Per-country comparison scheme: the in-scope attributes and DB-exact category
sets that drive population comparison.

The scheme is the single source of truth for *what the comparison scores*: which
demographic properties are compared for a country and, per property, the exact
category set the country's reference database emits. It is curated empirically --
each category list is the distinct non-None values the reference mapper produces
over that country's real reference population -- so the comparison axis has no
empty buckets, no DB-absent properties, and no mapper-synthesized categories.

The scheme is sourced from the unified per-attribute ``config/mapping/{scb,istat}``
config: the ``_index.json`` master lists the in-scope attributes (ordered) plus the
joint pairs and coherence attributes, and each per-attribute file's ``values`` list
*is* that attribute's comparison category set. Because both mappers now emit only
declared ``values``, the scored axis equals the ``values`` and no separate filter is
needed. A directory still carrying the legacy ``_scheme.json`` (pre-migration) is read
through the unchanged legacy path.

``age_group`` appears as a comparison dimension even though populations store only
the raw integer ``age``; the evaluator derives the age bin on the fly (see
``evaluator.attr_value``). Its categories are the age-bin labels declared as
``values`` in ``age.json``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from population_synth._paths import PROJECT_ROOT
from population_synth.comparison.reference_mapper.factory import _mapper_class
from population_synth.comparison.reference_mapper.mappings import index_path, load_index

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

    The scheme is sourced from the unified per-attribute mapping config: the
    ``_index.json`` master supplies the in-scope attributes (ordered) plus the
    joint pairs and coherence attributes, and each per-attribute file's ``values``
    list supplies that attribute's DB-grounded category set (``age_group``'s
    categories are the age-bin labels declared as ``values`` in ``age.json``).

    A country directory that still ships the legacy ``_scheme.json`` (and no
    ``_index.json``) is read through the pre-migration path unchanged, so the
    interface stays identical while the config is migrated. Fails loudly on a
    missing master/legacy file, a missing required key, or a per-attribute file
    that omits ``values``.
    """
    directory = _scheme_dir(country, mappings_path)

    if index_path(directory).is_file():
        return _scheme_from_index(directory)

    return _scheme_from_legacy(country, directory)


def _scheme_from_index(directory: Path) -> ComparisonScheme:
    """Build a :class:`ComparisonScheme` from ``_index.json`` + per-file ``values``."""
    index = load_index(directory)

    attributes: list[str] = list(index["attributes"].keys())  # key order = axis order
    categories: dict[str, list[str]] = {}
    for attr, filename in index["attributes"].items():
        attr_path = directory / filename
        if not attr_path.is_file():
            raise FileNotFoundError(
                f"Comparison scheme for attribute {attr!r} references missing file {attr_path}"
            )
        with open(attr_path, "r", encoding="utf-8") as fh:
            block = json.load(fh)
        if "values" not in block:
            raise KeyError(f"Mapping file {attr_path} is missing required key 'values'")
        categories[attr] = list(block["values"])

    joint_pairs = [tuple(pair) for pair in index["joint_pairs"]]
    coherence_attributes = tuple(index["coherence_attributes"])

    return ComparisonScheme(
        attributes=attributes,
        categories=categories,
        joint_pairs=joint_pairs,
        coherence_attributes=coherence_attributes,
    )


def _scheme_from_legacy(country: str, directory: Path) -> ComparisonScheme:
    """Build a :class:`ComparisonScheme` from a pre-migration ``_scheme.json`` file."""
    scheme_path = directory / _SCHEME_FILENAME
    if not scheme_path.is_file():
        raise FileNotFoundError(f"No comparison scheme for country {country!r}: {scheme_path} not found")

    with open(scheme_path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)

    for key in ("attributes", "categories", "joint_pairs", "coherence_attributes"):
        if key not in raw:
            raise KeyError(f"Comparison scheme {scheme_path} is missing required key {key!r}")

    attributes = list(raw["attributes"])
    categories = {attr: list(vals) for attr, vals in raw["categories"].items()}

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
