"""Tests for the method-comparison figure statistics (Phase 1).

Covers the config loader (fail-fast), the pair-resolution rules, and the
``_method_comparison`` block: complete-case ``models x methods`` TV-similarity
matrix, Friedman omnibus matched to a direct ``scipy`` call, a symmetric Nemenyi
pairwise p-matrix, the Overall-panel overall-TV response, and BH correction
across categories.

The block leans on ``benjamini_hochberg`` (statsmodels) and ``nemenyi_pairwise``
(scikit-posthocs), so the module is skipped without the ``[analysis]`` extra.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from scipy import stats

pytest.importorskip("statsmodels")
pytest.importorskip("scikit_posthocs")

from population_synthetic.analysis.method_significance.builder import (  # noqa: E402
    DEFAULT_COMPARISON_CONFIG_PATH,
    _method_comparison,
    build_method_significance,
    load_comparison_config,
    resolve_pairs,
    significance_cutoff,
)
from population_synthetic.analysis.utils.axes import strategy_complexity_order  # noqa: E402
from tests._performance_fixtures import make_combo  # noqa: E402

MODELS = ["model_a", "model_b", "model_c", "model_d", "model_e"]
# The five v1 families, ordered by the config-derived accessor (the same order
# every consumer resolves; asserted against the legacy sequence in test_axes.py).
STRATEGIES = strategy_complexity_order([
    "all_generate_evaluate_random_pick",
    "all_generate_evaluate_pick",
    "all_generate_pick",
    "all_pick_dag",
    "all_pick",
])
ATTRS = ["trend_attr", "shift_attr"]
# Config-sourced category levels per attribute (drives the panel level counts).
CATEGORY_VALUES = {
    "trend_attr": ["a", "b", "c", "d"],   # 4 levels
    "shift_attr": ["x", "y", "z"],        # 3 levels
}
_CMP_CONFIG = {"pairs_mode": "adjacent"}


def _trend_tv(m_idx: int, rank: int) -> float:
    """TV-distance strictly increasing in method rank (so similarity decreases)."""
    return round(0.05 + 0.15 * (rank - 1) + 0.004 * m_idx, 4)


def _shift_tv(m_idx: int, rank: int) -> float:
    """A second, differently-shaped TV pattern to give the Overall panel spread."""
    return round(0.40 - 0.05 * (rank - 1) + 0.01 * ((m_idx + rank) % 3), 4)


def _full_grid(*, drop=None, nan_cell=None):
    combos = []
    for m_idx, model in enumerate(MODELS):
        for rank, strategy in enumerate(STRATEGIES, start=1):
            if drop is not None and (model, strategy) == drop:
                continue
            tv_by_attr = {"trend_attr": _trend_tv(m_idx, rank), "shift_attr": _shift_tv(m_idx, rank)}
            if nan_cell is not None and (model, strategy) == nan_cell[:2]:
                tv_by_attr[nan_cell[2]] = float("nan")
            combos.append(make_combo(slug=f"swedish_{strategy}_{model}", strategy=strategy,
                                     model=model, tv_by_attr=tv_by_attr))
    return combos


def _by_ms(combos):
    by_ms = {(c.model, c.strategy): c for c in combos}
    models = sorted({c.model for c in combos})
    methods = [s for s in STRATEGIES if any((m, s) in by_ms for m in models)]
    return by_ms, models, methods


# --------------------------------------------------------------------------- #
# Config loader                                                               #
# --------------------------------------------------------------------------- #


def test_default_config_loads_with_vs_most_complex_mode():
    cfg = load_comparison_config()
    assert cfg["pairs_mode"] == "vs-most-complex"
    assert cfg["pairs_mode"] in cfg["allowed_pairs_modes"]
    assert cfg["star_thresholds"]
    assert isinstance(cfg["ns_symbol"], str)


def test_default_config_path_points_at_repo_config():
    assert DEFAULT_COMPARISON_CONFIG_PATH.name == "comparison.json"
    assert DEFAULT_COMPARISON_CONFIG_PATH.is_file()


def test_missing_config_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="not found"):
        load_comparison_config(tmp_path / "nope.json")


def test_unknown_pairs_mode_raises(tmp_path):
    bad = tmp_path / "comparison.json"
    bad.write_text(json.dumps({
        "pairs_mode": "bogus",
        "allowed_pairs_modes": ["adjacent", "all"],
        "star_thresholds": [{"max_p": 0.05, "symbol": "*"}],
        "ns_symbol": "ns",
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown pairs_mode"):
        load_comparison_config(bad)


def test_malformed_star_thresholds_raises(tmp_path):
    bad = tmp_path / "comparison.json"
    bad.write_text(json.dumps({
        "pairs_mode": "adjacent",
        "allowed_pairs_modes": ["adjacent"],
        "star_thresholds": [],
        "ns_symbol": "ns",
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="star_thresholds"):
        load_comparison_config(bad)


# --------------------------------------------------------------------------- #
# Pair resolution                                                             #
# --------------------------------------------------------------------------- #


def test_resolve_pairs_adjacent():
    methods = ["a", "b", "c", "d"]
    assert resolve_pairs(methods, "adjacent") == [("a", "b"), ("b", "c"), ("c", "d")]


def test_resolve_pairs_all():
    methods = ["a", "b", "c", "d"]
    pairs = resolve_pairs(methods, "all")
    assert len(pairs) == 6
    assert ("a", "d") in pairs and ("b", "c") in pairs


def test_resolve_pairs_vs_baseline():
    methods = ["a", "b", "c", "d"]
    assert resolve_pairs(methods, "vs-baseline") == [("a", "b"), ("a", "c"), ("a", "d")]


def test_resolve_pairs_significant_only_is_all_pairs_filtered():
    # All unordered pairs are candidates (not just adjacent); only p<=alpha kept.
    # The non-adjacent pair a|d is significant and MUST be returned, proving the
    # candidate set is 'all' rather than 'adjacent'.
    methods = ["a", "b", "c", "d"]
    pairwise_p = {
        "a|b": 0.01, "a|c": 0.20, "a|d": 0.002,   # a|d non-adjacent, significant
        "b|c": 0.049, "b|d": 0.30, "c|d": 0.51,
    }
    pairs = resolve_pairs(methods, "significant-only", pairwise_p=pairwise_p, alpha=0.05)
    assert pairs == [("a", "b"), ("a", "d"), ("b", "c")]  # ordered; ns pairs dropped
    # No non-significant pair leaks through.
    for a, b in pairs:
        assert pairwise_p[f"{a}|{b}"] <= 0.05


def test_resolve_pairs_significant_only_cutoff_from_config():
    # The cutoff is the config '*' threshold (max max_p), read via significance_cutoff,
    # not a hardcoded 0.05 -- a p just above it is excluded, one at it is kept.
    cfg = load_comparison_config()
    alpha = significance_cutoff(cfg["star_thresholds"])
    assert alpha == 0.05
    methods = ["a", "b", "c"]
    pairwise_p = {"a|b": alpha, "a|c": alpha + 1e-6, "b|c": 0.9}
    pairs = resolve_pairs(methods, "significant-only", pairwise_p=pairwise_p, alpha=alpha)
    assert pairs == [("a", "b")]  # a|c just above cutoff excluded; b|c ns excluded


def test_resolve_pairs_significant_only_without_p_raises():
    with pytest.raises(ValueError, match="significant-only"):
        resolve_pairs(["a", "b"], "significant-only", alpha=0.05)


def test_resolve_pairs_significant_only_without_alpha_raises():
    with pytest.raises(ValueError, match="alpha"):
        resolve_pairs(["a", "b"], "significant-only", pairwise_p={"a|b": 0.01})


def test_significance_cutoff_matches_star_cutoff():
    cfg = load_comparison_config()
    assert significance_cutoff(cfg["star_thresholds"]) == 0.05


def test_significance_cutoff_empty_raises():
    with pytest.raises(ValueError, match="non-empty"):
        significance_cutoff([])


def test_resolve_pairs_unknown_mode_raises():
    with pytest.raises(ValueError, match="Unknown pairs_mode"):
        resolve_pairs(["a", "b"], "diagonal")


# --------------------------------------------------------------------------- #
# _method_comparison block                                                    #
# --------------------------------------------------------------------------- #


def test_block_shape_and_metadata():
    by_ms, models, methods = _by_ms(_full_grid())
    block = _method_comparison(by_ms, models, ATTRS, methods, _CMP_CONFIG, CATEGORY_VALUES)

    assert block["response"] == "tv_similarity"
    assert block["methods"] == STRATEGIES
    assert block["pairs_mode"] == "adjacent"
    assert set(block["panels"]) == set(ATTRS) | {"overall"}
    panel = block["panels"]["trend_attr"]
    assert set(panel) >= {"n_models", "n_dropped", "means", "omnibus", "pairwise_p",
                          "pairwise_detail", "omnibus_friedman", "pairwise_p_nemenyi",
                          "correction", "insufficient_n"}
    assert panel["omnibus"]["test"] == "rm_anova"
    assert panel["omnibus_friedman"]["test"] == "friedman"


def test_category_panels_carry_level_count_from_config():
    by_ms, models, methods = _by_ms(_full_grid())
    block = _method_comparison(by_ms, models, ATTRS, methods, _CMP_CONFIG, CATEGORY_VALUES)
    # Each category panel records n_category_values == len(config values) for that attr.
    assert block["panels"]["trend_attr"]["n_category_values"] == len(CATEGORY_VALUES["trend_attr"])
    assert block["panels"]["shift_attr"]["n_category_values"] == len(CATEGORY_VALUES["shift_attr"])
    # The Overall panel spans all categories -> no single level count.
    assert "n_category_values" not in block["panels"]["overall"]


def test_missing_category_values_raises():
    by_ms, models, methods = _by_ms(_full_grid())
    with pytest.raises(ValueError, match="no category values"):
        _method_comparison(by_ms, models, ATTRS, methods, _CMP_CONFIG,
                           {"trend_attr": ["a"]})  # shift_attr absent -> fail-fast


def test_empty_category_values_raises():
    by_ms, models, methods = _by_ms(_full_grid())
    with pytest.raises(ValueError, match="no category values"):
        _method_comparison(by_ms, models, ATTRS, methods, _CMP_CONFIG,
                           {"trend_attr": ["a", "b"], "shift_attr": []})  # empty -> fail-fast


def test_complete_case_matrix_full_grid():
    by_ms, models, methods = _by_ms(_full_grid())
    block = _method_comparison(by_ms, models, ATTRS, methods, _CMP_CONFIG, CATEGORY_VALUES)
    panel = block["panels"]["trend_attr"]
    assert panel["n_models"] == len(MODELS)
    assert panel["n_dropped"] == 0
    assert panel["insufficient_n"] is False


def test_complete_case_drops_incomplete_model():
    # model_e loses its last method entirely -> incomplete for every category panel.
    by_ms, models, methods = _by_ms(_full_grid(drop=("model_e", STRATEGIES[-1])))
    block = _method_comparison(by_ms, models, ATTRS, methods, _CMP_CONFIG, CATEGORY_VALUES)
    panel = block["panels"]["trend_attr"]
    assert panel["n_models"] == len(MODELS) - 1
    assert panel["n_dropped"] == 1
    assert "model_e" in panel["dropped_models"]


def test_nan_cell_drops_model_from_that_panel_only():
    by_ms, models, methods = _by_ms(_full_grid(nan_cell=("model_a", STRATEGIES[0], "shift_attr")))
    block = _method_comparison(by_ms, models, ATTRS, methods, _CMP_CONFIG, CATEGORY_VALUES)
    # trend_attr unaffected; shift_attr drops model_a (its all_pick cell is NaN).
    assert block["panels"]["trend_attr"]["n_models"] == len(MODELS)
    shift = block["panels"]["shift_attr"]
    assert "model_a" in shift["dropped_models"]
    assert shift["n_models"] == len(MODELS) - 1


def test_friedman_retained_and_matches_direct_scipy():
    by_ms, models, methods = _by_ms(_full_grid())
    block = _method_comparison(by_ms, models, ATTRS, methods, _CMP_CONFIG, CATEGORY_VALUES)
    panel = block["panels"]["trend_attr"]

    # Rebuild the complete-case TV-similarity matrix (models x methods) by hand.
    matrix = np.array(
        [[by_ms[(m, s)].tv_similarity["trend_attr"] for s in methods] for m in models],
        dtype=float,
    )
    chi2, p = stats.friedmanchisquare(*matrix.T)
    friedman = panel["omnibus_friedman"]
    assert friedman["statistic"] == pytest.approx(float(chi2))
    assert friedman["p"] == pytest.approx(float(p))
    assert 0.0 <= friedman["kendall_w"] <= 1.0


def test_nemenyi_pairwise_symmetric_and_keyed_by_methods():
    by_ms, models, methods = _by_ms(_full_grid())
    block = _method_comparison(by_ms, models, ATTRS, methods, _CMP_CONFIG, CATEGORY_VALUES)
    pairwise = block["panels"]["trend_attr"]["pairwise_p_nemenyi"]
    # k=5 methods -> C(5,2)=10 unordered pairs.
    assert len(pairwise) == 10
    for a, b in zip(methods[:-1], methods[1:]):
        assert f"{a}|{b}" in pairwise
        assert 0.0 <= pairwise[f"{a}|{b}"] <= 1.0


def test_overall_panel_uses_overall_tv_similarity():
    by_ms, models, methods = _by_ms(_full_grid())
    block = _method_comparison(by_ms, models, ATTRS, methods, _CMP_CONFIG, CATEGORY_VALUES)
    overall = block["panels"]["overall"]
    assert overall["n_models"] == len(MODELS)

    # Hand-compute per-method overall means (mean over models of mean-over-categories).
    for s in methods:
        per_model_overall = [
            float(np.mean(list(by_ms[(m, s)].tv_similarity.values()))) for m in models
        ]
        assert overall["means"][s] == pytest.approx(float(np.mean(per_model_overall)))


def test_bh_applied_across_categories_not_overall():
    by_ms, models, methods = _by_ms(_full_grid())
    block = _method_comparison(by_ms, models, ATTRS, methods, _CMP_CONFIG, CATEGORY_VALUES)
    for attr in ATTRS:
        omni = block["panels"][attr]["omnibus"]
        assert omni["p_bh"] is not None
        assert omni["p_bh"] >= omni["p"]  # BH never shrinks a p below its raw value
    # Overall is a single pooled test, excluded from the category BH family.
    assert block["panels"]["overall"]["omnibus"]["p_bh"] is None


def test_insufficient_n_flagged_and_recorded():
    # Two models only -> below _MIN_COMPLETE_MODELS (3); recorded but flagged.
    combos = []
    for m_idx, model in enumerate(["solo_a", "solo_b"]):
        for rank, strategy in enumerate(STRATEGIES, start=1):
            combos.append(make_combo(slug=f"swedish_{strategy}_{model}", strategy=strategy,
                                     model=model,
                                     tv_by_attr={"trend_attr": _trend_tv(m_idx, rank),
                                                 "shift_attr": _shift_tv(m_idx, rank)}))
    by_ms, models, methods = _by_ms(combos)
    block = _method_comparison(by_ms, models, ATTRS, methods, _CMP_CONFIG, CATEGORY_VALUES)
    panel = block["panels"]["trend_attr"]
    assert panel["n_models"] == 2
    assert panel["insufficient_n"] is True
    assert "note" in panel


# --------------------------------------------------------------------------- #
# Integration through build_method_significance                               #
# --------------------------------------------------------------------------- #


def test_build_attaches_method_comparison_block():
    result = build_method_significance(
        _full_grid(), ATTRS, category_values=CATEGORY_VALUES, comparison_config=_CMP_CONFIG
    )
    assert "method_comparison" in result
    assert result["method_comparison"]["methods"] == STRATEGIES
    assert set(result["method_comparison"]["panels"]) == set(ATTRS) | {"overall"}
