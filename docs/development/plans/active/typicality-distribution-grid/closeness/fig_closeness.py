"""Figure: weight of strategy vs model on closeness of typicality to SCB (first-round basis).

(a) share of the total sum of squares of the 58 per-combination Cliff's delta values (type II),
    95% bootstrap CIs; (b) strategy least-squares means; (c) model least-squares means.
House presentation layer, 456 pt wide, fixed canvas; PNG kept (SVG/EPS siblings removed).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from population_synthetic.analysis.utils.figures import save_figure
from population_synthetic.analysis.utils.labels import method_key_lines
from population_synthetic.analysis.utils.palette import (
    BASELINE_DARK, CATEGORICAL_SERIES, ERROR_BAR_GREY, FOOTNOTE_GREY, GRID_RULE, RESIDUAL_GREY,
)
from population_synthetic.analysis.utils.style import (
    ANNOTATION, AXES_LINEWIDTH, AXIS_TITLE, LEGEND_LABEL, MAX_HEIGHT, PANEL_TITLE, POINTS_PER_INCH,
    TEXT_WIDTH, TICK_LABEL, house_style,
)

HERE = Path(__file__).resolve().parent
DEC = pd.read_csv(HERE / "decomposition.csv")
DEC = DEC[(DEC.basis == "first_round") & (DEC.outcome == "delta")].set_index("stat")
MEANS = pd.read_csv(HERE / "ls_means.csv")
MEANS = MEANS[MEANS.outcome == "delta"]
S = MEANS[MEANS.factor == "strategy"]
M = MEANS[MEANS.factor == "model"]
STRATS = list(S.level)
COL = {"strategy": CATEGORICAL_SERIES[0], "model": CATEGORICAL_SERIES[1], "resid": RESIDUAL_GREY}

W_PT = TEXT_WIDTH * POINTS_PER_INCH     # 456
H_PT = 396.0


@house_style
def draw():
    import matplotlib.pyplot as plt

    assert H_PT / POINTS_PER_INCH <= MAX_HEIGHT
    fig = plt.figure(figsize=(W_PT / POINTS_PER_INCH, H_PT / POINTS_PER_INCH))

    def frac(x0, y0, x1, y1):
        return [x0 / W_PT, y0 / H_PT, (x1 - x0) / W_PT, (y1 - y0) / H_PT]

    # ---- (a) variance shares
    ax = fig.add_axes(frac(118, 314, 300, 374))
    rows = [("Strategy", "share_strategy", "pomega2_strategy", COL["strategy"]),
            ("Model", "share_model", "pomega2_model", COL["model"]),
            ("Residual\n(interaction + noise)", "share_resid", None, COL["resid"])]
    for i, (lab, st, om, c) in enumerate(rows):
        r = DEC.loc[st]
        ax.barh(i, r.estimate, color=c, height=0.62, zorder=2)
        ax.errorbar(r.estimate, i, xerr=[[r.estimate - r.ci_lo_joint], [r.ci_hi_joint - r.estimate]],
                    fmt="none", ecolor=ERROR_BAR_GREY, elinewidth=0.8, capsize=2, zorder=3)
        txt = f"{r.estimate:.2f} [{r.ci_lo_joint:.2f}, {r.ci_hi_joint:.2f}]"
        if om:
            o = DEC.loc[om]
            txt += f"   partial ω² {o.estimate:.2f} [{o.ci_lo_joint:.2f}, {o.ci_hi_joint:.2f}]"
        ax.text(r.ci_hi_joint + 0.015, i, txt, va="center", ha="left", fontsize=ANNOTATION,
                color=BASELINE_DARK)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows], fontsize=TICK_LABEL)
    ax.invert_yaxis()
    ax.set_xlim(0, 0.8)
    ax.set_xticks(np.arange(0, 0.81, 0.2))
    ax.tick_params(labelsize=TICK_LABEL)
    ax.set_xlabel("Share of total sum of squares", fontsize=AXIS_TITLE, labelpad=2)
    for sd in ("top", "right"):
        ax.spines[sd].set_visible(False)
    fig.text(4 / W_PT, 378 / H_PT, "a", fontsize=PANEL_TITLE, fontweight="bold", va="bottom")

    # ---- (b) strategy LS means, (c) model LS means, shared y
    ylo, yhi = 0.0, 1.0
    axb = fig.add_axes(frac(58, 148, 132, 270))
    axc = fig.add_axes(frac(160, 148, 450, 270), sharey=axb)
    for a, T, c in ((axb, S, COL["strategy"]), (axc, M, COL["model"])):
        x = np.arange(len(T))
        a.errorbar(x, T.ls_mean, yerr=[T.ls_mean - T.ci_lo, T.ci_hi - T.ls_mean], fmt="o", color=c,
                   ecolor=ERROR_BAR_GREY, elinewidth=0.8, capsize=2, markersize=4, zorder=3)
        a.set_xticks(x)
        a.set_xlim(-0.6, len(T) - 0.4)
        a.yaxis.grid(True, color=GRID_RULE, linewidth=0.5, zorder=0)
        a.set_axisbelow(True)
        for sd in ("top", "right"):
            a.spines[sd].set_visible(False)
        a.tick_params(labelsize=TICK_LABEL)
    axb.set_xticklabels(S.label, fontsize=TICK_LABEL)
    axb.set_xlabel("Strategy", fontsize=AXIS_TITLE, labelpad=2)
    plt.setp(axc.get_yticklabels(), visible=False)
    axb.set_ylim(ylo, yhi)
    axb.set_yticks(np.arange(0, 1.01, 0.25))
    axb.set_ylabel("Cliff's δ vs SCB\n(0 = same distribution)", fontsize=AXIS_TITLE)
    axc.set_xticklabels([m.label + ("†" if m.n_cells < 5 else "") for m in M.itertuples()],
                        fontsize=TICK_LABEL, rotation=45, ha="right", rotation_mode="anchor")
    axc.set_xlabel("Model", fontsize=AXIS_TITLE, labelpad=2)
    fig.text(4 / W_PT, 274 / H_PT, "b", fontsize=PANEL_TITLE, fontweight="bold", va="bottom")
    fig.text(142 / W_PT, 274 / H_PT, "c", fontsize=PANEL_TITLE, fontweight="bold", va="bottom")

    key = method_key_lines(STRATS)
    fig.text(4 / W_PT, 4 / H_PT,
             "   ".join(key[:3]) + "\n" + "   ".join(key[3:])
             + "\n† strategy E withdrawn for this model; points are least-squares means of the additive model."
               "\nWhiskers: 95% bootstrap CI (individuals resampled within every combination and within SCB);"
               "\nin b and c the shared SCB sample (n = 100) supplies over 90% of each whisker's variance and"
               "\nmoves all points together, so differences between points are more precise than the whiskers.",
             fontsize=LEGEND_LABEL - 0.0, color=FOOTNOTE_GREY, va="bottom", ha="left", linespacing=1.25)

    out = HERE / "figures" / "closeness_model_vs_strategy.png"
    save_figure(fig, out, fixed_canvas=True)
    for ext in (".svg", ".eps"):
        out.with_suffix(ext).unlink(missing_ok=True)
    return out


if __name__ == "__main__":
    print(draw())
