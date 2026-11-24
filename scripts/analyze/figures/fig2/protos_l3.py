"""Figure 2 panel A for the reference-v3 reference (2026-11-23): three levels instead of four.

Why: the redrawn reference (worktree reference-v3-corrections, generators/real/sweden/sample_service.py::sample_one,
status-education merge OFF) conditions as follows.
  Level 1  age+sex (one joint table), parental structure, household size: unconditioned
  Level 2  | age, sex : education, civil status, birth country, housing tenure, socioeconomic class,
           region (NEW: region table filtered on age group and sex), employment status (no longer | education)
  Level 3  employment type, industry sector: if employed | age, sex; income source: | employment status, age
Education is no longer a parent of anything, so the old Level 3 (employment status | age, sex, education) disappears
and employment status moves into Level 2. Same grammar as protos_l2 P14/P15 (level tabs, grey context boxes, elbow
arrows, level greens); Level 2 is a two-wide sub-grid (as P15) because seven boxes in one column would run into the
panel B titles. Names, fonts, paddings, widths are those of protos_a.
"""
from __future__ import annotations

from matplotlib.patches import FancyBboxPatch, Rectangle

from protos_a import (A, ATTR, ATTR_EDGE, B, BOX_GAP, F12, GAP, HEADER_H, LEVEL_FILL, LINE, PAD_V, STUB, X0, DROP,
                      A_W, A_H, A_CORNER, tw)
from protos_ctx import CTX_FILL, empty_set
import protos_l2 as _PL  # publish_fig2 swaps _PL.A for the canvas-sized overlay class; use it at call time

NAMES = {
    "age_sex": ["age, sex"], "parental": ["parental", "structure"], "household": ["household", "size"],
    "region": ["region"], "education": ["education", "level"], "civil": ["civil", "status"],
    "birth": ["birth", "country"], "housing": ["housing", "tenure"], "socio": ["socioeconomic", "class"],
    "employment": ["employment status"], "income": ["income source"], "emptype": ["employment type"],
    "industry": ["industry sector"],
}
GRID_ROWS = [["civil", "education"], ["birth", "housing"], ["socio", "region"], ["employment"]]
CTX_H1 = LINE + 3.0
CTX3A = ["| employment status,", "age"]
CTX3B = ["if employed | age, sex"]


def ctx_h(lines):
    return len(lines) * LINE + 3.0


def attr_h(lines):
    return len(lines) * LINE + PAD_V


def draw(fig, H, **_unused):
    names = NAMES
    a = _PL.A(fig, H)
    ax = a.ax
    ax.add_patch(FancyBboxPatch((-40, -40), A_W + 40, A_H + 40, boxstyle=f"round,pad=0,rounding_size={A_CORNER}",
                                fc="white", ec="none", zorder=0))
    ax.text(1, 0.5, "a", fontsize=F12, fontweight="bold", ha="left", va="top", color="black")
    top = DROP
    y0 = top + HEADER_H + BOX_GAP

    def bw(keys):
        return max(tw(p, True) for k in keys for p in names[k]) + 3.0

    def cw(lines):
        return max(tw(p) for p in lines) + 5.0

    paired = [k_ for row in GRID_ROWS if len(row) == 2 for k_ in row]
    spanning = [row[0] for row in GRID_ROWS if len(row) == 1]
    sub = bw(paired)
    w1 = max(bw(["age_sex", "parental", "household"]), tw("Level 1", True) + 3)
    w2 = max(2 * sub + BOX_GAP, cw(["| age, sex"]), bw(spanning))
    sub = (w2 - BOX_GAP) / 2
    w3 = max(bw(["income", "emptype", "industry"]), cw(CTX3A), cw(CTX3B))
    widths = {1: w1, 2: w2, 3: w3}
    xs, x = {}, X0
    for k in range(1, 4):
        xs[k] = x
        x += widths[k] + GAP
    right = x - GAP
    items = {}

    def place(name, kind, k, y, h, xx=None, ww=None):
        items[name] = (xs[k] if xx is None else xx, y, widths[k] if ww is None else ww, h, kind)
        return y + h + BOX_GAP

    y = place("c1", "ctx", 1, y0, CTX_H1)
    for k_ in ("age_sex", "parental", "household"):
        y = place(k_, "attr", 1, y, attr_h(names[k_]))
    y = place("c2", "ctx", 2, y0, CTX_H1)
    for row in GRID_ROWS:
        hrow = max(attr_h(names[k_]) for k_ in row)
        if len(row) == 1:
            place(row[0], "attr", 2, y, hrow)
        else:
            for j, k_ in enumerate(row):
                place(k_, "attr", 2, y, hrow, xx=xs[2] + j * (sub + BOX_GAP), ww=sub)
        y += hrow + BOX_GAP
    y = place("c3a", "ctx", 3, y0, ctx_h(CTX3A))
    y = place("income", "attr", 3, y, attr_h(names["income"]))
    y = place("c3b", "ctx", 3, y, ctx_h(CTX3B))
    for k_ in ("emptype", "industry"):
        y = place(k_, "attr", 3, y, attr_h(names[k_]))
    ctx_lines = {"c1": None, "c2": ["| age, sex"], "c3a": CTX3A, "c3b": CTX3B}
    for name, (bx, by, bw_, bh, kind) in items.items():
        if kind == "ctx":
            a.box(bx, by, bw_, bh, CTX_FILL, ATTR_EDGE, lw=0.5)
            lines = ctx_lines[name]
            if lines is None:
                empty_set(ax, bx + bw_ / 2, by + bh / 2)
                continue
            for j, t in enumerate(lines):
                a.T(bx + 3, by + 1.5 + LINE / 2 + j * LINE, t, ha="left", zorder=5)
        else:
            a.box(bx, by, bw_, bh, ATTR, ATTR_EDGE)
            nl = names[name]
            y_first = by + bh / 2 - (len(nl) - 1) * LINE / 2
            for j, t in enumerate(nl):
                a.T(bx + bw_ / 2, y_first + j * LINE, t, bold=True, zorder=5)
    for k in range(1, 4):
        a.box(xs[k], top, widths[k], HEADER_H, LEVEL_FILL[k], z=2)
        a.T(xs[k] + widths[k] / 2, top + 5.6, f"Level {k}", bold=True, zorder=3)
    yb0 = top + HEADER_H
    col_bottom = {}
    for k in range(1, 4):
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
    feed("employment", ["c3a", "c3b"], xs[3] - STUB)
    assert mid("employment")[0] >= xs[2] + widths[2] - 0.01, "employment status must touch the Level 2 right edge"
    bottom = max(col_bottom.values()) + BOX_GAP / 2
    assert right <= A_W - 2 and bottom <= A_H - 3, (round(right, 1), round(bottom, 1))
    print("panel A (3 levels): right", round(right, 1), "bottom", round(bottom, 1))
    return right, bottom
