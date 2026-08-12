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
  grid, on a **diverging** ramp whose midpoint is the real population's own value, read
  from the block. The optimum is interior, so neither end of the ramp is "better"; the
  two ends are "more collapsed than the register population" and "more dispersed than
  it". With no real population in the consumption set there is no midpoint, and the
  figure degrades to the neutral sequential ramp with the reason printed on it.
* :func:`plot_typicality_by_method` -- the same statistic with the methods on x in
  complexity order, one mark per model, and the real population as a horizontal
  reference line. It is the one figure in this task where the real population is a
  reference rather than a series, and it is drawn that way only because this axis has no
  ranking to hold it out of: the line is the ramp midpoint of its sibling heatmap, in a
  form that shows each method's spread around it.

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
from typing import Any

from population_synthetic.analysis.utils.palette import (
    HEATMAP_CMAP,
    MISSING_COLOR,
    heatmap_cmap,
    text_color_on,
)

__all__ = [
    "plot_headline_map",
    "plot_impossibility_forest",
    "plot_impossibility_heatmap",
    "plot_severity_heatmap",
    "plot_severity_pair_summary",
    "plot_typicality_by_method",
    "plot_typicality_heatmap",
]

_COMPETITOR_COLOR = "#4878CF"
_REAL_COLOR = "#C44E52"
_CI_COLOR = "#8C8C8C"

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
                "edgecolor": "black", "linewidth": 0.6, "zorder": 3}
    return {"marker": "o", "s": 90, "color": _COMPETITOR_COLOR,
            "edgecolor": "white", "linewidth": 0.5, "zorder": 2}


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
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    distances = {
        row["slug"]: (row.get("distance_to_scb") or {}).get(measure)
        for row in ranking["axis_b"]["dispersion_contrast"]
    }
    real_slug = ranking.get("real_competitor")

    plotted = [entry for entry in ranking["axis_a"]["ranking"] if entry["rate"] is not None]
    if not plotted:
        raise ValueError("plot_headline_map requires at least one competitor with a defined rate")

    fig, ax = plt.subplots(figsize=(9, 7))
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
        annotation = f"{slug}*" if undefined else slug
        ax.annotate(
            annotation, (entry["rate"], y),
            textcoords="offset points", xytext=(6, 4), fontsize=7,
        )

    ax.set_xlabel(
        "Axis A -- impossibility rate (share of internally-contradictory personas); lower is better",
        fontsize=9,
    )
    ax.set_ylabel(
        f"Axis B -- typicality-dispersion distance to the real population ({measure}); "
        "near zero is better",
        fontsize=9,
    )
    ax.set_title(
        "Persona realism -- coherence vs typicality coverage\n"
        "(the real population is ranked as an ordinary competitor on Axis A)",
        fontsize=12, fontweight="bold",
    )
    ax.axhline(0, color="gray", linestyle="--", linewidth=0.7, alpha=0.7, zorder=0)
    ax.tick_params(axis="both", labelsize=8)
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(handles, labels, fontsize=8, loc="best")
    if any(distances.get(e["slug"]) is None and e["slug"] != real_slug for e in plotted):
        ax.text(
            0.99, 0.01, "* Axis-B distance undefined; plotted on the x-axis only",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7, color="gray",
        )
    fig.tight_layout()
    return fig


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
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    entries = [e for e in ranking["axis_a"]["ranking"] if e["rate"] is not None]
    if not entries:
        raise ValueError("plot_impossibility_forest requires at least one competitor with a rate")

    real_slug = ranking.get("real_competitor")
    labels = [f"{e['slug']}  (n={e['denominator']})" for e in entries]
    positions = list(range(len(entries)))

    fig, ax = plt.subplots(figsize=(10, max(3.0, len(entries) * 0.32 + 1.8)))
    for pos, entry in zip(positions, entries):
        is_real = entry["slug"] == real_slug
        lo, hi = entry["ci_lo"], entry["ci_hi"]
        if lo is not None and hi is not None:
            ax.plot([lo, hi], [pos, pos], color=_CI_COLOR, linewidth=1.2, zorder=1)
        color = _REAL_COLOR if is_real else _COMPETITOR_COLOR
        marker = "D" if is_real else "o"
        ax.scatter(entry["rate"], pos, color=color, marker=marker, s=44, zorder=2,
                   edgecolor="white", linewidth=0.4)

    ax.set_yticks(positions)
    ax.set_yticklabels(labels, fontsize=7)
    ax.invert_yaxis()  # best (lowest rate) at the top
    ax.set_xlabel(
        f"Impossibility rate with {int(round(entries[0]['ci_level'] * 100))}% bootstrap CI; "
        "lower is better",
        fontsize=9,
    )
    ax.set_title(
        "Axis A -- impossibility rate by competitor (the real population included)",
        fontsize=12, fontweight="bold",
    )
    ax.tick_params(axis="x", labelsize=8)
    ax.grid(axis="x", linestyle=":", linewidth=0.5, alpha=0.6)
    fig.tight_layout()
    return fig

def _render_grid_heatmap(
    grid: dict[str, Any],
    *,
    title: str,
    cbar_label: str,
    caption: str,
    error_context: str,
):
    """Render one ``{models, methods, cells, real}`` grid as a heatmap.

    The single implementation behind every heatmap this task emits, so the layout and
    the guards below cannot diverge between them. Computes nothing: each cell payload
    already carries its ``rate`` and ``denominator``.

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
    import matplotlib
    matplotlib.use("Agg")
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
        figsize=(max(7.0, len(methods) * 1.5 + 3.5), max(3.2, n_rows * 0.55 + 2.4))
    )
    im = ax.imshow(
        np.ma.masked_invalid(plotted), aspect="auto",
        cmap=heatmap_cmap(_SEQUENTIAL_CMAP, missing=_MISSING_COLOR), vmin=0.0, vmax=vmax,
    )

    row_labels = list(models)
    if real_rate is not None:
        row_labels.append(f"{real['slug']}  (real population)")
    ax.set_xticks(range(max(len(methods), 1)))
    ax.set_xticklabels(methods or [""], rotation=30, ha="right", fontsize=8)
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(row_labels, fontsize=8)

    # Annotate each cell with its value and denominator; grey cells say so explicitly.
    for i, model in enumerate(models):
        for j, method in enumerate(methods):
            cell = grid["cells"].get(model, {}).get(method)
            if cell is None or cell.get("rate") is None:
                ax.text(j, i, "n/a", ha="center", va="center", fontsize=7.5,
                        color="#666666", style="italic")
                continue
            value = float(cell["rate"])
            ax.text(
                j, i, f"{value:.3f}\nn={cell['denominator']}",
                ha="center", va="center", fontsize=7,
                color=text_color_on(im, value),
            )

    if real_rate is not None:
        row = n_rows - 1
        # A thick white rule + the band's own label: this row is not a model.
        ax.axhline(row - 0.5, color="white", linewidth=3.0)
        centre = (len(methods) - 1) / 2.0 if methods else 0.0
        ax.text(
            centre, row, f"{float(real_rate):.3f}   n={real['denominator']}",
            ha="center", va="center", fontsize=7.5,
            color=text_color_on(im, float(real_rate)),
        )

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label(cbar_label, fontsize=8)
    cbar.ax.tick_params(labelsize=7)

    ax.set_xlabel("Method (strategy)", fontsize=9)
    ax.set_ylabel("Model", fontsize=9)
    ax.set_title(title, fontsize=12, fontweight="bold")

    footnotes = [caption] if caption else []
    if real_rate is not None:
        footnotes.append(
            "The real population spans the full width because it has no method: it is not "
            "a model x method cell, and the factor tests hold it out."
        )
    text = "\n".join(footnotes)
    if text:
        # Reserve a strip first, then place the caption inside it: an artist dropped
        # below the axes without reserved space collides with the rotated tick labels.
        reserved = 0.07 + 0.035 * text.count("\n")
        fig.tight_layout(rect=(0.0, reserved, 1.0, 1.0))
        fig.text(0.5, 0.015, text, ha="center", va="bottom", fontsize=7, color="#555555")
    else:
        fig.tight_layout()
    return fig


def plot_impossibility_heatmap(ranking: dict[str, Any]):
    """Render Axis A as a model x method grid, with the real population as its own band.

    The forest plot answers "who is most coherent"; this one answers "does incoherence
    track the model, the method, or neither" -- the same question the Kruskal-Wallis
    tests answer numerically, in a form that shows the pattern rather than a p-value.
    Every number arrives pre-computed in ``axis_a.grid``.
    """
    return _render_grid_heatmap(
        ranking["axis_a"]["grid"],
        title=(
            "Axis A -- impossibility rate by model x method\n"
            "(grey = not judged, which is not a rate of zero)"
        ),
        cbar_label="Impossibility rate -- lower is better",
        caption="",
        error_context="plot_impossibility_heatmap",
    )


def plot_severity_heatmap(ranking: dict[str, Any], severity: str):
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
        title=(
            f"Severity {severity} -- share of personas with >=1 {severity} clash\n"
            f"({level['meaning']}; grey = not judged, not a prevalence of zero)"
        ),
        cbar_label=cbar_label,
        caption=caption,
        error_context=f"plot_severity_heatmap({severity})",
    )


#: Wrap width for the footnote block, in characters. Chosen for reading comfort rather
#: than for the figure's physical width: at 7pt the frame would hold well over 200
#: characters per line, which is past the point where the eye loses the line return.
_FOOTNOTE_WRAP = 140

#: Gap between the axes' lowest decoration and the first footnote line, in inches.
_FOOTNOTE_GAP_IN = 0.22


def _place_footnote(fig, ax, sentences: list[str]) -> None:
    """Hang the wrapped footnote directly under *ax*'s lowest decoration.

    Anchored to the axes' measured tight bounding box rather than to a reserved fraction
    of the figure: this figure's height grows with the number of bars, so any fixed
    fraction is simultaneously too much on one level and too little on another, and the
    first version of it left a hand's width of white space under the six-bar S3 chart.

    The text may extend below the figure canvas. That is deliberate and safe here --
    ``utils/figures.save_figure`` writes with ``bbox_inches="tight"``, which unions every
    artist's bounds (including those outside the canvas) and grows the output to fit. The
    caveats are the reason this figure can travel without its docstring, so they must
    never be the thing that gets cropped.
    """
    text = "\n".join(textwrap.fill(sentence, width=_FOOTNOTE_WRAP) for sentence in sentences)
    fig.tight_layout()
    fig.canvas.draw()   # the tight bbox below is only defined once a renderer exists
    box = ax.get_tightbbox(fig.canvas.get_renderer()).transformed(fig.transFigure.inverted())
    fig.text(
        0.5, box.y0 - _FOOTNOTE_GAP_IN / fig.get_figheight(), text,
        ha="center", va="top", fontsize=7, color="#555555",
    )


def _pair_summary_footnotes(summary: dict[str, Any]) -> list[str]:
    """The caveats that must travel *on* the figure, in reading order.

    Denominator first (a share is unreadable without it), then how the numbers were
    counted, then why they do not add up, then where they came from, then what was cut.
    Each caveat's *wording* is read from the payload (``counting_unit`` /
    ``non_additive`` / ``provenance`` / the level's ``direction``) rather than restated
    here, so the figure and the block it renders cannot disagree about what the bars mean.
    """
    real_slug, real_denominator = summary["real_slug"], summary["real_denominator"]
    lines = [
        f"Denominator: {summary['denominator']} personas pooled over "
        f"{summary['n_synthetic_competitors']} synthetic combination(s) -- the same "
        "population the severity heatmap divides its cells by. "
        + (
            f"{real_slug} is counted separately over its own {real_denominator} personas "
            "and is never pooled into the bars."
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
        ha="left", va="center", fontsize=7, color=color,
        fontweight="bold" if bold else "normal", annotation_clip=False,
    )


def _empty_pair_summary(summary: dict[str, Any], title: str):
    """The figure a level with nothing to rank gets -- an explanation, not empty axes.

    "No pair clashed at this level in any competitor" is a measurement, and a strong one:
    the neighbouring case on the current Swedish data, where the real population raises no
    S3 clash while the synthetic ones do, is the sharpest single number these figures
    produce. Emitting nothing here would make the strong result indistinguishable from a
    crashed render, and emitting a blank axis would make it look like a rendering bug; the
    figure says which it is, and the denominators still travel with it.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.axis("off")
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.text(
        0.5, 0.55,
        f"No {summary['severity']} clash was raised by any consumed competitor.\n"
        "There is nothing to rank at this level -- this is a measured absence, "
        "not a missing figure.",
        transform=ax.transAxes, ha="center", va="center", fontsize=10, color="#333333",
    )
    _place_footnote(fig, ax, _pair_summary_footnotes(summary))
    return fig


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
    import matplotlib
    matplotlib.use("Agg")
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

    labels = [f"{pair['attr_a']} x {pair['attr_b']}" for pair in pairs]
    values = [0.0 if pair["prevalence"] is None else float(pair["prevalence"]) for pair in pairs]
    positions = list(range(len(pairs)))

    fig, ax = plt.subplots(figsize=(12, max(3.6, len(pairs) * 0.42 + 2.6)))
    ax.barh(
        positions, values, height=0.62, color=_COMPETITOR_COLOR,
        edgecolor="white", linewidth=0.4, zorder=2,
        label=f"synthetic combinations pooled (n={summary['denominator']})",
    )

    real_slug = summary["real_slug"]
    real_values = [pair["real_prevalence"] for pair in pairs]
    drawn = [(pos, v) for pos, v in zip(positions, real_values) if v is not None]
    if real_slug is not None and drawn:
        ax.scatter(
            [v for _, v in drawn], [pos for pos, _ in drawn],
            marker="D", s=52, color=_REAL_COLOR, edgecolor="black", linewidth=0.6,
            zorder=4, label=f"{real_slug} (n={summary['real_denominator']})",
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
        _column(ax, pos, _COLUMN_SYNTHETIC_PT, f"{share}   n={pair['n_personas']}", "#333333")
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
    ax.set_yticklabels(labels, fontsize=8)
    # Top-down (most-affected first) with room above row 0 for the column headers. Set
    # directly rather than via invert_yaxis(), which would flip the reserved strip to the
    # bottom of the figure where the headers would sit under the columns they name.
    ax.set_ylim(len(pairs) - 0.5, _HEADER_ROW - 0.4)
    ax.set_xlabel(
        f"Share of personas exhibiting the pair at {severity} "
        "(each series over its own denominator)",
        fontsize=9,
    )
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.tick_params(axis="x", labelsize=8)
    ax.grid(axis="x", linestyle=":", linewidth=0.5, alpha=0.6, zorder=0)
    ax.set_axisbelow(True)
    handles, legend_labels = ax.get_legend_handles_labels()
    if real_slug is not None and not drawn:
        # Every listed pair happens to be absent from the real population: keep the series
        # in the legend anyway, at zero, so "SCB raised none of these" reads as a result
        # rather than as a series that was never drawn.
        handles.append(Line2D(
            [], [], linestyle="none", marker="D", markersize=6, color=_REAL_COLOR,
            markeredgecolor="black", markeredgewidth=0.6,
        ))
        legend_labels.append(
            f"{real_slug} (n={summary['real_denominator']}) -- none of these pairs"
        )
    if handles:
        # Bars first, the real series second: the bars are what the ranking is over, and
        # matplotlib's collection-before-patch ordering would otherwise lead with the
        # series that is deliberately not pooled into it.
        order = sorted(range(len(handles)), key=lambda i: legend_labels[i].startswith("synthetic"),
                       reverse=True)
        ax.legend([handles[i] for i in order], [legend_labels[i] for i in order],
                  fontsize=8, loc="best", framealpha=0.92)
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
_UNDER_POWERED_EDGE = "#333333"
_UNDER_POWERED_ALPHA = 0.35

#: Fill + overlay for a cell whose competitor was judged but carries NO typicality-bearing
#: persona (every persona was judged impossible). The fourth state on this figure, and
#: deliberately neither the ramp (there is no value), nor ``_MISSING_COLOR`` (that pair was
#: never judged), nor the under-powered hatch (that one has a value).
_NO_TYPICALITY_COLOR = "#FFFFFF"
_NO_TYPICALITY_HATCH = "xx"
_NO_TYPICALITY_EDGE = "#CCCCCC"

#: Ceiling the ramp falls back to when every consumed competitor sits at the statistic's
#: floor. The range is then genuinely zero-width; a ramp cannot be built on it and
#: normalising by it would divide by zero. Every cell renders at the ramp's bottom, which
#: is the truth (they are all totally collapsed), and the figure says so in a footnote
#: rather than implying a spread the limits invented.
_FLAT_RANGE_CEILING = 1.0

#: Qualitative colours for the per-model marks on the methods-on-x figure. Qualitative,
#: because model identity is nominal: a sequential ramp over an alphabetical model list
#: would encode an order that does not exist.
_MODEL_CMAP = "tab20"

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
    block: dict[str, Any], *, reference_role: str, under_powered_mark: str,
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
            f"{reference_role}: {block['reference_slug']} at {float(reference):.3f} -- "
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


def plot_typicality_heatmap(ranking: dict[str, Any]):
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

    Returns the ``Figure`` unsaved and open. Raises ``ValueError`` when no competitor has
    a defined statistic, matching the sibling charts.
    """
    import matplotlib
    matplotlib.use("Agg")
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
    for i, model in enumerate(models):
        for j, method in enumerate(methods):
            cell = grid["cells"][model][method]
            if cell is not None and cell["value"] is not None:
                plotted[i, j] = float(cell["value"])
    if real_value is not None:
        plotted[-1, :] = float(real_value)

    fig, ax = plt.subplots(
        figsize=(max(7.0, len(methods) * 1.5 + 3.5), max(3.2, n_rows * 0.55 + 2.4))
    )
    im = ax.imshow(
        np.ma.masked_invalid(plotted), aspect="auto",
        cmap=heatmap_cmap(_SEQUENTIAL_CMAP, missing=_MISSING_COLOR), vmin=vmin, vmax=vmax,
    )

    row_labels = list(models)
    if real_value is not None:
        suffix = " -- deltas are measured against it" if has_reference else ""
        row_labels.append(f"{real['slug']}  (real population{suffix})")
    ax.set_xticks(range(max(len(methods), 1)))
    ax.set_xticklabels(methods or [""], rotation=30, ha="right", fontsize=8)
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(row_labels, fontsize=8)

    for i, model in enumerate(models):
        for j, method in enumerate(methods):
            cell = grid["cells"][model][method]
            if cell is None:
                ax.text(j, i, "not judged", ha="center", va="center", fontsize=7.5,
                        color="#666666", style="italic")
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
                        ha="center", va="center", fontsize=7, color="#555555",
                        style="italic", zorder=4)
                continue
            value = float(cell["value"])
            if cell["under_powered"]:
                ax.add_patch(Rectangle(
                    (j - 0.5, i - 0.5), 1, 1, fill=False, edgecolor=_UNDER_POWERED_EDGE,
                    hatch=_UNDER_POWERED_HATCH, alpha=_UNDER_POWERED_ALPHA,
                    linewidth=0.0, zorder=2,
                ))
            # Above the hatch, always: the hatch qualifies the number and must not be
            # allowed to strike through it.
            ax.text(
                j, i, f"{value:.3f}{_delta(value)}\nn={cell['denominator']}",
                ha="center", va="center", fontsize=7, zorder=4,
                color=text_color_on(im, value),
            )

    if real_value is not None:
        row = n_rows - 1
        ax.axhline(row - 0.5, color="white", linewidth=3.0)
        centre = (len(methods) - 1) / 2.0 if methods else 0.0
        if real["under_powered"]:
            # The reference is measured on the same terms as everyone else, and can be
            # too thin to read like anyone else. An unmarked band would present a shaky
            # midpoint as a firm one -- and this ramp is centred on it.
            ax.add_patch(Rectangle(
                (-0.5, row - 0.5), max(len(methods), 1), 1, fill=False,
                edgecolor=_UNDER_POWERED_EDGE, hatch=_UNDER_POWERED_HATCH,
                alpha=_UNDER_POWERED_ALPHA, linewidth=0.0, zorder=2,
            ))
        ax.text(
            centre, row, f"{float(real_value):.3f}   n={real['denominator']}",
            ha="center", va="center", fontsize=7.5, zorder=4,
            color=text_color_on(im, float(real_value)),
        )

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    # The label states the statistic's endpoints and its lack of a direction, both read
    # from the block: a colourbar that says only "IOV" leaves the reader to guess which
    # end is which, and this family's own implementations disagree about that.
    cbar.set_label(
        textwrap.fill(f"{block['statistic_label']} -- no better/worse direction", _LABEL_WRAP),
        fontsize=8,
    )
    cbar.ax.tick_params(labelsize=7)
    if has_reference:
        # The one place on this figure where the reference is visible rather than
        # arithmetic. Its colour is taken from the ramp position it marks, so the rule
        # stays visible whether it lands on the dark floor or the bright ceiling.
        cbar.ax.axhline(
            float(reference), color=text_color_on(im, float(reference)),
            linewidth=_REFERENCE_RULE_WIDTH,
        )

    ax.set_xlabel("Method (strategy)", fontsize=9)
    ax.set_ylabel("Model", fontsize=9)
    subtitle = (
        "sequential ramp; the rule on the colourbar is the real population"
        if has_reference else "sequential ramp -- no real population to measure against"
    )
    ax.set_title(
        f"Typicality -- {block['statistic']} by model x method\n"
        f"({subtitle}; grey = not judged, which is not a value of zero)",
        fontsize=12, fontweight="bold",
    )
    _place_footnote(fig, ax, _typicality_footnotes(
        block, reference_role="Colourbar rule", under_powered_mark="hatched", flat=flat,
        has_reference=has_reference, has_band=real_value is not None,
    ))
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
    the ramp midpoint of the sibling heatmap, drawn so each method's spread around it is
    visible. It carries the real population's own colour and slug so it cannot be read as
    a target or a threshold.

    Under-powered competitors are drawn hollow rather than dropped, and their intervals
    are drawn with everyone else's: a mark with no visible uncertainty on a bounded
    statistic invites being read as exact. Returns the ``Figure`` unsaved and open; raises
    ``ValueError`` when no competitor has a defined statistic.
    """
    import matplotlib
    matplotlib.use("Agg")
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

    fig, ax = plt.subplots(figsize=(max(7.5, len(methods) * 1.6 + 3.0), 6.0))
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
                        color=colour, linewidth=0.9, alpha=0.45, zorder=2)
            if cell["under_powered"]:
                any_under_powered = True
                ax.scatter(x, value, s=46, facecolors="none", edgecolors=colour,
                           linewidths=1.2, zorder=3)
            else:
                ax.scatter(x, value, s=46, color=colour, edgecolor="white",
                           linewidth=0.4, zorder=3)
            xs.append(x)
            ys.append(value)
            drawn += 1
        if drawn > 1:
            ax.plot(xs, ys, color=colour, linewidth=0.9, alpha=0.55, zorder=2)
        if drawn:
            handles.append(Line2D([], [], color=colour, marker="o", markersize=5,
                                  linewidth=0.9, markeredgecolor="white",
                                  markeredgewidth=0.4, label=model))

    reference = block["reference_value"]
    if reference is not None:
        ax.axhline(float(reference), color=_REAL_COLOR, linestyle="--",
                   linewidth=1.1, alpha=0.9, zorder=1)
        # Inline, at the left edge and lifted a few points clear of the line, following
        # the c2st reference-line idiom: a legend entry alone would leave the line
        # unlabelled where it is actually read, and a baseline sitting *on* the line lets
        # the dashes strike through the label.
        ax.annotate(
            f"{block['reference_slug']} = {float(reference):.3f}  (real population, "
            "not a target)",
            xy=(-0.55, float(reference)), xytext=(0, 3), textcoords="offset points",
            va="bottom", ha="left", fontsize=7.5, color=_REAL_COLOR,
        )
    if any_under_powered:
        handles.append(Line2D([], [], color="#555555", marker="o", markersize=6,
                              markerfacecolor="none", markeredgewidth=1.2, linestyle="none",
                              label=f"hollow = under-powered (n < {block['min_n']})"))

    ax.set_xticks(range(len(methods)))
    ax.set_xticklabels(methods, rotation=25, ha="right", fontsize=8)
    ax.set_xlim(-0.6, len(methods) - 0.4)
    ax.set_xlabel("Method (strategy) -- simplest first", fontsize=9)
    ax.set_ylabel(textwrap.fill(block["statistic_label"], _LABEL_WRAP), fontsize=8)
    ax.set_title(
        f"Typicality -- {block['statistic']} by method, one mark per model\n"
        "(no better/worse direction: the optimum is interior)",
        fontsize=12, fontweight="bold",
    )
    ax.tick_params(axis="y", labelsize=8)
    ax.grid(axis="y", linestyle=":", linewidth=0.5, alpha=0.6, zorder=0)
    ax.set_axisbelow(True)
    if handles:
        ax.legend(handles=handles, fontsize=7.5, loc="center left",
                  bbox_to_anchor=(1.01, 0.5), framealpha=0.92)

    excluded = block["excluded"]
    footnotes = _typicality_footnotes(
        block, reference_role="Reference line", under_powered_mark="hollow", flat=False,
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
