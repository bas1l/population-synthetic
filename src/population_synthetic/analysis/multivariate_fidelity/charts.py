"""charts.py -- Charts for the standalone joint-fidelity process.

Thin orchestration only -- the association heatmap is drawn by the reused
:func:`~population_synthetic.analysis.fidelity.charts.plot_association_heatmap`, and the
cross-combo scatter is a self-contained variant of
:func:`~population_synthetic.analysis.model_ranking.charts.plot_c2st_vs_tv` whose axes both
come from the multivariate block (no marginal-TV dependency).

Follows the project charting conventions (deferred ``Agg`` matplotlib import,
persistence delegated to ``analysis/utils/figures.py::save_figure``, which writes
the PNG+SVG+EPS trio and closes the figure) and the categorical-colour
rule from the dataviz skill: strategy hues are assigned in a fixed complexity order, never
cycled, so colour follows the strategy entity rather than its rank.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from population_synthetic.analysis.fidelity.charts import plot_association_heatmap
from population_synthetic.analysis.utils.axes import strategy_complexity_order
from population_synthetic.analysis.utils.figures import save_figure
from population_synthetic.analysis.utils.labels import (
    country_label,
    method_key_lines,
    method_letters,
)
from population_synthetic.analysis.utils.palette import (
    CATEGORICAL_SERIES,
    GRID_RULE,
    MUTED_GREY,
    SECONDARY_GREY,
    SURFACE,
)
from population_synthetic.analysis.utils.style import (
    ANNOTATION,
    AXIS_TITLE,
    FIGURE_TITLE,
    FULL,
    LEGEND_LABEL,
    LEGEND_TITLE,
    figure_size,
    house_style,
)


def _ordered_strategies(strategies: list[str]) -> list[str]:
    """Strategies in config-derived complexity order (raises on an unknown id)."""
    return strategy_complexity_order(strategies)


def plot_joint_association_heatmap(
    envelope: dict[str, Any],
    output_dir: str | Path,
    *,
    prefix: str | None = None,
    attributes: list[str] | None = None,
) -> Path | None:
    """Draw one combo's pairwise ``|Delta V|`` heatmap via the reused comparison chart.

    The envelope already wraps the block under the ``multivariate`` key, so it is passed
    straight through to :func:`plot_association_heatmap` (which reads
    ``report["multivariate"]["association"]["pairs"]``).
    """
    return plot_association_heatmap(
        envelope, Path(output_dir), prefix=prefix, attributes=attributes
    )


@house_style
def plot_c2st_vs_grounded_tv(
    rows: list[dict[str, Any]],
    out_path: str | Path,
    *,
    country: str | None = None,
) -> Path | None:
    """Scatter of C2ST ROC-AUC vs mean grounded joint TV across combos, coloured by strategy.

    Both axes come from the multivariate block only: x = C2ST AUC (0.5 = indistinguishable
    joint, higher = more separable = worse) and y = mean joint TV over the grounded pairs
    (0 = perfect grounded-joint match, higher = worse). Colour encodes strategy in complexity
    order (identity, fixed order -- never cycled), so the reader can see whether the strategy
    that produces the least-separable joint also matches the grounded joints best.

    Combos lacking a finite value on either axis (degenerate synthetic populations, or a combo
    with no grounded pair) are skipped. Returns ``None`` when no combo has a plottable point.
    """
    strategies = _ordered_strategies(sorted({r["strategy"] for r in rows if r["strategy"]}))
    color_for = {s: CATEGORICAL_SERIES[i % len(CATEGORICAL_SERIES)] for i, s in enumerate(strategies)}
    # The legend entry is the method key line itself -- "A -- All Pick" -- so this figure
    # needs no separate key block. `method_letters` and `method_key_lines` are both
    # returned in complexity order, which is what makes the zip aligned.
    key_line = dict(zip(method_letters(strategies), method_key_lines(strategies)))

    by_strategy: dict[str, list[tuple[float, float, str]]] = {}
    for row in rows:
        strategy = row["strategy"]
        auc = row["c2st_auc"]
        tv = row["mean_grounded_joint_tv"]
        if not strategy or auc is None or tv is None or auc != auc or tv != tv:  # None or NaN
            continue
        by_strategy.setdefault(strategy, []).append((float(auc), float(tv), row["model"]))
    if not by_strategy:
        return None

    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=figure_size(FULL, 6.0))
    all_aucs: list[float] = []
    for strategy in strategies:
        pts = by_strategy.get(strategy)
        if not pts:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        all_aucs.extend(xs)
        ax.scatter(
            xs, ys, s=70, color=color_for[strategy], label=key_line[strategy],
            edgecolor=SURFACE, linewidth=0.6, zorder=3,
        )

    ax.axvline(0.5, color=MUTED_GREY, linestyle="--", linewidth=1.0, zorder=1)
    ax.text(
        0.5, 0.01, "0.5 = indistinguishable joint",
        transform=ax.get_xaxis_transform(), va="bottom", ha="left",
        rotation=90, fontsize=ANNOTATION, color=SECONDARY_GREY,
    )

    ax.set_xlabel("C2ST ROC-AUC (joint discriminability; 0.5 best)", fontsize=AXIS_TITLE)
    ax.set_ylabel("mean grounded joint TV (0 best)", fontsize=AXIS_TITLE)
    lo = min([0.5] + all_aucs) - 0.03
    hi = max([0.5] + all_aucs) + 0.03
    ax.set_xlim(lo, min(1.02, hi))
    ax.set_ylim(bottom=0.0)
    ax.grid(True, linestyle=":", color=GRID_RULE)
    ax.legend(title="generation method", fontsize=LEGEND_LABEL, title_fontsize=LEGEND_TITLE)

    title = "joint discriminability (C2ST) vs grounded joint TV"
    if country:
        title = f"{country_label(country)}: {title}"
    ax.set_title(title, fontsize=FIGURE_TITLE, fontweight="bold")
    fig.tight_layout()
    return save_figure(fig, out_path)
