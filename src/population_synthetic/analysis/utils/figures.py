"""figures.py -- Writing a finished figure to disk, in every format the paper needs.

One home for the multi-format save idiom, so a chart module never spells out which
formats a figure is written in, at what resolution, or against which size budget.
Callers only ever hand over a finished ``Figure`` and a target PNG path.

**What it owns.** The export policy: the format set (PNG, SVG and EPS), the raster
resolution, ``bbox_inches``, the figure lifecycle, the save-time ``rcParams`` that
decide how vector text is encoded, and the two budgets the standards document
imposes on anything written -- the printable canvas and the file-size ceiling.

**What it knows nothing about.** What the figure shows or how it was drawn. It sees
a ``Figure`` and a path; it reads no data, resolves no output directory, names no
colour, and sets no font size. It does not even know which of the ~15 chart modules
produced the figure it is writing.

**Why one function and not one per format.** Recorded in
``plans/completed/fidelity-radar-svg-export.md``: the alternative -- a second
``savefig`` line at each call site, or a second writer module -- was rejected because
the format set then drifts between call sites, and half the layer emitting vector
while the other half emits raster is exactly the state this module exists to end.
Extending this function is therefore the only sanctioned way to add a format.

**Why EPS.** Of the four target venues, EPS is the only format all four accept: PDF
fails PLOS, TIFF fails TMLR, PNG fails PLOS. The SVG sibling stays because it is the
format a figure is *edited* in, and the PNG because it is the one a draft is *read*
in; only the EPS is the submission artifact.

**On budgets: nothing partial is ever left on disk.** Every format is rendered to
memory, the budgets are checked against those bytes, and only then is anything
written. A figure that breaks a budget raises :class:`FigureBudgetExceeded` with
nothing written at all, rather than publishing an unusable file or -- worse --
silently shrinking a canvas the author sized deliberately.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

from population_synthetic.analysis.utils import style

# ------------------------------------------------------------------
# The export vocabulary
# ------------------------------------------------------------------

#: The raster resolution of every PNG this layer writes, and the single source of
#: truth for it: the ``--dpi`` flags on the analysis drivers default to this value
#: rather than restating a literal, and no chart module names a resolution at all.
#: It replaces the three regimes that preceded it -- 150 hardcoded at ~28 call sites,
#: a private ``_DPI = 150`` in one chart module and 200 from five CLI defaults -- under
#: which the same figure family exported at a different resolution depending on which
#: process drew it.
#:
#: 300 dpi is the publication raster floor for combination line-and-tone art, and
#: unifies *upwards*: no figure loses resolution against any of the three regimes it
#: replaces. The standards document's 600 dpi applies "only where raster content is
#: unavoidable", and this layer has no such content -- every figure is line art whose
#: submission artifact is the vector EPS, leaving the PNG a working sibling.
RASTER_DPI = 300

#: The raster format, named once: it is the format of the path callers pass, and the
#: one whose path is therefore used verbatim rather than derived.
RASTER_SUFFIX = ".png"

#: The vector siblings, derived from the raster path's stem. EPS is the submission
#: format and SVG the editable one. A caller cannot ask for a subset: a figure emitted
#: in fewer formats than its siblings is the drift this module exists to prevent.
VECTOR_SUFFIXES = (".svg", ".eps")

#: Every format a figure is written in.
OUTPUT_SUFFIXES = (RASTER_SUFFIX, *VECTOR_SUFFIXES)

#: The ``rcParams`` that are read by the backend at **write** time rather than at draw
#: time, so they must be installed here even when the figure was drawn outside
#: :func:`~population_synthetic.analysis.utils.style.apply_house_style` -- which is what
#: every chart module that *returns* an unsaved ``Figure`` for its driver to save does.
#: Left unset, matplotlib's default ``ps.fonttype = 3`` writes vector text as Type 3
#: charprocs instead of embedding the chosen TrueType face.
#:
#: The values are taken from the house style rather than restated, so the two can never
#: disagree; a key disappearing from the style block raises here rather than silently
#: reverting to a matplotlib default.
EXPORT_RC_KEYS = ("ps.fonttype", "pdf.fonttype", "ps.useafm", "savefig.transparent")

#: The file-size ceiling the standards document imposes, in bytes. Applied to every
#: written format, not only the EPS: a PNG over the ceiling is equally unsubmittable.
MAX_FILE_BYTES = 10 * 1024 * 1024

#: PostScript's unit. An EPS bounding box is stated in points; the canvas budget is
#: stated in inches (:mod:`style`), and this is the only conversion between them.
POINTS_PER_INCH = 72.0

#: Whitespace added outside the tight bounding box, in inches. **Zero, deliberately.**
#: matplotlib's default of 0.1 in is added on each side, so a written file is 0.2 in
#: wider and taller than the content it crops to -- which means a figure drawn exactly
#: at the printable cap is written 0.5 cm over it, and the size vocabulary in
#: :mod:`style` becomes unreachable by construction rather than by anything the author
#: did. At zero, the written canvas is the content extent, so it can exceed the cap
#: only when an artist genuinely overflows the figure rectangle -- which is the case
#: the budget check exists to catch. Journals set their own margins around a figure;
#: shipping whitespace inside the file only spends the page budget on nothing.
PAD_INCHES = 0.0

#: Slack allowed when comparing a measured canvas against the printable cap, in inches.
#: Float noise only -- a genuine overshoot in this layer is measured in whole
#: centimetres, never in millionths of an inch.
CANVAS_EPSILON_IN = 1e-6

_HIRES_BBOX_RE = re.compile(
    rb"^%%HiResBoundingBox:\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$", re.MULTILINE
)
_BBOX_RE = re.compile(
    rb"^%%BoundingBox:\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$", re.MULTILINE
)


class FigureBudgetExceeded(RuntimeError):
    """Raised when a rendered figure breaks a budget from the standards document.

    Either the canvas is larger than the printable page area
    (:data:`style.MAX_WIDTH` x :data:`style.MAX_HEIGHT`) or one of the written
    formats is larger than :data:`MAX_FILE_BYTES`. Both are hard limits at the
    target venues, so this fails the run: silently shrinking the canvas would
    change a figure the author sized deliberately, and writing the file anyway
    would publish one that is rejected at submission.
    """


class EPSBoundingBoxMissing(RuntimeError):
    """Raised when a rendered EPS carries no parsable ``%%BoundingBox`` comment.

    The bounding box is how the canvas budget is measured, so an EPS without one
    cannot be checked. Treated as a failure rather than as permission to skip the
    check -- an unmeasurable figure is not a compliant figure.
    """


def _export_rc_params() -> dict[str, Any]:
    """The save-time ``rcParams`` block, taken from the house style.

    Raises ``KeyError`` naming the key if the style block stops carrying one of
    :data:`EXPORT_RC_KEYS`, rather than falling back to matplotlib's default -- the
    default is precisely the non-compliant value this block exists to override.
    """
    house = style.house_rc_params()
    missing = [key for key in EXPORT_RC_KEYS if key not in house]
    if missing:
        raise KeyError(
            f"the house style no longer defines {', '.join(missing)}; export cannot "
            "fall back to matplotlib's defaults for these, since those defaults are "
            "what they exist to override"
        )
    return {key: house[key] for key in EXPORT_RC_KEYS}


def _output_paths(png_path: Path) -> dict[str, Path]:
    """The path of every emitted format, keyed by suffix.

    The raster path is used exactly as the caller gave it -- callers have always
    owned the filename -- and the vector siblings replace its suffix, so the trio
    shares one stem and one directory.
    """
    paths = {RASTER_SUFFIX: png_path}
    paths.update({suffix: png_path.with_suffix(suffix) for suffix in VECTOR_SUFFIXES})
    return paths


def _render(fig, suffix: str, *, dpi: int) -> bytes:
    """Render *fig* to one format in memory, returning its bytes."""
    buffer = io.BytesIO()
    fig.savefig(
        buffer,
        format=suffix.lstrip("."),
        dpi=dpi,
        bbox_inches="tight",
        pad_inches=PAD_INCHES,
    )
    return buffer.getvalue()


def _canvas_inches(eps_bytes: bytes) -> tuple[float, float]:
    """The written canvas of an EPS, in inches, from its bounding-box comment.

    Measured from the *rendered* file rather than from ``fig.get_size_inches()``,
    because ``bbox_inches="tight"`` is what decides the written extent: it trims
    unused margin, and it grows past the figure rectangle for any artist placed
    outside it (an outside legend, a suptitle). The figure's nominal size is
    therefore not the size the printer receives, and the budget applies to the
    latter.

    Prefers ``%%HiResBoundingBox`` (floating-point) over ``%%BoundingBox`` (integral
    points, rounded outwards), so the measurement is the renderer's own number.
    """
    match = _HIRES_BBOX_RE.search(eps_bytes) or _BBOX_RE.search(eps_bytes)
    if match is None:
        raise EPSBoundingBoxMissing(
            "the rendered EPS carries neither a %%HiResBoundingBox nor a "
            "%%BoundingBox comment, so its canvas cannot be measured against the "
            "printable page area"
        )
    x0, y0, x1, y1 = (float(value) for value in match.groups())
    return ((x1 - x0) / POINTS_PER_INCH, (y1 - y0) / POINTS_PER_INCH)


def _check_canvas(width_in: float, height_in: float, png_path: Path) -> None:
    """Raise unless the written canvas fits the printable page area."""
    over_width = width_in > style.MAX_WIDTH + CANVAS_EPSILON_IN
    over_height = height_in > style.MAX_HEIGHT + CANVAS_EPSILON_IN
    if not (over_width or over_height):
        return
    to_cm = style.CM_PER_INCH
    raise FigureBudgetExceeded(
        f"{png_path.name}: the rendered canvas is "
        f"{width_in * to_cm:.2f} x {height_in * to_cm:.2f} cm, which exceeds the "
        f"printable page area of {style.MAX_WIDTH * to_cm:.2f} x "
        f"{style.MAX_HEIGHT * to_cm:.2f} cm "
        f"({'width' if over_width else ''}"
        f"{' and ' if over_width and over_height else ''}"
        f"{'height' if over_height else ''} over). Note that the measured extent is "
        "the tight bounding box, which grows past the figure rectangle for any "
        "artist drawn outside it. Reduce the figure through the size vocabulary in "
        "analysis/utils/style.py -- the canvas is not clamped here, because a "
        "silently shrunk figure is a different figure from the one that was drawn."
    )


def _check_file_size(payload: bytes, path: Path) -> None:
    """Raise unless one rendered format fits the file-size ceiling."""
    if len(payload) <= MAX_FILE_BYTES:
        return
    mib = 1024 * 1024
    raise FigureBudgetExceeded(
        f"{path.name}: the rendered file is {len(payload) / mib:.2f} MiB, which "
        f"exceeds the {MAX_FILE_BYTES / mib:.0f} MiB ceiling. Reduce the raster "
        "resolution or the number of drawn elements; nothing was written."
    )


def save_figure(fig, png_path: Path, *, dpi: int = RASTER_DPI) -> Path:
    """Write *fig* as a PNG, SVG and EPS trio (same stem/dir) and close it.

    Renders all three formats to memory with ``bbox_inches="tight"`` and
    :data:`PAD_INCHES` of margin, checks both
    budgets against the rendered bytes, then writes ``png_path`` and its ``.svg``
    and ``.eps`` siblings, creating the parent directory if needed. *dpi* applies to
    the PNG and to any rasterised artist inside the two vector formats; it defaults
    to :data:`RASTER_DPI` and callers override it only to render a test figure
    cheaply.

    Closes *fig* on every path, including the failing one, and returns the PNG path
    -- the pre-existing caller contract of every chart function that routes here.

    Raises :class:`FigureBudgetExceeded` if the rendered canvas exceeds the
    printable page area or any rendered format exceeds :data:`MAX_FILE_BYTES`, in
    which case **no file is written**.
    """
    import matplotlib.pyplot as plt

    png_path = Path(png_path)
    paths = _output_paths(png_path)
    try:
        with plt.rc_context(_export_rc_params()):
            rendered = {
                suffix: _render(fig, suffix, dpi=dpi) for suffix in OUTPUT_SUFFIXES
            }
        width_in, height_in = _canvas_inches(rendered[".eps"])
        _check_canvas(width_in, height_in, png_path)
        for suffix, payload in rendered.items():
            _check_file_size(payload, paths[suffix])
        png_path.parent.mkdir(parents=True, exist_ok=True)
        for suffix, payload in rendered.items():
            paths[suffix].write_bytes(payload)
    finally:
        plt.close(fig)
    return png_path
