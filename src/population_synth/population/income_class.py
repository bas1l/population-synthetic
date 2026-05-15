from __future__ import annotations

# Thresholds follow Eurostat AROP (0.60) and OECD/Pew middle-class bands (1.00, 2.00).
# Caveat: the SCB/SSB tables used here report individual gross income, not equivalised
# disposable household income — so these thresholds are a relative-position classifier,
# not a literal measurement of the official AROP poverty rate.
_POVERTY_UPPER = 0.60
_WORKING_UPPER = 1.00
_MIDDLE_UPPER = 2.00


def median_from_brackets(midpoints: list[float], counts: list[float]) -> float:
    """Return the bracket midpoint at the 50th-percentile cumulative count."""
    total = sum(counts)
    if total <= 0:
        raise ValueError("counts must sum to a positive number")
    if len(midpoints) != len(counts):
        raise ValueError("midpoints and counts must have the same length")

    target = total / 2.0
    cumulative = 0.0
    for mid, cnt in zip(midpoints, counts):
        cumulative += cnt
        if cumulative >= target:
            return mid
    return midpoints[-1]


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
