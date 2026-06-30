"""Factory selecting the country-specific synthetic mapper."""

from __future__ import annotations

from population_synth.comparison.synthetic_mapper.base import AbstractSyntheticMapper
from population_synth.comparison.synthetic_mapper.italy import ItalianSyntheticMapper
from population_synth.comparison.synthetic_mapper.sweden import SwedishSyntheticMapper


def get_synthetic_mapper(country: str = "swedish") -> AbstractSyntheticMapper:
    """Return the synthetic mapper for *country* (``"swedish"`` or ``"italian"``)."""
    if country == "italian":
        return ItalianSyntheticMapper()
    if country == "swedish":
        return SwedishSyntheticMapper()
    raise ValueError(f"No synthetic mapper for country {country!r}")
