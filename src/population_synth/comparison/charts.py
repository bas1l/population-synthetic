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

from population_synth.comparison.evaluator import DEMOGRAPHIC_ATTRIBUTES

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

_RADAR_TV_COLOR = "#2A9D8F"
_RADAR_CHI_COLOR = "#E9C46A"


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _compute_proportions(individuals: list[dict], attr: str) -> dict[str, float]:
    counts: Counter = Counter()
    for ind in individuals:
        val = ind.get(attr)
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
) -> None:
    """Generate side-by-side bar charts for each demographic attribute."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    individuals_a: list[dict] = pop_a_data.get("individuals", [])
    individuals_b: list[dict] = pop_b_data.get("individuals", [])

    for attr in DEMOGRAPHIC_ATTRIBUTES:
        props_a = _compute_proportions(individuals_a, attr)
        props_b = _compute_proportions(individuals_b, attr)

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

        out_path = output_dir / f"{attr}.png"
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
) -> Path | None:
    """Generate a radar chart of TV-similarity (and optionally chi-sq p-values)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    attrs = [a for a in DEMOGRAPHIC_ATTRIBUTES if a in marginals]
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
    out_path = output_dir / "radar.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path
