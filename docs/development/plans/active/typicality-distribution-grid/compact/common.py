"""Shared data + layout for the compact typicality-distribution prototypes (P01..Pnn).

Data: first-round integer judge score, can_exist-majority personas (same basis as
../figs_by_method.py). Per-combination pmfs over 0..10 come from
../distribution_first_round_by_combo.csv; the SCB reference pmf from
../distribution_first_round_by_model.csv. Every statistic below is computed here, in the
data section, and handed to the drawing code as finished numbers.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
sys.path.insert(0, str(PARENT))

from figs_columns import HOSTING, MLAB, MODELS, REAL  # noqa: E402

from population_synthetic.analysis.utils.axes import strategy_complexity_order  # noqa: E402
from population_synthetic.analysis.utils.labels import method_key_lines, method_letters  # noqa: E402
from population_synthetic.analysis.utils.palette import (  # noqa: E402
    BASELINE_DARK, FOOTNOTE_GREY, HOST_COLORS, MISSING_COLOR,
)
from population_synthetic.analysis.utils.style import (  # noqa: E402
    LEGEND_LABEL, POINTS_PER_INCH, TEXT_WIDTH, TICK_LABEL, TICK_LABEL_LARGE,
)
from population_synthetic.analysis.utils.table_style import HOST_LABELS  # noqa: E402

meta = json.load(open(PARENT / "meta.json"))
STRATS = strategy_complexity_order(meta["strategies"])
LETTER = method_letters(STRATS)
KEY_LINES = method_key_lines(STRATS)
METHODS = [LETTER[s] for s in STRATS]
N_SCORES = 11
SCORES = np.arange(N_SCORES)
P = [f"p{k}" for k in SCORES]
REF_TICK = "SCB (real)"

_combo = pd.read_csv(PARENT / "distribution_first_round_by_combo.csv")
_real = pd.read_csv(PARENT / "distribution_first_round_by_model.csv").set_index("unit").loc[REAL]
assert list(_combo.method.unique()) == METHODS
assert set(_combo.model) == set(MODELS)

REF_PMF = _real[P].to_numpy(float)
REF_N = int(_real.n)
assert abs(REF_PMF.sum() - 1) < 1e-9


def _quantile(cdf: np.ndarray, q: float) -> int:
    """Smallest score k with F(k) >= q (lower quantile of a discrete distribution)."""
    return int(np.searchsorted(cdf, q - 1e-12))


def _stats(pmf: np.ndarray) -> dict:
    cdf = np.cumsum(pmf)
    rcdf = np.cumsum(REF_PMF)
    # Cliff's delta of the combination against SCB: P(X > Y) - P(X < Y)
    gt = sum(pmf[i] * REF_PMF[:i].sum() for i in SCORES)
    lt = sum(pmf[i] * REF_PMF[i + 1:].sum() for i in SCORES)
    return dict(
        pmf=pmf, cdf=cdf,
        median=_quantile(cdf, 0.5), q25=_quantile(cdf, 0.25), q75=_quantile(cdf, 0.75),
        q10=_quantile(cdf, 0.10), q90=_quantile(cdf, 0.90),
        le4=float(cdf[4]), mid=float(pmf[5:8].sum()), high=float(pmf[8:].sum()),
        w1=float(np.abs(cdf - rcdf)[:-1].sum()),
        tv=float(0.5 * np.abs(pmf - REF_PMF).sum()),
        ks=float(np.abs(cdf - rcdf).max()),
        delta=float(gt - lt),
        mean_shift=float((pmf * SCORES).sum() - (REF_PMF * SCORES).sum()),
    )


REF = _stats(REF_PMF)
REF["n"] = REF_N

# CELL[method_letter][model] -> stats dict, or None when withdrawn at the population cap
CELL: dict[str, dict[str, dict | None]] = {m: {} for m in METHODS}
for _, r in _combo.iterrows():
    if r.withdrawn:
        CELL[r.method][r.model] = None
        continue
    pmf = r[P].to_numpy(float)
    assert abs(pmf.sum() - 1) < 1e-9
    s = _stats(pmf)
    s["n"] = int(r.n)
    CELL[r.method][r.model] = s
assert all(len(CELL[m]) == len(MODELS) for m in METHODS)
WITHDRAWN = [(m, mod) for m in METHODS for mod in MODELS if CELL[m][mod] is None]


def matrix(key: str) -> np.ndarray:
    return np.array([[np.nan if CELL[m][mod] is None else CELL[m][mod][key] for mod in MODELS]
                     for m in METHODS], float)


# ---------------------------------------------------------------- layout (points)
W = TEXT_WIDTH * POINTS_PER_INCH  # 456
GRID_X0 = 20.0                   # left edge of the 12-model grid (row letters sit left of it)
REF_GAP = 10.0                   # detached reference column
LABEL_DROP = 54.0                # rotated model labels below the grid
KEY_H = 24.0                     # two-line method key at the bottom
LEGEND_H = 14.0                  # legend row at the top


class Canvas:
    """Absolute-point layout helper: fig of W x h pt, axes placed by point boxes."""

    def __init__(self, h: float):
        import matplotlib.pyplot as plt
        self.h = h
        self.fig = plt.figure(figsize=(W / POINTS_PER_INCH, h / POINTS_PER_INCH))

    def box(self, x0, y0, x1, y1):
        return [x0 / W, y0 / self.h, (x1 - x0) / W, (y1 - y0) / self.h]

    def axes(self, x0, y0, x1, y1, **kw):
        return self.fig.add_axes(self.box(x0, y0, x1, y1), **kw)

    def text(self, x, y, s, **kw):
        return self.fig.text(x / W, y / self.h, s, **kw)


def model_tick_labels(cv: Canvas, xs: list[float], y_top: float, *, ref_x: float | None,
                      ref_label: str = REF_TICK):
    """Rotated model labels (hosting-tinted) hanging from y_top, plus the reference label."""
    for x, m in zip(xs, MODELS):
        cv.text(x, y_top, MLAB[m], rotation=45, ha="right", va="top", rotation_mode="anchor",
                fontsize=TICK_LABEL, color=HOST_COLORS[HOSTING[m]])
    if ref_x is not None:
        cv.text(ref_x, y_top, ref_label, rotation=45, ha="right", va="top", rotation_mode="anchor",
                fontsize=TICK_LABEL, color=BASELINE_DARK)


def row_letters(cv: Canvas, ys: list[float], x: float = GRID_X0 - 5):
    for y, m in zip(ys, METHODS):
        cv.text(x, y, m, ha="right", va="center", fontsize=TICK_LABEL_LARGE, fontweight="bold",
                color=BASELINE_DARK)


def method_key(cv: Canvas, y_top: float, x: float = 4.0):
    """The A-E key, in the graphic (two lines)."""
    parts = [k.replace(" — ", " ") for k in KEY_LINES]
    line1 = "Methods:  " + "   ".join(parts[:3])
    line2 = "   ".join(parts[3:])
    cv.text(x, y_top, line1, ha="left", va="top", fontsize=LEGEND_LABEL, color=FOOTNOTE_GREY)
    cv.text(x + 38.5, y_top - 10.5, line2, ha="left", va="top", fontsize=LEGEND_LABEL, color=FOOTNOTE_GREY)


def legend_row(cv: Canvas, extra_handles=(), *, x: float = GRID_X0, y_top: float | None = None,
               withdrawn: bool = True, ncol: int | None = None):
    from matplotlib.patches import Patch
    handles = [Patch(facecolor=HOST_COLORS[c], edgecolor="none", label=HOST_LABELS[c]) for c in ("hosted", "local")]
    if withdrawn:
        handles.append(Patch(facecolor=MISSING_COLOR, edgecolor="none", label="withdrawn"))
    handles.extend(extra_handles)
    y_top = cv.h - 3 if y_top is None else y_top
    cv.fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(x / W, y_top / cv.h),
                  ncol=ncol or len(handles), fontsize=LEGEND_LABEL, frameon=False, handlelength=1.4,
                  handleheight=0.8, columnspacing=1.0, handletextpad=0.4, borderaxespad=0, borderpad=0)
