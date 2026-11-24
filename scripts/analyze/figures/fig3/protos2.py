"""Figure 3 round 2: current panel A + P03's strategy grid as panel B, with the worked example.

Run: python protos2.py [P09 P10 P11]. Panel A is the current figure's own panel A, cropped from the
embedded image (F3_P00_current.png, 600 dpi) and placed at its published size; nothing in it is redrawn.
"""
from __future__ import annotations

import sys

import numpy as np
from PIL import Image
from matplotlib.patches import Circle, Rectangle

import common as c
from common import (F8, F9, F10, INK, SOFT, FAINT, RULE, PANEL, T, box, line, arrow, chip, die, list_glyph,
                    bars_glyph, context_glyph, letter, step_glyph, panel_letter, text_width)
from example import EX, N_SHOWN
from protos import GLYPH_KEY, glyph_key
from population_synthetic.analysis.utils.style import house_style

S = c.STRATEGIES
SC = c.STRAT_COLOR
CUR = c.GALLERY / "F3_P00_current.png"
PX_PER_PT = 3800 / 456
A_BOX = (0, 0, 2340, 1012)  # x0, y0, x1, y1 in px: panel A only (gap to B measured at x 2329-2430)
A_W, A_H = (A_BOX[2] - A_BOX[0]) / PX_PER_PT, (A_BOX[3] - A_BOX[1]) / PX_PER_PT
LH = 9.2  # example line height, pt
BAR = SOFT


def place_a(ax, x, ytop):
    """Current panel A at its published size, top-left at (x, ytop)."""
    img = np.asarray(Image.open(CUR).convert("RGB").crop(A_BOX))
    ax.imshow(img, extent=(x, x + A_W, ytop - A_H, ytop), interpolation="lanczos", zorder=1)
    ax.set_xlim(0, c.W)
    ax.set_ylim(0, ax.figure.get_size_inches()[1] * 72)
    return ytop - A_H


def calls_label(ax, x, y):
    T(ax, x, y, "LLM calls per\nindividual", size=F8, color=SOFT, linespacing=0.95)


def value_list(ax, s, x, ytop, highlight, weights=False, wx=None, barw=26, bold_pick=True):
    """First N_SHOWN candidates of strategy s, one per line, the picked one bold; weights as bar + number."""
    e = EX[s]
    for i, v in enumerate(e["candidates"][:N_SHOWN]):
        y = ytop - i * LH
        hit = v == highlight
        T(ax, x, y, v, size=F8, ha="left", weight="bold" if (hit and bold_pick) else "normal",
          color=INK if hit else SOFT, zorder=4, bbox=dict(boxstyle="square,pad=0.08", fc="white", ec="none"))
        if weights:
            w = e["weights"][i]
            ax.add_patch(Rectangle((wx, y - 2.6), barw * w / 0.7, 5.2, fc=INK if hit else BAR, ec="white", lw=0.8, zorder=4))
            T(ax, wx + barw + 3, y, f"{w:.2f}", size=F8, ha="left", color=INK if hit else SOFT,
              weight="bold" if hit else "normal", zorder=4, bbox=dict(boxstyle="square,pad=0.08", fc="white", ec="none"))
    more = len(e["candidates"]) - N_SHOWN
    T(ax, x, ytop - N_SHOWN * LH, f"+ {more} more", size=F8, ha="left", color=SOFT, style="italic")


# ================================================================== P09 horizontal
@house_style
def p09():
    heights = {s: (N_SHOWN + 1) * LH + 4 if "list" in c.STEPS[s] else 16 for s in S}
    H = round(A_H + 2 + 30 + sum(heights.values()) + 3 * len(S) + 16)
    fig, ax = c.canvas(H)
    yb = place_a(ax, 2, H - 2)
    # key in the free space beside panel A
    kx = A_W + 14
    T(ax, kx, H - 10, "Steps", size=F9, weight="bold", ha="left")
    for i, (k, lab) in enumerate(GLYPH_KEY):
        glyph_key(ax, kx, H - 26 - i * 16, [(k, lab)], gs=10)
    # panel B
    top = yb - 6
    panel_letter(ax, 0, top + 2, "B")
    cols = {"letter": 22, "context": 42, "list": 66, "ltext": 80, "weigh": 182, "wtext": 196, "final": 268,
            "out": 284, "calls": 438}
    T(ax, c.W - 3, top - 4, "LLM calls per\nindividual", size=F8, color=SOFT, ha="right", linespacing=0.95)
    y = top - 18
    for s in S:
        hgt = heights[s]
        yc = y - 6
        st = c.STEPS[s]
        letter(ax, cols["letter"], yc, s, size=F10)
        line(ax, [cols["letter"] + 8, cols["final"]], [yc, yc], color=SC[s], lw=2.2, z=2)
        if c.HAS_CONTEXT[s]:
            context_glyph(ax, cols["context"], yc, 14)
        pick = EX[s]["value"]
        if "list" in st:
            list_glyph(ax, cols["list"], yc, 13)
            value_list(ax, s, cols["ltext"], yc, pick, weights="weigh" in st, wx=cols["wtext"])
        if "weigh" in st:
            bars_glyph(ax, cols["weigh"], yc, 13)
        if st[-1] == "draw":
            die(ax, cols["final"], yc, 13)
        else:
            chip(ax, cols["final"], yc, 17)
        arrow(ax, cols["final"] + 11, yc, cols["out"] - 2, yc, color=SC[s], lw=0.9, head=4)
        T(ax, cols["out"] + 2, yc, f"“{pick}”".replace("“", '"').replace("”", '"'), size=F8,
          ha="left", weight="bold")
        T(ax, cols["calls"], yc, f"{c.CALLS[s]:.0f}", size=F9, weight="bold")
        if s != S[-1]:
            line(ax, [10, c.W - 4], [y - hgt - 1, y - hgt - 1], color=RULE, lw=0.5, z=0.5)
        y -= hgt + 3
    T(ax, c.W - 3, 7, "example: employment status, raw LLM text", size=F8, ha="right", color=SOFT,
      style="italic")
    return c.save(fig, "P09_current_a_example_horizontal")


# ================================================================== P10 vertical (transposed grid)
@house_style
def p10():
    H = 344
    fig, ax = c.canvas(H)
    yb = place_a(ax, 2, H - 2)
    kx = A_W + 14
    T(ax, kx, H - 10, "Steps", size=F9, weight="bold", ha="left")
    for i, (k, lab) in enumerate(GLYPH_KEY):
        glyph_key(ax, kx, H - 26 - i * 16, [(k, lab)], gs=10)
    top = yb - 6
    panel_letter(ax, 0, top + 2, "B")
    x0 = 30
    colw = (c.W - x0 - 4) / 5
    xs = {s: x0 + colw * (i + 0.5) for i, s in enumerate(S)}
    rows = {"head": top - 6, "calls": top - 18, "context": top - 34, "list": top - 54, "weigh": top - 118,
            "final": top - 172, "out": top - 186}
    T(ax, 3, rows["calls"], "LLM calls", size=F8, color=SOFT, ha="left")
    # rails
    for s in S:
        letter(ax, xs[s], rows["head"], s, size=F10)
        line(ax, [xs[s], xs[s]], [rows["head"] - 8, rows["out"] + 8], color=SC[s], lw=2.2, z=1)
    # row glyphs in the margin, grey
    for k in ("context", "list", "weigh"):
        step_glyph(ax, k, 12, rows[k], 11, color=SOFT)
    chip(ax, 12, rows["final"] + 6, 12, color=SOFT, label=False)
    die(ax, 12, rows["final"] - 7, 9, color=SOFT)
    for s in S:
        st, x, e = c.STEPS[s], xs[s], EX[s]
        pick = e["value"]
        if c.HAS_CONTEXT[s]:
            context_glyph(ax, x, rows["context"], 14)
        if "list" in st:
            list_glyph(ax, x, rows["list"], 13)
            for i, v in enumerate(e["candidates"][:N_SHOWN]):
                hit = v == pick
                T(ax, x, rows["list"] - 12 - i * LH, v, size=F8, weight="bold" if hit else "normal",
                  color=INK if hit else SOFT, zorder=4, bbox=dict(boxstyle="square,pad=0.05", fc="white", ec="none"))
            T(ax, x, rows["list"] - 12 - N_SHOWN * LH, f"+ {len(e['candidates']) - N_SHOWN} more", size=F8,
              color=SOFT, style="italic", zorder=4, bbox=dict(boxstyle="square,pad=0.05", fc="white", ec="none"))
        if "weigh" in st:
            bars_glyph(ax, x, rows["weigh"], 13)
            for i, w in enumerate(e["weights"][:N_SHOWN]):
                hit = e["candidates"][i] == pick
                yy = rows["weigh"] - 12 - i * LH
                ax.add_patch(Rectangle((x - 22, yy - 2.6), 30 * w / 0.7, 5.2, fc=INK if hit else BAR, ec="none",
                                       zorder=4))
                T(ax, x + 12, yy, f"{w:.2f}", size=F8, ha="left", color=INK if hit else SOFT,
                  weight="bold" if hit else "normal", zorder=4,
                  bbox=dict(boxstyle="square,pad=0.05", fc="white", ec="none"))
        if st[-1] == "draw":
            die(ax, x, rows["final"], 13)
        else:
            chip(ax, x, rows["final"], 17)
        out = pick if text_width(pick, F8, "bold") < colw - 6 else pick.replace(" (", "\n(")
        T(ax, x, rows["out"] - 6, f'"{out}"' if "\n" not in out else '"' + out + '"', size=F8, weight="bold",
          va="top", linespacing=0.95, zorder=4, bbox=dict(boxstyle="round,pad=0.15", fc="white", ec=SC[s], lw=0.8))
        T(ax, x, rows["calls"], f"{c.CALLS[s]:.0f}", size=F8, color=SOFT, zorder=4,
          bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none"))
    return c.save(fig, "P10_current_a_example_vertical")


# ================================================================== P11 beside, like the current layout
@house_style
def p11():
    H = 246
    fig, ax = c.canvas(H)
    place_a(ax, 2, H - 2)
    # A has room below it: the key
    T(ax, 8, H - A_H - 16, "Steps", size=F9, weight="bold", ha="left")
    glyph_key(ax, 8, H - A_H - 34, GLYPH_KEY[:3], gs=10)
    glyph_key(ax, 8, H - A_H - 52, GLYPH_KEY[3:], gs=10)
    calls_x = 8
    T(ax, calls_x, H - A_H - 78, "LLM calls per individual:", size=F8, color=SOFT, ha="left")
    xx = calls_x + text_width("LLM calls per individual:", F8) + 6
    for s in S:
        T(ax, xx, H - A_H - 78, c.LETTERS[s], size=F8, color=SC[s], weight="bold", ha="left")
        T(ax, xx + 7, H - A_H - 78, f"{c.CALLS[s]:.0f}", size=F8, ha="left")
        xx += 26
    # B: vertical rails + example callouts at right
    bx = A_W + 6
    panel_letter(ax, bx, H - 2, "B")
    xs = np.linspace(bx + 16, bx + 76, 5)
    ys = {"context": H - 40, "list": H - 76, "weigh": H - 116, "final": H - 152}
    for s, x in zip(S, xs):
        letter(ax, x, H - 22, s)
        line(ax, [x, x], [H - 29, ys["final"] - 14], color=SC[s], lw=2.2, z=2)

    def plate(k, members, draw):
        xm = [xs[S.index(s)] for s in members]
        y = ys[k]
        box(ax, min(xm) - 7, y - 11, max(xm) - min(xm) + 14, 22, ec=SOFT, fc=PANEL, lw=0.6, r=5, z=3)
        draw((min(xm) + max(xm)) / 2, y)

    plate("context", [s for s in S if c.HAS_CONTEXT[s]], lambda x, y: context_glyph(ax, x, y, 16))
    plate("list", [s for s in S if "list" in c.STEPS[s]], lambda x, y: list_glyph(ax, x, y, 15))
    plate("weigh", [s for s in S if "weigh" in c.STEPS[s]], lambda x, y: bars_glyph(ax, x, y, 15))
    plate("final", [s for s in S if c.STEPS[s][-1] == "choose"], lambda x, y: chip(ax, x, y, 19))
    die(ax, xs[-1], ys["final"], 13)
    # callouts: strategy E's own call (list + probabilities + draw)
    E = S[-1]
    cx = bx + 92
    e = EX[E]
    T(ax, cx, H - 22, "example (E)", size=F8, color=SC[E], weight="bold", ha="left")
    line(ax, [bx + 84, cx - 2], [ys["list"], ys["list"] + 6], color=SOFT, lw=0.5, ls=(0, (1.5, 1)))
    for i, v in enumerate(e["candidates"][:N_SHOWN]):
        hit = v == e["value"]
        T(ax, cx, ys["list"] + 12 - i * LH, v, size=F8, ha="left", color=INK if hit else SOFT,
          weight="bold" if hit else "normal")
    T(ax, cx, ys["list"] + 12 - N_SHOWN * LH, f"+ {len(e['candidates']) - N_SHOWN} more", size=F8, ha="left",
      color=SOFT, style="italic")
    for i, w in enumerate(e["weights"][:N_SHOWN]):
        hit = e["candidates"][i] == e["value"]
        yy = ys["weigh"] - 4 - i * LH
        ax.add_patch(Rectangle((cx, yy - 2.6), 30 * w / 0.7, 5.2, fc=INK if hit else BAR, ec="none", zorder=3))
        T(ax, cx + 33, yy, f"{w:.2f}", size=F8, ha="left", color=INK if hit else SOFT,
          weight="bold" if hit else "normal")
    line(ax, [bx + 84, cx - 2], [ys["weigh"], ys["weigh"] - 4], color=SOFT, lw=0.5, ls=(0, (1.5, 1)))
    # outputs: one line per strategy under the rails
    for i, s in enumerate(S):
        y = ys["final"] - 26 - i * 11
        line(ax, [xs[i], xs[i]], [88, y + 4], color=SC[s], lw=0.8, z=1) if False else None
        T(ax, bx + 8, y, c.LETTERS[s], size=F8, color=SC[s], weight="bold")
        T(ax, bx + 16, y, f'"{EX[s]["value"]}"', size=F8, ha="left", weight="bold" if s == E else "normal")
    for x, s in zip(xs, S):
        ax.add_patch(Circle((x, ys["final"] - 14), 3.2, fc=SC[s], ec="white", lw=0.6, zorder=4))
    T(ax, bx + 8, 6, "example: employment status, raw LLM text", size=F8, ha="left", color=SOFT, style="italic")
    return c.save(fig, "P11_current_a_beside_example")


ALL = {"P09": p09, "P10": p10, "P11": p11}

if __name__ == "__main__":
    for k in (sys.argv[1:] or ALL):
        try:
            print(k, ALL[k]())
        except Exception as ex:
            print(k, "FAILED", str(ex)[:220])
