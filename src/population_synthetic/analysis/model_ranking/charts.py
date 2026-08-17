"""charts.py -- Charts for the cross-model performance comparison.

Consumes the serialisable structure from
:func:`population_synthetic.analysis.model_ranking.builder.build_performance_comparison`
and renders, per country:

* a **heatmap** -- rows = model × strategy combos in rank order, columns = the
  comparison attributes plus a visually separated "overall" column, cell =
  TV-similarity;
* a **leaderboard** -- horizontal bars of overall TV-similarity (best on top)
  with each combo's coherence score annotated;
* optional **per-attribute grouped bars** -- one chart per attribute, strategies
  on the x-axis (complexity order), one bar series per model;
* a **model x method heatmap** -- rows = models, columns = methods (strategies),
  cell = overall TV-similarity annotated with the combination's persona count,
  with under-sampled cells marked and under-evidenced models partitioned out of
  the ranking.

Follows the project charting conventions (deferred ``Agg`` matplotlib import,
``dpi=150``/``bbox_inches="tight"``, ``plt.close`` on every path). The model x
method heatmap additionally styles itself as a sibling of the manuscript tables
by calling :mod:`population_synthetic.analysis.model_ranking.table_style` and
:mod:`population_synthetic.analysis.utils.palette` for every colour and contrast
decision, so it can never drift from them.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from population_synthetic.analysis.model_ranking.table_style import (
    ANNOT_FONTSIZE,
    BOX_EDGE,
    HOST_COLORS,
    HOST_DEFAULT_CLASS,
    HOST_LABELS,
    add_percentage_colorbar,
    categories_on_top,
    horizontal_divider,
    inferno_cmap,
    vertical_divider,
)
from population_synthetic.analysis.utils.axes import strategy_complexity_order
from population_synthetic.analysis.utils.cap_index import CapIndex
from population_synthetic.analysis.utils.figures import save_figure
from population_synthetic.analysis.utils.palette import (
    MISSING_COLOR,
    heatmap_cmap,
    text_color_for_rgb,
    text_color_on,
)

_COLOR_SERIES = (
    "#4878CF",
    "#D65F5F",
    "#6AB187",
    "#E8935A",
    "#E9C46A",
    "#8172B2",
    "#64B5CD",
)


def _combo_label(combo: dict[str, Any]) -> str:
    return f"{combo['model']} / {combo['strategy']}"


def _ordered_strategies(strategies: list[str]) -> list[str]:
    """Strategies in config-derived complexity order (raises on an unknown id)."""
    return strategy_complexity_order(strategies)


# ------------------------------------------------------------------
# Heatmap (combos × attributes + overall)
# ------------------------------------------------------------------

def plot_performance_heatmap(result: dict[str, Any], out_path: str | Path) -> Path | None:
    """Rank-ordered combo × attribute heatmap of TV-similarity, plus an overall column."""
    attributes: list[str] = result["metadata"]["attributes"]
    ranking: list[str] = result["ranking"]
    if not attributes or not ranking:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    values = np.full((len(ranking), len(attributes) + 1), np.nan)
    labels: list[str] = []
    for i, slug in enumerate(ranking):
        combo = result["combos"][slug]
        labels.append(_combo_label(combo))
        for j, attr in enumerate(attributes):
            values[i, j] = combo["per_attribute"][attr]["tv_similarity"]
        values[i, -1] = combo["overall"]["tv_similarity_mean"]

    if np.all(np.isnan(values)):
        return None

    fig, ax = plt.subplots(
        figsize=(max(8.0, (len(attributes) + 1) * 0.8 + 3.0), max(4.0, len(ranking) * 0.45 + 2.5))
    )
    masked = np.ma.masked_invalid(values)
    im = ax.imshow(masked, aspect="auto", cmap=heatmap_cmap())

    ax.set_xticks(range(len(attributes) + 1))
    ax.set_xticklabels(attributes + ["overall"], rotation=40, ha="right", fontsize=8)
    ax.set_yticks(range(len(ranking)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.axvline(len(attributes) - 0.5, color="white", linewidth=2.5)

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("TV-similarity (1 - TV distance)", fontsize=8)

    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            v = values[i, j]
            if np.isnan(v):
                continue
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=6.5,
                    color=text_color_on(im, v))

    country = result["metadata"]["country"]
    ax.set_title(
        f"{country}: TV-similarity per attribute (combos in rank order)",
        fontsize=12, fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ------------------------------------------------------------------
# Leaderboard (overall ranking)
# ------------------------------------------------------------------

def plot_performance_leaderboard(result: dict[str, Any], out_path: str | Path) -> Path | None:
    """Horizontal bars of overall TV-similarity (best on top), coherence annotated."""
    ranking: list[str] = result["ranking"]
    if not ranking:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    labels: list[str] = []
    means: list[float] = []
    coherences: list[float] = []
    for slug in ranking:
        combo = result["combos"][slug]
        labels.append(_combo_label(combo))
        means.append(combo["overall"]["tv_similarity_mean"])
        coherences.append(combo["overall"]["coherence_score"])

    # Best combo at the top of the chart.
    positions = list(range(len(ranking)))[::-1]

    fig, ax = plt.subplots(figsize=(9.0, max(3.5, len(ranking) * 0.45 + 1.8)))
    ax.barh(
        positions, means,
        color=_COLOR_SERIES[0], edgecolor="#33486F", linewidth=0.5, alpha=0.85, height=0.65,
    )
    for pos, mean, coherence in zip(positions, means, coherences):
        if mean == mean:
            ax.text(
                mean, pos, f"  {mean:.3f}  (coh {coherence:.3f})",
                va="center", ha="left", fontsize=7.5, color="#333333",
            )

    ax.set_yticks(positions)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("mean TV-similarity across attributes", fontsize=9)
    finite = [m for m in means if m == m]
    if finite:
        ax.set_xlim(0.0, min(1.0, max(finite) * 1.18))
    ax.grid(axis="x", linestyle=":", alpha=0.4)

    country = result["metadata"]["country"]
    ax.set_title(f"{country}: model x strategy leaderboard", fontsize=12, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ------------------------------------------------------------------
# C2ST AUC vs mean TV-similarity scatter (multivariate summary)
# ------------------------------------------------------------------

def plot_c2st_vs_tv(result: dict[str, Any], out_path: str | Path) -> Path | None:
    """Scatter of C2ST ROC-AUC vs mean TV-similarity across combos, coloured by strategy.

    Positions each combo by its marginal fidelity (x = mean TV-similarity) and
    its joint discriminability (y = C2ST AUC, 0.5 = indistinguishable joint,
    higher = more separable = worse). Colour encodes strategy in complexity order
    (identity, fixed order -- never cycled), so the reader can see whether the
    strategy that wins on marginals also produces the least-separable joint.

    Combos lacking a finite C2ST AUC (reports predating the multivariate block,
    or degenerate synthetic populations) are skipped. Returns ``None`` when no
    combo has a plottable point.
    """
    combos: dict[str, Any] = result.get("combos", {})
    strategies = _ordered_strategies(result["metadata"]["strategies"])
    color_for = {s: _COLOR_SERIES[i % len(_COLOR_SERIES)] for i, s in enumerate(strategies)}

    by_strategy: dict[str, list[tuple[float, float, str]]] = {}
    for combo in combos.values():
        multivariate = combo.get("multivariate") or {}
        auc = multivariate.get("c2st_auc")
        tv = combo["overall"]["tv_similarity_mean"]
        if auc is None or auc != auc or tv != tv:  # None or NaN -> not plottable
            continue
        by_strategy.setdefault(combo["strategy"], []).append((float(tv), float(auc), combo["model"]))
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
        all_aucs.extend(ys)
        ax.scatter(
            xs, ys, s=70, color=color_for[strategy], label=strategy,
            edgecolor="white", linewidth=0.6, alpha=0.9, zorder=3,
        )

    ax.axhline(0.5, color="#888888", linestyle="--", linewidth=1.0, zorder=1)
    ax.text(
        0.01, 0.5, "0.5 = indistinguishable joint",
        transform=ax.get_yaxis_transform(), va="bottom", ha="left",
        fontsize=7.5, color="#666666",
    )

    ax.set_xlabel("mean TV-similarity across attributes (marginal fidelity)", fontsize=9)
    ax.set_ylabel("C2ST ROC-AUC (joint discriminability; 0.5 best)", fontsize=9)
    lo = min([0.5] + all_aucs) - 0.03
    hi = max([0.5] + all_aucs) + 0.03
    ax.set_ylim(lo, min(1.02, hi))
    ax.grid(True, linestyle=":", alpha=0.4)
    ax.legend(title="strategy", fontsize=7.5, title_fontsize=8)

    country = result["metadata"]["country"]
    ax.set_title(
        f"{country}: joint discriminability (C2ST) vs marginal fidelity",
        fontsize=12, fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ------------------------------------------------------------------
# Per-attribute grouped bars (optional)
# ------------------------------------------------------------------

def plot_attribute_bars(result: dict[str, Any], out_dir: str | Path) -> list[Path]:
    """One grouped bar chart per attribute: strategies on x, one series per model."""
    attributes: list[str] = result["metadata"]["attributes"]
    models: list[str] = result["metadata"]["models"]
    strategies = _ordered_strategies(result["metadata"]["strategies"])
    if not attributes or not models or not strategies:
        return []

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # (model, strategy) -> combo lookup.
    by_cell = {
        (combo["model"], combo["strategy"]): combo
        for combo in result["combos"].values()
    }

    written: list[Path] = []
    width = 0.8 / len(models)
    x = np.arange(len(strategies))

    for attr in attributes:
        fig, ax = plt.subplots(figsize=(max(7.0, len(strategies) * 1.4 + 2.0), 5.0))
        for m_idx, model in enumerate(models):
            heights = []
            for strategy in strategies:
                combo = by_cell.get((model, strategy))
                if combo is None:
                    heights.append(np.nan)
                else:
                    heights.append(combo["per_attribute"][attr]["tv_similarity"])
            offsets = x - 0.4 + width * (m_idx + 0.5)
            ax.bar(
                offsets, heights, width=width,
                label=model, color=_COLOR_SERIES[m_idx % len(_COLOR_SERIES)],
                edgecolor="#33486F", linewidth=0.4, alpha=0.85,
            )

        ax.set_xticks(x)
        ax.set_xticklabels(strategies, rotation=25, ha="right", fontsize=8)
        ax.set_ylabel("TV-similarity", fontsize=9)
        ax.set_ylim(0.0, 1.0)
        ax.grid(axis="y", linestyle=":", alpha=0.4)
        ax.legend(fontsize=7.5)

        country = result["metadata"]["country"]
        ax.set_title(f"{country}: {attr} -- TV-similarity by model x strategy",
                     fontsize=11, fontweight="bold")
        out_path = out_dir / f"{attr}_bars.png"
        fig.tight_layout()
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        written.append(out_path)

    return written


# ------------------------------------------------------------------
# Model x method heatmap (overall TV-similarity, honest about n)
# ------------------------------------------------------------------

#: Vertical gap, in row units, opened between the Tier 1 and Tier 2 blocks. Drawn as
#: a genuine gap (two images, not one with a spacer row) so the break is empty figure
#: background rather than a row of "not measured" grey cells.
_TIER_GAP_ROWS = 1.0

#: Row units between the grid's bottom edge and the per-method column marginal.
_COLUMN_MARGINAL_OFFSET = 1.0

#: Column units between the grid's right edge and the per-model row marginal.
_ROW_MARGINAL_OFFSET = 0.25

#: Characters of row-marginal text that fit in one grid column at the annotation size.
#: The row marginal is drawn *inside* the axes -- if it hung outside, the colourbar
#: would be laid out on top of it -- so its width has to be reserved in column units
#: and matched by the figure width. Measured with ~40% slack against the rendered
#: figure; it decides only how much whitespace follows the text.
_MARGINAL_CHARS_PER_COLUMN = 20.0

#: Inches per grid column, and the fixed inches reserved for the y labels, the
#: colourbar and the figure margins.
_COLUMN_INCHES = 1.5
_FIXED_INCHES = 3.5

#: Hatch stroke width for the thin marking. Lighter than the matplotlib default,
#: which at this cell size lays down enough ink to bury the annotation underneath.
_HATCH_LINEWIDTH = 0.6

#: Thin cells are marked with a diagonal HATCH, deliberately not with a hue change:
#: the ramp already means score, so repainting an under-sampled cell would collide
#: "low fidelity" with "few personas" and the reader could not tell which they were
#: looking at. A hatch is a texture -- it survives a greyscale print and a projector,
#: it composites over the ramp without altering the colour the reader decodes, and it
#: is a different visual channel from both the tier break (a dark dashed rule inside a
#: gap) and the marginal dividers (white rules along the grid edges), so the three
#: separators cannot be confused for variants of one device. The stroke colour is the
#: same luminance-derived contrast rule the annotations use, so it stays visible on
#: both the near-black low end and the bright-yellow high end of the ramp.
_THIN_HATCH = "///"

#: Wrap width (characters) for the caption block under the figure.
_CAPTION_WRAP = 130

#: Reason a Tier 2 model carries no rank. Stated on the figure, not merely "unranked":
#: the natural misreading of a block at the bottom is "these are the bad models", and
#: the block actually means "there is not enough evidence to rank them".
_UNRANKED_NOTE = "unranked -- every cell below the requested cap (n < requested n)"

#: The rest of the reason, kept off the grid and in the caption where there is room
#: for it. The short note above says *what* the block is; this says what it is not.
_UNRANKED_CAVEAT = (
    "No part of an unranked row rests on the same evidence as the ranked block, so it "
    "carries no claim about model quality -- it is a statement about sampling."
)


@dataclass(frozen=True)
class _ModelRow:
    """One model's row of the grid, with its tier and its ordering key.

    *values* holds the overall TV-similarity per method in column order, ``NaN`` where
    the ``(model, method)`` combination is absent from the run. *counts* holds the
    persona count per method (``None`` for an absent combination) and *full* whether
    that cell met its own slug's requested cap.

    The ordering key is recorded alongside the row rather than recomputed at sort time
    because the row marginal prints it: the figure must show the quantity the rows were
    actually sorted by, and a second derivation could disagree with the first.
    """

    model: str
    values: np.ndarray
    counts: list[int | None]
    full: list[bool]
    tier: int
    best_value: float | None
    best_method: str | None
    key_mean: float | None
    key_cells: int


def _row_summary(
    values: np.ndarray,
    scope: list[int],
    strategies: list[str],
) -> tuple[float | None, str | None, float | None, int]:
    """``(max, argmax method, mean, count)`` over the finite cells of *scope*.

    *scope* is given in column (complexity) order and the comparison is strict, so a
    within-row tie on the maximum resolves to the first method in
    :func:`~population_synthetic.analysis.utils.axes.strategy_complexity_order`. NaN
    cells are excluded from all four outputs -- a missing value is not a zero, and
    must not enter an ordering key. Returns ``(None, None, None, 0)`` when *scope*
    holds no finite cell, which is a defined state (the row has no ordering key), not
    an error.
    """
    best_value: float | None = None
    best_method: str | None = None
    total = 0.0
    count = 0
    for j in scope:
        v = float(values[j])
        if np.isnan(v):
            continue
        count += 1
        total += v
        if best_value is None or v > best_value:
            best_value = v
            best_method = strategies[j]
    if count == 0:
        return None, None, None, 0
    return best_value, best_method, total / count, count


def _model_method_rows(
    result: dict[str, Any],
    requested_n: CapIndex,
    models: list[str],
    strategies: list[str],
) -> list[_ModelRow]:
    """Regroup ``result["combos"]`` into one :class:`_ModelRow` per model.

    The tier partition and the ordering key are computed here, from ``n`` against each
    slug's own ``requested_n`` (:class:`~population_synthetic.analysis.utils.cap_index.CapIndex`) --
    Tier 1 is a model with at least one full-n cell and ranks on those cells only;
    Tier 2 is a model with none and ranks, provisionally, on all of its cells. A cell
    the run never produced is neither: it contributes no evidence and no value.
    """
    by_cell = {
        (combo["model"], combo["strategy"]): (slug, combo)
        for slug, combo in result["combos"].items()
    }

    rows: list[_ModelRow] = []
    for model in models:
        values = np.full(len(strategies), np.nan)
        counts: list[int | None] = []
        full: list[bool] = []
        for j, strategy in enumerate(strategies):
            entry = by_cell.get((model, strategy))
            if entry is None:
                counts.append(None)
                full.append(False)
                continue
            slug, combo = entry
            values[j] = float(combo["overall"]["tv_similarity_mean"])
            n = int(combo["n"])
            counts.append(n)
            full.append(requested_n.is_full_n(slug, n))

        tier = 1 if any(full) else 2
        if tier == 1:
            scope = [j for j in range(len(strategies)) if full[j]]
        else:
            scope = [j for j in range(len(strategies)) if counts[j] is not None]
        best_value, best_method, key_mean, key_cells = _row_summary(values, scope, strategies)
        rows.append(
            _ModelRow(
                model=model, values=values, counts=counts, full=full, tier=tier,
                best_value=best_value, best_method=best_method,
                key_mean=key_mean, key_cells=key_cells,
            )
        )
    return rows


def _tier1_sort_key(row: _ModelRow) -> tuple[int, float, float, str]:
    """``(-max_over_full_n, -mean_over_full_n, model_id)``, keyless rows last.

    A row whose full-n cells are all NaN has no defined key: it sorts last *within its
    tier* by the explicit leading flag rather than by comparing against NaN, and it
    stays in Tier 1 -- it has full-n cells, their values are missing, which is a
    different failure from thin evidence.
    """
    if row.best_value is None:
        return (1, 0.0, 0.0, row.model)
    return (0, -row.best_value, -(row.key_mean or 0.0), row.model)


def _tier2_sort_key(row: _ModelRow) -> tuple[int, float, str]:
    """``(-max_over_all_cells, model_id)``, keyless rows last (same explicit rule)."""
    if row.best_value is None:
        return (1, 0.0, row.model)
    return (0, -row.best_value, row.model)


def _column_marginals(
    ordered: list[_ModelRow],
    n_methods: int,
) -> tuple[list[float], list[int]]:
    """Per-method ``(mean, count)`` over **full-n cells only**, across all models.

    A method's mean must not be moved by a cell resting on a handful of personas, so
    thin cells are excluded; the count is returned with it so an excluded cell is
    visible on the figure rather than silent. A method with no full-n cell yields
    ``(NaN, 0)`` -- an absent mean, explicitly, never a zero.
    """
    means: list[float] = []
    counts: list[int] = []
    for j in range(n_methods):
        vals = [
            float(row.values[j])
            for row in ordered
            if row.full[j] and not np.isnan(row.values[j])
        ]
        means.append(sum(vals) / len(vals) if vals else float("nan"))
        counts.append(len(vals))
    return means, counts


def _row_marginal_text(row: _ModelRow) -> str:
    """The ordering key as printed beside the row: best score, argmax method, cell count.

    Deliberately not a mean: the rows are sorted by their maximum, and a marginal
    showing one quantity beside an axis ordered by another invites the reader to
    check the order against the wrong number. Tier 2's key is flagged provisional
    because it rests on cells that never reached the cap.
    """
    if row.best_value is None:
        return "n/a  (no scored cell)"
    scope = "full-n" if row.tier == 1 else "cells, provisional"
    return f"{row.best_value * 100:.1f}  {row.best_method}  ({row.key_cells} {scope})"


def plot_model_method_heatmap(
    result: dict[str, Any],
    requested_n: CapIndex,
    out_path: str | Path,
) -> Path | None:
    """Model x method heatmap of overall TV-similarity, marked and tiered by persona count.

    Rows are models, columns are methods (strategies) in
    :func:`~population_synthetic.analysis.utils.axes.strategy_complexity_order`, and each
    cell is that combination's mean TV-similarity across every demographic axis, printed
    as a percentage together with the persona count ``n`` it rests on. A cell whose ``n``
    is below its own slug's requested cap is hatched, and never decides a Tier 1 rank.

    Rows are partitioned by evidence before they are ranked: a model with at least one
    full-n cell is **Tier 1** and is ordered by ``(-max, -mean, model_id)`` over its
    full-n cells; a model with none is **Tier 2**, drawn after an explicit break and
    annotated with the reason. The row marginal prints each model's ordering key and how
    many cells it rested on; the column marginal prints each method's mean across models
    over full-n cells only, with the count it averaged.

    Args:
        result: The built performance comparison (``builder.build_performance_comparison``).
        requested_n: The gate's per-slug requested cap
            (:func:`~population_synthetic.analysis.utils.cap_index.load_cap_index`).
            Raises if a combination in *result* has no entry -- an unknown cap is never
            assumed to be met.
        out_path: The PNG path; the ``.svg`` sibling is written beside it.

    Returns:
        The PNG path (the SVG sibling is written by
        :func:`~population_synthetic.analysis.utils.figures.save_figure`), or ``None``
        when there is nothing to draw (no models, no methods, or an all-NaN grid).
    """
    metadata = result["metadata"]
    models: list[str] = metadata["models"]
    if not models or not metadata["strategies"]:
        return None
    # Called directly rather than read from ``result["methods_matrix"]["strategies"]``:
    # the column order is a config fact, not an artifact of an unrelated aggregation.
    strategies = _ordered_strategies(metadata["strategies"])

    rows = _model_method_rows(result, requested_n, models, strategies)
    tier1 = sorted([r for r in rows if r.tier == 1], key=_tier1_sort_key)
    tier2 = sorted([r for r in rows if r.tier == 2], key=_tier2_sort_key)
    ordered = tier1 + tier2
    if not ordered:
        return None
    values = np.vstack([row.values for row in ordered])
    if np.all(np.isnan(values)):
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch, Rectangle

    n_methods = len(strategies)
    gap = _TIER_GAP_ROWS if (tier1 and tier2) else 0.0
    row_y = [float(i) for i in range(len(tier1))] + [
        len(tier1) + gap + i for i in range(len(tier2))
    ]
    grid_bottom = row_y[-1] + 0.5
    marginal_y = grid_bottom + _COLUMN_MARGINAL_OFFSET

    # The row marginal lives inside the axes, so its width is reserved up front (in
    # column units) and the figure is widened to match.
    row_marginals = [_row_marginal_text(row) for row in ordered]
    marginal_columns = _ROW_MARGINAL_OFFSET + (
        max(len(text) for text in row_marginals) / _MARGINAL_CHARS_PER_COLUMN
    )

    finite = values[~np.isnan(values)]
    norm = mcolors.Normalize(vmin=float(finite.min()), vmax=float(finite.max()))
    cmap = inferno_cmap()

    fig, ax = plt.subplots(
        figsize=(
            max(9.0, (n_methods + marginal_columns) * _COLUMN_INCHES + _FIXED_INCHES),
            max(4.5, (len(ordered) + gap) * 0.62 + 3.2),
        )
    )

    def _draw_block(block: list[_ModelRow], y_top: float):
        """One imshow per tier block, so the break between them is a real gap."""
        block_values = np.vstack([row.values for row in block])
        return ax.imshow(
            np.ma.masked_invalid(block_values), cmap=cmap, norm=norm, aspect="auto",
            interpolation="nearest",
            extent=(-0.5, n_methods - 0.5, y_top + len(block) - 0.5, y_top - 0.5),
        )

    im = _draw_block(tier1, 0.0) if tier1 else _draw_block(tier2, 0.0)
    if tier1 and tier2:
        _draw_block(tier2, len(tier1) + gap)

    ax.set_xlim(-0.5, n_methods - 0.5 + marginal_columns)
    ax.set_ylim(marginal_y + 0.5, -0.5)

    categories_on_top(ax, strategies)
    ax.set_yticks(row_y)
    ax.set_yticklabels([row.model for row in ordered], fontsize=8)
    hosting: dict[str, str] = metadata.get("model_hosting", {})
    for label, row in zip(ax.get_yticklabels(), ordered):
        # Provenance side-marker (same rule and colours as the models table); Tier 2
        # rows are additionally italicised, so the tier is legible without colour.
        label.set_color(HOST_COLORS[hosting.get(row.model, HOST_DEFAULT_CLASS)])
        if row.tier == 2:
            label.set_fontstyle("italic")

    # --- cells: value, n, and the thin marking.
    missing_text_color = text_color_for_rgb(mcolors.to_rgb(MISSING_COLOR))
    for i, row in enumerate(ordered):
        y = row_y[i]
        for j in range(n_methods):
            n = row.counts[j]
            if n is None:  # combination absent from the run -- grey, no value, no marking
                continue
            v = float(row.values[j])
            measured = not np.isnan(v)
            fill = cmap(norm(v)) if measured else MISSING_COLOR
            color = text_color_for_rgb(cmap(norm(v))) if measured else missing_text_color
            # A thin cell's annotation is set on a patch of the cell's own colour, so
            # the hatch that marks the cell reads across the rest of it without
            # crossing the number and the count it is qualifying.
            bbox = None if row.full[j] else {"facecolor": fill, "edgecolor": "none", "pad": 1.4}
            ax.text(
                j, y, f"{v * 100:.1f}\nn={n}" if measured else f"--\nn={n}",
                ha="center", va="center", fontsize=ANNOT_FONTSIZE, color=color,
                linespacing=1.35, bbox=bbox,
            )
            if not row.full[j]:
                # Under the annotation (text sits at zorder 3), so the marking never
                # costs the reader the value and the count it is qualifying.
                ax.add_patch(
                    Rectangle(
                        (j - 0.5, y - 0.5), 1, 1, fill=False, linewidth=0.0,
                        hatch=_THIN_HATCH,
                        edgecolor=color if measured else BOX_EDGE, zorder=2,
                    )
                )

    # --- the break between the tiers: a gap, a dashed dark rule inside it, and the reason.
    if tier1 and tier2:
        ax.axhline(
            len(tier1) - 0.5 + gap / 2.0,
            color=BOX_EDGE, linewidth=1.6, linestyle=(0, (7, 4)), zorder=6,
        )
        ax.text(
            -0.5, len(tier1) - 0.5 + gap / 2.0 - 0.08, _UNRANKED_NOTE,
            ha="left", va="bottom", fontsize=7.5, color=BOX_EDGE, clip_on=False,
        )

    # --- marginals, fenced off from the grid by the shared divider.
    vertical_divider(ax, n_methods)
    horizontal_divider(ax, grid_bottom + 0.5)

    for i, row in enumerate(ordered):
        ax.text(
            n_methods - 0.5 + _ROW_MARGINAL_OFFSET, row_y[i], row_marginals[i],
            ha="left", va="center", fontsize=7.5,
            fontstyle="italic" if row.tier == 2 else "normal", clip_on=False,
        )

    means, counts = _column_marginals(ordered, n_methods)
    for j, (mean, count) in enumerate(zip(means, counts)):
        text = f"{mean * 100:.1f}\n({count} full-n)" if count else f"n/a\n({count} full-n)"
        ax.text(j, marginal_y, text, ha="center", va="center", fontsize=7.5, linespacing=1.35)
    ax.text(
        -0.5 - _ROW_MARGINAL_OFFSET, marginal_y, "method mean",
        ha="right", va="center", fontsize=7.5, clip_on=False,
    )

    add_percentage_colorbar(fig, im, ax, "TV-similarity (%)")

    classes_present = {hosting.get(row.model, HOST_DEFAULT_CLASS) for row in ordered}
    handles = [
        Patch(facecolor=HOST_COLORS[c], edgecolor="none", label=HOST_LABELS[c])
        for c in ("hosted", "local") if c in classes_present
    ]
    handles.append(
        Patch(
            facecolor="none", edgecolor=BOX_EDGE, hatch=_THIN_HATCH,
            label="hatched: n below the requested cap",
        )
    )
    ax.legend(
        handles=handles, loc="upper left", bbox_to_anchor=(0.0, -0.02),
        ncol=3, fontsize=7.5, title="provenance / sampling", title_fontsize=8, frameon=False,
    )

    country = metadata["country"]
    ax.set_title(
        f"{country}: overall fidelity by model x method (TV-similarity %)\n"
        "one cell per combination, averaged over every axis -- not the per-axis "
        "combo table or the single-method models table",
        fontsize=11, fontweight="bold", pad=30,
    )

    # The row-marginal scope clause names the tiers only when the grid actually has two,
    # so a healthy fully-capped run is not captioned about a partition it does not show.
    row_scope = (
        "(Tier 1: full-n cells only; Tier 2: all cells, provisional)" if tier2
        else "(full-n cells only)"
    )
    caption = (
        "Cell: mean TV-similarity across every demographic axis (x100), over the n personas "
        "the validation gate left for that combination. "
        "Row marginal: the model's ordering key -- best qualifying score, the method that "
        f"achieved it, and the number of cells the key rested on {row_scope}. "
        "Column marginal: the method's mean across models over full-n cells only, with the "
        "number of cells averaged, so an excluded thin cell is visible rather than silent."
    )
    if tier2:
        lead = f"No model has a full-n cell: {_UNRANKED_NOTE}. " if not tier1 else ""
        caption = f"{lead}{_UNRANKED_CAVEAT} {caption}"
    ax.text(
        0.0, -0.13, textwrap.fill(caption, _CAPTION_WRAP), transform=ax.transAxes,
        ha="left", va="top", fontsize=7, clip_on=False,
    )

    fig.tight_layout()
    # Hatch stroke width is an rcParam read at *draw* time, so it is set around the
    # save rather than on the patches, and scoped so no other figure inherits it.
    with plt.rc_context({"hatch.linewidth": _HATCH_LINEWIDTH}):
        return save_figure(fig, Path(out_path), dpi=150)
