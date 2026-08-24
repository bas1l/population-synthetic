"""charts.py -- pure rendering of :class:`CategoryStat` rows into matplotlib figures.

Publication-styled single-series percent bar charts for the real reference
population: one bar per config category value, y fixed to [0, 100]%, dashed gray
reference lines at 25/50/75/100%, and a percent label on every bar.

Pure sink boundary: this module never touches disk, never knows a file path, never
knows a DPI, and never knows which country/scheme produced the rows -- it only
turns already-computed :class:`CategoryStat` rows into a returned ``Figure``. The
caller (``artifacts.py``) is responsible for saving (via
``analysis/utils/figures.py::save_figure``) and closing.
"""

from __future__ import annotations

import math

from population_synthetic.analysis.real_population_stats.stats import CategoryStat
from population_synthetic.analysis.utils.labels import attribute_label
from population_synthetic.analysis.utils.palette import CATEGORICAL_SERIES, MUTED_GREY, SURFACE
from population_synthetic.analysis.utils.style import (
    ANNOTATION,
    AXIS_TITLE,
    FIGURE_TITLE,
    PANEL_TITLE,
    TICK_LABEL,
    figure_size,
    grow_height,
    grow_width,
    house_style,
    wrap_to_width,
)
from population_synthetic.analysis.utils.table_style import fit_to_page

_BAR_COLOR = CATEGORICAL_SERIES[0]
_REFERENCE_LINES = (25, 50, 75, 100)


#: Cosine of the category labels' rotation. A label rotated by that angle reaches
#: horizontally by its own length times this, which is what a width budget has to be
#: stated against -- not against the length of the string.
_LABEL_ROTATION_DEGREES = 30.0
_LABEL_HORIZONTAL_REACH = math.cos(math.radians(_LABEL_ROTATION_DEGREES))

#: How much of its own panel's width a rotated category label may reach into the margin
#: beside it, in the tiled overview. Half: the labels hang to the LEFT of their ticks, so
#: whatever the leftmost panel's labels claim comes out of the page margin, and the page
#: has no more to give. The most generous value that keeps the panel inside the printable
#: width -- measured, not guessed -- so labels wrap as little as they can.
_LABEL_REACH_FRACTION = 0.5


def _draw_bars(
    ax,
    rows: list[CategoryStat],
    attr: str,
    *,
    title: str | None = None,
    label_reach_in: float | None = None,
) -> None:
    """Render one attribute's bars onto an existing ``Axes`` (shared by both public functions).

    *label_reach_in* bounds how far, in inches, a rotated category label may reach to the
    left of its tick; labels longer than that are wrapped to fit. ``None`` leaves them
    unwrapped, which is right for a single-attribute figure whose canvas grows with the
    number of categories. A tiled panel cannot grow that way -- its panels divide a fixed
    page -- so the leftmost panel's labels run off the paper unless they are bounded, and
    ``tight_layout`` says so ("cannot make Axes width small enough") rather than fixing it.
    """
    categories = [row.value for row in rows]
    if label_reach_in is not None:
        categories = [
            wrap_to_width(
                category, label_reach_in / _LABEL_HORIZONTAL_REACH, fontsize=TICK_LABEL,
            )
            for category in categories
        ]
    percents = [row.percent for row in rows]
    x_pos = range(len(categories))

    for y in _REFERENCE_LINES:
        ax.axhline(y, color=MUTED_GREY, linestyle="--", linewidth=0.6, zorder=0)

    bars = ax.bar(x_pos, percents, color=_BAR_COLOR, edgecolor=SURFACE, linewidth=0.4, zorder=2)
    ax.bar_label(bars, fmt="%.1f%%", fontsize=ANNOTATION, padding=2)

    ax.set_xticks(list(x_pos))
    ax.set_xticklabels(
        categories, rotation=_LABEL_ROTATION_DEGREES, ha="right", fontsize=TICK_LABEL,
    )
    ax.set_ylim(0, 100)
    ax.set_ylabel("Percent", fontsize=AXIS_TITLE)
    # The panel heading is the attribute's display phrase, never its schema key: an
    # explicit *title* from the caller still wins, because only the caller knows when a
    # panel is showing something other than one plain attribute.
    ax.set_title(title or attribute_label(attr), fontsize=PANEL_TITLE, fontweight="bold")
    ax.tick_params(axis="both", labelsize=TICK_LABEL)


@house_style
def plot_category_bars(rows: list[CategoryStat], attr: str, title: str | None = None):
    """Render one attribute's category-proportion bars.

    ``rows`` is the config-ordered :class:`CategoryStat` list from
    ``compute_category_stats`` (an all-null attribute, i.e. every row's
    ``total == 0``, is the caller's cue to skip calling this at all -- it is not
    special-cased here). Returns the ``Figure`` unsaved and open; the caller saves
    (``save_figure``) and it closes there.
    """
    import matplotlib.pyplot as plt

    n_cats = len(rows)
    fig, ax = plt.subplots(figsize=figure_size(grow_width(n_cats, per_item=0.8, padding=2, minimum=6.0), 5))
    _draw_bars(ax, rows, attr, title=title)
    fig.tight_layout()
    return fig


@house_style
def plot_overview_panel(stats_by_attr: dict[str, list[CategoryStat]]):
    """Tile every attribute's bars into one multi-panel overview figure.

    ``stats_by_attr`` maps attribute name -> its :class:`CategoryStat` rows (the
    caller has already excluded all-null attributes). Grid is sized to a near-square
    layout (``ceil(sqrt(n))`` columns); unused grid cells are hidden. Returns the
    ``Figure`` unsaved and open.

    Raises:
        ValueError: if *stats_by_attr* is empty (nothing to tile).
    """
    import matplotlib.pyplot as plt

    attrs = list(stats_by_attr)
    n = len(attrs)
    if n == 0:
        raise ValueError("plot_overview_panel requires at least one attribute's stats (got none)")

    n_cols = math.ceil(math.sqrt(n))
    n_rows = math.ceil(n / n_cols)

    fig, axes = plt.subplots(
        n_rows,
        n_cols,
        figsize=(grow_width(n_cols, per_item=4.5, padding=0.0), grow_height(n_rows, per_item=4.2, padding=0.0)),
    )
    axes_flat = axes.flatten().tolist() if n_rows * n_cols > 1 else [axes]

    # One panel's share of the page is the budget its labels have to live inside.
    label_reach_in = float(fig.get_size_inches()[0]) / n_cols * _LABEL_REACH_FRACTION
    for ax, attr in zip(axes_flat, attrs):
        _draw_bars(ax, stats_by_attr[attr], attr, label_reach_in=label_reach_in)

    for ax in axes_flat[n:]:
        ax.axis("off")

    fig.suptitle("Real Population -- Category Proportions Overview", fontsize=FIGURE_TITLE, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    # The outermost panels' rotated category labels reach past the paper, and the tight
    # bounding box the exporter writes at would grow the page to contain them.
    fit_to_page(fig)
    return fig
