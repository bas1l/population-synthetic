"""table_style.py -- The shared visual grammar of the manuscript-style grids.

One definition of *how a manuscript grid looks*, so every figure in the family --
the models table, the methods table, and the model x method heatmap that sits
beside them -- matches by construction rather than by copy. Before this module the
grammar lived as private helpers inside ``manuscript_tables.py``; a third renderer
could only reuse it by duplicating it, and a duplicated ramp drifts on the first
restyle, which is precisely the failure these figures exist to avoid.

The module owns the *presentation* decisions and nothing else: the ramp with its
NaN grey, the annotation font size and best-cell box edge, the percentage
colourbar, the best-per-column argmax, the column divider, the top-placed column
labels, and the hosted/local provenance colours and legend text. It takes style
parameters and plain numeric arrays and returns matplotlib primitives.

It deliberately knows nothing about **which metric** is plotted, which country is
being analysed, what the models / strategies / attributes are called, how many
personas a cell rests on, what cap they were drawn against, where files go, or the
shape of the ``result`` dict. Every one of those is a caller concern -- which is
what lets three renderers share this module without inheriting anything from each
other.

The layer-wide colour vocabulary stays in
:mod:`population_synthetic.analysis.utils.palette` (the house ramp, its ``set_bad``
policy, and the luminance-derived text-contrast rule), which every analysis-layer
heatmap shares, not just the manuscript family. This module builds on it rather
than restating it, so there is still exactly one definition of the ramp.

Follows the project charting conventions: no module-level matplotlib import, so
importing this module never pulls in a backend; the callers select ``Agg`` and
matplotlib pieces are imported inside the functions that need them.
"""

from __future__ import annotations

import numpy as np

from population_synthetic.analysis.utils.palette import heatmap_cmap

#: Border drawn around a best-per-column cell. Near-black rather than pure black
#: so it reads as a rule on the bright end of the ramp without vibrating on the
#: dark end.
BOX_EDGE = "#111111"

#: Point size of the in-cell annotations. Sized for a printed table, not a slide.
ANNOT_FONTSIZE = 7.0

#: Colourblind-safe categorical hues for the provenance side-marker (figures) and
#: the LaTeX ``Host`` column swatch. These encode *category* (hosting class), not
#: score, and are deliberately distinct from the sequential score ramp.
HOST_COLORS = {"hosted": "#4878CF", "local": "#E8935A"}
HOST_LABELS = {"hosted": "hosted (API)", "local": "local (Ollama)"}

#: Hosting class assumed for a model absent from ``metadata.model_hosting`` (e.g.
#: the builder default of ``{}`` when hosting was not wired). This is a
#: **presentation** default -- it decides a label colour and nothing else; no
#: computed value is affected. Named here so every renderer in the family falls
#: back to the same class instead of each repeating the literal.
HOST_DEFAULT_CLASS = "hosted"


def inferno_cmap():
    """The house heatmap ramp with a grey ``set_bad`` for NaN cells.

    A one-line pass-through kept as a named function, because the manuscript
    grids' call sites read as "the same ramp every time" and the shared palette
    helper takes arguments these figures never vary.
    """
    return heatmap_cmap()


#: The divider rule's colour and width. White rather than a dark rule: the gap has
#: to read as a *break in the grid* at any point on the ramp, and a dark rule is
#: invisible against the ramp's low end. Named so the two orientations cannot
#: drift apart, and so a renderer that needs a divider never restates the values.
_DIVIDER_COLOR = "white"
_DIVIDER_LINEWIDTH = 2.5


def vertical_divider(ax, n_columns_left: float) -> None:
    """Draw the divider rule after the first *n_columns_left* columns.

    Separates a block of ordinary cells from a block that must not be read as one
    of them (in the two tables, the per-axis columns from the Overall roll-up; in
    the model x method heatmap, the grid from its row marginal).
    """
    ax.axvline(n_columns_left - 0.5, color=_DIVIDER_COLOR, linewidth=_DIVIDER_LINEWIDTH)


def horizontal_divider(ax, n_rows_above: float) -> None:
    """Draw the divider rule below the first *n_rows_above* rows.

    The row-wise twin of :func:`vertical_divider`, for a grid whose marginal sits
    *below* it rather than beside it. *n_rows_above* is a float rather than an int
    because a grid may open a gap between row blocks, which puts its bottom edge
    at a fractional row coordinate.
    """
    ax.axhline(n_rows_above - 0.5, color=_DIVIDER_COLOR, linewidth=_DIVIDER_LINEWIDTH)


def best_cells_per_column(values: np.ndarray) -> set[tuple[int, int]]:
    """Row index of the max finite value in each column (ties -> first row).

    Columns whose cells are all NaN contribute no marker.
    """
    best: set[tuple[int, int]] = set()
    n_rows, n_cols = values.shape
    for j in range(n_cols):
        finite = [(i, values[i, j]) for i in range(n_rows) if not np.isnan(values[i, j])]
        if not finite:
            continue
        # max() returns the first maximal element in iteration (row) order -> ties -> first row.
        best_row = max(finite, key=lambda t: t[1])[0]
        best.add((best_row, j))
    return best


def categories_on_top(ax, labels: list[str]) -> None:
    """Place the column tick labels above the grid, rotated for readability.

    *labels* is the complete, already-ordered column list -- the caller decides
    what the columns are (per-axis names plus an Overall roll-up in the tables,
    method ids in the heatmap), so this function neither appends nor renames
    anything. One tick per label, always.
    """
    ax.xaxis.set_ticks_position("top")
    ax.xaxis.set_label_position("top")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=40, ha="left", fontsize=8)


def add_percentage_colorbar(fig, im, ax, label: str):
    """Attach a colorbar whose tick labels read 0--100 while the mappable stays on 0--1.

    The underlying ``Normalize`` is unchanged (still 0--1); only the tick *labels*
    are scaled to a percentage via a ``FuncFormatter``, and the caller's *label*
    carries the ``(%)`` unit.
    """
    from matplotlib.ticker import FuncFormatter

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _pos: f"{v * 100:.0f}"))
    cbar.set_label(label, fontsize=8)
    return cbar
