"""charts.py -- Per-rule violation-rate bar chart for the consistency scan.

Thin, pure sink (per the pipeline's "visualisation never computes" convention): the one
plotter here takes the flat summary rows
:func:`~population_synthetic.analysis.consistency.builder.build_summary_rows` already
produced and draws them; it does not touch a raw population or a rule.

Follows the project charting conventions (deferred ``Agg`` matplotlib import,
persistence delegated to ``analysis/utils/figures.py::save_figure``, which writes
the PNG+SVG+EPS trio and closes the figure) and returns
``None`` -- writing nothing -- when there is no data to plot, matching the "skip a
chart only when the underlying data is genuinely empty" rule the other analysis
charts follow.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from population_synthetic.analysis.utils.figures import save_figure
from population_synthetic.analysis.utils.labels import country_label, population_label
from population_synthetic.analysis.utils.palette import CATEGORICAL_SERIES, GRID_RULE, SURFACE
from population_synthetic.analysis.utils.style import (
    AXIS_TITLE,
    FIGURE_TITLE,
    LEGEND_LABEL,
    LEGEND_TITLE,
    TICK_LABEL,
    figure_size,
    grow_width,
    house_style,
)


@house_style
def plot_violation_rates(
    rows: list[dict[str, Any]],
    out_path: str | Path,
    *,
    country: str | None = None,
) -> Path | None:
    """Grouped bar chart of violation rate per rule, one bar group per population.

    *rows* is :func:`~population_synthetic.analysis.consistency.builder.build_summary_rows`'s
    output (``population, rule_id, rule_label, severity, violations, rate``). Rules keep
    their first-seen order; populations are ordered alphabetically by *id*, so the legend
    is stable under a relabelling. Rows with a non-finite rate (``NaN``, an empty
    population) are skipped. Returns ``None`` -- writing nothing -- when no row has a
    plottable rate.

    Nothing an id names is printed. A rule ticks as the ``rule_label`` its config
    declares, which travels on the row; a population legends as its axis config's
    display name, resolved here because a *population* id is axis config rather than
    this process's own. Both raise on a miss rather than printing the id.
    """
    rule_order: list[str] = []
    for row in rows:
        if row["rule_id"] not in rule_order:
            rule_order.append(row["rule_id"])
    rule_ticks = {row["rule_id"]: row["rule_label"] for row in rows}
    populations = sorted({row["population"] for row in rows})
    legend_labels = {population: population_label(population) for population in populations}

    rate_by = {(row["population"], row["rule_id"]): row["rate"] for row in rows}
    plottable = any(
        rate_by.get((pop, rule)) is not None and rate_by[(pop, rule)] == rate_by[(pop, rule)]  # not NaN
        for pop in populations
        for rule in rule_order
    )
    if not rule_order or not populations or not plottable:
        return None

    import matplotlib.pyplot as plt
    import numpy as np

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n_pop = len(populations)
    x = np.arange(len(rule_order))
    width = min(0.8 / n_pop, 0.35)

    fig, ax = plt.subplots(
        figsize=figure_size(grow_width(len(rule_order), per_item=1.6, padding=0.0, minimum=7.0), 5.5),
    )
    for i, population in enumerate(populations):
        heights = [
            rate_by.get((population, rule), float("nan"))
            for rule in rule_order
        ]
        heights = [h if h == h else 0.0 for h in heights]  # NaN -> 0.0 for a drawable bar
        offset = (i - (n_pop - 1) / 2) * width
        ax.bar(
            x + offset, heights, width, label=legend_labels[population],
            color=CATEGORICAL_SERIES[i % len(CATEGORICAL_SERIES)], edgecolor=SURFACE, linewidth=0.6,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(
        [rule_ticks[rule] for rule in rule_order], rotation=20, ha="right", fontsize=TICK_LABEL
    )
    ax.set_ylabel("Violation rate", fontsize=AXIS_TITLE)
    ax.set_ylim(bottom=0.0)
    ax.grid(True, axis="y", linestyle=":", color=GRID_RULE)
    ax.legend(title="Population", fontsize=LEGEND_LABEL, title_fontsize=LEGEND_TITLE)

    title = "Consistency-rule violation rates"
    if country:
        title = f"{country_label(country)}: {title}"
    ax.set_title(title, fontsize=FIGURE_TITLE, fontweight="bold")
    fig.tight_layout()
    return save_figure(fig, out_path)
