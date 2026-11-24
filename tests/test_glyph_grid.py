"""Tests for the point-laid-out glyph grid drawing module.

What is pinned here is the presentation boundary as it applies to this module: it draws
finished numbers at exact point positions, validates rather than normalises what it is
handed, rejects a string that can only be an unresolved id, draws nothing translucent, and
imports nothing but the two presentation modules it builds on.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # noqa: E402 -- before any package import that may touch pyplot

import matplotlib.colors as mcolors  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402

from population_synthetic.analysis.utils import glyph_grid  # noqa: E402
from population_synthetic.analysis.utils.figures import save_figure  # noqa: E402
from population_synthetic.analysis.utils.glyph_grid import (  # noqa: E402
    REFERENCE_OUTLINE_WIDTH,
    TERNARY_HEIGHT_RATIO,
    TERNARY_VERTICES,
    WITHDRAWN_STROKE_WIDTH,
    PointCanvas,
    draw_empty_cell,
    draw_mini_histogram,
    draw_ternary,
    draw_withdrawn_cell,
    outline_handle,
    point_handle,
    reference_star_handle,
    step_colors,
    stepped_colorbar,
    swatch_handle,
    ternary_position,
    withdrawn_handle,
)
from population_synthetic.analysis.utils.palette import (  # noqa: E402
    BASELINE_DARK,
    MISSING_COLOR,
    MUTED_GREY,
    SURFACE,
    heatmap_levels,
    text_color_for_rgb,
)
from population_synthetic.analysis.utils.style import (  # noqa: E402
    FULL,
    MAX_HEIGHT,
    MIN_STROKE_PT,
    POINTS_PER_INCH,
    TICK_LABEL,
    apply_house_style,
)

# The P20 geometry of the plan's Definitions: 12 model columns x 5 strategy rows.
_W, _H = 456.0, 280.5
_CELL, _COL_GAP, _ROW_GAP, _X0, _Y0 = 26.5, 1.5, 3.0, 20.0, 60.0
_N_LEVELS = 11
_UNIFORM = np.full(_N_LEVELS, 1.0 / _N_LEVELS)
_PEAKED = np.r_[np.zeros(_N_LEVELS - 1), 1.0]


def _p20_boxes(n_models: int = 12, n_rows: int = 5):
    top_of_grid = _Y0 + n_rows * _CELL + (n_rows - 1) * _ROW_GAP
    boxes = []
    for i in range(n_rows):
        top = top_of_grid - i * (_CELL + _ROW_GAP)
        for j in range(n_models):
            x = _X0 + j * (_CELL + _COL_GAP)
            boxes.append((x, top - _CELL, x + _CELL, top))
    return boxes


@pytest.fixture
def canvas():
    with apply_house_style():
        cv = PointCanvas(_W, _H)
        yield cv
    plt.close(cv.figure)


def _ternary_axes(cv, x0=400.0, y0=100.0, side=20.0):
    return cv.axes(x0, y0, x0 + side, y0 + side * TERNARY_HEIGHT_RATIO)


def _drawn_figure():
    """One figure exercising every drawing function, inside the house style."""
    with apply_house_style():
        cv = PointCanvas(_W, _H)
        levels = heatmap_levels(_N_LEVELS)
        colors = step_colors(levels)
        boxes = _p20_boxes(3, 2)
        draw_mini_histogram(cv.axes(*boxes[0]), _UNIFORM, colors, outline=_PEAKED)
        draw_withdrawn_cell(cv.axes(*boxes[1]))
        draw_empty_cell(cv.axes(*boxes[2]), fill=SURFACE, mark="–")
        draw_empty_cell(cv.axes(*boxes[3]), fill=MISSING_COLOR, mark=None)
        draw_ternary(
            _ternary_axes(cv), [(0.2, 0.3, 0.5), (0.0, 0.0, 1.0)], (0.4, 0.4, 0.2),
            point_colors=["#4878CF", "#E8935A"], apex_guides=(0.5,),
            apex_label="8–10", base_labels=("0–4", "5–7"),
        )
        stepped_colorbar(cv, (430.0, 100.0, 437.0, 200.0), levels, _N_LEVELS, "Score")
        cv.text(10.0, 150.0, "A", fontsize=TICK_LABEL)
        cv.legend(
            [swatch_handle("hosted (API)", color="#4878CF"), outline_handle("Reference outline"),
             withdrawn_handle("withdrawn"), point_handle("combination", color=BASELINE_DARK),
             reference_star_handle("Reference")],
            x=4.0, y_top=40.0, ncol=5,
        )
    return cv


# --------------------------------------------------------------------------- #
# the canvas                                                                    #
# --------------------------------------------------------------------------- #

def test_the_canvas_is_written_at_exactly_its_point_size(tmp_path):
    cv = _drawn_figure()
    written = save_figure(cv.figure, tmp_path / "glyph.png", fixed_canvas=True)
    head = written.with_suffix(".svg").read_text(encoding="utf-8")[:2000]
    assert re.search(r'<svg[^>]*\swidth="456pt"', head)
    assert re.search(r'<svg[^>]*\sheight="280\.5pt"', head)


@pytest.mark.parametrize(
    "width, height",
    [
        (FULL * POINTS_PER_INCH + 0.01, 100.0),
        (100.0, MAX_HEIGHT * POINTS_PER_INCH + 0.01),
        (0.0, 100.0),
        (100.0, -1.0),
        (float("nan"), 100.0),
    ],
)
def test_an_unprintable_or_empty_canvas_raises(width, height):
    with pytest.raises(ValueError):
        PointCanvas(width, height)


def test_every_cell_sits_at_its_point_box(canvas):
    boxes = _p20_boxes()
    axes = [canvas.axes(*box) for box in boxes]
    for ax, box in zip(axes, boxes):
        assert canvas.points_box(ax) == pytest.approx(box, abs=1e-6)


@pytest.mark.parametrize(
    "box",
    [(10.0, 10.0, 10.0, 20.0), (10.0, 20.0, 20.0, 10.0), (-1.0, 0.0, 10.0, 10.0),
     (0.0, 0.0, _W + 1.0, 10.0), (0.0, 0.0, 10.0, _H + 1.0)],
)
def test_an_empty_or_off_canvas_box_raises(canvas, box):
    with pytest.raises(ValueError):
        canvas.axes(*box)


def test_canvas_text_is_checked(canvas):
    with pytest.raises(ValueError, match="underscore"):
        canvas.text(10.0, 10.0, "openrouter_kimi_k3", fontsize=TICK_LABEL)
    with pytest.raises(ValueError, match="house scale"):
        canvas.text(10.0, 10.0, "Kimi K3", fontsize=6.0)
    with pytest.raises(ValueError, match="alpha"):
        canvas.text(10.0, 10.0, "Kimi K3", fontsize=TICK_LABEL, alpha=0.5)
    with pytest.raises(ValueError, match="non-empty"):
        canvas.text(10.0, 10.0, " ", fontsize=TICK_LABEL)


def test_canvas_text_is_placed_in_points(canvas):
    text = canvas.text(114.0, 70.125, "Kimi K3", fontsize=TICK_LABEL)
    assert text.get_position() == pytest.approx((114.0 / _W, 70.125 / _H))


def test_a_legend_rejects_an_unresolved_id_and_a_bad_column_count(canvas):
    from matplotlib.lines import Line2D

    with pytest.raises(ValueError, match="underscore"):
        canvas.legend([Line2D([], [], label="claude_haiku")], x=4.0, y_top=40.0, ncol=1)
    with pytest.raises(ValueError, match="ncol"):
        canvas.legend([outline_handle("Reference")], x=4.0, y_top=40.0, ncol=0)
    with pytest.raises(ValueError, match="at least one"):
        canvas.legend([], x=4.0, y_top=40.0, ncol=1)


@pytest.mark.parametrize(
    "factory",
    [outline_handle, withdrawn_handle, reference_star_handle,
     lambda label: point_handle(label, color=BASELINE_DARK),
     lambda label: swatch_handle(label, color=MISSING_COLOR)],
)
def test_every_legend_handle_rejects_an_unresolved_id(factory):
    with pytest.raises(ValueError, match="underscore"):
        factory("real_swedish_02")


# --------------------------------------------------------------------------- #
# the mini histogram                                                            #
# --------------------------------------------------------------------------- #

def test_the_histogram_draws_the_mass_it_is_given(canvas):
    heights = np.array([0.0, 0.1, 0.2, 0.3, 0.4, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    colors = step_colors(heights_levels := heatmap_levels(_N_LEVELS))
    ax = canvas.axes(*_p20_boxes()[0])
    draw_mini_histogram(ax, heights, colors, outline=_UNIFORM)

    bars = ax.patches
    assert len(bars) == _N_LEVELS
    for k, bar in enumerate(bars):
        assert bar.get_x() + bar.get_width() / 2 == pytest.approx(k)
        assert bar.get_width() == pytest.approx(1.0)
        assert bar.get_height() == pytest.approx(heights[k])
        assert mcolors.to_hex(bar.get_facecolor()) == mcolors.to_hex(heights_levels(k))
    assert ax.get_yscale() == "function"
    assert ax.get_ylim() == pytest.approx((0.0, 1.0))
    assert ax.get_xticks().size == 0 and ax.get_yticks().size == 0

    (outline,) = ax.get_lines()
    assert outline.get_drawstyle() == "steps-post"
    assert outline.get_linewidth() == pytest.approx(REFERENCE_OUTLINE_WIDTH)
    assert mcolors.to_hex(outline.get_color()) == mcolors.to_hex(BASELINE_DARK)
    np.testing.assert_allclose(outline.get_xdata(), np.arange(_N_LEVELS + 1) - 0.5)
    np.testing.assert_allclose(outline.get_ydata(), np.r_[_UNIFORM, _UNIFORM[-1]])


def test_a_single_level_histogram_reaches_the_top_of_the_square_root_scale(canvas):
    ax = canvas.axes(*_p20_boxes()[0])
    draw_mini_histogram(ax, _PEAKED, step_colors(heatmap_levels(_N_LEVELS)))
    assert ax.patches[-1].get_height() == pytest.approx(1.0)
    assert len(ax.get_lines()) == 0


@pytest.mark.parametrize(
    "heights, message",
    [
        (np.full(_N_LEVELS, 0.1), "sums to"),
        (np.r_[-0.1, 1.1, np.zeros(_N_LEVELS - 2)], "outside"),
        (np.r_[np.nan, np.zeros(_N_LEVELS - 1)], "non-finite"),
        (np.zeros((2, 2)), "1-D"),
    ],
)
def test_histogram_heights_are_validated_not_normalised(canvas, heights, message):
    ax = canvas.axes(*_p20_boxes()[0])
    with pytest.raises(ValueError, match=message):
        draw_mini_histogram(ax, heights, ["#000000"] * np.asarray(heights).size)


def test_histogram_colour_and_outline_lengths_must_match(canvas):
    colors = step_colors(heatmap_levels(_N_LEVELS))
    with pytest.raises(ValueError, match="colour"):
        draw_mini_histogram(canvas.axes(*_p20_boxes()[0]), _UNIFORM, colors[:-1])
    with pytest.raises(ValueError, match="outline"):
        draw_mini_histogram(canvas.axes(*_p20_boxes()[1]), _UNIFORM, colors, outline=[0.5, 0.5])
    with pytest.raises(ValueError, match="sums to"):
        draw_mini_histogram(canvas.axes(*_p20_boxes()[2]), _UNIFORM, colors, outline=_UNIFORM * 2)


# --------------------------------------------------------------------------- #
# withdrawn and empty cells                                                     #
# --------------------------------------------------------------------------- #

def test_a_withdrawn_cell_is_crossed_out(canvas):
    ax = canvas.axes(*_p20_boxes()[0])
    draw_withdrawn_cell(ax)
    lines = ax.get_lines()
    assert len(lines) == 2
    assert {tuple(line.get_ydata()) for line in lines} == {(0.0, 1.0), (1.0, 0.0)}
    for line in lines:
        assert line.get_transform() == ax.transAxes
        assert line.get_linewidth() == pytest.approx(WITHDRAWN_STROKE_WIDTH)
        assert mcolors.to_hex(line.get_color()) == mcolors.to_hex(MUTED_GREY)
    assert len(ax.patches) == 0


def test_an_empty_cell_is_filled_and_optionally_marked(canvas):
    marked = canvas.axes(*_p20_boxes()[0])
    draw_empty_cell(marked, fill=SURFACE, mark="–")
    (text,) = marked.texts
    assert text.get_text() == "–"
    assert text.get_color() == text_color_for_rgb(mcolors.to_rgb(SURFACE))
    assert mcolors.to_hex(marked.get_facecolor()) == mcolors.to_hex(SURFACE)

    unmarked = canvas.axes(*_p20_boxes()[1])
    draw_empty_cell(unmarked, fill=MISSING_COLOR, mark=None)
    assert len(unmarked.texts) == 0
    assert mcolors.to_hex(unmarked.get_facecolor()) == mcolors.to_hex(MISSING_COLOR)

    with pytest.raises(ValueError, match="underscore"):
        draw_empty_cell(canvas.axes(*_p20_boxes()[2]), fill=SURFACE, mark="no_typicality")


# --------------------------------------------------------------------------- #
# the ternary                                                                   #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("corner", range(3))
def test_a_pure_triple_lands_on_its_corner(corner):
    shares = [0.0, 0.0, 0.0]
    shares[corner] = 1.0
    assert ternary_position(shares) == pytest.approx(TERNARY_VERTICES[corner])


def test_the_barycentre_is_the_centroid():
    assert ternary_position([1 / 3, 1 / 3, 1 / 3]) == pytest.approx((0.5, TERNARY_HEIGHT_RATIO / 3))


@pytest.mark.parametrize(
    "shares, message",
    [((0.5, 0.5, 0.5), "sums to"), ((-0.1, 0.6, 0.5), "non-negative"),
     ((0.5, 0.5), "three"), ((np.nan, 0.5, 0.5), "finite")],
)
def test_a_share_triple_is_validated_not_normalised(shares, message):
    with pytest.raises(ValueError, match=message):
        ternary_position(shares)


def test_the_ternary_draws_its_points_star_guide_and_labels(canvas):
    ax = _ternary_axes(canvas)
    points = [(0.2, 0.3, 0.5), (0.0, 0.1, 0.9)]
    draw_ternary(
        ax, points, (0.5, 0.3, 0.2), point_colors=["#4878CF", "#E8935A"], apex_guides=(0.5,),
        apex_label="8–10", base_labels=("0–4", "5–7"),
    )
    lines = ax.get_lines()
    dots = [line for line in lines if line.get_marker() == "o"]
    stars = [line for line in lines if line.get_marker() == "*"]
    assert [(d.get_xdata()[0], d.get_ydata()[0]) for d in dots] == pytest.approx(
        [ternary_position(p) for p in points]
    )
    assert [mcolors.to_hex(d.get_color()) for d in dots] == ["#4878cf", "#e8935a"]
    assert len(stars) == 1
    assert (stars[0].get_xdata()[0], stars[0].get_ydata()[0]) == pytest.approx(
        ternary_position((0.5, 0.3, 0.2))
    )
    assert stars[0].get_zorder() > dots[0].get_zorder()
    guide = [line for line in lines if line.get_marker() in ("None", None, "") and len(line.get_xdata()) == 2]
    assert len(guide) == 1
    assert guide[0].get_ydata() == pytest.approx((TERNARY_HEIGHT_RATIO / 2, TERNARY_HEIGHT_RATIO / 2))
    assert sorted(t.get_text() for t in ax.texts) == ["0–4", "5–7", "8–10"]


def test_ternary_labels_are_drawn_only_when_given(canvas):
    ax = _ternary_axes(canvas)
    draw_ternary(ax, [], (0.2, 0.3, 0.5), point_colors=[], apex_guides=())
    assert len(ax.texts) == 0


def test_ternary_inputs_are_checked(canvas):
    with pytest.raises(ValueError, match="distorted"):
        draw_ternary(canvas.axes(400.0, 100.0, 420.0, 120.0), [], (0.2, 0.3, 0.5),
                     point_colors=[], apex_guides=())
    with pytest.raises(ValueError, match="point colour"):
        draw_ternary(_ternary_axes(canvas), [(0.2, 0.3, 0.5)], (0.2, 0.3, 0.5),
                     point_colors=[], apex_guides=())
    with pytest.raises(ValueError, match="sums to"):
        draw_ternary(_ternary_axes(canvas), [(0.2, 0.3, 0.6)], (0.2, 0.3, 0.5),
                     point_colors=["#000000"], apex_guides=())
    with pytest.raises(ValueError, match="strictly between"):
        draw_ternary(_ternary_axes(canvas), [], (0.2, 0.3, 0.5), point_colors=[], apex_guides=(1.0,))
    with pytest.raises(ValueError, match="underscore"):
        draw_ternary(_ternary_axes(canvas), [], (0.2, 0.3, 0.5), point_colors=[], apex_guides=(),
                     apex_label="band_high")


# --------------------------------------------------------------------------- #
# the stepped colourbar                                                         #
# --------------------------------------------------------------------------- #

def test_the_colourbar_has_one_step_and_tick_per_level(canvas):
    levels = heatmap_levels(_N_LEVELS)
    colorbar = stepped_colorbar(canvas, (430.0, 60.0, 437.0, 204.5), levels, _N_LEVELS, "Score")
    np.testing.assert_allclose(colorbar.get_ticks(), np.arange(_N_LEVELS))
    np.testing.assert_allclose(colorbar.norm.boundaries, np.arange(_N_LEVELS + 1) - 0.5)
    assert canvas.points_box(colorbar.ax) == pytest.approx((430.0, 60.0, 437.0, 204.5), abs=1e-6)
    assert "Score" in [t.get_text() for t in canvas.figure.texts]
    assert step_colors(levels) == [mcolors.to_hex(levels(k)) for k in range(_N_LEVELS)]


def test_the_colourbar_inputs_are_checked(canvas):
    with pytest.raises(ValueError, match="step"):
        stepped_colorbar(canvas, (430.0, 60.0, 437.0, 200.0), heatmap_levels(5), _N_LEVELS, "Score")
    with pytest.raises(ValueError, match="underscore"):
        stepped_colorbar(canvas, (430.0, 60.0, 437.0, 200.0), heatmap_levels(_N_LEVELS), _N_LEVELS,
                         "typicality_score")


# --------------------------------------------------------------------------- #
# the presentation boundary                                                     #
# --------------------------------------------------------------------------- #

def test_no_artist_is_translucent():
    """Nothing is drawn below full coverage.

    ``alpha is None`` is what this module's own artists carry. matplotlib itself sets
    exactly ``1.0`` on a few artists it builds -- the legend frame (``legend.framealpha``)
    and some tick marks -- which is opaque and so equally safe in the EPS. Source-level
    absence of ``alpha=`` is asserted across the package by ``tests/test_palette.py``.
    """
    cv = _drawn_figure()
    translucent = [
        repr(artist) for artist in cv.figure.findobj()
        if hasattr(artist, "get_alpha") and artist.get_alpha() not in (None, 1.0)
    ]

    plt.close(cv.figure)
    assert translucent == []


def test_every_named_stroke_exceeds_the_floor():
    widths = {
        name: getattr(glyph_grid, name) for name in glyph_grid.__all__
        if name.endswith("_WIDTH")
    }
    assert widths, "the module names no stroke widths"
    for name, width in widths.items():
        assert width > MIN_STROKE_PT, name


def test_every_drawn_line_exceeds_the_stroke_floor():
    from matplotlib.lines import Line2D

    cv = _drawn_figure()
    for line in cv.figure.findobj(Line2D):
        if line.get_linestyle() not in ("None", "none", " ", ""):
            assert line.get_linewidth() > MIN_STROKE_PT, line
        if line.get_marker() not in ("None", "none", " ", "", None):
            assert line.get_markeredgewidth() > MIN_STROKE_PT, line
    plt.close(cv.figure)


def test_the_drawn_figure_is_camera_ready():
    from tests.test_figure_compliance import assert_camera_ready

    cv = _drawn_figure()
    assert_camera_ready(cv.figure, "glyph_grid")
    plt.close(cv.figure)


def test_the_module_imports_only_the_presentation_modules_it_builds_on():
    """Membership test for the layer, narrowed: no subpackage, no labels, no config."""
    tree = ast.parse(Path(glyph_grid.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    ours = {name for name in imported if name.startswith("population_synthetic")}
    assert ours == {
        "population_synthetic.analysis.utils.palette",
        "population_synthetic.analysis.utils.style",
    }


def test_the_module_draws_no_image_and_writes_no_file():
    source = Path(glyph_grid.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    called = {
        node.func.attr for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not called & {"imshow", "savefig", "use"}
