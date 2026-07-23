"""Shared numeric primitives for the analysis pipelines.

A single home for ``median`` / ``percentile`` / ``shannon_entropy`` so every
analysis consumer (the generation-metadata diagnostics and charts, the
cross-factor comparison, the cross-model performance comparison) uses the *same*
convention.  Previously these were implemented three times with divergent
percentile semantics (stdlib nearest-rank vs numpy linear interpolation), so the
same conceptual p95 could differ between a chart and a summary.

**Percentile convention: nearest-rank.**  ``percentile`` returns a value that
actually occurred in the sample (no interpolation between ranks).  This keeps the
core stdlib-only and is well-suited to the small latency/size samples here, where
interpolating to a value no run produced would be misleading.
"""

from __future__ import annotations

import math


def mean(values: list[float]) -> float | None:
    """Return the arithmetic mean of *values*, or ``None`` when empty.

    ``None`` (not ``0.0``) for an empty input keeps "no data" distinct from a
    genuine zero mean -- callers gate on availability rather than treating an
    absent metric as zero.
    """
    if not values:
        return None
    return sum(values) / len(values)


def stddev(values: list[float], *, sample: bool = True) -> float | None:
    """Return the standard deviation of *values*, or ``None`` when undefined.

    Uses the **sample** (``n-1``) denominator by default (``sample=True``), which
    is undefined for ``n < 2`` and therefore returns ``None`` there (never ``0``
    or a crash). Pass ``sample=False`` for the population (``n``) denominator,
    which is defined for ``n >= 1`` and returns ``None`` only when empty.
    """
    n = len(values)
    if n < 1:
        return None
    denom = n - 1 if sample else n
    if denom < 1:
        return None
    m = sum(values) / n
    variance = sum((x - m) ** 2 for x in values) / denom
    return math.sqrt(variance)


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
