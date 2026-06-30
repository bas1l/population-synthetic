"""Italian (ISTAT) reference mapper."""

from __future__ import annotations

from typing import ClassVar

from population_synth.comparison.reference_mapper.base import BaseReferenceMapper

_ITALY_BIRTH_LABELS: frozenset[str] = frozenset({
    "born in italy", "italia", "italy", "nato in italia", "italiana",
})


class ItalianReferenceMapper(BaseReferenceMapper):
    """Normalize raw ISTAT reference records to the canonical schema."""

    DOMESTIC_NAME: ClassVar[str] = "Italy"
    DOMESTIC_BIRTH_LABELS: ClassVar[frozenset[str]] = _ITALY_BIRTH_LABELS
    MAPPINGS_SUBDIR: ClassVar[str] = "istat"
