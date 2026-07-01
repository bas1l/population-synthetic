"""Raw-format detection for reference populations."""

from __future__ import annotations


def is_raw_format(individuals: list[dict]) -> bool:
    """Return True if the population uses raw nested-dict format (Phase 4+ SCB output)."""
    if not individuals:
        return False
    first = individuals[0]
    return any(isinstance(v, dict) for v in first.values())
