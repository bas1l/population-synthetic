"""Figure 1 prototypes. Run: python protos.py [P01 P02 ...]  (no args = all)."""
from __future__ import annotations

import sys

import numpy as np
from matplotlib.patches import Rectangle, Circle, FancyBboxPatch, Polygon

import common as c
from common import (T, box, arrow, line, table_icon, table_stack, person, crowd, llm_chip, die, card,
                    schema_slots, bubble, hist_overlap, judge_icon, coin_icon, funnel_icon, cross, badge,
                    combo_grid, strategy_letters, fmt, SC, REF, REF_FILL, INK, SOFT, SCHEMA, SCHEMA_FILL,
                    F8, F9, F10, F11, F12)
from population_synthetic.analysis.utils.style import house_style

LVL = ["Population level", "Individual level", "Operational\nperformance"]
LVL1 = ["Population level", "Individual level", "Operational performance"]


def analysis_icon(ax, k, x, y, s):
    if k == 0:
        hist_overlap(ax, x - s * 0.5, y - s * 0.4, s, s * 0.8, z=7)
    elif k == 1:
        judge_icon(ax, x, y, s, z=7)
    else:
        coin_icon(ax, x - s * 0.22, y, s * 0.62, z=7)
        funnel_icon(ax, x + s * 0.36, y, s * 0.5, z=7)


def bundle(ax, xs, ys, spread=2.0, lw=1.4, colors=None, z=3):
    """Five parallel strategy rails along a polyline (vertical offset)."""
    colors = colors or SC
    n = len(colors)
    for i, col in enumerate(colors):
        off = (i - (n - 1) / 2) * spread
        line(ax, xs, [y - off for y in ys], color=col, lw=lw, z=z)


# ------------------------------------------------------------------ P01 transit rails
@house_style
def p01(sections=False):
    H = 166
    cv, ax = c.canvas(H)
    yR, yS = 128, 50
    xm0, xm1 = 196, 226  # mapping interchange
    # origins
    table_stack(ax, 8, yR - 9, 22, 18, n=3)
    T(ax, 22, yR - 16, "13 tables", size=F8, color=REF, va="top")
    llm_chip(ax, 22, yS, 26)
    T(ax, 22, yS - 17, "13 LLMs", size=F8, va="top")
    # reference rail + conditional sampling
    line(ax, [40, 376], [yR, yR], color=REF, lw=2.6, z=2)
    die(ax, 95, yR, 15)
    T(ax, 95, yR + 11, "conditional\nsampling", size=F8, color=REF, va="bottom")
    T(ax, 160, yR + 6, "table label", size=F8, color=REF, va="bottom")
    # synthetic bundle, strategies A-E
    bundle(ax, [40, 330], [yS, yS], spread=2.4, lw=1.5)
    for i, s_ in enumerate(c.STRATEGIES):
        T(ax, 47 + i * 7, yS + 12, c.LETTERS[s_], size=F8, color=c.STRAT_COLOR[s_], weight="bold")
    card(ax, 86, yS - 12, 18, 24, bar_colors=SC)
    T(ax, 95, yS - 16, "one attribute\nat a time", size=F8, va="top")
    bubble(ax, 146, yS + 12, 26, 13)
    T(ax, 159, yS - 7, "free text", size=F8, va="top")
    # mapping interchange (one shared station)
    box(ax, xm0 - 6, yS - 20, xm1 - xm0 + 12, yR - yS + 40, ec=SCHEMA, fc=SCHEMA_FILL, lw=1.0, r=6, z=4)
    schema_slots(ax, xm0 + 3, yS + 6, xm1 - xm0 - 6, yR - yS - 12)
    T(ax, (xm0 + xm1) / 2, yR + 26, "same 14 attributes", size=F8, color=SCHEMA, weight="bold", va="bottom")
    # populations after mapping (off the rail)
    crowd(ax, 244, yR + 5, 3, 1, 11, REF)
    T(ax, 282, yR + 10, f"{fmt(c.N_REFERENCE)}", size=F9, color=REF, weight="bold", ha="left")
    crowd(ax, 244, yS - 19, 3, 1, 11, SC[1:4])
    T(ax, 282, yS - 14, f"{c.N_KEPT} × {c.N_PER_COMBO[0]}", size=F9, weight="bold", ha="left")
    # terminals: population + individual fed by both routes, operational by the synthetic route only
    xt, r = 438, 15
    yP, yI, yO = yR, (yR + yS) / 2, yS
    line(ax, [370, xt], [yR, yR], color=REF, lw=2.6, z=2)
    line(ax, [376, 376, xt], [yR, yI + 3, yI + 3], color=REF, lw=2.6, z=2)
    bundle(ax, [330, xt], [yS, yS], spread=1.8, lw=1.1)
    bundle(ax, [330, 344, 344, xt], [yS, yS, yP - 8, yP - 8], spread=1.8, lw=1.1)
    bundle(ax, [330, 358, 358, xt], [yS, yS, yI - 6, yI - 6], spread=1.8, lw=1.1)
    for k, yt in enumerate((yP, yI, yO)):
        ax.add_patch(Circle((xt, yt), r, fc="white", ec=INK, lw=1.0, zorder=6))
        analysis_icon(ax, k, xt, yt, 18)
    for txt, yt in (("population", yP), ("individual", yI), ("cost, retention", yO)):
        T(ax, xt - r - 3, yt + 8, txt, size=F8, va="bottom", ha="right",
          bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none"), zorder=7)
    if sections:
        def pill(x, y, t):
            T(ax, x, y, t, size=F8, color="white", weight="bold", zorder=12,
              bbox=dict(boxstyle="round,pad=0.25,rounding_size=0.6", fc=INK, ec="none"))
        pill(22, yR + 25, "4.1")
        pill(22, yS + 22, "4.2")
        pill((xm0 + xm1) / 2, yS - 30, "4.3")
        pill(xt, yP + r, "4.4.1")
        pill(xt, yI + r, "4.4.2")
        pill(xt, yO + r, "4.4.3")
        return c.save(cv.figure, "P10_transit_rails_sections")
    return c.save(cv.figure, "P01_transit_rails")


# ------------------------------------------------------------------ P02 bow tie
@house_style
def p02():
    H = 150
    cv, ax = c.canvas(H)
    yR, yS = 112, 38
    # reference row
    table_stack(ax, 6, yR - 10, 22, 18, n=3)
    arrow(ax, 38, yR, 56, yR, color=REF)
    die(ax, 68, yR, 16)
    arrow(ax, 80, yR, 98, yR, color=REF)
    crowd(ax, 104, yR - 9, 4, 1, 13, REF)
    T(ax, 124, yR + 16, fmt(c.N_REFERENCE), size=F10, color=REF, weight="bold", va="bottom")
    # synthetic row
    llm_chip(ax, 20, yS, 26)
    T(ax, 20, yS - 20, "13 × A–E", size=F8, va="top")
    arrow(ax, 38, yS, 56, yS, color=INK)
    bubble(ax, 57, yS - 4, 24, 14)
    arrow(ax, 84, yS, 98, yS, color=INK)
    crowd(ax, 104, yS - 9, 4, 1, 13, SC[:4])
    T(ax, 124, yS - 15, f"{c.N_KEPT} × {c.N_PER_COMBO[0]}", size=F10, weight="bold", va="top")
    # knot
    kx, ky, kw, kh = 205, 18, 26, 114
    arrow(ax, 150, yR, kx - 3, ky + kh * 0.62, color=REF, lw=2.2, head=7, conn="arc3,rad=-0.15")
    arrow(ax, 150, yS, kx - 3, ky + kh * 0.38, color=INK, lw=2.2, head=7, conn="arc3,rad=0.15")
    box(ax, kx - 4, ky - 4, kw + 8, kh + 8, ec=SCHEMA, fc=SCHEMA_FILL, lw=1.0, r=5)
    schema_slots(ax, kx, ky, kw, kh)
    T(ax, kx + kw / 2, ky - 8, "14 attributes", size=F8, color=SCHEMA, weight="bold", va="top")
    # fan out
    xs = 330
    ys = [118, 75, 32]
    for k, yy in enumerate(ys):
        arrow(ax, kx + kw + 6, ky + kh / 2, xs - 20, yy, color=INK, lw=1.2, conn=f"arc3,rad={0.12*(1-k)}")
        ax.add_patch(Circle((xs, yy), 16, fc="white", ec=INK, lw=1.0, zorder=6))
        analysis_icon(ax, k, xs, yy, 19)
        T(ax, xs + 22, yy, LVL[k], size=F10, ha="left")
    return c.save(cv.figure, "P02_bow_tie")


# ------------------------------------------------------------------ P03 grid centrepiece
@house_style
def p03():
    H = 168
    cv, ax = c.canvas(H)
    cell, gap = 9.0, 1.4
    gx, gy = 30, 26
    x1, ytop = combo_grid(ax, gx, gy, cell, gap, host_h=3.0)
    strategy_letters(ax, gx - 4, gy, cell, gap)
    llm_chip(ax, gx - 12, ytop + 12, 16, label=None)
    T(ax, (gx + x1) / 2, ytop + 12, "13 LLMs", size=F9, weight="bold")
    T(ax, (gx + x1) / 2, gy - 6, "each square: 100 individuals", size=F8, va="top")
    # host key
    hx = gx
    for k, h in enumerate(("hosted", "local")):
        ax.add_patch(Rectangle((hx, gy - 22), 7, 3, fc=c.HOST[h], ec="none"))
        T(ax, hx + 9, gy - 20.5, c.HOST_TXT[h], size=F8, ha="left")
        hx += 70
    ax.add_patch(Rectangle((hx, gy - 24), 6, 6, fc="white", ec=c.RESIDUAL_GREY, lw=0.5))
    cross(ax, hx + 3, gy - 21, 5)
    T(ax, hx + 9, gy - 20.5, "withdrawn", size=F8, ha="left")
    # reference block
    rx, ry, rs = 40, 118, 34
    ax.add_patch(Rectangle((gx, ry), rs * 1.6, rs, fc=REF_FILL, ec=REF, lw=0.8, zorder=4))
    crowd(ax, gx + 8, ry + 6, 4, 2, 10, REF)
    T(ax, gx + rs * 1.6 + 6, ry + rs / 2 + 6, f"Reference", size=F9, color=REF, ha="left", weight="bold")
    T(ax, gx + rs * 1.6 + 6, ry + rs / 2 - 6, f"{fmt(c.N_REFERENCE)} individuals from 13 tables", size=F8, color=REF, ha="left")
    # schema
    sx, sy, sw, sh = 236, 30, 22, 120
    arrow(ax, gx + rs * 1.6 + 128, ry + rs / 2, sx - 6, sy + sh * 0.72, color=REF, lw=1.6, conn="arc3,rad=-0.2")
    arrow(ax, x1 + 6, gy + 28, sx - 6, sy + sh * 0.3, color=INK, lw=1.6, conn="arc3,rad=0.1")
    box(ax, sx - 4, sy - 4, sw + 8, sh + 8, ec=SCHEMA, fc=SCHEMA_FILL, lw=1.0, r=5)
    schema_slots(ax, sx, sy, sw, sh)
    T(ax, sx + sw / 2, sy - 9, "14 attributes", size=F8, color=SCHEMA, weight="bold", va="top")
    # analyses
    xs = 318
    for k, yy in enumerate([132, 90, 48]):
        arrow(ax, sx + sw + 6, sy + sh / 2, xs - 19, yy, color=INK, lw=1.1, conn=f"arc3,rad={0.1*(1-k)}")
        ax.add_patch(Circle((xs, yy), 15, fc="white", ec=INK, lw=1.0, zorder=6))
        analysis_icon(ax, k, xs, yy, 18)
        T(ax, xs + 20, yy, LVL[k], size=F9, ha="left")
    return c.save(cv.figure, "P03_design_grid")


# ------------------------------------------------------------------ P04 four panels as section map
@house_style
def p04():
    H = 150
    cv, ax = c.canvas(H)
    pw, gap = 106, 8
    titles = ["Reference", "Synthetic", "Mapping", "Comparison"]
    secs = ["4.1", "4.2", "4.3", "4.4"]
    for k in range(4):
        x0 = 2 + k * (pw + gap)
        box(ax, x0, 2, pw, H - 4, ec=c.GRID_RULE, fc="white", lw=0.8, r=5, z=1)
        badge(ax, x0 + 12, H - 14, secs[k], r=9)
        T(ax, x0 + 25, H - 14, titles[k], size=F10, weight="bold", ha="left")
        if k < 3:
            arrow(ax, x0 + pw + 0.5, H / 2 - 6, x0 + pw + gap - 0.5, H / 2 - 6, color=INK, lw=1.2, head=5)
    # panel 1
    x0 = 2
    table_stack(ax, x0 + 10, 70, 24, 20, n=3)
    T(ax, x0 + 24, 62, "13 tables", size=F8, color=REF, va="top")
    arrow(ax, x0 + 42, 82, x0 + 56, 82, color=REF)
    die(ax, x0 + 66, 82, 16)
    crowd(ax, x0 + 18, 22, 6, 1, 12, REF)
    T(ax, x0 + 54, 44, fmt(c.N_REFERENCE), size=F10, color=REF, weight="bold")
    # panel 2
    x0 = 2 + pw + gap
    llm_chip(ax, x0 + 22, 86, 26)
    T(ax, x0 + 22, 68, "13 LLMs", size=F8, va="top")
    for i, s in enumerate(c.STRATEGIES):
        T(ax, x0 + 52 + i * 10, 92, c.LETTERS[s], size=F9, color=c.STRAT_COLOR[s], weight="bold")
        line(ax, [x0 + 52 + i * 10] * 2, [86, 74], color=c.STRAT_COLOR[s], lw=1.6)
    T(ax, x0 + 72, 66, "strategies", size=F8, va="top")
    for i in range(5):
        card(ax, x0 + 10 + i * 18, 18, 14, 22, color=SC[i], avatar=True)
    T(ax, x0 + pw / 2, 48, f"{c.N_KEPT} × {c.N_PER_COMBO[0]}", size=F10, weight="bold")
    # panel 3
    x0 = 2 + 2 * (pw + gap)
    T(ax, x0 + 24, 106, "table label", size=F8, color=REF)
    table_icon(ax, x0 + 12, 82, 24, 18)
    T(ax, x0 + 24, 66, "free text", size=F8)
    bubble(ax, x0 + 10, 34, 28, 22)
    sx = x0 + 74
    arrow(ax, x0 + 40, 90, sx - 4, 84, color=REF, lw=1.3)
    arrow(ax, x0 + 40, 46, sx - 4, 52, color=INK, lw=1.3)
    schema_slots(ax, sx, 18, 20, 98)
    T(ax, x0 + 48, 16, "14 attributes", size=F8, color=SCHEMA, weight="bold", va="top")
    # panel 4
    x0 = 2 + 3 * (pw + gap)
    for k, yy in enumerate([100, 66, 30]):
        ax.add_patch(Circle((x0 + 20, yy), 14, fc="white", ec=INK, lw=1.0, zorder=6))
        analysis_icon(ax, k, x0 + 20, yy, 17)
        T(ax, x0 + 38, yy, LVL[k], size=F8, ha="left")
    return c.save(cv.figure, "P04_section_panels")


# ------------------------------------------------------------------ P05 one individual's journey
@house_style
def p05():
    H = 160
    cv, ax = c.canvas(H)
    yR, yS = 118, 42
    # reference: table row -> 'sysselsatta'
    table_icon(ax, 6, yR - 12, 30, 24)
    T(ax, 3, yR - 18, "Statistics Sweden", size=F8, color=REF, va="top", ha="left")
    arrow(ax, 42, yR, 58, yR, color=REF)
    box(ax, 60, yR - 9, 78, 18, ec=REF, fc=REF_FILL, lw=0.8, r=3)
    T(ax, 99, yR, "“sysselsatta”", size=F9, color=REF)
    # synthetic: chip -> free text
    llm_chip(ax, 20, yS, 26)
    T(ax, 3, yS - 20, "13 LLMs × A–E", size=F8, va="top", ha="left")
    arrow(ax, 42, yS, 58, yS, color=INK)
    box(ax, 60, yS - 9, 78, 18, ec=INK, fc="white", lw=0.8, r=9)
    T(ax, 99, yS, "“Arbetar fulltid”", size=F9)
    # schema card with one highlighted slot
    sx, sy, sw, sh = 190, 22, 68, 126
    box(ax, sx - 5, sy - 5, sw + 10, sh + 10, ec=SCHEMA, fc=SCHEMA_FILL, lw=1.0, r=5)
    n = 14
    hi = 7
    fills = [SCHEMA_FILL] * n
    fills[hi] = SCHEMA
    schema_slots(ax, sx, sy, sw, sh, filled=fills)
    gapy = sh / n
    yhi = sy + hi * gapy + gapy / 2
    T(ax, sx + sw / 2, yhi, "Employed", size=F8, color="white", weight="bold", zorder=9)
    arrow(ax, 140, yR, sx - 7, yhi + 2, color=REF, lw=1.4, conn="arc3,rad=-0.15")
    arrow(ax, 140, yS, sx - 7, yhi - 2, color=INK, lw=1.4, conn="arc3,rad=0.15")
    T(ax, sx + sw / 2, sy - 9, "14 attributes, fixed categories", size=F8, color=SCHEMA, va="top")
    # populations then analyses
    crowd(ax, 282, yR - 9, 3, 1, 12, REF)
    T(ax, 296, yR + 14, fmt(c.N_REFERENCE), size=F9, color=REF, weight="bold", va="bottom")
    crowd(ax, 282, yS - 9, 3, 1, 12, SC[1:4])
    T(ax, 296, yS - 14, f"{c.N_KEPT} × {c.N_PER_COMBO[0]}", size=F9, weight="bold", va="top")
    arrow(ax, sx + sw + 7, sy + sh * 0.7, 278, yR, color=REF, lw=1.2)
    arrow(ax, sx + sw + 7, sy + sh * 0.3, 278, yS, color=INK, lw=1.2)
    xs = 360
    for k, yy in enumerate([124, 80, 36]):
        ax.add_patch(Circle((xs, yy), 14, fc="white", ec=INK, lw=1.0, zorder=6))
        analysis_icon(ax, k, xs, yy, 17)
        T(ax, xs + 18, yy, LVL[k], size=F8, ha="left")
    line(ax, [320, 324, 324], [yR, yR, 36], color=INK, lw=0.8)
    line(ax, [320, 324], [yS, yS], color=INK, lw=0.8)
    for yy in (124, 80, 36):
        arrow(ax, 324, yy, xs - 16, yy, color=INK, lw=0.8, head=4)
    return c.save(cv.figure, "P05_one_value_journey")


# ------------------------------------------------------------------ P06 conservative: current layout, icons
@house_style
def p06():
    H = 132
    cv, ax = c.canvas(H)
    yR, yS = 98, 32
    lane_h = 52
    box(ax, 2, yR - lane_h / 2, 196, lane_h, ec="none", fc=REF_FILL, r=6, z=0)
    box(ax, 2, yS - lane_h / 2, 196, lane_h, ec="none", fc="#F7F7F7", r=6, z=0)
    T(ax, 8, yR + lane_h / 2 - 7, "Reference", size=F9, color=REF, weight="bold", ha="left")
    T(ax, 8, yS + lane_h / 2 - 7, "Synthetic", size=F9, weight="bold", ha="left")
    table_stack(ax, 14, yR - 14, 22, 17, n=3)
    T(ax, 28, yR - 20, "13", size=F8, color=REF, va="top")
    arrow(ax, 46, yR - 4, 72, yR - 4, color=REF)
    die(ax, 86, yR - 4, 16)
    arrow(ax, 100, yR - 4, 128, yR - 4, color=REF)
    crowd(ax, 134, yR - 13, 3, 1, 12, REF)
    T(ax, 160, yR - 22, fmt(c.N_REFERENCE), size=F8, color=REF, weight="bold", va="top")
    llm_chip(ax, 25, yS - 4, 27)
    T(ax, 25, yS - 20, "13 × A–E", size=F8, va="top")
    arrow(ax, 46, yS - 4, 72, yS - 4, color=INK)
    card(ax, 78, yS - 16, 16, 22, bar_colors=SC)
    arrow(ax, 100, yS - 4, 128, yS - 4, color=INK)
    crowd(ax, 134, yS - 13, 3, 1, 12, SC[1:4])
    T(ax, 160, yS - 22, f"{c.N_KEPT} × {c.N_PER_COMBO[0]}", size=F8, weight="bold", va="top")
    # mapping chevrons (shared)
    for yy, col in ((yR - 4, REF), (yS - 4, INK)):
        ax.add_patch(Polygon([(206, yy + 16), (246, yy + 16), (256, yy), (246, yy - 16), (206, yy - 16), (214, yy)],
                             closed=True, fc=SCHEMA_FILL, ec=SCHEMA, lw=1.0, zorder=3))
        schema_slots(ax, 222, yy - 11, 18, 22, n=7)
        arrow(ax, 186, yy, 207, yy, color=col)
        arrow(ax, 257, yy, 286, yy, color=col)
    T(ax, 231, (yR + yS) / 2 - 4, "14 attributes", size=F8, color=SCHEMA, weight="bold")
    # merge to analysis
    line(ax, [286, 296, 296], [yR - 4, yR - 4, yS - 4], color=INK, lw=1.0)
    line(ax, [286, 296], [yS - 4, yS - 4], color=INK, lw=1.0)
    arrow(ax, 296, (yR + yS) / 2 - 4, 310, (yR + yS) / 2 - 4, color=INK, lw=1.2)
    box(ax, 312, 4, 142, H - 8, ec=INK, fc="#F4F4F4", lw=1.0, r=6)
    for k, yy in enumerate([104, 66, 26]):
        ax.add_patch(Circle((332, yy), 13, fc="white", ec=INK, lw=0.9, zorder=6))
        analysis_icon(ax, k, 332, yy, 16)
        T(ax, 350, yy, LVL[k], size=F9, ha="left")
    return c.save(cv.figure, "P06_current_layout_icons")


# ------------------------------------------------------------------ P07 layer cake (top-down)
@house_style
def p07():
    H = 194
    cv, ax = c.canvas(H)
    # top band: two sources
    yT = 150
    table_stack(ax, 20, yT - 8, 24, 19, n=3)
    arrow(ax, 54, yT + 2, 68, yT + 2, color=REF)
    die(ax, 79, yT + 2, 15)
    arrow(ax, 90, yT + 2, 104, yT + 2, color=REF)
    crowd(ax, 110, yT - 7, 4, 1, 12, REF)
    T(ax, 88, yT + 36, f"Reference: {fmt(c.N_REFERENCE)} individuals", size=F9, color=REF, weight="bold")
    cell, gap = 6.0, 1.0
    gx = 268
    x1, ytop = combo_grid(ax, gx, yT - 14, cell, gap, host_h=2.0)
    strategy_letters(ax, gx - 3, yT - 14, cell, gap)
    llm_chip(ax, gx - 24, yT + 2, 18, label=None)
    T(ax, (gx + x1) / 2 - 8, yT + 36, f"Synthetic: {c.N_KEPT} populations × {c.N_PER_COMBO[0]}", size=F9, weight="bold")
    # middle band: schema as horizontal strip
    yM = 92
    arrow(ax, 88, yT - 14, 150, yM + 14, color=REF, lw=1.6, conn="arc3,rad=0.15")
    arrow(ax, (gx + x1) / 2, yT - 18, 306, yM + 14, color=INK, lw=1.6, conn="arc3,rad=-0.15")
    box(ax, 60, yM - 10, 336, 22, ec=SCHEMA, fc=SCHEMA_FILL, lw=1.0, r=5)
    for i in range(14):
        ax.add_patch(FancyBboxPatch((66 + i * 23.4, yM - 6), 19.5, 14, boxstyle="round,pad=0,rounding_size=2",
                                    ec=SCHEMA, fc="white", lw=0.6, zorder=5))
    T(ax, 228, yM - 15, "mapped onto the same 14 attributes", size=F8, color=SCHEMA, weight="bold", va="top")
    # bottom band: analyses
    yB = 34
    xs = [90, 228, 366]
    for k, xx in enumerate(xs):
        arrow(ax, 228 + (k - 1) * 60, yM - 26, xx, yB + 18, color=INK, lw=1.1)
        ax.add_patch(Circle((xx, yB), 15, fc="white", ec=INK, lw=1.0, zorder=6))
        analysis_icon(ax, k, xx, yB, 18)
        T(ax, xx, yB - 20, LVL1[k], size=F9, va="top")
    return c.save(cv.figure, "P07_layer_cake")


# ------------------------------------------------------------------ P08 unit chart (one dot = one individual)
@house_style
def p08():
    H = 178
    cv, ax = c.canvas(H)
    pitch = 0.88
    # reference 100 x 100
    rx, ry = 8, 30
    xs, ys = np.meshgrid(np.arange(100), np.arange(100))
    xs = xs.ravel(); ys = ys.ravel()
    judged = (xs < 10) & (ys >= 90)
    ax.scatter(rx + xs[~judged] * pitch, ry + ys[~judged] * pitch, s=0.18, marker="s", c=c.RESIDUAL_GREY, linewidths=0, zorder=4)
    ax.scatter(rx + xs[judged] * pitch, ry + ys[judged] * pitch, s=0.5, marker="s", c=REF, linewidths=0, zorder=4)
    T(ax, rx + 44, ry - 8, f"Reference, {fmt(c.N_REFERENCE)}", size=F9, color=REF, weight="bold", va="top")
    T(ax, rx + 44, ry - 20, "dark corner: 100 judged", size=F8, color=REF, va="top")
    # synthetic: each combination 10 x 10, same pitch
    gx, gy = 150, 52
    blk = 10 * pitch
    g = 3.0
    bx, by = np.meshgrid(np.arange(10), np.arange(10))
    bx = bx.ravel(); by = by.ravel()
    allx, ally, allc = [], [], []
    for j, m in enumerate(c.MODEL_ORDER):
        for i, s in enumerate(c.STRATEGIES):
            x0 = gx + j * (blk + g)
            y0 = gy + (4 - i) * (blk + g)
            if (s, m) in c.WITHDRAWN:
                ax.add_patch(Rectangle((x0 - 0.5, y0 - 0.5), blk, blk, fc="white", ec=c.RESIDUAL_GREY, lw=0.4, zorder=4))
                cross(ax, x0 + blk / 2 - 0.5, y0 + blk / 2 - 0.5, blk * 0.8, lw=0.6)
                continue
            allx += list(x0 + bx * pitch); ally += list(y0 + by * pitch); allc += [c.STRAT_COLOR[s]] * 100
        ax.add_patch(Rectangle((gx + j * (blk + g) - 0.5, gy + 5 * (blk + g)), blk, 2.4, fc=c.HOST[c.HOSTING[m]], ec="none"))
    ax.scatter(allx, ally, s=0.18, marker="s", c=allc, linewidths=0, zorder=4)
    strategy_letters(ax, gx - 4, gy - 0.5, blk, g)
    gx1 = gx + 13 * (blk + g) - g
    T(ax, (gx + gx1) / 2, gy + 5 * (blk + g) + 10, "13 LLMs", size=F9, weight="bold")
    T(ax, (gx + gx1) / 2, gy - 8, f"Synthetic, {c.N_KEPT} × {c.N_PER_COMBO[0]}", size=F9, weight="bold", va="top")
    T(ax, (gx + gx1) / 2, 12, "one dot = one individual", size=F8, color=SOFT)
    # analyses, each with the inputs that feed it (no crossing arrows)
    xa = 430
    rows = [(140, "Population level", ("ref", "syn")), (92, "Individual level", ("judged", "syn")),
            (44, "Operational", ("syn",))]
    for k, (yy, lab, feeds) in enumerate(rows):
        ax.add_patch(Circle((xa, yy), 15, fc="white", ec=INK, lw=1.0, zorder=6))
        analysis_icon(ax, k, xa, yy, 18)
        T(ax, xa + 15, yy - 18, lab, size=F8, va="top", ha="right")
        fx = 386 - 18 * (len(feeds) - 1)
        for f in feeds:
            if f == "ref":
                ax.add_patch(Rectangle((fx, yy - 7), 14, 14, fc=c.RESIDUAL_GREY, ec="none", zorder=5))
            elif f == "judged":
                ax.add_patch(Rectangle((fx + 4, yy - 3), 6, 6, fc=REF, ec="none", zorder=5))
            else:
                for i2, col in enumerate(SC):
                    ax.add_patch(Rectangle((fx, yy + 5.6 - i2 * 2.8), 14, 2.4, fc=col, ec="none", zorder=5))
            fx += 18
        arrow(ax, 403, yy, xa - 17, yy, color=INK, lw=1.0, head=4)
    return c.save(cv.figure, "P08_unit_dots")


# ------------------------------------------------------------------ P09 typographic equation
@house_style
def p09():
    H = 104
    cv, ax = c.canvas(H)
    yR, yS = 78, 30
    table_stack(ax, 6, yR - 9, 20, 16, n=3)
    T(ax, 34, yR, "13", size=F12, color=REF, weight="bold", ha="left")
    arrow(ax, 52, yR, 70, yR, color=REF, lw=1.4)
    crowd(ax, 76, yR - 9, 3, 1, 12, REF)
    T(ax, 112, yR, fmt(c.N_REFERENCE), size=F12, color=REF, weight="bold", ha="left")
    llm_chip(ax, 16, yS, 26)
    T(ax, 34, yS, f"{c.N_KEPT}", size=F12, weight="bold", ha="left")
    arrow(ax, 52, yS, 70, yS, color=INK, lw=1.4)
    crowd(ax, 76, yS - 9, 3, 1, 12, SC[1:4])
    T(ax, 112, yS, f"{c.N_PER_COMBO[0]} each", size=F12, weight="bold", ha="left")
    # schema bracket
    line(ax, [170, 176, 176, 170], [yR + 12, yR + 12, yS - 12, yS - 12], color=SCHEMA, lw=1.2)
    schema_slots(ax, 184, yS - 12, 16, yR - yS + 24)
    T(ax, 192, yS - 18, "14", size=F10, color=SCHEMA, weight="bold", va="top")
    arrow(ax, 206, (yR + yS) / 2, 228, (yR + yS) / 2, color=INK, lw=1.4)
    for k, xx in enumerate([258, 332, 410]):
        ax.add_patch(Circle((xx, (yR + yS) / 2 + 8), 16, fc="white", ec=INK, lw=1.0, zorder=6))
        analysis_icon(ax, k, xx, (yR + yS) / 2 + 8, 19)
        T(ax, xx, (yR + yS) / 2 - 14, LVL[k].replace("\n", " ").replace("Operational performance", "Operational"), size=F9, va="top")
    return c.save(cv.figure, "P09_equation")


ALL = {"P10": lambda: p01(sections=True), "P01": p01, "P02": p02, "P03": p03, "P04": p04, "P05": p05, "P06": p06, "P07": p07, "P08": p08, "P09": p09}

if __name__ == "__main__":
    for k in (sys.argv[1:] or ALL):
        print(k, ALL[k]())
