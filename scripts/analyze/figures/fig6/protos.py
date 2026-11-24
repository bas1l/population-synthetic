"""Figure 6 gallery prototypes P01..P14: where finished individuals are lost (LLM vs mapping vs tables).

Run: python protos.py [P01 P05 ...]   (no args -> all). Writes P??_<name>.png here; the SVG/EPS
siblings the house writer emits are deleted at this prototype stage.
All numbers come from common.py (shares of the finished individuals, raw_valid, unless stated).
"""
from __future__ import annotations

import sys

import matplotlib.colors as mcolors
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

import common as d
from population_synthetic.analysis.utils.figures import save_figure as _save_figure
from population_synthetic.analysis.utils.glyph_grid import PointCanvas, draw_withdrawn_cell, withdrawn_handle
from population_synthetic.analysis.utils.grid_annotations import RateOnlyPolicy
from population_synthetic.analysis.utils.grids import render_grid
from population_synthetic.analysis.utils.palette import (
    BASELINE_DARK, FOOTNOTE_GREY, GRID_RULE, HOST_COLORS, MUTED_GREY, SECONDARY_GREY, SURFACE,
    heatmap_cmap, text_color_for_rgb,
)
from population_synthetic.analysis.utils.style import (
    ANNOTATION, AXES_LINEWIDTH, GRID_LINEWIDTH, LEGEND_LABEL, PATCH_LINEWIDTH, TICK_LABEL,
    TICK_LABEL_LARGE, house_style,
)

W = 456.0
import os as _os
from pathlib import Path as _Path
# 2026-10-20 manuscript copy: never write into the gallery folder; FIG_OUT_DIR, else ./out beside this script.
OUT = _Path(_os.environ.get("FIG_OUT_DIR") or (d.HERE / "out"))
PNG_DPI = 600
N_ROWS, N_COLS = 5, 13
LAST_SEP = 5.0          # extra gap before the model withdrawn in every strategy (published Fig 6 rule)
LABEL_BAND = 74.0       # rotated model names above a grid
KEY_H = 22.0            # two-line strategy key at the bottom
HATCH = "////"
CC = d.CAUSE_COLOR
LOSSES = ["llm", "mapping", "tables"]
PCT = lambda v: f"{100 * v:.0f}"  # noqa: E731


def save(cv, name, *, writer_dpi=None):
    # Manuscript export (2026-10-20): keep the house writer's PNG + SVG + EPS, add a PDF at the
    # same fixed canvas, PNG at 600 dpi (456 pt -> 3800 px, like the other docx figures).
    import matplotlib.pyplot as _plt
    from population_synthetic.analysis.utils.figures import _export_rc_params
    OUT.mkdir(parents=True, exist_ok=True)
    # A figure with raster content (the heatmap's imshow) is embedded in SVG/EPS at the writer's dpi;
    # at 600 dpi its EPS exceeds the house 10 MiB ceiling. So: PNG rendered here at 600 dpi, the
    # house writer at its own RASTER_DPI (300) for SVG/EPS and its checks, then the 600-dpi PNG
    # replaces the writer's 300-dpi one. A figure without raster content is unaffected by the dpi.
    import io as _io
    buf = _io.BytesIO()
    with _plt.rc_context(_export_rc_params()):
        cv.figure.savefig(OUT / f"{name}.pdf", format="pdf", dpi=PNG_DPI, bbox_inches=None, pad_inches=0)
        cv.figure.savefig(buf, format="png", dpi=PNG_DPI, bbox_inches=None, pad_inches=0)
    if writer_dpi is not None:  # the house writer itself renders the PNG (and runs its checks) at this dpi
        p = _save_figure(cv.figure, OUT / f"{name}.png", dpi=writer_dpi, fixed_canvas=True)
        print("wrote", p.name, f"{cv.height_pt:.0f} pt (house writer at {writer_dpi} dpi)")
        return p
    p = _save_figure(cv.figure, OUT / f"{name}.png", fixed_canvas=True)
    # the 600-dpi PNG replaces the writer's; its edges are checked here too (no ink on any edge row/column)
    import numpy as _np
    from PIL import Image as _Image
    arr = _np.asarray(_Image.open(_io.BytesIO(buf.getvalue())).convert("L"))
    if any((edge < 250).any() for edge in (arr[0], arr[-1], arr[:, 0], arr[:, -1])):
        raise ValueError(f"{name}: the 600-dpi PNG has ink on the canvas edge")
    p.write_bytes(buf.getvalue())
    print("wrote", p.name, f"{cv.height_pt:.0f} pt")
    return p


# =========================================================================== geometry
class Grid:
    """5 strategy rows x 13 model columns in points (bottom-left origin)."""

    def __init__(self, x0, x1, y_top, cell_h, *, row_gap=2.0, col_gap=2.0, last_sep=LAST_SEP):
        self.x0, self.x1, self.y_top, self.ch, self.rg, self.cg = x0, x1, y_top, cell_h, row_gap, col_gap
        self.cw = (x1 - x0 - last_sep - (N_COLS - 1) * col_gap) / N_COLS
        self.xs = [x0 + j * (self.cw + col_gap) + (last_sep if j == N_COLS - 1 else 0) for j in range(N_COLS)]
        self.y_bot = y_top - N_ROWS * cell_h - (N_ROWS - 1) * row_gap

    def box(self, i, j):
        top = self.y_top - i * (self.ch + self.rg)
        return self.xs[j], top - self.ch, self.xs[j] + self.cw, top

    def cx(self):
        return [x + self.cw / 2 for x in self.xs]

    def cy(self):
        return [self.y_top - i * (self.ch + self.rg) - self.ch / 2 for i in range(N_ROWS)]


def model_names_above(cv, xs, y, *, fontsize=TICK_LABEL):
    for x, m in zip(xs, d.MODELS):
        cv.text(x, y, d.MLAB[m], fontsize=fontsize, rotation=90, ha="center", va="bottom",
                color=HOST_COLORS[d.HOSTING[m]])


def row_letters(cv, ys, x):
    for y, m in zip(ys, d.METHODS):
        cv.text(x, y, m, fontsize=TICK_LABEL_LARGE, fontweight="bold", ha="right", va="center", color=BASELINE_DARK)


def strategy_key(cv, y_top=KEY_H - 3, x=4.0):
    l1, l2 = d.method_key_text()
    cv.text(x, y_top, l1, fontsize=LEGEND_LABEL, ha="left", va="top", color=FOOTNOTE_GREY)
    cv.text(x + 58, y_top - 10, l2, fontsize=LEGEND_LABEL, ha="left", va="top", color=FOOTNOTE_GREY)


def bare(ax, frame=True):
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(frame)
        s.set_linewidth(GRID_LINEWIDTH)
        s.set_color(GRID_RULE)


def hatch_handle(label="withdrawn"):
    return Patch(facecolor=SURFACE, edgecolor=BASELINE_DARK, hatch="///", linewidth=PATCH_LINEWIDTH, label=label)


def hatch_withdrawn(ax, wd, *, offset=0.0):
    for i in range(N_ROWS):
        for j in range(N_COLS):
            if wd[i, j]:
                ax.add_patch(Rectangle((j - 0.5, i - 0.5 + offset), 1, 1, facecolor="none", edgecolor=SURFACE,
                                       hatch=HATCH, linewidth=0, zorder=6))


def heatmap(cv, box, mat, *, vmax, wd, fmt=".0f", cmap=None, norm=None, fontsize=ANNOTATION):
    """One 5x13 heatmap through grids.render_grid; withdrawn hatched; last column set apart by a rule."""
    ax = cv.axes(*box)
    cells = [[{"v": float(mat[i, j])} for j in range(N_COLS)] for i in range(N_ROWS)]
    norm = norm or mcolors.Normalize(0, vmax)
    im = render_grid(ax, mat, cells, policy=RateOnlyPolicy(value_key="v", scale=100.0, number_format=fmt),
                     cmap=cmap or heatmap_cmap(), norm=norm, aspect="auto", fontsize=fontsize, zorder=5)
    hatch_withdrawn(ax, wd)
    ax.axvline(N_COLS - 1.5, color=BASELINE_DARK, linewidth=1.2, zorder=7)
    bare(ax, frame=False)
    return ax, im


def colorbar(cv, im, box, label, ticks):
    cax = cv.axes(*box)
    cb = cv.figure.colorbar(im, cax=cax, ticks=ticks)
    cb.ax.set_yticklabels([f"{100 * t:.0f}%" for t in ticks], fontsize=TICK_LABEL)
    cb.ax.tick_params(length=2, pad=1.5, width=AXES_LINEWIDTH)
    cb.outline.set_linewidth(AXES_LINEWIDTH)
    cb.set_label(label, fontsize=TICK_LABEL, labelpad=2)
    return cb


def grid_heat_xs(box):
    """Column centres (points) of a heatmap axes box spanning 13 equal columns."""
    x0, _, x1, _ = box
    cw = (x1 - x0) / N_COLS
    return [x0 + cw * (j + 0.5) for j in range(N_COLS)]


def hatch_ab(ax, x, y, w, h):
    """The A+B slice: LLM-lost individuals that also gave a table-limit answer (black, pink hatch)."""
    if w > 0 and h > 0:
        ax.add_patch(Rectangle((x, y), w, h, facecolor=CC["llm"], edgecolor=CC["tables"], hatch="//////",
                               linewidth=0, zorder=3))


def stack_v(ax, parts, colors, *, edge=None):
    """Vertical stacked bar in [0,1] axes coordinates; parts are fractions from the bottom."""
    y = 0.0
    for p, c in zip(parts, colors):
        if p > 0:
            ax.add_patch(Rectangle((0.08, y), 0.84, p, facecolor=c, edgecolor=edge or "none",
                                   linewidth=0.3 if edge else 0))
        y += p


def stack_h(ax, parts, colors, *, y0=0.0, h=1.0):
    x = 0.0
    for p, c in zip(parts, colors):
        if p > 0:
            ax.add_patch(Rectangle((x, y0), p, h, facecolor=c, edgecolor="none", linewidth=0))
        x += p


# =========================================================================== P01
@house_style
def P01():
    """Glyph grid: one 100% stacked column per cell (retained, LLM, mapping, tables)."""
    H = 296.0
    cv = PointCanvas(W, H)
    g = Grid(24, 452, H - 28 - LABEL_BAND, 31.0, row_gap=3)
    for i, m in enumerate(d.METHODS):
        for j, mod in enumerate(d.MODELS):
            r = d.CELL[m][mod]
            ax = cv.axes(*g.box(i, j))
            parts = [r.s_retained, r.s_llm, r.s_mapping, r.s_tables]
            stack_v(ax, parts, [CC[c] for c in d.CAUSES])
            hatch_ab(ax, 0.08, r.s_retained + r.s_llm - r.s_llm_alsoB, 0.84, r.s_llm_alsoB)
            ax.text(0.5, 0.04, PCT(r.s_retained), transform=ax.transAxes, ha="center", va="bottom",
                    fontsize=ANNOTATION, color=BASELINE_DARK if r.s_retained >= 0.3 else SURFACE)
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            if r.excluded:
                draw_withdrawn_cell(ax)
            else:
                bare(ax)
    model_names_above(cv, g.cx(), g.y_top + 3)
    row_letters(cv, g.cy(), g.x0 - 5)
    cv.legend(d.cause_handles(d.CAUSES, alsoB=True) + [withdrawn_handle("withdrawn")], x=4, y_top=H - 3, ncol=4)
    cv.text(452, KEY_H - 3, "number: retained %", fontsize=LEGEND_LABEL, ha="right", va="top", color=FOOTNOTE_GREY)
    strategy_key(cv)
    return save(cv, "P01_stacked_column_glyph_grid")


# =========================================================================== P02
@house_style
def P02():
    """Glyph grid: three aligned lanes per cell (LLM, mapping, tables), square-root length, % printed."""
    H = 262.0
    cv = PointCanvas(W, H)
    g = Grid(24, 452, H - 18 - LABEL_BAND, 27.0, row_gap=3)
    vmax = np.sqrt(0.85)
    for i, m in enumerate(d.METHODS):
        for j, mod in enumerate(d.MODELS):
            r = d.CELL[m][mod]
            ax = cv.axes(*g.box(i, j))
            for k, c in enumerate(LOSSES):
                v = r[f"s_{c}"]
                y = 2 - k
                ax.barh(y, np.sqrt(v) / vmax, height=0.78, color=CC[c], edgecolor="none")
                if c == "llm":
                    x0_ = np.sqrt(v - r.s_llm_alsoB) / vmax
                    hatch_ab(ax, x0_, y - 0.39, np.sqrt(v) / vmax - x0_, 0.78)
            ax.set_xlim(0, 1)
            ax.set_ylim(-0.5, 2.5)
            ax.text(0.98, 0.03, PCT(r.s_tables), transform=ax.transAxes, ha="right", va="bottom",
                    fontsize=ANNOTATION, color=CC["tables"], fontweight="bold")
            if r.excluded:
                draw_withdrawn_cell(ax)
            else:
                bare(ax)
    model_names_above(cv, g.cx(), g.y_top + 3)
    row_letters(cv, g.cy(), g.x0 - 5)
    cv.legend(d.cause_handles(LOSSES, alsoB=True) + [withdrawn_handle("withdrawn")], x=4, y_top=H - 3, ncol=5)
    cv.text(452, KEY_H - 3, "bar length: square root of % of finished\nnumber: table-limit %", fontsize=LEGEND_LABEL,
            ha="right", va="top", color=FOOTNOTE_GREY, linespacing=1.0)
    strategy_key(cv)
    return save(cv, "P02_three_lane_glyph_grid")


# =========================================================================== P03
@house_style
def P03():
    """Three heatmaps stacked (shared model columns): loss to LLM, to mapping, to tables, own scales."""
    H = 300.0
    cv = PointCanvas(W, H)
    wd = d.withdrawn_mask()
    x0, x1 = 24.0, 376.0
    ph, gap = 58.0, 10.0
    top = H - 10 - LABEL_BAND
    specs = [("llm", 0.85, [0, 0.4, 0.8], "LLM\nfailure"), ("tables", 0.22, [0, 0.1, 0.2], "table\nlimit"),
             ("mapping", 0.12, [0, 0.05, 0.1], "mapping\ngap")]
    for k, (c, vmax, ticks, name) in enumerate(specs):
        yt = top - k * (ph + gap)
        box = (x0, yt - ph, x1, yt)
        ax, im = heatmap(cv, box, d.matrix(f"s_{c}"), vmax=vmax, wd=wd)
        colorbar(cv, im, (381, yt - ph, 387, yt), "", ticks)
        cv.text(454, yt - ph / 2, name, fontsize=TICK_LABEL, ha="right", va="center", color=BASELINE_DARK,
                fontweight="bold", linespacing=1.0)
        ys = [yt - ph * (i + 0.5) / N_ROWS for i in range(N_ROWS)]
        row_letters(cv, ys, x0 - 4)
    model_names_above(cv, grid_heat_xs((x0, 0, x1, 0)), top + 3)
    cv.legend(d.host_handles() + [hatch_handle()], x=4, y_top=H - 3, ncol=3)
    cv.text(452, H - 4, "% of finished individuals", fontsize=LEGEND_LABEL, ha="right", va="top", color=FOOTNOTE_GREY)
    strategy_key(cv)
    return save(cv, "P03_three_heatmaps_stacked")


# =========================================================================== P04
@house_style
def P04():
    """Two heatmaps side by side, one shared square-root scale: lost to LLM | lost to tables."""
    H = 210.0
    cv = PointCanvas(W, H)
    wd = d.withdrawn_mask()
    norm = mcolors.PowerNorm(0.5, 0, 0.85)
    gh = 5 * 15.0
    yt = H - 20 - LABEL_BAND
    boxes = [(16, yt - gh, 212, yt), (226, yt - gh, 422, yt)]
    for box, c in zip(boxes, ("llm", "tables")):
        ax, im = heatmap(cv, box, d.matrix(f"s_{c}"), vmax=None, wd=wd, norm=norm)
        model_names_above(cv, grid_heat_xs(box), yt + 3)
        cv.text((box[0] + box[2]) / 2, H - 16, d.CAUSE_LABEL[c], fontsize=TICK_LABEL_LARGE, fontweight="bold",
                ha="center", va="bottom", color=CC[c] if c != "llm" else BASELINE_DARK)
        row_letters(cv, [yt - gh * (i + 0.5) / 5 for i in range(5)], box[0] - 3)
    colorbar(cv, im, (430, yt - gh, 436, yt), "", [0, 0.05, 0.2, 0.4, 0.8])
    cv.legend(d.host_handles() + [hatch_handle()], x=16, y_top=yt - gh - 6, ncol=3)
    cv.text(452, yt - gh - 6, "% of finished, square-root colour scale", fontsize=LEGEND_LABEL, ha="right",
            va="top", color=FOOTNOTE_GREY)
    strategy_key(cv)
    return save(cv, "P04_two_heatmaps_side_by_side")


# =========================================================================== P05
@house_style
def P05():
    """Published Fig 6 retention heatmap (left) + attribute rows of pooled unmapped answers by cause (right)."""
    H = 250.0
    cv = PointCanvas(W, H)
    wd = d.withdrawn_mask()
    yt = H - 6 - LABEL_BAND
    gh = 5 * 22.0
    box = (18, yt - gh, 262, yt)
    ax, im = heatmap(cv, box, d.matrix("s_retained"), vmax=1.0, wd=wd)
    colorbar(cv, im, (266, yt - gh, 271, yt), "", [0, 0.5, 1.0])
    model_names_above(cv, grid_heat_xs(box), yt + 3)
    row_letters(cv, [yt - gh * (i + 0.5) / 5 for i in range(5)], box[0] - 3)
    cv.text(18, yt - gh - 5, "a  retained, % of finished", fontsize=TICK_LABEL, ha="left", va="top",
            color=BASELINE_DARK, fontweight="bold")
    # panel b: attributes
    occ = d.OCC
    ax2 = cv.axes(356, KEY_H + 22, 446, H - 22)
    ys = np.arange(len(d.ATTRS))[::-1]
    left = np.zeros(len(d.ATTRS))
    for c in ("tables", "mapping", "llm"):
        v = occ[c].to_numpy()
        ax2.barh(ys, v, left=left, color=CC[c], height=0.72, edgecolor="none")
        left += v
    for y, a in zip(ys, d.ATTRS):
        ax2.text(-12, y, d.ALAB[a], ha="right", va="center", fontsize=TICK_LABEL, color=BASELINE_DARK)
        if occ.loc[a, "tables"] > 0:
            ax2.text(occ.loc[a, "total"] + 12, y, f"{occ.loc[a, 'tables']}", ha="left", va="center",
                     fontsize=ANNOTATION, color=CC["tables"], fontweight="bold")
    ax2.set_yticks([])
    ax2.set_ylim(-0.6, len(d.ATTRS) - 0.4)
    ax2.set_xlim(0, 1000)
    ax2.set_xticks([0, 400, 800])
    ax2.tick_params(labelsize=TICK_LABEL, length=2, pad=1)
    for s in ("top", "right", "left"):
        ax2.spines[s].set_visible(False)
    cv.text(446, H - 6, "b  unmapped answers", fontsize=TICK_LABEL, ha="right", va="top", color=BASELINE_DARK,
            fontweight="bold")
    cv.text(446, KEY_H + 4, "answers (number: table limits)", fontsize=LEGEND_LABEL, ha="right", va="bottom",
            color=FOOTNOTE_GREY)
    cv.legend(d.host_handles() + [hatch_handle()], x=18, y_top=yt - gh - 17, ncol=3)
    cv.legend(d.cause_handles(LOSSES), x=392, y_top=KEY_H + 22 + 34, ncol=1)
    strategy_key(cv, y_top=KEY_H - 3)
    return save(cv, "P05_fig6_plus_attribute_causes")


# =========================================================================== P06
@house_style
def P06():
    """Scatter, one point per combination: x = lost to LLM, y = lost to tables; letter = strategy, colour = hosting."""
    H = 250.0
    cv = PointCanvas(W, H)
    ax = cv.axes(46, 42, 330, H - 12)
    C = d.C
    for _, r in C.iterrows():
        col = HOST_COLORS[r.hosting]
        x, y = 100 * r.s_llm, 100 * r.s_tables
        if r.llm_alsoB > 0:
            ax.plot([x, x], [y + 0.5, 100 * (r.s_tables + r.s_llm_alsoB)], color=CC["tables"],
                     linewidth=PATCH_LINEWIDTH, zorder=1)
        ax.text(x, y, r.method, ha="center", va="center", fontsize=ANNOTATION, fontweight="bold",
                color=MUTED_GREY if r.excluded else col, zorder=2)
    ax.set_xscale("symlog", linthresh=5)
    ax.set_xlim(-0.3, 100)
    ax.set_ylim(-1, 30)
    ax.set_xticks([0, 2, 5, 10, 20, 50, 100])
    ax.set_xticklabels(["0", "2", "5", "10", "20", "50", "100"])
    ax.tick_params(labelsize=TICK_LABEL, length=2, pad=1.5)
    ax.set_xlabel("lost to LLM failures (% of finished, symmetric log)", fontsize=TICK_LABEL, labelpad=2)
    ax.set_ylabel("lost to statistics-table limits (%)", fontsize=TICK_LABEL, labelpad=2)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    # annotate the most table-limited combinations
    top = C[~C.excluded].sort_values("s_tables", ascending=False).head(3)
    for _, r in top.iterrows():
        ax.annotate(d.MLAB[r.model], (100 * r.s_llm, 100 * r.s_tables), xytext=(6 if r.s_llm < 0.2 else -6, 0), textcoords="offset points", ha="left" if r.s_llm < 0.2 else "right",
                    fontsize=ANNOTATION, va="center", color=SECONDARY_GREY)
    handles = d.host_handles() + [Patch(facecolor=MUTED_GREY, edgecolor="none", label="withdrawn")]
    cv.legend(handles, x=340, y_top=H - 12, ncol=1)
    cv.text(340, H - 140, "line: up to the share with any\ntable-limit answer (adds the\nLLM failures that also have one)",
            fontsize=LEGEND_LABEL, ha="left", va="top", color=FOOTNOTE_GREY, linespacing=1.0)
    cv.text(340, H - 60, "letter = strategy", fontsize=LEGEND_LABEL, ha="left", va="top", color=FOOTNOTE_GREY)
    lines = [k.replace(" — ", "  ") for k in d.KEY_LINES]
    for n, ln in enumerate(lines):
        cv.text(340, H - 80 - 10 * n, ln.replace("All Generate Evaluate", "All Gen. Eval.").replace(
            "All Generate", "All Gen."), fontsize=LEGEND_LABEL, ha="left", va="top", color=FOOTNOTE_GREY)
    return save(cv, "P06_scatter_llm_vs_tables")


# =========================================================================== P07
@house_style
def P07():
    """Small multiples per strategy: diverging columns per model, up = not the LLM's fault (tables, mapping), down = LLM."""
    H = 296.0
    cv = PointCanvas(W, H)
    top = H - 10 - LABEL_BAND
    ph, gap = 34.0, 4.0
    x0, x1 = 34.0, 452.0
    xs = np.arange(N_COLS) + np.r_[np.zeros(N_COLS - 1), 0.3]
    for i, m in enumerate(d.METHODS):
        yt = top - i * (ph + gap)
        ax = cv.axes(x0, yt - ph, x1, yt)
        up_t = np.array([d.CELL[m][mod].s_tables for mod in d.MODELS])
        up_m = np.array([d.CELL[m][mod].s_mapping for mod in d.MODELS])
        dn = np.array([d.CELL[m][mod].s_llm for mod in d.MODELS])
        wd = np.array([d.CELL[m][mod].excluded for mod in d.MODELS])
        f = lambda v: np.sqrt(v)  # noqa: E731
        ax.bar(xs, f(up_t), width=0.7, color=CC["tables"], edgecolor="none")
        ax.bar(xs, f(up_t + up_m) - f(up_t), bottom=f(up_t), width=0.7, color=CC["mapping"], edgecolor="none")
        ax.bar(xs, -f(dn), width=0.7, color=CC["llm"], edgecolor="none")
        ab = np.array([d.CELL[m][mod].s_llm_alsoB for mod in d.MODELS])
        for x, v_, a_ in zip(xs, dn, ab):
            hatch_ab(ax, x - 0.35, -f(v_), 0.7, f(v_) - f(v_ - a_))
        for x, w in zip(xs, wd):
            if w:
                ax.bar(x, f(0.95) * 2, bottom=-f(0.95), width=0.9, facecolor="none", edgecolor=MUTED_GREY,
                       hatch="xx", linewidth=0)
        ax.axhline(0, color=BASELINE_DARK, linewidth=AXES_LINEWIDTH)
        ax.set_ylim(-f(0.9), f(0.3))
        ax.set_xlim(-0.6, xs[-1] + 0.6)
        ax.set_yticks([-f(0.5), -f(0.1), f(0.1)])
        ax.set_yticklabels(["50", "10", "10"])
        ax.tick_params(labelsize=TICK_LABEL, length=2, pad=1)
        ax.set_xticks([])
        for s in ("top", "right", "bottom"):
            ax.spines[s].set_visible(False)
        cv.text(10, yt - ph / 2, m, fontsize=TICK_LABEL_LARGE, fontweight="bold", ha="center", va="center",
                color=BASELINE_DARK)
    span = (x1 - x0)
    cxs = [x0 + span * (x + 0.6) / (xs[-1] + 1.2) for x in xs]
    model_names_above(cv, cxs, top + 3)
    cv.legend(d.cause_handles(LOSSES, alsoB=True) + [Patch(facecolor=SURFACE, edgecolor=MUTED_GREY, hatch="xx",
                                                           linewidth=0, label="withdrawn")], x=4, y_top=H - 3, ncol=5)
    cv.text(452, KEY_H - 3, "% of finished, square-root axis", fontsize=LEGEND_LABEL, ha="right", va="top",
            color=FOOTNOTE_GREY)
    strategy_key(cv)
    return save(cv, "P07_diverging_columns_per_strategy")


# =========================================================================== P08
@house_style
def P08():
    """Pooled butterfly: rows = strategies A-E then hosted / locally served; left = LLM %, right = mapping + tables %."""
    H = 196.0
    cv = PointCanvas(W, H)
    rows = [(m, d.BY_METHOD.loc[m]) for m in d.METHODS] + [
        (d.HOST_LABEL_SHORT[h], d.BY_HOST.loc[h]) for h in ("hosted", "local")]
    n = len(rows)
    yb, yt = KEY_H + 36, H - 22
    axl = cv.axes(70, yb, 236, yt)
    axr = cv.axes(262, yb, 428, yt)
    ys = np.arange(n)[::-1].astype(float)
    ys[-2:] -= 0.6
    for y, (lab, r) in zip(ys, rows):
        axl.barh(y, -100 * r.s_llm, color=CC["llm"], height=0.7)
        hatch_ab(axl, -100 * r.s_llm, y - 0.35, 100 * r.s_llm_alsoB, 0.7)
        axl.text(-100 * r.s_llm - 1, y, f"{100 * r.s_llm:.1f} ({100 * r.s_llm_alsoB:.1f})", ha="right", va="center",
                 fontsize=ANNOTATION, color=BASELINE_DARK)
        axr.barh(y, 100 * r.s_tables, color=CC["tables"], height=0.7)
        axr.barh(y, 100 * r.s_mapping, left=100 * r.s_tables, color=CC["mapping"], height=0.7)
        axr.text(100 * (r.s_tables + r.s_mapping) + 0.3, y, f"{100 * r.s_tables:.1f} + {100 * r.s_mapping:.1f}",
                 ha="left", va="center", fontsize=ANNOTATION, color=BASELINE_DARK)
        cv.text(64, yb + (yt - yb) * (y + 0.5 + 0.6) / (n + 0.6) - 0.5 * (yt - yb) / (n + 0.6) * 0, lab,
                fontsize=TICK_LABEL_LARGE if len(lab) == 1 else TICK_LABEL, ha="right", va="center",
                fontweight="bold" if len(lab) == 1 else "normal",
                color=BASELINE_DARK if len(lab) == 1 else HOST_COLORS[[h for h in ("hosted", "local")
                                                                       if d.HOST_LABEL_SHORT[h] == lab][0]])
    for ax in (axl, axr):
        ax.set_ylim(ys.min() - 0.6, ys.max() + 0.6)
        ax.set_yticks([])
        ax.tick_params(labelsize=TICK_LABEL, length=2, pad=1)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
    axl.set_xlim(-62, 0)
    axl.set_xticks([-40, -20, 0])
    axl.set_xticklabels(["40", "20", "0"])
    axr.set_xlim(0, 16)
    axr.set_xticks([0, 5, 10, 15])
    axl.axvline(0, color=BASELINE_DARK, linewidth=AXES_LINEWIDTH)
    axr.axvline(0, color=BASELINE_DARK, linewidth=AXES_LINEWIDTH)
    cv.text(236, H - 6, "lost to LLM failures", fontsize=TICK_LABEL, ha="right", va="top", fontweight="bold",
            color=BASELINE_DARK)
    cv.text(262, H - 6, "lost to table limits + mapping gaps", fontsize=TICK_LABEL, ha="left", va="top",
            fontweight="bold", color=BASELINE_DARK)
    cv.text(249, yb - 13, "% of finished individuals (pooled over models or strategies)", fontsize=LEGEND_LABEL,
            ha="center", va="top", color=FOOTNOTE_GREY)
    cv.legend(d.cause_handles(LOSSES, alsoB=True), x=350, y_top=H - 22, ncol=1)
    cv.text(249, yb - 23, "(in brackets: LLM failures that also gave a table-limit answer)", fontsize=LEGEND_LABEL,
            ha="center", va="top", color=FOOTNOTE_GREY)
    strategy_key(cv, y_top=KEY_H - 3)
    return save(cv, "P08_pooled_butterfly")


# =========================================================================== P09
@house_style
def P09():
    """Waterfall per strategy (pooled over models): finished individuals (100%) stepping down through each loss to retained."""
    H = 236.0
    cv = PointCanvas(W, H)
    steps = ["llm", "mapping", "tables"]
    pw, gap, x0 = 77.0, 6.0, 36.0
    yb, yt = KEY_H + 44, H - 16
    for k, m in enumerate(d.METHODS):
        r = d.BY_METHOD.loc[m]
        ax = cv.axes(x0 + k * (pw + gap), yb, x0 + k * (pw + gap) + pw, yt)
        level = 1.0
        ax.bar(0, 1.0, color=SECONDARY_GREY, width=0.8)
        for n, c in enumerate(steps, start=1):
            v = r[f"s_{c}"]
            ax.bar(n, v, bottom=level - v, color=CC[c], width=0.8,
                   edgecolor=MUTED_GREY if c == "incomplete" else "none", linewidth=0.4)
            if c == "llm":
                hatch_ab(ax, n - 0.4, level - v, 0.8, r.s_llm_alsoB)
            ax.plot([n - 1.4, n + 0.4], [level, level], color=MUTED_GREY, linewidth=GRID_LINEWIDTH)
            if v >= 0.005:
                ax.text(n, level - v - 0.015, f"{100 * v:.0f}", ha="center", va="top", fontsize=ANNOTATION,
                        color=BASELINE_DARK)
            level -= v
        ax.bar(4, level, color=CC["retained"], width=0.8, edgecolor=MUTED_GREY, linewidth=0.4)
        ax.text(4, level + 0.015, f"{100 * level:.0f}", ha="center", va="bottom", fontsize=ANNOTATION,
                color=BASELINE_DARK, fontweight="bold")
        ax.set_xlim(-0.6, 4.6)
        ax.set_ylim(0.3, 1.04)
        ax.set_xticks([])
        ax.set_yticks([0.4, 0.6, 0.8, 1.0] if k == 0 else [])
        if k == 0:
            ax.set_yticklabels(["40", "60", "80", "100"])
        ax.tick_params(labelsize=TICK_LABEL, length=2, pad=1)
        for s in ("top", "right") + (("left",) if k else ()):
            ax.spines[s].set_visible(False)
        cv.text(x0 + k * (pw + gap) + pw / 2, H - 4, f"strategy {m}", fontsize=TICK_LABEL, fontweight="bold",
                ha="center", va="top", color=BASELINE_DARK)
    cv.text(8, (yb + yt) / 2, "% of finished", fontsize=TICK_LABEL, rotation=90, ha="center", va="center",
            color=BASELINE_DARK)
    handles = [Patch(facecolor=SECONDARY_GREY, label="finished")] + d.cause_handles(
        ["llm", "mapping", "tables", "retained"], alsoB=True)
    cv.legend(handles, x=36, y_top=yb - 4, ncol=3)
    cv.text(452, yb - 4, "y axis starts at 30%",
            fontsize=LEGEND_LABEL, ha="right", va="top", color=FOOTNOTE_GREY)
    strategy_key(cv)
    return save(cv, "P09_waterfall_per_strategy")


# =========================================================================== P10
@house_style
def P10():
    """Attribute x strategy heatmaps: LLM-failure answers and table-limit answers per 100 finished individuals."""
    H = 230.0
    cv = PointCanvas(W, H)
    ans = d.ANS.merge(d.C[["method"]], left_on="combination", right_index=True)
    gen = d.BY_METHOD.finished
    attrs = d.ATTRS[:-1]  # household size: 2 answers, both LLM -- dropped from the canvas, noted in proposals
    yt = H - 14
    names = {"llm": "LLM-failure answers", "tables": "table-limit answers"}
    for k, (c, vmax) in enumerate((("llm", 0.30), ("tables", 0.06))):
        t = ans[ans.cause == c].pivot_table(index="method", columns="attribute", values="persona",
                                            aggfunc="count", fill_value=0).reindex(index=d.METHODS, columns=attrs,
                                                                                    fill_value=0)
        mat = (t.T / gen).T.to_numpy(float)
        gh = 5 * 12.0
        box = (62, yt - gh, 418, yt)
        ax = cv.axes(*box)
        cells = [[{"v": float(mat[i, j])} for j in range(len(attrs))] for i in range(5)]
        im = render_grid(ax, mat, cells, policy=RateOnlyPolicy(value_key="v", scale=100.0, number_format=".1f"),
                         cmap=heatmap_cmap(), norm=mcolors.Normalize(0, vmax), aspect="auto", fontsize=ANNOTATION)
        bare(ax, frame=False)
        row_letters(cv, [yt - gh * (i + 0.5) / 5 for i in range(5)], 58)
        colorbar(cv, im, (424, yt - gh, 430, yt), "", [0, vmax / 2, vmax])
        cv.text(62, yt + 2, names[c], fontsize=TICK_LABEL, fontweight="bold", ha="left", va="bottom",
                color=BASELINE_DARK)
        yt -= gh + 16
    yt += 12
    cw = 356 / len(attrs)
    for j, a in enumerate(attrs):
        cv.text(62 + cw * (j + 0.5) + 3, yt, d.ALAB[a], fontsize=TICK_LABEL, ha="right", va="top",
                color=BASELINE_DARK, rotation=35, rotation_mode="anchor")
    cv.text(452, H - 3, "unmapped answers per 100 finished individuals", fontsize=LEGEND_LABEL, ha="right",
            va="top", color=FOOTNOTE_GREY)
    strategy_key(cv)
    return save(cv, "P10_attribute_by_strategy_heatmaps")


# =========================================================================== P11
@house_style
def P11():
    """2x2 frame: single attribute vs whole individual  x  LLM vs statistics tables; pooled count + A-E bars per cell."""
    H = 284.0
    cv = PointCanvas(W, H)
    T = d.TOTAL
    sel = int(d.C.loc[~d.C.excluded, "selected"].sum())
    wc_imp = d.WC_IMPOSSIBLE
    cells = {
        ("attr", "llm"): ("one answer unmappable", T.llm, T.finished, d.BY_METHOD.llm, d.BY_METHOD.finished, CC["llm"]),
        ("attr", "tables"): ("one answer outside the table", T.tables, T.finished, d.BY_METHOD.tables,
                             d.BY_METHOD.finished, CC["tables"]),
        ("whole", "llm"): ("impossible individual (R3)", wc_imp["total"], sel, wc_imp["by_method"], d.SEL_BY_METHOD,
                           CC["llm"]),
        ("whole", "tables"): ("combination outside SCB definitions", int(d.C.classc.sum()), sel,
                              d.C.groupby("method").classc.sum().reindex(d.METHODS), d.SEL_BY_METHOD, CC["classc"]),
    }
    cx0, cw, ch = 96.0, 172.0, 96.0
    ytop = H - 30
    cols = ["llm", "tables"]
    rowsk = ["attr", "whole"]
    cv.text(cx0 + cw / 2, H - 6, "caused by the LLM", fontsize=TICK_LABEL_LARGE, fontweight="bold", ha="center",
            va="top", color=BASELINE_DARK)
    cv.text(cx0 + cw + 12 + cw / 2, H - 6, "caused by the statistics tables", fontsize=TICK_LABEL_LARGE,
            fontweight="bold", ha="center", va="top", color=BASELINE_DARK)
    rlab = {"attr": "single attribute\n(validity gate;\nof finished)", "whole": "whole individual\n(judged sample;\nof 100 selected)"}
    for i, rk in enumerate(rowsk):
        y1 = ytop - i * (ch + 12)
        cv.text(4, y1 - ch / 2, rlab[rk], fontsize=TICK_LABEL, ha="left", va="center", color=BASELINE_DARK,
                linespacing=1.0)
        for j, ck in enumerate(cols):
            title, num, den, bym, byden, col = cells[(rk, ck)]
            x0 = cx0 + j * (cw + 12)
            frame = cv.axes(x0, y1 - ch, x0 + cw, y1)
            bare(frame)
            frame.set_facecolor(SURFACE)
            cv.text(x0 + 5, y1 - 4, title, fontsize=TICK_LABEL, ha="left", va="top", color=BASELINE_DARK)
            cv.text(x0 + 5, y1 - 16, f"{int(num):,}".replace(",", " "), fontsize=12.0, fontweight="bold", ha="left",
                    va="top", color=col)
            cv.text(x0 + 5, y1 - 32, f"{100 * num / den:.1f}% of {int(den):,}".replace(",", " "), fontsize=LEGEND_LABEL,
                    ha="left", va="top", color=FOOTNOTE_GREY)
            if (rk, ck) == ("attr", "llm"):
                ab = int(T.llm_alsoB)
                cv.text(x0 + 5, y1 - 44, f"of which {ab}\n({100 * ab / T.llm:.0f}%) also gave\na table-limit answer",
                        fontsize=LEGEND_LABEL, ha="left", va="top", color=FOOTNOTE_GREY, linespacing=1.0)
            ax = cv.axes(x0 + 96, y1 - ch + 6, x0 + cw - 6, y1 - 18)
            sh = (bym / byden).to_numpy(float) * 100
            ax.barh(np.arange(5)[::-1], sh, color=col, height=0.66)
            for y, v in zip(np.arange(5)[::-1], sh):
                ax.text(v + max(sh) * 0.04, y, f"{v:.1f}", va="center", ha="left", fontsize=ANNOTATION, color=BASELINE_DARK)
            ax.set_yticks(np.arange(5)[::-1])
            ax.set_yticklabels(d.METHODS, fontsize=TICK_LABEL, fontweight="bold")
            ax.set_xlim(0, max(sh) * 1.45 if max(sh) > 0 else 1)
            ax.set_xticks([])
            ax.tick_params(length=0, pad=2)
            for s in ("top", "right", "bottom"):
                ax.spines[s].set_visible(False)
            ax.spines["left"].set_linewidth(GRID_LINEWIDTH)
    cv.text(cx0, KEY_H + 3, "bars: % per strategy, pooled over models; the two rows have different denominators",
            fontsize=LEGEND_LABEL, ha="left", va="bottom", color=FOOTNOTE_GREY)
    strategy_key(cv)
    return save(cv, "P11_two_by_two_with_class_c")


# =========================================================================== P12
@house_style
def P12():
    """Marginals only: per model (columns, pooled over strategies) and per strategy (pooled over models), 100% stacked."""
    H = 244.0
    cv = PointCanvas(W, H)
    yb, yt = KEY_H + 36, H - 10 - LABEL_BAND
    ax = cv.axes(30, yb, 322, yt)
    xs = np.arange(N_COLS) + np.r_[np.zeros(N_COLS - 1), 0.4]
    order = ["llm", "mapping", "tables"]
    for x, mod in zip(xs, d.MODELS):
        r = d.BY_MODEL.loc[mod]
        b = 0.0
        for c in order:
            v = r[f"s_{c}"]
            ax.bar(x, v, bottom=b, color=CC[c], width=0.72, edgecolor=MUTED_GREY if c == "incomplete" else "none",
                   linewidth=0.3)
            if c == "llm":
                hatch_ab(ax, x - 0.36, v - r.s_llm_alsoB, 0.72, r.s_llm_alsoB)
            b += v
        ax.text(x, b + 0.01, PCT(r.s_tables), ha="center", va="bottom", fontsize=ANNOTATION, color=CC["tables"],
                fontweight="bold")
    ax.set_xlim(-0.6, xs[-1] + 0.6)
    ax.set_ylim(0, 0.9)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8])
    ax.set_yticklabels(["0", "20", "40", "60", "80"])
    ax.set_xticks([])
    ax.tick_params(labelsize=TICK_LABEL, length=2, pad=1)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    cv.text(10, (yb + yt) / 2, "lost, % of finished", fontsize=TICK_LABEL, rotation=90, ha="center", va="center",
            color=BASELINE_DARK)
    model_names_above(cv, [30 + 292 * (x + 0.6) / (xs[-1] + 1.2) for x in xs], yt + 3)
    ax2 = cv.axes(350, yb, 446, yt + 40)
    ys = np.arange(5)[::-1]
    for y, m in zip(ys, d.METHODS):
        r = d.BY_METHOD.loc[m]
        b = 0.0
        for c in order:
            v = r[f"s_{c}"]
            ax2.barh(y, v, left=b, color=CC[c], height=0.7, edgecolor=MUTED_GREY if c == "incomplete" else "none",
                     linewidth=0.3)
            if c == "llm":
                hatch_ab(ax2, v - r.s_llm_alsoB, y - 0.35, r.s_llm_alsoB, 0.7)
            b += v
        ax2.text(b + 0.01, y, PCT(r.s_tables), ha="left", va="center", fontsize=ANNOTATION, color=CC["tables"],
                 fontweight="bold")
    ax2.set_yticks(ys)
    ax2.set_yticklabels(d.METHODS, fontsize=TICK_LABEL_LARGE, fontweight="bold")
    ax2.set_xlim(0, 0.6)
    ax2.set_xticks([0, 0.25, 0.5])
    ax2.set_xticklabels(["0", "25", "50"])
    ax2.tick_params(labelsize=TICK_LABEL, length=2, pad=1)
    for s in ("top", "right"):
        ax2.spines[s].set_visible(False)
    cv.text(398, yt + 46, "by strategy", fontsize=TICK_LABEL, fontweight="bold", ha="center", va="bottom",
            color=BASELINE_DARK)
    cv.legend(d.cause_handles(order, alsoB=True), x=30, y_top=yb - 12, ncol=3)
    cv.legend(d.host_handles(), x=4, y_top=H - 3, ncol=2)
    cv.text(446, H - 4, "number: table limits %", fontsize=LEGEND_LABEL, ha="right", va="top", color=FOOTNOTE_GREY)
    strategy_key(cv, y_top=KEY_H - 5)
    return save(cv, "P12_marginals_model_and_strategy")


# =========================================================================== P13
@house_style
def P13():
    """Fig 6 retention heatmap with a cause strip per cell (composition of the lost), + separate class C dot grid."""
    H = 300.0
    cv = PointCanvas(W, H)
    yt = H - 8 - LABEL_BAND
    g = Grid(24, 398, yt, 20.0, row_gap=2, col_gap=2)
    cmap = heatmap_cmap()
    norm = mcolors.Normalize(0, 1)
    for i, m in enumerate(d.METHODS):
        for j, mod in enumerate(d.MODELS):
            r = d.CELL[m][mod]
            ax = cv.axes(*g.box(i, j))
            rgb = cmap(norm(r.s_retained))[:3]
            ax.add_patch(Rectangle((0, 0.3), 1, 0.7, facecolor=rgb, edgecolor="none"))
            ax.text(0.5, 0.65, PCT(r.s_retained), ha="center", va="center", fontsize=ANNOTATION,
                    color=text_color_for_rgb(rgb), transform=ax.transAxes)
            lost = r.llm + r.mapping + r.tables
            if lost:
                stack_h(ax, [r.llm / lost, r.mapping / lost, r.tables / lost],
                        [CC["llm"], CC["mapping"], CC["tables"]], y0=0.0, h=0.26)
                hatch_ab(ax, (r.llm - r.llm_alsoB) / lost, 0.0, r.llm_alsoB / lost, 0.26)
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            bare(ax, frame=False)
            if r.excluded:
                ax.add_patch(Rectangle((0, 0.3), 1, 0.7, facecolor="none", edgecolor=SURFACE, hatch=HATCH, linewidth=0))
    model_names_above(cv, g.cx(), g.y_top + 3)
    row_letters(cv, g.cy(), g.x0 - 4)
    from matplotlib.cm import ScalarMappable
    colorbar(cv, ScalarMappable(norm=norm, cmap=cmap), (404, g.y_bot, 410, g.y_top), "", [0, 0.5, 1.0])
    cv.text(452, g.y_top + 4, "retained %", fontsize=LEGEND_LABEL, ha="right", va="bottom", color=FOOTNOTE_GREY)
    # class C, separate grid of dots
    yc = g.y_bot - 18
    g2 = Grid(24, 398, yc, 9.0, row_gap=1, col_gap=2)
    ax = cv.axes(g2.x0, g2.y_bot - 1, g2.x1, g2.y_top + 1)
    ax.set_xlim(g2.x0, g2.x1)
    ax.set_ylim(g2.y_bot - 1, g2.y_top + 1)
    for i, m in enumerate(d.METHODS):
        for j, mod in enumerate(d.MODELS):
            r = d.CELL[m][mod]
            x, y = g2.cx()[j], g2.cy()[i]
            if r.excluded:
                ax.plot([x - 3, x + 3], [y - 3, y + 3], color=MUTED_GREY, linewidth=GRID_LINEWIDTH)
                ax.plot([x - 3, x + 3], [y + 3, y - 3], color=MUTED_GREY, linewidth=GRID_LINEWIDTH)
            elif r.classc > 0:
                ax.scatter([x], [y], s=4 + 5 * r.classc, color=CC["classc"], edgecolor="none")
                ax.text(x + 5, y, f"{int(r.classc)}", fontsize=ANNOTATION, va="center", ha="left", color=BASELINE_DARK)
            else:
                ax.scatter([x], [y], s=1.2, color=MUTED_GREY, edgecolor="none")
    bare(ax, frame=False)
    row_letters(cv, g2.cy(), g2.x0 - 4)
    cv.text(24, yc + 4, "combinations outside SCB definitions, individuals per 100 selected (judged sample)",
            fontsize=LEGEND_LABEL, ha="left", va="bottom", color=BASELINE_DARK, fontweight="bold")
    cv.legend(d.cause_handles(LOSSES, alsoB=True), x=24, y_top=g2.y_bot - 4, ncol=4)
    cv.text(452, g2.y_bot - 4, "strip: share of the lost", fontsize=LEGEND_LABEL, ha="right", va="top",
            color=FOOTNOTE_GREY)
    cv.legend(d.host_handles() + [hatch_handle()], x=4, y_top=H - 3, ncol=3)
    strategy_key(cv)
    return save(cv, "P13_fig6_cause_strip_and_class_c")


# =========================================================================== P14
@house_style
def P14():
    """Mosaic: one band per strategy (height = finished individuals), split by cause; class C as a separate strip."""
    H = 220.0
    cv = PointCanvas(W, H)
    yb, yt = KEY_H + 30, H - 20
    ax = cv.axes(24, yb, 360, yt)
    gen = d.BY_METHOD.finished.to_numpy(float)
    hs = gen / gen.sum()
    gapf = 0.012
    y = 1.0
    order = ["llm", "mapping", "tables", "retained"]
    cents = []
    for m, h in zip(d.METHODS, hs):
        r = d.BY_METHOD.loc[m]
        y0 = y - h + gapf / 2
        x = 0.0
        for c in order:
            v = r[f"s_{c}"]
            ax.add_patch(Rectangle((x, y0), v, h - gapf, facecolor=CC[c], edgecolor="none"))
            if c == "llm":
                hatch_ab(ax, x + v - r.s_llm_alsoB, y0, r.s_llm_alsoB, h - gapf)
            if c in ("llm", "tables", "retained") and v > 0.035:
                rgb = mcolors.to_rgb(CC[c])
                ax.text(x + v / 2, y0 + (h - gapf) / 2, f"{100 * v:.0f}", ha="center", va="center", fontsize=ANNOTATION,
                        color=text_color_for_rgb(rgb))
            x += v
        cents.append(y0 + (h - gapf) / 2)
        y -= h
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1])
    ax.set_xticklabels(["0", "25", "50", "75", "100%"])
    ax.set_yticks([])
    ax.tick_params(labelsize=TICK_LABEL, length=2, pad=1)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    for c, m, gn in zip(cents, d.METHODS, gen):
        cv.text(20, yb + (yt - yb) * c, m, fontsize=TICK_LABEL_LARGE, fontweight="bold", ha="right", va="center",
                color=BASELINE_DARK)
    cv.text(192, H - 6, "finished individuals (band height) by cause of loss", fontsize=TICK_LABEL,
            fontweight="bold", ha="center", va="top", color=BASELINE_DARK)
    # class C strip
    ax2 = cv.axes(384, yb, 446, yt)
    sel = d.SEL_BY_METHOD.to_numpy(float)
    cc = d.C.groupby("method").classc.sum().reindex(d.METHODS).to_numpy(float)
    yy = np.arange(5)[::-1]
    ax2.barh(yy, 100 * cc / sel, color=CC["classc"], height=0.6)
    for y_, v, n in zip(yy, 100 * cc / sel, cc):
        ax2.text(v + 0.15, y_, f"{int(n)}", fontsize=ANNOTATION, va="center", ha="left", color=BASELINE_DARK)
    ax2.set_yticks(yy)
    ax2.set_yticklabels(d.METHODS, fontsize=TICK_LABEL, fontweight="bold")
    ax2.set_xlim(0, 5)
    ax2.set_xticks([0, 2, 4])
    ax2.tick_params(labelsize=TICK_LABEL, length=2, pad=1)
    for s in ("top", "right"):
        ax2.spines[s].set_visible(False)
    cv.text(446, H - 6, "outside SCB\ndefinitions", fontsize=TICK_LABEL, fontweight="bold", ha="right", va="top",
            color=BASELINE_DARK, linespacing=0.95)
    cv.text(446, yb - 12, "% of selected (number: individuals)", fontsize=LEGEND_LABEL, ha="right", va="top", color=FOOTNOTE_GREY)
    cv.legend(d.cause_handles(order, alsoB=True), x=24, y_top=yb - 13, ncol=3)
    strategy_key(cv, y_top=KEY_H - 5)
    return save(cv, "P14_mosaic_per_strategy_with_class_c")


# =========================================================================== round 2 (the author feedback 2026-10-19)
SQ_MAX = 0.85                       # largest loss share in any cell is 0.83 (Llama3.1 8B, A)
SQ_TICKS = (0.05, 0.25, 0.75)


def sq(v):
    """Square-root position on [0, 1] for a share in [0, SQ_MAX]."""
    return np.sqrt(np.clip(v, 0, None)) / np.sqrt(SQ_MAX)


def lane_cell(ax, r, *, number=True):
    """Three horizontal lanes (LLM top, mapping, tables bottom) on a shared square-root x scale."""
    for t in SQ_TICKS:
        ax.axvline(sq(t), color=GRID_RULE, linewidth=GRID_LINEWIDTH, zorder=0)
    for k, c in enumerate(LOSSES):
        v = r[f"s_{c}"]
        y = 2 - k
        ax.barh(y, sq(v), height=0.76, color=CC[c], edgecolor="none", zorder=2)
        if c == "llm":
            x0_ = sq(v - r.s_llm_alsoB)
            hatch_ab(ax, x0_, y - 0.38, sq(v) - x0_, 0.76)
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.5, 2.5)
    if number:
        ax.text(0.98, 0.0, PCT(r.s_tables), transform=ax.transAxes, ha="right", va="bottom",
                fontsize=ANNOTATION, color=CC["tables"], fontweight="bold", zorder=4)
    if r.excluded:
        draw_withdrawn_cell(ax)
    else:
        bare(ax)


def sq_tick_labels(cv, g, j=0):
    """Tick labels of the square-root x scale under one column of the bottom row."""
    x0, y0, x1, _ = g.box(N_ROWS - 1, j)
    for t in SQ_TICKS:
        cv.text(x0 + (x1 - x0) * sq(t), y0 - 1.5, f"{100 * t:.0f}", fontsize=TICK_LABEL, ha="center", va="top",
                color=SECONDARY_GREY)


def strategy_bars(cv, box, ys=None, *, xmax=0.6, numbers="tables", ticks=(0, 0.25, 0.5)):
    """P12's by-strategy panel: stacked losses per strategy (LLM with A+B slice, mapping, tables, incomplete)."""
    order = ["llm", "mapping", "tables"]
    ax = cv.axes(*box)
    yy = np.arange(5)[::-1] if ys is None else ys
    for y, m in zip(yy, d.METHODS):
        r = d.BY_METHOD.loc[m]
        b = 0.0
        for c in order:
            v = r[f"s_{c}"]
            ax.barh(y, v, left=b, color=CC[c], height=0.7, edgecolor=MUTED_GREY if c == "incomplete" else "none",
                    linewidth=0.3)
            if c == "llm":
                hatch_ab(ax, v - r.s_llm_alsoB, y - 0.35, r.s_llm_alsoB, 0.7)
            b += v
        if numbers == "tables":
            ax.text(b + 0.01, y, PCT(r.s_tables), ha="left", va="center", fontsize=ANNOTATION, color=CC["tables"],
                    fontweight="bold")
        else:
            ax.text(r.s_llm / 2, y, f"{100 * r.s_llm:.1f}", ha="center", va="center", fontsize=ANNOTATION,
                    color=SURFACE)
            ax.text(b + 0.006, y, f"{100 * r.s_mapping:.1f}", ha="left", va="center", fontsize=ANNOTATION,
                    color=CC["mapping"], fontweight="bold")
            ax.text(b + 0.05, y, f"{100 * r.s_tables:.1f}", ha="left", va="center", fontsize=ANNOTATION,
                    color=CC["tables"], fontweight="bold")
            ax.text(xmax, y, f"{100 * r.s_retained:.0f}", ha="right", va="center", fontsize=ANNOTATION,
                    color=SECONDARY_GREY)
    ax.set_ylim(min(yy) - 0.5, max(yy) + 0.5)
    ax.set_yticks([])
    ax.set_xlim(0, xmax)
    ax.set_xticks(list(ticks))
    ax.set_xticklabels([f"{100 * t:.0f}" for t in ticks])
    ax.tick_params(labelsize=TICK_LABEL, length=2, pad=1)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    return ax


# =========================================================================== P15
@house_style
def P15():
    """P12's by-strategy panel alone at full width: stacked losses per strategy, LLM % inside, mapping and table % at the end, retained % at right."""
    H = 150.0
    cv = PointCanvas(W, H)
    yb, yt = KEY_H + 34, H - 22
    strategy_bars(cv, (24, yb, 452, yt), xmax=0.62, numbers="all", ticks=(0, 0.1, 0.2, 0.3, 0.4, 0.5))
    for i, m in enumerate(d.METHODS):
        cv.text(20, yt - (yt - yb) * (i + 0.5) / 5, m, fontsize=TICK_LABEL_LARGE, fontweight="bold", ha="right",
                va="center", color=BASELINE_DARK)
    cv.legend(d.cause_handles(["llm", "mapping", "tables"], alsoB=True), x=4, y_top=H - 3, ncol=5)
    cv.text(452, yt + 2, "retained %", fontsize=LEGEND_LABEL, ha="right", va="bottom", color=SECONDARY_GREY)
    cv.text(238, yb - 12, "lost, % of finished (pooled over models)", fontsize=LEGEND_LABEL, ha="center", va="top",
            color=FOOTNOTE_GREY)
    strategy_key(cv, y_top=KEY_H - 3)
    return save(cv, "P15_by_strategy_stacked_losses")


def lane_grid(cv, g):
    for i, m in enumerate(d.METHODS):
        for j, mod in enumerate(d.MODELS):
            lane_cell(cv.axes(*g.box(i, j)), d.CELL[m][mod])
    model_names_above(cv, g.cx(), g.y_top + 3)
    row_letters(cv, g.cy(), g.x0 - 5)


# =========================================================================== P16
@house_style
def P16():
    """P02 with an explicit shared x axis: three horizontal lanes per cell on one square-root x scale (ticks 5, 25, 75%, gridlines in every cell); table % printed."""
    H = 298.0
    cv = PointCanvas(W, H)
    g = Grid(24, 452, H - 18 - LABEL_BAND, 31.0, row_gap=3)
    lane_grid(cv, g)
    cv.legend(d.cause_handles(LOSSES, alsoB=True) + [withdrawn_handle("withdrawn")], x=4, y_top=H - 3, ncol=5)
    cv.text(452, g.y_bot - 2, "bar length: % of finished, square-root scale shared by all cells, gridlines at 5, 25 and 75%;"
            " number: table-limit %",
            fontsize=LEGEND_LABEL, ha="right", va="top", color=FOOTNOTE_GREY)
    strategy_key(cv)
    return save(cv, "P16_lane_grid_shared_x")


# =========================================================================== P17
@house_style
def P17():
    """P16 lane grid (a) beside the P15 by-strategy summary (b), rows aligned to the grid rows."""
    H = 300.0
    cv = PointCanvas(W, H)
    g = Grid(22, 334, H - 30 - LABEL_BAND, 29.0, row_gap=3)
    lane_grid(cv, g)
    ys = np.array([4 - i for i in range(5)], float)
    # panel b shares the grid's row geometry: its axes span the grid height, 5 equal rows
    strategy_bars(cv, (360, g.y_bot - 0.5, 448, g.y_top + 0.5), ys=ys, xmax=0.6, numbers="tables")
    cv.text(350, g.y_top + 8, "b  lost by strategy,\n    % of finished", fontsize=TICK_LABEL, fontweight="bold", ha="left",
            va="bottom", color=BASELINE_DARK, linespacing=1.0)
    cv.text(4, g.y_top + 8, "a", fontsize=TICK_LABEL, fontweight="bold", ha="left", va="bottom", color=BASELINE_DARK)
    for y, m in zip(g.cy(), d.METHODS):
        cv.text(356, y, m, fontsize=TICK_LABEL_LARGE, fontweight="bold", ha="right", va="center", color=BASELINE_DARK)
    cv.legend(d.cause_handles(["llm", "mapping", "tables"], alsoB=True) + [withdrawn_handle("withdrawn")],
              x=4, y_top=H - 3, ncol=4)
    cv.text(22, g.y_bot - 3, "a: square-root length, gridlines 5, 25, 75%; number: table-limit %",
            fontsize=LEGEND_LABEL, ha="left", va="top", color=FOOTNOTE_GREY)
    strategy_key(cv)
    return save(cv, "P17_lane_grid_plus_strategy_panel")


# =========================================================================== P18
@house_style
def P18():
    """One stacked horizontal bar per cell (LLM with A+B slice, mapping, tables) on a shared linear x scale 0-85%; table % printed."""
    H = 274.0
    cv = PointCanvas(W, H)
    g = Grid(24, 452, H - 18 - LABEL_BAND, 27.0, row_gap=3)
    xm = SQ_MAX
    for i, m in enumerate(d.METHODS):
        for j, mod in enumerate(d.MODELS):
            r = d.CELL[m][mod]
            ax = cv.axes(*g.box(i, j))
            for t in (0.25, 0.5, 0.75):
                ax.axvline(t / xm, color=GRID_RULE, linewidth=GRID_LINEWIDTH, zorder=0)
            x = 0.0
            for c in LOSSES:
                v = r[f"s_{c}"] / xm
                ax.add_patch(Rectangle((x, 0.5), v, 0.42, facecolor=CC[c], edgecolor="none", zorder=2))
                if c == "llm":
                    hatch_ab(ax, x + v - r.s_llm_alsoB / xm, 0.5, r.s_llm_alsoB / xm, 0.42)
                x += v
            ax.text(0.98, 0.02, PCT(r.s_tables), ha="right", va="bottom", fontsize=ANNOTATION, color=CC["tables"],
                    fontweight="bold", transform=ax.transAxes)
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            if r.excluded:
                draw_withdrawn_cell(ax)
            else:
                bare(ax)
    model_names_above(cv, g.cx(), g.y_top + 3)
    row_letters(cv, g.cy(), g.x0 - 5)
    cv.legend(d.cause_handles(LOSSES, alsoB=True) + [withdrawn_handle("withdrawn")], x=4, y_top=H - 3, ncol=5)
    cv.text(452, g.y_bot - 2, "bar length: % of finished, linear 0 to 85% shared by all cells, gridlines at 25, 50 and 75%;"
            " number: table-limit %",
            fontsize=LEGEND_LABEL, ha="right", va="top", color=FOOTNOTE_GREY)
    strategy_key(cv)
    return save(cv, "P18_stacked_bar_per_cell_linear")


# =========================================================================== P19
@house_style
def P19():
    """The other reading of 'use the x axis': causes side by side along x as three columns per cell, square-root height; table % printed."""
    H = 298.0
    cv = PointCanvas(W, H)
    g = Grid(24, 452, H - 18 - LABEL_BAND, 31.0, row_gap=3)
    for i, m in enumerate(d.METHODS):
        for j, mod in enumerate(d.MODELS):
            r = d.CELL[m][mod]
            ax = cv.axes(*g.box(i, j))
            for t in SQ_TICKS:
                ax.axhline(sq(t), color=GRID_RULE, linewidth=GRID_LINEWIDTH, zorder=0)
            for k, c in enumerate(LOSSES):
                v = r[f"s_{c}"]
                ax.bar(k, sq(v), width=0.78, color=CC[c], edgecolor="none", zorder=2)
                if c == "llm":
                    y0_ = sq(v - r.s_llm_alsoB)
                    hatch_ab(ax, k - 0.39, y0_, 0.78, sq(v) - y0_)
            ax.text(0.98, 0.98, PCT(r.s_tables), transform=ax.transAxes, ha="right", va="top", fontsize=ANNOTATION,
                    color=CC["tables"], fontweight="bold", zorder=4)
            ax.set_xlim(-0.5, 3.6)
            ax.set_ylim(0, 1)
            if r.excluded:
                draw_withdrawn_cell(ax)
            else:
                bare(ax)
    model_names_above(cv, g.cx(), g.y_top + 3)
    row_letters(cv, g.cy(), g.x0 - 5)
    cv.legend(d.cause_handles(LOSSES, alsoB=True) + [withdrawn_handle("withdrawn")], x=4, y_top=H - 3, ncol=5)
    cv.text(452, g.y_bot - 2, "height: % of finished, square-root scale (gridlines 5, 25, 75%); number: table-limit %",
            fontsize=LEGEND_LABEL, ha="right", va="top", color=FOOTNOTE_GREY)
    strategy_key(cv)
    return save(cv, "P19_cause_columns_per_cell")


# =========================================================================== round 3: log10 x axis
#: Axis start of the log variants. The smallest possible non-zero share is 1 individual over the largest
#: finished pool (1 / 488 = 0.2%, Qwen 3.5 Flash E); the floor is the decade below it, so every
#: non-zero value sits right of the floor and the gridlines fall on whole decades (1, 10, 100%).
LOG_FLOOR = 0.001
assert LOG_FLOOR < 1 / d.C.finished.max()
assert d.C[[f"s_{c}" for c in LOSSES]].to_numpy()[d.C[[f"s_{c}" for c in LOSSES]].to_numpy() > 0].min() > LOG_FLOOR
LOG_TICKS = (0.01, 0.1, 1.0)


def lg(v):
    """Position on [0, 1] of a share on the log10 axis from LOG_FLOOR to 100%."""
    return (np.log10(v) - np.log10(LOG_FLOOR)) / -np.log10(LOG_FLOOR)


def zero_mark(ax, x, y, c):
    """A true zero: an open marker at the floor, never a bar."""
    ax.plot([x], [y], marker="o", ms=2.6, mfc=SURFACE, mec=CC[c], mew=0.6, ls="none", zorder=3, clip_on=False)


def log_cell(ax, r, *, dots=False):
    for t in LOG_TICKS:
        ax.axvline(lg(t), color=GRID_RULE, linewidth=GRID_LINEWIDTH, zorder=0)
    for k, c in enumerate(LOSSES):
        v = r[f"s_{c}"]
        y = 2 - k
        if v <= 0:
            zero_mark(ax, 0.04, y, c)
            continue
        if dots:
            ax.plot([0, lg(v)], [y, y], color=GRID_RULE, linewidth=GRID_LINEWIDTH, zorder=1)
            ax.plot([lg(v)], [y], marker="o", ms=3.6, color=CC[c], mec=SURFACE, mew=0.3, ls="none", zorder=3)
            if c == "llm" and r.s_llm_alsoB > 0:
                # the A+B share as its own hatched-face dot on the same axis
                ax.plot([lg(r.s_llm_alsoB)], [y], marker="o", ms=3.6, mfc=CC["tables"], mec=CC["llm"], mew=0.8,
                        ls="none", zorder=3)
        else:
            ax.barh(y, lg(v), height=0.76, color=CC[c], edgecolor="none", zorder=2)
            if c == "llm" and r.s_llm_alsoB > 0:
                x0_ = lg(max(v - r.s_llm_alsoB, LOG_FLOOR))
                hatch_ab(ax, x0_, y - 0.38, lg(v) - x0_, 0.76)
    ax.set_xlim(0, 1.36)  # right margin holds the table-limit number
    ax.set_ylim(-0.5, 2.5)
    ax.text(0.98, 0.0, PCT(r.s_tables), transform=ax.transAxes, ha="right", va="bottom", fontsize=ANNOTATION,
            color=CC["tables"], fontweight="bold", zorder=4)
    if r.excluded:
        draw_withdrawn_cell(ax)
    else:
        bare(ax)


def log_grid(cv, g, *, dots=False):
    for i, m in enumerate(d.METHODS):
        for j, mod in enumerate(d.MODELS):
            log_cell(cv.axes(*g.box(i, j)), d.CELL[m][mod], dots=dots)
    model_names_above(cv, g.cx(), g.y_top + 3)
    row_letters(cv, g.cy(), g.x0 - 5)


def zero_handle():
    return Line2D([], [], marker="o", ls="none", ms=3.6, mfc=SURFACE, mec=SECONDARY_GREY, mew=0.6, label="zero")


LOG_NOTE = "log10 x axis from 0.1% (floor) to 100%, gridlines at 1, 10, 100%; open circle = 0; number: table-limit %"


# =========================================================================== P20
@house_style
def P20():
    """P16 on a shared log10 x axis (floor 0.1%): three horizontal lanes per cell, zeros as open circles at the floor."""
    H = 298.0
    cv = PointCanvas(W, H)
    g = Grid(24, 452, H - 18 - LABEL_BAND, 31.0, row_gap=3)
    log_grid(cv, g)
    cv.legend(d.cause_handles(LOSSES, alsoB=True) + [zero_handle(), withdrawn_handle("withdrawn")], x=4,
              y_top=H - 3, ncol=6)
    cv.text(452, g.y_bot - 2, LOG_NOTE, fontsize=LEGEND_LABEL, ha="right", va="top", color=FOOTNOTE_GREY)
    strategy_key(cv)
    return save(cv, "P20_lane_grid_log_x")


# =========================================================================== P21
@house_style
def P21():
    """P20 log grid (a) beside the linear by-strategy summary (b), rows aligned."""
    H = 300.0
    cv = PointCanvas(W, H)
    g = Grid(22, 334, H - 30 - LABEL_BAND, 29.0, row_gap=3)
    log_grid(cv, g)
    ys = np.array([4 - i for i in range(5)], float)
    strategy_bars(cv, (360, g.y_bot - 0.5, 448, g.y_top + 0.5), ys=ys, xmax=0.6, numbers="tables")
    cv.text(350, g.y_top + 8, "b  lost by strategy,\n    % of finished", fontsize=TICK_LABEL, fontweight="bold",
            ha="left", va="bottom", color=BASELINE_DARK, linespacing=1.0)
    cv.text(4, g.y_top + 8, "a", fontsize=TICK_LABEL, fontweight="bold", ha="left", va="bottom", color=BASELINE_DARK)
    for y, m in zip(g.cy(), d.METHODS):
        cv.text(356, y, m, fontsize=TICK_LABEL_LARGE, fontweight="bold", ha="right", va="center", color=BASELINE_DARK)
    cv.legend(d.cause_handles(["llm", "mapping", "tables"], alsoB=True)
              + [zero_handle(), withdrawn_handle("withdrawn")], x=4, y_top=H - 3, ncol=4)
    cv.text(22, g.y_bot - 3, "a: log10 x from 0.1% floor, gridlines 1, 10, 100%; open circle = 0; b: linear",
            fontsize=LEGEND_LABEL, ha="left", va="top", color=FOOTNOTE_GREY)
    strategy_key(cv)
    return save(cv, "P21_log_grid_plus_strategy_panel")


# =========================================================================== P22
@house_style
def P22():
    """Dot version of P20: one dot per cause on the log10 axis (no bar length from the floor); A+B as a pink dot ringed in black on the LLM lane."""
    H = 298.0
    cv = PointCanvas(W, H)
    g = Grid(24, 452, H - 18 - LABEL_BAND, 31.0, row_gap=3)
    log_grid(cv, g, dots=True)
    ab = Line2D([], [], marker="o", ls="none", ms=3.6, mfc=CC["tables"], mec=CC["llm"], mew=0.8,
                label="LLM failure + table limit")
    dots = [Line2D([], [], marker="o", ls="none", ms=3.6, color=CC[c], label=d.CAUSE_LABEL[c]) for c in LOSSES]
    cv.legend([dots[0], ab, dots[1], dots[2], zero_handle(), withdrawn_handle("withdrawn")], x=4, y_top=H - 3, ncol=6)
    cv.text(452, g.y_bot - 2, LOG_NOTE, fontsize=LEGEND_LABEL, ha="right", va="top", color=FOOTNOTE_GREY)
    strategy_key(cv)
    return save(cv, "P22_dot_grid_log_x")


# =========================================================================== round 4: exclusive A/B groups
#: P23 lane order, top to bottom: LLM failure only, LLM failure + table limit, table limit only, so the
#: mixed group sits between its two parents.
G_LABEL = {"llm_only": "LLM failure only", "both": "LLM failure + table limit", "tables_only": "table limit only"}
G_EDGE = {"llm_only": CC["llm"], "both": CC["llm"], "tables_only": CC["tables"]}
ZERO_X = -0.09          # the "0" slot, left of the axis break
X_LO = -0.18            # cell x range: [X_LO, 1.04]; 0 = the 0.1% floor, 1 = 100%


def group_bar(ax, k, x0, y, w, h):
    if k == "both":
        hatch_ab(ax, x0, y - h / 2, w, h)
    else:
        ax.barh(y, w, left=x0, height=h, color=CC["llm"] if k == "llm_only" else CC["tables"], edgecolor="none",
                zorder=2)


def group_cell(ax, r):
    for t in LOG_TICKS:
        ax.axvline(lg(t), color=GRID_RULE, linewidth=GRID_LINEWIDTH, zorder=0)
    ax.axvline(-0.035, color=GRID_RULE, linewidth=GRID_LINEWIDTH, linestyle=(0, (1, 1)), zorder=0)
    for k, key in enumerate(d.GROUPS):
        v = r[f"sg_{key}"]
        y = 2 - k
        if v <= 0:
            ax.plot([ZERO_X], [y], marker="o", ms=2.6, mfc=SURFACE, mec=G_EDGE[key], mew=0.6, ls="none", zorder=3)
        else:
            group_bar(ax, key, 0.0, y, lg(v), 0.76)
    ax.set_xlim(X_LO, 1.04)
    ax.set_ylim(-0.5, 2.5)
    if r.excluded:
        draw_withdrawn_cell(ax)
    else:
        bare(ax)


@house_style
def P23():
    """P21 rebuilt on three mutually exclusive groups of rejected finished individuals: LLM failure only, LLM failure + table limit, table limit only (each its own lane and its own bar); log10 x with 0 / 1 / 10 / 100 tick labels and an axis break; mapping-gap-only individuals not drawn."""
    H = 300.0
    cv = PointCanvas(W, H)
    g = Grid(22, 352, H - 40 - LABEL_BAND, 24.0, row_gap=3)
    for i, m in enumerate(d.METHODS):
        for j, mod in enumerate(d.MODELS):
            group_cell(cv.axes(*g.box(i, j)), d.CELL[m][mod])
    model_names_above(cv, g.cx(), g.y_top + 3)
    row_letters(cv, g.cy(), g.x0 - 5)
    # tick labels under the bottom row, rotated so the four fit a 23 pt cell; break mark on the axis
    span = 1.04 - X_LO
    for j in (0,):  # one labelled axis (first column, bottom row); every cell shares it
        x0, y0, x1, _ = g.box(N_ROWS - 1, j)
        pos = lambda u: x0 + (x1 - x0) * (u - X_LO) / span  # noqa: E731
        for u, lab in ((ZERO_X, "0"), (lg(0.01), "1"), (lg(0.1), "10"), (lg(1.0), "100")):
            cv.text(pos(u), y0 - 1.5, lab, fontsize=TICK_LABEL, rotation=90, ha="center", va="top",
                    color=SECONDARY_GREY)
        bx = pos(-0.035)
        for dx in (-0.7, 0.7):
            ln = Line2D([(bx + dx - 0.8) / W, (bx + dx + 0.8) / W], [(y0 - 1.6) / H, (y0 + 1.6) / H],
                        color=BASELINE_DARK, linewidth=PATCH_LINEWIDTH, transform=cv.figure.transFigure)
            cv.figure.add_artist(ln)
    # panel b: three separate bars per strategy, linear % of finished, count at the bar end
    ax = cv.axes(374, g.y_bot - 0.5, 446, g.y_top + 0.5)
    xmax = 0.40
    for i, m in enumerate(d.METHODS):
        r = d.BY_METHOD_G.loc[m]
        yc = 4 - i
        for k, key in enumerate(d.GROUPS):
            n = int(r[f"g_{key}"])
            v = n / r.finished
            y = yc + 0.28 - 0.28 * k
            if n:
                group_bar(ax, key, 0.0, y, v, 0.24)
            ax.text(v + 0.008, y, f"{n}", ha="left", va="center", fontsize=ANNOTATION,
                    color=BASELINE_DARK if key != "tables_only" else CC["tables"])
    ax.set_ylim(-0.5, 4.5)
    ax.set_yticks([])
    ax.set_xlim(0, xmax)
    ax.set_xticks([0, 0.2, 0.4])
    ax.set_xticklabels(["0", "20", "40"])
    ax.tick_params(labelsize=TICK_LABEL, length=2, pad=1)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for y, m in zip(g.cy(), d.METHODS):
        cv.text(370, y, m, fontsize=TICK_LABEL_LARGE, fontweight="bold", ha="right", va="center", color=BASELINE_DARK)
    cv.text(362, g.y_top + 8, "b  by strategy, % of\n    finished (number:\n    individuals)", fontsize=TICK_LABEL,
            fontweight="bold", ha="left", va="bottom", color=BASELINE_DARK, linespacing=1.0)
    cv.text(4, g.y_top + 8, "a", fontsize=TICK_LABEL, fontweight="bold", ha="left", va="bottom", color=BASELINE_DARK)
    T = d.GROUP_TOTAL
    fin = int(d.TOTAL.finished)

    def lab(k):
        return f"{G_LABEL[k]}: {T[k]:,} ({100 * T[k] / fin:.1f}%)".replace(",", " ")

    from matplotlib.patches import Patch as _P
    hs = [_P(facecolor=CC["llm"], edgecolor="none", label=lab("llm_only")),
          _P(facecolor=CC["llm"], edgecolor=CC["tables"], hatch="////", linewidth=0, label=lab("both")),
          _P(facecolor=CC["tables"], edgecolor="none", label=lab("tables_only")),
          zero_handle(), withdrawn_handle("withdrawn")]
    cv.legend(hs, x=4, y_top=H - 3, ncol=2)
    fin_txt = f"{fin:,}".replace(",", " ")
    cv.text(48, g.y_bot - 4, f"a: % of {fin_txt} finished; same log10 axis in every cell\n(0.1% floor; dotted line = "
            f"axis break; 0 = none).\n" + (f"Not drawn: {T['mapping_only']} lost only to mapping gaps."
                                           if T["mapping_only"] else "No individual is lost only to a mapping gap."),
            linespacing=1.0,
            fontsize=LEGEND_LABEL, ha="left", va="top", color=FOOTNOTE_GREY)
    strategy_key(cv)
    return save(cv, "P23_exclusive_groups_log_grid_plus_strategy")


# =========================================================================== round 5: P23 colour options
from population_synthetic.analysis.utils.palette import CAPTION_GREY, WORST_CLASH_COLORS, opaque  # noqa: E402

#: Okabe-Ito yellow. Not in palette.py (the layer leaves it out as unreadable as thin bars or text on
#: white), so it is kept local to this gallery script, only for the yellow options P23c and P23d.
OI_YELLOW = "#F0E442"
DARK = CAPTION_GREY                     # "dark grey" of the options (palette role, #444444)
GREEN = WORST_CLASH_COLORS["pipeline"]  # Okabe-Ito bluish green #009E73 (palette)

#: name -> {llm, tables, both: (face, hatch colour or None), outline: edge for light fills}
SCHEMES = {
    "P23a": dict(llm=CC["llm"], tables=CC["tables"], both=(CC["llm"], CC["tables"]), outline=None,
                 title="a  black / pink, both hatched (current)"),
    "P23b": dict(llm=DARK, tables=GREEN, both=(DARK, GREEN), outline=None,
                 title="b  dark grey / bluish green, both hatched"),
    "P23c": dict(llm=DARK, tables=OI_YELLOW, both=(DARK, OI_YELLOW), outline=BASELINE_DARK,
                 title="c  dark grey / yellow (outlined), both hatched"),
    "P23d": dict(llm=DARK, tables=GREEN, both=(OI_YELLOW, None), outline=BASELINE_DARK,
                 title="d  dark grey / bluish green, both solid yellow (outlined)"),
    "P23e": dict(llm=DARK, tables=GREEN, both=(opaque(GREEN, 0.5, over=DARK), None), outline=None,
                 title="e  dark grey / bluish green, both solid grey-green blend"),
}

# Round 6: options tied to the article's published colour system (see proposals.md section 8).
from population_synthetic.analysis.utils.glyph_grid import step_colors as _step_colors  # noqa: E402
from population_synthetic.analysis.utils.palette import NEUTRAL_GREY, SEVERITY_SERIES, heatmap_levels  # noqa: E402

#: Figure 5B's R3 "impossible" colour: step 8 of the 11-step inferno atypicality ramp (index 2 = #420A68).
R3_PURPLE = _step_colors(heatmap_levels(11))[2]
SCHEMES.update({
    "P23f": dict(llm=R3_PURPLE, tables=NEUTRAL_GREY, both=(R3_PURPLE, NEUTRAL_GREY), outline=None,
                 title="f  Fig 5 R3 purple (LLM) / neutral grey (tables), both hatched"),
    "P23g": dict(llm=DARK, tables=SEVERITY_SERIES[2], both=(DARK, SEVERITY_SERIES[2]), outline=None,
                 title="g  dark grey / sky blue accent (tables), both hatched"),
    "P23h": dict(llm=BASELINE_DARK, tables=NEUTRAL_GREY, both=(BASELINE_DARK, SURFACE), outline=None,
                 zero_both=BASELINE_DARK, title="h  greyscale: near-black / mid grey, both white-hatched"),
})


def _needs_outline(sch, colour):
    return sch["outline"] is not None and colour == OI_YELLOW


def sch_bar(ax, sch, key, x0, y, w, h):
    face, hatch = (sch["both"] if key == "both" else (sch["llm"] if key == "llm_only" else sch["tables"], None))
    edge = sch["outline"] if _needs_outline(sch, face) else (hatch or "none")
    lw = 0.3 if _needs_outline(sch, face) else 0
    ax.add_patch(Rectangle((x0, y - h / 2), w, h, facecolor=face, edgecolor=hatch if hatch else edge,
                           hatch="//////" if hatch else None, linewidth=lw, zorder=2))
    if hatch and _needs_outline(sch, hatch):  # yellow hatch: thin dark frame so the bar has an edge
        ax.add_patch(Rectangle((x0, y - h / 2), w, h, facecolor="none", edgecolor=sch["outline"], linewidth=0.3,
                               zorder=3))


def sch_lane_colour(sch, key):
    if key == "llm_only":
        return sch["llm"]
    if key == "tables_only":
        return sch["tables"]
    return sch.get("zero_both") or sch["both"][1] or sch["both"][0]


def sch_cell(ax, r, sch):
    for t in LOG_TICKS:
        ax.axvline(lg(t), color=GRID_RULE, linewidth=GRID_LINEWIDTH, zorder=0)
    # 2026-10-20: the dotted axis-break line is drawn AFTER the bars (zorder 2.5; it sits left of every
    # bar, so nothing visible changes). At zorder 0 the PostScript backend left its [0.5 0.5] dash active
    # when the hatch pattern was instantiated, so the EPS drew the hatch as dotted lines.
    ax.axvline(-0.035, color=GRID_RULE, linewidth=GRID_LINEWIDTH, linestyle=(0, (1, 1)), zorder=2.5)
    for k, key in enumerate(d.GROUPS):
        v = r[f"sg_{key}"]
        y = 2 - k
        if v <= 0:
            col = sch_lane_colour(sch, key)
            ax.plot([ZERO_X], [y], marker="o", ms=2.8, mfc=SURFACE, mec=col,
                    mew=0.9 if col == OI_YELLOW else 0.6, ls="none", zorder=3)
        else:
            sch_bar(ax, sch, key, 0.0, y, lg(v), 0.76)
    ax.set_xlim(X_LO, 1.04)
    ax.set_ylim(-0.5, 2.5)
    if r.excluded:
        draw_withdrawn_cell(ax)
    else:
        bare(ax)


def sch_handles(sch):
    from matplotlib.patches import Patch as _P
    T, fin = d.GROUP_TOTAL, int(d.TOTAL.finished)

    def lab(k):
        return f"{G_LABEL[k]}: {T[k]:,} ({100 * T[k] / fin:.1f}%)".replace(",", " ")

    def patch(key):
        face, hatch = (sch["both"] if key == "both" else (sch_lane_colour(sch, key), None))
        out = _needs_outline(sch, face) or (hatch is not None and _needs_outline(sch, hatch))
        return _P(facecolor=face, edgecolor=hatch if hatch else (sch["outline"] if out else "none"),
                  hatch="////" if hatch else None, linewidth=0.3 if out and not hatch else 0, label=lab(key))

    return [patch(k) for k in d.GROUPS]


def scale_key(cv, x0, x1, y):
    """One readable copy of the cell x axis: 0 slot, break, 1, 10, 100 (%), at the house tick size."""
    ax = cv.axes(x0, y - 4, x1, y)
    ax.set_xlim(X_LO, 1.04)
    ax.set_ylim(0, 1)
    for t in LOG_TICKS:
        ax.axvline(lg(t), color=GRID_RULE, linewidth=GRID_LINEWIDTH)
    ax.axvline(-0.035, color=GRID_RULE, linewidth=GRID_LINEWIDTH, linestyle=(0, (1, 1)))
    ax.set_yticks([])
    ax.set_xticks([ZERO_X, lg(0.01), lg(0.1), lg(1.0)])
    ax.set_xticklabels(["0", "1", "10", "100%"])
    ax.tick_params(axis="x", labelsize=TICK_LABEL, length=2, pad=1, width=AXES_LINEWIDTH)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_linewidth(AXES_LINEWIDTH)
    ax.spines["bottom"].set_bounds(0.0, 1.04)
    ax.plot([X_LO + 0.03, ZERO_X + 0.03], [0, 0], color=BASELINE_DARK, linewidth=AXES_LINEWIDTH, clip_on=False)
    for dx in (-0.055, -0.025):  # break mark
        ax.plot([dx - 0.012, dx + 0.012], [-0.9, 0.9], color=BASELINE_DARK, linewidth=PATCH_LINEWIDTH, clip_on=False)
    return ax


def strategy_panel(cv, box, sch, *, label_x=None, ys_points=None, xmax=0.40, count_fs=ANNOTATION):
    ax = cv.axes(*box)
    for i, m in enumerate(d.METHODS):
        r = d.BY_METHOD_G.loc[m]
        yc = 4 - i
        for k, key in enumerate(d.GROUPS):
            n = int(r[f"g_{key}"])
            v = n / r.finished
            y = yc + 0.28 - 0.28 * k
            if n:
                sch_bar(ax, sch, key, 0.0, y, v, 0.24)
            if count_fs:
                ax.text(v + 0.008, y, f"{n}", ha="left", va="center", fontsize=count_fs, color=BASELINE_DARK)
    ax.set_ylim(-0.5, 4.5)
    ax.set_yticks([])
    ax.set_xlim(0, xmax)
    ax.set_xticks([0, 0.2, 0.4])
    ax.set_xticklabels(["0", "20", "40%"])
    ax.tick_params(labelsize=TICK_LABEL, length=2, pad=1)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    if label_x is not None:
        for y, m in zip(ys_points, d.METHODS):
            cv.text(label_x, y, m, fontsize=TICK_LABEL_LARGE, fontweight="bold", ha="right", va="center",
                    color=BASELINE_DARK)
    return ax


def p23_variant(pid):
    sch = SCHEMES[pid]
    H = 300.0
    cv = PointCanvas(W, H)
    g = Grid(22, 352, H - 40 - LABEL_BAND, 24.0, row_gap=3)
    for i, m in enumerate(d.METHODS):
        for j, mod in enumerate(d.MODELS):
            sch_cell(cv.axes(*g.box(i, j)), d.CELL[m][mod], sch)
    model_names_above(cv, g.cx(), g.y_top + 3)
    row_letters(cv, g.cy(), g.x0 - 5)
    strategy_panel(cv, (374, g.y_bot - 0.5, 446, g.y_top + 0.5), sch, label_x=370, ys_points=g.cy())
    cv.text(362, g.y_top + 8, "b  by strategy, % of\n    finished (number:\n    individuals)", fontsize=TICK_LABEL,
            fontweight="bold", ha="left", va="bottom", color=BASELINE_DARK, linespacing=1.0)
    cv.text(4, g.y_top + 8, "a", fontsize=TICK_LABEL, fontweight="bold", ha="left", va="bottom", color=BASELINE_DARK)
    cv.legend(sch_handles(sch) + [zero_handle(), withdrawn_handle("withdrawn")], x=4, y_top=H - 3, ncol=2)
    # readable scale key under the grid, then the note
    cv.text(22, g.y_bot - 4, "a: x axis of every cell (% of finished, log10):", fontsize=LEGEND_LABEL, ha="left",
            va="top", color=FOOTNOTE_GREY)
    scale_key(cv, 196, 300, g.y_bot - 6)
    fin_txt = f"{int(d.TOTAL.finished):,}".replace(",", " ")
    T = d.GROUP_TOTAL
    # 2026-10-20 manuscript copy: the empty mapping-gap category is not mentioned
    tail = (f" Not drawn: {T['mapping_only']} lost only to mapping gaps." if T["mapping_only"] else "")
    cv.text(22, g.y_bot - 24, f"Of {fin_txt} finished individuals; floor 0.1%, 0 = none (left of the break).{tail}",
            fontsize=LEGEND_LABEL, ha="left", va="top", color=FOOTNOTE_GREY)
    strategy_key(cv)
    return save(cv, f"{pid}_colour_{pid[-1]}")


@house_style
def P23a():
    """Colour option a: current black / black hatched with pink / pink; readable x-scale key under the grid."""
    return p23_variant("P23a")


@house_style
def P23b():
    """Colour option b: LLM dark grey, table limit Okabe-Ito bluish green, both dark grey hatched with green."""
    return p23_variant("P23b")


@house_style
def P23c():
    """Colour option c: LLM dark grey, table limit Okabe-Ito yellow with a thin dark outline, both dark grey hatched with yellow."""
    return p23_variant("P23c")


@house_style
def P23d():
    """Colour option d: as b, but both as solid Okabe-Ito yellow (outlined): the one remaining Okabe-Ito hue that clashes with neither the hosted-blue / local-orange names nor Figure 5's orange and purple."""
    return p23_variant("P23d")


@house_style
def P23e():
    """Colour option e: as b, but both as a solid opaque 50/50 blend of dark grey and bluish green (palette.opaque)."""
    return p23_variant("P23e")


@house_style
def P23f():
    """Colour option f: LLM failure in Figure 5B's R3 'impossible' purple (#420A68, an inferno step), table limit in neutral grey (#8C8C8C), both purple hatched with grey."""
    return p23_variant("P23f")


@house_style
def P23g():
    """Colour option g: grey family with one accent: LLM dark grey, table limit sky blue (#56B4E9, palette SEVERITY_SERIES, unused in the published figures), both dark grey hatched with sky blue."""
    return p23_variant("P23g")


@house_style
def P23h():
    """Colour option h: pure greyscale: LLM near-black (#222222), table limit mid grey (#8C8C8C), both near-black hatched with white."""
    return p23_variant("P23h")


@house_style
def P23_compare():
    """Comparison sheet: per option, the strategy-E row of panel a and panel b side by side."""
    names = list(SCHEMES)
    blk = 116.0
    H = 14 + blk * len(names) + 10
    cv = PointCanvas(W, H)
    cw, gap = 17.0, 2.0
    x0 = 30.0
    cxs = [x0 + j * (cw + gap) + (4 if j == N_COLS - 1 else 0) for j in range(N_COLS)]
    for b, pid in enumerate(names):
        sch = SCHEMES[pid]
        top = H - 14 - b * blk
        cv.text(4, top, sch["title"], fontsize=TICK_LABEL, fontweight="bold", ha="left", va="top", color=BASELINE_DARK)
        y1, y0 = top - 16, top - 44
        for j, mod in enumerate(d.MODELS):
            sch_cell(cv.axes(cxs[j], y0, cxs[j] + cw, y1), d.CELL["E"][mod], sch)
        cv.text(x0 - 4, (y0 + y1) / 2, "E", fontsize=TICK_LABEL_LARGE, fontweight="bold", ha="right", va="center",
                color=BASELINE_DARK)
        scale_key(cv, x0, x0 + 150, y0 - 4)
        cv.legend(sch_handles(sch), x=x0, y_top=y0 - 20, ncol=2)
        pb = (362, top - blk + 14, 446, top - 16)
        strategy_panel(cv, pb, sch, xmax=0.40, count_fs=None)
        for i, m in enumerate(d.METHODS):
            y = pb[3] - (pb[3] - pb[1]) * (i + 0.5) / 5
            cv.text(358, y, m, fontsize=TICK_LABEL, fontweight="bold", ha="right", va="center", color=BASELINE_DARK)
    cv.text(4, 4, "Left: the strategy E row of panel a (models in the published order). Right: panel b without counts.", fontsize=LEGEND_LABEL,
            ha="left", va="bottom", color=FOOTNOTE_GREY)
    return save(cv, "P23_colour_comparison")


ALL = {f"P{n:02d}": globals()[f"P{n:02d}"] for n in range(1, 24)}
ALL.update({k: globals()[k] for k in ("P23a", "P23b", "P23c", "P23d", "P23e", "P23f", "P23g", "P23h")})
# P23_compare (strategy-E rows only) superseded by make_comparison.py (full figures), not registered

if __name__ == "__main__":
    for pid in (sys.argv[1:] or ALL):
        ALL[pid]()


# =========================================================================== manuscript Figure 6, panels B and C
# 2026-10-20 (manuscript copy only). P23b's drawing, lettered for the Figure 6 composite: A = the
# retention heatmap (fig6_heatmap.py), B = this cause grid, C = the by-strategy bars. Letters are
# bold capitals with a full stop, as in Figure 5's composite. The internal "a"/"b" of the gallery
# design are replaced by the letters; the note under the grid names panel B instead of "a".
from population_synthetic.analysis.utils.style import FIGURE_TITLE, HEADING_WEIGHT  # noqa: E402

P23B_H = 300.0          # standalone height (with model names), as the gallery P23b
NAMES_GAP = 6.0         # band above the grid when the model names are left to panel A (composite)
LETTER_INSET = 1.0     # the house writer rejects ink on the canvas edge (fixed canvas)


def fig6_bc_height(names: bool) -> float:
    return P23B_H if names else P23B_H - LABEL_BAND + NAMES_GAP


def fig6_bc(cv, *, names: bool, pid: str = "P23b"):
    """Draw panels B and C into the bottom fig6_bc_height(names) points of canvas *cv*."""
    sch = SCHEMES[pid]
    H = fig6_bc_height(names)
    band = LABEL_BAND if names else NAMES_GAP
    g = Grid(22, 352, H - 40 - band, 24.0, row_gap=3)
    for i, m in enumerate(d.METHODS):
        for j, mod in enumerate(d.MODELS):
            sch_cell(cv.axes(*g.box(i, j)), d.CELL[m][mod], sch)
    if names:
        model_names_above(cv, g.cx(), g.y_top + 3)
    row_letters(cv, g.cy(), g.x0 - 5)
    strategy_panel(cv, (374, g.y_bot - 0.5, 446, g.y_top + 0.5), sch, label_x=370, ys_points=g.cy())
    # panel letters (Figure 5 style) and panel C's title
    cv.text(LETTER_INSET, H - LETTER_INSET, "B.", fontsize=FIGURE_TITLE, fontweight=HEADING_WEIGHT, ha="left", va="top",
            color=BASELINE_DARK)
    c_top = g.y_top + 8 + 26.0
    cv.text(356.0, c_top, "C.", fontsize=FIGURE_TITLE, fontweight=HEADING_WEIGHT, ha="left", va="top",
            color=BASELINE_DARK)
    cv.text(372.0, c_top - 1.0, "by strategy, % of\nfinished (number:\nindividuals)", fontsize=TICK_LABEL,
            fontweight="bold", ha="left", va="top", color=BASELINE_DARK, linespacing=1.0)
    cv.legend(sch_handles(sch) + [zero_handle(), withdrawn_handle("withdrawn")], x=18, y_top=H - 3, ncol=2)
    cv.text(22, g.y_bot - 4, "B: x axis of every cell (% of finished, log10):", fontsize=LEGEND_LABEL, ha="left",
            va="top", color=FOOTNOTE_GREY)
    scale_key(cv, 196, 300, g.y_bot - 6)
    fin_txt = f"{int(d.TOTAL.finished):,}".replace(",", " ")
    T = d.GROUP_TOTAL
    tail = (f" Not drawn: {T['mapping_only']} lost only to mapping gaps." if T["mapping_only"] else "")
    cv.text(22, g.y_bot - 24, f"Of {fin_txt} finished individuals; floor 0.1%, 0 = none (left of the break).{tail}",
            fontsize=LEGEND_LABEL, ha="left", va="top", color=FOOTNOTE_GREY)
    strategy_key(cv)
    return g


@house_style
def FIG6B():
    """Standalone Figure 6 panels B + C (P23b, lettered B. / C.)."""
    cv = PointCanvas(W, fig6_bc_height(True))
    fig6_bc(cv, names=True)
    return save(cv, "fig6B")


ALL["FIG6B"] = FIG6B


# =========================================================================== Figure 6 panels B + C, the author's revised layout
# 2026-10-20 (rev): reproduces the author's Inkscape revision fig6B_revised.svg (456 x 179.93 pt). Every position
# below was read off that SVG (composed transforms; top-left origin, pt) and is converted here to the canvas's
# bottom-left points. No model names above the grid (panel A's serve both), "B." / "C." at the top, the legend
# and a magnified log10 axis key below the grid, no notes and no strategy key. Bars, lanes, counts, colours,
# fonts and sizes are those of P23b.
from population_synthetic.analysis.utils.glyph_grid import _WITHDRAWN_MARKER_PT, WITHDRAWN_STROKE_WIDTH  # noqa: E402
from population_synthetic.analysis.utils.palette import MUTED_GREY as _MUTED_GREY  # noqa: E402

REV_H = 179.92976                         # canvas height of the revision
REV_GRID_X0 = 22.0 - 1.8789062            # grid moved 1.879 pt left (20.121)
REV_GRID_TOP = 15.39134                   # grid top, from the top
REV_C_DX = 2.486328                       # panel C moved 2.486 pt right
REV_C_BOX = (374.0 + REV_C_DX, 14.89134, 446.0 + REV_C_DX, 147.89134)   # x0, top, x1, bottom (from the top)
REV_LETTERS = {"B.": (-0.8789, 8.8828), "C.": (358.4863, 8.7363)}       # x, baseline (from the top)
REV_LEG_SWATCH = (153.07, 11.2, 6.12, (152.65, 162.53, 172.41))         # x, w, h, tops
REV_LEG_TEXT = (167.4703, (158.4903, 168.3703, 178.2503))              # x, baselines
REV_LEG2_MARK_X, REV_LEG2_MARK_Y = 305.86, (155.71, 165.59)             # zero, withdrawn marker centres
REV_LEG2_TEXT = (314.6563, (157.7846, 168.4047))
REV_KEY = (196.0 - 175.05746 - 3.2288262, 300.0 - 175.05746 - 3.2288262, 156.65035)  # x0, x1, axis line (from top)
REV_KEY_LABEL = ("% of finished, log10", 37.9248, 173.3143)


# 2026-10-20 (margin): so the house writer's edge check passes, the revised layout gets a 1 pt top and a 1 pt
# bottom margin (canvas REV_H + 2 pt; every element moves 1 pt down), "B." moves 1 pt right and the "40%" tick
# label of panel C 1 pt left. Nothing else moves.
REV_PAD_TOP = 1.0
REV_PAD_BOTTOM = 1.0
REV_B_DX = 1.0
REV_40_DX = -1.0
REV_H_PADDED = REV_H + REV_PAD_TOP + REV_PAD_BOTTOM


def fig6_bc_rev(cv, *, pid: str = "P23b", block_h: float = REV_H, pad_top: float = 0.0, b_dx: float = 0.0,
                last_tick_dx: float = 0.0):
    """Panels B + C in the author's revised layout, drawn into the bottom *block_h* points of canvas *cv*.

    Returns the Grid (bottom-left points), whose column xs panel A must reuse to stay aligned."""
    sch = SCHEMES[pid]
    H = block_h

    def yb(y_top):  # from-the-top (in the revision's coordinates) -> bottom-left of this block
        return H - (y_top + pad_top)

    g = Grid(REV_GRID_X0, REV_GRID_X0 + 330.0, yb(REV_GRID_TOP), 24.0, row_gap=3)
    for i, m in enumerate(d.METHODS):
        for j, mod in enumerate(d.MODELS):
            sch_cell(cv.axes(*g.box(i, j)), d.CELL[m][mod], sch)
    row_letters(cv, g.cy(), g.x0 - 5)
    cx0, ctop, cx1, cbot = REV_C_BOX
    cax = strategy_panel(cv, (cx0, yb(cbot), cx1, yb(ctop)), sch, label_x=370.0 + REV_C_DX, ys_points=g.cy())
    if last_tick_dx:
        import matplotlib.transforms as _mt
        last = cax.get_xticklabels()[-1]
        last.set_transform(last.get_transform() + _mt.ScaledTranslation(last_tick_dx / 72.0, 0, cv.figure.dpi_scale_trans))
    for s, (x, y) in REV_LETTERS.items():
        x = x + (b_dx if s == "B." else 0.0)
        cv.text(x, yb(y), s, fontsize=FIGURE_TITLE, fontweight=HEADING_WEIGHT, ha="left", va="baseline",
                color=BASELINE_DARK)
    # legend, drawn element by element at the revision's positions
    T, fin = d.GROUP_TOTAL, int(d.TOTAL.finished)
    ov = cv.axes(0.0, 0.0, W, H)
    ov.set_xlim(0, W)
    ov.set_ylim(H - pad_top, -pad_top)   # the revision's from-the-top coordinates inside the overlay
    ov.set_axis_off()
    ov.patch.set_visible(False)
    sx, sw, sh, tops = REV_LEG_SWATCH
    for key, top in zip(d.GROUPS, tops):
        face, hatch = (sch["both"] if key == "both" else (sch_lane_colour(sch, key), None))
        ov.add_patch(Rectangle((sx, top), sw, sh, facecolor=face, edgecolor=hatch if hatch else "none",
                               hatch="////" if hatch else None, linewidth=0))
    tx, bases = REV_LEG_TEXT
    for key, base in zip(d.GROUPS, bases):
        label = f"{G_LABEL[key]}: {T[key]:,} ({100 * T[key] / fin:.1f}%)".replace(",", " ")
        cv.text(tx, yb(base), label, fontsize=LEGEND_LABEL, ha="left", va="baseline", color="black")
    zy, wy = REV_LEG2_MARK_Y
    ov.plot([REV_LEG2_MARK_X], [zy], marker="o", ms=3.6, mfc=SURFACE, mec=SECONDARY_GREY, mew=0.6, ls="none")
    ov.plot([REV_LEG2_MARK_X], [wy], marker="x", ms=_WITHDRAWN_MARKER_PT, color=_MUTED_GREY,
            mew=WITHDRAWN_STROKE_WIDTH, ls="none")
    t2x, (zb, wb) = REV_LEG2_TEXT
    cv.text(t2x, yb(zb), "zero", fontsize=LEGEND_LABEL, ha="left", va="baseline", color="black")
    cv.text(t2x, yb(wb), "withdrawn", fontsize=LEGEND_LABEL, ha="left", va="baseline", color="black")
    # the magnified axis key: 0 slot, break, 1, 10, 100%, with its title
    kx0, kx1, ky = REV_KEY
    scale_key(cv, kx0, kx1, yb(ky - 4.0))   # scale_key's y is the top of its 4 pt axes; the axis line is 4 pt below
    lab, lx, lb = REV_KEY_LABEL
    cv.text(lx, yb(lb), lab, fontsize=TICK_LABEL, ha="left", va="baseline", color="black")
    return g


@house_style
def FIG6B_REV():
    """Standalone Figure 6 panels B + C in the author's revised layout."""
    cv = PointCanvas(W, REV_H)
    fig6_bc_rev(cv)
    return save_exact(cv, "fig6B")


ALL["FIG6B_REV"] = FIG6B_REV


def save_exact(cv, name):
    """Write PNG (600 dpi) + SVG + EPS (300 dpi for raster content, the house RASTER_DPI) + PDF at the fixed
    canvas, with the house export rcParams and the house 10 MiB file ceiling, but WITHOUT the house writer's
    ink-on-edge check: the author's revised layout (fig6B_revised.svg) deliberately places "B.", "40%" and the
    last legend line at the canvas edge, and reproducing it exactly is the point."""
    import io as _io
    import matplotlib.pyplot as _plt
    from population_synthetic.analysis.utils.figures import MAX_FILE_BYTES, RASTER_DPI, _export_rc_params
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {}
    with _plt.rc_context(_export_rc_params()):
        for fmt, dpi in (("png", PNG_DPI), ("svg", RASTER_DPI), ("eps", RASTER_DPI), ("pdf", PNG_DPI)):
            buf = _io.BytesIO()
            cv.figure.savefig(buf, format=fmt, dpi=dpi, bbox_inches=None, pad_inches=0)
            payload[fmt] = buf.getvalue()
            if len(payload[fmt]) > MAX_FILE_BYTES:
                raise ValueError(f"{name}.{fmt} is {len(payload[fmt]) / 2**20:.1f} MiB, over the house ceiling")
    for fmt, data in payload.items():
        (OUT / f"{name}.{fmt}").write_bytes(data)
    _plt.close(cv.figure)
    print("wrote", name, f"{cv.height_pt:.2f} pt (exact layout, no edge check)")
    return OUT / f"{name}.png"


@house_style
def FIG6B_MARGIN():
    """Standalone Figure 6 panels B + C: the author's revised layout with the 1 pt margins, through the house writer."""
    cv = PointCanvas(W, REV_H_PADDED)
    fig6_bc_rev(cv, block_h=REV_H_PADDED, pad_top=REV_PAD_TOP, b_dx=REV_B_DX, last_tick_dx=REV_40_DX)
    return save(cv, "fig6B", writer_dpi=PNG_DPI)   # no raster content: the writer renders and checks at 600 dpi


ALL["FIG6B_MARGIN"] = FIG6B_MARGIN
