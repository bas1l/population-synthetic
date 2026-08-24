"""grids.py -- The one heatmap draw loop the analysis layer's grids share.

Eleven figures across six analysis processes draw the same picture: a matrix of already
computed values on the house sequential ramp, with a per-cell annotation whose colour has
to be legible on whatever the ramp painted underneath it. Each of the eleven used to own
its copy of that loop, so a change to the ramp, to the annotation colour rule or to the
missing-cell treatment had to be made eleven times and was made in fewer.

:func:`render_grid` is that loop, and it is deliberately small. It takes a matrix, one
record per cell, and an annotation policy; it draws the image and the annotations and
returns the ``AxesImage``. Everything a particular grid needs *besides* that -- tick
labels, dividers, best-cell boxes, hatches, marginals, colourbars, captions, legends --
is drawn by the caller, before or after, against the returned mappable. That is what lets
figures as different as a four-state validation grid and a two-sided slope map share this
function without either inheriting the other's furniture.

**The contract is validated, never guessed.** Each policy declares the keys it reads and
this module checks every cell record against that declaration before drawing anything.
The rule is not defensive programming; it is a recorded near-miss. ADR
``2026-08-12-self-contained-typicality-axis.md`` describes a renderer that read
``cell["rate"]`` by literal key, was handed a block whose value key was ``value``, and
painted every cell grey and labelled it unavailable **without raising** -- "a
silent-wrong-output path that produces a plausible figure". A mismatch here raises
:class:`CellRecordMismatch`, naming the policy, the cell, the missing keys and the keys
the record actually carries.

**Two colours are derived, never chosen.** An annotation over a painted cell takes its
colour from what the mappable actually painted there
(:func:`~population_synthetic.analysis.utils.palette.text_color_on`), and an annotation
over an unpainted one takes its colour from the colormap's own ``set_bad``. Neither is a
literal, so a ramp change moves both, and this module needs no colour vocabulary of its
own beyond the two contrast rules it borrows.

**What this module knows nothing about.** Which quantity is drawn, its units, its
direction, whether more is better, what the rows and columns are called, which country or
process produced them, and every caveat that travels with the figure -- all of which are
the caller's, and several of which are read from the data block rather than authored
anywhere in code. It also introduces **no second ramp**: the cmap and the norm arrive
from the caller, and a two-sided quantity is drawn on the house sequential ramp with
symmetric limits and its sign carried in the annotation
(:class:`~population_synthetic.analysis.utils.grid_annotations.SignedValuePolicy`), which
is the mechanism the 2026-08-12 ADR chose over a diverging colormap.

Follows the layer's charting conventions: no module-level matplotlib import, so importing
this module never pulls in a backend.
"""

from __future__ import annotations

from typing import Any, Collection, Mapping, Sequence

import numpy as np

from population_synthetic.analysis.utils.grid_annotations import CellAnnotationPolicy
from population_synthetic.analysis.utils.palette import text_color_for_rgb, text_color_on
from population_synthetic.analysis.utils.style import ANNOTATION

__all__ = [
    "CellRecordMismatch",
    "GridShapeMismatch",
    "TEXT_PATCH_PAD",
    "render_grid",
]


class GridShapeMismatch(ValueError):
    """The cell records do not describe the same grid as the value matrix."""


class CellRecordMismatch(ValueError):
    """A cell record does not carry the keys its annotation policy declared.

    The one failure this module exists to make loud. See the module docstring for the
    recorded case it comes from.
    """


#: Padding, in points, of the patch an annotation is set on when the caller marks a cell
#: as needing one. Named once so the two grids that hatch a cell -- and any that later do
#: -- open the same gap between the number and the marking that qualifies it.
TEXT_PATCH_PAD = 1.4


def _validate_shape(matrix: np.ndarray, cells: Sequence[Sequence[Any]]) -> tuple[int, int]:
    """Return ``(n_rows, n_cols)``, or raise when the two do not describe one grid."""
    if matrix.ndim != 2:
        raise GridShapeMismatch(
            f"render_grid expects a 2-D value matrix; got {matrix.ndim} dimension(s) with "
            f"shape {matrix.shape}."
        )
    n_rows, n_cols = matrix.shape
    if len(cells) != n_rows:
        raise GridShapeMismatch(
            f"cell records describe {len(cells)} row(s) but the value matrix has {n_rows}."
        )
    for index, row in enumerate(cells):
        if len(row) != n_cols:
            raise GridShapeMismatch(
                f"cell-record row {index} describes {len(row)} column(s) but the value "
                f"matrix has {n_cols}."
            )
    return n_rows, n_cols


def _validate_records(
    cells: Sequence[Sequence[Mapping[str, Any] | None]],
    policy: CellAnnotationPolicy,
) -> None:
    """Check every supplied record against *policy*'s declared keys.

    Every record, not merely the first: a block can be uniform in shape for its first row
    and ragged afterwards, and the cell that silently loses its number is exactly the one
    a first-record-only check would skip.
    """
    required = policy.required_keys
    for i, row in enumerate(cells):
        for j, cell in enumerate(row):
            if cell is None:
                continue
            missing = required - set(cell)
            if missing:
                raise CellRecordMismatch(
                    f"{type(policy).__name__} requires the cell keys {sorted(required)}, "
                    f"but the record at row {i}, column {j} is missing {sorted(missing)} "
                    f"(it carries {sorted(cell)}). The policy and the block it is drawing "
                    "disagree about what a cell holds; renaming a key to fit would "
                    "mislabel the number, and reading it leniently would paint a measured "
                    "cell as unmeasured without raising."
                )


def _missing_text_color(cmap) -> str:
    """Annotation colour over a cell the ramp did not paint, from the cmap's ``set_bad``.

    Derived rather than named, so the layer's missing-cell grey has exactly one
    definition. Raises when the colormap's bad colour is transparent: the annotation would
    then sit on the axes background, whose colour this module does not know, and guessing
    black would be unreadable on a dark figure.
    """
    bad = tuple(float(component) for component in cmap.get_bad())
    if len(bad) == 4 and bad[3] == 0.0:
        raise ValueError(
            "the colormap has a fully transparent 'bad' colour, so the colour of an "
            "annotation drawn over an unpainted cell cannot be derived from it. Build the "
            "colormap with population_synthetic.analysis.utils.palette.heatmap_cmap(), "
            "which sets it, or annotate only painted cells."
        )
    return text_color_for_rgb(bad[:3])


def render_grid(
    ax,
    matrix,
    cells: Sequence[Sequence[Mapping[str, Any] | None]],
    *,
    policy: CellAnnotationPolicy,
    cmap,
    norm=None,
    aspect: str | None = None,
    extent: tuple[float, float, float, float] | None = None,
    interpolation: str | None = None,
    row_origin: float = 0.0,
    fontsize: float = ANNOTATION,
    linespacing: float | None = None,
    zorder: float | None = None,
    text_on_fill: Sequence[Sequence[bool]] | None = None,
    bold_cells: Collection[tuple[int, int]] | None = None,
):
    """Draw *matrix* as a heatmap and annotate it through *policy*.

    Args:
        ax: The axes to draw on. Its limits, ticks and furniture are the caller's.
        matrix: The value grid, rows by columns. Non-finite entries are masked, so they
            take the colormap's ``set_bad`` fill rather than a ramp position.
        cells: One record per cell, row-major and the same shape as *matrix*. ``None`` in
            place of a record means "this renderer has nothing to say here" and draws no
            annotation; the caller may draw its own wording over that cell afterwards. A
            record that *is* supplied is validated against ``policy.required_keys``.
        policy: The annotation policy. Decides the text of each cell and nothing else.
        cmap: The colormap. Supplied by the caller so this module names no ramp.
        norm: The normalisation, or ``None`` to let matplotlib autoscale to the data.
        aspect: Passed to ``imshow``; ``None`` uses the ``image.aspect`` rcParam.
        extent: Passed to ``imshow``; ``None`` uses the default cell coordinates.
        interpolation: Passed to ``imshow``; ``None`` uses the rcParam default.
        row_origin: Data ``y`` of the first row's annotations. Non-zero for a grid drawn
            as several stacked blocks, where one call renders each block.
        fontsize: Annotation size, from the house scale.
        linespacing: Annotation line spacing, or ``None`` for the matplotlib default.
        zorder: Annotation z-order, or ``None`` for the matplotlib default. Set it above
            any marking the caller draws over a cell, so a hatch never strikes through
            the number it qualifies.
        text_on_fill: Optional boolean mask, the shape of *matrix*. A true entry sets that
            cell's annotation on a patch of the cell's own fill, which is what keeps a
            hatch or a rule from crossing the text. Plain data: this module does not know
            why a cell needs one.
        bold_cells: Optional ``(row, column)`` pairs whose annotation is emphasised. Plain
            data likewise -- which cells are distinguished, and why, is the caller's.

    Returns:
        The ``matplotlib.image.AxesImage``, for the caller's colourbar and for any
        further colour it needs to derive from what was actually painted.

    Raises:
        GridShapeMismatch: If *cells* does not describe the same grid as *matrix*.
        CellRecordMismatch: If a supplied record lacks a key the policy declared.
        MissingCellValue: If a record's value is ``None`` and the policy declares no
            wording for that case.
    """
    values = np.asarray(matrix, dtype=float)
    n_rows, n_cols = _validate_shape(values, cells)
    _validate_records(cells, policy)
    if text_on_fill is not None:
        _validate_shape(values, text_on_fill)

    im = ax.imshow(
        np.ma.masked_invalid(values),
        cmap=cmap,
        norm=norm,
        aspect=aspect,
        extent=extent,
        interpolation=interpolation,
    )

    bold = set(bold_cells or ())
    missing_color: str | None = None
    for i in range(n_rows):
        for j in range(n_cols):
            cell = cells[i][j]
            if cell is None:
                continue
            text = policy.text(cell)
            if text is None:
                continue
            value = float(values[i, j])
            painted = np.isfinite(value)
            if painted:
                color = text_color_on(im, value)
            else:
                if missing_color is None:
                    missing_color = _missing_text_color(im.cmap)
                color = missing_color
            options: dict[str, Any] = {}
            if linespacing is not None:
                options["linespacing"] = linespacing
            if zorder is not None:
                options["zorder"] = zorder
            if bold and (i, j) in bold:
                options["fontweight"] = "bold"
            if text_on_fill is not None and text_on_fill[i][j]:
                fill = im.cmap(im.norm(value)) if painted else im.cmap.get_bad()
                options["bbox"] = {"facecolor": fill, "edgecolor": "none", "pad": TEXT_PATCH_PAD}
            ax.text(
                j, row_origin + i, text,
                ha="center", va="center", fontsize=fontsize, color=color, **options,
            )
    return im
