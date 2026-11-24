"""Figure 2 round 5: all five Level 2 attributes in the Level 2 column (F2_P14, F2_P15, F2_P16; base F2_P12).

F2_P12's grammar (Figure 3A setup): level tab, one grey context box per group above its attribute boxes, arrows
entering the context box, P30 boxes and elbow arrows, full-width level greens. The housing tenure /
socioeconomic class trick (Level 2 drawn under Level 3, dashed L outline, extra context box) is dropped: education
level, civil status, birth country, housing tenure and socioeconomic class all sit under Level 2's single
"| age, sex" box.

  P14  one plain column of five; "socioeconomic class" on two lines so the column stays narrow
  P15  Level 2 as a two-wide sub-grid (2 + 2 + 1) under one context box spanning it; Level 2 names on two lines
  P16  one column of five with every Level 2 name on one line, unabbreviated; Level 3 and 4 text wrapped instead

Income-source wording is switchable: default "| employment status, age" (the author's decision, what the sampler
does); --income=current restores "if employed | age" with the "no sex filter" note.
Run: python protos_l2.py [P14 P15 P16] [--income=status|current]
"""
from __future__ import annotations

import sys

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

from protos_a import (A, ATTR, ATTR_EDGE, B, BC, BOX_GAP, F12, GAP, HEADER_H, LEVEL_FILL, LINE, PAD_V, STUB, X0,
                      DROP, A_W, A_H, A_CORNER, tw)
from protos_ctx import CTX_FILL, empty_set, note

#: Income-source context (the author, 2026-10-20: "| employment status, age"; drawn for everyone). The no-sex-filter
#: note is dropped with the new label: the label lists its whole set, so the missing sex is already stated.
#: "current" restores Figure 2A's old wording with its note.
INCOME_CTX = {"current": ["if employed | age", "NOTE"], "status": ["| employment status,", "age"]}
INCOME_MODE = "status"
for arg in sys.argv[1:]:
    if arg.startswith("--income="):
        INCOME_MODE = arg.split("=", 1)[1]
        assert INCOME_MODE in INCOME_CTX, INCOME_MODE

NAMES = {   # one-line defaults; variants override
    "age_sex": ["age, sex"], "parental": ["parental", "structure"], "household": ["household", "size"],
    "region": ["region"], "education": ["education level"], "civil": ["civil status"],
    "birth": ["birth country"], "housing": ["housing tenure"], "socio": ["socioeconomic class"],
    "employment": ["employment status"], "income": ["income source"], "emptype": ["employment type"],
    "industry": ["industry sector"],
}
import os as _os
#: ref-v3: the reference now draws region from the SCB region table filtered on age group and sex, so region moves
#: from Level 1 (unconditioned) to the Level 2 column ("| age, sex"). REFV3_REGION_L2=0 switches it off
#: (used only to check that this copy reproduces the staged F01-F02_reference_population_02.svg).
REGION_L2 = _os.environ.get("REFV3_REGION_L2", "1") == "1"
L1 = ("age_sex", "parental", "household") + (() if REGION_L2 else ("region",))
L2 = ["education", "civil", "birth", "housing", "socio"] + (["region"] if REGION_L2 else [])
CTX_H1 = LINE + 3.0


def ctx_h(lines):
    return len(lines) * LINE + 3.0


def attr_h(lines):
    return len(lines) * LINE + PAD_V


def draw(fig, H, *, names, ctx3, ctx4b, l2="column", grid_rows=None, income_lines=None):
    a = A(fig, H)
    ax = a.ax
    ax.add_patch(FancyBboxPatch((-40, -40), A_W + 40, A_H + 40, boxstyle=f"round,pad=0,rounding_size={A_CORNER}",
                                fc="white", ec="none", zorder=0))
    ax.text(1, 0.5, "a", fontsize=F12, fontweight="bold", ha="left", va="top", color="black")
    ctx4a = income_lines or INCOME_CTX[INCOME_MODE]
    top = DROP
    y0 = top + HEADER_H + BOX_GAP

    def bw(keys):
        return max(tw(p, True) for k in keys for p in names[k]) + 3.0

    def cw(lines):
        return max([tw(p) for p in lines if p != "NOTE"]
                   + ([tw("no sex filter") + 4] if "NOTE" in lines else [])) + 5.0

    w1 = max(bw(list(L1)), tw("Level 1", True) + 3)
    if l2 == "column":
        w2 = max(bw(L2), cw(["| age, sex"]))
    else:
        paired = [k_ for row in grid_rows if len(row) == 2 for k_ in row]
        spanning = [row[0] for row in grid_rows if len(row) == 1]
        sub = bw(paired)
        w2 = max(2 * sub + BOX_GAP, cw(["| age, sex"]), bw(spanning) if spanning else 0)
        sub = (w2 - BOX_GAP) / 2
    w3 = max(bw(["employment"]), cw(ctx3))
    w4 = max(bw(["income", "emptype", "industry"]), cw(ctx4a), cw(ctx4b))
    widths = {1: w1, 2: w2, 3: w3, 4: w4}
    xs, x = {}, X0
    for k in range(1, 5):
        xs[k] = x
        x += widths[k] + GAP
    right = x - GAP
    items = {}

    def place(name, kind, k, y, h, xx=None, ww=None):
        items[name] = (xs[k] if xx is None else xx, y, widths[k] if ww is None else ww, h, kind)
        return y + h + BOX_GAP

    y = place("c1", "ctx", 1, y0, CTX_H1)
    for k_ in L1:
        y = place(k_, "attr", 1, y, attr_h(names[k_]))
    y = place("c2", "ctx", 2, y0, CTX_H1)
    if l2 == "column":
        for k_ in L2:
            y = place(k_, "attr", 2, y, attr_h(names[k_]))
    else:
        for row in grid_rows:
            hrow = max(attr_h(names[k_]) for k_ in row)
            if len(row) == 1:                     # a row of one spans the sub-grid
                place(row[0], "attr", 2, y, hrow)
            for j, k_ in enumerate(row if len(row) == 2 else []):
                place(k_, "attr", 2, y, hrow, xx=xs[2] + j * (sub + BOX_GAP), ww=sub)
            y += hrow + BOX_GAP
    y = place("c3", "ctx", 3, y0, ctx_h(ctx3))
    y = place("employment", "attr", 3, y, attr_h(names["employment"]))
    y = place("c4a", "ctx", 4, y0, ctx_h(ctx4a))
    y = place("income", "attr", 4, y, attr_h(names["income"]))
    y = place("c4b", "ctx", 4, y, ctx_h(ctx4b))
    for k_ in ("emptype", "industry"):
        y = place(k_, "attr", 4, y, attr_h(names[k_]))
    ctx_lines = {"c1": None, "c2": ["| age, sex"], "c3": ctx3, "c4a": ctx4a, "c4b": ctx4b}
    for name, (bx, by, bw_, bh, kind) in items.items():
        if kind == "ctx":
            a.box(bx, by, bw_, bh, CTX_FILL, ATTR_EDGE, lw=0.5)
            lines = ctx_lines[name]
            if lines is None:
                empty_set(ax, bx + bw_ / 2, by + bh / 2)
                continue
            for j, t in enumerate(lines):
                yy = by + 1.5 + LINE / 2 + j * LINE
                if t == "NOTE":
                    note(ax, bx + 3, yy)
                else:
                    a.T(bx + 3, yy, t, ha="left", zorder=5)
        else:
            a.box(bx, by, bw_, bh, ATTR, ATTR_EDGE)
            nl = names[name]
            y_first = by + bh / 2 - (len(nl) - 1) * LINE / 2
            for j, t in enumerate(nl):
                a.T(bx + bw_ / 2, y_first + j * LINE, t, bold=True, zorder=5)
    for k in range(1, 5):
        a.box(xs[k], top, widths[k], HEADER_H, LEVEL_FILL[k], z=2)
        a.T(xs[k] + widths[k] / 2, top + 5.6, f"Level {k}", bold=True, zorder=3)
    yb0 = top + HEADER_H
    col_bottom = {}
    for k in range(1, 5):
        col_bottom[k] = max(v[1] + v[3] for v in items.values() if xs[k] - 0.01 <= v[0] < xs[k] + widths[k])
        ax.add_patch(Rectangle((xs[k], yb0), widths[k], col_bottom[k] + BOX_GAP / 2 - yb0, fc=LEVEL_FILL[k],
                               ec="none", zorder=1))

    def mid(n):
        bx, by, bw_, bh, _ = items[n]
        return bx + bw_, by + bh / 2

    def tgt(n):
        return items[n][0], items[n][1] + 1.5 + LINE / 2

    def feed(src, tgts, vx):
        xr, ys = mid(src)
        tp = [tgt(t) for t in tgts]
        a.line([xr, vx], [ys, ys])
        a.line([vx, vx], [min([ys] + [p[1] for p in tp]), max([ys] + [p[1] for p in tp])])
        for tx, ty in tp:
            a.arrow(vx, ty, tx)

    feed("age_sex", ["c2"], xs[2] - STUB)
    feed("education", ["c3"], xs[3] - STUB)
    feed("employment", ["c4a", "c4b"], xs[4] - STUB)
    assert mid("education")[0] >= xs[2] + widths[2] - 0.01, "education must touch the Level 2 right edge"
    bottom = max(col_bottom.values()) + BOX_GAP / 2
    assert right <= A_W - 2 and bottom <= A_H - 3, (round(right, 1), round(bottom, 1))
    return right, bottom


def build(stem, **kw):
    with plt.rc_context(BC.rc()):
        fig = plt.figure(figsize=(B.W / 72, B.H / 72))
        B.draw(fig, with_a=False, letters=True)
        right, bottom = draw(fig, B.H, **kw)
        out = BC.save(fig, stem)
    print(stem, "panel A right =", round(right, 1), "bottom =", round(bottom, 1), out[0])
    return out[0]


def names_with(**over):
    n = dict(NAMES)
    n.update(over)
    return n


SUFFIX = "" if INCOME_MODE == "status" else "_income-old-label"
ALL = {
    "P14": lambda: build("F2_P14_fig2a_level2_one_column" + SUFFIX,
                         names=names_with(socio=["socioeconomic", "class"]),
                         ctx3=["| age, sex, education"], ctx4b=["if employed | age, sex"]),
    "P15": lambda: build("F2_P15_fig2a_level2_subgrid" + SUFFIX,
                         names=names_with(education=["education", "level"], civil=["civil", "status"], socio=["socioeconomic", "class"],
                                          birth=["birth", "country"], housing=["housing", "tenure"],
                                          employment=["employment", "status"]),
                         ctx3=["| age, sex,", "education"], ctx4b=["if employed |", "age, sex"], l2="grid",
                         grid_rows=[["civil", "education"], ["birth", "housing"], ["socio", "region"] if REGION_L2 else ["socio"]],
                         income_lines=None if INCOME_MODE == "current" else ["| employment", "status, age"]),
    "P16": lambda: build("F2_P16_fig2a_level2_one_line_names" + SUFFIX,
                         names=names_with(employment=["employment", "status"]),
                         ctx3=["| age, sex,", "education"], ctx4b=["if employed |", "age, sex"],
                         income_lines=None if INCOME_MODE == "current" else ["| employment", "status, age"]),
}

if __name__ == "__main__":
    for k in [a_ for a_ in sys.argv[1:] if not a_.startswith("--")] or ALL:
        ALL[k]()
