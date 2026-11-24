"""charts.py -- render the two attrition figures. Draws only; computes no statistic.

Both renderers take the document
:func:`~population_synthetic.analysis.validation_attrition.builder.build_document`
assembled and **return** an unsaved ``Figure``; the driver owns the path, the dpi and
the PNG+SVG+EPS trio (``analysis/utils/figures.py::save_figure``). Nothing here opens a
file, resolves an output directory or knows which country it is drawing -- the country
travels in the document like every other value.

**Every published rate is read, never recomputed** (guide 02 sect. 9). ``retention_rate``
is derived once, in the builder, and the grid renders that field verbatim, so the CSV,
the JSON and the figure cannot disagree about a cell. The only arithmetic in this module
is the funnel's bar geometry -- three disjoint slices of one combination's finished pool,
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
    A combination the gate recorded whose finished pool is empty, so no rate exists.
    Grey, labelled with its zero pool -- never ``0.0``, which would claim a pool
    finished and was wholly discarded.
``absent``
    No such ``(model, method)`` combination in the run at all. Grey, labelled as not
    generated.

The two grey states share a fill and are separated by their label and border, because
grey is the layer's one "no value here" colour and inventing a second would imply a
value. The distinction that matters -- a measured cell is never grey, and a grey cell is
never annotated with a number -- is asserted by the tests.

**The grid is published twice from one renderer.** The clean variant -- the camera-ready
one, published at the bare filename -- prints the rate alone, one step up the house scale
on the room the dropped line frees; the ``_with_counts`` sibling prints it together with
the two counts it is the quotient of. They are the same figure in every other respect --
rows, columns, extent, colour scale, markings, marginals -- because the only thing that
varies between them is the annotation policy handed to
``analysis/utils/grids.py::render_grid``. A second ``..._clean()`` function would have
duplicated the draw loop, and the two would have diverged on the first edit. The record
that pairs a policy with its wording and its type size, and the rule that gives the clean
variant the unsuffixed name, are shared with every other varianted grid in the layer
(``analysis/utils/grid_variants.py``).

Byte-reproducibility is claimed for the PNGs only. Matplotlib stamps every SVG with a
creation timestamp, so no SVG in this repository is byte-stable and this module makes no
such claim for its own.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from population_synthetic.analysis.utils.axes import strategy_complexity_order
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
    country_label,
    method_key_lines,
    method_letters,
    model_labels,
)
from population_synthetic.analysis.utils.palette import (
    HOST_COLORS,
    MISSING_COLOR,
    STAGE_SERIES,
    text_color_for_rgb,
)
from population_synthetic.analysis.utils.style import (
    ANNOTATION,
    ANNOTATION_LARGE,
    AXIS_TITLE,
    FULL,
    LEGEND_LABEL,
    LEGEND_TITLE,
    PANEL_TITLE,
    TICK_LABEL,
    caption_block,
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
    best_cells_per_column,
    categories_on_top,
    fit_to_page,
    horizontal_divider,
    inferno_cmap,
    vertical_divider,
)

__all__ = [
    "CELL_STATES",
    "GRID_VARIANTS",
    "GRID_VARIANT_CLEAN",
    "GRID_VARIANT_WITH_COUNTS",
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

#: The funnel's three disjoint slices of the finished (raw-valid) pool, in draw order (widest stage
#: of the funnel last), on the palette's stage series: these encode **which stage** a
#: persona left at -- a category with a direction, not a score -- so they are
#: deliberately not the sequential score ramp, and the pair of blues (kept) reads against
#: the pair of reds (lost) without relying on hue discrimination alone.
_SEGMENTS: tuple[tuple[str, str, str], ...] = (
    ("selected", STAGE_SERIES[0], "selected (drawn by the cap)"),
    ("clean_unselected", STAGE_SERIES[1], "clean, not drawn"),
    ("failed_mapped", STAGE_SERIES[2], "failed the mapped-value gate"),
)

#: Colour of a withdrawn row's label: the stage series' last hue, which no bar slice
#: uses since unfinished generations left the bar.
_WITHDRAWN_LABEL_COLOR = STAGE_SERIES[3]

#: Fill for a combination whose finished pool is empty: there is no composition to draw,
#: and a zero-width bar is indistinguishable from a missing row.
_EMPTY_POOL_COLOR = MISSING_COLOR


#: The counted sibling: the rate over the two counts it is the quotient of. Written to
#: ``..._with_counts``, so nothing this figure ever printed is lost.
GRID_VARIANT_WITH_COUNTS = GridVariant(
    name=COUNTED_VARIANT,
    policy=RateWithCountsPolicy(
        value_key="rate", numerator_key="numerator", denominator_key="denominator",
    ),
    cell_clause=(
        "Cell: retention_rate (clean / finished) as published in the attrition CSV, "
        "printed with the two counts it is the quotient of."
    ),
    fontsize=ANNOT_FONTSIZE,
    linespacing=1.35,
)

#: The camera-ready variant, published at the bare filename: the rate alone, one step
#: larger. The counts it drops are not lost -- they are in the CSV, in the counted sibling
#: and in the row marginals -- so this variant costs ink rather than evidence.
GRID_VARIANT_CLEAN = GridVariant(
    name=CANONICAL_VARIANT,
    policy=RateOnlyPolicy(value_key="rate"),
    cell_clause=(
        "Cell: retention_rate (clean / finished) as published in the attrition CSV. The "
        "two counts behind each rate are printed on the with-counts sibling figure and in "
        "the CSV; the pooled marginals here carry theirs."
    ),
    fontsize=ANNOTATION_LARGE,
    linespacing=None,
)

#: The publishable variants by name, so a driver enumerates them instead of naming them.
#: The clean one is first because it is the one published at the bare filename.
GRID_VARIANTS: dict[str, GridVariant] = variant_map(
    GRID_VARIANT_CLEAN, GRID_VARIANT_WITH_COUNTS,
)


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
    """Partition the finished pool into the three disjoint slices the funnel draws.

    ``raw_valid = (raw_valid - clean) + (clean - selected) + selected``, an identity rather
    than an estimate: ``clean`` is by construction the subset of the raw-gate passers that
    also passed the mapped gate, so ``raw_valid - clean`` is exactly the personas the
    mapped gate rejected among those the raw gate kept. The ``generated - raw_valid``
    personas the raw gate rejected are generations stopped midway; they are not part of
    the bar, and their count is printed beside it instead.
    Every slice is a count difference, never a rate -- the rates on this figure are read
    from the document.

    Raises ``ValueError`` when the counts cannot be partitioned (a negative slice), which
    means the three gate records disagree about the same combination and no honest bar
    can be drawn from them.
    """
    generated, raw_valid, _mapped_valid, clean, selected = _funnel_counts(entry)
    slices = {
        "failed_mapped": raw_valid - clean,
        "clean_unselected": clean - selected,
        "selected": selected,
    }
    negative = {name: value for name, value in slices.items() if value < 0}
    if negative:
        raise ValueError(
            f"combination {entry['slug']!r}: the gate counts do not partition its "
            f"finished pool -- {negative} is negative for generated={generated}, "
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
    """``(clean / raw_valid, clean, raw_valid)`` pooled over *entries*.

    Count-weighted, not a mean of the per-cell rates: the pools behind the cells differ
    by a factor of five on the live grid, and averaging their rates would weight a
    110-persona combination equally with a 549-persona one. Returned with both counts so
    the caller can print the rate beside the base it was taken over.
    """
    raw_valid = sum(_funnel_counts(entry)[1] for entry in entries)
    clean = sum(_funnel_counts(entry)[3] for entry in entries)
    if raw_valid == 0:
        return (None, clean, raw_valid)
    return (clean / raw_valid, clean, raw_valid)


@house_style
def plot_attrition_funnel(document: Mapping[str, Any]):
    """Per-combination attrition funnel, normalised, one horizontal bar per combination.

    Each bar is one combination's finished pool cut into the three disjoint slices of
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
            do not partition its finished pool.
    """
    entries = sorted(_combinations(document), key=_sort_key)

    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    n_rows = len(entries)
    fig, ax = plt.subplots(figsize=(FULL, grow_height(n_rows, per_item=0.26, padding=3.4, minimum=4.0)))

    # Row captions are the model's display name and the combination's method letter,
    # resolved over the whole figure's id set because a letter's version marker is a
    # property of the set. The key travels with the caption block below.
    display_models = model_labels([entry["model"] for entry in entries])
    letters = method_letters([entry["strategy"] for entry in entries])
    labels: list[str] = []
    for index, entry in enumerate(entries):
        y = n_rows - 1 - index  # worst at the top
        generated, raw_valid = _funnel_counts(entry)[:2]
        suffix = "  [withdrawn]" if entry["excluded"] else ""
        labels.append(
            f"{display_models[entry['model']]} / {letters[entry['strategy']]}{suffix}"
        )

        unfinished = generated - raw_valid
        unfinished_text = f"   ({unfinished} unfinished ignored)" if unfinished else ""
        if raw_valid == 0:
            # No composition exists. Drawn as a full-width grey band rather than as an
            # absent row, so "nothing finished" is visible instead of looking like a
            # combination the figure forgot.
            ax.barh(y, 1.0, height=0.72, color=_EMPTY_POOL_COLOR, edgecolor="none")
            ax.text(
                0.5, y, "finished = 0 -- no pool to partition", ha="center", va="center",
                fontsize=ANNOT_FONTSIZE,
                color=text_color_for_rgb(_to_rgb(_EMPTY_POOL_COLOR)),
            )
            ax.text(1.02, y, f"N=0{unfinished_text}", ha="left", va="center", fontsize=ANNOTATION)
            continue

        slices = _segment_counts(entry)
        left = 0.0
        for name, color, _legend in _SEGMENTS:
            width = slices[name] / raw_valid
            if width > 0:
                ax.barh(y, width, left=left, height=0.72, color=color, edgecolor="none")
            left += width

        rate = entry["retention_rate"]
        ax.text(
            1.02, y, f"N={raw_valid}   retained {rate * 100:.1f}%{unfinished_text}",
            ha="left", va="center", fontsize=ANNOTATION,
            fontweight="bold" if entry["excluded"] else "normal",
        )

    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(list(reversed(labels)), fontsize=TICK_LABEL)
    for label, entry in zip(reversed(ax.get_yticklabels()), entries):
        if entry["excluded"]:
            label.set_color(_WITHDRAWN_LABEL_COLOR)
            label.set_fontweight("bold")

    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(-0.8, n_rows - 0.2)
    ax.set_xticks([0.0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xticklabels(["0", "25", "50", "75", "100"], fontsize=TICK_LABEL)
    ax.set_xlabel("share of the combination's finished pool (%)", fontsize=AXIS_TITLE)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    totals = document["totals"]
    ax.set_title(
        f"{country_label(document['country'])}: validation attrition per combination "
        f"({document['n_combinations']} combinations, {document['n_excluded']} withdrawn)\n"
        "each bar is one combination's finished pool, normalised -- absolute pools are "
        "not comparable",
        fontsize=PANEL_TITLE, fontweight="bold", pad=14,
    )

    handles = [
        Patch(facecolor=color, edgecolor="none", label=legend)
        for _name, color, legend in _SEGMENTS
    ]
    ax.legend(
        handles=handles, loc="upper left", bbox_to_anchor=(0.0, -0.04),
        ncol=3, fontsize=LEGEND_LABEL, frameon=False,
    )

    pooled_rate = totals["retention_rate"]
    pooled_text = (
        "n/a" if pooled_rate is None else f"{pooled_rate * 100:.1f}%"
    )
    caption = (
        "Bar, left to right: the three disjoint fates of one combination's finished personas "
        "-- drawn by the seeded cap, clean but not drawn, passed the raw-completeness gate but "
        "failed the mapped-value gate. The three sum to the finished pool exactly, so the bar "
        "is a partition and not a stack of overlapping counts. N is that pool (personas whose "
        "generation completed), printed on every row: the percentage axis is a share of it, "
        "never of the sweep. Generations stopped midway fail the raw-completeness gate; they "
        "are an artefact of interrupting a run, are ignored by every rate and are only "
        "counted beside the bar. 'retained' is the document's retention_rate "
        "(clean / finished), read from the same record the CSV publishes. Pooled over every "
        f"combination shown: {totals['clean']} clean of {totals['raw_valid']} finished "
        f"({pooled_text}; {totals['generated']} generated), {totals['selected']} selected. A "
        "withdrawn combination held fewer clean personas than the requested cap, so the "
        "gate excluded it: its personas were generated and validated but reach no other "
        "artifact in the analysis layer."
    )
    # The row captions carry method letters, so the key travels on the figure with them.
    key = "Methods:  " + "   ".join(method_key_lines([e["strategy"] for e in entries]))
    # Drawn as a figure-width block rather than as unclipped axes text: the axes are
    # inset from the paper by the label column, so a caption anchored at their left
    # edge ran off the right of the page and grew the exported canvas with it.
    caption_block(fig, f"{key}\n{caption}", fontsize=ANNOTATION)
    # The title is centred on the axes and the legend is anchored to them, so both
    # inherit the label column's inset and reach past the right edge of the page.
    fit_to_page(fig)
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


@house_style
def plot_mapped_validity_grid(
    document: Mapping[str, Any],
    *,
    hosting: Mapping[str, str] | None = None,
    variant: GridVariant = GRID_VARIANT_CLEAN,
):
    """Model x method grid of validation survival -- the mapping-survival figure.

    Each cell is that combination's ``retention_rate`` read from the document: the share
    of its finished pool that passed **both** validity gates and so was available to the
    cap. Columns are methods in
    :func:`~population_synthetic.analysis.utils.axes.strategy_complexity_order` -- a
    config fact, not an artifact of this figure -- lettered from the family index, with
    the key drawn on the figure; rows are models ordered by their pooled survival, worst
    last, under their display labels. No axis carries a config id.

    What a cell *prints* is the *variant*'s decision and the only difference between the
    two publications of this figure: the clean one prints the rate alone one step larger,
    the with-counts one prints it together with the two counts it is the quotient of.
    Everything else -- the rows, the columns, the extent, the colour scale, the markings
    and the marginals -- is shared, because both go through the same draw loop
    (:func:`~population_synthetic.analysis.utils.grids.render_grid`) with different
    annotation policies rather than through two functions that would diverge on the next
    edit. The row and column marginals always print their counts, so the clean variant
    still shows every rate on the figure over a stated base.

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
        variant: Which publication of the figure to draw -- :data:`GRID_VARIANT_CLEAN`
            (the default, and the one published at the bare filename) or
            :data:`GRID_VARIANT_WITH_COUNTS`.

    Returns:
        An unsaved ``matplotlib.figure.Figure``. The caller saves and closes it.

    Raises:
        ValueError: If the document carries no combination, or no method that
            ``strategy_complexity_order`` can rank.
        UnknownAxisValue: If a model or strategy id on the grid has no display label.
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
    # One record per cell for the shared renderer, and the mask saying which annotations
    # need a patch of their own fill under them. A cell with no rate carries no record:
    # its wording is a statement about the *state* rather than about a value, and it is
    # drawn below in the state's own colour.
    cells: list[list[dict[str, Any] | None]] = []
    text_on_fill: list[list[bool]] = []
    for i, model in enumerate(models):
        row_states: list[str] = []
        row_cells: list[dict[str, Any] | None] = []
        row_fill: list[bool] = []
        for j, method in enumerate(methods):
            entry = by_cell.get((model, method))
            state = _cell_state(entry)
            row_states.append(state)
            if state in ("measured", "withdrawn"):
                rate = float(entry["retention_rate"])
                values[i, j] = rate
                _generated, raw_valid, _mapped_valid, clean, _selected = _funnel_counts(entry)
                row_cells.append({"rate": rate, "numerator": clean, "denominator": raw_valid})
                # A withdrawn cell is hatched; the patch keeps the hatch off its number.
                row_fill.append(state == "withdrawn")
            else:
                row_cells.append(None)
                row_fill.append(False)
        states.append(row_states)
        cells.append(row_cells)
        text_on_fill.append(row_fill)

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
            grow_width(n_methods + marginal_columns, per_item=1.5, padding=3.0, minimum=FULL),
            grow_height(len(models), per_item=0.62, padding=3.6, minimum=4.5),
        ),
    )
    im = render_grid(
        ax, values, cells,
        policy=variant.policy, cmap=cmap, norm=norm,
        aspect="auto", interpolation="none",
        extent=(-0.5, n_methods - 0.5, len(models) - 0.5, -0.5),
        fontsize=variant.fontsize, linespacing=variant.linespacing, zorder=5,
        text_on_fill=text_on_fill,
    )
    marginal_y = len(models) - 0.5 + 0.7
    ax.set_xlim(-0.5, n_methods - 0.5 + marginal_columns)
    ax.set_ylim(marginal_y + 0.5, -0.5)

    letters = method_letters(methods)
    categories_on_top(ax, [letters[method] for method in methods])
    display_models = model_labels(models)
    ax.set_yticks(range(len(models)))
    ax.set_yticklabels([display_models[model] for model in models], fontsize=TICK_LABEL)
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
            elif (i, j) in best:
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
        rate, clean, finished = row_pooled[model]
        text = "n/a" if rate is None else f"{rate * 100:.1f}%"
        ax.text(
            n_methods - 0.5 + 0.12, i, f"{text}  ({clean}/{finished})",
            ha="left", va="center", fontsize=ANNOTATION, clip_on=False,
        )
    for j, method in enumerate(methods):
        rate, clean, finished = _pooled([e for e in entries if e["strategy"] == method])
        text = "n/a" if rate is None else f"{rate * 100:.1f}%"
        ax.text(
            j, marginal_y, f"{text}\n({clean}/{finished})",
            ha="center", va="center", fontsize=ANNOTATION, linespacing=1.3,
        )
    ax.text(
        -0.6, marginal_y, "method pooled", ha="right", va="center", fontsize=ANNOTATION,
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
        ncol=2, fontsize=LEGEND_LABEL, title="provenance / cell state", title_fontsize=LEGEND_TITLE,
        frameon=False,
    )

    ax.set_title(
        f"{country_label(document['country'])}: validation survival by model x method\n"
        "share of each combination's finished pool that passed both validity gates -- "
        f"{document['n_excluded']} of {document['n_combinations']} combinations withdrawn",
        fontsize=PANEL_TITLE, fontweight="bold", pad=30,
    )

    caption = (
        f"{variant.cell_clause} "
        "'clean' means a persona passed the raw-completeness gate AND the mapped-value "
        "gate, out of the personas whose generation finished (a generation stopped midway "
        "is ignored); the colour scale is the full "
        "0-100% range, not the observed one, so grids from different runs are comparable. "
        "Marginals are pooled over persona counts, not means of the cell rates -- the pools "
        "behind the cells differ by a factor of five, and an unweighted mean would give a "
        "110-persona combination the weight of a 549-persona one. Four cell states are drawn "
        "and never collapsed: a measured rate, a measured rate the full-N rule withdrew "
        "(hatched -- present here and in no other artifact), a combination recorded with an "
        "empty pool (dotted grey, no rate exists), and a pair that was never generated "
        "(plain grey). A withdrawn cell is not a zero and an absent cell is not a zero."
    )
    # The method key travels in the graphic rather than being deferred to the caption:
    # the letters on the column axis are meaningless without it, and a figure is read
    # apart from the text that published it.
    key = "Methods:  " + "   ".join(method_key_lines(methods))
    caption_block(fig, f"{key}\n{caption}", fontsize=ANNOTATION)
    # The title is centred on the axes and the legend is anchored to them, so both
    # inherit the label column's inset and reach past the right edge of the page.
    fit_to_page(fig)
    return fig
