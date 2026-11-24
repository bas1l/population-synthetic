"""Figure 2 round 2: panel A redrawn in vector in Figure 3A's P30 visual language (F2_P09, F2_P10).

Panel B is the published one, drawn by the published builder
(04_Figures/swedish_02/manuscript_2026-10-04/notes/builders_2026-10-20/fig2/fig2.py, draw(with_a=False)) on the
same 456 x 400.248 pt canvas, so only panel A differs. Panel A keeps Figure 2A's content: four levels, the 13
table boxes in the same columns (housing tenure and socioeconomic class are Level 2 attributes drawn under the
Level 3 column, joined to Level 2 by the Level 2 green), the same conditioning text and arrows, and the
"no sex filter" note with its #620011 outline.

P30 style (figure3_gallery_2026-10-20/code/protos9.py + protos10.py): 11 pt level header tab in the level
green with a bold 8 pt "Level k"; attribute boxes #BDC9D8 / #2C5633, lw 0.7, corner 2.5, line pitch 8.9 pt,
2.5 pt padding, 1.5 pt between boxes; bold 8 pt names; level-green band inset 3 pt behind each column; elbow
arrows lw 0.6, head 2.8, vertical run in the column gap, 4.2 pt stub into the target; column gap 5.8 pt;
panel letter 12 pt bold at the top-left with the panel 9 pt below.

Run: python protos_a.py [P09 P10]   (PNG only, written by the published builder's own save at 600 dpi)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

GALLERY = Path(__file__).resolve().parent
BUILDER = GALLERY  # ref-v3 copy: use this folder's common.py / fig2.py, not the original builder folder
os.environ["FIG_OUT_DIR"] = str(GALLERY)
os.environ["FIG_SUFFIXES"] = "png"
sys.path.insert(0, str(BUILDER))

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, PathPatch, Rectangle  # noqa: E402
from matplotlib.path import Path as MPath  # noqa: E402

import common as BC  # noqa: E402  (the builder's common)
import fig2 as B  # noqa: E402
from population_synthetic.analysis.utils import style  # noqa: E402

# ---- P30 constants
LEVEL_FILL = {1: "#EEFFE2", 2: "#D2EAC1", 3: "#A5D286", 4: "#74A44D"}
ATTR, ATTR_EDGE = "#BDC9D8", "#2C5633"
NOTE_EDGE = "#620011"
INK = "#222222"
F8, F12 = 8.0, 12.0
LINE = 8.9
PAD_V = 2.5
BOX_GAP = 1.5
HEADER_H = 11.0
GAP = 5.8
STUB = 4.2
HEAD = 2.8
LW = 0.6
BOX_LW = 0.7
R = 2.5
X0 = 2.0
DROP = 9.0
# ---- Figure 2 geometry: panel A's white area in the published figure (measured on fig2.png)
#: ref-v3: the three-level panel A (protos_l3.py, REFV3_PANEL_A=L3, the default) has a taller Level 2 sub-grid (four rows),
#: so the panel is 117.5 pt high instead of 111.4; its ink ends at 112.5 pt, 6 pt above the cap tops of the panel B
#: titles "Education" / "Employment" (y = 118.5 pt). REFV3_PANEL_A=P14 restores the staged height.
A_W, A_H, A_CORNER = 294.4, (117.5 if os.environ.get("REFV3_PANEL_A", "L3") == "L3" else 111.4), 17.0

# Figure 2A content, exactly: (name lines, conditioning line or None)
CONTENT = {
    "age_sex": (["age, sex"], None),
    "parental": (["parental", "structure"], None),
    "household": (["household", "size"], None),
    "region": (["region"], None),
    "education": (["education level"], "| age, sex"),
    "civil": (["civil status"], "| age, sex"),
    "birth": (["birth country"], "| age, sex"),
    "employment": (["employment status"], "| age, sex, education"),
    "housing": (["housing tenure"], "| age, sex"),
    "socio": (["socioeconomic class"], "| age, sex"),
    "income": (["income source"], "if employed | age"),
    "emptype": (["employment type"], "if employed | age, sex"),
    "industry": (["industry sector"], "if employed | age, sex"),
}
COLUMNS = {1: ["age_sex", "parental", "household", "region"],
           2: ["education", "civil", "birth"],
           3: ["employment", "housing", "socio"],
           4: ["income", "emptype", "industry"]}
LEVEL2_UNDER_3 = ["housing", "socio"]   # Level 2 attributes drawn in the Level 3 column


def tw(s, bold=False):
    return style.text_width_inches(s, fontsize=F8, weight="bold" if bold else None) * 72


class A:
    """Panel A in top-down point coordinates on an overlay axes."""

    def __init__(self, fig, H):
        self.ax = fig.add_axes((0, 0, 1, 1), zorder=1)
        self.ax.set_xlim(0, 456.0)
        self.ax.set_ylim(H, 0)
        self.ax.set_axis_off()
        self.ax.patch.set_visible(False)

    def T(self, x, y, s, bold=False, ha="center", **kw):
        assert "_" not in s
        kw.setdefault("color", INK)
        return self.ax.text(x, y, s, fontsize=F8, fontweight="bold" if bold else "normal", ha=ha, va="center", **kw)

    def box(self, x, y, w, h, fc, ec="none", lw=BOX_LW, r=R, z=2):
        self.ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}", fc=fc, ec=ec,
                                         lw=lw, zorder=z))

    def line(self, xs, ys, z=4):
        self.ax.plot(xs, ys, color=INK, lw=LW, solid_capstyle="butt", zorder=z)

    def arrow(self, x0, y, x1):
        self.ax.add_patch(FancyArrowPatch((x0, y), (x1, y), arrowstyle=f"-|>,head_length={HEAD * 0.8},"
                                          f"head_width={HEAD * 0.45}", color=INK, lw=LW, zorder=4,
                                          shrinkA=0, shrinkB=0, mutation_scale=1))


def box_height(key):
    names, cond = CONTENT[key]
    n = len(names) + (1 if cond else 0) + (1 if key == "income" else 0)
    return n * LINE + PAD_V


def col_width(keys, level):
    bold = [tw(f"Level {level}", True)] + [tw(n, True) for k in keys for n in CONTENT[k][0]]
    plain = [tw(CONTENT[k][1]) for k in keys if CONTENT[k][1]]
    return max(max(bold) + 3.0, max(plain + [0]) + 5.0)     # P30's col_widths_bold padding


def draw_a(fig, H, *, variant="P09"):
    a = A(fig, H)
    ax = a.ax
    # white panel-A area over the pink ground, as in the published figure
    ax.add_patch(FancyBboxPatch((-40, -40), A_W + 40, A_H + 40, boxstyle=f"round,pad=0,rounding_size={A_CORNER}",
                                fc="white", ec="none", zorder=0))
    ax.text(1, 0.5, "A", fontsize=F12, fontweight="bold", ha="left", va="top", color="black")  # P30: top-left
    top = DROP
    widths = {k: col_width(v, k) for k, v in COLUMNS.items()}
    xs = {}
    x = X0
    for k in range(1, 5):
        xs[k] = x
        x += widths[k] + GAP
    right = x - GAP
    assert right <= A_W - 2, right
    pos = {}
    col_bottom = {}
    l3_split = None
    for k in range(1, 5):
        xk, w = xs[k], widths[k]
        y = top + HEADER_H + BOX_GAP
        for i, key in enumerate(COLUMNS[k]):
            if k == 3 and key == LEVEL2_UNDER_3[0]:
                l3_split = y + 2.0          # Level 3 band ends here; Level 2 green takes over below
                y += 5.5                    # visible step between the two greens
            h = box_height(key)
            if k == 2 and i > 0:
                y += 3.0                    # room for the age-sex line routed across Level 2
            a.box(xk, y, w, h, ATTR, ATTR_EDGE)
            names, cond = CONTENT[key]
            lines = [(n, True) for n in names] + ([(cond, False)] if cond else [])
            cy0 = y + PAD_V / 2 + LINE / 2
            for j, (s, bold) in enumerate(lines):
                a.T(xk + w / 2, cy0 + j * LINE, s, bold=bold, zorder=5)
            if key == "income":     # the note, kept with its dark-red outline
                nw = tw("no sex filter") + 4
                ny = cy0 + len(lines) * LINE
                ax.add_patch(Rectangle((xk + w - nw - 2, ny - LINE / 2 + 0.6), nw, LINE - 1.2, fc="white",
                                       ec=NOTE_EDGE, lw=0.7, zorder=5))
                ax.text(xk + w - nw / 2 - 2, ny, "no sex filter", fontsize=F8, style="italic", ha="center",
                        va="center", color=INK, zorder=6)
            pos[key] = (xk, xk + w, y + h / 2, y, y + h)
            y += h + BOX_GAP
        col_bottom[k] = y
    bottom = max(col_bottom.values()) + 1.0
    assert bottom <= A_H - 3, bottom
    # header tabs
    for k in range(1, 5):
        a.box(xs[k], top, widths[k], HEADER_H, LEVEL_FILL[k], z=2)
        a.T(xs[k] + widths[k] / 2, top + HEADER_H / 2, f"Level {k}", bold=True, zorder=3)
    # level bands behind the columns (inset 3 pt, as P30)
    ins = 3.0 if variant == "P09" else 0.0
    yb0 = top + HEADER_H
    for k in (1, 4):
        ax.add_patch(Rectangle((xs[k] + ins, yb0), widths[k] - 2 * ins, col_bottom[k] - yb0 - BOX_GAP,
                               fc=LEVEL_FILL[k], ec="none", zorder=1))
    ax.add_patch(Rectangle((xs[3] + ins, yb0), widths[3] - 2 * ins, l3_split - yb0, fc=LEVEL_FILL[3], ec="none",
                           zorder=1))
    # Level 2: one L-shaped region = its own column + a bridge under Level 3 holding housing tenure, socioeconomic
    h0 = pos["housing"][3] - 2.0
    y2b = max(col_bottom[2], col_bottom[3]) - BOX_GAP
    x2l, x2r = xs[2] + ins, xs[2] + widths[2] - ins
    x3r = xs[3] + widths[3] - ins
    pts = [(x2l, yb0), (x2r, yb0), (x2r, h0), (x3r, h0), (x3r, y2b), (x2l, y2b), (x2l, yb0)]
    codes = [MPath.MOVETO] + [MPath.LINETO] * (len(pts) - 2) + [MPath.CLOSEPOLY]
    ax.add_patch(PathPatch(MPath(pts, codes), fc=LEVEL_FILL[2], ec="none", zorder=1))
    if variant == "P10":   # full-width level regions, and the Level 2 L-shape outlined (dashed, Level 4 green)
        ax.add_patch(PathPatch(MPath(pts, codes), fc="none", ec="#74A44D", lw=0.6, zorder=1.5,
                               linestyle=(0, (2.0, 1.2))))
    # ---- elbow arrows
    def feed(src, targets, vx):
        _, xr, ys, _, _ = pos[src]
        tys = [pos[t][2] for t in targets]
        a.line([xr, vx], [ys, ys])
        a.line([vx, vx], [min([ys] + tys), max([ys] + tys)])
        for t in targets:
            a.arrow(vx, pos[t][2], pos[t][0])

    feed("age_sex", ["education", "civil", "birth"], xs[2] - STUB)
    # age, sex -> housing tenure, socioeconomic class: across Level 2 between education and civil status
    ycross = (pos["education"][4] + pos["civil"][3]) / 2
    v1, v2 = xs[2] - STUB, xs[3] - STUB
    a.line([v1, v2], [ycross, ycross])
    a.line([v2, v2], [ycross, pos["socio"][2]])
    for t in LEVEL2_UNDER_3:
        a.arrow(v2, pos[t][2], pos[t][0])
    feed("education", ["employment"], xs[3] - STUB)
    feed("employment", ["income", "emptype", "industry"], xs[4] - STUB)
    return right, bottom


def build(variant, stem):
    with plt.rc_context(BC.rc()):
        fig = plt.figure(figsize=(B.W / 72, B.H / 72))
        B.draw(fig, with_a=False, letters=True)
        right, bottom = draw_a(fig, B.H, variant=variant)
        out = BC.save(fig, stem)
    print(stem, "panel A right =", round(right, 1), "bottom =", round(bottom, 1), "canvas", B.W, "x", B.H, out[0])
    return out[0]


ALL = {"P09": lambda: build("P09", "F2_P09_fig2a_p30_style"),
       "P10": lambda: build("P10", "F2_P10_fig2a_p30_level2_outlined")}



# ================================================================== round 3: F2_P11 / F2_P11b (baseline P10)
def draw_a_p11(fig, H, *, move_civil_birth=True):
    """P10 with (1) the age-sex feed to housing tenure and socioeconomic class routed through the gap between
    civil status and birth country, and (2) the lower boxes moved down so the lowest of them aligns with the
    bottom of industry sector (the lowest box). move_civil_birth=True moves civil status, birth country,
    housing tenure and socioeconomic class (P11); False moves only housing tenure and socioeconomic class (P11b).
    """
    a = A(fig, H)
    ax = a.ax
    ax.add_patch(FancyBboxPatch((-40, -40), A_W + 40, A_H + 40, boxstyle=f"round,pad=0,rounding_size={A_CORNER}",
                                fc="white", ec="none", zorder=0))
    ax.text(1, 0.5, "A", fontsize=F12, fontweight="bold", ha="left", va="top", color="black")
    top = DROP
    widths = {k: col_width(v, k) for k, v in COLUMNS.items()}
    xs, x = {}, X0
    for k in range(1, 5):
        xs[k] = x
        x += widths[k] + GAP
    right = x - GAP
    ROUTE_GAP = 4.5                      # gap between civil status and birth country that the feed runs through
    y0 = top + HEADER_H + BOX_GAP
    tops = {}
    # default stacking (P30 spacing) for columns 1 and 4
    for k in (1, 4):
        y = y0
        for key in COLUMNS[k]:
            tops[key] = y
            y += box_height(key) + BOX_GAP
    bottom_line = tops["industry"] + box_height("industry")      # the lowest box
    tops["education"] = y0
    tops["employment"] = y0
    hb = box_height("birth")
    if move_civil_birth:
        tops["birth"] = bottom_line - hb
        tops["civil"] = tops["birth"] - ROUTE_GAP - box_height("civil")
    else:
        tops["civil"] = y0 + box_height("education") + BOX_GAP
        tops["birth"] = tops["civil"] + box_height("civil") + ROUTE_GAP
    # housing tenure and socioeconomic class: bottom of socioeconomic class on the bottom line
    tops["socio"] = bottom_line - box_height("socio")
    tops["housing"] = tops["socio"] - ROUTE_GAP - box_height("housing")
    assert tops["civil"] >= y0 + box_height("education") + BOX_GAP - 1e-6
    assert tops["housing"] >= y0 + box_height("employment") + 6.0, "no visible gap under employment status"
    pos = {}
    for k in range(1, 5):
        xk, w = xs[k], widths[k]
        for key in COLUMNS[k]:
            y, h = tops[key], box_height(key)
            a.box(xk, y, w, h, ATTR, ATTR_EDGE)
            names, cond = CONTENT[key]
            lines = [(n, True) for n in names] + ([(cond, False)] if cond else [])
            cy0 = y + PAD_V / 2 + LINE / 2
            for j, (s, bold) in enumerate(lines):
                a.T(xk + w / 2, cy0 + j * LINE, s, bold=bold, zorder=5)
            if key == "income":
                nw = tw("no sex filter") + 4
                ny = cy0 + len(lines) * LINE
                ax.add_patch(Rectangle((xk + w - nw - 2, ny - LINE / 2 + 0.6), nw, LINE - 1.2, fc="white",
                                       ec=NOTE_EDGE, lw=0.7, zorder=5))
                ax.text(xk + w - nw / 2 - 2, ny, "no sex filter", fontsize=F8, style="italic", ha="center",
                        va="center", color=INK, zorder=6)
            pos[key] = (xk, xk + w, y + h / 2, y, y + h)
    col_bottom = {k: max(pos[key][4] for key in COLUMNS[k]) + BOX_GAP for k in COLUMNS}
    for k in range(1, 5):
        a.box(xs[k], top, widths[k], HEADER_H, LEVEL_FILL[k], z=2)
        a.T(xs[k] + widths[k] / 2, top + HEADER_H / 2, f"Level {k}", bold=True, zorder=3)
    yb0 = top + HEADER_H
    for k in (1, 4):   # P10: full-width level regions
        ax.add_patch(Rectangle((xs[k], yb0), widths[k], col_bottom[k] - yb0 - BOX_GAP, fc=LEVEL_FILL[k], ec="none",
                               zorder=1))
    l3_end = pos["employment"][4] + 2.0
    ax.add_patch(Rectangle((xs[3], yb0), widths[3], l3_end - yb0, fc=LEVEL_FILL[3], ec="none", zorder=1))
    h0 = pos["housing"][3] - 2.0
    y2b = max(col_bottom[2], col_bottom[3]) - BOX_GAP
    x2l, x2r, x3r = xs[2], xs[2] + widths[2], xs[3] + widths[3]
    pts = [(x2l, yb0), (x2r, yb0), (x2r, h0), (x3r, h0), (x3r, y2b), (x2l, y2b), (x2l, yb0)]
    codes = [MPath.MOVETO] + [MPath.LINETO] * (len(pts) - 2) + [MPath.CLOSEPOLY]
    ax.add_patch(PathPatch(MPath(pts, codes), fc=LEVEL_FILL[2], ec="none", zorder=1))
    ax.add_patch(PathPatch(MPath(pts, codes), fc="none", ec="#74A44D", lw=0.6, zorder=1.5,
                           linestyle=(0, (2.0, 1.2))))

    def feed(src, targets, vx):
        _, xr, ys, _, _ = pos[src]
        tys = [pos[t][2] for t in targets]
        a.line([xr, vx], [ys, ys])
        a.line([vx, vx], [min([ys] + tys), max([ys] + tys)])
        for t in targets:
            a.arrow(vx, pos[t][2], pos[t][0])

    feed("age_sex", ["education", "civil", "birth"], xs[2] - STUB)
    # age, sex -> housing tenure, socioeconomic class: through the civil status / birth country gap
    ycross = (pos["civil"][4] + pos["birth"][3]) / 2
    v1, v2 = xs[2] - STUB, xs[3] - STUB
    a.line([v1, v2], [ycross, ycross])
    a.line([v2, v2], [min(ycross, pos["housing"][2]), max(ycross, pos["socio"][2])])
    for t in LEVEL2_UNDER_3:
        a.arrow(v2, pos[t][2], pos[t][0])
    feed("education", ["employment"], xs[3] - STUB)
    feed("employment", ["income", "emptype", "industry"], xs[4] - STUB)
    bottom = max(col_bottom.values())
    assert right <= A_W - 2 and bottom <= A_H - 3, (right, bottom)
    return right, bottom


def build_p11(stem, **kw):
    with plt.rc_context(BC.rc()):
        fig = plt.figure(figsize=(B.W / 72, B.H / 72))
        B.draw(fig, with_a=False, letters=True)
        right, bottom = draw_a_p11(fig, B.H, **kw)
        out = BC.save(fig, stem)
    print(stem, "panel A right =", round(right, 1), "bottom =", round(bottom, 1), "canvas", B.W, "x", B.H, out[0])
    return out[0]


ALL["P11"] = lambda: build_p11("F2_P11_fig2a_route_civil_birth_four_lowered", move_civil_birth=True)

if __name__ == "__main__":
    for k in sys.argv[1:] or ALL:
        ALL[k]()
