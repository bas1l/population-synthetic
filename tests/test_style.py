"""Tests for the house figure style.

These are compliance tests, not behaviour tests. ``figure-preparation-standards.docx``
states four numeric constraints -- text at 8-12 pt with 8 pt a hard floor, strokes above
0.25 pt, a canvas of at most 19.05 x 22.23 cm, and Arial -- and the whole point of
:mod:`population_synthetic.analysis.utils.style` is that those are enforced in one place.
A test suite that only exercised the helpers' arithmetic would let the constraints drift
while every test still passed, so each one below asserts a constraint directly.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from population_synthetic.analysis.utils import style

ANALYSIS_ROOT = Path(style.__file__).resolve().parents[1]

# The final dotted segment of every rcParam key whose value is a *text* size, plus the
# one such key that does not follow the pattern. Matched this way rather than on a bare
# ``endswith("size")``, which also catches ``agg.path.chunksize`` (a buffer length) and
# ``xtick.major.size`` (a tick-mark length) -- neither of which is type.
FONT_SIZE_LEAVES = frozenset({"labelsize", "titlesize", "fontsize", "title_fontsize"})
BASE_FONT_SIZE_KEY = "font.size"

# Every rcParam key whose value is a stroke width in points.
STROKE_KEYS = (
    "lines.linewidth",
    "axes.linewidth",
    "grid.linewidth",
    "patch.linewidth",
    "hatch.linewidth",
    "xtick.major.width",
    "ytick.major.width",
    "xtick.minor.width",
    "ytick.minor.width",
)


# ------------------------------------------------------------------
# The import must not pull in a backend
# ------------------------------------------------------------------

def test_importing_style_does_not_import_matplotlib():
    """Importing the style module must not drag a matplotlib backend into the process.

    Checked in a fresh interpreter rather than in this one: by the time this test runs,
    some other import has almost certainly loaded matplotlib already, so an in-process
    assertion would pass no matter what the module does.
    """
    probe = (
        "import sys;"
        "import population_synthetic.analysis.utils.style;"
        "print(any(m == 'matplotlib' or m.startswith('matplotlib.') for m in sys.modules))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "False", (
        "importing style pulled in matplotlib; the module must keep every matplotlib "
        "import inside the functions that need one"
    )


# ------------------------------------------------------------------
# The point-size scale
# ------------------------------------------------------------------

def test_every_named_size_sits_inside_the_publishable_band():
    assert style.FONT_SCALE, "the scale must not be empty"
    for name, size in style.FONT_SCALE.items():
        assert size >= style.FONT_FLOOR_PT, f"{name} = {size} pt is below the 8 pt floor"
        assert size <= style.FONT_CEILING_PT, f"{name} = {size} pt is above the scale's ceiling"


def test_the_scale_covers_each_role_the_standard_names():
    """The standard names four roles; every one of them must have a size."""
    for name in ("TICK_LABEL", "LEGEND_LABEL", "AXIS_TITLE", "PANEL_TITLE"):
        assert name in style.FONT_SCALE


def test_no_rc_param_permits_text_below_the_floor():
    """Resolved inside the applied style, so relative sizes ('small') are caught too."""
    import matplotlib
    from matplotlib.font_manager import font_scalings

    with style.apply_house_style():
        base = matplotlib.rcParams["font.size"]
        for key, value in matplotlib.rcParams.items():
            if key != BASE_FONT_SIZE_KEY and key.rsplit(".", 1)[-1] not in FONT_SIZE_LEAVES:
                continue
            if isinstance(value, str):
                if value not in font_scalings:
                    continue
                points = font_scalings[value] * base
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                points = float(value)
            else:
                continue
            assert points >= style.FONT_FLOOR_PT, (
                f"rcParam {key} = {value!r} resolves to {points} pt, below the 8 pt floor"
            )


def test_no_rc_param_permits_a_stroke_at_or_below_the_floor():
    import matplotlib

    params = style.house_rc_params()
    for key in STROKE_KEYS:
        assert key in params, f"{key} is unpinned; matplotlib's default would decide it"
        assert params[key] > style.MIN_STROKE_PT, (
            f"rcParam {key} = {params[key]} pt does not exceed the 0.25 pt floor"
        )
    with style.apply_house_style():
        for key, value in matplotlib.rcParams.items():
            if not (key.endswith("linewidth") or key.endswith(".width")):
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                assert value > style.MIN_STROKE_PT, (
                    f"rcParam {key} = {value} pt does not exceed the 0.25 pt floor"
                )


def test_the_style_names_no_colour():
    """Colour belongs to ``palette``; the style block must not decide any of it."""
    for key in style.house_rc_params():
        assert not key.endswith(("color", "facecolor", "edgecolor", "colors")), (
            f"rcParam {key} is a colour decision and does not belong in style.py"
        )


# ------------------------------------------------------------------
# The font
# ------------------------------------------------------------------

def test_the_resolved_font_comes_from_the_house_stack():
    assert style.house_font() in style.FONT_STACK


def test_dejavu_is_not_in_the_stack():
    """matplotlib's own default must never satisfy the check that guards against it."""
    assert "DejaVu Sans" not in style.FONT_STACK


def test_the_rc_params_name_the_resolved_family_not_the_generic_alias():
    params = style.house_rc_params()
    assert params["font.family"] == [style.house_font()]
    assert params["font.sans-serif"][0] == style.house_font()


def test_a_figure_built_under_the_style_still_renders_in_the_house_font():
    """The lazy-resolution trap: a generic family is resolved at *render* time.

    Several chart functions return an unsaved ``Figure`` that a driver writes later,
    outside the style context. If the family were the generic ``sans-serif`` alias, that
    render would resolve it against the ambient rcParams and silently produce DejaVu
    Sans -- a compliant-looking figure in the wrong typeface.
    """
    @style.house_style
    def build():
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=style.figure_size(style.SINGLE, 2.0))
        ax.plot([0, 1], [0, 1])
        ax.set_xlabel("x")
        return fig, ax

    fig, ax = build()
    try:
        fig.canvas.draw()
        assert ax.xaxis.label.get_fontname() == style.house_font()
        assert all(t.get_fontname() == style.house_font() for t in ax.get_xticklabels())
    finally:
        import matplotlib.pyplot as plt

        plt.close(fig)


# ------------------------------------------------------------------
# The canvas vocabulary
# ------------------------------------------------------------------

def test_the_size_vocabulary_stays_within_the_printable_canvas():
    assert style.SINGLE == pytest.approx(8.9 / 2.54)
    assert style.DOUBLE == pytest.approx(17.4 / 2.54)
    assert style.FULL == pytest.approx(19.05 / 2.54)
    assert style.MAX_HEIGHT == pytest.approx(22.23 / 2.54)
    assert style.SINGLE < style.DOUBLE < style.FULL
    assert style.MAX_WIDTH == style.FULL


def test_the_strip_canvas_is_the_manuscript_text_width_and_fits_the_page():
    assert style.TEXT_WIDTH == pytest.approx(456.0 / 72.0)
    assert style.STRIP_HEIGHT == pytest.approx(150.0 / 72.0)
    assert style.SINGLE < style.TEXT_WIDTH < style.DOUBLE < style.FULL
    assert style.STRIP_HEIGHT < style.MAX_HEIGHT


def test_the_strip_axis_title_sits_at_the_floor():
    """A strip is set entirely at the floor, its axis title included."""
    assert style.STRIP_AXIS_TITLE == style.FONT_FLOOR_PT
    assert style.FONT_SCALE["STRIP_AXIS_TITLE"] == style.STRIP_AXIS_TITLE


def test_figure_size_clamps_an_oversized_pair():
    width, height = style.figure_size(40.0, 40.0)
    assert width == style.FULL
    assert height == style.MAX_HEIGHT


def test_figure_size_leaves_a_pair_inside_the_caps_alone():
    assert style.figure_size(4.0, 3.0) == (4.0, 3.0)


@pytest.mark.parametrize("width,height", [(0.0, 3.0), (-1.0, 3.0), (3.0, 0.0), (3.0, -1.0)])
def test_figure_size_rejects_a_non_positive_length(width, height):
    with pytest.raises(ValueError):
        style.figure_size(width, height)


def test_growth_helpers_clamp_to_the_printable_canvas():
    assert style.grow_width(500, per_item=1.5, padding=3.0) == style.FULL
    assert style.grow_height(500, per_item=1.5, padding=3.0) == style.MAX_HEIGHT


def test_growth_helpers_honour_their_floor():
    assert style.grow_width(0, per_item=1.5, padding=0.1, minimum=3.0) == 3.0
    assert style.grow_height(0, per_item=1.5, padding=0.1, minimum=3.0) == 3.0


def test_growth_helpers_grow_between_the_floor_and_the_cap():
    assert style.grow_width(2, per_item=1.0, padding=1.0, minimum=1.0) == pytest.approx(3.0)


def test_growth_helpers_default_their_floor_to_the_single_column_width():
    assert style.grow_width(0, per_item=1.0, padding=0.0) == style.SINGLE
    assert style.grow_height(0, per_item=1.0, padding=0.0) == style.SINGLE


def test_a_growth_cap_above_the_printable_canvas_is_still_clamped():
    """A caller may not opt out of the paper's limits by passing a larger maximum."""
    assert style.grow_width(500, per_item=1.0, padding=0.0, maximum=40.0) == style.FULL
    assert style.grow_height(500, per_item=1.0, padding=0.0, maximum=40.0) == style.MAX_HEIGHT


def test_a_growth_floor_above_the_printable_canvas_raises():
    with pytest.raises(ValueError, match="exceeds the printable maximum"):
        style.grow_width(1, per_item=1.0, padding=0.0, minimum=40.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"per_item": 0.0, "padding": 1.0},
        {"per_item": -1.0, "padding": 1.0},
        {"per_item": 1.0, "padding": -1.0},
    ],
)
def test_growth_helpers_reject_a_degenerate_rate(kwargs):
    with pytest.raises(ValueError):
        style.grow_width(3, **kwargs)


def test_growth_helpers_reject_a_negative_count():
    with pytest.raises(ValueError):
        style.grow_width(-1, per_item=1.0, padding=1.0)


def test_growth_helpers_reject_a_boolean_count():
    """``True`` is an ``int``; a boolean reaching a length calculation is always a bug."""
    with pytest.raises(TypeError):
        style.grow_width(True, per_item=1.0, padding=1.0)


def test_growth_helpers_admit_a_fractional_count():
    """Two manuscript grids reserve an in-axes margin in fractional column units."""
    assert style.grow_width(2.5, per_item=1.0, padding=0.0, minimum=1.0) == pytest.approx(2.5)


# ------------------------------------------------------------------
# Global state stays confined
# ------------------------------------------------------------------

def test_applying_the_style_restores_the_previous_rc_params():
    import matplotlib

    before = matplotlib.rcParams["font.size"]
    with style.apply_house_style():
        assert matplotlib.rcParams["font.size"] == style.TICK_LABEL
    assert matplotlib.rcParams["font.size"] == before


def test_applying_the_style_selects_the_headless_backend():
    import matplotlib

    with style.apply_house_style():
        assert matplotlib.get_backend().lower() == style.HEADLESS_BACKEND.lower()


def test_the_decorator_applies_the_style_for_the_call_only():
    import matplotlib

    @style.house_style
    def draw():
        return matplotlib.rcParams["font.size"]

    before = matplotlib.rcParams["font.size"]
    assert draw() == style.TICK_LABEL
    assert matplotlib.rcParams["font.size"] == before


# ------------------------------------------------------------------
# The analysis layer draws through it
# ------------------------------------------------------------------

SIZE_LITERAL = re.compile(r"\b(?:fontsize|labelsize|title_fontsize)\s*=\s*(\d+(?:\.\d+)?)")


def _analysis_sources():
    return sorted(ANALYSIS_ROOT.rglob("*.py"))


def test_no_analysis_module_writes_a_font_size_literal():
    offenders = [
        f"{path.relative_to(ANALYSIS_ROOT).as_posix()}: {match.group(0)}"
        for path in _analysis_sources()
        for match in SIZE_LITERAL.finditer(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        "font sizes must be named from the house scale, not written as literals: "
        + "; ".join(offenders)
    )


def test_style_is_the_only_module_that_selects_a_backend():
    offenders = [
        path.relative_to(ANALYSIS_ROOT).as_posix()
        for path in _analysis_sources()
        if path.name != "style.py" and "matplotlib.use(" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"backend selection belongs to style.py alone, found in {offenders}"


def test_the_shared_grid_annotation_size_respects_the_floor():
    """The one named size that used to sit at 7.0 pt, below the floor."""
    from population_synthetic.analysis.utils import table_style

    assert table_style.ANNOT_FONTSIZE >= style.FONT_FLOOR_PT


# ------------------------------------------------------------------
# Fitting text to the canvas
# ------------------------------------------------------------------

def test_a_measured_width_grows_with_the_size_it_is_set_at():
    """Metrics read from the font, not a characters-per-inch guess."""
    small = style.text_width_inches("a caption of some length", fontsize=style.FONT_FLOOR_PT)
    large = style.text_width_inches("a caption of some length", fontsize=style.FONT_CEILING_PT)
    assert 0 < small < large


def test_measuring_a_multi_line_string_raises_rather_than_measuring_the_run():
    """Measuring the concatenation would report a width no line actually has."""
    with pytest.raises(ValueError, match="newline"):
        style.text_width_inches("two\nlines", fontsize=style.ANNOTATION)


@pytest.mark.parametrize("width", [style.SINGLE, style.DOUBLE, style.FULL])
def test_every_wrapped_line_fits_the_width_it_was_given(width):
    """The property the caption fix rests on, asserted by measuring the result."""
    caption = (
        "Each cell is that combination's retention rate: the share of the generated "
        "pool that survived both validators, printed with the two counts it is the "
        "quotient of, and hatched where the full-N rule withdrew the combination."
    )
    wrapped = style.wrap_to_width(caption, width, fontsize=style.ANNOTATION)
    for line in wrapped.splitlines():
        assert style.text_width_inches(line, fontsize=style.ANNOTATION) <= width


def test_wrapping_preserves_the_words_and_their_order():
    """A wrap is a layout decision; it must not edit the sentence."""
    caption = "one two three four five six seven eight nine ten eleven twelve thirteen"
    wrapped = style.wrap_to_width(caption, style.SINGLE, fontsize=style.ANNOTATION)
    assert wrapped.split() == caption.split()


def test_a_string_that_already_fits_is_returned_unwrapped():
    """No gratuitous break: the caption fills the line it is given."""
    assert style.wrap_to_width("short", style.FULL, fontsize=style.ANNOTATION) == "short"


def test_hard_breaks_survive_the_wrap():
    """A caption that authored its own paragraph break keeps it."""
    wrapped = style.wrap_to_width("first line\nsecond line", style.FULL, fontsize=style.ANNOTATION)
    assert wrapped == "first line\nsecond line"


def test_a_non_positive_width_raises():
    with pytest.raises(ValueError, match="positive"):
        style.wrap_to_width("anything", 0.0, fontsize=style.ANNOTATION)


def test_the_point_conversion_has_one_definition():
    """`figures` binds it rather than restating it, so the two can never disagree."""
    from population_synthetic.analysis.utils import figures

    assert figures.POINTS_PER_INCH is style.POINTS_PER_INCH
