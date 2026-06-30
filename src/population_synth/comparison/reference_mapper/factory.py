"""Factory selecting the country-specific reference mapper."""

from __future__ import annotations

from pathlib import Path

from population_synth._paths import PROJECT_ROOT
from population_synth.comparison.reference_mapper.base import AbstractReferenceMapper
from population_synth.comparison.reference_mapper.sweden import SwedishReferenceMapper
from population_synth.comparison.reference_mapper.italy import ItalianReferenceMapper
from population_synth.comparison.reference_mapper.mappings import load_mappings

_MAPPINGS_ROOT = PROJECT_ROOT / "config" / "mapping"

_REFERENCE_MAPPERS: dict[str, type[AbstractReferenceMapper]] = {
    "swedish": SwedishReferenceMapper,
    "italian": ItalianReferenceMapper,
}


def _mapper_class(country: str) -> type[AbstractReferenceMapper]:
    cls = _REFERENCE_MAPPERS.get(country)
    if cls is None:
        raise ValueError(f"No reference mapper for country {country!r}")
    return cls


def build_reference_mapper(country: str, mappings: dict) -> AbstractReferenceMapper:
    """Return the reference mapper for *country* using a pre-loaded *mappings* dict."""
    return _mapper_class(country)(mappings)


def get_reference_mapper(country: str = "swedish", mappings_path: Path | None = None) -> AbstractReferenceMapper:
    """Return the reference mapper for *country* (``"swedish"`` or ``"italian"``).

    The mapper loads its category mappings from *mappings_path* if given,
    otherwise from the country's default ``config/mapping/{subdir}`` directory.
    """
    cls = _mapper_class(country)
    path = mappings_path or (_MAPPINGS_ROOT / cls.MAPPINGS_SUBDIR)
    return cls(load_mappings(path))
