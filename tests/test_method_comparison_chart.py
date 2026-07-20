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
from population_synthetic.analysis.utils.axes import STRATEGY_COMPLEXITY_ORDER  # noqa: E402
from tests._performance_fixtures import make_combo  # noqa: E402

MODELS = ["model_a", "model_b", "model_c", "model_d", "model_e"]
STRATEGIES = list(STRATEGY_COMPLEXITY_ORDER)
ATTRS = ["trend_attr", "shift_attr"]


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
                                       comparison_config=load_comparison_config())
    out = plot_method_comparison(result, tmp_path / "swedish_method_comparison.png")
    assert out is not None
    assert out.suffix == ".png"
    assert out.is_file()
    assert out.with_suffix(".svg").is_file()


def test_overall_only_renders_single_panel(tmp_path):
    result = build_method_significance(_full_grid(), ATTRS,
                                       comparison_config=load_comparison_config())
    out = plot_method_comparison(
        result, tmp_path / "swedish_method_comparison_overall.png", overall_only=True
    )
    assert out is not None and out.is_file()
    assert out.with_suffix(".svg").is_file()


def test_returns_none_when_block_absent(tmp_path):
    assert plot_method_comparison({}, tmp_path / "none.png") is None
    assert plot_method_comparison({"method_comparison": {}}, tmp_path / "none.png") is None


def test_insufficient_n_panel_renders_without_error(tmp_path, caplog):
    # Two models only -> every panel is insufficient_n (n<3); must still render.
    result = build_method_significance(
        _full_grid(models=["solo_a", "solo_b"]), ATTRS,
        comparison_config=load_comparison_config(),
    )
    assert result["method_comparison"]["panels"]["trend_attr"]["insufficient_n"] is True
    import logging
    with caplog.at_level(logging.WARNING):
        out = plot_method_comparison(result, tmp_path / "insufficient.png")
    assert out is not None and out.is_file()
    assert any("insufficient n" in rec.message for rec in caplog.records)
