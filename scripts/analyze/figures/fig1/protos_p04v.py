"""Figure 1, P04 variants after the author's feedback (2026-10-20). Run: python protos_p04v.py [P11 P12 P13]."""
from __future__ import annotations

import sys

import numpy as np
from matplotlib.patches import Rectangle, Circle

import common as c
from common import (T, box, arrow, line, table_icon, table_stack, person, llm_chip, die, schema_slots, bubble,
                    badge, cross, fmt, SC, REF, REF_FILL, INK, SOFT, SCHEMA, SCHEMA_FILL, F8, F9, F10)
from protos import analysis_icon, LVL
from population_synthetic.analysis.utils.labels import method_key_lines, figure_term
from population_synthetic.analysis.utils.style import house_style, text_width_inches, POINTS_PER_INCH

WIDTHS = [117, 121, 92, 100]
GAP = 8
SECS = ["4.1", "4.2", "4.3", "4.4"]
TITLES = ["Reference", "Synthetic", "Mapping", "Comparison"]
N_ATT = c.N_ATTRIBUTES


def tw(s, size=F8, weight=None):
    return text_width_inches(s, fontsize=size, weight=weight) * POINTS_PER_INCH


def panels(ax, H, y0=2, top=None):
    """Draw the four section panels; return their x0 list and the header baseline."""
    top = top or H - 2
    xs = []
    x = 1
    for k, w in enumerate(WIDTHS):
        box(ax, x, y0, w, top - y0, ec=c.GRID_RULE, fc="white", lw=0.8, r=5, z=1)
        badge(ax, x + 12, top - 12, SECS[k], r=9)
        T(ax, x + 25, top - 12, TITLES[k], size=F10, weight="bold", ha="left")
        xs.append(x)
        if k < 3:
            ym = (y0 + top) / 2
            arrow(ax, x + w + 0.5, ym, x + w + GAP - 0.5, ym, color=INK, lw=1.2, head=5)
        x += w + GAP
    return xs


def card14(ax, x, y, w, h, kind="ref", color=None, z=5, stack=0):
    """An individual: one card, 14 attribute rows. kind: 'ref' (table values, solid bars),
    'llm' (free text, wavy), 'slots' (canonical categories)."""
    color = color or (REF if kind == "ref" else INK)
    for k in range(stack, 0, -1):
        box(ax, x + 2.2 * k, y + 2.2 * k, w, h, ec=color, fc="white", lw=0.6, r=1.5, z=z - k * 0.01)
    box(ax, x, y, w, h, ec=color, fc="white", lw=0.8, r=1.5, z=z)
    head = h * 0.16
    person(ax, x + w * 0.2, y + h - head - 0.6, head * 0.95, color=color, z=z + 0.1)
    y1, y0 = y + h - head - 2.2, y + 1.6
    pitch = (y1 - y0) / N_ATT
    rng = np.random.default_rng(7)
    for i in range(N_ATT):
        yy = y1 - (i + 0.5) * pitch
        L = 0.4 + 0.45 * rng.random()
        if kind == "ref":
            line(ax, [x + w * 0.12, x + w * (0.12 + 0.76 * L)], [yy] * 2, color=color, lw=pitch * 0.5, z=z + 0.1, cap="butt")
        elif kind == "llm":
            xs_ = np.linspace(x + w * 0.12, x + w * (0.12 + 0.76 * L), 14)
            line(ax, xs_, yy + pitch * 0.18 * np.sin((xs_ - x) / w * 5 * np.pi), color=color, lw=0.5, z=z + 0.1)
        else:
            ax.add_patch(Rectangle((x + w * 0.1, yy - pitch * 0.35), w * 0.8, pitch * 0.7, fc=SCHEMA_FILL, ec=SCHEMA,
                                   lw=0.35, zorder=z + 0.1))
    return y0, y1, pitch


def brace_label(ax, x, y0, y1, text, color=INK, size=F8):
    line(ax, [x, x + 2.5, x + 2.5, x], [y1, y1, y0, y0], color=color, lw=0.6)
    T(ax, x + 5, (y0 + y1) / 2, text, size=size, color=color, ha="left")


def mechanism_key(ax, x, ytop, pitch_r=8.6, col_x=None):
    """Visual A-E key: which steps each strategy runs (context, list, weigh, choose; E draws at random)."""
    cols = ["context", "list", "weigh", "choose"]
    col_x = col_x or [x + 26, x + 50, x + 72, x + 95]
    for cx, h in zip(col_x, cols):
        T(ax, cx, ytop, h, size=F8, color=SOFT)
    steps = {0: [3], 1: [0, 3], 2: [0, 1, 3], 3: [0, 1, 2, 3], 4: [0, 1, 2, 3]}
    for i, s in enumerate(c.STRATEGIES):
        yy = ytop - 9 - i * pitch_r
        T(ax, x + 6, yy, c.LETTERS[s], size=F8, color=c.STRAT_COLOR[s], weight="bold")
        line(ax, [col_x[0] - 8, col_x[-1] + 6], [yy, yy], color=c.GRID_RULE, lw=0.5, z=2)
        on = steps[i]
        line(ax, [col_x[on[0]], col_x[on[-1]]], [yy, yy], color=c.STRAT_COLOR[s], lw=1.2, z=3)
        for j in on:
            if i == 4 and j == 3:
                die(ax, col_x[j], yy, 7.2, color=c.STRAT_COLOR[s], z=6)
            else:
                ax.add_patch(Circle((col_x[j], yy), 2.3, fc=c.STRAT_COLOR[s], ec="none", zorder=5))
    return ytop - 9 - 4 * pitch_r


def family_key(ax, x, y, width, size=F8):
    """In-figure key from labels.method_key_lines (the convention's own key), wrapped into rows."""
    title = figure_term("strategy_key_title") + ":"
    T(ax, x, y, title, size=size, weight="bold", ha="left")
    cx, cy = x + tw(title, size, "bold") + 6, y
    for s, ln in zip(c.STRATEGIES, method_key_lines(c.STRATEGIES)):
        letter, rest = ln[0], ln[1:]
        wl = tw(letter, size, "bold") + tw(rest, size) + 10
        if cx + wl > x + width:
            cx, cy = x + tw(title, size, "bold") + 6, cy - 11
        T(ax, cx, cy, letter, size=size, color=c.STRAT_COLOR[s], weight="bold", ha="left")
        T(ax, cx + tw(letter, size, "bold"), cy, rest, size=size, ha="left")
        cx += wl
    return cy


def comparison_panel(ax, x0, ys, r=13):
    for k, yy in enumerate(ys):
        ax.add_patch(Circle((x0 + 17, yy), r, fc="white", ec=INK, lw=1.0, zorder=6))
        analysis_icon(ax, k, x0 + 17, yy, r * 1.25)
        T(ax, x0 + 17 + r + 4, yy, LVL[k], size=F8, ha="left")


def mapping_panel(ax, x0, w, ylo, yhi):
    """Both individual cards, aligned onto the same 14 slots."""
    ch = (yhi - ylo) * 0.33
    cw = 24
    yr = yhi - ch - 8
    yl = ylo + 8
    T(ax, x0 + 4, yr + ch + 5, "table label", size=F8, color=REF, va="bottom", ha="left")
    card14(ax, x0 + 6, yr, cw, ch, "ref")
    T(ax, x0 + 4, yl + ch + 5, "free text", size=F8, va="bottom", ha="left")
    card14(ax, x0 + 6, yl, cw, ch, "llm")
    sx, sw = x0 + w - 32, 24
    sy0, sy1 = ylo + 6, yhi - 4
    box(ax, sx - 3, sy0 - 3, sw + 6, sy1 - sy0 + 6, ec=SCHEMA, fc=SCHEMA_FILL, lw=0.9, r=3)
    schema_slots(ax, sx, sy0, sw, sy1 - sy0, n=N_ATT, fc="white")
    arrow(ax, x0 + 6 + cw + 3, yr + ch / 2, sx - 6, (sy0 + sy1) / 2 + 10, color=REF, lw=1.2)
    arrow(ax, x0 + 6 + cw + 3, yl + ch / 2, sx - 6, (sy0 + sy1) / 2 - 10, color=INK, lw=1.2)
    return sx, sw, sy0


# ------------------------------------------------------------------ P11 glyph-led
@house_style
def p11():
    H = 214
    cv, ax = c.canvas(H)
    xs = panels(ax, H)
    top = H - 30
    # 4.1 reference ------------------------------------------------------------
    x0 = xs[0]
    table_stack(ax, x0 + 7, top - 22, 22, 17, n=3)
    T(ax, x0 + 38, top - 6, "Statistics Sweden", size=F8, color=REF, ha="left", weight="bold")
    T(ax, x0 + 38, top - 16, "official statistics", size=F8, color=REF, ha="left")
    T(ax, x0 + 38, top - 26, "(SCB), 13 tables", size=F8, color=REF, ha="left")
    die(ax, x0 + 20, top - 50, 13)
    T(ax, x0 + 32, top - 50, "conditional sampling", size=F8, color=REF, ha="left")
    arrow(ax, x0 + 20, top - 27, x0 + 20, top - 42, color=REF, head=4)
    arrow(ax, x0 + 20, top - 58, x0 + 20, top - 68, color=REF, head=4)
    cy0, ch = 48, 52
    y0_, y1_, _ = card14(ax, x0 + 8, cy0, 26, ch, "ref", stack=2)
    brace_label(ax, x0 + 41, y0_, y1_, f"{N_ATT} attributes", color=REF)
    T(ax, x0 + 41, cy0 + ch - 3, "1 individual", size=F8, color=REF, ha="left", va="top")
    T(ax, x0 + 58, 33, f"{fmt(c.N_REFERENCE)} individuals", size=F9, color=REF, weight="bold")
    T(ax, x0 + 58, 22, "= 1 reference population", size=F8, color=REF)
    # 4.2 synthetic --------------------------------------------------------------
    x0 = xs[1]
    llm_chip(ax, x0 + 15, top - 8, 25)
    T(ax, x0 + 30, top - 3, "13 LLMs", size=F8, ha="left", weight="bold")
    T(ax, x0 + 30, top - 13, f"× {len(c.STRATEGIES)} strategies", size=F8, ha="left", weight="bold")
    kbot = mechanism_key(ax, x0 + 2, top - 28, pitch_r=7.4, col_x=[x0 + 30, x0 + 54, x0 + 76, x0 + 104])
    y0_, y1_, _ = card14(ax, x0 + 8, cy0, 26, ch, "llm", stack=2)
    brace_label(ax, x0 + 41, y0_, y1_, f"{N_ATT} attributes")
    T(ax, x0 + 41, cy0 + ch - 3, "1 individual", size=F8, ha="left", va="top")
    T(ax, x0 + 60, 33, f"{c.N_PER_COMBO[0]} individuals = 1 population", size=F8)
    T(ax, x0 + 60, 22, f"× {c.N_KEPT} populations", size=F9, weight="bold")
    T(ax, x0 + 60, 11, f"(13 × 5 = {c.N_COMBOS}, {c.N_COMBOS - c.N_KEPT} withdrawn)", size=F8, color=SOFT)
    # 4.3 mapping -----------------------------------------------------------------
    x0 = xs[2]
    sx, sw, sy0 = mapping_panel(ax, x0, WIDTHS[2], 22, top - 6)
    T(ax, x0 + WIDTHS[2] / 2, 11, f"same {N_ATT} attributes", size=F8, color=SCHEMA, weight="bold")
    # 4.4 comparison --------------------------------------------------------------
    comparison_panel(ax, xs[3], [top - 22, (top + 14) / 2 - 6, 30])
    return c.save(cv.figure, "P11_p04_glyph_cards")


# ------------------------------------------------------------------ P12 text-line led, convention key strip
@house_style
def p12():
    H = 200
    KEY = 26
    cv, ax = c.canvas(H)
    xs = panels(ax, H, y0=KEY + 2)
    top = H - 30
    # 4.1
    x0, w = xs[0], WIDTHS[0]
    T(ax, x0 + 6, top - 2, "Official statistics", size=F8, color=REF, ha="left", weight="bold")
    T(ax, x0 + 6, top - 12, "Statistics Sweden (SCB)", size=F8, color=REF, ha="left")
    table_stack(ax, x0 + 8, top - 48, 24, 19, n=3)
    T(ax, x0 + 22, top - 54, "13 tables", size=F8, color=REF, va="top")
    arrow(ax, x0 + 40, top - 38, x0 + 56, top - 38, color=REF)
    die(ax, x0 + 67, top - 38, 15)
    T(ax, x0 + 67, top - 50, "conditional\nsampling", size=F8, color=REF, va="top")
    y0_, y1_, _ = card14(ax, x0 + 10, 58, 22, 40, "ref", stack=2)
    brace_label(ax, x0 + 37, y0_, y1_, "", color=REF)
    T(ax, x0 + 43, 86, "1 individual =", size=F8, color=REF, ha="left")
    T(ax, x0 + 43, 76, f"{N_ATT} attributes", size=F8, color=REF, ha="left")
    T(ax, x0 + w / 2, 45, f"{fmt(c.N_REFERENCE)} individuals", size=F9, color=REF, weight="bold")
    T(ax, x0 + w / 2, 35, "= 1 reference population", size=F8, color=REF)
    # 4.2
    x0, w = xs[1], WIDTHS[1]
    T(ax, x0 + 6, top - 2, f"13 LLMs × {len(c.STRATEGIES)} strategies", size=F8, ha="left", weight="bold")
    T(ax, x0 + 6, top - 12, "one attribute at a time", size=F8, ha="left")
    llm_chip(ax, x0 + 20, top - 38, 24)
    for i, s_ in enumerate(c.STRATEGIES):
        xx = x0 + 50 + i * 13
        T(ax, xx, top - 28, c.LETTERS[s_], size=F9, color=c.STRAT_COLOR[s_], weight="bold")
        line(ax, [xx, xx], [top - 35, top - 50], color=c.STRAT_COLOR[s_], lw=1.6)
    y0_, y1_, _ = card14(ax, x0 + 10, 58, 22, 40, "llm", stack=2)
    brace_label(ax, x0 + 37, y0_, y1_, "")
    T(ax, x0 + 43, 86, "1 individual =", size=F8, ha="left")
    T(ax, x0 + 43, 76, f"{N_ATT} attributes", size=F8, ha="left")
    T(ax, x0 + w / 2, 45, f"{c.N_KEPT} populations", size=F9, weight="bold")
    T(ax, x0 + w / 2, 35, f"of {c.N_PER_COMBO[0]} individuals each", size=F8)
    # 4.3
    x0, w = xs[2], WIDTHS[2]
    T(ax, x0 + 6, top - 2, "Both onto the same", size=F8, ha="left", color=SCHEMA, weight="bold")
    T(ax, x0 + 6, top - 12, f"{N_ATT} attributes", size=F8, ha="left", color=SCHEMA, weight="bold")
    mapping_panel(ax, x0, w, KEY + 10, top - 26)
    # 4.4
    comparison_panel(ax, xs[3], [top - 22, (top + KEY) / 2 - 4, KEY + 22])
    family_key(ax, 4, KEY - 8, 448)
    return c.save(cv.figure, "P12_p04_text_lines")


# ------------------------------------------------------------------ P13 zoom: grid -> population -> individual
@house_style
def p13():
    H = 214
    KEY = 26
    cv, ax = c.canvas(H)
    xs = panels(ax, H, y0=KEY + 2)
    top = H - 30
    # 4.1: block of 10,000 -> one individual
    x0, w = xs[0], WIDTHS[0]
    table_stack(ax, x0 + 7, top - 22, 22, 17, n=3)
    T(ax, x0 + 38, top - 6, "Statistics Sweden", size=F8, color=REF, ha="left", weight="bold")
    T(ax, x0 + 38, top - 16, "official statistics", size=F8, color=REF, ha="left")
    T(ax, x0 + 38, top - 26, "(SCB), 13 tables", size=F8, color=REF, ha="left")
    bx, by, bs = x0 + 8, top - 92, 50
    pitch = bs / 100
    ax.add_patch(Rectangle((bx - 0.5, by - 0.5), bs, bs, fc=REF_FILL, ec=REF, lw=0.6, zorder=3))
    gx, gy = np.meshgrid(np.arange(0, 100, 2), np.arange(0, 100, 2))
    ax.scatter(bx + gx.ravel() * pitch, by + gy.ravel() * pitch, s=0.25, marker="s", c=c.MUTED_GREY, linewidths=0, zorder=4)
    T(ax, x0 + 6, by - 9, f"{fmt(c.N_REFERENCE)} individuals", size=F8, color=REF, weight="bold", va="top", ha="left")
    hx, hy = bx + bs - 5, by + bs - 8
    ax.add_patch(Rectangle((hx - 1.4, hy - 1.4), 2.8, 2.8, fc=REF, ec="none", zorder=6))
    kx, ky, kw, kh = x0 + 84, by + 8, 24, 38
    line(ax, [hx, kx], [hy, ky + kh], color=SOFT, lw=0.5, z=3)
    line(ax, [hx, kx], [hy, ky], color=SOFT, lw=0.5, z=3)
    card14(ax, kx, ky, kw, kh, "ref")
    T(ax, kx + kw / 2, ky + kh + 3, "1 individual", size=F8, color=REF, va="bottom")
    T(ax, x0 + WIDTHS[0] - 3, ky - 3, f"= {N_ATT} attributes", size=F8, color=REF, va="top", ha="right")
    T(ax, x0 + 6, by - 24, "= 1 reference population", size=F8, color=REF, ha="left", va="top")
    # 4.2: 13 x 5 grid -> one population of 100 -> one card
    x0, w = xs[1], WIDTHS[1]
    llm_chip(ax, x0 + 13, top - 6, 18, label=None)
    T(ax, x0 + 26, top - 1, "13 LLMs", size=F8, ha="left", weight="bold")
    T(ax, x0 + 26, top - 11, f"× {len(c.STRATEGIES)} strategies", size=F8, ha="left", weight="bold")
    cell, g = 6.2, 1.2
    gx0, gy0 = x0 + 16, top - 72
    xg1, yg1 = c.combo_grid(ax, gx0, gy0, cell, g, show_host=False)
    c.strategy_letters(ax, gx0 - 3, gy0, cell, g)
    T(ax, (gx0 + xg1) / 2 - 4, top - 26, f"{c.N_KEPT} populations ({c.N_COMBOS - c.N_KEPT} withdrawn)", size=F8, weight="bold")
    # zoom from one square (Kimi column, strategy E) to a 10 x 10 population
    sq_x, sq_y = gx0 + 1 * (cell + g), gy0
    ax.add_patch(Rectangle((sq_x - 0.6, sq_y - 0.6), cell + 1.2, cell + 1.2, fc="none", ec=INK, lw=0.9, zorder=7))
    px, py, ps = x0 + 10, KEY + 18, 40
    pp = ps / 10
    for i in range(10):
        for j in range(10):
            person(ax, px + i * pp + pp / 2, py + j * pp + 0.3, pp * 0.85, color=c.STRAT_COLOR[c.STRATEGIES[4]], z=5)
    ax.add_patch(Rectangle((px - 0.5, py - 0.5), ps + 1, ps + 1, fc="none", ec=INK, lw=0.6, zorder=6))
    line(ax, [sq_x, px], [sq_y, py + ps], color=SOFT, lw=0.5, z=3)
    line(ax, [sq_x + cell, px + ps], [sq_y, py + ps], color=SOFT, lw=0.5, z=3)
    T(ax, px + ps / 2, py - 3, f"1 population = {c.N_PER_COMBO[0]} individuals", size=F8, va="top", ha="left") if False else None
    T(ax, px - 2, py - 4, f"1 population = {c.N_PER_COMBO[0]} individuals", size=F8, va="top", ha="left")
    # zoom from one person to a card
    kx, ky = x0 + w - 30, py + 2
    hx, hy = px + 9.5 * pp, py + 9.5 * pp
    line(ax, [hx, kx], [hy, ky + 40], color=SOFT, lw=0.5, z=3)
    line(ax, [hx, kx], [hy - pp / 2, ky], color=SOFT, lw=0.5, z=3)
    card14(ax, kx, ky, 24, 40, "llm")
    T(ax, kx + 12, ky + 46, "1 individual", size=F8, va="bottom")
    T(ax, kx + 12, ky + 56, f"{N_ATT} attributes", size=F8, va="bottom") if False else None
    # 4.3
    x0, w = xs[2], WIDTHS[2]
    mapping_panel(ax, x0, w, KEY + 18, top - 4)
    T(ax, x0 + w / 2, KEY + 10, f"same {N_ATT} attributes", size=F8, color=SCHEMA, weight="bold")
    # 4.4
    comparison_panel(ax, xs[3], [top - 22, (top + KEY) / 2 - 4, KEY + 22])
    family_key(ax, 4, KEY - 8, 448)
    return c.save(cv.figure, "P13_p04_zoom_grid")


ALL = {"P11": p11, "P12": p12, "P13": p13}


if __name__ == "__main__":
    for k in (sys.argv[1:] or ALL):
        print(k, ALL[k]())
