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
  (model vs method vs category vs residual) from ``overall.mixed_logit.eta_sq``;
* a **method x method pairwise-significance grid** per attribute panel (plus
  ``overall``) -- the square view of the same pairwise comparisons the bracket
  figure draws only a configured subset of. Fill = the significance tier, text =
  the signed row-minus-column difference, both read from the panel's own
  ``pair_matrix`` block.

Faithful-visualisation rules (per the statistical-software guide, §7): the raw
data is shown, not silently dropped; absent cells are drawn as gaps (masked), not
zeros; significance is annotated only from the **corrected** p-values; every chart
returns ``None`` (logged as a skip by the caller) when its data is genuinely
empty rather than emitting a misleading empty axes.

Follows the project charting conventions (deferred ``Agg`` matplotlib import,
persistence delegated to ``analysis/utils/figures.py::save_figure``, which writes
the PNG+SVG+EPS trio and closes the figure).
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
from population_synthetic.analysis.utils.grid_annotations import (
    SignedValuePolicy,
    SignedValueWithStarsPolicy,
)
from population_synthetic.analysis.utils.grid_variants import (
    CANONICAL_VARIANT,
    COUNTED_VARIANT,
    GridVariant,
    variant_map,
    variant_suffixes,
)
from population_synthetic.analysis.utils.grids import render_grid
from population_synthetic.analysis.utils.labels import (
    attribute_label,
    country_label,
    method_key_lines,
    method_letters,
    model_labels,
)
from population_synthetic.analysis.utils.palette import (
    ANNOTATION_GREY,
    BAR_EDGE,
    CATEGORICAL_SERIES,
    FAINT_LINK,
    GRID_RULE,
    MUTED_GREY,
    PALE_FILL,
    RESIDUAL_GREY,
    SURFACE,
    WARNING_FILL,
    WARNING_TEXT,
    heatmap_cmap,
    heatmap_levels,
    opaque,
    text_color_on,
)
from population_synthetic.analysis.utils.style import (
    ANNOTATION,
    ANNOTATION_LARGE,
    AXIS_TITLE,
    CALLOUT,
    CAPTION_MARGIN_IN,
    DOUBLE,
    FIGURE_TITLE,
    FULL,
    HEADING_WEIGHT,
    LEGEND_LABEL,
    LEGEND_TITLE,
    LINE_SPACING,
    PANEL_TITLE,
    POINTS_PER_INCH,
    TICK_LABEL,
    TICK_LABEL_LARGE,
    caption_block,
    figure_size,
    grow_height,
    grow_width,
    house_style,
    wrap_to_width,
)
from population_synthetic.analysis.utils.table_style import categories_on_top, fit_to_page

logger = logging.getLogger(__name__)


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

@house_style
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
    # Letters on the method axis with the key printed beneath each facet; the legend
    # carries the models' display names. Neither axis prints a config id.
    letters = method_letters(method_order)
    method_key = "Methods:  " + "   ".join(method_key_lines(method_order))
    display_models = model_labels(models)

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

        fig, ax = plt.subplots(
            figsize=figure_size(grow_width(len(method_order), per_item=1.4, padding=2.0, minimum=7.0), 5.0),
        )
        for m_idx, model in enumerate(models):
            ys = []
            for strategy in method_order:
                record = by_cell.get((model, strategy))
                ys.append(np.nan if record is None else _tv_distance(record, attr))
            ys = [np.nan if v is None else v for v in ys]
            ax.plot(
                x, ys, marker="o", markersize=5, linewidth=1.6,
                color=opaque(CATEGORICAL_SERIES[m_idx % len(CATEGORICAL_SERIES)], 0.9),
                label=display_models[model],
            )

        ax.set_xticks(x)
        ax.set_xticklabels([letters[s] for s in method_order], fontsize=TICK_LABEL)
        ax.set_xlabel("generation method (simplest -> most complex)", fontsize=AXIS_TITLE)
        ax.set_ylabel("TV distance (lower = better fidelity)", fontsize=AXIS_TITLE)
        ax.grid(axis="y", linestyle=":", color=GRID_RULE)
        ax.legend(fontsize=LEGEND_LABEL, title="model", title_fontsize=LEGEND_TITLE)

        method = result["per_attribute"][attr]["method_trend"]
        p_bh = method.get("p_bh")
        if p_bh is None:
            trend_note = "Page L (BH): n/a"
        else:
            flag = "significant" if p_bh < alpha else "n.s."
            trend_note = f"Page L trend (BH-adj p = {p_bh:.3g}, {flag})"
        ax.set_title(
            f"{country_label(country)}: {attribute_label(attr)} -- TV by method, per model\n{trend_note}",
            fontsize=PANEL_TITLE, fontweight="bold",
        )
        caption_block(fig, method_key, fontsize=ANNOTATION)
        fit_to_page(fig)
        written.append(save_figure(fig, out_dir / f"{attr}_method_trend.png"))

    return written


# ------------------------------------------------------------------
# Slope heatmap (attribute x model) -- descriptive interaction view
# ------------------------------------------------------------------

#: The slope grid's cell annotation. The sign is not decoration: the house ramp is
#: sequential and orders cells by magnitude alone, so two slopes of equal size and
#: opposite direction are drawn differently and neither drawing says which was which.
#: The printed sign, the colourbar label and the rule at zero are the only places the
#: direction appears.
_SLOPE_CELL_POLICY = SignedValuePolicy(value_key="value", scale=1.0, number_format=".3f")


@house_style
def plot_slope_heatmap(result: dict[str, Any], out_path: str | Path) -> Path | None:
    """Attribute x model heatmap of the descriptive TV(method) trend slope.

    Cell = the per-(attribute, model) OLS slope of TV distance on method rank
    (positive = fidelity worsens with complexity, negative = improves). This is
    the *descriptive* per-category interaction: **no p-value is claimed at this
    grain** (n = 1 per cell), so no significance stars are drawn. Absent slopes
    render as grey gaps.

    The sign is carried by the ``+``/``-`` on every cell, by the colourbar label and
    by the rule drawn at zero on the colourbar -- **not** by the colour. The house
    sequential ramp orders cells by magnitude, so two slopes of equal size and
    opposite sign are drawn differently and neither drawing says which was which.
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

    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    masked = np.ma.masked_invalid(values)
    finite = masked.compressed()
    bound = float(np.max(np.abs(finite))) if finite.size else 1.0
    bound = bound if bound > 0 else 1.0

    fig, ax = plt.subplots(
        figsize=(
            grow_width(len(models), per_item=0.9, padding=3.0, minimum=6.0),
            grow_height(len(attributes), per_item=0.45, padding=2.5, minimum=4.0),
        ),
    )
    # The house sequential ramp, on limits kept symmetric about zero so a slope of zero
    # always lands at the same point of the ramp across figures. The ramp orders by
    # magnitude, not by sign, so the sign is carried by the signed cell annotations, the
    # colourbar label and the rule drawn at zero below -- never by the colour.
    cells = [
        [None if np.isnan(value) else {"value": float(value)} for value in row]
        for row in values
    ]
    im = render_grid(
        ax, values, cells,
        policy=_SLOPE_CELL_POLICY, cmap=heatmap_cmap(),
        norm=mcolors.Normalize(vmin=-bound, vmax=bound),
        aspect="auto", fontsize=ANNOTATION, interpolation="none",
    )

    ax.set_xticks(range(len(models)))
    display_models = model_labels(models)
    ax.set_xticklabels(
        [display_models[m] for m in models], rotation=40, ha="right", fontsize=TICK_LABEL,
    )
    ax.set_yticks(range(len(attributes)))
    ax.set_yticklabels([attribute_label(a) for a in attributes], fontsize=TICK_LABEL)

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("TV(method) slope (+ = worsens, - = improves)", fontsize=AXIS_TITLE)
    cbar.ax.axhline(0.0, color=text_color_on(im, 0.0), linewidth=2.0)

    country = result["metadata"]["country"]
    ax.set_title(
        f"{country_label(country)}: per-category TV(method) trend slope "
        f"(descriptive; n=1 per cell)",
        fontsize=PANEL_TITLE, fontweight="bold",
    )
    fig.tight_layout()
    fit_to_page(fig)
    return save_figure(fig, out_path)


# ------------------------------------------------------------------
# Critical-difference (CD) diagram for models (Demšar 2006)
# ------------------------------------------------------------------

@house_style
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
    display_models = model_labels(names)

    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lo = min(ranks)
    hi = max(ranks)
    pad = max(0.5, (hi - lo) * 0.1)
    axis_lo = np.floor(lo - pad)
    axis_hi = np.ceil(hi + pad)

    fig, ax = plt.subplots(figsize=(FULL, grow_height(k, per_item=0.4, padding=2.5, minimum=3.5)))
    ax.set_xlim(axis_lo, axis_hi)
    ax.set_ylim(0.0, 1.0)
    ax.axis("off")

    axis_y = 0.82
    ax.plot([axis_lo, axis_hi], [axis_y, axis_y], color="black", linewidth=1.2)
    ticks = np.arange(int(axis_lo), int(axis_hi) + 1)
    for t in ticks:
        ax.plot([t, t], [axis_y, axis_y + 0.02], color="black", linewidth=1.0)
        ax.text(t, axis_y + 0.05, str(t), ha="center", va="bottom", fontsize=ANNOTATION)
    ax.text((axis_lo + axis_hi) / 2.0, axis_y + 0.12, "average rank (lower = better)",
            ha="center", va="bottom", fontsize=ANNOTATION_LARGE)

    # Model markers: labels alternate left/right, dropping down from the axis.
    label_levels = np.linspace(0.62, 0.10, num=k)
    for idx, (name, rank) in enumerate(zip(names, ranks)):
        y = label_levels[idx]
        side_left = idx < k / 2.0
        edge = axis_lo if side_left else axis_hi
        ha = "right" if side_left else "left"
        ax.plot([rank, rank], [axis_y, y], color=CATEGORICAL_SERIES[idx % len(CATEGORICAL_SERIES)],
                linewidth=1.3)
        ax.plot([rank, edge], [y, y], color=CATEGORICAL_SERIES[idx % len(CATEGORICAL_SERIES)],
                linewidth=1.3)
        label = f"{display_models[name]} ({rank:.2f})"
        ax.text(edge, y, f"{label} " if ha == "right" else f" {label}",
                ha=ha, va="center", fontsize=ANNOTATION)

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
                    color=ANNOTATION_GREY, linewidth=3.0, solid_capstyle="round")
            drawn += 1
            i = j
        else:
            i += 1

    # CD scale bar (top-left) showing the critical difference magnitude.
    ax.plot([axis_lo, axis_lo + cd], [axis_y + 0.18, axis_y + 0.18],
            color=ANNOTATION_GREY, linewidth=2.0)
    ax.text(axis_lo + cd / 2.0, axis_y + 0.20, f"CD = {cd:.2f}",
            ha="center", va="bottom", fontsize=ANNOTATION)

    country = result["metadata"]["country"]
    n_blocks = comparison.get("n_blocks")
    ax.set_title(
        f"{country_label(country)}: model critical-difference diagram "
        f"(Nemenyi, {n_blocks} category x method blocks)",
        fontsize=PANEL_TITLE, fontweight="bold",
    )
    fig.tight_layout()
    fit_to_page(fig)
    return save_figure(fig, out_path)


# ------------------------------------------------------------------
# Factor-dominance bar (eta^2 variance shares)
# ------------------------------------------------------------------

@house_style
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

    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    positions = list(range(len(order)))[::-1]
    colors = {"model": CATEGORICAL_SERIES[0], "method": CATEGORICAL_SERIES[1],
              "category": CATEGORICAL_SERIES[2], "residual": RESIDUAL_GREY}

    fig, ax = plt.subplots(figsize=(FULL, grow_height(len(order), per_item=0.55, padding=1.4, minimum=2.6)))
    ax.barh(positions, shares, color=[opaque(colors.get(k, MUTED_GREY), 0.9) for k in order],
            edgecolor=BAR_EDGE, linewidth=0.5, height=0.6)
    for pos, share in zip(positions, shares):
        ax.text(share, pos, f"  {share * 100:.1f}%", va="center", ha="left",
                fontsize=ANNOTATION, color=ANNOTATION_GREY)

    ax.set_yticks(positions)
    ax.set_yticklabels(order, fontsize=TICK_LABEL_LARGE)
    ax.set_xlabel("share of fitted variance (eta^2, approximate)", fontsize=AXIS_TITLE)
    ax.set_xlim(0.0, min(1.0, max(shares) * 1.2) if shares else 1.0)
    ax.grid(axis="x", linestyle=":", color=GRID_RULE)

    converged = mixed.get("converged")
    country = result["metadata"]["country"]
    suffix = "" if converged else "  (mixed fit did NOT converge -- descriptive only)"
    ax.set_title(
        f"{country_label(country)}: factor dominance (variance share){suffix}",
        fontsize=PANEL_TITLE, fontweight="bold",
    )
    fig.tight_layout()
    fit_to_page(fig)
    return save_figure(fig, out_path)


# ------------------------------------------------------------------
#: Display names for the omnibus tests the builder can run. Keyed by the panel's
#: ``omnibus["test"]`` so the figure reports the test that actually produced the
#: p-value; an unknown id falls through to the raw id rather than a wrong name.
_OMNIBUS_LABELS = {
    "rm_anova": "Repeated-measures ANOVA",
    "friedman": "Friedman",
}


def _omnibus_note(omnibus: dict[str, Any]) -> str:
    """The panel's omnibus line: the test the builder ran, its p, and its BH sibling.

    The test NAME comes from the panel, never from a literal at the call site: the
    builder decides which omnibus it ran, and a hardcoded label silently mislabels the
    number the moment that changes. It did -- a panel title read "Friedman" while
    showing a repeated-measures ANOVA p, which is a wrong name on a right number.

    Shared by every figure in this module that prints the line, so two figures drawn
    from the same panel can never report it differently. Reads the panel; derives no
    p-value, no correction and no verdict.
    """
    label = _OMNIBUS_LABELS.get(omnibus.get("test"), omnibus.get("test") or "omnibus")
    p = omnibus.get("p")
    if p is None:
        return f"{label}: n/a"
    p_bh = omnibus.get("p_bh")
    if p_bh is not None:
        return f"{label} p={p:.3g} (BH {p_bh:.3g})"
    return f"{label} p={p:.3g}"


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
    color: str = ANNOTATION_GREY,
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


def _star_key_text(
    thresholds: list[dict[str, Any]],
    ns_symbol: str,
    *,
    include_ns: bool,
) -> str:
    """Human-readable in-figure key defining the star symbols from config.

    *include_ns* is the caller's statement of whether its own figure can show a
    non-significant result at all. The bracket figure under ``significant-only``
    never draws one, so its key defines only ``* ** *** ****``; the pair grid paints
    the ``ns`` tier in every cell that earned it, so its key has to define it. The
    key stays accurate to what the figure shows, and this function stays ignorant of
    what a pairs mode is.
    """
    parts: list[str] = []
    if include_ns:
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
    # Letters, not ids: three panels sit side by side at the printable cap, so the
    # method axis has no room for a phrase. The key is printed once for the figure.
    letters = method_letters(methods)
    ax.set_xticklabels([letters[s] for s in methods], fontsize=TICK_LABEL)
    ax.set_xlim(-0.6, len(methods) - 0.4)
    ax.set_ylabel("TV-similarity (higher = more faithful)", fontsize=AXIS_TITLE)
    ax.grid(axis="y", linestyle=":", color=GRID_RULE)

    n_models = panel.get("n_models", 0)
    if panel.get("insufficient_n"):
        ax.set_ylim(0.0, 1.0)
        ax.text(
            (len(methods) - 1) / 2.0, 0.5,
            f"insufficient n (n<3)\nn={n_models} complete model(s)",
            ha="center", va="center", fontsize=CALLOUT, color=WARNING_TEXT, fontweight="bold",
            bbox={"boxstyle": "round", "facecolor": WARNING_FILL, "edgecolor": WARNING_TEXT},
        )
        ax.set_title(title, fontsize=PANEL_TITLE, fontweight="bold")
        return

    means = panel.get("means", {})
    heights = [means.get(s) if means.get(s) is not None else 0.0 for s in methods]
    ax.bar(x, heights, width=0.62, color=PALE_FILL, edgecolor=BAR_EDGE,
           linewidth=0.6, zorder=1)

    # Individual model points + faint paired lines (the paired/blocked structure).
    per_model: dict[str, dict[str, float]] = panel.get("per_model", {})
    rng = np.random.default_rng(0)
    for model, row in per_model.items():
        ys = [row.get(s) for s in methods]
        ys = [np.nan if (v is None or v != v) else float(v) for v in ys]
        jitter = (rng.random(len(methods)) - 0.5) * 0.18
        ax.plot(x + jitter, ys, color=FAINT_LINK, linewidth=0.6, zorder=2)
        ax.scatter(x + jitter, ys, s=14, color=opaque(CATEGORICAL_SERIES[0], 0.75),
                   edgecolors=SURFACE, linewidths=0.4, zorder=3)

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

    omni_note = _omnibus_note(panel.get("omnibus", {}))
    # Header: model n and (for a category panel) the attribute's declared level
    # count from the block; the Overall panel spans all categories, so it has no
    # single level count and shows only the model n. Pure consumer -- the count is
    # computed in the builder (panel["n_category_values"]), never derived here.
    n_levels = panel.get("n_category_values")
    if n_levels is not None:
        count_note = f"n={n_models} models · {n_levels} levels"
    else:
        count_note = f"n={n_models} models"
    ax.set_title(f"{title}  ({count_note})\n{omni_note}", fontsize=PANEL_TITLE, fontweight="bold")


@house_style
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
    over the configured pairs, the omnibus p (labelled by the test the builder
    actually ran, via ``_OMNIBUS_LABELS``) + ``n`` in the panel title, and
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

    import matplotlib.pyplot as plt

    n_panels = len(panel_keys)
    if overall_only:
        ncols, nrows = 1, 1
    else:
        ncols = min(3, n_panels)
        nrows = int(np.ceil(n_panels / ncols))

    fig, axes = plt.subplots(
        nrows,
        ncols,
        figsize=(
            grow_width(ncols, per_item=4.6, padding=0.0, minimum=6.0),
            grow_height(nrows, per_item=4.0, padding=0.0, minimum=4.6),
        ),
        squeeze=False,
    )
    flat = axes.flatten()

    for ax, key in zip(flat, panel_keys):
        label = "Overall" if key == "overall" else attribute_label(key)
        _draw_method_panel(ax, panels[key], methods, pairs_mode, thresholds, ns_symbol, label)
    for ax in flat[n_panels:]:
        ax.axis("off")

    headline = (
        f"{country_label(country)}: method comparison on TV-similarity (models as blocks)"
    )
    if overall_only:
        headline += " -- Overall"

    # Both figure-level strings are wrapped to the paper before they are drawn, and the
    # strips they need are then reserved from the measured line counts. Wrapping after
    # the layout would be too late: `tight_layout` does not account for a suptitle, so a
    # second line would grow down into the panels it was supposed to sit above.
    figure_width, figure_height = (float(v) for v in fig.get_size_inches())
    usable = figure_width - 2 * CAPTION_MARGIN_IN
    headline = wrap_to_width(
        headline, usable, fontsize=FIGURE_TITLE, weight=HEADING_WEIGHT,
    )
    key_text = _star_key_text(
        thresholds, ns_symbol, include_ns=pairs_mode != "significant-only",
    )
    key_block = wrap_to_width(
        "Methods:  " + "   ".join(method_key_lines(methods)) + "      key -- " + key_text,
        usable, fontsize=ANNOTATION,
    )

    def _strip(text: str, fontsize: float) -> float:
        """Fraction of the canvas height a wrapped block of *text* occupies."""
        lines = text.count(chr(10)) + 1
        return (lines * fontsize * LINE_SPACING + POINTS_PER_INCH * CAPTION_MARGIN_IN) / (
            POINTS_PER_INCH * figure_height
        )

    fig.suptitle(headline, fontsize=FIGURE_TITLE, fontweight=HEADING_WEIGHT)
    fig.text(
        0.5, CAPTION_MARGIN_IN / figure_height, key_block,
        ha="center", va="bottom", fontsize=ANNOTATION, color=ANNOTATION_GREY,
    )

    fig.tight_layout(rect=(
        0.0, _strip(key_block, ANNOTATION), 1.0, 1.0 - _strip(headline, FIGURE_TITLE),
    ))
    fit_to_page(fig)
    return save_figure(fig, Path(out_path))


# ------------------------------------------------------------------
# Method x method pairwise-significance grids (one per attribute panel)
# ------------------------------------------------------------------

#: The camera-ready variant, published at the bare filename: the signed difference and
#: the symbol qualifying it, one step up the house scale. The paired-block count it
#: drops is not lost -- it is in the comparison JSON, in the pairwise CSV and in the
#: counted sibling beside it -- so this variant costs ink rather than evidence.
GRID_VARIANT_CLEAN = GridVariant(
    name=CANONICAL_VARIANT,
    policy=SignedValueWithStarsPolicy(value_key="value", stars_key="stars"),
    cell_clause=(
        "Cell: the row method's mean TV-similarity minus the column method's, over the "
        "models that entered this panel's test, with the significance symbol of the "
        "Holm-corrected pairwise test beneath it."
    ),
    fontsize=ANNOTATION_LARGE,
    linespacing=None,
)

#: The counted sibling: the same two lines over the number of paired model blocks the
#: test rested on. Written to ``..._with_counts``, so nothing this figure ever printed
#: is lost.
GRID_VARIANT_WITH_COUNTS = GridVariant(
    name=COUNTED_VARIANT,
    policy=SignedValueWithStarsPolicy(
        value_key="value", stars_key="stars", count_key="n",
    ),
    cell_clause=(
        "Cell: the row method's mean TV-similarity minus the column method's, with the "
        "significance symbol of the Holm-corrected pairwise test beneath it, printed "
        "over the number of paired model blocks that test used."
    ),
    fontsize=ANNOTATION,
    linespacing=1.35,
)

#: The publishable variants by name, so a driver enumerates them instead of naming them.
#: The clean one is first because it is the one published at the bare filename.
GRID_VARIANTS: dict[str, GridVariant] = variant_map(
    GRID_VARIANT_CLEAN, GRID_VARIANT_WITH_COUNTS,
)


def _star_ladder(thresholds: list[dict[str, Any]], ns_symbol: str) -> list[str]:
    """The significance symbols as an ordered ladder, most significant first.

    ``["****", "***", "**", "*", "ns"]`` on the current config -- the config's own
    thresholds sorted by their cutoff, with the ``ns`` symbol as the final rung. Its
    *length* is the number of discrete colour levels the grid paints, so a threshold
    added to config adds a level without any figure being edited.

    A rung's index is the position the grid paints, and it is resolved from the symbol
    :func:`_p_to_stars` returned -- not from a second binning of the p-value. That is
    deliberate: the fill and the printed symbol then come from one lookup and cannot
    disagree at a cutoff, where the config's rule (``p <= max_p``) and a half-open
    colour bin would otherwise place ``p = 0.05`` on opposite sides.
    """
    ordered = [
        str(entry["symbol"])
        for entry in sorted(thresholds, key=lambda e: float(e["max_p"]))
    ]
    return ordered + [ns_symbol]


def _pair_grid(
    panel_key: str,
    methods: list[str],
    pair_matrix: dict[str, Any],
    thresholds: list[dict[str, Any]],
    ns_symbol: str,
    ladder: list[str],
) -> tuple[np.ndarray, list[list[dict[str, Any] | None]]]:
    """The painted tier matrix and the cell records for one panel's square.

    Three cell states, and keeping them apart is the whole point of the figure:

    * the **diagonal** -- ``np.nan`` value *and* ``None`` record, so it takes the
      colormap's unpainted fill and carries no text at all;
    * an **untested** off-diagonal pair (the panel stored no corrected p for it) --
      ``np.nan`` value with a record whose value is ``None``, so it takes the same
      unpainted fill but prints the policy's ``absent_text``. Painting it at the palest
      tier instead would present "never tested" as "tested, not significant";
    * a **tested** pair -- painted at its tier's rung and printed with the stored
      difference, symbol and block count.

    Nothing is computed here. The tier is :func:`_p_to_stars`, which is a config
    lookup; the difference, the count and the p arrive oriented from the builder's
    ``pair_matrix`` and are read at ``(i, j)`` verbatim, sign included.

    Raises:
        ValueError: If a pair carries a corrected p but no difference. That cell would
            be painted at a tier while printing the mark reserved for a pair that was
            never tested, which is a figure contradicting itself.
    """
    p_holm = pair_matrix["p_holm"]
    mean_diff = pair_matrix["mean_diff"]
    n_blocks = pair_matrix["n_blocks"]
    k = len(methods)
    values = np.full((k, k), np.nan)
    cells: list[list[dict[str, Any] | None]] = [[None] * k for _ in range(k)]
    for i in range(k):
        for j in range(k):
            if i == j:
                continue
            p = p_holm[i][j]
            if p is None:
                cells[i][j] = {"value": None, "stars": None, "n": None}
                continue
            difference = mean_diff[i][j]
            if difference is None:
                raise ValueError(
                    f"panel {panel_key!r}: the pair {methods[i]!r} vs {methods[j]!r} "
                    f"carries a corrected p of {p!r} but no mean difference. A painted "
                    "cell has to print the value its tier qualifies; there is nothing "
                    "for this one to print."
                )
            symbol = _p_to_stars(float(p), thresholds, ns_symbol)
            values[i, j] = float(ladder.index(symbol))
            cells[i][j] = {
                "value": float(difference),
                "stars": symbol,
                "n": n_blocks[i][j],
            }
    return values, cells


def _draw_pair_placeholder(ax, note: str) -> None:
    """Fill *ax* with the panel's own explanation of why there is no square to draw.

    *note* is read from the panel block. The wording is the builder's -- how many
    complete models it found and what it needed -- and is never authored here: a caveat
    restated in a renderer is a caveat that drifts from the rule that produced it.
    """
    ax.axis("off")
    ax.text(
        0.5, 0.5, note,
        transform=ax.transAxes, ha="center", va="center",
        fontsize=CALLOUT, color=WARNING_TEXT, fontweight="bold",
        bbox={"boxstyle": "round", "facecolor": WARNING_FILL, "edgecolor": WARNING_TEXT},
    )


@house_style
def plot_method_pair_significance(
    result: dict[str, Any],
    out_dir: str | Path,
) -> list[Path]:
    """One method x method significance square per attribute panel, in both variants.

    The bracket figure (:func:`plot_method_comparison`) draws only the pairs its
    configured ``pairs_mode`` selects -- four of ten on the live five-method axis. Every
    pair is nonetheless computed and Holm-corrected across the whole family, and this
    figure is the square that shows all of them at once, one file per demographic
    category plus the pooled ``overall`` panel.

    **The renderer claims no p-value of its own and performs no arithmetic.** Both
    channels are read from the panel's ``pair_matrix`` block, whose ``mean_diff`` is
    already oriented row-minus-column by ``builder._method_panel`` -- the sign
    convention's only home. Nothing here negates, re-signs or re-derives a cell.

    Two channels, deliberately different: the **fill** is the pair's significance tier,
    which is symmetric across the diagonal, and the **text** is the signed difference,
    which is antisymmetric. Direction therefore travels in the annotation, on the house
    sequential ramp binned to the config's own star ladder
    (:func:`~population_synthetic.analysis.utils.palette.heatmap_levels`), rather than
    in a diverging hue -- the mechanism the 2026-08-12 ADR chose. Because p ascends
    while the ramp brightens, the most significant tier is darkest and ``ns`` palest.

    A panel flagged ``insufficient_n`` renders a labelled placeholder carrying the
    panel's own note, and is logged (never a silent blank or a missing file).

    Args:
        result: The built analysis (``builder.build_method_significance``).
        out_dir: Directory for the figures. One stem per panel, at the panel's key, with
            the variant suffix appended by
            :func:`~population_synthetic.analysis.utils.grid_variants.variant_suffixes`.

    Returns:
        The written PNG paths (each with its SVG and EPS siblings), in panel order and,
        within a panel, in the variant map's own order. Empty when the block carries no
        panels or the metadata declares no method axis.
    """
    block: dict[str, Any] = result.get("method_comparison") or {}
    panels: dict[str, Any] = block.get("panels") or {}
    if not panels:
        return []

    metadata: dict[str, Any] = result.get("metadata", {})
    attributes: list[str] = metadata.get("attributes") or []
    order = [attr for attr in attributes if attr in panels]
    if "overall" in panels:
        order.append("overall")
    if not order:
        return []

    method_order: list[str] = metadata.get("method_order") or []
    if not method_order:
        return []
    # Letters are absolute over the run's whole method axis, so this square reads
    # against every other figure in the process rather than being renumbered locally.
    letters = method_letters(method_order)
    method_key = "Methods:  " + "   ".join(method_key_lines(method_order))

    thresholds = block.get("star_thresholds")
    ns_symbol = block.get("ns_symbol")
    if not thresholds or not ns_symbol:
        cfg = load_comparison_config()
        thresholds = cfg["star_thresholds"]
        ns_symbol = cfg["ns_symbol"]
    ladder = _star_ladder(thresholds, ns_symbol)
    star_key = "Significance:  " + _star_key_text(thresholds, ns_symbol, include_ns=True)

    # The two readings the fill alone cannot carry, stated once for every panel: which
    # way the sign points, and that an unpainted cell is not a pale one.
    absent_mark = GRID_VARIANT_CLEAN.policy.absent_text
    sign_note = (
        "Rows and columns are the same methods in the same order. A positive cell means "
        "the ROW method scored closer to the real population than the column method; a "
        "negative one, the reverse."
    )
    state_note = (
        "Fill is the pair's significance tier, so it reads the same either side of the "
        f"diagonal. An unpainted cell printing {absent_mark} is a pair that was never "
        "tested, which is not the same finding as a pair tested and reported "
        f"{ns_symbol} (the palest painted tier). The unpainted diagonal prints nothing: "
        "it is a method against itself."
    )

    country = metadata.get("country", "")

    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # One discrete level per rung of the config's ladder, and a norm whose bins are those
    # rungs. Neither the level count nor the tier a cell lands in is a literal here: both
    # follow the config's thresholds.
    cmap = heatmap_levels(len(ladder))
    norm = mcolors.BoundaryNorm(np.arange(len(ladder) + 1) - 0.5, len(ladder))

    written: list[Path] = []
    for panel_key in order:
        panel: dict[str, Any] = panels[panel_key]
        pair_matrix: dict[str, Any] = panel["pair_matrix"]
        methods: list[str] = pair_matrix["methods"]
        if not methods:
            continue
        unknown = [s for s in methods if s not in letters]
        if unknown:
            raise ValueError(
                f"panel {panel_key!r} compares the method(s) {unknown}, which the run's "
                f"method axis {method_order} does not declare; the square's letters "
                "would not be the ones every other figure in this process prints."
            )

        insufficient = bool(panel.get("insufficient_n"))
        note = panel.get("note")
        values: np.ndarray | None = None
        cells: list[list[dict[str, Any] | None]] | None = None
        if insufficient:
            if not note:
                raise ValueError(
                    f"panel {panel_key!r} is flagged insufficient_n but carries no "
                    "'note'. The placeholder's wording is the builder's statement of "
                    "what it found, and this renderer does not author one."
                )
            logger.warning(
                "method pair-significance panel %r has insufficient n (n=%s complete "
                "model(s)); rendering placeholder: %s",
                panel_key, panel.get("n_models"), note,
            )
        else:
            values, cells = _pair_grid(
                panel_key, methods, pair_matrix, thresholds, ns_symbol, ladder,
            )

        label = "Overall" if panel_key == "overall" else attribute_label(panel_key)
        title = (
            f"{country_label(country)}: {label} -- pairwise method significance\n"
            f"{_omnibus_note(panel.get('omnibus', {}))}  "
            f"(n={panel.get('n_models', 0)} models)"
        )
        k = len(methods)

        def _draw(variant: GridVariant):
            """One publication of this panel. Only the cell text differs between them."""
            fig, ax = plt.subplots(
                figsize=(
                    grow_width(k, per_item=0.85, padding=3.6, minimum=DOUBLE),
                    grow_height(k, per_item=0.45, padding=3.9, minimum=4.8),
                ),
            )
            if values is None:
                _draw_pair_placeholder(ax, note)
            else:
                im = render_grid(
                    ax, values, cells,
                    policy=variant.policy, cmap=cmap, norm=norm,
                    aspect="equal", interpolation="none",
                    fontsize=variant.fontsize, linespacing=variant.linespacing,
                )
                categories_on_top(ax, [letters[s] for s in methods])
                ax.set_yticks(range(k))
                ax.set_yticklabels([letters[s] for s in methods], fontsize=TICK_LABEL)
                # Ticked with the symbols, not with the cutoffs: the swatch a reader
                # matches a cell to is the one whose star string that cell prints.
                cbar = fig.colorbar(
                    im, ax=ax, fraction=0.03, pad=0.02, ticks=range(len(ladder)),
                )
                cbar.ax.set_yticklabels(ladder, fontsize=TICK_LABEL)
                cbar.set_label("pairwise significance tier", fontsize=AXIS_TITLE)
                # The colourbar anchors its parent east, which on an equal-aspect square
                # leaves every spare inch of the canvas in one margin. Centring spends it
                # evenly instead, so the grid sits under the title it belongs to.
                ax.set_anchor("C")
            ax.set_title(title, fontsize=PANEL_TITLE, fontweight="bold", pad=30)
            # The key travels inside the graphic, in the strip `caption_block` reserves
            # within the canvas -- PLOS and Springer both require it there.
            caption_block(
                fig,
                "\n".join([
                    method_key, star_key, variant.cell_clause, sign_note, state_note,
                ]),
                fontsize=ANNOTATION,
            )
            fit_to_page(fig)
            return fig

        # One publication per variant, enumerated rather than named: the canonical
        # (unsuffixed) file is the camera-ready one.
        for suffix, variant in variant_suffixes(GRID_VARIANTS):
            written.append(
                save_figure(_draw(variant), out_dir / f"{panel_key}{suffix}.png")
            )

    return written
