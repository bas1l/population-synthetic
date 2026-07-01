"""
charts.py -- Visualization tools for demographic population comparisons.

Provides bar-chart comparisons per attribute and a radar (spider) chart
summarizing per-dimension TV similarity and chi-squared p-values.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from population_synthetic.analysis.comparison.evaluator import attr_value

# ------------------------------------------------------------------
# Chart styling constants
# ------------------------------------------------------------------

_HIGH_CARDINALITY_FIELDS = frozenset({
    "region",
    "industry_sector",
    "employment_type",
    "housing_tenure",
    "birth_country_detail",
})

_ATTR_COLORS = (
    "#4878CF",
    "#D65F5F",
)

_ATTR_COLORS_3WAY = (
    "#4878CF",  # blue  (Sweden)
    "#D65F5F",  # red   (Norway)
    "#6AB187",  # green (Italy)
)

_RADAR_TV_COLOR = "#2A9D8F"
_RADAR_CHI_COLOR = "#E9C46A"

_RADAR_3WAY_COLORS = ("#4878CF", "#D65F5F", "#6AB187")
_RADAR_3WAY_STYLES = ("solid", "dashed", "dotted")


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _compute_proportions(individuals: list[dict], attr: str) -> dict[str, float]:
    counts: Counter = Counter()
    for ind in individuals:
        val = attr_value(ind, attr)
        if val is not None:
            counts[val] += 1
    total = sum(counts.values())
    if total == 0:
        return {}
    return {k: v / total for k, v in counts.items()}


def _close_polygon(values: list[float]) -> list[float]:
    return values + values[:1]


# ------------------------------------------------------------------
# Bar-chart comparison
# ------------------------------------------------------------------

def plot_comparison_charts(
    pop_a_data: dict,
    pop_b_data: dict,
    output_dir: Path,
    pop_a_label: str = "Population A",
    pop_b_label: str = "Population B",
    *,
    prefix: str | None = None,
    attributes: list[str],
    categories: dict[str, list[str]] | None = None,
) -> None:
    """Generate side-by-side bar charts for each demographic attribute.

    *attributes* (required) is the comparison axis from a per-country
    ``ComparisonScheme`` -- the charted attributes come from config, never an
    in-code default. When *categories* is supplied each attribute uses the
    scheme's DB-grounded category set so no synthetic-only bar appears with a
    zero reference; otherwise categories fall back to the observed union.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    individuals_a: list[dict] = pop_a_data.get("individuals", [])
    individuals_b: list[dict] = pop_b_data.get("individuals", [])

    for attr in attributes:
        props_a = _compute_proportions(individuals_a, attr)
        props_b = _compute_proportions(individuals_b, attr)

        if categories is not None and attr in categories:
            all_categories = list(categories[attr])
        else:
            all_categories = sorted((set(props_a) | set(props_b)) - {None})
        if not all_categories:
            continue

        vals_a = [props_a.get(cat, 0.0) for cat in all_categories]
        vals_b = [props_b.get(cat, 0.0) for cat in all_categories]

        horizontal = attr in _HIGH_CARDINALITY_FIELDS
        n_cats = len(all_categories)

        if horizontal:
            fig_height = max(4, min(n_cats * 0.5 + 2, 16))
            fig, ax = plt.subplots(figsize=(10, fig_height))

            bar_height = 0.35
            y_pos = np.arange(n_cats)

            ax.barh(y_pos + bar_height / 2, vals_a, height=bar_height,
                    color=_ATTR_COLORS[0], label=pop_a_label, edgecolor="white", linewidth=0.4)
            ax.barh(y_pos - bar_height / 2, vals_b, height=bar_height,
                    color=_ATTR_COLORS[1], label=pop_b_label, edgecolor="white", linewidth=0.4)

            ax.set_yticks(y_pos)
            ax.set_yticklabels(all_categories, fontsize=7)
            ax.set_xlabel("Proportion", fontsize=8)
            ax.set_xlim(0, 1.0)
        else:
            fig, ax = plt.subplots(figsize=(max(8, n_cats * 0.9 + 2), 5))

            bar_width = 0.35
            x_pos = np.arange(n_cats)

            ax.bar(x_pos - bar_width / 2, vals_a, width=bar_width,
                   color=_ATTR_COLORS[0], label=pop_a_label, edgecolor="white", linewidth=0.4)
            ax.bar(x_pos + bar_width / 2, vals_b, width=bar_width,
                   color=_ATTR_COLORS[1], label=pop_b_label, edgecolor="white", linewidth=0.4)

            ax.set_xticks(x_pos)
            ax.set_xticklabels(all_categories, rotation=30, ha="right", fontsize=7)
            ax.set_ylabel("Proportion", fontsize=8)
            ax.set_ylim(0, 1.0)

        ax.set_title(
            f"{attr} distribution: {pop_a_label} vs {pop_b_label}",
            fontsize=10,
            fontweight="bold",
        )
        ax.legend(fontsize=8)
        ax.tick_params(axis="both", labelsize=7)

        plt.tight_layout()

        fname = f"{prefix}_{attr}.png" if prefix else f"{attr}.png"
        out_path = output_dir / fname
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close(fig)


# ------------------------------------------------------------------
# Radar chart
# ------------------------------------------------------------------

def plot_radar_comparison(
    marginals: dict[str, dict[str, Any]],
    output_dir: Path,
    pop_a_label: str = "Population A",
    pop_b_label: str = "Population B",
    *,
    show_chi_sq: bool = True,
    prefix: str | None = None,
    attributes: list[str],
) -> Path | None:
    """Generate a radar chart of TV-similarity (and optionally chi-sq p-values).

    *attributes* (required) is the config-sourced comparison axis.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    attrs = [a for a in attributes if a in marginals]
    if len(attrs) < 3:
        print(f"Skipping radar: needs >=3 attributes (got {len(attrs)})", file=sys.stderr)
        return None

    n = len(attrs)
    angles = [2 * np.pi * i / n for i in range(n)]

    tv_sim = [1.0 - marginals[a]["tv_distance"] for a in attrs]

    raw_chi = [marginals[a]["chi_sq_p"] for a in attrs]
    nan_mask = [np.isnan(v) for v in raw_chi]
    chi_plot = [0.0 if m else v for v, m in zip(raw_chi, nan_mask)]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={"projection": "polar"})
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)

    closed_angles = _close_polygon(angles)
    closed_tv = _close_polygon(tv_sim)

    ax.plot(closed_angles, closed_tv, color=_RADAR_TV_COLOR, linewidth=2, label="TV-similarity")
    ax.fill(closed_angles, closed_tv, color=_RADAR_TV_COLOR, alpha=0.20)

    if show_chi_sq:
        closed_chi = _close_polygon(chi_plot)
        ax.plot(
            closed_angles, closed_chi, color=_RADAR_CHI_COLOR,
            linestyle="--", linewidth=1.5, label="Chi-sq p-value",
        )
        ax.fill(closed_angles, closed_chi, color=_RADAR_CHI_COLOR, alpha=0.20)

        nan_angles = [ang for ang, m in zip(angles, nan_mask) if m]
        if nan_angles:
            ax.scatter(nan_angles, [0.0] * len(nan_angles), facecolors="none", edgecolors=_RADAR_CHI_COLOR, zorder=5)

    ax.set_xticks(angles)
    ax.set_xticklabels([])
    for i, (ang, label) in enumerate(zip(angles, attrs)):
        rotation = np.degrees(ang) - 90 if ang <= np.pi else np.degrees(ang) + 90
        ax.text(
            ang,
            1.18,
            label,
            ha="center",
            va="center",
            fontsize=7,
            rotation=rotation,
            rotation_mode="anchor",
        )

    for ang, val in zip(angles, tv_sim):
        ax.annotate(
            f"{val:.2f}",
            xy=(ang, val),
            xytext=(ang, val + 0.07),
            fontsize=7,
            color=_RADAR_TV_COLOR,
            ha="center",
            va="center",
        )

    ax.set_title(
        f"Per-dimension similarity\n{pop_a_label} vs {pop_b_label}",
        fontsize=11,
        fontweight="bold",
        pad=24,
    )

    ax.set_ylim(0, 1)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.yaxis.grid(True, color="lightgray")
    ax.spines["polar"].set_linewidth(1.2)

    if show_chi_sq:
        ax.legend(loc="lower left", bbox_to_anchor=(-0.1, -0.05), fontsize=8)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{prefix}_radar.png" if prefix else "radar.png"
    out_path = output_dir / fname
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ------------------------------------------------------------------
# 3-way bar-chart comparison
# ------------------------------------------------------------------

_SUBPLOT_THRESHOLD = 30


def plot_3way_comparison_charts(
    pop_a: dict,
    pop_b: dict,
    pop_c: dict,
    labels: tuple[str, str, str],
    output_dir: Path,
    *,
    attributes: list[str],
    prefix: str | None = None,
) -> None:
    """Generate grouped bar charts comparing three populations per attribute."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    inds_a: list[dict] = pop_a.get("individuals", [])
    inds_b: list[dict] = pop_b.get("individuals", [])
    inds_c: list[dict] = pop_c.get("individuals", [])
    all_inds = (inds_a, inds_b, inds_c)

    for attr in attributes:
        props = [_compute_proportions(ind, attr) for ind in all_inds]
        all_categories = sorted((set().union(*[set(p) for p in props])) - {None})
        if not all_categories:
            continue

        vals = [[p.get(cat, 0.0) for cat in all_categories] for p in props]
        n_cats = len(all_categories)
        use_subplots = n_cats > _SUBPLOT_THRESHOLD

        if use_subplots:
            fig, axes = plt.subplots(1, 3, figsize=(18, max(4, n_cats * 0.35 + 2)), sharey=True)
            for idx, (ax, label) in enumerate(zip(axes, labels)):
                y_pos = np.arange(n_cats)
                ax.barh(y_pos, vals[idx], color=_ATTR_COLORS_3WAY[idx], edgecolor="white", linewidth=0.3)
                ax.set_yticks(y_pos)
                if idx == 0:
                    ax.set_yticklabels(all_categories, fontsize=6)
                else:
                    ax.set_yticklabels([])
                ax.set_xlabel("Proportion", fontsize=7)
                ax.set_xlim(0, max(max(v) for v in vals) * 1.15 or 1.0)
                ax.set_title(label, fontsize=9, fontweight="bold")
                ax.tick_params(axis="both", labelsize=6)
            fig.suptitle(f"{attr} distribution", fontsize=11, fontweight="bold")
        elif attr in _HIGH_CARDINALITY_FIELDS:
            fig_height = max(4, min(n_cats * 0.6 + 2, 16))
            fig, ax = plt.subplots(figsize=(10, fig_height))
            bar_h = 0.25
            y_pos = np.arange(n_cats)
            for idx, label in enumerate(labels):
                ax.barh(y_pos + (idx - 1) * bar_h, vals[idx], height=bar_h,
                        color=_ATTR_COLORS_3WAY[idx], label=label, edgecolor="white", linewidth=0.3)
            ax.set_yticks(y_pos)
            ax.set_yticklabels(all_categories, fontsize=7)
            ax.set_xlabel("Proportion", fontsize=8)
            ax.set_xlim(0, 1.0)
            ax.set_title(f"{attr} distribution", fontsize=10, fontweight="bold")
            ax.legend(fontsize=8)
            ax.tick_params(axis="both", labelsize=7)
        else:
            fig, ax = plt.subplots(figsize=(max(8, n_cats * 1.2 + 2), 5))
            bar_w = 0.25
            x_pos = np.arange(n_cats)
            for idx, label in enumerate(labels):
                ax.bar(x_pos + (idx - 1) * bar_w, vals[idx], width=bar_w,
                       color=_ATTR_COLORS_3WAY[idx], label=label, edgecolor="white", linewidth=0.3)
            ax.set_xticks(x_pos)
            ax.set_xticklabels(all_categories, rotation=30, ha="right", fontsize=7)
            ax.set_ylabel("Proportion", fontsize=8)
            ax.set_ylim(0, 1.0)
            ax.set_title(f"{attr} distribution", fontsize=10, fontweight="bold")
            ax.legend(fontsize=8)
            ax.tick_params(axis="both", labelsize=7)

        plt.tight_layout()
        fname = f"{prefix}_{attr}.png" if prefix else f"{attr}.png"
        fig.savefig(output_dir / fname, dpi=150, bbox_inches="tight")
        plt.close(fig)


# ------------------------------------------------------------------
# 3-way radar chart
# ------------------------------------------------------------------

def plot_3way_radar(
    pairwise: dict[str, dict],
    labels: tuple[str, ...],
    output_dir: Path,
    *,
    attributes: list[str],
    prefix: str | None = None,
) -> Path | None:
    """Generate a radar chart with overlaid TV-similarity polygons for each pair."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pair_names = list(pairwise.keys())
    if not pair_names:
        return None

    first_metrics = pairwise[pair_names[0]]
    attrs = [a for a in attributes if a in first_metrics]
    if len(attrs) < 3:
        print(f"Skipping 3-way radar: needs >=3 attributes (got {len(attrs)})", file=sys.stderr)
        return None

    n = len(attrs)
    angles = [2 * np.pi * i / n for i in range(n)]
    closed_angles = _close_polygon(angles)

    fig, ax = plt.subplots(figsize=(9, 9), subplot_kw={"projection": "polar"})
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)

    for idx, pn in enumerate(pair_names):
        metrics = pairwise[pn]
        tv_sim = []
        for a in attrs:
            tv = metrics.get(a, {}).get("tv_distance", 0.0)
            if tv != tv:  # NaN
                tv = 0.0
            tv_sim.append(1.0 - tv)

        color = _RADAR_3WAY_COLORS[idx % len(_RADAR_3WAY_COLORS)]
        style = _RADAR_3WAY_STYLES[idx % len(_RADAR_3WAY_STYLES)]
        lbl = labels[idx] if idx < len(labels) else pn

        closed_tv = _close_polygon(tv_sim)
        ax.plot(closed_angles, closed_tv, color=color, linewidth=2, linestyle=style, label=lbl)
        ax.fill(closed_angles, closed_tv, color=color, alpha=0.08)

    ax.set_xticks(angles)
    ax.set_xticklabels([])
    for i, (ang, label_text) in enumerate(zip(angles, attrs)):
        rotation = np.degrees(ang) - 90 if ang <= np.pi else np.degrees(ang) + 90
        ax.text(ang, 1.18, label_text, ha="center", va="center", fontsize=7,
                rotation=rotation, rotation_mode="anchor")

    ax.set_title("Per-dimension TV-similarity\n(3-way pairwise)", fontsize=11, fontweight="bold", pad=24)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.yaxis.grid(True, color="lightgray")
    ax.spines["polar"].set_linewidth(1.2)
    ax.legend(loc="lower left", bbox_to_anchor=(-0.15, -0.08), fontsize=8)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{prefix}_radar_3way.png" if prefix else "radar_3way.png"
    out_path = output_dir / fname
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ------------------------------------------------------------------
# Radar grid (models × strategies)
# ------------------------------------------------------------------

STRATEGY_COMPLEXITY_ORDER = [
    "all_pick",
    "all_pick_dag",
    "all_generate_pick",
    "all_generate_evaluate_pick",
    "all_generate_evaluate_random_pick",
]


def plot_radar_grid(
    results: dict[tuple[str, str], dict[str, dict[str, Any]]],
    output_dir: Path,
    *,
    strategy_order: list[str] | None = None,
    prefix: str | None = None,
    attributes: list[str],
) -> Path | None:
    """Grid of radar subplots: rows = models, columns = strategies (by complexity).

    *attributes* (required) is the config-sourced comparison axis.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not results:
        return None

    if strategy_order is None:
        strategy_order = STRATEGY_COMPLEXITY_ORDER

    all_models = sorted({m for m, _ in results})
    all_strategies = sorted({s for _, s in results})
    strategies = [s for s in strategy_order if s in all_strategies]
    if not strategies:
        return None

    attrs = [a for a in attributes
             if any(a in marg for marg in results.values())]
    if len(attrs) < 3:
        print(f"Skipping radar grid: needs >=3 attributes (got {len(attrs)})",
              file=sys.stderr)
        return None

    n_attrs = len(attrs)
    angles = [2 * np.pi * i / n_attrs for i in range(n_attrs)]
    closed_angles = _close_polygon(angles)

    n_rows = len(all_models)
    n_cols = len(strategies)

    cell_size = 3.2
    fig, axes = plt.subplots(
        n_rows, n_cols,
        figsize=(n_cols * cell_size + 1.5, n_rows * cell_size + 1.2),
        subplot_kw={"projection": "polar"},
    )

    if n_rows == 1 and n_cols == 1:
        axes = np.array([[axes]])
    elif n_rows == 1:
        axes = axes[np.newaxis, :]
    elif n_cols == 1:
        axes = axes[:, np.newaxis]

    for r, model in enumerate(all_models):
        for c, strategy in enumerate(strategies):
            ax = axes[r, c]
            ax.set_theta_offset(np.pi / 2)
            ax.set_theta_direction(-1)

            marginals = results.get((model, strategy))
            if marginals is None:
                ax.set_xticks([])
                ax.set_yticks([])
                ax.text(0.5, 0.5, "N/A", transform=ax.transAxes,
                        ha="center", va="center", fontsize=11, color="gray")
                if r == 0:
                    ax.set_title(strategy.replace("_", "\n"), fontsize=7,
                                 fontweight="bold", pad=14)
                if c == 0:
                    ax.set_ylabel(model, fontsize=7, labelpad=30,
                                  fontweight="bold")
                continue

            tv_sim = []
            for a in attrs:
                tv = marginals.get(a, {}).get("tv_distance", 0.0)
                if tv != tv:
                    tv = 0.0
                tv_sim.append(1.0 - tv)

            closed_tv = _close_polygon(tv_sim)
            ax.plot(closed_angles, closed_tv, color=_RADAR_TV_COLOR,
                    linewidth=1.5)
            ax.fill(closed_angles, closed_tv, color=_RADAR_TV_COLOR,
                    alpha=0.20)

            ax.set_ylim(0, 1)
            ax.set_yticks([0.5, 1.0])
            ax.set_yticklabels(["0.5", "1.0"], fontsize=5, color="gray")
            ax.yaxis.grid(True, color="lightgray", linewidth=0.5)

            ax.set_xticks(angles)
            ax.set_xticklabels([])
            for ang, label_text in zip(angles, attrs):
                rotation = (np.degrees(ang) - 90 if ang <= np.pi
                            else np.degrees(ang) + 90)
                ax.text(ang, 1.22, label_text, ha="center", va="center",
                        fontsize=4.5, rotation=rotation,
                        rotation_mode="anchor")

            mean_tv_sim = sum(tv_sim) / len(tv_sim)
            ax.text(0.5, -0.08, f"mean: {mean_tv_sim:.2f}",
                    transform=ax.transAxes, ha="center", fontsize=6,
                    color=_RADAR_TV_COLOR, fontweight="bold")

            if r == 0:
                ax.set_title(strategy.replace("_", "\n"), fontsize=7,
                             fontweight="bold", pad=14)
            if c == 0:
                ax.set_ylabel(model, fontsize=7, labelpad=30,
                              fontweight="bold")

    fig.suptitle("TV-similarity radar: models × strategies",
                 fontsize=13, fontweight="bold", y=1.01)
    plt.tight_layout(rect=[0, 0, 1, 0.98])

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{prefix}_radar_grid.png" if prefix else "radar_grid.png"
    out_path = output_dir / fname
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out_path
