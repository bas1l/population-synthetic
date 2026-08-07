"""charts.py -- pure rendering of the realism ranking into matplotlib figures.

Three figures:

* :func:`plot_headline_map` -- the coherence x coverage map. x = impossibility rate
  (Axis A), y = typicality-dispersion distance to the real population (Axis B).
* :func:`plot_impossibility_forest` -- every competitor's impossibility rate with its
  bootstrap CI, in rank order.
* :func:`plot_impossibility_heatmap` -- Axis A reshaped as a model x method grid, with
  the real population as a separate band beneath it.

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

from typing import Any

__all__ = ["plot_headline_map", "plot_impossibility_forest", "plot_impossibility_heatmap"]

_COMPETITOR_COLOR = "#4878CF"
_REAL_COLOR = "#C44E52"
_CI_COLOR = "#8C8C8C"

# Sequential ramp for the impossibility heatmap. Sequential, not diverging: the
# quantity has a true zero (no impossible persona) and no meaningful midpoint, so a
# diverging map would invent one and split the combinations into "good" and "bad"
# sides at an arbitrary rate. Pale = few impossible personas = good.
_HEATMAP_CMAP = "Reds"

# Fill for a model x method pair that was never judged. Deliberately outside the ramp
# so it can never be mistaken for its pale (good) end.
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


def plot_impossibility_heatmap(ranking: dict[str, Any]):
    """Render Axis A as a model x method grid, with the real population as its own band.

    The forest plot answers "who is most coherent"; this one answers "does incoherence
    track the model, the method, or neither" -- the same question the Kruskal-Wallis
    tests answer numerically, in a form that shows the pattern rather than a p-value.
    Every number arrives pre-computed in ``axis_a.grid``; nothing is calculated here.

    Three rendering decisions carry meaning:

    * **The ramp is sequential and anchored at a true zero.** ``vmin=0`` because zero
      impossible personas is a real floor, not the bottom of the observed range, so a
      pale cell always means "few", never "fewest in this particular sweep". A diverging
      map is wrong here: it would invent a midpoint and sort combinations into good and
      bad halves at an arbitrary rate.
    * **An unjudged cell is grey and labelled ``n/a``**, drawn outside the ramp entirely.
      Rendering it at the pale end would show a combination that was never judged as the
      most coherent in the sweep -- the single most damaging misreading this figure could
      produce.
    * **The real population is a separated band, not a grid row.** It has no model and no
      method; giving it a row would present it as a factor level, which is exactly what
      the ranking's factor tests hold it out of being. A white rule and a gap keep it
      visually apart, and its rate spans the full width because it is not decomposed by
      method.

    Returns the ``Figure`` unsaved and open. Raises ``ValueError`` when the grid has no
    cell with a defined rate (nothing to shade), matching the sibling charts.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    grid = ranking["axis_a"]["grid"]
    models: list[str] = list(grid["models"])
    methods: list[str] = list(grid["methods"])
    real = grid.get("real")

    values = np.full((len(models), len(methods)), np.nan)
    for i, model in enumerate(models):
        for j, method in enumerate(methods):
            cell = grid["cells"].get(model, {}).get(method)
            if cell is not None and cell["rate"] is not None:
                values[i, j] = float(cell["rate"])

    real_rate = None if real is None else real.get("rate")
    if not np.any(np.isfinite(values)) and real_rate is None:
        raise ValueError(
            "plot_impossibility_heatmap requires at least one competitor with a defined rate"
        )

    # The real band is appended as an extra row so it shares the colour scale -- the
    # point of putting it on this figure at all is that its rate is comparable with the
    # grid's. The separating rule below keeps it from reading as another model.
    n_rows = len(models) + (1 if real_rate is not None else 0)
    plotted = np.full((n_rows, max(len(methods), 1)), np.nan)
    plotted[:len(models), :len(methods)] = values
    if real_rate is not None:
        plotted[-1, :] = float(real_rate)

    finite = plotted[np.isfinite(plotted)]
    vmax = float(finite.max()) if finite.size else 1.0
    if vmax <= 0.0:
        vmax = 1.0   # every rate is 0: keep a valid range instead of a degenerate one

    fig, ax = plt.subplots(
        figsize=(max(7.0, len(methods) * 1.5 + 3.5), max(3.2, n_rows * 0.55 + 2.2))
    )
    cmap = plt.get_cmap(_HEATMAP_CMAP).copy()
    cmap.set_bad(color=_MISSING_COLOR)
    im = ax.imshow(np.ma.masked_invalid(plotted), aspect="auto", cmap=cmap, vmin=0.0, vmax=vmax)

    row_labels = list(models)
    if real_rate is not None:
        row_labels.append(f"{real['slug']}  (real population)")
    ax.set_xticks(range(max(len(methods), 1)))
    ax.set_xticklabels(methods or [""], rotation=30, ha="right", fontsize=8)
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(row_labels, fontsize=8)

    # Annotate each cell with its rate and denominator; grey cells say so explicitly.
    threshold = vmax * 0.6   # dark fill -> white text
    for i, model in enumerate(models):
        for j, method in enumerate(methods):
            cell = grid["cells"].get(model, {}).get(method)
            if cell is None or cell["rate"] is None:
                ax.text(j, i, "n/a", ha="center", va="center", fontsize=7.5,
                        color="#666666", style="italic")
                continue
            value = float(cell["rate"])
            ax.text(
                j, i, f"{value:.3f}\nn={cell['denominator']}",
                ha="center", va="center", fontsize=7,
                color="white" if value > threshold else "black",
            )

    caption = ""
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
        caption = (
            "The real population spans the full width because it has no method: it is not a "
            "model x method cell, and the factor tests hold it out."
        )

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("Impossibility rate -- lower is better", fontsize=8)
    cbar.ax.tick_params(labelsize=7)

    ax.set_xlabel("Method (strategy)", fontsize=9)
    ax.set_ylabel("Model", fontsize=9)
    ax.set_title(
        "Axis A -- impossibility rate by model x method\n"
        "(grey = not judged, which is not a rate of zero)",
        fontsize=12, fontweight="bold",
    )
    if caption:
        # Reserve a strip first, then place the caption inside it: an artist dropped
        # below the axes without reserved space collides with the rotated tick labels.
        fig.tight_layout(rect=(0.0, 0.07, 1.0, 1.0))
        fig.text(0.5, 0.02, caption, ha="center", va="bottom", fontsize=7, color="#555555")
    else:
        fig.tight_layout()
    return fig
