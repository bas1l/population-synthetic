"""comparison_charts.py -- Charts for the cross-run scientific comparison.

Consumes the in-memory structure from
:func:`population_synthetic.analysis.llm_metrics.cross_run.run_comparison.build_comparison` and renders, per
metric and per factor (model / method):

* a grouped **box plot** with individual points overlaid, the Kruskal-Wallis
  omnibus result in the title, and significance brackets for significant Dunn
  pairs;
* a mean +/- SD **grouped bar** companion;
* a model x method **heatmap** of the per-cell summary statistic.

Follows the project charting conventions (deferred ``Agg`` matplotlib import,
``dpi=150``/``bbox_inches="tight"``, ``plt.close`` on every path).

Entry point: :func:`plot_run_comparison`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

# ------------------------------------------------------------------
# Chart styling constants
# ------------------------------------------------------------------

_COLOR_BLUE = "#4878CF"
_COLOR_ORANGE = "#E8935A"
_COLOR_RED = "#D65F5F"
_COLOR_GREEN = "#6AB187"
_COLOR_YELLOW = "#E9C46A"

# Cap on the number of significance brackets drawn on a single box plot, to keep
# many-group figures readable.  Omitted pairs are reported (full pairwise results
# remain in the comparison JSON).
_MAX_BRACKETS = 8


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _stars(p: float | None) -> str:
    """Significance asterisks for a p-value."""
    if p is None:
        return "ns"
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return "ns"


def _kruskal_subtitle(kruskal: dict[str, Any]) -> str:
    h = kruskal.get("H")
    p = kruskal.get("p")
    if h is None or p is None:
        note = kruskal.get("note", "not computed")
        return f"Kruskal-Wallis: n/a ({note})"
    return f"Kruskal-Wallis H={h:.2f}, p={p:.3g} (k={kruskal.get('k')}, N={kruskal.get('n')})"


def _figwidth(n_groups: int) -> float:
    return max(7.0, min(22.0, n_groups * 1.1 + 3.0))


# ------------------------------------------------------------------
# Box plot with significance brackets
# ------------------------------------------------------------------

def _plot_box_grouped(
    block: dict[str, Any],
    factor_label: str,
    metric_label: str,
    unit: str,
    out_path: Path,
) -> Path | None:
    """Box plot of *metric* across the groups of one factor, with Dunn brackets."""
    groups: dict[str, list[float]] = block["groups"]
    order = [g for g in block["order"] if groups.get(g)]
    if not order:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path.parent.mkdir(parents=True, exist_ok=True)

    data = [groups[g] for g in order]
    positions = list(range(1, len(order) + 1))
    pos_of = {g: i + 1 for i, g in enumerate(order)}

    fig, ax = plt.subplots(figsize=(_figwidth(len(order)), 6))

    bp = ax.boxplot(
        data,
        positions=positions,
        widths=0.6,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": "black", "linewidth": 1.4},
    )
    for patch in bp["boxes"]:
        patch.set_facecolor(_COLOR_BLUE)
        patch.set_alpha(0.55)
        patch.set_edgecolor("#33486F")

    # Overlay individual observations (jittered) -- N per group is small.
    rng = np.random.default_rng(0)
    for i, g in enumerate(order):
        vals = groups[g]
        jitter = rng.uniform(-0.14, 0.14, size=len(vals))
        ax.scatter(
            np.full(len(vals), i + 1) + jitter, vals,
            s=14, color=_COLOR_ORANGE, alpha=0.7, edgecolor="white", linewidth=0.3, zorder=3,
        )

    ax.set_xticks(positions)
    ax.set_xticklabels(order, rotation=35, ha="right", fontsize=8)
    ylabel = f"{metric_label} ({unit})" if unit else metric_label
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(f"{metric_label} by {factor_label}", fontsize=12, fontweight="bold")
    ax.text(
        0.5, 1.015, _kruskal_subtitle(block["kruskal"]),
        transform=ax.transAxes, ha="center", va="bottom", fontsize=8, color="#444444",
    )
    ax.grid(axis="y", linestyle=":", alpha=0.4)

    # Significance brackets for significant Dunn pairs (within plotted groups).
    sig = [
        d for d in block.get("dunn", [])
        if d.get("p_holm") is not None and d["p_holm"] < 0.05
        and d["a"] in pos_of and d["b"] in pos_of
    ]
    sig.sort(key=lambda d: d["p_holm"])
    omitted = max(0, len(sig) - _MAX_BRACKETS)
    sig = sig[:_MAX_BRACKETS]

    all_vals = [v for vals in data for v in vals]
    if sig and all_vals:
        ymin, ymax = min(all_vals), max(all_vals)
        span = (ymax - ymin) or (abs(ymax) or 1.0)
        step = span * 0.09
        for level, d in enumerate(sig):
            x1, x2 = sorted((pos_of[d["a"]], pos_of[d["b"]]))
            y = ymax + step * (level + 1)
            ax.plot(
                [x1, x1, x2, x2],
                [y - step * 0.25, y, y, y - step * 0.25],
                color="black", linewidth=1.0,
            )
            ax.text((x1 + x2) / 2.0, y, _stars(d["p_holm"]), ha="center", va="bottom", fontsize=9)
        ax.set_ylim(top=ymax + step * (len(sig) + 1.5))

    if omitted:
        ax.text(
            0.99, 0.01, f"+{omitted} more significant pair(s) omitted",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7, color="#888888",
        )
        print(f"  note: {out_path.name}: {omitted} significant pair(s) omitted from brackets")

    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ------------------------------------------------------------------
# Grouped bar with mean +/- SD
# ------------------------------------------------------------------

def _plot_grouped_bar_errorbars(
    block: dict[str, Any],
    factor_label: str,
    metric_label: str,
    unit: str,
    out_path: Path,
) -> Path | None:
    """Mean +/- SD bars per group (companion view to the box plot)."""
    groups: dict[str, list[float]] = block["groups"]
    order = [g for g in block["order"] if groups.get(g)]
    if not order:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path.parent.mkdir(parents=True, exist_ok=True)

    means = [float(np.mean(groups[g])) for g in order]
    stds = [float(np.std(groups[g], ddof=1)) if len(groups[g]) > 1 else 0.0 for g in order]
    positions = list(range(len(order)))

    fig, ax = plt.subplots(figsize=(_figwidth(len(order)), 6))
    ax.bar(
        positions, means, yerr=stds, capsize=4,
        color=_COLOR_GREEN, edgecolor="#33486F", linewidth=0.5, alpha=0.85,
        error_kw={"elinewidth": 1.0, "ecolor": "#444444"},
    )
    ax.set_xticks(positions)
    ax.set_xticklabels(order, rotation=35, ha="right", fontsize=8)
    ylabel = f"{metric_label} ({unit})" if unit else metric_label
    ax.set_ylabel(f"mean {ylabel}", fontsize=9)
    ax.set_title(f"{metric_label} by {factor_label} (mean +/- SD)", fontsize=12, fontweight="bold")
    ax.text(
        0.5, 1.015, _kruskal_subtitle(block["kruskal"]),
        transform=ax.transAxes, ha="center", va="bottom", fontsize=8, color="#444444",
    )
    ax.grid(axis="y", linestyle=":", alpha=0.4)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ------------------------------------------------------------------
# Heatmap (model x method)
# ------------------------------------------------------------------

def _plot_heatmap(
    matrix: dict[str, Any],
    metric_label: str,
    unit: str,
    out_path: Path,
) -> Path | None:
    """Model x method heatmap of the per-cell summary statistic."""
    models = matrix["models"]
    methods = matrix["methods"]
    if not models or not methods:
        return None

    values = np.array(
        [[np.nan if v is None else v for v in row] for row in matrix["values"]],
        dtype=float,
    )
    if np.all(np.isnan(values)):
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(
        figsize=(max(6.0, len(methods) * 1.3 + 3.0), max(5.0, len(models) * 0.5 + 2.5))
    )
    masked = np.ma.masked_invalid(values)
    cmap = plt.get_cmap("viridis").copy()
    cmap.set_bad(color="#DDDDDD")
    im = ax.imshow(masked, aspect="auto", cmap=cmap)

    ax.set_xticks(range(len(methods)))
    ax.set_xticklabels(methods, rotation=35, ha="right", fontsize=8)
    ax.set_yticks(range(len(models)))
    ax.set_yticklabels(models, fontsize=8)

    agg = matrix.get("cell_agg", "value")
    label = f"{agg} {metric_label}" + (f" ({unit})" if unit else "")
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(label, fontsize=8)

    finite = masked.compressed()
    threshold = (finite.max() + finite.min()) / 2.0 if finite.size else 0.0
    for i in range(len(models)):
        for j in range(len(methods)):
            v = values[i, j]
            if np.isnan(v):
                continue
            txt = f"{v:.3g}"
            color = "white" if v < threshold else "black"
            ax.text(j, i, txt, ha="center", va="center", fontsize=7, color=color)

    ax.set_title(f"{metric_label}: model x method", fontsize=12, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def plot_run_comparison(result: dict[str, Any], output_dir: str | Path) -> list[Path]:
    """Render all comparison charts.  Returns the list of written paths."""
    output_dir = Path(output_dir)
    written: list[Path] = []

    for key, entry in result["metrics"].items():
        if entry.get("skipped"):
            print(f"  skip {key}: {entry['skipped']}")
            continue

        metric_label = entry["label"]
        unit = entry["unit"]

        for factor, factor_label in (("by_model", "model"), ("by_method", "method")):
            block = entry.get(factor)
            if block is None:
                continue
            box = _plot_box_grouped(
                block, factor_label, metric_label, unit,
                output_dir / f"{key}_{factor}_box.png",
            )
            if box:
                written.append(box)
            bar = _plot_grouped_bar_errorbars(
                block, factor_label, metric_label, unit,
                output_dir / f"{key}_{factor}_bar.png",
            )
            if bar:
                written.append(bar)

        matrix = entry.get("matrix")
        if matrix:
            heat = _plot_heatmap(matrix, metric_label, unit, output_dir / f"{key}_heatmap.png")
            if heat:
                written.append(heat)

    return written
