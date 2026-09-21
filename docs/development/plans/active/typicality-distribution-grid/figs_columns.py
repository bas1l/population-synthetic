"""Typicality score distribution per model as vertical stacked columns (house standard).

Same data and colouring as figs.py::fig_distribution; models are columns in the
model_ranking order, the real (SCB) population is a detached column at the right.
Laid out in absolute points on a fixed TEXT_WIDTH canvas and written with fixed_canvas=True.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from population_synthetic.analysis.model_ranking.hosting import classify_hosting, load_hosting_config
from population_synthetic.analysis.utils.figures import save_figure
from population_synthetic.analysis.utils.labels import PROJECT_ROOT, model_labels
from population_synthetic.analysis.utils.palette import (
    BASELINE_DARK, FOOTNOTE_GREY, HOST_COLORS, SURFACE, heatmap_levels, text_color_for_rgb,
)
from population_synthetic.analysis.utils.style import (
    ANNOTATION, AXES_LINEWIDTH, AXIS_TITLE, LEGEND_LABEL, MAX_HEIGHT, POINTS_PER_INCH, TEXT_WIDTH,
    TICK_LABEL, house_style,
)
from population_synthetic.analysis.utils.table_style import HOST_LABELS
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values

OUT = Path(__file__).resolve().parent
FIG = OUT / "figures"
meta = json.load(open(OUT / "meta.json"))
MODELS = meta["model_order"]
MLAB = model_labels(MODELS)
REAL = "real_swedish_02"
# labels.population_label(REAL) reads "Sweden 02 (config 006, guided prompt) real population",
# which neither fits a 26 pt column nor names the source; no label in labels.py names SCB.
REAL_TICK = "Real population (SCB)"
dist = pd.read_csv(OUT / "distribution_first_round_by_model.csv").set_index("unit")
assert list(dist.index) == MODELS + [REAL], list(dist.index)

HOSTING = classify_hosting(
    discover_axis_values("models"),
    load_hosting_config(PROJECT_ROOT / "config/analysis/model_ranking/provider_hosting.json"),
)

N_SCORES = 11
LABEL_MIN_SHARE = 0.06   # segments this tall carry their score digit (same rule as the row figure)
BAR_W = 0.72
MEDIAN_W = 0.98          # median rule is drawn behind the bar, so only its ends show
MEDIAN_LW = 1.2
SEP_LW = 0.6
# In the plot the median rule is hidden behind each bar, so it reads as short dashes (the rule's
# ends) separated by long gaps (the bars). The legend key reproduces that rhythm: a dash, a gap,
# a dash over a KEY_LEN-em handle. Dash lengths are in linewidth units (lines.scale_dashes).
KEY_LEN = 2.0                                     # handle length in font-size units (8 pt -> 16 pt)
_KEY_DASH_PT, _KEY_GAP_PT = 4.0, 8.0              # 4 + 8 + 4 = 16 pt = the handle length
MEDIAN_KEY_DASH = (0, (_KEY_DASH_PT / MEDIAN_LW, _KEY_GAP_PT / MEDIAN_LW))

# ---- canvas, in points
W_PT = TEXT_WIDTH * POINTS_PER_INCH   # 456
H_PT = 290.0
AX_L, AX_R = 38.0, 390.0
AX_B, AX_T = 66.0, 256.0
CB_L, CB_W = 402.0, 8.0


def _median_score(row) -> int:
    cum = np.cumsum([row[f"p{k}"] for k in range(N_SCORES)])
    return int(np.searchsorted(cum, 0.5))


@house_style
def fig_distribution_columns():
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt
    from matplotlib.cm import ScalarMappable
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    assert H_PT / POINTS_PER_INCH <= MAX_HEIGHT
    fig = plt.figure(figsize=(W_PT / POINTS_PER_INCH, H_PT / POINTS_PER_INCH))

    def frac(x0, y0, x1, y1):
        return [x0 / W_PT, y0 / H_PT, (x1 - x0) / W_PT, (y1 - y0) / H_PT]

    ax = fig.add_axes(frac(AX_L, AX_B, AX_R, AX_T))
    cax = fig.add_axes(frac(CB_L, AX_B, CB_L + CB_W, AX_T))
    levels = heatmap_levels(N_SCORES)

    units = MODELS + [REAL]
    xs = list(range(len(MODELS))) + [len(MODELS) + 0.6]
    for x, u in zip(xs, units):
        r = dist.loc[u]
        bottom = 0.0
        for k in range(N_SCORES):
            h = float(r[f"p{k}"])
            if h > 0:
                col = levels(k)
                ax.bar(x, h, bottom=bottom, width=BAR_W, color=col, edgecolor=SURFACE,
                       linewidth=0.4, zorder=2)
                if h >= LABEL_MIN_SHARE:
                    ax.text(x, bottom + h / 2, str(k), ha="center", va="center", fontsize=ANNOTATION,
                            color=text_color_for_rgb(col[:3]), zorder=3)
            bottom += h
        assert abs(bottom - 1.0) < 1e-9, (u, bottom)
        ax.text(x, 1.015, f"{int(r.n)}", ha="center", va="bottom", fontsize=ANNOTATION,
                color=FOOTNOTE_GREY)
        # the median is the score whose segment crosses 0.5; mark that height with a rule whose
        # ends stick out either side of the bar
        ax.plot([x - MEDIAN_W / 2, x + MEDIAN_W / 2], [0.5, 0.5], color=BASELINE_DARK,
                linewidth=MEDIAN_LW, solid_capstyle="butt", zorder=1)

    sep_x = (xs[-2] + xs[-1]) / 2
    ax.axvline(sep_x, color=BASELINE_DARK, linewidth=SEP_LW, zorder=1)

    ax.set_xlim(-0.6, xs[-1] + 0.6)
    ax.set_ylim(0, 1)
    ax.text(-0.02, 1.015, "n", ha="right", va="bottom", fontsize=ANNOTATION, color=FOOTNOTE_GREY,
            transform=ax.get_yaxis_transform())
    ax.set_yticks(np.arange(0, 1.01, 0.25))
    ax.tick_params(axis="y", labelsize=TICK_LABEL)
    ax.set_ylabel("Share of personas", fontsize=AXIS_TITLE)
    ax.set_xticks(xs)
    ax.set_xticklabels([MLAB[m] for m in MODELS] + [REAL_TICK], fontsize=TICK_LABEL, rotation=45,
                       ha="right", rotation_mode="anchor")
    for lab, u in zip(ax.get_xticklabels(), units):
        lab.set_color(HOST_COLORS[HOSTING[u]] if u in HOSTING else BASELINE_DARK)
    ax.tick_params(axis="x", length=0, pad=3)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)

    handles = [Patch(facecolor=HOST_COLORS[c], edgecolor="none", label=HOST_LABELS[c])
               for c in ("hosted", "local")]
    handles.append(Line2D([], [], color=BASELINE_DARK, linewidth=MEDIAN_LW, linestyle=MEDIAN_KEY_DASH,
                          dash_capstyle="butt", label="median (share 0.5)"))
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(AX_L / W_PT, 1 - 3 / H_PT),
               ncol=3, fontsize=LEGEND_LABEL, frameon=False, handlelength=KEY_LEN, handleheight=0.8,
               columnspacing=1.2, borderaxespad=0, borderpad=0)

    sm = ScalarMappable(cmap=levels, norm=mcolors.BoundaryNorm(np.arange(-0.5, N_SCORES), N_SCORES))
    cbar = fig.colorbar(sm, cax=cax, ticks=range(N_SCORES))
    cbar.set_label("Typicality score\n(0 = rarest possible, 10 = ordinary)", fontsize=AXIS_TITLE)
    cbar.ax.tick_params(labelsize=TICK_LABEL)
    cbar.outline.set_linewidth(AXES_LINEWIDTH)

    save_figure(fig, FIG / "typicality_distribution_by_model_columns.png", fixed_canvas=True)


if __name__ == "__main__":
    for u in MODELS + [REAL]:
        print(u, _median_score(dist.loc[u]))
    fig_distribution_columns()
    print("ok")
