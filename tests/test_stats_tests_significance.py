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
