"""Manuscript Figure 6 (2026-10-20): A = retention heatmap, B = cause grid, C = by-strategy bars.

Writes into protos.OUT (FIG_OUT_DIR, else ./out beside this script), each as PNG (600 dpi) + SVG +
EPS (house writer, fixed canvas) + PDF:
  fig6A  the heatmap alone, the single-panel build of 2026-10-20 (fig6_heatmap.py, black rule)
  fig6B  panels B + C alone in the author's revised layout (protos.FIG6B_REV; fig6B_revised.svg)
  fig6   the composite: A above B + C on one 456 pt canvas, the heatmap's columns drawn over the
         cause grid's columns (same model order; the all-withdrawn model set apart by the same gap)

Run: python fig6_composite.py   (popsynth env; live data, FIG6_SOURCE unset)
"""
from __future__ import annotations

import matplotlib.pyplot as plt

import fig6_heatmap as HM
import protos as P
from population_synthetic.analysis.utils.glyph_grid import PointCanvas
from population_synthetic.analysis.utils.palette import BASELINE_DARK
from population_synthetic.analysis.utils.style import FIGURE_TITLE, HEADING_WEIGHT, house_style

A_TO_BC = 4.0   # gap between the heatmap block and the panel B/C block (points)
A_LETTER_X = -0.04   # "A." ink then starts at x = 0, where the revision's "B." (x = -0.879) has its ink


class _Canvas:
    """The two attributes protos.save reads, for a plain matplotlib figure."""

    def __init__(self, fig, height_pt):
        self.figure, self.height_pt = fig, height_pt


def fig6A():
    with plt.rc_context(HM.common.rc()):
        fig = plt.figure(figsize=(HM.W / 72, HM.H / 72))
        HM.build(fig)
        return P.save(_Canvas(fig, HM.H), "fig6A")


@house_style
def fig6():
    """Composite: panel A (heatmap) above panels B + C in the author's revised layout (fig6B_revised.svg)."""
    h_bc = P.REV_H_PADDED
    H = HM.H + A_TO_BC + h_bc
    cv = PointCanvas(P.W, H)
    # Column geometry of panel B (x only; the same Grid arguments fig6_bc_rev uses).
    g = P.Grid(P.REV_GRID_X0, P.REV_GRID_X0 + 330.0, 0.0, 24.0, row_gap=3)
    half = g.cg / 2
    last = P.N_COLS - 1
    groups = [(g.xs[0] - half, g.xs[last - 1] + g.cw + half, list(range(last))),
              (g.xs[last] - half, g.xs[last] + g.cw + half, [last])]
    with plt.rc_context(HM.common.rc()):
        HM.build(cv.figure, origin=(0.0, 0.0), canvas=(P.W, H), col_groups=groups)
    hm_models = cv.figure._fig6_models
    if list(hm_models) != list(P.d.MODELS):
        raise ValueError(f"panel A and panel B model orders differ: {hm_models} vs {P.d.MODELS}")
    hm = HM.load()[0]
    set_apart = [m for m in hm_models if hm.loc[hm.model == m, "excluded"].all()]
    if set_apart != [hm_models[last]]:
        raise ValueError(f"the set-apart column must be the all-withdrawn model, got {set_apart}")
    # "A." on the same baseline offset from its block top as "B."; x so that its ink starts where B.'s does.
    ax_, ab = A_LETTER_X + P.REV_B_DX, P.REV_LETTERS["B."][1] + P.REV_PAD_TOP
    cv.text(ax_, H - ab, "A.", fontsize=FIGURE_TITLE, fontweight=HEADING_WEIGHT, ha="left", va="baseline",
            color=BASELINE_DARK)
    P.fig6_bc_rev(cv, block_h=h_bc, pad_top=P.REV_PAD_TOP, b_dx=P.REV_B_DX, last_tick_dx=P.REV_40_DX)
    return P.save(cv, "fig6")   # house writer, edge check on


if __name__ == "__main__":
    print(fig6A())
    print(P.FIG6B_MARGIN())
    print(fig6())
