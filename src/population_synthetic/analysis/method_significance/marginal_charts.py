"""marginal_charts.py -- descriptive per-method marginal-progression charts.

For a fixed ``(country, model)`` this module emits one grouped-bar figure per
demographic attribute showing per-category proportions for the real statistical
baseline overlaid with each generation *method* (strategy), ordered simplest ->
most complex. It answers, per attribute, which method's marginal sits closest to
the real distribution and how the proportions shift across the method progression.

This is the **one** path in ``method_significance`` that reads mapped populations
rather than the pre-computed fidelity reports (the package's other paths remain
report-only). The departure is contained here and split along the architectural
seam:

* :func:`load_marginal_series` is the population-reading orchestration -- it opens
  the mapped real baseline and each combo, assembles the 6-series structure per
  ``(model, attribute)``, and knows nothing about matplotlib or figure styling.
* :func:`plot_marginal_progression` is a pure visualization sink -- it consumes the
  finished structure, draws grouped-bar figures, and returns the written paths;
  it knows nothing about how the proportions were computed or loaded.

The per-category proportion arithmetic itself lives in the shared, chart-agnostic
:func:`population_synthetic.analysis.utils.marginals.compute_proportions`; the
category axis and attribute list come from the country comparison scheme of the
same mapping tier the combos were scored against (config, never in-code literals).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from population_synthetic.analysis.fidelity.charts import _HIGH_CARDINALITY_FIELDS
from population_synthetic.analysis.fidelity.scheme import load_scheme
from population_synthetic.analysis.method_significance.charts import _COLOR_SERIES
from population_synthetic.analysis.utils.axes import (
    STRATEGY_COMPLEXITY_ORDER,
    decompose_slug,
    diagnose_slug,
)
from population_synthetic.analysis.utils.capped_source import resolve_mapped_dir
from population_synthetic.analysis.utils.figures import save_figure
from population_synthetic.analysis.utils.marginals import compute_proportions
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values

logger = logging.getLogger(__name__)

# Label of the real statistical baseline series (always the first entry, drawn
# distinct from the method-progression series).
REAL_SERIES_LABEL = "real"

# Colour of the baseline series -- deliberately outside ``_COLOR_SERIES`` so the
# real distribution reads as distinct from the method-progression ramp.
_BASELINE_COLOR = "#222222"

# Type alias for the assembled structure returned by load_marginal_series.
PreparedSeries = dict[str, dict[str, list[tuple[str, dict[str, float]]]]]


def _load_individuals(path: Path) -> list[dict]:
    """Read a mapped population file, returning its ``individuals`` list."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data.get("individuals", [])


def _axis_ids() -> tuple[list[str], list[str], list[str]]:
    """Config-sourced ``(country_ids, strategy_ids, model_ids)`` (sorted)."""
    country_ids = sorted(d["id"] for d in discover_axis_values("countries"))
    strategy_ids = sorted(d["id"] for d in discover_axis_values("strategies"))
    model_ids = sorted(d["id"] for d in discover_axis_values("models"))
    return country_ids, strategy_ids, model_ids


def load_marginal_series(
    country: str,
    output_base: str | Path,
    mapping_tier: str | Path | None,
    *,
    axis_ids: tuple[list[str], list[str], list[str]] | None = None,
) -> PreparedSeries:
    """Assemble the per-``(model, attribute)`` marginal-progression series for *country*.

    Reads the mapped populations under ``output_base`` (the same mapping-stage
    output :func:`load_combo_performances` walks, but opening populations instead
    of reports), computes per-category proportions on the config-driven category
    axis, and returns:

    ``prepared[model][attr] = [(label, proportions), ...]``

    where the **first** entry is always the real baseline
    (``label == REAL_SERIES_LABEL``) and the remaining entries are the generation
    methods present for that model, ordered by
    :data:`~population_synthetic.analysis.utils.axes.STRATEGY_COMPLEXITY_ORDER`
    (simplest -> most complex). ``proportions`` maps **every** category on the
    attribute's scheme axis to its proportion (an absent category is an explicit
    ``0.0`` bar). A method with no mapped population for a ``(country, model)`` is
    omitted from that model's series and logged -- never zero-filled.

    Args:
        country: the country id to build series for (combos of other countries in
            the index are ignored).
        output_base: the run's ``02_Data`` base; the mapping folder is resolved
            under it via the analysis registry.
        mapping_tier: the mapping directory whose category axis the combos were
            scored against (the same tier used to score fidelity). ``None`` defers
            to the country's default tier (``mappings_for_country``). Passing it
            explicitly keeps the chart axis aligned with the scored reports.
        axis_ids: optional ``(country_ids, strategy_ids, model_ids)`` override for
            slug decomposition (defaults to the config-sourced axis registries;
            injectable for tests).

    Returns:
        The ``prepared`` structure described above. Empty when the index contains
        no usable combo for *country* (the real baseline alone is not emitted --
        there is no ``(model, attribute)`` grid to attach it to).

    Raises:
        FileNotFoundError: if the mapping index or the required real baseline
            (``mapping/real_{country}.json``) is absent -- the baseline is a hard
            requirement, so its absence fails loud rather than dropping the series.
    """
    output_base = Path(output_base)
    scheme = load_scheme(country, mappings_path=Path(mapping_tier) if mapping_tier is not None else None)
    attributes = scheme.attributes
    categories = scheme.categories

    mapped_dir = resolve_mapped_dir(output_base)
    index_path = mapped_dir / "_index.json"
    if not index_path.is_file():
        raise FileNotFoundError(
            f"Mapped index not found: {index_path}. Run scripts/analyze/map_populations.py first."
        )

    real_path = mapped_dir / f"real_{country}.json"
    if not real_path.is_file():
        raise FileNotFoundError(
            f"Missing real baseline for {country!r}: {real_path}. "
            "Run scripts/analyze/map_populations.py first."
        )

    country_ids, strategy_ids, model_ids = axis_ids if axis_ids is not None else _axis_ids()

    with open(index_path, "r", encoding="utf-8") as fh:
        index_entries = json.load(fh)

    # Group the mapped combos for this country by model -> strategy -> individuals.
    combos_by_model: dict[str, dict[str, list[dict]]] = {}
    for entry in index_entries:
        slug = entry["slug"]
        if entry.get("skipped") is True or entry.get("synthetic_file") is None:
            continue
        decomposed = decompose_slug(slug, country_ids, strategy_ids, model_ids)
        if decomposed is None:
            logger.warning(
                "marginal_charts: %s", diagnose_slug(slug, country_ids, strategy_ids, model_ids)
            )
            continue
        combo_country, strategy, model = decomposed
        if combo_country != country:
            continue

        combo_path = mapped_dir / entry["synthetic_file"]
        if not combo_path.is_file():
            logger.warning(
                "marginal_charts: mapped population missing for combo %r (%s); "
                "skipping that method series.",
                slug, combo_path,
            )
            continue
        combos_by_model.setdefault(model, {})[strategy] = _load_individuals(combo_path)

    if not combos_by_model:
        logger.warning(
            "marginal_charts: no mapped combos found for country %r under %s; "
            "no marginal-progression series produced.",
            country, mapped_dir,
        )
        return {}

    # Real baseline proportions, computed once on the shared category axis.
    real_individuals = _load_individuals(real_path)
    real_props: dict[str, dict[str, float]] = {
        attr: compute_proportions(real_individuals, attr, categories[attr])[0]
        for attr in attributes
    }

    prepared: PreparedSeries = {}
    for model in sorted(combos_by_model):
        by_strategy = combos_by_model[model]
        present = [s for s in STRATEGY_COMPLEXITY_ORDER if s in by_strategy]
        missing = [s for s in STRATEGY_COMPLEXITY_ORDER if s not in by_strategy]
        if missing:
            logger.info(
                "marginal_charts: model %r (country %r) has no mapped population for "
                "method(s) %s; those series are omitted (not zero-filled).",
                model, country, missing,
            )

        # Per-method proportions, computed once per (model, strategy, attr).
        method_props: dict[str, dict[str, dict[str, float]]] = {
            strategy: {
                attr: compute_proportions(by_strategy[strategy], attr, categories[attr])[0]
                for attr in attributes
            }
            for strategy in present
        }

        prepared[model] = {
            attr: [(REAL_SERIES_LABEL, real_props[attr])]
            + [(strategy, method_props[strategy][attr]) for strategy in present]
            for attr in attributes
        }

    return prepared


def _series_color(index: int) -> str:
    """Colour for the *index*-th series: baseline distinct, methods ramp _COLOR_SERIES."""
    if index == 0:
        return _BASELINE_COLOR
    return _COLOR_SERIES[(index - 1) % len(_COLOR_SERIES)]


def plot_marginal_progression(
    prepared: PreparedSeries,
    country: str,
    out_dir: str | Path,
) -> list[Path]:
    """Draw one grouped-bar marginal-progression figure per ``(model, attribute)``.

    Pure visualization sink over the structure from :func:`load_marginal_series`:
    each figure overlays the real baseline (drawn distinct) with the method series
    (colour-ramped from
    :data:`~population_synthetic.analysis.method_significance.charts._COLOR_SERIES`)
    as offset bar groups at every category on the scheme axis. Proportions use a
    fixed ``[0, 1]`` scale; high-cardinality attributes
    (:data:`~population_synthetic.analysis.fidelity.charts._HIGH_CARDINALITY_FIELDS`)
    fall back to horizontal bars. An attribute whose every series is all-zero
    (genuinely no data anywhere) is skipped -- no empty axes is written.

    Figures are written under
    ``out_dir/{country}_marginal_progression/{model}/{attr}.png`` (with an SVG
    sibling via :func:`~population_synthetic.analysis.utils.figures.save_figure`).

    Args:
        prepared: the ``prepared[model][attr] = [(label, proportions), ...]``
            structure; the first entry per attribute is the baseline.
        country: the country id (used for the output subfolder and titles).
        out_dir: the method-significance output directory; the
            ``{country}_marginal_progression`` tree is created beneath it.

    Returns:
        The list of written PNG paths (SVG siblings are written alongside but not
        listed), in ``(model, attribute)`` iteration order.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    root = Path(out_dir) / f"{country}_marginal_progression"
    written: list[Path] = []

    for model, by_attr in prepared.items():
        for attr, series in by_attr.items():
            if not series:
                continue
            # Shared category axis: every series was built on categories[attr], so
            # the first series' keys are the ordered axis.
            cats = list(series[0][1].keys())
            if not cats:
                continue
            # Skip a genuinely empty attribute (no data in any series).
            if all(props.get(cat, 0.0) == 0.0 for _, props in series for cat in cats):
                continue

            n_series = len(series)
            n_cats = len(cats)
            horizontal = attr in _HIGH_CARDINALITY_FIELDS

            # Group of ``n_series`` bars per category, centred on each tick.
            group_width = 0.8
            bar_size = group_width / n_series
            offsets = [(i - (n_series - 1) / 2.0) * bar_size for i in range(n_series)]

            if horizontal:
                fig_height = max(4.0, min(n_cats * (0.35 * n_series + 0.4) + 2.0, 22.0))
                fig, ax = plt.subplots(figsize=(11.0, fig_height))
                y_pos = np.arange(n_cats)
                for i, (label, props) in enumerate(series):
                    vals = [props.get(cat, 0.0) for cat in cats]
                    ax.barh(
                        y_pos - offsets[i], vals, height=bar_size,
                        color=_series_color(i), label=label,
                        edgecolor="white", linewidth=0.3,
                    )
                ax.set_yticks(y_pos)
                ax.set_yticklabels(cats, fontsize=7)
                ax.set_xlabel("Proportion", fontsize=8)
                ax.set_xlim(0.0, 1.0)
                ax.invert_yaxis()
            else:
                fig_width = max(8.0, n_cats * max(0.9, n_series * 0.22) + 2.0)
                fig, ax = plt.subplots(figsize=(fig_width, 5.0))
                x_pos = np.arange(n_cats)
                for i, (label, props) in enumerate(series):
                    vals = [props.get(cat, 0.0) for cat in cats]
                    ax.bar(
                        x_pos + offsets[i], vals, width=bar_size,
                        color=_series_color(i), label=label,
                        edgecolor="white", linewidth=0.3,
                    )
                ax.set_xticks(x_pos)
                ax.set_xticklabels(cats, rotation=30, ha="right", fontsize=7)
                ax.set_ylabel("Proportion", fontsize=8)
                ax.set_ylim(0.0, 1.0)

            ax.set_title(
                f"{country} / {model}: {attr}\nreal baseline vs method progression",
                fontsize=10, fontweight="bold",
            )
            ax.legend(fontsize=7, title="series (simplest -> most complex)", title_fontsize=7)
            ax.tick_params(axis="both", labelsize=7)
            fig.tight_layout()

            out_path = root / model / f"{attr}.png"
            written.append(save_figure(fig, out_path, dpi=150))

    return written
