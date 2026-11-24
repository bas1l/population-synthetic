"""Figure 6: percentage of generated individuals surviving the validity gates.

Transposed remake of validation_attrition/<country>_mapped_validity_grid, laid out to the
docx artwork (poc_F05_mapping_survival_transposed_456pt_remake): strategies A-E down the
rows, models across the columns in model_ranking's published order, the gate-withdrawn
model appended last, cells = retention_rate from the attrition CSV, withdrawn combinations
hatched. 456 x 183.97 pt.

2026-10-20: validation_attrition now defines retention_rate = clean / raw_valid (raw_valid =
the finished individuals; generations stopped midway are ignored). The builder still reads the
CSV column and computes nothing; load() checks that the column is clean / raw_valid, and the
colourbar label names the denominator.
"""
from __future__ import annotations
import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.patches import Patch, Rectangle

import figs_common as common

from population_synthetic.analysis.utils.axes import strategy_complexity_order
from population_synthetic.analysis.utils.grid_annotations import RateOnlyPolicy
from population_synthetic.analysis.utils.grids import render_grid
from population_synthetic.analysis.utils.labels import method_letters
from population_synthetic.analysis.utils.palette import BASELINE_DARK, HOST_COLORS, SURFACE, heatmap_cmap
from population_synthetic.analysis.utils.style import (
    ANNOTATION_LARGE, AXIS_TITLE, HEADING_WEIGHT, LEGEND_LABEL, TICK_LABEL, TICK_LABEL_LARGE,
)

W, H = 456.0, 183.968
# Geometry measured on the docx artwork (points, origin top-left).
GRID_X0, GRID_X1 = 27.5, 388.3
GRID_Y0, GRID_Y1 = 71.8, 180.0          # from the top
CBAR_X0, CBAR_X1 = 400.0, 410.0
LEG_SWATCH_X, LEG_TEXT_X = 384.5, 403.5
LEG_ROWS = (18.75, 30.0, 43.5)
HATCH = "////"
CBAR_LABEL = "% of finished individuals" + chr(10) + "surviving validity gates"
HOSTING_PATH = common.Path(os.environ["POPSYNTH_REPO"]) / "config" / "analysis" / "model_ranking" / "provider_hosting.json"


def load():
    d = pd.read_csv(common.adir("validation_attrition") / f"{common.COUNTRY}_attrition.csv")
    if not np.allclose(d["retention_rate"], d["clean"] / d["raw_valid"], rtol=0, atol=1e-12):
        raise ValueError("retention_rate is not clean / raw_valid; the colourbar label would be wrong")
    if len(d) != d[["model", "strategy"]].drop_duplicates().shape[0]:
        raise ValueError("duplicate model x strategy rows in the attrition CSV")
    ranked = common.ranked_models()
    extra = sorted(set(d.model) - set(ranked))
    for m in extra:  # a model the ranking does not hold must be withdrawn everywhere
        if not d.loc[d.model == m, "excluded"].all():
            raise ValueError(f"{m} is not ranked but has a non-withdrawn combination")
    models = ranked + extra
    strategies = strategy_complexity_order(sorted(d.strategy.unique()))
    return d, models, strategies


def build(fig=None, *, origin=(0.0, 0.0), canvas=(W, H), col_groups=None):
    d, models, strategies = load()
    cw, ch = canvas
    ox, oy = origin

    def box(x0, y0_top, x1, y1_top):  # points (top-left origin) -> figure fraction rect
        return ((ox + x0) / cw, 1 - (oy + y1_top) / ch, (x1 - x0) / cw, (y1_top - y0_top) / ch)

    rate = d.pivot(index="strategy", columns="model", values="retention_rate").loc[strategies, models]
    excl = d.pivot(index="strategy", columns="model", values="excluded").loc[strategies, models].astype(bool)
    if rate.isna().any().any():
        raise ValueError("a model x strategy cell has no retention rate")
    matrix = rate.to_numpy(dtype=float)
    cells = [[{"rate": float(matrix[i, j])} for j in range(len(models))] for i in range(len(strategies))]
    names = common.display_models(models)
    hosting = common.hosting_classes()
    letters = method_letters(strategies)

    cmap = heatmap_cmap()
    norm = Normalize(0.0, 1.0)
    # 2026-10-20 composite: with ``col_groups`` = [(x_left, x_right, [column indices]), ...] (points) the
    # grid is drawn as one render_grid per group, so its columns can sit exactly over another panel's
    # columns; the gap between groups sets the all-withdrawn model apart instead of the black rule.
    # Without it, the published single-panel geometry (GRID_X0..GRID_X1, black rule) is drawn unchanged.
    groups = col_groups or [(GRID_X0, GRID_X1, list(range(len(models))))]
    if sorted(j for *_, js in groups for j in js) != list(range(len(models))):
        raise ValueError("col_groups must cover every model column exactly once")
    im = None
    for g_i, (gx0, gx1, js) in enumerate(groups):
        ax = fig.add_axes(box(gx0, GRID_Y0, gx1, GRID_Y1))
        sub = matrix[:, js]
        im = render_grid(
            ax, sub, [[cells[i][j] for j in js] for i in range(len(strategies))],
            policy=RateOnlyPolicy(value_key="rate", scale=100.0, number_format=".1f"),
            cmap=cmap, norm=norm, aspect="auto", fontsize=ANNOTATION_LARGE, zorder=5,
            bold_cells=[(i, k) for i in range(len(strategies)) for k in range(len(js))],
        )
        for i in range(len(strategies)):
            for k, j in enumerate(js):
                if excl.iat[i, j]:
                    ax.add_patch(Rectangle((k - 0.5, i - 0.5), 1, 1, facecolor="none", edgecolor=SURFACE,
                                           hatch=HATCH, linewidth=0, zorder=3))
        if col_groups is None:
            # A model withdrawn in every strategy is set apart by a rule, as in the docx artwork.
            for k, j in enumerate(js):
                if excl[models[j]].all():
                    ax.axvline(k - 0.5, color=BASELINE_DARK, linewidth=1.6, zorder=6)
        ax.set_xticks(range(len(js)))
        ax.set_xticklabels([names[models[j]] for j in js], rotation=90, fontsize=TICK_LABEL)
        ax.xaxis.tick_top()
        for tick, j in zip(ax.xaxis.get_major_ticks(), js):
            tick.label2.set_color(HOST_COLORS[hosting[models[j]]])
        ax.tick_params(axis="x", length=2.5, pad=1.5)
        if g_i == 0:
            ax.set_yticks(range(len(strategies)))
            ax.set_yticklabels([letters[s] for s in strategies], fontsize=TICK_LABEL_LARGE,
                               fontweight=HEADING_WEIGHT)
            ax.tick_params(axis="y", length=2.5, pad=1.5)
            if col_groups is None:  # composite: no room left of the aligned grid; panel B has no axis title either
                ax.set_ylabel("strategy", fontsize=AXIS_TITLE, labelpad=2)
        else:
            ax.set_yticks([])

    cax = fig.add_axes(box(CBAR_X0, GRID_Y0, CBAR_X1, GRID_Y1))
    cb = fig.colorbar(im, cax=cax, ticks=np.linspace(0, 1, 6))
    cb.ax.set_yticklabels([f"{int(t * 100)}%" for t in np.linspace(0, 1, 6)], fontsize=TICK_LABEL)
    cb.ax.tick_params(length=2.5, pad=1.5)
    cb.set_label(CBAR_LABEL, fontsize=TICK_LABEL_LARGE, labelpad=3,
                 linespacing=0.95)

    handles = [
        Patch(facecolor=HOST_COLORS["hosted"], label="hosted (API)"),
        Patch(facecolor=HOST_COLORS["local"], label="locally served"),
        Patch(facecolor=SURFACE, edgecolor=BASELINE_DARK, hatch="///", linewidth=0.6,
              label="withdrawn\ncombination"),
    ]
    fig.legend(handles=handles, loc="upper left", frameon=False, fontsize=LEGEND_LABEL,
               bbox_to_anchor=((ox + LEG_SWATCH_X - 1) / cw, 1 - (oy + 10.5) / ch),
               handlelength=1.6, handleheight=0.9, handletextpad=0.6, labelspacing=0.25,
               borderaxespad=0, borderpad=0)
    fig._fig6_models = models  # read by the composite builder to check the column order
    return fig


def main():
    with plt.rc_context(common.rc()):
        fig = plt.figure(figsize=(W / 72, H / 72))
        build(fig)
        out = common.save(fig, "fig6")
    print("\n".join(map(str, out)))


if __name__ == "__main__":
    main()
