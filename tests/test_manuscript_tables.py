"""Tests for the manuscript fidelity heatmap-tables (models + methods renderers).

Pure-consumer renderers over a built ``result`` dict: exercise the PNG+SVG dual
output, the global-best-strategy selection cited in the models-table title, the
Overall-sort of both tables, the drop-and-report of a model missing at the
global-best strategy, the provenance side-marker (row-label colour), the LaTeX
snippet emitters, and the empty / all-NaN ``None`` contract. Figures / snippets
are written to a pytest ``tmp_path``, never the repo.
"""

from __future__ import annotations

import re

from population_synthetic.analysis.model_ranking.builder import build_performance_comparison
from population_synthetic.analysis.model_ranking.manuscript_tables import (
    _HOST_COLORS,
    plot_method_fidelity_table,
    plot_model_fidelity_table,
    write_method_fidelity_latex,
    write_model_fidelity_latex,
)
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

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    captured = {}
    orig = plt.subplots

    def spy(*args, **kwargs):
        fig, ax = orig(*args, **kwargs)
        captured["ax"] = ax
        return fig, ax

    plt.subplots = spy
    try:
        out = plot_model_fidelity_table(result, tmp_path / "t.png")
    finally:
        plt.subplots = orig

    assert out is not None
    title = captured["ax"].get_title()
    assert f"strategy '{expected}'" in title


def test_model_table_one_row_per_model_at_best_strategy(tmp_path):
    """Row count == number of distinct models present at the chosen strategy."""
    result = build_performance_comparison(_grid(), ATTRIBUTES, model_hosting=_HOSTING)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    captured = {}
    orig = plt.subplots

    def spy(*args, **kwargs):
        fig, ax = orig(*args, **kwargs)
        captured["ax"] = ax
        return fig, ax

    plt.subplots = spy
    try:
        out = plot_model_fidelity_table(result, tmp_path / "m.png")
    finally:
        plt.subplots = orig

    assert out is not None
    # 2 models both present at all_pick -> 2 rows; y ticks reflect them, Overall-sorted.
    ax = captured["ax"]
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

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    captured = {}
    orig = plt.subplots

    def spy(*args, **kwargs):
        fig, ax = orig(*args, **kwargs)
        captured["ax"] = ax
        return fig, ax

    plt.subplots = spy
    try:
        out = plot_model_fidelity_table(result, tmp_path / "m.png")
    finally:
        plt.subplots = orig

    assert out is not None
    labels = [t.get_text() for t in captured["ax"].get_yticklabels()]
    assert labels == ["claude_haiku"]  # gemini_flash dropped (no all_pick combo)
    assert "gemini_flash" in capsys.readouterr().out  # reported, not silent


def test_method_table_writes_both_formats_and_is_sorted(tmp_path):
    result = build_performance_comparison(_grid(), ATTRIBUTES, model_hosting=_HOSTING)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    captured = {}
    orig = plt.subplots

    def spy(*args, **kwargs):
        fig, ax = orig(*args, **kwargs)
        captured["ax"] = ax
        return fig, ax

    plt.subplots = spy
    try:
        out = plot_method_fidelity_table(result, tmp_path / "swedish_methods_table.png")
    finally:
        plt.subplots = orig

    assert out is not None
    assert out.exists()
    assert out.with_suffix(".svg").exists()

    labels = [t.get_text() for t in captured["ax"].get_yticklabels()]
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

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    captured = {}
    orig = plt.subplots

    def spy(*args, **kwargs):
        fig, ax = orig(*args, **kwargs)
        captured["ax"] = ax
        return fig, ax

    plt.subplots = spy
    try:
        out = plot_model_fidelity_table(result, tmp_path / "m.png")
    finally:
        plt.subplots = orig

    assert out is not None
    ax = captured["ax"]
    color_by_model = {
        t.get_text(): mcolors.to_hex(t.get_color()).lower() for t in ax.get_yticklabels()
    }
    # claude_haiku is hosted, gemini_flash is local (per _HOSTING).
    assert color_by_model["claude_haiku"] == _HOST_COLORS["hosted"].lower()
    assert color_by_model["gemini_flash"] == _HOST_COLORS["local"].lower()


def test_model_table_categories_on_top(tmp_path):
    """Category (column) tick labels are placed above the axes."""
    result = build_performance_comparison(_grid(), ATTRIBUTES, model_hosting=_HOSTING)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    captured = {}
    orig = plt.subplots

    def spy(*args, **kwargs):
        fig, ax = orig(*args, **kwargs)
        captured["ax"] = ax
        return fig, ax

    plt.subplots = spy
    try:
        out = plot_model_fidelity_table(result, tmp_path / "m.png")
    finally:
        plt.subplots = orig

    assert out is not None
    assert captured["ax"].xaxis.get_ticks_position() == "top"


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
