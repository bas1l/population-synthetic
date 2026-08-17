"""Tests for the model x method TV-similarity heatmap.

A pure consumer of the built ``result`` dict plus the gate's per-slug requested cap,
so every fixture here is an in-memory grid: the assertions are structural properties
of the artists the renderer actually drew (the imshow arrays, the tick labels and
their colours, the in-cell annotations, the hatched patches, the tier-break rule and
the two marginals), never byte comparisons of the PNG, whose bytes move with
matplotlib metadata and font hinting without anything about the figure having changed.

The fixture cap is **40**, not the production 100: a threshold hardcoded anywhere in
the tiering rule would otherwise pass by coincidence. Nothing below states a persona
count as a bare literal without deriving it from ``REQUESTED_N``. (The ``x 100`` in
the value assertions is the metric's percentage rescaling, an unrelated quantity.)

The last two tests drive the real CLI edge (``scripts/analyze/rank_models.py``) via
subprocess against a ``tmp_path`` workspace, to pin that the pair is emitted alongside
the pre-existing artifacts and suppressed by ``--no-charts``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.model_ranking.builder import build_performance_comparison
from population_synthetic.analysis.model_ranking.charts import plot_model_method_heatmap
from population_synthetic.analysis.model_ranking.loader import scheme_attributes
from population_synthetic.analysis.model_ranking.table_style import BOX_EDGE, HOST_COLORS
from population_synthetic.analysis.utils.axes import strategy_complexity_order
from population_synthetic.analysis.utils.cap_index import INDEX_FILENAME, CapIndex
from population_synthetic.analysis.utils.registry import analysis_output_dir
from tests._performance_fixtures import ATTRIBUTES, build_workspace, make_combo, make_report

# The cap every fixture combination was drawn against. Deliberately not 100.
REQUESTED_N = 40

COUNTRY = "swedish"

# Two real strategy ids in the config-derived complexity order the columns must follow.
STRATEGIES = strategy_complexity_order(["all_pick", "all_generate_pick"])
S1, S2 = STRATEGIES

_FIXTURE_INDEX = Path("fixture") / INDEX_FILENAME


def _slug(model: str, strategy: str) -> str:
    return f"{COUNTRY}_{strategy}_{model}"


def _result(cells, *, hosting=None) -> dict:
    """Build the performance result for *cells* = ``[(model, strategy, similarity, n)]``.

    Every attribute of a combination carries the same TV-distance, so the combination's
    overall ``tv_similarity_mean`` is exactly the requested *similarity* -- which is what
    lets the cell assertions state an expected number rather than re-deriving a mean.
    """
    records = [
        make_combo(
            slug=_slug(model, strategy), strategy=strategy, model=model,
            tv_by_attr={attr: 1.0 - similarity for attr in ATTRIBUTES}, n_synth=n,
        )
        for model, strategy, similarity, n in cells
    ]
    return build_performance_comparison(records, ATTRIBUTES, model_hosting=hosting or {})


def _cap(cells, requested: int = REQUESTED_N) -> CapIndex:
    return CapIndex(
        {_slug(model, strategy): requested for model, strategy, _s, _n in cells},
        source=_FIXTURE_INDEX,
    )


def _render(cells, tmp_path, *, hosting=None, requested: int = REQUESTED_N):
    """Draw *cells* and return ``(returned_path, ax)``.

    The renderer owns and closes its figure and returns only a path, so the axes has
    to be captured as it is created.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    result = _result(cells, hosting=hosting)
    captured: dict[str, object] = {}
    orig = plt.subplots

    def spy(*args, **kwargs):
        fig, ax = orig(*args, **kwargs)
        captured["ax"] = ax
        return fig, ax

    plt.subplots = spy
    try:
        out = plot_model_method_heatmap(
            result, _cap(cells, requested), tmp_path / f"{COUNTRY}_model_method_heatmap.png"
        )
    finally:
        plt.subplots = orig
    return out, captured.get("ax")


# ------------------------------------------------------------------
# Artist readers
# ------------------------------------------------------------------

def _grid(ax) -> np.ndarray:
    """The values actually handed to ``imshow``, tier blocks stacked in draw order."""
    return np.vstack(
        [np.ma.filled(im.get_array().astype(float), np.nan) for im in ax.images]
    )


def _row_models(ax) -> list[str]:
    return [t.get_text() for t in ax.get_yticklabels()]


def _row_y(ax) -> list[float]:
    return [round(float(y), 3) for y in ax.get_yticks()]


def _cell_texts(ax) -> dict[tuple[float, int], str]:
    """``{(row y, column): text}`` for the in-cell annotations.

    Cells sit at integer coordinates in both axes; every other text artist the
    renderer places (marginals, the tier note, the caption) is off-lattice by
    construction, which is what makes this filter exact.
    """
    out: dict[tuple[float, int], str] = {}
    for text in ax.texts:
        x, y = text.get_position()
        if float(x).is_integer() and float(y).is_integer():
            out[(round(float(y), 3), int(x))] = text.get_text()
    return out


def _cell_text(ax, model: str, strategy: str) -> str:
    return _cell_texts(ax)[(_row_y(ax)[_row_models(ax).index(model)], STRATEGIES.index(strategy))]


def _row_marginals(ax) -> dict[str, str]:
    """``{model: text}`` for the per-model marginal drawn right of the grid."""
    ys = _row_y(ax)
    models = _row_models(ax)
    out: dict[str, str] = {}
    for text in ax.texts:
        x, y = text.get_position()
        if float(x).is_integer():
            continue
        key = round(float(y), 3)
        if key in ys:
            out[models[ys.index(key)]] = text.get_text()
    return out


def _column_marginals(ax) -> dict[str, str]:
    """``{strategy: text}`` for the per-method marginal drawn below the grid."""
    target = round(_row_y(ax)[-1] + 1.5, 3)
    out: dict[str, str] = {}
    for text in ax.texts:
        x, y = text.get_position()
        if float(x).is_integer() and round(float(y), 3) == target:
            out[STRATEGIES[int(x)]] = text.get_text()
    return out


def _hatched(ax) -> set[tuple[str, str]]:
    """``{(model, strategy)}`` of the cells marked as thin."""
    ys = _row_y(ax)
    models = _row_models(ax)
    out: set[tuple[str, str]] = set()
    for patch in ax.patches:
        if not patch.get_hatch():
            continue
        x0, y0 = patch.get_xy()
        out.add((models[ys.index(round(float(y0) + 0.5, 3))], STRATEGIES[int(round(x0 + 0.5))]))
    return out


def _break_lines(ax) -> list:
    return [line for line in ax.lines if line.get_color() == BOX_EDGE]


def _divider_lines(ax) -> list:
    return [line for line in ax.lines if line.get_color() == "white"]


def _all_text(ax) -> str:
    return "\n".join(t.get_text() for t in ax.texts)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

def _full_grid():
    """3 models x 2 methods, every cell exactly at the requested cap."""
    return [
        ("model_a", S1, 0.90, REQUESTED_N), ("model_a", S2, 0.80, REQUESTED_N),
        ("model_b", S1, 0.70, REQUESTED_N), ("model_b", S2, 0.60, REQUESTED_N),
        ("model_c", S1, 0.50, REQUESTED_N), ("model_c", S2, 0.40, REQUESTED_N),
    ]


def _mixed_grid():
    """One fully-sampled model, one with a single full-n cell, one with none.

    ``model_b``'s *best* cell is thin, so its rank must come from its weaker full-n
    cell; ``model_c`` has no full-n cell at all and belongs to Tier 2.
    """
    return [
        ("model_a", S1, 0.90, REQUESTED_N), ("model_a", S2, 0.80, REQUESTED_N),
        ("model_b", S1, 0.60, REQUESTED_N), ("model_b", S2, 0.95, REQUESTED_N - 1),
        ("model_c", S1, 0.99, REQUESTED_N - 1), ("model_c", S2, 0.85, 5),
    ]


# ------------------------------------------------------------------
# Values, order, and the two agreeing sources of the column order
# ------------------------------------------------------------------

def test_cell_values_are_the_overall_tv_similarity(tmp_path):
    cells = _full_grid()
    _out, ax = _render(cells, tmp_path)

    models = _row_models(ax)
    expected = np.array([
        [next(s for m, st, s, _n in cells if m == model and st == strategy)
         for strategy in STRATEGIES]
        for model in models
    ])
    assert np.allclose(_grid(ax), expected)


def test_cell_annotations_print_the_rescaled_value_and_n(tmp_path):
    cells = _mixed_grid()
    _out, ax = _render(cells, tmp_path)

    for model, strategy, similarity, n in cells:
        assert _cell_text(ax, model, strategy) == f"{similarity * 100:.1f}\nn={n}"


def test_column_order_is_the_config_order_and_agrees_with_methods_matrix(tmp_path):
    cells = _full_grid()
    result = _result(cells)
    _out, ax = _render(cells, tmp_path)

    expected = strategy_complexity_order(result["metadata"]["strategies"])
    assert [t.get_text() for t in ax.get_xticklabels()] == expected
    # Pinned, not depended on: the chart derives the order itself, and this asserts the
    # unrelated aggregation still agrees.
    assert result["methods_matrix"]["strategies"] == expected


# ------------------------------------------------------------------
# The tier partition
# ------------------------------------------------------------------

def test_tier_assignment_splits_on_having_any_full_n_cell(tmp_path):
    _out, ax = _render(_mixed_grid(), tmp_path)

    models = _row_models(ax)
    assert models[-1] == "model_c"  # no full-n cell -> Tier 2, drawn last
    assert set(models[:-1]) == {"model_a", "model_b"}


def test_tier1_ordering_key_ignores_thin_cells(tmp_path):
    """``model_b``'s best cell (0.95) is thin, so it ranks on its 0.60 full-n cell."""
    _out, ax = _render(_mixed_grid(), tmp_path)

    assert _row_models(ax) == ["model_a", "model_b", "model_c"]
    assert _row_marginals(ax)["model_b"].startswith("60.0")
    # The thin cell is still drawn and still marked.
    assert ("model_b", S2) in _hatched(ax)
    assert _cell_text(ax, "model_b", S2) == f"95.0\nn={REQUESTED_N - 1}"


def test_single_full_n_cell_is_ranked_on_that_one_cell(tmp_path):
    _out, ax = _render(_mixed_grid(), tmp_path)

    assert _row_marginals(ax)["model_b"] == f"60.0  {S1}  (1 full-n)"


def test_tier1_rows_precede_tier2_rows_regardless_of_values(tmp_path):
    """The Tier 2 model holds the highest value in the grid and still sorts last."""
    cells = [
        ("model_a", S1, 0.10, REQUESTED_N), ("model_a", S2, 0.20, REQUESTED_N),
        ("model_z", S1, 0.99, REQUESTED_N - 1), ("model_z", S2, 0.98, 3),
    ]
    _out, ax = _render(cells, tmp_path)

    assert _row_models(ax) == ["model_a", "model_z"]


def test_tier2_block_is_annotated_with_the_reason(tmp_path):
    _out, ax = _render(_mixed_grid(), tmp_path)

    text = _all_text(ax)
    assert "unranked" in text
    assert "below the requested cap" in text
    assert len(_break_lines(ax)) == 1  # the dark rule inside the gap


def test_tier2_row_labels_are_styled_distinctly(tmp_path):
    _out, ax = _render(_mixed_grid(), tmp_path)

    styles = {t.get_text(): t.get_fontstyle() for t in ax.get_yticklabels()}
    assert styles["model_c"] == "italic"
    assert styles["model_a"] == "normal"
    assert styles["model_b"] == "normal"


def test_no_tier2_draws_no_break_and_no_unranked_annotation(tmp_path):
    _out, ax = _render(_full_grid(), tmp_path)

    assert _break_lines(ax) == []
    assert "unranked" not in _all_text(ax)
    assert "Tier 2" not in _all_text(ax)


def test_all_tier2_grid_renders_fully_marked_and_provisional(tmp_path):
    cells = [
        ("model_a", S1, 0.50, REQUESTED_N - 1), ("model_a", S2, 0.40, 5),
        ("model_b", S1, 0.30, 7), ("model_b", S2, 0.20, 9),
    ]
    out, ax = _render(cells, tmp_path)

    assert out is not None
    assert len(ax.images) == 1  # no empty Tier 1 block drawn
    assert _hatched(ax) == {(m, s) for m, s, _v, _n in cells}
    assert _break_lines(ax) == []  # nothing to separate
    assert "unranked" in _all_text(ax)
    assert all("provisional" in text for text in _row_marginals(ax).values())


# ------------------------------------------------------------------
# Ordering keys: totality and stability
# ------------------------------------------------------------------

def test_tier1_tie_on_max_breaks_on_mean_before_model_id(tmp_path):
    cells = [
        ("model_a", S1, 0.90, REQUESTED_N), ("model_a", S2, 0.30, REQUESTED_N),
        ("model_b", S1, 0.90, REQUESTED_N), ("model_b", S2, 0.50, REQUESTED_N),
    ]
    _out, ax = _render(cells, tmp_path)

    # Equal maxima; model_b's mean is higher, which outranks the alphabetical id.
    assert _row_models(ax) == ["model_b", "model_a"]


def test_tier1_tie_on_max_and_mean_breaks_on_model_id(tmp_path):
    cells = [
        ("model_z", S1, 0.90, REQUESTED_N), ("model_z", S2, 0.50, REQUESTED_N),
        ("model_a", S1, 0.90, REQUESTED_N), ("model_a", S2, 0.50, REQUESTED_N),
    ]
    _out, ax = _render(cells, tmp_path)

    assert _row_models(ax) == ["model_a", "model_z"]


def test_tier2_tie_on_max_breaks_on_model_id_only(tmp_path):
    """Tier 2's key is ``(-max, model_id)`` -- the mean is deliberately not in it."""
    cells = [
        ("model_z", S1, 0.90, 5), ("model_z", S2, 0.10, 5),
        ("model_a", S1, 0.90, 5), ("model_a", S2, 0.50, 5),
    ]
    _out, ax = _render(cells, tmp_path)

    assert _row_models(ax) == ["model_a", "model_z"]


def test_row_order_is_stable_across_repeated_calls(tmp_path):
    cells = _mixed_grid()
    orders = []
    for i in range(3):
        run_dir = tmp_path / f"run_{i}"
        run_dir.mkdir()
        _out, ax = _render(cells, run_dir)
        orders.append(_row_models(ax))

    assert orders[0] == orders[1] == orders[2]


def test_a_row_with_no_scored_full_n_cell_sorts_last_in_its_tier(tmp_path):
    """NaN full-n values leave the row keyless; it stays in Tier 1 and sorts last."""
    cells = [
        ("model_z", S1, 0.90, REQUESTED_N), ("model_z", S2, 0.80, REQUESTED_N),
        ("model_a", S1, float("nan"), REQUESTED_N), ("model_a", S2, 0.99, 5),
    ]
    _out, ax = _render(cells, tmp_path)

    assert _row_models(ax) == ["model_z", "model_a"]
    assert _row_marginals(ax)["model_a"] == "n/a  (no scored cell)"
    assert _break_lines(ax) == []  # model_a has a full-n cell -> still Tier 1


def test_a_model_with_no_finite_cell_sorts_last_in_whichever_tier_it_lands(tmp_path):
    """The keyless rule is the same in both tiers, and never compares against NaN."""
    nan = float("nan")
    cells = [
        ("model_a", S1, 0.90, REQUESTED_N), ("model_a", S2, 0.80, REQUESTED_N),
        ("model_b", S1, nan, REQUESTED_N), ("model_b", S2, nan, REQUESTED_N),
        ("model_c", S1, 0.50, 5), ("model_c", S2, 0.40, 5),
        ("model_d", S1, nan, 5), ("model_d", S2, nan, 5),
    ]
    _out, ax = _render(cells, tmp_path)

    assert _row_models(ax) == ["model_a", "model_b", "model_c", "model_d"]
    marginals = _row_marginals(ax)
    assert marginals["model_b"] == "n/a  (no scored cell)"
    assert marginals["model_d"] == "n/a  (no scored cell)"


# ------------------------------------------------------------------
# Marginals
# ------------------------------------------------------------------

def test_row_marginal_prints_the_ordering_key_not_a_mean(tmp_path):
    _out, ax = _render(_full_grid(), tmp_path)

    marginals = _row_marginals(ax)
    assert marginals["model_a"] == f"90.0  {S1}  (2 full-n)"
    assert marginals["model_b"] == f"70.0  {S1}  (2 full-n)"


def test_row_marginal_argmax_tie_resolves_to_the_simpler_method(tmp_path):
    cells = [
        ("model_a", S1, 0.70, REQUESTED_N), ("model_a", S2, 0.70, REQUESTED_N),
        ("model_b", S1, 0.50, REQUESTED_N), ("model_b", S2, 0.50, REQUESTED_N),
    ]
    _out, ax = _render(cells, tmp_path)

    assert _row_marginals(ax)["model_a"] == f"70.0  {STRATEGIES[0]}  (2 full-n)"


def test_tier2_row_marginal_is_flagged_provisional(tmp_path):
    _out, ax = _render(_mixed_grid(), tmp_path)

    assert _row_marginals(ax)["model_c"] == f"99.0  {S1}  (2 cells, provisional)"


def test_column_marginal_averages_full_n_cells_only_and_prints_the_count(tmp_path):
    _out, ax = _render(_mixed_grid(), tmp_path)

    marginals = _column_marginals(ax)
    # S1: model_a 0.90 + model_b 0.60 (model_c's cell is thin) -> 0.75 over 2 cells.
    assert marginals[S1] == "75.0\n(2 full-n)"
    # S2: only model_a's cell is full-n -> the mean is that cell, over 1.
    assert marginals[S2] == "80.0\n(1 full-n)"


def test_column_with_no_full_n_cell_reports_no_mean(tmp_path):
    cells = [
        ("model_a", S1, 0.90, REQUESTED_N), ("model_a", S2, 0.80, REQUESTED_N - 1),
        ("model_b", S1, 0.70, REQUESTED_N), ("model_b", S2, 0.60, 5),
    ]
    _out, ax = _render(cells, tmp_path)

    assert _column_marginals(ax)[S2] == "n/a\n(0 full-n)"


def test_marginals_are_fenced_off_by_the_shared_dividers(tmp_path):
    _out, ax = _render(_full_grid(), tmp_path)

    # One vertical (grid | row marginal) and one horizontal (grid | column marginal).
    assert len(_divider_lines(ax)) == 2


def test_caption_states_both_marginal_scopes(tmp_path):
    _out, ax = _render(_mixed_grid(), tmp_path)

    text = _all_text(ax)
    assert "Row marginal" in text and "Column marginal" in text
    assert "full-n cells only" in text


# ------------------------------------------------------------------
# Thin marking
# ------------------------------------------------------------------

def test_marking_fires_exactly_on_the_cells_below_the_cap(tmp_path):
    _out, ax = _render(_mixed_grid(), tmp_path)

    assert _hatched(ax) == {("model_b", S2), ("model_c", S1), ("model_c", S2)}


def test_boundary_cell_at_exactly_the_requested_cap_is_unmarked(tmp_path):
    cells = [
        ("model_a", S1, 0.90, REQUESTED_N), ("model_a", S2, 0.80, REQUESTED_N - 1),
        ("model_b", S1, 0.70, REQUESTED_N + 1), ("model_b", S2, 0.60, REQUESTED_N),
    ]
    _out, ax = _render(cells, tmp_path)

    assert _hatched(ax) == {("model_a", S2)}


def test_marking_follows_the_slugs_own_cap_not_a_literal(tmp_path):
    """The same persona counts flip from full-n to thin when the cap changes."""
    cells = [
        ("model_a", S1, 0.90, REQUESTED_N), ("model_a", S2, 0.80, REQUESTED_N),
        ("model_b", S1, 0.70, REQUESTED_N), ("model_b", S2, 0.60, REQUESTED_N),
    ]
    _out, ax = _render(cells, tmp_path, requested=REQUESTED_N)
    assert _hatched(ax) == set()

    _out, ax = _render(cells, tmp_path, requested=REQUESTED_N + 1)
    assert _hatched(ax) == {(m, s) for m, s, _v, _n in cells}


def test_thin_marking_has_a_legend_entry(tmp_path):
    _out, ax = _render(_mixed_grid(), tmp_path)

    labels = [t.get_text() for t in ax.get_legend().get_texts()]
    assert any("requested cap" in label for label in labels)


def test_a_slug_missing_from_the_cap_index_raises(tmp_path):
    cells = _full_grid()
    result = _result(cells)
    partial = CapIndex(
        {_slug("model_a", S1): REQUESTED_N}, source=_FIXTURE_INDEX
    )

    with pytest.raises(KeyError):
        plot_model_method_heatmap(result, partial, tmp_path / "out.png")


# ------------------------------------------------------------------
# Provenance colouring
# ------------------------------------------------------------------

def test_model_label_colours_follow_the_hosting_map(tmp_path):
    hosting = {"model_a": "hosted", "model_b": "local"}
    _out, ax = _render(_full_grid(), tmp_path, hosting=hosting)

    colors = {t.get_text(): t.get_color() for t in ax.get_yticklabels()}
    assert colors["model_a"] == HOST_COLORS["hosted"]
    assert colors["model_b"] == HOST_COLORS["local"]
    # model_c is absent from the map -> the family's presentation default.
    assert colors["model_c"] == HOST_COLORS["hosted"]


# ------------------------------------------------------------------
# Degenerate grids
# ------------------------------------------------------------------

def test_missing_combination_renders_as_a_masked_cell_never_zero(tmp_path):
    cells = [
        ("model_a", S1, 0.90, REQUESTED_N), ("model_a", S2, 0.80, REQUESTED_N),
        ("model_b", S1, 0.70, REQUESTED_N),  # no (model_b, S2) combination in the run
    ]
    _out, ax = _render(cells, tmp_path)

    grid = _grid(ax)
    row = _row_models(ax).index("model_b")
    assert np.isnan(grid[row, STRATEGIES.index(S2)])
    assert ("model_b", S2) not in _hatched(ax)
    assert (_row_y(ax)[row], STRATEGIES.index(S2)) not in _cell_texts(ax)


def test_all_nan_column_does_not_crash_the_marginals(tmp_path):
    nan = float("nan")
    cells = [
        ("model_a", S1, 0.90, REQUESTED_N), ("model_a", S2, nan, REQUESTED_N),
        ("model_b", S1, 0.70, REQUESTED_N), ("model_b", S2, nan, REQUESTED_N),
    ]
    _out, ax = _render(cells, tmp_path)

    assert _column_marginals(ax)[S2] == "n/a\n(0 full-n)"
    assert _cell_text(ax, "model_a", S2) == f"--\nn={REQUESTED_N}"


def test_single_method_grid_renders(tmp_path):
    cells = [("model_a", S1, 0.90, REQUESTED_N), ("model_b", S1, 0.70, REQUESTED_N)]
    out, ax = _render(cells, tmp_path)

    assert out is not None
    assert _grid(ax).shape == (2, 1)


def test_single_model_grid_renders(tmp_path):
    cells = [("model_a", S1, 0.90, REQUESTED_N), ("model_a", S2, 0.70, REQUESTED_N)]
    out, ax = _render(cells, tmp_path)

    assert out is not None
    assert _grid(ax).shape == (1, 2)


# ------------------------------------------------------------------
# Persistence and naming
# ------------------------------------------------------------------

def test_writes_the_png_and_its_svg_sibling(tmp_path):
    out, _ax = _render(_mixed_grid(), tmp_path)

    assert out == tmp_path / f"{COUNTRY}_model_method_heatmap.png"
    assert out.is_file()
    assert out.with_suffix(".svg").is_file()


def test_title_distinguishes_the_figure_from_its_two_siblings(tmp_path):
    _out, ax = _render(_full_grid(), tmp_path)

    title = ax.get_title()
    assert COUNTRY in title
    assert "model x method" in title
    assert "\n" in title  # headline plus the distinguishing subtitle


# ------------------------------------------------------------------
# CLI integration
# ------------------------------------------------------------------

SCRIPT = PROJECT_ROOT / "scripts" / "analyze" / "rank_models.py"

# Two real model ids and two real strategy ids, so the script's slug decomposition
# against the live axis registries succeeds.
_CLI_MODELS = ("claude_haiku", "gemini_flash")
_CLI_STRATEGIES = ("all_pick", "all_generate_pick")


def _build_cli_workspace(tmp_path: Path) -> Path:
    """A workspace the real script can rank: fidelity reports + both cap indexes."""
    attributes = scheme_attributes(COUNTRY)
    entries = []
    slugs = []
    for m_idx, model in enumerate(_CLI_MODELS):
        for s_idx, strategy in enumerate(_CLI_STRATEGIES):
            slug = f"{COUNTRY}_{strategy}_{model}"
            slugs.append(slug)
            tv = 0.1 + 0.05 * m_idx + 0.02 * s_idx
            entries.append({
                "slug": slug,
                "country": COUNTRY,
                "report": make_report({attr: tv for attr in attributes}, n_synth=REQUESTED_N),
            })
    build_workspace(tmp_path, entries)

    index_path = analysis_output_dir("population_cap", tmp_path) / INDEX_FILENAME
    index_path.write_text(
        json.dumps([
            {"slug": slug, "country": COUNTRY, "requested_n": REQUESTED_N} for slug in slugs
        ]),
        encoding="utf-8",
    )
    return tmp_path


def _run_cli(output_base: Path, *extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--output-base", str(output_base),
            "--country", COUNTRY,
            *extra_args,
        ],
        capture_output=True, text=True,
    )


def test_cli_emits_the_new_pair_alongside_the_existing_artifacts(tmp_path):
    _build_cli_workspace(tmp_path)

    proc = _run_cli(tmp_path)
    assert proc.returncode == 0, proc.stderr

    out_dir = analysis_output_dir("model_ranking", tmp_path)
    written = {p.name for p in out_dir.iterdir()}
    assert f"{COUNTRY}_model_method_heatmap.png" in written
    assert f"{COUNTRY}_model_method_heatmap.svg" in written
    # The pre-existing artifacts are untouched by the addition.
    for name in (
        f"{COUNTRY}_performance.json", f"{COUNTRY}_performance.csv",
        f"{COUNTRY}_heatmap.png", f"{COUNTRY}_leaderboard.png",
        f"{COUNTRY}_models_table.png", f"{COUNTRY}_methods_table.png",
        f"{COUNTRY}_models_table.tex", f"{COUNTRY}_methods_table.tex",
    ):
        assert name in written


def test_cli_no_charts_suppresses_the_pair_but_still_writes_json_and_csv(tmp_path):
    _build_cli_workspace(tmp_path)

    proc = _run_cli(tmp_path, "--no-charts")
    assert proc.returncode == 0, proc.stderr

    out_dir = analysis_output_dir("model_ranking", tmp_path)
    written = {p.name for p in out_dir.iterdir()}
    assert written == {f"{COUNTRY}_performance.json", f"{COUNTRY}_performance.csv"}
