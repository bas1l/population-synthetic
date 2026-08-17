"""Tests for the manuscript fidelity heatmap-tables (models + methods renderers).

Pure-consumer renderers over a built ``result`` dict: exercise the PNG+SVG dual
output, the global-best-strategy selection cited in the models-table title, the
Overall-sort of both tables, the drop-and-report of a model missing at the
global-best strategy, the provenance side-marker (row-label colour), the LaTeX
snippet emitters, and the empty / all-NaN ``None`` contract. Figures / snippets
are written to a pytest ``tmp_path``, never the repo.

A second group pins the *visual grammar* now shared with
:mod:`population_synthetic.analysis.model_ranking.table_style`: the grid values
actually drawn, the row and column order, the annotation text, the best-cell
boxing and bolding, the Overall divider, the host label colours, and the
extracted helpers' own contracts. These are structural assertions on the rendered
artists -- never byte comparisons of the PNG, whose bytes move with matplotlib
metadata and font hinting without anything about the figure having changed.
"""

from __future__ import annotations

import re

import numpy as np

from population_synthetic.analysis.model_ranking.builder import build_performance_comparison
from population_synthetic.analysis.model_ranking.manuscript_tables import (
    plot_method_fidelity_table,
    plot_model_fidelity_table,
    write_method_fidelity_latex,
    write_model_fidelity_latex,
)
from population_synthetic.analysis.model_ranking.table_style import (
    HOST_COLORS,
    add_percentage_colorbar,
    best_cells_per_column,
    categories_on_top,
    inferno_cmap,
    vertical_divider,
)
from population_synthetic.analysis.utils.palette import HEATMAP_CMAP, MISSING_COLOR
from tests._performance_fixtures import ATTRIBUTES, make_combo


def _grid():
    """2 models x 2 strategies; all_pick strictly better than all_generate_pick.

    Under STRATEGY_COMPLEXITY_ORDER (all_pick before all_generate_pick) all_pick
    is both the higher-scoring and the simpler strategy -> global-best.
    """
    return [
        make_combo(
            slug="swedish_all_pick_claude_haiku", strategy="all_pick", model="claude_haiku",
            tv_by_attr={"age_group": 0.1, "biological_sex": 0.1, "education_level": 0.1},
        ),
        make_combo(
            slug="swedish_all_pick_gemini_flash", strategy="all_pick", model="gemini_flash",
            tv_by_attr={"age_group": 0.3, "biological_sex": 0.3, "education_level": 0.3},
        ),
        make_combo(
            slug="swedish_all_generate_pick_claude_haiku", strategy="all_generate_pick",
            model="claude_haiku",
            tv_by_attr={"age_group": 0.2, "biological_sex": 0.2, "education_level": 0.2},
        ),
        make_combo(
            slug="swedish_all_generate_pick_gemini_flash", strategy="all_generate_pick",
            model="gemini_flash",
            tv_by_attr={"age_group": 0.4, "biological_sex": 0.4, "education_level": 0.4},
        ),
    ]


_HOSTING = {"claude_haiku": "hosted", "gemini_flash": "local"}


# ------------------------------------------------------------------
# Rendering harness -- the renderers own their figure and return only a
# path, so the axes has to be captured as it is created.
# ------------------------------------------------------------------

def _render(plot_fn, result, out_path):
    """Call *plot_fn(result, out_path)* and return ``(returned_path, ax)``.

    ``ax`` is ``None`` when the renderer bailed out before drawing.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    captured: dict[str, object] = {}
    orig = plt.subplots

    def spy(*args, **kwargs):
        fig, ax = orig(*args, **kwargs)
        captured["ax"] = ax
        return fig, ax

    plt.subplots = spy
    try:
        out = plot_fn(result, out_path)
    finally:
        plt.subplots = orig
    return out, captured.get("ax")


def _cell_values(ax) -> np.ndarray:
    """The grid the renderer actually handed to ``imshow``, NaN where masked."""
    return np.ma.filled(ax.images[0].get_array().astype(float), np.nan)


def _annotations(ax) -> dict[tuple[int, int], str]:
    """``{(row, col): text}`` for the in-cell annotations (imshow x = col, y = row)."""
    return {
        (int(round(t.get_position()[1])), int(round(t.get_position()[0]))): t.get_text()
        for t in ax.texts
    }


def _bold_cells(ax) -> set[tuple[int, int]]:
    """``{(row, col)}`` of the annotations rendered bold."""
    return {
        (int(round(t.get_position()[1])), int(round(t.get_position()[0])))
        for t in ax.texts if t.get_fontweight() == "bold"
    }


def _boxed_cells(ax) -> set[tuple[int, int]]:
    """``{(row, col)}`` of the cells carrying a best-per-column border rectangle."""
    return {
        (int(round(p.get_y() + 0.5)), int(round(p.get_x() + 0.5)))
        for p in ax.patches
    }


def test_model_table_writes_png_and_svg(tmp_path):
    result = build_performance_comparison(_grid(), ATTRIBUTES, model_hosting=_HOSTING)
    out = plot_model_fidelity_table(result, tmp_path / "swedish_models_table.png")

    assert out is not None
    assert out == tmp_path / "swedish_models_table.png"
    assert out.exists()
    assert out.with_suffix(".svg").exists()


def test_model_table_title_cites_global_best_strategy(tmp_path):
    """The strategy named in the rendered title is the methods-matrix Overall argmax."""
    result = build_performance_comparison(_grid(), ATTRIBUTES, model_hosting=_HOSTING)
    cells = result["methods_matrix"]["cells"]
    expected = max(cells, key=lambda s: cells[s]["overall"])
    assert expected == "all_pick"

    out, ax = _render(plot_model_fidelity_table, result, tmp_path / "t.png")

    assert out is not None
    assert f"strategy '{expected}'" in ax.get_title()


def test_model_table_one_row_per_model_at_best_strategy(tmp_path):
    """Row count == number of distinct models present at the chosen strategy."""
    result = build_performance_comparison(_grid(), ATTRIBUTES, model_hosting=_HOSTING)
    out, ax = _render(plot_model_fidelity_table, result, tmp_path / "m.png")

    assert out is not None
    # 2 models both present at all_pick -> 2 rows; y ticks reflect them, Overall-sorted.
    labels = [t.get_text() for t in ax.get_yticklabels()]
    assert labels == ["claude_haiku", "gemini_flash"]  # haiku 0.9 overall > flash 0.7


def test_model_missing_at_best_strategy_is_omitted(tmp_path, capsys):
    """A model with no combo at the global-best strategy is dropped (and reported)."""
    combos = [
        # all_pick present only for haiku; flash only appears at all_generate_pick.
        make_combo(
            slug="swedish_all_pick_claude_haiku", strategy="all_pick", model="claude_haiku",
            tv_by_attr={a: 0.1 for a in ATTRIBUTES},
        ),
        make_combo(
            slug="swedish_all_generate_pick_claude_haiku", strategy="all_generate_pick",
            model="claude_haiku", tv_by_attr={a: 0.5 for a in ATTRIBUTES},
        ),
        make_combo(
            slug="swedish_all_generate_pick_gemini_flash", strategy="all_generate_pick",
            model="gemini_flash", tv_by_attr={a: 0.6 for a in ATTRIBUTES},
        ),
    ]
    # all_pick overall (0.9) > all_generate_pick overall mean (0.45) -> all_pick global-best.
    result = build_performance_comparison(
        combos, ATTRIBUTES, model_hosting={"claude_haiku": "hosted", "gemini_flash": "local"}
    )
    out, ax = _render(plot_model_fidelity_table, result, tmp_path / "m.png")

    assert out is not None
    labels = [t.get_text() for t in ax.get_yticklabels()]
    assert labels == ["claude_haiku"]  # gemini_flash dropped (no all_pick combo)
    assert "gemini_flash" in capsys.readouterr().out  # reported, not silent


def test_method_table_writes_both_formats_and_is_sorted(tmp_path):
    result = build_performance_comparison(_grid(), ATTRIBUTES, model_hosting=_HOSTING)
    out, ax = _render(plot_method_fidelity_table, result, tmp_path / "swedish_methods_table.png")

    assert out is not None
    assert out.exists()
    assert out.with_suffix(".svg").exists()

    labels = [t.get_text() for t in ax.get_yticklabels()]
    # 2 strategies, Overall-sorted: all_pick (0.8) above all_generate_pick (0.7).
    assert labels == ["all_pick", "all_generate_pick"]


def test_model_table_none_on_empty_attributes(tmp_path):
    result = build_performance_comparison(_grid(), ATTRIBUTES, model_hosting=_HOSTING)
    result["metadata"]["attributes"] = []
    assert plot_model_fidelity_table(result, tmp_path / "x.png") is None


def test_model_table_none_on_missing_methods_matrix(tmp_path):
    result = build_performance_comparison(_grid(), ATTRIBUTES, model_hosting=_HOSTING)
    result.pop("methods_matrix")
    assert plot_model_fidelity_table(result, tmp_path / "x.png") is None


def test_method_table_none_on_all_nan(tmp_path):
    combos = [
        make_combo(
            slug="swedish_all_pick_claude_haiku", strategy="all_pick", model="claude_haiku",
            tv_by_attr={a: float("nan") for a in ATTRIBUTES},
        ),
        make_combo(
            slug="swedish_all_pick_gemini_flash", strategy="all_pick", model="gemini_flash",
            tv_by_attr={a: float("nan") for a in ATTRIBUTES},
        ),
    ]
    result = build_performance_comparison(combos, ATTRIBUTES)
    assert plot_method_fidelity_table(result, tmp_path / "x.png") is None
    assert plot_model_fidelity_table(result, tmp_path / "y.png") is None


def test_model_table_provenance_side_marker_colours_row_labels(tmp_path):
    """Each model row label is coloured by its hosting class (side-marker encoding)."""
    result = build_performance_comparison(_grid(), ATTRIBUTES, model_hosting=_HOSTING)

    import matplotlib.colors as mcolors

    out, ax = _render(plot_model_fidelity_table, result, tmp_path / "m.png")

    assert out is not None
    color_by_model = {
        t.get_text(): mcolors.to_hex(t.get_color()).lower() for t in ax.get_yticklabels()
    }
    # claude_haiku is hosted, gemini_flash is local (per _HOSTING).
    assert color_by_model["claude_haiku"] == HOST_COLORS["hosted"].lower()
    assert color_by_model["gemini_flash"] == HOST_COLORS["local"].lower()


def test_model_table_categories_on_top(tmp_path):
    """Category (column) tick labels are placed above the axes."""
    result = build_performance_comparison(_grid(), ATTRIBUTES, model_hosting=_HOSTING)
    out, ax = _render(plot_model_fidelity_table, result, tmp_path / "m.png")

    assert out is not None
    assert ax.xaxis.get_ticks_position() == "top"


# ------------------------------------------------------------------
# Shared visual grammar -- the grid as actually drawn
#
# These pin what the extraction into ``table_style`` had to preserve: the
# values, the row/column order, the annotation text, the best-cell marking
# and the Overall divider. Structural, not byte-wise.
# ------------------------------------------------------------------

def test_model_table_columns_are_attributes_plus_overall(tmp_path):
    """The models table still labels exactly ``attributes + ["overall"]``, in order.

    ``categories_on_top`` no longer appends the Overall column itself, so this is
    the call site's assertion that the generalised signature did not drop or
    duplicate it.
    """
    result = build_performance_comparison(_grid(), ATTRIBUTES, model_hosting=_HOSTING)
    out, ax = _render(plot_model_fidelity_table, result, tmp_path / "m.png")

    assert out is not None
    assert [t.get_text() for t in ax.get_xticklabels()] == ATTRIBUTES + ["overall"]
    assert list(ax.get_xticks()) == list(range(len(ATTRIBUTES) + 1))


def test_method_table_columns_are_attributes_plus_overall(tmp_path):
    result = build_performance_comparison(_grid(), ATTRIBUTES, model_hosting=_HOSTING)
    out, ax = _render(plot_method_fidelity_table, result, tmp_path / "m.png")

    assert out is not None
    assert [t.get_text() for t in ax.get_xticklabels()] == ATTRIBUTES + ["overall"]
    assert list(ax.get_xticks()) == list(range(len(ATTRIBUTES) + 1))


def test_model_table_grid_values_and_annotations(tmp_path):
    """Cell values, their percentage annotations, and the best-cell marking.

    ``_grid()`` at the global-best strategy ``all_pick``: claude_haiku scores 0.9
    on every axis (and overall), gemini_flash 0.7 -- so every column's best cell
    is row 0, and the annotations are the values rescaled to one-decimal percent.
    """
    result = build_performance_comparison(_grid(), ATTRIBUTES, model_hosting=_HOSTING)
    out, ax = _render(plot_model_fidelity_table, result, tmp_path / "m.png")

    assert out is not None
    n_cols = len(ATTRIBUTES) + 1
    expected = np.array([[0.9] * n_cols, [0.7] * n_cols])
    np.testing.assert_allclose(_cell_values(ax), expected)

    annotations = _annotations(ax)
    assert len(annotations) == expected.size
    assert annotations == {
        (i, j): f"{expected[i, j] * 100:.1f}"
        for i in range(expected.shape[0]) for j in range(n_cols)
    }

    best = {(0, j) for j in range(n_cols)}
    assert _boxed_cells(ax) == best
    assert _bold_cells(ax) == best


def test_method_table_grid_values_and_annotations(tmp_path):
    """Same grid/annotation/best-cell contract for the methods table.

    Cells are the mean over models: all_pick (0.9, 0.7) -> 0.8,
    all_generate_pick (0.8, 0.6) -> 0.7, on every axis and overall.
    """
    result = build_performance_comparison(_grid(), ATTRIBUTES, model_hosting=_HOSTING)
    out, ax = _render(plot_method_fidelity_table, result, tmp_path / "m.png")

    assert out is not None
    n_cols = len(ATTRIBUTES) + 1
    expected = np.array([[0.8] * n_cols, [0.7] * n_cols])
    np.testing.assert_allclose(_cell_values(ax), expected)

    assert _annotations(ax) == {
        (i, j): f"{expected[i, j] * 100:.1f}"
        for i in range(expected.shape[0]) for j in range(n_cols)
    }

    best = {(0, j) for j in range(n_cols)}
    assert _boxed_cells(ax) == best
    assert _bold_cells(ax) == best


def test_tables_draw_the_overall_divider_before_the_last_column(tmp_path):
    """Both tables still separate the Overall column with the white vertical rule."""
    result = build_performance_comparison(_grid(), ATTRIBUTES, model_hosting=_HOSTING)

    import matplotlib.colors as mcolors

    for plot_fn in (plot_model_fidelity_table, plot_method_fidelity_table):
        out, ax = _render(plot_fn, result, tmp_path / f"{plot_fn.__name__}.png")
        assert out is not None
        rules = [
            line for line in ax.lines
            if mcolors.to_hex(line.get_color()) == mcolors.to_hex("white")
        ]
        assert len(rules) == 1, plot_fn.__name__
        assert list(rules[0].get_xdata()) == [len(ATTRIBUTES) - 0.5] * 2


# ------------------------------------------------------------------
# table_style helpers -- the extracted grammar's own contracts
# ------------------------------------------------------------------

def test_categories_on_top_places_exactly_the_given_labels():
    """The generalised signature places the caller's list verbatim -- nothing appended.

    Deliberately a list *without* an "overall" entry: the pre-extraction helper
    hardcoded one, and a consumer that does not want it must not receive it.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = ["all_pick", "all_generate_pick", "all_pick_dag"]
    fig, ax = plt.subplots()
    try:
        categories_on_top(ax, labels)
        assert [t.get_text() for t in ax.get_xticklabels()] == labels
        assert list(ax.get_xticks()) == [0, 1, 2]
        assert ax.xaxis.get_ticks_position() == "top"
    finally:
        plt.close(fig)


def test_best_cells_per_column_ties_go_to_the_first_row():
    values = np.array([[0.5, 0.2], [0.5, 0.9]])
    assert best_cells_per_column(values) == {(0, 0), (1, 1)}


def test_best_cells_per_column_skips_all_nan_columns():
    values = np.array([[np.nan, 0.2], [np.nan, 0.9]])
    assert best_cells_per_column(values) == {(1, 1)}


def test_inferno_cmap_is_the_house_ramp_with_missing_grey():
    """The ramp is the shared house ramp, NaN-grey, and a copy (not the registry's)."""
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    cmap = inferno_cmap()
    assert cmap.name == HEATMAP_CMAP
    assert mcolors.to_hex(cmap.get_bad()).lower() == MISSING_COLOR.lower()
    # A copy: ``set_bad`` mutates, and the registry hands the same object to every
    # caller -- so the registry's own ramp must still carry matplotlib's default
    # (fully transparent) bad colour rather than this module's grey.
    assert plt.get_cmap(HEATMAP_CMAP).get_bad()[3] == 0.0


def test_vertical_divider_draws_a_white_rule_at_the_column_boundary():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    try:
        vertical_divider(ax, 4)
        line = ax.lines[-1]
        assert list(line.get_xdata()) == [3.5, 3.5]
        assert mcolors.to_hex(line.get_color()) == mcolors.to_hex("white")
        assert line.get_linewidth() == 2.5
    finally:
        plt.close(fig)


def test_percentage_colorbar_scales_labels_but_not_the_norm():
    """Ticks read 0--100 while the mappable stays on the underlying 0--1 scale."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    try:
        im = ax.imshow(np.array([[0.0, 0.5], [0.75, 1.0]]), cmap=inferno_cmap())
        cbar = add_percentage_colorbar(fig, im, ax, "TV-similarity (%)")
        formatter = cbar.ax.yaxis.get_major_formatter()
        assert formatter(0.5) == "50"
        assert formatter(1.0) == "100"
        assert (im.norm.vmin, im.norm.vmax) == (0.0, 1.0)
        assert cbar.ax.get_ylabel() == "TV-similarity (%)"
    finally:
        plt.close(fig)


# ------------------------------------------------------------------
# LaTeX snippet emitters
# ------------------------------------------------------------------

def _tabular(content: str) -> str:
    """The ``\\begin{tabular}...\\end{tabular}`` body, excluding the leading comment block."""
    return content.split("\\begin{tabular}", 1)[1].split("\\end{tabular}", 1)[0]


def _row_count(content: str) -> int:
    """Number of body rows (``\\\\``-terminated lines between the mid/bottom rules)."""
    body = _tabular(content).split("\\midrule", 1)[1].split("\\bottomrule", 1)[0]
    return body.count("\\\\")


def test_model_latex_snippet_shape(tmp_path):
    result = build_performance_comparison(_grid(), ATTRIBUTES, model_hosting=_HOSTING)
    out = write_model_fidelity_latex(result, tmp_path / "swedish_models_table.tex")

    assert out is not None
    assert out == tmp_path / "swedish_models_table.tex"
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert content.strip()  # non-empty
    assert "\\toprule" in content and "\\bottomrule" in content
    # Header row = category names (attributes escaped) + Overall.
    header = _tabular(content).split("\\toprule", 1)[1].split("\\midrule", 1)[0]
    for attr in ATTRIBUTES:
        assert attr.replace("_", "\\_") in header
    assert "Overall" in header
    # Values are shown as percentages (0--100, one decimal); the caption notes the unit.
    assert "TV-similarity, %" in content
    assert re.search(r"\\textbf\{\d+\.\d\}", content)  # best-per-column bold, percentage form
    # Best per column (claude_haiku, TV-sim 0.90 -> 90.0%) is bold.
    assert "\\textbf{90.0}" in content
    # One body row per model at the global-best strategy.
    assert _row_count(content) == 2
    # Provenance indicator present (leading Host column, hosted/local text).
    assert "Host" in header
    assert "hosted" in content and "local" in content


def test_method_latex_snippet_shape(tmp_path):
    result = build_performance_comparison(_grid(), ATTRIBUTES, model_hosting=_HOSTING)
    out = write_method_fidelity_latex(result, tmp_path / "swedish_methods_table.tex")

    assert out is not None
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert content.strip()
    assert "\\toprule" in content and "\\bottomrule" in content
    header = _tabular(content).split("\\toprule", 1)[1].split("\\midrule", 1)[0]
    for attr in ATTRIBUTES:
        assert attr.replace("_", "\\_") in header
    assert "Overall" in header
    # Values are shown as percentages (0--100, one decimal); the caption notes the unit.
    assert "TV-similarity, %" in content
    assert re.search(r"\\textbf\{\d+\.\d\}", content)  # best-per-column bold, percentage form
    # all_pick wins every column (mean 0.80 -> 80.0%) -> bold.
    assert "\\textbf{80.0}" in content
    # One body row per strategy.
    assert _row_count(content) == 2


def test_latex_emitters_none_on_all_nan(tmp_path):
    combos = [
        make_combo(
            slug="swedish_all_pick_claude_haiku", strategy="all_pick", model="claude_haiku",
            tv_by_attr={a: float("nan") for a in ATTRIBUTES},
        ),
        make_combo(
            slug="swedish_all_pick_gemini_flash", strategy="all_pick", model="gemini_flash",
            tv_by_attr={a: float("nan") for a in ATTRIBUTES},
        ),
    ]
    result = build_performance_comparison(combos, ATTRIBUTES)
    assert write_model_fidelity_latex(result, tmp_path / "x.tex") is None
    assert write_method_fidelity_latex(result, tmp_path / "y.tex") is None


def test_latex_emitters_none_on_empty_attributes(tmp_path):
    result = build_performance_comparison(_grid(), ATTRIBUTES, model_hosting=_HOSTING)
    result["metadata"]["attributes"] = []
    assert write_model_fidelity_latex(result, tmp_path / "x.tex") is None
    assert write_method_fidelity_latex(result, tmp_path / "y.tex") is None
