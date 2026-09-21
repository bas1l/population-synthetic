"""Typicality score distribution per model, split by generation method (no pooling across methods).

Same basis as figs_columns.py (first-round integer judge score, can_exist-majority personas only),
same styling. One figure per method (A-E, simplest first) plus one five-panel stacked figure.
Combinations withdrawn at the population cap keep their column slot, drawn as a grey
"withdrawn" placeholder, so every panel has the same 13 column positions.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from figs_columns import (
    BAR_W, HOSTING, KEY_LEN, MEDIAN_KEY_DASH, MEDIAN_LW, MEDIAN_W, MLAB, MODELS, N_SCORES, REAL,
    REAL_TICK, SEP_LW, dist as POOLED,
)
from population_synthetic.analysis.utils.axes import strategy_complexity_order
from population_synthetic.analysis.utils.figures import save_figure
from population_synthetic.analysis.utils.labels import method_key_lines, method_letters
from population_synthetic.analysis.utils.palette import (
    BASELINE_DARK, FOOTNOTE_GREY, HOST_COLORS, MISSING_COLOR, SURFACE, heatmap_levels,
    text_color_for_rgb,
)
from population_synthetic.analysis.utils.style import (
    ANNOTATION, AXES_LINEWIDTH, AXIS_TITLE, HEADING_WEIGHT, LEGEND_LABEL, MAX_HEIGHT, PANEL_TITLE,
    POINTS_PER_INCH, TEXT_WIDTH, TICK_LABEL, house_style,
)
from population_synthetic.analysis.utils.table_style import HOST_LABELS

OUT = Path(__file__).resolve().parent
FIG = OUT / "figures"
BASE = Path("<project-data>/02_Data")
meta = json.load(open(OUT / "meta.json"))

# ---------------------------------------------------------------- data (same basis as effects.py)
df = pd.concat([pd.read_csv(f) for f in meta["files"]], ignore_index=True)
df["first"] = df.typicality_rounds.astype(str).str.split("|").map(
    lambda x: float(x[0]) if x[0] not in ("", "nan") else np.nan)
surv = df[df.can_exist_majority == True]  # noqa: E712
syn = surv[surv.is_real_reference == False]  # noqa: E712
real = surv[surv.is_real_reference == True]  # noqa: E712
assert len(syn) == meta["n_syn"] and len(real) == meta["n_real"]

STRATS = strategy_complexity_order(meta["strategies"])
LETTER = method_letters(STRATS)
KEY = dict(zip(STRATS, method_key_lines(STRATS)))   # "A — All Pick", ...
assert LETTER == meta["letters"]


def hist11(values) -> np.ndarray:
    v = np.asarray(values, float)
    assert np.allclose(v, np.round(v)) and v.min() >= 0 and v.max() <= 10  # first round is integer
    return np.bincount(v.astype(int), minlength=N_SCORES)


def as_row(h: np.ndarray) -> dict:
    return dict(n=int(h.sum()), **{f"p{k}": h[k] / h.sum() for k in range(N_SCORES)})


# withdrawn combinations come from the population-cap index, never inferred from absence
cap = json.load(open(BASE / "03_Analysis/population_cap/_index.json"))
excluded = {e["slug"] for e in cap if e["excluded"]}
rows, withdrawn = [], set()
for s in STRATS:
    for m in MODELS:
        sub = syn[(syn.model == m) & (syn.strategy == s)]
        slug = f"swedish_02_{s}_{m}"
        if slug in excluded:
            assert sub.empty, slug
            withdrawn.add((m, s))
            rows.append(dict(strategy=s, method=LETTER[s], model=m, withdrawn=True))
            continue
        assert not sub.empty, f"{slug}: no personas and not withdrawn at the cap"
        rows.append(dict(strategy=s, method=LETTER[s], model=m, withdrawn=False, **as_row(hist11(sub["first"]))))
combo = pd.DataFrame(rows)
real_row = as_row(hist11(real["first"]))
# consistency with the pooled figure: per-model sums of per-combo counts reproduce its columns
for m in MODELS:
    c = combo[(combo.model == m) & ~combo.withdrawn]
    h = sum(np.array([r[f"p{k}"] for k in range(N_SCORES)]) * r.n for _, r in c.iterrows())
    assert int(round(h.sum())) == int(POOLED.loc[m].n), m
    assert np.allclose(h / h.sum(), [POOLED.loc[m][f"p{k}"] for k in range(N_SCORES)]), m
assert real_row["n"] == POOLED.loc[REAL].n
assert np.allclose([real_row[f"p{k}"] for k in range(N_SCORES)], [POOLED.loc[REAL][f"p{k}"] for k in range(N_SCORES)])
combo.to_csv(OUT / "distribution_first_round_by_combo.csv", index=False)

UNITS = MODELS + [REAL]
XS = list(range(len(MODELS))) + [len(MODELS) + 0.6]
W_PT = TEXT_WIDTH * POINTS_PER_INCH   # 456
N_OFFSET_PT = 3.0                     # = 0.015 of the 190 pt columns-figure axes
WITHDRAWN_TEXT = "withdrawn"


def _column(s: str, m: str):
    if m == REAL:
        return real_row
    r = combo[(combo.strategy == s) & (combo.model == m)].iloc[0]
    return None if r.withdrawn else r


def draw_panel(ax, s: str, *, digit_min_pt: float | None, ax_h_pt: float, yticks):
    """Draw one method's 12 model columns + the SCB column. digit_min_pt=None -> no digits."""
    n_y = 1 + N_OFFSET_PT / ax_h_pt   # n labels sit a fixed 3 pt above the axes, whatever its height
    levels = heatmap_levels(N_SCORES)
    for x, u in zip(XS, UNITS):
        r = _column(s, u)
        if r is None:   # withdrawn at the population cap: keep the slot, say so
            ax.bar(x, 1.0, width=BAR_W, color=MISSING_COLOR, edgecolor="none", zorder=2)
            ax.text(x, 0.5, WITHDRAWN_TEXT, rotation=90, ha="center", va="center", fontsize=ANNOTATION,
                    color=FOOTNOTE_GREY, zorder=3)
            ax.text(x, n_y, "–", ha="center", va="bottom", fontsize=ANNOTATION, color=FOOTNOTE_GREY)
            continue
        bottom = 0.0
        for k in range(N_SCORES):
            h = float(r[f"p{k}"])
            if h > 0:
                col = levels(k)
                ax.bar(x, h, bottom=bottom, width=BAR_W, color=col, edgecolor=SURFACE, linewidth=0.4, zorder=2)
                if digit_min_pt is not None and h * ax_h_pt >= digit_min_pt:
                    ax.text(x, bottom + h / 2, str(k), ha="center", va="center", fontsize=ANNOTATION,
                            color=text_color_for_rgb(col[:3]), zorder=3)
            bottom += h
        assert abs(bottom - 1.0) < 1e-9, (s, u, bottom)
        ax.text(x, n_y, f"{int(r['n'])}", ha="center", va="bottom", fontsize=ANNOTATION, color=FOOTNOTE_GREY)
        ax.plot([x - MEDIAN_W / 2, x + MEDIAN_W / 2], [0.5, 0.5], color=BASELINE_DARK,
                linewidth=MEDIAN_LW, solid_capstyle="butt", zorder=1)
    ax.axvline((XS[-2] + XS[-1]) / 2, color=BASELINE_DARK, linewidth=SEP_LW, zorder=1)
    ax.set_xlim(-0.6, XS[-1] + 0.6)
    ax.set_ylim(0, 1)
    ax.text(-0.02, n_y, "n", ha="right", va="bottom", fontsize=ANNOTATION, color=FOOTNOTE_GREY,
            transform=ax.get_yaxis_transform())
    ax.set_yticks(yticks)
    ax.tick_params(axis="y", labelsize=TICK_LABEL)
    ax.set_xticks(XS)
    ax.tick_params(axis="x", length=0, pad=3)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def model_ticklabels(ax):
    ax.set_xticklabels([MLAB[m] for m in MODELS] + [REAL_TICK], fontsize=TICK_LABEL, rotation=45,
                       ha="right", rotation_mode="anchor")
    for lab, u in zip(ax.get_xticklabels(), UNITS):
        lab.set_color(HOST_COLORS[HOSTING[u]] if u in HOSTING else BASELINE_DARK)


def legend_and_colorbar(fig, cax, *, x0_pt, y_top_pt, h_pt, show_withdrawn: bool):
    import matplotlib.colors as mcolors
    from matplotlib.cm import ScalarMappable
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    handles = [Patch(facecolor=HOST_COLORS[c], edgecolor="none", label=HOST_LABELS[c]) for c in ("hosted", "local")]
    handles.append(Line2D([], [], color=BASELINE_DARK, linewidth=MEDIAN_LW, linestyle=MEDIAN_KEY_DASH,
                          dash_capstyle="butt", label="median (share 0.5)"))
    if show_withdrawn:   # keyed only where a withdrawn slot is drawn
        handles.append(Patch(facecolor=MISSING_COLOR, edgecolor="none", label="withdrawn at population cap"))
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(x0_pt / W_PT, 1 - y_top_pt / h_pt),
               ncol=4, fontsize=LEGEND_LABEL, frameon=False, handlelength=KEY_LEN, handleheight=0.8,
               columnspacing=1.0, handletextpad=0.5, borderaxespad=0, borderpad=0)
    levels = heatmap_levels(N_SCORES)
    sm = ScalarMappable(cmap=levels, norm=mcolors.BoundaryNorm(np.arange(-0.5, N_SCORES), N_SCORES))
    cbar = fig.colorbar(sm, cax=cax, ticks=range(N_SCORES))
    cbar.set_label("Typicality score\n(0 = rarest possible, 10 = ordinary)", fontsize=AXIS_TITLE)
    cbar.ax.tick_params(labelsize=TICK_LABEL)
    cbar.outline.set_linewidth(AXES_LINEWIDTH)


# ---------------------------------------------------------------- (1) one figure per method
S_H = 306.0
S_AX_L, S_AX_R, S_AX_B, S_AX_T = 38.0, 390.0, 66.0, 256.0
S_CB_L, S_CB_W = 402.0, 8.0
S_DIGIT_MIN_PT = 0.06 * (S_AX_T - S_AX_B)   # identical to the columns figure's 6% rule


@house_style
def fig_single(s: str):
    import matplotlib.pyplot as plt

    assert S_H / POINTS_PER_INCH <= MAX_HEIGHT
    fig = plt.figure(figsize=(W_PT / POINTS_PER_INCH, S_H / POINTS_PER_INCH))

    def frac(x0, y0, x1, y1):
        return [x0 / W_PT, y0 / S_H, (x1 - x0) / W_PT, (y1 - y0) / S_H]

    ax = fig.add_axes(frac(S_AX_L, S_AX_B, S_AX_R, S_AX_T))
    cax = fig.add_axes(frac(S_CB_L, S_AX_B, S_CB_L + S_CB_W, S_AX_T))
    draw_panel(ax, s, digit_min_pt=S_DIGIT_MIN_PT, ax_h_pt=S_AX_T - S_AX_B, yticks=np.arange(0, 1.01, 0.25))
    ax.set_ylabel("Share of personas", fontsize=AXIS_TITLE)
    model_ticklabels(ax)
    fig.text(4 / W_PT, 1 - 3 / S_H, f"Method {KEY[s]}", ha="left", va="top", fontsize=PANEL_TITLE,
             fontweight=HEADING_WEIGHT, color=BASELINE_DARK)
    legend_and_colorbar(fig, cax, x0_pt=S_AX_L, y_top_pt=22.0, h_pt=S_H,
                        show_withdrawn=any(ws == s for _, ws in withdrawn))
    save_figure(fig, FIG / f"typicality_distribution_method_{LETTER[s]}.png", fixed_canvas=True)


# ---------------------------------------------------------------- (2) five panels stacked
C_TOP = 18.0          # legend row
C_TITLE = 14.0        # method title strip above each panel
C_NROW = 11.0         # n labels above each panel's axes
C_AX_H = 78.0
C_GAP = 6.0
C_BOTTOM = 68.0       # rotated model labels under the bottom panel
C_H = C_TOP + 5 * (C_TITLE + C_NROW + C_AX_H) + 4 * C_GAP + C_BOTTOM
C_AX_L, C_AX_R = 38.0, 390.0
C_CB_L, C_CB_W = 402.0, 8.0
# Same legibility rule as the single figures, stated in points: a digit is printed when its segment
# is at least as tall as a 6% segment of the 190 pt columns-figure axes (11.4 pt) -> >= 14.25% here.
C_DIGIT_MIN_PT = S_DIGIT_MIN_PT


@house_style
def fig_combined():
    import matplotlib.pyplot as plt

    assert C_H / POINTS_PER_INCH <= MAX_HEIGHT, (C_H, MAX_HEIGHT * POINTS_PER_INCH)
    fig = plt.figure(figsize=(W_PT / POINTS_PER_INCH, C_H / POINTS_PER_INCH))

    def frac(x0, y0, x1, y1):
        return [x0 / W_PT, y0 / C_H, (x1 - x0) / W_PT, (y1 - y0) / C_H]

    axes = []
    for i, s in enumerate(STRATS):
        top = C_H - C_TOP - i * (C_TITLE + C_NROW + C_AX_H + C_GAP)   # top of the title strip
        ax_top = top - C_TITLE - C_NROW
        ax = fig.add_axes(frac(C_AX_L, ax_top - C_AX_H, C_AX_R, ax_top))
        draw_panel(ax, s, digit_min_pt=C_DIGIT_MIN_PT, ax_h_pt=C_AX_H, yticks=[0, 0.5, 1])
        ax.set_yticklabels(["0", "0.5", "1"])
        fig.text(4 / W_PT, (top - 1) / C_H, f"Method {KEY[s]}", ha="left", va="top", fontsize=LEGEND_LABEL + 1,
                 fontweight=HEADING_WEIGHT, color=BASELINE_DARK)
        if i == len(STRATS) - 1:
            model_ticklabels(ax)
        else:
            ax.set_xticklabels([])
        axes.append(ax)
    y_hi = C_H - C_TOP - C_TITLE - C_NROW
    y_lo = C_BOTTOM
    fig.text(6 / W_PT, (y_lo + y_hi) / 2 / C_H, "Share of personas", rotation=90, ha="left", va="center",
             fontsize=AXIS_TITLE)
    # the colourbar spans the middle three panels: long enough for 11 legible steps, clear of the legend
    cax = fig.add_axes(frac(C_CB_L, y_lo + 60, C_CB_L + C_CB_W, y_hi - 60))
    legend_and_colorbar(fig, cax, x0_pt=C_AX_L, y_top_pt=3.0, h_pt=C_H, show_withdrawn=bool(withdrawn))
    save_figure(fig, FIG / "typicality_distribution_by_method.png", fixed_canvas=True)
    return C_H


# ---------------------------------------------------------------- share <= 4 table
def low_share_table() -> pd.DataFrame:
    real_low = sum(real_row[f"p{k}"] for k in range(5))
    t = []
    for m in MODELS:
        row = {"model": MLAB[m]}
        for s in STRATS:
            r = _column(s, m)
            row[LETTER[s]] = np.nan if r is None else sum(float(r[f"p{k}"]) for k in range(5))
        t.append(row)
    t = pd.DataFrame(t)
    t.loc[len(t)] = {"model": REAL_TICK, **{LETTER[s]: real_low for s in STRATS}}
    return t


if __name__ == "__main__":
    for s in STRATS:
        fig_single(s)
    h = fig_combined()
    print("combined height pt", h)
    t = low_share_table()
    t.to_csv(OUT / "share_le4_by_combo.csv", index=False)
    print(t.round(3).to_string())
    med = combo.copy()
    print("withdrawn:", sorted(withdrawn))
