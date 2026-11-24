"""Figure 3 round 9: panel A in Figure 2A's colour code (P23b) and a spectrum of panel-A variants (P24-P29).

Panel B and the simplified strategy-E example are exactly P23's (protos8.grid / protos8.example_strip).
Figure 2A colour code, sampled from the published fig2A.png / the current Figure 3 image (exact pixel values):
  level 1 #EEFFE2, level 2 #D2EAC1, level 3 #A5D286, level 4 #74A44D, level 5 #417215 (level 5 exists only in 3A);
  attribute box #BDC9D8 with outline #2C5633; highlighted box #86ACD8; 3A context box #E1E4E0.
"""
from __future__ import annotations

import sys

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, FancyBboxPatch, PathPatch, Rectangle
from matplotlib.path import Path as MPath

import common as c
from common import F8, INK, SOFT, T, box, line, arrow, panel_letter, text_width
from protos8 import (GROUPS, FEEDS, SHORT, HIGHLIGHTED, ctx_text, ancestors, grid, example_strip, LINE,
                     CTX_WORD, ORDER_IN_LIST)
from population_synthetic.analysis.utils.style import house_style

LEVEL_FILL = {1: "#EEFFE2", 2: "#D2EAC1", 3: "#A5D286", 4: "#74A44D", 5: "#417215"}
LEVEL_TEXT = {1: INK, 2: INK, 3: INK, 4: INK, 5: "#FFFFFF"}   # black on #417215 is unreadable
ATTR = "#BDC9D8"
ATTR_EDGE = "#2C5633"
HL = "#86ACD8"
CTX_FILL = "#E1E4E0"
GUTTER = 13
X0 = 12
MAX_RIGHT = 271          # panel B needs the rest of the 456 pt


def empty_set(ax, x, y, color=SOFT):
    ax.add_patch(Circle((x, y), 3.2, fc="none", ec=color, lw=0.7, zorder=6))
    line(ax, [x - 4.2, x + 4.2], [y - 4.2, y + 4.2], color=color, lw=0.7, z=6)


def col_widths(pad=6, ctx_in=True):
    w = {}
    for k, gs in GROUPS.items():
        texts = [SHORT[a] for g in gs for a in g] + [f"Level {k}"] + ([ctx_text(g, maxw=0) for g in gs] if ctx_in else [])
        w[k] = max(text_width(p, F8) for t_ in texts for p in t_.split("\n")) + pad
    return w


def feed_arrows(ax, pos, ctxpos, gap, color=INK):
    for (k, gi), srcs in FEEDS.items():
        cx, cy = ctxpos[(k, gi)]
        gx = cx - gap / 2
        for s_ in srcs:
            _, xr, ys = pos[s_]
            line(ax, [xr, gx], [ys, ys], color=color, lw=0.6, z=4)
            line(ax, [gx, gx], [ys, cy], color=color, lw=0.6, z=4)
        arrow(ax, gx, cy, cx, cy, color=color, lw=0.6, head=3.0, z=4)


# ================================================================== box layouts (P23b, P24, P25)
def boxes_a(ax, x0, ytop, bands=False, bold=False, header_ctx=False, gap=4):
    widths = col_widths(pad=5.5, ctx_in=True)
    x = x0
    pos, ctxpos = {}, {}
    ybot = ytop
    cols = {}
    for k in range(1, 6):
        w = widths[k]
        g0 = GROUPS[k][0]
        if header_ctx:
            txt = ctx_text(g0, maxw=w - 4)
            n = 0 if txt == "∅" else txt.count("\n") + 1
            th = 11 + max(n, 1) * LINE + 2
        else:
            th = 11
        box(ax, x, ytop - th, w, th, ec="none", fc=LEVEL_FILL[k], r=2.5, z=2)
        T(ax, x + w / 2, ytop - 5.6, f"Level {k}", size=F8, weight="bold", color=LEVEL_TEXT[k], zorder=3)
        y = ytop - th - 1.5
        for gi, g in enumerate(GROUPS[k]):
            txt = ctx_text(g, maxw=w - 4)
            if header_ctx and gi == 0:
                cy = ytop - 11 - (max(txt.count("\n") + 1, 1) * LINE) / 2 - 1
                if txt == "∅":
                    empty_set(ax, x + w / 2, cy, color=LEVEL_TEXT[k])
                else:
                    T(ax, x + 3, cy, txt, size=F8, color=LEVEL_TEXT[k], ha="left", linespacing=1.0, zorder=3)
                ctxpos[(k, gi)] = (x, cy)
            else:
                n = txt.count("\n") + 1
                hgt = n * LINE + 3
                if header_ctx:   # second group of level 3: plain text, no box
                    T(ax, x + 3, y - hgt / 2, txt, size=F8, color=SOFT, ha="left", linespacing=1.0, zorder=3)
                else:
                    box(ax, x, y - hgt, w, hgt, ec=ATTR_EDGE, fc=CTX_FILL, lw=0.5, r=2.5, z=2)
                    if txt == "∅":
                        empty_set(ax, x + w / 2, y - hgt / 2)
                    else:
                        T(ax, x + 3, y - hgt / 2, txt, size=F8, color=INK, ha="left", linespacing=1.0, zorder=3)
                ctxpos[(k, gi)] = (x, y - hgt / 2)
                y -= hgt + 1.5
            for a in g:
                n = SHORT[a].count("\n") + 1
                hgt = n * LINE + 2.5
                hl = a in HIGHLIGHTED
                box(ax, x, y - hgt, w, hgt, ec=ATTR_EDGE, fc=HL if hl else ATTR, lw=0.7, r=2.5, z=2)
                T(ax, x + w / 2, y - hgt / 2, SHORT[a], size=F8, color=INK, linespacing=1.0, zorder=3,
                  weight="bold" if bold else "normal")
                pos[a] = (x, x + w, y - hgt / 2)
                y -= hgt + 1.5
            y -= 1.5
        cols[k] = (x, w, ytop - th, y)
        ybot = min(ybot, y)
        x += w + gap
    if bands:  # the current figure's level-coloured bands behind each column
        for k, (xx, w, yt, yb) in cols.items():
            ax.add_patch(Rectangle((xx + 3, yb + 1.5), w - 6, yt - yb - 1.5, fc=LEVEL_FILL[k], ec="none", zorder=1))
    feed_arrows(ax, pos, ctxpos, gap)
    return x - gap, ybot


# ================================================================== P26 text columns
def text_columns_a(ax, x0, ytop, gap=6):
    widths = col_widths(pad=4)
    x = x0
    pos, ctxpos = {}, {}
    ybot = ytop
    for k in range(1, 6):
        w = widths[k]
        ax.add_patch(Rectangle((x, ytop - 3), w, 3, fc=LEVEL_FILL[k], ec=ATTR_EDGE, lw=0.4, zorder=2))
        T(ax, x, ytop - 9, f"Level {k}", size=F8, weight="bold", ha="left", color=INK)
        y = ytop - 17
        for gi, g in enumerate(GROUPS[k]):
            txt = ctx_text(g, maxw=w - 2)
            n = txt.count("\n") + 1
            if txt == "∅":
                empty_set(ax, x + 5, y - 4)
            else:
                T(ax, x, y - n * LINE / 2 + 0.5, txt, size=F8, color=SOFT, ha="left", linespacing=1.0, style="italic")
            ctxpos[(k, gi)] = (x - 1, y - n * LINE / 2 + 0.5)
            y -= n * LINE + 3
            for a in g:
                n = SHORT[a].count("\n") + 1
                hgt = n * LINE + 1.5
                if a in HIGHLIGHTED:
                    box(ax, x - 1.5, y - hgt, w + 1, hgt, ec="none", fc=HL, r=2, z=1)
                T(ax, x, y - hgt / 2, SHORT[a], size=F8, color=INK, ha="left", linespacing=1.0, zorder=3)
                pos[a] = (x, x + max(text_width(p, F8) for p in SHORT[a].split("\n")) + 1, y - hgt / 2)
                y -= hgt + 1.5
            y -= 2
        ybot = min(ybot, y)
        x += w + gap
    feed_arrows(ax, pos, ctxpos, gap, color=SOFT)
    return x - gap, ybot


# ================================================================== P27 horizontal rows
def incremental(g, prev):
    anc = ancestors(g[0])
    new = [CTX_WORD[a] for a in ORDER_IN_LIST if a in anc and a not in prev]
    return anc, ("+ " if prev else "| ") + ", ".join(new) if anc else "∅"


def rows_a(ax, x0, ytop):
    lab_w, ctx_w = 34, 66
    cx0 = x0 + lab_w + ctx_w + 6
    y = ytop
    prev = set()
    rows = []
    for k in range(1, 6):
        for gi, g in enumerate(GROUPS[k]):
            base = prev if not (k == 3 and gi == 1) else ancestors(GROUPS[2][0][0]) | set()
            if k == 3 and gi == 1:
                base = set(ancestors("civil_status")) | set()
                base = ancestors(GROUPS[2][0][0])
            anc, txt = incremental(g, base if k > 1 else set())
            rows.append((k, gi, g, txt))
            if not (k == 3 and gi == 1):
                prev = anc
    row_h = 2 * LINE + 3.5
    for i, (k, gi, g, txt) in enumerate(rows):
        yc = y - row_h / 2
        ax.add_patch(Rectangle((x0, y - row_h), 259, row_h - 1.2, fc=LEVEL_FILL[k], ec="none", zorder=1))
        if gi == 0:
            T(ax, x0 + 3, yc, f"Level {k}", size=F8, weight="bold", ha="left", color=LEVEL_TEXT[k], zorder=3)
        if txt == "∅":
            empty_set(ax, x0 + lab_w + 8, yc, color=LEVEL_TEXT[k])
        else:
            T(ax, x0 + lab_w + 2, yc, txt, size=F8, ha="left", color=LEVEL_TEXT[k], zorder=3)
        xx = cx0
        names = [SHORT[a] for a in g]
        ws = [max(text_width(p, F8) for p in n_.split("\n")) + 4.5 for n_ in names]
        for a, n_, w in zip(g, names, ws):
            box(ax, xx, yc - (row_h - 4) / 2, w, row_h - 4, ec=ATTR_EDGE, fc=HL if a in HIGHLIGHTED else ATTR, lw=0.7,
                r=2.5, z=3)
            T(ax, xx + w / 2, yc, n_, size=F8, linespacing=1.0, zorder=4)
            xx += w + 2
        assert xx <= x0 + 262, (k, xx)
        y -= row_h
    # growing bracket: the context accumulates downwards
    bx = x0 - 6
    pts = np.array([[bx + 4, ytop - 16], [bx, ytop - 16], [bx, y + 1]])
    line(ax, pts[:, 0], pts[:, 1], color=INK, lw=0.8)
    arrow(ax, bx, y + 8, bx, y + 1, color=INK, lw=0.8, head=3.5)
    return x0 + 259, y


# ================================================================== P28 staircase
def staircase_a(ax, x0, ytop):
    order = [a for k in range(1, 6) for g in GROUPS[k] for a in g]
    n = len(order)
    rh = 8.3
    name_w = max(text_width(SHORT[a].replace("\n", " "), F8) for a in order) + 6
    band_w = 9
    cell = 8.3
    gx0 = x0 + band_w + name_w + 2
    y = ytop - 2
    idx = {a: i for i, a in enumerate(order)}
    for i, a in enumerate(order):
        k = c.LEVEL[a]
        yy = y - (i + 1) * rh
        ax.add_patch(Rectangle((x0, yy), band_w, rh, fc=LEVEL_FILL[k], ec="none", zorder=1))
        box(ax, x0 + band_w + 1, yy + 0.6, name_w, rh - 1.2, ec=ATTR_EDGE, fc=HL if a in HIGHLIGHTED else ATTR, lw=0.5,
            r=1.8, z=2)
        T(ax, x0 + band_w + 4, yy + rh / 2, SHORT[a].replace("\n", " "), size=F8, ha="left", zorder=3)
        anc = ancestors(a)
        for j, d in enumerate(order[:i]):
            xx = gx0 + j * cell
            if d in anc:
                ax.add_patch(Rectangle((xx + 0.5, yy + 0.5), cell - 1, rh - 1, fc=CTX_FILL, ec="none", zorder=2))
            if d in c.DEPS[a]:
                ax.add_patch(Circle((xx + cell / 2, yy + rh / 2), cell * 0.26, fc=ATTR_EDGE, ec="none", zorder=3))
    for k in range(1, 6):
        ii = [idx[a] for a in order if c.LEVEL[a] == k]
        T(ax, x0 + band_w / 2, y - (min(ii) + max(ii) + 1) / 2 * rh, str(k), size=F8, weight="bold",
          color=LEVEL_TEXT[k], zorder=3)
    right = gx0 + (n - 1) * cell
    # column heads: same order, as the level band colours (one small square each)
    for j, d in enumerate(order[:-1]):
        ax.add_patch(Rectangle((gx0 + j * cell + 1.5, y + 0.8), cell - 3, 3, fc=LEVEL_FILL[c.LEVEL[d]], ec=ATTR_EDGE,
                               lw=0.3, zorder=2))
    yb = y - n * rh
    lx, ly = gx0 + 5 * cell, y - 3 * rh
    ax.add_patch(Rectangle((lx, ly - 3.5), 8, 7, fc=CTX_FILL, ec="none"))
    T(ax, lx + 11, ly, "context (all dependencies)", size=F8, ha="left")
    ax.add_patch(Circle((lx + 4, ly - 10), 2.3, fc=ATTR_EDGE, ec="none"))
    T(ax, lx + 11, ly - 10, "direct dependency", size=F8, ha="left")
    return max(right, lx + 11 + text_width("context (all dependencies)", F8)), yb


# ================================================================== P29 node-link
def nodelink_a(ax, x0, ytop, gap=5):
    widths = {}
    for k, gs in GROUPS.items():
        texts = [SHORT[a] for g in gs for a in g]
        widths[k] = max(max(text_width(p, F8) for t_ in texts for p in t_.split("\n")) + 4,
                        max(text_width(p, F8) for g in gs for p in ctx_text(g, maxw=0).split("\n")) + 4)
    x = x0
    pos = {}
    ybot = ytop
    for k in range(1, 6):
        w = widths[k]
        txt = ctx_text(GROUPS[k][0], maxw=w - 4)
        nl = 1 if txt == "∅" else txt.count("\n") + 1
        th = 11 + nl * LINE + 2
        box(ax, x, ytop - th, w, th, ec="none", fc=LEVEL_FILL[k], r=2.5, z=2)
        T(ax, x + w / 2, ytop - 5.6, f"Level {k}", size=F8, weight="bold", color=LEVEL_TEXT[k], zorder=3)
        cy = ytop - 11 - nl * LINE / 2 - 1
        if txt == "∅":
            empty_set(ax, x + w / 2, cy, color=LEVEL_TEXT[k])
        else:
            T(ax, x + 3, cy, txt, size=F8, color=LEVEL_TEXT[k], ha="left", linespacing=1.0, zorder=3)
        ax.add_patch(Rectangle((x, 0), 0, 0))
        y = ytop - th - 3
        for gi, g in enumerate(GROUPS[k]):
            if gi == 1:
                t2 = ctx_text(g, maxw=w - 4)
                T(ax, x + 3, y - 4, t2, size=F8, color=SOFT, ha="left", va="top", linespacing=1.0, style="italic")
                y -= (t2.count("\n") + 1) * LINE + 3
            for a in g:
                nlines = SHORT[a].count("\n") + 1
                yc = y - 3.8
                ax.add_patch(Circle((x + w / 2, yc), 3.6, fc=HL if a in HIGHLIGHTED else ATTR, ec=ATTR_EDGE, lw=0.8,
                                    zorder=5))
                T(ax, x + w / 2, yc - 4.4, SHORT[a], size=F8, va="top", linespacing=0.95, zorder=5,
                  bbox=dict(boxstyle="square,pad=0.02", fc="white", ec="none"))
                pos[a] = (x + w / 2, yc)
                y -= 7.6 + nlines * LINE * 0.95 + 1.5
        line(ax, [x, x], [ytop - th, y + 2], color=LEVEL_FILL[k], lw=2.4, z=1)
        ybot = min(ybot, y)
        x += w + gap
    for a in c.ORDER:   # every depends_on edge, thin
        for d in c.DEPS[a]:
            (xa, ya), (xb, yb) = pos[d], pos[a]
            dx = (xb - xa) * 0.5
            path = MPath([(xa + 3.8, ya), (xa + dx, ya), (xb - dx, yb), (xb - 3.8, yb)],
                         [MPath.MOVETO, MPath.CURVE4, MPath.CURVE4, MPath.CURVE4])
            ax.add_patch(PathPatch(path, fc="none", ec=SOFT, lw=0.5, zorder=4))
    return x - gap, ybot


# ================================================================== composite
@house_style
def compose(name, draw_a, **kw):
    H = 205.0
    for _ in range(3):
        fig, ax = c.canvas(H)
        top = H - 2
        panel_letter(ax, 2, top, "A")
        ar, ab = draw_a(ax, X0, top - 2, **kw)
        assert ar <= MAX_RIGHT + 0.5, (name, ar)
        bx0 = max(ar, 258) + GUTTER
        panel_letter(ax, bx0, top, "B")
        bb = grid(ax, bx0 + 2, c.W - 2, top)
        yb = example_strip(ax, 3, c.W - 3, min(ab, bb) - 4)
        if abs(yb - 2.5) < 0.3:
            break
        plt.close(fig)
        H = round(H - (yb - 2.5), 1)
    assert H < 214, (name, H)
    out = c.save(fig, name)
    print(name, "H =", H, "A right =", round(ar, 1), "A bottom =", round(ab, 1))
    return out


ALL = {
    "P23b": lambda: compose("P23b_fig2a_colour_code", boxes_a),
    "P24": lambda: compose("P24_near_current_bands_bold", boxes_a, bands=True, bold=True),
    "P25": lambda: compose("P25_context_in_level_header", boxes_a, header_ctx=True),
    "P26": lambda: compose("P26_text_columns", text_columns_a),
    "P27": lambda: compose("P27_level_rows_growing_context", rows_a),
    "P28": lambda: compose("P28_staircase", staircase_a),
    "P29": lambda: compose("P29_node_link", nodelink_a),
}

if __name__ == "__main__":
    for k in (sys.argv[1:] or ALL):
        try:
            ALL[k]()
        except Exception as ex:
            print(k, "FAILED", repr(ex)[:300])
