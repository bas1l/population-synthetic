"""charts.py -- pure rendering of the realism ranking into matplotlib figures.

Three figures:

* :func:`plot_headline_map` -- the coherence x coverage map. x = impossibility rate
  (Axis A), y = typicality-dispersion distance to the real population (Axis B).
* :func:`plot_impossibility_forest` -- every competitor's impossibility rate with its
  bootstrap CI, in rank order.
* :func:`plot_impossibility_heatmap` -- Axis A reshaped as a model x method grid, with
  the real population as a separate band beneath it.
* :func:`plot_severity_heatmap` -- the same grid layout for one clash-severity level
  (S3 / S2 / S1). S3 and S2 are defects and use the lower-is-better ramp; S1 is
  reported-but-never-penalised and uses a neutral ramp, because colouring it as a
  defect would assert that unusual people are errors.
* :func:`plot_severity_pair_summary` -- the complement of that heatmap at one level: the
  attribute pairs that clashed, ranked country-wide, with the real population as its own
  series rather than pooled into the bars.
* :func:`plot_typicality_heatmap` -- the self-contained typicality statistic on the same
  grid and the same **sequential** house ramp. The optimum is interior, so neither end of
  the ramp is "better" -- but a sequential ramp orders cells by magnitude alone, so the
  side of the real population's own value cannot live in the hue. It lives in the
  annotations instead: a signed delta printed beside every cell's number and a rule
  across the colourbar at the reference, both read from ``block["reference_value"]``.
  With no real population in the consumption set there is no reference, and both are
  dropped with the reason printed on the figure.
* :func:`plot_typicality_by_method` -- the same statistic with the methods on x in
  complexity order, one mark per model, and the real population as a horizontal
  reference line. It is the one figure in this task where the real population is a
  reference rather than a series, and it is drawn that way only because this axis has no
  ranking to hold it out of: the line is the same reference its sibling heatmap prints a
  delta against, in a form that shows each method's spread around it.
* :func:`plot_typicality_distribution_grid` -- every combination's whole round-weighted
  typicality distribution as a mini histogram on the model x strategy grid (models in the
  published ``model_ranking`` order, resolved by the caller), the reference's distribution
  as an outline in every cell and as its own detached column, one ternary of the three
  score-band shares per strategy, on a fixed 456 pt canvas. Laid out through the
  ``glyph_grid`` presentation module; withdrawn, unjudged and no-typicality cells each
  have their own drawing.

**The real population is drawn as an ordinary competitor.** The previous version of the
map pinned it to ``y = 0`` and marked it with a reference star, which encoded *the real
population is the origin; closer to it is better* into the picture itself -- and made
the open question (is the conditionally-chain-sampled population internally coherent?)
unaskable, because the axis was defined relative to its answer. Here the real population
is one point among many on Axis A: it can sit anywhere on the x-axis, including to the
right of synthetic competitors. It keeps a distinct colour purely so a reader can find
it, and it does sit at ``y = 0`` on Axis B for the arithmetic reason that its distance
to itself is zero -- which is a fact about that axis's definition, not a claim about
quality.

Pure sink boundary (02-architecture guide sect. 9): these functions never touch disk,
never know a file path or a DPI, and **compute nothing** -- every number arrives
pre-computed from ``builder.py``. The caller saves via ``utils/figures.save_figure``.
The non-interactive ``Agg`` backend is selected lazily inside each function so importing
this module never touches a display.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from typing import Any

from population_synthetic.analysis.utils.glyph_grid import (
    COLORBAR_TICK_LENGTH_PT,
    COLORBAR_TICK_PAD_PT,
    TERNARY_HEIGHT_RATIO,
    PointCanvas,
    draw_empty_cell,
    draw_mini_histogram,
    draw_ternary,
    draw_withdrawn_cell,
    outline_handle,
    point_handle,
    reference_star_handle,
    step_colors,
    stepped_colorbar,
    swatch_handle,
    withdrawn_handle,
)
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
    figure_term,
    method_key_lines,
    method_letters,
    model_labels,
    strategy_label,
)
from population_synthetic.analysis.utils.palette import (
    ANNOTATION_GREY,
    BASELINE_DARK,
    CATEGORICAL_SERIES,
    FOOTNOTE_GREY,
    GRID_RULE,
    HEATMAP_CMAP,
    HIGHLIGHT_ACCENT,
    HOLLOW_EDGE,
    HOST_COLORS,
    LARGE_CATEGORICAL_CMAP,
    MISSING_COLOR,
    MUTED_GREY,
    NEUTRAL_GREY,
    SECONDARY_GREY,
    SURFACE,
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
    FIGURE_TITLE,
    FULL,
    HEADING_WEIGHT,
    LEGEND_LABEL,
    LINE_SPACING,
    POINTS_PER_INCH,
    TEXT_WIDTH,
    TICK_LABEL,
    TICK_LABEL_LARGE,
    figure_size,
    grow_height,
    grow_width,
    house_style,
    text_width_inches,
    wrap_to_width,
)
from population_synthetic.analysis.utils.table_style import HOST_LABELS, fit_to_page

__all__ = [
    "RATE_GRID_VARIANTS",
    "TYPICALITY_GRID_VARIANTS",
    "plot_headline_map",
    "plot_impossibility_forest",
    "plot_impossibility_heatmap",
    "plot_severity_heatmap",
    "plot_severity_pair_summary",
    "plot_typicality_by_method",
    "plot_typicality_distribution_grid",
    "plot_typicality_heatmap",
]

#: The impossibility / severity grids' counted variant: the rate at its own 0--1 scale
#: over the personas it was taken across. The rate is not a quotient of two counts the
#: figure prints, so the base is named ``n=`` rather than as a fraction.
RATE_VARIANT_WITH_COUNTS = GridVariant(
    name=COUNTED_VARIANT,
    policy=RateWithCountsPolicy(
        value_key="value", numerator_key=None, denominator_key="denominator",
        scale=1.0, number_format=".3f",
    ),
    cell_clause="Cell: the rate at its own 0-1 scale, over the n personas it was taken across.",
    fontsize=ANNOTATION,
    linespacing=None,
)

#: The camera-ready variant, published at the bare filename: the rate alone, one step up
#: the house scale on the room the dropped count line frees. The denominator is constant
#: down a column of this grid -- every cell of a combination is judged over the same
#: capped population -- so printing it in every cell spends a line on a repetition, and
#: it stays available in the per-persona CSV, in the counted sibling and on the real
#: population's own band.
RATE_VARIANT_CLEAN = GridVariant(
    name=CANONICAL_VARIANT,
    policy=RateOnlyPolicy(value_key="value", scale=1.0, number_format=".3f"),
    cell_clause=(
        "Cell: the rate at its own 0-1 scale; the n it was taken across is on the "
        "with-counts sibling figure and in the per-persona realism CSV."
    ),
    fontsize=ANNOTATION_LARGE,
    linespacing=None,
)

#: The rate grids' publishable variants, clean first because it takes the bare filename.
RATE_GRID_VARIANTS: dict[str, GridVariant] = variant_map(
    RATE_VARIANT_CLEAN, RATE_VARIANT_WITH_COUNTS,
)

#: The typicality grid's counted variant: the statistic, its parenthesised signed
#: distance to the real population, and the survivor count it rests on. The delta is
#: read from the record, not derived here: it is a function of a *second* competitor's
#: value, so the chart -- which owns the reference -- formats it and the policy prints
#: what it is handed. That keeps the reference out of every cell's arithmetic while
#: leaving it visible in the rendering, which is the whole of ADR 2026-08-12's
#: Decision 2.
TYPICALITY_VARIANT_WITH_COUNTS = GridVariant(
    name=COUNTED_VARIANT,
    policy=RateWithCountsPolicy(
        value_key="value", numerator_key=None, denominator_key="denominator",
        scale=1.0, number_format=".3f", qualifier_key="delta",
    ),
    cell_clause=(
        "Cell: the statistic, its parenthesised signed distance to the reference, and "
        "the n typicality-bearing personas it rests on."
    ),
    fontsize=ANNOTATION,
    linespacing=None,
)

#: The camera-ready variant, at the bare filename: the statistic and its signed distance,
#: without the count line. The **delta is not dropped** -- on a sequential ramp it is the
#: only place the side of the reference is readable (ADR 2026-08-12), so a variant without
#: it would be missing content rather than ink. Its type size is deliberately *not* raised:
#: unlike its sibling grids this cell carries an inline qualifier, so the annotation is
#: bound by the cell's width rather than by the line the variant drops.
TYPICALITY_VARIANT_CLEAN = GridVariant(
    name=CANONICAL_VARIANT,
    policy=RateOnlyPolicy(
        value_key="value", scale=1.0, number_format=".3f", qualifier_key="delta",
    ),
    cell_clause=(
        "Cell: the statistic and, parenthesised, its signed distance to the reference; "
        "its n is on the with-counts sibling figure."
    ),
    fontsize=ANNOTATION,
    linespacing=None,
)

#: The typicality grid's publishable variants, clean first.
TYPICALITY_GRID_VARIANTS: dict[str, GridVariant] = variant_map(
    TYPICALITY_VARIANT_CLEAN, TYPICALITY_VARIANT_WITH_COUNTS,
)

_COMPETITOR_COLOR = CATEGORICAL_SERIES[0]
_REAL_COLOR = HIGHLIGHT_ACCENT
_CI_COLOR = NEUTRAL_GREY

# The house sequential ramp, shared with every other grid in ``03_Analysis`` (see
# ``analysis/utils/palette.py``). Used for every monotone quantity this module draws:
# the impossibility rate and all three clash prevalences. Sequential, not diverging:
# those quantities have a true zero and no meaningful midpoint, so a diverging map
# would invent one and split the combinations into "good" and "bad" sides at an
# arbitrary value.
#
# **This ramp carries no better/worse reading, and that is a change in where the
# reading lives, not a loss of it.** S3/S2 are defects and S1 is unusual-but-possible
# -- reported and never penalised -- and these once used two hues to say so (Reds vs
# Blues). Hue is now spent on figure-family identity instead, so the distinction is
# carried entirely by ``plot_severity_heatmap``'s colourbar label and its caption,
# both of which already stated it in words and both of which travel on the figure.
_SEQUENTIAL_CMAP = HEATMAP_CMAP

# Fill for a model x method pair that was never judged. Deliberately outside the ramp
# so it can never be mistaken for its low (few / none) end.
_MISSING_COLOR = MISSING_COLOR

#: Axis-B measure the headline map's y-axis uses. A presentation choice, not a
#: statistic: the other two measures are in the JSON and the contrast CSV.
_DEFAULT_MEASURE = "variance"


def _point_style(is_real: bool) -> dict[str, Any]:
    """Marker style for one competitor -- distinct, but not privileged."""
    if is_real:
        return {"marker": "D", "s": 130, "color": _REAL_COLOR,
                "edgecolor": BASELINE_DARK, "linewidth": 0.6, "zorder": 3}
    return {"marker": "o", "s": 90, "color": _COMPETITOR_COLOR,
            "edgecolor": SURFACE, "linewidth": 0.5, "zorder": 2}


@house_style
def plot_headline_map(ranking: dict[str, Any], *, measure: str = _DEFAULT_MEASURE):
    """Render the coherence x coverage map from a built ranking document.

    Every competitor with a defined impossibility rate is plotted. The real population
    is included on the same footing: its x-coordinate is its own measured rate, so if
    conditional chained sampling does produce incoherent people, that shows up here as
    the real point sitting to the right of the synthetic ones.

    A competitor whose Axis-B distance is undefined (no typicality data, or no real
    population to measure against) is plotted on the x-axis only, at ``y = 0``, and
    annotated -- rather than dropped, which would make an unmeasurable combination look
    like one that was never judged. Returns the ``Figure`` unsaved and open; raises when
    there is nothing plottable.
    """
    import matplotlib.pyplot as plt

    distances = {
        row["slug"]: (row.get("distance_to_scb") or {}).get(measure)
        for row in ranking["axis_b"]["dispersion_contrast"]
    }
    real_slug = ranking.get("real_competitor")

    plotted = [entry for entry in ranking["axis_a"]["ranking"] if entry["rate"] is not None]
    if not plotted:
        raise ValueError("plot_headline_map requires at least one competitor with a defined rate")

    fig, ax = plt.subplots(figsize=figure_size(FULL, 7))
    seen_labels: set[str] = set()
    for entry in plotted:
        slug = entry["slug"]
        is_real = slug == real_slug
        # The real competitor's distance to itself is zero by definition; an undefined
        # distance is drawn at zero too but flagged in the annotation.
        distance = 0.0 if is_real else distances.get(slug)
        undefined = distance is None
        y = 0.0 if undefined else float(distance)

        style = _point_style(is_real)
        legend_label = "real population (competitor)" if is_real else "synthetic combination"
        if legend_label in seen_labels:
            legend_label = None
        else:
            seen_labels.add(legend_label)
        ax.scatter(entry["rate"], y, label=legend_label, **style)
        caption = _competitor_caption(entry)
        annotation = f"{caption}*" if undefined else caption
        ax.annotate(
            annotation, (entry["rate"], y),
            textcoords="offset points", xytext=(6, 4), fontsize=ANNOTATION,
        )

    ax.set_xlabel(
        "Axis A -- impossibility rate (share of internally-contradictory personas); lower is better",
        fontsize=AXIS_TITLE,
    )
    ax.set_ylabel(
        f"Axis B -- typicality-dispersion distance to the real population ({measure}); "
        "near zero is better",
        fontsize=AXIS_TITLE,
    )
    ax.set_title(
        "Persona realism -- coherence vs typicality coverage\n"
        "(the real population is ranked as an ordinary competitor on Axis A)",
        fontsize=FIGURE_TITLE, fontweight="bold",
    )
    ax.axhline(0, color=MUTED_GREY, linestyle="--", linewidth=0.7, zorder=0)
    ax.tick_params(axis="both", labelsize=TICK_LABEL)
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(handles, labels, fontsize=LEGEND_LABEL, loc="best")
    if any(distances.get(e["slug"]) is None and e["slug"] != real_slug for e in plotted):
        ax.text(
            0.99, 0.01, "* Axis-B distance undefined; plotted on the x-axis only",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=ANNOTATION, color="gray",
        )
    fig.tight_layout()
    fit_to_page(fig)
    return fig


@house_style
def plot_impossibility_forest(ranking: dict[str, Any]):
    """Render every competitor's impossibility rate with its bootstrap CI, in rank order.

    A forest plot rather than a bar chart, because the interval is the point: the rates
    are estimates from a bounded number of personas, and a bar would present them as if
    they were exact. Overlap between intervals is there to be *read*, not to be
    interpreted as a hypothesis test -- the pairwise contrasts in the JSON do that job,
    with a correction.

    Competitors whose rate is undefined (no successful persona) are omitted from the
    figure; they are still present in the ranking with an explicit ``None``. Returns the
    ``Figure`` unsaved and open; raises when there is nothing plottable.
    """
    import matplotlib.pyplot as plt

    entries = [e for e in ranking["axis_a"]["ranking"] if e["rate"] is not None]
    if not entries:
        raise ValueError("plot_impossibility_forest requires at least one competitor with a rate")

    real_slug = ranking.get("real_competitor")
    labels = [f"{_competitor_caption(e)}  (n={e['denominator']})" for e in entries]
    positions = list(range(len(entries)))

    fig, ax = plt.subplots(figsize=(FULL, grow_height(len(entries), per_item=0.32, padding=1.8, minimum=3.0)))
    for pos, entry in zip(positions, entries):
        is_real = entry["slug"] == real_slug
        lo, hi = entry["ci_lo"], entry["ci_hi"]
        if lo is not None and hi is not None:
            ax.plot([lo, hi], [pos, pos], color=_CI_COLOR, linewidth=1.2, zorder=1)
        color = _REAL_COLOR if is_real else _COMPETITOR_COLOR
        marker = "D" if is_real else "o"
        ax.scatter(entry["rate"], pos, color=color, marker=marker, s=44, zorder=2,
                   edgecolor=SURFACE, linewidth=0.4)

    ax.set_yticks(positions)
    ax.set_yticklabels(labels, fontsize=TICK_LABEL)
    ax.invert_yaxis()  # best (lowest rate) at the top
    ax.set_xlabel(
        f"Impossibility rate with {int(round(entries[0]['ci_level'] * 100))}% bootstrap CI; "
        "lower is better",
        fontsize=AXIS_TITLE,
    )
    ax.set_title(
        "Axis A -- impossibility rate by competitor (the real population included)",
        fontsize=FIGURE_TITLE, fontweight="bold",
    )
    ax.tick_params(axis="x", labelsize=TICK_LABEL)
    ax.grid(axis="x", linestyle=":", linewidth=0.5, color=GRID_RULE)
    fig.tight_layout()
    fit_to_page(fig)
    return fig

@house_style
def _render_grid_heatmap(
    grid: dict[str, Any],
    *,
    country: str,
    title: str,
    cbar_label: str,
    caption: str,
    error_context: str,
    variant: GridVariant,
):
    """Render one ``{models, methods, cells, real}`` grid as a heatmap.

    The single implementation behind every heatmap this task emits, so the layout and
    the guards below cannot diverge between them. Computes nothing: each cell payload
    already carries its ``rate`` and ``denominator``.

    *variant* decides what a cell prints and nothing else -- the clean publication prints
    the rate alone one step larger, the with-counts one adds the base beneath it -- so the
    two are the same figure in rows, columns, extent, colour scale and markings by
    construction. The real-population band keeps its own ``n`` in both, exactly as the
    marginals of the sibling grids do: it is stated once on the figure rather than in
    every cell.

    Three rendering decisions carry meaning:

    * **The ramp is sequential and anchored at a true zero.** ``vmin=0`` because zero is
      a real floor, not the bottom of the observed range, so a cell at the ramp's low end
      always means "few", never "fewest in this particular sweep". A diverging map would
      be wrong: the quantity has no meaningful midpoint, so a diverging map would invent
      one and sort combinations into good and bad halves at an arbitrary value.
    * **An unjudged cell is grey and labelled ``n/a``**, drawn outside the ramp entirely.
      Rendering it at the ramp's low end would show a combination that was never judged
      as the cleanest in the sweep -- the single most damaging misreading these figures
      could produce.
    * **The real population is a separated band, not a grid row.** It has no model and no
      method; giving it a row would present it as a factor level, which is exactly what
      the ranking's factor tests hold it out of being. A white rule and a caption keep it
      visually apart, and its value spans the full width because it is not decomposed by
      method.

    Returns the ``Figure`` unsaved and open. Raises ``ValueError`` when nothing has a
    defined value, matching the sibling charts.
    """
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt
    import numpy as np

    models: list[str] = list(grid["models"])
    methods: list[str] = list(grid["methods"])
    real = grid.get("real")

    values = np.full((len(models), len(methods)), np.nan)
    for i, model in enumerate(models):
        for j, method in enumerate(methods):
            cell = grid["cells"].get(model, {}).get(method)
            if cell is not None and cell.get("rate") is not None:
                values[i, j] = float(cell["rate"])

    real_rate = None if real is None else real.get("rate")
    if not np.any(np.isfinite(values)) and real_rate is None:
        raise ValueError(f"{error_context} requires at least one competitor with a defined value")

    # The real band is appended as an extra row so it shares the colour scale -- the
    # point of putting it on this figure at all is that its value is comparable with the
    # grid's. The separating rule below keeps it from reading as another model.
    n_rows = len(models) + (1 if real_rate is not None else 0)
    plotted = np.full((n_rows, max(len(methods), 1)), np.nan)
    plotted[:len(models), :len(methods)] = values
    if real_rate is not None:
        plotted[-1, :] = float(real_rate)

    finite = plotted[np.isfinite(plotted)]
    vmax = float(finite.max()) if finite.size else 1.0
    if vmax <= 0.0:
        vmax = 1.0   # every value is 0: keep a valid range instead of a degenerate one

    fig, ax = plt.subplots(
        figsize=(
            grow_width(len(methods), per_item=1.5, padding=3.5, minimum=7.0),
            grow_height(n_rows, per_item=0.55, padding=2.4, minimum=3.2),
        ),
    )
    # One record per judged competitor cell. An unjudged pair carries none: its wording
    # is a statement about the absence of a judgement rather than about a value, and it
    # is written below in the grey the figure reserves for exactly that. The real band's
    # row carries no record either -- it is annotated once across the full width, because
    # it is not decomposed by method.
    cells: list[list[dict[str, Any] | None]] = []
    for i in range(n_rows):
        row: list[dict[str, Any] | None] = []
        for j in range(max(len(methods), 1)):
            value = plotted[i, j]
            in_grid = i < len(models) and j < len(methods)
            row.append(
                {"value": float(value), "denominator": grid["cells"][models[i]][methods[j]]["denominator"]}
                if in_grid and np.isfinite(value) else None
            )
        cells.append(row)

    im = render_grid(
        ax, plotted, cells,
        policy=variant.policy,
        cmap=heatmap_cmap(_SEQUENTIAL_CMAP, missing=_MISSING_COLOR),
        norm=mcolors.Normalize(vmin=0.0, vmax=vmax),
        aspect="auto", fontsize=variant.fontsize, linespacing=variant.linespacing,
        interpolation="none",
    )

    # Letters on the method axis and display names on the model axis; the key is drawn
    # with the footnotes below, beside the caption that already qualifies the grid.
    letters = method_letters(methods) if methods else {}
    display_models = model_labels(models)
    row_labels = [display_models[model] for model in models]
    if real_rate is not None:
        row_labels.append(f"{country_label(country)}  (real population)")
    ax.set_xticks(range(max(len(methods), 1)))
    ax.set_xticklabels(
        [letters[m] for m in methods] if methods else [""], fontsize=TICK_LABEL,
    )
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(row_labels, fontsize=TICK_LABEL)

    # The grey cells say so explicitly; the measured ones were annotated by the shared
    # renderer above.
    for i, model in enumerate(models):
        for j, method in enumerate(methods):
            if cells[i][j] is None:
                ax.text(j, i, "n/a", ha="center", va="center", fontsize=ANNOTATION,
                        color=SECONDARY_GREY, style="italic")

    if real_rate is not None:
        row = n_rows - 1
        # A thick white rule + the band's own label: this row is not a model.
        ax.axhline(row - 0.5, color=SURFACE, linewidth=3.0)
        centre = (len(methods) - 1) / 2.0 if methods else 0.0
        ax.text(
            centre, row, f"{float(real_rate):.3f}   n={real['denominator']}",
            ha="center", va="center", fontsize=ANNOTATION,
            color=text_color_on(im, float(real_rate)),
        )

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label(cbar_label, fontsize=AXIS_TITLE)
    cbar.ax.tick_params(labelsize=TICK_LABEL)

    ax.set_xlabel("Generation method", fontsize=AXIS_TITLE)
    ax.set_ylabel("Model", fontsize=AXIS_TITLE)
    ax.set_title(title, fontsize=FIGURE_TITLE, fontweight="bold")

    footnotes = ["Methods:  " + "   ".join(method_key_lines(methods))] if methods else []
    # What a cell prints is the first thing a reader of this figure needs, and it is the
    # one sentence the two publications do not share.
    footnotes.append(variant.cell_clause)
    if caption:
        footnotes.append(caption)
    if real_rate is not None:
        footnotes.append(
            "The real population spans the full width because it has no method: it is not "
            "a model x method cell, and the factor tests hold it out."
        )
    if footnotes:
        # Reserve a strip first, then place the caption inside it: an artist dropped
        # below the axes without reserved space collides with the rotated tick labels,
        # and one dropped below the *canvas* grows the exported page past the cap.
        _place_footnote(fig, ax, footnotes)
    else:
        fig.tight_layout()
        fit_to_page(fig)
    return fig


def plot_impossibility_heatmap(
    ranking: dict[str, Any], *, variant: GridVariant = RATE_VARIANT_CLEAN,
):
    """Render Axis A as a model x method grid, with the real population as its own band.

    The forest plot answers "who is most coherent"; this one answers "does incoherence
    track the model, the method, or neither" -- the same question the Kruskal-Wallis
    tests answer numerically, in a form that shows the pattern rather than a p-value.
    Every number arrives pre-computed in ``axis_a.grid``.

    *variant* selects the publication: :data:`RATE_VARIANT_CLEAN` (the default, and the
    one written at the bare filename) or :data:`RATE_VARIANT_WITH_COUNTS`.
    """
    return _render_grid_heatmap(
        ranking["axis_a"]["grid"],
        country=ranking["country"],
        title=(
            "Axis A -- impossibility rate by model x method\n"
            "(grey = not judged, which is not a rate of zero)"
        ),
        cbar_label="Impossibility rate -- lower is better",
        caption="",
        error_context="plot_impossibility_heatmap",
        variant=variant,
    )


def plot_severity_heatmap(
    ranking: dict[str, Any], severity: str, *, variant: GridVariant = RATE_VARIANT_CLEAN,
):
    """Render one severity level's clash prevalence as a model x method grid.

    *severity* is one of ``S3`` / ``S2`` / ``S1``. The value shown is the share of a
    combination's personas exhibiting at least one clash at that level; the three levels
    are counted independently, so a persona carrying both an S3 and an S2 appears on
    both figures.

    **The three levels are not labelled alike, and that is deliberate.** S3 and S2 are
    defects and their colourbar says lower is better. S1 is *unusual but possible* -- the
    judge's own contract reports it and never penalises it, and a high S1 rate plausibly
    means healthy reach into the tails rather than a problem. Its colourbar therefore
    marks it as not penalised and it carries a caption saying a higher value is not
    worse. The distinction is drawn on the figure, not only in this docstring, because
    the figure travels without the code.

    It is drawn in *words* rather than in hue: all three levels share the house ramp
    (``_SEQUENTIAL_CMAP``), which carries no better/worse reading of its own. A reader
    must therefore take the direction from the colourbar label and the caption, both of
    which are always present, and never from the colour.

    *variant* selects the publication: :data:`RATE_VARIANT_CLEAN` (the default, and the
    one written at the bare filename) or :data:`RATE_VARIANT_WITH_COUNTS`.

    Raises ``KeyError`` on an unknown severity level.
    """
    block = ranking["severity"]["levels"]
    if severity not in block:
        raise KeyError(
            f"Unknown severity level {severity!r}: known levels are {sorted(block)}."
        )
    level = block[severity]
    penalised = bool(level["penalised"])

    if penalised:
        cbar_label = f"{severity} prevalence -- lower is better"
        caption = ""
    else:
        cbar_label = f"{severity} prevalence (not penalised)"
        caption = (
            f"{severity} is unusual-but-possible: it is reported and never penalised, and a "
            "higher value is not worse. It may indicate reach into the unusual-but-possible "
            "tail rather than a defect -- do not read this figure as a score."
        )

    return _render_grid_heatmap(
        level["grid"],
        country=ranking["country"],
        title=(
            f"Severity {severity} -- share of personas with >=1 {severity} clash\n"
            f"({level['meaning']}; grey = not judged, not a prevalence of zero)"
        ),
        cbar_label=cbar_label,
        caption=caption,
        error_context=f"plot_severity_heatmap({severity})",
        variant=variant,
    )


#: Gap between the axes' lowest decoration and the first footnote line, in inches.
_FOOTNOTE_GAP_IN = 0.22


def _place_footnote(fig, ax, sentences: list[str]) -> None:
    """Reserve a strip at the foot of *fig* for the wrapped footnote, and fill it.

    The caveats are the reason these figures can travel without their docstring, so
    they are never the thing that gets cropped -- but they must not be the thing that
    grows the page either. An earlier version hung them below the canvas and relied on
    ``bbox_inches="tight"`` to expand the output around them; that expansion is exactly
    what the printable-canvas budget in ``utils/figures.py`` now rejects, and it fails
    the whole figure rather than the footnote.

    So the strip is reserved *inside* the canvas, measured from the wrapped text rather
    than taken as a fixed fraction: these figures grow with the number of bars, and any
    fixed fraction is simultaneously too much on one level and too little on another.
    The wrap is to the page, not to a character count, for the same reason.
    """
    width_in, height_in = (float(value) for value in fig.get_size_inches())
    text = "\n".join(
        wrap_to_width(sentence, width_in - 2 * CAPTION_MARGIN_IN, fontsize=ANNOTATION)
        for sentence in sentences
    )
    lines = text.count(chr(10)) + 1
    strip_in = CAPTION_MARGIN_IN + lines * ANNOTATION * LINE_SPACING / POINTS_PER_INCH
    fig.tight_layout(rect=(0.0, (strip_in + _FOOTNOTE_GAP_IN) / height_in, 1.0, 1.0))
    fig.text(
        0.5, CAPTION_MARGIN_IN / height_in, text,
        ha="center", va="bottom", fontsize=ANNOTATION, color=FOOTNOTE_GREY,
        linespacing=LINE_SPACING,
    )
    fit_to_page(fig)


def _pair_summary_footnotes(summary: dict[str, Any]) -> list[str]:
    """The caveats that must travel *on* the figure, in reading order.

    Denominator first (a share is unreadable without it), then how the numbers were
    counted, then why they do not add up, then where they came from, then what was cut.
    Each caveat's *wording* is read from the payload (``counting_unit`` /
    ``non_additive`` / ``provenance`` / the level's ``direction``) rather than restated
    here, so the figure and the block it renders cannot disagree about what the bars mean.
    """
    # ``real_slug`` decides only whether a real series exists; what the reader is shown
    # is the country's own name, because a slug is a filesystem key, not a caption.
    real_slug, real_denominator = summary["real_slug"], summary["real_denominator"]
    real_caption = f"The {country_label(summary['country'])} real population"
    lines = [
        f"Denominator: {summary['denominator']} personas pooled over "
        f"{summary['n_synthetic_competitors']} synthetic combination(s) -- the same "
        "population the severity heatmap divides its cells by. "
        + (
            f"{real_caption} is counted separately over its own {real_denominator} "
            "personas and is never pooled into the bars."
            if real_slug is not None
            else "No real population was consumable, so no second series is drawn."
        ),
        f"Counted in {summary['counting_unit']}.",
        f"Not additive: {summary['non_additive']}",
        f"Provenance: {summary['provenance']}.",
    ]
    if summary["n_pairs_hidden"]:
        cut = (
            f"Showing the top {summary['n_pairs_shown']} of {summary['n_pairs_total']} "
            f"distinct pair(s) at this level; {summary['n_pairs_hidden']} are below the cut "
            "and are counted here rather than dropped silently"
        )
        if summary["n_pairs_real_only"]:
            cut += (
                f", of which {summary['n_pairs_real_only']} were raised only by the real "
                "population (they rank at zero synthetic personas)"
            )
        lines.append(cut + ".")
    if not summary["penalised"]:
        lines.append(f"{summary['severity']} is {summary['direction']}")
    return lines


#: Horizontal offsets, in points from the right spine, of the two numeric columns that sit
#: beside the ranked bars. The values live outside the plot rather than at each bar's end
#: because the two series overlap: on the Swedish S1 data the real population's marker lands
#: on top of the bar-end label on a third of the rows, and a value hidden under a mark is
#: worse than a value in a column. Aligned columns also free the x-axis of the label
#: headroom the in-plot labels needed, so the bars keep the width the ranking is read from.
_COLUMN_SYNTHETIC_PT = 10
_COLUMN_REAL_PT = 82

#: Data-space row the column headers sit on -- above the first bar, and reserved by the
#: y-limit so nothing is drawn into it.
_HEADER_ROW = -1.0


def _competitor_caption(entry: dict[str, Any]) -> str:
    """Reader-facing name of one ranked competitor.

    A synthetic competitor is its model's display name and its combination's method
    phrase. The real population is named by its **country**, because it is a register
    population carrying no model and no method -- the loader hands it through with both
    fields empty, and that emptiness is the branch taken here rather than a guess.
    """
    if entry["is_real_reference"]:
        return f"{country_label(entry['country'])} (real population)"
    model = entry["model"]
    return f"{model_labels([model])[model]} / {strategy_label(entry['strategy'])}"


def _column(ax, row: float, offset_pt: int, text: str, color: str, *, bold: bool = False) -> None:
    """Write one cell of the numeric columns beside the axes, at *row*.

    Positioned in mixed coordinates -- x pinned to the right spine in axes fraction, y in
    data space -- so the columns stay aligned however the x-scale ends up, and stay locked
    to their bar however tall the figure grows. ``annotation_clip=False`` keeps the cells
    from being clipped at the spine; the tight bounding box at save time grows the canvas
    to include them.
    """
    ax.annotate(
        text, xy=(1.0, row), xycoords=("axes fraction", "data"),
        xytext=(offset_pt, 0), textcoords="offset points",
        ha="left", va="center", fontsize=ANNOTATION, color=color,
        fontweight="bold" if bold else "normal", annotation_clip=False,
    )


@house_style
def _empty_pair_summary(summary: dict[str, Any], title: str):
    """The figure a level with nothing to rank gets -- an explanation, not empty axes.

    "No pair clashed at this level in any competitor" is a measurement, and a strong one:
    the neighbouring case on the current Swedish data, where the real population raises no
    S3 clash while the synthetic ones do, is the sharpest single number these figures
    produce. Emitting nothing here would make the strong result indistinguishable from a
    crashed render, and emitting a blank axis would make it look like a rendering bug; the
    figure says which it is, and the denominators still travel with it.
    """
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=figure_size(FULL, 4.2))
    ax.axis("off")
    ax.set_title(title, fontsize=FIGURE_TITLE, fontweight="bold")
    ax.text(
        0.5, 0.55,
        f"No {summary['severity']} clash was raised by any consumed competitor.\n"
        "There is nothing to rank at this level -- this is a measured absence, "
        "not a missing figure.",
        transform=ax.transAxes, ha="center", va="center", fontsize=CALLOUT, color=ANNOTATION_GREY,
    )
    _place_footnote(fig, ax, _pair_summary_footnotes(summary))
    return fig


@house_style
def plot_severity_pair_summary(summary: dict[str, Any]):
    """Render one severity level's clashing attribute pairs, ranked country-wide.

    The complement of :func:`plot_severity_heatmap`. The heatmap answers "which model x
    method cells have a high rate at this level" and structurally cannot answer "what
    clashed"; this figure answers exactly that, at the attribute-pair grain, pooled across
    competitors. *summary* arrives fully computed from
    ``builder.severity_pair_summary`` -- this function derives no statistic.

    **Form.** A horizontal bar chart sorted descending: the job is comparing magnitudes
    across nominal categories whose names are long (``education_level x
    industry_sector``), which is the case horizontal bars exist for -- vertical columns
    would force rotated, colliding tick labels. Both series' numbers are written in
    aligned columns to the right of the axes rather than at each bar's end, because the
    two series overlap in x and an in-plot label lands under the other series' marker on a
    third of the Swedish S1 rows.

    **The real population is a second series, not a pooled contribution.** It gets the
    same encoding it already has on the forest plot -- a red diamond against the synthetic
    blue -- so the reader learns one mapping for the whole folder, and identity is carried
    by shape as well as hue rather than by colour alone. Pooling it into the bars would
    destroy the contrast these numbers exist to show (a population that raises no S3 clash
    at all would vanish inside a 4500-persona synthetic total), and averaging it in would
    let its contribution be misread as the synthetic population's.

    **Colour is constant across the three levels**, unlike the heatmaps, and deliberately:
    here the two colours encode *identity* (which population), not magnitude, so
    repainting them per level would break the one mapping the figure asks the reader to
    learn. The S1-is-not-a-defect signal is carried instead by the caption, taken from the
    same ``SEVERITY_DIRECTIONS`` entry the heatmap's neutral ramp is chosen from.

    Returns the ``Figure`` unsaved and open. A level with no clash at all returns the
    explaining figure rather than raising, so the artifact set is never silently short.
    """
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    severity = summary["severity"]
    # Deliberately short: who is pooled and who is not is carried by the legend and by the
    # first footnote line, and a title wide enough to say it again runs into the axes.
    title = (
        f"Severity {severity} -- which attribute pairs clashed, ranked ({summary['country']})\n"
        f"({summary['meaning']})"
    )
    pairs = summary["pairs"]
    if not pairs:
        return _empty_pair_summary(summary, title)

    labels = [
        f"{attribute_label(pair['attr_a'])} x {attribute_label(pair['attr_b'])}"
        for pair in pairs
    ]
    values = [0.0 if pair["prevalence"] is None else float(pair["prevalence"]) for pair in pairs]
    positions = list(range(len(pairs)))

    fig, ax = plt.subplots(figsize=(FULL, grow_height(len(pairs), per_item=0.42, padding=2.6, minimum=3.6)))
    ax.barh(
        positions, values, height=0.62, color=_COMPETITOR_COLOR,
        edgecolor=SURFACE, linewidth=0.4, zorder=2,
        label=f"synthetic combinations pooled (n={summary['denominator']})",
    )

    real_slug = summary["real_slug"]
    real_values = [pair["real_prevalence"] for pair in pairs]
    drawn = [(pos, v) for pos, v in zip(positions, real_values) if v is not None]
    if real_slug is not None and drawn:
        ax.scatter(
            [v for _, v in drawn], [pos for pos, _ in drawn],
            marker="D", s=52, color=_REAL_COLOR, edgecolor=BASELINE_DARK, linewidth=0.6,
            zorder=4,
            label=f"{country_label(summary['country'])} real population "
                  f"(n={summary['real_denominator']})",
        )

    headroom = max([*values, *(v for v in real_values if v is not None), 0.0]) or 1.0
    # The left edge sits just below zero so a marker at exactly 0.000 -- which is a
    # measurement, and the most informative one the real population makes at S3 -- renders
    # whole instead of being bisected by the spine. The right edge needs almost no
    # headroom, because the values are read off the columns beside the axes rather than
    # off labels inside it.
    ax.set_xlim(-0.03 * headroom, headroom * 1.04)

    for pos, pair, value in zip(positions, pairs, values):
        share = "n/a" if pair["prevalence"] is None else f"{value:.4f}"
        _column(ax, pos, _COLUMN_SYNTHETIC_PT, f"{share}   n={pair['n_personas']}", ANNOTATION_GREY)
        if pair["real_prevalence"] is not None:
            _column(
                ax, pos, _COLUMN_REAL_PT,
                f"{float(pair['real_prevalence']):.4f}   n={pair['real_n_personas']}",
                _REAL_COLOR,
            )
    _column(ax, _HEADER_ROW, _COLUMN_SYNTHETIC_PT, "synthetic", _COMPETITOR_COLOR, bold=True)
    if real_slug is not None:
        _column(ax, _HEADER_ROW, _COLUMN_REAL_PT, "real", _REAL_COLOR, bold=True)

    ax.set_yticks(positions)
    ax.set_yticklabels(labels, fontsize=TICK_LABEL)
    # Top-down (most-affected first) with room above row 0 for the column headers. Set
    # directly rather than via invert_yaxis(), which would flip the reserved strip to the
    # bottom of the figure where the headers would sit under the columns they name.
    ax.set_ylim(len(pairs) - 0.5, _HEADER_ROW - 0.4)
    ax.set_xlabel(
        f"Share of personas exhibiting the pair at {severity} "
        "(each series over its own denominator)",
        fontsize=AXIS_TITLE,
    )
    ax.set_title(title, fontsize=FIGURE_TITLE, fontweight="bold")
    ax.tick_params(axis="x", labelsize=TICK_LABEL)
    ax.grid(axis="x", linestyle=":", linewidth=0.5, color=GRID_RULE, zorder=0)
    ax.set_axisbelow(True)
    handles, legend_labels = ax.get_legend_handles_labels()
    if real_slug is not None and not drawn:
        # Every listed pair happens to be absent from the real population: keep the series
        # in the legend anyway, at zero, so "SCB raised none of these" reads as a result
        # rather than as a series that was never drawn.
        handles.append(Line2D(
            [], [], linestyle="none", marker="D", markersize=6, color=_REAL_COLOR,
            markeredgecolor=BASELINE_DARK, markeredgewidth=0.6,
        ))
        legend_labels.append(
            f"{country_label(summary['country'])} real population "
            f"(n={summary['real_denominator']}) -- none of these pairs"
        )
    if handles:
        # Bars first, the real series second: the bars are what the ranking is over, and
        # matplotlib's collection-before-patch ordering would otherwise lead with the
        # series that is deliberately not pooled into it.
        order = sorted(range(len(handles)), key=lambda i: legend_labels[i].startswith("synthetic"),
                       reverse=True)
        ax.legend([handles[i] for i in order], [legend_labels[i] for i in order],
                  fontsize=LEGEND_LABEL, loc="best")
    _place_footnote(fig, ax, _pair_summary_footnotes(summary))
    return fig


# --------------------------------------------------------------------------- #
# Typicality -- the self-contained statistic, rendered against the real value  #
# --------------------------------------------------------------------------- #


#: This figure draws on the house sequential ramp like every other grid in the layer, and
#: that costs it something the other grids never had to carry: the statistic's optimum is
#: **interior**. Collapsed onto one level and maximally dispersed are both departures from
#: the real population, in *opposite* directions, and a sequential ramp orders cells by
#: magnitude alone -- so two competitors equally far above and below the reference get
#: different colours, and neither colour says which side it was on.
#:
#: The side is therefore carried explicitly instead of chromatically, in two places that
#: are always drawn together: a rule across the colourbar at the reference's own value,
#: and a signed delta printed inside every cell. Both are read from
#: ``block["reference_value"]``, never from a literal, and both disappear together when
#: there is no reference to measure against. A reader gets the two-sided reading from the
#: numbers rather than from the hue; what they must not do is infer a direction from the
#: ramp, which is why ``direction_reason`` stays printed on the figure.
_REFERENCE_RULE_WIDTH = 2.0

#: Overlay for an UNDER-POWERED cell -- measured, but on fewer personas than ``min_n``.
#: A hatch rather than a fill, because the value is still published and still readable:
#: greying it out would make "measured on too few personas to read" look like the
#: unjudged ``_MISSING_COLOR``, which claims nothing was measured at all. Sparse and
#: semi-transparent for the same reason -- a dense hatch strikes through the number it is
#: qualifying, and the number is still the cell's point.
_UNDER_POWERED_HATCH = "//"
_UNDER_POWERED_EDGE = ANNOTATION_GREY

#: Fill + overlay for a cell whose competitor was judged but carries NO typicality-bearing
#: persona (every persona was judged impossible). The fourth state on this figure, and
#: deliberately neither the ramp (there is no value), nor ``_MISSING_COLOR`` (that pair was
#: never judged), nor the under-powered hatch (that one has a value).
_NO_TYPICALITY_COLOR = SURFACE
_NO_TYPICALITY_HATCH = "xx"
_NO_TYPICALITY_EDGE = HOLLOW_EDGE

#: Ceiling the ramp falls back to when every consumed competitor sits at the statistic's
#: floor. The range is then genuinely zero-width; a ramp cannot be built on it and
#: normalising by it would divide by zero. Every cell renders at the ramp's bottom, which
#: is the truth (they are all totally collapsed), and the figure says so in a footnote
#: rather than implying a spread the limits invented.
_FLAT_RANGE_CEILING = 1.0

#: Qualitative colours for the per-model marks on the methods-on-x figure. Qualitative,
#: because model identity is nominal: a sequential ramp over an alphabetical model list
#: would encode an order that does not exist.
_MODEL_CMAP = LARGE_CATEGORICAL_CMAP

#: ``tab20`` entries withheld from the model palette: its red pair. Red is this folder's
#: identity colour for the real population (``_REAL_COLOR`` on the forest plot, the pair
#: summary and this figure's reference line), so handing it to a model would break the one
#: colour mapping every figure here asks the reader to learn.
_RESERVED_MODEL_COLORS = (6, 7)

#: Total width the per-model marks are dodged across within one method's slot. Wide enough
#: to separate a dozen models, narrow enough that a mark never crosses into its
#: neighbour's slot -- a point read against the wrong method is worse than a crowded one.
_METHOD_DODGE_SPAN = 0.62

#: Wrap width for the colourbar / y-axis label. The label states the statistic's endpoints
#: (it comes from the block, not from here), which is longer than a single axis line.
_LABEL_WRAP = 42


def _typicality_block(ranking: dict[str, Any], context: str) -> dict[str, Any]:
    """The typicality block, or a raise naming what is missing.

    The block is ``None`` on a document built without the axis's options -- a state the
    builder records as a skipped test. Rendering that as an empty figure would present a
    deliberate omission as a measured absence.
    """
    block = ranking.get("typicality")
    if block is None:
        raise ValueError(
            f"{context} requires a ranking built with the typicality options; this "
            "document carries typicality: null (the reason is in skipped_tests)."
        )
    return block


def _typicality_values(grid: dict[str, Any]) -> list[float]:
    """Every defined statistic value on the grid, the real population's included.

    The real population is in the list because the ramp's limits must cover it: it is
    drawn on the same colour scale as the cells, and limits computed without it would
    clip the one value the scale is centred on.
    """
    values = [
        float(cell["value"])
        for model in grid["models"]
        for cell in (grid["cells"][model][method] for method in grid["methods"])
        if cell is not None and cell["value"] is not None
    ]
    real = grid.get("real")
    if real is not None and real["value"] is not None:
        values.append(float(real["value"]))
    return values


def _typicality_limits(values: list[float]) -> tuple[float, float, bool]:
    """Colour limits for the typicality ramp: ``(vmin, vmax, flat)``.

    Anchored at the statistic's **true zero**, exactly as the sibling grids are, because
    zero here is a real measurement (total collapse onto one level) rather than the bottom
    of whatever this sweep happened to contain. A cell at the ramp's floor therefore always
    means "no internal variety at all", never "least in this particular run".

    The reference plays no part in the limits. It cannot: on a sequential ramp it is not a
    midpoint, and centring the range on it would push the observed values off both ends.
    It is drawn *onto* the finished ramp instead -- see ``_REFERENCE_RULE_WIDTH``.

    *flat* reports that every consumed competitor sits at the floor, so the ceiling is the
    fallback rather than a measured maximum; the caller prints it.
    """
    vmax = max(values)
    flat = vmax <= 0.0
    return 0.0, _FLAT_RANGE_CEILING if flat else vmax, flat


def _typicality_footnotes(
    block: dict[str, Any], *, country: str, reference_role: str, under_powered_mark: str,
    flat: bool, has_reference: bool, has_band: bool,
) -> list[str]:
    """The caveats that must travel *on* a typicality figure, in reading order.

    The reference first (the whole rendering is relative to it), then the direction
    refusal, then how to read a cell's two denominators, then what the marks mean, then
    what is excluded. Every caveat's *wording* comes from the block --
    ``reference_note``, ``direction_reason``, ``counting_unit``,
    ``under_powered_policy``, ``n_confound`` -- so the figure and the numbers it renders
    cannot disagree about what they mean. Only the two words for *how this figure draws
    a thing* (``reference_role``, ``under_powered_mark``) are the caller's, because they
    describe the rendering rather than the measurement.
    """
    reference = block["reference_value"]
    if has_reference:
        role = (
            f"{reference_role}: {country_label(country)} at {float(reference):.3f} -- "
            f"{block['reference_note']}"
        )
    else:
        role = f"No {reference_role.lower()}: {block['reference_note']}"
    lines = [
        role,
        *(
            ["Parenthesised in each cell: that competitor's signed distance to the "
             "reference. The ramp orders by magnitude only, so the SIDE of the reference "
             "is readable from this sign and from nothing else on the figure."]
            if has_reference else []
        ),
        f"Not a score: {block['direction_reason']}",
        f"Counted in {block['counting_unit']}",
        f"Under-powered ({under_powered_mark}, min_n = {block['min_n']}): "
        f"{block['under_powered_policy']}",
        f"Denominator confound: {block['n_confound']}",
    ]
    if flat:
        lines.append(
            "Every consumed competitor sits at the statistic's floor, so the ramp has no "
            f"measured range; its ceiling is the fallback {_FLAT_RANGE_CEILING} and every "
            "cell is drawn at the floor."
        )
    if has_band:
        lines.append(
            "The real population spans the full width because it has no method: it is not "
            "a model x method cell, and the factor tests hold it out."
        )
    return lines


@house_style
def plot_typicality_heatmap(
    ranking: dict[str, Any], *, variant: GridVariant = TYPICALITY_VARIANT_CLEAN,
):
    """Render the self-contained typicality statistic as a model x method grid.

    The severity and impossibility dimensions each have this figure; typicality had none,
    and appeared only as a *distance* on the headline map's y-axis. Here each cell is the
    competitor's own spread, computed from its own personas alone -- so a mode-collapsed
    combination and an over-dispersed one, which ``axis_b.dispersion_contrast`` cannot
    tell apart once it takes an absolute value, land on opposite sides of the ramp.

    **The reference is drawn onto the figure, never mixed into a cell's arithmetic.** It is
    read from ``block["reference_value"]`` -- the real population's own statistic, computed
    exactly as every competitor's -- and appears twice: as a rule across the colourbar at
    its own value, and as the signed delta beside every cell's number. Removing the real
    population from the consumption set removes both, with the reason printed on the
    figure, rather than falling back on a literal that would be a claim nobody measured.

    Because the ramp is sequential, the *side* of the reference is not in the colour: two
    competitors equally far above and below it are drawn differently, and neither drawing
    says which was which. That reading lives entirely in the printed delta, which is why
    the delta is not optional decoration.

    **Four states, four appearances**, because collapsing any two of them into one fill
    would publish a claim that was never made: a value (on the ramp), an under-powered
    value (on the ramp, hatched), a judged competitor with no typicality-bearing persona
    (white, cross-hatched, labelled), and an unjudged pair (grey, labelled). Computes
    nothing -- every number, and every caption's wording, arrives from the block.

    *variant* decides what a cell prints and nothing else: the clean publication, written
    at the bare filename, drops the count line, and the with-counts sibling keeps it. The
    **delta is in both** -- dropping it would remove the only reading of the reference's
    side this figure has -- and so is the real band's own ``n``, which is stated once
    rather than in every cell.

    Returns the ``Figure`` unsaved and open. Raises ``ValueError`` when no competitor has
    a defined statistic, matching the sibling charts.
    """
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.patches import Rectangle

    block = _typicality_block(ranking, "plot_typicality_heatmap")
    grid = block["grid"]
    models: list[str] = list(grid["models"])
    methods: list[str] = list(grid["methods"])
    real = grid.get("real")
    real_value = None if real is None else real["value"]

    values = _typicality_values(grid)
    if not values:
        raise ValueError(
            "plot_typicality_heatmap requires at least one competitor with a defined "
            "typicality statistic"
        )
    vmin, vmax, flat = _typicality_limits(values)
    reference = block["reference_value"]
    has_reference = reference is not None

    def _delta(value: float) -> str:
        """The signed distance to the reference, or nothing when there is none.

        Parenthesised and inline rather than on its own line: it qualifies the number it
        follows, and repeating "vs real" in fifty cells crowds out the number itself. The
        footnote names what the parentheses hold.
        """
        return f"  ({value - float(reference):+.3f})" if has_reference else ""

    n_rows = len(models) + (1 if real_value is not None else 0)
    plotted = np.full((n_rows, max(len(methods), 1)), np.nan)
    # A record only where the statistic exists. The two states that have no value -- a
    # judged competitor holding no typicality-bearing persona, and an unjudged pair --
    # are annotated below in their own wording and their own fill, because collapsing
    # either into a number would publish a claim nobody made. The signed distance to the
    # reference is pre-formatted here rather than in the policy: it needs a second unit's
    # value, which no cell's own record carries.
    cells: list[list[dict[str, Any] | None]] = []
    for i, model in enumerate(models):
        row: list[dict[str, Any] | None] = []
        for j, method in enumerate(methods):
            cell = grid["cells"][model][method]
            if cell is not None and cell["value"] is not None:
                value = float(cell["value"])
                plotted[i, j] = value
                row.append({
                    "value": value,
                    "denominator": cell["denominator"],
                    "delta": _delta(value),
                })
            else:
                row.append(None)
        cells.append(row)
    if real_value is not None:
        plotted[-1, :] = float(real_value)
        cells.append([None] * max(len(methods), 1))

    fig, ax = plt.subplots(
        figsize=(
            grow_width(len(methods), per_item=1.5, padding=3.5, minimum=7.0),
            grow_height(n_rows, per_item=0.55, padding=2.4, minimum=3.2),
        ),
    )
    im = render_grid(
        ax, plotted, cells,
        policy=variant.policy,
        cmap=heatmap_cmap(_SEQUENTIAL_CMAP, missing=_MISSING_COLOR),
        norm=mcolors.Normalize(vmin=vmin, vmax=vmax),
        aspect="auto", fontsize=variant.fontsize, linespacing=variant.linespacing,
        zorder=4, interpolation="none",
    )

    # As every other grid in this task: letters on the method axis, display names on the
    # model axis, and the key printed with the footnotes below.
    letters = method_letters(methods) if methods else {}
    display_models = model_labels(models)
    row_labels = [display_models[model] for model in models]
    if real_value is not None:
        suffix = " -- deltas are measured against it" if has_reference else ""
        row_labels.append(f"{country_label(ranking['country'])}  (real population{suffix})")
    ax.set_xticks(range(max(len(methods), 1)))
    ax.set_xticklabels(
        [letters[m] for m in methods] if methods else [""], fontsize=TICK_LABEL,
    )
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(row_labels, fontsize=TICK_LABEL)

    for i, model in enumerate(models):
        for j, method in enumerate(methods):
            cell = grid["cells"][model][method]
            if cell is None:
                ax.text(j, i, "not judged", ha="center", va="center", fontsize=ANNOTATION,
                        color=SECONDARY_GREY, style="italic")
                continue
            if cell["value"] is None:
                # Judged, but no persona survived to carry a typicality: a measurement
                # that could not be made, which is not the same as one that was not tried.
                ax.add_patch(Rectangle(
                    (j - 0.5, i - 0.5), 1, 1, facecolor=_NO_TYPICALITY_COLOR,
                    edgecolor=_NO_TYPICALITY_EDGE, hatch=_NO_TYPICALITY_HATCH,
                    linewidth=0.0, zorder=2,
                ))
                ax.text(j, i, f"no typicality\nof {cell['n_personas']} personas",
                        ha="center", va="center", fontsize=ANNOTATION, color=FOOTNOTE_GREY,
                        style="italic", zorder=4)
                continue
            if cell["under_powered"]:
                # Under the annotation the shared renderer already drew at zorder 4: the
                # hatch qualifies the number and must not strike through it.
                ax.add_patch(Rectangle(
                    (j - 0.5, i - 0.5), 1, 1, fill=False, edgecolor=_UNDER_POWERED_EDGE,
                    hatch=_UNDER_POWERED_HATCH, linewidth=0.0, zorder=2,
                ))

    if real_value is not None:
        row = n_rows - 1
        ax.axhline(row - 0.5, color=SURFACE, linewidth=3.0)
        centre = (len(methods) - 1) / 2.0 if methods else 0.0
        if real["under_powered"]:
            # The reference is measured on the same terms as everyone else, and can be
            # too thin to read like anyone else. An unmarked band would present a shaky
            # reference as a firm one -- and every cell's printed delta is measured
            # against it.
            ax.add_patch(Rectangle(
                (-0.5, row - 0.5), max(len(methods), 1), 1, fill=False,
                edgecolor=_UNDER_POWERED_EDGE, hatch=_UNDER_POWERED_HATCH,
                linewidth=0.0, zorder=2,
            ))
        ax.text(
            centre, row, f"{float(real_value):.3f}   n={real['denominator']}",
            ha="center", va="center", fontsize=ANNOTATION, zorder=4,
            color=text_color_on(im, float(real_value)),
        )

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    # The label states the statistic's endpoints and its lack of a direction, both read
    # from the block: a colourbar that says only "IOV" leaves the reader to guess which
    # end is which, and this family's own implementations disagree about that.
    cbar.set_label(
        textwrap.fill(f"{block['statistic_label']} -- no better/worse direction", _LABEL_WRAP),
        fontsize=AXIS_TITLE,
    )
    cbar.ax.tick_params(labelsize=TICK_LABEL)
    if has_reference:
        # The one place on this figure where the reference is visible rather than
        # arithmetic. Its colour is taken from the ramp position it marks, so the rule
        # stays visible whether it lands on the dark floor or the bright ceiling.
        cbar.ax.axhline(
            float(reference), color=text_color_on(im, float(reference)),
            linewidth=_REFERENCE_RULE_WIDTH,
        )

    ax.set_xlabel("Method (strategy)", fontsize=AXIS_TITLE)
    ax.set_ylabel("Model", fontsize=AXIS_TITLE)
    subtitle = (
        "sequential ramp; the rule on the colourbar is the real population"
        if has_reference else "sequential ramp -- no real population to measure against"
    )
    ax.set_title(
        f"Typicality -- {block['statistic']} by model x method\n"
        f"({subtitle}; grey = not judged, which is not a value of zero)",
        fontsize=FIGURE_TITLE, fontweight="bold",
    )
    # The variant's clause leads: what a cell prints is the one sentence the two
    # publications do not share, and it is what tells the reader whether the denominator
    # is on this figure or in the CSV beside it.
    _place_footnote(fig, ax, [variant.cell_clause, *_typicality_footnotes(
        block, country=ranking["country"], reference_role="Colourbar rule", under_powered_mark="hatched", flat=flat,
        has_reference=has_reference, has_band=real_value is not None,
    )])
    return fig


def _model_colors(n_models: int, palette) -> list[Any]:
    """One colour per model, most-distinguishable first.

    ``tab20`` is a set of ten hues each paired with a lighter tint of itself, in
    alternating order, so taking its entries in sequence hands the first two models two
    shades of the same blue -- the pair a reader is most likely to confuse on a figure
    whose whole content is which model sits where. Every *dark* entry is taken first, and
    the light tints only once the ten hues are exhausted. The red pair is withheld
    (:data:`_RESERVED_MODEL_COLORS`) because red identifies the real population here.
    """
    order = [
        index
        for index in list(range(0, palette.N, 2)) + list(range(1, palette.N, 2))
        if index not in _RESERVED_MODEL_COLORS
    ]
    return [palette(order[index % len(order)]) for index in range(n_models)]


def _method_dodge(n_models: int) -> list[float]:
    """Per-model x-offsets within one method's slot, evenly spread and deterministic.

    A dodge rather than the jitter its sibling panel in ``method_significance`` uses: the
    offsets there come from a seeded RNG, which is reproducible but places a model at a
    different position in each method's slot, so the eye cannot follow one model across
    the axis. Here a model keeps its offset, which is what makes the per-model polyline
    readable -- and the figure stays byte-identical without depending on a seed.
    """
    if n_models <= 1:
        return [0.0]
    step = _METHOD_DODGE_SPAN / (n_models - 1)
    return [-_METHOD_DODGE_SPAN / 2 + step * i for i in range(n_models)]


@house_style
def plot_typicality_by_method(ranking: dict[str, Any]):
    """Render the typicality statistic with the methods on x and the real value as a line.

    The heatmap's complement: it answers "does the spread track the method" in the shape
    the rest of the analysis layer asks that question in -- methods on x in complexity
    order (taken from ``grid["methods"]`` verbatim, never re-sorted here), one mark per
    model, and each model's marks joined so a reader can follow it across the axis.

    **The real population is a horizontal reference line here, and nowhere else in this
    task.** Everywhere else it is an ordinary series, bar or marker, because everywhere
    else it is *ranked* and a reference line would encode "closer to it is better" into a
    figure whose whole point is not to assume that. This axis ranks nothing: the line is
    the same reference the sibling heatmap prints a delta against, drawn so each method's
    spread around it is visible. It carries the real population's own colour and slug so it cannot be read as
    a target or a threshold.

    Under-powered competitors are drawn hollow rather than dropped, and their intervals
    are drawn with everyone else's: a mark with no visible uncertainty on a bounded
    statistic invites being read as exact. Returns the ``Figure`` unsaved and open; raises
    ``ValueError`` when no competitor has a defined statistic.
    """
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    block = _typicality_block(ranking, "plot_typicality_by_method")
    grid = block["grid"]
    models: list[str] = list(grid["models"])
    methods: list[str] = list(grid["methods"])
    if not _typicality_values(grid):
        raise ValueError(
            "plot_typicality_by_method requires at least one competitor with a defined "
            "typicality statistic"
        )

    fig, ax = plt.subplots(figsize=figure_size(grow_width(len(methods), per_item=1.6, padding=3.0, minimum=FULL), 6.0))
    # Letters on the method axis with the key among the footnotes; display names in the
    # legend, which is the one place on this figure with room for a phrase.
    letters = method_letters(methods)
    display_models = model_labels(models)
    colours = _model_colors(len(models), plt.get_cmap(_MODEL_CMAP))
    offsets = _method_dodge(len(models))
    handles: list[Line2D] = []
    any_under_powered = False

    for index, model in enumerate(models):
        colour = colours[index]
        xs: list[float] = []
        ys: list[float] = []
        drawn = 0
        for position, method in enumerate(methods):
            x = position + offsets[index]
            cell = grid["cells"][model][method]
            if cell is None or cell["value"] is None:
                # A break in the polyline, not a shortcut across the gap: joining the two
                # neighbours would draw a segment through a method this model was never
                # judged on, which is the one thing the line must not imply.
                xs.append(x)
                ys.append(float("nan"))
                continue
            value = float(cell["value"])
            if cell["ci_lo"] is not None and cell["ci_hi"] is not None:
                ax.plot([x, x], [cell["ci_lo"], cell["ci_hi"]],
                        color=opaque(colour, 0.45), linewidth=0.9, zorder=2)
            if cell["under_powered"]:
                any_under_powered = True
                ax.scatter(x, value, s=46, facecolors="none", edgecolors=colour,
                           linewidths=1.2, zorder=3)
            else:
                ax.scatter(x, value, s=46, color=colour, edgecolor=SURFACE,
                           linewidth=0.4, zorder=3)
            xs.append(x)
            ys.append(value)
            drawn += 1
        if drawn > 1:
            ax.plot(xs, ys, color=opaque(colour, 0.55), linewidth=0.9, zorder=2)
        if drawn:
            handles.append(Line2D([], [], color=colour, marker="o", markersize=5,
                                  linewidth=0.9, markeredgecolor=SURFACE,
                                  markeredgewidth=0.4, label=display_models[model]))

    reference = block["reference_value"]
    if reference is not None:
        ax.axhline(float(reference), color=_REAL_COLOR, linestyle="--",
                   linewidth=1.1, zorder=1)
        # Inline, at the left edge and lifted a few points clear of the line, following
        # the c2st reference-line idiom: a legend entry alone would leave the line
        # unlabelled where it is actually read, and a baseline sitting *on* the line lets
        # the dashes strike through the label.
        ax.annotate(
            f"{country_label(ranking['country'])} = {float(reference):.3f}  "
            "(real population, not a target)",
            xy=(-0.55, float(reference)), xytext=(0, 3), textcoords="offset points",
            va="bottom", ha="left", fontsize=ANNOTATION, color=_REAL_COLOR,
        )
    if any_under_powered:
        handles.append(Line2D([], [], color=FOOTNOTE_GREY, marker="o", markersize=6,
                              markerfacecolor="none", markeredgewidth=1.2, linestyle="none",
                              label=f"hollow = under-powered (n < {block['min_n']})"))

    ax.set_xticks(range(len(methods)))
    ax.set_xticklabels([letters[m] for m in methods], fontsize=TICK_LABEL)
    ax.set_xlim(-0.6, len(methods) - 0.4)
    ax.set_xlabel("Generation method -- simplest first", fontsize=AXIS_TITLE)
    ax.set_ylabel(textwrap.fill(block["statistic_label"], _LABEL_WRAP), fontsize=AXIS_TITLE)
    ax.set_title(
        f"Typicality -- {block['statistic']} by method, one mark per model\n"
        "(no better/worse direction: the optimum is interior)",
        fontsize=FIGURE_TITLE, fontweight="bold",
    )
    ax.tick_params(axis="y", labelsize=TICK_LABEL)
    ax.grid(axis="y", linestyle=":", linewidth=0.5, color=GRID_RULE, zorder=0)
    ax.set_axisbelow(True)
    if handles:
        ax.legend(handles=handles, fontsize=LEGEND_LABEL, loc="center left",
                  bbox_to_anchor=(1.01, 0.5))

    excluded = block["excluded"]
    footnotes = _typicality_footnotes(
        block, country=ranking["country"], reference_role="Reference line", under_powered_mark="hollow", flat=False,
        has_reference=reference is not None, has_band=False,
    )
    footnotes.append(
        f"Not drawn: {excluded['cells_unjudged']} unjudged model x method pair(s) and "
        f"{excluded['competitors_without_typicality']} judged competitor(s) whose personas "
        f"carry no typicality; {excluded['competitors_under_powered']} under-powered "
        "competitor(s) are drawn hollow rather than dropped."
    )
    _place_footnote(fig, ax, footnotes)
    return fig


# --------------------------------------------------------------------------- #
# The typicality distribution grid                                              #
# --------------------------------------------------------------------------- #
#
# The approved layout (P20 of the typicality-distribution-grid plan), in points with the
# origin at the bottom left of a fixed 456 pt canvas. Every value below is that
# geometry, named once; the layout function derives every box from them and the chart
# test asserts the boxes, so a change here is a visible change to the published figure.

#: Canvas width: the manuscript text block (``style.TEXT_WIDTH``), fixed.
_DG_CANVAS_WIDTH_PT = TEXT_WIDTH * POINTS_PER_INCH
#: Side of a square cell when the columns fit; the side shrinks below it only when more
#: models than the approved twelve must share the width.
_DG_MAX_CELL_PT = 26.5
#: Below this side an 8 pt column label no longer fits its column: raise rather than draw.
_DG_MIN_CELL_PT = 18.0
_DG_COLUMN_GAP_PT = 1.5
_DG_ROW_GAP_PT = 3.0
#: Left edge of the grid; the strategy letters sit in the margin to its left.
_DG_GRID_LEFT_PT = 20.0
_DG_ROW_LETTER_GAP_PT = 5.0
#: The detached reference column, the ternary column and the colourbar, left to right.
_DG_REFERENCE_GAP_PT = 6.0
_DG_TERNARY_GAP_PT = 5.0
_DG_TERNARY_PAD_PT = 1.5
_DG_COLORBAR_GAP_PT = 6.0
_DG_COLORBAR_WIDTH_PT = 7.0
#: Clearance kept between any ink and the canvas edge (the fixed-canvas writer rejects
#: ink that touches it).
_DG_EDGE_MARGIN_PT = 2.0
#: Vertical model labels above the grid: the block they sit in, and their baseline gap.
_DG_TOP_BLOCK_PT = 76.0
_DG_LABEL_GAP_PT = 2.0
#: Left edge of the bottom block's legend, note and key.
_DG_TEXT_LEFT_PT = 4.0
#: The bottom block, stacked from the canvas bottom up: the key's last line, the pitch
#: between key lines, then the note, the legend and the grid above it. With a one-row
#: legend and a two-line key this is the approved 60 pt block.
_DG_KEY_LAST_LINE_TOP_PT = 12.5
_DG_KEY_LINE_PITCH_PT = 10.5
_DG_NOTE_ABOVE_KEY_PT = 14.0
_DG_LEGEND_ABOVE_NOTE_PT = 13.0
_DG_LEGEND_ROW_PITCH_PT = 11.0
_DG_GRID_ABOVE_LEGEND_PT = 10.0
#: Legend entries that share one row before the legend wraps to a second.
_DG_LEGEND_ROW_ENTRIES = 6
#: Separators of the strategy key: after its title, and between entries.
_DG_KEY_TITLE_SEPARATOR = ":  "
_DG_KEY_ENTRY_SEPARATOR = "   "
#: The half-mass guide of the ternary's apex band.
_DG_APEX_GUIDES = (0.5,)
#: Mark of a judged competitor with no survivor (no distribution to draw).
_DG_NO_TYPICALITY_MARK = "–"


def _text_width_pt(text: str, fontsize: float) -> float:
    return text_width_inches(text, fontsize=fontsize) * POINTS_PER_INCH


def _distribution_cell_side(n_models: int, n_levels: int) -> float:
    """The square cell side: the approved 26.5 pt, or less when more columns must fit.

    The width is spent left to right on the grid margin, ``n_models`` cells and their
    gaps, the reference column, the ternary (whose side follows the cell), the colourbar
    and room for its widest tick label. Solving that sum for the side gives ``fit``.
    """
    reserve = (
        COLORBAR_TICK_LENGTH_PT + COLORBAR_TICK_PAD_PT
        + _text_width_pt(str(n_levels - 1), TICK_LABEL) + _DG_EDGE_MARGIN_PT
    )
    fixed = (
        _DG_GRID_LEFT_PT + (n_models - 1) * _DG_COLUMN_GAP_PT + _DG_REFERENCE_GAP_PT
        + _DG_TERNARY_GAP_PT - 2 * _DG_TERNARY_PAD_PT / TERNARY_HEIGHT_RATIO
        + _DG_COLORBAR_GAP_PT + _DG_COLORBAR_WIDTH_PT + reserve
    )
    fit = (_DG_CANVAS_WIDTH_PT - fixed) / (n_models + 1 + 1 / TERNARY_HEIGHT_RATIO)
    side = min(_DG_MAX_CELL_PT, fit)
    if side < _DG_MIN_CELL_PT:
        raise ValueError(
            f"{n_models} model columns leave a {fit:.1f} pt cell on the fixed "
            f"{_DG_CANVAS_WIDTH_PT:.0f} pt canvas, below the {_DG_MIN_CELL_PT} pt floor at "
            "which an 8 pt column label still fits; draw fewer models"
        )
    return side


def _key_lines(entries: list[str], title: str, width_pt: float) -> list[str]:
    """Split the strategy key into the fewest balanced lines that fit *width_pt*.

    The first line opens with *title*; later lines hang under the first entry, so every
    line has the title's width less room. Balanced, earlier lines longer: five entries
    are set 3 + 2, as the approved layout sets them.
    """
    room = width_pt - _text_width_pt(title, LEGEND_LABEL)
    for n_lines in range(1, len(entries) + 1):
        per_line = -(-len(entries) // n_lines)
        lines = [
            _DG_KEY_ENTRY_SEPARATOR.join(entries[i:i + per_line])
            for i in range(0, len(entries), per_line)
        ]
        if max(_text_width_pt(line, LEGEND_LABEL) for line in lines) <= room:
            return lines
    raise ValueError(f"a strategy key entry is wider than the {room:.0f} pt the figure has for it")


@dataclass(frozen=True)
class _DistributionGridLayout:
    """Every box of the distribution grid, in points (see the P20 constants above)."""

    width: float
    height: float
    cell: float
    column_x0: tuple[float, ...]
    row_y: tuple[tuple[float, float], ...]
    reference_x: tuple[float, float]
    ternary_x0: float
    ternary_side: float
    colorbar_box: tuple[float, float, float, float]
    grid_y: tuple[float, float]
    legend_top: float
    note_top: float
    key_tops: tuple[float, ...]


def _distribution_grid_layout(
    n_models: int, n_methods: int, n_levels: int, *, legend_rows: int, key_lines: int,
) -> _DistributionGridLayout:
    """The P20 geometry for *n_models* columns and *n_methods* rows (rows top to bottom)."""
    cell = _distribution_cell_side(n_models, n_levels)
    key_tops = tuple(
        _DG_KEY_LAST_LINE_TOP_PT + (key_lines - 1 - i) * _DG_KEY_LINE_PITCH_PT
        for i in range(key_lines)
    )
    note_top = key_tops[0] + _DG_NOTE_ABOVE_KEY_PT
    legend_top = note_top + _DG_LEGEND_ABOVE_NOTE_PT + (legend_rows - 1) * _DG_LEGEND_ROW_PITCH_PT
    y0 = legend_top + _DG_GRID_ABOVE_LEGEND_PT
    y1 = y0 + n_methods * cell + (n_methods - 1) * _DG_ROW_GAP_PT
    column_x0 = tuple(_DG_GRID_LEFT_PT + j * (cell + _DG_COLUMN_GAP_PT) for j in range(n_models))
    reference_x0 = column_x0[-1] + cell + _DG_REFERENCE_GAP_PT
    ternary_x0 = reference_x0 + cell + _DG_TERNARY_GAP_PT
    ternary_side = (cell - 2 * _DG_TERNARY_PAD_PT) / TERNARY_HEIGHT_RATIO
    colorbar_x0 = ternary_x0 + ternary_side + _DG_COLORBAR_GAP_PT
    row_y = tuple(
        (y1 - i * (cell + _DG_ROW_GAP_PT) - cell, y1 - i * (cell + _DG_ROW_GAP_PT))
        for i in range(n_methods)
    )
    return _DistributionGridLayout(
        width=_DG_CANVAS_WIDTH_PT, height=y1 + _DG_TOP_BLOCK_PT, cell=cell,
        column_x0=column_x0, row_y=row_y, reference_x=(reference_x0, reference_x0 + cell),
        ternary_x0=ternary_x0, ternary_side=ternary_side,
        colorbar_box=(colorbar_x0, y0, colorbar_x0 + _DG_COLORBAR_WIDTH_PT, y1),
        grid_y=(y0, y1), legend_top=legend_top, note_top=note_top, key_tops=key_tops,
    )


def _distribution_block(ranking: dict[str, Any]) -> dict[str, Any]:
    block = ranking.get("typicality_distribution")
    if block is None:
        raise ValueError(
            "plot_typicality_distribution_grid requires a ranking built with the typicality "
            "options; this document carries typicality_distribution: null (the reason is in "
            "skipped_tests)."
        )
    return block


@house_style
def plot_typicality_distribution_grid(
    ranking: dict[str, Any], *, model_order: list[str], hosting: dict[str, str],
):
    """Draw every combination's typicality distribution on the model x strategy grid.

    One mini histogram per cell -- strategies down the rows in complexity order (the
    block's ``grid.methods``, verbatim), models across the columns in *model_order* --
    with the reference's distribution drawn over each as a step outline, the reference
    itself in a detached column, one ternary per strategy placing every combination's
    three band shares beside the reference's star, and a stepped colourbar whose steps
    are the bars' colours. Laid out on a fixed 456 pt canvas; the caller saves it with
    ``save_figure(..., fixed_canvas=True)``.

    Each cell state has its own drawing, mapped here and computed nowhere: ``ok`` a
    histogram, ``withdrawn`` a crossed-out cell (the gate excluded the combination),
    ``unjudged`` a grey cell, ``no_typicality`` an empty frame with a centred dash. The
    legend lists "not judged" and "no typicality" only when such a cell is drawn.

    Args:
        ranking: The built ranking; its ``typicality_distribution`` block is drawn.
        model_order: The grid's models in the published ``model_ranking`` order
            (resolved at the edge through ``utils.model_order.ranked_grid_columns``).
            Must hold exactly the block's grid models.
        hosting: ``{model: "hosted" | "local"}``, the column-label and point tint,
            classified at the edge from config.

    Returns the ``Figure`` unsaved and open. Raises ``ValueError`` when the block is
    absent, the consumption set holds no reference with a distribution (the outline, the
    column and the star *are* the comparison), *model_order* is not exactly the grid's
    models, a model has no hosting class, or the layout cannot fit the canvas.
    """
    block = _distribution_block(ranking)
    grid = block["grid"]
    grid_models: list[str] = list(grid["models"])
    methods: list[str] = list(grid["methods"])
    states = grid["states"]
    n_levels = int(block["n_levels"])
    band_labels: list[str] = list(block["bands"]["labels"])

    real = grid["real"]
    if real is None:
        raise ValueError("no real population in the consumption set")
    if real["status"] != "ok":
        raise ValueError(
            f"the real population {real['slug']!r} has no scored survivor, so there is no "
            "reference distribution to draw"
        )
    if not grid_models or not methods:
        raise ValueError("the distribution grid holds no model x strategy cell")
    if len(set(model_order)) != len(model_order) or set(model_order) != set(grid_models):
        raise ValueError(
            f"model_order {list(model_order)} must hold exactly the grid's models {sorted(grid_models)}"
        )
    unclassified = [m for m in model_order if hosting.get(m) not in HOST_COLORS]
    if unclassified:
        raise ValueError(f"model(s) {unclassified} have no hosting class in {sorted(HOST_COLORS)}")

    # Display strings, every one resolved from config.
    model_names = model_labels(model_order)
    letters = method_letters(methods)
    reference_term = figure_term("reference")
    key_title = figure_term("strategy_key_title") + _DG_KEY_TITLE_SEPARATOR
    note = (
        f"Triangles: share of {figure_term('individuals')} in score bands "
        f"{' / '.join(band_labels)} (corners); bar heights √-scaled"
    )

    drawn_states = {states[m][s] for m in model_order for s in methods}
    handles = [
        swatch_handle(HOST_LABELS["hosted"], color=HOST_COLORS["hosted"]),
        swatch_handle(HOST_LABELS["local"], color=HOST_COLORS["local"]),
        outline_handle(f"{reference_term} outline"),
        withdrawn_handle("withdrawn"),
    ]
    if "unjudged" in drawn_states:
        handles.append(swatch_handle("not judged", color=MISSING_COLOR))
    if "no_typicality" in drawn_states:
        handles.append(swatch_handle("no typicality", color=SURFACE, edgecolor=GRID_RULE))
    handles += [point_handle("combination", color=BASELINE_DARK), reference_star_handle(reference_term)]
    ncol = min(len(handles), max(_DG_LEGEND_ROW_ENTRIES, -(-len(handles) // 2)))
    legend_rows = -(-len(handles) // ncol)

    key = _key_lines(method_key_lines(methods), key_title, _DG_CANVAS_WIDTH_PT - 2 * _DG_TEXT_LEFT_PT)
    layout = _distribution_grid_layout(
        len(model_order), len(methods), n_levels, legend_rows=legend_rows, key_lines=len(key),
    )
    label_room = _DG_TOP_BLOCK_PT - _DG_LABEL_GAP_PT - _DG_EDGE_MARGIN_PT
    for name in [*model_names.values(), reference_term]:
        if _text_width_pt(name, TICK_LABEL) > label_room:
            raise ValueError(f"column label {name!r} is longer than the {label_room:.0f} pt above the grid")

    canvas = PointCanvas(layout.width, layout.height)
    levels = heatmap_levels(n_levels)
    colors = step_colors(levels)
    reference = real["distribution"]
    reference_x0, reference_x1 = layout.reference_x

    for i, method in enumerate(methods):
        bottom, top = layout.row_y[i]
        for j, model in enumerate(model_order):
            x0 = layout.column_x0[j]
            ax = canvas.axes(x0, bottom, x0 + layout.cell, top)
            state = states[model][method]
            if state == "ok":
                draw_mini_histogram(ax, grid["cells"][model][method]["distribution"], colors, outline=reference)
            elif state == "withdrawn":
                draw_withdrawn_cell(ax)
            elif state == "unjudged":
                draw_empty_cell(ax, fill=MISSING_COLOR, mark=None)
            elif state == "no_typicality":
                draw_empty_cell(ax, fill=SURFACE, mark=_DG_NO_TYPICALITY_MARK)
            else:
                raise ValueError(f"cell ({model}, {method}) has unknown state {state!r}")
        # The reference's own histogram, without an outline of itself.
        draw_mini_histogram(canvas.axes(reference_x0, bottom, reference_x1, top), reference, colors)
        shown = [m for m in model_order if states[m][method] == "ok"]
        tx0, ty0 = layout.ternary_x0, bottom + _DG_TERNARY_PAD_PT
        draw_ternary(
            canvas.axes(tx0, ty0, tx0 + layout.ternary_side, ty0 + layout.ternary_side * TERNARY_HEIGHT_RATIO),
            [grid["cells"][m][method]["band_shares"] for m in shown],
            real["band_shares"],
            point_colors=[HOST_COLORS[hosting[m]] for m in shown],
            apex_guides=_DG_APEX_GUIDES,
            apex_label=band_labels[2] if i == 0 else None,
            base_labels=(band_labels[0], band_labels[1]) if i == len(methods) - 1 else None,
        )
        canvas.text(
            _DG_GRID_LEFT_PT - _DG_ROW_LETTER_GAP_PT, (bottom + top) / 2, letters[method],
            fontsize=TICK_LABEL_LARGE, fontweight=HEADING_WEIGHT, ha="right", va="center",
            color=BASELINE_DARK,
        )

    stepped_colorbar(canvas, layout.colorbar_box, levels, n_levels, "Score")
    label_y = layout.grid_y[1] + _DG_LABEL_GAP_PT
    for x0, model in zip(layout.column_x0, model_order):
        canvas.text(x0 + layout.cell / 2, label_y, model_names[model], fontsize=TICK_LABEL, rotation=90,
                    ha="center", va="bottom", color=HOST_COLORS[hosting[model]])
    canvas.text((reference_x0 + reference_x1) / 2, label_y, reference_term, fontsize=TICK_LABEL, rotation=90,
                ha="center", va="bottom", color=BASELINE_DARK)

    canvas.legend(handles, x=_DG_TEXT_LEFT_PT, y_top=layout.legend_top, ncol=ncol)
    canvas.text(_DG_TEXT_LEFT_PT, layout.note_top, note, fontsize=LEGEND_LABEL, ha="left", va="top",
                color=FOOTNOTE_GREY)
    # Continuation lines hang under the first entry, measured from the title itself.
    hang = _text_width_pt(key_title, LEGEND_LABEL)
    for index, (line, line_top) in enumerate(zip(key, layout.key_tops)):
        text, x = (key_title + line, _DG_TEXT_LEFT_PT) if index == 0 else (line, _DG_TEXT_LEFT_PT + hang)
        canvas.text(x, line_top, text, fontsize=LEGEND_LABEL, ha="left", va="top", color=FOOTNOTE_GREY)
    return canvas.figure
