"""Figure 3 round 8 (P23): redrawn compact vector panel A + P21's B + simplified strategy-E example.

Panel A keeps the current panel A's content (5 levels, 14 attributes, one context line per level, dependency
arrows, highlighted attributes) but every element is derived from the strategy config and asserted:
levels = longest depends_on path; context text = the transitive dependencies of the level's attributes;
highlight = attributes whose LLM dependencies differ from the reference tables' conditioning (common.DIFFERS).
"""
from __future__ import annotations

import sys

from matplotlib.patches import Circle, Rectangle

import common as c
from common import (F8, F10, F12, INK, SOFT, T, box, line, arrow, chip, call_chip, die, step_glyph, panel_letter,
                    letter, text_width)
from example import EX, N_SHOWN
from protos5 import CONTEXT_SHOWN, _ctx
from population_synthetic.analysis.utils.labels import attribute_label
from population_synthetic.analysis.utils.style import house_style

S = c.STRATEGIES
SC = c.STRAT_COLOR
E_ = S[-1]
MID = "#9A9A9A"
LH = 9.4
LINE = 8.9           # 8 pt text line pitch inside boxes
HEAD_FILL = "#BDBDBD"   # level header tabs: one neutral grey
ATTR_FILL = "#E3E3E3"   # attribute boxes
HIGHLIGHT = "#F0E442"   # Okabe-Ito yellow: used by no other figure in the article
EDGE = "#6E6E6E"

# ---------------------------------------------------------------- panel A content, derived from config
SHORT = {  # the current panel A's own words for the attributes and its context lists
    "age": "age", "biological_sex": "sex", "region": "region", "parental_structure": "parental\nstructure",
    "birth_country_detail": "birth\ncountry", "civil_status": "civil\nstatus", "education_level": "education\nlevel",
    "household_size": "household\nsize", "employment_status": "employment\nstatus",
    "employment_type": "employment\ntype", "industry_sector": "industry\nsector",
    "socioeconomic_class": "socioeconomic\nclass", "income_source": "income\nsource",
    "housing_tenure": "housing\ntenure",
}
CTX_WORD = {"age": "age", "biological_sex": "sex", "civil_status": "civil", "education_level": "education",
            "employment_status": "employment", "socioeconomic_class": "socioeconomic"}
ORDER_IN_LIST = ["age", "biological_sex", "civil_status", "education_level", "employment_status", "socioeconomic_class"]


def ancestors(a, memo={}):
    if a not in memo:
        s = set()
        for d in c.DEPS[a]:
            s |= {d} | ancestors(d)
        memo[a] = s
    return memo[a]


# the current panel A's grouping: one context box per level, except level 3, whose household size has its own
GROUPS = {
    1: [["age", "biological_sex", "parental_structure", "region"]],
    2: [["education_level", "civil_status", "birth_country_detail"]],
    3: [["employment_status"], ["household_size"]],
    4: [["socioeconomic_class", "employment_type", "industry_sector"]],
    5: [["housing_tenure", "income_source"]],
}
for k, gs in GROUPS.items():
    assert sorted(a for g in gs for a in g) == sorted(c.BY_LEVEL[k]), k
    for g in gs:  # every attribute in a group has the same transitive dependencies (one context line is exact)
        assert len({frozenset(ancestors(a)) for a in g}) == 1, g
# arrows of the current panel A: which attributes feed which context box
FEEDS = {(2, 0): ["age", "biological_sex"], (3, 0): ["education_level", "civil_status"],
         (3, 1): ["civil_status"], (4, 0): ["employment_status"], (5, 0): ["socioeconomic_class"]}
for (k, gi), srcs in FEEDS.items():  # each feeding attribute is a direct dependency of that group
    g = GROUPS[k][gi]
    assert all(any(s_ in c.DEPS[a] for a in g) for s_ in srcs), (k, srcs)

HIGHLIGHTED = {a for a in c.ORDER if c.DIFFERS[a]}
_SEVEN = {"household_size", "employment_status", "employment_type", "industry_sector",
          "socioeconomic_class", "income_source", "housing_tenure"}
# ref-v3: region is now conditioned on (age group, sex) in the reference but has no parents in the LLM graph: eight
assert HIGHLIGHTED == (_SEVEN | {"region"} if "region" in HIGHLIGHTED else _SEVEN), HIGHLIGHTED


def ctx_text(g, maxw=50):
    anc = ancestors(g[0])
    if not anc:
        return "∅"
    words = [CTX_WORD[a] for a in ORDER_IN_LIST if a in anc]
    assert len(words) == len(anc)
    lines, cur = [], "| "
    for i, w in enumerate(words):
        piece = w + ("," if i < len(words) - 1 else "")
        if cur.strip() in ("|",):
            cur = "| " + piece
        elif text_width(cur + " " + piece, F8) <= maxw:
            cur = cur + " " + piece
        else:
            lines.append(cur)
            cur = piece
    lines.append(cur)
    return "\n".join(lines)


def panel_a(ax, x0, ytop):
    """Draws panel A; returns (right x, bottom y)."""
    gap = 4
    widths = {}
    for k, gs in GROUPS.items():
        texts = [SHORT[a] for g in gs for a in g] + [ctx_text(g, maxw=0) for g in gs] + [f"Level {k}"]
        widths[k] = max(text_width(p, F8) for t_ in texts for p in t_.split("\n")) + 6
    x = x0
    pos, ctxbox = {}, {}
    ybot = ytop
    for k in range(1, 6):
        w = widths[k]
        # header tab
        box(ax, x, ytop - 11, w, 11, ec="none", fc=HEAD_FILL, r=2.5, z=2)
        T(ax, x + w / 2, ytop - 5.6, f"Level {k}", size=F8, weight="bold", color=INK, zorder=3)
        y = ytop - 13
        for gi, g in enumerate(GROUPS[k]):
            txt = ctx_text(g, maxw=w - 4)
            n = txt.count("\n") + 1
            hgt = n * LINE + 3
            box(ax, x, y - hgt, w, hgt, ec=EDGE, fc="white", lw=0.5, r=2.5, z=2)
            if txt == "∅":  # Arial has no empty-set glyph: draw it
                ax.add_patch(Circle((x + w / 2, y - hgt / 2), 3.2, fc="none", ec=SOFT, lw=0.7, zorder=3))
                line(ax, [x + w / 2 - 4.2, x + w / 2 + 4.2], [y - hgt / 2 - 4.2, y - hgt / 2 + 4.2], color=SOFT,
                     lw=0.7, z=3)
            else:
                T(ax, x + 3, y - hgt / 2, txt, size=F8, color=SOFT, ha="left", linespacing=1.0, zorder=3)
            ctxbox[(k, gi)] = (x, y - hgt / 2)
            y -= hgt + 1.5
            for a in g:
                n = SHORT[a].count("\n") + 1
                hgt = n * LINE + 2.5
                hl = a in HIGHLIGHTED
                box(ax, x, y - hgt, w, hgt, ec=INK if hl else EDGE, fc=HIGHLIGHT if hl else ATTR_FILL,
                    lw=0.9 if hl else 0.5, r=2.5, z=2)
                T(ax, x + w / 2, y - hgt / 2, SHORT[a], size=F8, color=INK, linespacing=1.0, zorder=3)
                pos[a] = (x, x + w, y - hgt / 2)
                y -= hgt + 1.5
            y -= 1.5
        ybot = min(ybot, y)
        x += w + gap
    # arrows: from each feeding attribute's right edge into the context box (elbow in the gap)
    for (k, gi), srcs in FEEDS.items():
        cx, cy = ctxbox[(k, gi)]
        gx = cx - gap / 2
        for s_ in srcs:
            _, xr, ys = pos[s_]
            line(ax, [xr, gx], [ys, ys], color=INK, lw=0.6, z=4)
            line(ax, [gx, gx], [ys, cy], color=INK, lw=0.6, z=4)
        arrow(ax, gx, cy, cx, cy, color=INK, lw=0.6, head=3.0, z=4)
    return x - gap, ybot


# ---------------------------------------------------------------- panel B grid (P21, labels on one line)
LABELS = ["attributes\nalready set", "candidates", "probabilities", "LLM picks\nor draw"]


def label_w(s):
    return max(text_width(p, F8) for p in s.split("\n"))


HEAD_CHIP = 12   # header chips: one size for the three LLM-call columns


def call_key(ax, x, y, vertical=False, pitch=12.0):
    """Key for the step symbols: an empty chip = one LLM call; the die = a random draw (code). Left edge at x;
    returns the right edge (horizontal) or the bottom row's y (vertical)."""
    call_chip(ax, x + 6, y, 13, None, color=SOFT)
    T(ax, x + 15, y, "= one LLM call", size=F8, color=SOFT, ha="left")
    if vertical:
        x2, y2 = x, y - pitch
    else:
        x2, y2 = x + 15 + text_width("= one LLM call", F8) + 12, y
    die(ax, x2 + 6, y2, 8.5, color=SOFT)
    T(ax, x2 + 15, y2, "= random draw", size=F8, color=SOFT, ha="left")
    return y2 if vertical else x2 + 15 + text_width("= random draw", F8)


def grid(ax, x0, x1, ytop, pitch=13.2, gs=10):
    lx = x0 + 3
    c0 = max(lx + 16, x0 + label_w(LABELS[0]) / 2)
    c3 = x1 - label_w(LABELS[3]) / 2
    c1 = c0 + label_w(LABELS[0]) / 2 + label_w(LABELS[1]) / 2 + 3
    c2 = c3 - label_w(LABELS[3]) / 2 - label_w(LABELS[2]) / 2 - 3
    xs = [c0, c1, c2, c3]
    for a, b, la, lb in zip(xs, xs[1:], LABELS, LABELS[1:]):
        assert b - a >= label_w(la) / 2 + label_w(lb) / 2 + 2, (a, b, la, lb)
    y_icon = ytop - 8
    step_glyph(ax, "context", xs[0], y_icon, 11, color=SOFT)
    call_chip(ax, xs[1], y_icon, HEAD_CHIP, "list", color=SOFT)      # LLM call: candidates
    call_chip(ax, xs[2], y_icon, HEAD_CHIP, "weigh", color=SOFT)     # LLM call: probabilities
    call_chip(ax, xs[3] - 7.5, y_icon, HEAD_CHIP, "pick", color=SOFT)   # LLM call: pick
    T(ax, xs[3] + 0.5, y_icon, "/", size=F8, color=SOFT)
    die(ax, xs[3] + 7.5, y_icon, 8.5, color=SOFT)
    for kx, lab in zip(xs, LABELS):
        T(ax, kx, y_icon - 9, lab, size=F8, color=SOFT, va="top", linespacing=0.95)
    y = y_icon - 9 - 2 * 9.4 - 7
    for s in S:
        letter(ax, lx, y, s, size=F10)
        line(ax, [lx + 7, x1 - 1], [y, y], color=SC[s], lw=2.0, z=2)
        st = c.STEPS[s]
        have = [c.HAS_CONTEXT[s], "list" in st, "weigh" in st, True]
        for kx, k, h in zip(xs, ["context", "list", "weigh", "final"], have):
            if not h:
                continue
            if k == "final":
                if st[-1] == "draw":
                    die(ax, kx, y, gs)                       # random draw: not an LLM call
                else:
                    call_chip(ax, kx, y, gs + 4, "pick")     # LLM call: pick
            elif k == "context":
                step_glyph(ax, k, kx, y, gs)                 # prompt context: not an LLM call
            else:
                call_chip(ax, kx, y, gs + 4, k)             # LLM call: candidates / probabilities
        y -= pitch
    return y + pitch - 7


# ---------------------------------------------------------------- simplified example: the four shown = whole list
_cands = EX[E_]["candidates"][:N_SHOWN]
_w4 = EX[E_]["weights"][:N_SHOWN]
RENORM = [w / sum(_w4) for w in _w4]
SHOWN_TXT = [round(w, 2) for w in RENORM]
ADJUST = round(1.0 - sum(SHOWN_TXT), 2)
assert ADJUST == 0.0, (SHOWN_TXT, ADJUST)   # 0.77 + 0.07 + 0.11 + 0.05 = 1.00, no adjustment needed
assert SHOWN_TXT == [0.77, 0.07, 0.11, 0.05]
DRAWN = EX[E_]["value"]
assert DRAWN == "unemployed" and DRAWN in _cands


def example_strip(ax, x0, x1, ytop):
    T(ax, x0 + 6, ytop - 3, "Example (strategy E): setting employment status", size=F8, weight="bold",
      color=SC[E_], ha="left", va="top")
    cols = {"ctx": x0 + 22, "cand": x0 + 236, "prob": x0 + 342, "draw": x0 + 410}
    hy = ytop - 22
    letter(ax, x0 + 9, hy - 22, E_, size=F10)
    step_glyph(ax, "context", cols["ctx"] + 6, hy, 11)
    call_chip(ax, cols["cand"] + 6, hy, 14, "list")     # LLM call
    call_chip(ax, cols["prob"] + 6, hy, 14, "weigh")    # LLM call
    die(ax, cols["draw"] + 6, hy, 9.5)
    for xa, xb in ((cols["ctx"] + 14, cols["cand"] - 4), (cols["cand"] + 16, cols["prob"] - 3),
                   (cols["prob"] + 14, cols["draw"] - 4)):
        arrow(ax, xa, hy, xb, hy, color=SOFT, lw=0.6, head=3.5)
    y0 = hy - 14
    for i, a in enumerate(CONTEXT_SHOWN):
        T(ax, cols["ctx"], y0 - i * LH, f"{attribute_label(a)}: {_ctx[a]}", size=F8, ha="left", color=INK)
    for i, (v, w, wt) in enumerate(zip(_cands, RENORM, SHOWN_TXT)):
        y = y0 - i * LH
        hit = v == DRAWN
        T(ax, cols["cand"], y, v, size=F8, ha="left", color=INK if hit else SOFT, weight="bold" if hit else "normal")
        ax.add_patch(Rectangle((cols["prob"], y - 2.6), 34 * w / max(RENORM), 5.2, fc=INK if hit else MID,
                               ec="none", zorder=3))
        T(ax, cols["prob"] + 37, y, f"{wt:.2f}", size=F8, ha="left", color=INK if hit else SOFT,
          weight="bold" if hit else "normal")
        if hit:
            die(ax, cols["draw"] + 6, y, 9)
            T(ax, cols["draw"] + 14, y, "drawn", size=F8, ha="left", weight="bold")
    ybot = y0 - (N_SHOWN - 1) * LH - 6
    box(ax, x0, ybot, x1 - x0, ytop - ybot, ec=SC[E_], fc="white", lw=0.7, r=3, z=0.5)
    return ybot


GUTTER = 13


@house_style
def p23():
    H = 194
    fig, ax = c.canvas(H)
    top = H - 2
    panel_letter(ax, 2, top, "A")
    ax_right, a_bot = panel_a(ax, 12, top - 2)
    bx0 = ax_right + GUTTER
    panel_letter(ax, bx0, top, "B")
    b_bot = grid(ax, bx0 + 2, c.W - 2, top)
    strip_top = min(a_bot, b_bot) - 4
    yb = example_strip(ax, 3, c.W - 3, strip_top)
    assert yb >= 2, ("too low by", 2 - yb)
    print("panel A width", round(ax_right - 14, 1), "bottom", round(a_bot, 1), "; B bottom", round(b_bot, 1),
          "; strip bottom", round(yb, 1))
    return c.save(fig, "P23_compact_vector_a_simplified_example")


if __name__ == "__main__":
    print("renormalised", [round(w, 4) for w in RENORM], "displayed", SHOWN_TXT, "adjust", ADJUST)
    print(p23())
