"""Serialize a country's combo summaries to CSV + JSON.

Takes the aggregated :class:`ComboSummary` records for one country and writes two
artifacts under the process output folder:

- ``{country}_summary.csv`` -- one row per ``(model, method)`` combo, with a
  ``<metric>_{mean,std,median,q1,q3,n}`` column set per distribution metric, then
  the combo-level scalar-diagnostic columns (``latency_p95``, ``latency_max``,
  ``success_rate``). Deep (per-category / per-step) diagnostics are NOT flattened
  here -- they live in the JSON only.
- ``{country}_summary.json`` -- the same scalar numbers nested per combo (including
  the scalar diagnostics inside each combo's ``metrics``), a per-combo
  ``diagnostics`` block (the full ``compute_metrics`` dict), plus run metadata
  (pricing provenance, generation timestamp, output base) and the combined
  skipped list.

This module owns serialization only: it knows nothing about how the metrics were
computed or how charts are styled. Row/column *ordering* is presentation and lives
here (methods by pipeline complexity, then model alphabetically).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from population_synthetic.analysis.generation_metadata.combo_aggregator import (
    DISTRIBUTION_STATS,
    METRIC_NAMES,
    SCALAR_METRIC_NAMES,
    ComboSummary,
)
from population_synthetic.analysis.generation_metadata.comparison import FACTORS, group_label
from population_synthetic.analysis.utils.axes import strategy_complexity_order

__all__ = ["write_reports"]

# Significance-group column tail (appended after the scalar columns). For every
# comparison metric (``METRIC_NAMES``) and every experimental factor, one
# ``<metric>_<factor>_group`` compact-letter-display column. Iterating metric-outer,
# factor-inner keeps the pair for a metric adjacent and the order deterministic;
# this is the single source of truth for both the header and the row cells.
_GROUP_FACTORS: tuple[str, ...] = tuple(label for label, _ in FACTORS)

# Rounding applied to every serialized mean/std (keeps files readable and stable
# across platforms without discarding meaningful precision for tokens/time/cost).
_ROUND = 6


def _round(value: float | int | None) -> float | int | None:
    """Round a numeric value for output; pass ``None`` and ints through unchanged."""
    if value is None or isinstance(value, int):
        return value
    return round(value, _ROUND)


def _strategy_ranks(summaries: list[ComboSummary]) -> dict[str, int]:
    """Rank map over the strategies present, resolved once per report.

    Resolved here (once) rather than per row, and **loudly**: an id with no axis
    file, or with a family absent from the family index, raises out of
    :func:`~population_synthetic.analysis.utils.axes.strategy_complexity_order`.
    The previous behaviour -- "unknown strategies sort last" -- turned an
    axis-naming drift into a plausible-looking report whose row order silently
    stopped meaning pipeline complexity.
    """
    ordered = strategy_complexity_order(sorted({s.strategy for s in summaries}))
    return {strategy: rank for rank, strategy in enumerate(ordered)}


def _sort_key(summary: ComboSummary, ranks: dict[str, int]) -> tuple[int, str, str]:
    """Order combos by strategy pipeline complexity, then model id (stable)."""
    return (ranks[summary.strategy], summary.strategy, summary.model)


def _factor_name(summary: ComboSummary, factor_label: str) -> str:
    """The combo's group name under a factor: its model, or its method/strategy."""
    return summary.model if factor_label == "model" else summary.strategy


def _csv_header() -> list[str]:
    """Column order: identity, ``<metric>_<stat>`` per metric, scalars, group labels.

    The scalar columns come after the distribution stats; the significance
    ``<metric>_<factor>_group`` columns come last (one per comparison metric per
    factor, metric-outer / factor-inner). A single source of truth shared with
    :func:`_csv_row`.
    """
    header = ["model", "method", "n_personas", "has_token_data"]
    for name in METRIC_NAMES:
        header += [f"{name}_{stat}" for stat in DISTRIBUTION_STATS]
    header += list(SCALAR_METRIC_NAMES)
    for name in METRIC_NAMES:
        header += [f"{name}_{factor}_group" for factor in _GROUP_FACTORS]
    return header


def _csv_row(summary: ComboSummary, significance: dict[str, Any] | None) -> list[object]:
    row: list[object] = [
        summary.model,
        summary.strategy,
        summary.n_personas,
        summary.has_token_data,
    ]
    for name in METRIC_NAMES:
        cell = summary.metrics[name]
        for stat in DISTRIBUTION_STATS:
            # ``n`` is an exact count; the rest are rounded floats (or None).
            row.append(cell[stat] if stat == "n" else _round(cell[stat]))
    for name in SCALAR_METRIC_NAMES:
        row.append(_round(summary.scalar_metrics.get(name)))
    for name in METRIC_NAMES:
        for factor_label, block_key in FACTORS:
            row.append(group_label(significance, name, block_key, _factor_name(summary, factor_label)))
    return row


def write_reports(
    country: str,
    summaries: list[ComboSummary],
    *,
    output_dir: Path,
    pricing_meta: dict[str, str],
    combo_skipped: list[dict[str, str]],
    generated_at: str,
    output_base: str,
    significance: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Write ``{country}_summary.csv`` + ``.json`` and return their paths.

    Parameters
    ----------
    country:
        Country axis id (used only in the output filenames and JSON body).
    summaries:
        The combo summaries to serialize (rows). Reordered for presentation.
    output_dir:
        The process output folder (created if absent).
    pricing_meta:
        Provenance stamps ``{observed_date, source, currency}`` from the pricing
        table -- carried through verbatim so the report records which price sheet
        the cost estimates came from.
    combo_skipped:
        Combo-level skip records (e.g. combos with no interaction data at all).
    generated_at, output_base:
        Run-provenance stamps for the JSON body.
    significance:
        The country-level cross-factor significance view from
        :func:`comparison.significance_from_comparison` (KW p + Dunn matrix +
        per-group CLD letters, per metric per factor). ``None`` renders every
        group-label cell empty and omits the JSON ``significance`` block.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    ranks = _strategy_ranks(summaries)
    ordered = sorted(summaries, key=lambda s: _sort_key(s, ranks))

    csv_path = output_dir / f"{country}_summary.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(_csv_header())
        for summary in ordered:
            writer.writerow(_csv_row(summary, significance))

    json_path = output_dir / f"{country}_summary.json"
    combos = [
        {
            "model": s.model,
            "method": s.strategy,
            "n_personas": s.n_personas,
            "has_token_data": s.has_token_data,
            "metrics": {
                **{
                    name: {
                        stat: (
                            s.metrics[name][stat]
                            if stat == "n"
                            else _round(s.metrics[name][stat])
                        )
                        for stat in DISTRIBUTION_STATS
                    }
                    for name in METRIC_NAMES
                },
                # Combo-level scalar diagnostics live alongside the distribution
                # metrics (flat values, not {mean,std,...} dicts).
                **{name: _round(s.scalar_metrics.get(name)) for name in SCALAR_METRIC_NAMES},
            },
            # Deep per-combo diagnostics (nested per-category / per-step); JSON only.
            "diagnostics": s.diagnostics,
            "skipped": s.skipped,
        }
        for s in ordered
    ]
    payload = {
        "process": "generation_metadata",
        "country": country,
        "generated_at": generated_at,
        "output_base": output_base,
        "pricing": pricing_meta,
        "metrics": list(METRIC_NAMES),
        "scalar_metrics": list(SCALAR_METRIC_NAMES),
        "combos": combos,
        "skipped": combo_skipped,
    }
    # Country-level cross-factor significance (full KW/Dunn results + CLD letters).
    # Left unrounded on purpose: rounding p-values to 6 dp would flatten tiny
    # (highly significant) p-values to 0.0 and lose exactly the information the
    # block exists to carry.
    if significance is not None:
        payload["significance"] = significance
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    return {"csv": csv_path, "json": json_path}
