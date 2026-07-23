"""generation_metadata -- per country x model x method(strategy) generation-cost report.

Pipe-and-filter analysis stage: reads 01_Raw LLM-call telemetry, reduces each
persona to a per-persona metric record, aggregates per-combo mean/std/n, applies a
config-driven cost model, and emits a per-country CSV + JSON (+ charts, Phase 3)
under ``03_Analysis/generation_metadata/``.

Module boundaries (see each module's docstring for the exact contract):
- ``pricing.py``          -- parse/validate ``config/analysis/model_pricing.yaml``.
- ``persona_metrics.py``  -- reduce one persona's normalized call entries to a record.
- ``cost.py``             -- per-persona USD cost from the pricing table (fail-fast).
- ``combo_aggregator.py`` -- per-metric mean/std/n over a combo's personas.
- ``report_writer.py``    -- serialize a country's combo summaries to CSV + JSON.
- ``charts.py``           -- per-metric model x method mean-heatmaps (PNG+SVG).

Public entrypoint: :func:`summarize`. Stats primitives live in
``analysis/utils/_stats.py`` (single source of truth), never inlined here.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from population_synthetic.analysis.generation_metadata.charts import render_metric_heatmaps
from population_synthetic.analysis.generation_metadata.combo_aggregator import ComboSummary, aggregate_combo
from population_synthetic.analysis.generation_metadata.cost import persona_cost
from population_synthetic.analysis.generation_metadata.persona_metrics import (
    PersonaMetrics,
    load_persona_entries,
    reduce_persona,
)
from population_synthetic.analysis.generation_metadata.pricing import PricingTable, load_pricing_table
from population_synthetic.analysis.generation_metadata.report_writer import write_reports
from population_synthetic.analysis.utils.axes import decompose_slug, diagnose_slug
from population_synthetic.analysis.utils.registry import analysis_output_dir, resolve_output_base
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values

logger = logging.getLogger(__name__)

__all__ = ["summarize"]

# Canonical analysis process id: registry key == GUI task key == output folder name.
_PROCESS_ID = "generation_metadata"

# The raw-generation stage folder. This mirrors the literal used by the generator
# (see manifest_loader.compose_manifest: ``{output_base}/01_Raw/{slug}``); it is a
# structural path constant for the pipeline layout, not a tunable value.
_RAW_STAGE_DIR = "01_Raw"


def _axis_ids() -> tuple[list[str], list[str], list[str]]:
    """Return ``(country_ids, strategy_ids, model_ids)`` from the axis registries."""
    country_ids = sorted(d["id"] for d in discover_axis_values("countries"))
    strategy_ids = sorted(d["id"] for d in discover_axis_values("strategies"))
    model_ids = sorted(d["id"] for d in discover_axis_values("models"))
    return country_ids, strategy_ids, model_ids


def _collect_personas(
    slug_dir: Path,
    slug: str,
    model: str,
    pricing: PricingTable,
) -> tuple[list[tuple[str, PersonaMetrics, float | None]], list[dict[str, str]]]:
    """Reduce every ``persona_*`` dir under *slug_dir* to metric+cost records.

    Returns ``(personas, no_file_skips)`` where *personas* is one
    ``(persona_id, PersonaMetrics, cost)`` triple per persona that had an
    interaction file, and *no_file_skips* records personas whose directory carried
    no ``llm_interactions.*`` file. Cost computation is fail-fast: a persona with
    token telemetry but an unpriced model raises (via :func:`persona_cost`).
    """
    personas: list[tuple[str, PersonaMetrics, float | None]] = []
    no_file_skips: list[dict[str, str]] = []

    for persona_dir in sorted(p for p in slug_dir.glob("persona_*") if p.is_dir()):
        persona_id = persona_dir.name
        entries = load_persona_entries(persona_dir)
        if entries is None:
            no_file_skips.append(
                {"slug": slug, "persona": persona_id, "reason": "no interaction file"}
            )
            continue
        pm = reduce_persona(entries)
        cost = persona_cost(model, pm.input_tokens, pm.output_tokens, pricing)
        personas.append((persona_id, pm, cost))

    return personas, no_file_skips


def summarize(
    *,
    output_base: str | Path | None = None,
    countries: list[str] | None = None,
    models: list[str] | None = None,
    strategies: list[str] | None = None,
    slugs: list[str] | None = None,
    force: bool = False,
    charts: bool = False,
    strict: bool = False,
    pricing_path: str | Path | None = None,
) -> dict[str, dict[str, Path]]:
    """Compute and write per-country generation-metadata reports.

    Discovers run slug dirs under ``{output_base}/01_Raw/``, decomposes each into a
    ``(country, method, model)`` combo via the shared axis registries, filters by
    the axis arguments, groups by country, reduces each combo's personas to
    per-metric mean/std/n (+ estimated USD cost), and writes ``{country}_summary``
    CSV + JSON per country.

    Idempotent: a country whose CSV already exists is skipped unless *force* is set
    (its charts are skipped with it). When *charts* is set, per-metric model x
    method mean-heatmaps are rendered into a ``charts/`` subfolder for each country
    actually written.

    Parameters
    ----------
    output_base:
        Run base (the ``02_Data`` dir). Defaults via
        :func:`resolve_output_base` (CLI value else experiment defaults).
    countries, models, strategies, slugs:
        Optional axis filters (narrow the selection; filtered-out combos are
        neither reported nor skipped).
    force:
        Re-write a country whose report already exists.
    charts:
        Render per-metric model x method heatmaps into ``{output_dir}/charts/``
        for each country written.
    strict:
        Raise on an undecomposable slug that matches a known country prefix,
        instead of silently skipping it.
    pricing_path:
        Optional override for the pricing config path.

    Returns
    -------
    dict[str, dict[str, Path]]
        ``{country: {"csv": path, "json": path}}`` for every country actually written.
    """
    base = resolve_output_base(str(output_base) if output_base is not None else None)
    raw_root = base / _RAW_STAGE_DIR
    if not raw_root.is_dir():
        raise FileNotFoundError(f"Raw generation stage not found: {raw_root}")

    pricing = load_pricing_table(pricing_path)
    pricing_meta = {
        "observed_date": pricing.observed_date,
        "source": pricing.source,
        "currency": pricing.currency,
    }

    country_ids, strategy_ids, model_ids = _axis_ids()

    # combo summaries + combo-level skips, grouped by country.
    per_country: dict[str, list[ComboSummary]] = {}
    per_country_skipped: dict[str, list[dict[str, str]]] = {}

    for slug_dir in sorted(p for p in raw_root.iterdir() if p.is_dir()):
        slug = slug_dir.name
        if slugs and slug not in slugs:
            continue

        decomposed = decompose_slug(slug, country_ids, strategy_ids, model_ids)
        if decomposed is None:
            # Non-combo dirs (legacy seed_*, ad-hoc runs) are not this task's data.
            # Only diagnose-and-fail loudly under --strict for country-prefixed slugs.
            if strict and any(slug == c or slug.startswith(c + "_") for c in country_ids):
                raise ValueError(
                    f"Undecomposable slug {slug!r}: "
                    f"{diagnose_slug(slug, country_ids, strategy_ids, model_ids)}"
                )
            continue
        country, strategy, model = decomposed

        if countries and country not in countries:
            continue
        if models and model not in models:
            continue
        if strategies and strategy not in strategies:
            continue

        personas, no_file_skips = _collect_personas(slug_dir, slug, model, pricing)
        skips = per_country_skipped.setdefault(country, [])
        if not personas:
            skips.append(
                {"slug": slug, "reason": "no persona had an interaction file"}
            )
            skips.extend(no_file_skips)
            continue

        summary = aggregate_combo(country, model, strategy, personas, prior_skipped=no_file_skips)
        per_country.setdefault(country, []).append(summary)

    output_dir = analysis_output_dir(_PROCESS_ID, base)
    generated_at = datetime.now(timezone.utc).isoformat()
    written: dict[str, dict[str, Path]] = {}

    for country, summaries in sorted(per_country.items()):
        csv_path = output_dir / f"{country}_summary.csv"
        if csv_path.exists() and not force:
            logger.info(
                "generation_metadata: %s report exists (%s); skipping (use force=True to overwrite).",
                country,
                csv_path,
            )
            continue
        written[country] = write_reports(
            country,
            summaries,
            output_dir=output_dir,
            pricing_meta=pricing_meta,
            combo_skipped=per_country_skipped.get(country, []),
            generated_at=generated_at,
            output_base=str(base),
        )
        logger.info("generation_metadata: wrote %s (%d combos).", csv_path, len(summaries))

        if charts:
            chart_paths = render_metric_heatmaps(country, summaries, output_dir / "charts")
            logger.info(
                "generation_metadata: rendered %d chart(s) for %s into %s.",
                len(chart_paths),
                country,
                output_dir / "charts",
            )

    return written
