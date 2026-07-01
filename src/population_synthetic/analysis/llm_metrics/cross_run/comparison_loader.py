"""comparison_loader.py -- Registry, DTOs, and filesystem I/O for cross-run comparison.

Owns the data contract shared by the cross-run comparison path: the metric
registry (:class:`MetricSpec` / :data:`METRIC_SPECS`), the per-run :class:`RunRecord`
DTO, slug decomposition against the axis-ID registries, the reshaping of a run's
analytics dict into per-metric sample lists, and the filesystem walk that loads
all decodable ``run_analytics.json`` files under the ``llm_metrics`` master folder.

Keeping the registry next to the extraction that produces samples for it lets the
reshaping (:func:`extract_comparison_metrics`) be tested without a filesystem,
while :func:`load_run_records` welds the directory walk to that reshaping.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values

# ---------------------------------------------------------------------------
# Metric specifications
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MetricSpec:
    """Describes one comparable metric extracted from a run's analytics dict."""

    key: str
    label: str
    unit: str
    kind: str            # "dist" (within-run distribution) or "scalar" (one per run)
    token_gated: bool    # only computable for runs that carry token/timing data
    cell_agg: str        # "median" or "mean" -- summary for heatmap cells
    higher_is_better: bool | None


METRIC_SPECS: list[MetricSpec] = [
    MetricSpec("retry_rate", "Retry rate (per category)", "rate", "dist", False, "mean", False),
    MetricSpec("error_rate", "Error rate", "rate", "scalar", False, "mean", False),
    MetricSpec("success_rate", "Success rate", "rate", "scalar", False, "mean", True),
    MetricSpec("wall_clock", "Wall-clock per persona", "s", "dist", False, "median", False),
    MetricSpec("value_diversity", "Value diversity (entropy)", "bits", "dist", False, "mean", True),
    MetricSpec("tokens_per_persona", "Tokens per persona", "tokens", "dist", True, "median", None),
    MetricSpec("latency", "Latency per category (median)", "ms", "dist", True, "median", False),
]

METRIC_SPECS_BY_KEY: dict[str, MetricSpec] = {s.key: s for s in METRIC_SPECS}


# ---------------------------------------------------------------------------
# Run records
# ---------------------------------------------------------------------------

@dataclass
class RunRecord:
    """One analysed run, tagged with its axis IDs and per-metric samples."""

    slug: str
    country: str
    strategy: str
    model: str
    has_token_data: bool
    samples: dict[str, list[float]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Slug decomposition
# ---------------------------------------------------------------------------

def decompose_slug(
    slug: str,
    country_ids: list[str],
    strategy_ids: list[str],
    model_ids: list[str],
) -> tuple[str, str, str] | None:
    """Decompose ``{country}_{strategy}_{model}`` using the known ID registries.

    Slugs are not parseable by naive ``_`` split because both strategy and model
    IDs contain underscores.  We match a country prefix, then the longest model
    suffix that leaves a valid strategy in the middle.  Returns ``None`` when the
    slug does not correspond to a known axis combination (e.g. legacy ``seed_*``).
    """
    strategy_set = set(strategy_ids)
    for country in country_ids:
        if slug != country and not slug.startswith(country + "_"):
            continue
        rest = slug[len(country):].lstrip("_")
        for model in sorted(model_ids, key=len, reverse=True):
            if rest == model or rest.endswith("_" + model):
                strategy = rest[: len(rest) - len(model)].rstrip("_")
                if strategy in strategy_set:
                    return country, strategy, model
    return None


def diagnose_slug(
    slug: str,
    country_ids: list[str],
    strategy_ids: list[str],
    model_ids: list[str],
) -> str:
    """Explain *why* :func:`decompose_slug` returned ``None`` for *slug*.

    Mirrors the decomposition steps to report which axis (country / model /
    strategy) failed to match, so axis-naming drift is diagnosable rather than a
    silent skip.  Assumes the slug is undecomposable (caller checks first).
    """
    matched_country = next(
        (c for c in country_ids if slug == c or slug.startswith(c + "_")), None
    )
    if matched_country is None:
        return (
            "slug not decomposable: no known country prefix "
            f"(known: {', '.join(sorted(country_ids))})"
        )
    rest = slug[len(matched_country):].lstrip("_")
    matched_model = next(
        (m for m in sorted(model_ids, key=len, reverse=True)
         if rest == m or rest.endswith("_" + m)),
        None,
    )
    if matched_model is None:
        return (
            f"slug not decomposable: country '{matched_country}' ok, but no known "
            f"model suffix (known: {', '.join(sorted(model_ids))})"
        )
    middle = rest[: len(rest) - len(matched_model)].rstrip("_")
    return (
        f"slug not decomposable: country '{matched_country}' + model "
        f"'{matched_model}' ok, but middle '{middle}' is not a known strategy "
        f"(known: {', '.join(sorted(strategy_ids))})"
    )


# ---------------------------------------------------------------------------
# Metric extraction
# ---------------------------------------------------------------------------

def extract_comparison_metrics(metrics: dict[str, Any]) -> tuple[dict[str, list[float]], bool]:
    """Reduce a run's analytics dict to per-metric sample lists.

    Distribution metrics yield the within-run values; scalar metrics yield a
    single-element list (or an empty list when unavailable).  Returns
    ``(samples, has_token_data)``.
    """
    summary = metrics.get("summary") or {}
    total_entries = summary.get("total_entries") or 0
    total_errors = summary.get("total_errors") or 0
    run_summary = summary.get("run_summary") or {}

    per_category = metrics.get("per_category") or {}
    retry_rates = [
        float(info.get("retry_rate", 0.0))
        for info in per_category.values()
    ]

    value_div = metrics.get("value_diversity") or {}
    entropies = [
        float(info.get("entropy_bits", 0.0))
        for info in value_div.values()
    ]

    wall = metrics.get("wall_clock_per_persona") or {}
    wall_vals = [float(v) for v in wall.values() if v is not None]

    # Scalar metrics ---------------------------------------------------------
    error_rate = (total_errors / total_entries) if total_entries else None
    success = run_summary.get("success")
    failed = run_summary.get("failed")
    success_rate: float | None = None
    if success is not None and failed is not None and (success + failed) > 0:
        success_rate = success / (success + failed)

    # Token-gated metrics ----------------------------------------------------
    tok_per_persona = metrics.get("token_consumption_per_persona")
    tokens: list[float] = []
    if tok_per_persona:
        tokens = [float(d.get("total_tokens", 0)) for d in tok_per_persona.values()]

    latency_cat = metrics.get("latency_by_category")
    latencies: list[float] = []
    if latency_cat:
        latencies = [
            float(d["median_ms"])
            for d in latency_cat.values()
            if d.get("median_ms") is not None
        ]

    has_token_data = tok_per_persona is not None or latency_cat is not None

    samples: dict[str, list[float]] = {
        "retry_rate": retry_rates,
        "error_rate": [error_rate] if error_rate is not None else [],
        "success_rate": [success_rate] if success_rate is not None else [],
        "wall_clock": wall_vals,
        "value_diversity": entropies,
        "tokens_per_persona": tokens,
        "latency": latencies,
    }
    return samples, has_token_data


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_run_records(
    llm_metrics_root: str | Path,
    *,
    json_filename: str = "run_analytics.json",
    country: str | None = None,
) -> tuple[list[RunRecord], list[tuple[str, str]]]:
    """Load all decodable per-run analytics under the master folder.

    Returns ``(records, skipped)`` where *skipped* is a list of
    ``(slug, reason)`` for directories that were not usable.
    """
    root = Path(llm_metrics_root)
    if not root.is_dir():
        raise FileNotFoundError(f"llm_metrics root not found: {root}")

    model_ids = [d["id"] for d in discover_axis_values("models")]
    strategy_ids = [d["id"] for d in discover_axis_values("strategies")]
    country_ids = [d["id"] for d in discover_axis_values("countries")]

    records: list[RunRecord] = []
    skipped: list[tuple[str, str]] = []

    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        if sub.name.startswith("_"):
            continue  # reserved (e.g. _comparison)
        jpath = sub / json_filename
        if not jpath.exists():
            skipped.append((sub.name, "no run_analytics.json"))
            continue
        decomp = decompose_slug(sub.name, country_ids, strategy_ids, model_ids)
        if decomp is None:
            skipped.append(
                (sub.name, diagnose_slug(sub.name, country_ids, strategy_ids, model_ids))
            )
            continue
        c, strategy, model = decomp
        if country is not None and c != country:
            continue
        with open(jpath, encoding="utf-8") as fh:
            metrics = json.load(fh)
        samples, has_token = extract_comparison_metrics(metrics)
        records.append(
            RunRecord(
                slug=sub.name,
                country=c,
                strategy=strategy,
                model=model,
                has_token_data=has_token,
                samples=samples,
            )
        )

    return records, skipped
