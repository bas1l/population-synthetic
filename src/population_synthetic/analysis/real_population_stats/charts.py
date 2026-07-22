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

_BAR_COLOR = "#4878CF"
_REFERENCE_LINES = (25, 50, 75, 100)


def _draw_bars(ax, rows: list[CategoryStat], attr: str, *, title: str | None = None) -> None:
    """Render one attribute's bars onto an existing ``Axes`` (shared by both public functions)."""
    categories = [row.value for row in rows]
    percents = [row.percent for row in rows]
    x_pos = range(len(categories))

    for y in _REFERENCE_LINES:
        ax.axhline(y, color="gray", linestyle="--", linewidth=0.6, alpha=0.6, zorder=0)

    bars = ax.bar(x_pos, percents, color=_BAR_COLOR, edgecolor="white", linewidth=0.4, zorder=2)
    ax.bar_label(bars, fmt="%.1f%%", fontsize=6, padding=2)

    ax.set_xticks(list(x_pos))
    ax.set_xticklabels(categories, rotation=30, ha="right", fontsize=7)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Percent", fontsize=8)
    ax.set_title(title or attr, fontsize=10, fontweight="bold")
    ax.tick_params(axis="both", labelsize=7)


def plot_category_bars(rows: list[CategoryStat], attr: str, title: str | None = None):
    """Render one attribute's category-proportion bars.

    ``rows`` is the config-ordered :class:`CategoryStat` list from
    ``compute_category_stats`` (an all-null attribute, i.e. every row's
    ``total == 0``, is the caller's cue to skip calling this at all -- it is not
    special-cased here). Returns the ``Figure`` unsaved and open; the caller saves
    (``save_figure``) and it closes there.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n_cats = len(rows)
    fig, ax = plt.subplots(figsize=(max(6.0, n_cats * 0.8 + 2), 5))
    _draw_bars(ax, rows, attr, title=title)
    fig.tight_layout()
    return fig


def plot_overview_panel(stats_by_attr: dict[str, list[CategoryStat]]):
    """Tile every attribute's bars into one multi-panel overview figure.

    ``stats_by_attr`` maps attribute name -> its :class:`CategoryStat` rows (the
    caller has already excluded all-null attributes). Grid is sized to a near-square
    layout (``ceil(sqrt(n))`` columns); unused grid cells are hidden. Returns the
    ``Figure`` unsaved and open.

    Raises:
        ValueError: if *stats_by_attr* is empty (nothing to tile).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    attrs = list(stats_by_attr)
    n = len(attrs)
    if n == 0:
        raise ValueError("plot_overview_panel requires at least one attribute's stats (got none)")

    n_cols = math.ceil(math.sqrt(n))
    n_rows = math.ceil(n / n_cols)

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(n_cols * 4.5, n_rows * 4.2))
    axes_flat = axes.flatten().tolist() if n_rows * n_cols > 1 else [axes]

    for ax, attr in zip(axes_flat, attrs):
        _draw_bars(ax, stats_by_attr[attr], attr)

    for ax in axes_flat[n:]:
        ax.axis("off")

    fig.suptitle("Real Population -- Category Proportions Overview", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    return fig
