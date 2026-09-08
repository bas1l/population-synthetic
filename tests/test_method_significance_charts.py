"""Smoke tests for the method/model significance charts (matplotlib Agg backend).

Builds a small (model x strategy x attribute) grid, runs the builder, then drives
every chart function and asserts the expected files are written. Charts are pure
rendering downstream of the builder's serialisable result (+ the loader records
for the raw TV trend lines), so this just guards that they execute and emit files.

Skipped without the ``[analysis]`` extra (the builder needs statsmodels +
scikit-posthocs).
"""

from __future__ import annotations

import logging

import pytest

pytest.importorskip("statsmodels")
pytest.importorskip("scikit_posthocs")
matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

import population_synthetic.analysis.method_significance.charts as charts_module  # noqa: E402
from population_synthetic.analysis.method_significance.builder import (  # noqa: E402
    build_method_significance,
)
from population_synthetic.analysis.method_significance.charts import (  # noqa: E402
    plot_cd_diagram,
    plot_factor_dominance,
    plot_method_pair_significance,
    plot_method_trends,
    plot_slope_heatmap,
)
from population_synthetic.analysis.utils.axes import strategy_complexity_order  # noqa: E402
from population_synthetic.analysis.utils.grid_variants import variant_suffixes  # noqa: E402
from tests import _method_significance_fixtures as ms_fixtures  # noqa: E402
from tests._performance_fixtures import make_combo  # noqa: E402

# The layer-wide variant assertions, reused rather than restated: a new grid family is
# held to the property every other family is already held to.
from tests.test_grids import (  # noqa: E402
    _assert_clean_drops_only_the_count_line,
    _assert_substitutable,
)

# Real axis ids throughout. The charts resolve every id they print through
# ``analysis/utils/labels.py``, which raises on an id with no display string in config,
# so a fixture built from invented ids would only ever exercise the raise. The values
# below are the *shape* of a run, drawn from the real model and attribute axes.
MODELS = ["claude_haiku", "claude_sonnet", "openrouter_kimi_k3", "ollama_qwen3_14b"]
# The five v1 families, ordered by the config-derived accessor (the same order
# every consumer resolves; asserted against the legacy sequence in test_axes.py).
STRATEGIES = strategy_complexity_order([
    "all_generate_evaluate_random_pick",
    "all_generate_evaluate_pick",
    "all_generate_pick",
    "all_pick_dag",
    "all_pick",
])
#: One attribute carrying a monotone method trend and one carrying none, so the trend
#: test has both a positive and a null case. Which canonical attribute plays which role
#: is arbitrary -- only the numbers below decide it.
TREND_ATTR = "education_level"
NULL_ATTR = "housing_tenure"
ATTRS = [TREND_ATTR, NULL_ATTR]
CATEGORY_VALUES = {
    TREND_ATTR: ["Primary", "Upper secondary", "Tertiary", "Unknown"],
    NULL_ATTR: ["Owned", "Rented", "Other"],
}
_NULL_VALUES = [0.10, 0.20, 0.30, 0.40, 0.50]


def _grid():
    combos = []
    for m_idx, model in enumerate(MODELS):
        for rank, strategy in enumerate(STRATEGIES, start=1):
            combos.append(
                make_combo(
                    slug=f"swedish_{strategy}_{model}",
                    strategy=strategy,
                    model=model,
                    tv_by_attr={
                        TREND_ATTR: round(0.05 + 0.15 * (rank - 1) + 0.004 * m_idx, 4),
                        NULL_ATTR: _NULL_VALUES[(m_idx + (rank - 1)) % 5],
                    },
                )
            )
    return combos


def test_all_charts_write_files(tmp_path):
    records = _grid()
    result = build_method_significance(records, ATTRS, category_values=CATEGORY_VALUES)

    heatmap = plot_slope_heatmap(result, tmp_path / "swedish_slope_heatmap.png")
    cd = plot_cd_diagram(result, tmp_path / "swedish_cd_diagram.png")
    dominance = plot_factor_dominance(result, tmp_path / "swedish_factor_dominance.png")
    trends = plot_method_trends(result, records, tmp_path / "swedish_method_trends")

    assert heatmap is not None and heatmap.is_file()
    assert cd is not None and cd.is_file()
    assert dominance is not None and dominance.is_file()
    assert len(trends) == len(ATTRS)
    for path in trends:
        assert path.is_file()


# --------------------------------------------------------------------------- #
# the method x method pairwise-significance grids                              #
# --------------------------------------------------------------------------- #
#
# Driven from the serialised block rather than from a fitted grid: the renderer is a
# pure consumer of ``pair_matrix``, and only a hand-built block can state which pairs
# were tested, which were never tested, and which p sits exactly on a cutoff.


def _annotations(ax) -> dict[tuple[float, float], str]:
    """Every cell annotation on *ax*, keyed by its data position."""
    return {tuple(text.get_position()): text.get_text() for text in ax.texts}


def _draw_one(result, tmp_path):
    """Render *result* and return ``(paths, figures)``, with the writer intercepted.

    The figures are captured as well as written, because several of the properties
    asserted below -- what a cell printed, what the ramp painted -- live on the
    ``Figure`` and not in the file.
    """
    captured: list = []
    original = charts_module.save_figure

    def spy(fig, path, **kwargs):
        captured.append(fig)
        return original(fig, path, **kwargs)

    charts_module.save_figure = spy
    try:
        paths = plot_method_pair_significance(result, tmp_path)
    finally:
        charts_module.save_figure = original
    return paths, captured


def test_pair_significance_writes_all_three_formats_for_every_panel_and_variant(tmp_path):
    """Every panel is published twice, in the three formats, and only those are returned."""
    methods = ms_fixtures.FIVE_METHODS
    pairs = ms_fixtures.significant_pairs(methods)
    result = ms_fixtures.result(methods, {
        ms_fixtures.ATTRIBUTES[0]: ms_fixtures.panel(methods, pairs),
        "overall": ms_fixtures.panel(methods, pairs),
    })

    paths = plot_method_pair_significance(result, tmp_path)

    expected = [
        tmp_path / f"{stem}{suffix}.png"
        for stem in (ms_fixtures.ATTRIBUTES[0], "overall")
        for suffix, _variant in variant_suffixes(charts_module.GRID_VARIANTS)
    ]
    assert paths == expected
    for path in expected:
        for suffix in (".png", ".svg", ".eps"):
            assert path.with_suffix(suffix).is_file()
    # Nothing beyond the declared stems: the canonical file is unsuffixed and the
    # counted one is its only sibling.
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        f"{path.stem}{suffix}" for path in expected for suffix in (".png", ".svg", ".eps")
    )


def test_the_two_pair_significance_variants_are_the_same_figure(tmp_path):
    """Substitutability, on the layer's own terms: only the cell text may differ."""
    methods = ms_fixtures.FIVE_METHODS
    result = ms_fixtures.result(methods, {
        "overall": ms_fixtures.panel(methods, ms_fixtures.significant_pairs(methods)),
    })

    _paths, figures = _draw_one(result, tmp_path)
    clean, counted = figures  # the canonical variant is published first
    _assert_substitutable(counted, clean, "method_significance::pair_significance")
    _assert_clean_drops_only_the_count_line(
        counted, clean, "method_significance::pair_significance",
    )


def test_an_insufficient_n_panel_prints_the_blocks_own_note(tmp_path, caplog):
    """The placeholder's wording is the builder's, and the skip is logged, not silent."""
    methods = ms_fixtures.FIVE_METHODS
    note = "2 complete model(s) < 3; recorded but not charted"
    result = ms_fixtures.result(methods, {
        "overall": ms_fixtures.panel(
            methods, {}, n_models=2, insufficient_n=True, note=note, omnibus_p=None,
        ),
    })

    with caplog.at_level(logging.WARNING):
        paths, figures = _draw_one(result, tmp_path)

    assert len(paths) == len(charts_module.GRID_VARIANTS)
    for path in paths:
        assert path.is_file()
    for figure in figures:
        assert note in [text.get_text() for text in figure.axes[0].texts]
    assert any(note in record.getMessage() for record in caplog.records)


def test_an_insufficient_n_panel_without_a_note_raises(tmp_path):
    """Caveat text is data: the renderer never authors a placeholder of its own."""
    methods = ms_fixtures.FIVE_METHODS
    result = ms_fixtures.result(methods, {
        "overall": ms_fixtures.panel(methods, {}, n_models=2, insufficient_n=True),
    })

    with pytest.raises(ValueError, match="note"):
        plot_method_pair_significance(result, tmp_path)


def test_an_untested_pair_reads_differently_from_a_non_significant_one(tmp_path):
    """The correctness failure this figure exists to avoid: absent read as measured."""
    methods = ms_fixtures.FIVE_METHODS
    # (0, 1) tested and non-significant; (0, 2) never tested; everything else tested.
    pairs = ms_fixtures.significant_pairs(methods)
    pairs[(0, 1)] = (0.4, 0.01, 6)
    del pairs[(0, 2)]
    result = ms_fixtures.result(methods, {
        "overall": ms_fixtures.panel(methods, pairs),
    })

    _paths, figures = _draw_one(result, tmp_path)
    ax = figures[0].axes[0]
    texts = _annotations(ax)
    painted = ax.get_images()[0].get_array()

    ns_text = texts[(1.0, 0.0)]
    untested_text = texts[(2.0, 0.0)]
    assert ns_text == f"+0.010\n{ms_fixtures.ns_symbol()}"
    assert untested_text == charts_module.GRID_VARIANT_CLEAN.policy.absent_text
    assert untested_text != ns_text
    # And the two are different states of the ramp, not two labels on one fill: the
    # non-significant pair is painted at the palest tier, the untested one not at all.
    assert not painted.mask[0, 1]
    assert painted.mask[0, 2]
    # The diagonal is unpainted like the untested cell, and prints nothing at all.
    assert painted.mask[0, 0]
    assert (0.0, 0.0) not in texts


def test_a_p_on_a_cutoff_is_painted_at_the_tier_the_star_lookup_assigns(tmp_path):
    """Fill and printed symbol come from one lookup, so a cutoff cannot split them."""
    methods = ms_fixtures.FIVE_METHODS
    thresholds = ms_fixtures.star_thresholds()
    ns = ms_fixtures.ns_symbol()
    ladder = charts_module._star_ladder(thresholds, ns)
    cutoffs = sorted(float(entry["max_p"]) for entry in thresholds)

    pairs = ms_fixtures.significant_pairs(methods)
    # One pair sitting exactly on each configured cutoff, plus one a hair above the
    # loosest -- the only p in the set that must fall through to the ns rung.
    on_cutoff = [(0, 1), (0, 2), (0, 3), (0, 4)][: len(cutoffs)]
    for cell, cutoff in zip(on_cutoff, cutoffs):
        pairs[cell] = (cutoff, 0.02, 6)
    pairs[(1, 2)] = (cutoffs[-1] + 1e-9, 0.02, 6)
    result = ms_fixtures.result(methods, {
        "overall": ms_fixtures.panel(methods, pairs),
    })

    _paths, figures = _draw_one(result, tmp_path)
    ax = figures[0].axes[0]
    painted = ax.get_images()[0].get_array()
    texts = _annotations(ax)

    for cell, cutoff in zip(on_cutoff, cutoffs):
        i, j = cell
        symbol = charts_module._p_to_stars(cutoff, thresholds, ns)
        assert texts[(float(j), float(i))].endswith(symbol)
        assert painted[i, j] == ladder.index(symbol)
    assert texts[(2.0, 1.0)].endswith(ns)
    assert painted[1, 2] == ladder.index(ns)


def test_a_panel_where_every_pair_is_non_significant_is_pale_but_not_blank(tmp_path):
    """Uniformly ns is a finding; a blank grid would read as no data at all."""
    methods = ms_fixtures.FIVE_METHODS
    ns = ms_fixtures.ns_symbol()
    result = ms_fixtures.result(methods, {
        "overall": ms_fixtures.panel(
            methods, ms_fixtures.significant_pairs(methods, p=0.9), omnibus_p=0.9,
        ),
    })

    _paths, figures = _draw_one(result, tmp_path)
    ax = figures[0].axes[0]
    painted = ax.get_images()[0].get_array()
    ladder = charts_module._star_ladder(ms_fixtures.star_thresholds(), ns)

    off_diagonal = [
        (i, j)
        for i in range(len(methods)) for j in range(len(methods)) if i != j
    ]
    assert all(painted[i, j] == ladder.index(ns) for i, j in off_diagonal)
    assert not any(painted.mask[i, j] for i, j in off_diagonal)
    assert len(_annotations(ax)) == len(off_diagonal)


@pytest.mark.parametrize("methods", [
    pytest.param(ms_fixtures.FIVE_METHODS[:2], id="k2"),
    pytest.param(ms_fixtures.TEN_METHODS, id="k10"),
])
def test_the_square_stays_inside_the_print_budget_at_both_axis_widths(tmp_path, methods):
    """Two methods, and both strategy versions live -- the narrowest and widest squares.

    ``save_figure`` raises ``FigureBudgetExceeded`` *before* writing anything, so a
    breach at either width surfaces here as an error rather than as a missing file.
    """
    result = ms_fixtures.result(methods, {
        "overall": ms_fixtures.panel(methods, ms_fixtures.significant_pairs(methods)),
    })

    paths = plot_method_pair_significance(result, tmp_path)

    assert len(paths) == len(charts_module.GRID_VARIANTS)
    for path in paths:
        for suffix in (".png", ".svg", ".eps"):
            assert path.with_suffix(suffix).is_file()


def test_a_tested_pair_with_no_difference_to_print_raises(tmp_path):
    """A painted tier with nothing to qualify is a figure contradicting itself."""
    methods = ms_fixtures.FIVE_METHODS
    result = ms_fixtures.result(methods, {
        "overall": ms_fixtures.panel(methods, ms_fixtures.significant_pairs(methods)),
    })
    result["method_comparison"]["panels"]["overall"]["pair_matrix"]["mean_diff"][0][1] = None

    with pytest.raises(ValueError, match="no mean difference"):
        plot_method_pair_significance(result, tmp_path)
