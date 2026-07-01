"""Italian (ISTAT) synthetic-population mapper."""

from __future__ import annotations

from typing import ClassVar

from population_synthetic.analysis.mapping.synthetic_mapper.base import BaseSyntheticMapper


class ItalianSyntheticMapper(BaseSyntheticMapper):
    """Map Italian (ISTAT) pipeline identities to the canonical schema.

    Country divergence is entirely the mapping directory (``config/mapping/istat/``):
    every label and keyword cascade lives there, including the Italian sex tokens
    and the pipe-separated ``employment_type`` passthrough.
    """

    MAPPINGS_SUBDIR: ClassVar[str] = "istat"
