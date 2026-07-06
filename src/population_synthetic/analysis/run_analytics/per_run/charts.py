"""
charts.py -- Visualization tools for run analytics metrics.

Generates PNG charts from the metrics dict produced by
:func:`population_synthetic.analysis.run_analytics.per_run.aggregator.compute_metrics`.

Entry point: :func:`plot_run_charts`.
"""

from __future__ import annotations

from pathlib import Path

from population_synthetic.analysis.utils._stats import median as _median
from population_synthetic.analysis.utils._stats import percentile as _percentile

# ------------------------------------------------------------------
# Chart styling constants
# ------------------------------------------------------------------

_COLOR_BLUE   = "#4878CF"
_COLOR_ORANGE = "#E8935A"
_COLOR_RED    = "#D65F5F"
_COLOR_GREEN  = "#6AB187"
_COLOR_YELLOW = "#E9C46A"


# ------------------------------------------------------------------
# Individual chart functions
# ------------------------------------------------------------------

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
    out_path = output_dir / "category_call_count.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


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
    out_path = output_dir / "category_retry_rate.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


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
    out_path = output_dir / "value_diversity_entropy.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


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
    out_path = output_dir / "method_distribution.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


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
    out_path = output_dir / "prompt_size_growth.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


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
    out_path = output_dir / "wall_clock_per_persona.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


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
    out_path = output_dir / "token_consumption_by_category.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


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
    out_path = output_dir / "token_budget_by_step_type.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


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
    out_path = output_dir / "latency_by_category.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ------------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------------

def plot_run_charts(metrics: dict, output_dir: Path) -> list[Path]:
    """Generate all applicable run analytics charts. Returns list of paths written."""
    from pathlib import Path as _Path
    output_dir = _Path(output_dir)
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
