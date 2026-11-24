"""Figure 3 round 5 (P20): P19 + labelled B columns + a column-wise strategy E example with its real context.

Run: python protos5.py. Current panel A unchanged at its printed size; no key under A (the words sit at the top of
B's columns); no calls per individual; no '+n more'.
"""
from __future__ import annotations

import sys

from matplotlib.patches import Rectangle

import common as c
from common import (F8, F10, INK, SOFT, T, box, line, arrow, chip, die, step_glyph, panel_letter, letter,
                    text_width)
from example import EX, N_SHOWN
from protos2 import place_a, A_W, A_H
from population_synthetic.analysis.utils.labels import attribute_label
from population_synthetic.analysis.utils.style import house_style

S = c.STRATEGIES
SC = c.STRAT_COLOR
E_ = S[-1]
MID = "#9A9A9A"
LH = 9.4
CONTEXT_SHOWN = ["age", "biological_sex", "civil_status", "education_level"]  # the four the author asked for

# real context of strategy E's first individual (the same call whose candidates and probabilities are shown)
_ctx = dict(ln.split(": ", 1) for ln in EX[E_]["context_lines"])
assert _ctx["age"] == "55" and _ctx["biological_sex"] == "male" and _ctx["civil_status"] == "divorced"
assert _ctx["education_level"] == "upper secondary education (gymnasium)"
assert len(_ctx) == 8  # the real prompt also carried region, parental structure, birth country, household size


def grid(ax, x0, x1, ytop, pitch=13.2, gs=10):
    """P19's grid; the step words sit at the column tops, staggered above / below the icons so they never collide."""
    lx = x0 + 5
    xs = [lx + 20 + k * 40 for k in range(4)]
    assert xs[-1] + 9 <= x1, xs
    y_above = ytop - 2
    y_icon = ytop - 27
    y_below = y_icon - 9
    # labels: columns 1 and 3 above the icons, 2 and 4 below
    T(ax, xs[0], y_above, "attributes\nalready set", size=F8, color=SOFT, va="top", linespacing=0.95)
    T(ax, xs[2], y_above - 9, "probabilities", size=F8, color=SOFT, va="top")
    T(ax, xs[1], y_below, "candidates", size=F8, color=SOFT, va="top")
    T(ax, x1, y_below, "LLM picks /\nrandom draw", size=F8, color=SOFT, va="top", ha="right", linespacing=0.95)
    for kx, k in zip(xs, ["context", "list", "weigh"]):
        step_glyph(ax, k, kx, y_icon, 11, color=SOFT)
    chip(ax, xs[3] - 7, y_icon, 11, color=SOFT, label=False)
    T(ax, xs[3] + 0.5, y_icon, "/", size=F8, color=SOFT)
    die(ax, xs[3] + 7.5, y_icon, 8.5, color=SOFT)
    y = y_below - 2 * 9.4 - 6
    for s in S:
        letter(ax, lx, y, s, size=F10)
        line(ax, [lx + 7, x1 - 2], [y, y], color=SC[s], lw=2.0, z=2)
        st = c.STEPS[s]
        have = [c.HAS_CONTEXT[s], "list" in st, "weigh" in st, True]
        for kx, k, h in zip(xs, ["context", "list", "weigh", "final"], have):
            if not h:
                continue
            if k == "final":
                if st[-1] == "draw":
                    die(ax, kx, y, gs)
                else:
                    chip(ax, kx, y, gs + 4)
            else:
                step_glyph(ax, k, kx, y, gs)
        y -= pitch
    return y + pitch


def example_strip(ax, x0, x1, ytop):
    """Strategy E's call as four columns headed by the same icons as panel B: context, candidates, probabilities, draw."""
    e = EX[E_]
    cols = {"ctx": x0 + 22, "cand": x0 + 236, "prob": x0 + 342, "draw": x0 + 410}
    hy = ytop - 9
    letter(ax, x0 + 9, hy - 22, E_, size=F10)
    step_glyph(ax, "context", cols["ctx"] + 6, hy, 11)
    step_glyph(ax, "list", cols["cand"] + 6, hy, 11)
    T(ax, cols["cand"] + 15, hy, "employment status", size=F8, ha="left", weight="bold", color=INK)
    step_glyph(ax, "weigh", cols["prob"] + 6, hy, 11)
    die(ax, cols["draw"] + 6, hy, 9.5)
    for xa, xb in ((cols["ctx"] + 14, cols["cand"] - 4), (cols["cand"] + 90, cols["prob"] - 3),
                   (cols["prob"] + 14, cols["draw"] - 4)):
        arrow(ax, xa, hy, xb, hy, color=SOFT, lw=0.6, head=3.5)
    y0 = hy - 14
    for i, a in enumerate(CONTEXT_SHOWN):
        T(ax, cols["ctx"], y0 - i * LH, f"{attribute_label(a)}: {_ctx[a]}", size=F8, ha="left", color=INK)
    for i, v in enumerate(e["candidates"][:N_SHOWN]):
        y = y0 - i * LH
        hit = v == e["value"]
        T(ax, cols["cand"], y, v, size=F8, ha="left", color=INK if hit else SOFT, weight="bold" if hit else "normal")
        w = e["weights"][i]
        ax.add_patch(Rectangle((cols["prob"], y - 2.6), 34 * w / 0.68, 5.2, fc=INK if hit else MID, ec="none",
                               zorder=3))
        T(ax, cols["prob"] + 37, y, f"{w:.2f}", size=F8, ha="left", color=INK if hit else SOFT,
          weight="bold" if hit else "normal")
        if hit:
            die(ax, cols["draw"] + 6, y, 9)
            T(ax, cols["draw"] + 14, y, "drawn", size=F8, ha="left", weight="bold")
    ybot = y0 - (N_SHOWN - 1) * LH - 6
    box(ax, x0, ybot, x1 - x0, ytop - ybot, ec=SC[E_], fc="white", lw=0.7, r=3, z=0.5)
    return ybot


@house_style
def p20():
    H = 187
    fig, ax = c.canvas(H)
    place_a(ax, 2, H - 2)
    bx0, bx1 = A_W + 12, c.W - 2
    panel_letter(ax, bx0 - 6, H - 2, "B")
    yb_grid = grid(ax, bx0, bx1, H - 2)
    assert yb_grid > H - 2 - A_H - 2, yb_grid  # grid stays beside panel A
    yb = example_strip(ax, 3, c.W - 3, H - A_H - 6)
    assert yb >= 2, yb
    return c.save(fig, "P20_p19_labelled_example_columns")


ALL = {"P20": p20}

if __name__ == "__main__":
    for k in (sys.argv[1:] or ALL):
        try:
            print(k, ALL[k]())
        except Exception as ex:
            print(k, "FAILED", str(ex)[:220])
