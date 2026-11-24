"""Publish the official Figure 3 (from 2026-10-21) as fig3, fig3A, fig3B .{png,svg,eps,pdf}.

Gallery P30 with panel B redrawn so that every LLM call is a pinned chip (approved by the author on 2026-10-21, the
"check mark" variant): candidates chip with a list icon, probabilities chip with a bar icon, pick chip with a check
mark; the context card and the die stay plain (not LLM calls); key "chip = one LLM call / die = random draw".
The pick mark is set once, ``common.PICK_MARK = "check"``.

PNG, SVG and EPS go through the house writer ``figures.save_figure`` (fixed canvas: canvas and file-size budgets
plus the ink-at-edge check). The writer emits no PDF, so each PDF is written from a second, identical build with
the writer's own export rcParams at the same fixed canvas.
fig3 = protos10.p30() (the composite, key under the rails). fig3A and fig3B are separate builds of the same drawing
functions: fig3A = panel A alone (unchanged since 2026-10-20, rebuilt so the set stays consistent);
fig3B = panel B's strategy grid with the key right of the rails and the strategy-E example strip under it.
The run refuses to overwrite: move the previous fig3*.* to _prev/ first.
The earlier builder (notes/builders_2026-10-20/fig3/, panel B without call chips) is kept unchanged.
Run: python publish_fig3.py <output_dir>   (popsynth env, repo installed in editable mode)
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt

import common as c
import protos9 as p9
import protos10 as p10
from protos8 import grid, example_strip, call_key
from population_synthetic.analysis.utils import figures
from population_synthetic.analysis.utils.style import house_style

OUT = Path(sys.argv[1])
DPI = 600  # as fig1, fig2, fig5, fig6 (3800 px for 456 pt)
MODE = {"pdf": False}
STEMS = ("fig3", "fig3A", "fig3B")
EXTS = ("png", "svg", "eps", "pdf")


def _check(fig):
    texts = [t for t in fig.findobj(lambda a: hasattr(a, "get_text") and hasattr(a, "get_fontsize"))
             if t.get_visible() and t.get_text().strip()]
    for t in texts:
        assert "_" not in t.get_text(), t.get_text()
        assert 8.0 <= t.get_fontsize() <= 12.0, (t.get_text(), t.get_fontsize())


def saver(fig, name):
    stem = {"P30_p24_elbow_arrows": "fig3"}.get(name, name)
    _check(fig)
    if MODE["pdf"]:
        with plt.rc_context(figures._export_rc_params()):
            fig.savefig(OUT / f"{stem}.pdf", dpi=DPI, bbox_inches=None)
        plt.close(fig)
        return OUT / f"{stem}.pdf"
    return figures.save_figure(fig, OUT / f"{stem}.png", dpi=DPI, fixed_canvas=True)


def _patch():
    p9.feed_arrows = p10.elbow_arrows
    p9.col_widths = lambda pad=6, ctx_in=True: p10.col_widths_bold()


@house_style
def fig3a():
    _patch()
    fig, ax = c.canvas(10)  # measure
    ar, ab = p9.boxes_a(ax, p10.X0, 1000, bands=True, bold=True, gap=p10.GAP)
    plt.close(fig)
    w, h = round(ar + 2.5, 1), round(1000 - ab + p10.DROP + 2 + 3, 1)
    from population_synthetic.analysis.utils.glyph_grid import PointCanvas
    cv = PointCanvas(w, h)
    ax = cv.figure.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, w); ax.set_ylim(0, h); ax.set_aspect("equal"); ax.axis("off")
    c.panel_letter(ax, 1, h - 1, "A")
    p9.boxes_a(ax, p10.X0, h - 2 - p10.DROP, bands=True, bold=True, gap=p10.GAP)
    return c.save(cv.figure, "fig3A")


@house_style
def fig3b():
    H = 200.0
    for _ in range(3):
        fig, ax = c.canvas(H)
        top = H - 2
        c.panel_letter(ax, 1, top + 1, "B")
        bb = grid(ax, 14, 14 + 166, top)   # same grid width as in fig3 (x 288 to 454)
        call_key(ax, 14 + 166 + 22, top - 63, vertical=True)   # key in the free space right of the rails
        yb = example_strip(ax, 3, c.W - 3, bb - 4)
        if abs(yb - 2.5) < 0.3:
            break
        plt.close(fig)
        H = round(H - (yb - 2.5), 1)
    return c.save(fig, "fig3B")


if __name__ == "__main__":
    assert c.PICK_MARK == "check", c.PICK_MARK
    OUT.mkdir(parents=True, exist_ok=True)
    existing = [OUT / f"{s}.{e}" for s in STEMS for e in EXTS if (OUT / f"{s}.{e}").exists()]
    assert not existing, f"refusing to overwrite; move these to _prev/ first: {[p.name for p in existing]}"
    c.save = saver
    for pdf in (False, True):
        MODE["pdf"] = pdf
        print(p10.p30())
        print(fig3a())
        print(fig3b())
