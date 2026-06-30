"""Italian (ISTAT) reference mapper."""

from __future__ import annotations

from typing import ClassVar

from population_synth.comparison.reference_mapper.base import BaseReferenceMapper


class ItalianReferenceMapper(BaseReferenceMapper):
    """Normalize raw ISTAT reference records to the canonical schema.

    Country divergence is entirely the mapping directory: every label, including the
    domestic-birth collapse, lives in ``config/mapping/istat/``.
    """

    MAPPINGS_SUBDIR: ClassVar[str] = "istat"
