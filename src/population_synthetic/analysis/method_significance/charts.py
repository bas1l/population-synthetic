"""charts.py -- Charts for the per-category method/model significance analysis.

Consumes the serialisable structure from
:func:`population_synthetic.analysis.method_significance.builder.build_method_significance`
(and, for the raw TV(method) trend lines, the loader's ``ComboPerformance``
records that fed it) and renders, per country:

* **per-attribute TV(method) trend lines** -- one chart per attribute, x = the 5
  ordered methods (complexity order), one line per model; the facet title carries
  the attribute's **BH-corrected** Page's-L p-value (never the raw p);
* a **slope heatmap** (attribute x model, cell = the descriptive TV(method) trend
  slope, diverging colour about 0) -- the *descriptive* view of the per-category
  method x model interaction (no p-value is claimed at this grain, so no
  significance is annotated here);
* a **critical-difference (CD) diagram** for models from
  ``overall.model_comparison`` (average-rank axis + a CD bar linking models that
  are *not* significantly different at the Nemenyi critical difference);
* a **factor-dominance bar** of the mixed model's eta^2 variance shares
  (model vs method vs category vs residual) from ``overall.mixed_logit.eta_sq``.

Faithful-visualisation rules (per the statistical-software guide, §7): the raw
data is shown, not silently dropped; absent cells are drawn as gaps (masked), not
zeros; significance is annotated only from the **corrected** p-values; every chart
returns ``None`` (logged as a skip by the caller) when its data is genuinely
empty rather than emitting a misleading empty axes.

Follows the project charting conventions (deferred ``Agg`` matplotlib import,
``dpi=150`` / ``bbox_inches="tight"``, ``plt.close`` on every path).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from population_synthetic.analysis.model_ranking.loader import ComboPerformance
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

# Ordered method axis (simplest -> most complex); rank = index + 1.
_METHOD_ORDER: list[str] = list(STRATEGY_COMPLEXITY_ORDER)


def _tv_distance(record: ComboPerformance, attr: str) -> float | None:
    """TV distance of *record* at *attr*, or ``None`` for an absent (NaN) cell."""
    value = record.marginals.get(attr, {}).get("tv_distance")
    if value is None:
        return None
    val = float(value)
    return val if val == val else None  # NaN -> absent


# ------------------------------------------------------------------
# Per-attribute TV(method) trend lines, one line per model
# ------------------------------------------------------------------

def plot_method_trends(
    result: dict[str, Any],
    records: list[ComboPerformance],
    out_dir: str | Path,
) -> list[Path]:
    """One TV(method) trend chart per attribute: x = 5 ordered methods, line per model.

    *records* supply the raw per-cell TV distances (the builder's serialisable
    output keeps only the derived slopes/tests, not the grid). Absent cells are
    left as gaps in the line, never imputed. The facet title reports the
    attribute's **BH-corrected** Page's-L p-value and flags significance from it.
    """
    attributes: list[str] = result["metadata"]["attributes"]
    models: list[str] = result["metadata"]["models"]
    alpha: float = result["metadata"]["alpha"]
    if not attributes or not models:
        return []

    by_cell = {(r.model, r.strategy): r for r in records}
    x = np.arange(len(_METHOD_ORDER))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    country = result["metadata"]["country"]
    written: list[Path] = []
    for attr in attributes:
        # Skip an attribute with no plottable TV in any cell (genuinely empty).
        any_point = any(
            _tv_distance(by_cell[(m, s)], attr) is not None
            for m in models for s in _METHOD_ORDER if (m, s) in by_cell
        )
        if not any_point:
            continue

        fig, ax = plt.subplots(figsize=(max(7.0, len(_METHOD_ORDER) * 1.4 + 2.0), 5.0))
        for m_idx, model in enumerate(models):
            ys = []
            for strategy in _METHOD_ORDER:
                record = by_cell.get((model, strategy))
                ys.append(np.nan if record is None else _tv_distance(record, attr))
            ys = [np.nan if v is None else v for v in ys]
            ax.plot(
                x, ys, marker="o", markersize=5, linewidth=1.6,
                color=_COLOR_SERIES[m_idx % len(_COLOR_SERIES)], label=model, alpha=0.9,
            )

        ax.set_xticks(x)
        ax.set_xticklabels(_METHOD_ORDER, rotation=25, ha="right", fontsize=8)
        ax.set_xlabel("generation method (simplest -> most complex)", fontsize=9)
        ax.set_ylabel("TV distance (lower = better fidelity)", fontsize=9)
        ax.grid(axis="y", linestyle=":", alpha=0.4)
        ax.legend(fontsize=7.5, title="model", title_fontsize=8)

        method = result["per_attribute"][attr]["method_trend"]
        p_bh = method.get("p_bh")
        if p_bh is None:
            trend_note = "Page L (BH): n/a"
        else:
            flag = "significant" if p_bh < alpha else "n.s."
            trend_note = f"Page L trend (BH-adj p = {p_bh:.3g}, {flag})"
        ax.set_title(
            f"{country}: {attr} -- TV by method, per model\n{trend_note}",
            fontsize=11, fontweight="bold",
        )
        out_path = out_dir / f"{attr}_method_trend.png"
        fig.tight_layout()
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        written.append(out_path)

    return written


# ------------------------------------------------------------------
# Slope heatmap (attribute x model) -- descriptive interaction view
# ------------------------------------------------------------------

def plot_slope_heatmap(result: dict[str, Any], out_path: str | Path) -> Path | None:
    """Attribute x model heatmap of the descriptive TV(method) trend slope.

    Cell = the per-(attribute, model) OLS slope of TV distance on method rank
    (positive = fidelity worsens with complexity, negative = improves). This is
    the *descriptive* per-category interaction: **no p-value is claimed at this
    grain** (n = 1 per cell), so no significance stars are drawn. A diverging
    colormap centres white at 0. Absent slopes render as grey gaps.
    """
    attributes: list[str] = result["metadata"]["attributes"]
    models: list[str] = result["metadata"]["models"]
    per_attribute_model: dict[str, Any] = result.get("per_attribute_model", {})
    if not attributes or not models:
        return None

    values = np.full((len(attributes), len(models)), np.nan)
    for i, attr in enumerate(attributes):
        row = per_attribute_model.get(attr, {})
        for j, model in enumerate(models):
            slope = (row.get(model) or {}).get("ols_slope")
            if slope is not None:
                values[i, j] = float(slope)
    if np.all(np.isnan(values)):
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    masked = np.ma.masked_invalid(values)
    finite = masked.compressed()
    bound = float(np.max(np.abs(finite))) if finite.size else 1.0
    bound = bound if bound > 0 else 1.0

    fig, ax = plt.subplots(
        figsize=(max(6.0, len(models) * 0.9 + 3.0), max(4.0, len(attributes) * 0.45 + 2.5))
    )
    cmap = plt.get_cmap("RdBu_r").copy()
    cmap.set_bad(color="#DDDDDD")
    im = ax.imshow(masked, aspect="auto", cmap=cmap, vmin=-bound, vmax=bound)

    ax.set_xticks(range(len(models)))
    ax.set_xticklabels(models, rotation=40, ha="right", fontsize=8)
    ax.set_yticks(range(len(attributes)))
    ax.set_yticklabels(attributes, fontsize=8)

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("TV(method) slope (+ = worsens, - = improves)", fontsize=8)

    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            v = values[i, j]
            if np.isnan(v):
                continue
            color = "white" if abs(v) > 0.6 * bound else "black"
            ax.text(j, i, f"{v:+.3f}", ha="center", va="center", fontsize=6.5, color=color)

    country = result["metadata"]["country"]
    ax.set_title(
        f"{country}: per-category TV(method) trend slope (descriptive; n=1 per cell)",
        fontsize=11, fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ------------------------------------------------------------------
# Critical-difference (CD) diagram for models (Demšar 2006)
# ------------------------------------------------------------------

def plot_cd_diagram(result: dict[str, Any], out_path: str | Path) -> Path | None:
    """Critical-difference diagram of models from the Demšar model comparison.

    Places each model on an average-rank axis (lower = better) and connects, with
    a thick bar, groups of models whose average ranks differ by **less than the
    Nemenyi critical difference** (i.e. not significantly different). Returns
    ``None`` when the model comparison was degenerate (fewer than 2 models /
    blocks, so no ranks or CD).
    """
    comparison: dict[str, Any] = result.get("overall", {}).get("model_comparison", {})
    avg_ranks: dict[str, float] | None = comparison.get("avg_ranks")
    nemenyi: dict[str, Any] | None = comparison.get("nemenyi")
    if not avg_ranks or not nemenyi or nemenyi.get("cd") is None:
        return None
    cd = float(nemenyi["cd"])

    # Models sorted best (lowest average rank) first.
    ordered = sorted(avg_ranks.items(), key=lambda kv: kv[1])
    names = [m for m, _ in ordered]
    ranks = [r for _, r in ordered]
    k = len(names)
    if k < 2:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lo = min(ranks)
    hi = max(ranks)
    pad = max(0.5, (hi - lo) * 0.1)
    axis_lo = np.floor(lo - pad)
    axis_hi = np.ceil(hi + pad)

    fig, ax = plt.subplots(figsize=(9.0, max(3.5, k * 0.4 + 2.5)))
    ax.set_xlim(axis_lo, axis_hi)
    ax.set_ylim(0.0, 1.0)
    ax.axis("off")

    axis_y = 0.82
    ax.plot([axis_lo, axis_hi], [axis_y, axis_y], color="black", linewidth=1.2)
    ticks = np.arange(int(axis_lo), int(axis_hi) + 1)
    for t in ticks:
        ax.plot([t, t], [axis_y, axis_y + 0.02], color="black", linewidth=1.0)
        ax.text(t, axis_y + 0.05, str(t), ha="center", va="bottom", fontsize=8)
    ax.text((axis_lo + axis_hi) / 2.0, axis_y + 0.12, "average rank (lower = better)",
            ha="center", va="bottom", fontsize=9)

    # Model markers: labels alternate left/right, dropping down from the axis.
    label_levels = np.linspace(0.62, 0.10, num=k)
    for idx, (name, rank) in enumerate(zip(names, ranks)):
        y = label_levels[idx]
        side_left = idx < k / 2.0
        edge = axis_lo if side_left else axis_hi
        ha = "right" if side_left else "left"
        ax.plot([rank, rank], [axis_y, y], color=_COLOR_SERIES[idx % len(_COLOR_SERIES)],
                linewidth=1.3)
        ax.plot([rank, edge], [y, y], color=_COLOR_SERIES[idx % len(_COLOR_SERIES)],
                linewidth=1.3)
        label = f"{name} ({rank:.2f})"
        ax.text(edge, y, f"{label} " if ha == "right" else f" {label}",
                ha=ha, va="center", fontsize=8)

    # CD bars: connect maximal runs of adjacent models within CD of each other.
    bar_y = axis_y - 0.06
    i = 0
    drawn = 0
    while i < k:
        j = i
        while j + 1 < k and (ranks[j + 1] - ranks[i]) < cd:
            j += 1
        if j > i:
            ax.plot([ranks[i] - 0.02, ranks[j] + 0.02], [bar_y - drawn * 0.03] * 2,
                    color="#333333", linewidth=3.0, solid_capstyle="round")
            drawn += 1
            i = j
        else:
            i += 1

    # CD scale bar (top-left) showing the critical difference magnitude.
    ax.plot([axis_lo, axis_lo + cd], [axis_y + 0.18, axis_y + 0.18],
            color="#333333", linewidth=2.0)
    ax.text(axis_lo + cd / 2.0, axis_y + 0.20, f"CD = {cd:.2f}",
            ha="center", va="bottom", fontsize=8)

    country = result["metadata"]["country"]
    n_blocks = comparison.get("n_blocks")
    ax.set_title(
        f"{country}: model critical-difference diagram "
        f"(Nemenyi, {n_blocks} category x method blocks)",
        fontsize=11, fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ------------------------------------------------------------------
# Factor-dominance bar (eta^2 variance shares)
# ------------------------------------------------------------------

def plot_factor_dominance(result: dict[str, Any], out_path: str | Path) -> Path | None:
    """Horizontal bars of the mixed model's eta^2 variance shares by factor.

    Shows how the fitted ``logit(TV) ~ model*method + (1|category)`` variance
    splits across ``model`` / ``method`` / ``category`` / ``residual`` (shares sum
    to 1). Returns ``None`` when the mixed fit did not converge or produced no
    decomposition (an eta^2 of ``None``), which the caller logs as a skip.
    """
    mixed: dict[str, Any] = result.get("overall", {}).get("mixed_logit", {})
    eta_sq: dict[str, float] | None = mixed.get("eta_sq")
    if not eta_sq:
        return None

    order = [k for k in ("model", "method", "category", "residual") if k in eta_sq]
    shares = [float(eta_sq[k]) for k in order]
    if not order or not any(s == s for s in shares):
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    positions = list(range(len(order)))[::-1]
    colors = {"model": "#4878CF", "method": "#D65F5F",
              "category": "#6AB187", "residual": "#BBBBBB"}

    fig, ax = plt.subplots(figsize=(8.0, max(2.6, len(order) * 0.55 + 1.4)))
    ax.barh(positions, shares, color=[colors.get(k, "#888888") for k in order],
            edgecolor="#33486F", linewidth=0.5, alpha=0.9, height=0.6)
    for pos, share in zip(positions, shares):
        ax.text(share, pos, f"  {share * 100:.1f}%", va="center", ha="left",
                fontsize=8, color="#333333")

    ax.set_yticks(positions)
    ax.set_yticklabels(order, fontsize=9)
    ax.set_xlabel("share of fitted variance (eta^2, approximate)", fontsize=9)
    ax.set_xlim(0.0, min(1.0, max(shares) * 1.2) if shares else 1.0)
    ax.grid(axis="x", linestyle=":", alpha=0.4)

    converged = mixed.get("converged")
    country = result["metadata"]["country"]
    suffix = "" if converged else "  (mixed fit did NOT converge -- descriptive only)"
    ax.set_title(
        f"{country}: factor dominance (variance share){suffix}",
        fontsize=11, fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path
