"""Figure 5: A) atypicality (10 - judge typicality) distribution grid, B) worst clash per individual.

Panel A redraws realism_ranking's typicality_distribution block (realism_ranking.json,
the same data plot_typicality_distribution_grid draws, shown as atypicality = 10 - typicality
per persona, ramp reversed so colours are unchanged) on the docx composite layout
(typicality_distribution_by_model_strategy_02.svg): legend and colourbar title moved to
the top right, "common" (0)/"rarest" (10) colourbar annotations, no bottom note/key.

Panel B rebuilds the docx's scratch figure severity_worst_clash_by_model_strategy (its
script is lost; the geometry, colours and text are read off its matplotlib SVG): one
4-bar mini histogram per combination -- each judged individual counted once at the rank
of its worst clash (persona_realism <combo>_personas.csv column max_severity; empty =
no clash), square-root heights, the reference's distribution as the step outline, and
the counts of rank-2 and rank-3 individuals printed top right (R1-R3 in inferno steps, see b_color).

Drawn with the repo presentation layer (glyph_grid PointCanvas, draw_mini_histogram,
draw_withdrawn_cell, draw_ternary, stepped_colorbar; palette; labels).
"""
from __future__ import annotations

import json
import textwrap
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import common
from population_synthetic.analysis.utils.glyph_grid import (
    REFERENCE_OUTLINE_WIDTH, TERNARY_HEIGHT_RATIO, PointCanvas, draw_mini_histogram, draw_ternary,
    draw_withdrawn_cell, outline_handle, step_colors, stepped_colorbar, swatch_handle, withdrawn_handle,
)
from population_synthetic.analysis.utils.labels import figure_term, method_letters, worst_clash_label
from population_synthetic.analysis.utils.palette import (
    BASELINE_DARK, HOST_COLORS, heatmap_levels, worst_clash_color,
)
from population_synthetic.analysis.utils.style import (
    FIGURE_TITLE, HEADING_WEIGHT, LEGEND_LABEL, TICK_LABEL, TICK_LABEL_LARGE,
)

W = 456.0
CELL, COL_PITCH, ROW_PITCH = 26.5, 28.0, 29.5
GRID_X0 = 16.7
REF_X0 = 357.2
TERN_X0, TERN_PAD = 390.5, 1.5
CBAR_X0, CBAR_W = 429.3, 7.0
LETTER_RIGHT = GRID_X0 - 1.9
LEG_SWATCH_X, LEG_TEXT_GAP = 385.5, 3.0
LABEL_GAP = 1.5            # 2026-10-20: was 2.0, which put the top of "Mistral Medium 3.5" ~0.1 pt past the canvas edge
LEGEND_SPACE = 4.0         # the gap between the R1-R3 ladder and the off-ladder categories
LEGEND_FITS = 16           # a legend label longer than this reaches the fixed canvas edge ...
LEGEND_WRAP = 12           # ... and is wrapped to lines of at most this many characters
LEGEND_LINE = 8.6          # the extra height of each wrapped legend line
TOP_BLOCK = 69.0           # column labels above panel A's grid
A_TO_B = 17.7              # gap between panel A's last row and panel B's first row
BAND_LABELS = ("0–4", "5–7", "8–10")   # the block's typicality bands (checked on load)
# noC inspection variants: 'excluded' drops C individuals from each cell's denominator;
# 'gap' keeps the denominator (C mass is simply not drawn).
NOC_MODE = next(a.split('=', 1)[1] for a in sys.argv if a.startswith('--noc='))
if NOC_MODE not in ('excluded', 'gap'):
    raise ValueError(NOC_MODE)
# 2026-10-20 (d): the categories left out of panel B and out of each cell's denominator are read from
# realism_ranking.json (clash_analysis.excluded_categories, i.e. worst_clash_split.yaml
# clash_analysis.excluded), not hard-coded: now class C and pipeline. Set in Split.__init__.
EXCLUDED: frozenset = frozenset()
# Excluded variant: a fixed count band at the top of every panel-B cell. Counts keep their
# baseline (7.05 pt below the cell top, TICK_LABEL bold); every bar and the reference outline
# end at least COUNT_CLEAR pt below that baseline, by raising the y-limit of the (sqrt-scaled)
# axes so value 1.0 lands at CELL - COUNT_DROP - COUNT_CLEAR pt. A centred digit's ink is
# ~3.9 pt wide in a 6.3 pt bin, so the side gap to a neighbouring bar is only ~1.2 pt and the
# clearance has to be vertical.
COUNT_DROP, COUNT_CLEAR = 7.05, 2.5
# 2026-10-20 (d): panel letters 1 pt inside the canvas (the "A." touched the top and left edges), as in Figure 6.
LETTER_INSET = 1.0
# 2026-10-20 (e): panel B's legend touched the Reference column (0.4 pt). It now starts B_LEG_GAP pt right of
# that column; to stay inside 456 pt its swatches are square (handlelength 0.8 em = 6.4 pt, the house
# handleheight) instead of 1.4 em. Panel A's legend is unchanged.
B_LEG_GAP = 7.8   # nominal; the drawn ink gap is ~7.0 pt (legend handles start ~0.6 pt left of x)
B_HANDLELENGTH = 0.8

# Panel A shows ATYPICALITY = 10 - judge typicality, transformed per persona at plot time
# (a reversal of the 0..10 mass vector; no statistic is recomputed). The ramp is reversed
# with it, so every persona keeps its colour: common = yellow, rarest = near-black.
N_SCORE = 10
ATYP_BAND_LABELS = ("0–2", "3–5", "6–10")  # = typicality 8–10, 5–7, 0–4 (same persona groups)


def atypicality(mass):
    """Per-persona 10 - typicality: the mass at typicality t moves to atypicality 10 - t."""
    mass = list(mass)
    if len(mass) != N_SCORE + 1:
        raise ValueError(f"expected an {N_SCORE + 1}-level score mass, got {len(mass)}")
    return mass[::-1]


def atypicality_bands(shares):
    """Typicality band shares (0–4, 5–7, 8–10) as the ternary triple (BL, BR, apex) =
    atypicality (3–5, 6–10, 0–2): apex stays the common group, base runs low -> high left to right."""
    s04, s57, s810 = shares
    return [s57, s04, s810]


# Panel B colours: a presentation-only override of palette.WORST_CLASH_COLORS (the repo is
# untouched). R1-R3 are three steps of panel A's own inferno ramp, darker with severity, at
# the atypicality steps 3 / 6 / 8 of the 11-step colourbar; C leaves the R gradient for the
# Okabe-Ito bluish green (sky blue #56B4E9 is too light as text on white, 2.3:1).
_STEPS = None


def _atyp_step(a):
    global _STEPS
    if _STEPS is None:
        _STEPS = step_colors(heatmap_levels(N_SCORE + 1))  # index = typicality
    return _STEPS[N_SCORE - a]


B_COLOR_OVERRIDES = {"S1": 3, "S2": 6, "r3_impossible": 8, "c_scb_category_limitation": "#009E73"}


def b_color(category):
    v = B_COLOR_OVERRIDES.get(category)
    if v is None:
        return worst_clash_color(category)
    return _atyp_step(v) if isinstance(v, int) else v


# Worst-clash levels, low to high (unsplit panel B): the unsplit R3 takes the split R3's colour.
LEVELS = ("none", "S1", "S2", "S3")
LEVEL_COLORS = [b_color("none"), b_color("S1"), b_color("S2"), b_color("r3_impossible")]
LEVEL_LABELS = ("no clash", "R1: unusual", "R2: implausible", "R3: impossible")


def load():
    rr = json.load(open(common.adir("realism_ranking") / common.COUNTRY / "realism_ranking.json", encoding="utf-8"))
    block = rr["typicality_distribution"]
    if rr["provenance"]["n_rounds"] != 1:
        raise ValueError("manuscript basis is one judge round")
    grid = block["grid"]
    if [*block["bands"]["labels"]] != list(BAND_LABELS):
        raise ValueError(f"band labels changed: {block['bands']['labels']}")

    pr = common.adir("persona_realism") / common.COUNTRY
    # 2026-10-20: skip the stage-2 sidecars (<combo>_stage2_personas.csv, one row per S3
    # individual, no slug column), which the glob also matches; they dropped out of the
    # groupby on slug before, so no count changes.
    frames = [pd.read_csv(p) for p in pr.glob("*/*_personas.csv") if not p.name.endswith("_stage2_personas.csv")]
    personas = pd.concat(frames, ignore_index=True)
    personas["worst"] = personas["max_severity"].fillna("none")
    bad = set(personas["worst"]) - set(LEVELS)
    if bad:
        raise ValueError(f"unknown max_severity values {bad}")
    counts = personas.groupby(["slug", "worst"]).size().unstack(fill_value=0).reindex(columns=list(LEVELS), fill_value=0)
    meta = personas.drop_duplicates("slug").set_index("slug")[["model", "strategy", "is_real_reference"]]
    return rr, grid, counts, meta, personas


def worst_clash_cells(grid, counts, meta):
    """{(model, strategy): counts over LEVELS} for every judged combination, + the reference."""
    cells = {}
    real = None
    for slug, row in counts.iterrows():
        m = meta.loc[slug]
        if bool(m["is_real_reference"]):
            real = row.to_numpy(dtype=int)
        else:
            cells[(m["model"], m["strategy"])] = row.to_numpy(dtype=int)
    ok = {(mo, s) for mo in grid["models"] for s in grid["methods"] if grid["states"][mo][s] == "ok"}
    if set(cells) != ok:
        raise ValueError(f"judged clash combinations {sorted(set(cells) ^ ok)} disagree with the typicality grid")
    if real is None:
        raise ValueError("no reference in the persona_realism outputs")
    return cells, real


class Split:
    """realism_ranking's ``worst_clash_split`` block, arranged for drawing (no statistic computed).

    ``shown`` are the categories drawn and listed: every category of the block, except that a
    category the block's ``display.only_when_nonzero`` names (the unsplit R3, pipeline) is kept
    only when some count handed to the figure (a combination or the reference) is non-zero.
    ``syn_bins`` are the bins of a combination cell (= ``shown``); ``ref_bins`` the reference's
    own (none/S1/S2 and, when shown, the unsplit R3: no free text, never split). ``r3_bins`` is
    the run of bins whose individuals the judge put at S3 (R3, R3 not split, C), across which the
    reference's R3 share is outlined. ``ladder`` / ``off_ladder`` order the legend: the R1-R3
    ladder, a gap, then the block's ``display.off_ladder`` categories (C, pipeline).
    """

    def __init__(self, rr, grid):
        block = rr.get("worst_clash_split")
        if not block:
            raise ValueError("realism_ranking.json has no worst_clash_split block (stage 2 missing); "
                             "re-run the ranking after the stage-2 judge run")
        cats = list(block["categories"])
        split = block["s3_split"]
        display = block["display"]
        unsplit = split["not_applicable_no_free_text"]
        if split["unclassified"] != unsplit:
            raise ValueError("unclassified and not-applicable S3 must share the unsplit category")
        pipe = {split["mapping_error"], split["judge_error"]}
        if len(pipe) != 1:
            raise ValueError(f"mapping_error and judge_error map to different buckets {pipe}")
        self.pipeline = pipe.pop()
        self.unsplit = unsplit
        self.cells, self.ref = {}, None
        for row in block["competitors"]:
            counts = row["counts"]
            if row["is_real_reference"]:
                if any(counts[c] for c in cats if c not in ("none", "S1", "S2", unsplit)):
                    raise ValueError("the reference carries a split R3 category; it has no free text")
                self.ref = counts
            else:
                self.cells[(row["model"], row["strategy"])] = counts
        ok = {(mo, s) for mo in grid["models"] for s in grid["methods"] if grid["states"][mo][s] == "ok"}
        if set(self.cells) != ok:
            raise ValueError(f"split combinations {sorted(set(self.cells) ^ ok)} disagree with the typicality grid")
        if self.ref is None:
            raise ValueError("no reference in the worst_clash_split block")
        # Omit-when-zero: a check on the counts given, nothing derived from them.
        given = [*self.cells.values(), self.ref]
        optional = set(display["only_when_nonzero"])
        self.shown = [c for c in cats if c not in optional or any(counts[c] for counts in given)]
        off = set(display["off_ladder"])
        self.ladder = [c for c in self.shown if c not in off]
        self.off_ladder = [c for c in self.shown if c in off]
        global EXCLUDED
        excl = rr["clash_analysis"]["excluded_categories"]
        if sorted(excl) != sorted(block["clash_analysis_excluded"]):
            raise ValueError(f"clash_analysis.excluded_categories {excl} != worst_clash_split.clash_analysis_excluded")
        if not set(excl) <= set(cats):
            raise ValueError(f"excluded categories {excl} are not worst-clash categories {cats}")
        EXCLUDED = frozenset(excl)
        self.excluded = EXCLUDED
        self.shown = [c for c in self.shown if c not in EXCLUDED]
        self.ladder = [c for c in self.ladder if c not in EXCLUDED]
        self.off_ladder = [c for c in self.off_ladder if c not in EXCLUDED]
        # Each cell's denominator must be the clash analysis's own n (judged minus excluded).
        n_by_slug = {r["slug"]: r["n"] for r in rr["clash_analysis"]["competitors"]}
        rows = block["competitors"]
        if len(n_by_slug) != len(rows):
            raise ValueError("clash_analysis and worst_clash_split cover different competitors")
        for row in rows:
            own_n = sum(row["counts"].values()) - sum(row["counts"][c] for c in EXCLUDED)
            if own_n != n_by_slug[row["slug"]]:
                raise ValueError(f"{row['slug']}: denominator {own_n} != clash_analysis n {n_by_slug[row['slug']]}")
        self.n_checked = len(rows)
        self.syn_bins = list(self.shown)
        self.ref_bins = [c for c in ("none", "S1", "S2", unsplit) if c in self.shown]
        self.r3_bins = [c for c in self.shown if c not in ("none", "S1", "S2", self.pipeline)]

    def vector(self, counts, bins):
        total = sum(counts.values())
        if NOC_MODE == 'excluded':
            total -= sum(counts[c] for c in EXCLUDED)
        missing = sum(n for c, n in counts.items() if c not in bins and c not in EXCLUDED)
        if missing:
            raise ValueError(f"{missing} individual(s) fall in categories not drawn {bins}")
        return np.array([counts[c] for c in bins], dtype=float) / total


def _reserve_count_band(ax):
    frac = (CELL - COUNT_DROP - COUNT_CLEAR) / CELL   # axes fraction at which value 1.0 sits
    ax.set_ylim(0.0, 1.0 / frac ** 2)                 # sqrt scale: sqrt(1 / ymax) = frac


def _hist(ax, mass, colors):
    if NOC_MODE == 'excluded':
        draw_mini_histogram(ax, mass, colors)
        _reserve_count_band(ax)
        return
    from population_synthetic.analysis.utils.glyph_grid import HISTOGRAM_X_MARGIN, _bare
    mass = np.asarray(mass, dtype=float)
    if mass.sum() > 1 + 1e-9 or (mass < 0).any() or len(colors) != mass.size:
        raise ValueError(mass)
    n = mass.size
    ax.bar(np.arange(n), mass, width=1.0, color=list(colors), edgecolor="none")
    ax.set_yscale("function", functions=(np.sqrt, np.square))
    ax.set_xlim(-0.5 - HISTOGRAM_X_MARGIN, n - 0.5 + HISTOGRAM_X_MARGIN)
    ax.set_ylim(0.0, 1.0)
    _bare(ax)


def _outline_split(ax, split):
    """The reference over none/S1/S2, and its unsplit R3 share (zero when omitted) as one rule over the R3 bins."""
    ref = split.vector(split.ref, split.ref_bins)
    steps = [*ref[:3], ref[3] if len(ref) > 3 else 0.0]
    for i, value in enumerate(steps[:3]):
        ax.hlines(value, i - 0.5, i + 0.5, color=BASELINE_DARK, linewidth=REFERENCE_OUTLINE_WIDTH, zorder=3)
    lo = split.syn_bins.index(split.r3_bins[0]) - 0.5
    hi = split.syn_bins.index(split.r3_bins[-1]) + 0.5
    ax.hlines(steps[3], lo, hi, color=BASELINE_DARK, linewidth=REFERENCE_OUTLINE_WIDTH, zorder=3)
    for i in range(3):  # the risers between adjacent outline steps
        nxt = steps[i + 1]
        ax.vlines(i + 0.5, min(steps[i], nxt), max(steps[i], nxt), color=BASELINE_DARK,
                  linewidth=REFERENCE_OUTLINE_WIDTH, zorder=3)


def _mass(c):
    c = np.asarray(c, dtype=float)
    return c / c.sum()


class Layout:
    def __init__(self, panels):
        self.panels = panels
        n = 5
        grid_h = n * CELL + (n - 1) * (ROW_PITCH - CELL)
        tops = {}
        y = TOP_BLOCK
        if "A" in panels:
            tops["A"] = y
            y += grid_h + (A_TO_B if "B" in panels else 0.0)
        if "B" in panels:
            tops["B"] = y
            y += grid_h
        self.height = y + 0.6
        self.tops = tops

    def row(self, panel, i):  # (bottom, top) in canvas points (origin bottom-left)
        top_from_top = self.tops[panel] + i * ROW_PITCH
        return self.height - top_from_top - CELL, self.height - top_from_top


def draw(panels=("A", "B"), split=False):
    rr, grid, counts, meta, personas = load()
    sp = Split(rr, grid) if split else None
    models = common.ranked_models()
    if set(models) != set(grid["models"]):
        raise ValueError("ranked models differ from the realism grid's models")
    methods = list(grid["methods"])
    letters = method_letters(methods)
    names = common.display_models(models)
    hosting = common.hosting_classes()
    ref_term = figure_term("reference")
    clash_cells, clash_ref = worst_clash_cells(grid, counts, meta)

    L = Layout(panels)
    canvas = PointCanvas(W, L.height)
    H = L.height
    colx = [GRID_X0 + j * COL_PITCH for j in range(len(models))]

    # Column labels, once, above the first panel.
    first = panels[0]
    label_y = H - L.tops[first] + LABEL_GAP
    for x0, m in zip(colx, models):
        canvas.text(x0 + CELL / 2, label_y, names[m], fontsize=TICK_LABEL, rotation=90, ha="center",
                    va="bottom", color=HOST_COLORS[hosting[m]])
    canvas.text(REF_X0 + CELL / 2, label_y, ref_term, fontsize=TICK_LABEL, rotation=90, ha="center",
                va="bottom", color=BASELINE_DARK)

    def panel_frame(panel, letter_top):
        if len(panels) > 1:
            canvas.text(LETTER_INSET, H - letter_top - LETTER_INSET, f"{panel}.", fontsize=FIGURE_TITLE, fontweight=HEADING_WEIGHT,
                        ha="left", va="top", color=BASELINE_DARK)
        y_mid = (L.row(panel, 0)[1] + L.row(panel, 4)[0]) / 2
        canvas.text(0.0, y_mid, "strategy", fontsize=TICK_LABEL, rotation=90, ha="left", va="center",
                    color=BASELINE_DARK)
        for i, s in enumerate(methods):
            b, t = L.row(panel, i)
            canvas.text(LETTER_RIGHT, (b + t) / 2, letters[s], fontsize=TICK_LABEL_LARGE, fontweight=HEADING_WEIGHT,
                        ha="right", va="center", color=BASELINE_DARK)

    def legend(entries, top_from_top, dx=0.0, handlelength=None):
        y = H - top_from_top
        for kind, label, payload in entries:
            if kind == "space":
                pass
            elif kind == "title":
                canvas.text(LEG_SWATCH_X + dx, y, label, fontsize=LEGEND_LABEL, ha="left", va="center", color="black")
            elif handlelength is None:
                canvas.legend([payload], x=LEG_SWATCH_X + dx - 0.2, y_top=y + 5.2, ncol=1)
            else:  # canvas.legend with only the handle length changed (glyph_grid's own spacing otherwise)
                from population_synthetic.analysis.utils.glyph_grid import _LEGEND_SPACING
                spacing = dict(_LEGEND_SPACING, handlelength=handlelength)
                canvas.figure.legend(handles=[payload], loc="upper left", ncol=1, fontsize=LEGEND_LABEL,
                                     frameon=False, bbox_to_anchor=((LEG_SWATCH_X + dx - 0.2) / W, (y + 5.2) / H),
                                     **spacing)
            y -= step(kind, label)

    def step(kind, label):
        return {"gap": 0.0, "space": LEGEND_SPACE}.get(kind, 10.6 + LEGEND_LINE * label.count(chr(10)))

    def legend_height(entries):
        return sum(step(kind, label) for kind, label, _ in entries)

    if "A" in panels:
        n_levels = int(rr["typicality_distribution"]["n_levels"])
        if n_levels != N_SCORE + 1:
            raise ValueError(f"atypicality = {N_SCORE} - typicality assumes {N_SCORE + 1} levels, got {n_levels}")
        levels = heatmap_levels(n_levels).reversed()  # atypicality a gets typicality 10-a's colour
        colors = step_colors(levels)
        real = grid["real"]
        ref = atypicality(real["distribution"])
        panel_frame("A", 0.0)
        tside = (CELL - 2 * TERN_PAD) / TERNARY_HEIGHT_RATIO
        for i, s in enumerate(methods):
            b, t = L.row("A", i)
            for x0, m in zip(colx, models):
                ax = canvas.axes(x0, b, x0 + CELL, t)
                st = grid["states"][m][s]
                if st == "ok":
                    draw_mini_histogram(ax, atypicality(grid["cells"][m][s]["distribution"]), colors, outline=ref)
                elif st == "withdrawn":
                    draw_withdrawn_cell(ax)
                else:
                    raise ValueError(f"unexpected cell state {st} for {m} x {s}")
            draw_mini_histogram(canvas.axes(REF_X0, b, REF_X0 + CELL, t), ref, colors)
            shown = [m for m in models if grid["states"][m][s] == "ok"]
            ty0 = b + TERN_PAD
            draw_ternary(
                canvas.axes(TERN_X0, ty0, TERN_X0 + tside, ty0 + tside * TERNARY_HEIGHT_RATIO),
                [atypicality_bands(grid["cells"][m][s]["band_shares"]) for m in shown],
                atypicality_bands(real["band_shares"]),
                point_colors=[HOST_COLORS[hosting[m]] for m in shown], apex_guides=(0.5,),
                apex_label=ATYP_BAND_LABELS[0] if i == 0 else None,
                base_labels=(ATYP_BAND_LABELS[1], ATYP_BAND_LABELS[2]) if i == 0 else None,
            )
        cb_box = (CBAR_X0, L.row("A", 4)[0], CBAR_X0 + CBAR_W, L.row("A", 0)[1])
        stepped_colorbar(canvas, cb_box, levels, n_levels, "Atypicality")
        title = canvas.figure.texts[-1]
        title.set_ha("center")
        title.set_x((CBAR_X0 + CBAR_W / 2 + 3.0) / W)
        text_x = CBAR_X0 + CBAR_W + 15.8
        # Atypicality runs 0 (bottom, yellow) to 10 (top, near-black).
        canvas.text(text_x, cb_box[3], "rarest", fontsize=TICK_LABEL, rotation=90, ha="center", va="top",
                    color=BASELINE_DARK)
        canvas.text(text_x, cb_box[1], "common", fontsize=TICK_LABEL, rotation=90, ha="center", va="bottom",
                    color=BASELINE_DARK)
        legend([("h", "", swatch_handle("hosted (API)", color=HOST_COLORS["hosted"])),
                ("h", "", swatch_handle("locally served", color=HOST_COLORS["local"]))], 30.3)

    if "B" in panels and sp is not None:
        panel_frame("B", L.tops["B"] - 10.8)
        syn_colors = [b_color(c) for c in sp.syn_bins]
        ref_colors = [b_color(c) for c in sp.ref_bins]
        # Severest first: R3, R3 not split (when shown), C, then R2.
        lines = [c for c in sp.r3_bins if c in sp.ladder] + [c for c in sp.r3_bins if c in sp.off_ladder] + ["S2"]
        for i, s in enumerate(methods):
            b, t = L.row("B", i)
            for x0, m in zip(colx, models):
                ax = canvas.axes(x0, b, x0 + CELL, t)
                if grid["states"][m][s] == "withdrawn":
                    draw_withdrawn_cell(ax)
                    continue
                cell = sp.cells[(m, s)]
                _hist(ax, sp.vector(cell, sp.syn_bins), syn_colors)
                _outline_split(ax, sp)
                if NOC_MODE == 'excluded':
                    _counts_bins(canvas, x0, t, sp.syn_bins, [(c, cell[c]) for c in lines])
                else:
                    _counts_lines(canvas, x0, t, [(cell[c], b_color(c)) for c in lines])
            # Excluded variant: the reference uses the model cells' four bins (its R3 slot is
            # an empty zero), so its bars line up column-for-column with theirs.
            rbins, rcolors = (sp.syn_bins, syn_colors) if NOC_MODE == 'excluded' else (sp.ref_bins, ref_colors)
            _hist(canvas.axes(REF_X0, b, REF_X0 + CELL, t), sp.vector(sp.ref, rbins), rcolors)
            if NOC_MODE == 'excluded':
                _counts_bins(canvas, REF_X0, t, rbins, [(c, sp.ref[c]) for c in [*sp.ref_bins[3:], "S2"]])
            else:
              _counts_lines(canvas, REF_X0, t, [(sp.ref[c], b_color(c)) for c in sp.ref_bins[3:]]
                          + [(sp.ref["S2"], b_color("S2"))])
        t0 = L.tops["B"]
        def item(c):
            label = worst_clash_label(c)  # layout only below: the words are config's
            text = label if len(label) <= LEGEND_FITS else textwrap.fill(label, LEGEND_WRAP)
            return ("h", text, swatch_handle(text, color=b_color(c)))

        entries = [item("none"), ("title", figure_term("worst_clash_title"), None)]
        entries += [item(c) for c in sp.ladder if c != "none"]
        if sp.off_ladder:  # not ranks of the ladder: set apart after it
            entries += [("space", "", None)] + [item(c) for c in sp.off_ladder]
        bdx = REF_X0 + CELL + B_LEG_GAP - LEG_SWATCH_X  # swatch left edge B_LEG_GAP pt right of the Reference column
        legend(entries, t0 + 3.0, dx=bdx, handlelength=B_HANDLELENGTH)
        legend([("h", "", outline_handle(ref_term)), ("h", "", withdrawn_handle("withdrawn"))],
               t0 + 3.0 + legend_height(entries) + 4.5, dx=bdx, handlelength=B_HANDLELENGTH)
        print("panel B: categories drawn", sp.shown, "| excluded from drawing and denominators:",
              sorted(sp.excluded), "| denominators equal clash_analysis n in", sp.n_checked, "cells")
    elif "B" in panels:
        panel_frame("B", L.tops["B"] - 10.8)
        ref_mass = _mass(clash_ref)
        for i, s in enumerate(methods):
            b, t = L.row("B", i)
            for x0, m in zip(colx, models):
                ax = canvas.axes(x0, b, x0 + CELL, t)
                st = grid["states"][m][s]
                if st == "withdrawn":
                    draw_withdrawn_cell(ax)
                    continue
                c = clash_cells[(m, s)]
                draw_mini_histogram(ax, _mass(c), LEVEL_COLORS, outline=ref_mass)
                _counts(canvas, x0, t, c)
            draw_mini_histogram(canvas.axes(REF_X0, b, REF_X0 + CELL, t), ref_mass, LEVEL_COLORS)
            _counts(canvas, REF_X0, t, clash_ref)
        t0 = L.tops["B"]
        entries = [("h", "", swatch_handle(LEVEL_LABELS[0], color=LEVEL_COLORS[0])),
                   ("title", "Atypicality rank:", None)]
        entries += [("h", "", swatch_handle(lab, color=col)) for lab, col in zip(LEVEL_LABELS[1:], LEVEL_COLORS[1:])]
        legend(entries, t0 + 3.0)
        legend([("h", "", outline_handle(ref_term)), ("h", "", withdrawn_handle("withdrawn"))], t0 + 3.0 + 5 * 10.6 + 4.5)
    return canvas.figure, clash_cells, clash_ref


def _counts_bins(canvas, x0, top, bins, values):
    """Excluded variant: each non-zero count centred over its own bar, all on the first line
    (same baseline and type as _counts_lines); x from the histogram's own data -> point mapping."""
    from population_synthetic.analysis.utils.glyph_grid import HISTOGRAM_X_MARGIN
    lo, hi = -0.5 - HISTOGRAM_X_MARGIN, len(bins) - 0.5 + HISTOGRAM_X_MARGIN
    for c, n in values:
        if n > 0:
            x = x0 + CELL * (bins.index(c) - lo) / (hi - lo)
            canvas.text(x, top - COUNT_DROP, str(int(n)), fontsize=TICK_LABEL, fontweight=HEADING_WEIGHT,
                        ha="center", va="baseline", color=b_color(c))


def _counts_lines(canvas, x0, top, values):
    """Non-zero counts, one per line from the top right, each in its category colour."""
    right = x0 + CELL - 0.8
    line = 0
    for n, color in values:
        if n > 0:
            canvas.text(right, top - 7.05 - 7.15 * line, str(int(n)), fontsize=TICK_LABEL,
                        fontweight=HEADING_WEIGHT, ha="right", va="baseline", color=color)
            line += 1


def _counts(canvas, x0, top, c):
    """Rank-3 (red, first line) and rank-2 (orange, second line) counts, when non-zero."""
    right = x0 + CELL - 0.8
    if c[3] > 0:
        canvas.text(right, top - 7.05, str(int(c[3])), fontsize=TICK_LABEL, fontweight=HEADING_WEIGHT,
                    ha="right", va="baseline", color=LEVEL_COLORS[3])
    if c[2] > 0:
        canvas.text(right, top - 14.2, str(int(c[2])), fontsize=TICK_LABEL, fontweight=HEADING_WEIGHT,
                    ha="right", va="baseline", color=LEVEL_COLORS[2])


def main():
    if "--split" in sys.argv:
        # Draft: panel B with R3 split by stage 2 (realism_ranking worst_clash_split block).
        # Written beside the published stems, never over them.
        for stem, panels in (("fig5_split", ("A", "B")), ("fig5B_split", ("B",))):
            with plt.rc_context(common.rc()):
                fig, cells, ref = draw(panels, split=True)
                out = common.save(fig, stem)
            print(out[0])
        return
    # Published stems (2026-10-05): panel B is the stage-2 split (R3 / C, pipeline and
    # "R3 not split" only when non-zero). The pre-split panel B stays reachable via --unsplit.
    use_split = True
    # 2026-10-20: the standalone panel A (fig5A) is written again, since its data changed.
    for stem, panels in ((f"fig5_noC_{NOC_MODE}", ("A", "B")), (f"fig5A_noC_{NOC_MODE}", ("A",)),
                         (f"fig5B_noC_{NOC_MODE}", ("B",))):
        with plt.rc_context(common.rc()):
            fig, cells, ref = draw(panels, split=use_split and "B" in panels)
            out = common.save(fig, stem)
        print(out[0])
    tot = np.sum(list(cells.values()), axis=0)
    print("synthetic worst-clash totals none/S1/S2/S3:", tot.tolist(), "reference:", ref.tolist())


if __name__ == "__main__":
    main()
