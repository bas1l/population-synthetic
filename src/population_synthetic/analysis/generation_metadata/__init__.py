"""generation_metadata -- per country x model x method(strategy) generation-cost report.

Pipe-and-filter analysis stage: reads 01_Raw LLM-call telemetry, reduces each
persona to a per-persona metric record, aggregates per-combo distribution stats
(mean/std/median/q1/q3/n) + combo-level scalar diagnostics, runs one deep
per-combo diagnostics pass over the combo's joined entry stream, applies a
config-driven cost model, and emits a per-country CSV (scalars) + JSON (scalars +
deep diagnostics) + charts under ``03_Analysis/generation_metadata/``.

Module boundaries (see each module's docstring for the exact contract):
- ``pricing.py``            -- parse/validate ``config/analysis/model_pricing.yaml``.
- ``interaction_parser.py`` -- parse ``llm_interactions.{jsonl,json}`` into entries.
- ``log_parser.py``         -- parse ``logs/run_*.log`` call lines + run summary.
- ``joiner.py``             -- join log call records into the JSONL entry stream.
- ``persona_metrics.py``    -- reduce one persona's normalized call entries to a record.
- ``cost.py``               -- per-persona USD cost from the pricing table (fail-fast).
- ``diagnostics.py``        -- ``compute_metrics``: deep per-combo diagnostics.
- ``combo_aggregator.py``   -- per-metric distribution stats + scalar diagnostics.
- ``report_writer.py``      -- serialize a country's combo summaries to CSV + JSON.
- ``charts.py``             -- metric heatmaps + per-combo diagnostic charts (PNG+SVG).

Public entrypoint: :func:`summarize`. Stats primitives live in
``analysis/utils/_stats.py`` (single source of truth), never inlined here.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from population_synthetic.analysis.generation_metadata.charts import (
    plot_run_charts,
    plot_run_comparison,
    render_metric_heatmaps,
)
from population_synthetic.analysis.generation_metadata.combo_aggregator import ComboSummary, aggregate_combo
from population_synthetic.analysis.generation_metadata.comparison import (
    build_summary_comparison,
    significance_from_comparison,
)
from population_synthetic.analysis.generation_metadata.cost import persona_cost
from population_synthetic.analysis.generation_metadata.diagnostics import compute_metrics
from population_synthetic.analysis.generation_metadata.interaction_parser import (
    find_interaction_file,
    parse_interactions,
)
from population_synthetic.analysis.generation_metadata.joiner import join_entries
from population_synthetic.analysis.generation_metadata.log_parser import (
    find_log_files,
    parse_log_file,
    parse_run_summary,
)
from population_synthetic.analysis.generation_metadata.persona_metrics import (
    PersonaMetrics,
    reduce_persona,
)
from population_synthetic.analysis.generation_metadata.pricing import PricingTable, load_pricing_table
from population_synthetic.analysis.generation_metadata.report_writer import write_reports
from population_synthetic.analysis.utils.axes import decompose_slug, diagnose_slug
from population_synthetic.analysis.utils.capped_source import resolve_stage_source
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


def _persona_joined_entries(persona_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Parse+join one persona dir's JSONL entries with its own ``logs/`` records.

    Parses the interaction file, parses any per-persona ``logs/run_*.log`` call
    lines, and joins them (JSONL-native telemetry preferred, log-derived
    tokens/latency backfilled). The last
    log file supplies the run summary when present. Assumes an interaction file
    exists (the caller checked). Returns ``(enriched_entries, run_summary)``.
    """
    interaction_file = find_interaction_file(persona_dir)
    jsonl_entries = parse_interactions(interaction_file) if interaction_file else []

    log_files = find_log_files(persona_dir)
    log_entries: list[dict[str, Any]] = []
    for lf in log_files:
        log_entries.extend(parse_log_file(lf))
    run_summary = parse_run_summary(log_files[-1]) if log_files else None

    return join_entries(jsonl_entries, log_entries), run_summary


def _collect_personas(
    slug_dir: Path,
    slug: str,
    model: str,
    pricing: PricingTable,
) -> tuple[
    list[tuple[str, PersonaMetrics, float | None]],
    list[dict[str, str]],
    list[dict[str, Any]],
    dict[str, Any] | None,
]:
    """Reduce every ``persona_*`` dir under *slug_dir* and build the combo entry stream.

    Returns ``(personas, no_file_skips, combo_entries, run_summary)`` where:

    - *personas* is one ``(persona_id, PersonaMetrics, cost)`` triple per persona
      that had an interaction file (the scalar/distribution path, reduced from the
      persona's JSONL entries; cost is fail-fast on a tokened-but-unpriced model).
    - *no_file_skips* records personas whose dir carried no ``llm_interactions.*``.
    - *combo_entries* is every persona's joined entries (each tagged with its
      ``persona_id``), the single stream fed to ``compute_metrics`` for the combo's
      deep diagnostics.
    - *run_summary* is the best available ``{elapsed_s, success, failed}`` summary.

    The join contract: entries are
    joined against each persona's own ``logs/`` first, then -- for parallel runs
    that write a single top-level ``logs/`` master holding every persona's call
    records -- the combined stream is re-joined against those top-level records so
    token/latency metrics are populated. The join is exact on a ``(persona_id,
    call_index)`` correlation key when present, else timestamp-proximity.
    """
    personas: list[tuple[str, PersonaMetrics, float | None]] = []
    no_file_skips: list[dict[str, str]] = []
    combo_entries: list[dict[str, Any]] = []
    run_summary: dict[str, Any] | None = None

    for persona_dir in sorted(p for p in slug_dir.glob("persona_*") if p.is_dir()):
        persona_id = persona_dir.name
        interaction_file = find_interaction_file(persona_dir)
        if interaction_file is None:
            no_file_skips.append(
                {"slug": slug, "persona": persona_id, "reason": "no interaction file"}
            )
            continue
        jsonl_entries = parse_interactions(interaction_file)

        # Scalar/distribution path: reduce from the persona's own JSONL entries.
        pm = reduce_persona(jsonl_entries)
        cost = persona_cost(model, pm.input_tokens, pm.output_tokens, pricing)
        personas.append((persona_id, pm, cost))

        # Diagnostics path: join with the persona's own logs, tag, accumulate.
        enriched, persona_summary = _persona_joined_entries(persona_dir)
        for entry in enriched:
            entry["persona_id"] = persona_id
        combo_entries.extend(enriched)
        if persona_summary is not None:
            run_summary = persona_summary

    # Parallel runs keep a single top-level logs/ master (the persona_* dirs carry
    # no logs/ of their own); re-join the combined stream against it for tokens
    # and latency, and prefer its success/failed summary.
    top_level_logs = find_log_files(slug_dir)
    top_level_log_entries: list[dict[str, Any]] = []
    for lf in top_level_logs:
        top_level_log_entries.extend(parse_log_file(lf))
    if top_level_logs:
        top_summary = parse_run_summary(top_level_logs[-1])
        if top_summary is not None:
            run_summary = top_summary
    if top_level_log_entries:
        combo_entries = join_entries(combo_entries, top_level_log_entries)

    return personas, no_file_skips, combo_entries, run_summary


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
    metrics: list[str] | None = None,
    on_combo: Callable[[ComboSummary, Path], None] | None = None,
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
    metrics:
        Optional subset of the comparison metric ids (``combo_aggregator.
        METRIC_NAMES``) to restrict the cross-factor significance computation to.
        ``None`` (default) considers all eight. The CSV/JSON scalar columns are
        unaffected -- this only narrows the ``significance`` block and the
        comparison charts.
    on_combo:
        Optional callback invoked once per combo of every country actually
        written, as ``on_combo(summary, raw_slug_dir)``. It is a pure
        presentation hook (the CLI's ``--verbose`` console view uses it to render
        each combo's deep diagnostics); ``summarize`` computes nothing extra for
        it and ignores its return value. Not called for skipped (already-present,
        no-``force``) countries.

    Returns
    -------
    dict[str, dict[str, Path]]
        ``{country: {"csv": path, "json": path}}`` for every country actually written.
    """
    base = resolve_output_base(str(output_base) if output_base is not None else None)
    # Personas are read from the capped mirror, never from 01_Raw. resolve_stage_source
    # raises FileNotFoundError (fail-fast, no fallback) if population_cap has not run.
    raw_root = resolve_stage_source(base)
    if not raw_root.is_dir():
        raise FileNotFoundError(f"Capped generation stage not found: {raw_root}")

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

        personas, no_file_skips, combo_entries, run_summary = _collect_personas(
            slug_dir, slug, model, pricing
        )
        skips = per_country_skipped.setdefault(country, [])
        if not personas:
            skips.append(
                {"slug": slug, "reason": "no persona had an interaction file"}
            )
            skips.extend(no_file_skips)
            continue

        # One deep-diagnostics pass per combo over its whole (joined) entry stream.
        diagnostics = compute_metrics(combo_entries, run_summary=run_summary)
        summary = aggregate_combo(
            country, model, strategy, personas,
            prior_skipped=no_file_skips, diagnostics=diagnostics,
        )
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

        # Country-level cross-factor comparison + significance over the in-memory
        # combos (no file re-read). The rich structure feeds the comparison charts;
        # its reduction (KW/Dunn + CLD letters) goes into the CSV columns and JSON.
        comparison = build_summary_comparison(summaries, metric_keys=metrics)
        significance = significance_from_comparison(comparison)

        written[country] = write_reports(
            country,
            summaries,
            output_dir=output_dir,
            pricing_meta=pricing_meta,
            combo_skipped=per_country_skipped.get(country, []),
            generated_at=generated_at,
            output_base=str(base),
            significance=significance,
        )
        logger.info("generation_metadata: wrote %s (%d combos).", csv_path, len(summaries))

        if on_combo is not None:
            for summary in summaries:
                slug_dir = raw_root / f"{summary.country}_{summary.strategy}_{summary.model}"
                on_combo(summary, slug_dir)

        if charts:
            charts_dir = output_dir / "charts"
            chart_paths = render_metric_heatmaps(country, summaries, charts_dir)
            # Cross-factor comparison charts (box + Dunn brackets, mean+/-SD bars,
            # model x method heatmaps) into a per-country comparison/ subdir.
            chart_paths.extend(
                plot_run_comparison(comparison, charts_dir / f"{country}_comparison")
            )
            # Per-combo deep-diagnostic charts (latency, error/retry taxonomy,
            # value-diversity entropy, token budgets, ...) into a per-combo subdir
            # so the generic diagnostic filenames never collide across combos.
            for summary in summaries:
                if not summary.diagnostics:
                    continue
                combo_dir = charts_dir / f"{summary.strategy}_{summary.model}"
                chart_paths.extend(plot_run_charts(summary.diagnostics, combo_dir))
            logger.info(
                "generation_metadata: rendered %d chart(s) for %s into %s.",
                len(chart_paths),
                country,
                charts_dir,
            )

    return written
