"""Tests for the method-comparison figure renderer (Phase 2).

Covers the pure-consumer chart in
``population_synthetic.analysis.method_significance.charts``:

* ``_p_to_stars`` boundary mapping against the repo star thresholds;
* ``plot_method_comparison`` returns a PNG ``Path`` with an SVG sibling from a
  built ``result`` fixture (grid + ``overall_only`` variants);
* an ``insufficient_n`` panel renders its placeholder without error.

The renderer imports the builder (for ``resolve_pairs`` / ``load_comparison_config``)
and matplotlib; the block itself leans on the ``[analysis]`` extra, so the module is
skipped without it.
"""

from __future__ import annotations

import pytest

pytest.importorskip("statsmodels")
pytest.importorskip("scikit_posthocs")

from population_synthetic.analysis.method_significance.builder import (  # noqa: E402
    build_method_significance,
    load_comparison_config,
)
from population_synthetic.analysis.method_significance.charts import (  # noqa: E402
    _p_to_stars,
    _stack_bracket_levels,
    plot_method_comparison,
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
CATEGORY_VALUES = {"trend_attr": ["a", "b", "c", "d"], "shift_attr": ["x", "y", "z"]}


def _trend_tv(m_idx: int, rank: int) -> float:
    return round(0.05 + 0.15 * (rank - 1) + 0.004 * m_idx, 4)


def _shift_tv(m_idx: int, rank: int) -> float:
    return round(0.40 - 0.05 * (rank - 1) + 0.01 * ((m_idx + rank) % 3), 4)


def _full_grid(models=MODELS):
    combos = []
    for m_idx, model in enumerate(models):
        for rank, strategy in enumerate(STRATEGIES, start=1):
            combos.append(make_combo(
                slug=f"swedish_{strategy}_{model}", strategy=strategy, model=model,
                tv_by_attr={"trend_attr": _trend_tv(m_idx, rank),
                            "shift_attr": _shift_tv(m_idx, rank)},
            ))
    return combos


# --------------------------------------------------------------------------- #
# _p_to_stars boundary mapping                                                #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def _thresholds_and_ns():
    cfg = load_comparison_config()
    return cfg["star_thresholds"], cfg["ns_symbol"]


@pytest.mark.parametrize(
    "p, expected",
    [
        (0.2, "ns"),
        (0.05, "*"),
        (0.049, "*"),
        (0.01, "**"),
        (0.001, "***"),
        (0.0001, "****"),
        (0.00005, "****"),
        (None, "ns"),
    ],
)
def test_p_to_stars_boundaries(_thresholds_and_ns, p, expected):
    thresholds, ns = _thresholds_and_ns
    assert _p_to_stars(p, thresholds, ns) == expected


def test_p_just_above_005_is_ns(_thresholds_and_ns):
    thresholds, ns = _thresholds_and_ns
    assert _p_to_stars(0.0500001, thresholds, ns) == "ns"


# --------------------------------------------------------------------------- #
# Bracket stacking                                                            #
# --------------------------------------------------------------------------- #


def test_stack_levels_non_overlapping_share_level():
    # Two disjoint spans can share level 0; a span overlapping both climbs.
    levels = _stack_bracket_levels([(0.0, 1.0), (2.0, 3.0), (0.5, 2.5)])
    assert levels[0] == 0
    assert levels[1] == 0
    assert levels[2] >= 1


# --------------------------------------------------------------------------- #
# plot_method_comparison                                                      #
# --------------------------------------------------------------------------- #


def test_grid_returns_png_and_svg(tmp_path):
    result = build_method_significance(_full_grid(), ATTRS,
                                       category_values=CATEGORY_VALUES,
                                       comparison_config=load_comparison_config())
    out = plot_method_comparison(result, tmp_path / "swedish_method_comparison.png")
    assert out is not None
    assert out.suffix == ".png"
    assert out.is_file()
    assert out.with_suffix(".svg").is_file()


def test_overall_only_renders_single_panel(tmp_path):
    result = build_method_significance(_full_grid(), ATTRS,
                                       category_values=CATEGORY_VALUES,
                                       comparison_config=load_comparison_config())
    out = plot_method_comparison(
        result, tmp_path / "swedish_method_comparison_overall.png", overall_only=True
    )
    assert out is not None and out.is_file()
    assert out.with_suffix(".svg").is_file()


def test_returns_none_when_block_absent(tmp_path):
    assert plot_method_comparison({}, tmp_path / "none.png") is None
    assert plot_method_comparison({"method_comparison": {}}, tmp_path / "none.png") is None


def _crafted_result(*, pairwise_p, n_category_values, pairs_mode="significant-only"):
    """A minimal built-shaped result for pure-consumer renderer tests.

    One category panel + a trivial Overall panel; the star mapping is echoed from
    the real config so the renderer stays a pure consumer.
    """
    cfg = load_comparison_config()
    methods = STRATEGIES[:3]
    panel = {
        "n_models": 5,
        "n_dropped": 0,
        "dropped_models": [],
        "means": {s: 0.8 for s in methods},
        "per_model": {f"m{i}": {s: 0.8 for s in methods} for i in range(5)},
        "omnibus": {"test": "friedman", "statistic": 1.0, "p": 0.6, "p_bh": 0.6, "kendall_w": 0.1},
        "pairwise_p": pairwise_p,
        "insufficient_n": False,
        "n_category_values": n_category_values,
    }
    overall = dict(panel)
    overall.pop("n_category_values")
    return {
        "metadata": {"country": "swedish"},
        "method_comparison": {
            "response": "tv_similarity",
            "methods": methods,
            "pairs_mode": pairs_mode,
            "star_thresholds": cfg["star_thresholds"],
            "ns_symbol": cfg["ns_symbol"],
            "panels": {"age_group": panel, "overall": overall},
        },
    }


def test_zero_significant_pairs_panel_renders_without_brackets(tmp_path):
    # significant-only: every pair non-significant -> no bracket drawn, but the
    # bars + header (with the level count) still render without error.
    methods = STRATEGIES[:3]
    ns_pairwise = {f"{a}|{b}": 0.9 for i, a in enumerate(methods) for b in methods[i + 1:]}
    result = _crafted_result(pairwise_p=ns_pairwise, n_category_values=7)
    out = plot_method_comparison(result, tmp_path / "zero_sig.png")
    assert out is not None and out.is_file()
    assert out.with_suffix(".svg").is_file()


def test_insufficient_n_panel_renders_without_error(tmp_path, caplog):
    # Two models only -> every panel is insufficient_n (n<3); must still render.
    result = build_method_significance(
        _full_grid(models=["solo_a", "solo_b"]), ATTRS,
        category_values=CATEGORY_VALUES,
        comparison_config=load_comparison_config(),
    )
    assert result["method_comparison"]["panels"]["trend_attr"]["insufficient_n"] is True
    import logging
    with caplog.at_level(logging.WARNING):
        out = plot_method_comparison(result, tmp_path / "insufficient.png")
    assert out is not None and out.is_file()
    assert any("insufficient n" in rec.message for rec in caplog.records)
