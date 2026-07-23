"""charts.py -- per-metric model x method heatmaps for generation_metadata.

Renders one heatmap per metric in :data:`combo_aggregator.METRIC_NAMES`: rows are
the country's models, columns are its methods (strategies, in pipeline-complexity
order), and each cell is that combo's per-persona **mean** for the metric,
annotated with the value and the contributing-persona count ``n`` so the reader
sees the uncertainty behind every mean (a mean over ``n=1`` is not the same
evidence as a mean over ``n=50``). A metric whose mean is undefined for *every*
combo (e.g. token/cost families for a country of token-less runs) is genuinely
empty and its chart is skipped -- no blank figure is written.

Boundary: this module is a pure rendering sink downstream of the already-computed
:class:`~population_synthetic.analysis.generation_metadata.combo_aggregator.ComboSummary`
numbers. It never parses telemetry, never does cost arithmetic, and never touches
the CSV schema; it only reads ``ComboSummary.metrics`` and draws. Saving is
delegated to ``analysis/utils/figures.py::save_figure`` (PNG+SVG pair), never a
private savefig.
"""

from __future__ import annotations

from pathlib import Path

from population_synthetic.analysis.generation_metadata.combo_aggregator import METRIC_NAMES, ComboSummary
from population_synthetic.analysis.utils.axes import STRATEGY_COMPLEXITY_ORDER
from population_synthetic.analysis.utils.figures import save_figure

__all__ = ["render_metric_heatmaps"]

# PNG raster resolution forwarded to save_figure (the SVG sibling is vector and
# ignores it); matches the dpi=150 used across the analysis chart modules.
_DPI = 150

# Human-facing axis/title labels per metric id (presentation only; the metric ids
# themselves remain the single source of truth in METRIC_NAMES).
_METRIC_LABELS: dict[str, str] = {
    "time": "wall-clock time / persona (s)",
    "input_tokens": "input tokens / persona",
    "output_tokens": "output tokens / persona",
    "total_tokens": "total tokens / persona",
    "calls": "LLM calls / persona",
    "retry_rate": "retry rate / persona",
    "error_rate": "error rate / persona",
    "cost": "estimated USD cost / persona",
}


def _ordered_methods(strategies: set[str]) -> list[str]:
    """Methods in pipeline-complexity order; any unknown strategy appended (sorted)."""
    ordered = [s for s in STRATEGY_COMPLEXITY_ORDER if s in strategies]
    ordered += sorted(s for s in strategies if s not in STRATEGY_COMPLEXITY_ORDER)
    return ordered


def _fmt_mean(value: float) -> str:
    """Compact cell label for a mean (integers plain, small/large floats via %g)."""
    if abs(value) >= 1000 or (value and abs(value) < 0.01):
        return f"{value:.3g}"
    return f"{value:.2f}"


def render_metric_heatmaps(
    country: str,
    summaries: list[ComboSummary],
    out_dir: Path | str,
) -> list[Path]:
    """Render one model x method mean-heatmap per non-empty metric.

    Parameters
    ----------
    country:
        Country axis id -- used only in filenames and chart titles.
    summaries:
        The country's combo summaries (one per ``(model, method)``). Rows are the
        distinct models, columns the distinct methods.
    out_dir:
        The ``charts/`` directory to write into (created if absent).

    Returns
    -------
    list[Path]
        The PNG paths written (each has a sibling ``.svg``). A metric that is
        empty (mean undefined for every combo) is skipped and contributes no path.
    """
    out_dir = Path(out_dir)
    if not summaries:
        return []

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    models = sorted({s.model for s in summaries})
    methods = _ordered_methods({s.strategy for s in summaries})
    by_cell: dict[tuple[str, str], ComboSummary] = {(s.model, s.strategy): s for s in summaries}

    written: list[Path] = []

    for metric in METRIC_NAMES:
        means = np.full((len(models), len(methods)), np.nan)
        counts = np.zeros((len(models), len(methods)), dtype=int)
        for i, model in enumerate(models):
            for j, method in enumerate(methods):
                summary = by_cell.get((model, method))
                if summary is None:
                    continue
                cell = summary.metrics[metric]
                counts[i, j] = int(cell["n"])
                if cell["mean"] is not None:
                    means[i, j] = float(cell["mean"])

        # A metric with no defined mean anywhere is genuinely empty -> no chart.
        if bool(np.all(np.isnan(means))):
            continue

        fig, ax = plt.subplots(
            figsize=(max(6.0, len(methods) * 1.5 + 2.5), max(3.5, len(models) * 0.55 + 2.0))
        )
        masked = np.ma.masked_invalid(means)
        cmap = plt.get_cmap("viridis").copy()
        cmap.set_bad(color="#DDDDDD")
        im = ax.imshow(masked, aspect="auto", cmap=cmap)

        ax.set_xticks(range(len(methods)))
        ax.set_xticklabels(methods, rotation=30, ha="right", fontsize=8)
        ax.set_yticks(range(len(models)))
        ax.set_yticklabels(models, fontsize=8)

        cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
        cbar.set_label(_METRIC_LABELS.get(metric, metric), fontsize=8)

        finite = masked.compressed()
        threshold = (finite.max() + finite.min()) / 2.0 if finite.size else 0.0
        for i in range(len(models)):
            for j in range(len(methods)):
                if np.isnan(means[i, j]):
                    # Distinguish "combo absent" from "combo present, metric ungated".
                    if (models[i], methods[j]) in by_cell:
                        ax.text(j, i, "n/a", ha="center", va="center", fontsize=6.5, color="#666666")
                    continue
                color = "white" if means[i, j] < threshold else "black"
                ax.text(
                    j, i, f"{_fmt_mean(means[i, j])}\nn={counts[i, j]}",
                    ha="center", va="center", fontsize=6.5, color=color,
                )

        ax.set_title(
            f"{country}: {_METRIC_LABELS.get(metric, metric)} (mean per model x method)",
            fontsize=11, fontweight="bold",
        )
        fig.tight_layout()
        written.append(save_figure(fig, out_dir / f"{country}_{metric}.png", dpi=_DPI))

    return written
