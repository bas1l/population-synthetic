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
persistence delegated to ``analysis/utils/figures.py::save_figure``, which writes
the PNG+SVG+EPS trio and closes the figure). The model x
method heatmap additionally styles itself as a sibling of the manuscript tables
by calling :mod:`population_synthetic.analysis.utils.table_style` and
:mod:`population_synthetic.analysis.utils.palette` for every colour and contrast
decision, so it can never drift from them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from population_synthetic.analysis.utils.axes import strategy_complexity_order
from population_synthetic.analysis.utils.cap_index import CapIndex
from population_synthetic.analysis.utils.figures import save_figure
from population_synthetic.analysis.utils.grid_annotations import (
    RateOnlyPolicy,
    RateWithCountsPolicy,
)
from population_synthetic.analysis.utils.grid_variants import (
    CANONICAL_VARIANT,
    COUNTED_VARIANT,
    GridVariant,
    variant_map,
)
from population_synthetic.analysis.utils.grids import render_grid
from population_synthetic.analysis.utils.labels import (
    attribute_label,
    country_label,
    method_key_lines,
    method_letters,
    model_labels,
)
from population_synthetic.analysis.utils.model_order import (
    _model_method_rows,
    _ModelRow,
    _tier1_sort_key,
    _tier2_sort_key,
)
from population_synthetic.analysis.utils.palette import (
    ANNOTATION_GREY,
    BAR_EDGE,
    CATEGORICAL_SERIES,
    GRID_RULE,
    HOST_COLORS,
    MISSING_COLOR,
    MUTED_GREY,
    SECONDARY_GREY,
    SURFACE,
    heatmap_cmap,
    opaque,
    text_color_for_rgb,
)
from population_synthetic.analysis.utils.style import (
    ANNOTATION,
    ANNOTATION_LARGE,
    AXIS_TITLE,
    FIGURE_TITLE,
    FULL,
    LEGEND_LABEL,
    LEGEND_TITLE,
    PANEL_TITLE,
    TICK_LABEL,
    caption_block,
    figure_size,
    grow_height,
    grow_width,
    house_style,
)
from population_synthetic.analysis.utils.table_style import (
    ANNOT_FONTSIZE,
    BOX_EDGE,
    HOST_DEFAULT_CLASS,
    HOST_LABELS,
    add_percentage_colorbar,
    categories_on_top,
    fit_to_page,
    horizontal_divider,
    inferno_cmap,
    vertical_divider,
)

#: The combo table's cell annotation: TV-similarity at its own 0--1 scale, two decimals.
_COMBO_CELL_POLICY = RateOnlyPolicy(value_key="value", scale=1.0, number_format=".2f")

#: The model x method grid's counted variant: TV-similarity as a percentage over the
#: persona count the cell rests on. Not a quotient of two printed counts, so the base is
#: named ``n=``; a combination that was scored on no axis prints the count it does have
#: beneath an explicit dash rather than a number it never measured.
GRID_VARIANT_WITH_COUNTS = GridVariant(
    name=COUNTED_VARIANT,
    policy=RateWithCountsPolicy(
        value_key="value", numerator_key=None, denominator_key="n",
        scale=100.0, number_format=".1f", absent_text="--",
    ),
    cell_clause=(
        "Cell: mean TV-similarity across every demographic axis (x100), printed over the "
        "n personas the validation gate left for that combination."
    ),
    fontsize=ANNOT_FONTSIZE,
    linespacing=1.35,
)

#: The camera-ready variant, published at the bare filename: the score alone, one step up
#: the house scale on the room the dropped count line frees. The persona count is not
#: lost -- it is in the performance CSV, in the counted sibling, and on both marginals of
#: this very figure -- and it is constant down most of a column, which is exactly the
#: repetition a manuscript grid should not spend a line on.
GRID_VARIANT_CLEAN = GridVariant(
    name=CANONICAL_VARIANT,
    policy=RateOnlyPolicy(
        value_key="value", scale=100.0, number_format=".1f", absent_text="--",
    ),
    cell_clause=(
        "Cell: mean TV-similarity across every demographic axis (x100). The n personas "
        "each cell rests on are printed on the with-counts sibling figure and in the "
        "performance CSV; the row and column marginals here carry their own counts."
    ),
    fontsize=ANNOTATION_LARGE,
    linespacing=None,
)

#: The publishable variants by name, clean first because it takes the bare filename.
GRID_VARIANTS: dict[str, GridVariant] = variant_map(
    GRID_VARIANT_CLEAN, GRID_VARIANT_WITH_COUNTS,
)


def _combo_label(
    combo: dict[str, Any], display_models: dict[str, str], letters: dict[str, str]
) -> str:
    """Row caption for one combination: the model's display name and its method letter.

    Both mappings are resolved by the caller over the *whole* figure's id set, because a
    method letter's version marker is a property of the set, not of any one id.
    """
    return f"{display_models[combo['model']]} / {letters[combo['strategy']]}"


def _combo_captions(
    result: dict[str, Any], ranking: list[str]
) -> tuple[dict[str, str], list[str]]:
    """``(caption_by_slug, method_key_lines)`` for a figure keyed on combination slugs."""
    combos = [result["combos"][slug] for slug in ranking]
    display_models = model_labels([c["model"] for c in combos])
    strategies = [c["strategy"] for c in combos]
    letters = method_letters(strategies)
    captions = {
        slug: _combo_label(combo, display_models, letters)
        for slug, combo in zip(ranking, combos)
    }
    return captions, method_key_lines(strategies)


def _ordered_strategies(strategies: list[str]) -> list[str]:
    """Strategies in config-derived complexity order (raises on an unknown id)."""
    return strategy_complexity_order(strategies)


# ------------------------------------------------------------------
# Heatmap (combos × attributes + overall)
# ------------------------------------------------------------------

@house_style
def plot_performance_heatmap(result: dict[str, Any], out_path: str | Path) -> Path | None:
    """Rank-ordered combo × attribute heatmap of TV-similarity, plus an overall column."""
    attributes: list[str] = result["metadata"]["attributes"]
    ranking: list[str] = result["ranking"]
    if not attributes or not ranking:
        return None

    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    values = np.full((len(ranking), len(attributes) + 1), np.nan)
    captions, key_lines = _combo_captions(result, ranking)
    labels: list[str] = []
    for i, slug in enumerate(ranking):
        combo = result["combos"][slug]
        labels.append(captions[slug])
        for j, attr in enumerate(attributes):
            values[i, j] = combo["per_attribute"][attr]["tv_similarity"]
        values[i, -1] = combo["overall"]["tv_similarity_mean"]

    if np.all(np.isnan(values)):
        return None

    fig, ax = plt.subplots(
        figsize=(
            grow_width(len(attributes) + 1, per_item=0.8, padding=3.0, minimum=FULL),
            grow_height(len(ranking), per_item=0.45, padding=2.5, minimum=4.0),
        ),
    )
    cells = [
        [None if np.isnan(value) else {"value": float(value)} for value in row]
        for row in values
    ]
    im = render_grid(
        ax, values, cells,
        policy=_COMBO_CELL_POLICY, cmap=heatmap_cmap(), aspect="auto",
        fontsize=ANNOTATION, interpolation="none",
    )

    ax.set_xticks(range(len(attributes) + 1))
    ax.set_xticklabels(
        [attribute_label(a) for a in attributes] + ["Overall"],
        rotation=40, ha="right", fontsize=TICK_LABEL,
    )
    ax.set_yticks(range(len(ranking)))
    ax.set_yticklabels(labels, fontsize=TICK_LABEL)
    # The rule that sets the "Overall" column apart from the per-attribute ones. Drawn
    # in the page colour rather than in a literal "white", so it stays a role like every
    # other colour in the layer and follows the ground if that ever moves.
    ax.axvline(len(attributes) - 0.5, color=SURFACE, linewidth=2.5)

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("TV-similarity (1 - TV distance)", fontsize=AXIS_TITLE)

    country = result["metadata"]["country"]
    ax.set_title(
        f"{country_label(country)}: TV-similarity per attribute (combos in rank order)",
        fontsize=FIGURE_TITLE, fontweight="bold",
    )
    caption_block(fig, "Methods:  " + "   ".join(key_lines), fontsize=ANNOTATION)
    fit_to_page(fig)
    return save_figure(fig, out_path)


# ------------------------------------------------------------------
# Leaderboard (overall ranking)
# ------------------------------------------------------------------

@house_style
def plot_performance_leaderboard(result: dict[str, Any], out_path: str | Path) -> Path | None:
    """Horizontal bars of overall TV-similarity (best on top), coherence annotated."""
    ranking: list[str] = result["ranking"]
    if not ranking:
        return None

    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    captions, key_lines = _combo_captions(result, ranking)
    labels: list[str] = []
    means: list[float] = []
    coherences: list[float] = []
    for slug in ranking:
        combo = result["combos"][slug]
        labels.append(captions[slug])
        means.append(combo["overall"]["tv_similarity_mean"])
        coherences.append(combo["overall"]["coherence_score"])

    # Best combo at the top of the chart.
    positions = list(range(len(ranking)))[::-1]

    fig, ax = plt.subplots(figsize=(FULL, grow_height(len(ranking), per_item=0.45, padding=1.8, minimum=3.5)))
    ax.barh(
        positions, means,
        color=opaque(CATEGORICAL_SERIES[0], 0.85), edgecolor=BAR_EDGE, linewidth=0.5, height=0.65,
    )
    for pos, mean, coherence in zip(positions, means, coherences):
        if mean == mean:
            ax.text(
                mean, pos, f"  {mean:.3f}  (coh {coherence:.3f})",
                va="center", ha="left", fontsize=ANNOTATION, color=ANNOTATION_GREY,
            )

    ax.set_yticks(positions)
    ax.set_yticklabels(labels, fontsize=TICK_LABEL)
    ax.set_xlabel("mean TV-similarity across attributes", fontsize=AXIS_TITLE)
    finite = [m for m in means if m == m]
    if finite:
        ax.set_xlim(0.0, min(1.0, max(finite) * 1.18))
    ax.grid(axis="x", linestyle=":", color=GRID_RULE)

    country = result["metadata"]["country"]
    ax.set_title(
        f"{country_label(country)}: model x method leaderboard",
        fontsize=FIGURE_TITLE, fontweight="bold",
    )
    caption_block(fig, "Methods:  " + "   ".join(key_lines), fontsize=ANNOTATION)
    fit_to_page(fig)
    return save_figure(fig, out_path)


# ------------------------------------------------------------------
# C2ST AUC vs mean TV-similarity scatter (multivariate summary)
# ------------------------------------------------------------------

@house_style
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
    color_for = {s: CATEGORICAL_SERIES[i % len(CATEGORICAL_SERIES)] for i, s in enumerate(strategies)}
    # The legend entry is the method key line itself, so the letters this figure would
    # otherwise need a key block for are explained where they are read.
    method_key = dict(zip(method_letters(strategies), method_key_lines(strategies)))

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
        all_aucs.extend(ys)
        ax.scatter(
            xs, ys, s=70, color=color_for[strategy], label=method_key[strategy],
            edgecolor=SURFACE, linewidth=0.6, zorder=3,
        )

    ax.axhline(0.5, color=MUTED_GREY, linestyle="--", linewidth=1.0, zorder=1)
    ax.text(
        0.01, 0.5, "0.5 = indistinguishable joint",
        transform=ax.get_yaxis_transform(), va="bottom", ha="left",
        fontsize=ANNOTATION, color=SECONDARY_GREY,
    )

    ax.set_xlabel("mean TV-similarity across attributes (marginal fidelity)", fontsize=AXIS_TITLE)
    ax.set_ylabel("C2ST ROC-AUC (joint discriminability; 0.5 best)", fontsize=AXIS_TITLE)
    lo = min([0.5] + all_aucs) - 0.03
    hi = max([0.5] + all_aucs) + 0.03
    ax.set_ylim(lo, min(1.02, hi))
    ax.grid(True, linestyle=":", color=GRID_RULE)
    ax.legend(title="generation method", fontsize=LEGEND_LABEL, title_fontsize=LEGEND_TITLE)

    country = result["metadata"]["country"]
    ax.set_title(
        f"{country_label(country)}: joint discriminability (C2ST) vs marginal fidelity",
        fontsize=FIGURE_TITLE, fontweight="bold",
    )
    fig.tight_layout()
    fit_to_page(fig)
    return save_figure(fig, out_path)


# ------------------------------------------------------------------
# Per-attribute grouped bars (optional)
# ------------------------------------------------------------------

@house_style
def plot_attribute_bars(result: dict[str, Any], out_dir: str | Path) -> list[Path]:
    """One grouped bar chart per attribute: strategies on x, one series per model."""
    attributes: list[str] = result["metadata"]["attributes"]
    models: list[str] = result["metadata"]["models"]
    strategies = _ordered_strategies(result["metadata"]["strategies"])
    if not attributes or not models or not strategies:
        return []

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
    letters = method_letters(strategies)
    method_key = "Methods:  " + "   ".join(method_key_lines(strategies))
    display_models = model_labels(models)

    for attr in attributes:
        fig, ax = plt.subplots(
            figsize=figure_size(grow_width(len(strategies), per_item=1.4, padding=2.0, minimum=7.0), 5.0),
        )
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
                label=display_models[model],
                color=CATEGORICAL_SERIES[m_idx % len(CATEGORICAL_SERIES)],
                edgecolor=BAR_EDGE, linewidth=0.4,
            )

        ax.set_xticks(x)
        ax.set_xticklabels([letters[s] for s in strategies], fontsize=TICK_LABEL)
        ax.set_ylabel("TV-similarity", fontsize=AXIS_TITLE)
        ax.set_ylim(0.0, 1.0)
        ax.grid(axis="y", linestyle=":", color=GRID_RULE)
        ax.legend(fontsize=LEGEND_LABEL)

        country = result["metadata"]["country"]
        ax.set_title(f"{country_label(country)}: {attribute_label(attr)} -- "
                     f"TV-similarity by model x method",
                     fontsize=PANEL_TITLE, fontweight="bold")
        caption_block(fig, method_key, fontsize=ANNOTATION)
        fit_to_page(fig)
        written.append(save_figure(fig, out_dir / f"{attr}_bars.png"))

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


def _row_marginal_text(row: _ModelRow, letters: dict[str, str]) -> str:
    """The ordering key as printed beside the row: best score, argmax method, cell count.

    Deliberately not a mean: the rows are sorted by their maximum, and a marginal
    showing one quantity beside an axis ordered by another invites the reader to
    check the order against the wrong number. Tier 2's key is flagged provisional
    because it rests on cells that never reached the cap.
    """
    if row.best_value is None:
        return "n/a  (no scored cell)"
    scope = "full-n" if row.tier == 1 else "cells, provisional"
    return f"{row.best_value * 100:.1f}  {letters[row.best_method]}  ({row.key_cells} {scope})"


@house_style
def plot_model_method_heatmap(
    result: dict[str, Any],
    requested_n: CapIndex,
    out_path: str | Path,
    *,
    variant: GridVariant = GRID_VARIANT_CLEAN,
) -> Path | None:
    """Model x method heatmap of overall TV-similarity, marked and tiered by persona count.

    Rows are models, columns are methods (strategies) in
    :func:`~population_synthetic.analysis.utils.axes.strategy_complexity_order`, and each
    cell is that combination's mean TV-similarity across every demographic axis, printed
    as a percentage. A cell whose ``n`` is below its own slug's requested cap is hatched,
    and never decides a Tier 1 rank.

    What a cell *prints* is the *variant*'s decision, and the only difference between the
    two publications of this figure: the clean one prints the score alone one step larger,
    the with-counts one prints it over the persona count ``n`` it rests on. Rows, columns,
    tiers, extent, colour scale, markings and both marginals are shared, because both go
    through the same draw loop with different annotation policies rather than through two
    functions that would diverge on the next edit. The marginals always print their
    counts, so the clean variant still states a base on the figure.

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
        out_path: The PNG path; the ``.svg`` sibling is written beside it. The caller
            owns the filename, including the variant's suffix
            (:func:`~population_synthetic.analysis.utils.grid_variants.variant_suffixes`).
        variant: Which publication of the figure to draw -- :data:`GRID_VARIANT_CLEAN`
            (the default, and the one published at the bare filename) or
            :data:`GRID_VARIANT_WITH_COUNTS`.

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
    letters = method_letters(strategies)
    display_models = model_labels([row.model for row in ordered])
    row_marginals = [_row_marginal_text(row, letters) for row in ordered]
    marginal_columns = _ROW_MARGINAL_OFFSET + (
        max(len(text) for text in row_marginals) / _MARGINAL_CHARS_PER_COLUMN
    )

    finite = values[~np.isnan(values)]
    norm = mcolors.Normalize(vmin=float(finite.min()), vmax=float(finite.max()))
    cmap = inferno_cmap()

    fig, ax = plt.subplots(
        figsize=(
            grow_width(n_methods + marginal_columns, per_item=_COLUMN_INCHES, padding=_FIXED_INCHES, minimum=FULL),
            grow_height(len(ordered) + gap, per_item=0.62, padding=3.2, minimum=4.5),
        ),
    )

    def _draw_block(block: list[_ModelRow], y_top: float):
        """One render per tier block, so the break between them is a real gap.

        The cell records carry the value and the count it rests on; a combination absent
        from the run carries none at all, so it is painted grey and left unannotated
        rather than being given a dash it could be read as a measurement of. A thin cell's
        annotation is set on a patch of its own fill, which is what keeps the hatch that
        marks it from crossing the number it qualifies.
        """
        block_values = np.vstack([row.values for row in block])
        cells = [
            [
                None if row.counts[j] is None else {
                    "value": None if np.isnan(row.values[j]) else float(row.values[j]),
                    "n": row.counts[j],
                }
                for j in range(n_methods)
            ]
            for row in block
        ]
        text_on_fill = [[not row.full[j] for j in range(n_methods)] for row in block]
        return render_grid(
            ax, block_values, cells,
            policy=variant.policy, cmap=cmap, norm=norm, aspect="auto",
            interpolation="none",
            extent=(-0.5, n_methods - 0.5, y_top + len(block) - 0.5, y_top - 0.5),
            row_origin=y_top, fontsize=variant.fontsize, linespacing=variant.linespacing,
            text_on_fill=text_on_fill,
        )

    im = _draw_block(tier1, 0.0) if tier1 else _draw_block(tier2, 0.0)
    if tier1 and tier2:
        _draw_block(tier2, len(tier1) + gap)

    ax.set_xlim(-0.5, n_methods - 0.5 + marginal_columns)
    ax.set_ylim(marginal_y + 0.5, -0.5)

    categories_on_top(ax, [letters[s] for s in strategies])
    ax.set_yticks(row_y)
    ax.set_yticklabels([display_models[row.model] for row in ordered], fontsize=TICK_LABEL)
    hosting: dict[str, str] = metadata.get("model_hosting", {})
    for label, row in zip(ax.get_yticklabels(), ordered):
        # Provenance side-marker (same rule and colours as the models table); Tier 2
        # rows are additionally italicised, so the tier is legible without colour.
        label.set_color(HOST_COLORS[hosting.get(row.model, HOST_DEFAULT_CLASS)])
        if row.tier == 2:
            label.set_fontstyle("italic")

    # --- the thin marking, drawn under the annotations the blocks above already wrote
    # (text sits at zorder 3), so the marking never costs the reader the value and the
    # count it is qualifying.
    missing_text_color = text_color_for_rgb(mcolors.to_rgb(MISSING_COLOR))
    for i, row in enumerate(ordered):
        y = row_y[i]
        for j in range(n_methods):
            if row.counts[j] is None or row.full[j]:
                continue
            v = float(row.values[j])
            measured = not np.isnan(v)
            color = text_color_for_rgb(cmap(norm(v))) if measured else missing_text_color
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
            ha="left", va="bottom", fontsize=ANNOTATION, color=BOX_EDGE, clip_on=False,
        )

    # --- marginals, fenced off from the grid by the shared divider.
    vertical_divider(ax, n_methods)
    horizontal_divider(ax, grid_bottom + 0.5)

    for i, row in enumerate(ordered):
        ax.text(
            n_methods - 0.5 + _ROW_MARGINAL_OFFSET, row_y[i], row_marginals[i],
            ha="left", va="center", fontsize=ANNOTATION,
            fontstyle="italic" if row.tier == 2 else "normal", clip_on=False,
        )

    means, counts = _column_marginals(ordered, n_methods)
    for j, (mean, count) in enumerate(zip(means, counts)):
        text = f"{mean * 100:.1f}\n({count} full-n)" if count else f"n/a\n({count} full-n)"
        ax.text(j, marginal_y, text, ha="center", va="center", fontsize=ANNOTATION, linespacing=1.35)
    ax.text(
        -0.5 - _ROW_MARGINAL_OFFSET, marginal_y, "method mean",
        ha="right", va="center", fontsize=ANNOTATION, clip_on=False,
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
        ncol=3, fontsize=LEGEND_LABEL, title="provenance / sampling", title_fontsize=LEGEND_TITLE, frameon=False,
    )

    country = metadata["country"]
    ax.set_title(
        f"{country_label(country)}: overall fidelity by model x method (TV-similarity %)\n"
        "one cell per combination, averaged over every axis -- not the per-axis "
        "combo table or the single-method models table",
        fontsize=PANEL_TITLE, fontweight="bold", pad=30,
    )

    # The row-marginal scope clause names the tiers only when the grid actually has two,
    # so a healthy fully-capped run is not captioned about a partition it does not show.
    row_scope = (
        "(Tier 1: full-n cells only; Tier 2: all cells, provisional)" if tier2
        else "(full-n cells only)"
    )
    method_key = "Methods:  " + "   ".join(method_key_lines(strategies)) + "  "
    caption = (
        f"{variant.cell_clause} "
        "Row marginal: the model's ordering key -- best qualifying score, the method that "
        f"achieved it, and the number of cells the key rested on {row_scope}. "
        "Column marginal: the method's mean across models over full-n cells only, with the "
        "number of cells averaged, so an excluded thin cell is visible rather than silent."
    )
    if tier2:
        lead = f"No model has a full-n cell: {_UNRANKED_NOTE}. " if not tier1 else ""
        caption = f"{lead}{_UNRANKED_CAVEAT} {caption}"
    caption_block(fig, method_key + caption, fontsize=ANNOTATION)
    fit_to_page(fig)
    # Hatch stroke width is an rcParam read at *draw* time, so it is set around the
    # save rather than on the patches, and scoped so no other figure inherits it.
    with plt.rc_context({"hatch.linewidth": _HATCH_LINEWIDTH}):
        return save_figure(fig, Path(out_path))
