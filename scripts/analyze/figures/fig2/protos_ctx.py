"""Figure 2 round 4: panel A with the conditioning shown above the boxes, as Figure 3A does (F2_P12, F2_P13).

Baseline F2_P11 (protos_a.py): P30 style, full-width level greens, dashed Level 2 L-shape, the four lower boxes
aligned with industry sector, the age-sex feed to housing tenure and socioeconomic class through the gap between
civil status and birth country.

Conditioning per table, verified in generators/real/sweden/sample_service.py::sample_one:
  Level 1  age+sex (one joint table), region, parental structure, household size: unconditioned
  Level 2  education, civil status, birth country, housing tenure, socioeconomic class: | age, sex
           (birth country also uses the sampled born-in-Sweden flag, a deprecated attribute not shown)
  Level 3  employment status: | age, sex, education
  Level 4  employment type, industry sector: only if employed, | age, sex
           income source: | employment status (four groups), age; drawn for everyone, no sex
Every level shares one conditioning set except Level 4, where income source differs (no sex).

Run: python protos_ctx.py [P12 P13]
"""
from __future__ import annotations

import sys

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, PathPatch, Rectangle
from matplotlib.path import Path as MPath

import protos_a as PA
from protos_a import (A, ATTR, ATTR_EDGE, B, BC, BOX_GAP, CONTENT, COLUMNS, F8, F12, GAP, HEADER_H, INK,
                      LEVEL_FILL, LINE, NOTE_EDGE, PAD_V, STUB, X0, DROP, A_W, A_H, A_CORNER, col_width, tw)

CTX_FILL = "#E1E4E0"     # Figure 3A context box
SOFT = "#666666"
EMPTY = "empty"
L4_SHARED = "if employed | age, sex"
#: Income-source context. "current": Figure 2A's old wording plus the no-sex-filter note; "status": what the
#: sampler does (drawn for everyone, given employment status and age), decided by the author on 2026-10-20.
INCOME = {"current": ["if employed | age", "NOTE"], "status": ["| employment status,", "age"]}
INCOME_MODE = "current"
CTX_OF = {1: EMPTY, 2: "| age, sex", 3: "| age, sex, education", 4: L4_SHARED}


def empty_set(ax, x, y, color=SOFT):
    """Arial has no empty-set glyph: drawn, as in Figure 3A."""
    ax.add_patch(Circle((x, y), 3.2, fc="none", ec=color, lw=0.7, zorder=6))
    ax.plot([x - 4.2, x + 4.2], [y + 4.2, y - 4.2], color=color, lw=0.7, zorder=6)


def note(ax, x, y):
    nw = tw("no sex filter") + 4
    ax.add_patch(Rectangle((x, y - LINE / 2 + 0.6), nw, LINE - 1.2, fc="white", ec=NOTE_EDGE, lw=0.7, zorder=5))
    ax.text(x + nw / 2, y, "no sex filter", fontsize=F8, style="italic", ha="center", va="center", color=INK,
            zorder=6)


def draw_a_ctx(fig, H, *, mode="boxes"):
    """mode="boxes": a Figure 3A context box above each group (F2_P12).
    mode="header": the context printed in the level header tab, as Figure 3 gallery P25 (F2_P13)."""
    a = A(fig, H)
    ax = a.ax
    ax.add_patch(FancyBboxPatch((-40, -40), A_W + 40, A_H + 40, boxstyle=f"round,pad=0,rounding_size={A_CORNER}",
                                fc="white", ec="none", zorder=0))
    ax.text(1, 0.5, "A", fontsize=F12, fontweight="bold", ha="left", va="top", color="black")
    top = DROP
    widths = {k: max(col_width(v, k), (tw(CTX_OF[k]) + 5.0) if CTX_OF[k] != EMPTY else 0) for k, v in COLUMNS.items()}
    xs, x = {}, X0
    for k in range(1, 5):
        xs[k] = x
        x += widths[k] + GAP
    right = x - GAP
    hdr = HEADER_H if mode == "boxes" else HEADER_H + LINE + 1.0
    y0 = top + hdr + BOX_GAP
    CTX_H = LINE + 3.0
    items = {}      # name -> (x, y, w, h, kind)

    def attr_h(key):
        n = len(CONTENT[key][0]) + (1 if (key == "income" and mode == "header") else 0)
        return n * LINE + PAD_V

    def stack(k, seq, y):
        for kind, name, h in seq:
            if kind != "gap":
                items[name] = (xs[k], y, widths[k], h, kind)
            y += h + BOX_GAP
        return y

    seq1 = ([("ctx", "c1", CTX_H)] if mode == "boxes" else []) + [("attr", k_, attr_h(k_)) for k_ in COLUMNS[1]]
    if mode == "boxes":
        seq4 = [("ctx", "c4a", len(INCOME[INCOME_MODE]) * LINE + 3.0), ("attr", "income", attr_h("income")),
                ("gap", "g", 0.0),
                ("ctx", "c4b", CTX_H), ("attr", "emptype", attr_h("emptype")), ("attr", "industry", attr_h("industry"))]
    else:
        seq4 = [("attr", k_, attr_h(k_)) for k_ in COLUMNS[4]]
    stack(1, seq1, y0)
    stack(4, seq4, y0)
    bottom_line = items["industry"][1] + items["industry"][3]     # P11 rule: align with industry sector
    yy = y0
    if mode == "boxes":
        items["c2"] = (xs[2], yy, widths[2], CTX_H, "ctx")
        items["c3"] = (xs[3], yy, widths[3], CTX_H, "ctx")
        yy += CTX_H + BOX_GAP
    items["education"] = (xs[2], yy, widths[2], attr_h("education"), "attr")
    items["employment"] = (xs[3], yy, widths[3], attr_h("employment"), "attr")
    emp_bottom = yy + attr_h("employment")
    ROUTE_GAP = 4.5
    need = emp_bottom + 6.0 + CTX_H + BOX_GAP + attr_h("housing") + ROUTE_GAP + attr_h("socio")
    bottom_line = max(bottom_line, need)
    hs = bottom_line - attr_h("socio")
    items["socio"] = (xs[3], hs, widths[3], attr_h("socio"), "attr")
    items["birth"] = (xs[2], hs, widths[2], attr_h("birth"), "attr")
    hh = hs - ROUTE_GAP - attr_h("housing")
    items["housing"] = (xs[3], hh, widths[3], attr_h("housing"), "attr")
    items["civil"] = (xs[2], hh, widths[2], attr_h("civil"), "attr")
    items["cb"] = (xs[3], hh - BOX_GAP - CTX_H, widths[3], CTX_H, "ctx")      # the bridge's own context
    assert items["civil"][1] >= items["education"][1] + attr_h("education") + BOX_GAP
    ctx_text = {"c1": CTX_OF[1], "c2": CTX_OF[2], "c3": CTX_OF[3], "c4a": INCOME[INCOME_MODE], "c4b": L4_SHARED,
                "cb": "| age, sex"}
    for name, (bx, by, bw, bh, kind) in items.items():
        if kind == "ctx":
            a.box(bx, by, bw, bh, CTX_FILL, ATTR_EDGE, lw=0.5)
            t = ctx_text[name]
            if t == EMPTY:
                empty_set(ax, bx + bw / 2, by + bh / 2)
            else:
                for j, line_ in enumerate([t] if isinstance(t, str) else t):
                    if line_ == "NOTE":
                        note(ax, bx + 3, by + 1.5 + LINE / 2 + j * LINE)
                    else:
                        a.T(bx + 3, by + 1.5 + LINE / 2 + j * LINE, line_, ha="left", zorder=5)
        else:
            a.box(bx, by, bw, bh, ATTR, ATTR_EDGE)
            for j, nme in enumerate(CONTENT[name][0]):
                a.T(bx + bw / 2, by + PAD_V / 2 + LINE / 2 + j * LINE, nme, bold=True, zorder=5)
            if name == "income" and mode == "header":
                note(ax, bx + bw / 2 - (tw("no sex filter") + 4) / 2, by + PAD_V / 2 + 1.5 * LINE)
    for k in range(1, 5):
        a.box(xs[k], top, widths[k], hdr, LEVEL_FILL[k], z=2)
        a.T(xs[k] + widths[k] / 2, top + 5.6, f"Level {k}", bold=True, zorder=3)
        if mode == "header":
            cy = top + HEADER_H + LINE / 2 - 0.5
            if CTX_OF[k] == EMPTY:
                empty_set(ax, xs[k] + widths[k] / 2, cy, color=INK)
            else:
                a.T(xs[k] + 3, cy, CTX_OF[k], ha="left", zorder=3)
    yb0 = top + hdr
    col_bottom = {k: max(v[1] + v[3] for v in items.values() if v[0] == xs[k]) + BOX_GAP for k in xs}
    for k in (1, 4):
        ax.add_patch(Rectangle((xs[k], yb0), widths[k], col_bottom[k] - yb0 - BOX_GAP, fc=LEVEL_FILL[k], ec="none",
                               zorder=1))
    ax.add_patch(Rectangle((xs[3], yb0), widths[3], emp_bottom + 2.0 - yb0, fc=LEVEL_FILL[3], ec="none", zorder=1))
    h0 = items["cb"][1] - 2.0
    y2b = bottom_line + BOX_GAP / 2
    x2l, x2r, x3r = xs[2], xs[2] + widths[2], xs[3] + widths[3]
    pts = [(x2l, yb0), (x2r, yb0), (x2r, h0), (x3r, h0), (x3r, y2b), (x2l, y2b), (x2l, yb0)]
    codes = [MPath.MOVETO] + [MPath.LINETO] * (len(pts) - 2) + [MPath.CLOSEPOLY]
    ax.add_patch(PathPatch(MPath(pts, codes), fc=LEVEL_FILL[2], ec="none", zorder=1))
    ax.add_patch(PathPatch(MPath(pts, codes), fc="none", ec="#74A44D", lw=0.6, zorder=1.5,
                           linestyle=(0, (2.0, 1.2))))

    def mid(n):
        bx, by, bw, bh, _ = items[n]
        return bx, bx + bw, by + bh / 2

    def target(n):
        if n in items and items[n][4] == "ctx":
            return items[n][0], items[n][1] + 1.5 + LINE / 2
        k = {"c2": 2, "c3": 3, "c4": 4}[n]
        return xs[k], top + HEADER_H + LINE / 2 - 0.5      # the header's context line (P13)

    def feed(src, tgts, vx):
        _, xr, ys = mid(src)
        tp = [target(t) for t in tgts]
        a.line([xr, vx], [ys, ys])
        a.line([vx, vx], [min([ys] + [p[1] for p in tp]), max([ys] + [p[1] for p in tp])])
        for tx, ty in tp:
            a.arrow(vx, ty, tx)

    v1, v2, v3 = xs[2] - STUB, xs[3] - STUB, xs[4] - STUB
    feed("age_sex", ["c2"], v1)
    ycross = (items["civil"][1] + items["civil"][3] + items["birth"][1]) / 2
    _, xr, ys = mid("age_sex")
    a.line([v1, v1], [ys, ycross])
    a.line([v1, v2], [ycross, ycross])
    bx, by = target("cb")
    a.line([v2, v2], [by, ycross])
    a.arrow(v2, by, bx)
    feed("education", ["c3"], v2)
    feed("employment", ["c4a", "c4b"] if mode == "boxes" else ["c4"], v3)
    bottom = max(col_bottom.values())
    assert right <= A_W - 2 and bottom <= A_H - 3, (right, bottom)
    return right, bottom


def build_ctx(stem, **kw):
    with plt.rc_context(BC.rc()):
        fig = plt.figure(figsize=(B.W / 72, B.H / 72))
        B.draw(fig, with_a=False, letters=True)
        right, bottom = draw_a_ctx(fig, B.H, **kw)
        out = BC.save(fig, stem)
    print(stem, "panel A right =", round(right, 1), "bottom =", round(bottom, 1), out[0])
    return out[0]


def _p12a():
    global INCOME_MODE
    INCOME_MODE = "status"
    try:
        return build_ctx("F2_P12a_fig2a_context_boxes_income_status", mode="boxes")
    finally:
        INCOME_MODE = "current"


ALL = {"P12": lambda: build_ctx("F2_P12_fig2a_context_boxes", mode="boxes"),
       "P12a": _p12a,
       "P13": lambda: build_ctx("F2_P13_fig2a_context_in_header", mode="header")}

if __name__ == "__main__":
    for k in sys.argv[1:] or ALL:
        ALL[k]()
