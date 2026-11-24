"""Manuscript Figure 7 (cost per 100 valid individuals vs overall TV similarity), rebuilt on the
2026-10-04 cost_efficiency output. Layout reproduces F26_cost_vs_fidelity_remake (456 x 375.2 pt):
log-x scatter, strategy hue (A-E key, 2 columns, inside upper-left), hosted = circle,
locally served = square, every point labelled with its model name; no title, no footnote.
"""
from __future__ import annotations

import csv

import numpy as np
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, MultipleLocator, NullFormatter

import common as C
from common import L, P, S, plt

W, H = 456.0, 375.181
FS = S.TICK_LABEL           # 8 pt: point labels, tick labels
FS_AX = S.TICK_LABEL_LARGE  # 9 pt: axis titles, legend

rows = list(csv.DictReader(open(C.ANALYSIS / "cost_efficiency" / f"{C.COUNTRY}_cost_efficiency.csv",
                                encoding="utf-8")))
perf = C.performance()
hosting = perf["metadata"]["model_hosting"]
methods = perf["metadata"]["strategies"]
from population_synthetic.analysis.utils.axes import strategy_complexity_order  # noqa: E402

methods = strategy_complexity_order(sorted({r["strategy"] for r in rows}))
letters = L.method_letters(methods)
hue = dict(zip(methods, P.ORDERED_QUALITATIVE_SERIES))
MARK = {"hosted": "o", "local": "s"}

pts = []
for r in rows:
    pts.append(dict(x=float(r["cost_per_100_usable_personas"]), y=float(r["overall_tv_similarity"]),
                    model=r["model"], strategy=r["strategy"], host=hosting[r["model"]]))

plt.rcParams.update(C.house_rc())
cv = C.PtCanvas(W, H, dpi=300)
fig = cv.fig
AX = (39.5, 3.0, 451.0, 343.0)
ax = cv.axes(*AX)
ax.set_xscale("log")
xs = np.array([p["x"] for p in pts])
ys = np.array([p["y"] for p in pts])
ax.set_xlim(xs.min() * 0.62, xs.max() * 2.2)
ylo, yhi = ys.min(), ys.max()
pad = 0.04 * (yhi - ylo)
ax.set_ylim(ylo - pad, yhi + pad)
ax.grid(True, which="major", color=P.GRID_RULE, linewidth=0.6, zorder=0)
ax.set_axisbelow(True)
MS = 7.0
for p in pts:
    ax.plot(p["x"], p["y"], marker=MARK[p["host"]], markersize=MS, linestyle="none",
            color=hue[p["strategy"]], markeredgecolor=P.SURFACE, markeredgewidth=0.6, zorder=3)
ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
ax.xaxis.set_minor_formatter(NullFormatter())
ax.tick_params(labelsize=FS_AX, length=3, width=0.6)
ax.tick_params(which="minor", length=1.8, width=0.5)
ax.yaxis.set_major_locator(MultipleLocator(0.05))
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.2f}"))
ax.set_xlabel(f"Cost per 100 valid {L.figure_term('individuals')} (USD, log scale)",
              fontsize=FS_AX + 1, labelpad=3)
ax.set_ylabel("TV-similarity (higher is better)", fontsize=FS_AX + 1, labelpad=3)

handles = [Line2D([], [], marker="o", linestyle="none", markersize=6.5, color=hue[m],
                  markeredgecolor=P.SURFACE, label=letters[m]) for m in methods]
leg = ax.legend(handles=handles, title="strategy", ncol=2, loc="upper left",
                bbox_to_anchor=(0.045, 0.975), fontsize=FS_AX + 1, title_fontsize=FS_AX + 2,
                frameon=True, fancybox=True, edgecolor=P.SECONDARY_GREY, handletextpad=0.2,
                columnspacing=2.4, borderpad=0.6, labelspacing=0.35, handlelength=1.0)
leg.get_frame().set_linewidth(1.0)

# ---- label placement: greedy, in display points, avoiding labels, markers, legend, frame ----
fig.canvas.draw()
rend = fig.canvas.get_renderer()
to_pt = 72.0 / fig.dpi


def disp(p):
    X, Y = ax.transData.transform((p["x"], p["y"]))
    return X * to_pt, Y * to_pt


axbb = ax.get_window_extent(rend)
AXB = (axbb.x0 * to_pt, axbb.y0 * to_pt, axbb.x1 * to_pt, axbb.y1 * to_pt)
lbb = leg.get_window_extent(rend)
obstacles = [(lbb.x0 * to_pt, lbb.y0 * to_pt, lbb.x1 * to_pt, lbb.y1 * to_pt)]
R = MS / 2 + 0.6
for p in pts:
    X, Y = disp(p)
    obstacles.append((X - R, Y - R, X + R, Y + R))


def overlap(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if (w > 0 and h > 0) else 0.0


GAP = 1.2
leaders = []  # placed leader segments, display pt


def leader_of(X, Y, box):
    lx = min(max(X, box[0]), box[2])
    ly = min(max(Y, box[1]), box[3])
    v = np.array([lx - X, ly - Y])
    n = np.linalg.norm(v)
    if n <= R + 1:
        return None
    return (X + v[0] / n * R, Y + v[1] / n * R, lx, ly)


def seg_hits(seg, box, pad=0.5):
    if seg is None:
        return 0
    t = np.linspace(0.05, 0.95, 24)
    xs_ = seg[0] + t * (seg[2] - seg[0])
    ys_ = seg[1] + t * (seg[3] - seg[1])
    inside = (xs_ > box[0] - pad) & (xs_ < box[2] + pad) & (ys_ > box[1] - pad) & (ys_ < box[3] + pad)
    return int(inside.sum())


PAD = 1.0  # clearance (pt) every label keeps from other labels, other markers and leaders

# label extents (display pt)
sizes = []
for p in pts:
    t = ax.text(0, 0, C.model_name(p["model"]), fontsize=FS)
    bb = t.get_window_extent(rend)
    sizes.append((bb.width * to_pt, bb.height * to_pt))  # full drawn extent
    t.remove()
anchors = [disp(p) for p in pts]
N = len(pts)
markers = obstacles[1:]
legend_box = obstacles[0]

CANDS = [(d, a if a <= 180 else a - 360) for d in (0.0, 4.0, 9.0, 15.0, 22.0, 30.0, 40.0, 55.0, 70.0)
         for a in range(0, 360, 10)]


def candidate_box(i, dist, ang):
    X, Y = anchors[i]
    w, h = sizes[i]
    rad = np.radians(ang)
    cx = X + np.cos(rad) * (R + GAP + dist)
    cy = Y + np.sin(rad) * (R + GAP + dist)
    c, s_ = np.cos(rad), np.sin(rad)
    x0 = cx if c > 0.25 else (cx - w if c < -0.25 else cx - w / 2)
    y0 = cy if s_ > 0.25 else (cy - h if s_ < -0.25 else cy - h / 2)
    return (x0, y0, x0 + w, y0 + h)


def padded(b, d=PAD):
    return (b[0] - d, b[1] - d, b[2] + d, b[3] + d)


# per point: list of admissible candidates (static constraints already satisfied) with soft cost
opts = []
for i in range(N):
    X, Y = anchors[i]
    lst = []
    for dist, ang in CANDS:
        box = candidate_box(i, dist, ang)
        seg = leader_of(X, Y, box) if dist >= 4.0 else None
        pb = padded(box)
        if box[0] < AXB[0] + 1 or box[2] > AXB[2] - 1 or box[1] < AXB[1] + 1 or box[3] > AXB[3] - 1:
            continue
        if overlap(pb, legend_box) > 0:
            continue
        if any(overlap(pb, m) > 0 for k, m in enumerate(markers) if k != i):
            continue
        if seg is not None and any(seg_hits(seg, m, pad=0.3) for k, m in enumerate(markers) if k != i):
            continue
        soft = dist * 1.5 + (0 if ang == 0 else 0.5 + abs(ang) / 180.0)
        lst.append(dict(box=box, seg=seg, soft=soft, cand=(dist, ang)))
    if not lst:
        raise RuntimeError(f"no admissible label position for point {i}")
    lst.sort(key=lambda o: o["soft"])
    opts.append(lst)

near = [[j for j in range(N) if j != i and np.hypot(anchors[i][0] - anchors[j][0],
                                                    anchors[i][1] - anchors[j][1]) < 2 * 70 + 2 * 120] for i in range(N)]


def clash(a, b):
    """Do two placed labels (box + leader) collide?"""
    if overlap(padded(a["box"]), b["box"]) > 0:
        return True
    if a["seg"] is not None and seg_hits(a["seg"], b["box"], pad=PAD):
        return True
    if b["seg"] is not None and seg_hits(b["seg"], a["box"], pad=PAD):
        return True
    return False


def conflicts(i, o, sol):
    return [j for j in near[i] if j in sol and clash(o, sol[j])]


def solve(order, rng):
    """Greedy start, then min-conflicts local search with plateau moves (seeded, deterministic)."""
    sol = {}
    for i in order:
        sol[i] = min(opts[i], key=lambda o: (len(conflicts(i, o, sol)), o["soft"]))
    for _ in range(600):
        bad = [i for i in range(N) if conflicts(i, sol[i], sol)]
        if not bad:
            break
        i = bad[int(rng.integers(len(bad)))]
        cur = len(conflicts(i, sol[i], sol))
        scored = [(len(conflicts(i, o, sol)), o["soft"], k) for k, o in enumerate(opts[i])]
        mn = min(c for c, _, _ in scored)
        pool = [k for c, _, k in scored if c == mn]
        if mn < cur or rng.random() < 0.7:
            k = min(pool, key=lambda k: opts[i][k]["soft"])
        else:
            k = pool[int(rng.integers(len(pool)))]
        if rng.random() < 0.05:  # random walk escape
            k = int(rng.integers(len(opts[i])))
        sol[i] = opts[i][k]
    # polish: shorten leaders where it stays collision-free
    for i in range(N):
        if not conflicts(i, sol[i], sol):
            for o in opts[i]:
                if o["soft"] >= sol[i]["soft"]:
                    break
                if not conflicts(i, o, sol):
                    sol[i] = o
                    break
    return sol, sum(1 for i in range(N) if conflicts(i, sol[i], sol))


base_order = sorted(range(N), key=lambda i: -pts[i]["y"])
rng = np.random.default_rng(7)
best_sol, best_bad = None, None
for attempt in range(int(__import__('os').environ.get('ATTEMPTS', '40'))):  # deterministic: fixed seed, first attempt is the y-order
    order = base_order if attempt == 0 else list(rng.permutation(N))
    sol, nbad = solve(order, rng)
    total = sum(o["soft"] for o in sol.values())
    if best_sol is None or (nbad, total) < (best_bad, best_total):
        best_sol, best_bad, best_total = sol, nbad, total
    if nbad == 0 and attempt >= 4:
        break
if best_bad:
    for i in range(N):
        cs = conflicts(i, best_sol[i], best_sol)
        if cs:
            print("collide:", C.model_name(pts[i]["model"]), letters[pts[i]["strategy"]], "opts", len(opts[i]),
                  "with", [C.model_name(pts[j]["model"]) + "/" + letters[pts[j]["strategy"]] for j in cs])
    raise RuntimeError(f"{best_bad} labels still collide after placement")

for i, st in best_sol.items():
    p = pts[i]
    box, seg = st["box"], st["seg"]
    dx_, dy_ = ax.transData.inverted().transform((box[0] / to_pt, box[1] / to_pt))
    ax.text(dx_, dy_, C.model_name(p["model"]), fontsize=FS, color=P.ANNOTATION_GREY,
            ha="left", va="bottom", zorder=4)
    if seg is not None:
        a0 = ax.transData.inverted().transform((seg[0] / to_pt, seg[1] / to_pt))
        a1 = ax.transData.inverted().transform((seg[2] / to_pt, seg[3] / to_pt))
        ax.plot([a0[0], a1[0]], [a0[1], a1[1]], color=P.MUTED_GREY, linewidth=0.4, zorder=2)

# independent check on the drawn text extents (not the estimates used for placement)
fig.canvas.draw()
drawn = [t for t in ax.texts]
ext = [t.get_window_extent(rend) for t in drawn]
hits = []
for a_ in range(len(ext)):
    for b_ in range(a_ + 1, len(ext)):
        if ext[a_].overlaps(ext[b_]):
            hits.append((drawn[a_].get_text(), drawn[b_].get_text()))
mk_px = [ax.transData.transform((p["x"], p["y"])) for p in pts]
r_px = (MS / 2) * fig.dpi / 72.0
own = {id(t): k for k, t in zip([i for i in best_sol], drawn)}
for t, e in zip(drawn, ext):
    k_own = own[id(t)]
    for k, (mx, my) in enumerate(mk_px):
        if k == k_own:
            continue
        cx_, cy_ = min(max(mx, e.x0), e.x1), min(max(my, e.y0), e.y1)
        if np.hypot(cx_ - mx, cy_ - my) < r_px:
            hits.append((t.get_text(), "marker " + C.model_name(pts[k]["model"]) + "/" + letters[pts[k]["strategy"]]))
if hits:
    raise RuntimeError(f"drawn labels touch: {hits}")
print(f"label check: 0 collisions among {len(drawn)} labels (drawn extents; placement clearance {PAD} pt)")

if __name__ == "__main__":
    out = C.OUT_DIR / "fig7"
    C.save_all(fig, out, dpi=600)
    print("wrote", out, "points:", len(pts))
