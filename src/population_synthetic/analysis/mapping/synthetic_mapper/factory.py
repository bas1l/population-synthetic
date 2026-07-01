"""Factory selecting the country-specific synthetic mapper."""

from __future__ import annotations

from pathlib import Path

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.mapping.real_mapper.mappings import load_mappings
from population_synthetic.analysis.mapping.synthetic_mapper.base import AbstractSyntheticMapper
from population_synthetic.analysis.mapping.synthetic_mapper.italy import ItalianSyntheticMapper
from population_synthetic.analysis.mapping.synthetic_mapper.sweden import SwedishSyntheticMapper

_MAPPINGS_ROOT = PROJECT_ROOT / "config" / "mapping"

_SYNTHETIC_MAPPERS: dict[str, type[AbstractSyntheticMapper]] = {
    "swedish": SwedishSyntheticMapper,
    "italian": ItalianSyntheticMapper,
}


def _mapper_class(country: str) -> type[AbstractSyntheticMapper]:
    cls = _SYNTHETIC_MAPPERS.get(country)
    if cls is None:
        raise ValueError(f"No synthetic mapper for country {country!r}")
    return cls


def get_synthetic_mapper(country: str = "swedish", mappings_path: Path | None = None) -> AbstractSyntheticMapper:
    """Return the synthetic mapper for *country* (``"swedish"`` or ``"italian"``).

    The mapper loads its category mappings from *mappings_path* if given,
    otherwise from the country's default ``config/mapping/{subdir}`` directory.
    """
    cls = _mapper_class(country)
    path = mappings_path or (_MAPPINGS_ROOT / cls.MAPPINGS_SUBDIR)
    return cls(load_mappings(path))
