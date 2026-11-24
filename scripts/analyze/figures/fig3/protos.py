"""Figure 3 prototypes. Run: python protos.py [P01 P02 ...]  (no args = all).

Set F3DEBUG=1 to write an unchecked preview into code/debug/ instead of the gallery PNG.
"""
from __future__ import annotations

import sys
from collections import defaultdict

import numpy as np
from matplotlib.patches import Circle, PathPatch, Rectangle
from matplotlib.path import Path as MPath

import common as c
from common import (F8, F9, F10, INK, SOFT, FAINT, RULE, PANEL, REFC, T, box, line, arrow, chip, die,
                    list_glyph, bars_glyph, context_glyph, query_glyph, pill, letter, step_glyph, panel_letter,
                    text_width)
from population_synthetic.analysis.utils.style import house_style

S = c.STRATEGIES
SC = c.STRAT_COLOR

# row order inside each level, chosen to limit edge crossings (layout only; asserted against config)
LEVEL_ROWS = {
    1: ["age", "biological_sex", "region", "parental_structure"],
    2: ["education_level", "civil_status", "birth_country_detail"],
    3: ["employment_status", "household_size"],
    4: ["socioeconomic_class", "employment_type", "industry_sector"],
    5: ["income_source", "housing_tenure"],
}
assert {k: sorted(v) for k, v in LEVEL_ROWS.items()} == {k: sorted(v) for k, v in c.BY_LEVEL.items()}

GLYPH_KEY = [("context", "attributes already set"), ("list", "candidate values"),
             ("weigh", "probabilities"), ("choose", "LLM picks"), ("draw", "random draw")]


def wrap2(name):
    parts = name.split(" ")
    return name if len(parts) == 1 else parts[0] + "\n" + " ".join(parts[1:])


def bez(ax, p0, p1, color=FAINT, lw=0.6, z=2, bend=0.5, ls="-"):
    (x0, y0), (x1, y1) = p0, p1
    dx = (x1 - x0) * bend
    path = MPath([(x0, y0), (x0 + dx, y0), (x1 - dx, y1), (x1, y1)],
                 [MPath.MOVETO, MPath.CURVE4, MPath.CURVE4, MPath.CURVE4])
    ax.add_patch(PathPatch(path, fc="none", ec=color, lw=lw, zorder=z, ls=ls))


def dag(ax, x0, x1, y0, y1, wrap=True, edges=True, diff_badge=False, heads=True, size=F8, pill_h=None,
        edge_color=None):
    """Layered dependency graph: columns = levels, pills = attributes, curves = direct dependencies.
    Edges that skip a level run in the channel between two pill rows, never under a pill."""
    names = {a: (wrap2(c.NAME[a]) if wrap else c.NAME[a]) for a in c.ORDER}
    nl = c.N_LEVELS
    widths = {k: max(max(text_width(s, size) for s in names[a].split("\n")) for a in LEVEL_ROWS[k]) + 7
              for k in LEVEL_ROWS}
    gap = (x1 - x0 - sum(widths.values())) / (nl - 1)
    assert gap > 6, gap
    head_h = 14 if heads else 0
    ph = pill_h or (22 if wrap else 13)
    step = ((y1 - head_h) - y0) / 4
    pos, colx = {}, {}
    xc = x0
    for k in range(1, nl + 1):
        wk = widths[k]
        colx[k] = (xc, xc + wk)
        for i, a in enumerate(LEVEL_ROWS[k]):
            pos[a] = (xc, xc + wk, y1 - head_h - step * (i + 0.5))
        if heads:
            ax.add_patch(Circle((xc + wk / 2, y1 - 6), 5.5, fc=PANEL, ec=SOFT, lw=0.6, zorder=3))
            T(ax, xc + wk / 2, y1 - 6.1, str(k), size=F8, color=INK, weight="bold")
        xc += wk + gap
    ec = edge_color or SOFT
    if edges:
        chan_count = defaultdict(int)
        for a in c.ORDER:
            for d in c.DEPS[a]:
                xa0, xa1, ya = pos[d]
                xb0, xb1, yb = pos[a]
                la, lb = c.LEVEL[d], c.LEVEL[a]
                if lb - la == 1:
                    bez(ax, (xa1, ya), (xb0 - 3, yb), color=ec, lw=0.6, z=2)
                else:
                    ych = yb + step / 2 if ya > yb else yb - step / 2
                    key = round(ych, 1)
                    ych += chan_count[key] * 1.8
                    chan_count[key] += 1
                    g1 = (colx[la][1] + colx[la + 1][0]) / 2
                    g2 = (colx[lb - 1][1] + colx[lb][0]) / 2
                    bez(ax, (xa1, ya), (g1, ych), color=ec, lw=0.6, z=2)
                    line(ax, [g1, g2], [ych, ych], color=ec, lw=0.6, z=2)
                    bez(ax, (g2, ych), (xb0 - 3, yb), color=ec, lw=0.6, z=2)
                arrow(ax, xb0 - 3.4, yb, xb0, yb, color=ec, lw=0.5, head=3.4, z=2.5)
    for a, (xa, xb, y) in pos.items():
        pill(ax, (xa + xb) / 2, y, xb - xa, ph, names[a], color=INK, fc=c.NODE, size=size, z=5, lw=0.7)
        if diff_badge and c.DIFFERS[a]:
            ax.add_patch(Circle((xb - 1, y + ph / 2 - 1), 3.6, fc=REFC, ec="white", lw=0.5, zorder=7))
            T(ax, xb - 1, y + ph / 2 - 1.3, "≠", size=F8, color="white", weight="bold", zorder=8)
    return pos


def strategy_matrix(ax, x0, x1, y0, y1, calls=True, header=True, gsize=13, rail_lw=2.2):
    """Rows A-E; columns context, list, probabilities, final pick; a coloured rail threads each row."""
    cols = ["context", "list", "weigh", "final"]
    lx = x0 + 6
    right = x1 - (46 if calls else 4)
    xs = np.linspace(lx + 20, right - 14, len(cols))
    head_h = 22 if header else 0
    rows_y = np.linspace(y1 - head_h - 10, y0 + 8, len(S))
    if header:
        for kx, k in zip(xs, cols):
            if k == "final":
                chip(ax, kx - 8, y1 - 9, 12, color=SOFT, label=False)
                T(ax, kx + 0.5, y1 - 9, "/", size=F8, color=SOFT)
                die(ax, kx + 8.5, y1 - 9, 9.5, color=SOFT)
            else:
                step_glyph(ax, k, kx, y1 - 9, 12, color=SOFT)
        if calls:
            T(ax, x1 - 21, y1 - 9, "LLM calls\nper individual", size=F8, color=SOFT, linespacing=0.95)
    for s, y in zip(S, rows_y):
        letter(ax, lx, y, s, size=F10)
        line(ax, [lx + 8, right], [y, y], color=SC[s], lw=rail_lw, z=2)
        st = c.STEPS[s]
        have = {"context": c.HAS_CONTEXT[s], "list": "list" in st, "weigh": "weigh" in st, "final": True}
        for kx, k in zip(xs, cols):
            if not have[k]:
                continue
            if k == "final":
                if st[-1] == "draw":
                    die(ax, kx, y, gsize)
                else:
                    chip(ax, kx, y, gsize + 4)
            else:
                step_glyph(ax, k, kx, y, gsize, color=INK)
        if calls:
            T(ax, x1 - 21, y, f"{c.CALLS[s]:.0f}", size=F9, color=INK, weight="bold")
    return xs, rows_y


def glyph_key(ax, x0, y, items=GLYPH_KEY, gs=10, size=F8, color=INK, gap=9):
    x = x0
    for k, lab in items:
        if k == "choose":
            chip(ax, x + gs / 2, y, gs + 2, color=color, label=False)
        elif k == "draw":
            die(ax, x + gs / 2, y, gs * 0.9, color=color)
        else:
            step_glyph(ax, k, x + gs / 2, y, gs, color=color)
        T(ax, x + gs + 3, y, lab, size=size, ha="left", color=INK)
        x += gs + 3 + text_width(lab, size) + gap
    return x


def glyph_sentence(ax, s, x, y, gs=14, pitch=21, rail=True, rail_len=None):
    seq = (["context"] if c.HAS_CONTEXT[s] else []) + c.STEPS[s]
    letter(ax, x, y, s, size=F10)
    gx = x + 12
    if rail:
        line(ax, [gx, gx + (rail_len or 4 * pitch)], [y, y], color=SC[s], lw=2.0, z=1)
    if not c.HAS_CONTEXT[s]:
        gx += pitch
    for k in seq:
        cx = gx + pitch / 2
        if k == "choose":
            chip(ax, cx, y, gs + 4)
        elif k == "draw":
            die(ax, cx, y, gs * 0.9)
        else:
            step_glyph(ax, k, cx, y, gs)
        gx += pitch


# ================================================================== P01 cleaned current
@house_style
def p01():
    H = 214
    fig, ax = c.canvas(H)
    panel_letter(ax, 2, H - 2, "A")
    dag(ax, 16, 282, 22, H - 4, wrap=True, edges=True, diff_badge=True)
    T(ax, 19, 9, "≠", size=F8, color="white", weight="bold", zorder=8,
      bbox=dict(boxstyle="circle,pad=0.12", fc=REFC, ec="none"))
    T(ax, 27, 9, "conditioning differs from the reference tables", size=F8, ha="left", color=SOFT)
    panel_letter(ax, 296, H - 2, "B")
    x0, x1 = 312, 452
    xs = np.linspace(x0 + 10, x1 - 12, 5)
    ybot = 28
    query_glyph(ax, (xs[0] + xs[-1]) / 2, H - 11, 17)
    ys = {"context": H - 52, "list": H - 88, "weigh": H - 122, "final": H - 160}
    for s, x in zip(S, xs):
        letter(ax, x, H - 30, s)
        line(ax, [x, x], [H - 38, ybot + 6], color=SC[s], lw=2.4, z=2)

    def plate(k, members, draw):
        xm = [xs[S.index(s)] for s in members]
        y = ys[k]
        box(ax, min(xm) - 8, y - 12, max(xm) - min(xm) + 16, 24, ec=SOFT, fc=PANEL, lw=0.6, r=5, z=3)
        draw((min(xm) + max(xm)) / 2, y)

    plate("context", [s for s in S if c.HAS_CONTEXT[s]], lambda x, y: context_glyph(ax, x, y, 18))
    plate("list", [s for s in S if "list" in c.STEPS[s]], lambda x, y: list_glyph(ax, x, y, 16))
    plate("weigh", [s for s in S if "weigh" in c.STEPS[s]], lambda x, y: bars_glyph(ax, x, y, 16))
    plate("final", [s for s in S if c.STEPS[s][-1] == "choose"], lambda x, y: chip(ax, x, y, 22))
    die(ax, xs[-1], ys["final"], 15)
    for s, x in zip(S, xs):
        ax.add_patch(Circle((x, ybot + 2), 3.8, fc=SC[s], ec="white", lw=0.6, zorder=4))
    T(ax, (xs[0] + xs[-1]) / 2, 13, "one value per attribute", size=F8, color=SOFT)
    return c.save(fig, "P01_cleaned_current")


# ================================================================== P02 transit rails (stacked)
@house_style
def p02():
    H = 226
    fig, ax = c.canvas(H)
    panel_letter(ax, 2, H - 2, "A")
    dag(ax, 16, 452, 112, H - 4, wrap=False, edges=True, pill_h=13)
    panel_letter(ax, 2, 104, "B")
    xs = {"query": 44, "context": 122, "list": 200, "weigh": 278, "final": 356, "out": 440}
    ys = np.linspace(92, 28, 5)
    for k in ("context", "list", "weigh", "final"):
        ax.add_patch(Rectangle((xs[k] - 13, 19), 26, 82, fc=PANEL, ec="none", zorder=0.5))
    for s, y in zip(S, ys):
        letter(ax, 22, y, s)
        line(ax, [xs["query"], xs["out"]], [y, y], color=SC[s], lw=2.2, z=2)
        st = c.STEPS[s]
        query_glyph(ax, xs["query"], y, 12)
        if c.HAS_CONTEXT[s]:
            context_glyph(ax, xs["context"], y, 14)
        if "list" in st:
            list_glyph(ax, xs["list"], y, 12)
        if "weigh" in st:
            bars_glyph(ax, xs["weigh"], y, 12)
        if st[-1] == "draw":
            die(ax, xs["final"], y, 12)
        else:
            chip(ax, xs["final"], y, 16)
        ax.add_patch(Circle((xs["out"], y), 3.5, fc=SC[s], ec="white", lw=0.6, zorder=4))
    for k, lab in (("query", "attribute"), ("context", "attributes already set"), ("list", "candidate values"),
                   ("weigh", "probabilities"), ("final", "LLM picks or draw"), ("out", "value")):
        T(ax, xs[k], 9, lab, size=F8, color=SOFT)
    return c.save(fig, "P02_transit_rails")


# ================================================================== P03 context staircase + strategy matrix
@house_style
def p03():
    H = 214
    fig, ax = c.canvas(H)
    panel_letter(ax, 2, H - 2, "A")
    n = len(c.ORDER)
    cell = 10.6
    gx0 = 14
    gy1 = H - 10
    for i, a in enumerate(c.ORDER):
        y = gy1 - (i + 1) * cell
        for j in range(i):
            x = gx0 + j * cell
            d = c.ORDER[j]
            ax.add_patch(Rectangle((x + 0.5, y + 0.5), cell - 1, cell - 1, fc=PANEL, ec="none", zorder=2))
            if d in c.DEPS[a]:
                ax.add_patch(Circle((x + cell / 2, y + cell / 2), cell * 0.27, fc=INK, ec="none", zorder=4))
            if d in c.REF_COND[a]:
                ax.add_patch(Circle((x + cell / 2, y + cell / 2), cell * 0.4, fc="none", ec=REFC, lw=0.8, zorder=5))
        T(ax, gx0 + i * cell + 2, y + cell / 2, c.NAME[a], size=F8, ha="left")
    for k in range(2, c.N_LEVELS + 1):
        i = c.ORDER.index(c.BY_LEVEL[k][0])
        yy = gy1 - i * cell
        line(ax, [gx0 - 2, gx0 + i * cell], [yy, yy], color=SOFT, lw=0.6, z=3)
    for k in range(1, c.N_LEVELS + 1):
        i0 = c.ORDER.index(c.BY_LEVEL[k][0])
        i1 = c.ORDER.index(c.BY_LEVEL[k][-1])
        T(ax, gx0 - 7, gy1 - (i0 + i1 + 1) / 2 * cell, str(k), size=F8, color=SOFT, weight="bold")
    ky = gy1 - n * cell - 15
    ax.add_patch(Rectangle((gx0, ky - 4), 8, 8, fc=PANEL, ec="none"))
    T(ax, gx0 + 11, ky, "in the prompt", size=F8, ha="left")
    ax.add_patch(Circle((gx0 + 74, ky), 2.9, fc=INK, ec="none"))
    T(ax, gx0 + 79, ky, "dependency", size=F8, ha="left")
    ax.add_patch(Circle((gx0 + 134, ky), 4.2, fc="none", ec=REFC, lw=0.8))
    T(ax, gx0 + 140, ky, "reference table filter", size=F8, ha="left")
    panel_letter(ax, 262, H - 2, "B")
    strategy_matrix(ax, 270, 453, 38, H - 4, calls=True)
    glyph_key(ax, 272, 23, [GLYPH_KEY[0], GLYPH_KEY[1]], gs=9, gap=7)
    glyph_key(ax, 272, 8, GLYPH_KEY[2:], gs=9, gap=7)
    return c.save(fig, "P03_context_staircase")


# ================================================================== P04 mirrored arcs (vertical) + matrix
@house_style
def p04():
    H = 214
    fig, ax = c.canvas(H)
    n = len(c.ORDER)
    xc = 150
    half = 40
    ytop, ybot = H - 24, 20
    ys = {a: ytop - i * (ytop - ybot) / (n - 1) for i, a in enumerate(c.ORDER)}
    # level bands behind the names
    for k in range(1, c.N_LEVELS + 1):
        aa = c.BY_LEVEL[k]
        yt, yb = ys[aa[0]] + 5.6, ys[aa[-1]] - 5.6
        if k % 2:
            ax.add_patch(Rectangle((xc - half, yb), 2 * half, yt - yb, fc=PANEL, ec="none", zorder=0.5))
        T(ax, xc - half - 4, (yt + yb) / 2, "", size=F8)
    for a in c.ORDER:
        T(ax, xc, ys[a], c.NAME[a], size=F8)
    xl, xr = xc - half, xc + half

    def arc(p, q, x, side, color, lw, ls="-"):
        ya, yb = ys[p], ys[q]
        r = abs(ya - yb) / 2
        bulge = min(r * 0.9, 68)
        t = np.linspace(0, np.pi, 60)
        yy = (ya + yb) / 2 + r * np.cos(t)
        xx = x + side * bulge * np.sin(t)
        line(ax, xx, yy, color=color, lw=lw, z=2, ls=ls)

    for a in c.ORDER:
        for d in c.DEPS[a]:
            arc(d, a, xl, -1, INK, 0.75)
        for d in c.REF_COND[a]:
            arc(d, a, xr, +1, REFC, 0.75, ls=(0, (2.4, 1.4)))
        ax.add_patch(Circle((xl, ys[a]), 1.6, fc=INK, ec="none", zorder=3))
        ax.add_patch(Circle((xr, ys[a]), 1.6, fc=REFC, ec="none", zorder=3))
    T(ax, xl - 36, H - 8, "LLM dependency", size=F8, weight="bold")
    T(ax, xr + 36, H - 8, "reference table filter", size=F8, color=REFC)
    T(ax, xc, 8, "resolution order, top to bottom", size=F8, color=SOFT)
    line(ax, [276, 276], [10, H - 6], color=RULE, lw=0.6)
    strategy_matrix(ax, 284, 453, 36, H - 4, calls=False)
    glyph_key(ax, 288, 21, [GLYPH_KEY[0]], gs=9)
    glyph_key(ax, 288, 7, [("list", "values"), ("weigh", "probabilities")], gs=9, gap=6)
    return c.save(fig, "P04_mirrored_arcs")


# ================================================================== P05 layer cake + decision key
@house_style
def p05():
    H = 214
    fig, ax = c.canvas(H)
    panel_letter(ax, 2, H - 2, "A")
    bx0, bx1 = 30, 262
    bh, bg = 33, 4
    yb0 = 18
    for k in range(1, c.N_LEVELS + 1):
        y = yb0 + (k - 1) * (bh + bg)
        ax.add_patch(Rectangle((bx0, y), bx1 - bx0, bh, fc=PANEL, ec="none", zorder=1))
        T(ax, bx0 - 9, y + bh / 2, str(k), size=F9, color=SOFT, weight="bold")
        names = [c.NAME[a] for a in LEVEL_ROWS[k]]
        ws = [max(text_width(nm, F8) + 8, bh) for nm in names]
        if sum(ws) + 4 * (len(ws) - 1) > bx1 - bx0 - 8:
            names = [wrap2(nm) for nm in names]
            ws = [max(text_width(p, F8) for p in nm.split("\n")) + 8 for nm in names]
        tot = sum(ws) + 5 * (len(ws) - 1)
        x = (bx0 + bx1) / 2 - tot / 2
        for nm, w in zip(names, ws):
            pill(ax, x + w / 2, y + bh / 2, w, bh - 8, nm, color=INK, fc="white", size=F8, lw=0.7)
            x += w + 5
    top = yb0 + c.N_LEVELS * (bh + bg) - bg
    arrow(ax, bx1 + 8, yb0, bx1 + 8, top, color=SOFT, lw=0.8)
    T(ax, bx1 + 12, (yb0 + top) / 2, "the prompt carries everything set below", size=F8, color=SOFT, rotation=90,
      ha="left")
    T(ax, (bx0 + bx1) / 2, 8, "", size=F8)
    # B: decision key
    panel_letter(ax, 286, H - 2, "B")
    qx = 312
    qs = [("context", H - 24), ("list", H - 64), ("weigh", H - 104), ("who", H - 144)]
    for k, y in qs:
        if k == "who":
            chip(ax, qx - 9, y, 14, label=False)
            T(ax, qx + 0.5, y, "/", size=F8, color=SOFT)
            die(ax, qx + 10, y, 11)
        else:
            step_glyph(ax, k, qx, y, 16)
            T(ax, qx + 11, y, "?", size=F10, weight="bold", color=SOFT, ha="left")
    xleaf = 436
    for (k, y), s in zip(qs[:3], S[:3]):
        line(ax, [qx + 20, xleaf], [y, y], color=SC[s], lw=1.8)
        T(ax, (qx + 20 + xleaf) / 2, y + 6, "no", size=F8, color=SOFT)
        ax.add_patch(Circle((xleaf + 7, y), 8.5, fc=SC[s], ec="none", zorder=3))
        T(ax, xleaf + 7, y - 0.2, c.LETTERS[s], size=F10, color="white", weight="bold", zorder=4)
    for (k1, y1), (k2, y2) in zip(qs[:-1], qs[1:]):
        line(ax, [qx, qx], [y1 - 11, y2 + 11], color=SOFT, lw=1.0)
        T(ax, qx - 5, (y1 + y2) / 2, "yes", size=F8, color=SOFT, ha="right")
    yw = qs[-1][1]
    line(ax, [qx + 20, xleaf], [yw, yw], color=SC[S[3]], lw=1.8)
    ax.add_patch(Circle((xleaf + 7, yw), 8.5, fc=SC[S[3]], ec="none", zorder=3))
    T(ax, xleaf + 7, yw - 0.2, "D", size=F10, color="white", weight="bold", zorder=4)
    line(ax, [qx + 10, qx + 10, xleaf], [yw - 8, yw - 34, yw - 34], color=SC[S[4]], lw=1.8)
    ax.add_patch(Circle((xleaf + 7, yw - 34), 8.5, fc=SC[S[4]], ec="none", zorder=3))
    T(ax, xleaf + 7, yw - 34.2, "E", size=F10, color="white", weight="bold", zorder=4)
    T(ax, (qx + 20 + xleaf) / 2, yw + 6, "LLM picks", size=F8, color=SOFT)
    T(ax, (qx + 20 + xleaf) / 2, yw - 28, "random draw", size=F8, color=SOFT)
    glyph_key(ax, 292, 8, [("context", "set"), ("list", "values"), ("weigh", "probabilities")], gs=9, gap=6)
    return c.save(fig, "P05_layer_cake_decision_key")


# ================================================================== P06 record filmstrip
@house_style
def p06():
    H = 214
    fig, ax = c.canvas(H)
    rows_y = {a: H - 22 - i * 12.2 for i, a in enumerate(c.ORDER)}
    for a, y in rows_y.items():
        T(ax, 84, y, c.NAME[a], size=F8, ha="right")
    cw, gap = 34, 13
    ytop_card = rows_y[c.ORDER[0]] + 8
    ybot_card = rows_y[c.ORDER[-1]] - 8
    for k in range(1, c.N_LEVELS + 1):
        x = 92 + (k - 1) * (cw + gap)
        box(ax, x, ybot_card, cw, ytop_card - ybot_card, ec=SOFT, fc="white", lw=0.6, r=3, z=1)
        ax.add_patch(Circle((x + cw / 2, H - 7), 5, fc=PANEL, ec=SOFT, lw=0.6))
        T(ax, x + cw / 2, H - 7.1, str(k), size=F8, weight="bold")
        for a, y in rows_y.items():
            lv = c.LEVEL[a]
            if lv < k:
                ax.add_patch(Rectangle((x + 4, y - 3.6), cw - 8, 7.2, fc=FAINT, ec="none", zorder=2))
            elif lv == k:
                ax.add_patch(Rectangle((x + 4, y - 3.6), cw - 8, 7.2, fc=INK, ec="none", zorder=2))
            else:
                ax.add_patch(Rectangle((x + 4, y - 3.6), cw - 8, 7.2, fc="white", ec=RULE, lw=0.5, zorder=2))
        if k < c.N_LEVELS:
            ym = (ytop_card + ybot_card) / 2
            arrow(ax, x + cw + 2, ym, x + cw + gap - 2, ym, color=SOFT, lw=0.7)
    ky = 9
    for i, (fc, ec, lab) in enumerate(((INK, "none", "set at this level"), (FAINT, "none", "in the prompt"),
                                       ("white", RULE, "not yet set"))):
        x = 92 + i * 78
        ax.add_patch(Rectangle((x, ky - 3.6), 14, 7.2, fc=fc, ec=ec, lw=0.5))
        T(ax, x + 17, ky, lab, size=F8, ha="left")
    sx = 340
    line(ax, [sx - 8, sx - 8], [14, H - 6], color=RULE, lw=0.6)
    ys = np.linspace(H - 18, 52, 5)
    for s, y in zip(S, ys):
        glyph_sentence(ax, s, sx + 2, y, gs=15, pitch=23, rail_len=4 * 23 + 2)
    glyph_key(ax, sx - 2, 31, [("context", "attributes set")], gs=9)
    glyph_key(ax, sx - 2, 18, [("list", "values"), ("weigh", "probabilities")], gs=9, gap=5)
    glyph_key(ax, sx - 2, 5, [("draw", "random draw")], gs=9)
    return c.save(fig, "P06_record_filmstrip")


# ================================================================== P07 call budget bars
@house_style
def p07():
    H = 214
    fig, ax = c.canvas(H)
    panel_letter(ax, 2, H - 2, "A")
    dag(ax, 16, 452, 120, H - 4, wrap=False, edges=True, pill_h=13)
    panel_letter(ax, 2, 112, "B")
    glyph_key(ax, 40, 104, GLYPH_KEY, gs=9, gap=8)
    x0, x1 = 68, 440
    sx = (x1 - x0) / 42
    ys = np.linspace(86, 38, 5)
    bh = 10.5
    segs = {}
    for s in S:
        st = c.STEPS[s]
        if st == ["choose"]:
            segs[s] = [("choose", 14)]
        elif st == ["list", "choose"]:
            segs[s] = [("list", 14), ("choose", 14)]
        elif st == ["list", "weigh", "choose"]:
            segs[s] = [("list", 14), ("weigh", 14), ("choose", 14)]
        else:  # E: 13 list calls + 13 weight calls + 1 distribution call for age (numeric)
            segs[s] = [("list", 13), ("weigh", 14)]
        assert sum(v for _, v in segs[s]) == c.CALLS[s], s
    for t in (0, 14, 28, 42):
        line(ax, [x0 + t * sx] * 2, [30, 93], color=RULE, lw=0.5, z=0.5)
        T(ax, x0 + t * sx, 23, str(t), size=F8, color=SOFT)
    T(ax, (x0 + x1) / 2, 10, "LLM calls per individual (median)", size=F8, color=SOFT)
    for s, y in zip(S, ys):
        letter(ax, 14, y, s)
        if c.HAS_CONTEXT[s]:
            context_glyph(ax, 38, y, 15)
        else:
            box(ax, 38 - 7.5, y - 6, 15, 12, ec=FAINT, fc="white", lw=0.6, r=1.5, ls=(0, (1.5, 1.2)))
        xx = x0
        for k, v in segs[s]:
            w = v * sx
            ax.add_patch(Rectangle((xx, y - bh / 2), w - 1.2, bh, fc=SC[s], ec="none", zorder=2))
            if k == "list":
                list_glyph(ax, xx + w / 2, y, 9.5, fill="white")
            elif k == "weigh":
                bars_glyph(ax, xx + w / 2, y, 9.5, fill="white")
            else:
                chip(ax, xx + w / 2, y, 11, fill="white", label=False)
            xx += w
        if c.STEPS[s][-1] == "draw":
            die(ax, xx + 7, y, 10)
    return c.save(fig, "P07_call_budget")


# ================================================================== P08 compact strip
@house_style
def p08():
    H = 150
    fig, ax = c.canvas(H)
    panel_letter(ax, 2, H - 2, "A")
    dag(ax, 16, 282, 6, H - 4, wrap=True, edges=True, pill_h=20)
    panel_letter(ax, 290, H - 2, "B")
    strategy_matrix(ax, 296, 450, 24, H - 4, calls=False, gsize=12)
    glyph_key(ax, 300, 8, [("context", "set"), ("list", "values"), ("weigh", "probabilities")], gs=8, gap=5)
    return c.save(fig, "P08_compact_strip")


ALL = {"P01": p01, "P02": p02, "P03": p03, "P04": p04, "P05": p05, "P06": p06, "P07": p07, "P08": p08}

if __name__ == "__main__":
    for k in (sys.argv[1:] or ALL):
        try:
            print(k, ALL[k]())
        except Exception as e:
            print(k, "FAILED", str(e)[:200])
