"""Publish the approved Figure 2 (gallery F2_P14) as fig2, fig2A, fig2B .{png,svg,eps,pdf}.

Panel A: gallery design F2_P14 (protos_l2.py), drawn in vector in Figure 3A's style: level tabs, a grey context
box above each group, all five Level 2 attributes in one column, income source "| employment status, age".
Panel B: the published panel, drawn by fig2.draw(with_a=False) from real_population_stats.

PNG, SVG and EPS go through the house writer ``figures.save_figure`` (fixed canvas: canvas and file-size budgets
plus the ink-at-edge check). The writer emits no PDF, so the PDF is written from a second, identical build with
the writer's own export rcParams, at the same fixed canvas (as publish_fig1.py / publish_fig3.py).
Run (popsynth env, from this folder): python publish_fig2.py <output_dir>
"""
from __future__ import annotations

import sys
from pathlib import Path

OUT = Path(sys.argv[1])
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import os as _os  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

import protos_a as PA  # noqa: E402  (imports this folder's common.py and fig2.py)
import protos_l2 as PL  # noqa: E402
from population_synthetic.analysis.utils import figures  # noqa: E402

DPI = 600  # as fig1, fig3, fig5, fig6 (3800 px for 456 pt)
assert PL.INCOME_MODE == "status", "the published label is '| employment status, age'"


class _A(PA.A):
    """Panel A's overlay sized to whatever canvas it is drawn on (456 pt composite, or panel A alone)."""

    def __init__(self, fig, H):
        super().__init__(fig, H)
        self.ax.set_xlim(0, fig.get_size_inches()[0] * 72)


PL.A = _A
_kw = {}
PL.build = lambda stem, **kw: _kw.update(kw) or kw
PL.ALL["P14"]()                       # the approved design's arguments, exactly as in the gallery
P14_KW = dict(_kw)


import protos_l3 as L3  # ref-v3: three-level panel A (reference conditioning after the 2026-11-23 redraw)
PANEL_A = _os.environ.get("REFV3_PANEL_A", "L3")  # "L3" = new three-level design, "P14" = the staged four-level one


def composite(with_a=True, letters=True, size=None):
    w, h = size or (PA.B.W, PA.B.H)
    fig = plt.figure(figsize=(w / 72, h / 72))
    if size is None:
        PA.B.draw(fig, with_a=False, letters=letters)
    if with_a:
        (L3.draw if PANEL_A == "L3" else PL.draw)(fig, h, **P14_KW)
    return fig


JOBS = {
    "fig2": dict(),
    "fig2A": dict(size=(PA.A_W, PA.A_H)),
    "fig2B": dict(with_a=False, letters=False),
}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for stem, kw in JOBS.items():
        for pdf in (False, True):
            with plt.rc_context(PA.BC.rc()):
                fig = composite(**kw)
                if pdf:
                    with plt.rc_context(figures._export_rc_params()):
                        fig.savefig(OUT / f"{stem}.pdf", dpi=DPI, bbox_inches=None)
                    plt.close(fig)
                else:
                    print(figures.save_figure(fig, OUT / f"{stem}.png", dpi=DPI, fixed_canvas=True))
