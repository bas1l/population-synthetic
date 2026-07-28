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

import logging
from pathlib import Path
from typing import Any

import numpy as np

from population_synthetic.analysis.method_significance.builder import (
    load_comparison_config,
    resolve_pairs,
    significance_cutoff,
)
from population_synthetic.analysis.model_ranking.loader import ComboPerformance
from population_synthetic.analysis.utils.figures import save_figure

logger = logging.getLogger(__name__)

_COLOR_SERIES = (
    "#4878CF",
    "#D65F5F",
    "#6AB187",
    "#E8935A",
    "#E9C46A",
    "#8172B2",
    "#64B5CD",
)


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
    """One TV(method) trend chart per attribute: x = the ordered methods, line per model.

    *records* supply the raw per-cell TV distances (the builder's serialisable
    output keeps only the derived slopes/tests, not the grid). Absent cells are
    left as gaps in the line, never imputed. The facet title reports the
    attribute's **BH-corrected** Page's-L p-value and flags significance from it.

    The x-axis order is read from the builder's ``metadata.method_order`` -- the
    renderer is a pure consumer of the resolved axis and never resolves an ordering
    of its own, so a chart cannot disagree with the statistics drawn on it.
    """
    attributes: list[str] = result["metadata"]["attributes"]
    models: list[str] = result["metadata"]["models"]
    method_order: list[str] = result["metadata"]["method_order"]
    alpha: float = result["metadata"]["alpha"]
    if not attributes or not models:
        return []

    by_cell = {(r.model, r.strategy): r for r in records}
    x = np.arange(len(method_order))

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
            for m in models for s in method_order if (m, s) in by_cell
        )
        if not any_point:
            continue

        fig, ax = plt.subplots(figsize=(max(7.0, len(method_order) * 1.4 + 2.0), 5.0))
        for m_idx, model in enumerate(models):
            ys = []
            for strategy in method_order:
                record = by_cell.get((model, strategy))
                ys.append(np.nan if record is None else _tv_distance(record, attr))
            ys = [np.nan if v is None else v for v in ys]
            ax.plot(
                x, ys, marker="o", markersize=5, linewidth=1.6,
                color=_COLOR_SERIES[m_idx % len(_COLOR_SERIES)], label=model, alpha=0.9,
            )

        ax.set_xticks(x)
        ax.set_xticklabels(method_order, rotation=25, ha="right", fontsize=8)
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


# ------------------------------------------------------------------
# Method-comparison figure (bars + points + significance brackets/stars)
# ------------------------------------------------------------------

# Separator for a method-pair key in ``pairwise_p`` (matches builder._pair_key).
_PAIR_SEP = "|"


def _p_to_stars(
    p: float | None,
    thresholds: list[dict[str, Any]],
    ns_symbol: str,
) -> str:
    """Map a p-value to its significance symbol (GraphPad/Prism convention).

    *thresholds* is the config's ``star_thresholds`` list of ``{"max_p", "symbol"}``
    entries; matched smallest-``max_p`` first (first match wins), so a p at or below
    the tightest cutoff earns the most stars. A ``None`` p, or a p above every
    threshold, maps to *ns_symbol*. This is a pure lookup -- it does **not** know how
    the p-value was computed.
    """
    if p is None:
        return ns_symbol
    for entry in sorted(thresholds, key=lambda e: float(e["max_p"])):
        if p <= float(entry["max_p"]):
            return str(entry["symbol"])
    return ns_symbol


def _draw_sig_bracket(
    ax,
    x1: float,
    x2: float,
    y: float,
    text: str,
    *,
    tick: float,
    color: str = "#333333",
    linewidth: float = 1.1,
    fontsize: float = 8.0,
) -> None:
    """Draw one significance bracket: a horizontal line spanning ``[x1, x2]`` at
    height *y* with short down-ticks of length *tick* at each end, and *text* (the
    star/``ns`` label) centred just above it. Height stacking is the caller's job
    (it passes a *y* that already clears lower brackets)."""
    ax.plot(
        [x1, x1, x2, x2],
        [y - tick, y, y, y - tick],
        color=color, linewidth=linewidth, solid_capstyle="round",
    )
    ax.text((x1 + x2) / 2.0, y, text, ha="center", va="bottom",
            fontsize=fontsize, color=color)


def _stack_bracket_levels(pairs_x: list[tuple[float, float]]) -> list[int]:
    """Assign each bracket a stacking level so overlapping spans never collide.

    *pairs_x* are the ``(x1, x2)`` horizontal spans (left < right) in draw order.
    Greedy interval-graph colouring: each bracket takes the lowest level whose
    already-placed spans do not horizontally overlap it (a small pad keeps adjacent
    brackets visually distinct). Returns a parallel list of integer levels
    (0 = lowest).
    """
    levels: list[list[tuple[float, float]]] = []
    assigned: list[int] = []
    pad = 0.05
    for x1, x2 in pairs_x:
        lo, hi = min(x1, x2), max(x1, x2)
        placed = False
        for lvl, occupied in enumerate(levels):
            if all(hi < o_lo - pad or lo > o_hi + pad for o_lo, o_hi in occupied):
                occupied.append((lo, hi))
                assigned.append(lvl)
                placed = True
                break
        if not placed:
            levels.append([(lo, hi)])
            assigned.append(len(levels) - 1)
    return assigned


def _panel_data_max(panel: dict[str, Any], methods: list[str]) -> float:
    """Highest plotted TV-similarity in a panel (means + individual points).

    Used to seat the lowest significance bracket above the data. Ignores absent
    (``None``/``NaN``) values; falls back to ``1.0`` when nothing is plottable.
    """
    values: list[float] = []
    for v in panel.get("means", {}).values():
        if v is not None and v == v:
            values.append(float(v))
    for row in panel.get("per_model", {}).values():
        for s in methods:
            v = row.get(s)
            if v is not None and v == v:
                values.append(float(v))
    return max(values) if values else 1.0


def _star_key_text(thresholds: list[dict[str, Any]], ns_symbol: str, pairs_mode: str) -> str:
    """Human-readable in-figure key defining the star symbols from config.

    The ``ns`` entry is included only when the *pairs_mode* can actually draw a
    non-significant bracket. Under ``significant-only`` no ``ns`` bracket is ever
    drawn, so the key omits ``ns`` and defines only ``* ** *** ****`` -- keeping the
    key accurate to what the figure shows.
    """
    parts: list[str] = []
    if pairs_mode != "significant-only":
        parts.append(f"{ns_symbol}: p>{max(float(e['max_p']) for e in thresholds):g}")
    for entry in sorted(thresholds, key=lambda e: float(e["max_p"]), reverse=True):
        parts.append(f"{entry['symbol']}: p≤{float(entry['max_p']):g}")
    return "   ".join(parts)


def _draw_method_panel(
    ax,
    panel: dict[str, Any],
    methods: list[str],
    pairs_mode: str,
    thresholds: list[dict[str, Any]],
    ns_symbol: str,
    title: str,
) -> None:
    """Render one comparison panel in-place on *ax*.

    Bars = per-method mean TV-similarity (order = *methods*), overlaid with the
    individual model points and faint paired lines (one polyline per model across
    methods). Significance brackets are drawn over the resolved pairs, each labelled
    by :func:`_p_to_stars` from the panel's ``pairwise_p``. A panel flagged
    ``insufficient_n`` renders a labelled placeholder instead (and the caller logs
    it). Purely consumes *panel* -- no statistics are recomputed here.
    """
    x = np.arange(len(methods))
    ax.set_xticks(x)
    ax.set_xticklabels(methods, rotation=25, ha="right", fontsize=7.5)
    ax.set_xlim(-0.6, len(methods) - 0.4)
    ax.set_ylabel("TV-similarity (higher = more faithful)", fontsize=8)
    ax.grid(axis="y", linestyle=":", alpha=0.35)

    n_models = panel.get("n_models", 0)
    if panel.get("insufficient_n"):
        ax.set_ylim(0.0, 1.0)
        ax.text(
            (len(methods) - 1) / 2.0, 0.5,
            f"insufficient n (n<3)\nn={n_models} complete model(s)",
            ha="center", va="center", fontsize=10, color="#B00020", fontweight="bold",
            bbox={"boxstyle": "round", "facecolor": "#FDECEC", "edgecolor": "#B00020"},
        )
        ax.set_title(title, fontsize=9.5, fontweight="bold")
        return

    means = panel.get("means", {})
    heights = [means.get(s) if means.get(s) is not None else 0.0 for s in methods]
    ax.bar(x, heights, width=0.62, color="#BFD1EA", edgecolor="#33486F",
           linewidth=0.6, zorder=1)

    # Individual model points + faint paired lines (the paired/blocked structure).
    per_model: dict[str, dict[str, float]] = panel.get("per_model", {})
    rng = np.random.default_rng(0)
    for model, row in per_model.items():
        ys = [row.get(s) for s in methods]
        ys = [np.nan if (v is None or v != v) else float(v) for v in ys]
        jitter = (rng.random(len(methods)) - 0.5) * 0.18
        ax.plot(x + jitter, ys, color="#8899AA", linewidth=0.6, alpha=0.35, zorder=2)
        ax.scatter(x + jitter, ys, s=14, color="#4878CF", alpha=0.75,
                   edgecolors="white", linewidths=0.4, zorder=3)

    # Significance brackets over the configured pairs.
    pairwise_p: dict[str, float] = panel.get("pairwise_p", {})
    # The significant-only cutoff is read from the config star thresholds (the '*'
    # cutoff), never a hardcoded literal; ignored by the non-filtering modes.
    pairs = resolve_pairs(
        methods, pairs_mode, pairwise_p=pairwise_p, alpha=significance_cutoff(thresholds)
    )
    idx = {s: j for j, s in enumerate(methods)}
    spans = [(float(idx[a]), float(idx[b])) for a, b in pairs if a in idx and b in idx]
    levels = _stack_bracket_levels(spans)

    data_max = _panel_data_max(panel, methods)
    base = max(data_max, max(heights) if heights else 0.0)
    gap = 0.05
    step = 0.075
    tick = 0.02
    top = base + gap
    for (a, b), (x1, x2), lvl in zip(pairs, spans, levels):
        p = pairwise_p.get(f"{a}{_PAIR_SEP}{b}")
        if p is None:
            p = pairwise_p.get(f"{b}{_PAIR_SEP}{a}")
        y = top + lvl * step
        _draw_sig_bracket(ax, x1, x2, y, _p_to_stars(p, thresholds, ns_symbol), tick=tick)

    top_used = top + (max(levels) if levels else 0) * step
    ax.set_ylim(0.0, max(1.0, top_used + step))

    omnibus = panel.get("omnibus", {})
    p_omni = omnibus.get("p")
    p_bh = omnibus.get("p_bh")
    if p_omni is None:
        omni_note = "Friedman: n/a"
    elif p_bh is not None:
        omni_note = f"Friedman p={p_omni:.3g} (BH {p_bh:.3g})"
    else:
        omni_note = f"Friedman p={p_omni:.3g}"
    # Header: model n and (for a category panel) the attribute's declared level
    # count from the block; the Overall panel spans all categories, so it has no
    # single level count and shows only the model n. Pure consumer -- the count is
    # computed in the builder (panel["n_category_values"]), never derived here.
    n_levels = panel.get("n_category_values")
    if n_levels is not None:
        count_note = f"n={n_models} models · {n_levels} levels"
    else:
        count_note = f"n={n_models} models"
    ax.set_title(f"{title}  ({count_note})\n{omni_note}", fontsize=9.5, fontweight="bold")


def plot_method_comparison(
    result: dict[str, Any],
    out_path: str | Path,
    *,
    overall_only: bool = False,
) -> Path | None:
    """Bars + points + significance-bracket comparison figure of TV-similarity by method.

    Pure consumer of ``result["method_comparison"]`` (the builder's serialised
    block): each panel is a demographic category (or ``overall``) drawn by
    :func:`_draw_method_panel` -- bars = per-method mean TV-similarity, individual
    model points + faint paired lines overlaid, pairwise significance brackets/stars
    over the configured pairs, the omnibus Friedman p + ``n`` in the panel title, and
    an in-figure star key. The renderer never recomputes a statistic nor discovers
    files.

    * ``overall_only=False`` -> a dynamically sized grid of every category panel plus
      ``overall``.
    * ``overall_only=True`` -> a single ``overall`` headline panel.

    The star thresholds are read from the block (``star_thresholds`` / ``ns_symbol``);
    if the block predates that echo they are loaded from the comparison config.
    Panels flagged ``insufficient_n`` (``n<3`` complete models) render a labelled
    placeholder and are logged (never a silent blank). Returns the PNG :class:`Path`
    (with an SVG sibling via :func:`save_figure`), or ``None`` when the block is
    absent/empty or nothing is plottable.
    """
    block: dict[str, Any] = result.get("method_comparison") or {}
    methods: list[str] = block.get("methods") or []
    panels: dict[str, Any] = block.get("panels") or {}
    if not methods or not panels:
        return None

    pairs_mode: str = block.get("pairs_mode", "adjacent")
    thresholds = block.get("star_thresholds")
    ns_symbol = block.get("ns_symbol")
    if not thresholds or not ns_symbol:
        cfg = load_comparison_config()
        thresholds = cfg["star_thresholds"]
        ns_symbol = cfg["ns_symbol"]

    country = result.get("metadata", {}).get("country", "")

    # Panel order: categories in block order, then Overall last.
    category_keys = [k for k in panels if k != "overall"]
    if overall_only:
        panel_keys = ["overall"] if "overall" in panels else []
    else:
        panel_keys = category_keys + (["overall"] if "overall" in panels else [])
    if not panel_keys:
        return None

    for key in panel_keys:
        if panels[key].get("insufficient_n"):
            logger.warning(
                "method_comparison panel %r has insufficient n (n=%s < 3 complete "
                "models); rendering placeholder.", key, panels[key].get("n_models"),
            )

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n_panels = len(panel_keys)
    if overall_only:
        ncols, nrows = 1, 1
    else:
        ncols = min(3, n_panels)
        nrows = int(np.ceil(n_panels / ncols))

    fig, axes = plt.subplots(
        nrows, ncols,
        figsize=(max(6.0, ncols * 4.6), max(4.6, nrows * 4.0)),
        squeeze=False,
    )
    flat = axes.flatten()

    for ax, key in zip(flat, panel_keys):
        label = "Overall" if key == "overall" else key
        _draw_method_panel(ax, panels[key], methods, pairs_mode, thresholds, ns_symbol, label)
    for ax in flat[n_panels:]:
        ax.axis("off")

    headline = f"{country}: method comparison on TV-similarity (models as blocks)"
    if overall_only:
        headline += " -- Overall"
    fig.suptitle(headline, fontsize=12, fontweight="bold")

    key_text = _star_key_text(thresholds, ns_symbol, pairs_mode)
    fig.text(0.5, 0.005, "key -- " + key_text, ha="center", va="bottom", fontsize=8,
             color="#333333")

    fig.tight_layout(rect=(0.0, 0.03, 1.0, 0.97))
    return save_figure(fig, Path(out_path), dpi=150)
