"""Factory selecting the country-specific real mapper."""

from __future__ import annotations

from pathlib import Path

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.mapping.real_mapper.base import AbstractRealMapper
from population_synthetic.analysis.mapping.real_mapper.italy import ItalianRealMapper
from population_synthetic.analysis.mapping.real_mapper.mappings import load_mappings
from population_synthetic.analysis.mapping.real_mapper.sweden import SwedishRealMapper

_MAPPINGS_ROOT = PROJECT_ROOT / "config" / "mapping"

_REAL_MAPPERS: dict[str, type[AbstractRealMapper]] = {
    "swedish": SwedishRealMapper,
    "swedish_02": SwedishRealMapper,  # guided-prompt A/B arm (simulation config 006)
    "italian": ItalianRealMapper,
}


def _mapper_class(country: str) -> type[AbstractRealMapper]:
    cls = _REAL_MAPPERS.get(country)
    if cls is None:
        raise ValueError(f"No real mapper for country {country!r}")
    return cls


def build_real_mapper(country: str, mappings: dict) -> AbstractRealMapper:
    """Return the real mapper for *country* using a pre-loaded *mappings* dict."""
    return _mapper_class(country)(mappings)


def get_real_mapper(country: str = "swedish", mappings_path: Path | None = None) -> AbstractRealMapper:
    """Return the real mapper for *country* (``"swedish"`` or ``"italian"``).

    The mapper loads its category mappings from *mappings_path* if given,
    otherwise from the country's default ``config/mapping/{subdir}`` directory.
    """
    cls = _mapper_class(country)
    path = mappings_path or (_MAPPINGS_ROOT / cls.MAPPINGS_SUBDIR)
    return cls(load_mappings(path))
