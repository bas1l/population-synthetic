"""Publish the approved Figure 1 (gallery P16) as fig1.{png,svg,eps,pdf}.

PNG, SVG and EPS go through the house writer ``figures.save_figure`` (fixed canvas: canvas and
file-size budgets plus the ink-at-edge check). The writer emits no PDF, so the PDF is written from a
second, identical build with the writer's own export rcParams, at the same fixed canvas.
Run: python publish_fig1.py <output_dir>
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt

import common
import protos_p15
from population_synthetic.analysis.utils import figures

OUT = Path(sys.argv[1])
DPI = 600  # same as the published fig2, fig5, fig6 (3800 px for 456 pt)


def _save_house(fig, name):
    return figures.save_figure(fig, OUT / "fig1.png", dpi=DPI, fixed_canvas=True)


def _save_pdf(fig, name):
    with plt.rc_context(figures._export_rc_params()):
        fig.savefig(OUT / "fig1.pdf", dpi=DPI, bbox_inches=None)
    plt.close(fig)
    return OUT / "fig1.pdf"


if __name__ == "__main__":
    for saver in (_save_house, _save_pdf):
        common.save = saver
        print(protos_p15.p15(v16=True))
