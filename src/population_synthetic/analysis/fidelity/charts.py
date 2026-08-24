"""
charts.py -- Visualization tools for demographic population comparisons.

Provides bar-chart comparisons per attribute and a radar (spider) chart
summarizing per-dimension TV similarity and chi-squared p-values.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np

from population_synthetic.analysis.fidelity.evaluator import attr_value
from population_synthetic.analysis.utils.axes import strategy_complexity_order
from population_synthetic.analysis.utils.figures import save_figure
from population_synthetic.analysis.utils.marginals import compute_proportions
from population_synthetic.analysis.utils.palette import (
    ACCENT_PAIR,
    CATEGORICAL_SERIES,
    MUTED_GREY,
    SECONDARY_GREY,
    heatmap_cmap,
    text_color_on,
)
from population_synthetic.analysis.utils.style import (
    ANNOTATION,
    AXIS_TITLE,
    CALLOUT,
    FIGURE_TITLE,
    FULL,
    LEGEND_LABEL,
    LEGEND_TITLE,
    MAX_HEIGHT,
    PANEL_TITLE,
    TICK_LABEL,
    figure_size,
    grow_height,
    grow_width,
    house_style,
)

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

# One slot of the house categorical series per compared population, in the order the
# populations are passed. Positional, not semantic: nothing here knows which country
# sits in which slot.
_ATTR_COLORS = CATEGORICAL_SERIES[:2]
_ATTR_COLORS_3WAY = CATEGORICAL_SERIES[:3]

# The radar overlays two filled polygons on the same axes, so its two series take the
# palette's overlay accent pair rather than the first two slots of the series above.
_RADAR_TV_COLOR, _RADAR_CHI_COLOR = ACCENT_PAIR

_RADAR_3WAY_COLORS = CATEGORICAL_SERIES[:3]
_RADAR_3WAY_STYLES = ("solid", "dashed", "dotted")


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _compute_proportions(individuals: list[dict], attr: str) -> dict[str, float]:
    """Proportions keyed by the categories *observed* for *attr* (summing to 1).

    Thin adapter over the shared :func:`compute_proportions`: the observed
    category set is the axis, so the result is the full observed distribution
    (empty when the attribute is null for every individual). Callers pick their
    own display axis and ``.get(cat, 0.0)`` any category absent from the data.
    """
    observed = [v for v in {attr_value(ind, attr) for ind in individuals} if v is not None]
    proportions, _ = compute_proportions(individuals, attr, observed)
    return proportions


def _close_polygon(values: list[float]) -> list[float]:
    return values + values[:1]


# ------------------------------------------------------------------
# Bar-chart comparison
# ------------------------------------------------------------------

@house_style
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
    zero real-population count; otherwise categories fall back to the observed union.
    """
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
            fig_height = grow_height(n_cats, per_item=0.5, padding=2, minimum=4.0)
            fig, ax = plt.subplots(figsize=figure_size(FULL, fig_height))

            bar_height = 0.35
            y_pos = np.arange(n_cats)

            ax.barh(y_pos + bar_height / 2, vals_a, height=bar_height,
                    color=_ATTR_COLORS[0], label=pop_a_label, edgecolor="white", linewidth=0.4)
            ax.barh(y_pos - bar_height / 2, vals_b, height=bar_height,
                    color=_ATTR_COLORS[1], label=pop_b_label, edgecolor="white", linewidth=0.4)

            ax.set_yticks(y_pos)
            ax.set_yticklabels(all_categories, fontsize=TICK_LABEL)
            ax.set_xlabel("Proportion", fontsize=AXIS_TITLE)
            ax.set_xlim(0, 1.0)
        else:
            fig, ax = plt.subplots(figsize=figure_size(grow_width(n_cats, per_item=0.9, padding=2, minimum=FULL), 5))

            bar_width = 0.35
            x_pos = np.arange(n_cats)

            ax.bar(x_pos - bar_width / 2, vals_a, width=bar_width,
                   color=_ATTR_COLORS[0], label=pop_a_label, edgecolor="white", linewidth=0.4)
            ax.bar(x_pos + bar_width / 2, vals_b, width=bar_width,
                   color=_ATTR_COLORS[1], label=pop_b_label, edgecolor="white", linewidth=0.4)

            ax.set_xticks(x_pos)
            ax.set_xticklabels(all_categories, rotation=30, ha="right", fontsize=TICK_LABEL)
            ax.set_ylabel("Proportion", fontsize=AXIS_TITLE)
            ax.set_ylim(0, 1.0)

        ax.set_title(
            f"{attr} distribution: {pop_a_label} vs {pop_b_label}",
            fontsize=PANEL_TITLE,
            fontweight="bold",
        )
        ax.legend(fontsize=LEGEND_LABEL)
        ax.tick_params(axis="both", labelsize=TICK_LABEL)

        plt.tight_layout()

        fname = f"{prefix}_{attr}.png" if prefix else f"{attr}.png"
        out_path = output_dir / fname
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close(fig)


# ------------------------------------------------------------------
# Radar chart
# ------------------------------------------------------------------

@house_style
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

    fig, ax = plt.subplots(figsize=figure_size(FULL, 8), subplot_kw={"projection": "polar"})
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
            fontsize=ANNOTATION,
            rotation=rotation,
            rotation_mode="anchor",
        )

    for ang, val in zip(angles, tv_sim):
        ax.annotate(
            f"{val:.2f}",
            xy=(ang, val),
            xytext=(ang, val + 0.07),
            fontsize=ANNOTATION,
            color=_RADAR_TV_COLOR,
            ha="center",
            va="center",
        )

    ax.set_title(
        f"Per-dimension similarity\n{pop_a_label} vs {pop_b_label}",
        fontsize=PANEL_TITLE,
        fontweight="bold",
        pad=24,
    )

    ax.set_ylim(0, 1)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.yaxis.grid(True, color="lightgray")
    ax.spines["polar"].set_linewidth(1.2)

    if show_chi_sq:
        ax.legend(loc="lower left", bbox_to_anchor=(-0.1, -0.05), fontsize=LEGEND_LABEL)

    out_path = Path(output_dir) / (f"{prefix}_radar.png" if prefix else "radar.png")
    return save_figure(fig, out_path, dpi=150)


# ------------------------------------------------------------------
# Multivariate association-fidelity heatmap (|Delta V|)
# ------------------------------------------------------------------

@house_style
def plot_association_heatmap(
    report: dict[str, Any],
    output_dir: Path,
    *,
    prefix: str | None = None,
    attributes: list[str] | None = None,
) -> Path | None:
    """Per-combo attribute x attribute heatmap of Cramer's-V discrepancy ``|Delta V|``.

    Consumes ``report["multivariate"]["association"]["pairs"]`` (each carrying
    ``attr_x`` / ``attr_y`` / ``abs_delta_v``) and renders a symmetric grid where
    each cell is the absolute difference between the real and synthetic pairwise
    association. ``|Delta V|`` is an error magnitude (0 = identical association,
    higher = worse), so it uses a single-hue sequential ramp -- more colour reads
    as a larger joint-structure discrepancy.

    Returns ``None`` for reports without a multivariate association block (old
    reports) or with no usable pairs, so callers degrade gracefully.
    """
    pairs = report.get("multivariate", {}).get("association", {}).get("pairs", [])
    if not pairs:
        return None

    import matplotlib.pyplot as plt

    # Attribute order: the config axis when supplied (stable across combos),
    # otherwise the observed union of the pair endpoints (sorted).
    if attributes is not None:
        attrs = [a for a in attributes if any(a in (p["attr_x"], p["attr_y"]) for p in pairs)]
    else:
        seen: list[str] = []
        for p in pairs:
            for a in (p["attr_x"], p["attr_y"]):
                if a not in seen:
                    seen.append(a)
        attrs = sorted(seen)
    if len(attrs) < 2:
        return None

    idx = {a: i for i, a in enumerate(attrs)}
    n = len(attrs)
    grid = np.full((n, n), np.nan)
    for p in pairs:
        i = idx.get(p["attr_x"])
        j = idx.get(p["attr_y"])
        if i is None or j is None:
            continue
        raw = p.get("abs_delta_v")
        val = float(raw) if raw is not None else np.nan
        grid[i, j] = val
        grid[j, i] = val

    masked = np.ma.masked_invalid(grid)
    if masked.count() == 0:
        return None

    fig, ax = plt.subplots(
        figsize=(
            grow_width(n, per_item=0.7, padding=2.5, minimum=6.0),
            grow_height(n, per_item=0.7, padding=2.0, minimum=5.0),
        ),
    )
    vmax = max(float(masked.max()), 1e-6)
    im = ax.imshow(masked, cmap=heatmap_cmap(), vmin=0.0, vmax=vmax)

    ax.set_xticks(range(n))
    ax.set_xticklabels(attrs, rotation=40, ha="right", fontsize=TICK_LABEL)
    ax.set_yticks(range(n))
    ax.set_yticklabels(attrs, fontsize=TICK_LABEL)

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
    cbar.set_label("|Delta V|  (Cramer's V: real vs synthetic)", fontsize=AXIS_TITLE)

    for i in range(n):
        for j in range(n):
            v = grid[i, j]
            if np.isnan(v):
                continue
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=ANNOTATION,
                    color=text_color_on(im, v))

    title = "Pairwise association fidelity  |Delta V|"
    if prefix:
        title = f"{prefix}: {title}"
    ax.set_title(title, fontsize=PANEL_TITLE, fontweight="bold")
    fig.tight_layout()

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{prefix}_association_heatmap.png" if prefix else "association_heatmap.png"
    out_path = output_dir / fname
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ------------------------------------------------------------------
# 3-way bar-chart comparison
# ------------------------------------------------------------------

_SUBPLOT_THRESHOLD = 30


@house_style
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
            fig, axes = plt.subplots(
                1,
                3,
                figsize=(FULL, grow_height(n_cats, per_item=0.35, padding=2, minimum=4.0)),
                sharey=True,
            )
            for idx, (ax, label) in enumerate(zip(axes, labels)):
                y_pos = np.arange(n_cats)
                ax.barh(y_pos, vals[idx], color=_ATTR_COLORS_3WAY[idx], edgecolor="white", linewidth=0.3)
                ax.set_yticks(y_pos)
                if idx == 0:
                    ax.set_yticklabels(all_categories, fontsize=TICK_LABEL)
                else:
                    ax.set_yticklabels([])
                ax.set_xlabel("Proportion", fontsize=AXIS_TITLE)
                ax.set_xlim(0, max(max(v) for v in vals) * 1.15 or 1.0)
                ax.set_title(label, fontsize=PANEL_TITLE, fontweight="bold")
                ax.tick_params(axis="both", labelsize=TICK_LABEL)
            fig.suptitle(f"{attr} distribution", fontsize=FIGURE_TITLE, fontweight="bold")
        elif attr in _HIGH_CARDINALITY_FIELDS:
            fig_height = grow_height(n_cats, per_item=0.6, padding=2, minimum=4.0)
            fig, ax = plt.subplots(figsize=figure_size(FULL, fig_height))
            bar_h = 0.25
            y_pos = np.arange(n_cats)
            for idx, label in enumerate(labels):
                ax.barh(y_pos + (idx - 1) * bar_h, vals[idx], height=bar_h,
                        color=_ATTR_COLORS_3WAY[idx], label=label, edgecolor="white", linewidth=0.3)
            ax.set_yticks(y_pos)
            ax.set_yticklabels(all_categories, fontsize=TICK_LABEL)
            ax.set_xlabel("Proportion", fontsize=AXIS_TITLE)
            ax.set_xlim(0, 1.0)
            ax.set_title(f"{attr} distribution", fontsize=PANEL_TITLE, fontweight="bold")
            ax.legend(fontsize=LEGEND_LABEL)
            ax.tick_params(axis="both", labelsize=TICK_LABEL)
        else:
            fig, ax = plt.subplots(figsize=figure_size(grow_width(n_cats, per_item=1.2, padding=2, minimum=FULL), 5))
            bar_w = 0.25
            x_pos = np.arange(n_cats)
            for idx, label in enumerate(labels):
                ax.bar(x_pos + (idx - 1) * bar_w, vals[idx], width=bar_w,
                       color=_ATTR_COLORS_3WAY[idx], label=label, edgecolor="white", linewidth=0.3)
            ax.set_xticks(x_pos)
            ax.set_xticklabels(all_categories, rotation=30, ha="right", fontsize=TICK_LABEL)
            ax.set_ylabel("Proportion", fontsize=AXIS_TITLE)
            ax.set_ylim(0, 1.0)
            ax.set_title(f"{attr} distribution", fontsize=PANEL_TITLE, fontweight="bold")
            ax.legend(fontsize=LEGEND_LABEL)
            ax.tick_params(axis="both", labelsize=TICK_LABEL)

        plt.tight_layout()
        fname = f"{prefix}_{attr}.png" if prefix else f"{attr}.png"
        fig.savefig(output_dir / fname, dpi=150, bbox_inches="tight")
        plt.close(fig)


# ------------------------------------------------------------------
# 3-way radar chart
# ------------------------------------------------------------------

@house_style
def plot_3way_radar(
    pairwise: dict[str, dict],
    labels: tuple[str, ...],
    output_dir: Path,
    *,
    attributes: list[str],
    prefix: str | None = None,
) -> Path | None:
    """Generate a radar chart with overlaid TV-similarity polygons for each pair."""
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

    fig, ax = plt.subplots(figsize=(FULL, MAX_HEIGHT), subplot_kw={"projection": "polar"})
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
        ax.text(ang, 1.18, label_text, ha="center", va="center", fontsize=ANNOTATION,
                rotation=rotation, rotation_mode="anchor")

    ax.set_title("Per-dimension TV-similarity\n(3-way pairwise)", fontsize=PANEL_TITLE, fontweight="bold", pad=24)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.yaxis.grid(True, color="lightgray")
    ax.spines["polar"].set_linewidth(1.2)
    ax.legend(loc="lower left", bbox_to_anchor=(-0.15, -0.08), fontsize=LEGEND_LABEL)

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

@house_style
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
    import matplotlib.pyplot as plt

    if not results:
        return None

    all_models = sorted({m for m, _ in results})
    all_strategies = sorted({s for _, s in results})
    # No caller-supplied order -> resolve the config-derived complexity order over
    # exactly the strategies present (an unknown id raises rather than sorting last).
    if strategy_order is None:
        strategy_order = strategy_complexity_order(all_strategies)
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
        n_rows,
        n_cols,
        figsize=(
            grow_width(n_cols, per_item=cell_size, padding=1.5),
            grow_height(n_rows, per_item=cell_size, padding=1.2),
        ),
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
                        ha="center", va="center", fontsize=CALLOUT, color="gray")
                if r == 0:
                    ax.set_title(strategy.replace("_", "\n"), fontsize=PANEL_TITLE,
                                 fontweight="bold", pad=14)
                if c == 0:
                    ax.set_ylabel(model, fontsize=AXIS_TITLE, labelpad=30,
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
            ax.set_yticklabels(["0.5", "1.0"], fontsize=TICK_LABEL, color="gray")
            ax.yaxis.grid(True, color="lightgray", linewidth=0.5)

            ax.set_xticks(angles)
            ax.set_xticklabels([])
            for ang, label_text in zip(angles, attrs):
                rotation = (np.degrees(ang) - 90 if ang <= np.pi
                            else np.degrees(ang) + 90)
                ax.text(ang, 1.22, label_text, ha="center", va="center",
                        fontsize=ANNOTATION, rotation=rotation,
                        rotation_mode="anchor")

            mean_tv_sim = sum(tv_sim) / len(tv_sim)
            ax.text(0.5, -0.08, f"mean: {mean_tv_sim:.2f}",
                    transform=ax.transAxes, ha="center", fontsize=ANNOTATION,
                    color=_RADAR_TV_COLOR, fontweight="bold")

            if r == 0:
                ax.set_title(strategy.replace("_", "\n"), fontsize=PANEL_TITLE,
                             fontweight="bold", pad=14)
            if c == 0:
                ax.set_ylabel(model, fontsize=AXIS_TITLE, labelpad=30,
                              fontweight="bold")

    fig.suptitle("TV-similarity radar: models × strategies",
                 fontsize=FIGURE_TITLE, fontweight="bold", y=1.01)
    plt.tight_layout(rect=[0, 0, 1, 0.98])

    out_path = Path(output_dir) / (f"{prefix}_radar_grid.png" if prefix else "radar_grid.png")
    return save_figure(fig, out_path, dpi=180)


# ------------------------------------------------------------------
# Multivariate metric figures (C2ST, grounded joint TV, k-way)
# ------------------------------------------------------------------
#
# Each mirrors :func:`plot_association_heatmap`: reads one report block, returns
# ``None`` (before importing matplotlib) when there is nothing plottable -- an
# absent block or all-NaN values from a tiny/failed synthetic population -- and
# otherwise writes a single ``{prefix}_<metric>.png`` at dpi 150.


@house_style
def plot_c2st(
    report: dict[str, Any],
    output_dir: Path,
    *,
    prefix: str | None = None,
) -> Path | None:
    """Single-bar view of the C2ST AUC against the 0.5 "indistinguishable" line.

    Reads ``report["multivariate"]["c2st"]``. Returns ``None`` when the block is
    absent or the AUC is NaN (balanced size below 2), so a degenerate B degrades
    gracefully.
    """
    c2st = report.get("multivariate", {}).get("c2st")
    if not c2st:
        return None
    auc = c2st.get("auc")
    if auc is None or (isinstance(auc, float) and np.isnan(auc)):
        return None

    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    p_value = c2st.get("p_value")
    method = c2st.get("method", "?")
    balanced_n = c2st.get("balanced_n", "?")

    fig, ax = plt.subplots(figsize=figure_size(4.5, 5.0))
    ax.bar([0], [auc], width=0.5, color=CATEGORICAL_SERIES[0], edgecolor="white", linewidth=0.6, zorder=3)
    ax.axhline(0.5, color=MUTED_GREY, linestyle="--", linewidth=1.0, zorder=1)
    ax.text(0.0, 0.5, "  0.5 = indistinguishable joint", va="bottom", ha="center",
            fontsize=ANNOTATION, color=SECONDARY_GREY)
    ax.text(0.0, auc, f"{auc:.3f}", va="bottom", ha="center", fontsize=CALLOUT, fontweight="bold")

    p_str = "nan" if p_value is None or (isinstance(p_value, float) and np.isnan(p_value)) else f"{p_value:.3f}"
    ax.set_xticks([0])
    ax.set_xticklabels([f"p = {p_str}\n{method}, balanced n = {balanced_n}"], fontsize=TICK_LABEL)
    ax.set_ylabel("C2ST ROC-AUC", fontsize=AXIS_TITLE)
    ax.set_ylim(0.4, 1.02)
    ax.grid(True, axis="y", linestyle=":", alpha=0.4)

    title = "C2ST: real vs synthetic separability"
    ax.set_title(f"{prefix}: {title}" if prefix else title, fontsize=FIGURE_TITLE, fontweight="bold")
    fig.tight_layout()

    fname = f"{prefix}_c2st.png" if prefix else "c2st.png"
    out_path = output_dir / fname
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


@house_style
def plot_joint_fidelity(
    report: dict[str, Any],
    output_dir: Path,
    *,
    prefix: str | None = None,
    attributes: list[str] | None = None,
) -> Path | None:
    """Horizontal bar of grounded joint-TV per attribute pair.

    Reads ``report["multivariate"]["joint_fidelity"]["pairs"]``; each bar is
    coloured/hatched by the ``grounded`` verdict (grounded solid, reference
    hatched) so an over-claim is visible at a glance. ``attributes`` (optional,
    the config axis) only orders the pairs. Returns ``None`` when there are no
    pairs or every ``joint_tv`` is NaN.
    """
    pairs = report.get("multivariate", {}).get("joint_fidelity", {}).get("pairs", [])
    plottable = [p for p in pairs if not (p.get("joint_tv") is None
                                          or (isinstance(p.get("joint_tv"), float) and np.isnan(p["joint_tv"])))]
    if not plottable:
        return None

    if attributes is not None:
        order = {a: i for i, a in enumerate(attributes)}
        plottable.sort(key=lambda p: (order.get(p["attr_x"], len(order)), order.get(p["attr_y"], len(order))))

    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    labels = [f"{p['attr_x']}×{p['attr_y']}" for p in plottable]
    values = [float(p["joint_tv"]) for p in plottable]
    grounded = [bool(p.get("grounded")) for p in plottable]
    colors = [CATEGORICAL_SERIES[2] if g else CATEGORICAL_SERIES[3] for g in grounded]
    hatches = ["" if g else "//" for g in grounded]

    y_pos = np.arange(len(plottable))
    fig, ax = plt.subplots(figsize=(FULL, grow_height(len(plottable), per_item=0.5, padding=1.5, minimum=3.0)))
    bars = ax.barh(y_pos, values, color=colors, edgecolor="white", linewidth=0.6, zorder=3)
    for bar, hatch in zip(bars, hatches):
        bar.set_hatch(hatch)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=TICK_LABEL)
    ax.invert_yaxis()
    ax.set_xlabel("joint TV distance  (0 = identical joint, lower better)", fontsize=AXIS_TITLE)
    ax.set_xlim(0, max(1.0, max(values) * 1.1))
    ax.grid(True, axis="x", linestyle=":", alpha=0.4)

    from matplotlib.patches import Patch
    legend_handles = [
        Patch(facecolor=CATEGORICAL_SERIES[2], label="grounded"),
        Patch(facecolor=CATEGORICAL_SERIES[3], hatch="//", label="reference"),
    ]
    ax.legend(handles=legend_handles, fontsize=LEGEND_LABEL, title="basis", title_fontsize=LEGEND_TITLE)

    title = "Grounded joint total-variation distance"
    ax.set_title(f"{prefix}: {title}" if prefix else title, fontsize=FIGURE_TITLE, fontweight="bold")
    fig.tight_layout()

    fname = f"{prefix}_joint_fidelity.png" if prefix else "joint_fidelity.png"
    out_path = output_dir / fname
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


@house_style
def plot_combination_plausibility(
    report: dict[str, Any],
    output_dir: Path,
    *,
    prefix: str | None = None,
) -> Path | None:
    """Stacked severity bar (plausible / rare / impossible) per k-way check.

    Reads ``report["multivariate"]["combination_plausibility"]["checks"]``. A
    check with ``n_total == 0`` (NaN fractions) is skipped. Returns ``None`` when
    there are no plottable checks.
    """
    checks = report.get("multivariate", {}).get("combination_plausibility", {}).get("checks", [])
    plottable = [c for c in checks if c.get("n_total", 0) and not (
        isinstance(c.get("fraction_impossible"), float) and np.isnan(c["fraction_impossible"]))]
    if not plottable:
        return None

    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    labels = [f"{' | '.join(c['attributes'])}\n(k={c['k']})" for c in plottable]
    frac_impossible = [float(c["fraction_impossible"]) for c in plottable]
    frac_rare = [float(c["fraction_rare"]) for c in plottable]
    frac_plausible = [max(0.0, 1.0 - i - r) for i, r in zip(frac_impossible, frac_rare)]

    y_pos = np.arange(len(plottable))
    fig, ax = plt.subplots(figsize=(FULL, grow_height(len(plottable), per_item=0.6, padding=1.5, minimum=3.0)))
    left_imp = [p + r for p, r in zip(frac_plausible, frac_rare)]
    ax.barh(y_pos, frac_plausible, color=CATEGORICAL_SERIES[2],
            edgecolor="white", linewidth=0.6, label="plausible")
    ax.barh(y_pos, frac_rare, left=frac_plausible, color=CATEGORICAL_SERIES[4],
            edgecolor="white", linewidth=0.6, label="rare")
    ax.barh(y_pos, frac_impossible, left=left_imp, color=CATEGORICAL_SERIES[1],
            edgecolor="white", linewidth=0.6, label="impossible")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=TICK_LABEL)
    ax.invert_yaxis()
    ax.set_xlabel("fraction of synthetic individuals", fontsize=AXIS_TITLE)
    ax.set_xlim(0, 1.0)
    ax.legend(fontsize=LEGEND_LABEL, ncol=3, loc="lower center", bbox_to_anchor=(0.5, 1.0))

    title = "K-way combination plausibility"
    ax.set_title(f"{prefix}: {title}" if prefix else title, fontsize=FIGURE_TITLE, fontweight="bold", pad=24)
    fig.tight_layout()

    fname = f"{prefix}_combination_plausibility.png" if prefix else "combination_plausibility.png"
    out_path = output_dir / fname
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ------------------------------------------------------------------
# Legacy metric figures (joint chi-squared, coherence)
# ------------------------------------------------------------------
#
# Kept in their own section (mirroring the legacy CSV writers in evaluator.py)
# so the pair can be dropped in one edit if the legacy tier is retired.


@house_style
def plot_joint_chi_sq(
    report: dict[str, Any],
    output_dir: Path,
    *,
    prefix: str | None = None,
) -> Path | None:
    """Bar of the joint chi-squared p-value per configured pair, with a 0.05 line.

    Reads ``report["joint_chi_sq"]``. NaN p-values are skipped. Returns ``None``
    when there is nothing plottable.
    """
    joint = report.get("joint_chi_sq", {})
    items = [(k, v) for k, v in joint.items()
             if not (v is None or (isinstance(v, float) and np.isnan(v)))]
    if not items:
        return None

    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    labels = [k.replace("_x_", "×") for k, _ in items]
    values = [float(v) for _, v in items]
    colors = [CATEGORICAL_SERIES[1] if v < 0.05 else CATEGORICAL_SERIES[0] for v in values]

    x_pos = np.arange(len(items))
    fig, ax = plt.subplots(figsize=figure_size(grow_width(len(items), per_item=1.1, padding=2, minimum=6.0), 5.0))
    ax.bar(x_pos, values, width=0.6, color=colors, edgecolor="white", linewidth=0.6, zorder=3)
    ax.axhline(0.05, color=CATEGORICAL_SERIES[1], linestyle="--", linewidth=1.0, zorder=1)
    ax.text(len(items) - 0.5, 0.05, " 0.05 significance", va="bottom", ha="right",
            fontsize=ANNOTATION, color=SECONDARY_GREY)

    ax.set_xticks(x_pos)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=TICK_LABEL)
    ax.set_ylabel("joint chi-squared p-value  (higher = consistent)", fontsize=AXIS_TITLE)
    ax.set_ylim(0, 1.0)
    ax.grid(True, axis="y", linestyle=":", alpha=0.4)

    title = "Joint chi-squared p-value per pair"
    ax.set_title(f"{prefix}: {title}" if prefix else title, fontsize=FIGURE_TITLE, fontweight="bold")
    fig.tight_layout()

    fname = f"{prefix}_joint_chi_sq.png" if prefix else "joint_chi_sq.png"
    out_path = output_dir / fname
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


@house_style
def plot_coherence(
    report: dict[str, Any],
    output_dir: Path,
    *,
    prefix: str | None = None,
) -> Path | None:
    """Two-panel coherence view: plausible-vs-flagged split + flagged-probability histogram.

    Reads ``report["coherence"]``. Returns ``None`` when the block is absent.
    """
    coherence = report.get("coherence")
    if not coherence:
        return None

    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    n_plausible = coherence.get("n_plausible", 0)
    flagged = coherence.get("flagged", [])
    n_flagged = len(flagged)
    score = coherence.get("score")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figure_size(FULL, 4.6))

    ax1.pie(
        [n_plausible, n_flagged],
        labels=[f"plausible\n{n_plausible}", f"flagged\n{n_flagged}"],
        colors=[CATEGORICAL_SERIES[2], CATEGORICAL_SERIES[1]],
        autopct=lambda pct: f"{pct:.1f}%" if pct > 0 else "",
        startangle=90,
        wedgeprops={"width": 0.42, "edgecolor": "white"},
        textprops={"fontsize": ANNOTATION},
    )
    score_str = "nan" if score is None else f"{score:.2f}"
    ax1.text(0, 0, score_str, ha="center", va="center", fontsize=FIGURE_TITLE, fontweight="bold",
             color=CATEGORICAL_SERIES[2])
    ax1.set_title("Coherence score", fontsize=PANEL_TITLE, fontweight="bold")

    probs = [f.get("probability", 0.0) for f in flagged
             if f.get("probability") is not None]
    if probs:
        ax2.hist(probs, bins=min(20, max(3, len(set(probs)))), color=CATEGORICAL_SERIES[1],
                 edgecolor="white", linewidth=0.5)
        ax2.set_xlabel("combination probability in real A", fontsize=AXIS_TITLE)
        ax2.set_ylabel("flagged individuals", fontsize=AXIS_TITLE)
    else:
        ax2.text(0.5, 0.5, "no flagged individuals", transform=ax2.transAxes,
                 ha="center", va="center", fontsize=CALLOUT, color="gray")
        ax2.set_xticks([])
        ax2.set_yticks([])
    ax2.set_title("Flagged-probability distribution", fontsize=PANEL_TITLE, fontweight="bold")
    ax2.tick_params(axis="both", labelsize=TICK_LABEL)

    suptitle = "Individual coherence"
    fig.suptitle(f"{prefix}: {suptitle}" if prefix else suptitle, fontsize=FIGURE_TITLE, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])

    fname = f"{prefix}_coherence.png" if prefix else "coherence.png"
    out_path = output_dir / fname
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path
