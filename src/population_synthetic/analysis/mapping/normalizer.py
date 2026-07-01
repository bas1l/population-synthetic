"""
normalizer.py -- Backward-compat facade over the ``real_mapper`` package.

The real-population mapping moved to ``comparison/real_mapper/`` (the
structural counterpart to ``synthetic_mapper/``).  This module is kept as a thin
facade so existing callers -- and ``extract/mappings.py`` on the synthetic side,
which imports ``load_mappings`` from here -- keep working unchanged.  New code
should prefer ``real_mapper.load_real_population`` /
``real_mapper.map_population``.
"""

from __future__ import annotations

from pathlib import Path

from population_synthetic.analysis.mapping.real_mapper.factory import build_real_mapper
from population_synthetic.analysis.mapping.real_mapper.mappings import load_mappings
from population_synthetic.analysis.mapping.real_mapper.raw_format import is_raw_format

__all__ = ["load_mappings", "is_raw_format", "normalize_raw_to_schema", "normalize_if_raw"]


def normalize_raw_to_schema(records: list[dict], mappings: dict, country: str = "swedish") -> list[dict]:
    """Convert raw-format records to flat schema strings using a pre-loaded *mappings* dict."""
    mapper = build_real_mapper(country, mappings)
    return [mapper.normalize_individual(rec) for rec in records]


def normalize_if_raw(
    pop: dict,
    mappings: dict,
    mappings_path: Path | None = None,
    country: str = "swedish",
) -> dict:
    """Return a copy of pop with individuals normalized if raw-format, else return pop unchanged.

    Parameters
    ----------
    pop : dict
        Population dict with an ``"individuals"`` list.
    mappings : dict
        Pre-loaded category mappings (used as-is).
    mappings_path : Path | None
        If provided, *overrides* ``mappings`` by loading from this path.
    country : str
        ``"swedish"`` (default) or ``"italian"`` -- controls birth-location
        detection and other country-specific normalisation logic.
    """
    if mappings_path is not None:
        mappings = load_mappings(path=mappings_path)
    individuals = pop.get("individuals", [])
    if not is_raw_format(individuals):
        return pop
    normalized_individuals = normalize_raw_to_schema(individuals, mappings, country=country)
    return {**pop, "individuals": normalized_individuals}
