"""Unit tests for the method/model-significance statistical primitives.

Validates the in-house re-implementations (Page's L, Friedman's Kendall's W,
Cliff's delta) against hand-computed / textbook values, and pins the
library-backed primitives (Nemenyi, Benjamini-Hochberg, the mixed-logit
interaction) to the underlying library's own output on a fixture -- per the
statistical-software guide (validate against an authority, compare floats
approximately, cover degenerate inputs).  Tests that need the optional
``[analysis]`` extra (scikit-posthocs / statsmodels) skip gracefully when it is
not installed.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy import stats

from population_synthetic.analysis.utils.stats_tests import (
    benjamini_hochberg,
    cliffs_delta,
    friedman_test,
    mixed_logit_interaction,
    nemenyi_posthoc,
    page_trend_test,
)

# --------------------------------------------------------------------------- #
# page_trend_test -- hand-computed L and z                                     #
# --------------------------------------------------------------------------- #

def test_page_trend_perfect_increasing():
    # Each block ranks 1..5 in ascending column order; order = identity.
    # R_j = N*j = [4,8,12,16,20]; L = sum j*R_j = 220.
    # mu = N*k*(k+1)^2/4 = 180; var = N*k^2*(k+1)*(k^2-1)/144 = 100 -> z = 4.0.
    blocks = [[1, 2, 3, 4, 5]] * 4
    res = page_trend_test(blocks, order=[0, 1, 2, 3, 4])
    assert res["L"] == pytest.approx(220.0)
    assert res["z"] == pytest.approx(4.0)
    assert res["p"] == pytest.approx(float(stats.norm.sf(4.0)))
    assert res["k"] == 5 and res["n"] == 4


def test_page_trend_order_mapping_reverses_sign():
    # Same data, reversed predicted order -> mirror-image L and z.
    blocks = [[1, 2, 3, 4, 5]] * 4
    res = page_trend_test(blocks, order=[4, 3, 2, 1, 0])
    assert res["L"] == pytest.approx(140.0)
    assert res["z"] == pytest.approx(-4.0)


def test_page_trend_ties_average_ranks():
    # A block that is all-equal contributes average ranks (all 3.0 for k=5),
    # so it shifts every rank sum equally and cannot fabricate a trend.
    blocks = [[1, 2, 3, 4, 5], [7, 7, 7, 7, 7]]
    res = page_trend_test(blocks, order=[0, 1, 2, 3, 4])
    # rank sums: [1+3, 2+3, 3+3, 4+3, 5+3] = [4,5,6,7,8]; L = 1*4+2*5+3*6+4*7+5*8 = 100
    assert res["L"] == pytest.approx(100.0)


def test_page_trend_bad_order_raises():
    with pytest.raises(ValueError):
        page_trend_test([[1, 2, 3], [3, 2, 1]], order=[0, 1, 1])


def test_page_trend_degenerate():
    assert page_trend_test([[1, 2, 3]], order=[0, 1, 2])["L"] is None  # <2 blocks
    res = page_trend_test([[1], [1]], order=[0])                       # <2 treatments
    assert res["z"] is None and "note" in res


def test_page_trend_nan_fails_loud():
    with pytest.raises(ValueError):
        page_trend_test([[1.0, 2.0], [float("nan"), 3.0]], order=[0, 1])


# --------------------------------------------------------------------------- #
# friedman_test -- Kendall's W + Iman-Davenport, pinned to scipy               #
# --------------------------------------------------------------------------- #

def test_friedman_perfect_concordance():
    # Identical ascending blocks -> perfect concordance: chi2 = N*(k-1), W = 1.
    blocks = [[1, 2, 3]] * 3
    res = friedman_test(blocks)
    chi2_scipy, p_scipy = stats.friedmanchisquare(*np.asarray(blocks, float).T)
    assert res["chi2"] == pytest.approx(float(chi2_scipy))
    assert res["p"] == pytest.approx(float(p_scipy))
    assert res["chi2"] == pytest.approx(3 * (3 - 1))  # = 6
    assert res["kendalls_w"] == pytest.approx(1.0)
    # W == 1 -> Iman-Davenport denominator 0 -> F = inf, p_f = 0 (explicit, not NaN).
    assert math.isinf(res["iman_davenport_f"])
    assert res["p_f"] == 0.0


def test_friedman_matches_scipy_general():
    blocks = [[1, 2, 3, 4], [2, 1, 4, 3], [1, 3, 2, 4], [2, 1, 3, 4], [1, 2, 4, 3]]
    res = friedman_test(blocks)
    chi2_scipy, p_scipy = stats.friedmanchisquare(*np.asarray(blocks, float).T)
    assert res["chi2"] == pytest.approx(float(chi2_scipy))
    assert res["p"] == pytest.approx(float(p_scipy))
    n, k = 5, 4
    assert res["kendalls_w"] == pytest.approx(float(chi2_scipy) / (n * (k - 1)))
    # Iman-Davenport F recomputed independently.
    denom = n * (k - 1) - float(chi2_scipy)
    f_expected = (n - 1) * float(chi2_scipy) / denom
    assert res["iman_davenport_f"] == pytest.approx(f_expected)
    assert res["df1"] == k - 1 and res["df2"] == (k - 1) * (n - 1)


def test_friedman_degenerate():
    assert friedman_test([[1, 2, 3]])["chi2"] is None            # <2 blocks
    res = friedman_test([[1], [2]])                              # <2 treatments
    assert res["chi2"] is None and "note" in res


# --------------------------------------------------------------------------- #
# cliffs_delta -- hand-computed                                                #
# --------------------------------------------------------------------------- #

def test_cliffs_delta_extremes():
    assert cliffs_delta([1, 2, 3], [4, 5, 6])["delta"] == pytest.approx(-1.0)
    assert cliffs_delta([1, 2, 3], [4, 5, 6])["magnitude"] == "large"
    assert cliffs_delta([10, 20, 30], [1, 2, 3])["delta"] == pytest.approx(1.0)


def test_cliffs_delta_overlap_medium():
    # a=[1,2,3,4] vs b=[2,3,4,5]: sum of signs = -7 over 16 pairs = -0.4375 (medium).
    res = cliffs_delta([1, 2, 3, 4], [2, 3, 4, 5])
    assert res["delta"] == pytest.approx(-7.0 / 16.0)
    assert res["magnitude"] == "medium"


def test_cliffs_delta_negligible_and_identical():
    assert cliffs_delta([1, 2, 3], [1, 2, 3])["delta"] == pytest.approx(0.0)
    assert cliffs_delta([1, 2, 3], [1, 2, 3])["magnitude"] == "negligible"


def test_cliffs_delta_empty_raises():
    with pytest.raises(ValueError):
        cliffs_delta([], [1, 2, 3])


# --------------------------------------------------------------------------- #
# nemenyi_posthoc -- pinned to scikit-posthocs + independent CD formula        #
# --------------------------------------------------------------------------- #

def test_nemenyi_matches_library_and_cd():
    sp = pytest.importorskip("scikit_posthocs")
    matrix = np.array(
        [[1, 2, 3, 4], [2, 1, 4, 3], [1, 3, 2, 4], [2, 1, 3, 4], [1, 2, 4, 3]],
        dtype=float,
    )
    res = nemenyi_posthoc(matrix, alpha=0.05)
    expected = sp.posthoc_nemenyi_friedman(matrix).to_numpy(dtype=float)
    np.testing.assert_allclose(np.asarray(res["p_matrix"]), expected, rtol=1e-9)
    n, k = 5, 4
    q_alpha = stats.studentized_range.ppf(0.95, k, np.inf) / math.sqrt(2.0)
    cd_expected = q_alpha * math.sqrt(k * (k + 1) / (6.0 * n))
    assert res["q_alpha"] == pytest.approx(q_alpha)
    assert res["cd"] == pytest.approx(cd_expected)


def test_nemenyi_degenerate():
    res = nemenyi_posthoc([[1, 2, 3]])  # <2 blocks -> no library call
    assert res["p_matrix"] is None and "note" in res


# --------------------------------------------------------------------------- #
# benjamini_hochberg -- pinned to statsmodels                                  #
# --------------------------------------------------------------------------- #

def test_benjamini_hochberg_matches_statsmodels():
    multitest = pytest.importorskip("statsmodels.stats.multitest")
    pvals = [0.01, 0.02, 0.03, 0.5, 0.005]
    _, expected, _, _ = multitest.multipletests(pvals, method="fdr_bh")
    got = benjamini_hochberg(pvals)
    np.testing.assert_allclose(got, expected, rtol=1e-12)
    # Order is preserved (input order, not sorted).
    assert len(got) == len(pvals)


def test_benjamini_hochberg_empty():
    assert benjamini_hochberg([]) == []


# --------------------------------------------------------------------------- #
# mixed_logit_interaction -- pinned to a direct statsmodels fit                #
# --------------------------------------------------------------------------- #

def _interaction_frame():
    pd = pytest.importorskip("pandas")
    rng = np.random.default_rng(0)
    rows = []
    for cat in range(6):
        cat_intercept = rng.normal(0, 0.5)
        for model in ("A", "B", "C"):
            for mr in (1, 2, 3, 4, 5):
                tv = 0.2 + 0.03 * mr + (0.02 * mr if model == "B" else 0.0)
                tv += cat_intercept + rng.normal(0, 0.05)
                tv = min(max(tv, 0.0), 1.0)
                rows.append((cat, model, mr, tv))
    return pd.DataFrame(rows, columns=["category", "model", "method_rank", "tv"])


def test_mixed_logit_interaction_pins_to_statsmodels():
    pytest.importorskip("statsmodels")
    from scipy.special import logit

    frame = _interaction_frame()
    res = mixed_logit_interaction(frame)
    assert res["converged"] is True

    # Independently reproduce the fit + Wald test to pin the interaction p-value.
    import statsmodels.api as sm

    df = frame.copy()
    m = len(df)
    y = df["tv"].to_numpy(float)
    df["_y"] = logit((y * (m - 1) + 0.5) / m)
    md = sm.MixedLM.from_formula("_y ~ C(model) * method_rank", groups="category", data=df)
    fit = md.fit()
    terms = [n for n in fit.fe_params.index if ":" in n]
    w = fit.wald_test(terms, scalar=True)
    assert res["interaction"]["p"] == pytest.approx(float(w.pvalue), rel=1e-6)
    assert res["interaction"]["stat"] == pytest.approx(float(w.statistic), rel=1e-6)

    # eta^2-style shares are a normalised 4-way partition.
    eta = res["eta_sq"]
    assert set(eta) == {"model", "method", "category", "residual"}
    assert sum(eta.values()) == pytest.approx(1.0)
    assert all(0.0 <= v <= 1.0 for v in eta.values())


def test_mixed_logit_interaction_missing_columns_raises():
    pd = pytest.importorskip("pandas")
    pytest.importorskip("statsmodels")
    bad = pd.DataFrame({"tv": [0.1, 0.2], "model": ["A", "B"]})
    with pytest.raises(ValueError):
        mixed_logit_interaction(bad)


def test_mixed_logit_interaction_needs_two_models():
    pd = pytest.importorskip("pandas")
    pytest.importorskip("statsmodels")
    frame = pd.DataFrame(
        {"tv": [0.1, 0.2, 0.3, 0.4], "model": ["A"] * 4,
         "method_rank": [1, 2, 1, 2], "category": [0, 0, 1, 1]}
    )
    with pytest.raises(ValueError):
        mixed_logit_interaction(frame)


# --------------------------------------------------------------------------- #
# paired_t_pairwise -- confidence interval of the mean paired difference       #
# --------------------------------------------------------------------------- #

def _paired_matrix() -> np.ndarray:
    rng = np.random.default_rng(20260916)
    base = rng.uniform(0.2, 0.8, size=(10, 1))
    return base + rng.normal(0.0, 0.05, size=(10, 4)) + np.array([0.0, 0.03, 0.08, 0.2])


@pytest.mark.parametrize("level", [0.9, 0.95, 0.99])
def test_paired_t_interval_matches_scipy_t_interval(level):
    from population_synthetic.analysis.utils.stats_tests import paired_t_pairwise

    matrix = _paired_matrix()
    labels = ["m0", "m1", "m2", "m3"]
    pairs = paired_t_pairwise(matrix, labels=labels, confidence_level=level)["pairs"]
    n = matrix.shape[0]
    for i in range(4):
        for j in range(i + 1, 4):
            diff = matrix[:, j] - matrix[:, i]
            rec = pairs[f"{labels[i]}|{labels[j]}"]
            sd = float(np.std(diff, ddof=1))
            low, high = stats.t.interval(level, n - 1, loc=diff.mean(), scale=sd / math.sqrt(n))
            assert rec["sd_diff"] == pytest.approx(sd, abs=1e-12)
            assert rec["ci_low"] == pytest.approx(float(low), abs=1e-12)
            assert rec["ci_high"] == pytest.approx(float(high), abs=1e-12)
            assert rec["ci_low"] < rec["mean_diff"] < rec["ci_high"]


def test_paired_t_bit_identical_columns_give_zero_sd_and_no_interval():
    from population_synthetic.analysis.utils.stats_tests import paired_t_pairwise

    matrix = _paired_matrix()
    matrix[:, 1] = matrix[:, 0]
    out = paired_t_pairwise(matrix, labels=["a", "b", "c", "d"], confidence_level=0.95)
    rec = out["pairs"]["a|b"]
    assert rec["sd_diff"] == 0.0
    assert rec["ci_low"] is None and rec["ci_high"] is None
    assert rec["p_raw"] is None and rec["p_holm"] is None
    assert sum(1 for r in out["pairs"].values() if r["p_holm"] is not None) == 5


def test_paired_t_confidence_level_is_required():
    from population_synthetic.analysis.utils.stats_tests import paired_t_pairwise

    with pytest.raises(TypeError):
        paired_t_pairwise(_paired_matrix(), labels=["a", "b", "c", "d"])


@pytest.mark.parametrize("level", [0, 0.0, 1, 1.0, 1.2, -0.5, True])
def test_paired_t_confidence_level_outside_the_open_unit_interval_raises(level):
    from population_synthetic.analysis.utils.stats_tests import paired_t_pairwise

    with pytest.raises(ValueError, match="confidence_level"):
        paired_t_pairwise(_paired_matrix(), labels=["a", "b", "c", "d"], confidence_level=level)


# =========================================================================== #
# Typicality effect sizes and the closeness complete-block tests              #
# (epsilon^2, Mann-Whitney, Cliff's delta via histograms + its bootstrap CI,   #
#  complete_block_matrix, Conover-Friedman).  Golden values come from the      #
#  prototype under docs/development/plans/active/typicality-distribution-grid/ #
# =========================================================================== #

from tests._closeness_fixtures import LETTERS, STRATEGIES, combination_outcomes  # noqa: E402


def test_epsilon_squared_golden_and_identity():
    from population_synthetic.analysis.utils.stats_tests import epsilon_squared

    # golden/omnibus_kruskal_epsilon2.csv: model factor H = 564.14, N = 5760 -> 0.0980.
    assert round(epsilon_squared(564.14, 5760), 4) == 0.0980
    h, n = 12.5, 40
    assert epsilon_squared(h, n) == pytest.approx(h * (n + 1) / (n**2 - 1), rel=1e-12)


@pytest.mark.parametrize("h,n", [(1.0, 1), (1.0, 0), (-0.1, 10), (float("nan"), 10), (1.0, 2.5), (1.0, True)])
def test_epsilon_squared_rejects_undefined_input(h, n):
    from population_synthetic.analysis.utils.stats_tests import epsilon_squared

    with pytest.raises(ValueError):
        epsilon_squared(h, n)


def test_mann_whitney_matches_scipy_and_the_delta_identity():
    from population_synthetic.analysis.utils.stats_tests import cliffs_delta, mann_whitney_test

    a = [3, 4, 2, 6, 2, 5]
    b = [9, 7, 5, 10, 6, 8]
    res = mann_whitney_test(a, b)
    ref = stats.mannwhitneyu(a, b, alternative="two-sided", method="asymptotic")
    assert res["U"] == pytest.approx(float(ref.statistic))
    assert res["p"] == pytest.approx(float(ref.pvalue))
    assert (res["n_a"], res["n_b"], res["alternative"], res["method"]) == (6, 6, "two-sided", "asymptotic")
    # Hand count: U_a = pairs a > b + ties / 2 = 1 (6 > 5) + 0.5 (5 = 5) + 0.5 (6 = 6) = 2.
    assert res["U"] == pytest.approx(2.0)
    assert 2 * res["U"] / 36 - 1 == pytest.approx(cliffs_delta(a, b)["delta"])


@pytest.mark.parametrize("a,b", [([], [1.0]), ([1.0], []), ([1.0, float("nan")], [2.0])])
def test_mann_whitney_rejects_empty_or_nan(a, b):
    from population_synthetic.analysis.utils.stats_tests import mann_whitney_test

    with pytest.raises(ValueError):
        mann_whitney_test(a, b)


def test_cliffs_delta_from_histograms_equals_the_sign_matrix():
    from population_synthetic.analysis.utils.stats_tests import cliffs_delta, cliffs_delta_from_histograms

    rng = np.random.default_rng(3)
    for _ in range(25):
        a = rng.integers(0, 11, size=rng.integers(1, 60))
        b = rng.integers(0, 11, size=rng.integers(1, 60))
        h_a = np.bincount(a, minlength=11)
        h_b = np.bincount(b, minlength=11)
        assert cliffs_delta_from_histograms(h_a, h_b) == pytest.approx(cliffs_delta(a, b)["delta"], abs=1e-12)


def test_cliffs_delta_from_histograms_fractional_weights_hand_worked():
    from population_synthetic.analysis.utils.stats_tests import cliffs_delta_from_histograms

    # a: survivors with rounds (8, 9), (9), (10, 10) -> weights 8: 0.5, 9: 1.5, 10: 1.0.
    # b: one individual at 9. P(X > Y) = 1/3, P(X < Y) = 0.5/3 -> delta = 1/6.
    h_a = np.zeros(11)
    h_a[[8, 9, 10]] = [0.5, 1.5, 1.0]
    h_b = np.zeros(11)
    h_b[9] = 1.0
    assert cliffs_delta_from_histograms(h_a, h_b) == pytest.approx(1.0 / 6.0)


def test_cliffs_delta_from_histograms_golden_prototype_values():
    from population_synthetic.analysis.utils.stats_tests import cliffs_delta_from_histograms
    from tests._closeness_fixtures import first_round_histograms

    keys, counts, reference = first_round_histograms()
    expected = {(r["model"], r["strategy"]): r["delta"] for r in combination_outcomes()}
    got = cliffs_delta_from_histograms(counts, reference[None, :])
    assert got.shape == (58,)
    for key, value in zip(keys, got):
        assert value == pytest.approx(expected[key], abs=1e-12)


def test_bootstrap_cliffs_delta_point_is_cliffs_delta_on_tied_samples():
    from population_synthetic.analysis.utils.stats_tests import bootstrap_cliffs_delta_ci, cliffs_delta

    rng = np.random.default_rng(11)
    a = rng.integers(0, 11, size=80) / 2.0
    b = rng.integers(0, 11, size=60) / 2.0
    res = bootstrap_cliffs_delta_ci(a, b, iterations=500, ci_level=0.95, seed=1)
    assert res["point"] == pytest.approx(cliffs_delta(a, b)["delta"], abs=1e-15)
    assert res["lo"] <= res["point"] <= res["hi"]
    assert set(res) == {"point", "lo", "hi", "ci_level", "iterations", "n_a", "n_b", "method"}
    assert (res["n_a"], res["n_b"], res["method"]) == (80, 60, "percentile")


def test_bootstrap_cliffs_delta_key_set_matches_the_difference_ci():
    from population_synthetic.analysis.utils.stats_tests import bootstrap_cliffs_delta_ci, bootstrap_difference_ci

    a, b = [1.0, 2.0, 3.0], [2.0, 3.0, 4.0]
    got = bootstrap_cliffs_delta_ci(a, b, iterations=10, ci_level=0.9, seed=0)
    assert set(got) == set(bootstrap_difference_ci(a, b, iterations=10, ci_level=0.9, seed=0))


def test_bootstrap_cliffs_delta_identical_and_separated_samples():
    from population_synthetic.analysis.utils.stats_tests import bootstrap_cliffs_delta_ci

    same = bootstrap_cliffs_delta_ci([1, 2, 3], [1, 2, 3], iterations=200, ci_level=0.95, seed=4)
    assert same["point"] == 0.0
    separated = bootstrap_cliffs_delta_ci([5, 6, 7], [1, 2, 3], iterations=200, ci_level=0.95, seed=4)
    assert (separated["point"], separated["lo"], separated["hi"]) == (1.0, 1.0, 1.0)


def test_bootstrap_cliffs_delta_is_seeded_and_mirrors_exactly_on_swap():
    from population_synthetic.analysis.utils.stats_tests import bootstrap_cliffs_delta_ci

    rng = np.random.default_rng(5)
    a = rng.integers(0, 11, size=70)
    b = rng.integers(0, 11, size=90)
    first = bootstrap_cliffs_delta_ci(a, b, iterations=400, ci_level=0.95, seed=9)
    again = bootstrap_cliffs_delta_ci(a, b, iterations=400, ci_level=0.95, seed=9)
    swapped = bootstrap_cliffs_delta_ci(b, a, iterations=400, ci_level=0.95, seed=9)
    assert first == again
    assert swapped["point"] == pytest.approx(-first["point"], abs=1e-15)
    assert swapped["lo"] == pytest.approx(-first["hi"], abs=1e-12)
    assert swapped["hi"] == pytest.approx(-first["lo"], abs=1e-12)


def test_bootstrap_cliffs_delta_agrees_with_a_naive_element_bootstrap():
    from population_synthetic.analysis.utils.stats_tests import bootstrap_cliffs_delta_ci, cliffs_delta

    # The counts-based resampling must be distributionally the same as resampling elements.
    rng = np.random.default_rng(21)
    a = rng.integers(0, 11, size=60)
    b = rng.integers(2, 11, size=50)
    res = bootstrap_cliffs_delta_ci(a, b, iterations=4000, ci_level=0.9, seed=2)
    naive_rng = np.random.default_rng(99)
    naive = [cliffs_delta(naive_rng.choice(a, a.size), naive_rng.choice(b, b.size))["delta"] for _ in range(4000)]
    lo, hi = np.quantile(naive, [0.05, 0.95])
    assert res["lo"] == pytest.approx(lo, abs=0.03)
    assert res["hi"] == pytest.approx(hi, abs=0.03)


@pytest.mark.parametrize(
    "kwargs",
    [dict(iterations=0, ci_level=0.95), dict(iterations=10, ci_level=1.0), dict(iterations=10, ci_level=0.0)],
)
def test_bootstrap_cliffs_delta_rejects_a_malformed_request(kwargs):
    from population_synthetic.analysis.utils.stats_tests import bootstrap_cliffs_delta_ci

    with pytest.raises(ValueError):
        bootstrap_cliffs_delta_ci([1, 2], [2, 3], seed=0, **kwargs)


def test_bootstrap_cliffs_delta_empty_sample_raises():
    from population_synthetic.analysis.utils.stats_tests import bootstrap_cliffs_delta_ci

    with pytest.raises(ValueError):
        bootstrap_cliffs_delta_ci([], [1.0], iterations=10, ci_level=0.95, seed=0)


def test_percentile_interval_one_and_two_dimensional():
    from population_synthetic.analysis.utils.stats_tests import percentile_interval

    lo, hi = percentile_interval(np.arange(101, dtype=float), ci_level=0.9)
    assert isinstance(lo, float) and (lo, hi) == pytest.approx((5.0, 95.0), abs=1e-12)
    lo2, hi2 = percentile_interval(np.stack([np.arange(101.0), -np.arange(101.0)], axis=1), ci_level=0.9)
    assert lo2.tolist() == pytest.approx([5.0, -95.0], abs=1e-12)
    assert hi2.tolist() == pytest.approx([95.0, -5.0], abs=1e-12)
    with pytest.raises(ValueError):
        percentile_interval([1.0, float("nan")], ci_level=0.9)
    with pytest.raises(ValueError):
        percentile_interval([], ci_level=0.9)


def test_complete_block_matrix_drops_absent_and_none_cells():
    from population_synthetic.analysis.utils.stats_tests import complete_block_matrix

    cells = {"m1": {"A": 1.0, "B": 2.0}, "m2": {"A": 3.0}, "m3": {"A": None, "B": 4.0}, "m4": {"B": 6.0, "A": 5.0}}
    matrix, complete, dropped = complete_block_matrix(cells, ["m1", "m2", "m3", "m4"], ["A", "B"])
    assert matrix.tolist() == [[1.0, 2.0], [5.0, 6.0]]
    assert complete == ["m1", "m4"] and dropped == ["m2", "m3"]
    empty, none_kept, _ = complete_block_matrix({"m2": {"A": 1.0}}, ["m2"], ["A", "B"])
    assert empty.shape == (0, 2) and none_kept == []


def _golden_grid(outcome: str) -> tuple[np.ndarray, list[str], list[str]]:
    from population_synthetic.analysis.utils.stats_tests import complete_block_matrix

    cells: dict[str, dict[str, float]] = {}
    for r in combination_outcomes():
        cells.setdefault(r["model"], {})[r["strategy"]] = r[outcome]
    return complete_block_matrix(cells, list(cells), STRATEGIES)


def test_friedman_on_complete_blocks_golden():
    grid, complete, dropped = _golden_grid("delta")
    assert grid.shape == (10, 5)
    assert dropped == ["ollama_deepseek_r1_14b", "ollama_gemma4_e4b"]
    # closeness/complete_block_tests.json (delta) and closeness_shape/complete_block_tests.json (tv).
    by_strategy = friedman_test(grid)
    assert by_strategy["chi2"] == pytest.approx(27.2, abs=1e-9)
    assert by_strategy["kendalls_w"] == pytest.approx(0.68, abs=1e-12)
    assert by_strategy["p"] == pytest.approx(1.811122816736785e-05, rel=1e-9)
    by_model = friedman_test(grid.T)
    assert by_model["chi2"] == pytest.approx(23.00727272727275, rel=1e-12)
    assert by_model["kendalls_w"] == pytest.approx(0.5112727272727278, rel=1e-12)
    tv_grid, _, _ = _golden_grid("tv")
    assert friedman_test(tv_grid)["kendalls_w"] == pytest.approx(0.5611111111111111, rel=1e-12)
    assert friedman_test(tv_grid.T)["chi2"] == pytest.approx(16.895504252733918, rel=1e-12)


def test_paired_t_on_complete_blocks_golden():
    from population_synthetic.analysis.utils.stats_tests import paired_t_pairwise

    grid, _, _ = _golden_grid("delta")
    pairs = paired_t_pairwise(grid, labels=LETTERS, confidence_level=0.95)["pairs"]
    # closeness/posthoc_pairs.csv, factor = strategy, outcome = delta.
    assert pairs["A|B"]["mean_diff"] == pytest.approx(0.13782636363636355, rel=1e-12)
    assert pairs["A|B"]["dz"] == pytest.approx(1.7107564108743898, rel=1e-12)
    assert pairs["A|B"]["p_holm"] == pytest.approx(0.0029921234051506376, rel=1e-9)
    assert pairs["B|E"]["p_holm"] == pytest.approx(2.0846413076970975e-05, rel=1e-9)
    assert pairs["D|E"]["dz"] == pytest.approx(-1.6878679114017523, rel=1e-12)


def test_conover_friedman_golden_raw_and_holm():
    pytest.importorskip("scikit_posthocs")
    from population_synthetic.analysis.utils.stats_tests import conover_friedman_pairwise

    grid, _, _ = _golden_grid("delta")
    out = conover_friedman_pairwise(grid, labels=LETTERS)
    assert (out["test"], out["k"], out["n"], out["correction"]) == ("conover_friedman", 5, 10, "holm")
    # closeness/posthoc_pairs.csv (p_conover_raw, p_conover_holm).
    golden = {
        "A|B": (0.00013648598294864578, 0.0010918878635891663),
        "A|D": (0.8138687871519491, 0.8138687871519491),
        "B|E": (1.3933156669813111e-09, 1.393315666981311e-08),
        "C|D": (0.013146994320221097, 0.03944098296066329),
        "D|E": (0.0002746489394360092, 0.0019225425760520643),
    }
    for key, (raw, holm) in golden.items():
        assert out["pairs"][key]["p_raw"] == pytest.approx(raw, rel=1e-9)
        assert out["pairs"][key]["p_holm"] == pytest.approx(holm, rel=1e-9)
    assert len(out["pairs"]) == 10


def test_conover_friedman_holm_matches_the_library_adjustment():
    sp = pytest.importorskip("scikit_posthocs")
    from population_synthetic.analysis.utils.stats_tests import conover_friedman_pairwise

    rng = np.random.default_rng(8)
    matrix = rng.normal(size=(12, 4)) + np.array([0.0, 0.4, 0.8, 1.2])
    labels = ["a", "b", "c", "d"]
    out = conover_friedman_pairwise(matrix, labels=labels)
    lib = sp.posthoc_conover_friedman(matrix, p_adjust="holm").to_numpy()
    for i in range(4):
        for j in range(i + 1, 4):
            assert out["pairs"][f"{labels[i]}|{labels[j]}"]["p_holm"] == pytest.approx(lib[i, j], rel=1e-9)


def test_conover_friedman_degenerate_and_label_mismatch():
    from population_synthetic.analysis.utils.stats_tests import conover_friedman_pairwise

    out = conover_friedman_pairwise([[1.0, 2.0]], labels=["a", "b"])
    assert out["pairs"] == {} and "note" in out
    with pytest.raises(ValueError, match="labels"):
        conover_friedman_pairwise([[1.0, 2.0], [2.0, 3.0]], labels=["a"])
