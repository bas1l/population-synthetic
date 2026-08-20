"""charts.py -- render the two attrition figures. Draws only; computes no statistic.

Both renderers take the document
:func:`~population_synthetic.analysis.validation_attrition.builder.build_document`
assembled and **return** an unsaved ``Figure``; the driver owns the path, the dpi and
the PNG+SVG pair (``analysis/utils/figures.py::save_figure``). Nothing here opens a
file, resolves an output directory or knows which country it is drawing -- the country
travels in the document like every other value.

**Every published rate is read, never recomputed** (guide 02 sect. 9). ``retention_rate``
is derived once, in the builder, and the grid renders that field verbatim, so the CSV,
the JSON and the figure cannot disagree about a cell. The only arithmetic in this module
is the funnel's bar geometry -- four disjoint slices of one combination's generated pool,
which is the drawing itself rather than a statistic -- and the two pooled marginals on
the grid, both of which are printed **with the counts they are quotients of** so a reader
never meets a rate over an unstated base (guide 03 sect. 4).

**Four cell states, never three** (ADR 2026-08-12). The grid distinguishes:

``measured``
    A combination that reached its requested cap. Painted on the house ramp.
``withdrawn``
    A combination whose rate is equally measured but which the full-N rule *excluded*,
    so it contributes nothing to any other analysis. Painted on the ramp too -- its rate
    is real and often the most interesting on the figure -- and marked, because rendering
    it as an ordinary cell would publish a survival rate for a combination that no
    downstream artifact contains. It is emphatically **not** drawn as ``0``.
``undefined``
    A combination the gate recorded whose generated pool is empty, so no rate exists.
    Grey, labelled with its zero pool -- never ``0.0``, which would claim a pool was
    generated and wholly discarded.
``absent``
    No such ``(model, method)`` combination in the run at all. Grey, labelled as not
    generated.

The two grey states share a fill and are separated by their label and border, because
grey is the layer's one "no value here" colour and inventing a second would imply a
value. The distinction that matters -- a measured cell is never grey, and a grey cell is
never annotated with a number -- is asserted by the tests.

Byte-reproducibility is claimed for the PNGs only. Matplotlib stamps every SVG with a
creation timestamp, so no SVG in this repository is byte-stable and this module makes no
such claim for its own.
"""

from __future__ import annotations

import textwrap
from typing import Any, Mapping, Sequence

import numpy as np

from population_synthetic.analysis.model_ranking.table_style import (
    ANNOT_FONTSIZE,
    BOX_EDGE,
    HOST_COLORS,
    HOST_DEFAULT_CLASS,
    HOST_LABELS,
    add_percentage_colorbar,
    best_cells_per_column,
    categories_on_top,
    horizontal_divider,
    inferno_cmap,
    vertical_divider,
)
from population_synthetic.analysis.utils.axes import strategy_complexity_order
from population_synthetic.analysis.utils.palette import (
    MISSING_COLOR,
    text_color_for_rgb,
    text_color_on,
)

__all__ = [
    "CELL_STATES",
    "plot_attrition_funnel",
    "plot_mapped_validity_grid",
]

#: The four mutually exclusive states a grid cell can be in, resolved in this order.
#: Named so the renderer, the legend and the tests all read from one list rather than
#: three copies of the same four strings.
CELL_STATES = ("absent", "undefined", "withdrawn", "measured")

#: Hatch marking a withdrawn cell. Coarse enough to read across a cell at print size
#: without obscuring the two lines of text it qualifies, which is set on a patch of the
#: cell's own fill so the hatch never crosses the number it qualifies. Left at the
#: default stroke width: the width is an rcParam read at *draw* time, and this module
#: returns an unsaved figure, so setting it here would mutate global state for every
#: other figure drawn in the process rather than for this one.
_WITHDRAWN_HATCH = "xxx"

#: Border on an ``undefined`` cell, which shares its grey with ``absent``. Dotted rather
#: than solid so the two greys are separable at a glance while neither reads as a value.
_UNDEFINED_EDGE_STYLE = (0, (1, 1.6))

#: The funnel's four disjoint slices of the generated pool, in draw order (widest stage
#: of the funnel last). ColorBrewer's 4-class RdBu: these encode **which stage** a
#: persona left at -- a category with a direction, not a score -- so they are
#: deliberately not the sequential score ramp, and the pair of blues (kept) reads against
#: the pair of reds (lost) without relying on hue discrimination alone.
_SEGMENTS: tuple[tuple[str, str, str], ...] = (
    ("selected", "#0571B0", "selected (drawn by the cap)"),
    ("clean_unselected", "#92C5DE", "clean, not drawn"),
    ("failed_mapped", "#F4A582", "failed the mapped-value gate"),
    ("failed_raw", "#CA0020", "failed the raw-completeness gate"),
)

#: Fill for a combination whose generated pool is empty: there is no composition to draw,
#: and a zero-width bar is indistinguishable from a missing row.
_EMPTY_POOL_COLOR = MISSING_COLOR

_CAPTION_WRAP = 150


def _combinations(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The document's combination entries, or raise when there are none to draw."""
    entries = document.get("combinations")
    if not entries:
        raise ValueError(
            "no combination in the attrition document to draw: the validation gate "
            "recorded nothing for this country."
        )
    return list(entries)


def _funnel_counts(entry: Mapping[str, Any]) -> tuple[int, int, int, int, int]:
    """The five funnel counts of *entry*, in funnel order."""
    funnel = entry["funnel"]
    return (
        int(funnel["generated"]),
        int(funnel["raw_valid"]),
        int(funnel["mapped_valid"]),
        int(funnel["clean"]),
        int(funnel["selected"]),
    )


def _segment_counts(entry: Mapping[str, Any]) -> dict[str, int]:
    """Partition the generated pool into the four disjoint slices the funnel draws.

    ``generated = (generated - raw_valid) + (raw_valid - clean) + (clean - selected) +
    selected``, an identity rather than an estimate: ``clean`` is by construction the
    subset of the raw-gate passers that also passed the mapped gate, so ``raw_valid -
    clean`` is exactly the personas the mapped gate rejected among those the raw gate
    kept. Every slice is a count difference, never a rate -- the rates on this figure are
    read from the document.

    Raises ``ValueError`` when the counts cannot be partitioned (a negative slice), which
    means the three gate records disagree about the same combination and no honest bar
    can be drawn from them.
    """
    generated, raw_valid, _mapped_valid, clean, selected = _funnel_counts(entry)
    slices = {
        "failed_raw": generated - raw_valid,
        "failed_mapped": raw_valid - clean,
        "clean_unselected": clean - selected,
        "selected": selected,
    }
    negative = {name: value for name, value in slices.items() if value < 0}
    if negative:
        raise ValueError(
            f"combination {entry['slug']!r}: the gate counts do not partition its "
            f"generated pool -- {negative} is negative for generated={generated}, "
            f"raw_valid={raw_valid}, clean={clean}, selected={selected}. Re-run the "
            "validation gate for this combination before charting it."
        )
    return slices


def _sort_key(entry: Mapping[str, Any]) -> tuple[int, float, str]:
    """Order combinations worst-surviving first, with undefined rates last.

    A pure ordering over the document's own ``retention_rate`` -- no value is derived
    here. The slug breaks every tie, so the row order is total and two runs over the same
    document draw the same figure.
    """
    rate = entry["retention_rate"]
    if rate is None:
        return (1, 0.0, entry["slug"])
    return (0, float(rate), entry["slug"])


def _pooled(entries: Sequence[Mapping[str, Any]]) -> tuple[float | None, int, int]:
    """``(clean / generated, clean, generated)`` pooled over *entries*.

    Count-weighted, not a mean of the per-cell rates: the pools behind the cells differ
    by a factor of five on the live grid, and averaging their rates would weight a
    110-persona combination equally with a 549-persona one. Returned with both counts so
    the caller can print the rate beside the base it was taken over.
    """
    generated = sum(_funnel_counts(entry)[0] for entry in entries)
    clean = sum(_funnel_counts(entry)[3] for entry in entries)
    if generated == 0:
        return (None, clean, generated)
    return (clean / generated, clean, generated)


def plot_attrition_funnel(document: Mapping[str, Any]):
    """Per-combination attrition funnel, normalised, one horizontal bar per combination.

    Each bar is one combination's generated pool cut into the four disjoint slices of
    :func:`_segment_counts` and drawn on a common 0--100% axis. Normalised because the
    absolute pools are not comparable -- they range from 110 to 549 on the live Swedish
    grid -- so a raw-count funnel would rank pool size and not survival. The count the
    normalisation divides by is printed at the end of every bar (``N=``) together with
    the combination's ``retention_rate`` read from the document, so no percentage on the
    figure sits over an unstated denominator.

    Rows are ordered worst-surviving first. A combination the full-N rule withdrew is
    labelled ``withdrawn`` beside its slug: its personas are real and were validated, but
    no downstream artifact contains them.

    Args:
        document: The built attrition document (``builder.build_document``).

    Returns:
        An unsaved ``matplotlib.figure.Figure``. The caller saves and closes it.

    Raises:
        ValueError: If the document carries no combination, or if a combination's counts
            do not partition its generated pool.
    """
    entries = sorted(_combinations(document), key=_sort_key)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    n_rows = len(entries)
    fig, ax = plt.subplots(figsize=(15.0, max(4.0, n_rows * 0.26 + 3.4)))

    labels: list[str] = []
    for index, entry in enumerate(entries):
        y = n_rows - 1 - index  # worst at the top
        generated = _funnel_counts(entry)[0]
        suffix = "  [withdrawn]" if entry["excluded"] else ""
        labels.append(f"{entry['slug']}{suffix}")

        if generated == 0:
            # No composition exists. Drawn as a full-width grey band rather than as an
            # absent row, so "generated nothing" is visible instead of looking like a
            # combination the figure forgot.
            ax.barh(y, 1.0, height=0.72, color=_EMPTY_POOL_COLOR, edgecolor="none")
            ax.text(
                0.5, y, "generated = 0 -- no pool to partition", ha="center", va="center",
                fontsize=ANNOT_FONTSIZE,
                color=text_color_for_rgb(_to_rgb(_EMPTY_POOL_COLOR)),
            )
            ax.text(1.02, y, "N=0", ha="left", va="center", fontsize=7.0)
            continue

        slices = _segment_counts(entry)
        left = 0.0
        for name, color, _legend in _SEGMENTS:
            width = slices[name] / generated
            if width > 0:
                ax.barh(y, width, left=left, height=0.72, color=color, edgecolor="none")
            left += width

        rate = entry["retention_rate"]
        ax.text(
            1.02, y, f"N={generated}   retained {rate * 100:.1f}%",
            ha="left", va="center", fontsize=7.0,
            fontweight="bold" if entry["excluded"] else "normal",
        )

    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(list(reversed(labels)), fontsize=6.5)
    for label, entry in zip(reversed(ax.get_yticklabels()), entries):
        if entry["excluded"]:
            label.set_color(_SEGMENTS[3][1])
            label.set_fontweight("bold")

    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(-0.8, n_rows - 0.2)
    ax.set_xticks([0.0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xticklabels(["0", "25", "50", "75", "100"], fontsize=8)
    ax.set_xlabel("share of the combination's generated pool (%)", fontsize=9)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    totals = document["totals"]
    ax.set_title(
        f"{document['country']}: validation attrition per combination "
        f"({document['n_combinations']} combinations, {document['n_excluded']} withdrawn)\n"
        "each bar is one combination's generated pool, normalised -- absolute pools are "
        "not comparable",
        fontsize=11, fontweight="bold", pad=14,
    )

    handles = [
        Patch(facecolor=color, edgecolor="none", label=legend)
        for _name, color, legend in _SEGMENTS
    ]
    ax.legend(
        handles=handles, loc="upper left", bbox_to_anchor=(0.0, -0.04),
        ncol=4, fontsize=7.5, frameon=False,
    )

    pooled_rate = totals["retention_rate"]
    pooled_text = (
        "n/a" if pooled_rate is None else f"{pooled_rate * 100:.1f}%"
    )
    caption = (
        "Bar, left to right: the four disjoint fates of one combination's generated personas "
        "-- drawn by the seeded cap, clean but not drawn, passed the raw-completeness gate but "
        "failed the mapped-value gate, failed the raw gate. The four sum to the pool exactly, "
        "so the bar is a "
        "partition and not a stack of overlapping counts. N is that pool, printed on every "
        "row: the percentage axis is a share of it, never of the sweep. 'retained' is the "
        "document's retention_rate (clean / generated), read from the same record the CSV "
        f"publishes. Pooled over every combination shown: {totals['clean']} clean of "
        f"{totals['generated']} generated ({pooled_text}), {totals['selected']} selected. A "
        "withdrawn combination held fewer clean personas than the requested cap, so the "
        "gate excluded it: its personas were generated and validated but reach no other "
        "artifact in the analysis layer."
    )
    ax.text(
        0.0, -0.075, textwrap.fill(caption, _CAPTION_WRAP), transform=ax.transAxes,
        ha="left", va="top", fontsize=7, clip_on=False,
    )

    fig.tight_layout()
    return fig


def _to_rgb(color: str):
    """``matplotlib.colors.to_rgb``, imported lazily like every other pyplot piece."""
    import matplotlib.colors as mcolors

    return mcolors.to_rgb(color)


def _cell_state(entry: Mapping[str, Any] | None) -> str:
    """Which of :data:`CELL_STATES` *entry* is in; ``None`` means the pair is absent.

    Resolution order is ``absent`` -> ``undefined`` -> ``withdrawn`` -> ``measured``.
    ``undefined`` outranks ``withdrawn`` because a withdrawn combination with an empty
    pool has no rate to paint -- the withdrawal is still marked on the cell, but the fill
    cannot pretend to a value.
    """
    if entry is None:
        return "absent"
    if entry["retention_rate"] is None:
        return "undefined"
    if entry["excluded"]:
        return "withdrawn"
    return "measured"


def plot_mapped_validity_grid(
    document: Mapping[str, Any],
    *,
    hosting: Mapping[str, str] | None = None,
):
    """Model x method grid of validation survival -- the mapping-survival figure.

    Each cell is that combination's ``retention_rate`` read from the document: the share
    of its generated pool that passed **both** validity gates and so was available to the
    cap. Printed as a percentage together with the two counts it is the quotient of
    (``clean/generated``), so the rate never travels without its denominator. Columns are
    methods in :func:`~population_synthetic.analysis.utils.axes.strategy_complexity_order`
    -- a config fact, not an artifact of this figure -- and rows are models ordered by
    their pooled survival, worst last.

    This is the one artifact in the analysis layer on which a **withdrawn** combination
    appears at all: every other consumer reads the capped mirror, which an excluded
    combination has none of. Withdrawn cells therefore carry their measured rate and a
    hatch, and are never collapsed into the grey of a combination that was never
    generated. See the module docstring for the four states.

    Args:
        document: The built attrition document (``builder.build_document``).
        hosting: Optional ``{model_id: "local"|"hosted"}`` provenance map used to colour
            the row labels, matching the sibling fidelity grids. A model absent from it
            is drawn in the shared presentation default; ``None`` colours every row in
            it, which is a label colour and affects no value.

    Returns:
        An unsaved ``matplotlib.figure.Figure``. The caller saves and closes it.

    Raises:
        ValueError: If the document carries no combination, or no method that
            ``strategy_complexity_order`` can rank.
    """
    entries = _combinations(document)
    by_cell = {(entry["model"], entry["strategy"]): entry for entry in entries}
    methods = strategy_complexity_order([entry["strategy"] for entry in entries])
    if not methods:
        raise ValueError("no method column to draw: every combination lacks a strategy id.")

    models = sorted({entry["model"] for entry in entries})
    row_pooled = {
        model: _pooled([e for e in entries if e["model"] == model]) for model in models
    }
    # Worst-surviving last; a model with no defined pooled rate sorts to the very end.
    models.sort(
        key=lambda m: (
            row_pooled[m][0] is None,
            -(row_pooled[m][0] or 0.0),
            m,
        )
    )

    values = np.full((len(models), len(methods)), np.nan, dtype=float)
    states: list[list[str]] = []
    for i, model in enumerate(models):
        row_states = []
        for j, method in enumerate(methods):
            entry = by_cell.get((model, method))
            state = _cell_state(entry)
            row_states.append(state)
            if state in ("measured", "withdrawn"):
                values[i, j] = float(entry["retention_rate"])
        states.append(row_states)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch, Rectangle

    cmap = inferno_cmap()
    # Fixed 0--1: a survival share has a meaningful full range, and rescaling to the
    # observed one would make two runs' grids incomparable at a glance.
    norm = mcolors.Normalize(vmin=0.0, vmax=1.0)

    n_methods = len(methods)
    marginal_columns = 1.5
    fig, ax = plt.subplots(
        figsize=(
            max(9.0, (n_methods + marginal_columns) * 1.5 + 3.0),
            max(4.5, len(models) * 0.62 + 3.6),
        )
    )
    im = ax.imshow(
        np.ma.masked_invalid(values), cmap=cmap, norm=norm,
        aspect="auto", interpolation="nearest",
        extent=(-0.5, n_methods - 0.5, len(models) - 0.5, -0.5),
    )
    marginal_y = len(models) - 0.5 + 0.7
    ax.set_xlim(-0.5, n_methods - 0.5 + marginal_columns)
    ax.set_ylim(marginal_y + 0.5, -0.5)

    categories_on_top(ax, methods)
    ax.set_yticks(range(len(models)))
    ax.set_yticklabels(models, fontsize=8)
    hosting = dict(hosting or {})
    for label, model in zip(ax.get_yticklabels(), models):
        label.set_color(HOST_COLORS[hosting.get(model, HOST_DEFAULT_CLASS)])

    missing_text_color = text_color_for_rgb(_to_rgb(MISSING_COLOR))
    best = best_cells_per_column(values)
    for i, model in enumerate(models):
        for j, method in enumerate(methods):
            state = states[i][j]
            entry = by_cell.get((model, method))
            if state == "absent":
                ax.text(
                    j, i, "not\ngenerated", ha="center", va="center",
                    fontsize=ANNOT_FONTSIZE, color=missing_text_color, linespacing=1.3,
                )
                continue
            if state == "undefined":
                ax.text(
                    j, i, "no rate\nN=0", ha="center", va="center",
                    fontsize=ANNOT_FONTSIZE, color=missing_text_color, linespacing=1.3,
                )
                ax.add_patch(
                    Rectangle(
                        (j - 0.5, i - 0.5), 1, 1, fill=False, linewidth=1.1,
                        linestyle=_UNDEFINED_EDGE_STYLE, edgecolor=BOX_EDGE, zorder=4,
                    )
                )
            else:
                value = float(values[i, j])
                clean = _funnel_counts(entry)[3]
                generated = _funnel_counts(entry)[0]
                color = text_color_on(im, value)
                fill = cmap(norm(value))
                ax.text(
                    j, i, f"{value * 100:.1f}\n{clean}/{generated}",
                    ha="center", va="center", fontsize=ANNOT_FONTSIZE,
                    color=color, linespacing=1.35,
                    bbox=(
                        {"facecolor": fill, "edgecolor": "none", "pad": 1.4}
                        if state == "withdrawn" else None
                    ),
                    zorder=5,
                )
                if (i, j) in best:
                    ax.add_patch(
                        Rectangle(
                            (j - 0.5, i - 0.5), 1, 1, fill=False, linewidth=1.4,
                            edgecolor=BOX_EDGE, zorder=3,
                        )
                    )
            if entry is not None and entry["excluded"]:
                # Drawn for `withdrawn` AND for an `undefined` cell that was also
                # withdrawn: the fill cannot carry a rate there, but the withdrawal is a
                # separate fact and is never dropped.
                ax.add_patch(
                    Rectangle(
                        (j - 0.5, i - 0.5), 1, 1, fill=False, linewidth=0.0,
                        hatch=_WITHDRAWN_HATCH, edgecolor=BOX_EDGE, zorder=2,
                    )
                )

    vertical_divider(ax, n_methods)
    horizontal_divider(ax, len(models) - 0.5 + 0.5)

    for i, model in enumerate(models):
        rate, clean, generated = row_pooled[model]
        text = "n/a" if rate is None else f"{rate * 100:.1f}%"
        ax.text(
            n_methods - 0.5 + 0.12, i, f"{text}  ({clean}/{generated})",
            ha="left", va="center", fontsize=7.5, clip_on=False,
        )
    for j, method in enumerate(methods):
        rate, clean, generated = _pooled([e for e in entries if e["strategy"] == method])
        text = "n/a" if rate is None else f"{rate * 100:.1f}%"
        ax.text(
            j, marginal_y, f"{text}\n({clean}/{generated})",
            ha="center", va="center", fontsize=7.5, linespacing=1.3,
        )
    ax.text(
        -0.6, marginal_y, "method pooled", ha="right", va="center", fontsize=7.5,
        clip_on=False,
    )

    add_percentage_colorbar(fig, im, ax, "personas surviving both validity gates (%)")

    classes_present = {hosting.get(model, HOST_DEFAULT_CLASS) for model in models}
    handles = [
        Patch(facecolor=HOST_COLORS[c], edgecolor="none", label=HOST_LABELS[c])
        for c in ("hosted", "local") if c in classes_present
    ]
    handles += [
        Patch(
            facecolor="none", edgecolor=BOX_EDGE, hatch=_WITHDRAWN_HATCH,
            label="hatched: withdrawn (below the requested cap; in no other artifact)",
        ),
        Patch(facecolor=MISSING_COLOR, edgecolor="none", label="grey: never generated"),
        Patch(
            facecolor=MISSING_COLOR, edgecolor=BOX_EDGE, linestyle=_UNDEFINED_EDGE_STYLE,
            label="grey, dotted: recorded with an empty pool -- rate undefined",
        ),
        Patch(facecolor="none", edgecolor=BOX_EDGE, label="boxed: best in column"),
    ]
    ax.legend(
        handles=handles, loc="upper left", bbox_to_anchor=(0.0, -0.02),
        ncol=2, fontsize=7.5, title="provenance / cell state", title_fontsize=8,
        frameon=False,
    )

    ax.set_title(
        f"{document['country']}: validation survival by model x method\n"
        "share of each combination's generated pool that passed both validity gates -- "
        f"{document['n_excluded']} of {document['n_combinations']} combinations withdrawn",
        fontsize=11, fontweight="bold", pad=30,
    )

    caption = (
        "Cell: retention_rate (clean / generated) as published in the attrition CSV, "
        "printed with the two counts it is the quotient of. 'clean' means a persona passed "
        "the raw-completeness gate AND the mapped-value gate; the colour scale is the full "
        "0-100% range, not the observed one, so grids from different runs are comparable. "
        "Marginals are pooled over persona counts, not means of the cell rates -- the pools "
        "behind the cells differ by a factor of five, and an unweighted mean would give a "
        "110-persona combination the weight of a 549-persona one. Four cell states are drawn "
        "and never collapsed: a measured rate, a measured rate the full-N rule withdrew "
        "(hatched -- present here and in no other artifact), a combination recorded with an "
        "empty pool (dotted grey, no rate exists), and a pair that was never generated "
        "(plain grey). A withdrawn cell is not a zero and an absent cell is not a zero."
    )
    ax.text(
        0.0, -0.155, textwrap.fill(caption, _CAPTION_WRAP), transform=ax.transAxes,
        ha="left", va="top", fontsize=7, clip_on=False,
    )

    fig.tight_layout()
    return fig
