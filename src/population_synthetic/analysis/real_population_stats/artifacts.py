"""artifacts.py -- orchestrate one country's real-population reference artifacts.

Iterates the scheme's analyzed axis (``scheme.attributes``), computes per-attribute
stats (``stats.py``), renders + saves the PNG+SVG bar figure (``charts.py`` +
``analysis/utils/figures.py::save_figure``), writes the proportion CSV
(``csv_writer.py``), and finally builds + saves the combined overview panel.

This module owns the output paths and the per-attribute skip decision (all-null ->
logged, not emitted); it must NOT know how the population/scheme were loaded, and
knows nothing about the GUI or its dispatch modes -- those live in the calling
script and, later, the GUI engine.
"""

from __future__ import annotations

import logging
from pathlib import Path

from population_synthetic.analysis.fidelity.scheme import ComparisonScheme
from population_synthetic.analysis.real_population_stats.charts import (
    plot_category_bars,
    plot_overview_panel,
)
from population_synthetic.analysis.real_population_stats.csv_writer import write_proportions_csv
from population_synthetic.analysis.real_population_stats.stats import compute_category_stats
from population_synthetic.analysis.utils.figures import save_figure

logger = logging.getLogger(__name__)


def write_real_population_stats(
    real_pop: dict,
    scheme: ComparisonScheme,
    out_dir: Path,
    *,
    dpi: int,
    force: bool,
    charts: bool = True,
) -> list[Path]:
    """Compute + render + write every analyzed attribute's reference artifacts.

    For each ``attr`` in ``scheme.attributes``: computes :class:`CategoryStat` rows
    via ``compute_category_stats(real_pop["individuals"], attr, scheme.categories[attr])``;
    an all-null attribute (every row's ``total == 0``) is skipped with a logged
    ``WARNING`` -- no all-zero figure/CSV is emitted for it. Otherwise writes
    ``{attr}.png``/``{attr}.svg`` (via ``plot_category_bars`` + ``save_figure``,
    unless *charts* is ``False``) and ``{attr}.csv`` (via ``write_proportions_csv``)
    under *out_dir*, skipping any of the three that already exist unless *force*.
    After the loop, builds and saves ``overview.png``/``overview.svg`` over every
    non-skipped attribute (also honoring *force*; skipped entirely if *charts* is
    ``False`` or every attribute turned out all-null).

    Args:
        real_pop: the mapped real population, ``{"metadata": ..., "individuals": [...]}``.
        scheme: the country's :class:`ComparisonScheme` (analyzed axis + categories).
        out_dir: the country's output directory (created if needed).
        dpi: PNG render resolution, forwarded to ``save_figure``.
        force: when ``False``, an attribute (or the overview) whose output files
            already exist on disk is left untouched; when ``True``, always
            recompute and overwrite.
        charts: when ``False``, skip all figure rendering (PNG/SVG, including the
            overview) and only write the per-attribute CSVs.

    Returns:
        Every path written or left-in-place (existing-and-skipped paths are
        included so the caller can report the full artifact set either way), in
        attribute order followed by the overview.

    Raises:
        KeyError: if ``real_pop`` lacks ``"individuals"`` or ``scheme.categories``
            lacks an entry for one of ``scheme.attributes`` (malformed input --
            fails loudly rather than silently skipping).
    """
    individuals: list[dict] = real_pop["individuals"]
    out_dir = Path(out_dir)

    written: list[Path] = []
    stats_by_attr: dict[str, list] = {}

    for attr in scheme.attributes:
        categories = scheme.categories[attr]
        # extra_categories (data values outside the config axis) are already logged at
        # WARNING inside compute_category_stats -> compute_proportions; nothing further
        # to do with them here.
        rows, _extra_categories = compute_category_stats(individuals, attr, categories)

        total = rows[0].total if rows else 0
        if total == 0:
            logger.warning(
                "write_real_population_stats: attribute %r is all-null (N=0) in this "
                "population; skipping its figure/CSV.",
                attr,
            )
            continue

        stats_by_attr[attr] = rows

        csv_path = out_dir / f"{attr}.csv"
        png_path = out_dir / f"{attr}.png"
        svg_path = png_path.with_suffix(".svg")

        expected = [csv_path, *([png_path, svg_path] if charts else [])]
        if not force and all(p.exists() for p in expected):
            logger.info(
                "write_real_population_stats: %s outputs already exist under %s; skipping "
                "(force=False).",
                attr,
                out_dir,
            )
            written.extend(expected)
            continue

        written.append(write_proportions_csv(rows, csv_path))

        if charts:
            fig = plot_category_bars(rows, attr)
            saved_png = save_figure(fig, png_path, dpi=dpi)
            written.append(saved_png)
            written.append(saved_png.with_suffix(".svg"))

    if not charts:
        return written

    if not stats_by_attr:
        logger.warning(
            "write_real_population_stats: every analyzed attribute was all-null; skipping "
            "the overview panel."
        )
        return written

    overview_png = out_dir / "overview.png"
    overview_svg = overview_png.with_suffix(".svg")
    if not force and overview_png.exists() and overview_svg.exists():
        logger.info(
            "write_real_population_stats: overview already exists under %s; skipping "
            "(force=False).",
            out_dir,
        )
        written.append(overview_png)
        written.append(overview_svg)
        return written

    fig = plot_overview_panel(stats_by_attr)
    saved_overview = save_figure(fig, overview_png, dpi=dpi)
    written.append(saved_overview)
    written.append(saved_overview.with_suffix(".svg"))

    return written
