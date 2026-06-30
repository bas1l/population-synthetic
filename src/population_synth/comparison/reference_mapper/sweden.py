"""Swedish (SCB) reference mapper."""

from __future__ import annotations

from typing import ClassVar

from population_synth.comparison.reference_mapper.base import BaseReferenceMapper

_SWEDEN_BIRTH_LABELS: frozenset[str] = frozenset({
    "born in sweden", "sverige", "sweden", "födda i sverige",
})


class SwedishReferenceMapper(BaseReferenceMapper):
    """Normalize raw SCB reference records to the canonical schema."""

    DOMESTIC_NAME: ClassVar[str] = "Sweden"
    DOMESTIC_BIRTH_LABELS: ClassVar[frozenset[str]] = _SWEDEN_BIRTH_LABELS
    MAPPINGS_SUBDIR: ClassVar[str] = "scb"
