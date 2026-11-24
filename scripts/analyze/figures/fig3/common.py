"""Figure 3 gallery: shared facts, colours and glyphs.

Every structural fact a prototype draws is read from the repository (strategy YAMLs, the
generator's own scheduler) or from the run outputs, and asserted here, so a prototype can never
draw a dependency, a step or a call count the code does not hold. Glyphs draw on one point-unit
axes (origin bottom-left), 456 pt wide.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import yaml
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle, Wedge

from population_synthetic.analysis.utils import style
from population_synthetic.analysis.utils.labels import attribute_label, method_letters
from population_synthetic.analysis.utils.palette import (
    BASELINE_DARK, GRID_RULE, MUTED_GREY, ORDERED_QUALITATIVE_SERIES, RESIDUAL_GREY,
    SECONDARY_GREY, SURFACE, BAND_FILL,
)
from population_synthetic.analysis.utils.registry import resolve_output_base
from population_synthetic.generators.synthetic.identity_generator_configurable import (
    IdentityGeneratorConfigurable,
)

REPO = Path(os.environ["POPSYNTH_REPO"])
GALLERY = Path(__file__).resolve().parent.parent
STRAT_DIR = REPO / "config" / "synthetic" / "axes" / "strategies"
W = style.TEXT_WIDTH * style.POINTS_PER_INCH  # 456 pt
H_CURRENT = 7.561791666666666 / 2.54 * 72      # current figure height in the docx: 214.4 pt

# ---------------------------------------------------------------- strategies (config)
_families = yaml.safe_load((STRAT_DIR / "_families.yaml").read_text(encoding="utf-8"))["families"]
STRATEGIES = [f"{f['id']}_v2" for f in _families]
LETTERS = method_letters(STRATEGIES)
assert [LETTERS[s] for s in STRATEGIES] == list("ABCDE")
_docs = {s: yaml.safe_load((STRAT_DIR / f"{s}.yaml").read_text(encoding="utf-8")) for s in STRATEGIES}
CONTEXT = {s: _docs[s].get("context", "cumulative") for s in STRATEGIES}
METHOD = {s: {c["method"] for c in _docs[s]["categories"].values()} for s in STRATEGIES}
assert all(len(m) == 1 for m in METHOD.values())
METHOD = {s: next(iter(m)) for s, m in METHOD.items()}
# steps per attribute, from the method token (category.py: PickCategory, GeneratePickCategory,
# GenerateEvaluatePickCategory, GenerateEvaluateRandomPickCategory)
_STEPS = {
    "pick": ["choose"],
    "generate_pick": ["list", "choose"],
    "generate_evaluate_pick": ["list", "weigh", "choose"],
    "generate_evaluate_random_pick": ["list", "weigh", "draw"],
}
STEPS = {s: _STEPS[METHOD[s]] for s in STRATEGIES}
HAS_CONTEXT = {s: CONTEXT[s] == "cumulative" for s in STRATEGIES}
assert [HAS_CONTEXT[s] for s in STRATEGIES] == [False, True, True, True, True]
assert [len(STEPS[s]) for s in STRATEGIES] == [1, 1, 2, 3, 3]

# ---------------------------------------------------------------- dependency graph (config + scheduler)
_cats = _docs["all_pick_dag_v2"]["categories"]
DEPS = {a: list(v["depends_on"]) for a, v in _cats.items()}
ORDER = IdentityGeneratorConfigurable._build_dag(_cats)  # the order prompts are resolved in
for s in STRATEGIES[1:]:
    assert {a: list(v["depends_on"]) for a, v in _docs[s]["categories"].items()} == DEPS, s
assert all(not v["depends_on"] for v in _docs["all_pick_v2"]["categories"].values())
assert len(ORDER) == 14


def _level(a, memo={}):
    if a not in memo:
        memo[a] = 1 + max((_level(d) for d in DEPS[a]), default=0)
    return memo[a]


LEVEL = {a: _level(a) for a in ORDER}
N_LEVELS = max(LEVEL.values())
assert N_LEVELS == 5
BY_LEVEL = {k: [a for a in ORDER if LEVEL[a] == k] for k in range(1, N_LEVELS + 1)}
assert [len(BY_LEVEL[k]) for k in BY_LEVEL] == [4, 3, 2, 3, 2]
# context seen by strategies B-E = every attribute resolved earlier (persona.py, context_mode
# "cumulative"; identity_generator_configurable.py docstring: "depends_on schedules only")
CONTEXT_SET = {a: ORDER[:i] for i, a in enumerate(ORDER)}

# Reference conditioning, read from generators/real/sweden/sample_service.py (sample_one):
# structural, not a distribution. Age and sex are one joint draw.
REF_COND = {
    "age": [], "biological_sex": ["age"], "region": [], "parental_structure": [],
    "birth_country_detail": ["age", "biological_sex"], "civil_status": ["age", "biological_sex"],
    "education_level": ["age", "biological_sex"], "household_size": [],
    "employment_status": ["age", "biological_sex", "education_level"],
    "employment_type": ["employment_status", "age", "biological_sex"],
    "industry_sector": ["employment_status", "age", "biological_sex"],
    "socioeconomic_class": ["age", "biological_sex"],
    "income_source": ["employment_status", "age"],
    "housing_tenure": ["age", "biological_sex"],
}
# ref-v3 (reference redrawn 2026-11-23, generators/real/sweden/sample_service.py of worktree reference-v3-corrections):
#  - region is drawn from the region table filtered on (age group, sex): "# Step 4 ... region conditional on (age_group, sex_label)"
#  - employment status is conditioned on (age group, sex) only, because the status-education merge is OFF
#    (emp_dist = employment_by_sex_education[cell]); education is no longer a parent.
REF_COND["region"] = ["age", "biological_sex"]
REF_COND["employment_status"] = ["age", "biological_sex"]
assert set(REF_COND) == set(ORDER)
# an attribute's LLM parents differ from its reference conditioning (sex: joint draw with age,
# counted as the same conditioning)
DIFFERS = {a: set(DEPS[a]) != set(REF_COND[a]) for a in ORDER}
DIFFERS["biological_sex"] = False
CURRENT_BLUE = {"household_size", "socioeconomic_class", "housing_tenure", "income_source"}

NAME = {a: attribute_label(a) for a in ORDER}

# ---------------------------------------------------------------- LLM calls per individual (run data)
_OUT = resolve_output_base(None)
_gm = pd.read_csv(_OUT / "03_Analysis" / "generation_metadata" / "swedish_02_summary.csv")
CALLS = {s: float(_gm.loc[_gm["method"] == s, "calls_median"].median()) for s in STRATEGIES}
assert [CALLS[s] for s in STRATEGIES] == [14, 14, 28, 42, 27], CALLS
# per attribute: E's numeric attribute (age) is one distribution call, so 13 x 2 + 1 = 27
LLM_CALLS_PER_ATTRIBUTE = {s: sum(st != "draw" for st in STEPS[s]) for s in STRATEGIES}
assert [LLM_CALLS_PER_ATTRIBUTE[s] for s in STRATEGIES] == [1, 1, 2, 3, 2]

# ---------------------------------------------------------------- colours
STRAT_COLOR = {s: ORDERED_QUALITATIVE_SERIES[i] for i, s in enumerate(STRATEGIES)}
SC = [STRAT_COLOR[s] for s in STRATEGIES]
INK = BASELINE_DARK
SOFT = SECONDARY_GREY
FAINT = RESIDUAL_GREY
RULE = GRID_RULE
PANEL = "#F2F2F2"        # neutral panel fill
NODE = "#FFFFFF"
REFC = "#4D4D4D"         # reference conditioning: neutral dark grey (no data hue)
F8, F9, F10, F11, F12 = 8.0, 9.0, 10.0, 11.0, 12.0


# ---------------------------------------------------------------- canvas / save
def canvas(h):
    from population_synthetic.analysis.utils.glyph_grid import PointCanvas
    c = PointCanvas(W, h)
    ax = c.figure.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(0, h)
    ax.set_aspect("equal")
    ax.axis("off")
    return c.figure, ax


def save(fig, name):
    from population_synthetic.analysis.utils.figures import save_figure
    png = GALLERY / f"F3_{name}.png"
    texts = [t for t in fig.findobj(lambda a: hasattr(a, "get_text") and hasattr(a, "get_fontsize"))
             if t.get_visible() and t.get_text().strip()]
    words = sum(len(t.get_text().replace("\n", " ").split()) for t in texts)
    for t in texts:
        assert "_" not in t.get_text(), t.get_text()
        assert 8.0 <= t.get_fontsize() <= 12.0, (t.get_text(), t.get_fontsize())
    if os.environ.get("F3DEBUG"):
        dbg = GALLERY / "code" / "debug"
        dbg.mkdir(exist_ok=True)
        fig.patch.set_edgecolor("red"); fig.patch.set_linewidth(1)
        fig.savefig(dbg / f"{name}.png", dpi=200)
        import matplotlib.pyplot as plt
        plt.close(fig)
        return dbg / f"{name}.png"
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


# ---------------------------------------------------------------- primitives
def T(ax, x, y, s, size=F8, color=INK, ha="center", va="center", weight="normal", **kw):
    return ax.text(x, y, s, fontsize=size, color=color, ha=ha, va=va, fontweight=weight, **kw)


def box(ax, x, y, w, h, ec=INK, fc=SURFACE, lw=0.8, r=3, ls="-", z=1):
    p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}", ec=ec, fc=fc, lw=lw,
                       ls=ls, zorder=z)
    ax.add_patch(p)
    return p


def line(ax, xs, ys, color=INK, lw=1.0, z=2, ls="-", cap="round"):
    ln = Line2D(xs, ys, color=color, lw=lw, zorder=z, ls=ls, solid_capstyle=cap)
    ax.add_line(ln)
    return ln


def arrow(ax, x0, y0, x1, y1, color=INK, lw=0.8, head=4.5, z=3, conn=None):
    a = FancyArrowPatch((x0, y0), (x1, y1),
                        arrowstyle=f"-|>,head_length={head*0.8},head_width={head*0.45}",
                        color=color, lw=lw, zorder=z, shrinkA=0, shrinkB=0,
                        connectionstyle=conn or "arc3", mutation_scale=1)
    ax.add_patch(a)
    return a


def panel_letter(ax, x, y, s):
    T(ax, x, y, s, size=F12, weight="bold", ha="left", va="top")


# ---------------------------------------------------------------- step glyphs (the visual vocabulary)
def chip(ax, x, y, s, color=INK, fill=SURFACE, label=True, z=6, lw=0.8, aspect=None):
    """An LLM call: chip with pins; a labelled chip is widened to hold 'LLM'."""
    b = s * 0.78
    show = label and s >= 14
    size = F8
    bw = max(b, text_width("LLM", size, "bold") + 4) if show else b
    bh = b * (0.8 if show else 1.0) if aspect is None else b * aspect
    ax.add_patch(FancyBboxPatch((x - bw / 2, y - bh / 2), bw, bh, boxstyle=f"round,pad=0,rounding_size={b*0.14}",
                                ec=color, fc=fill, lw=lw, zorder=z))
    pin = (s - b) / 2
    for k in (-1, 0, 1):
        ox = k * bw * 0.28
        oy = k * bh * 0.28
        for (xa, ya, xb, yb) in ((x + ox, y + bh / 2, x + ox, y + bh / 2 + pin),
                                 (x + ox, y - bh / 2, x + ox, y - bh / 2 - pin),
                                 (x + bw / 2, y + oy, x + bw / 2 + pin, y + oy),
                                 (x - bw / 2, y + oy, x - bw / 2 - pin, y + oy)):
            line(ax, [xa, xb], [ya, yb], color=color, lw=lw * 0.8, z=z - 0.1, cap="butt")
    if show:
        T(ax, x, y, "LLM", size=size, color=color, weight="bold", zorder=z + 1)


PICK_MARK = "check"   # the standard (approved 2026-10-21). pick_mark() keeps a "pointer" branch, not rendered


def pick_mark(ax, x, y, b, color=INK, z=7, kind=None):
    """The 'pick' type mark inside a call chip, drawn as paths (no font glyph)."""
    kind = kind or PICK_MARK
    if kind == "check":
        line(ax, [x - b * 0.28, x - b * 0.07, x + b * 0.30], [y + b * 0.01, y - b * 0.22, y + b * 0.24],
             color=color, lw=max(1.0, b * 0.12), z=z, cap="round")
    elif kind == "pointer":
        pts = [(-0.17, 0.33), (-0.17, -0.20), (-0.05, -0.09), (0.04, -0.31), (0.13, -0.27), (0.04, -0.06),
               (0.20, -0.06)]
        ax.add_patch(Polygon([(x + px * b, y + py * b) for px, py in pts], closed=True, fc=color, ec=color,
                             lw=0.4, joinstyle="miter", zorder=z))
    else:
        raise ValueError(f"unknown pick mark {kind!r}")


CALL_ASPECT = 0.8   # box height / width: the old labelled LLM chip's proportion (and the record card's)


def call_chip(ax, x, y, s, inner=None, color=INK, fill=SURFACE, z=6, lw=0.8):
    """One LLM call: the chip outline and pins of ``chip`` (unlabelled, box 0.78 s wide x 0.8 of that high, same pin geometry),
    typed by the icon drawn inside: 'list' (candidates), 'weigh' (probabilities), 'pick' (final pick), None (key)."""
    chip(ax, x, y, s, color=color, fill=fill, label=False, z=z, lw=lw, aspect=CALL_ASPECT)
    h = s * 0.78 * CALL_ASPECT   # inner icons scale with the box height
    if inner == "list":
        list_glyph(ax, x, y, h * 1.05, color=color, z=z + 0.5, frame=False)
    elif inner == "weigh":
        bars_glyph(ax, x + h * 0.03, y + h * 0.03, h * 1.0, color=color, z=z + 0.5, frame=False)
    elif inner == "pick":
        pick_mark(ax, x, y, h * 1.15, color=color, z=z + 0.5)
    elif inner is not None:
        raise ValueError(f"unknown chip content {inner!r}")


def die(ax, x, y, s, color=INK, z=6):
    """A random draw (code, not the LLM)."""
    ax.add_patch(FancyBboxPatch((x - s / 2, y - s / 2), s, s, boxstyle=f"round,pad=0,rounding_size={s*0.2}",
                                ec=color, fc=SURFACE, lw=0.8, zorder=z))
    q = s * 0.25
    for dx, dy in [(-q, -q), (q, q), (-q, q), (q, -q), (0, 0)]:
        ax.add_patch(Circle((x + dx, y + dy), s * 0.08, fc=color, ec="none", zorder=z + 0.1))


def list_glyph(ax, x, y, s, color=INK, z=6, fill=SURFACE, frame=True):
    """Candidate list: bullet + line rows."""
    if frame:
        box(ax, x - s / 2, y - s / 2, s, s, ec=color, fc=fill, lw=0.7, r=s * 0.12, z=z)
    for i in range(4):
        yy = y + s * (0.27 - i * 0.18)
        ax.add_patch(Circle((x - s * 0.26, yy), s * 0.045, fc=color, ec="none", zorder=z + 0.1))
        line(ax, [x - s * 0.15, x + s * (0.3 - 0.08 * (i % 2))], [yy, yy], color=color, lw=0.7, z=z + 0.1)


def bars_glyph(ax, x, y, s, color=INK, z=6, fill=SURFACE, frame=True):
    """Probabilities: a small bar distribution."""
    if frame:
        box(ax, x - s / 2, y - s / 2, s, s, ec=color, fc=fill, lw=0.7, r=s * 0.12, z=z)
    hs = [0.62, 0.38, 0.22, 0.12]
    bw = s * 0.14
    x0 = x - s * 0.3
    for i, h in enumerate(hs):
        ax.add_patch(Rectangle((x0 + i * bw * 1.35, y - s * 0.3), bw, h * s, fc=color, ec="none", zorder=z + 0.1))


def context_glyph(ax, x, y, s, color=INK, z=6, filled=3, n=3, fill=SURFACE):
    """Context: an individual's record card (head + filled rows = attributes already set)."""
    w, h = s * 1.0, s * 0.8
    box(ax, x - w / 2, y - h / 2, w, h, ec=color, fc=fill, lw=0.7, r=s * 0.1, z=z)
    ax.add_patch(Circle((x - w * 0.24, y + h * 0.08), s * 0.11, fc=color, ec="none", zorder=z + 0.1))
    ax.add_patch(Wedge((x - w * 0.24, y - h * 0.32), s * 0.2, 0, 180, fc=color, ec="none", zorder=z + 0.1))
    for i in range(n):
        yy = y + h * 0.22 - i * h * 0.22
        c_ = color if i < filled else FAINT
        line(ax, [x - w * 0.02, x + w * 0.36], [yy, yy], color=c_, lw=max(0.6, s * 0.07), z=z + 0.1, cap="butt")


def query_glyph(ax, x, y, s, color=INK, z=6, fill=SURFACE):
    """The attribute request: a question bubble."""
    box(ax, x - s / 2, y - s * 0.35, s, s * 0.7, ec=color, fc=fill, lw=0.7, r=s * 0.2, z=z)
    ax.add_patch(Polygon([(x - s * 0.2, y - s * 0.35), (x - s * 0.3, y - s * 0.55), (x - s * 0.05, y - s * 0.35)],
                         closed=True, fc=fill, ec=color, lw=0.7, zorder=z + 0.05))
    line(ax, [x - s * 0.19, x - s * 0.06], [y - s * 0.35, y - s * 0.35], color=fill, lw=1.2, z=z + 0.06)
    T(ax, x, y, "?", size=F9, color=color, weight="bold", zorder=z + 1)


def pill(ax, x, y, w, h, text, color=INK, fc=SURFACE, size=F8, z=6, ls="-", lw=0.8, weight="normal"):
    box(ax, x - w / 2, y - h / 2, w, h, ec=color, fc=fc, lw=lw, r=h / 2, ls=ls, z=z)
    T(ax, x, y, text, size=size, color=INK, weight=weight, zorder=z + 1)


def letter(ax, x, y, s, size=F10, ha="center"):
    T(ax, x, y, LETTERS[s], size=size, color=STRAT_COLOR[s], weight="bold", ha=ha)


def step_glyph(ax, kind, x, y, s, color=INK):
    {"list": list_glyph, "weigh": bars_glyph, "choose": chip, "draw": die,
     "context": context_glyph, "query": query_glyph}[kind](ax, x, y, s, color=color)


def text_width(s, size=F8, weight=None):
    return style.text_width_inches(s, fontsize=size, weight=weight) * 72
