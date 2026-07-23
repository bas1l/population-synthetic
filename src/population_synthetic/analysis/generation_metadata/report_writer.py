"""Serialize a country's combo summaries to CSV + JSON.

Takes the aggregated :class:`ComboSummary` records for one country and writes two
artifacts under the process output folder:

- ``{country}_summary.csv`` -- one row per ``(model, method)`` combo, with a
  ``<metric>_mean`` / ``<metric>_std`` / ``<metric>_n`` column triple per metric.
- ``{country}_summary.json`` -- the same numbers nested per combo, plus run
  metadata (pricing provenance, generation timestamp, output base) and the
  combined skipped list.

This module owns serialization only: it knows nothing about how the metrics were
computed or how charts are styled. Row/column *ordering* is presentation and lives
here (methods by pipeline complexity, then model alphabetically).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from population_synthetic.analysis.generation_metadata.combo_aggregator import METRIC_NAMES, ComboSummary
from population_synthetic.analysis.utils.axes import STRATEGY_COMPLEXITY_ORDER

__all__ = ["write_reports"]

# Rounding applied to every serialized mean/std (keeps files readable and stable
# across platforms without discarding meaningful precision for tokens/time/cost).
_ROUND = 6


def _round(value: float | int | None) -> float | int | None:
    """Round a numeric value for output; pass ``None`` and ints through unchanged."""
    if value is None or isinstance(value, int):
        return value
    return round(value, _ROUND)


def _sort_key(summary: ComboSummary) -> tuple[int, str, str]:
    """Order combos by strategy pipeline complexity, then model id (stable)."""
    try:
        strat_rank = STRATEGY_COMPLEXITY_ORDER.index(summary.strategy)
    except ValueError:
        strat_rank = len(STRATEGY_COMPLEXITY_ORDER)  # unknown strategies sort last
    return (strat_rank, summary.strategy, summary.model)


def _csv_header() -> list[str]:
    """Column order: identity, then ``<metric>_{mean,std,n}`` per metric in order."""
    header = ["model", "method", "n_personas", "has_token_data"]
    for name in METRIC_NAMES:
        header += [f"{name}_mean", f"{name}_std", f"{name}_n"]
    return header


def _csv_row(summary: ComboSummary) -> list[object]:
    row: list[object] = [
        summary.model,
        summary.strategy,
        summary.n_personas,
        summary.has_token_data,
    ]
    for name in METRIC_NAMES:
        cell = summary.metrics[name]
        row += [_round(cell["mean"]), _round(cell["std"]), cell["n"]]
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
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(summaries, key=_sort_key)

    csv_path = output_dir / f"{country}_summary.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(_csv_header())
        for summary in ordered:
            writer.writerow(_csv_row(summary))

    json_path = output_dir / f"{country}_summary.json"
    combos = [
        {
            "model": s.model,
            "method": s.strategy,
            "n_personas": s.n_personas,
            "has_token_data": s.has_token_data,
            "metrics": {
                name: {
                    "mean": _round(s.metrics[name]["mean"]),
                    "std": _round(s.metrics[name]["std"]),
                    "n": s.metrics[name]["n"],
                }
                for name in METRIC_NAMES
            },
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
        "combos": combos,
        "skipped": combo_skipped,
    }
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    return {"csv": csv_path, "json": json_path}
