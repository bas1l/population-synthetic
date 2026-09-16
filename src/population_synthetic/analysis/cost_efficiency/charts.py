"""charts.py -- render the accuracy-vs-cost scatter. Draws only; computes no statistic.

The renderer takes the document
:func:`~population_synthetic.analysis.cost_efficiency.builder.build_document` assembled
and **returns** an unsaved ``Figure``; the driver owns the path, the dpi and the
PNG+SVG+EPS trio (``analysis/utils/figures.py::save_figure``). Nothing here opens a file, resolves an
output directory or knows which country it is drawing -- the country travels in the
document like every other value.

**Every plotted number and every printed caveat is read from the document**, never
recomputed and never written as a literal (guide 02 sect. 9; ADR 2026-08-12 Decision 2).
``cost_per_usable_persona`` is derived once, in the builder; the cost basis, the
unmetered note and the non-composite declaration are fields on the document. A figure and
the table beside it therefore cannot disagree about what they are showing.

**Why a symlog x-axis.** About a third of the model axis is *unmetered* -- priced
``{in: 0, out: 0}`` in the pricing config, the local ``ollama_*`` models -- so their
measured cost is exactly ``0.0``. A log axis, which the four-orders-of-magnitude spread
of the metered models otherwise demands, cannot place zero at all; a linear axis crushes
every metered model into the left margin. ``symlog`` is linear across a narrow band
around zero and logarithmic outside it, which is the only scaling that shows both
populations honestly. The band is drawn and **labelled**, because an unlabelled linear
region on a log axis silently misstates every distance inside it.

**Unmetered is not free.** The band's label says so on the figure, from the document's
own ``unmetered_note``. Rendering a local model at zero dollars without that sentence
would publish the claim that local inference costs nothing, which this pipeline's pricing
config does not measure and cannot support.

**Nothing is silently dropped.** Two kinds of combination cannot be drawn on these axes,
and both are counted on the figure rather than omitted (guide 03 sect. 7): the ones the
full-N rule withdrew, which have no accuracy score at all, and any whose run reported no
token telemetry, which have no cost. Their counts and their measured spend live in the
JSON.

**No composite score is drawn** -- no accuracy-per-dollar contour, no ranking, no
frontier line. Accuracy and cost are two axes and the trade-off is the reader's; a drawn
frontier would encode an exchange rate between them that no reader can see or dispute.

Byte-reproducibility is claimed for the PNG only. Matplotlib stamps every SVG with a
creation timestamp, so no SVG in this repository is byte-stable.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from population_synthetic.analysis.utils.axes import strategy_complexity_order
from population_synthetic.analysis.utils.labels import (
    country_label,
    method_key_lines,
    method_letters,
    model_label,
)
from population_synthetic.analysis.utils.palette import (
    ANNOTATION_GREY,
    BAND_EDGE,
    BAND_FILL,
    CAPTION_GREY,
    FOOTNOTE_GREY,
    GRID_RULE,
    HOST_COLORS,
    ORDERED_QUALITATIVE_SERIES,
    SURFACE,
    opaque,
)
from population_synthetic.analysis.utils.style import (
    ANNOTATION,
    AXIS_TITLE,
    CAPTION_MARGIN_IN,
    FIGURE_TITLE,
    FULL,
    LEGEND_LABEL,
    LEGEND_TITLE,
    LINE_SPACING,
    MAX_HEIGHT,
    POINTS_PER_INCH,
    house_style,
    wrap_to_width,
)
from population_synthetic.analysis.utils.table_style import (
    HOST_DEFAULT_CLASS,
    HOST_LABELS,
    fit_to_page,
)

__all__ = [
    "HOST_MARKERS",
    "METHOD_COLORS",
    "plot_cost_vs_accuracy",
]

#: Marker shape per hosting class. Identity is carried by **shape as well as hue** so the
#: figure survives greyscale printing and colour-vision deficiency, and because the
#: hosted/local split is exactly the split that determines whether a point can leave the
#: unmetered band at all.
HOST_MARKERS = {"hosted": "o", "local": "s"}

#: Colour series for the generation methods, cycled in complexity order. The palette's
#: ordered-qualitative series: the methods do have an order, but it is read off the
#: legend -- which is printed in that order -- rather than off the hue.
METHOD_COLORS = ORDERED_QUALITATIVE_SERIES

#: Fraction of the smallest positive cost used as the symlog linear threshold. Small
#: enough that no metered point falls inside the linear band (so every drawn distance
#: between metered models is a true log distance), large enough that the zero-cost points
#: are not painted onto the axis spine.
_LINTHRESH_FRACTION = 0.2

#: How far across the band the unmetered points are spread, as a fraction of the linear
#: threshold on each side of zero. **Every point inside the band is a measured 0.00 USD**;
#: the horizontal offset is a legibility device and carries no cost information, which is
#: why the band's own on-figure label says exactly that. Without it the thirteen
#: zero-cost combinations stack on one vertical line and their model labels overlap into
#: an unreadable block -- which loses information as surely as omitting them would.
_BAND_SPREAD = 0.72

#: Fill and edge for the unmetered band.
_BAND_COLOR = BAND_FILL
_BAND_EDGE = BAND_EDGE

#: Fallback linear threshold when *every* combination is unmetered and there is no
#: positive cost to scale against. The axis is then entirely inside the band, which is
#: itself the finding, and the caption says so.
_FALLBACK_LINTHRESH = 1e-4

#: Gap, in inches, between the legend strip and the caption block beneath it. One
#: annotation line, so the two blocks read as separate without a rule between them.
_LEGEND_GAP_IN = ANNOTATION * LINE_SPACING / POINTS_PER_INCH

#: Columns of the method legend in the strip under the axes. Three, so the five-family
#: key is two rows deep whatever the run's method set, and the hosting legend still has
#: the right-hand half of the strip to itself.
_LEGEND_COLUMNS = 3

#: Right edge of the axes in figure coordinates. Not 1.0: the rightmost x tick label is
#: centred on the axes' right edge, so an axes flush to the paper puts half a label past
#: it -- which the save-time tight bounding box picks up as an overhang.
_AXES_RIGHT = 0.97


def _combinations(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The document's combination entries, or raise when there are none to draw."""
    entries = document.get("combinations")
    if not entries:
        raise ValueError(
            "no combination in the cost-efficiency document to draw: the join produced no "
            "row, so there is nothing to plot. Run the fidelity ranking, the validation "
            "attrition task and the generation-metadata summary for this country first."
        )
    return list(entries)


def _method_order(entries: Sequence[Mapping[str, Any]]) -> list[str]:
    """The methods present, simplest-first. Raises on an id with no axis file."""
    return strategy_complexity_order([str(entry["strategy"]) for entry in entries])


def _linthresh(costs: Sequence[float]) -> float:
    """The symlog linear threshold: a fraction of the smallest positive cost."""
    positive = [c for c in costs if c > 0.0]
    if not positive:
        return _FALLBACK_LINTHRESH
    return min(positive) * _LINTHRESH_FRACTION


def _rented_equivalent_note(entries: Sequence[Mapping[str, Any]]) -> list[str] | None:
    """Caption line naming the models priced by rented equivalent, or ``None``.

    A rented-equivalent rate estimates a counterfactual -- what the same model
    would cost to rent per token -- rather than measuring a transaction, and it
    prices an fp8/bf16 build while a local run is 4-bit quantised. Both facts are
    already columns on the row (the pricing flags); this lifts them onto the
    figure, because the figure travels without the table.
    """
    # Named as a reader sees them, not as the pricing config keys them. The flag is
    # per model *id*, so the id is what the row carries and what this must resolve --
    # a caption listing `ollama_gemma4_e4b` prints a config key on a published figure,
    # and does it in the one sentence that is a caveat about that very model.
    flagged_ids = {
        str(entry["model"])
        for entry in entries
        for flag in (entry["cost"].get("pricing_flags") or ())
        if str(flag).startswith("rented-equivalent")
    }
    flagged = sorted(model_label(model_id) for model_id in flagged_ids)
    if not flagged:
        return None
    return [
        f"{len(flagged)} model(s) are priced by RENTED EQUIVALENT, not by what was billed: "
        f"{', '.join(flagged)}. They run locally and are billed nothing; the rate is what "
        f"the same model costs to rent per token, for an fp8/bf16 build while the run was "
        f"4-bit quantised -- so the proxy prices a better model than was used.",
    ]


def _caption(
    document: Mapping[str, Any],
    *,
    n_drawn: int,
    n_no_cost: int,
    n_unmetered: int,
) -> str:
    """The figure's provenance and caveat block, read wholly from the document."""
    totals = document["totals"]
    withdrawn = document["withdrawn_totals"]
    metered = totals["metered"]
    scored_n = sorted({int(e["accuracy"]["n_scored"]) for e in document["combinations"]})
    lines = [
        f"Cost basis: {document['cost_basis']} -- every LLM call of the full generated "
        f"pool, not the capped mirror "
        f"({'/'.join(str(n) for n in scored_n)} personas) the accuracy is scored on.",
        f"x = cost_per_100_usable_personas = 100 * total_cost_usd / clean personas (passed both "
        f"validity gates). y = overall_tv_similarity over n_scored personas. "
        f"{n_drawn} combination(s) drawn; pooled {totals['generated']} generated -> "
        f"{totals['clean']} clean. The x-axis is logarithmic outside the shaded band and "
        f"linear inside it"
        + ("; every point inside the band cost a measured 0.00 USD and is spread "
           "horizontally for legibility only." if n_unmetered else
           ". No combination is unmetered on this grid, so the band is empty."),
        f"Metered subtotal: {metered['n_combinations']} combination(s), "
        f"{metered['total_cost_usd']:.2f} USD over {metered['clean']} clean personas. "
        f"{n_unmetered} combination(s) are unmetered. {document['unmetered_note']}",
        *(_rented_equivalent_note(document['combinations']) or []),
    ]
    if n_no_cost:
        lines.append(
            f"{n_no_cost} combination(s) reported no token telemetry and have no cost; "
            "they are counted here and carried in the JSON, but cannot be placed on a "
            "cost axis."
        )
    if withdrawn["n_combinations"]:
        lines.append(
            f"{withdrawn['n_combinations']} combination(s) were WITHDRAWN by the full-N "
            f"rule and are not drawn: they have no accuracy score. They generated "
            f"{withdrawn['generated']} personas, kept {withdrawn['clean']}, and cost "
            f"{withdrawn['metered_total_cost_usd']:.2f} USD across their "
            f"{withdrawn['n_metered_combinations']} metered combination(s). Full list in "
            "the JSON report."
        )
    lines.append(document["non_composite_reason"])
    # Returned unwrapped, with the sentence breaks the author intended. The figure
    # wraps it to the canvas it actually has -- a character count cannot know that.
    return "\n".join(lines)


@house_style
def plot_cost_vs_accuracy(
    document: Mapping[str, Any],
    *,
    hosting: Mapping[str, str] | None = None,
    xscale: str = "symlog",
):
    """Render fidelity against cost per usable persona; return an unsaved ``Figure``.

    Args:
        document: The builder's document for one country.
        hosting: ``{model_id: "hosted" | "local"}``, as
            ``model_ranking/hosting.py::classify_hosting`` produces it. Resolved at the
            CLI edge and passed down so this module holds no config path and the sibling
            grids cannot disagree about what "local" means. ``None`` draws every model in
            the default class.

    Raises:
        ValueError: When the document holds no combination to draw.
    """
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    hosting = hosting or {}
    entries = _combinations(document)
    methods = _method_order(entries)
    color_for = {m: METHOD_COLORS[i % len(METHOD_COLORS)] for i, m in enumerate(methods)}
    # Each legend entry carries its own key line -- "A -- All Pick" -- so the letters this
    # figure would otherwise need a separate key block for are explained where they are
    # read. Both resolvers return complexity order, which is what aligns the zip.
    method_key = dict(zip(method_letters(methods), method_key_lines(methods)))

    drawn: list[tuple[float, float, str, str, str]] = []  # x, y, model, strategy, host
    no_cost: list[str] = []
    for entry in entries:
        cost = entry["cost"]["cost_per_100_usable_personas"]
        model = str(entry["model"])
        if cost is None:
            no_cost.append(str(entry["slug"]))
            continue
        drawn.append(
            (
                float(cost),
                float(entry["accuracy"]["overall_tv_similarity"]),
                model,
                str(entry["strategy"]),
                hosting.get(model, HOST_DEFAULT_CLASS),
            )
        )

    if not drawn:
        raise ValueError(
            f"none of the {len(entries)} combination(s) in the cost-efficiency document "
            "has a cost per usable persona, so there is nothing to place on the cost "
            "axis. Every run reported no token telemetry -- check the 01_Raw interaction "
            "logs for this country."
        )

    linthresh = _linthresh([x for x, *_ in drawn])
    max_cost = max(x for x, *_ in drawn)

    # Zero-cost points all share one x, so they stack on a single vertical line and their
    # model labels become unreadable. They are spread across the band by rank in fidelity
    # -- a legibility device, declared on the figure, that adds no cost information
    # because there is none to add: every one of them is a measured 0.00 USD.
    zero_ranks = {
        item[2:4]: i
        for i, item in enumerate(sorted((d for d in drawn if d[0] == 0.0), key=lambda d: (d[1], d[2])))
    }
    n_zero = len(zero_ranks)

    def _draw_x(x: float, model: str, strategy: str) -> float:
        if x != 0.0 or n_zero < 2:
            return x
        fraction = zero_ranks[(model, strategy)] / (n_zero - 1)
        return linthresh * _BAND_SPREAD * (2.0 * fraction - 1.0)

    fig, ax = plt.subplots(figsize=(FULL, MAX_HEIGHT))

    n_unmetered = sum(1 for entry in entries if entry["cost"]["unmetered"])
    # The unmetered band, drawn first so every marker sits above it. It spans the symlog
    # linear region, which is exactly the region where a distance is NOT a log distance.
    # Drawn ONLY when something is unmetered: an empty band is grey canvas reserving
    # room for points that do not exist, and it pushes every real point rightwards.
    draw_band = bool(n_unmetered) and xscale == "symlog"
    if draw_band:
        ax.axvspan(-linthresh, linthresh, facecolor=_BAND_COLOR, edgecolor="none", zorder=0)
        ax.axvline(linthresh, color=_BAND_EDGE, linewidth=1.0, linestyle=(0, (4, 3)), zorder=1)

    # Labels alternate above and below their marker in ascending fidelity order, so two
    # points close in y push their text in opposite directions instead of onto each
    # other. Pure layout: it moves no marker and reports no number.
    label_side = {
        item[2:4]: (1 if i % 2 == 0 else -1)
        for i, item in enumerate(sorted(drawn, key=lambda d: (d[1], d[2], d[3])))
    }

    for x, y, model, strategy, host in drawn:
        draw_x = _draw_x(x, model, strategy)
        ax.scatter(
            draw_x, y,
            s=78,
            marker=HOST_MARKERS.get(host, HOST_MARKERS[HOST_DEFAULT_CLASS]),
            facecolor=opaque(color_for[strategy], 0.92),
            edgecolor=SURFACE,
            linewidth=0.7,
            zorder=3,
        )
        ax.annotate(
            model_label(model),
            xy=(draw_x, y),
            xytext=(5, 4 if label_side[(model, strategy)] > 0 else -10),
            textcoords="offset points",
            fontsize=ANNOTATION,
            color=ANNOTATION_GREY,
            zorder=4,
            clip_on=True,
        )

    # linscale sets how many decades of canvas the linear band is given. Kept below 1 so
    # the band -- which holds one distinct x value, zero -- does not occupy the width of
    # a whole decade of real cost variation.
    positive = [x for x, *_ in drawn if x > 0]
    if xscale == "linear":
        # Linear reads costs as ratios of the largest, not of each other: the cheap
        # models collapse toward the axis. Offered because a reader comparing absolute
        # spend wants that, but it is the wrong scale for comparing the cheap end.
        ax.set_xscale("linear")
        ax.set_xlim(0.0, max_cost * 1.08 if max_cost > 0 else 1.0)
        ax.set_xlabel("Cost per 100 usable personas (USD, linear scale)", fontsize=AXIS_TITLE)
    elif draw_band:
        # linscale sets how many decades of canvas the linear band is given. Kept below 1 so
        # the band -- which holds one distinct x value, zero -- does not occupy the width of
        # a whole decade of real cost variation.
        ax.set_xscale("symlog", linthresh=linthresh, linscale=0.5)
        # The left limit stops exactly at the band edge: a symlog axis has a negative
        # logarithmic branch beyond it, and a cost axis showing -10^-4 is nonsense.
        ax.set_xlim(-linthresh, max_cost * 3.2 if max_cost > 0 else linthresh * 10)
        # No tick inside the band. It holds exactly one distinct value -- zero -- so a
        # decade tick there labels a position that means nothing, and the band's own text
        # already states what every point in it cost.
        ax.set_xticks([t for t in ax.get_xticks() if abs(t) >= linthresh])
        ax.set_xlabel(
            "Cost per 100 usable personas (USD, log scale outside the shaded band)", fontsize=AXIS_TITLE
        )
    else:
        # Nothing is unmetered, so every cost is strictly positive and a plain log axis
        # applies throughout -- no linear band, and no dead grey margin before the data.
        ax.set_xscale("log")
        lo = min(positive) if positive else 1e-6
        ax.set_xlim(lo / 2.2, max_cost * 3.2 if max_cost > 0 else lo * 10)
        ax.set_xlabel("Cost per 100 usable personas (USD, log scale)", fontsize=AXIS_TITLE)
    ax.set_ylabel("Fidelity -- overall TV-similarity (higher is better)", fontsize=AXIS_TITLE)
    ax.set_title(
        f"Fidelity against generation cost -- {country_label(document['country'])} "
        f"({document['n_combinations']} combinations)",
        fontsize=FIGURE_TITLE, fontweight="bold", pad=14,
    )
    ax.grid(True, which="major", axis="both", color=GRID_RULE, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)

    # Only label the band when something is in it. Every local model in the live
    # grid now carries a rented-equivalent rate, so the band is routinely empty --
    # and a label reading "every point here is a measured 0.00 USD" over an empty
    # band asserts something about points that are not there.
    if n_unmetered:
        ax.annotate(
            f"unmetered (priced 0/0), n={n_unmetered}\nevery point here is a measured 0.00 USD\n"
            "horizontal position inside the band is\nspread for legibility, not measured",
            xy=(0.0, 1.0), xycoords=("data", "axes fraction"),
            xytext=(0, -8), textcoords="offset points",
            ha="center", va="top", fontsize=ANNOTATION, color=FOOTNOTE_GREY, zorder=2,
        )

    method_handles = [
        Line2D([], [], linestyle="none", marker="o", markersize=7,
               markerfacecolor=color_for[m], markeredgecolor=SURFACE, label=method_key[m])
        for m in methods
    ]
    host_classes = [h for h in HOST_MARKERS if any(d[4] == h for d in drawn)]
    host_handles = [
        Line2D([], [], linestyle="none", marker=HOST_MARKERS[h], markersize=7,
               markerfacecolor=SURFACE, markeredgecolor=HOST_COLORS[h],
               label=HOST_LABELS[h])
        for h in host_classes
    ]
    # Both legends sit OUTSIDE the axes: the point cloud's shape is data-dependent, so
    # any in-axes placement is a bet that this run's empty corner stays empty. They sit
    # in a strip UNDER the axes rather than in a right-hand gutter, because the widest
    # method key line is wider than any gutter narrow enough to leave the scatter room --
    # a gutter that fits it either truncates the key or runs the legend off the page,
    # which the save-time canvas budget then rejects. Under the axes both legends have
    # the whole page width, and the scatter gets it back too.
    figure_width, figure_height = (float(v) for v in fig.get_size_inches())
    caption = wrap_to_width(
        _caption(document, n_drawn=len(drawn), n_no_cost=len(no_cost),
                 n_unmetered=n_unmetered),
        figure_width - 2 * CAPTION_MARGIN_IN, fontsize=ANNOTATION,
    )
    caption_in = (caption.count(chr(10)) + 1) * ANNOTATION * LINE_SPACING / POINTS_PER_INCH
    legend_in = (max(len(method_handles), 1) / _LEGEND_COLUMNS + 1) * (
        LEGEND_LABEL * LINE_SPACING / POINTS_PER_INCH
    )
    strip_in = CAPTION_MARGIN_IN + caption_in + _LEGEND_GAP_IN + legend_in
    fig.subplots_adjust(bottom=strip_in / figure_height, right=_AXES_RIGHT)

    legend_y = (CAPTION_MARGIN_IN + caption_in + _LEGEND_GAP_IN + legend_in) / figure_height
    fig.legend(
        handles=method_handles, title="method (simplest first)",
        loc="upper left", bbox_to_anchor=(CAPTION_MARGIN_IN / figure_width, legend_y),
        bbox_transform=fig.transFigure, ncol=_LEGEND_COLUMNS,
        fontsize=LEGEND_LABEL, title_fontsize=LEGEND_TITLE, borderaxespad=0.0,
    )
    fig.legend(
        handles=host_handles, title="hosting",
        loc="upper right",
        bbox_to_anchor=(1.0 - CAPTION_MARGIN_IN / figure_width, legend_y),
        bbox_transform=fig.transFigure,
        fontsize=LEGEND_LABEL, title_fontsize=LEGEND_TITLE, borderaxespad=0.0,
    )

    fig.text(
        CAPTION_MARGIN_IN / figure_width, CAPTION_MARGIN_IN / figure_height, caption,
        ha="left", va="bottom", fontsize=ANNOTATION, color=CAPTION_GREY,
        linespacing=LINE_SPACING,
    )
    # No tight_layout: the strip above is reserved explicitly, and tight_layout would
    # recompute the subplot box and take it back.
    fit_to_page(fig)
    return fig
