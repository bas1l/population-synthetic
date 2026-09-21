"""Compact prototypes P01..P14 of the per-combination typicality distributions vs SCB.

Run: python protos.py [P01 P05 ...]   (no args -> all). Writes P??_*.png here (SVG/EPS siblings deleted at this prototype stage).
"""
from __future__ import annotations

import sys

import matplotlib.colors as mcolors
import numpy as np
from matplotlib.cm import ScalarMappable
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

from common import (
    CELL, GRID_X0, HERE, KEY_H, LABEL_DROP, LEGEND_H, LETTER, METHODS, MODELS, MLAB, N_SCORES, REF,
    REF_GAP, REF_TICK, SCORES, STRATS, WITHDRAWN, Canvas, HOSTING, legend_row, matrix, method_key,
    model_tick_labels, row_letters,
)
from population_synthetic.analysis.utils.figures import save_figure as _save_figure


def save_figure(fig, png, fixed_canvas=True):
    """Prototype stage: PNG only. Route through the house writer (budgets + ink checks), then drop SVG/EPS."""
    p = _save_figure(fig, png, fixed_canvas=fixed_canvas)
    for suf in ('.svg', '.eps'):
        p.with_suffix(suf).unlink()
    return p
from population_synthetic.analysis.utils.grid_annotations import (
    NoAnnotationPolicy, RateOnlyPolicy, SignedValuePolicy,
)
from population_synthetic.analysis.utils.grids import render_grid
from population_synthetic.analysis.utils.palette import (
    BAND_EDGE, BAND_FILL, BASELINE_DARK, CELL_STROKE, FOOTNOTE_GREY, GRID_RULE, HOST_COLORS,
    MISSING_COLOR, MUTED_GREY, SECONDARY_GREY, SURFACE, heatmap_cmap, heatmap_levels,
    text_color_for_rgb,
)
from population_synthetic.analysis.utils.style import (
    ANNOTATION, AXES_LINEWIDTH, AXIS_TITLE, GRID_LINEWIDTH, LEGEND_LABEL, LINE_LINEWIDTH,
    MIN_STROKE_PT, PATCH_LINEWIDTH, TICK_LABEL, TICK_LABEL_LARGE, house_style,
)

OUT = HERE
THIN = 0.5            # thin data stroke (>= MIN_STROKE_PT)
REF_LW = 1.0          # the SCB reference line in glyph cells
assert THIN >= MIN_STROKE_PT


# ====================================================================== grid geometry
class Grid:
    """5 method rows x 12 model columns + one detached SCB column, laid out in points."""

    def __init__(self, cell_w, cell_h, *, row_gap=3.0, col_gap=3.0, right_reserve=0.0, top_reserve=LEGEND_H + 6):
        self.cw, self.ch, self.rg, self.cg = cell_w, cell_h, row_gap, col_gap
        self.grid_h = 5 * cell_h + 4 * row_gap
        self.y0 = KEY_H + LABEL_DROP             # bottom of grid
        self.y1 = self.y0 + self.grid_h
        self.h = self.y1 + top_reserve
        self.xs0 = [GRID_X0 + j * (cell_w + col_gap) for j in range(12)]
        self.x1 = self.xs0[-1] + cell_w
        self.ref_x0 = self.x1 + REF_GAP
        self.ref_x1 = self.ref_x0 + cell_w
        self.right = self.ref_x1 + right_reserve

    def cell_box(self, i, j):   # i = method row (0 = A at top), j = model column
        top = self.y1 - i * (self.ch + self.rg)
        return self.xs0[j], top - self.ch, self.xs0[j] + self.cw, top

    def row_centres(self):
        return [self.y1 - i * (self.ch + self.rg) - self.ch / 2 for i in range(5)]

    def col_centres(self):
        return [x + self.cw / 2 for x in self.xs0]

    def ref_box(self, i):
        _, y0, _, y1 = self.cell_box(i, 0)
        return self.ref_x0, y0, self.ref_x1, y1


def finish(cv, g, name, *, ref_label=REF_TICK, key=True):
    model_tick_labels(cv, [c + 3 for c in g.col_centres()], g.y0 - 4,
                      ref_x=(g.ref_x0 + g.ref_x1) / 2 + 3, ref_label=ref_label)
    row_letters(cv, g.row_centres())
    if key:
        method_key(cv, KEY_H - 2)
    save_figure(cv.fig, OUT / f"{name}.png", fixed_canvas=True)
    return cv.h


def bare(ax):
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_linewidth(GRID_LINEWIDTH)
        s.set_color(GRID_RULE)


def withdrawn_cell(ax):
    """Glyph cells: a withdrawn combination is a crossed-out empty cell (grey fills are taken by data)."""
    ax.plot([0, 1], [0, 1], color=MUTED_GREY, linewidth=THIN, transform=ax.transAxes)
    ax.plot([0, 1], [1, 0], color=MUTED_GREY, linewidth=THIN, transform=ax.transAxes)
    bare(ax)


WD_HANDLE = Line2D([], [], marker="x", ls="none", color=MUTED_GREY, ms=4, mew=THIN, label="withdrawn")


def score_colorbar(cv, x0, y0, y1, *, label="Typicality score", levels=None, n=N_SCORES, ticks=None,
                   ticklabels=None):
    levels = levels or heatmap_levels(n)
    cax = cv.axes(x0, y0, x0 + 7, y1)
    sm = ScalarMappable(cmap=levels, norm=mcolors.BoundaryNorm(np.arange(-0.5, n), n))
    cb = cv.fig.colorbar(sm, cax=cax, ticks=ticks if ticks is not None else range(n))
    if ticklabels is not None:
        cb.set_ticklabels(ticklabels)
    cb.ax.tick_params(labelsize=TICK_LABEL, length=2, pad=1.5)
    cb.outline.set_linewidth(AXES_LINEWIDTH)
    cb.set_label(label, fontsize=TICK_LABEL, labelpad=2)
    return cb


# ====================================================================== P01 ECDF glyph grid
@house_style
def P01():
    """ECDF per cell, SCB ECDF superimposed; the area between them (= Wasserstein-1) shaded and printed."""
    g = Grid(28.0, 32.0, right_reserve=0)
    cv = Canvas(g.h)
    xs = np.arange(N_SCORES + 1) - 0.5

    def step(cdf):
        return np.r_[0.0, cdf]

    for i, m in enumerate(METHODS):
        for j, mod in enumerate(MODELS):
            ax = cv.axes(*g.cell_box(i, j))
            s = CELL[m][mod]
            if s is None:
                withdrawn_cell(ax)
                continue
            f, r = step(s["cdf"]), step(REF["cdf"])
            ax.fill_between(xs, f, r, step="post", color=BAND_FILL, linewidth=0, zorder=1)
            ax.step(xs, r, where="post", color=SECONDARY_GREY, linewidth=REF_LW, linestyle=(0, (2, 1)), zorder=2)
            ax.step(xs, f, where="post", color=BASELINE_DARK, linewidth=REF_LW, zorder=3)
            ax.text(-0.2, 1.0, f"{s['w1']:.1f}", ha="left", va="top", fontsize=ANNOTATION, color=BASELINE_DARK)
            ax.set_xlim(-0.5, 10.5)
            ax.set_ylim(-0.02, 1.04)
            bare(ax)
        ax = cv.axes(*g.ref_box(i))
        ax.step(xs, step(REF["cdf"]), where="post", color=SECONDARY_GREY, linewidth=REF_LW, linestyle=(0, (2, 1)))
        ax.set_xlim(-0.5, 10.5)
        ax.set_ylim(-0.02, 1.04)
        bare(ax)
    legend_row(cv, [Line2D([], [], color=BASELINE_DARK, lw=REF_LW, label="combination ECDF"),
                    Line2D([], [], color=SECONDARY_GREY, lw=REF_LW, ls=(0, (2, 1)), label="SCB ECDF"),
                    Patch(facecolor=BAND_FILL, label="gap area = W1, printed"), WD_HANDLE], x=4, withdrawn=False)
    return finish(cv, g, "P01_ecdf_glyph_grid")


# ====================================================================== P02 mini-histogram glyph grid
@house_style
def P02():
    """11-bar histogram per cell, bars coloured by score; SCB histogram as a black step outline in every cell."""
    g = Grid(26.0, 32.0, col_gap=2.0, right_reserve=46)
    cv = Canvas(g.h)
    lev = heatmap_levels(N_SCORES)
    ymax = 1.0
    rx = np.arange(N_SCORES + 1) - 0.5
    ry = np.r_[REF["pmf"], REF["pmf"][-1]]

    def hist(ax, pmf, outline=True):
        ax.bar(SCORES, pmf, width=1.0, color=[lev(k) for k in SCORES], edgecolor="none", zorder=1)
        if outline:
            ax.step(rx, ry, where="post", color=BASELINE_DARK, linewidth=0.7, zorder=3)
        ax.set_yscale("function", functions=(np.sqrt, np.square))
        ax.set_xlim(-0.6, 10.6)
        ax.set_ylim(0, ymax)
        bare(ax)

    for i, m in enumerate(METHODS):
        for j, mod in enumerate(MODELS):
            ax = cv.axes(*g.cell_box(i, j))
            s = CELL[m][mod]
            if s is None:
                withdrawn_cell(ax)
                continue
            hist(ax, s["pmf"])
        hist(cv.axes(*g.ref_box(i)), REF["pmf"], outline=False)
    score_colorbar(cv, g.ref_x1 + 12, g.y0, g.y1, label="Typicality score (bar colour)")
    legend_row(cv, [Line2D([], [], color=BASELINE_DARK, lw=0.7, label="SCB histogram (outline)"), WD_HANDLE],
               x=4, withdrawn=False)
    cv.text(452, cv.h - 3, "bar height √-scaled", ha="right", va="top", fontsize=LEGEND_LABEL, color=FOOTNOTE_GREY)
    return finish(cv, g, "P02_histogram_glyph_grid")


# ====================================================================== P03 diverging bar glyph grid
@house_style
def P03():
    """One diverging stacked bar per cell (Heiberger-Robbins), centred on the 4|5 cut (SCB median = 4)."""
    g = Grid(26.0, 34.0, col_gap=2.0, right_reserve=46)
    cv = Canvas(g.h)
    lev = heatmap_levels(N_SCORES)
    lo, hi = -0.62, 1.0
    ref_le4 = REF["le4"]

    def bar(ax, pmf, ref_mark=True, width=0.5):
        below = pmf[:5][::-1]   # 4,3,2,1,0 going down
        y = 0.0
        for k, h in zip(range(4, -1, -1), below):
            if h > 0:
                ax.bar(0, -h, bottom=y, width=width, color=lev(k), edgecolor=SURFACE, linewidth=0.3)
            y -= h
        y = 0.0
        for k in range(5, N_SCORES):
            h = pmf[k]
            if h > 0:
                ax.bar(0, h, bottom=y, width=width, color=lev(k), edgecolor=SURFACE, linewidth=0.3)
            y += h
        ax.axhline(0, color=BASELINE_DARK, linewidth=AXES_LINEWIDTH, zorder=4)
        if ref_mark:
            ax.plot([-0.36, 0.36], [-ref_le4, -ref_le4], color=BASELINE_DARK, linewidth=0.8, linestyle=(0, (1.5, 1)), zorder=4)
        ax.set_xlim(-0.5, 0.5)
        ax.set_ylim(lo, hi)
        ax.axis("off")

    for i, m in enumerate(METHODS):
        for j, mod in enumerate(MODELS):
            ax = cv.axes(*g.cell_box(i, j))
            s = CELL[m][mod]
            if s is None:
                withdrawn_cell(ax)
                continue
            bar(ax, s["pmf"])
        bar(cv.axes(*g.ref_box(i)), REF["pmf"], ref_mark=False)
    score_colorbar(cv, g.ref_x1 + 12, g.y0, g.y1, label="Typicality score")
    legend_row(cv, [Line2D([], [], color=BASELINE_DARK, lw=AXES_LINEWIDTH, label="cut 4|5"),
                    Line2D([], [], color=BASELINE_DARK, lw=0.8, ls=(0, (1.5, 1)), label=f"SCB share ≤4 ({ref_le4:.0%})"), WD_HANDLE],
               x=4, withdrawn=False)
    return finish(cv, g, "P03_diverging_bar_glyph_grid")


# ====================================================================== heatmap family (P04-P08)
def heatmap(name, mat, cells, policy, norm, *, ref_value, ref_cell, cbar_label, cbar_ticks=None,
            extra_legend=(), cell_h=24.0, fontsize=ANNOTATION, ref_rows=5, note=None, cbar_ticklabels=None):
    g = Grid(26.0, cell_h, row_gap=0.0, col_gap=0.0, right_reserve=58)
    cv = Canvas(g.h)
    cmap = heatmap_cmap()
    ax = cv.axes(GRID_X0, g.y0, g.x1, g.y1)
    im = render_grid(ax, mat, cells, policy=policy, cmap=cmap, norm=norm, aspect="auto", fontsize=fontsize)
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    for (i, j) in [(METHODS.index(m), MODELS.index(mod)) for m, mod in WITHDRAWN]:
        pass  # masked cells already take MISSING_COLOR through set_bad
    rax = cv.axes(g.ref_x0, g.y0, g.ref_x1, g.y1)
    render_grid(rax, np.full((1, 1), ref_value), [[ref_cell]], policy=policy, cmap=cmap, norm=norm,
                aspect="auto", fontsize=fontsize)
    rax.set_xticks([])
    rax.set_yticks([])
    for sp in rax.spines.values():
        sp.set_visible(False)
    cax = cv.axes(g.ref_x1 + 10, g.y0, g.ref_x1 + 17, g.y1)
    cb = cv.fig.colorbar(im, cax=cax, ticks=cbar_ticks)
    if cbar_ticklabels is not None:
        cb.set_ticklabels(cbar_ticklabels)
    cb.ax.tick_params(labelsize=TICK_LABEL, length=2, pad=1.5)
    cb.outline.set_linewidth(AXES_LINEWIDTH)
    cb.set_label(cbar_label, fontsize=TICK_LABEL, labelpad=2)
    if ref_value is not None and np.isfinite(ref_value):
        cb.ax.axhline(ref_value, color=SURFACE, linewidth=1.2)
        cb.ax.axhline(ref_value, color=BASELINE_DARK, linewidth=0.6)
    legend_row(cv, list(extra_legend), x=4)
    if note:
        cv.text(452, cv.h - 3, note, ha="right", va="top", fontsize=LEGEND_LABEL, color=FOOTNOTE_GREY)
    return cv, g


_all_above = all(CELL[m][mod]["mean_shift"] > 0 for m in METHODS for mod in MODELS if CELL[m][mod] is not None)
assert _all_above
NOTE_ABOVE = "every combination sits above SCB (mean shift > 0)"


def _cells(key, fmt=None):
    return [[{"value": (None if CELL[m][mod] is None else CELL[m][mod][key])} for mod in MODELS] for m in METHODS]


@house_style
def P04():
    """Heatmap of Wasserstein-1 (EMD) to SCB, in score points; value printed; SCB column = 0."""
    mat = matrix("w1")
    pol = RateOnlyPolicy(value_key="value", scale=1.0, number_format=".1f", absent_text="–")
    cv, g = heatmap("P04", mat, _cells("w1"), pol, mcolors.Normalize(0, 5.5), ref_value=0.0,
                    ref_cell={"value": 0.0}, cbar_label="Wasserstein-1 to SCB (score points)",
                    cbar_ticks=[0, 1, 2, 3, 4, 5], note=NOTE_ABOVE)
    return finish(cv, g, "P04_heatmap_wasserstein")


@house_style
def P05():
    """Heatmap of the share scoring <= 4 (SCB's median), SCB's own 57 % as the reference column."""
    mat = matrix("le4")
    pol = RateOnlyPolicy(value_key="value", scale=100.0, number_format=".0f", absent_text="–")
    cv, g = heatmap("P05", mat, _cells("le4"), pol, mcolors.Normalize(0, 0.6), ref_value=REF["le4"],
                    ref_cell={"value": REF["le4"]}, cbar_label="Share scoring ≤ 4 (%)",
                    cbar_ticks=[0, 0.2, 0.4, 0.6], cbar_ticklabels=["0", "20", "40", "60"])
    return finish(cv, g, "P05_heatmap_share_le4")


class MedianIQRPolicy:
    """Median on line 1, IQR on line 2 (pre-formatted by the caller)."""
    required_keys = frozenset({"head", "iqr"})

    def text(self, cell):
        return f"{cell['head']}\n{cell['iqr']}"


@house_style
def P06():
    """Heatmap of the median score, IQR printed under it."""
    mat = matrix("median")
    cells = [[{"head": "–", "iqr": ""} if CELL[m][mod] is None else
              {"head": str(CELL[m][mod]["median"]), "iqr": f"{CELL[m][mod]['q25']}–{CELL[m][mod]['q75']}"}
              for mod in MODELS] for m in METHODS]
    cv, g = heatmap("P06", mat, cells, MedianIQRPolicy(), mcolors.Normalize(0, 10), ref_value=REF["median"],
                    ref_cell={"head": str(REF["median"]), "iqr": f"{REF['q25']}–{REF['q75']}"},
                    cbar_label="Median typicality score", cbar_ticks=[0, 2, 4, 6, 8, 10], cell_h=26.0)
    return finish(cv, g, "P06_heatmap_median_iqr")


@house_style
def P07():
    """Heatmap of |Cliff's delta| vs SCB; the signed delta is printed (side lives in the text)."""
    mat = np.abs(matrix("delta"))
    pol = SignedValuePolicy(value_key="value", scale=1.0, number_format=".2f", absent_text="–")
    cv, g = heatmap("P07", mat, _cells("delta"), pol, mcolors.Normalize(0, 1), ref_value=0.0,
                    ref_cell={"value": 0.0}, cbar_label="|Cliff's δ| vs SCB", cbar_ticks=[0, 0.25, 0.5, 0.75, 1],
                    note="sign printed; + = scores above SCB")
    return finish(cv, g, "P07_heatmap_cliffs_delta")


@house_style
def P08():
    """Heatmap of total-variation distance to SCB (order-blind), value printed."""
    mat = matrix("tv")
    pol = RateOnlyPolicy(value_key="value", scale=1.0, number_format=".2f", absent_text="–")
    cv, g = heatmap("P08", mat, _cells("tv"), pol, mcolors.Normalize(0, 1), ref_value=0.0,
                    ref_cell={"value": 0.0}, cbar_label="Total variation to SCB", cbar_ticks=[0, 0.25, 0.5, 0.75, 1])
    return finish(cv, g, "P08_heatmap_total_variation")


# ====================================================================== P09 median + IQR dot/interval strip
MARKERS = ["o", "s", "^", "D", "v"]


@house_style
def P09():
    """One strip: models as columns, 5 method intervals per column (median dot, IQR bar, 10-90 whisker); SCB band."""
    H = 34 + 140 + LABEL_DROP + KEY_H
    cv = Canvas(H)
    x0, x1 = 40.0, 440.0
    y0, y1 = KEY_H + LABEL_DROP, KEY_H + LABEL_DROP + 140
    ax = cv.axes(x0, y0, x1, y1)
    n = len(MODELS)
    ref_xc = n + 0.4
    ax.axhspan(REF["q25"], REF["q75"], color=BAND_FILL, zorder=0, linewidth=0)
    ax.axhline(REF["median"], color=BAND_EDGE, linewidth=0.8, zorder=0.5)
    offs = np.linspace(-0.32, 0.32, 5)
    for j, mod in enumerate(MODELS):
        if j:
            ax.axvline(j - 0.5, color=GRID_RULE, linewidth=GRID_LINEWIDTH, zorder=0.2)
        for i, m in enumerate(METHODS):
            s = CELL[m][mod]
            x = j + offs[i]
            if s is None:
                ax.text(x, 0.2, "×", ha="center", va="bottom", fontsize=ANNOTATION, color=MUTED_GREY)
                continue
            ax.plot([x, x], [s["q10"], s["q90"]], color=MUTED_GREY, linewidth=THIN, zorder=1)
            ax.plot([x, x], [s["q25"], s["q75"]], color=BASELINE_DARK, linewidth=1.6, zorder=2, solid_capstyle="butt")
            ax.plot(x, s["median"], marker=MARKERS[i], markersize=3.2, color=BASELINE_DARK,
                    markerfacecolor=SURFACE if m != "E" else BASELINE_DARK, markeredgewidth=0.6, zorder=3)
    ax.axvline(n - 0.5 + 0.2, color=BASELINE_DARK, linewidth=0.6)
    ax.plot([ref_xc, ref_xc], [REF["q10"], REF["q90"]], color=MUTED_GREY, linewidth=THIN)
    ax.plot([ref_xc, ref_xc], [REF["q25"], REF["q75"]], color=BASELINE_DARK, linewidth=1.6, solid_capstyle="butt")
    ax.plot(ref_xc, REF["median"], marker="*", markersize=5, color=BASELINE_DARK)
    ax.set_xlim(-0.55, ref_xc + 0.55)
    ax.set_ylim(-0.3, 10.3)
    ax.set_yticks([0, 2, 4, 6, 8, 10])
    ax.tick_params(axis="y", labelsize=TICK_LABEL, length=2, pad=1.5)
    ax.set_ylabel("Typicality score", fontsize=TICK_LABEL, labelpad=2)
    ax.set_xticks([])
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    xs_pt = [x0 + (j + 0.55) / (ref_xc + 1.1) * (x1 - x0) for j in range(n)]
    ref_pt = x0 + (ref_xc + 0.55) / (ref_xc + 1.1) * (x1 - x0)
    model_tick_labels(cv, [x + 3 for x in xs_pt], y0 - 4, ref_x=ref_pt + 3)
    handles = [Line2D([], [], marker=MARKERS[i], ls="none", markersize=3.2, color=BASELINE_DARK,
                      markerfacecolor=SURFACE if m != "E" else BASELINE_DARK, markeredgewidth=0.6, label=m)
               for i, m in enumerate(METHODS)]
    handles += [Line2D([], [], color=BASELINE_DARK, lw=1.6, label="IQR"),
                Line2D([], [], color=MUTED_GREY, lw=THIN, label="10–90%"),
                Patch(facecolor=BAND_FILL, edgecolor=BAND_EDGE, linewidth=0.6, label="SCB IQR, median")]
    legend_row(cv, handles, x=4, withdrawn=False)
    cv.text(4, cv.h - 15, "Median marker; methods left→right A–E within each model; × withdrawn",
            ha="left", va="top", fontsize=LEGEND_LABEL, color=FOOTNOTE_GREY)
    method_key(cv, KEY_H - 2)
    save_figure(cv.fig, OUT / "P09_median_iqr_intervals.png", fixed_canvas=True)
    return H


# ====================================================================== P10 thin diverging bars strip
@house_style
def P10():
    """One strip, 12 model groups x 5 thin diverging stacked bars (A-E), centred on the 4|5 cut; SCB bar at right."""
    H = 32 + 140 + LABEL_DROP + KEY_H
    cv = Canvas(H)
    x0, x1 = 36.0, 404.0
    y0, y1 = KEY_H + LABEL_DROP, KEY_H + LABEL_DROP + 140
    ax = cv.axes(x0, y0, x1, y1)
    lev = heatmap_levels(N_SCORES)
    n = len(MODELS)
    offs = np.linspace(-0.34, 0.34, 5)
    bw = 0.155
    ref_xc = n + 0.3

    def dbar(x, pmf, w):
        y = 0.0
        for k in range(4, -1, -1):
            if pmf[k] > 0:
                ax.bar(x, -pmf[k], bottom=y, width=w, color=lev(k), edgecolor="none", zorder=2)
            y -= pmf[k]
        y = 0.0
        for k in range(5, N_SCORES):
            if pmf[k] > 0:
                ax.bar(x, pmf[k], bottom=y, width=w, color=lev(k), edgecolor="none", zorder=2)
            y += pmf[k]

    for j, mod in enumerate(MODELS):
        for i, m in enumerate(METHODS):
            s = CELL[m][mod]
            x = j + offs[i]
            if s is None:
                ax.bar(x, 1.0, bottom=-0.0, width=bw, color=MISSING_COLOR, edgecolor="none", zorder=1)
                continue
            dbar(x, s["pmf"], bw)
    dbar(ref_xc, REF["pmf"], 0.5)
    ax.axhline(0, color=BASELINE_DARK, linewidth=AXES_LINEWIDTH, zorder=3)
    ax.axhline(-REF["le4"], color=BASELINE_DARK, linewidth=0.6, linestyle=(0, (2, 1.5)), zorder=3)
    ax.axvline(n - 0.5 + 0.15, color=BASELINE_DARK, linewidth=0.6)
    for i, m in enumerate(METHODS):   # letter the first group only
        ax.text(offs[i], 1.01, m, ha="center", va="bottom", fontsize=ANNOTATION, color=FOOTNOTE_GREY)
    ax.set_xlim(-0.5, ref_xc + 0.45)
    ax.set_ylim(-0.62, 1.0)
    ax.set_yticks([-0.5, 0, 0.5, 1.0])
    ax.set_yticklabels(["50", "0", "50", "100"])
    ax.tick_params(axis="y", labelsize=TICK_LABEL, length=2, pad=1.5)
    ax.set_ylabel("% ≤ 4   |   % ≥ 5", fontsize=TICK_LABEL, labelpad=2)
    ax.set_xticks([])
    for sp in ("top", "right", "bottom"):
        ax.spines[sp].set_visible(False)
    span = ref_xc + 0.45 + 0.5
    xs_pt = [x0 + (j + 0.5) / span * (x1 - x0) for j in range(n)]
    ref_pt = x0 + (ref_xc + 0.5) / span * (x1 - x0)
    model_tick_labels(cv, [x + 3 for x in xs_pt], y0 - 4, ref_x=ref_pt + 3)
    score_colorbar(cv, x1 + 14, y0, y1, label="Typicality score")
    legend_row(cv, [Line2D([], [], color=BASELINE_DARK, lw=0.6, ls=(0, (2, 1.5)), label=f"SCB share ≤ 4 ({REF['le4']:.0%})")],
               x=4)
    cv.text(4, cv.h - 14, "Five bars per model = methods A–E, left to right", ha="left", va="top",
            fontsize=LEGEND_LABEL, color=FOOTNOTE_GREY)
    method_key(cv, KEY_H - 2)
    save_figure(cv.fig, OUT / "P10_thin_diverging_bars.png", fixed_canvas=True)
    return H


# ====================================================================== P11 ternary small multiples
@house_style
def P11():
    """Five ternary panels (one per method): each combination as a point in (0-4, 5-7, 8-10) share space."""
    H = 116.0
    cv = Canvas(H)
    V = np.array([[0.0, 0.0], [1.0, 0.0], [0.5, np.sqrt(3) / 2]])   # low (bottom-left), mid (bottom-right), high (top)
    pw = 84.0
    for i, m in enumerate(METHODS):
        xa = 8 + i * (pw + 5)
        ax = cv.axes(xa, 14, xa + pw, 14 + pw * np.sqrt(3) / 2 + 8)
        tri = np.vstack([V, V[:1]])
        ax.plot(tri[:, 0], tri[:, 1], color=BASELINE_DARK, linewidth=AXES_LINEWIDTH)
        for t in (0.25, 0.5, 0.75):   # iso-lines of the high share
            a = V[0] + t * (V[2] - V[0])
            b = V[1] + t * (V[2] - V[1])
            ax.plot([a[0], b[0]], [a[1], b[1]], color=GRID_RULE, linewidth=GRID_LINEWIDTH, zorder=0)
        for mod in MODELS:
            s = CELL[m][mod]
            if s is None:
                continue
            p = np.array([s["le4"], s["mid"], s["high"]]) @ V
            ax.plot(*p, marker="o", ms=3.0, color=HOST_COLORS[HOSTING[mod]], mec=SURFACE, mew=0.3, ls="none", zorder=3)
        p = np.array([REF["le4"], REF["mid"], REF["high"]]) @ V
        ax.plot(*p, marker="*", ms=7, color=BASELINE_DARK, mec=SURFACE, mew=0.3, ls="none", zorder=4)
        ax.set_xlim(-0.04, 1.04)
        ax.set_ylim(-0.04, np.sqrt(3) / 2 + 0.1)
        ax.set_aspect("equal", adjustable="box", anchor="S")
        ax.axis("off")
        ax.text(0.5, np.sqrt(3) / 2 + 0.06, f"Method {m}", ha="center", va="bottom", fontsize=TICK_LABEL_LARGE,
                fontweight="bold", color=BASELINE_DARK)
        ax.text(-0.02, -0.03, "0–4", ha="left", va="top", fontsize=TICK_LABEL, color=FOOTNOTE_GREY)
        ax.text(1.02, -0.03, "5–7", ha="right", va="top", fontsize=TICK_LABEL, color=FOOTNOTE_GREY)
        ax.text(0.62, np.sqrt(3) / 2 - 0.02, "8–10", ha="left", va="center", fontsize=TICK_LABEL, color=FOOTNOTE_GREY)
    legend_row(cv, [Line2D([], [], marker="*", ms=7, ls="none", color=BASELINE_DARK, label="SCB")],
               x=8, withdrawn=False)
    cv.text(448, H - 3, "corner = all mass in that score band", ha="right", va="top", fontsize=LEGEND_LABEL,
            color=FOOTNOTE_GREY)
    save_figure(cv.fig, OUT / "P11_ternary_by_method.png", fixed_canvas=True)
    return H


# ====================================================================== P12 per-model sparklines
@house_style
def P12():
    """12 small panels (models as columns): share <= 4 across methods A-E, SCB level as a dashed rule."""
    H = 18 + 80 + LABEL_DROP + 22
    cv = Canvas(H)
    y0, y1 = LABEL_DROP + 22, LABEL_DROP + 22 + 80
    cw, cg = 29.0, 4.0
    xs0 = [34 + j * (cw + cg) for j in range(12)]
    for j, mod in enumerate(MODELS):
        ax = cv.axes(xs0[j], y0, xs0[j] + cw, y1)
        v = [np.nan if CELL[m][mod] is None else CELL[m][mod]["le4"] for m in METHODS]
        ax.axhline(REF["le4"], color=BASELINE_DARK, linewidth=0.8, linestyle=(0, (2, 1.5)))
        ax.plot(range(5), v, color=BASELINE_DARK, linewidth=LINE_LINEWIDTH * 0.8, marker="o", ms=2.2, zorder=3)
        ax.plot(4, v[4], marker="o", ms=3.2, color=BASELINE_DARK, zorder=4) if np.isfinite(v[4]) else \
            ax.text(4, 0.02, "×", ha="center", va="bottom", fontsize=ANNOTATION, color=MUTED_GREY)
        ax.set_xlim(-0.5, 4.5)
        ax.set_ylim(0, 0.62)
        ax.set_xticks(range(5))
        ax.set_xticklabels([METHODS[0], "", "", "", METHODS[-1]], fontsize=TICK_LABEL)
        ax.tick_params(axis="x", length=0, pad=1)
        ax.set_yticks([0, 0.2, 0.4, 0.6])
        ax.tick_params(axis="y", length=1.5, labelsize=TICK_LABEL, pad=1)
        if j:
            ax.set_yticklabels([])
        else:
            ax.set_yticklabels(["0", "20", "40", "60"])
            ax.set_ylabel("% scoring ≤ 4", fontsize=TICK_LABEL, labelpad=1)
        ax.grid(axis="y", color=GRID_RULE, linewidth=GRID_LINEWIDTH)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    model_tick_labels(cv, [x + cw / 2 + 3 for x in xs0], y0 - 12, ref_x=None)
    legend_row(cv, [Line2D([], [], color=BASELINE_DARK, lw=0.8, ls=(0, (2, 1.5)), label=f"SCB ({REF['le4']:.0%})"),
                    Line2D([], [], color=BASELINE_DARK, lw=0.96, marker="o", ms=2.2, label="methods A→E"),
                    Line2D([], [], marker="x", ls="none", color=MUTED_GREY, ms=3, label="withdrawn")],
               x=34, withdrawn=False)
    save_figure(cv.fig, OUT / "P12_sparklines_share_le4.png", fixed_canvas=True)
    return H


# ====================================================================== P13 histogram heatmap
@house_style
def P13():
    """Distribution heatmap: per method block, 11 score rows x 12 model columns (+ SCB), fill = share."""
    rh, gap = 3.4, 4.0
    block = N_SCORES * rh
    top = LEGEND_H + 8
    H = top + 5 * block + 4 * gap + LABEL_DROP + KEY_H
    cv = Canvas(H)
    cw = 26.0
    x0 = 30.0
    x1 = x0 + 12 * cw
    rx0 = x1 + REF_GAP
    rx1 = rx0 + cw
    cmap = heatmap_cmap()
    norm = mcolors.PowerNorm(0.5, 0, 1)
    y_grid0 = KEY_H + LABEL_DROP
    im = None
    for i, m in enumerate(METHODS):
        by1 = H - top - i * (block + gap)
        by0 = by1 - block
        mat = np.full((N_SCORES, 12), np.nan)
        for j, mod in enumerate(MODELS):
            s = CELL[m][mod]
            if s is not None:
                mat[:, j] = s["pmf"][::-1]     # row 0 = score 10 at the top
        ax = cv.axes(x0, by0, x1, by1)
        im = render_grid(ax, mat, [[None] * 12 for _ in range(N_SCORES)], policy=NoAnnotationPolicy(),
                         cmap=cmap, norm=norm, aspect="auto")
        ax.set_xticks([])
        ax.set_yticks([0, 10])
        ax.set_yticklabels(["10", "0"], fontsize=TICK_LABEL)
        ax.tick_params(axis="y", length=0, pad=1)
        for sp in ax.spines.values():
            sp.set_visible(False)
        rax = cv.axes(rx0, by0, rx1, by1)
        render_grid(rax, REF["pmf"][::-1].reshape(-1, 1), [[None] for _ in range(N_SCORES)],
                    policy=NoAnnotationPolicy(), cmap=cmap, norm=norm, aspect="auto")
        rax.axis("off")
        cv.text(4, (by0 + by1) / 2, m, ha="left", va="center", fontsize=TICK_LABEL_LARGE, fontweight="bold",
                color=BASELINE_DARK)
    cax = cv.axes(rx1 + 12, y_grid0, rx1 + 19, H - top)
    cb = cv.fig.colorbar(im, cax=cax, ticks=[0, 0.05, 0.2, 0.5, 1])
    cb.set_ticklabels(["0", "5", "20", "50", "100"])
    cb.ax.tick_params(labelsize=TICK_LABEL, length=2, pad=1.5)
    cb.outline.set_linewidth(AXES_LINEWIDTH)
    cb.set_label("% of personas at score (√ scale)", fontsize=TICK_LABEL, labelpad=2)
    model_tick_labels(cv, [x0 + (j + 0.5) * cw + 3 for j in range(12)], y_grid0 - 4, ref_x=(rx0 + rx1) / 2 + 3)
    legend_row(cv, [], x=4)
    cv.text(452, cv.h - 3, "each block: score rows 0 (bottom) to 10 (top)", ha="right", va="top",
            fontsize=LEGEND_LABEL, color=FOOTNOTE_GREY)
    method_key(cv, KEY_H - 2)
    save_figure(cv.fig, OUT / "P13_histogram_heatmap.png", fixed_canvas=True)
    return H


# ====================================================================== P14 ECDF overlays per method
@house_style
def P14():
    """Five ECDF panels (one per method): 12 model curves each, SCB curve bold; mass right of SCB = higher typicality."""
    H = 128.0
    cv = Canvas(H)
    pw, gapx = 74.0, 7.0
    xs = np.arange(N_SCORES + 1) - 0.5
    for i, m in enumerate(METHODS):
        xa = 34 + i * (pw + gapx)
        ax = cv.axes(xa, 38, xa + pw, 112)
        for mod in MODELS:
            s = CELL[m][mod]
            if s is None:
                continue
            ax.step(xs, np.r_[0, s["cdf"]], where="post", color=HOST_COLORS[HOSTING[mod]], linewidth=THIN)
        ax.step(xs, np.r_[0, REF["cdf"]], where="post", color=BASELINE_DARK, linewidth=1.6)
        ax.set_xlim(-0.5, 10.5)
        ax.set_ylim(0, 1.02)
        ax.set_xticks([0, 4, 10])
        ax.tick_params(labelsize=TICK_LABEL, length=2, pad=1.5)
        ax.set_yticks([0, 0.5, 1])
        if i:
            ax.set_yticklabels([])
        else:
            ax.set_yticklabels(["0", "50", "100"])
            ax.set_ylabel("Cumulative %", fontsize=TICK_LABEL, labelpad=2)
        ax.axvline(4, color=GRID_RULE, linewidth=GRID_LINEWIDTH, zorder=0)
        ax.set_title(f"Method {m}", fontsize=TICK_LABEL_LARGE, fontweight="bold", pad=3)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    cv.text(34 + 2.5 * pw + 2 * gapx, 16, "Typicality score", ha="center", va="bottom", fontsize=TICK_LABEL)
    legend_row(cv, [Line2D([], [], color=BASELINE_DARK, lw=1.6, label="SCB")], x=4, y_top=11, withdrawn=False)
    save_figure(cv.fig, OUT / "P14_ecdf_overlay_by_method.png", fixed_canvas=True)
    return H


ALL = [P01, P02, P03, P04, P05, P06, P07, P08, P09, P10, P11, P12, P13, P14]

if __name__ == "__main__":
    want = set(sys.argv[1:])
    for f in ALL:
        if want and f.__name__ not in want:
            continue
        try:
            h = f()
            print(f.__name__, f"{h:.0f} pt")
        except Exception as e:  # keep going so every prototype reports
            print(f.__name__, "FAILED:", str(e)[:160])
