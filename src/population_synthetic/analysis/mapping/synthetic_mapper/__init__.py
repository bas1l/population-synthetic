"""Synthetic-population mapper: raw pipeline identities -> canonical schema.

Public API:
- ``load_synthetic_population(seed_root)`` / ``map_population(raw_pop, country)`` -- the
  two-step load-then-map flow used by the compare scripts.
- ``get_synthetic_mapper(country)`` -- factory for the country mapper class.
- ``AbstractSyntheticMapper`` / ``BaseSyntheticMapper`` /
  ``SwedishSyntheticMapper`` / ``ItalianSyntheticMapper`` -- the class hierarchy.
"""

from population_synthetic.analysis.mapping.synthetic_mapper.base import (
    AbstractSyntheticMapper,
    BaseSyntheticMapper,
)
from population_synthetic.analysis.mapping.synthetic_mapper.factory import get_synthetic_mapper
from population_synthetic.analysis.mapping.synthetic_mapper.italy import ItalianSyntheticMapper
from population_synthetic.analysis.mapping.synthetic_mapper.loader import load_synthetic_population, map_population
from population_synthetic.analysis.mapping.synthetic_mapper.sweden import SwedishSyntheticMapper

__all__ = [
    "AbstractSyntheticMapper",
    "BaseSyntheticMapper",
    "SwedishSyntheticMapper",
    "ItalianSyntheticMapper",
    "get_synthetic_mapper",
    "load_synthetic_population",
    "map_population",
]
