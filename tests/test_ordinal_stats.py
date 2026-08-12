"""Unit tests for the ordinal-scale dispersion statistics.

Validates :mod:`population_synthetic.analysis.utils.ordinal` -- the interior CDF,
Berry-Mielke IOV, Leik's D, the mean level, the cumulative proportion and the Wilson
score interval -- against hand-computed answers, an algebraic identity, and (for the
Wilson interval) scipy's own implementation, per the statistical-software guide: validate
against an authority, compare floats approximately, and cover every degenerate input.

Three properties carry most of the weight here, because each guards a failure mode that
still returns a plausible number:

- the **identity** ``SUM (F_j - 0.5)^2 + SUM F_j*(1-F_j) = (k-1)/4``, which a sign or
  complement error in either IOV form breaks immediately;
- **ordinal invariance** -- a strictly increasing relabelling of the levels must not move
  the statistic, together with the contrast that the mean *does* move, so the claimed
  distinction between the two is pinned rather than asserted in prose;
- the **endpoints**, including the ``{0, 10}`` vs ``{9, 10}`` separation that motivates
  choosing IOV over an order-blind summary.

Hand derivations are recorded inline next to each expected value so the fixtures are
checkable without rerunning the code.
"""

from __future__ import annotations

import random

import pytest
from scipy.stats import binomtest

from population_synthetic.analysis.utils.ordinal import (
    STATISTIC_LABELS,
    cdf_interior,
    cumulative_count,
    cumulative_proportion,
    histogram_counts,
    iov,
    leik_d,
    mean_level,
    wilson_interval,
)

_K = 11  # the scale this module was built for: integer levels 0..10.


def _counts_at(k: int, **mass: int) -> list[int]:
    """A ``k``-entry counts vector with the given mass placed at named levels."""
    counts = [0] * k
    for level, count in mass.items():
        counts[int(level.lstrip("l"))] = count
    return counts


# --------------------------------------------------------------------------- #
# histogram_counts + cdf_interior                                              #
# --------------------------------------------------------------------------- #


def test_histogram_counts_bins_levels_in_scale_order():
    assert histogram_counts([0, 2, 2, 4], 5) == [1, 0, 2, 0, 1]


def test_cdf_interior_returns_exactly_the_k_minus_one_interior_cutpoints():
    # F_{k-1} = 1 identically and is excluded: it varies with nothing and would cost the
    # statistic its upper endpoint (see the cdf_interior docstring).
    for k in (2, 3, 5, 11):
        counts = [1] * k
        interior = cdf_interior(counts, k)
        assert len(interior) == k - 1
        assert interior[-1] == pytest.approx((k - 1) / k)  # not 1.0


def test_cdf_interior_hand_computed():
    # counts [1, 1, 2], total 4 -> F_0 = 1/4, F_1 = 2/4.
    assert cdf_interior([1, 1, 2], 3) == pytest.approx([0.25, 0.5])


# --------------------------------------------------------------------------- #
# 1.2 -- the identity that guards against a sign / complement error            #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("k", [2, 3, 5, 11, 17])
def test_cdf_identity_holds_over_random_count_vectors(k):
    """``SUM (F_j - 0.5)^2 + SUM F_j*(1-F_j) = (k-1)/4`` for every distribution.

    Algebraically each term is ``F^2 - F + 0.25 + F - F^2 = 0.25`` and there are ``k-1``
    interior cutpoints. A flipped sign or a complement taken on the wrong side of 0.5
    breaks it on the first non-symmetric vector.
    """
    rng = random.Random(20260812 + k)
    for _ in range(25):
        counts = [rng.randint(0, 7) for _ in range(k)]
        if sum(counts) == 0:
            counts[rng.randrange(k)] = 1
        interior = cdf_interior(counts, k)
        squares = sum((f - 0.5) ** 2 for f in interior)
        products = sum(f * (1.0 - f) for f in interior)
        assert squares + products == pytest.approx((k - 1) / 4.0)
        # The two published forms of IOV are therefore the same number.
        assert iov(counts, k) == pytest.approx(1.0 - 4.0 * squares / (k - 1))


# --------------------------------------------------------------------------- #
# 1.3 -- ordinal invariance, and the contrast the mean fails                    #
# --------------------------------------------------------------------------- #

# A strictly increasing relabelling of the 11 levels. Any such map preserves the ORDER of
# every observation, so the ordinal statistics must not move; it does not preserve the
# spacing, so anything reading the level values must.
_RELABEL = {level: value for level, value in enumerate([0, 1, 4, 9, 16, 25, 36, 49, 64, 81, 100])}
_LEVELS = [0, 0, 3, 3, 4, 7, 9, 10, 10, 2, 5, 5, 5, 8]


def _reindex(levels, relabel):
    """Re-encode *levels* through *relabel*, back onto ordinal positions of the new support."""
    support = sorted(relabel.values())
    assert support == list(relabel.values()), "the relabelling must be strictly increasing"
    return [support.index(relabel[level]) for level in levels]


@pytest.mark.parametrize("statistic", [iov, leik_d])
def test_ordinal_statistics_are_invariant_under_a_strictly_increasing_relabelling(statistic):
    original = histogram_counts(_LEVELS, _K)
    relabelled = histogram_counts(_reindex(_LEVELS, _RELABEL), _K)
    assert relabelled == original  # the order is all these statistics can see
    assert statistic(relabelled, _K) == statistic(original, _K)  # exact, not approx


def test_the_mean_moves_under_the_relabelling_the_ordinal_statistics_ignore():
    """The property IOV has and the mean does not -- pinned, not just claimed in prose.

    ``mean_level`` reads the level *values* (via their index on the 0..k-1 scale), so it
    is only defined up to the assumption that those levels are equally spaced. Relabel
    them to any other increasing sequence and the mean of the sample moves, while the
    ordinal statistics above are untouched.
    """
    n = len(_LEVELS)
    mean_on_the_original_scale = sum(_LEVELS) / n
    mean_on_the_relabelled_scale = sum(_RELABEL[level] for level in _LEVELS) / n
    assert mean_level(histogram_counts(_LEVELS, _K), _K) == pytest.approx(mean_on_the_original_scale)
    assert mean_on_the_relabelled_scale != pytest.approx(mean_on_the_original_scale)


# --------------------------------------------------------------------------- #
# 1.4 -- the endpoints, and the {0,10} vs {9,10} separation                     #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("level", [0, 4, 9, 10])
def test_all_mass_on_one_level_is_zero_dispersion(level):
    # Every interior F_j is 0 or 1 -> F*(1-F) = 0 and min(F, 1-F) = 0 at every cutpoint.
    counts = _counts_at(_K, **{f"l{level}": 23})
    assert iov(counts, _K) == 0.0
    assert leik_d(counts, _K) == 0.0


def test_fifty_fifty_at_the_extremes_is_maximal_dispersion():
    # F_j = 0.5 at all 10 interior cutpoints -> SUM F(1-F) = 10*0.25 = 2.5,
    # IOV = (4/10)*2.5 = 1.0; SUM min(F, 1-F) = 10*0.5 = 5, D = (2/10)*5 = 1.0.
    counts = _counts_at(_K, l0=50, l10=50)
    assert iov(counts, _K) == pytest.approx(1.0)
    assert leik_d(counts, _K) == pytest.approx(1.0)


def test_iov_separates_a_full_split_from_a_top_end_split():
    """The distinction that motivates IOV over an order-blind summary.

    ``{0, 10}`` and ``{9, 10}`` are the same two-level 50/50 histogram to Shannon
    entropy, Simpson and Berger-Parker; only a measure that reads *where* the split sits
    tells collapse onto the top of the scale apart from maximal spread.
    """
    full_split = _counts_at(_K, l0=50, l10=50)
    top_end_split = _counts_at(_K, l9=50, l10=50)
    # {9,10}: the only non-zero interior cutpoint is F_9 = 0.5 -> IOV = (4/10)*0.25 = 0.1.
    assert iov(full_split, _K) == pytest.approx(1.000)
    assert iov(top_end_split, _K) == pytest.approx(0.100)


def test_endpoints_hold_for_scales_other_than_eleven_levels():
    # The statistics are general in k, not written for the 11-level case.
    assert iov([1, 1], 2) == pytest.approx(1.0)  # k=2: one cutpoint at F_0 = 0.5
    assert iov([2, 0], 2) == 0.0
    assert iov(_counts_at(5, l0=3, l4=3), 5) == pytest.approx(1.0)
    assert leik_d(_counts_at(5, l2=7), 5) == 0.0


# --------------------------------------------------------------------------- #
# Uniform and hand-computed vectors                                            #
# --------------------------------------------------------------------------- #


def test_uniform_distribution_hand_computed():
    # F_j = (j+1)/11 for j = 0..9.
    # SUM F(1-F) = (1/121) * SUM_{i=1..10} i*(11-i) = (11*55 - 385)/121 = 220/121 = 20/11
    #   -> IOV = (4/10)*(20/11) = 8/11.
    # SUM min(F, 1-F) = (1+2+3+4+5)/11 + (5+4+3+2+1)/11 = 30/11
    #   -> D = (2/10)*(30/11) = 6/11.
    counts = [1] * _K
    assert iov(counts, _K) == pytest.approx(8.0 / 11.0)
    assert leik_d(counts, _K) == pytest.approx(6.0 / 11.0)
    assert mean_level(counts, _K) == pytest.approx(5.0)


def test_small_hand_computed_vectors():
    # counts [1, 1, 2] (k=3): F = [0.25, 0.5].
    # IOV = (4/2)*(0.1875 + 0.25) = 0.875;  D = (2/2)*(0.25 + 0.5) = 0.75;
    # mean = (0*1 + 1*1 + 2*2)/4 = 1.25.
    assert iov([1, 1, 2], 3) == pytest.approx(0.875)
    assert leik_d([1, 1, 2], 3) == pytest.approx(0.75)
    assert mean_level([1, 1, 2], 3) == pytest.approx(1.25)

    # counts [3, 0, 1] (k=3): F = [0.75, 0.75].
    # IOV = (4/2)*(0.1875 + 0.1875) = 0.75;  D = (2/2)*(0.25 + 0.25) = 0.5;  mean = 0.5.
    assert iov([3, 0, 1], 3) == pytest.approx(0.75)
    assert leik_d([3, 0, 1], 3) == pytest.approx(0.5)
    assert mean_level([3, 0, 1], 3) == pytest.approx(0.5)


def test_dispersion_does_not_depend_on_where_the_mass_sits_only_how_it_is_ordered():
    # Two adjacent levels at 50/50 give the same dispersion wherever the pair sits.
    assert iov(_counts_at(_K, l0=4, l1=4), _K) == pytest.approx(iov(_counts_at(_K, l9=4, l10=4), _K))


# --------------------------------------------------------------------------- #
# cumulative_count / cumulative_proportion                                     #
# --------------------------------------------------------------------------- #


def test_cumulative_proportion_is_the_cdf_read_at_one_cutpoint():
    counts = [1, 1, 2, 4]  # total 8
    assert cumulative_count(counts, 4, 0) == 1
    assert cumulative_proportion(counts, 4, 0) == pytest.approx(0.125)
    assert cumulative_proportion(counts, 4, 2) == pytest.approx(0.5)
    assert cumulative_proportion(counts, 4, 2) == pytest.approx(cdf_interior(counts, 4)[2])


def test_cumulative_proportion_at_the_top_level_is_one_by_construction():
    # Legal but degenerate: the cut selects the whole sample.
    assert cumulative_proportion([1, 1, 2, 4], 4, 3) == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Determinism                                                                  #
# --------------------------------------------------------------------------- #


def test_repeated_calls_return_the_identical_float():
    counts = _counts_at(_K, l0=3, l4=17, l7=5, l9=41, l10=2)
    for statistic in (iov, leik_d, mean_level):
        assert statistic(counts, _K) == statistic(counts, _K)  # exact equality, not approx


def test_differently_ordered_but_equivalent_input_gives_the_identical_float():
    """Byte-reproducibility must not depend on the order the sample was assembled in."""
    levels = [9, 0, 4, 9, 10, 4, 9, 7, 4, 9]
    shuffled = list(levels)
    random.Random(4).shuffle(shuffled)
    assert shuffled != levels
    ascending = histogram_counts(sorted(levels), _K)
    scrambled = histogram_counts(shuffled, _K)
    assert scrambled == ascending
    assert iov(scrambled, _K) == iov(ascending, _K)
    assert leik_d(scrambled, _K) == leik_d(ascending, _K)
    assert mean_level(scrambled, _K) == mean_level(ascending, _K)


# --------------------------------------------------------------------------- #
# Every raise path -- a malformed request is a caller bug, never a sentinel     #
# --------------------------------------------------------------------------- #


def test_empty_sample_raises():
    with pytest.raises(ValueError, match="empty sample"):
        histogram_counts([], _K)
    with pytest.raises(ValueError, match="empty sample"):
        iov([0] * _K, _K)  # zero total count


@pytest.mark.parametrize("k", [1, 0, -3])
def test_a_scale_with_fewer_than_two_levels_raises(k):
    with pytest.raises(ValueError, match="k must be >= 2"):
        histogram_counts([0], k)
    with pytest.raises(ValueError, match="k must be >= 2"):
        iov([1] * max(k, 1), k)


@pytest.mark.parametrize("level", [-1, 11, 42])
def test_a_level_outside_the_scale_raises(level):
    with pytest.raises(ValueError, match="outside the scale"):
        histogram_counts([0, 1, level], _K)


@pytest.mark.parametrize("level", [3.0, 2.5, True, "4", None])
def test_a_non_integer_level_raises(level):
    # 3.0 is rejected too: a fractional level means the caller averaged something, which
    # destroys the k-level support these statistics are defined on.
    with pytest.raises(TypeError, match="must be an integer"):
        histogram_counts([0, level], _K)


def test_a_mis_sized_counts_vector_raises():
    with pytest.raises(ValueError, match="exactly k=11"):
        iov([1] * 10, _K)
    with pytest.raises(ValueError, match="exactly k=11"):
        leik_d([1] * 12, _K)


def test_a_negative_count_raises():
    counts = _counts_at(_K, l3=5)
    counts[7] = -1
    with pytest.raises(ValueError, match=r"counts\[7\] must be >= 0"):
        iov(counts, _K)


@pytest.mark.parametrize("count", [1.5, 2.0, True, "3"])
def test_a_non_integer_count_raises(count):
    counts: list = _counts_at(_K, l3=5)
    counts[1] = count
    with pytest.raises(TypeError, match="must be an integer"):
        iov(counts, _K)


@pytest.mark.parametrize("k0", [-1, 11, 99])
def test_a_cutpoint_outside_the_scale_raises(k0):
    with pytest.raises(ValueError, match=r"k0 must lie in \[0, 10\]"):
        cumulative_proportion([1] * _K, _K, k0)


def test_a_non_integer_cutpoint_raises():
    with pytest.raises(TypeError, match="must be an integer"):
        cumulative_count([1] * _K, _K, 5.0)


# --------------------------------------------------------------------------- #
# wilson_interval -- pinned to scipy.stats.binomtest(...).proportion_ci        #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("successes", "n", "level"),
    [(0, 10, 0.95), (5, 10, 0.95), (15, 20, 0.95), (10, 10, 0.95), (2, 50, 0.99), (1, 3, 0.90)],
)
def test_wilson_matches_scipy(successes, n, level):
    lo, hi = wilson_interval(successes, n, confidence_level=level)
    reference = binomtest(successes, n).proportion_ci(confidence_level=level, method="wilson")
    assert lo == pytest.approx(float(reference.low), abs=1e-12)
    assert hi == pytest.approx(float(reference.high), abs=1e-12)


def test_wilson_published_values():
    # The textbook 95% examples: 0/10 -> (0, 0.2775), 5/10 -> (0.2366, 0.7634).
    assert wilson_interval(0, 10) == pytest.approx((0.0, 0.27753), abs=1e-5)
    assert wilson_interval(5, 10) == pytest.approx((0.23659, 0.76341), abs=1e-5)


def test_wilson_boundaries_are_exact_and_non_degenerate():
    """The reason for choosing Wilson: the Wald interval collapses to zero width here."""
    lo, hi = wilson_interval(0, 40)
    assert lo == 0.0                       # exactly, not -1e-17
    assert hi > 0.0                        # and still an interval, not a point
    lo, hi = wilson_interval(40, 40)
    assert hi == 1.0
    assert lo < 1.0


@pytest.mark.parametrize("n", [1, 3, 10, 97])
def test_wilson_brackets_the_observed_proportion_and_stays_in_the_unit_interval(n):
    for successes in range(n + 1):
        lo, hi = wilson_interval(successes, n)
        assert 0.0 <= lo <= successes / n <= hi <= 1.0


def test_wilson_rejects_a_malformed_request():
    with pytest.raises(ValueError, match="n must be >= 1"):
        wilson_interval(0, 0)
    with pytest.raises(ValueError, match=r"successes must lie in \[0, 5\]"):
        wilson_interval(6, 5)
    with pytest.raises(ValueError, match=r"successes must lie in \[0, 5\]"):
        wilson_interval(-1, 5)
    with pytest.raises(ValueError, match=r"confidence_level must be in \(0, 1\)"):
        wilson_interval(1, 5, confidence_level=1.0)
    with pytest.raises(ValueError, match=r"confidence_level must be in \(0, 1\)"):
        wilson_interval(1, 5, confidence_level=0.0)
    with pytest.raises(TypeError, match="must be an integer"):
        wilson_interval(1.5, 5)


# --------------------------------------------------------------------------- #
# The published orientation                                                    #
# --------------------------------------------------------------------------- #


def test_every_shipped_statistic_has_a_label_that_states_its_endpoints():
    """Implementations of this family disagree on direction, so it travels as data."""
    assert set(STATISTIC_LABELS) == {"iov", "leik_d", "mean_level"}
    assert STATISTIC_LABELS["iov"] == (
        "Berry-Mielke IOV (0 = collapsed onto one level, 1 = maximally dispersed)"
    )
    for label in STATISTIC_LABELS.values():
        assert "0 = " in label or "0.." in label


def test_the_label_table_is_immutable():
    with pytest.raises(TypeError):
        STATISTIC_LABELS["iov"] = "something else"  # type: ignore[index]
