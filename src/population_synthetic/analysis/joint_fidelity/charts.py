"""charts.py -- Charts for the standalone joint-fidelity process.

Thin orchestration only -- the association heatmap is drawn by the reused
:func:`~population_synthetic.analysis.comparison.charts.plot_association_heatmap`, and the
cross-combo scatter is a self-contained variant of
:func:`~population_synthetic.analysis.performance.charts.plot_c2st_vs_tv` whose axes both
come from the multivariate block (no marginal-TV dependency).

Follows the project charting conventions (deferred ``Agg`` matplotlib import,
``dpi=150``/``bbox_inches="tight"``, ``plt.close`` on every path) and the categorical-colour
rule from the dataviz skill: strategy hues are assigned in a fixed complexity order, never
cycled, so colour follows the strategy entity rather than its rank.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from population_synthetic.analysis.comparison.charts import plot_association_heatmap
from population_synthetic.analysis.utils.axes import STRATEGY_COMPLEXITY_ORDER

_COLOR_SERIES = (
    "#4878CF",
    "#D65F5F",
    "#6AB187",
    "#E8935A",
    "#E9C46A",
    "#8172B2",
    "#64B5CD",
)


def _ordered_strategies(strategies: list[str]) -> list[str]:
    """Strategies in complexity order; any unknown strategy appended (sorted)."""
    ordered = [s for s in STRATEGY_COMPLEXITY_ORDER if s in strategies]
    ordered += sorted(s for s in strategies if s not in STRATEGY_COMPLEXITY_ORDER)
    return ordered


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
    color_for = {s: _COLOR_SERIES[i % len(_COLOR_SERIES)] for i, s in enumerate(strategies)}

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

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8.5, 6.0))
    all_aucs: list[float] = []
    for strategy in strategies:
        pts = by_strategy.get(strategy)
        if not pts:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        all_aucs.extend(xs)
        ax.scatter(
            xs, ys, s=70, color=color_for[strategy], label=strategy,
            edgecolor="white", linewidth=0.6, alpha=0.9, zorder=3,
        )

    ax.axvline(0.5, color="#888888", linestyle="--", linewidth=1.0, zorder=1)
    ax.text(
        0.5, 0.01, "0.5 = indistinguishable joint",
        transform=ax.get_xaxis_transform(), va="bottom", ha="left",
        rotation=90, fontsize=7.5, color="#666666",
    )

    ax.set_xlabel("C2ST ROC-AUC (joint discriminability; 0.5 best)", fontsize=9)
    ax.set_ylabel("mean grounded joint TV (0 best)", fontsize=9)
    lo = min([0.5] + all_aucs) - 0.03
    hi = max([0.5] + all_aucs) + 0.03
    ax.set_xlim(lo, min(1.02, hi))
    ax.set_ylim(bottom=0.0)
    ax.grid(True, linestyle=":", alpha=0.4)
    ax.legend(title="strategy", fontsize=7.5, title_fontsize=8)

    title = "joint discriminability (C2ST) vs grounded joint TV"
    if country:
        title = f"{country}: {title}"
    ax.set_title(title, fontsize=12, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path
