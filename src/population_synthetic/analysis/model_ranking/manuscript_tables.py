"""manuscript_tables.py -- Manuscript-grade fidelity heatmap-tables.

Two print-oriented renderers, both **pure consumers** of the built
performance ``result`` dict (from
:func:`population_synthetic.analysis.model_ranking.builder.build_performance_comparison`):

* :func:`plot_model_fidelity_table` -- rows = models at the single *global-best*
  strategy, columns = the country's demographic axes + an "overall" column,
  cell = TV-similarity. Rows are Overall-sorted; each column's best cell is
  bold + boxed. Cell hue encodes provenance: **hosted** models use ``Blues`` and
  **local** (Ollama) models use ``Oranges``, both evaluated at one shared
  ``Normalize`` so darkness is comparable across the two families.
* :func:`plot_method_fidelity_table` -- rows = strategies, cell = mean over
  models of that strategy's per-axis TV-similarity, single sequential ``viridis``
  ramp (no provenance split). Same Overall-sort and best-per-column bold + box.

This module knows nothing about *how* hosting was derived or *how* the
methods matrix was aggregated -- it reads ``metadata.model_hosting`` and
``methods_matrix`` straight from *result* -- and it does no file discovery.
The hosting class of a model absent from ``metadata.model_hosting`` (e.g. the
builder default of ``{}`` when hosting was not wired) is treated as ``hosted``
for *colouring only*; this is a presentation default, not a data default -- no
computed value is affected.

Follows the project charting conventions (deferred ``Agg`` matplotlib import,
NaN -> grey, ``dpi=150``, white Overall divider) and persists via the shared
:func:`population_synthetic.analysis.utils.figures.save_figure` (PNG + SVG pair).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from population_synthetic.analysis.utils.figures import save_figure

_GREY = "#DDDDDD"
_BOX_EDGE = "#111111"
_ANNOT_FONTSIZE = 7.0


# ------------------------------------------------------------------
# Shared private helpers
# ------------------------------------------------------------------

def _overall_divider(ax, n_attributes: int) -> None:
    """Draw the white vertical divider separating the axes from the Overall column."""
    ax.axvline(n_attributes - 0.5, color="white", linewidth=2.5)


def _text_color_for_rgb(rgb) -> str:
    """Pick white/black annotation text by the cell colour's relative luminance."""
    r, g, b = float(rgb[0]), float(rgb[1]), float(rgb[2])
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return "white" if luminance < 0.5 else "black"


def _best_cells_per_column(values: np.ndarray) -> set[tuple[int, int]]:
    """Row index of the max finite value in each column (ties -> first row).

    Columns whose cells are all NaN contribute no marker.
    """
    best: set[tuple[int, int]] = set()
    n_rows, n_cols = values.shape
    for j in range(n_cols):
        finite = [(i, values[i, j]) for i in range(n_rows) if not np.isnan(values[i, j])]
        if not finite:
            continue
        # max() returns the first maximal element in iteration (row) order -> ties -> first row.
        best_row = max(finite, key=lambda t: t[1])[0]
        best.add((best_row, j))
    return best


def _annotate_and_box(ax, values: np.ndarray, rgba: np.ndarray, best_cells: set[tuple[int, int]]) -> None:
    """Write ``f"{v:.2f}"`` per finite cell; bold + draw a border on the best-per-column cells."""
    from matplotlib.patches import Rectangle

    n_rows, n_cols = values.shape
    for i in range(n_rows):
        for j in range(n_cols):
            v = values[i, j]
            if np.isnan(v):
                continue
            is_best = (i, j) in best_cells
            ax.text(
                j, i, f"{v:.2f}",
                ha="center", va="center", fontsize=_ANNOT_FONTSIZE,
                color=_text_color_for_rgb(rgba[i, j]),
                fontweight="bold" if is_best else "normal",
            )
            if is_best:
                ax.add_patch(
                    Rectangle(
                        (j - 0.5, i - 0.5), 1, 1,
                        fill=False, edgecolor=_BOX_EDGE, linewidth=2.0, zorder=5,
                    )
                )


def _global_best_strategy(matrix: dict[str, Any]) -> str | None:
    """Strategy with the max finite ``overall``; ties -> simpler (complexity order).

    ``matrix["strategies"]`` is already ordered simplest-first, so iterating it
    with a strict ``>`` keeps the earlier (simpler) strategy on a tie. Returns
    ``None`` when no strategy has a finite overall.
    """
    best: str | None = None
    best_val: float | None = None
    for strategy in matrix["strategies"]:
        v = matrix["cells"][strategy]["overall"]
        if v != v:  # NaN
            continue
        if best_val is None or v > best_val:
            best_val = v
            best = strategy
    return best


def _sort_key_desc(value: float, tiebreak: str) -> tuple[float, str]:
    """Descending-by-value sort key; NaN sinks to the bottom, label breaks ties."""
    return (-value if value == value else float("inf"), tiebreak)


# ------------------------------------------------------------------
# Models table (rows = models at the global-best strategy)
# ------------------------------------------------------------------

def plot_model_fidelity_table(result: dict[str, Any], out_path: str | Path) -> Path | None:
    """Models x (axes + Overall) TV-similarity table at the single global-best strategy.

    Picks the global-best strategy (argmax over strategies of the methods-matrix
    Overall column, ties -> simpler), keeps one row per model *at that strategy*,
    and Overall-sorts the rows descending. Models with no combo at the chosen
    strategy are omitted and printed (no silent truncation). Cells are coloured
    by ``metadata.model_hosting`` (hosted -> ``Blues``, local -> ``Oranges``) at a
    shared normalisation; NaN cells are grey; each column's best cell is bold +
    boxed. Returns the PNG path (SVG sibling written too), or ``None`` when there
    is nothing to draw (no attributes, no methods matrix, no strategy, no
    surviving rows, or an all-NaN grid).
    """
    attributes: list[str] = result["metadata"]["attributes"]
    matrix = result.get("methods_matrix") or {}
    if not attributes or not matrix.get("cells"):
        return None

    best_strategy = _global_best_strategy(matrix)
    if best_strategy is None:
        return None

    hosting: dict[str, str] = result["metadata"].get("model_hosting", {})
    models: list[str] = result["metadata"]["models"]
    by_cell = {(combo["model"], combo["strategy"]): combo for combo in result["combos"].values()}

    surviving: list[tuple[str, dict[str, Any]]] = []
    dropped: list[str] = []
    for model in models:
        combo = by_cell.get((model, best_strategy))
        if combo is None:
            dropped.append(model)
            continue
        surviving.append((model, combo))

    if dropped:
        print(
            f"[manuscript_tables] {len(dropped)} model(s) omitted from the models table -- no combo "
            f"at the global-best strategy '{best_strategy}': {', '.join(sorted(dropped))}"
        )
    if not surviving:
        return None

    surviving.sort(key=lambda mc: _sort_key_desc(mc[1]["overall"]["tv_similarity_mean"], mc[0]))
    row_models = [model for model, _ in surviving]

    values = np.full((len(surviving), len(attributes) + 1), np.nan)
    for i, (_model, combo) in enumerate(surviving):
        for j, attr in enumerate(attributes):
            values[i, j] = combo["per_attribute"][attr]["tv_similarity"]
        values[i, -1] = combo["overall"]["tv_similarity_mean"]

    if np.all(np.isnan(values)):
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    finite = values[~np.isnan(values)]
    norm = mcolors.Normalize(vmin=float(finite.min()), vmax=float(finite.max()))
    blues = plt.get_cmap("Blues")
    oranges = plt.get_cmap("Oranges")
    grey_rgba = mcolors.to_rgba(_GREY)

    rgba = np.zeros((values.shape[0], values.shape[1], 4))
    for i, model in enumerate(row_models):
        cmap = oranges if hosting.get(model, "hosted") == "local" else blues
        for j in range(values.shape[1]):
            v = values[i, j]
            rgba[i, j] = grey_rgba if np.isnan(v) else cmap(norm(v))

    n_cols = len(attributes) + 1
    fig, ax = plt.subplots(
        figsize=(max(8.0, n_cols * 0.8 + 3.0), max(4.0, len(surviving) * 0.5 + 2.5))
    )
    ax.imshow(rgba, aspect="auto")

    ax.set_xticks(range(n_cols))
    ax.set_xticklabels(attributes + ["overall"], rotation=40, ha="right", fontsize=8)
    ax.set_yticks(range(len(row_models)))
    ax.set_yticklabels(row_models, fontsize=8)
    _overall_divider(ax, len(attributes))
    _annotate_and_box(ax, values, rgba, _best_cells_per_column(values))

    classes_present = {hosting.get(m, "hosted") for m in row_models}
    handles: list[Patch] = []
    if "hosted" in classes_present:
        handles.append(Patch(facecolor=blues(0.7), edgecolor="none", label="hosted (API)"))
    if "local" in classes_present:
        handles.append(Patch(facecolor=oranges(0.7), edgecolor="none", label="local (Ollama)"))
    if handles:
        ax.legend(
            handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1.0),
            fontsize=7.5, title="hosting", title_fontsize=8, frameon=False,
        )

    country = result["metadata"]["country"]
    ax.set_title(
        f"{country}: model fidelity by axis at strategy '{best_strategy}' (TV-similarity)",
        fontsize=12, fontweight="bold",
    )
    fig.tight_layout()
    return save_figure(fig, Path(out_path), dpi=150)


# ------------------------------------------------------------------
# Methods table (rows = strategies)
# ------------------------------------------------------------------

def plot_method_fidelity_table(result: dict[str, Any], out_path: str | Path) -> Path | None:
    """Strategies x (axes + Overall) mean-over-models TV-similarity table.

    Rows are the strategies from ``methods_matrix.cells``, Overall-sorted
    descending. A single sequential ``viridis`` ramp encodes the score (no
    provenance split); NaN cells are grey; each column's best cell is bold +
    boxed. Returns the PNG path (SVG sibling written too), or ``None`` when there
    is nothing to draw (no attributes, no methods matrix, or an all-NaN grid).
    """
    attributes: list[str] = result["metadata"]["attributes"]
    matrix = result.get("methods_matrix") or {}
    cells: dict[str, dict[str, float]] = matrix.get("cells") or {}
    if not attributes or not cells:
        return None

    ordered = sorted(matrix["strategies"], key=lambda s: _sort_key_desc(cells[s]["overall"], s))

    values = np.full((len(ordered), len(attributes) + 1), np.nan)
    for i, strategy in enumerate(ordered):
        cell = cells[strategy]
        for j, attr in enumerate(attributes):
            values[i, j] = cell[attr]
        values[i, -1] = cell["overall"]

    if np.all(np.isnan(values)):
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    finite = values[~np.isnan(values)]
    norm = mcolors.Normalize(vmin=float(finite.min()), vmax=float(finite.max()))
    cmap = plt.get_cmap("viridis")
    grey_rgba = mcolors.to_rgba(_GREY)

    rgba = np.zeros((values.shape[0], values.shape[1], 4))
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            v = values[i, j]
            rgba[i, j] = grey_rgba if np.isnan(v) else cmap(norm(v))

    n_cols = len(attributes) + 1
    fig, ax = plt.subplots(
        figsize=(max(8.0, n_cols * 0.8 + 3.0), max(3.0, len(ordered) * 0.5 + 2.5))
    )
    ax.imshow(rgba, aspect="auto")

    ax.set_xticks(range(n_cols))
    ax.set_xticklabels(attributes + ["overall"], rotation=40, ha="right", fontsize=8)
    ax.set_yticks(range(len(ordered)))
    ax.set_yticklabels(ordered, fontsize=8)
    _overall_divider(ax, len(attributes))
    _annotate_and_box(ax, values, rgba, _best_cells_per_column(values))

    # imshow got an RGBA array (no scalar mappable), so drive the colorbar from an
    # explicit ScalarMappable carrying the shared cmap + norm.
    scalar_mappable = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    scalar_mappable.set_array([])
    cbar = fig.colorbar(scalar_mappable, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("TV-similarity (mean over models)", fontsize=8)

    country = result["metadata"]["country"]
    ax.set_title(
        f"{country}: methods (strategy) fidelity by axis (TV-similarity)",
        fontsize=12, fontweight="bold",
    )
    fig.tight_layout()
    return save_figure(fig, Path(out_path), dpi=150)
