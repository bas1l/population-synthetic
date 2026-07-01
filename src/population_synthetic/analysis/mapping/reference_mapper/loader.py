"""Two-step reference-population pipeline: load raw from disk, then normalize.

``load_reference_population`` reads the reference JSON file verbatim (the
population *as it is on the harddrive*); ``normalize_population`` applies the
country-specific reference mapper to produce the canonical schema population --
but only when the population is in raw (nested-dict) format; an already-flat
population is returned unchanged.  Keeping the two steps separate mirrors the
synthetic side (``load_raw_population`` -> ``map_population``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from population_synthetic.analysis.mapping.reference_mapper.factory import get_reference_mapper
from population_synthetic.analysis.mapping.reference_mapper.raw_format import is_raw_format


def load_reference_population(path: Path) -> dict[str, Any]:
    """Load a reference population JSON file verbatim from disk (no normalization)."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_population(
    raw_pop: dict[str, Any],
    country: str = "swedish",
    mappings_path: Path | None = None,
) -> dict[str, Any]:
    """Normalize a raw reference population to the canonical schema for *country*.

    Returns *raw_pop* unchanged when its individuals are already flat (not raw
    nested-dict format); otherwise returns a copy with normalized individuals.
    """
    individuals = raw_pop.get("individuals", [])
    if not is_raw_format(individuals):
        return raw_pop
    mapper = get_reference_mapper(country, mappings_path=mappings_path)
    normalized = [mapper.normalize_individual(ind) for ind in individuals]
    return {**raw_pop, "individuals": normalized}
