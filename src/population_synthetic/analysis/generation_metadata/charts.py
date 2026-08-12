"""charts.py -- rendering sink for generation_metadata figures.

Three families of charts live here, all pure rendering downstream of
already-computed numbers and all persisted through
``analysis/utils/figures.py::save_figure`` (PNG+SVG pair), never a private
``savefig``:

* :func:`render_metric_heatmaps` -- one model x method mean-heatmap per metric in
  :data:`combo_aggregator.METRIC_NAMES` (annotated with each cell's per-persona
  ``mean`` and contributing count ``n``).
* :func:`plot_run_charts` -- per-combo diagnostic charts (call counts, retry
  rate, value diversity, method distribution, prompt-size growth, wall clock,
  token consumption/budget, latency) from a
  :func:`diagnostics.compute_metrics` dict.
* :func:`plot_run_comparison` -- cross-factor comparison charts (grouped box
  plots with Dunn significance brackets, mean +/- SD bars, model x method
  heatmaps) from a :func:`comparison.build_summary_comparison` structure.

Boundary: this module never parses telemetry, never does cost arithmetic, and
never touches the CSV schema; it only reads finished metric structures and draws.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from population_synthetic.analysis.generation_metadata.combo_aggregator import METRIC_NAMES, ComboSummary
from population_synthetic.analysis.utils._stats import median as _median
from population_synthetic.analysis.utils._stats import percentile as _percentile
from population_synthetic.analysis.utils.axes import strategy_complexity_order
from population_synthetic.analysis.utils.figures import save_figure
from population_synthetic.analysis.utils.palette import heatmap_cmap, text_color_on

__all__ = ["render_metric_heatmaps", "plot_run_charts", "plot_run_comparison"]

# PNG raster resolution forwarded to save_figure (the SVG sibling is vector and
# ignores it); matches the dpi=150 used across the analysis chart modules.
_DPI = 150

# ------------------------------------------------------------------
# Chart styling constants
# ------------------------------------------------------------------

_COLOR_BLUE   = "#4878CF"
_COLOR_ORANGE = "#E8935A"
_COLOR_RED    = "#D65F5F"
_COLOR_GREEN  = "#6AB187"
_COLOR_YELLOW = "#E9C46A"

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
    """Methods in config-derived pipeline-complexity order (raises on an unknown id)."""
    return strategy_complexity_order(sorted(strategies))


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
        im = ax.imshow(masked, aspect="auto", cmap=heatmap_cmap())

        ax.set_xticks(range(len(methods)))
        ax.set_xticklabels(methods, rotation=30, ha="right", fontsize=8)
        ax.set_yticks(range(len(models)))
        ax.set_yticklabels(models, fontsize=8)

        cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
        cbar.set_label(_METRIC_LABELS.get(metric, metric), fontsize=8)

        for i in range(len(models)):
            for j in range(len(methods)):
                if np.isnan(means[i, j]):
                    # Distinguish "combo absent" from "combo present, metric ungated".
                    if (models[i], methods[j]) in by_cell:
                        ax.text(j, i, "n/a", ha="center", va="center", fontsize=6.5, color="#666666")
                    continue
                color = text_color_on(im, means[i, j])
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


# ==================================================================
# Per-combo diagnostic charts
#
# Consume the nested metrics dict produced by
# :func:`diagnostics.compute_metrics`.  Entry point: :func:`plot_run_charts`.
# ==================================================================

def _plot_category_call_count(metrics: dict, output_dir: Path) -> Path | None:
    """Horizontal bar chart: call count per category, sorted descending."""
    if not metrics.get("per_category"):
        return None

    data = {cat: info["call_count"] for cat, info in metrics["per_category"].items()}
    if not data:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)

    cats_sorted = sorted(data, key=lambda c: data[c])  # ascending → bottom-to-top
    vals = [data[c] for c in cats_sorted]
    n_cats = len(cats_sorted)

    fig, ax = plt.subplots(figsize=(10, max(4, n_cats * 0.45 + 2)))
    ax.barh(range(n_cats), vals, color=_COLOR_BLUE, edgecolor="white", linewidth=0.4)
    ax.set_yticks(range(n_cats))
    ax.set_yticklabels(cats_sorted, fontsize=8)
    ax.set_xlabel("Call count", fontsize=9)
    ax.set_title("LLM calls per category", fontsize=11, fontweight="bold")
    ax.tick_params(axis="both", labelsize=8)

    fig.tight_layout()
    return save_figure(fig, output_dir / "category_call_count.png", dpi=_DPI)


def _plot_category_retry_rate(metrics: dict, output_dir: Path) -> Path | None:
    """Horizontal bar chart: retry rate per category, sorted descending (same order as call count)."""
    if not metrics.get("per_category"):
        return None

    # Sort order: descending by call_count (largest at top) to match chart 1
    per_cat = metrics["per_category"]
    cats_sorted = sorted(per_cat, key=lambda c: per_cat[c]["call_count"])  # ascending → bottom-to-top
    rates = {cat: per_cat[cat]["retry_rate"] for cat in cats_sorted}

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)

    n_cats = len(cats_sorted)
    vals = [rates[c] for c in cats_sorted]

    max_rate = max(vals) if vals else 0.0
    x_max = max(0.05, max_rate * 1.15) if max_rate > 0 else 0.10

    fig, ax = plt.subplots(figsize=(10, max(4, n_cats * 0.45 + 2)))
    ax.barh(range(n_cats), vals, color=_COLOR_RED, edgecolor="white", linewidth=0.4)
    ax.set_yticks(range(n_cats))
    ax.set_yticklabels(cats_sorted, fontsize=8)
    ax.set_xlabel("Retry rate", fontsize=9)
    ax.set_xlim(0, x_max)
    ax.set_title("Retry rate per category", fontsize=11, fontweight="bold")
    ax.tick_params(axis="both", labelsize=8)

    ax.axvline(0.10, color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
    ax.text(0.10, n_cats - 0.5, "10%", va="top", ha="left", fontsize=7, color="gray", alpha=0.8)

    fig.tight_layout()
    return save_figure(fig, output_dir / "category_retry_rate.png", dpi=_DPI)


def _plot_value_diversity_entropy(metrics: dict, output_dir: Path) -> Path | None:
    """Horizontal bar chart: Shannon entropy per category, annotated with unique value count."""
    if not metrics.get("value_diversity"):
        return None

    vd = metrics["value_diversity"]
    cats_sorted = sorted(vd, key=lambda c: vd[c]["entropy_bits"])  # ascending → bottom-to-top
    if not cats_sorted:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)

    n_cats = len(cats_sorted)
    vals = [vd[c]["entropy_bits"] for c in cats_sorted]

    fig, ax = plt.subplots(figsize=(10, max(4, n_cats * 0.45 + 2)))
    ax.barh(range(n_cats), vals, color=_COLOR_BLUE, edgecolor="white", linewidth=0.4)
    ax.set_yticks(range(n_cats))
    ax.set_yticklabels(cats_sorted, fontsize=8)
    ax.set_xlabel("Entropy (bits)", fontsize=9)
    ax.set_title("Value diversity (Shannon entropy) per category", fontsize=11, fontweight="bold")
    ax.tick_params(axis="both", labelsize=8)

    x_max = max(vals) if vals else 1.0
    x_offset = x_max * 0.01

    for idx, (cat, val) in enumerate(zip(cats_sorted, vals)):
        unique = vd[cat]["unique_values"]
        ax.text(val + x_offset, idx, f"({unique} unique)", va="center", fontsize=8)

    fig.tight_layout()
    return save_figure(fig, output_dir / "value_diversity_entropy.png", dpi=_DPI)


def _plot_method_distribution(metrics: dict, output_dir: Path) -> Path | None:
    """Bar chart: method call counts. Horizontal when many methods or long names."""
    if not metrics.get("method_distribution"):
        return None

    dist = metrics["method_distribution"]
    if not dist:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)

    methods = sorted(dist, key=lambda m: dist[m], reverse=True)
    vals = [dist[m] for m in methods]
    n_methods = len(methods)

    use_horizontal = n_methods > 10 or any(len(m) > 20 for m in methods)

    if use_horizontal:
        methods_plot = list(reversed(methods))  # largest at top
        vals_plot = list(reversed(vals))
        fig, ax = plt.subplots(figsize=(10, max(4, n_methods * 0.45 + 2)))
        ax.barh(range(n_methods), vals_plot, color=_COLOR_BLUE, edgecolor="white", linewidth=0.4)
        ax.set_yticks(range(n_methods))
        ax.set_yticklabels(methods_plot, fontsize=8)
        ax.set_xlabel("Call count", fontsize=9)
    else:
        fig, ax = plt.subplots(figsize=(max(6, n_methods * 1.0 + 2), 5))
        ax.bar(range(n_methods), vals, color=_COLOR_BLUE, edgecolor="white", linewidth=0.4)
        ax.set_xticks(range(n_methods))
        ax.set_xticklabels(methods, rotation=30, ha="right", fontsize=8)
        ax.set_ylabel("Call count", fontsize=9)

    ax.set_title("Method distribution", fontsize=11, fontweight="bold")
    ax.tick_params(axis="both", labelsize=8)

    fig.tight_layout()
    return save_figure(fig, output_dir / "method_distribution.png", dpi=_DPI)


def _plot_prompt_size_growth(metrics: dict, output_dir: Path) -> Path | None:
    """Line chart: median prompt length by chain position, with optional p25/p75 band."""
    if not metrics.get("prompt_size_growth"):
        return None

    growth = metrics["prompt_size_growth"]
    if not growth:
        return None

    # Group prompt_len by chain_position
    from collections import defaultdict
    pos_lens: dict[int, list[float]] = defaultdict(list)
    for entry in growth:
        pos = entry.get("chain_position")
        plen = entry.get("prompt_len")
        if pos is not None and plen is not None:
            pos_lens[pos].append(float(plen))

    if not pos_lens:
        return None

    positions = sorted(pos_lens)
    medians = [_median(pos_lens[p]) for p in positions]

    total_personas = metrics.get("summary", {}).get("total_personas", 1)
    compute_band = total_personas > 1

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(positions, medians, color=_COLOR_BLUE, linewidth=2, label="Median")

    if compute_band:
        p25_vals = [_percentile(pos_lens[p], 25) for p in positions]
        p75_vals = [_percentile(pos_lens[p], 75) for p in positions]
        ax.fill_between(positions, p25_vals, p75_vals, alpha=0.15, color=_COLOR_BLUE)

    ax.set_xlabel("Chain position", fontsize=9)
    ax.set_ylabel("Prompt length (chars)", fontsize=9)
    ax.set_title("Prompt size growth by chain position", fontsize=11, fontweight="bold")
    ax.tick_params(axis="both", labelsize=8)
    if compute_band:
        ax.legend(["Median (p25–p75 band)"], fontsize=8)

    fig.tight_layout()
    return save_figure(fig, output_dir / "prompt_size_growth.png", dpi=_DPI)


def _plot_wall_clock_per_persona(metrics: dict, output_dir: Path) -> Path | None:
    """Horizontal bar chart: wall-clock time per persona (filtered, ≥2 personas required)."""
    if not metrics.get("wall_clock_per_persona"):
        return None

    valid = {
        pid: v
        for pid, v in metrics["wall_clock_per_persona"].items()
        if v is not None
    }
    if len(valid) <= 1:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)

    pids_sorted = sorted(valid, key=lambda p: valid[p])  # ascending → bottom-to-top
    vals = [valid[p] for p in pids_sorted]
    n_pids = len(pids_sorted)

    fig, ax = plt.subplots(figsize=(10, max(4, n_pids * 0.45 + 2)))
    ax.barh(range(n_pids), vals, color=_COLOR_BLUE, edgecolor="white", linewidth=0.4)
    ax.set_yticks(range(n_pids))
    ax.set_yticklabels(pids_sorted, fontsize=8)
    ax.set_xlabel("Wall-clock time (s)", fontsize=9)
    ax.set_title("Wall-clock time per persona", fontsize=11, fontweight="bold")
    ax.tick_params(axis="both", labelsize=8)

    fig.tight_layout()
    return save_figure(fig, output_dir / "wall_clock_per_persona.png", dpi=_DPI)


def _plot_token_consumption_by_category(metrics: dict, output_dir: Path) -> Path | None:
    """Stacked horizontal bar: prompt + completion tokens per category."""
    if metrics.get("token_consumption_per_category") is None:
        return None

    tok = metrics["token_consumption_per_category"]
    if not tok:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)

    cats_sorted = sorted(tok, key=lambda c: tok[c]["total_tokens"])  # ascending → bottom-to-top
    prompt_vals = [tok[c]["prompt_tokens"] for c in cats_sorted]
    completion_vals = [tok[c]["completion_tokens"] for c in cats_sorted]
    n_cats = len(cats_sorted)

    fig, ax = plt.subplots(figsize=(10, max(4, n_cats * 0.45 + 2)))
    y_pos = range(n_cats)
    ax.barh(y_pos, prompt_vals, color=_COLOR_BLUE, label="Prompt",
            edgecolor="white", linewidth=0.4)
    ax.barh(y_pos, completion_vals, left=prompt_vals, color=_COLOR_ORANGE,
            label="Completion", edgecolor="white", linewidth=0.4)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(cats_sorted, fontsize=8)
    ax.set_xlabel("Token count", fontsize=9)
    ax.set_title("Token consumption by category", fontsize=11, fontweight="bold")
    ax.tick_params(axis="both", labelsize=8)
    ax.legend(fontsize=8)

    fig.tight_layout()
    return save_figure(fig, output_dir / "token_consumption_by_category.png", dpi=_DPI)


def _plot_token_budget_by_step_type(metrics: dict, output_dir: Path) -> Path | None:
    """Grouped vertical bar: prompt and completion tokens per step type."""
    if metrics.get("token_budget_by_step_type") is None:
        return None

    budget = metrics["token_budget_by_step_type"]
    if not budget:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    output_dir.mkdir(parents=True, exist_ok=True)

    step_types = sorted(budget)
    n_types = len(step_types)
    prompt_vals = [budget[s]["prompt_tokens"] for s in step_types]
    completion_vals = [budget[s]["completion_tokens"] for s in step_types]

    x = np.arange(n_types)
    bar_width = 0.35

    fig, ax = plt.subplots(figsize=(max(6, n_types * 1.0 + 2), 5))
    ax.bar(x - bar_width / 2, prompt_vals, width=bar_width, color=_COLOR_BLUE,
           label="Prompt", edgecolor="white", linewidth=0.4)
    ax.bar(x + bar_width / 2, completion_vals, width=bar_width, color=_COLOR_ORANGE,
           label="Completion", edgecolor="white", linewidth=0.4)

    ax.set_xticks(x)
    ax.set_xticklabels(step_types, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Token count", fontsize=9)
    ax.set_title("Token budget by step type", fontsize=11, fontweight="bold")
    ax.tick_params(axis="both", labelsize=8)
    ax.legend(fontsize=8)

    fig.tight_layout()
    return save_figure(fig, output_dir / "token_budget_by_step_type.png", dpi=_DPI)


def _plot_latency_by_category(metrics: dict, output_dir: Path) -> Path | None:
    """Grouped horizontal bar: median / p95 / max latency per category."""
    if metrics.get("latency_by_category") is None:
        return None

    lat = metrics["latency_by_category"]
    if not lat:
        return None

    # Filter: skip categories where all three stats are None
    filtered = {
        cat: info
        for cat, info in lat.items()
        if not (info.get("median_ms") is None
                and info.get("p95_ms") is None
                and info.get("max_ms") is None)
    }
    if not filtered:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)

    # Sort by p95 descending (None → 0 for sort key)
    cats_sorted = sorted(
        filtered,
        key=lambda c: (filtered[c].get("p95_ms") or 0.0),
        reverse=True,
    )
    # Reverse for horizontal chart (highest at top = first in list → last in y_pos)
    cats_plot = list(reversed(cats_sorted))
    n_cats = len(cats_plot)

    median_vals = [filtered[c].get("median_ms") or 0.0 for c in cats_plot]
    p95_vals    = [filtered[c].get("p95_ms")    or 0.0 for c in cats_plot]
    max_vals    = [filtered[c].get("max_ms")    or 0.0 for c in cats_plot]

    bar_height = 0.25
    y_base = range(n_cats)

    fig, ax = plt.subplots(figsize=(10, max(4, n_cats * 0.9 + 2)))
    ax.barh([y + bar_height for y in y_base], median_vals, height=bar_height,
            color=_COLOR_GREEN,  label="Median",  edgecolor="white", linewidth=0.3)
    ax.barh([y              for y in y_base], p95_vals,    height=bar_height,
            color=_COLOR_YELLOW, label="p95",     edgecolor="white", linewidth=0.3)
    ax.barh([y - bar_height for y in y_base], max_vals,    height=bar_height,
            color=_COLOR_RED,    label="Max",     edgecolor="white", linewidth=0.3)

    ax.set_yticks(list(y_base))
    ax.set_yticklabels(cats_plot, fontsize=8)
    ax.set_xlabel("Latency (ms)", fontsize=9)
    ax.set_title("Latency by category (median / p95 / max)", fontsize=11, fontweight="bold")
    ax.tick_params(axis="both", labelsize=8)
    ax.legend(fontsize=8)

    fig.tight_layout()
    return save_figure(fig, output_dir / "latency_by_category.png", dpi=_DPI)


def plot_run_charts(metrics: dict, output_dir: Path) -> list[Path]:
    """Generate all applicable per-combo diagnostic charts. Returns list of paths written."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    plotters = [
        _plot_category_call_count,
        _plot_category_retry_rate,
        _plot_value_diversity_entropy,
        _plot_method_distribution,
        _plot_prompt_size_growth,
        _plot_wall_clock_per_persona,
        _plot_token_consumption_by_category,
        _plot_token_budget_by_step_type,
        _plot_latency_by_category,
    ]
    return [p for fn in plotters if (p := fn(metrics, output_dir)) is not None]


# ==================================================================
# Cross-factor comparison charts
#
# Consume the in-memory structure from :func:`comparison.build_summary_comparison` and
# render, per metric and per factor (model / method), a grouped box plot with
# Dunn significance brackets, a mean +/- SD grouped-bar companion, and a
# model x method heatmap.  Entry point: :func:`plot_run_comparison`.
# ==================================================================

# Cap on the number of significance brackets drawn on a single box plot, to keep
# many-group figures readable.  Omitted pairs are reported (full pairwise results
# remain in the comparison JSON).
_MAX_BRACKETS = 8


def _stars(p: float | None) -> str:
    """Significance asterisks for a p-value."""
    if p is None:
        return "ns"
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return "ns"


def _kruskal_subtitle(kruskal: dict[str, Any]) -> str:
    h = kruskal.get("H")
    p = kruskal.get("p")
    if h is None or p is None:
        note = kruskal.get("note", "not computed")
        return f"Kruskal-Wallis: n/a ({note})"
    return f"Kruskal-Wallis H={h:.2f}, p={p:.3g} (k={kruskal.get('k')}, N={kruskal.get('n')})"


def _figwidth(n_groups: int) -> float:
    return max(7.0, min(22.0, n_groups * 1.1 + 3.0))


def _plot_box_grouped(
    block: dict[str, Any],
    factor_label: str,
    metric_label: str,
    unit: str,
    out_path: Path,
) -> Path | None:
    """Box plot of *metric* across the groups of one factor, with Dunn brackets."""
    groups: dict[str, list[float]] = block["groups"]
    order = [g for g in block["order"] if groups.get(g)]
    if not order:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    out_path.parent.mkdir(parents=True, exist_ok=True)

    data = [groups[g] for g in order]
    positions = list(range(1, len(order) + 1))
    pos_of = {g: i + 1 for i, g in enumerate(order)}

    fig, ax = plt.subplots(figsize=(_figwidth(len(order)), 6))

    bp = ax.boxplot(
        data,
        positions=positions,
        widths=0.6,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": "black", "linewidth": 1.4},
    )
    for patch in bp["boxes"]:
        patch.set_facecolor(_COLOR_BLUE)
        patch.set_alpha(0.55)
        patch.set_edgecolor("#33486F")

    # Overlay individual observations (jittered) -- N per group is small.
    rng = np.random.default_rng(0)
    for i, g in enumerate(order):
        vals = groups[g]
        jitter = rng.uniform(-0.14, 0.14, size=len(vals))
        ax.scatter(
            np.full(len(vals), i + 1) + jitter, vals,
            s=14, color=_COLOR_ORANGE, alpha=0.7, edgecolor="white", linewidth=0.3, zorder=3,
        )

    ax.set_xticks(positions)
    ax.set_xticklabels(order, rotation=35, ha="right", fontsize=8)
    ylabel = f"{metric_label} ({unit})" if unit else metric_label
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(f"{metric_label} by {factor_label}", fontsize=12, fontweight="bold")
    ax.text(
        0.5, 1.015, _kruskal_subtitle(block["kruskal"]),
        transform=ax.transAxes, ha="center", va="bottom", fontsize=8, color="#444444",
    )
    ax.grid(axis="y", linestyle=":", alpha=0.4)

    # Significance brackets for significant Dunn pairs (within plotted groups).
    sig = [
        d for d in block.get("dunn", [])
        if d.get("p_holm") is not None and d["p_holm"] < 0.05
        and d["a"] in pos_of and d["b"] in pos_of
    ]
    sig.sort(key=lambda d: d["p_holm"])
    omitted = max(0, len(sig) - _MAX_BRACKETS)
    sig = sig[:_MAX_BRACKETS]

    all_vals = [v for vals in data for v in vals]
    if sig and all_vals:
        ymin, ymax = min(all_vals), max(all_vals)
        span = (ymax - ymin) or (abs(ymax) or 1.0)
        step = span * 0.09
        for level, d in enumerate(sig):
            x1, x2 = sorted((pos_of[d["a"]], pos_of[d["b"]]))
            y = ymax + step * (level + 1)
            ax.plot(
                [x1, x1, x2, x2],
                [y - step * 0.25, y, y, y - step * 0.25],
                color="black", linewidth=1.0,
            )
            ax.text((x1 + x2) / 2.0, y, _stars(d["p_holm"]), ha="center", va="bottom", fontsize=9)
        ax.set_ylim(top=ymax + step * (len(sig) + 1.5))

    if omitted:
        ax.text(
            0.99, 0.01, f"+{omitted} more significant pair(s) omitted",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7, color="#888888",
        )
        print(f"  note: {out_path.name}: {omitted} significant pair(s) omitted from brackets")

    fig.tight_layout()
    return save_figure(fig, out_path, dpi=_DPI)


def _plot_grouped_bar_errorbars(
    block: dict[str, Any],
    factor_label: str,
    metric_label: str,
    unit: str,
    out_path: Path,
) -> Path | None:
    """Mean +/- SD bars per group (companion view to the box plot)."""
    groups: dict[str, list[float]] = block["groups"]
    order = [g for g in block["order"] if groups.get(g)]
    if not order:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    out_path.parent.mkdir(parents=True, exist_ok=True)

    means = [float(np.mean(groups[g])) for g in order]
    stds = [float(np.std(groups[g], ddof=1)) if len(groups[g]) > 1 else 0.0 for g in order]
    positions = list(range(len(order)))

    fig, ax = plt.subplots(figsize=(_figwidth(len(order)), 6))
    ax.bar(
        positions, means, yerr=stds, capsize=4,
        color=_COLOR_GREEN, edgecolor="#33486F", linewidth=0.5, alpha=0.85,
        error_kw={"elinewidth": 1.0, "ecolor": "#444444"},
    )
    ax.set_xticks(positions)
    ax.set_xticklabels(order, rotation=35, ha="right", fontsize=8)
    ylabel = f"{metric_label} ({unit})" if unit else metric_label
    ax.set_ylabel(f"mean {ylabel}", fontsize=9)
    ax.set_title(f"{metric_label} by {factor_label} (mean +/- SD)", fontsize=12, fontweight="bold")
    ax.text(
        0.5, 1.015, _kruskal_subtitle(block["kruskal"]),
        transform=ax.transAxes, ha="center", va="bottom", fontsize=8, color="#444444",
    )
    ax.grid(axis="y", linestyle=":", alpha=0.4)

    fig.tight_layout()
    return save_figure(fig, out_path, dpi=_DPI)


def _plot_heatmap(
    matrix: dict[str, Any],
    metric_label: str,
    unit: str,
    out_path: Path,
) -> Path | None:
    """Model x method heatmap of the per-cell summary statistic."""
    import numpy as np

    models = matrix["models"]
    methods = matrix["methods"]
    if not models or not methods:
        return None

    values = np.array(
        [[np.nan if v is None else v for v in row] for row in matrix["values"]],
        dtype=float,
    )
    if np.all(np.isnan(values)):
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(
        figsize=(max(6.0, len(methods) * 1.3 + 3.0), max(5.0, len(models) * 0.5 + 2.5))
    )
    masked = np.ma.masked_invalid(values)
    im = ax.imshow(masked, aspect="auto", cmap=heatmap_cmap())

    ax.set_xticks(range(len(methods)))
    ax.set_xticklabels(methods, rotation=35, ha="right", fontsize=8)
    ax.set_yticks(range(len(models)))
    ax.set_yticklabels(models, fontsize=8)

    agg = matrix.get("cell_agg", "value")
    label = f"{agg} {metric_label}" + (f" ({unit})" if unit else "")
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(label, fontsize=8)

    for i in range(len(models)):
        for j in range(len(methods)):
            v = values[i, j]
            if np.isnan(v):
                continue
            ax.text(j, i, f"{v:.3g}", ha="center", va="center", fontsize=7,
                    color=text_color_on(im, v))

    ax.set_title(f"{metric_label}: model x method", fontsize=12, fontweight="bold")
    fig.tight_layout()
    return save_figure(fig, out_path, dpi=_DPI)


def plot_run_comparison(result: dict[str, Any], output_dir: str | Path) -> list[Path]:
    """Render all comparison charts.  Returns the list of written paths."""
    output_dir = Path(output_dir)
    written: list[Path] = []

    for key, entry in result["metrics"].items():
        if entry.get("skipped"):
            print(f"  skip {key}: {entry['skipped']}")
            continue

        metric_label = entry["label"]
        unit = entry["unit"]

        for factor, factor_label in (("by_model", "model"), ("by_method", "method")):
            block = entry.get(factor)
            if block is None:
                continue
            box = _plot_box_grouped(
                block, factor_label, metric_label, unit,
                output_dir / f"{key}_{factor}_box.png",
            )
            if box:
                written.append(box)
            bar = _plot_grouped_bar_errorbars(
                block, factor_label, metric_label, unit,
                output_dir / f"{key}_{factor}_bar.png",
            )
            if bar:
                written.append(bar)

        matrix = entry.get("matrix")
        if matrix:
            heat = _plot_heatmap(matrix, metric_label, unit, output_dir / f"{key}_heatmap.png")
            if heat:
                written.append(heat)

    return written
