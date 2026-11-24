"""Shared paths, data loading and layout helpers for the manuscript Figure 4 / Figure 7 rebuild.

Every number drawn is read from the current 03_Analysis outputs (2026-10-20 re-run); nothing is typed in.
Draws through the repo presentation layer (style / palette / labels) where it can.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from population_synthetic.analysis.utils import labels as L  # noqa: E402
from population_synthetic.analysis.utils import palette as P  # noqa: E402
from population_synthetic.analysis.utils import style as S  # noqa: E402
from population_synthetic.analysis.utils.cap_index import load_cap_index  # noqa: E402
from population_synthetic.analysis.utils.model_order import ranked_model_order  # noqa: E402

# ref-v3 copy: read root and write folder come from the environment (the live 03_Analysis is only ever read)
OUTPUT_BASE = Path(os.environ["FIG_OUTPUT_BASE"])
ANALYSIS = OUTPUT_BASE / "03_Analysis"
OUT_DIR = Path(os.environ["FIG_OUT_DIR"])  # scratch build; published copies are made by hand
PUBLISHED_DIR = OUTPUT_BASE / "04_Figures" / "swedish_02" / "manuscript_2026-10-04"
COUNTRY = "swedish_02"

PT = 72.0

# Manuscript display names that differ from config display.name (docx wording). Everything
# else resolves through labels.model_label.
MANUSCRIPT_MODEL_NAMES = {
    "claude_haiku": "Claude Haiku 4.5",
    "claude_sonnet": "Claude Sonnet 5",
}


def model_name(model_id: str) -> str:
    return MANUSCRIPT_MODEL_NAMES.get(model_id) or L.model_label(model_id)


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def performance(base: Path = ANALYSIS) -> dict:
    return load_json(base / "model_ranking" / f"{COUNTRY}_performance.json")


def method_significance(base: Path = ANALYSIS) -> dict:
    return load_json(base / "method_significance" / f"{COUNTRY}_method_significance.json")


def model_order(perf: dict) -> list[str]:
    """model_ranking's published order (the heatmap's row order)."""
    return ranked_model_order(perf, load_cap_index(OUTPUT_BASE))


def house_rc() -> dict:
    return S.house_rc_params()


class PtCanvas:
    """A figure laid out in points, origin top-left."""

    def __init__(self, width_pt: float, height_pt: float, dpi: int = 300):
        self.w, self.h = width_pt, height_pt
        self.fig = plt.figure(figsize=(width_pt / PT, height_pt / PT), dpi=dpi)

    def rect(self, x0, y0, x1, y1):
        """[left, bottom, width, height] figure fraction from a top-left pt box."""
        return [x0 / self.w, 1 - y1 / self.h, (x1 - x0) / self.w, (y1 - y0) / self.h]

    def axes(self, x0, y0, x1, y1, **kw):
        return self.fig.add_axes(self.rect(x0, y0, x1, y1), **kw)

    def xy(self, x, y):
        """Figure-fraction coordinates of a top-left pt point."""
        return x / self.w, 1 - y / self.h

    def text(self, x, y, s, **kw):
        fx, fy = self.xy(x, y)
        return self.fig.text(fx, fy, s, **kw)

    def letter(self, x, y, s):
        return self.text(x, y, s, fontsize=S.FONT_CEILING_PT + 2, fontweight="bold",
                         ha="left", va="top")


def save_all(fig, stem: Path, *, dpi: int, panels: dict[str, tuple] | None = None, pt_h=None, pt_w=None):
    """Write stem.{png,svg,pdf,eps} at the figure's own canvas; panels are top-left pt boxes
    written as stem_panel{X}.{png,svg,pdf} crops of the same vector drawing."""
    from matplotlib.transforms import Bbox

    from population_synthetic.analysis.utils.figures import EXPORT_RC_KEYS

    fig.canvas.draw()
    tb = fig.get_tightbbox(fig.canvas.get_renderer())
    wi, hi = fig.get_size_inches()
    if tb.x0 < -1e-3 or tb.y0 < -1e-3 or tb.x1 > wi + 1e-3 or tb.y1 > hi + 1e-3:
        print(f"WARNING: ink outside canvas: tight bbox {tb.bounds} vs canvas {wi:.3f}x{hi:.3f} in")
    stem.parent.mkdir(parents=True, exist_ok=True)
    export_rc = {k: v for k, v in S.house_rc_params().items() if k in EXPORT_RC_KEYS}
    with plt.rc_context(export_rc):
        for ext in ("png", "svg", "pdf", "eps"):
            fig.savefig(stem.with_suffix("." + ext), dpi=dpi, facecolor="white")
        for name, (x0, y0, x1, y1) in (panels or {}).items():
            bb = Bbox.from_extents(x0 / PT, (pt_h - y1) / PT, x1 / PT, (pt_h - y0) / PT)
            for ext in ("png", "svg", "pdf"):
                fig.savefig(stem.parent / f"{stem.name}_panel{name}.{ext}", dpi=dpi,
                            bbox_inches=bb, facecolor="white")
