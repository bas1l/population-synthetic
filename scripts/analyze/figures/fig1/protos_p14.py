"""Figure 1, P14: P12 with P11's 4.1, an explicit LLM x strategies row, redrawn 4.4 icons and a
step-word strategy key. Run: python protos_p14.py [P14 P14a]."""
from __future__ import annotations

import sys

from matplotlib.patches import Circle, Ellipse, Polygon, Rectangle

import common as c
from common import T, arrow, line, table_stack, llm_chip, die, fmt, REF, INK, SCHEMA, F8, F9
from protos_p04v import WIDTHS, panels, card14, brace_label, mapping_panel, tw
from population_synthetic.analysis.utils.labels import figure_term, METHOD_KEY_SEPARATOR
from population_synthetic.analysis.utils.style import house_style

# Strategy display names: none exist in the article or in config (labels.py resolves only the
# code-like family labels of _families.yaml). The key uses the step words of Figure 3B
# ("+ context", "list values", "values probability", "choose a value", "random"), shortened.
STEP_KEY = ["choose a value", "context, choose a value", "context, list values, choose",
            "context, list values, probabilities, choose", "context, list values, probabilities, random draw"]
ICON_LW = 1.0
ICON_FILL = "#BDBDBD"


def step_key(ax, x, y, width, size=F8):
    title = figure_term("strategy_key_title") + ":"
    T(ax, x, y, title, size=size, weight="bold", ha="left")
    x_start = x + tw(title, size, "bold") + 6
    cx, cy = x_start, y
    for i, s in enumerate(c.STRATEGIES):
        letter, rest = c.LETTERS[s], METHOD_KEY_SEPARATOR + STEP_KEY[i]
        wl = tw(letter, size, "bold") + tw(rest, size) + 10
        if cx + wl > x + width:
            cx, cy = x_start, cy - 11
        T(ax, cx, cy, letter, size=size, color=c.STRAT_COLOR[s], weight="bold", ha="left")
        T(ax, cx + tw(letter, size, "bold"), cy, rest, size=size, ha="left")
        cx += wl


def icon_population(ax, x, y, w=26, h=18):
    """Population level: a reference distribution (outline) over a synthetic one (grey fill)."""
    ref = [0.45, 0.95, 0.7, 0.35, 0.2]
    syn = [0.25, 1.0, 0.95, 0.15, 0.05]
    bw = w / len(ref)
    x0, y0 = x - w / 2, y - h / 2
    for i in range(len(ref)):
        ax.add_patch(Rectangle((x0 + i * bw + bw * 0.1, y0), bw * 0.8, syn[i] * h, fc=ICON_FILL, ec="none", zorder=7))
        ax.add_patch(Rectangle((x0 + i * bw + bw * 0.1, y0), bw * 0.8, ref[i] * h, fc="none", ec=INK, lw=ICON_LW, zorder=7.1))
    line(ax, [x0 - 1, x0 + w + 1], [y0, y0], color=INK, lw=ICON_LW, z=7.2)


def icon_individual(ax, x, y):
    """Individual level: one individual card (the 14-row glyph) under a magnifying lens with a check."""
    card14(ax, x - 14, y - 12, 15, 24, "ref", color=INK, z=7)
    lx, ly, r = x + 3, y, 6.5
    ax.add_patch(Circle((lx, ly), r, fc="white", ec=INK, lw=ICON_LW * 1.4, zorder=8))
    line(ax, [lx - 3, lx - 0.8, lx + 3.2], [ly, ly - 2.4, ly + 2.6], color=INK, lw=ICON_LW * 1.3, z=8.2)
    line(ax, [lx + r * 0.72, lx + r * 0.72 + 5.5], [ly - r * 0.72, ly - r * 0.72 - 5.5], color=INK, lw=2.4, z=8.1)


def icon_operational(ax, x, y):
    """Operational performance: a stack of coins (cost) beside a funnel keeping 1 of 4 (retention)."""
    cx = x - 7
    for k in range(3):
        ax.add_patch(Ellipse((cx, y - 7 + k * 4.0), 13, 5, fc="white", ec=INK, lw=ICON_LW, zorder=7 + k * 0.1))
    T(ax, cx, y + 1.0, "$", size=F8, weight="bold", zorder=9)
    fx = x + 10
    ax.add_patch(Polygon([(fx - 6, y + 4), (fx + 6, y + 4), (fx + 1.3, y - 2), (fx + 1.3, y - 7),
                          (fx - 1.3, y - 7), (fx - 1.3, y - 2)], closed=True, fc="white", ec=INK, lw=ICON_LW, zorder=7))
    for dx in (-4.5, -1.5, 1.5, 4.5):
        ax.add_patch(Circle((fx + dx, y + 7.5), 1.1, fc=INK, ec="none", zorder=7))
    ax.add_patch(Circle((fx, y - 10), 1.1, fc=INK, ec="none", zorder=7))


def comparison_panel_v2(ax, x0, ys):
    labels = ["Population level", "Individual level", "Operational\nperformance"]
    for yy, lab, draw in zip(ys, labels, (icon_population, icon_individual, icon_operational)):
        draw(ax, x0 + 19, yy)
        T(ax, x0 + 38, yy, lab, size=F8, ha="left")


@house_style
def p14(mapping_text=("Both onto the same", f"{c.N_ATTRIBUTES} attribute", "categories"), name="P14_p12_final"):
    H = 228
    KEY = 26
    cv, ax = c.canvas(H)
    xs = panels(ax, H, y0=KEY + 2)
    top = H - 30
    yb = KEY + 2
    card_y, card_h = yb + 34, 46
    # 4.1, as P11 -----------------------------------------------------------------------
    x0, w = xs[0], WIDTHS[0]
    table_stack(ax, x0 + 7, top - 22, 22, 17, n=3)
    T(ax, x0 + 38, top - 6, "Statistics Sweden", size=F8, color=REF, ha="left", weight="bold")
    T(ax, x0 + 38, top - 16, "official statistics", size=F8, color=REF, ha="left")
    T(ax, x0 + 38, top - 26, "(SCB), 13 tables", size=F8, color=REF, ha="left")
    arrow(ax, x0 + 20, top - 27, x0 + 20, top - 42, color=REF, head=4)
    die(ax, x0 + 20, top - 50, 13)
    T(ax, x0 + 32, top - 50, "conditional sampling", size=F8, color=REF, ha="left")
    arrow(ax, x0 + 20, top - 58, x0 + 20, card_y + card_h + 7, color=REF, head=4)
    y0_, y1_, _ = card14(ax, x0 + 8, card_y, 24, card_h, "ref", stack=2)
    brace_label(ax, x0 + 38, y0_, y1_, "", color=REF)
    T(ax, x0 + 45, (y0_ + y1_) / 2 + 5, "1 individual =", size=F8, color=REF, ha="left")
    T(ax, x0 + 45, (y0_ + y1_) / 2 - 5, f"{c.N_ATTRIBUTES} attributes", size=F8, color=REF, ha="left")
    T(ax, x0 + w / 2, yb + 19, "1 reference population", size=F9, color=REF, weight="bold")
    T(ax, x0 + w / 2, yb + 8, f"of {fmt(c.N_REFERENCE)} individuals", size=F8, color=REF)
    # 4.2 --------------------------------------------------------------------------------
    x0, w = xs[1], WIDTHS[1]
    llm_chip(ax, x0 + 20, top - 10, 24)
    T(ax, x0 + 20, top - 29, "13 LLMs", size=F8, weight="bold")
    T(ax, x0 + 43, top - 10, "×", size=12, weight="bold")
    for i, s_ in enumerate(c.STRATEGIES):
        xx = x0 + 58 + i * 12
        T(ax, xx, top - 1, c.LETTERS[s_], size=F9, color=c.STRAT_COLOR[s_], weight="bold")
        line(ax, [xx, xx], [top - 8, top - 20], color=c.STRAT_COLOR[s_], lw=1.6)
    T(ax, x0 + 82, top - 29, f"{len(c.STRATEGIES)} strategies", size=F8, weight="bold")
    arrow(ax, x0 + 20, top - 36, x0 + 20, card_y + card_h + 7, color=INK, head=4)
    T(ax, x0 + 27, top - 50, "one attribute at a time", size=F8, ha="left")
    y0_, y1_, _ = card14(ax, x0 + 8, card_y, 24, card_h, "llm", stack=2)
    brace_label(ax, x0 + 38, y0_, y1_, "")
    T(ax, x0 + 45, (y0_ + y1_) / 2 + 5, "1 individual =", size=F8, ha="left")
    T(ax, x0 + 45, (y0_ + y1_) / 2 - 5, f"{c.N_ATTRIBUTES} attributes", size=F8, ha="left")
    T(ax, x0 + w / 2, yb + 19, f"{c.N_KEPT} populations", size=F9, weight="bold")
    T(ax, x0 + w / 2, yb + 8, f"of {c.N_PER_COMBO[0]} individuals each", size=F8)
    # 4.3 --------------------------------------------------------------------------------
    x0, w = xs[2], WIDTHS[2]
    T(ax, x0 + 6, top - 2, mapping_text[0], size=F8, ha="left", color=SCHEMA, weight="bold")
    for k, t in enumerate(mapping_text[1:], start=1):
        T(ax, x0 + 6, top - 2 - 10 * k, t, size=F8, ha="left", color=SCHEMA, weight="bold")
    mapping_panel(ax, x0, w, yb + 8, top - 36)
    # 4.4 --------------------------------------------------------------------------------
    comparison_panel_v2(ax, xs[3], [top - 22, (top + yb) / 2 - 4, yb + 28])
    step_key(ax, 4, KEY - 8, 448)
    return c.save(cv.figure, name)


def p14a():
    return p14(mapping_text=("Both onto the same", f"{c.N_ATTRIBUTES} attributes", "and categories"),
               name="P14a_p12_final_alt_wording")


ALL = {"P14": p14, "P14a": p14a}

if __name__ == "__main__":
    for k in (sys.argv[1:] or ALL):
        print(k, ALL[k]())
