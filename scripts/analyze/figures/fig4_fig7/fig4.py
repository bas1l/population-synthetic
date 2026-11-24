"""Manuscript Figure 4 (population-level fidelity), rebuilt on the 2026-10-04 outputs.

Layout reproduces the docx composite F07-F10-F11_population-level-result_03 (456 x 381.9 pt):
A  strategy means + per-model lines + E brackets (bars coloured on the shared TV ramp)
B  strategy x model heatmap (models as columns, model_ranking order, hosted/local hue)
C  strategy x model radar grid aligned under B, with a single attribute key on the left
D  E-minus-strategy gain per attribute (paired mean difference, 95% CI, Holm stars)
"""
from __future__ import annotations

import sys

import numpy as np
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, PathPatch, Rectangle
from matplotlib.path import Path as MPath
from matplotlib.transforms import ScaledTranslation

import common as C
from common import L, P, S, plt
from population_synthetic.analysis.method_significance.charts import (
    _FOREST_MARKERS,
    _p_to_stars,
)
from population_synthetic.analysis.method_significance.builder import significance_cutoff

W, H = 456.0, 381.887
FS_TICK = S.TICK_LABEL           # 8
FS_LABEL = S.TICK_LABEL_LARGE    # 9
FS_NUM = S.ANNOTATION            # 8
FS_SMALL = S.TICK_LABEL         # 8 (docx-measured label size)
GREY_BG = P.opaque(P.BAND_FILL, 0.7)

# ---- data ------------------------------------------------------------------------------
perf = C.performance()
msig = C.method_significance()
meta = msig["metadata"]
methods = meta["method_order"]
letters = L.method_letters(methods)
attrs = meta["attributes"]
models = C.model_order(perf)
hosting = perf["metadata"]["model_hosting"]

cells: dict[tuple[str, str], dict] = {}
for rec in perf["combos"].values():
    cells[(rec["model"], rec["strategy"])] = rec
grid = np.full((len(methods), len(models)), np.nan)
for i, m in enumerate(methods):
    for j, mod in enumerate(models):
        rec = cells.get((mod, m))
        if rec is not None:
            grid[i, j] = 100.0 * rec["overall"]["tv_similarity_mean"]

block = msig["method_comparison"]
thresholds, ns_symbol = block["star_thresholds"], block["ns_symbol"]
cutoff = significance_cutoff(thresholds)
overall = block["panels"]["overall"]
reference = methods[-1]

norm = Normalize(vmin=np.nanmin(grid), vmax=np.nanmax(grid))
cmap = P.heatmap_cmap()

rc = C.house_rc()
plt.rcParams.update(rc)
cv = C.PtCanvas(W, H, dpi=300)
fig = cv.fig

# ---- layout constants (pt, top-left origin; measured off the docx composite) -----------
HM_X0, HM_X1 = 213.9, 453.7
HM_Y0, HM_Y1 = 74.5, 128.8
COL_W = (HM_X1 - HM_X0) / len(models)
ROW_LETTER_X = 208.0
STRAT_LABEL_X = 197.0
RAD_Y = [156.9, 176.7, 196.5, 216.3, 236.1]
RAD_R = 9.3
GREY_TOP_R, GREY_TOP_L, GREY_BOT, GREY_SPLIT = 143.4, 151.6, 250.8, 196.0

# =========================================================================================
# Panel A
# =========================================================================================
cv.letter(1.0, 1.0, "A".lower())
axA = cv.axes(34.0, 24.0, 172.0, 128.8)
x = np.arange(len(methods))
means = [100 * overall["means"][m] for m in methods]
for xi, mu in zip(x, means):
    axA.bar(xi, mu, width=0.56, color=cmap(norm(mu)), edgecolor=P.BAR_EDGE,
            linewidth=0.4, zorder=2)
per_model = overall["per_model"]
rng = np.random.default_rng(0)
for mod in per_model:
    jit = (rng.random(len(methods)) - 0.5) * 0.24
    ys = [100 * per_model[mod][m] for m in methods]
    axA.plot(x + jit, ys, color=P.FAINT_LINK, linewidth=0.5, zorder=3)
    axA.scatter(x + jit, ys, s=9, color=P.CATEGORICAL_SERIES[0], edgecolors=P.SURFACE,
                linewidths=0.4, zorder=4)
data_top = max(100 * max(per_model[mod][m] for m in methods) for mod in per_model)
axA.set_xlim(-0.6, len(methods) - 0.4)
step = 8.0
base = data_top + 6.0
pairs = [m for m in methods[:-1]]
for k, m in enumerate(pairs):
    p = overall["pairwise_p"].get(f"{m}|{reference}")
    if p is None:
        p = overall["pairwise_p"][f"{reference}|{m}"]
    # docx stacking: the widest bracket (A-E) lowest, D-E highest
    y = base + step * k
    x1, x2 = methods.index(m), methods.index(reference)
    axA.plot([x1, x1, x2, x2], [y - 2.2, y, y, y - 2.2], color=P.ANNOTATION_GREY,
             linewidth=0.9, solid_capstyle="butt")
    axA.text(x1 + 0.5, y + 0.6,
             _p_to_stars(p, thresholds, ns_symbol), ha="center", va="bottom",
             fontsize=FS_TICK, color=P.ANNOTATION_GREY)
axA.set_ylim(0, base + step * (len(pairs) - 1) + 7.5)
axA.set_yticks([0, 20, 40, 60, 80])
axA.yaxis.grid(True, linestyle=(0, (4, 3)), color=P.SECONDARY_GREY, linewidth=0.6, zorder=0)
axA.set_axisbelow(True)
for sp in axA.spines.values():
    sp.set_visible(False)
axA.tick_params(axis="both", length=0, labelsize=FS_LABEL, pad=2)
axA.set_xticks(x)
axA.set_xticklabels([letters[m] for m in methods])
axA.set_ylabel("TV-similarity (%)", fontsize=FS_LABEL, labelpad=2)
axA.set_xlabel("strategy", fontsize=FS_LABEL, labelpad=0)

# shared colour key
cax = cv.axes(26.0, 21.0, 85.5, 27.6)
sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
cb = fig.colorbar(sm, cax=cax, orientation="horizontal")
ticks = [t for t in (40, 50, 60, 70, 80, 90) if norm.vmin <= t <= norm.vmax]
cb.set_ticks(ticks)
cb.ax.tick_params(labelsize=FS_LABEL, length=2, pad=1, width=0.6)
cb.outline.set_linewidth(0.8)
cv.text(55.75, 19.0, "TV-similarity (%)", ha="center", va="bottom", fontsize=FS_SMALL)

# =========================================================================================
# Panel B
# =========================================================================================
cv.letter(189.5, 1.0, "B".lower())
axB = cv.axes(HM_X0, HM_Y0, HM_X1, HM_Y1)
im = axB.imshow(np.ma.masked_invalid(grid), cmap=cmap, norm=norm, aspect="auto",
                interpolation="none")
for i in range(grid.shape[0]):
    for j in range(grid.shape[1]):
        v = grid[i, j]
        if np.isfinite(v):
            axB.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=FS_NUM,
                     color=P.text_color_on(im, v))
axB.set_xticks([])
axB.set_yticks(range(len(methods)))
axB.set_yticklabels([letters[m] for m in methods], fontsize=FS_LABEL)
axB.tick_params(axis="y", length=0, pad=2.5)
for sp in axB.spines.values():
    sp.set_visible(False)
for j, mod in enumerate(models):
    xc = HM_X0 + (j + 0.5) * COL_W
    cv.text(xc, HM_Y0 - 3.0, C.model_name(mod), rotation=90, ha="center", va="bottom",
            fontsize=FS_SMALL, color=P.HOST_COLORS[hosting[mod]])
cv.text(STRAT_LABEL_X, (HM_Y0 + HM_Y1) / 2, "strategy", rotation=90, ha="center",
        va="center", fontsize=FS_LABEL)
# hosted / local key (rotated, as in the docx)
for k, (cls, lab) in enumerate((("hosted", "hosted (API)"), ("local", "locally served"))):
    xk = 195.5 + 8.6 * k
    fig.patches.append(Rectangle(cv.xy(xk - 2.4, HM_Y0 - 1.0), 4.8 / W, 4.8 / H,
                                 transform=fig.transFigure, color=P.HOST_COLORS[cls]))
    cv.text(xk, HM_Y0 - 8.0, lab, rotation=90, ha="center", va="bottom", fontsize=FS_SMALL)

# arrows from the heatmap into the radar grid (first and last column)
for j in (0, len(models) - 1):
    xc = HM_X0 + (j + 0.5) * COL_W
    fig.add_artist(Line2D([cv.xy(xc, 0)[0]] * 2, [cv.xy(0, 133.5)[1], cv.xy(0, 145.0)[1]],
                          transform=fig.transFigure, color="black", linewidth=0.5))
    fig.patches.append(PathPatch(MPath([cv.xy(xc - 1.6, 142.2), cv.xy(xc, 145.4),
                                        cv.xy(xc + 1.6, 142.2)]),
                                 transform=fig.transFigure, fill=False, linewidth=0.5,
                                 edgecolor="black"))

# =========================================================================================
# Panel C
# =========================================================================================
# grey ground: full width from GREY_TOP_L down, raised to GREY_TOP_R right of GREY_SPLIT
r = 8.0
verts = [
    (0, GREY_BOT), (0, GREY_TOP_L),
    (GREY_SPLIT - 12, GREY_TOP_L), (GREY_SPLIT - 4, GREY_TOP_L), (GREY_SPLIT - 3, GREY_TOP_R),
    (GREY_SPLIT + 6, GREY_TOP_R),
    (W - r, GREY_TOP_R), (W, GREY_TOP_R), (W, GREY_TOP_R + r),
    (W, GREY_BOT), (0, GREY_BOT),
]
codes = [MPath.MOVETO, MPath.LINETO, MPath.LINETO, MPath.CURVE4, MPath.CURVE4, MPath.CURVE4,
         MPath.LINETO, MPath.CURVE3, MPath.CURVE3, MPath.LINETO, MPath.CLOSEPOLY]
fig.patches.append(PathPatch(MPath([cv.xy(*v) for v in verts], codes),
                             transform=fig.transFigure, facecolor="#ffffff", edgecolor="none",
                             zorder=-10))

n_attr = len(attrs)
ang = np.array([2 * np.pi * k / n_attr for k in range(n_attr)])
TEAL = P.ACCENT_PAIR[0]


def radar(ax, values, *, key=False):
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_ylim(0, 1)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.spines["polar"].set_visible(False)
    ax.grid(False)
    ax.set_facecolor(P.SURFACE)
    th = np.linspace(0, 2 * np.pi, 200)
    for a in ang:
        ax.plot([a, a], [0, 1], color=P.RESIDUAL_GREY, linewidth=0.35 if not key else 0.6,
                zorder=1)
    ax.plot(th, np.full_like(th, 0.5), color=P.BASELINE_DARK, linewidth=0.35 if not key else 0.6,
            zorder=2)
    ax.plot(th, np.ones_like(th), color="black", linewidth=0.7 if not key else 1.2, zorder=5,
            clip_on=False)
    if values is not None:
        a2 = np.append(ang, ang[0])
        v2 = np.append(values, values[0])
        ax.fill(a2, v2, color=P.opaque(TEAL, 0.20), zorder=3, linewidth=0)
        ax.plot(a2, v2, color=TEAL, linewidth=1.0, zorder=4)


for i, m in enumerate(methods):
    cv.text(ROW_LETTER_X, RAD_Y[i], letters[m], ha="center", va="center", fontsize=FS_LABEL)
    for j, mod in enumerate(models):
        xc = HM_X0 + (j + 0.5) * COL_W
        ax = cv.axes(xc - RAD_R, RAD_Y[i] - RAD_R, xc + RAD_R, RAD_Y[i] + RAD_R,
                     projection="polar")
        rec = cells.get((mod, m))
        if rec is None:
            radar(ax, None)
            for ln in ax.lines[:-1]:
                ln.set_visible(False)
            ax.text(0.5, 0.5, "N/A", transform=ax.transAxes, ha="center", va="center",
                    fontsize=FS_LABEL, color=P.SECONDARY_GREY)
            continue
        vals = np.array([rec["per_attribute"][a]["tv_similarity"] for a in attrs])
        radar(ax, vals)
cv.text(STRAT_LABEL_X, (RAD_Y[0] + RAD_Y[-1]) / 2, "strategy", rotation=90, ha="center",
        va="center", fontsize=FS_LABEL)

# key radar
cv.letter(1.0, 152.5, "C".lower())
KX, KY, KR = 94.6, 210.0, 19.4
cv.text(KX, 158.0, "Attributes TV-similarity (%)", ha="center", va="center", fontsize=FS_SMALL)
axK = cv.axes(KX - KR, KY - KR, KX + KR, KY + KR, projection="polar")
radar(axK, None, key=True)
half = n_attr // 2
row_y = np.linspace(175.6, 242.6, half)
for k, a in enumerate(attrs):
    theta = ang[k]
    px, py = KX + KR * np.sin(theta), KY - KR * np.cos(theta)
    if k < half:                   # right side, top to bottom
        ly = row_y[k]
        side = 1
    else:                          # left side, bottom to top
        ly = row_y[n_attr - 1 - k]
        side = -1
    dy = ly - KY
    dx = (KR + 3.0) * np.sqrt(max(0.0, 1.0 - (dy / 40.0) ** 2))
    lx = KX + side * (dx + 2.0)
    fig.add_artist(Line2D([cv.xy(px, py)[0], cv.xy(lx, ly)[0]], [cv.xy(px, py)[1], cv.xy(lx, ly)[1]],
                          transform=fig.transFigure, color="black", linewidth=0.5))
    cv.text(lx + side * 0.8, ly, L.attribute_label(a), ha="left" if side > 0 else "right",
            va="center", fontsize=FS_SMALL)
# ring values: 50 on the inner ring, 100 below the outer ring between the two lowest leaders
cv.text(KX, KY + 0.5 * KR, "50", ha="center", va="center", fontsize=FS_SMALL,
        bbox=dict(boxstyle="square,pad=0.05", facecolor=P.SURFACE, edgecolor="none"))
cv.text(KX + 2.3, KY + KR + 7.0, "100", ha="center", va="center", fontsize=FS_SMALL)

# =========================================================================================
# Panel D
# =========================================================================================
cv.letter(1.0, 254.5, "D".lower())
hues = list(P.ORDERED_QUALITATIVE_SERIES[: len(methods) - 1])
comparators = methods[:-1]
marks = []
for col, a in enumerate(attrs):
    pm = block["panels"][a]["pair_matrix"]
    idx = {m: k for k, m in enumerate(pm["methods"])}
    ra = idx[reference]
    for c, m in enumerate(comparators):
        at = idx[m]
        marks.append(dict(col=col, c=c, mean=pm["mean_diff"][ra][at], p=pm["p_holm"][ra][at],
                          low=pm["ci_low"][ra][at], high=pm["ci_high"][ra][at]))
D_X0, D_X1 = 33.0, 454.0
D_ZERO, D_UNIT = 319.5, 63.0           # pt of y=0 and pt per unit (docx scale)
lows = min(0.0, min(mk["low"] for mk in marks))
ylo = lows - 0.03
D_TOP = 259.0
yhi = (D_ZERO - D_TOP) / D_UNIT
D_BOT = D_ZERO - ylo * D_UNIT
axD = cv.axes(D_X0, D_TOP, D_X1, D_BOT)
axD.set_ylim(ylo, yhi)
axD.set_xlim(-0.55, len(attrs) - 0.45)
gridvals = [v for v in (0.2, 0.4, 0.6) if v < yhi]
band_top = gridvals[-1]
for col in range(1, len(attrs), 2):
    axD.add_patch(Rectangle((col - 0.5, 0), 1.0, band_top, facecolor=GREY_BG,
                            edgecolor="none", zorder=0))
for v in gridvals:
    axD.axhline(v, color=P.RESIDUAL_GREY, linewidth=0.5, linestyle=":", zorder=0.5)
axD.axhline(0, color=P.MUTED_GREY, linewidth=0.6, linestyle=":", zorder=0.5)
span = 0.88
stepc = span / len(comparators)
offs = [(c - (len(comparators) - 1) / 2) * stepc for c in range(len(comparators))]
for mk in marks:
    xx = mk["col"] + offs[mk["c"]]
    col_ = hues[mk["c"]]
    sig = mk["p"] is not None and mk["p"] <= cutoff
    axD.plot([xx, xx], [mk["low"], mk["high"]], color=col_, linewidth=0.8, zorder=2)
    axD.plot(xx, mk["mean"], marker=_FOREST_MARKERS[mk["c"]], markersize=4.2, linestyle="none",
             color=col_, markeredgecolor=col_, markerfacecolor=col_ if sig else P.SURFACE,
             markeredgewidth=0.8, zorder=3)
    txt = _p_to_stars(mk["p"], thresholds, ns_symbol)
    shift = ScaledTranslation(2.9 / 72, 1.2 / 72, fig.dpi_scale_trans)
    axD.text(xx, mk["high"], txt, rotation=90, ha="center", va="bottom",
             rotation_mode="default", fontsize=FS_TICK if txt != ns_symbol else FS_LABEL,
             color=col_, zorder=4,
             transform=axD.transData + ScaledTranslation(0, 1.0 / 72, fig.dpi_scale_trans),
             linespacing=0.8)
axD.set_yticks([0] + gridvals)
axD.set_yticklabels(["0"] + [f"{v:.1f}" for v in gridvals])
axD.tick_params(axis="y", length=2.5, width=0.6, labelsize=FS_LABEL, pad=1.5)
axD.set_xticks(range(len(attrs)))
axD.set_xticklabels([L.attribute_label(a).replace(" ", "\n", 1) for a in attrs], rotation=90,
                    ha="center", va="top", fontsize=FS_SMALL, multialignment="right",
                    linespacing=1.0)
axD.tick_params(axis="x", length=2.5, width=0.6, pad=1.5)
for sp in axD.spines.values():
    sp.set_visible(False)
cv.text(9.0, D_ZERO - 0.3 * D_UNIT, f"{letters[reference]} − strategy", rotation=90,
        ha="center", va="center", fontsize=FS_LABEL)
handles = [Line2D([], [], marker=_FOREST_MARKERS[c], linestyle="none", color=hues[c],
                  markersize=5.0, label=f"{letters[reference]} minus {letters[m]}")
           for c, m in enumerate(comparators)]
LEG_X, LEG_Y = 113.0, 257.0
fig.legend(handles=handles, ncol=2, frameon=False, fontsize=FS_SMALL, loc="upper left",
           bbox_to_anchor=cv.xy(LEG_X, LEG_Y), handlelength=1.0, handletextpad=0.3,
           columnspacing=0.4, labelspacing=0.15, borderaxespad=0, borderpad=0)

if __name__ == "__main__":
    out = C.OUT_DIR / "fig4"
    panels = {
        "A": (0, 0, 186.0, 141.0),
        "B": (186.0, 0, W, 141.0),
        "C": (0, 141.0, W, 252.0),
        "D": (0, 252.0, W, H),
    }
    C.save_all(fig, out, dpi=900, panels=panels, pt_h=H, pt_w=W)
    print("wrote", out)
