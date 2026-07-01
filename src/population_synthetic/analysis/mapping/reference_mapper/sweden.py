"""Swedish (SCB) reference mapper."""

from __future__ import annotations

from typing import ClassVar

from population_synthetic.analysis.mapping.reference_mapper.base import BaseReferenceMapper


class SwedishReferenceMapper(BaseReferenceMapper):
    """Normalize raw SCB reference records to the canonical schema.

    Country divergence is entirely the mapping directory: every label, including the
    domestic-birth collapse, lives in ``config/mapping/scb/``.
    """

    MAPPINGS_SUBDIR: ClassVar[str] = "scb"
