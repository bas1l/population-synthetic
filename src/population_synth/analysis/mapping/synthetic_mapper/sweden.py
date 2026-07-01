"""Swedish (SCB) synthetic-population mapper."""

from __future__ import annotations

from typing import ClassVar

from population_synth.analysis.mapping.synthetic_mapper.base import BaseSyntheticMapper


class SwedishSyntheticMapper(BaseSyntheticMapper):
    """Map Swedish (SCB) pipeline identities to the canonical schema.

    Country divergence is entirely the mapping directory (``config/mapping/scb/``):
    every label and keyword cascade lives there.
    """

    MAPPINGS_SUBDIR: ClassVar[str] = "scb"
