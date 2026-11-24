"""Classify income brackets into four socioeconomic classes.

Maps bracketed income data to Poverty, Working Class, Middle Class, and
Wealthy using thresholds relative to the median: Eurostat AROP (0.60x)
and OECD/Pew middle-class bands (1.00x, 2.00x). ``median_from_brackets``
estimates the median by linear interpolation inside the bracket that holds the
50th percentile, and ``classify_brackets`` splits straddling brackets
proportionally by width to return a probability per class. Both rest on the
same assumption -- counts are spread uniformly within a bracket -- so the
median and the class split are consistent with each other.
"""

from __future__ import annotations

# Thresholds follow Eurostat AROP (0.60) and OECD/Pew middle-class bands (1.00, 2.00).
# Caveat: the SCB/SSB tables used here report individual gross income, not equivalised
# disposable household income — so these thresholds are a relative-position classifier,
# not a literal measurement of the official AROP poverty rate.
_POVERTY_UPPER = 0.60
_WORKING_UPPER = 1.00
_MIDDLE_UPPER = 2.00


def median_from_brackets(edges: list[tuple[float, float]], counts: list[float]) -> float:
    """Return the median of bracketed counts by within-bracket linear interpolation.

    ``edges`` are ``(low, high)`` per bracket in ascending order, ``counts`` the
    number of persons in each. The 50th percentile is located in the bracket
    whose cumulative count first reaches half the total, and placed inside it
    assuming the bracket's persons are spread uniformly over ``[low, high]``
    (the grouped-data median, ``L + (N/2 - F) / f * w``).

    The previous estimator returned that bracket's midpoint, which is off by up
    to half a bracket width: SCB's brackets are 100-200 tkr wide above 400 tkr,
    so every cell whose median fell in 400-499 tkr got 450 (45 tkr from SCB's
    published 486.9 for men aged 40-44). Interpolation is within 3.3 tkr of
    SCB's published medians in all 20 five-year band x sex cells (see
    ``tests/test_income_class.py``).
    """
    if len(edges) != len(counts):
        raise ValueError("edges and counts must have the same length")
    if any(c < 0 for c in counts):
        raise ValueError("counts must be non-negative")
    total = sum(counts)
    if total <= 0:
        raise ValueError("counts must sum to a positive number")
    prev_hi = None
    for lo, hi in edges:
        if hi < lo or (prev_hi is not None and lo < prev_hi):
            raise ValueError(f"edges must be ascending, non-overlapping (low, high) pairs; got {edges!r}")
        prev_hi = hi

    target = total / 2.0
    cumulative = 0.0
    for (lo, hi), cnt in zip(edges, counts):
        if cnt > 0 and cumulative + cnt >= target:
            return lo + (target - cumulative) / cnt * (hi - lo)
        cumulative += cnt
    raise AssertionError("unreachable: a positive total always reaches its half")


def classify_brackets(
    edges: list[tuple[float, float]],
    counts: list[float],
    median: float,
) -> dict[str, float]:
    """Return {class_label: probability} for the four income classes.

    Brackets that straddle a threshold are split proportionally by width.
    """
    if len(edges) != len(counts):
        raise ValueError("edges and counts must have the same length")
    if median <= 0:
        raise ValueError("median must be positive")

    thresholds = [
        (_POVERTY_UPPER * median, "Poverty"),
        (_WORKING_UPPER * median, "Working Class"),
        (_MIDDLE_UPPER * median, "Middle Class"),
    ]

    class_totals: dict[str, float] = {
        "Poverty": 0.0,
        "Working Class": 0.0,
        "Middle Class": 0.0,
        "Wealthy": 0.0,
    }

    def _class_for(income: float) -> str:
        if income < _POVERTY_UPPER * median:
            return "Poverty"
        if income < _WORKING_UPPER * median:
            return "Working Class"
        if income < _MIDDLE_UPPER * median:
            return "Middle Class"
        return "Wealthy"

    for (lo, hi), cnt in zip(edges, counts):
        if cnt <= 0:
            continue
        width = hi - lo
        if width <= 0:
            class_totals[_class_for(lo)] += cnt
            continue

        # Find all threshold boundaries that fall strictly inside (lo, hi).
        breakpoints = [lo]
        for cutoff, _ in thresholds:
            if lo < cutoff < hi:
                breakpoints.append(cutoff)
        breakpoints.append(hi)

        for k in range(len(breakpoints) - 1):
            seg_lo = breakpoints[k]
            seg_hi = breakpoints[k + 1]
            fraction = (seg_hi - seg_lo) / width
            mid = (seg_lo + seg_hi) / 2.0
            class_totals[_class_for(mid)] += cnt * fraction

    grand_total = sum(class_totals.values())
    if grand_total <= 0:
        raise ValueError("All bracket counts are zero — cannot classify")
    return {cls: v / grand_total for cls, v in class_totals.items()}
