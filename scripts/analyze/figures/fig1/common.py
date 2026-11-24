"""Figure 1 gallery: shared facts, colours and glyphs.

Facts are read from the run outputs and repo config, and asserted, so a prototype can never
print a count the data do not hold. Glyphs draw on one point-unit axes (origin bottom-left).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
from matplotlib.patches import Circle, FancyBboxPatch, Polygon, Rectangle, Wedge, FancyArrowPatch
from matplotlib.lines import Line2D

from population_synthetic.analysis.utils import style
from population_synthetic.analysis.utils.palette import (
    ORDERED_QUALITATIVE_SERIES, HOST_COLORS, MUTED_GREY, BASELINE_DARK, SECONDARY_GREY,
    GRID_RULE, SURFACE, RESIDUAL_GREY, BAND_FILL,
)
from population_synthetic.analysis.utils.labels import method_letters, model_labels
from population_synthetic.analysis.utils.cap_index import load_cap_index
from population_synthetic.analysis.utils.model_order import ranked_model_order
from population_synthetic.analysis.utils.registry import resolve_output_base
from population_synthetic.analysis.utils.table_style import HOST_LABELS
from population_synthetic.analysis.model_ranking.hosting import classify_hosting, load_hosting_config
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values

REPO = Path(os.environ["POPSYNTH_REPO"])
GALLERY = Path(__file__).resolve().parent.parent
COUNTRY = "swedish_02"
W = style.TEXT_WIDTH * style.POINTS_PER_INCH  # 456 pt

# ---------------------------------------------------------------- facts
OUT = resolve_output_base(None)
ANALYSIS = OUT / "03_Analysis"
CAP = load_cap_index(OUT)
_mapped_index = json.loads((ANALYSIS / "population_cap" / "_mapped" / "_index.json").read_text(encoding="utf-8"))
_real = json.loads((ANALYSIS / "population_cap" / "_mapped" / f"real_{COUNTRY}.json").read_text(encoding="utf-8"))
_map_cfg = json.loads((REPO / "config" / "mapping" / "scb_native" / "_index.json").read_text(encoding="utf-8"))

N_REFERENCE = len(_real["individuals"])
N_ATTRIBUTES = len(_map_cfg["attributes"]) - len(_map_cfg["deprecated_attributes"])
N_SCB_TABLES = 13  # age and sex share one table (manuscript 4.1); structural constant
N_COMBOS = len(_mapped_index)
_kept = [e for e in _mapped_index if not e.get("skipped")]
N_KEPT = len(_kept)
N_PER_COMBO = sorted({e["n"] for e in _kept})
N_JUDGED_REFERENCE = 100  # manuscript 4.4.2: first 100 reference individuals judged

_slugs = [e["slug"] for e in _mapped_index]
_pre = f"{COUNTRY}_"
_strategy_ids = sorted({s for s in (Path(p).stem for p in (REPO / "config/synthetic/axes/strategies").glob("*.yaml"))
                        if not s.startswith("_") and s.endswith("_v2")})


def _split(slug: str):
    rest = slug[len(_pre):]
    for sid in sorted(_strategy_ids, key=len, reverse=True):
        if rest.startswith(sid + "_"):
            return sid, rest[len(sid) + 1:]
    raise ValueError(slug)


PAIRS = {s: _split(s) for s in _slugs}
STRATEGIES = list(method_letters(sorted({p[0] for p in PAIRS.values()})).keys())
LETTERS = method_letters(STRATEGIES)
MODELS_PRESENT = sorted({p[1] for p in PAIRS.values()})
WITHDRAWN = {PAIRS[s] for s in CAP.withdrawn_slugs()}

_perf = json.loads((ANALYSIS / "model_ranking" / f"{COUNTRY}_performance.json").read_text(encoding="utf-8"))
_ranked = ranked_model_order(_perf, CAP)
MODEL_ORDER = [m for m in _ranked if m in MODELS_PRESENT] + [m for m in MODELS_PRESENT if m not in _ranked]
MODEL_NAMES = model_labels(MODEL_ORDER)
_model_dicts = [d for d in discover_axis_values("models") if d["id"] in MODELS_PRESENT]
HOSTING = classify_hosting(_model_dicts, load_hosting_config(REPO / "config/analysis/model_ranking/provider_hosting.json"))

assert N_REFERENCE == 10000, N_REFERENCE
assert N_ATTRIBUTES == 14, N_ATTRIBUTES
assert N_COMBOS == 65 and N_KEPT == 58 and N_PER_COMBO == [100], (N_COMBOS, N_KEPT, N_PER_COMBO)
assert len(MODEL_ORDER) == 13 and len(STRATEGIES) == 5, (MODEL_ORDER, STRATEGIES)
assert [LETTERS[s] for s in STRATEGIES] == list("ABCDE")
assert len(WITHDRAWN) == 7
assert sum(1 for m in MODEL_ORDER if HOSTING[m] == "local") == 4

# ---------------------------------------------------------------- colours
STRAT_COLOR = {s: ORDERED_QUALITATIVE_SERIES[i] for i, s in enumerate(STRATEGIES)}
SC = [STRAT_COLOR[s] for s in STRATEGIES]
REF = "#4D4D4D"        # reference route: neutral dark grey (no data hue)
REF_FILL = "#E6E6E6"
INK = BASELINE_DARK
SOFT = SECONDARY_GREY
SCHEMA = "#7A6A45"     # canonical schema accent: dark khaki, outside every data palette
SCHEMA_FILL = "#F3EEDF"
HOST = HOST_COLORS
HOST_TXT = HOST_LABELS

F8, F9, F10, F11, F12 = 8.0, 9.0, 10.0, 11.0, 12.0


# ---------------------------------------------------------------- canvas
def canvas(h):
    from population_synthetic.analysis.utils.glyph_grid import PointCanvas
    c = PointCanvas(W, h)
    ax = c.axes(0, 0, W, h)
    ax.set_xlim(0, W)
    ax.set_ylim(0, h)
    ax.set_aspect("equal")
    ax.axis("off")
    return c, ax


def save(fig, name):
    from population_synthetic.analysis.utils.figures import save_figure
    png = GALLERY / f"F1_{name}.png"
    words = sum(len(t.get_text().split()) for t in fig.findobj(lambda a: hasattr(a, "get_text") and a.get_visible()) if t.get_text().strip())
    save_figure(fig, png, fixed_canvas=True)
    for suf in (".svg", ".eps"):
        p = png.with_suffix(suf)
        if p.exists():
            os.remove(p)
    meta = GALLERY / "code" / "word_counts.json"
    d = json.loads(meta.read_text()) if meta.exists() else {}
    d[name] = words
    meta.write_text(json.dumps(d, indent=1))
    return png


# ---------------------------------------------------------------- glyphs
def T(ax, x, y, s, size=F8, color=INK, ha="center", va="center", weight="normal", **kw):
    return ax.text(x, y, s, fontsize=size, color=color, ha=ha, va=va, fontweight=weight, **kw)


def box(ax, x, y, w, h, ec=INK, fc=SURFACE, lw=0.8, r=3, ls="-", z=1):
    p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}", ec=ec, fc=fc, lw=lw, ls=ls, zorder=z)
    ax.add_patch(p)
    return p


def arrow(ax, x0, y0, x1, y1, color=INK, lw=1.0, head=5, z=3, style_="-|>", conn=None):
    a = FancyArrowPatch((x0, y0), (x1, y1), arrowstyle=f"{style_},head_length={head*0.8},head_width={head*0.5}",
                        color=color, lw=lw, zorder=z, shrinkA=0, shrinkB=0,
                        connectionstyle=conn or "arc3", mutation_scale=1)
    ax.add_patch(a)
    return a


def line(ax, xs, ys, color=INK, lw=1.0, z=2, ls="-", cap="round"):
    l = Line2D(xs, ys, color=color, lw=lw, zorder=z, ls=ls, solid_capstyle=cap)
    ax.add_line(l)
    return l


def table_icon(ax, x, y, w, h, color=REF, fill=SURFACE, rows=4, cols=3, lw=0.6, z=4):
    """A statistical table: header band + grid."""
    ax.add_patch(Rectangle((x, y), w, h, ec=color, fc=fill, lw=lw, zorder=z))
    hh = h / (rows + 1)
    ax.add_patch(Rectangle((x, y + h - hh), w, hh, ec=color, fc=color, lw=lw, zorder=z))
    for i in range(1, rows):
        line(ax, [x, x + w], [y + i * hh] * 2, color=color, lw=0.3, z=z + 0.1)
    for j in range(1, cols):
        line(ax, [x + j * w / cols] * 2, [y, y + h - hh], color=color, lw=0.3, z=z + 0.1)


def table_stack(ax, x, y, w, h, n=3, color=REF, step=3.0):
    for k in range(n - 1, -1, -1):
        table_icon(ax, x + k * step, y + k * step, w, h, color=color, z=4 + (n - k))


def person(ax, x, y, h, color=INK, z=5, fc=None):
    """Head + shoulders glyph, centred at x, base at y, height h."""
    fc = fc or color
    r = h * 0.2
    ax.add_patch(Circle((x, y + h - r), r, fc=fc, ec="none", zorder=z))
    ax.add_patch(Wedge((x, y), h * 0.42, 0, 180, fc=fc, ec="none", zorder=z))


def crowd(ax, x, y, cols, rows, h, colors, gap=1.15, z=5):
    k = 0
    for r in range(rows):
        for c in range(cols):
            col = colors[k % len(colors)] if isinstance(colors, (list, tuple)) else colors
            person(ax, x + c * h * 0.9 * gap, y + r * h * gap, h, color=col, z=z)
            k += 1


def llm_chip(ax, x, y, s, color=INK, fill=SURFACE, label="LLM", size=F8, z=5, lw=0.8):
    """Microchip glyph: square body with pins; x,y = centre."""
    b = s * 0.8
    ax.add_patch(FancyBboxPatch((x - b / 2, y - b / 2), b, b, boxstyle=f"round,pad=0,rounding_size={b*0.12}",
                                ec=color, fc=fill, lw=lw, zorder=z))
    for k in (-1, 0, 1):
        o = k * b * 0.28
        for (xa, ya, xb, yb) in ((x + o, y + b / 2, x + o, y + s / 2), (x + o, y - b / 2, x + o, y - s / 2),
                                 (x + b / 2, y + o, x + s / 2, y + o), (x - b / 2, y + o, x - s / 2, y + o)):
            line(ax, [xa, xb], [ya, yb], color=color, lw=lw * 0.9, z=z - 0.1, cap="butt")
    if label:
        T(ax, x, y, label, size=size, color=color, weight="bold", zorder=z + 1)


def die(ax, x, y, s, color=REF, z=5, pips=5):
    ax.add_patch(FancyBboxPatch((x - s / 2, y - s / 2), s, s, boxstyle=f"round,pad=0,rounding_size={s*0.18}",
                                ec=color, fc=SURFACE, lw=0.8, zorder=z))
    q = s * 0.26
    pts = {5: [(-q, -q), (q, q), (-q, q), (q, -q), (0, 0)], 3: [(-q, -q), (0, 0), (q, q)]}[pips]
    for dx, dy in pts:
        ax.add_patch(Circle((x + dx, y + dy), s * 0.08, fc=color, ec="none", zorder=z + 0.1))


def card(ax, x, y, w, h, color=INK, n=14, fill=SURFACE, z=5, lw=0.7, avatar=True, bar_colors=None):
    """An individual record: avatar + n attribute lines."""
    box(ax, x, y, w, h, ec=color, fc=fill, lw=lw, r=1.5, z=z)
    top = y + h - 2
    if avatar:
        person(ax, x + w * 0.22, top - h * 0.2, h * 0.17, color=color, z=z + 0.1)
        line(ax, [x + w * 0.42, x + w * 0.85], [top - h * 0.1] * 2, color=color, lw=0.8, z=z + 0.1)
        line(ax, [x + w * 0.42, x + w * 0.7], [top - h * 0.17] * 2, color=color, lw=0.8, z=z + 0.1)
        y0, y1 = y + 2, top - h * 0.26
    else:
        y0, y1 = y + 2, top
    rng = np.random.default_rng(3)
    for i in range(n):
        yy = y1 - (i + 0.5) * (y1 - y0) / n
        L = 0.35 + 0.45 * rng.random()
        c = bar_colors[i % len(bar_colors)] if bar_colors else color
        line(ax, [x + w * 0.12, x + w * (0.12 + L * 0.76)], [yy] * 2, color=c, lw=max(0.4, (y1 - y0) / n * 0.45), z=z + 0.1, cap="butt")


def schema_slots(ax, x, y, w, h, n=14, ec=SCHEMA, fc=SCHEMA_FILL, z=5, lw=0.7, filled=None):
    """The canonical schema: n fixed slots stacked vertically."""
    gap = h / n
    for i in range(n):
        f = filled[i] if filled is not None else fc
        ax.add_patch(FancyBboxPatch((x, y + i * gap + gap * 0.14), w, gap * 0.72,
                                    boxstyle=f"round,pad=0,rounding_size={gap*0.2}", ec=ec, fc=f, lw=lw, zorder=z))


def bubble(ax, x, y, w, h, color=INK, z=5, lines_=3, fill=SURFACE):
    """Speech bubble with wavy free-text lines; x,y lower-left."""
    box(ax, x, y, w, h, ec=color, fc=fill, lw=0.7, r=h * 0.25, z=z)
    ax.add_patch(Polygon([(x + w * 0.2, y + 0.3), (x + w * 0.12, y - h * 0.3), (x + w * 0.35, y + 0.3)],
                         closed=True, fc=fill, ec=color, lw=0.7, zorder=z + 0.05))
    line(ax, [x + w * 0.2, x + w * 0.35], [y + 0.3, y + 0.3], color=fill, lw=1.4, z=z + 0.06)
    for i in range(lines_):
        yy = y + h * (0.72 - i * 0.22)
        xs = np.linspace(x + w * 0.14, x + w * (0.86 - 0.18 * (i == lines_ - 1)), 30)
        line(ax, xs, yy + h * 0.035 * np.sin((xs - x) / w * 6 * np.pi), color=color, lw=0.6, z=z + 0.1)


def hist_overlap(ax, x, y, w, h, z=5, synth=None):
    """Population-level icon: reference bars (grey outline) vs synthetic bars (colour)."""
    ref = [0.55, 0.95, 0.7, 0.35, 0.2]
    syn = [0.25, 1.0, 0.95, 0.15, 0.05]
    n = len(ref)
    bw = w / n
    for i in range(n):
        ax.add_patch(Rectangle((x + i * bw + bw * 0.12, y), bw * 0.76, syn[i] * h, fc=synth or "#B3B3B3", ec="none", zorder=z))
        ax.add_patch(Rectangle((x + i * bw + bw * 0.12, y), bw * 0.76, ref[i] * h, fc="none", ec=REF, lw=0.9, zorder=z + 0.1))
    line(ax, [x - 1, x + w + 1], [y, y], color=INK, lw=0.6, z=z + 0.2)


def judge_icon(ax, x, y, s, z=5, color=INK):
    """Individual-level icon: one person under a magnifier."""
    person(ax, x - s * 0.12, y - s * 0.42, s * 0.62, color=color, z=z)
    ax.add_patch(Circle((x + s * 0.12, y + s * 0.02), s * 0.3, fc="none", ec=color, lw=1.1, zorder=z + 0.2))
    line(ax, [x + s * 0.33, x + s * 0.5], [y - s * 0.19, y - s * 0.4], color=color, lw=1.8, z=z + 0.2)


def coin_icon(ax, x, y, s, z=5, color=INK):
    """Operational icon: a coin with a currency mark."""
    ax.add_patch(Circle((x, y), s / 2, fc=SURFACE, ec=color, lw=0.9, zorder=z))
    ax.add_patch(Circle((x, y), s * 0.38, fc="none", ec=color, lw=0.4, zorder=z))
    T(ax, x, y - 0.2, "$", size=F9, color=color, weight="bold", zorder=z + 1)


def funnel_icon(ax, x, y, s, z=5, color=INK):
    ax.add_patch(Polygon([(x - s / 2, y + s / 2), (x + s / 2, y + s / 2), (x + s * 0.1, y - s * 0.05),
                          (x + s * 0.1, y - s / 2), (x - s * 0.1, y - s / 2), (x - s * 0.1, y - s * 0.05)],
                         closed=True, fc=SURFACE, ec=color, lw=0.9, zorder=z))


def cross(ax, x, y, s, color=MUTED_GREY, lw=0.8, z=6):
    line(ax, [x - s / 2, x + s / 2], [y - s / 2, y + s / 2], color=color, lw=lw, z=z)
    line(ax, [x - s / 2, x + s / 2], [y + s / 2, y - s / 2], color=color, lw=lw, z=z)


def badge(ax, x, y, s, r=6.5, fc=INK, color=SURFACE, size=F8):
    ax.add_patch(Circle((x, y), r, fc=fc, ec="none", zorder=8))
    T(ax, x, y, s, size=size, color=color, weight="bold", zorder=9)


def combo_grid(ax, x, y, cell, gap=1.0, marker="square", show_host=True, host_h=3.0):
    """13 x 5 grid: rows strategies A-E (top to bottom), columns models in published order.
    Withdrawn combinations crossed out, never dropped. Returns (x1, ytop)."""
    for j, m in enumerate(MODEL_ORDER):
        cx = x + j * (cell + gap)
        for i, s in enumerate(STRATEGIES):
            cy = y + (len(STRATEGIES) - 1 - i) * (cell + gap)
            if (s, m) in WITHDRAWN:
                ax.add_patch(Rectangle((cx, cy), cell, cell, fc=SURFACE, ec=RESIDUAL_GREY, lw=0.5, zorder=5))
                cross(ax, cx + cell / 2, cy + cell / 2, cell * 0.8, lw=0.7)
            elif marker == "square":
                ax.add_patch(Rectangle((cx, cy), cell, cell, fc=STRAT_COLOR[s], ec="none", zorder=5))
            else:
                ax.add_patch(Circle((cx + cell / 2, cy + cell / 2), cell * 0.45, fc=STRAT_COLOR[s], ec="none", zorder=5))
        if show_host:
            ytop = y + len(STRATEGIES) * (cell + gap)
            ax.add_patch(Rectangle((cx, ytop + 0.5), cell, host_h, fc=HOST[HOSTING[m]], ec="none", zorder=5))
    return x + len(MODEL_ORDER) * (cell + gap) - gap, y + len(STRATEGIES) * (cell + gap) - gap


def strategy_letters(ax, x, y, cell, gap=1.0, size=F8, ha="right"):
    for i, s in enumerate(STRATEGIES):
        cy = y + (len(STRATEGIES) - 1 - i) * (cell + gap) + cell / 2
        T(ax, x, cy, LETTERS[s], size=size, color=STRAT_COLOR[s], weight="bold", ha=ha)


def fmt(n):
    return f"{n:,}"
