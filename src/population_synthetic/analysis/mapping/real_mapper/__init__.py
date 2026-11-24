"""Real-population mapper: raw national-statistics records -> canonical schema.

The structural counterpart to ``synthetic_mapper/``.  Public API:
- ``load_real_population(path)`` / ``map_population(raw_pop, country)`` --
  the two-step load-then-map flow used by the compare scripts.
- ``get_real_mapper(country)`` -- factory for the country mapper class.
- ``AbstractRealMapper`` / ``BaseRealMapper`` /
  ``SwedishRealMapper`` / ``ItalianRealMapper`` -- the class hierarchy.
- ``load_mappings`` / ``is_raw_format`` -- the supporting primitives.
"""

from population_synthetic.analysis.mapping.real_mapper.base import (
    AbstractRealMapper,
    BaseRealMapper,
)
from population_synthetic.analysis.mapping.real_mapper.factory import get_real_mapper
from population_synthetic.analysis.mapping.real_mapper.italy import ItalianRealMapper
from population_synthetic.analysis.mapping.real_mapper.loader import (
    load_real_population,
    map_population,
)
from population_synthetic.analysis.mapping.real_mapper.mappings import load_mappings
from population_synthetic.analysis.mapping.real_mapper.raw_format import is_raw_format
from population_synthetic.analysis.mapping.real_mapper.sweden import SwedishRealMapper

__all__ = [
    "AbstractRealMapper",
    "BaseRealMapper",
    "SwedishRealMapper",
    "ItalianRealMapper",
    "get_real_mapper",
    "load_real_population",
    "map_population",
    "load_mappings",
    "is_raw_format",
]
