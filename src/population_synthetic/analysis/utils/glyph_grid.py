"""glyph_grid.py -- A grid of small drawn glyphs, laid out in points.

Some figures are not heatmaps. A cell that has to show a whole distribution -- eleven score
levels, say -- cannot be one colour, so each cell becomes its own small axes carrying a mini
histogram, and the figure becomes a point-accurate arrangement of such axes plus whatever
furniture sits beside them: a detached reference column, a small ternary triangle per row, a
stepped colourbar. :mod:`~population_synthetic.analysis.utils.grids` cannot draw that picture
(it paints one raster image with one value per cell), and it is not asked to: this module is
its sibling, not its replacement, and it paints no raster image at all -- each cell is its own
small axes.

**The pieces.**

- :class:`PointCanvas` -- a figure of an exact size in points, on which axes, text and a
  legend are placed by point coordinates (origin at the bottom left). A fixed-canvas figure
  (``save_figure(..., fixed_canvas=True)``) is written at exactly this size.
- :func:`draw_mini_histogram` -- bars of width 1 at ``0..n-1`` on a square-root height scale,
  with an optional reference outline drawn over them as a step line.
- :func:`draw_withdrawn_cell` and :func:`draw_empty_cell` -- the two cells that carry no
  distribution: one crossed out, one filled with an optional centred mark.
- :func:`draw_ternary` -- a small triangle placing share triples at their barycentric
  positions, with a reference star and optional corner labels.
- :func:`stepped_colorbar` -- a colourbar of *n* discrete steps of the house ramp.

**Coordinate transforms are not statistics.** Two things here change where a number is drawn
without changing the number: the square-root height scale (``set_yscale("function", ...)``,
the same kind of object as a log axis) and the barycentric map of a share triple onto the
triangle (a fixed 3 x 2 matrix product). Both are invertible and neither aggregates,
normalises or ranks anything. That is the line this module is not allowed to cross: every
height it receives must already be a probability mass that sums to 1, and every share triple
must already sum to 1 -- **both are validated, neither is normalised**, because a renderer
that quietly rescales its input has computed something, and a caller whose input is off has
a bug that should surface here rather than as a plausible figure.

**Displayed text arrives resolved.** Every string this module draws -- a label, a mark, a
legend entry, a colourbar title -- is handed in finished by the caller, which resolves ids
through :mod:`~population_synthetic.analysis.utils.labels`. A string containing an underscore
is rejected with a ``ValueError`` before it can reach a canvas: there is nothing on a tick or
a legend it could be but an unresolved id, and the labelling convention is that an id with no
display label raises rather than printing itself.

**No transparency.** No artist here is given a coverage below 1 -- matplotlib's PostScript
backend flattens it, so an EPS drawn with it diverges from its PNG and SVG siblings. A
de-emphasised colour arrives from the caller already composited
(:func:`~population_synthetic.analysis.utils.palette.opaque`).

**What this module knows nothing about.** Which quantity is drawn, what the rows and columns
are, which model, strategy or country a cell belongs to, whether a combination was withdrawn
or merely unjudged (the caller maps each cell state onto a draw call), what the reference is
called, which bands the ternary corners stand for, or where the figure is saved. It imports
only :mod:`~population_synthetic.analysis.utils.palette` and
:mod:`~population_synthetic.analysis.utils.style` -- nothing from any analysis subpackage,
which is the membership test for the presentation layer, now eight modules with this one.

Follows the layer's charting conventions: no module-level matplotlib import, so importing
this module never pulls in a backend. A figure built here is drawn inside the caller's
``house_style`` and saved by the caller through
:func:`~population_synthetic.analysis.utils.figures.save_figure`.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

from population_synthetic.analysis.utils.palette import (
    BASELINE_DARK,
    FOOTNOTE_GREY,
    GRID_RULE,
    MUTED_GREY,
    SURFACE,
    text_color_for_rgb,
)
from population_synthetic.analysis.utils.style import (
    AXES_LINEWIDTH,
    FONT_CEILING_PT,
    FONT_FLOOR_PT,
    FULL,
    GRID_LINEWIDTH,
    LEGEND_LABEL,
    MAX_HEIGHT,
    PATCH_LINEWIDTH,
    POINTS_PER_INCH,
    TICK_LABEL,
    TICK_MAJOR_WIDTH,
)

__all__ = [
    "COLORBAR_TICK_LENGTH_PT",
    "COLORBAR_TICK_PAD_PT",
    "COLORBAR_TITLE_GAP_PT",
    "FRAME_WIDTH",
    "HISTOGRAM_X_MARGIN",
    "MARKER_EDGE_WIDTH",
    "POINT_SIZE_PT",
    "PointCanvas",
    "REFERENCE_OUTLINE_WIDTH",
    "SHARE_TOLERANCE",
    "STAR_SIZE_PT",
    "TERNARY_APEX_LABEL_GAP_PT",
    "TERNARY_BASE_LABEL_GAP_PT",
    "TERNARY_GUIDE_WIDTH",
    "TERNARY_HEIGHT_RATIO",
    "TERNARY_OUTLINE_WIDTH",
    "TERNARY_VERTICES",
    "WITHDRAWN_STROKE_WIDTH",
    "draw_empty_cell",
    "draw_mini_histogram",
    "draw_ternary",
    "draw_withdrawn_cell",
    "outline_handle",
    "point_handle",
    "reference_star_handle",
    "step_colors",
    "stepped_colorbar",
    "swatch_handle",
    "ternary_position",
    "withdrawn_handle",
]

# ------------------------------------------------------------------
# Named sizes. Every stroke exceeds style.MIN_STROKE_PT (tests/test_glyph_grid.py asserts it).
# ------------------------------------------------------------------

#: How far a probability mass or a share triple may be from summing to 1 before it is
#: rejected. Tight enough that only floating-point round-off passes; a caller whose weights
#: were normalised by the wrong denominator is off by far more.
SHARE_TOLERANCE = 1e-9

#: Width, in points, of the reference outline drawn over a mini histogram. Heavier than the
#: cell frame so the outline reads as data, lighter than a data line so it never hides the
#: bars it is read against.
REFERENCE_OUTLINE_WIDTH = 0.7

#: Width of a glyph cell's frame: the house style's lightest furniture weight.
FRAME_WIDTH = GRID_LINEWIDTH

#: Width of the two diagonals that cross out a withdrawn cell. Furniture weight: the cross
#: says "nothing here by construction", and must not read as data.
WITHDRAWN_STROKE_WIDTH = GRID_LINEWIDTH

#: Space left, in bar widths, between the outermost bar and the cell frame.
HISTOGRAM_X_MARGIN = 0.1

#: Height of an equilateral triangle of side 1. The caller sizes a ternary's axes box as
#: ``side`` wide and ``side * TERNARY_HEIGHT_RATIO`` tall; :func:`draw_ternary` checks it.
TERNARY_HEIGHT_RATIO = math.sqrt(3.0) / 2.0

#: The triangle's corners in its own data coordinates: the first share at the bottom left,
#: the second at the bottom right, the third at the apex. Which bands those are is the
#: caller's; the corner labels say it.
TERNARY_VERTICES = ((0.0, 0.0), (1.0, 0.0), (0.5, TERNARY_HEIGHT_RATIO))

#: Stroke widths of the triangle's outline and of its guide lines.
TERNARY_OUTLINE_WIDTH = PATCH_LINEWIDTH
TERNARY_GUIDE_WIDTH = GRID_LINEWIDTH

#: Marker diameters, in points, of one plotted share triple and of the reference star. A
#: 2.2 pt dot is too small to carry a per-point label, which is why the points are only
#: tinted.
POINT_SIZE_PT = 2.2
STAR_SIZE_PT = 5.0

#: Width of the page-coloured halo around each marker, which keeps overlapping points
#: distinguishable. Just above the publisher's 0.25 pt floor: a stroke *at* the floor is not
#: acceptable, and a heavier halo visibly shrinks a 2.2 pt dot.
MARKER_EDGE_WIDTH = 0.3

#: How much larger a marker is drawn in the legend than on the triangle, so a 2.2 pt dot is
#: still identifiable beside its label.
_LEGEND_MARKER_BOOST_PT = 1.0

#: Marker size of the cross in the withdrawn legend entry.
_WITHDRAWN_MARKER_PT = 4.0

#: Gaps, in points, between a ternary corner and its label: the apex label sits above the
#: apex, the base labels hang below their corners.
TERNARY_APEX_LABEL_GAP_PT = 1.0
TERNARY_BASE_LABEL_GAP_PT = 2.0

#: Tick length, tick-label pad and title gap (above the bar), in points, of the stepped
#: colourbar.
COLORBAR_TICK_LENGTH_PT = 2.0
COLORBAR_TICK_PAD_PT = 1.5
COLORBAR_TITLE_GAP_PT = 2.0

#: Legend spacing, in font-size units (matplotlib's own unit for these keys). Tight, because
#: a point-laid-out figure has no slack for matplotlib's defaults.
_LEGEND_SPACING = {
    "handlelength": 1.4,
    "handleheight": 0.8,
    "columnspacing": 1.0,
    "handletextpad": 0.4,
    "borderaxespad": 0.0,
    "borderpad": 0.0,
}

#: Keyword arguments no call into this module may carry: a coverage (see the module
#: docstring). Font sizes are checked separately, against the house scale.
_FORBIDDEN_KEYWORDS = ("alpha",)


# ------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------

def _check_displayable(text: str, what: str) -> str:
    """Return *text*, or raise when it cannot be a finished display string."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{what} must be a non-empty display string, got {text!r}")
    if "_" in text:
        raise ValueError(
            f"{what} {text!r} contains an underscore, which on a figure can only be an "
            "unresolved id. Resolve it through population_synthetic.analysis.utils.labels "
            "before handing it to the renderer."
        )
    return text


def _check_font_size(fontsize: float, what: str) -> float:
    if not FONT_FLOOR_PT <= fontsize <= FONT_CEILING_PT:
        raise ValueError(
            f"{what}: font size {fontsize!r} pt is outside the house scale "
            f"[{FONT_FLOOR_PT}, {FONT_CEILING_PT}] pt; pass a named size from style.py"
        )
    return fontsize


def _check_keywords(kwargs: dict[str, Any], what: str) -> None:
    for key in _FORBIDDEN_KEYWORDS:
        if key in kwargs:
            raise ValueError(
                f"{what}: {key}= is not accepted. The PostScript backend flattens "
                "transparency; composite the colour with palette.opaque() instead."
            )


def _as_mass(values, what: str) -> np.ndarray:
    """Validate a probability mass: 1-D, non-empty, finite, in [0, 1], summing to 1."""
    mass = np.asarray(values, dtype=float)
    if mass.ndim != 1 or mass.size == 0:
        raise ValueError(f"{what} must be a non-empty 1-D sequence, got shape {mass.shape}")
    if not np.all(np.isfinite(mass)):
        raise ValueError(f"{what} contains a non-finite value: {mass.tolist()}")
    if np.any(mass < 0.0) or np.any(mass > 1.0):
        raise ValueError(f"{what} has a value outside [0, 1]: {mass.tolist()}")
    total = float(mass.sum())
    if abs(total - 1.0) > SHARE_TOLERANCE:
        raise ValueError(
            f"{what} sums to {total!r}, not 1 (tolerance {SHARE_TOLERANCE}). The renderer "
            "draws a finished distribution and does not normalise one."
        )
    return mass


def ternary_position(shares: Sequence[float]) -> tuple[float, float]:
    """The point a share triple occupies on the triangle of :data:`TERNARY_VERTICES`.

    A coordinate transform (a convex combination of the three corners), not a statistic:
    the triple is validated -- three finite, non-negative shares summing to 1 within
    :data:`SHARE_TOLERANCE` -- and never normalised.
    """
    triple = np.asarray(shares, dtype=float)
    if triple.shape != (3,):
        raise ValueError(f"a share triple has exactly three entries, got shape {triple.shape}")
    if not np.all(np.isfinite(triple)) or np.any(triple < 0.0):
        raise ValueError(f"a share triple must be finite and non-negative, got {triple.tolist()}")
    total = float(triple.sum())
    if abs(total - 1.0) > SHARE_TOLERANCE:
        raise ValueError(
            f"share triple {triple.tolist()} sums to {total!r}, not 1 (tolerance "
            f"{SHARE_TOLERANCE}); the renderer does not normalise it"
        )
    x, y = triple @ np.asarray(TERNARY_VERTICES)
    return float(x), float(y)


# ------------------------------------------------------------------
# The canvas
# ------------------------------------------------------------------

class PointCanvas:
    """A figure of exactly ``width_pt`` x ``height_pt``, laid out in points.

    The origin is the bottom-left corner of the canvas. Axes, text and a legend are placed
    by point coordinates and converted to figure fractions here, once, so a caller's layout
    reads as the geometry it specifies rather than as fractions of a size it has to repeat.

    Raises:
        ValueError: If a dimension is not positive, the width exceeds the printable width
            (``style.FULL``) or the height exceeds the printable height
            (``style.MAX_HEIGHT``). The writer would reject such a canvas anyway; raising at
            construction names the layout rather than the file.
    """

    def __init__(self, width_pt: float, height_pt: float):
        import matplotlib.pyplot as plt

        for name, value in (("width", width_pt), ("height", height_pt)):
            if not (isinstance(value, (int, float)) and math.isfinite(value) and value > 0):
                raise ValueError(f"canvas {name} must be a positive number of points, got {value!r}")
        max_width_pt = FULL * POINTS_PER_INCH
        max_height_pt = MAX_HEIGHT * POINTS_PER_INCH
        if width_pt > max_width_pt:
            raise ValueError(
                f"canvas width {width_pt} pt exceeds the printable width {max_width_pt:.2f} pt"
            )
        if height_pt > max_height_pt:
            raise ValueError(
                f"canvas height {height_pt} pt exceeds the printable height {max_height_pt:.2f} pt"
            )
        self.width_pt = float(width_pt)
        self.height_pt = float(height_pt)
        self._figure = plt.figure(
            figsize=(self.width_pt / POINTS_PER_INCH, self.height_pt / POINTS_PER_INCH)
        )

    @property
    def figure(self):
        """The ``matplotlib.figure.Figure`` being laid out."""
        return self._figure

    def _fraction(self, x: float, y: float) -> tuple[float, float]:
        return x / self.width_pt, y / self.height_pt

    def axes(self, x0: float, y0: float, x1: float, y1: float):
        """Add an axes occupying the point box ``[x0, x1] x [y0, y1]``.

        Raises ``ValueError`` when the box is empty or reaches outside the canvas.
        """
        if not (x0 < x1 and y0 < y1):
            raise ValueError(f"an axes box needs x0 < x1 and y0 < y1, got ({x0}, {y0}, {x1}, {y1})")
        if x0 < 0 or y0 < 0 or x1 > self.width_pt or y1 > self.height_pt:
            raise ValueError(
                f"axes box ({x0}, {y0}, {x1}, {y1}) pt reaches outside the "
                f"{self.width_pt} x {self.height_pt} pt canvas"
            )
        left, bottom = self._fraction(x0, y0)
        width, height = self._fraction(x1 - x0, y1 - y0)
        return self._figure.add_axes((left, bottom, width, height))

    def points_box(self, ax) -> tuple[float, float, float, float]:
        """The point box ``(x0, y0, x1, y1)`` an axes on this canvas occupies."""
        left, bottom, width, height = ax.get_position().bounds
        return (
            left * self.width_pt,
            bottom * self.height_pt,
            (left + width) * self.width_pt,
            (bottom + height) * self.height_pt,
        )

    def text(self, x: float, y: float, s: str, *, fontsize: float, **kwargs):
        """Place the display string *s* at point ``(x, y)``.

        *fontsize* is required and must lie on the house scale; *s* must be a finished
        display string (no underscore). Remaining keyword arguments go to
        ``Figure.text`` unchanged, except ``alpha``, which is rejected.
        """
        _check_displayable(s, "canvas text")
        _check_font_size(fontsize, f"canvas text {s!r}")
        _check_keywords(kwargs, f"canvas text {s!r}")
        fx, fy = self._fraction(x, y)
        return self._figure.text(fx, fy, s, fontsize=fontsize, **kwargs)

    def legend(self, handles: Sequence, *, x: float, y_top: float, ncol: int):
        """A frameless legend whose top-left corner sits at point ``(x, y_top)``.

        Every handle's label is checked as a display string. *ncol* is required: how many
        entries share a row is a layout decision the caller makes against its own width.
        """
        if not handles:
            raise ValueError("a legend needs at least one handle")
        for handle in handles:
            _check_displayable(handle.get_label(), "legend entry")
        if isinstance(ncol, bool) or not isinstance(ncol, int) or ncol < 1:
            raise ValueError(f"ncol must be a positive integer, got {ncol!r}")
        fx, fy = self._fraction(x, y_top)
        return self._figure.legend(
            handles=list(handles), loc="upper left", bbox_to_anchor=(fx, fy), ncol=ncol,
            fontsize=LEGEND_LABEL, frameon=False, **_LEGEND_SPACING,
        )


# ------------------------------------------------------------------
# Cells
# ------------------------------------------------------------------

def _bare(ax) -> None:
    """No ticks; a frame in the lightest furniture weight."""
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_linewidth(FRAME_WIDTH)
        spine.set_color(GRID_RULE)


def draw_mini_histogram(ax, heights, colors: Sequence, *, outline=None) -> None:
    """Draw a probability mass as bars of width 1 at ``0..n-1`` on a square-root scale.

    Args:
        ax: A cell axes (see :meth:`PointCanvas.axes`).
        heights: The mass per level. Finite, in ``[0, 1]`` and summing to 1 within
            :data:`SHARE_TOLERANCE` -- validated, never normalised.
        colors: One colour per level, typically :func:`step_colors` of the colourbar's
            ramp so a bar and its colourbar step are the same colour.
        outline: An optional second mass of the same length (the reference), drawn over
            the bars as a post-step line. Validated like *heights*.

    The height axis is square-root scaled over ``[0, 1]`` -- a coordinate transform like a
    log axis, which keeps a small mass visible beside a large one without changing any value.
    """
    mass = _as_mass(heights, "histogram heights")
    n = mass.size
    if len(colors) != n:
        raise ValueError(f"{len(colors)} bar colour(s) for {n} level(s)")
    levels = np.arange(n)
    ax.bar(levels, mass, width=1.0, color=list(colors), edgecolor="none")
    if outline is not None:
        reference = _as_mass(outline, "reference outline")
        if reference.size != n:
            raise ValueError(f"the reference outline has {reference.size} level(s), the bars {n}")
        edges = np.arange(n + 1) - 0.5
        ax.step(
            edges, np.r_[reference, reference[-1]], where="post",
            color=BASELINE_DARK, linewidth=REFERENCE_OUTLINE_WIDTH, zorder=3,
        )
    ax.set_yscale("function", functions=(np.sqrt, np.square))
    ax.set_xlim(-0.5 - HISTOGRAM_X_MARGIN, n - 0.5 + HISTOGRAM_X_MARGIN)
    ax.set_ylim(0.0, 1.0)
    _bare(ax)


def draw_withdrawn_cell(ax) -> None:
    """Cross a cell out: two grey diagonals corner to corner, inside the usual frame."""
    for ys in ((0.0, 1.0), (1.0, 0.0)):
        ax.plot(
            (0.0, 1.0), ys, color=MUTED_GREY, linewidth=WITHDRAWN_STROKE_WIDTH,
            transform=ax.transAxes,
        )
    _bare(ax)


def draw_empty_cell(ax, *, fill, mark: str | None) -> None:
    """Fill a cell with *fill* and, when *mark* is given, centre it in the cell.

    The mark's colour is derived from the fill's luminance, never chosen, so it stays
    legible on whatever fill the caller picks.
    """
    import matplotlib.colors as mcolors

    ax.set_facecolor(fill)
    if mark is not None:
        _check_displayable(mark, "empty-cell mark")
        ax.text(
            0.5, 0.5, mark, transform=ax.transAxes, ha="center", va="center",
            fontsize=TICK_LABEL, color=text_color_for_rgb(mcolors.to_rgb(fill)),
        )
    _bare(ax)


# ------------------------------------------------------------------
# The ternary
# ------------------------------------------------------------------

def _check_equilateral(ax) -> None:
    """Raise unless *ax* is sized ``side x side * TERNARY_HEIGHT_RATIO``: else it distorts."""
    _, _, width, height = ax.get_position().bounds
    fig_w, fig_h = ax.figure.get_size_inches()
    width_pt = width * fig_w * POINTS_PER_INCH
    height_pt = height * fig_h * POINTS_PER_INCH
    expected = width_pt * TERNARY_HEIGHT_RATIO
    if not math.isclose(height_pt, expected, rel_tol=1e-6):
        raise ValueError(
            f"a ternary axes of width {width_pt:.4f} pt must be {expected:.4f} pt tall "
            f"(side x TERNARY_HEIGHT_RATIO), got {height_pt:.4f} pt; the triangle would be "
            "drawn distorted"
        )


def draw_ternary(
    ax,
    points: Sequence[Sequence[float]],
    reference: Sequence[float],
    *,
    point_colors: Sequence,
    apex_guides: Sequence[float],
    apex_label: str | None = None,
    base_labels: tuple[str, str] | None = None,
) -> None:
    """Draw one small ternary triangle with its points, a reference star and labels.

    Args:
        ax: An axes sized ``side`` x ``side * TERNARY_HEIGHT_RATIO`` (checked).
        points: Share triples, one per plotted unit, in the order of
            :data:`TERNARY_VERTICES` (bottom left, bottom right, apex). Each is validated.
        reference: The reference's share triple, drawn as a star above the points.
        point_colors: One colour per point.
        apex_guides: Apex-share values at which a guide line is drawn parallel to the base
            (for instance ``(0.5,)``: the line where half the mass sits at the apex).
            Each lies strictly between 0 and 1. Empty for no guide.
        apex_label: Text above the apex, or ``None``. A figure labels the corners once, so
            the caller passes labels on one row only.
        base_labels: ``(bottom-left, bottom-right)`` texts centred under the base corners,
            or ``None``.
    """
    if len(point_colors) != len(points):
        raise ValueError(f"{len(point_colors)} point colour(s) for {len(points)} point(s)")
    positions = [ternary_position(shares) for shares in points]
    star = ternary_position(reference)
    _check_equilateral(ax)

    vertices = np.asarray(TERNARY_VERTICES)
    closed = np.vstack([vertices, vertices[:1]])
    ax.plot(
        closed[:, 0], closed[:, 1], color=BASELINE_DARK, linewidth=TERNARY_OUTLINE_WIDTH,
        clip_on=False,
    )
    for t in apex_guides:
        if not 0.0 < t < 1.0:
            raise ValueError(f"an apex guide lies strictly between 0 and 1, got {t!r}")
        left = vertices[0] + t * (vertices[2] - vertices[0])
        right = vertices[1] + t * (vertices[2] - vertices[1])
        ax.plot(
            (left[0], right[0]), (left[1], right[1]), color=GRID_RULE,
            linewidth=TERNARY_GUIDE_WIDTH, zorder=0,
        )
    for (x, y), color in zip(positions, point_colors):
        ax.plot(
            x, y, marker="o", markersize=POINT_SIZE_PT, color=color, markeredgecolor=SURFACE,
            markeredgewidth=MARKER_EDGE_WIDTH, linestyle="none", zorder=3, clip_on=False,
        )
    ax.plot(
        *star, marker="*", markersize=STAR_SIZE_PT, color=BASELINE_DARK, markeredgecolor=SURFACE,
        markeredgewidth=MARKER_EDGE_WIDTH, linestyle="none", zorder=4, clip_on=False,
    )
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, TERNARY_HEIGHT_RATIO)
    ax.axis("off")

    label_style = {"fontsize": TICK_LABEL, "color": FOOTNOTE_GREY, "textcoords": "offset points"}
    if apex_label is not None:
        _check_displayable(apex_label, "ternary apex label")
        ax.annotate(
            apex_label, xy=tuple(vertices[2]), xytext=(0.0, TERNARY_APEX_LABEL_GAP_PT),
            ha="center", va="bottom", annotation_clip=False, **label_style,
        )
    if base_labels is not None:
        if len(base_labels) != 2:
            raise ValueError(f"base_labels holds two texts, got {len(base_labels)}")
        for corner, text in zip(vertices[:2], base_labels):
            _check_displayable(text, "ternary base label")
            ax.annotate(
                text, xy=tuple(corner), xytext=(0.0, -TERNARY_BASE_LABEL_GAP_PT),
                ha="center", va="top", annotation_clip=False, **label_style,
            )


# ------------------------------------------------------------------
# The stepped colourbar
# ------------------------------------------------------------------

def step_colors(levels) -> list[str]:
    """The colour of each step of a discrete colormap, as hex strings.

    Pass the same *levels* to :func:`stepped_colorbar` and use this for the bars, and a bar
    and its colourbar step can never disagree.
    """
    import matplotlib.colors as mcolors

    return [mcolors.to_hex(levels(k)) for k in range(levels.N)]


def stepped_colorbar(canvas: PointCanvas, box: tuple[float, float, float, float], levels, n: int, title: str):
    """A colourbar of *n* discrete steps in the point box *box*, titled above.

    Args:
        canvas: The canvas the bar is placed on.
        box: ``(x0, y0, x1, y1)`` in points.
        levels: The discrete colormap, typically ``palette.heatmap_levels(n)``.
        n: The number of steps. Must equal ``levels.N``; step *k* is centred on the value
            *k* and ticked there.
        title: Display string drawn above the bar, anchored at its horizontal centre.

    Returns:
        The ``Colorbar``.
    """
    import matplotlib.colors as mcolors
    from matplotlib.cm import ScalarMappable

    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError(f"a stepped colourbar needs a positive integer step count, got {n!r}")
    if levels.N != n:
        raise ValueError(f"the colormap has {levels.N} step(s) but the colourbar was asked for {n}")
    _check_displayable(title, "colourbar title")
    x0, y0, x1, y1 = box
    cax = canvas.axes(x0, y0, x1, y1)
    mappable = ScalarMappable(cmap=levels, norm=mcolors.BoundaryNorm(np.arange(n + 1) - 0.5, n))
    colorbar = canvas.figure.colorbar(mappable, cax=cax, ticks=range(n))
    colorbar.ax.tick_params(
        labelsize=TICK_LABEL, length=COLORBAR_TICK_LENGTH_PT, width=TICK_MAJOR_WIDTH,
        pad=COLORBAR_TICK_PAD_PT,
    )
    colorbar.outline.set_linewidth(AXES_LINEWIDTH)
    canvas.text(
        (x0 + x1) / 2.0, y1 + COLORBAR_TITLE_GAP_PT, title, fontsize=TICK_LABEL,
        ha="left", va="bottom", color=BASELINE_DARK,
    )
    return colorbar


# ------------------------------------------------------------------
# Legend handles, so the legend draws each glyph exactly as the figure does
# ------------------------------------------------------------------

def outline_handle(label: str):
    """Legend entry for the reference outline."""
    from matplotlib.lines import Line2D

    return Line2D(
        [], [], color=BASELINE_DARK, linewidth=REFERENCE_OUTLINE_WIDTH,
        label=_check_displayable(label, "legend entry"),
    )


def withdrawn_handle(label: str):
    """Legend entry for a crossed-out cell."""
    from matplotlib.lines import Line2D

    return Line2D(
        [], [], marker="x", linestyle="none", color=MUTED_GREY, markersize=_WITHDRAWN_MARKER_PT,
        markeredgewidth=WITHDRAWN_STROKE_WIDTH, label=_check_displayable(label, "legend entry"),
    )


def point_handle(label: str, *, color):
    """Legend entry for one ternary point."""
    from matplotlib.lines import Line2D

    return Line2D(
        [], [], marker="o", linestyle="none", markersize=POINT_SIZE_PT + _LEGEND_MARKER_BOOST_PT,
        color=color, markeredgecolor=SURFACE, markeredgewidth=MARKER_EDGE_WIDTH,
        label=_check_displayable(label, "legend entry"),
    )


def reference_star_handle(label: str):
    """Legend entry for the reference star."""
    from matplotlib.lines import Line2D

    return Line2D(
        [], [], marker="*", linestyle="none", markersize=STAR_SIZE_PT + _LEGEND_MARKER_BOOST_PT,
        color=BASELINE_DARK, markeredgecolor=SURFACE, markeredgewidth=MARKER_EDGE_WIDTH,
        label=_check_displayable(label, "legend entry"),
    )


def swatch_handle(label: str, *, color, edgecolor=None):
    """Legend entry for a filled swatch (a hosting tint, an empty-cell fill).

    *edgecolor* frames a swatch whose fill is the page colour; ``None`` draws no edge.
    """
    from matplotlib.patches import Patch

    return Patch(
        facecolor=color, edgecolor="none" if edgecolor is None else edgecolor,
        linewidth=FRAME_WIDTH, label=_check_displayable(label, "legend entry"),
    )
