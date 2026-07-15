"""charts.py -- Per-rule violation-rate bar chart for the consistency scan.

Thin, pure sink (per the pipeline's "visualisation never computes" convention): the one
plotter here takes the flat summary rows
:func:`~population_synthetic.analysis.consistency.builder.build_summary_rows` already
produced and draws them; it does not touch a raw population or a rule.

Follows the project charting conventions (deferred ``Agg`` matplotlib import,
``dpi=150``/``bbox_inches="tight"``, ``plt.close`` on every path) and returns
``None`` -- writing nothing -- when there is no data to plot, matching the "skip a
chart only when the underlying data is genuinely empty" rule the other analysis
charts follow.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_COLOR_SERIES = (
    "#4878CF",
    "#D65F5F",
    "#6AB187",
    "#E8935A",
    "#E9C46A",
    "#8172B2",
    "#64B5CD",
)


def plot_violation_rates(
    rows: list[dict[str, Any]],
    out_path: str | Path,
    *,
    country: str | None = None,
) -> Path | None:
    """Grouped bar chart of violation rate per rule, one bar group per population.

    *rows* is :func:`~population_synthetic.analysis.consistency.builder.build_summary_rows`'s
    output (``population, rule_id, severity, violations, rate``). Rules keep their
    first-seen order; populations are ordered alphabetically for a stable legend.
    Rows with a non-finite rate (``NaN``, an empty population) are skipped. Returns
    ``None`` -- writing nothing -- when no row has a plottable rate.
    """
    rule_order: list[str] = []
    for row in rows:
        if row["rule_id"] not in rule_order:
            rule_order.append(row["rule_id"])
    populations = sorted({row["population"] for row in rows})

    rate_by = {(row["population"], row["rule_id"]): row["rate"] for row in rows}
    plottable = any(
        rate_by.get((pop, rule)) is not None and rate_by[(pop, rule)] == rate_by[(pop, rule)]  # not NaN
        for pop in populations
        for rule in rule_order
    )
    if not rule_order or not populations or not plottable:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n_pop = len(populations)
    x = np.arange(len(rule_order))
    width = min(0.8 / n_pop, 0.35)

    fig, ax = plt.subplots(figsize=(max(7.0, 1.6 * len(rule_order)), 5.5))
    for i, population in enumerate(populations):
        heights = [
            rate_by.get((population, rule), float("nan"))
            for rule in rule_order
        ]
        heights = [h if h == h else 0.0 for h in heights]  # NaN -> 0.0 for a drawable bar
        offset = (i - (n_pop - 1) / 2) * width
        ax.bar(
            x + offset, heights, width, label=population,
            color=_COLOR_SERIES[i % len(_COLOR_SERIES)], edgecolor="white", linewidth=0.6,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(rule_order, rotation=20, ha="right", fontsize=8.5)
    ax.set_ylabel("violation rate", fontsize=9)
    ax.set_ylim(bottom=0.0)
    ax.grid(True, axis="y", linestyle=":", alpha=0.4)
    ax.legend(title="population", fontsize=7.5, title_fontsize=8)

    title = "consistency-rule violation rates"
    if country:
        title = f"{country}: {title}"
    ax.set_title(title, fontsize=12, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path
