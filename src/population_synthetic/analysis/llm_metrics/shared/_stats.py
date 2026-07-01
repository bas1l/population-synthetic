"""Shared numeric primitives for the llm_metrics pipeline.

A single home for ``median`` / ``percentile`` / ``shannon_entropy`` so the
per-run aggregator, the per-run charts, and the cross-run comparison all use the
*same* convention.  Previously these were implemented three times with divergent
percentile semantics (stdlib nearest-rank vs numpy linear interpolation), so the
same conceptual p95 could differ between a chart and a cross-run summary.

**Percentile convention: nearest-rank.**  ``percentile`` returns a value that
actually occurred in the sample (no interpolation between ranks).  This keeps the
core stdlib-only and is well-suited to the small latency/size samples here, where
interpolating to a value no run produced would be misleading.
"""

from __future__ import annotations

import math


def median(values: list[float]) -> float | None:
    """Return the median of *values*, or ``None`` when empty.

    Even-length lists return the mean of the two middle elements.
    """
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 0:
        return (s[mid - 1] + s[mid]) / 2.0
    return s[mid]


def percentile(values: list[float], p: float) -> float | None:
    """Return the *p*-th percentile (0-100) using the **nearest-rank** method.

    ``idx = ceil(p/100 * n) - 1`` (0-based), clamped to ``[0, n-1]``.  Returns a
    value present in *values*; returns ``None`` when *values* is empty.
    """
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    idx = max(0, min(n - 1, int(math.ceil(p / 100.0 * n)) - 1))
    return s[idx]


def shannon_entropy(counts: dict[str, int]) -> float:
    """Compute Shannon entropy (bits) for a frequency distribution.

    Returns ``0.0`` for an empty or single-valued distribution.
    """
    total = sum(counts.values())
    if total == 0:
        return 0.0
    entropy = 0.0
    for count in counts.values():
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)
    return entropy
