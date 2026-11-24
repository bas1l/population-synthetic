"""Tests for the repeated-measures ANOVA assumption checks.

``rm_anova_assumptions`` is pinned to hand-computed reference values on a real
10-model x 5-method overall TV-similarity grid (literal fixture data below), then
exercised on the explicit ``k = 2`` case, the degenerate and singular grids, and
malformed input. The builder wiring is checked on ``_method_comparison``: every
panel carries the block, judged at the config-derived significance cutoff.

Lilliefors needs ``statsmodels`` (the ``[analysis]`` extra), so the module is
skipped without it.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy import stats

pytest.importorskip("statsmodels")
pytest.importorskip("scikit_posthocs")

from population_synthetic.analysis.method_significance.builder import (  # noqa: E402
    _method_comparison,
    load_comparison_config,
    significance_cutoff,
)
from population_synthetic.analysis.utils.stats_tests import (  # noqa: E402
    HUYNH_FELDT_FORMULA,
    paired_t_pairwise,
    rm_anova_assumptions,
    rm_anova_within,
)
from tests._performance_fixtures import make_combo  # noqa: E402

# Methods A-E in complexity order; rows are the ten models, alphabetical.
METHODS = ["A", "B", "C", "D", "E"]
OVERALL = np.array([
    [0.5133785714285715, 0.5269428571428573, 0.5734999999999999, 0.6434857142857142, 0.8408181818181818],
    [0.4522, 0.44423571428571434, 0.4657071428571428, 0.5816642857142857, 0.8391414580265096],
    [0.5257785714285714, 0.49708571428571435, 0.4949928571428572, 0.5794928571428571, 0.754234024577573],
    [0.49835714285714283, 0.5316857142857143, 0.47800714285714285, 0.5417857142857143, 0.8171950937950937],
    [0.4737785714285715, 0.4635714285714285, 0.48358571428571423, 0.5608357142857143, 0.8205166666666667],
    [0.5120142857142858, 0.4627928571428571, 0.5425928571428572, 0.5504857142857142, 0.7904095959595959],
    [0.5261928571428571, 0.5137357142857143, 0.5177642857142857, 0.5420571428571429, 0.8419785714285712],
    [0.5131357142857144, 0.51995, 0.6064642857142857, 0.5627928571428571, 0.7879617604617605],
    [0.5056357142857143, 0.4331642857142857, 0.45662857142857144, 0.5326857142857143, 0.8317500000000001],
    [0.5144142857142857, 0.4797928571428571, 0.5161214285714285, 0.5548928571428571, 0.8103099125364431],
])
ALPHA = 0.05


def _no_nan(obj) -> bool:
    if isinstance(obj, float):
        return not math.isnan(obj)
    if isinstance(obj, dict):
        return all(_no_nan(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return all(_no_nan(v) for v in obj)
    return True


@pytest.fixture(scope="module")
def reference():
    return rm_anova_assumptions(OVERALL, labels=METHODS, alpha=ALPHA)


# --------------------------------------------------------------------------- #
# Reference grid                                                              #
# --------------------------------------------------------------------------- #


def test_reference_omnibus_is_the_one_being_checked():
    anova = rm_anova_within(OVERALL)
    assert (anova["df1"], anova["df2"]) == (4, 36)
    assert anova["F"] == pytest.approx(189.487, abs=1e-3)
    assert anova["p"] == pytest.approx(1.194e-23, rel=1e-3)


def test_reference_residual_normality(reference):
    block = reference["residual_normality"]
    assert block["n_residuals"] == 50
    assert block["shapiro_wilk"]["W"] == pytest.approx(0.9827, abs=1e-4)
    assert block["shapiro_wilk"]["p"] == pytest.approx(0.6704, abs=1e-4)
    assert block["lilliefors"]["D"] == pytest.approx(0.0915, abs=1e-4)
    assert block["lilliefors"]["p"] == pytest.approx(0.3725, abs=1e-4)
    assert set(block["per_method_shapiro_wilk"]) == set(METHODS)
    assert block["worst_method"]["method"] == "C"
    assert block["worst_method"]["W"] == pytest.approx(0.8866, abs=1e-4)
    assert block["worst_method"]["p"] == pytest.approx(0.1553, abs=1e-4)


def test_reference_paired_difference_normality(reference):
    ad = reference["pairs"]["A|D"]["diff_shapiro_wilk"]
    assert ad["W"] == pytest.approx(0.8433, abs=1e-4)
    assert ad["p"] == pytest.approx(0.0483, abs=1e-4)
    assert ad["p_holm"] == pytest.approx(0.4834, abs=1e-4)
    # Every other pair's Holm-adjusted p saturates at 1.
    others = [rec["diff_shapiro_wilk"]["p_holm"] for key, rec in reference["pairs"].items() if key != "A|D"]
    assert others == pytest.approx([1.0] * 9)


def test_reference_sphericity(reference):
    sph = reference["sphericity"]
    assert sph["mauchly"]["W"] == pytest.approx(0.5061, abs=1e-4)
    assert sph["mauchly"]["chi2"] == pytest.approx(5.0508, abs=1e-4)
    assert sph["mauchly"]["df"] == 9
    assert sph["mauchly"]["p"] == pytest.approx(0.8299, abs=1e-4)

    eps = sph["epsilon"]
    assert sph["huynh_feldt_formula"] == HUYNH_FELDT_FORMULA == "huynh_feldt_1976"
    assert eps["greenhouse_geisser"] == pytest.approx(0.7250, abs=1e-4)
    assert eps["huynh_feldt"] == pytest.approx(1.1065, abs=1e-4)
    assert eps["huynh_feldt_capped"] == 1.0
    assert eps["lower_bound"] == 0.25

    corrected = sph["corrected"]
    gg = corrected["greenhouse_geisser"]
    assert gg["df1"] == pytest.approx(2.900, abs=1e-3)
    assert gg["df2"] == pytest.approx(26.099, abs=1e-3)
    assert gg["p"] == pytest.approx(1.0594e-17, rel=1e-3)
    # HF capped at 1 is the uncorrected test.
    hf = corrected["huynh_feldt_capped"]
    assert (hf["df1"], hf["df2"]) == (4.0, 36.0)
    assert hf["p"] == pytest.approx(1.1936e-23, rel=1e-3)
    lb = corrected["lower_bound"]
    assert (lb["df1"], lb["df2"]) == (1.0, 9.0)
    assert lb["p"] == pytest.approx(2.3730e-7, rel=1e-3)


def test_reference_difference_variances(reference):
    expected = {"A|B": 0.000971, "A|C": 0.001818, "C|E": 0.003783, "D|E": 0.001651}
    for key, var in expected.items():
        assert reference["pairs"][key]["diff_variance"] == pytest.approx(var, abs=1e-6)


def test_reference_wilcoxon_only_c_d_changes_verdict(reference):
    pairs = reference["pairs"]
    flipped = [key for key, rec in pairs.items() if rec["verdict_differs_from_t"]]
    assert flipped == ["C|D"]
    cd = pairs["C|D"]
    assert cd["wilcoxon"]["p"] == pytest.approx(0.01367, abs=1e-5)
    assert cd["wilcoxon"]["p_holm"] == pytest.approx(0.05469, abs=1e-5)
    assert cd["t_p_holm"] == pytest.approx(0.024632, abs=1e-6)
    # A 10/10 sweep hits the exact minimum two-sided p, 2 / 2**10.
    assert pairs["A|E"]["wilcoxon"]["p"] == pytest.approx(2 / 2 ** 10)
    # t_p_holm is paired_t_pairwise's value, not a recomputation that could drift.
    t_pairs = paired_t_pairwise(OVERALL, labels=METHODS, confidence_level=0.95)["pairs"]
    assert all(rec["t_p_holm"] == t_pairs[key]["p_holm"] for key, rec in pairs.items())


def test_reference_block_is_nan_free_and_complete(reference):
    assert _no_nan(reference)
    assert reference["alpha"] == ALPHA
    assert (reference["n"], reference["k"]) == (10, 5)
    assert len(reference["pairs"]) == 10
    assert "note" not in reference


# --------------------------------------------------------------------------- #
# k = 2, degenerate and singular grids                                        #
# --------------------------------------------------------------------------- #


def test_two_treatments_sphericity_trivial():
    grid = OVERALL[:, [0, 4]]
    out = rm_anova_assumptions(grid, labels=["A", "E"], alpha=ALPHA)
    sph = out["sphericity"]
    assert sph["mauchly"]["W"] == 1.0
    assert sph["mauchly"]["p"] is None and sph["mauchly"]["df"] == 0
    assert "k = 2" in sph["mauchly"]["note"]
    assert sph["epsilon"] == {"greenhouse_geisser": 1.0, "huynh_feldt": 1.0,
                              "huynh_feldt_capped": 1.0, "lower_bound": 1.0}
    anova = rm_anova_within(grid)
    for rec in sph["corrected"].values():
        assert rec["p"] == pytest.approx(anova["p"])
    # And the F is the paired t squared, so its p is the paired t's raw p.
    assert anova["p"] == pytest.approx(stats.ttest_rel(grid[:, 1], grid[:, 0]).pvalue)
    assert list(out["pairs"]) == ["A|E"]
    assert _no_nan(out)


@pytest.mark.parametrize("n_blocks", [0, 1])
def test_too_few_blocks_returns_skeleton(n_blocks):
    out = rm_anova_assumptions(OVERALL[:n_blocks], labels=METHODS, alpha=ALPHA)
    assert out["residual_normality"] is None
    assert out["sphericity"] is None
    assert out["pairs"] == {}
    assert "need >=2" in out["note"]


def test_single_treatment_returns_skeleton():
    out = rm_anova_assumptions(OVERALL[:, [0]], labels=["A"], alpha=ALPHA)
    assert out["sphericity"] is None and "need >=2" in out["note"]


def test_constant_grid_reports_undefined_not_nan():
    out = rm_anova_assumptions(np.full((6, 4), 0.5), labels=METHODS[:4], alpha=ALPHA)
    res = out["residual_normality"]
    assert res["shapiro_wilk"]["W"] is None and "zero spread" in res["shapiro_wilk"]["note"]
    assert res["lilliefors"]["D"] is None and "zero residual" in res["lilliefors"]["note"]
    assert res["worst_method"] is None
    sph = out["sphericity"]
    assert sph["epsilon"]["greenhouse_geisser"] is None
    assert sph["mauchly"]["W"] is None and "zero variance" in sph["mauchly"]["note"]
    # The lower bound does not depend on the data; the F it would correct does not exist.
    assert sph["corrected"]["lower_bound"]["epsilon"] == pytest.approx(1 / 3)
    assert sph["corrected"]["lower_bound"]["p"] is None
    for rec in out["pairs"].values():
        assert rec["wilcoxon"]["p"] is None and "zero" in rec["wilcoxon"]["note"]
        assert rec["verdict_differs_from_t"] is None
    assert _no_nan(out)


def test_perfectly_additive_grid_keeps_the_diverging_f():
    # Constant per-method offsets: zero residual, F diverges, differences are constant.
    grid = np.array([[0.1 * i + 0.2 * j for j in range(4)] for i in range(5)])
    out = rm_anova_assumptions(grid, labels=METHODS[:4], alpha=ALPHA)
    assert out["sphericity"]["corrected"]["lower_bound"]["p"] == 0.0
    assert out["sphericity"]["epsilon"]["greenhouse_geisser"] is None
    for rec in out["pairs"].values():
        # A constant non-zero difference still has signs to rank.
        assert rec["wilcoxon"]["p"] is not None
        assert rec["diff_shapiro_wilk"]["W"] is None
    assert _no_nan(out)


def test_fewer_blocks_than_contrasts_skips_mauchly_but_keeps_epsilon():
    out = rm_anova_assumptions(OVERALL[:3], labels=METHODS, alpha=ALPHA)
    sph = out["sphericity"]
    assert sph["mauchly"]["W"] is None and "singular" in sph["mauchly"]["note"]
    assert sph["epsilon"]["greenhouse_geisser"] is not None
    assert sph["corrected"]["greenhouse_geisser"]["p"] is not None
    assert _no_nan(out)


# --------------------------------------------------------------------------- #
# Malformed input                                                             #
# --------------------------------------------------------------------------- #


def test_nan_cell_raises():
    grid = OVERALL.copy()
    grid[2, 3] = np.nan
    with pytest.raises(ValueError, match="NaN"):
        rm_anova_assumptions(grid, labels=METHODS, alpha=ALPHA)


def test_label_count_mismatch_raises():
    with pytest.raises(ValueError, match="labels"):
        rm_anova_assumptions(OVERALL, labels=METHODS[:4], alpha=ALPHA)


@pytest.mark.parametrize("alpha", [0.0, 1.0, -0.1, True, "0.05", None])
def test_bad_alpha_raises(alpha):
    with pytest.raises(ValueError, match="alpha"):
        rm_anova_assumptions(OVERALL, labels=METHODS, alpha=alpha)


# --------------------------------------------------------------------------- #
# Builder wiring                                                              #
# --------------------------------------------------------------------------- #

_BUILDER_METHODS = ["all_pick", "all_pick_dag", "all_generate_pick"]


def _combos(n_models: int):
    combos = []
    for m in range(n_models):
        for r, strategy in enumerate(_BUILDER_METHODS):
            tv = round(0.3 - 0.05 * r + 0.01 * ((m * 7 + r * 3) % 5), 4)
            combos.append(make_combo(slug=f"swedish_{strategy}_model_{m}", strategy=strategy,
                                     model=f"model_{m}", tv_by_attr={"attr": tv}))
    return combos


def _block(n_models: int, config):
    combos = _combos(n_models)
    by_ms = {(c.model, c.strategy): c for c in combos}
    models = sorted({c.model for c in combos})
    return _method_comparison(by_ms, models, ["attr"], _BUILDER_METHODS, config, {"attr": ["a", "b"]})


def test_every_panel_carries_assumptions_at_the_config_cutoff():
    config = load_comparison_config()
    block = _block(6, config)
    cutoff = significance_cutoff(config["star_thresholds"])
    for panel in block["panels"].values():
        assumptions = panel["assumptions"]
        assert assumptions["alpha"] == cutoff
        assert set(assumptions["pairs"]) == set(panel["pairwise_detail"])
        assert assumptions["sphericity"]["corrected"]["greenhouse_geisser"]["p"] is not None


def test_degenerate_panel_still_carries_assumptions():
    block = _block(1, load_comparison_config())
    assumptions = block["panels"]["overall"]["assumptions"]
    assert assumptions["sphericity"] is None and "need >=2" in assumptions["note"]


def test_config_without_star_thresholds_fails_loudly():
    with pytest.raises(KeyError, match="star_thresholds"):
        _block(6, {"pairs_mode": "adjacent", "confidence_level": 0.95})
