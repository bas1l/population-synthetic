"""Smoke tests for the method/model significance charts (matplotlib Agg backend).

Builds a small (model x strategy x attribute) grid, runs the builder, then drives
every chart function and asserts the expected files are written. Charts are pure
rendering downstream of the builder's serialisable result (+ the loader records
for the raw TV trend lines), so this just guards that they execute and emit files.

Skipped without the ``[analysis]`` extra (the builder needs statsmodels +
scikit-posthocs).
"""

from __future__ import annotations

import colorsys
import logging
from pathlib import Path

import pytest

pytest.importorskip("statsmodels")
pytest.importorskip("scikit_posthocs")
matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

import matplotlib.colors as mcolors  # noqa: E402

import population_synthetic.analysis.method_significance.charts as charts_module  # noqa: E402
from population_synthetic.analysis.method_significance.builder import (  # noqa: E402
    build_method_significance,
)
from population_synthetic.analysis.method_significance.charts import (  # noqa: E402
    plot_cd_diagram,
    plot_factor_dominance,
    plot_method_pair_significance,
    plot_method_trends,
    plot_reference_method_gap,
    plot_slope_heatmap,
)
from population_synthetic.analysis.utils.axes import strategy_complexity_order  # noqa: E402
from population_synthetic.analysis.utils.grid_variants import variant_suffixes  # noqa: E402
from population_synthetic.analysis.utils.labels import (  # noqa: E402
    attribute_label,
    method_key_lines,
    method_letters,
)
from population_synthetic.analysis.utils.palette import (  # noqa: E402
    HEATMAP_CMAP,
    MISSING_COLOR,
    SIGNIFICANCE_CMAP,
    heatmap_levels,
    relative_luminance,
)
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


# --------------------------------------------------------------------------- #
# the reference-method gap grid (methods x categories, one grid per run)       #
# --------------------------------------------------------------------------- #
#
# Same source as the squares above -- the serialised block -- for the same reason: only
# a hand-built block can state which comparisons were never made. What is new here is the
# orientation, which is the opposite of the squares', so the sign is asserted against the
# panel's own per-method means rather than against a number restated in the test.

_GAP_STEM = "swedish_reference_method_gap.png"


def _draw_gap(result, tmp_path, stem: str = _GAP_STEM):
    """Render the gap grid and return ``(paths, figures)``, with the writer intercepted."""
    captured: list = []
    original = charts_module.save_figure

    def spy(fig, path, **kwargs):
        captured.append(fig)
        return original(fig, path, **kwargs)

    charts_module.save_figure = spy
    try:
        paths = plot_reference_method_gap(result, tmp_path / stem)
    finally:
        charts_module.save_figure = original
    return paths, captured


def _gap_result(methods, pairs, *, attributes=None, country="swedish", **panel_kwargs):
    """A result whose every column carries the same panel, plus the pooled Overall one."""
    columns = list(attributes if attributes is not None else ms_fixtures.ATTRIBUTES)
    panels = {
        attr: ms_fixtures.panel(methods, pairs, **panel_kwargs) for attr in columns
    }
    panels["overall"] = ms_fixtures.panel(methods, pairs, **panel_kwargs)
    return ms_fixtures.result(methods, panels, country=country)


def test_the_gap_grid_writes_all_three_formats_for_every_variant(tmp_path):
    """One grid for the whole run, published twice, in the three formats."""
    methods = ms_fixtures.FIVE_METHODS
    result = _gap_result(methods, ms_fixtures.significant_pairs(methods))

    paths = plot_reference_method_gap(result, tmp_path / _GAP_STEM)

    expected = [
        tmp_path / f"{Path(_GAP_STEM).stem}{suffix}.png"
        for suffix, _variant in variant_suffixes(charts_module.REFERENCE_GRID_VARIANTS)
    ]
    assert paths == expected
    for path in expected:
        for suffix in (".png", ".svg", ".eps"):
            assert path.with_suffix(suffix).is_file()
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        f"{path.stem}{suffix}" for path in expected for suffix in (".png", ".svg", ".eps")
    )


@pytest.mark.parametrize("methods", [
    pytest.param(ms_fixtures.FIVE_METHODS, id="five"),
    pytest.param(ms_fixtures.FIVE_METHODS[:3], id="three"),
])
def test_the_reference_method_is_read_off_the_method_order(tmp_path, methods):
    """The reference is the axis's last method, never a letter frozen into the module.

    Run at two axis widths whose last methods are different families: a hardcoded
    reference would survive one of them and fail the other.
    """
    result = _gap_result(methods, ms_fixtures.significant_pairs(methods))

    _paths, figures = _draw_gap(result, tmp_path)
    ax = figures[0].axes[0]

    reference = methods[-1]
    letters = method_letters(methods)
    key_lines = dict(zip(letters, method_key_lines(methods)))
    row_labels = [text.get_text() for text in ax.get_yticklabels()]

    # Every simpler method is a row, in complexity order, and the reference is not.
    assert row_labels == [letters[method] for method in methods[:-1]]
    assert letters[reference] not in row_labels
    # And the title names it by letter and family phrase, so the figure stays correct
    # when both strategy versions are live and the letters become A1/A2/...
    assert key_lines[reference] in ax.get_title()


def test_the_printed_gap_is_the_reference_minus_the_row_method(tmp_path):
    """The orientation this figure inverts: reference minus row, not row minus reference.

    Asserted against the panel's own per-method means, so the test states the subtraction
    rather than a number, and a renderer that read the mirrored index pair would print
    every cell with the wrong sign and fail here.
    """
    methods = ms_fixtures.FIVE_METHODS
    # One simpler method beats the reference and the rest do not, so both signs appear:
    # a flipped orientation cannot pass by accident on an all-positive fixture.
    means = {
        method: value
        for method, value in zip(methods, [0.50, 0.53, 0.56, 0.62, 0.59])
    }
    pairs = ms_fixtures.pairs_from_means(methods, means)
    result = _gap_result(methods, pairs, means=means)

    _paths, figures = _draw_gap(result, tmp_path)
    ax = figures[0].axes[0]
    texts = _annotations(ax)

    reference = methods[-1]
    rows = methods[:-1]
    columns = ms_fixtures.ATTRIBUTES + ["overall"]
    for i, method in enumerate(rows):
        gap = means[reference] - means[method]
        for j in range(len(columns)):
            printed = texts[(float(j), float(i))].splitlines()[0]
            assert printed == f"{gap:+.3f}"
            # The mirrored subtraction is a different string for every row here, which
            # is what makes the assertion above about orientation and not about format.
            assert printed != f"{means[method] - means[reference]:+.3f}"


def test_an_untested_comparison_reads_differently_from_a_non_significant_one(tmp_path):
    """Absent must not read as measured -- the same rule the squares are held to."""
    methods = ms_fixtures.FIVE_METHODS
    reference_at = len(methods) - 1
    pairs = ms_fixtures.significant_pairs(methods)
    # Row 0 against the reference: tested and non-significant. Row 1: never tested.
    pairs[(0, reference_at)] = (0.4, 0.01, 6)
    del pairs[(1, reference_at)]
    result = _gap_result(methods, pairs)

    _paths, figures = _draw_gap(result, tmp_path)
    ax = figures[0].axes[0]
    texts = _annotations(ax)
    painted = ax.get_images()[0].get_array()
    ladder = charts_module._star_ladder(
        ms_fixtures.star_thresholds(), ms_fixtures.ns_symbol(),
    )

    ns_text = texts[(0.0, 0.0)]
    untested_text = texts[(0.0, 1.0)]
    assert ns_text.splitlines()[-1] == ms_fixtures.ns_symbol()
    assert untested_text == charts_module.REFERENCE_GRID_VARIANT_CLEAN.policy.absent_text
    assert untested_text != ns_text
    # Two states of the ramp, not two labels on one fill: the non-significant comparison
    # is painted at the palest tier, the untested one not at all.
    assert not painted.mask[0, 0]
    assert painted[0, 0] == ladder.index(ms_fixtures.ns_symbol())
    assert painted.mask[1, 0]


def test_an_insufficient_n_category_is_an_unpainted_marked_column(tmp_path, caplog):
    """A degenerate panel loses its column's fills, not its column -- and it is logged.

    Blanking the column would drop the category from the figure's own axis and read as
    "this category was analysed and nothing separated"; the honest rendering is the same
    unpainted, marked state an untested pair takes anywhere else in the layer.
    """
    methods = ms_fixtures.FIVE_METHODS
    note = "2 complete model(s) < 3; recorded but not charted"
    pairs = ms_fixtures.significant_pairs(methods)
    degenerate, healthy = ms_fixtures.ATTRIBUTES
    result = ms_fixtures.result(methods, {
        degenerate: ms_fixtures.panel(
            methods, {}, n_models=2, insufficient_n=True, note=note, omnibus_p=None,
        ),
        healthy: ms_fixtures.panel(methods, pairs),
        "overall": ms_fixtures.panel(methods, pairs),
    })

    with caplog.at_level(logging.WARNING):
        paths, figures = _draw_gap(result, tmp_path)

    assert len(paths) == len(charts_module.REFERENCE_GRID_VARIANTS)
    for path in paths:
        assert path.is_file()

    ax = figures[0].axes[0]
    painted = ax.get_images()[0].get_array()
    texts = _annotations(ax)
    absent = charts_module.REFERENCE_GRID_VARIANT_CLEAN.policy.absent_text
    n_rows = len(methods) - 1
    # The degenerate category is the first column; every row of it is unpainted and marked.
    assert all(painted.mask[i, 0] for i in range(n_rows))
    assert all(texts[(0.0, float(i))] == absent for i in range(n_rows))
    # Its neighbours are untouched -- one bad panel does not blank the figure.
    assert not any(painted.mask[i, 1] for i in range(n_rows))
    # The column still carries its heading, and the skip is logged with the panel's own
    # wording rather than with any authored in the chart.
    assert any(
        attribute_label(degenerate) in text.get_text()
        for text in ax.get_xticklabels()
    )
    assert any(note in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize("methods", [
    pytest.param(ms_fixtures.FIVE_METHODS, id="four_rows"),
    pytest.param(ms_fixtures.TEN_METHODS, id="nine_rows"),
])
def test_the_gap_grid_stays_inside_the_print_budget_at_the_live_column_count(
    tmp_path, methods,
):
    """The live 15-column shape, at one strategy version and at both.

    ``save_figure`` raises ``FigureBudgetExceeded`` *before* writing anything, so a canvas
    or file-size breach surfaces here as an error rather than as a missing file. The
    columns come from the country's own analysed axis, so the widest shape this test
    covers is the widest shape the sweep can draw.
    """
    result = _gap_result(
        methods,
        ms_fixtures.significant_pairs(methods),
        attributes=ms_fixtures.LIVE_ATTRIBUTES,
        country="swedish_02",
    )

    paths = plot_reference_method_gap(
        result, tmp_path / "swedish_02_reference_method_gap.png",
    )

    assert len(paths) == len(charts_module.REFERENCE_GRID_VARIANTS)
    for path in paths:
        for suffix in (".png", ".svg", ".eps"):
            assert path.with_suffix(suffix).is_file()


def test_a_single_method_axis_draws_no_gap_grid(tmp_path):
    """With nothing simpler than the reference there is no comparison to draw."""
    methods = ms_fixtures.FIVE_METHODS[:1]
    result = _gap_result(methods, {})

    assert plot_reference_method_gap(result, tmp_path / _GAP_STEM) == []
    assert not list(tmp_path.iterdir())


def test_a_tested_comparison_with_no_difference_to_print_raises(tmp_path):
    """A painted tier with nothing to qualify is a figure contradicting itself."""
    methods = ms_fixtures.FIVE_METHODS
    result = _gap_result(methods, ms_fixtures.significant_pairs(methods))
    reference_at = len(methods) - 1
    panel = result["method_comparison"]["panels"]["overall"]
    panel["pair_matrix"]["mean_diff"][reference_at][0] = None

    with pytest.raises(ValueError, match="no mean difference"):
        plot_reference_method_gap(result, tmp_path / _GAP_STEM)


# ------------------------------------------------------------------
# The ramp the two grids share
# ------------------------------------------------------------------
#
# Both grids paint an *ordinal grade* rather than a magnitude, which is why they are the
# layer's only departure from the house ramp. The properties below are what make the
# departure worth having, so each is asserted on the mappable the renderer actually
# built rather than on the constant it was built from.


def _significance_steps():
    """The RGB the ladder's rungs are painted, in ladder order (most significant first)."""
    ladder = charts_module._star_ladder(
        ms_fixtures.star_thresholds(), ms_fixtures.ns_symbol(),
    )
    cmap = heatmap_levels(len(ladder), name=SIGNIFICANCE_CMAP)
    return ladder, [cmap(i)[:3] for i in range(len(ladder))]


@pytest.mark.parametrize("draw", [
    pytest.param(_draw_one, id="pair_squares"),
    pytest.param(_draw_gap, id="reference_gap"),
])
def test_both_significance_grids_paint_on_the_significance_ramp(tmp_path, draw):
    """Not the house ramp: a tier is an ordinal grade, and inferno's hue changes read
    as changes of kind rather than of degree.

    Asserted on the drawn mappable, so a call site left on the default would fail here
    rather than only in the picture. Both grids are checked because a cell is meant to
    read the same in either figure.
    """
    methods = ms_fixtures.FIVE_METHODS
    pairs = ms_fixtures.significant_pairs(methods)
    result = (
        ms_fixtures.result(methods, {"overall": ms_fixtures.panel(methods, pairs)})
        if draw is _draw_one
        else _gap_result(methods, pairs)
    )

    _paths, figures = draw(result, tmp_path)
    cmap = figures[0].axes[0].get_images()[0].cmap

    assert cmap.name == SIGNIFICANCE_CMAP
    assert cmap.name != HEATMAP_CMAP
    ladder, _steps = _significance_steps()
    assert cmap.N == len(ladder)


def test_the_significance_ramp_darkens_towards_the_most_significant_rung():
    """Brightness alone carries the ladder, and it runs the right way round.

    Index 0 of the ladder is ``****``. A ramp that brightened towards it would paint the
    strongest finding as the faintest cell -- the reading every other grid in the layer
    gives to its lowest value.
    """
    ladder, steps = _significance_steps()
    luminances = [relative_luminance(rgb) for rgb in steps]

    assert ladder[0] == "****" and ladder[-1] == ms_fixtures.ns_symbol()
    assert luminances == sorted(luminances)
    assert all(a < b for a, b in zip(luminances, luminances[1:]))
    # The palest painted rung stays clearly lighter than the unpainted "never tested"
    # grey, because those are different findings the grids draw differently on purpose.
    assert luminances[-1] > relative_luminance(mcolors.to_rgb(MISSING_COLOR))


def test_the_significance_ramp_is_a_single_hue():
    """One hue, so no step can be told from its neighbour by anything but its darkness.

    A multi-hue ramp invites reading the ladder as a set of kinds -- the red tier, the
    yellow tier -- when the only relation between the rungs is more and less.
    """
    _ladder, steps = _significance_steps()
    hues = [colorsys.rgb_to_hls(*rgb)[0] * 360.0 for rgb in steps]

    assert max(hues) - min(hues) < 30.0


@pytest.mark.parametrize("draw", [
    pytest.param(_draw_one, id="pair_squares"),
    pytest.param(_draw_gap, id="reference_gap"),
])
def test_the_cell_text_stays_legible_at_both_ends_of_the_ramp(tmp_path, draw):
    """Derived from the painted colour, never hardcoded: white on the darkest rung,
    black on the palest.

    A ramp change that left an annotation colour behind produces a figure that renders
    without error and cannot be read, so the two extreme rungs are drawn together and
    both are checked.
    """
    methods = ms_fixtures.FIVE_METHODS
    ladder = charts_module._star_ladder(
        ms_fixtures.star_thresholds(), ms_fixtures.ns_symbol(),
    )
    # The tightest configured cutoff lands on the darkest rung; a p of 0.9 on the palest.
    # Two cells carry it, because the two figures read opposite index pairs of the same
    # matrix: the square draws (0, 1), the gap grid the reference against row 0.
    strongest = min(float(entry["max_p"]) for entry in ms_fixtures.star_thresholds())
    pairs = ms_fixtures.significant_pairs(methods, p=0.9)
    pairs[(0, 1)] = (strongest, 0.02, 6)
    pairs[(0, len(methods) - 1)] = (strongest, 0.02, 6)
    result = (
        ms_fixtures.result(methods, {"overall": ms_fixtures.panel(methods, pairs)})
        if draw is _draw_one
        else _gap_result(methods, pairs)
    )

    _paths, figures = draw(result, tmp_path)
    ax = figures[0].axes[0]
    painted = ax.get_images()[0].get_array()
    colors = {
        tuple(text.get_position()): text.get_color() for text in ax.texts
    }

    darkest = 0
    palest = ladder.index(ms_fixtures.ns_symbol())
    seen = set()
    for (x, y), color in colors.items():
        j, i = int(round(x)), int(round(y))
        if painted.mask[i, j]:
            continue
        tier = int(painted[i, j])
        if tier == darkest:
            assert color == "white"
            seen.add("dark")
        elif tier == palest:
            assert color == "black"
            seen.add("pale")
    assert seen == {"dark", "pale"}
