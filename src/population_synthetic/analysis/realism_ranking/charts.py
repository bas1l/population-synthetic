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

__all__ = [
    "plot_headline_map",
    "plot_impossibility_forest",
    "plot_impossibility_heatmap",
    "plot_severity_heatmap",
    "plot_severity_pair_summary",
]

_COMPETITOR_COLOR = "#4878CF"
_REAL_COLOR = "#C44E52"
_CI_COLOR = "#8C8C8C"

# Sequential ramp for a quantity where MORE IS WORSE (the impossibility rate, and the
# S3/S2 clash prevalences). Sequential, not diverging: these quantities have a true
# zero and no meaningful midpoint, so a diverging map would invent one and split the
# combinations into "good" and "bad" sides at an arbitrary value. Red carries the
# defect reading intentionally -- pale means few, dark means many, and many is bad.
_DEFECT_CMAP = "Reds"

# Sequential ramp for a quantity that is REPORTED BUT NOT PENALISED -- the S1
# (unusual-but-possible) prevalence. It still encodes magnitude, but in a hue that
# carries no defect connotation, because a high S1 rate plausibly means healthy reach
# into the tails. Rendering S1 on the red ramp would silently assert that unusual
# people are defects, which the judge's own contract explicitly denies.
_NEUTRAL_CMAP = "Blues"

# Fill for a model x method pair that was never judged. Deliberately outside both ramps
# so it can never be mistaken for their pale (few / none) end.
_MISSING_COLOR = "#DDDDDD"

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
    cmap_name: str,
    caption: str,
    error_context: str,
):
    """Render one ``{models, methods, cells, real}`` grid as a heatmap.

    The single implementation behind every heatmap this task emits, so the layout and
    the guards below cannot diverge between them. Computes nothing: each cell payload
    already carries its ``rate`` and ``denominator``.

    Three rendering decisions carry meaning:

    * **The ramp is sequential and anchored at a true zero.** ``vmin=0`` because zero is
      a real floor, not the bottom of the observed range, so a pale cell always means
      "few", never "fewest in this particular sweep". A diverging map would be wrong:
      the quantity has no meaningful midpoint, so a diverging map would invent one and
      sort combinations into good and bad halves at an arbitrary value.
    * **An unjudged cell is grey and labelled ``n/a``**, drawn outside the ramp entirely.
      Rendering it at the pale end would show a combination that was never judged as the
      cleanest in the sweep -- the single most damaging misreading these figures could
      produce.
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
    cmap = plt.get_cmap(cmap_name).copy()
    cmap.set_bad(color=_MISSING_COLOR)
    im = ax.imshow(np.ma.masked_invalid(plotted), aspect="auto", cmap=cmap, vmin=0.0, vmax=vmax)

    row_labels = list(models)
    if real_rate is not None:
        row_labels.append(f"{real['slug']}  (real population)")
    ax.set_xticks(range(max(len(methods), 1)))
    ax.set_xticklabels(methods or [""], rotation=30, ha="right", fontsize=8)
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(row_labels, fontsize=8)

    # Annotate each cell with its value and denominator; grey cells say so explicitly.
    threshold = vmax * 0.6   # dark fill -> white text
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
                color="white" if value > threshold else "black",
            )

    if real_rate is not None:
        row = n_rows - 1
        # A thick white rule + the band's own label: this row is not a model.
        ax.axhline(row - 0.5, color="white", linewidth=3.0)
        centre = (len(methods) - 1) / 2.0 if methods else 0.0
        ax.text(
            centre, row, f"{float(real_rate):.3f}   n={real['denominator']}",
            ha="center", va="center", fontsize=7.5,
            color="white" if float(real_rate) > threshold else "black",
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
        cmap_name=_DEFECT_CMAP,
        caption="",
        error_context="plot_impossibility_heatmap",
    )


def plot_severity_heatmap(ranking: dict[str, Any], severity: str):
    """Render one severity level's clash prevalence as a model x method grid.

    *severity* is one of ``S3`` / ``S2`` / ``S1``. The value shown is the share of a
    combination's personas exhibiting at least one clash at that level; the three levels
    are counted independently, so a persona carrying both an S3 and an S2 appears on
    both figures.

    **The three levels are not rendered alike, and that is deliberate.** S3 and S2 are
    defects and get the lower-is-better ramp. S1 is *unusual but possible* -- the judge's
    own contract reports it and never penalises it, and a high S1 rate plausibly means
    healthy reach into the tails rather than a problem. Putting it on a lower-is-better
    ramp would silently assert that unusual people are defects, so it gets a neutral
    ramp and a caption saying so. The distinction is drawn in the figure, not only in
    this docstring, because the figure travels without the code.

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
        cmap_name=_DEFECT_CMAP if penalised else _NEUTRAL_CMAP,
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
