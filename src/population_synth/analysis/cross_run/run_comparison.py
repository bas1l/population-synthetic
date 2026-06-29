"""run_comparison.py -- Cross-run scientific comparison of run analytics.

Compares per-run metrics (produced by
:func:`population_synth.analysis.per_run.aggregator.compute_metrics` and persisted as
``run_analytics.json`` files under the ``llm_metrics`` master folder) across the
two experimental factors: **model** and **method/strategy** (country held fixed).

Pipeline:
    1. :func:`load_run_records` (in :mod:`population_synth.analysis.cross_run.comparison_loader`)
       -- glob ``*/run_analytics.json``, decompose each slug into
       ``(country, strategy, model)``, extract comparable samples.
    2. :func:`build_comparison` -- group samples by model and by method, run a
       Kruskal-Wallis omnibus test plus Dunn post-hoc per factor, and build a
       model x method matrix for heatmaps.
    3. :func:`write_comparison_json` -- persist a serialisable summary.

This module is the builder/serialiser layer: it groups, aggregates, and assembles
the comparison structure.  The hypothesis tests live in
:mod:`population_synth.analysis.cross_run.comparison_stats` and the registry/DTOs/I/O live in
:mod:`population_synth.analysis.cross_run.comparison_loader`; both are re-exported below so
existing import sites keep working.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import numpy as np

from population_synth.analysis.cross_run.comparison_loader import (
    METRIC_SPECS,
    METRIC_SPECS_BY_KEY,
    MetricSpec,
    RunRecord,
    decompose_slug,
    diagnose_slug,
    extract_comparison_metrics,
    load_run_records,
)
from population_synth.analysis.cross_run.comparison_stats import (
    _holm,
    _nonempty_groups,
    dunn_posthoc,
    kruskal_test,
    summarize,
)
from population_synth.analysis.shared import _stats

__all__ = [
    # Registry / DTOs / loader (re-exported from comparison_loader)
    "MetricSpec",
    "METRIC_SPECS",
    "METRIC_SPECS_BY_KEY",
    "RunRecord",
    "decompose_slug",
    "diagnose_slug",
    "extract_comparison_metrics",
    "load_run_records",
    # Statistics (re-exported from comparison_stats)
    "_holm",
    "_nonempty_groups",
    "dunn_posthoc",
    "kruskal_test",
    "summarize",
    # Builder / serialiser (defined here)
    "build_comparison",
    "comparison_to_json",
    "write_comparison_json",
]


# ---------------------------------------------------------------------------
# Grouping / aggregation helpers
# ---------------------------------------------------------------------------

def _aggregate(samples: list[float], how: str) -> float | None:
    if not samples:
        return None
    if how == "median":
        return float(_stats.median(samples))
    return float(np.mean(np.asarray(samples, dtype=float)))


def _group_samples(
    records: list[RunRecord],
    key: Callable[[RunRecord], str],
    metric_key: str,
) -> dict[str, list[float]]:
    """Concatenate within-run samples across records sharing the same group key."""
    groups: dict[str, list[float]] = {}
    for r in records:
        groups.setdefault(key(r), []).extend(r.samples.get(metric_key, []))
    return groups


def _order_by_median(groups: dict[str, list[float]]) -> list[str]:
    """Order group labels by ascending median (empty groups last, then by name)."""
    def sort_key(label: str) -> tuple[int, float, str]:
        vals = groups[label]
        if not vals:
            return (1, 0.0, label)
        return (0, float(_stats.median(vals)), label)

    return sorted(groups.keys(), key=sort_key)


# ---------------------------------------------------------------------------
# Comparison build
# ---------------------------------------------------------------------------

def build_comparison(
    records: list[RunRecord],
    metric_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Build the in-memory comparison structure (keeps raw samples for charts)."""
    specs = [s for s in METRIC_SPECS if metric_keys is None or s.key in metric_keys]
    models = sorted({r.model for r in records})
    methods = sorted({r.strategy for r in records})
    countries = sorted({r.country for r in records})

    metrics_out: dict[str, Any] = {}
    for spec in specs:
        recs = [r for r in records if (r.has_token_data or not spec.token_gated)]
        entry: dict[str, Any] = {
            "label": spec.label,
            "unit": spec.unit,
            "kind": spec.kind,
            "token_gated": spec.token_gated,
            "cell_agg": spec.cell_agg,
            "higher_is_better": spec.higher_is_better,
            "skipped": None,
            "by_model": None,
            "by_method": None,
            "matrix": None,
        }

        if not recs or all(not r.samples.get(spec.key) for r in recs):
            reason = (
                "no runs carry token/timing data"
                if spec.token_gated
                else "no samples available"
            )
            entry["skipped"] = reason
            metrics_out[spec.key] = entry
            continue

        by_model = _group_samples(recs, lambda r: r.model, spec.key)
        by_method = _group_samples(recs, lambda r: r.strategy, spec.key)

        entry["by_model"] = {
            "order": _order_by_median(by_model),
            "groups": by_model,
            "kruskal": kruskal_test(by_model),
            "dunn": dunn_posthoc(by_model),
        }
        entry["by_method"] = {
            "order": _order_by_median(by_method),
            "groups": by_method,
            "kruskal": kruskal_test(by_method),
            "dunn": dunn_posthoc(by_method),
        }

        rec_models = sorted({r.model for r in recs})
        rec_methods = sorted({r.strategy for r in recs})
        values: list[list[float | None]] = []
        for model in rec_models:
            row: list[float | None] = []
            for method in rec_methods:
                cell_samples: list[float] = []
                for r in recs:
                    if r.model == model and r.strategy == method:
                        cell_samples.extend(r.samples.get(spec.key, []))
                row.append(_aggregate(cell_samples, spec.cell_agg))
            values.append(row)
        entry["matrix"] = {
            "models": rec_models,
            "methods": rec_methods,
            "cell_agg": spec.cell_agg,
            "values": values,
        }

        metrics_out[spec.key] = entry

    return {
        "metadata": {
            "n_runs": len(records),
            "models": models,
            "methods": methods,
            "countries": countries,
        },
        "metrics": metrics_out,
    }


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def comparison_to_json(result: dict[str, Any]) -> dict[str, Any]:
    """Reduce the in-memory comparison to a serialisable summary (no raw samples)."""
    out: dict[str, Any] = {"metadata": result["metadata"], "metrics": {}}
    for key, entry in result["metrics"].items():
        red: dict[str, Any] = {
            "label": entry["label"],
            "unit": entry["unit"],
            "kind": entry["kind"],
            "token_gated": entry["token_gated"],
            "cell_agg": entry["cell_agg"],
            "higher_is_better": entry["higher_is_better"],
            "skipped": entry["skipped"],
        }
        for factor in ("by_model", "by_method"):
            block = entry.get(factor)
            if block is None:
                red[factor] = None
                continue
            red[factor] = {
                "order": block["order"],
                "groups": {g: summarize(v) for g, v in block["groups"].items()},
                "kruskal": block["kruskal"],
                "dunn": block["dunn"],
            }
        red["matrix"] = entry.get("matrix")
        out["metrics"][key] = red
    return out


def write_comparison_json(result: dict[str, Any], out_path: str | Path) -> Path:
    """Write the serialisable comparison summary to *out_path*."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(comparison_to_json(result), fh, indent=2, ensure_ascii=False)
    return out_path
