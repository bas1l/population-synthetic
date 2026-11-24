"""P17 / P18: a per-method ternary column appended after the SCB column.

P17 = P02 (mini-histogram glyph grid) + ternary column.
P18 = P04 (Wasserstein-1 heatmap) + ternary column -- the alternative reading of "#4".
Ternary bins as in P11: 0-4 / 5-7 / 8-10. Points are host-tinted, SCB is a star; no per-point
model label (a 2.2 pt marker cannot carry one legibly).

Run: python p17.py [P17 P18]
"""
from __future__ import annotations

import sys

import matplotlib.colors as mcolors
import numpy as np
from matplotlib.lines import Line2D

from common import (
    CELL, GRID_X0, HOSTING, KEY_H, LABEL_DROP, LEGEND_H, METHODS, MODELS, N_SCORES, REF, Canvas,
    legend_row, method_key, model_tick_labels, row_letters,
)
from protos import NOTE_ABOVE, THIN, WD_HANDLE, _cells, bare, save_figure, score_colorbar, withdrawn_cell
from population_synthetic.analysis.utils.grid_annotations import RateOnlyPolicy
from population_synthetic.analysis.utils.grids import render_grid
from population_synthetic.analysis.utils.palette import (
    BASELINE_DARK, FOOTNOTE_GREY, GRID_RULE, HOST_COLORS, SURFACE, heatmap_cmap, heatmap_levels,
)
from population_synthetic.analysis.utils.style import (
    AXES_LINEWIDTH, GRID_LINEWIDTH, LEGEND_LABEL, TICK_LABEL, house_style,
)

HERE_OUT = __import__("common").HERE
FINAL = "--final" in sys.argv          # P20 only: write PNG + SVG + EPS to final/
FINAL_STEM = "typicality_distribution_by_model_strategy"
SQ3 = np.sqrt(3) / 2
V = np.array([[0.0, 0.0], [1.0, 0.0], [0.5, SQ3]])   # 0-4 bottom-left, 5-7 bottom-right, 8-10 apex
POINT_PT = 2.2       # marker diameter of a combination point
STAR_PT = 5.0        # marker diameter of the SCB star
TRI_PAD = 1.5        # vertical padding inside the row for the triangle


def ternary(cv, x0, y0, side, method, *, label_apex=False, label_base=False, base_centred=False):
    """One small ternary triangle with its lower-left corner at (x0, y0) pt, side `side` pt."""
    ax = cv.axes(x0, y0, x0 + side, y0 + side * SQ3)
    tri = np.vstack([V, V[:1]])
    ax.plot(tri[:, 0], tri[:, 1], color=BASELINE_DARK, linewidth=AXES_LINEWIDTH * 0.75, clip_on=False)
    for t in (0.5,):   # the half-mass line of the 8-10 band
        a, b = V[0] + t * (V[2] - V[0]), V[1] + t * (V[2] - V[1])
        ax.plot([a[0], b[0]], [a[1], b[1]], color=GRID_RULE, linewidth=GRID_LINEWIDTH, zorder=0)
    for mod in MODELS:
        s = CELL[method][mod]
        if s is None:
            continue
        p = np.array([s["le4"], s["mid"], s["high"]]) @ V
        ax.plot(*p, marker="o", ms=POINT_PT, color=HOST_COLORS[HOSTING[mod]], mec=SURFACE, mew=0.25,
                ls="none", zorder=3, clip_on=False)
    p = np.array([REF["le4"], REF["mid"], REF["high"]]) @ V
    ax.plot(*p, marker="*", ms=STAR_PT, color=BASELINE_DARK, mec=SURFACE, mew=0.25, ls="none", zorder=4)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, SQ3)
    ax.axis("off")
    if label_apex:
        cv.text(x0 + side / 2, y0 + side * SQ3 + 1.0, "8–10", ha="center", va="bottom", fontsize=TICK_LABEL,
                color=FOOTNOTE_GREY)
    if label_base and base_centred:   # centred on the corners: more air between the two labels
        cv.text(x0, y0 - 2, "0–4", ha="center", va="top", fontsize=TICK_LABEL, color=FOOTNOTE_GREY)
        cv.text(x0 + side, y0 - 2, "5–7", ha="center", va="top", fontsize=TICK_LABEL, color=FOOTNOTE_GREY)
    elif label_base:
        cv.text(x0 - 1, y0 - 2, "0–4", ha="left", va="top", fontsize=TICK_LABEL, color=FOOTNOTE_GREY)
        cv.text(x0 + side + 1, y0 - 2, "5–7", ha="right", va="top", fontsize=TICK_LABEL, color=FOOTNOTE_GREY)


def tri_handles():
    return [Line2D([], [], marker="o", ms=POINT_PT + 1, ls="none", color=BASELINE_DARK, mec=SURFACE,
                   label="combination"),
            Line2D([], [], marker="*", ms=STAR_PT + 1, ls="none", color=BASELINE_DARK, label="SCB")]


# ---------------------------------------------------------------- shared geometry
class Layout:
    def __init__(self, cell_w, cell_h, col_gap, row_gap, tri_gap=7.0, ref_gap=8.0, cbar_gap=8.0):
        self.cw, self.ch, self.cg, self.rg = cell_w, cell_h, col_gap, row_gap
        self.y0 = KEY_H + LABEL_DROP
        self.y1 = self.y0 + 5 * cell_h + 4 * row_gap
        self.h = self.y1 + LEGEND_H + 18     # legend row + a second legend line + the apex label
        self.xs0 = [GRID_X0 + j * (cell_w + col_gap) for j in range(12)]
        self.x1 = self.xs0[-1] + cell_w
        self.ref_x0 = self.x1 + ref_gap
        self.ref_x1 = self.ref_x0 + cell_w
        self.side = (cell_h - 2 * TRI_PAD) / SQ3
        self.tri_x0 = self.ref_x1 + tri_gap
        self.tri_x1 = self.tri_x0 + self.side
        self.cbar_x0 = self.tri_x1 + cbar_gap

    def row(self, i):
        top = self.y1 - i * (self.ch + self.rg)
        return top - self.ch, top

    def tri_column(self, cv, base_centred=False):
        for i, m in enumerate(METHODS):
            b, _ = self.row(i)
            ternary(cv, self.tri_x0, b + TRI_PAD, self.side, m, label_apex=(i == 0), label_base=(i == 4),
                    base_centred=base_centred)

    def labels(self, cv):
        model_tick_labels(cv, [x + self.cw / 2 + 3 for x in self.xs0], self.y0 - 4,
                          ref_x=(self.ref_x0 + self.ref_x1) / 2 + 3)
        row_letters(cv, [sum(self.row(i)) / 2 for i in range(5)])
        method_key(cv, KEY_H - 2)


def second_legend_line(cv, lay, extra=""):
    cv.text(4, cv.h - 16, f"Triangles: share of personas in score bands 0–4 / 5–7 / 8–10 (corners)"
            f"{extra}", ha="left", va="top", fontsize=LEGEND_LABEL, color=FOOTNOTE_GREY)


# ---------------------------------------------------------------- P17
@house_style
def P17():
    lay = Layout(cell_w=23.0, cell_h=32.0, col_gap=2.0, row_gap=3.0)
    cv = Canvas(lay.h)
    lev = heatmap_levels(N_SCORES)
    rx = np.arange(N_SCORES + 1) - 0.5
    ry = np.r_[REF["pmf"], REF["pmf"][-1]]

    def hist(ax, pmf, outline=True):
        ax.bar(np.arange(N_SCORES), pmf, width=1.0, color=[lev(k) for k in range(N_SCORES)], edgecolor="none")
        if outline:
            ax.step(rx, ry, where="post", color=BASELINE_DARK, linewidth=0.7, zorder=3)
        ax.set_yscale("function", functions=(np.sqrt, np.square))
        ax.set_xlim(-0.6, 10.6)
        ax.set_ylim(0, 1)
        bare(ax)

    for i, m in enumerate(METHODS):
        b, t = lay.row(i)
        for j, mod in enumerate(MODELS):
            ax = cv.axes(lay.xs0[j], b, lay.xs0[j] + lay.cw, t)
            s = CELL[m][mod]
            if s is None:
                withdrawn_cell(ax)
                continue
            hist(ax, s["pmf"])
        hist(cv.axes(lay.ref_x0, b, lay.ref_x1, t), REF["pmf"], outline=False)
    lay.tri_column(cv)
    score_colorbar(cv, lay.cbar_x0, lay.y0, lay.y1, label="Typicality score (bar colour)")
    legend_row(cv, [Line2D([], [], color=BASELINE_DARK, lw=0.7, label="SCB outline"), WD_HANDLE,
                    *tri_handles()], x=4, withdrawn=False)
    second_legend_line(cv, lay, "; bar heights √-scaled")
    lay.labels(cv)
    save_figure(cv.fig, HERE_OUT / "P17_histogram_grid_with_ternary.png", fixed_canvas=True)
    return lay.h, lay.side


# ---------------------------------------------------------------- P18
@house_style
def P18():
    lay = Layout(cell_w=23.0, cell_h=30.0, col_gap=0.0, row_gap=0.0)
    cv = Canvas(lay.h)
    cmap = heatmap_cmap()
    norm = mcolors.Normalize(0, 5.5)
    pol = RateOnlyPolicy(value_key="value", scale=1.0, number_format=".1f", absent_text="–")
    ax = cv.axes(GRID_X0, lay.y0, lay.x1, lay.y1)
    im = render_grid(ax, np.array([[np.nan if CELL[m][x] is None else CELL[m][x]["w1"] for x in MODELS]
                                   for m in METHODS]), _cells("w1"), policy=pol, cmap=cmap, norm=norm, aspect="auto")
    rax = cv.axes(lay.ref_x0, lay.y0, lay.ref_x1, lay.y1)
    render_grid(rax, np.zeros((1, 1)), [[{"value": 0.0}]], policy=pol, cmap=cmap, norm=norm, aspect="auto")
    for a in (ax, rax):
        a.set_xticks([])
        a.set_yticks([])
        for sp in a.spines.values():
            sp.set_visible(False)
    lay.tri_column(cv)
    cax = cv.axes(lay.cbar_x0, lay.y0, lay.cbar_x0 + 7, lay.y1)
    cb = cv.fig.colorbar(im, cax=cax, ticks=[0, 1, 2, 3, 4, 5])
    cb.ax.tick_params(labelsize=TICK_LABEL, length=2, pad=1.5)
    cb.outline.set_linewidth(AXES_LINEWIDTH)
    cb.set_label("Wasserstein-1 to SCB (score points)", fontsize=TICK_LABEL, labelpad=2)
    legend_row(cv, tri_handles(), x=4)
    second_legend_line(cv, lay, "; every cell lies above SCB")
    lay.labels(cv)
    save_figure(cv.fig, HERE_OUT / "P18_wasserstein_heatmap_with_ternary.png", fixed_canvas=True)
    return lay.h, lay.side


# ---------------------------------------------------------------- P19 = P17 with square cells
P19_CELL = 26.5      # square grid + SCB cells, pt (the widest that fits 456 pt with the triangle column)


@house_style
def P19():
    c = P19_CELL
    lay = Layout(cell_w=c, cell_h=c, col_gap=1.5, row_gap=3.0, tri_gap=5.0, ref_gap=6.0, cbar_gap=6.0)
    cv = Canvas(lay.h)
    lev = heatmap_levels(N_SCORES)
    rx = np.arange(N_SCORES + 1) - 0.5
    ry = np.r_[REF["pmf"], REF["pmf"][-1]]

    def hist(ax, pmf, outline=True):
        ax.bar(np.arange(N_SCORES), pmf, width=1.0, color=[lev(k) for k in range(N_SCORES)], edgecolor="none")
        if outline:
            ax.step(rx, ry, where="post", color=BASELINE_DARK, linewidth=0.7, zorder=3)
        ax.set_yscale("function", functions=(np.sqrt, np.square))
        ax.set_xlim(-0.6, 10.6)
        ax.set_ylim(0, 1)
        bare(ax)

    for i, m in enumerate(METHODS):
        b, t = lay.row(i)
        assert abs((t - b) - c) < 1e-9
        for j, mod in enumerate(MODELS):
            ax = cv.axes(lay.xs0[j], b, lay.xs0[j] + lay.cw, t)
            s = CELL[m][mod]
            if s is None:
                withdrawn_cell(ax)
                continue
            hist(ax, s["pmf"])
        hist(cv.axes(lay.ref_x0, b, lay.ref_x1, t), REF["pmf"], outline=False)
    lay.tri_column(cv, base_centred=True)
    # colourbar title on top instead of a rotated side label: reclaims ~12 pt of width for the cells
    cb = score_colorbar(cv, lay.cbar_x0, lay.y0, lay.y1, label="")
    cv.text(lay.cbar_x0 + 3.5, lay.y1 + 2, "Score", ha="left", va="bottom", fontsize=TICK_LABEL,
            color=BASELINE_DARK)
    legend_row(cv, [Line2D([], [], color=BASELINE_DARK, lw=0.7, label="SCB outline"), WD_HANDLE,
                    *tri_handles()], x=4, withdrawn=False)
    second_legend_line(cv, lay, "; bar heights √-scaled")
    lay.labels(cv)
    save_figure(cv.fig, HERE_OUT / "P19_square_histogram_grid_with_ternary.png", fixed_canvas=True)
    return lay.h, lay.side


# ---------------------------------------------------------------- P20 = P19 with vertical model labels on top
P20_TOP = 76.0          # vertical labels above the grid (longest label, "Mistral Medium 3.5", ~68 pt at 8 pt)
P20_BOTTOM = 60.0       # method key (2 lines) + triangle caption + legend row + base corner labels
P20_LABEL_GAP = 2.0     # label baseline sits this far above the top row


class TopLabelLayout(Layout):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        grid_h = self.y1 - self.y0
        self.y0 = P20_BOTTOM
        self.y1 = self.y0 + grid_h
        self.h = self.y1 + P20_TOP


@house_style
def P20():
    from common import MLAB, REF_TICK
    c = P19_CELL
    lay = TopLabelLayout(cell_w=c, cell_h=c, col_gap=1.5, row_gap=3.0, tri_gap=5.0, ref_gap=6.0, cbar_gap=6.0)
    cv = Canvas(lay.h)
    lev = heatmap_levels(N_SCORES)
    rx = np.arange(N_SCORES + 1) - 0.5
    ry = np.r_[REF["pmf"], REF["pmf"][-1]]

    def hist(ax, pmf, outline=True):
        ax.bar(np.arange(N_SCORES), pmf, width=1.0, color=[lev(k) for k in range(N_SCORES)], edgecolor="none")
        if outline:
            ax.step(rx, ry, where="post", color=BASELINE_DARK, linewidth=0.7, zorder=3)
        ax.set_yscale("function", functions=(np.sqrt, np.square))
        ax.set_xlim(-0.6, 10.6)
        ax.set_ylim(0, 1)
        bare(ax)

    for i, m in enumerate(METHODS):
        b, t = lay.row(i)
        for j, mod in enumerate(MODELS):
            ax = cv.axes(lay.xs0[j], b, lay.xs0[j] + lay.cw, t)
            s = CELL[m][mod]
            if s is None:
                withdrawn_cell(ax)
                continue
            hist(ax, s["pmf"])
        hist(cv.axes(lay.ref_x0, b, lay.ref_x1, t), REF["pmf"], outline=False)
    lay.tri_column(cv, base_centred=True)
    score_colorbar(cv, lay.cbar_x0, lay.y0, lay.y1, label="")
    cv.text(lay.cbar_x0 + 3.5, lay.y1 + 2, "Score", ha="left", va="bottom", fontsize=TICK_LABEL,
            color=BASELINE_DARK)
    # model labels on top: exactly vertical, reading bottom-to-top, centred on the column, host-tinted
    for x, mod in zip(lay.xs0, MODELS):
        cv.text(x + c / 2, lay.y1 + P20_LABEL_GAP, MLAB[mod], rotation=90, ha="center", va="bottom",
                fontsize=TICK_LABEL, color=HOST_COLORS[HOSTING[mod]])
    cv.text((lay.ref_x0 + lay.ref_x1) / 2, lay.y1 + P20_LABEL_GAP, REF_TICK, rotation=90, ha="center",
            va="bottom", fontsize=TICK_LABEL, color=BASELINE_DARK)
    row_letters(cv, [sum(lay.row(i)) / 2 for i in range(5)])
    # bottom block, top to bottom: legend row, triangle caption, method key
    legend_row(cv, [Line2D([], [], color=BASELINE_DARK, lw=0.7, label="SCB outline"), WD_HANDLE,
                    *tri_handles()], x=4, y_top=P20_BOTTOM - 10, withdrawn=False)
    cv.text(4, P20_BOTTOM - 23, "Triangles: share of personas in score bands 0–4 / 5–7 / 8–10 (corners); "
            "bar heights √-scaled", ha="left", va="top", fontsize=LEGEND_LABEL, color=FOOTNOTE_GREY)
    method_key(cv, KEY_H - 1)
    if FINAL:   # approved version: house writer, all three formats kept (PNG + SVG + EPS)
        from population_synthetic.analysis.utils.figures import save_figure as house_save
        house_save(cv.fig, HERE_OUT / "final" / f"{FINAL_STEM}.png", fixed_canvas=True)
    else:
        save_figure(cv.fig, HERE_OUT / "P20_square_grid_top_labels.png", fixed_canvas=True)
    return lay.h, lay.side


if __name__ == "__main__":
    want = set(a for a in sys.argv[1:] if not a.startswith("--"))
    for f in (P17, P18, P19, P20):
        if not want or f.__name__ in want:
            h, side = f()
            print(f.__name__, f"{h:.0f} pt tall, triangle side {side:.1f} pt (height {side * SQ3:.1f} pt)")
