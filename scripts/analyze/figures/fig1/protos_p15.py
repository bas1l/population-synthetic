"""Figure 1, P15: P14 refined (one title / header / body text style, no key strip, colour-only
strategy marks, one operational-performance symbol, two-line 4.3 header). Run: python protos_p15.py"""
from __future__ import annotations

import numpy as np
from matplotlib.patches import Arc, Circle, Polygon

import common as c
from common import arrow, box, line, table_stack, llm_chip, die, badge, fmt, REF, INK, F8, F10
from protos_p04v import card14, brace_label, mapping_panel
from protos_p14 import icon_population, icon_individual, ICON_LW
from population_synthetic.analysis.utils.style import house_style

WIDTHS = [116, 114, 98, 102]
GAP = 8
SECS = ["4.1", "4.2", "4.3", "4.4"]
TITLES = ["Reference", "Synthetic", "Mapping", "Comparison"]

# The three text styles, defined once and used for every string on the canvas.
STYLE = {
    "title": dict(fontsize=F10, fontweight="bold", color=INK),   # panel titles
    "header": dict(fontsize=F8, fontweight="bold", color=INK),   # header lines and the first count line
    "body": dict(fontsize=F8, fontweight="normal", color=INK),   # labels, second count line, analysis names
}


def S(ax, x, y, s, style, ha="left", va="center", **kw):
    return ax.text(x, y, s, ha=ha, va=va, **STYLE[style], **kw)


def panels(ax, H, y0=2):
    top = H - 2
    xs, x = [], 1
    for k, w in enumerate(WIDTHS):
        box(ax, x, y0, w, top - y0, ec=c.GRID_RULE, fc="white", lw=0.8, r=5, z=1)
        badge(ax, x + 12, top - 12, SECS[k], r=9)
        S(ax, x + 25, top - 12, TITLES[k], "title")
        xs.append(x)
        if k < 3:
            ym = (y0 + top) / 2
            arrow(ax, x + w + 0.5, ym, x + w + GAP - 0.5, ym, color=INK, lw=1.2, head=5)
        x += w + GAP
    return xs


def icon_gauge(ax, x, y, r=12):
    """Operational performance: one gauge (a measured level of performance), line art."""
    cy = y - r * 0.35
    ax.add_patch(Arc((x, cy), 2 * r, 2 * r, theta1=0, theta2=180, ec=INK, lw=ICON_LW * 1.4, zorder=7))
    for ang in np.linspace(0, 180, 7):
        a = np.radians(ang)
        line(ax, [x + r * 0.78 * np.cos(a), x + r * np.cos(a)], [cy + r * 0.78 * np.sin(a), cy + r * np.sin(a)],
             color=INK, lw=ICON_LW, z=7)
    line(ax, [x - r - 1, x + r + 1], [cy, cy], color=INK, lw=ICON_LW, z=7)
    a = np.radians(52)
    ax.add_patch(Polygon([(x + r * 0.72 * np.cos(a), cy + r * 0.72 * np.sin(a)),
                          (x - 1.3 * np.sin(a), cy + 1.3 * np.cos(a)), (x + 1.3 * np.sin(a), cy - 1.3 * np.cos(a))],
                         closed=True, fc=INK, ec="none", zorder=8))
    ax.add_patch(Circle((x, cy), 2.0, fc=INK, ec="none", zorder=8.1))


@house_style
def p15(v16=False):
    H = 202
    cv, ax = c.canvas(H)
    xs = panels(ax, H)
    top = H - 30
    yb = 2
    card_y, card_h = yb + 34, 46
    # 4.1 ---------------------------------------------------------------------------------
    x0, w = xs[0], WIDTHS[0]
    table_stack(ax, x0 + 7, top - 22, 22, 17, n=3)
    S(ax, x0 + 38, top - 6, "Statistics Sweden", "header")
    S(ax, x0 + 38, top - 16, "official statistics", "header")
    S(ax, x0 + 38, top - 26, "(SCB), 13 tables", "header")
    arrow(ax, x0 + 20, top - 27, x0 + 20, top - 42, color=REF, head=4)
    die(ax, x0 + 20, top - 50, 13)
    S(ax, x0 + 32, top - 50, "conditional sampling", "body")
    arrow(ax, x0 + 20, top - 58, x0 + 20, card_y + card_h + 7, color=REF, head=4)
    y0_, y1_, _ = card14(ax, x0 + 8, card_y, 24, card_h, "ref", stack=2)
    brace_label(ax, x0 + 38, y0_, y1_, "", color=REF)
    S(ax, x0 + 45, (y0_ + y1_) / 2 + 5, "1 individual =", "body")
    S(ax, x0 + 45, (y0_ + y1_) / 2 - 5, f"{c.N_ATTRIBUTES} attributes", "body")
    S(ax, x0 + w / 2, yb + 19, "1 reference population", "header", ha="center")
    S(ax, x0 + w / 2, yb + 9, f"of {fmt(c.N_REFERENCE)} individuals", "body", ha="center")
    # 4.2 ---------------------------------------------------------------------------------
    x0, w = xs[1], WIDTHS[1]
    llm_chip(ax, x0 + 20, top - 12, 24, label="LLM", size=F8)
    S(ax, x0 + 20, top - 31, "13 LLMs", "header", ha="center")
    for sgn in (1, -1):  # the multiplication sign drawn as a glyph, at the strategy-mark stroke weight
        line(ax, [x0 + 39.5, x0 + 46.5], [top - 12 - 3.5 * sgn, top - 12 + 3.5 * sgn], color=INK, lw=1.6)
    for i, s_ in enumerate(c.STRATEGIES):  # colour-only marks: no letters, so no key is needed
        xx = x0 + 60 + i * 9
        line(ax, [xx, xx], [top - 2, top - 22], color=c.STRAT_COLOR[s_], lw=2.2, cap="butt")
    S(ax, x0 + 78, top - 31, f"{len(c.STRATEGIES)} strategies", "header", ha="center")
    if v16:
        # one bracket spanning the chip and the five bars: the combination generates the individual
        yb_ = top - 40
        xl, xr = x0 + 7, x0 + 99
        xc = (xl + xr) / 2
        line(ax, [xl, xl, xr, xr], [yb_ + 4, yb_, yb_, yb_ + 4], color=INK, lw=1.0, cap="butt")
        line(ax, [xc, xc, x0 + 20, x0 + 20], [yb_, top - 54, top - 54, top - 56], color=INK, lw=1.0)
        arrow(ax, x0 + 20, top - 56, x0 + 20, card_y + card_h + 7, color=INK, head=4)
    else:
        arrow(ax, x0 + 20, top - 38, x0 + 20, card_y + card_h + 7, color=INK, head=4)
        S(ax, x0 + 27, top - 50, "one attribute at a time", "body")
    y0_, y1_, _ = card14(ax, x0 + 8, card_y, 24, card_h, "llm", stack=2)
    brace_label(ax, x0 + 38, y0_, y1_, "")
    S(ax, x0 + 45, (y0_ + y1_) / 2 + 5, "1 individual =", "body")
    S(ax, x0 + 45, (y0_ + y1_) / 2 - 5, f"{c.N_ATTRIBUTES} attributes", "body")
    S(ax, x0 + w / 2, yb + 19, f"{c.N_KEPT} populations", "header", ha="center")
    S(ax, x0 + w / 2, yb + 9, f"of {c.N_PER_COMBO[0]} individuals each", "body", ha="center")
    # 4.3 ---------------------------------------------------------------------------------
    x0, w = xs[2], WIDTHS[2]
    S(ax, x0 + 6, top - 6, "Map onto the same" if v16 else "Both onto the same", "header")
    S(ax, x0 + 6, top - 16, f"{c.N_ATTRIBUTES} attribute categories", "header")
    # mapping_panel prints "table label" / "free text" through common.T at 8 pt regular in the
    # reference grey; those two are re-set to the body style just below.
    mapping_panel(ax, x0, w, yb + 8, top - 36)
    for t in ax.texts:
        if t.get_text() in ("table label", "free text"):
            t.set_color(STYLE["body"]["color"])
            t.set_fontweight(STYLE["body"]["fontweight"])
    # 4.4 ---------------------------------------------------------------------------------
    x0 = xs[3]
    ys = [top - 22, (top + yb) / 2 - 4, yb + 28]
    icon_population(ax, x0 + 19, ys[0])
    icon_individual(ax, x0 + 19, ys[1])
    icon_gauge(ax, x0 + 19, ys[2] + 3)
    for yy, lab in zip(ys, ["Population level", "Individual level", "Operational\nperformance"]):
        S(ax, x0 + 38, yy, lab, "body")
    return c.save(cv.figure, "P16_p15_bracket" if v16 else "P15_p14_refined")


if __name__ == "__main__":
    import sys
    if "P16" in sys.argv[1:]:
        print("P16", p15(v16=True))
    else:
        print("P15", p15())
