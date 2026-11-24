"""Figure 3 round 10 (P30): P24 with orthogonal elbow connectors and panel A moved left, letter above it.

Each of the five dependency arrows: horizontal run out of the source attribute, vertical run in the gap, then a
horizontal stub that enters the target context box from the left with the arrowhead on it.
"""
from __future__ import annotations

import matplotlib.pyplot as plt

import common as c
from common import F8, INK, T, box, line, arrow, panel_letter, text_width
import protos9 as p9
from protos8 import FEEDS, GROUPS, SHORT, ctx_text, grid, example_strip, call_key
from population_synthetic.analysis.utils.style import house_style

GAP = 5.8        # column gap in panel A (P24: 4)
STUB = 4.2       # horizontal stub before the target box; arrowhead sits on it
HEAD = 2.8
LW = 0.6
X0 = 2.0         # panel A left edge (P24: 12)
DROP = 9.0       # panel A starts this far below the canvas top so the letter sits above level 1's header


def elbow_arrows(ax, pos, ctxpos, gap, color=INK):
    for (k, gi), srcs in FEEDS.items():
        cx, cy = ctxpos[(k, gi)]
        vx = cx - STUB
        ys = [pos[s_][2] for s_ in srcs]
        for s_ in srcs:
            _, xr, y_ = pos[s_]
            assert vx - xr >= 1.4, (s_, vx - xr)
            line(ax, [xr, vx], [y_, y_], color=color, lw=LW, z=4, cap="butt")
        line(ax, [vx, vx], [min(ys + [cy]), max(ys + [cy])], color=color, lw=LW, z=4, cap="butt")
        arrow(ax, vx, cy, cx, cy, color=color, lw=LW, head=HEAD, z=4)


def col_widths_bold(pad=3.0, ctx_in=True):
    w = {}
    for k, gs in GROUPS.items():
        names = [p for g in gs for a in g for p in SHORT[a].split("\n")]
        ctx = [p for g in gs for p in ctx_text(g, maxw=0).split("\n")] if ctx_in else []
        w[k] = max(max([text_width(p, F8, "bold") for p in names] + [text_width(f"Level {k}", F8, "bold")]) + pad,
                   max([text_width(p, F8) for p in ctx] + [0]) + 5)   # context text starts 3 pt in
    return w


@house_style
def p30():
    p9.feed_arrows = elbow_arrows          # P24's drawing, new connectors
    p9.col_widths = lambda pad=6, ctx_in=True: col_widths_bold()
    H = 210.0
    for _ in range(3):
        fig, ax = c.canvas(H)
        top = H - 2
        panel_letter(ax, 1, top + 1, "A")
        ar, ab = p9.boxes_a(ax, X0, top - DROP, bands=True, bold=True, gap=GAP)
        bx0 = max(ar, 258) + p9.GUTTER
        panel_letter(ax, bx0, top + 1, "B")
        bb = grid(ax, bx0 + 2, c.W - 2, top)
        ky = bb - 8                               # key for the step symbols, under the rails
        call_key(ax, bx0 + 12, ky)
        bb = ky - 7
        yb = example_strip(ax, 3, c.W - 3, min(ab, bb) - 4)
        if abs(yb - 2.5) < 0.3:
            break
        plt.close(fig)
        H = round(H - (yb - 2.5), 1)
    assert H < 214, H
    print("B rails+key bottom =", round(bb, 1), "A bottom =", round(ab, 1))
    print("H =", H, "A left =", X0, "A right =", round(ar, 1), "gutter =", round(bx0 - ar, 1))
    return c.save(fig, "P30_p24_elbow_arrows")


if __name__ == "__main__":
    print(p30())
