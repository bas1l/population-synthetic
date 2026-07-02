"""Swedish (SCB) real mapper."""

from __future__ import annotations

from typing import ClassVar

from population_synthetic.analysis.mapping.real_mapper.base import BaseRealMapper


class SwedishRealMapper(BaseRealMapper):
    """Normalize raw SCB real records to the canonical schema.

    Country divergence is entirely the mapping directory: every label, including the
    domestic-birth collapse, lives in ``config/mapping/scb/``.
    """

    MAPPINGS_SUBDIR: ClassVar[str] = "scb"
