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
)
from population_synthetic.analysis.utils.axes import STRATEGY_COMPLEXITY_ORDER  # noqa: E402
from tests._performance_fixtures import make_combo  # noqa: E402

MODELS = ["model_a", "model_b", "model_c", "model_d", "model_e"]
STRATEGIES = list(STRATEGY_COMPLEXITY_ORDER)
ATTRS = ["trend_attr", "shift_attr"]
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


def test_default_config_loads_with_adjacent_mode():
    cfg = load_comparison_config()
    assert cfg["pairs_mode"] == "adjacent"
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


def test_resolve_pairs_significant_only():
    methods = ["a", "b", "c"]
    pairwise_p = {"a|b": 0.01, "a|c": 0.20, "b|c": 0.049}
    pairs = resolve_pairs(methods, "significant-only", pairwise_p=pairwise_p, alpha=0.05)
    assert pairs == [("a", "b"), ("b", "c")]  # a|c (p=0.20) excluded


def test_resolve_pairs_significant_only_without_p_raises():
    with pytest.raises(ValueError, match="significant-only"):
        resolve_pairs(["a", "b"], "significant-only")


def test_resolve_pairs_unknown_mode_raises():
    with pytest.raises(ValueError, match="Unknown pairs_mode"):
        resolve_pairs(["a", "b"], "diagonal")


# --------------------------------------------------------------------------- #
# _method_comparison block                                                    #
# --------------------------------------------------------------------------- #


def test_block_shape_and_metadata():
    by_ms, models, methods = _by_ms(_full_grid())
    block = _method_comparison(by_ms, models, ATTRS, methods, _CMP_CONFIG)

    assert block["response"] == "tv_similarity"
    assert block["methods"] == STRATEGIES
    assert block["pairs_mode"] == "adjacent"
    assert set(block["panels"]) == set(ATTRS) | {"overall"}
    panel = block["panels"]["trend_attr"]
    assert set(panel) >= {"n_models", "n_dropped", "means", "omnibus", "pairwise_p", "insufficient_n"}
    assert panel["omnibus"]["test"] == "friedman"


def test_complete_case_matrix_full_grid():
    by_ms, models, methods = _by_ms(_full_grid())
    block = _method_comparison(by_ms, models, ATTRS, methods, _CMP_CONFIG)
    panel = block["panels"]["trend_attr"]
    assert panel["n_models"] == len(MODELS)
    assert panel["n_dropped"] == 0
    assert panel["insufficient_n"] is False


def test_complete_case_drops_incomplete_model():
    # model_e loses its last method entirely -> incomplete for every category panel.
    by_ms, models, methods = _by_ms(_full_grid(drop=("model_e", STRATEGIES[-1])))
    block = _method_comparison(by_ms, models, ATTRS, methods, _CMP_CONFIG)
    panel = block["panels"]["trend_attr"]
    assert panel["n_models"] == len(MODELS) - 1
    assert panel["n_dropped"] == 1
    assert "model_e" in panel["dropped_models"]


def test_nan_cell_drops_model_from_that_panel_only():
    by_ms, models, methods = _by_ms(_full_grid(nan_cell=("model_a", STRATEGIES[0], "shift_attr")))
    block = _method_comparison(by_ms, models, ATTRS, methods, _CMP_CONFIG)
    # trend_attr unaffected; shift_attr drops model_a (its all_pick cell is NaN).
    assert block["panels"]["trend_attr"]["n_models"] == len(MODELS)
    shift = block["panels"]["shift_attr"]
    assert "model_a" in shift["dropped_models"]
    assert shift["n_models"] == len(MODELS) - 1


def test_friedman_p_matches_direct_scipy():
    by_ms, models, methods = _by_ms(_full_grid())
    block = _method_comparison(by_ms, models, ATTRS, methods, _CMP_CONFIG)
    panel = block["panels"]["trend_attr"]

    # Rebuild the complete-case TV-similarity matrix (models x methods) by hand.
    matrix = np.array(
        [[by_ms[(m, s)].tv_similarity["trend_attr"] for s in methods] for m in models],
        dtype=float,
    )
    chi2, p = stats.friedmanchisquare(*matrix.T)
    assert panel["omnibus"]["statistic"] == pytest.approx(float(chi2))
    assert panel["omnibus"]["p"] == pytest.approx(float(p))
    assert 0.0 <= panel["omnibus"]["kendall_w"] <= 1.0


def test_nemenyi_pairwise_symmetric_and_keyed_by_methods():
    by_ms, models, methods = _by_ms(_full_grid())
    block = _method_comparison(by_ms, models, ATTRS, methods, _CMP_CONFIG)
    pairwise = block["panels"]["trend_attr"]["pairwise_p"]
    # k=5 methods -> C(5,2)=10 unordered pairs.
    assert len(pairwise) == 10
    for a, b in zip(methods[:-1], methods[1:]):
        assert f"{a}|{b}" in pairwise
        assert 0.0 <= pairwise[f"{a}|{b}"] <= 1.0


def test_overall_panel_uses_overall_tv_similarity():
    by_ms, models, methods = _by_ms(_full_grid())
    block = _method_comparison(by_ms, models, ATTRS, methods, _CMP_CONFIG)
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
    block = _method_comparison(by_ms, models, ATTRS, methods, _CMP_CONFIG)
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
    block = _method_comparison(by_ms, models, ATTRS, methods, _CMP_CONFIG)
    panel = block["panels"]["trend_attr"]
    assert panel["n_models"] == 2
    assert panel["insufficient_n"] is True
    assert "note" in panel


# --------------------------------------------------------------------------- #
# Integration through build_method_significance                               #
# --------------------------------------------------------------------------- #


def test_build_attaches_method_comparison_block():
    result = build_method_significance(_full_grid(), ATTRS, comparison_config=_CMP_CONFIG)
    assert "method_comparison" in result
    assert result["method_comparison"]["methods"] == STRATEGIES
    assert set(result["method_comparison"]["panels"]) == set(ATTRS) | {"overall"}
