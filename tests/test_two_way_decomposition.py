"""Unit tests for the additive two-way decomposition and its within-block permutation test.

Hand-worked on a balanced 2 x 3 grid, pinned to ``statsmodels`` ``anova_lm(typ=2)`` on an
unbalanced one, and reproduced against the closeness prototype's golden values
(``docs/development/plans/active/typicality-distribution-grid/closeness{,_shape}/``:
``decomposition.csv`` and ``permutation_tests.csv``) over its 58 combinations.
"""

from __future__ import annotations

from itertools import product

import numpy as np
import pytest

from population_synthetic.analysis.utils.two_way_decomposition import (
    additive_two_way_anova,
    additive_two_way_effect_sizes,
    within_block_permutation_test,
)
from tests._closeness_fixtures import combination_outcomes

# --------------------------------------------------------------------------- #
# Hand-worked balanced example                                                 #
# --------------------------------------------------------------------------- #
# Rows a1 = [1, 2, 3], a2 = [2, 4, 6] over b1..b3. Grand mean 3; row means 2, 4 ->
# SS_A = 3 * (1 + 1) = 6; column means 1.5, 3, 4.5 -> SS_B = 2 * (2.25 + 0 + 2.25) = 9;
# SS_total = 4 + 1 + 0 + 1 + 1 + 9 = 16; SS_res = 1 with df 2 -> MS_res = 0.5.
_Y = [1.0, 2.0, 3.0, 2.0, 4.0, 6.0]
_A = ["a1", "a1", "a1", "a2", "a2", "a2"]
_B = ["b1", "b2", "b3", "b1", "b2", "b3"]


def test_balanced_grid_hand_worked():
    out = additive_two_way_anova(_Y, {"a": _A, "b": _B})
    assert (out["n"], out["df_residual"], out["factor_names"]) == (6, 2, ["a", "b"])
    assert out["ss_total"] == pytest.approx(16.0)
    assert out["ss_residual"] == pytest.approx(1.0)
    assert out["ms_residual"] == pytest.approx(0.5)
    a, b = out["factors"]["a"], out["factors"]["b"]
    assert (a["levels"], a["df"], b["levels"], b["df"]) == (2, 1, 3, 2)
    assert a["ss"] == pytest.approx(6.0) and b["ss"] == pytest.approx(9.0)
    assert a["ss_type1_first"] == pytest.approx(6.0)  # balanced: type I = type II
    assert a["F"] == pytest.approx(12.0) and b["F"] == pytest.approx(9.0)
    assert a["partial_eta_sq"] == pytest.approx(6.0 / 7.0)
    assert a["partial_omega_sq"] == pytest.approx(5.5 / 8.5)
    assert b["partial_omega_sq"] == pytest.approx((9.0 - 1.0) / (9.0 + 4 * 0.5))
    assert a["omega_sq"] == pytest.approx(5.5 / 16.5)
    assert a["share"] == pytest.approx(6.0 / 16.0) and b["share"] == pytest.approx(9.0 / 16.0)
    assert out["share_residual"] == pytest.approx(1.0 / 16.0)
    assert out["share_overlap"] == pytest.approx(0.0, abs=1e-12)
    from scipy import stats

    assert a["p"] == pytest.approx(float(stats.f.sf(12.0, 1, 2)))
    assert "note" not in out


def test_unbalanced_grid_matches_statsmodels_type_ii():
    pd = pytest.importorskip("pandas")
    smf = pytest.importorskip("statsmodels.formula.api")
    sm = pytest.importorskip("statsmodels.api")

    rng = np.random.default_rng(4)
    cells = [(m, s) for m, s in product(range(6), range(4)) if (m, s) not in {(0, 3), (2, 1), (5, 3)}]
    frame = pd.DataFrame({"m": [f"m{m}" for m, _ in cells], "s": [f"s{s}" for _, s in cells]})
    frame["y"] = [0.3 * m - 0.5 * s + rng.normal(scale=0.4) for m, s in cells]
    table = sm.stats.anova_lm(smf.ols("y ~ C(m, Sum) + C(s, Sum)", data=frame).fit(), typ=2)
    out = additive_two_way_anova(frame["y"].tolist(), {"model": frame["m"].tolist(), "strategy": frame["s"].tolist()})
    assert out["factors"]["model"]["ss"] == pytest.approx(table.loc["C(m, Sum)", "sum_sq"], rel=1e-9)
    assert out["factors"]["strategy"]["ss"] == pytest.approx(table.loc["C(s, Sum)", "sum_sq"], rel=1e-9)
    assert out["factors"]["model"]["F"] == pytest.approx(table.loc["C(m, Sum)", "F"], rel=1e-9)
    assert out["factors"]["strategy"]["p"] == pytest.approx(table.loc["C(s, Sum)", "PR(>F)"], rel=1e-9)
    assert out["ss_residual"] == pytest.approx(table.loc["Residual", "sum_sq"], rel=1e-9)
    assert out["df_residual"] == int(table.loc["Residual", "df"])


def test_the_decomposition_does_not_depend_on_row_order():
    order = [3, 0, 5, 1, 4, 2]
    shuffled = additive_two_way_anova(
        [_Y[i] for i in order], {"a": [_A[i] for i in order], "b": [_B[i] for i in order]}
    )
    base = additive_two_way_anova(_Y, {"a": _A, "b": _B})
    assert shuffled["factors"]["a"]["F"] == pytest.approx(base["factors"]["a"]["F"], rel=1e-12)
    assert shuffled["ss_residual"] == pytest.approx(base["ss_residual"], rel=1e-12)


# --------------------------------------------------------------------------- #
# Golden: the closeness prototype's 58 combinations                            #
# --------------------------------------------------------------------------- #

def _golden(outcome: str) -> tuple[list[float], dict[str, list[str]]]:
    rows = combination_outcomes()
    return [r[outcome] for r in rows], {"model": [r["model"] for r in rows], "strategy": [r["strategy"] for r in rows]}


def test_golden_delta_decomposition():
    y, factors = _golden("delta")
    out = additive_two_way_anova(y, factors)
    m, s = out["factors"]["model"], out["factors"]["strategy"]
    assert (out["n"], m["df"], s["df"], out["df_residual"]) == (58, 11, 4, 42)
    # closeness/decomposition.csv, basis first_round, outcome delta.
    assert out["ss_total"] == pytest.approx(1.6581215973847234, rel=1e-10)
    assert m["ss"] == pytest.approx(0.4022311141126659, rel=1e-10)
    assert s["ss"] == pytest.approx(1.0034772057095123, rel=1e-10)
    assert out["ss_residual"] == pytest.approx(0.2818489770877003, rel=1e-10)
    assert m["ss_type1_first"] == pytest.approx(0.37279541458751075, rel=1e-10)
    assert s["ss_type1_first"] == pytest.approx(0.9740415061843573, rel=1e-10)
    assert m["F"] == pytest.approx(5.448987406238197, rel=1e-10)
    assert s["F"] == pytest.approx(37.38353343986532, rel=1e-10)
    assert m["p"] == pytest.approx(2.561392713092834e-05, rel=1e-8)
    assert s["p"] == pytest.approx(2.520528581823507e-13, rel=1e-8)
    assert m["partial_eta_sq"] == pytest.approx(0.5879883354109379, rel=1e-10)
    assert s["partial_eta_sq"] == pytest.approx(0.7807179369253012, rel=1e-10)
    assert m["partial_omega_sq"] == pytest.approx(0.45763402374524664, rel=1e-10)
    assert s["partial_omega_sq"] == pytest.approx(0.7150355130675772, rel=1e-10)
    assert m["omega_sq"] == pytest.approx(0.19726523048456288, rel=1e-10)
    assert s["omega_sq"] == pytest.approx(0.5866263247223186, rel=1e-10)
    assert m["share"] == pytest.approx(0.2425823985087016, rel=1e-10)
    assert s["share"] == pytest.approx(0.6051891533722552, rel=1e-10)
    assert out["share_residual"] == pytest.approx(0.1699808853176072, rel=1e-10)
    assert out["share_overlap"] == pytest.approx(-0.017752437198564064, rel=1e-8)


@pytest.mark.parametrize(
    "outcome,f_model,f_strategy,pomega_model,pomega_strategy",
    [
        # closeness/decomposition.csv (le4, cdf) and closeness_shape/decomposition.csv (tv, cramer).
        ("le4", 3.3284359431151636, 38.6284223398181, 0.30632626573025157, 0.7218408048976339),
        ("cdf", 5.480750087061232, 35.683557625080944, 0.4594002653386374, 0.7051860276043597),
        ("tv", 5.032004836245919, 37.18507648109371, 0.43332841709194186, 0.7139197371950555),
        ("cramer", 6.777049663599932, 41.732964379162546, 0.5228204783580133, 0.7374756150971621),
    ],
)
def test_golden_sensitivity_outcomes(outcome, f_model, f_strategy, pomega_model, pomega_strategy):
    y, factors = _golden(outcome)
    out = additive_two_way_anova(y, factors)
    assert out["factors"]["model"]["F"] == pytest.approx(f_model, rel=1e-9)
    assert out["factors"]["strategy"]["F"] == pytest.approx(f_strategy, rel=1e-9)
    assert out["factors"]["model"]["partial_omega_sq"] == pytest.approx(pomega_model, rel=1e-9)
    assert out["factors"]["strategy"]["partial_omega_sq"] == pytest.approx(pomega_strategy, rel=1e-9)


def test_tv_similarity_decomposes_exactly_like_tv_distance():
    # 1 - TV is an affine map of TV: every SS, F and effect size is unchanged.
    y, factors = _golden("tv")
    distance = additive_two_way_anova(y, factors)
    similarity = additive_two_way_anova([1.0 - v for v in y], factors)
    assert similarity["factors"]["strategy"]["F"] == pytest.approx(37.18507648109371, rel=1e-9)
    assert similarity["share_overlap"] == pytest.approx(-0.05617733920998011, rel=1e-8)
    for name in ("model", "strategy"):
        for key in ("ss", "F", "partial_eta_sq", "partial_omega_sq", "share"):
            assert similarity["factors"][name][key] == pytest.approx(distance["factors"][name][key], rel=1e-9)


def test_effect_sizes_over_replicates_equal_the_one_shot_fit():
    y, factors = _golden("delta")
    rng = np.random.default_rng(0)
    stack = np.vstack([y, np.asarray(y) + rng.normal(scale=0.05, size=len(y))])
    reps = additive_two_way_effect_sizes(stack, factors)
    one = additive_two_way_anova(y, factors)
    assert reps["factors"]["strategy"]["partial_omega_sq"].shape == (2,)
    for name in ("model", "strategy"):
        for key in ("ss", "F", "partial_eta_sq", "partial_omega_sq", "omega_sq", "share"):
            assert reps["factors"][name][key][0] == pytest.approx(one["factors"][name][key], rel=1e-10)
    assert reps["share_overlap"][0] == pytest.approx(one["share_overlap"], rel=1e-8)
    second = additive_two_way_anova(stack[1].tolist(), factors)
    assert reps["factors"]["model"]["F"][1] == pytest.approx(second["factors"]["model"]["F"], rel=1e-10)


# --------------------------------------------------------------------------- #
# Degenerate and malformed input                                               #
# --------------------------------------------------------------------------- #

def test_no_residual_degrees_of_freedom_is_reported_not_raised():
    out = additive_two_way_anova([1.0, 2.0, 4.0], {"a": ["x", "x", "y"], "b": ["p", "q", "p"]})
    assert out["df_residual"] == 0
    assert out["factors"]["a"]["F"] is None and out["factors"]["a"]["partial_omega_sq"] is None
    assert "no residual degrees of freedom" in out["note"]


def test_single_level_factor_and_zero_variation():
    one_level = additive_two_way_anova([1.0, 2.0, 3.0, 5.0], {"a": ["x"] * 4, "b": ["p", "q", "p", "q"]})
    assert one_level["factors"]["a"]["df"] == 0 and one_level["factors"]["a"]["F"] is None
    assert "no degrees of freedom" in one_level["note"]
    flat = additive_two_way_anova([2.0] * 6, {"a": _A, "b": _B})
    assert flat["factors"]["a"]["share"] is None and flat["share_residual"] is None
    assert "zero total variation" in flat["note"]


def test_zero_residual_variation_diverges_explicitly():
    additive = [1.0, 2.0, 3.0, 3.0, 4.0, 5.0]  # a2 = a1 + 2 in every column
    out = additive_two_way_anova(additive, {"a": _A, "b": _B})
    assert out["factors"]["a"]["F"] == float("inf") and out["factors"]["a"]["p"] == 0.0
    assert "zero residual variation" in out["note"]
    with pytest.raises(ValueError, match="zero total or residual"):
        additive_two_way_effect_sizes([additive, _Y], {"a": _A, "b": _B})


@pytest.mark.parametrize(
    "values,factors",
    [
        (_Y, {"a": _A}),
        (_Y, {"a": _A, "b": _B, "c": _B}),
        (_Y, {"a": _A[:-1], "b": _B}),
        (_Y[:-1] + [float("nan")], {"a": _A, "b": _B}),
        ([], {"a": [], "b": []}),
    ],
)
def test_malformed_input_raises(values, factors):
    with pytest.raises(ValueError):
        additive_two_way_anova(values, factors)


def test_effect_sizes_reject_a_design_without_residual_df():
    with pytest.raises(ValueError, match="residual degrees of freedom"):
        additive_two_way_effect_sizes([[1.0, 2.0, 4.0]], {"a": ["x", "x", "y"], "b": ["p", "q", "p"]})


# --------------------------------------------------------------------------- #
# Within-block permutation test                                                #
# --------------------------------------------------------------------------- #

def test_permutation_p_matches_exact_enumeration():
    # Factor a (2 levels) permuted within each of 3 b-blocks of 2 cells: 2^3 = 8 equally
    # likely arrangements, so the exact p is the share of them with F >= F_obs.
    y = [1.0, 5.0, 2.0, 4.0, 6.0, 7.0]
    factors = {"a": _A, "b": _B}
    f_obs = additive_two_way_anova(y, factors)["factors"]["a"]["F"]
    hits = 0
    for flips in product([False, True], repeat=3):
        arranged = list(y)
        for col, flip in enumerate(flips):
            if flip:
                arranged[col], arranged[col + 3] = arranged[col + 3], arranged[col]
        hits += additive_two_way_anova(arranged, factors)["factors"]["a"]["F"] >= f_obs * (1 - 1e-9)
    exact = hits / 8
    res = within_block_permutation_test(y, factors, factor="a", iterations=20000, seed=3)
    assert (res["factor"], res["block"], res["df_effect"], res["df_residual"]) == ("a", "b", 1, 2)
    assert res["F"] == pytest.approx(f_obs)
    assert res["p"] == pytest.approx(exact, abs=0.01)
    assert res["p"] == (1 + res["n_at_least_as_extreme"]) / 20001


def test_permutation_is_seeded():
    y, factors = _golden("le4")
    first = within_block_permutation_test(y, factors, factor="model", iterations=500, seed=5)
    again = within_block_permutation_test(y, factors, factor="model", iterations=500, seed=5)
    assert first == again


def test_golden_permutation_p_values():
    # closeness/permutation_tests.csv, first_round (10,000 permutations each): no permutation
    # reached the observed F for delta; the model factor under le4 gave p = 0.0030.
    y, factors = _golden("delta")
    for factor in ("strategy", "model"):
        res = within_block_permutation_test(y, factors, factor=factor, iterations=2000, seed=20260921)
        assert res["n_at_least_as_extreme"] == 0 and res["p"] == pytest.approx(1 / 2001)
    y4, _ = _golden("le4")
    res = within_block_permutation_test(y4, factors, factor="model", iterations=10000, seed=20260928)
    assert res["F"] == pytest.approx(3.3284359431151636, rel=1e-9)
    assert res["p"] == pytest.approx(0.0030, abs=0.0015)


def test_permutation_undefined_observed_f_and_bad_requests():
    out = within_block_permutation_test([1.0, 2.0, 4.0], {"a": ["x", "x", "y"], "b": ["p", "q", "p"]},
                                        factor="a", iterations=10, seed=0)
    assert out["F"] is None and out["p"] is None and "note" in out
    with pytest.raises(ValueError, match="not one of"):
        within_block_permutation_test(_Y, {"a": _A, "b": _B}, factor="c", iterations=10, seed=0)
    with pytest.raises(ValueError, match="iterations"):
        within_block_permutation_test(_Y, {"a": _A, "b": _B}, factor="a", iterations=0, seed=0)
