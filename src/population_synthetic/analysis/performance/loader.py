"""loader.py -- DTO and filesystem I/O for the cross-model performance comparison.

Owns the data contract of the performance process: the per-combo
:class:`ComboPerformance` DTO, the pure reshaping of one comparison report into
that DTO (:func:`extract_combo_performance`, testable without a filesystem), and
the discovery walk that welds the mapped index to the per-slug comparison
reports (:func:`load_combo_performances`).

Discovery follows the canonical downstream route: read
``{output_base}/03_Analysis/mapped/_index.json``, decompose each non-skipped
slug into ``(country, strategy, model)`` via the shared axis registries, and
open ``{output_base}/03_Analysis/comparison/{slug}/{slug}.json``.

Failure policy (fail-fast where it matters):

* a missing mapped index or a **malformed** report (missing ``metadata`` /
  ``marginals`` / ``coherence`` / per-attribute ``tv_distance``, or a marginals
  axis that drifted from the country's comparison scheme) always raises;
* a **missing** report file is a pipeline-progress state, not corruption: the
  combo is skipped with a reason (or raises with ``strict=True``);
* a ``NaN`` ``tv_distance`` is tolerated (the evaluator emits it for degenerate
  cells): the attribute is omitted from ``tv_similarity`` and thereby from the
  stats samples and the overall mean.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from population_synthetic.analysis.comparison.scheme import load_scheme
from population_synthetic.analysis.utils.axes import decompose_slug, diagnose_slug
from population_synthetic.analysis.utils.country_config import mappings_for_country
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values

# Per-attribute metrics carried through from the comparison report into the
# performance output (reference only -- TV-similarity drives ranking/charts).
_CARRIED_METRICS = ("tv_distance", "kl_divergence", "chi_sq_p", "max_diff")


@dataclass(frozen=True)
class ComboPerformance:
    """One model × strategy × country combo's fidelity scores vs the real baseline."""

    slug: str
    country: str
    strategy: str
    model: str
    n_synthetic: int                     # metadata.population_b.n of the report
    marginals: dict[str, dict[str, Any]]  # attr -> full per-attribute metric dict
    tv_similarity: dict[str, float]       # attr -> 1 - tv_distance (NaN attrs omitted)
    coherence: dict[str, Any]             # the report's coherence block
    # Optional multivariate summaries (reference only -- never the ranking key).
    # ``None`` when the report predates the multivariate block; may be ``NaN``
    # when the block is present but degenerate (tiny/failed synthetic n).
    c2st_auc: float | None = None         # multivariate.c2st.auc
    mean_delta_v: float | None = None     # multivariate.association.mean_abs_delta_v


def _optional_float(value: Any) -> float | None:
    """Coerce an optional report value to ``float`` (keeping ``NaN``), else ``None``."""
    if value is None:
        return None
    return float(value)


def scheme_attributes(country: str) -> list[str]:
    """The config-sourced comparison axis for *country* (ordered, fail-fast)."""
    return load_scheme(country, mappings_path=mappings_for_country(country)).attributes


def extract_combo_performance(
    slug: str,
    country: str,
    strategy: str,
    model: str,
    report: dict[str, Any],
    attributes: list[str],
) -> ComboPerformance:
    """Reshape one comparison report into a :class:`ComboPerformance` (pure, I/O-free).

    *attributes* is the country's config-sourced comparison axis; a report whose
    ``marginals`` keys drifted from it (in either direction) is stale relative to
    the current scheme and raises rather than being silently reconciled.
    """
    for key in ("metadata", "marginals", "coherence"):
        if key not in report:
            raise KeyError(f"Comparison report for {slug!r} is missing required key {key!r}")

    marginals: dict[str, dict[str, Any]] = report["marginals"]
    missing = [a for a in attributes if a not in marginals]
    extra = [a for a in marginals if a not in attributes]
    if missing or extra:
        raise KeyError(
            f"Comparison report for {slug!r} does not match the {country!r} comparison scheme "
            f"(missing attributes: {missing}, unknown attributes: {extra}). "
            "The report is stale -- re-run scripts/analyze/compare_all_pipelines.py."
        )

    tv_similarity: dict[str, float] = {}
    for attr in attributes:
        metric = marginals[attr]
        if "tv_distance" not in metric:
            raise KeyError(
                f"Comparison report for {slug!r} is missing 'tv_distance' for attribute {attr!r}"
            )
        tv = float(metric["tv_distance"])
        if tv == tv:  # NaN attributes are omitted (excluded from stats and the overall mean)
            tv_similarity[attr] = 1.0 - tv

    population_b = report["metadata"].get("population_b") or {}
    if "n" not in population_b:
        raise KeyError(
            f"Comparison report for {slug!r} is missing 'metadata.population_b.n'"
        )

    # Multivariate block is additive and optional: old reports lack it entirely
    # (fields stay None), new reports supply c2st.auc / association.mean_abs_delta_v
    # (which may themselves be NaN for degenerate synthetic populations).
    multivariate = report.get("multivariate") or {}
    c2st_block = multivariate.get("c2st") or {}
    association_block = multivariate.get("association") or {}

    return ComboPerformance(
        slug=slug,
        country=country,
        strategy=strategy,
        model=model,
        n_synthetic=int(population_b["n"]),
        marginals=marginals,
        tv_similarity=tv_similarity,
        coherence=report["coherence"],
        c2st_auc=_optional_float(c2st_block.get("auc")),
        mean_delta_v=_optional_float(association_block.get("mean_abs_delta_v")),
    )


def load_combo_performances(
    output_base: str | Path,
    *,
    countries: list[str] | None = None,
    models: list[str] | None = None,
    strategies: list[str] | None = None,
    slugs: list[str] | None = None,
    strict: bool = False,
    attributes_for_country: Callable[[str], list[str]] | None = None,
    axis_ids: tuple[list[str], list[str], list[str]] | None = None,
) -> tuple[list[ComboPerformance], list[tuple[str, str]]]:
    """Load every selected combo's comparison report under *output_base*.

    Returns ``(records, skipped)`` where *skipped* lists ``(slug, reason)`` for
    combos that could not be used (skipped during mapping, undecomposable slug,
    or missing report). Filter arguments (*countries* / *models* / *strategies* /
    *slugs*) silently narrow the selection -- filtered-out combos are neither
    records nor skips.

    *attributes_for_country* and *axis_ids* (``(country_ids, strategy_ids,
    model_ids)``) default to the config-sourced scheme and axis registries; they
    are injectable for tests.
    """
    output_base = Path(output_base)
    mapped_dir = output_base / "03_Analysis" / "mapped"
    comparison_dir = output_base / "03_Analysis" / "comparison"

    index_path = mapped_dir / "_index.json"
    if not index_path.is_file():
        raise FileNotFoundError(
            f"Mapped index not found: {index_path}. Run scripts/analyze/map_populations.py "
            "and scripts/analyze/compare_all_pipelines.py first."
        )

    if axis_ids is None:
        country_ids = sorted(d["id"] for d in discover_axis_values("countries"))
        strategy_ids = sorted(d["id"] for d in discover_axis_values("strategies"))
        model_ids = sorted(d["id"] for d in discover_axis_values("models"))
    else:
        country_ids, strategy_ids, model_ids = axis_ids

    attrs_fn = attributes_for_country if attributes_for_country is not None else scheme_attributes
    attrs_cache: dict[str, list[str]] = {}

    with open(index_path, "r", encoding="utf-8") as fh:
        index_entries = json.load(fh)

    records: list[ComboPerformance] = []
    skipped: list[tuple[str, str]] = []

    for entry in index_entries:
        slug = entry["slug"]
        if slugs and slug not in slugs:
            continue

        if entry.get("skipped") is True or entry.get("synthetic_file") is None:
            skipped.append((slug, "skipped during mapping (no mapped synthetic file)"))
            continue

        decomposed = decompose_slug(slug, country_ids, strategy_ids, model_ids)
        if decomposed is None:
            skipped.append((slug, diagnose_slug(slug, country_ids, strategy_ids, model_ids)))
            continue
        country, strategy, model = decomposed

        if countries and country not in countries:
            continue
        if models and model not in models:
            continue
        if strategies and strategy not in strategies:
            continue

        report_path = comparison_dir / slug / f"{slug}.json"
        if not report_path.is_file():
            if strict:
                raise RuntimeError(
                    f"Missing comparison report for {slug!r}: {report_path}. "
                    "Run scripts/analyze/compare_all_pipelines.py first (or drop --strict)."
                )
            skipped.append((slug, f"no comparison report: {report_path}"))
            continue

        if country not in attrs_cache:
            attrs_cache[country] = attrs_fn(country)

        with open(report_path, "r", encoding="utf-8") as fh:
            report = json.load(fh)

        records.append(
            extract_combo_performance(slug, country, strategy, model, report, attrs_cache[country])
        )

    return records, skipped
