"""ordinal.py -- Dispersion statistics for a bounded ordinal scale.

A pure statistics module over a vector of integer *levels* ``0 .. k-1`` (equivalently,
over the per-level ``counts`` histogram of such a vector).  It knows nothing about what
the levels mean, where they came from, or what is done with the result: every function
takes numbers and ``k`` and returns a number.

**The family.**  Leik's D, Kvalseth's COV and Berry-Mielke's IOV are one family (Weiss
2019), parameterised by the exponent ``q``::

    OV_q = 1 - [ (1/(k-1)) * SUM_{j=0}^{k-2} |2*F_j - 1|^q ]^(1/q)

with ``q = 1`` giving Leik's D and the un-rooted ``q = 2`` giving Berry-Mielke's IOV.
``F_j`` is the cumulative distribution at the ``k-1`` **interior** cutpoints only; see
:func:`cdf_interior` for why the ``k``-th cutpoint is excluded rather than merely
harmless.

**Orientation is a real hazard here, not a pedantic one.**  Published implementations of
this family disagree with each other on which way it points: Blair & Lacy's ``l^2`` is a
normed *concentration* (high = agreement), ``agrmt::dsquared()`` and Stata's ``ordvar``
disagree with one another, and R's ``wINEQ`` publishes ``1 - l^2`` under the Blair-Lacy
name.  Every statistic in this module is therefore stated in the **dispersion**
orientation -- ``0`` = all mass on one level, ``1`` = maximally spread -- and each one
names its endpoints in :data:`STATISTIC_LABELS` so a caller can emit the direction as
data rather than re-deriving it.

**Ordinal validity.**  :func:`iov` and :func:`leik_d` are functions of the *order* of the
levels alone: any strictly increasing relabelling leaves the interior CDF, and hence the
statistic, unchanged.  :func:`mean_level` is not -- it is a function of the level
*values*, so it assumes the levels are equally spaced.  That assumption is a substantive
claim about the scale, and metric summaries of ordinal data are known to invert group
orderings precisely when the groups differ in distributional *shape* (Liddell & Kruschke
2018), so :func:`mean_level` is offered as an explicitly-caveated alternative, never as
the interchangeable equivalent of a dispersion statistic.

**Determinism.**  Cumulative counts are accumulated as exact integers and every sum over
them goes through :func:`math.fsum`, which is exactly rounded and therefore independent
of summation order.  Results are byte-identical run to run and identical for two
differently-ordered constructions of the same sample.

**Degenerate-input policy: raise, do not return a sentinel.**  This departs deliberately
from :mod:`population_synthetic.analysis.utils.stats_tests`, whose estimators report a
skipped-with-a-reason ``{metric: None, "note": ...}`` dict.  That module answers "was
this measurable?" for a report; this one is the arithmetic underneath, and the
"unmeasurable" decision belongs to the caller that knows what an absent measurement
means.  A malformed request (an empty sample, a level off the scale, a mis-sized counts
vector) is a caller bug and is surfaced as an exception.

References
----------
- Berry & Mielke; Blair & Lacy -- the ``q = 2`` member and its concentration-oriented twin.
- Leik (1966), *Pacific Sociological Review* 9(2):85-90 -- the ``q = 1`` member.
- Weiss (2019), *J. Applied Statistics* 46(16):2905-2926 -- the ``OV_q`` unification.
- Wilson (1927), *JASA* 22(158):209-212 -- the score interval in :func:`wilson_interval`.
- Liddell & Kruschke (2018), *JESP* 79:328-348 -- why a metric summary of an ordinal
  scale is a claim, not a convenience.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from numbers import Integral
from statistics import NormalDist
from types import MappingProxyType

__all__ = [
    "STATISTIC_LABELS",
    "cdf_interior",
    "cumulative_count",
    "cumulative_proportion",
    "histogram_counts",
    "iov",
    "leik_d",
    "mean_level",
    "wilson_interval",
]

#: Human-readable label per statistic, **stating its endpoints**.  Exported so a
#: consumer publishes the orientation as data instead of re-wording it at the emission
#: site, where it would drift from the definition it describes (see the module docstring
#: on why this family's orientation cannot be assumed).
STATISTIC_LABELS: Mapping[str, str] = MappingProxyType(
    {
        "iov": "Berry-Mielke IOV (0 = collapsed onto one level, 1 = maximally dispersed)",
        "leik_d": "Leik's D (0 = consensus on one level, 1 = maximally dispersed)",
        "mean_level": (
            "mean level on the 0..k-1 scale (a location measure, not dispersion; "
            "assumes the levels are equally spaced)"
        ),
    }
)


def _check_integral(value: object, what: str) -> int:
    """Return *value* as an ``int``, raising ``TypeError`` if it is not an integer.

    Accepts any :class:`numbers.Integral` (so ``numpy`` integer types pass) but rejects
    ``bool``, which is an ``int`` subclass in Python and would silently read as level 0/1.
    A ``float`` is rejected even when it is integral: a non-integer level means the caller
    averaged something before reaching here, which destroys the ``k``-level support every
    CDF-based statistic in this module is defined on.
    """
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{what} must be an integer, got {value!r} ({type(value).__name__})")
    return int(value)


def _check_scale(k: int) -> int:
    """Return the validated level count *k*, raising below 2 levels."""
    k = _check_integral(k, "k")
    if k < 2:
        raise ValueError(f"k must be >= 2 (a single-level scale has no interior cutpoint), got {k}")
    return k


def _validated_counts(counts: Sequence[int], k: int) -> tuple[list[int], int]:
    """Return ``(counts as ints, total)`` for a well-formed histogram, else raise.

    *k* is required alongside *counts* even though it is implied by ``len(counts)``: a
    mis-sized vector is then a loud error rather than a statistic silently computed on a
    different scale (and so normalised by a different ``k-1``).
    """
    k = _check_scale(k)
    values = list(counts)
    if len(values) != k:
        raise ValueError(f"counts must have exactly k={k} entries (one per level), got {len(values)}")
    resolved: list[int] = []
    for level, count in enumerate(values):
        count = _check_integral(count, f"counts[{level}]")
        if count < 0:
            raise ValueError(f"counts[{level}] must be >= 0, got {count}")
        resolved.append(count)
    total = sum(resolved)
    if total == 0:
        raise ValueError("counts sum to zero; an ordinal statistic over an empty sample is undefined")
    return resolved, total


def histogram_counts(levels: Sequence[int], k: int) -> list[int]:
    """Bin *levels* into the ``k``-entry per-level count vector the statistics take.

    The single normalisation point between "a sample of levels" and "a histogram": every
    other function in this module consumes counts, so a caller holding raw levels passes
    them through here once and the level-range check happens in exactly one place.

    Raises
    ------
    TypeError
        If *k* or any level is not an integer (``bool`` and ``float`` included).
    ValueError
        If ``k < 2``, if *levels* is empty, or if a level falls outside ``[0, k-1]`` --
        an off-scale level is a decoding error, never a value to clamp.
    """
    k = _check_scale(k)
    counts = [0] * k
    seen = 0
    for level in levels:
        level = _check_integral(level, "level")
        if not 0 <= level <= k - 1:
            raise ValueError(f"level {level} is outside the scale [0, {k - 1}]")
        counts[level] += 1
        seen += 1
    if seen == 0:
        raise ValueError("levels is empty; an ordinal statistic over an empty sample is undefined")
    return counts


def cdf_interior(counts: Sequence[int], k: int) -> list[float]:
    """Cumulative distribution at the ``k-1`` **interior** cutpoints ``j = 0 .. k-2``.

    ``F_j = P(level <= j)``, returned in ascending ``j`` order.

    **Why ``F_{k-1}`` is excluded.**  ``F_{k-1} = 1`` for every distribution -- all mass
    lies at or below the top level, by definition -- so it is a constant with zero
    variance across samples, and it is degenerate in each kernel this family is built
    from: ``F*(1-F) = 0``, ``min(F, 1-F) = 0``, ``(F - 0.5)^2 = 0.25``.  Including it
    contributes nothing that varies with the data while forcing the normalising constant
    from ``k-1`` to ``k``, so the statistic could no longer reach its upper endpoint: the
    maximally dispersed 50/50-at-the-extremes distribution would score ``(k-1)/k``
    (0.909 at ``k = 11``) instead of ``1``.  Every normalising constant in this module is
    ``k-1`` for exactly this reason -- there are ``k-1`` interior cutpoints.

    Raises
    ------
    TypeError, ValueError
        Per :func:`_validated_counts`: non-integer or negative counts, a counts vector
        whose length is not *k*, ``k < 2``, or a zero total.
    """
    values, total = _validated_counts(counts, k)
    cumulative = 0
    interior: list[float] = []
    for level in range(k - 1):
        cumulative += values[level]
        interior.append(cumulative / total)
    return interior


def iov(counts: Sequence[int], k: int) -> float:
    """Berry-Mielke index of ordinal variation (IOV) -- the ``q = 2`` member, un-rooted.

    ``IOV = (4/(k-1)) * SUM_{j=0}^{k-2} F_j*(1-F_j)``, equivalently
    ``1 - (4/(k-1)) * SUM_{j=0}^{k-2} (F_j - 0.5)^2`` (the two forms are the same number
    because ``SUM (F_j - 0.5)^2 + SUM F_j*(1-F_j) = (k-1)/4`` identically).

    Range ``[0, 1]`` in the **dispersion** orientation:

    - ``0`` -- all mass on one level (total collapse), whichever level that is;
    - ``1`` -- half the mass on level ``0`` and half on level ``k-1``.

    Higher means *more dispersed*.  This runs opposite to Blair & Lacy's normed
    concentration ``l^2``; see the module docstring, and emit
    ``STATISTIC_LABELS["iov"]`` alongside the number rather than restating it.

    Ordinal-valid: it reads only the interior CDF, so any strictly increasing relabelling
    of the levels leaves it unchanged.  It is also the member of this family that
    separates the two collapse patterns a location or order-blind summary cannot: on
    ``k = 11`` a 50/50 split across ``{0, 10}`` scores ``1.000`` while a 50/50 split
    across ``{9, 10}`` scores ``0.100``, where Shannon entropy, Simpson and
    Berger-Parker are identical on both.
    """
    interior = cdf_interior(counts, k)
    return 4.0 * math.fsum(f * (1.0 - f) for f in interior) / (k - 1)


def leik_d(counts: Sequence[int], k: int) -> float:
    """Leik's D ordinal dispersion -- the ``q = 1`` (L1) sibling of :func:`iov`.

    ``D = (2/(k-1)) * SUM_{j=0}^{k-2} min(F_j, 1-F_j)``, range ``[0, 1]`` in the same
    dispersion orientation as :func:`iov`: ``0`` = consensus on one level, ``1`` = 50/50
    at the two extremes.  Ordinal-valid for the same reason.

    Being an L1 rather than an L2 summary of the same interior CDF, it responds more
    gently to a single far-out cutpoint; the two agree on the endpoints and rank
    distributions almost identically in between.
    """
    interior = cdf_interior(counts, k)
    return 2.0 * math.fsum(min(f, 1.0 - f) for f in interior) / (k - 1)


def mean_level(counts: Sequence[int], k: int) -> float:
    """Mean level ``SUM_j j*p_j`` -- a **location** measure, on ``[0, k-1]``.

    Offered as the readable alternative to :func:`iov`, and it is not a substitute for
    one: it answers "where does this sample sit on the scale?", not "how spread is it?".

    **It is not ordinal-valid.**  It reads the level *values*, so it assumes the levels
    are equally spaced -- a substantive claim about the scale rather than a formality.
    Under a strictly increasing relabelling of the levels (which leaves :func:`iov` and
    :func:`leik_d` untouched) this value moves, and metric summaries of ordinal data are
    known to invert group orderings exactly when the groups differ in shape (Liddell &
    Kruschke 2018).  A caller publishing this statistic is expected to publish that
    caveat with it.
    """
    values, total = _validated_counts(counts, k)
    return math.fsum(level * count for level, count in enumerate(values)) / total


def cumulative_count(counts: Sequence[int], k: int, k0: int) -> int:
    """Number of observations at or below level *k0* -- the numerator of ``P(X <= k0)``.

    Returned separately from :func:`cumulative_proportion` because an interval estimate
    for a proportion needs the raw successes and denominator, not the ratio (see
    :func:`wilson_interval`).

    Raises
    ------
    TypeError, ValueError
        Per :func:`_validated_counts`, plus a *k0* outside ``[0, k-1]``.  ``k0 = k-1`` is
        legal but degenerate: it selects the whole sample, so the proportion is ``1`` by
        construction.
    """
    values, _ = _validated_counts(counts, k)
    k0 = _check_integral(k0, "k0")
    if not 0 <= k0 <= k - 1:
        raise ValueError(f"k0 must lie in [0, {k - 1}], got {k0}")
    return sum(values[: k0 + 1])


def cumulative_proportion(counts: Sequence[int], k: int, k0: int) -> float:
    """``P(X <= k0)`` -- the interior CDF read at one chosen cutpoint, on ``[0, 1]``.

    The assumption-free member of this module: it is a proportion of the sample and makes
    no claim about spacing, ordering beyond the cut itself, or shape.  Its price is
    resolution -- everything on one side of *k0* is one bucket -- so it reads as a
    plain-language companion to a dispersion statistic rather than as one.
    """
    values, total = _validated_counts(counts, k)
    return cumulative_count(values, k, k0) / total


def wilson_interval(successes: int, n: int, *, confidence_level: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion, as ``(lo, hi)``.

    Inverts the score test rather than putting a normal approximation around ``p_hat``
    itself (Wilson 1927).  That matters wherever a proportion approaches its boundary:
    the Wald interval degenerates to zero width at ``p_hat = 0`` or ``1`` and can leave
    ``[0, 1]`` elsewhere, whereas the Wilson interval stays inside ``[0, 1]`` and keeps a
    non-degenerate width at both boundaries.  With ``z`` the two-sided standard-normal
    quantile at *confidence_level*::

        centre = (p_hat + z^2/(2n)) / (1 + z^2/n)
        half   = z * sqrt( p_hat*(1-p_hat)/n + z^2/(4n^2) ) / (1 + z^2/n)

    The endpoints are pinned algebraically rather than left to floating-point
    cancellation: at ``successes = 0`` the two expressions are equal, so ``lo`` is exactly
    ``0.0`` (and ``hi = z^2/(n + z^2)``), and symmetrically ``hi`` is exactly ``1.0`` at
    ``successes = n``.

    Raises
    ------
    TypeError
        If *successes* or *n* is not an integer.
    ValueError
        If ``n < 1``, if *successes* is outside ``[0, n]``, or if *confidence_level* is
        not in the open interval ``(0, 1)``.
    """
    successes = _check_integral(successes, "successes")
    n = _check_integral(n, "n")
    if n < 1:
        raise ValueError(f"n must be >= 1 for a proportion interval, got {n}")
    if not 0 <= successes <= n:
        raise ValueError(f"successes must lie in [0, {n}], got {successes}")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError(f"confidence_level must be in (0, 1), got {confidence_level}")

    z = NormalDist().inv_cdf(1.0 - (1.0 - confidence_level) / 2.0)
    z2 = z * z
    p_hat = successes / n
    denominator = 1.0 + z2 / n
    centre = (p_hat + z2 / (2.0 * n)) / denominator
    half = z * math.sqrt(p_hat * (1.0 - p_hat) / n + z2 / (4.0 * n * n)) / denominator
    lo = 0.0 if successes == 0 else centre - half
    hi = 1.0 if successes == n else centre + half
    return lo, hi
