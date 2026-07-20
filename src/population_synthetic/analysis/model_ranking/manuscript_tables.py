"""manuscript_tables.py -- Manuscript-grade fidelity heatmap-tables.

Two print-oriented renderers, both **pure consumers** of the built
performance ``result`` dict (from
:func:`population_synthetic.analysis.model_ranking.builder.build_performance_comparison`):

* :func:`plot_model_fidelity_table` -- rows = models at the single *global-best*
  strategy, columns = the country's demographic axes + an "overall" column,
  cell = TV-similarity. Rows are Overall-sorted; each column's best cell is
  bold + boxed. The score is coloured with a single sequential **inferno** ramp
  (matching the RF-mapping convention); hosted-vs-local provenance is encoded as
  a **side-marker** -- the model row label is coloured (hosted = blue, local =
  orange) with a small legend -- not by cell hue.
* :func:`plot_method_fidelity_table` -- rows = strategies, cell = mean over
  models of that strategy's per-axis TV-similarity, single sequential
  **inferno** ramp. Same Overall-sort and best-per-column bold + box.

Two LaTeX emitters mirror the figures for direct paste into the manuscript:

* :func:`write_model_fidelity_latex` / :func:`write_method_fidelity_latex` --
  emit a self-contained ``booktabs`` ``tabular`` snippet, categories as the
  header row, each numeric cell backed by the inferno ``\\cellcolor`` at the
  same normalisation as the figure, best-per-column ``\\textbf``, NaN cells grey.

This module knows nothing about *how* hosting was derived or *how* the
methods matrix was aggregated -- it reads ``metadata.model_hosting`` and
``methods_matrix`` straight from *result* -- and it does no file discovery.
The hosting class of a model absent from ``metadata.model_hosting`` (e.g. the
builder default of ``{}`` when hosting was not wired) is treated as ``hosted``
for *presentation only*; this is a presentation default, not a data default --
no computed value is affected.

Follows the project charting conventions (deferred ``Agg`` matplotlib import,
NaN -> grey, ``dpi=150``, white Overall divider, category labels on top) and
persists via the shared
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
_CMAP_NAME = "inferno"

# Colourblind-safe categorical hues for the provenance side-marker (figure) and
# the LaTeX ``Host`` column swatch. These encode *category* (hosting class), not
# score, and are deliberately distinct from the inferno score ramp.
_HOST_COLORS = {"hosted": "#4878CF", "local": "#E8935A"}
_HOST_LABELS = {"hosted": "hosted (API)", "local": "local (Ollama)"}


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


def _annotate_and_box(ax, values: np.ndarray, cmap, norm, best_cells: set[tuple[int, int]]) -> None:
    """Write ``f"{v*100:.1f}"`` per finite cell; bold + draw a border on the best-per-column cells.

    The displayed number is the TV-similarity rescaled to a 0--100 percentage
    (one decimal), while colour (``cmap(norm(v))``) and the best-per-column argmax
    stay on the underlying 0--1 value -- only the annotation text is rescaled.
    Text colour is chosen from the actual inferno cell colour by relative
    luminance, so annotations stay legible on both the near-black low end and the
    bright-yellow high end of the ramp.
    """
    from matplotlib.patches import Rectangle

    n_rows, n_cols = values.shape
    for i in range(n_rows):
        for j in range(n_cols):
            v = values[i, j]
            if np.isnan(v):
                continue
            is_best = (i, j) in best_cells
            ax.text(
                j, i, f"{v * 100:.1f}",
                ha="center", va="center", fontsize=_ANNOT_FONTSIZE,
                color=_text_color_for_rgb(cmap(norm(v))),
                fontweight="bold" if is_best else "normal",
            )
            if is_best:
                ax.add_patch(
                    Rectangle(
                        (j - 0.5, i - 0.5), 1, 1,
                        fill=False, edgecolor=_BOX_EDGE, linewidth=2.0, zorder=5,
                    )
                )


def _categories_on_top(ax, attributes: list[str]) -> None:
    """Place the column (category) tick labels above the table, rotated for readability."""
    n_cols = len(attributes) + 1
    ax.xaxis.set_ticks_position("top")
    ax.xaxis.set_label_position("top")
    ax.set_xticks(range(n_cols))
    ax.set_xticklabels(attributes + ["overall"], rotation=40, ha="left", fontsize=8)


def _inferno_cmap():
    """The shared inferno colormap with a grey ``set_bad`` for NaN cells."""
    import matplotlib.pyplot as plt

    cmap = plt.get_cmap(_CMAP_NAME).copy()
    cmap.set_bad(_GREY)
    return cmap


def _add_percentage_colorbar(fig, im, ax, label: str):
    """Attach a colorbar whose tick labels read 0--100 while the mappable stays on 0--1.

    The underlying ``Normalize`` is unchanged (still 0--1); only the tick *labels*
    are scaled to a percentage via a ``FuncFormatter``, and the label carries the
    ``(%)`` unit.
    """
    from matplotlib.ticker import FuncFormatter

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _pos: f"{v * 100:.0f}"))
    cbar.set_label(label, fontsize=8)
    return cbar


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


def _model_grid(result: dict[str, Any]) -> tuple[str, list[str], np.ndarray] | None:
    """Shared models-table preparation for the figure and the LaTeX emitter.

    Returns ``(best_strategy, row_models, values)`` where *values* is the
    (models x attributes+overall) TV-similarity grid, Overall-sorted, at the
    single global-best strategy; or ``None`` when there is nothing to render
    (no attributes, no methods matrix, no strategy, no surviving rows, all-NaN).
    Models with no combo at the chosen strategy are dropped and printed.
    """
    attributes: list[str] = result["metadata"]["attributes"]
    matrix = result.get("methods_matrix") or {}
    if not attributes or not matrix.get("cells"):
        return None

    best_strategy = _global_best_strategy(matrix)
    if best_strategy is None:
        return None

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
    return best_strategy, row_models, values


def _method_grid(result: dict[str, Any]) -> tuple[list[str], np.ndarray] | None:
    """Shared methods-table preparation for the figure and the LaTeX emitter.

    Returns ``(row_strategies, values)`` Overall-sorted, or ``None`` on empty /
    all-NaN input.
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
    return ordered, values


def _shared_norm(values: np.ndarray):
    """A single ``Normalize`` over all finite cells of *values*."""
    import matplotlib.colors as mcolors

    finite = values[~np.isnan(values)]
    return mcolors.Normalize(vmin=float(finite.min()), vmax=float(finite.max()))


# ------------------------------------------------------------------
# Models table (rows = models at the global-best strategy)
# ------------------------------------------------------------------

def plot_model_fidelity_table(result: dict[str, Any], out_path: str | Path) -> Path | None:
    """Models x (axes + Overall) TV-similarity table at the single global-best strategy.

    Picks the global-best strategy (argmax over strategies of the methods-matrix
    Overall column, ties -> simpler), keeps one row per model *at that strategy*,
    and Overall-sorts the rows descending. Models with no combo at the chosen
    strategy are omitted and printed (no silent truncation). The score is
    coloured with a single sequential ``inferno`` ramp at a shared normalisation;
    NaN cells are grey; each column's best cell is bold + boxed. Hosted-vs-local
    provenance is encoded as a **row-label colour** side-marker (hosted -> blue,
    local -> orange) plus a legend, *not* by cell hue. Category labels sit above
    the table. Returns the PNG path (SVG sibling written too), or ``None`` when
    there is nothing to draw.
    """
    grid = _model_grid(result)
    if grid is None:
        return None
    best_strategy, row_models, values = grid
    attributes: list[str] = result["metadata"]["attributes"]
    hosting: dict[str, str] = result["metadata"].get("model_hosting", {})

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    norm = _shared_norm(values)
    cmap = _inferno_cmap()

    n_cols = len(attributes) + 1
    fig, ax = plt.subplots(
        figsize=(max(8.0, n_cols * 0.8 + 3.0), max(4.0, len(row_models) * 0.5 + 2.5))
    )
    im = ax.imshow(np.ma.masked_invalid(values), cmap=cmap, norm=norm, aspect="auto")

    _categories_on_top(ax, attributes)
    ax.set_yticks(range(len(row_models)))
    ax.set_yticklabels(row_models, fontsize=8)
    # Provenance side-marker: colour each model's row label by hosting class
    # (models absent from the map default to "hosted").
    for label, model in zip(ax.get_yticklabels(), row_models):
        label.set_color(_HOST_COLORS[hosting.get(model, "hosted")])

    _overall_divider(ax, len(attributes))
    _annotate_and_box(ax, values, cmap, norm, _best_cells_per_column(values))

    _add_percentage_colorbar(fig, im, ax, "TV-similarity (%)")

    classes_present = {hosting.get(m, "hosted") for m in row_models}
    handles = [
        Patch(facecolor=_HOST_COLORS[c], edgecolor="none", label=_HOST_LABELS[c])
        for c in ("hosted", "local") if c in classes_present
    ]
    if handles:
        ax.legend(
            handles=handles, loc="upper left", bbox_to_anchor=(0.0, -0.02),
            ncol=2, fontsize=7.5, title="provenance", title_fontsize=8, frameon=False,
        )

    country = result["metadata"]["country"]
    ax.set_title(
        f"{country}: model fidelity by axis at strategy '{best_strategy}' (TV-similarity %)",
        fontsize=12, fontweight="bold", pad=28,
    )
    fig.tight_layout()
    return save_figure(fig, Path(out_path), dpi=150)


# ------------------------------------------------------------------
# Methods table (rows = strategies)
# ------------------------------------------------------------------

def plot_method_fidelity_table(result: dict[str, Any], out_path: str | Path) -> Path | None:
    """Strategies x (axes + Overall) mean-over-models TV-similarity table.

    Rows are the strategies from ``methods_matrix.cells``, Overall-sorted
    descending. A single sequential ``inferno`` ramp encodes the score; NaN cells
    are grey; each column's best cell is bold + boxed; category labels sit above
    the table. Returns the PNG path (SVG sibling written too), or ``None`` when
    there is nothing to draw (no attributes, no methods matrix, or an all-NaN grid).
    """
    grid = _method_grid(result)
    if grid is None:
        return None
    ordered, values = grid
    attributes: list[str] = result["metadata"]["attributes"]

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    norm = _shared_norm(values)
    cmap = _inferno_cmap()

    n_cols = len(attributes) + 1
    fig, ax = plt.subplots(
        figsize=(max(8.0, n_cols * 0.8 + 3.0), max(3.0, len(ordered) * 0.5 + 2.5))
    )
    im = ax.imshow(np.ma.masked_invalid(values), cmap=cmap, norm=norm, aspect="auto")

    _categories_on_top(ax, attributes)
    ax.set_yticks(range(len(ordered)))
    ax.set_yticklabels(ordered, fontsize=8)
    _overall_divider(ax, len(attributes))
    _annotate_and_box(ax, values, cmap, norm, _best_cells_per_column(values))

    _add_percentage_colorbar(fig, im, ax, "TV-similarity (%, mean over models)")

    country = result["metadata"]["country"]
    ax.set_title(
        f"{country}: methods (strategy) fidelity by axis (TV-similarity %)",
        fontsize=12, fontweight="bold", pad=28,
    )
    fig.tight_layout()
    return save_figure(fig, Path(out_path), dpi=150)


# ------------------------------------------------------------------
# LaTeX emitters (mirror the two figures)
# ------------------------------------------------------------------

_LATEX_HEADER_COMMENT = (
    "% Auto-generated manuscript fidelity table -- self-contained tabular snippet.\n"
    "% Required packages in the document preamble:\n"
    "%   \\usepackage{booktabs}          % for the top / mid / bottom rules\n"
    "%   \\usepackage[table]{xcolor}     % for cell colouring (pulls in colortbl) and text colour\n"
    "% Cells are coloured on the matplotlib 'inferno' ramp; dark cells use white text.\n"
    "% Numeric cell values are TV-similarity as a percentage (0--100, one decimal).\n"
)


def _latex_escape(text: str) -> str:
    """Escape the LaTeX specials that appear in model / attribute names."""
    out = str(text)
    for ch, rep in (("_", r"\_"), ("&", r"\&"), ("%", r"\%"), ("#", r"\#")):
        out = out.replace(ch, rep)
    return out


def _latex_number(v: float, cmap, norm, is_best: bool) -> str:
    """The formatted, coloured LaTeX cell string for a (possibly NaN) value."""
    import matplotlib.colors as mcolors

    if np.isnan(v):
        return "\\cellcolor[HTML]{DDDDDD} --"
    rgba = cmap(norm(v))
    hex6 = mcolors.to_hex(rgba).lstrip("#").upper()
    # Displayed value is the 0--100 percentage (one decimal); the cell colour is
    # still computed from the underlying 0--1 ``norm(v)`` above.
    num = f"{v * 100:.1f}"
    if is_best:
        num = f"\\textbf{{{num}}}"
    if _text_color_for_rgb(rgba) == "white":
        num = f"\\textcolor{{white}}{{{num}}}"
    return f"\\cellcolor[HTML]{{{hex6}}} {num}"


def _write_latex_table(
    out_path: Path,
    caption: str,
    lead_headers: list[str],
    attributes: list[str],
    body_rows: list[str],
) -> Path:
    """Assemble and write the booktabs tabular. *body_rows* are pre-formatted (no trailing ``\\\\``)."""
    n_lead = len(lead_headers)
    # Column spec: left-aligned lead columns, centred attribute columns, a rule
    # before the Overall column mirroring the figure's white divider.
    col_spec = "l" * n_lead + "c" * len(attributes) + "|c"
    header_cells = [_latex_escape(h) for h in lead_headers] + \
        [_latex_escape(a) for a in attributes] + ["Overall"]

    lines = [_LATEX_HEADER_COMMENT, f"% {caption}", "\\begin{tabular}{" + col_spec + "}",
             "\\toprule", "  " + " & ".join(header_cells) + " \\\\", "\\midrule"]
    for row in body_rows:
        lines.append("  " + row + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}", ""]

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def write_model_fidelity_latex(result: dict[str, Any], out_path: str | Path) -> Path | None:
    """Emit the models-table figure as a manuscript-ready LaTeX ``tabular`` snippet.

    Mirrors :func:`plot_model_fidelity_table`: rows = models at the global-best
    strategy, Overall-sorted; header row = the category names (attributes +
    "Overall"); each numeric cell backed by the inferno ``\\cellcolor`` at the
    same normalisation as the figure, best-per-column ``\\textbf``, NaN grey/``--``.
    Provenance is a leading ``Host`` column carrying ``hosted``/``local`` text
    (a compilable, colour-independent indicator; the figure's colour side-marker
    does not survive a plain-text LaTeX cell). Names are underscore-escaped.
    Returns the written ``.tex`` ``Path``, or ``None`` on empty / all-NaN input.
    """
    grid = _model_grid(result)
    if grid is None:
        return None
    best_strategy, row_models, values = grid
    attributes: list[str] = result["metadata"]["attributes"]
    hosting: dict[str, str] = result["metadata"].get("model_hosting", {})
    country = result["metadata"]["country"]

    norm = _shared_norm(values)
    cmap = _inferno_cmap()
    best_cells = _best_cells_per_column(values)

    body_rows: list[str] = []
    for i, model in enumerate(row_models):
        host = hosting.get(model, "hosted")
        cells = [_latex_escape(model), _latex_escape(host)]
        for j in range(values.shape[1]):
            cells.append(_latex_number(values[i, j], cmap, norm, (i, j) in best_cells))
        body_rows.append(" & ".join(cells))

    caption = (
        f"{country}: model fidelity by axis at strategy '{best_strategy}' (TV-similarity, %). "
        "Best per column in bold; Host = hosted (API) / local (Ollama)."
    )
    return _write_latex_table(Path(out_path), caption, ["Model", "Host"], attributes, body_rows)


def write_method_fidelity_latex(result: dict[str, Any], out_path: str | Path) -> Path | None:
    """Emit the methods-table figure as a manuscript-ready LaTeX ``tabular`` snippet.

    Mirrors :func:`plot_method_fidelity_table`: rows = strategies, Overall-sorted;
    header row = the category names (attributes + "Overall"); each numeric cell
    backed by the inferno ``\\cellcolor`` at the figure's normalisation,
    best-per-column ``\\textbf``, NaN grey/``--``; a leading ``Strategy`` column.
    Returns the written ``.tex`` ``Path``, or ``None`` on empty / all-NaN input.
    """
    grid = _method_grid(result)
    if grid is None:
        return None
    ordered, values = grid
    attributes: list[str] = result["metadata"]["attributes"]
    country = result["metadata"]["country"]

    norm = _shared_norm(values)
    cmap = _inferno_cmap()
    best_cells = _best_cells_per_column(values)

    body_rows: list[str] = []
    for i, strategy in enumerate(ordered):
        cells = [_latex_escape(strategy)]
        for j in range(values.shape[1]):
            cells.append(_latex_number(values[i, j], cmap, norm, (i, j) in best_cells))
        body_rows.append(" & ".join(cells))

    caption = (
        f"{country}: methods (strategy) fidelity by axis (TV-similarity, %, mean over models). "
        "Best per column in bold."
    )
    return _write_latex_table(Path(out_path), caption, ["Strategy"], attributes, body_rows)
