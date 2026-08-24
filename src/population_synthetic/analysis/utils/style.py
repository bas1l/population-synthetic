"""style.py -- The one place that decides how an analysis-layer figure *looks*.

Before this module the analysis layer had no style layer at all. No ``rcParams``
were ever set, no ``.mplstyle`` existed and no font family was named, so every
figure shipped in matplotlib's default DejaVu Sans; ``fontsize=`` was passed ~300
times across 29 distinct values, fourteen of them below the publisher's 8 pt floor;
the backend was selected by 52 separate in-function ``matplotlib.use("Agg")`` calls;
and 58 ``figsize=`` call sites grew their canvas by ad-hoc formulae with no upper
bound, so a wide grid could exceed the maximum printable canvas without anything
noticing. Each of those is a *presentation* decision that has exactly one right
answer per publication, which is why they now have exactly one home.

**What it owns.** matplotlib's global state: the headless backend, the ``rcParams``
block, the font family and its fallback stack, the point-size scale, the stroke
weights, and the figure-size vocabulary with the growth helpers that clamp to the
printable canvas.

**What it knows nothing about.** Any data, any label text, any colour value. It
never sees a number that will be plotted, never authors a string that will be
printed, and names no hue -- colour is :mod:`population_synthetic.analysis.utils.palette`
and nothing here may restate any part of it. A helper here takes a count or a pair
of lengths and returns lengths; it takes no arrays and no records. The two that do
receive a string -- :func:`wrap_to_width` and :func:`caption_block` -- measure and
place it and nothing else: neither reads it, branches on it, or could tell a caption
from a legend entry.

**Global state is confined here.** ``rcParams`` is process-wide, so mutating it from
a chart module would make one figure's appearance depend on which figure was drawn
before it. Every application therefore goes through :func:`apply_house_style` (or the
:func:`house_style` decorator that wraps a draw function in it), which enters a
``plt.rc_context`` -- the values are installed for the duration of one draw and
restored on exit, so the layer has one style and no ordering hazard.

**The constraints below are not preferences.** They are the binding requirements of
``figure-preparation-standards.docx`` in the manuscript folder: Arial; 8-12 pt at
final print size with 8 pt a hard floor; strokes above 0.25 pt; RGB, 8-bit; a canvas
of at most 19.05 x 22.23 cm, with 8.9 cm the single-column and 17.4 cm the
double-column target. Every constant in this module is one of those numbers or is
derived from one, and ``tests/test_style.py`` asserts that none of them drifts below
a floor or above a cap.

Follows the project charting convention: **no module-level matplotlib import**, so
importing this module never pulls in a backend (mirroring
:mod:`population_synthetic.analysis.utils.table_style`). matplotlib is imported inside
the two functions that need it.
"""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache, wraps
from pathlib import Path
from typing import Any, Callable, TypeVar

# ------------------------------------------------------------------
# The backend
# ------------------------------------------------------------------

#: The rendering backend. ``Agg`` because every figure in this layer is written to a
#: file by a batch process that has no display; selecting it before pyplot is first
#: imported is what keeps the analysis workflow runnable over SSH and inside CI.
#: This is the **only** place in ``src/`` that names a backend.
HEADLESS_BACKEND = "Agg"


# ------------------------------------------------------------------
# The font
# ------------------------------------------------------------------

#: The font families tried, in order, when installing the house font.
#:
#: Arial is what the standards document requires. The rest are its metric-compatible
#: substitutes, in descending order of fidelity to Arial's metrics -- Liberation Sans
#: and Arimo are metric clones, Helvetica is the typeface Arial was drawn to replace
#: and Nimbus Sans is the standard free Helvetica clone. A figure set out in any of
#: them is typographically the figure set the standard asks for.
#:
#: **DejaVu Sans is deliberately absent.** It is matplotlib's own default, so leaving
#: it in the stack would make the failure this stack exists to prevent -- a silent
#: substitution back to the default -- indistinguishable from success.
FONT_STACK = ("Arial", "Liberation Sans", "Arimo", "Helvetica", "Nimbus Sans")


class HouseFontUnavailable(RuntimeError):
    """Raised when none of :data:`FONT_STACK` is installed on the render host.

    Fails the run rather than letting matplotlib fall back to DejaVu Sans, which
    would produce a full figure set that looks finished and is non-compliant.
    """


@lru_cache(maxsize=1)
def house_font() -> str:
    """Return the first family of :data:`FONT_STACK` actually installed here.

    Resolved against ``font_manager``'s registry of installed families by exact
    name, not through ``findfont`` -- ``findfont`` answers a *nearest match*, which
    is precisely the silent substitution this check exists to catch.

    Raises :class:`HouseFontUnavailable`, naming the stack that was searched and the
    font directories it was searched in, when the host has none of them installed.
    """
    from matplotlib import font_manager

    installed = {entry.name for entry in font_manager.fontManager.ttflist}
    for family in FONT_STACK:
        if family in installed:
            return family
    searched = sorted({str(Path(entry.fname).parent) for entry in font_manager.fontManager.ttflist})
    raise HouseFontUnavailable(
        "None of the house font families is installed on this render host. Searched "
        f"for {', '.join(FONT_STACK)} among the {len(installed)} families matplotlib "
        f"found in: {', '.join(searched) or '(no font directories)'}. Install Arial, "
        "or one of its metric-compatible substitutes, on this host: the figure set is "
        "not publishable in matplotlib's DejaVu Sans default, and substituting it "
        "silently is the failure this check exists to prevent."
    )


# ------------------------------------------------------------------
# The point-size scale
# ------------------------------------------------------------------

#: The publisher's hard floor, in points, at final print size. No text in any emitted
#: figure may be smaller; ``tests/test_style.py`` asserts no size below it exists.
FONT_FLOOR_PT = 8.0

#: The top of the scale. Larger type is not forbidden by the standard so much as
#: pointless at these canvas sizes -- a 16 pt number on an 8.9 cm panel is a slide,
#: not a figure -- and capping it keeps the family visually homogeneous.
FONT_CEILING_PT = 12.0

#: Tick labels: the standard's 8-9 pt band. The plain name is the floor value, used
#: everywhere the axis is dense; the ``_LARGE`` variant is the one step up, for the
#: sparse axes where the extra point buys legibility without crowding.
TICK_LABEL = 8.0
TICK_LABEL_LARGE = 9.0

#: Legend entries: 8 pt, exactly as the standard specifies. The legend *title* takes
#: one step up so the group heading still reads as a heading, as it did before this
#: scale existed (7.5 pt entries under an 8 pt title).
LEGEND_LABEL = 8.0
LEGEND_TITLE = 9.0

#: In-canvas annotation: numbers written into heatmap cells, value labels on bars,
#: footnotes and caveat lines. Shares the floor with tick labels because it is the
#: densest text on any figure in this layer and has the least room to grow.
ANNOTATION = 8.0
ANNOTATION_LARGE = 9.0

#: In-canvas emphasis: a placeholder message standing in for an undrawable panel, or
#: a single highlighted value. Larger than an annotation because it must be found
#: without being looked for, smaller than a panel header because it is not one.
CALLOUT = 10.0

#: Axis titles: 10 pt, as the standard specifies.
AXIS_TITLE = 10.0

#: Panel headers: the standard's 11-12 pt bold band. :data:`PANEL_TITLE` heads one
#: panel of a figure, :data:`FIGURE_TITLE` heads the whole canvas. Boldness is carried
#: by the ``rcParams`` below, not by the size.
PANEL_TITLE = 11.0
FIGURE_TITLE = 12.0

#: Every size the scale offers, for the tests and for anyone auditing the ladder.
#: A name is admitted here only if it is one of the constants above.
FONT_SCALE: dict[str, float] = {
    "TICK_LABEL": TICK_LABEL,
    "TICK_LABEL_LARGE": TICK_LABEL_LARGE,
    "LEGEND_LABEL": LEGEND_LABEL,
    "LEGEND_TITLE": LEGEND_TITLE,
    "ANNOTATION": ANNOTATION,
    "ANNOTATION_LARGE": ANNOTATION_LARGE,
    "CALLOUT": CALLOUT,
    "AXIS_TITLE": AXIS_TITLE,
    "PANEL_TITLE": PANEL_TITLE,
    "FIGURE_TITLE": FIGURE_TITLE,
}

#: Weight for the two heading roles. The standard asks for bold panel headers; naming
#: it here means a chart module never has to remember to pass ``fontweight``.
HEADING_WEIGHT = "bold"


# ------------------------------------------------------------------
# Stroke weights
# ------------------------------------------------------------------

#: The publisher's stroke floor, in points. A stroke *at* 0.25 pt is not acceptable --
#: the standard requires strokes above it -- so every width below must exceed this,
#: which ``tests/test_style.py`` asserts.
MIN_STROKE_PT = 0.25

#: The stroke ladder. Data lines are the heaviest because they carry the content;
#: spines and major ticks sit a step below so the frame never competes with the data;
#: grid rules, minor ticks, patch edges and hatching are the lightest furniture. The
#: lightest of them is 0.5 pt -- twice the floor -- which leaves head-room for a
#: downscaled figure to still print above 0.25 pt.
LINE_LINEWIDTH = 1.2
AXES_LINEWIDTH = 0.8
TICK_MAJOR_WIDTH = 0.8
TICK_MINOR_WIDTH = 0.6
PATCH_LINEWIDTH = 0.6
HATCH_LINEWIDTH = 0.6
GRID_LINEWIDTH = 0.5


# ------------------------------------------------------------------
# The canvas vocabulary
# ------------------------------------------------------------------

#: matplotlib measures figures in inches; the standards document specifies the canvas
#: in centimetres. The conversion lives here once so no call site restates 2.54.
CM_PER_INCH = 2.54

#: The typographic unit. Font sizes, stroke widths and PostScript bounding boxes are all
#: stated in points while the canvas is stated in inches, so this module -- which owns
#: both vocabularies -- owns the conversion between them, and :mod:`figures` imports it
#: rather than keeping a second copy.
POINTS_PER_INCH = 72.0


def cm_to_inches(centimetres: float) -> float:
    """Convert a length in centimetres to matplotlib's inches.

    Raises ``ValueError`` on a non-positive length: a zero-width canvas is always a
    caller bug, and matplotlib would accept it and emit an empty file.
    """
    if not centimetres > 0:
        raise ValueError(f"a canvas length must be positive, got {centimetres!r} cm")
    return centimetres / CM_PER_INCH


#: Single-column target width (8.9 cm). The width a figure should be drawn at when it
#: is to be read at one column of the printed page.
SINGLE = cm_to_inches(8.9)

#: Double-column target width (17.4 cm), for a figure spanning the text block.
DOUBLE = cm_to_inches(17.4)

#: The maximum printable width (19.05 cm). Not a target -- a ceiling. Every width the
#: growth helpers return is clamped to it.
FULL = cm_to_inches(19.05)

#: The maximum printable height (22.23 cm). The same: a ceiling, never a target.
MAX_HEIGHT = cm_to_inches(22.23)

#: Alias for :data:`FULL` used where the reading is "the cap", not "the widest of the
#: three targets". Bound, never restated, so the two can never disagree.
MAX_WIDTH = FULL


def _clamped_length(
    value: float, *, minimum: float, maximum: float, what: str
) -> float:
    """Clamp *value* into ``[minimum, maximum]``, validating the bounds first.

    Bound validation is not defensive noise: a caller that passes a floor above the
    printable ceiling has asked for a canvas that cannot be printed, and silently
    honouring one of the two bounds would publish it.
    """
    if not minimum > 0:
        raise ValueError(f"{what}: minimum must be positive, got {minimum!r} in")
    if minimum > maximum:
        raise ValueError(
            f"{what}: minimum {minimum!r} in exceeds the printable maximum "
            f"{maximum!r} in; the canvas asked for cannot be printed"
        )
    return min(max(value, minimum), maximum)


def figure_size(width: float, height: float) -> tuple[float, float]:
    """Clamp an explicit ``(width, height)`` in inches to the printable canvas.

    The entry point for a figure whose size is a fixed pair rather than a function of
    a series length. Widths above :data:`FULL` and heights above :data:`MAX_HEIGHT`
    are reduced to the cap; nothing is ever enlarged. A non-positive length raises --
    matplotlib would accept it and write an empty file.
    """
    if not width > 0:
        raise ValueError(f"figure width must be positive, got {width!r} in")
    if not height > 0:
        raise ValueError(f"figure height must be positive, got {height!r} in")
    return (min(width, FULL), min(height, MAX_HEIGHT))


def _grown(
    n_items: float,
    *,
    per_item: float,
    padding: float,
    minimum: float,
    maximum: float,
    what: str,
) -> float:
    """``n_items * per_item + padding``, floored at *minimum*, capped at *maximum*.

    The shape every ad-hoc formula in the layer already had -- ``max(6.0, n * 0.7 +
    2.5)`` and its three dozen siblings -- with the one thing they all lacked: an
    upper bound. ``per_item`` and ``padding`` stay caller arguments because the growth
    *rate* is a property of what is being drawn (a bar row, a heatmap cell, a grouped
    column), which this module must not know; the *caps* are a property of the paper,
    which is exactly what this module does know.

    ``n_items`` is usually a count, but it is admitted as a real number because two of
    the manuscript grids reserve an in-axes margin measured in *fractional* column
    units and then widen the canvas by it. A bool is rejected outright: ``True`` is an
    ``int`` in Python and a boolean reaching a length calculation is always a bug.
    """
    if isinstance(n_items, bool) or not isinstance(n_items, (int, float)):
        raise TypeError(f"{what}: n_items must be a real number, got {n_items!r}")
    if n_items < 0:
        raise ValueError(f"{what}: n_items must not be negative, got {n_items!r}")
    if not per_item > 0:
        raise ValueError(f"{what}: per_item must be positive, got {per_item!r} in")
    if padding < 0:
        raise ValueError(f"{what}: padding must not be negative, got {padding!r} in")
    return _clamped_length(
        n_items * per_item + padding, minimum=minimum, maximum=maximum, what=what
    )


def grow_width(
    n_items: float,
    *,
    per_item: float,
    padding: float,
    minimum: float = SINGLE,
    maximum: float = FULL,
) -> float:
    """Width in inches for a series of *n_items*, clamped to the printable width.

    *minimum* defaults to :data:`SINGLE`: the narrowest canvas the house vocabulary
    offers, and the right floor for a figure whose own layout imposes none.
    """
    return _grown(
        n_items,
        per_item=per_item,
        padding=padding,
        minimum=minimum,
        maximum=min(maximum, FULL),
        what="grow_width",
    )


def grow_height(
    n_items: float,
    *,
    per_item: float,
    padding: float,
    minimum: float = SINGLE,
    maximum: float = MAX_HEIGHT,
) -> float:
    """Height in inches for a series of *n_items*, clamped to the printable height.

    *minimum* defaults to :data:`SINGLE` for the same reason as :func:`grow_width`;
    a figure shorter than the single-column width is a strip, not a panel.
    """
    return _grown(
        n_items,
        per_item=per_item,
        padding=padding,
        minimum=minimum,
        maximum=min(maximum, MAX_HEIGHT),
        what="grow_height",
    )


# ------------------------------------------------------------------
# Fitting text to the canvas
# ------------------------------------------------------------------

#: Narrowest wrap this module will consider, in characters. Below it a caption is a
#: column of single words, which is not a legible fallback but a different defect.
_MIN_WRAP_CHARS = 12


def text_width_inches(text: str, *, fontsize: float, weight: str | None = None) -> float:
    """Width, in inches, of *text* set on one line in the house font at *fontsize*.

    Measured from the font's own glyph advances rather than estimated from a
    characters-per-inch rule of thumb, because the rule of thumb is what put every
    caption in this layer over the printable width: a wrap chosen as "150 characters"
    is 21 cm of Arial at 8 pt, against a 19.05 cm page.

    Renderer-free by construction -- it reads the metrics out of the font file through
    ``TextToPath``, so it needs no figure, no canvas and no draw, and a caller can size
    a string *before* the figure it will sit on exists. Newlines are not handled: pass
    one line.

    Raises:
        ValueError: If *text* contains a newline, which would silently measure the whole
            string as one run and return a width no line actually has.
    """
    if "\n" in text:
        raise ValueError(
            "text_width_inches measures one line; got a string containing a newline. "
            "Split it, or use wrap_to_width, which does."
        )
    from matplotlib.font_manager import FontProperties
    from matplotlib.textpath import TextToPath

    prop = FontProperties(family=house_font(), size=fontsize)
    if weight is not None:
        prop.set_weight(weight)
    width_points, _height, _descent = TextToPath().get_text_width_height_descent(
        text, prop, ismath=False
    )
    return width_points / POINTS_PER_INCH


def wrap_to_width(
    text: str, width_inches: float, *, fontsize: float, weight: str | None = None
) -> str:
    """Wrap *text* so that no line is wider than *width_inches* at *fontsize*.

    The replacement for the character-count wraps the chart modules used to carry
    (``_CAPTION_WRAP = 150``). A character count is a guess about a font: the same 150
    characters are 21 cm of Arial at 8 pt and 14 cm at 5.5 pt, so a wrap tuned by eye on
    one figure silently overflows the page on the next. This takes the constraint that
    actually exists -- the printable width -- and finds the widest wrap that satisfies it.

    The search is over ``textwrap.fill``'s character width, because that is the knob
    ``textwrap`` offers; every candidate is then *measured*, so the result is a fact
    about the font and not about the search. The widest fitting candidate wins, so the
    caption fills the line it is given rather than being conservatively narrow.

    A word longer than *width_inches* cannot be wrapped and would overflow on its own.
    Rather than let it silently bust the page budget, long words are broken -- a broken
    word is visible to a reader and a page over the cap is not. The search bottoms out at
    :data:`_MIN_WRAP_CHARS`, so a target narrower than that many characters of the given
    size returns the narrowest wrap rather than a column of single letters.

    Args:
        text: The string to wrap. Existing newlines are honoured as hard breaks and each
            resulting paragraph is wrapped independently.
        width_inches: The width to fit inside.
        fontsize: The size the text will be set at, from the house scale.
        weight: The weight it will be set at, if not the default.

    Returns:
        The wrapped string, ready to pass to ``ax.text`` / ``fig.text``.

    Raises:
        ValueError: If *width_inches* is not positive -- a caller bug that would
            otherwise loop or return the text unwrapped.
    """
    import textwrap

    if not width_inches > 0:
        raise ValueError(f"width_inches must be positive, got {width_inches!r} in")

    def fits(candidate: str) -> bool:
        return all(
            text_width_inches(line, fontsize=fontsize, weight=weight) <= width_inches
            for line in candidate.splitlines() or [""]
        )

    wrapped_paragraphs: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            wrapped_paragraphs.append(paragraph)
            continue
        if fits(paragraph):
            wrapped_paragraphs.append(paragraph)
            continue
        low, high = _MIN_WRAP_CHARS, max(len(paragraph), _MIN_WRAP_CHARS)
        best = textwrap.fill(paragraph, low, break_long_words=True)
        while low <= high:
            middle = (low + high) // 2
            candidate = textwrap.fill(paragraph, middle, break_long_words=True)
            if fits(candidate):
                best = candidate
                low = middle + 1
            else:
                high = middle - 1
        wrapped_paragraphs.append(best)
    return "\n".join(wrapped_paragraphs)


#: Margin, in inches, between a caption block and the two page edges it sits against.
#: One line of the floor size, so the gap scales with the type rather than being a
#: number chosen against one figure's proportions.
CAPTION_MARGIN_IN = FONT_FLOOR_PT / POINTS_PER_INCH

#: matplotlib's default ``linespacing``. Named because the caption block has to reserve
#: room for text it has not drawn yet, and the reservation must agree with what the draw
#: will actually occupy.
LINE_SPACING = 1.2

#: The most of the canvas a caption block may claim. Beyond this the figure has become a
#: paragraph with a picture on top, which is an authoring problem rather than a layout
#: one -- so it raises here, where it is deterministic and shows up on the first render,
#: instead of quietly squeezing the data into the remaining strip.
MAX_CAPTION_FRACTION = 0.45


class CaptionDoesNotFit(ValueError):
    """A caption block would claim more of the canvas than :data:`MAX_CAPTION_FRACTION`."""


def caption_block(fig, text: str, *, fontsize: float = ANNOTATION, color=None):
    """Draw *text* across the foot of *fig* and reserve the room it needs.

    The replacement for the idiom every chart module used to carry -- a
    ``textwrap.fill(text, 150)`` set with ``ax.text(0.0, -0.15, ..., clip_on=False)``.
    That idiom overflowed the page twice over. It wrapped to a **character count**, which
    is a guess about a font rather than a fact about the page; and it anchored at the
    *axes*' left edge, which is inset from the paper by however wide the tick-label column
    happens to be, so even a correctly-sized caption ran off the right. Because the text
    was unclipped and outside the figure rectangle, ``bbox_inches="tight"`` then grew the
    written canvas to contain it -- silently, past the printable width, at export time.

    This draws in **figure** coordinates, wrapped to the width the paper actually has, and
    reserves the vertical room by shrinking the axes rather than by growing the canvas.
    The figure keeps the size the caller chose from the vocabulary above.

    Call it **after** the drawing is done and **instead of** ``fig.tight_layout()``: it
    performs that call itself, with the caption's own strip held back.

    Args:
        fig: The figure. Its size is treated as fixed -- nothing here resizes it.
        text: The already-composed caption. Newlines are honoured as hard breaks. This
            module neither authors nor inspects it.
        fontsize: The size to set it at, from the house scale.
        color: The colour to set it in, or ``None`` for the ambient text colour. Passed
            through; this module names no colour of its own.

    Returns:
        The ``matplotlib.text.Text`` that was drawn, for a caller that needs to measure
        or adjust it.

    Raises:
        CaptionDoesNotFit: If the wrapped block would claim more than
            :data:`MAX_CAPTION_FRACTION` of the canvas height.
    """
    width_in, height_in = (float(v) for v in fig.get_size_inches())
    available = width_in - 2 * CAPTION_MARGIN_IN
    wrapped = wrap_to_width(text, available, fontsize=fontsize)
    n_lines = wrapped.count("\n") + 1
    block_in = n_lines * fontsize * LINE_SPACING / POINTS_PER_INCH
    reserved_in = block_in + 2 * CAPTION_MARGIN_IN
    if reserved_in > MAX_CAPTION_FRACTION * height_in:
        raise CaptionDoesNotFit(
            f"the caption wraps to {n_lines} line(s), needing {reserved_in:.2f} in of a "
            f"{height_in:.2f} in canvas -- more than the {MAX_CAPTION_FRACTION:.0%} this "
            "layer allows a caption to claim. Shorten it, or move the detail into the "
            "figure legend of the document that publishes it."
        )
    fig.tight_layout(rect=(0.0, reserved_in / height_in, 1.0, 1.0))
    return fig.text(
        CAPTION_MARGIN_IN / width_in,
        CAPTION_MARGIN_IN / height_in,
        wrapped,
        ha="left", va="bottom", fontsize=fontsize, color=color,
        linespacing=LINE_SPACING,
    )


# ------------------------------------------------------------------
# The rcParams block
# ------------------------------------------------------------------

def house_rc_params() -> dict[str, Any]:
    """The full house ``rcParams`` block, ready for ``plt.rc_context``.

    Built rather than stored as a module constant because the font family is
    *resolved against this host* every time -- :func:`house_font` raises here if the
    render machine has none of the stack, which is the one moment at which that
    failure is still cheap.

    **No colour appears in this block.** ``figure.facecolor``, ``axes.edgecolor``,
    ``text.color`` and their siblings are deliberately left at matplotlib's defaults
    rather than named here: colour has one home and it is
    :mod:`population_synthetic.analysis.utils.palette`.

    **On "RGB, 8-bit".** matplotlib has no CMYK path -- its raster backends write
    8-bit RGB(A) and its PostScript backend writes ``DeviceRGB`` -- so the colour
    model is satisfied by construction. What is *not* automatic is the alpha channel:
    ``savefig.transparent`` is pinned off below, because an RGBA figure with a
    transparent ground is not the 8-bit RGB the standard asks for.
    """
    font = house_font()
    return {
        # -- typography -------------------------------------------------
        # The *resolved* family, not the generic "sans-serif" alias. matplotlib resolves
        # a generic alias against ``font.sans-serif`` at **render** time, not when the
        # text is created, so a figure built under this style and saved after it -- which
        # is exactly what a chart function returning an unsaved ``Figure`` does -- would
        # be rendered in whatever the ambient rcParams pointed at, i.e. DejaVu Sans.
        # Naming the concrete family binds it to each text object at creation instead.
        "font.family": [font],
        # Kept in step for anything that asks for the alias explicitly: the resolved
        # family first, then the rest of the stack.
        "font.sans-serif": [font, *(f for f in FONT_STACK if f != font)],
        "font.size": TICK_LABEL,
        "axes.titlesize": PANEL_TITLE,
        "axes.titleweight": HEADING_WEIGHT,
        "axes.labelsize": AXIS_TITLE,
        "xtick.labelsize": TICK_LABEL,
        "ytick.labelsize": TICK_LABEL,
        "legend.fontsize": LEGEND_LABEL,
        "legend.title_fontsize": LEGEND_TITLE,
        "figure.titlesize": FIGURE_TITLE,
        "figure.titleweight": HEADING_WEIGHT,
        "figure.labelsize": AXIS_TITLE,
        # -- stroke weights ---------------------------------------------
        "lines.linewidth": LINE_LINEWIDTH,
        "axes.linewidth": AXES_LINEWIDTH,
        "grid.linewidth": GRID_LINEWIDTH,
        "patch.linewidth": PATCH_LINEWIDTH,
        "hatch.linewidth": HATCH_LINEWIDTH,
        "xtick.major.width": TICK_MAJOR_WIDTH,
        "ytick.major.width": TICK_MAJOR_WIDTH,
        "xtick.minor.width": TICK_MINOR_WIDTH,
        "ytick.minor.width": TICK_MINOR_WIDTH,
        # -- output form -------------------------------------------------
        # 8-bit RGB, not RGBA: see the docstring.
        "savefig.transparent": False,
        # matplotlib's own default is 0.8, so *every* legend in the layer was drawn
        # translucent without a single call site asking for it -- and the PostScript
        # backend flattens it, which is exactly the PNG/SVG-versus-EPS divergence the
        # no-transparency rule exists to remove. Opaque, here, once.
        "legend.framealpha": 1.0,
        # Type 42 (TrueType) rather than Type 3, so the chosen family is *embedded*
        # in vector output instead of being requested from the reader's machine.
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "ps.useafm": False,
    }


# ------------------------------------------------------------------
# Applying it
# ------------------------------------------------------------------

@contextmanager
def apply_house_style():
    """Select the headless backend and install the house ``rcParams`` for one draw.

    The single call site for both pieces of matplotlib global state. The backend is
    selected first -- it must be, before pyplot resolves one -- and the ``rcParams``
    are installed through ``rc_context``, so they are restored when the block exits
    and one figure's appearance can never depend on which figure preceded it.
    """
    import matplotlib

    matplotlib.use(HEADLESS_BACKEND)
    import matplotlib.pyplot as plt

    with plt.rc_context(house_rc_params()):
        yield


_F = TypeVar("_F", bound=Callable[..., Any])


def house_style(func: _F) -> _F:
    """Run *func* inside :func:`apply_house_style`.

    The form the chart modules use: a draw function is decorated once at its
    definition rather than opening a ``with`` block around its whole body, which keeps
    the diff at the ~50 draw sites to one line and makes "this function draws" visible
    in its signature. Nesting is harmless -- ``rc_context`` re-enters cleanly -- so a
    decorated helper called from a decorated caller needs no special handling.
    """
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with apply_house_style():
            return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]
