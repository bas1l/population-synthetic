"""Tests for ``realism_ranking.charts.plot_typicality_distribution_grid``.

The figure is the approved P20 layout of the typicality-distribution-grid plan, so the
geometry is asserted in points against that layout's constants (12 models x 5
strategies: cells 26.5 pt square, column gap 1.5, row gap 3.0, grid left edge 20, a
456 x 280.5 pt canvas), not against a rendering. The cell states, the column order, the
failure modes and the written SVG's width are asserted beside it.
"""

from __future__ import annotations

import math
import re

import matplotlib

matplotlib.use("Agg")

import matplotlib.colors as mcolors  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
from matplotlib.legend import Legend  # noqa: E402

from population_synthetic.analysis.realism_ranking import charts  # noqa: E402
from population_synthetic.analysis.realism_ranking.charts import (  # noqa: E402
    plot_typicality_distribution_grid,
)
from population_synthetic.analysis.utils.axes import strategy_complexity_order  # noqa: E402
from population_synthetic.analysis.utils.figures import save_figure  # noqa: E402
from population_synthetic.analysis.utils.labels import figure_term, model_labels  # noqa: E402
from population_synthetic.analysis.utils.palette import HOST_COLORS, MISSING_COLOR  # noqa: E402
from population_synthetic.analysis.utils.style import POINTS_PER_INCH  # noqa: E402

#: The live swedish_02 grid: twelve models in the published model_ranking order.
MODELS = [
    "openrouter_kimi_k3", "claude_haiku", "claude_sonnet", "openrouter_opus_5",
    "openrouter_gpt56_sol", "openrouter_glm_52", "openrouter_qwen35_flash",
    "openrouter_gpt_oss_120b", "openrouter_mistral_medium", "ollama_mistral_nemo_12b",
    "ollama_deepseek_r1_14b", "ollama_gemma4_e4b",
]
HOSTING = {m: ("local" if m.startswith("ollama_") else "hosted") for m in MODELS}
STRATEGIES = strategy_complexity_order([
    "all_pick_v2", "all_pick_dag_v2", "all_generate_pick_v2",
    "all_generate_evaluate_pick_v2", "all_generate_evaluate_random_pick_v2",
])
COUNTRY = "swedish_02"

# The P20 geometry, restated here as the test's expectation (not imported from the module).
CELL, COLUMN_GAP, ROW_GAP, GRID_LEFT = 26.5, 1.5, 3.0, 20.0
WIDTH, HEIGHT, GRID_BOTTOM = 456.0, 280.5, 60.0


def _distribution(peak: int) -> list[float]:
    mass = [0.02] * 11
    mass[peak] += 1.0 - sum(mass)
    return mass


def _bands(distribution: list[float]) -> list[float]:
    return [sum(distribution[:5]), sum(distribution[5:8]), sum(distribution[8:])]


def _ok(slug: str, peak: int) -> dict:
    distribution = _distribution(peak)
    return {"slug": slug, "status": "ok", "distribution": distribution, "band_shares": _bands(distribution)}


def _ranking(models=MODELS, *, states=None, real=True) -> dict:
    """A ranking carrying only the typicality_distribution block the chart reads.

    *states* overrides ``{(model, strategy): state}``; every other cell is ``ok``.
    """
    states = states or {}
    cells: dict = {}
    state_grid: dict = {}
    for j, model in enumerate(sorted(models)):
        cells[model], state_grid[model] = {}, {}
        for i, strategy in enumerate(STRATEGIES):
            slug = f"{COUNTRY}_{strategy}_{model}"
            state = states.get((model, strategy), "ok")
            state_grid[model][strategy] = state
            if state == "ok":
                cells[model][strategy] = _ok(slug, 5 + (i + j) % 6)
            elif state == "no_typicality":
                cells[model][strategy] = {"slug": slug, "status": "no_typicality", "distribution": None,
                                          "band_shares": None}
            else:
                cells[model][strategy] = None
    return {
        "country": COUNTRY,
        "typicality_distribution": {
            "n_levels": 11,
            "bands": {"edges": [4, 7], "labels": ["0–4", "5–7", "8–10"]},
            "grid": {
                "models": sorted(models), "methods": list(STRATEGIES), "cells": cells,
                "states": state_grid, "real": _ok(f"real_{COUNTRY}", 3) if real else None,
            },
        },
    }


def _draw(ranking=None, *, order=MODELS, hosting=HOSTING):
    return plot_typicality_distribution_grid(ranking or _ranking(), model_order=list(order), hosting=hosting)


def _box(fig, ax) -> tuple[float, float, float, float]:
    width_pt, height_pt = (v * POINTS_PER_INCH for v in fig.get_size_inches())
    left, bottom, w, h = ax.get_position().bounds
    return left * width_pt, bottom * height_pt, (left + w) * width_pt, (bottom + h) * height_pt


def _cell_axes(fig, i: int, j: int):
    """Axes of row *i*, column *j*: each row adds its cells, the reference and the ternary."""
    return fig.axes[i * (len(MODELS) + 2) + j]


def _texts(fig) -> list:
    return [t for t in fig.texts]


@pytest.fixture
def figure():
    fig = _draw()
    yield fig
    plt.close(fig)


# ------------------------------------------------------------------
# Geometry
# ------------------------------------------------------------------

def test_the_canvas_is_the_approved_456_by_280_5_points(figure):
    width, height = (v * POINTS_PER_INCH for v in figure.get_size_inches())
    assert width == pytest.approx(WIDTH, abs=1e-6)
    assert height == pytest.approx(HEIGHT, abs=1e-6)


def test_every_histogram_cell_sits_at_its_p20_box(figure):
    top = GRID_BOTTOM + 5 * CELL + 4 * ROW_GAP
    for i in range(len(STRATEGIES)):
        cell_top = top - i * (CELL + ROW_GAP)
        for j in range(len(MODELS)):
            x0 = GRID_LEFT + j * (CELL + COLUMN_GAP)
            assert _box(figure, _cell_axes(figure, i, j)) == pytest.approx(
                (x0, cell_top - CELL, x0 + CELL, cell_top), abs=1e-6
            ), (i, j)


def test_the_reference_ternary_and_colourbar_columns_sit_at_their_p20_offsets(figure):
    grid_right = GRID_LEFT + 12 * CELL + 11 * COLUMN_GAP
    assert grid_right - GRID_LEFT == pytest.approx(334.5)
    reference_x0 = grid_right + 6.0
    side = (CELL - 2 * 1.5) / (math.sqrt(3) / 2)
    ternary_x0 = reference_x0 + CELL + 5.0
    top = GRID_BOTTOM + 144.5
    for i in range(len(STRATEGIES)):
        cell_top = top - i * (CELL + ROW_GAP)
        reference = _box(figure, _cell_axes(figure, i, len(MODELS)))
        assert reference == pytest.approx((reference_x0, cell_top - CELL, reference_x0 + CELL, cell_top), abs=1e-6)
        ternary = _box(figure, _cell_axes(figure, i, len(MODELS) + 1))
        bottom = cell_top - CELL + 1.5
        assert ternary == pytest.approx(
            (ternary_x0, bottom, ternary_x0 + side, bottom + side * math.sqrt(3) / 2), abs=1e-6
        )
    colourbar = _box(figure, figure.axes[-1])
    colourbar_x0 = ternary_x0 + side + 6.0
    assert colourbar == pytest.approx((colourbar_x0, GRID_BOTTOM, colourbar_x0 + 7.0, top), abs=1e-6)


def test_thirteen_models_shrink_the_cell_but_keep_the_456_pt_canvas():
    models = [*MODELS, "openrouter_qwen37_max"]
    hosting = {**HOSTING, models[-1]: "hosted"}
    fig = _draw(_ranking(models), order=models, hosting=hosting)
    try:
        width, _ = (v * POINTS_PER_INCH for v in fig.get_size_inches())
        x0, _, x1, _ = _box(fig, fig.axes[0])
        assert width == pytest.approx(WIDTH)
        assert x1 - x0 < CELL
    finally:
        plt.close(fig)


def test_too_many_models_for_the_label_floor_raise():
    with pytest.raises(ValueError, match="18"):
        charts._distribution_cell_side(40, 11)


# ------------------------------------------------------------------
# Cell states
# ------------------------------------------------------------------

def _state_ranking():
    return _ranking(states={
        ("ollama_deepseek_r1_14b", STRATEGIES[-1]): "withdrawn",
        ("ollama_gemma4_e4b", STRATEGIES[-1]): "withdrawn",
        ("claude_haiku", STRATEGIES[0]): "unjudged",
        ("claude_sonnet", STRATEGIES[1]): "no_typicality",
    })


def test_each_cell_state_has_its_own_drawing():
    fig = _draw(_state_ranking())
    try:
        withdrawn = _cell_axes(fig, 4, MODELS.index("ollama_deepseek_r1_14b"))
        assert len(withdrawn.lines) == 2 and not withdrawn.patches
        unjudged = _cell_axes(fig, 0, MODELS.index("claude_haiku"))
        assert mcolors.to_hex(unjudged.get_facecolor()) == mcolors.to_hex(MISSING_COLOR)
        assert not unjudged.patches and not unjudged.texts
        empty = _cell_axes(fig, 1, MODELS.index("claude_sonnet"))
        assert [t.get_text() for t in empty.texts] == ["–"]
        drawn = _cell_axes(fig, 0, 0)
        assert len(drawn.patches) == 11 and len(drawn.lines) == 1   # bars + reference outline
        # The reference column draws its own histogram without an outline of itself.
        reference = _cell_axes(fig, 0, len(MODELS))
        assert len(reference.patches) == 11 and not reference.lines
        legend = fig.findobj(Legend)[0]
        labels = [t.get_text() for t in legend.get_texts()]
        assert "not judged" in labels and "no typicality" in labels and "withdrawn" in labels
    finally:
        plt.close(fig)


def test_the_legend_names_not_judged_and_no_typicality_only_when_drawn(figure):
    labels = [t.get_text() for t in figure.findobj(Legend)[0].get_texts()]
    reference = figure_term("reference")
    assert labels == ["hosted (API)", "locally served", f"{reference} outline", "withdrawn",
                      "combination", reference]


def test_a_ternary_plots_only_the_combinations_it_has_shares_for():
    fig = _draw(_state_ranking())
    try:
        ternary = _cell_axes(fig, 4, len(MODELS) + 1)
        markers = [line for line in ternary.lines if line.get_marker() == "o"]
        assert len(markers) == len(MODELS) - 2
    finally:
        plt.close(fig)


# ------------------------------------------------------------------
# Order, labels and wording
# ------------------------------------------------------------------

def test_columns_follow_the_given_order_and_are_host_tinted(figure):
    names = model_labels(MODELS)
    rotated = [t for t in _texts(figure) if t.get_rotation() == 90]
    assert [t.get_text() for t in rotated] == [names[m] for m in MODELS] + [figure_term("reference")]
    for text, model in zip(rotated, MODELS):
        assert mcolors.to_hex(text.get_color()) == mcolors.to_hex(HOST_COLORS[HOSTING[model]])


def test_rows_are_the_strategy_letters_in_complexity_order(figure):
    letters = [t.get_text() for t in _texts(figure) if t.get_text() in "ABCDE" and len(t.get_text()) == 1]
    assert letters == ["A", "B", "C", "D", "E"]


def test_the_key_and_note_use_the_configured_terms(figure):
    texts = [t.get_text() for t in _texts(figure)]
    key = next(t for t in texts if t.startswith(figure_term("strategy_key_title") + ":"))
    assert "A — All Pick" in key
    assert any(f"share of {figure_term('individuals')} in score bands 0–4 / 5–7 / 8–10" in t for t in texts)
    assert not any("persona" in t.lower() or "SCB" in t for t in texts)


# ------------------------------------------------------------------
# Failure modes
# ------------------------------------------------------------------

def test_a_missing_reference_raises():
    with pytest.raises(ValueError, match="no real population in the consumption set"):
        _draw(_ranking(real=False))


def test_an_order_that_is_not_the_grid_s_models_raises():
    with pytest.raises(ValueError, match="exactly the grid"):
        _draw(order=MODELS[:-1])


def test_a_model_without_a_hosting_class_raises():
    with pytest.raises(ValueError, match="hosting"):
        _draw(hosting={m: c for m, c in HOSTING.items() if m != MODELS[0]})


def test_a_ranking_without_the_block_raises():
    with pytest.raises(ValueError, match="typicality_distribution"):
        plot_typicality_distribution_grid({"typicality_distribution": None}, model_order=[], hosting={})


# ------------------------------------------------------------------
# The written file
# ------------------------------------------------------------------

def test_the_written_svg_is_456_pt_wide(tmp_path):
    path = save_figure(_draw(_state_ranking()), tmp_path / "typicality_distribution_by_model_strategy.png",
                       dpi=100, fixed_canvas=True)
    svg = path.with_suffix(".svg").read_text(encoding="utf-8")
    assert re.search(r'<svg[^>]*\swidth="456pt"', svg)
    assert path.with_suffix(".eps").is_file()
