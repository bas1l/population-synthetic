"""Reference-population mapper: raw national-statistics records -> canonical schema.

The structural counterpart to ``synthetic_mapper/``.  Public API:
- ``load_reference_population(path)`` / ``normalize_population(raw_pop, country)`` --
  the two-step load-then-normalize flow used by the compare scripts.
- ``get_reference_mapper(country)`` -- factory for the country mapper class.
- ``AbstractReferenceMapper`` / ``BaseReferenceMapper`` /
  ``SwedishReferenceMapper`` / ``ItalianReferenceMapper`` -- the class hierarchy.
- ``load_mappings`` / ``is_raw_format`` -- the supporting primitives.
"""

from population_synth.analysis.mapping.reference_mapper.base import (
    AbstractReferenceMapper,
    BaseReferenceMapper,
)
from population_synth.analysis.mapping.reference_mapper.factory import get_reference_mapper
from population_synth.analysis.mapping.reference_mapper.italy import ItalianReferenceMapper
from population_synth.analysis.mapping.reference_mapper.loader import (
    load_reference_population,
    normalize_population,
)
from population_synth.analysis.mapping.reference_mapper.mappings import load_mappings
from population_synth.analysis.mapping.reference_mapper.raw_format import is_raw_format
from population_synth.analysis.mapping.reference_mapper.sweden import SwedishReferenceMapper

__all__ = [
    "AbstractReferenceMapper",
    "BaseReferenceMapper",
    "SwedishReferenceMapper",
    "ItalianReferenceMapper",
    "get_reference_mapper",
    "load_reference_population",
    "normalize_population",
    "load_mappings",
    "is_raw_format",
]
