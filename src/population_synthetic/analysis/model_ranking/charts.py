"""charts.py -- Charts for the cross-model performance comparison.

Consumes the serialisable structure from
:func:`population_synthetic.analysis.model_ranking.builder.build_performance_comparison`
and renders, per country:

* a **heatmap** -- rows = model × strategy combos in rank order, columns = the
  comparison attributes plus a visually separated "overall" column, cell =
  TV-similarity;
* a **leaderboard** -- horizontal bars of overall TV-similarity (best on top)
  with each combo's coherence score annotated;
* optional **per-attribute grouped bars** -- one chart per attribute, strategies
  on the x-axis (complexity order), one bar series per model.

Follows the project charting conventions (deferred ``Agg`` matplotlib import,
``dpi=150``/``bbox_inches="tight"``, ``plt.close`` on every path).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from population_synthetic.analysis.utils.axes import strategy_complexity_order
from population_synthetic.analysis.utils.palette import heatmap_cmap, text_color_on

_COLOR_SERIES = (
    "#4878CF",
    "#D65F5F",
    "#6AB187",
    "#E8935A",
    "#E9C46A",
    "#8172B2",
    "#64B5CD",
)


def _combo_label(combo: dict[str, Any]) -> str:
    return f"{combo['model']} / {combo['strategy']}"


def _ordered_strategies(strategies: list[str]) -> list[str]:
    """Strategies in config-derived complexity order (raises on an unknown id)."""
    return strategy_complexity_order(strategies)


# ------------------------------------------------------------------
# Heatmap (combos × attributes + overall)
# ------------------------------------------------------------------

def plot_performance_heatmap(result: dict[str, Any], out_path: str | Path) -> Path | None:
    """Rank-ordered combo × attribute heatmap of TV-similarity, plus an overall column."""
    attributes: list[str] = result["metadata"]["attributes"]
    ranking: list[str] = result["ranking"]
    if not attributes or not ranking:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    values = np.full((len(ranking), len(attributes) + 1), np.nan)
    labels: list[str] = []
    for i, slug in enumerate(ranking):
        combo = result["combos"][slug]
        labels.append(_combo_label(combo))
        for j, attr in enumerate(attributes):
            values[i, j] = combo["per_attribute"][attr]["tv_similarity"]
        values[i, -1] = combo["overall"]["tv_similarity_mean"]

    if np.all(np.isnan(values)):
        return None

    fig, ax = plt.subplots(
        figsize=(max(8.0, (len(attributes) + 1) * 0.8 + 3.0), max(4.0, len(ranking) * 0.45 + 2.5))
    )
    masked = np.ma.masked_invalid(values)
    im = ax.imshow(masked, aspect="auto", cmap=heatmap_cmap())

    ax.set_xticks(range(len(attributes) + 1))
    ax.set_xticklabels(attributes + ["overall"], rotation=40, ha="right", fontsize=8)
    ax.set_yticks(range(len(ranking)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.axvline(len(attributes) - 0.5, color="white", linewidth=2.5)

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("TV-similarity (1 - TV distance)", fontsize=8)

    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            v = values[i, j]
            if np.isnan(v):
                continue
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=6.5,
                    color=text_color_on(im, v))

    country = result["metadata"]["country"]
    ax.set_title(
        f"{country}: TV-similarity per attribute (combos in rank order)",
        fontsize=12, fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ------------------------------------------------------------------
# Leaderboard (overall ranking)
# ------------------------------------------------------------------

def plot_performance_leaderboard(result: dict[str, Any], out_path: str | Path) -> Path | None:
    """Horizontal bars of overall TV-similarity (best on top), coherence annotated."""
    ranking: list[str] = result["ranking"]
    if not ranking:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    labels: list[str] = []
    means: list[float] = []
    coherences: list[float] = []
    for slug in ranking:
        combo = result["combos"][slug]
        labels.append(_combo_label(combo))
        means.append(combo["overall"]["tv_similarity_mean"])
        coherences.append(combo["overall"]["coherence_score"])

    # Best combo at the top of the chart.
    positions = list(range(len(ranking)))[::-1]

    fig, ax = plt.subplots(figsize=(9.0, max(3.5, len(ranking) * 0.45 + 1.8)))
    ax.barh(
        positions, means,
        color=_COLOR_SERIES[0], edgecolor="#33486F", linewidth=0.5, alpha=0.85, height=0.65,
    )
    for pos, mean, coherence in zip(positions, means, coherences):
        if mean == mean:
            ax.text(
                mean, pos, f"  {mean:.3f}  (coh {coherence:.3f})",
                va="center", ha="left", fontsize=7.5, color="#333333",
            )

    ax.set_yticks(positions)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("mean TV-similarity across attributes", fontsize=9)
    finite = [m for m in means if m == m]
    if finite:
        ax.set_xlim(0.0, min(1.0, max(finite) * 1.18))
    ax.grid(axis="x", linestyle=":", alpha=0.4)

    country = result["metadata"]["country"]
    ax.set_title(f"{country}: model x strategy leaderboard", fontsize=12, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ------------------------------------------------------------------
# C2ST AUC vs mean TV-similarity scatter (multivariate summary)
# ------------------------------------------------------------------

def plot_c2st_vs_tv(result: dict[str, Any], out_path: str | Path) -> Path | None:
    """Scatter of C2ST ROC-AUC vs mean TV-similarity across combos, coloured by strategy.

    Positions each combo by its marginal fidelity (x = mean TV-similarity) and
    its joint discriminability (y = C2ST AUC, 0.5 = indistinguishable joint,
    higher = more separable = worse). Colour encodes strategy in complexity order
    (identity, fixed order -- never cycled), so the reader can see whether the
    strategy that wins on marginals also produces the least-separable joint.

    Combos lacking a finite C2ST AUC (reports predating the multivariate block,
    or degenerate synthetic populations) are skipped. Returns ``None`` when no
    combo has a plottable point.
    """
    combos: dict[str, Any] = result.get("combos", {})
    strategies = _ordered_strategies(result["metadata"]["strategies"])
    color_for = {s: _COLOR_SERIES[i % len(_COLOR_SERIES)] for i, s in enumerate(strategies)}

    by_strategy: dict[str, list[tuple[float, float, str]]] = {}
    for combo in combos.values():
        multivariate = combo.get("multivariate") or {}
        auc = multivariate.get("c2st_auc")
        tv = combo["overall"]["tv_similarity_mean"]
        if auc is None or auc != auc or tv != tv:  # None or NaN -> not plottable
            continue
        by_strategy.setdefault(combo["strategy"], []).append((float(tv), float(auc), combo["model"]))
    if not by_strategy:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8.5, 6.0))
    all_aucs: list[float] = []
    for strategy in strategies:
        pts = by_strategy.get(strategy)
        if not pts:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        all_aucs.extend(ys)
        ax.scatter(
            xs, ys, s=70, color=color_for[strategy], label=strategy,
            edgecolor="white", linewidth=0.6, alpha=0.9, zorder=3,
        )

    ax.axhline(0.5, color="#888888", linestyle="--", linewidth=1.0, zorder=1)
    ax.text(
        0.01, 0.5, "0.5 = indistinguishable joint",
        transform=ax.get_yaxis_transform(), va="bottom", ha="left",
        fontsize=7.5, color="#666666",
    )

    ax.set_xlabel("mean TV-similarity across attributes (marginal fidelity)", fontsize=9)
    ax.set_ylabel("C2ST ROC-AUC (joint discriminability; 0.5 best)", fontsize=9)
    lo = min([0.5] + all_aucs) - 0.03
    hi = max([0.5] + all_aucs) + 0.03
    ax.set_ylim(lo, min(1.02, hi))
    ax.grid(True, linestyle=":", alpha=0.4)
    ax.legend(title="strategy", fontsize=7.5, title_fontsize=8)

    country = result["metadata"]["country"]
    ax.set_title(
        f"{country}: joint discriminability (C2ST) vs marginal fidelity",
        fontsize=12, fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ------------------------------------------------------------------
# Per-attribute grouped bars (optional)
# ------------------------------------------------------------------

def plot_attribute_bars(result: dict[str, Any], out_dir: str | Path) -> list[Path]:
    """One grouped bar chart per attribute: strategies on x, one series per model."""
    attributes: list[str] = result["metadata"]["attributes"]
    models: list[str] = result["metadata"]["models"]
    strategies = _ordered_strategies(result["metadata"]["strategies"])
    if not attributes or not models or not strategies:
        return []

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # (model, strategy) -> combo lookup.
    by_cell = {
        (combo["model"], combo["strategy"]): combo
        for combo in result["combos"].values()
    }

    written: list[Path] = []
    width = 0.8 / len(models)
    x = np.arange(len(strategies))

    for attr in attributes:
        fig, ax = plt.subplots(figsize=(max(7.0, len(strategies) * 1.4 + 2.0), 5.0))
        for m_idx, model in enumerate(models):
            heights = []
            for strategy in strategies:
                combo = by_cell.get((model, strategy))
                if combo is None:
                    heights.append(np.nan)
                else:
                    heights.append(combo["per_attribute"][attr]["tv_similarity"])
            offsets = x - 0.4 + width * (m_idx + 0.5)
            ax.bar(
                offsets, heights, width=width,
                label=model, color=_COLOR_SERIES[m_idx % len(_COLOR_SERIES)],
                edgecolor="#33486F", linewidth=0.4, alpha=0.85,
            )

        ax.set_xticks(x)
        ax.set_xticklabels(strategies, rotation=25, ha="right", fontsize=8)
        ax.set_ylabel("TV-similarity", fontsize=9)
        ax.set_ylim(0.0, 1.0)
        ax.grid(axis="y", linestyle=":", alpha=0.4)
        ax.legend(fontsize=7.5)

        country = result["metadata"]["country"]
        ax.set_title(f"{country}: {attr} -- TV-similarity by model x strategy",
                     fontsize=11, fontweight="bold")
        out_path = out_dir / f"{attr}_bars.png"
        fig.tight_layout()
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        written.append(out_path)

    return written
