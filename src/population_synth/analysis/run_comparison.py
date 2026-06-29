"""run_comparison.py -- Cross-run scientific comparison of run analytics.

Compares per-run metrics (produced by
:func:`population_synth.analysis.aggregator.compute_metrics` and persisted as
``run_analytics.json`` files under the ``llm_metrics`` master folder) across the
two experimental factors: **model** and **method/strategy** (country held fixed).

Pipeline:
    1. :func:`load_run_records` -- glob ``*/run_analytics.json``, decompose each
       slug into ``(country, strategy, model)``, extract comparable samples.
    2. :func:`build_comparison` -- group samples by model and by method, run a
       Kruskal-Wallis omnibus test plus Dunn post-hoc per factor, and build a
       model x method matrix for heatmaps.
    3. :func:`write_comparison_json` -- persist a serialisable summary.

Statistics use the non-parametric Kruskal-Wallis H-test (``scipy.stats.kruskal``)
and an inline Dunn post-hoc with Holm step-down correction -- chosen over
parametric ANOVA because per-group sample sizes are small and the metrics are not
expected to be normally distributed.  Dunn's test is implemented here (rather than
via ``scikit-posthocs``) to avoid adding a dependency.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np
from scipy import stats

from population_synth.analysis import _stats
from population_synth.identity.manifest_loader import discover_axis_values

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


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def _nonempty_groups(groups: dict[str, list[float]]) -> dict[str, list[float]]:
    return {g: v for g, v in groups.items() if len(v) >= 1}


def kruskal_test(groups: dict[str, list[float]]) -> dict[str, Any]:
    """Kruskal-Wallis H-test across groups.

    Returns ``{"H","p","k","n"}`` on success, or ``{"H":None,"p":None,"note":...}``
    when the test cannot be computed (fewer than 2 non-empty groups, or all values
    identical).
    """
    g = _nonempty_groups(groups)
    if len(g) < 2:
        return {"H": None, "p": None, "k": len(g), "n": sum(len(v) for v in g.values()),
                "note": "need >=2 non-empty groups"}
    try:
        h, p = stats.kruskal(*g.values())
    except ValueError as exc:
        return {"H": None, "p": None, "k": len(g),
                "n": sum(len(v) for v in g.values()), "note": str(exc)}
    return {"H": float(h), "p": float(p), "k": len(g), "n": sum(len(v) for v in g.values())}


def _holm(pvals: list[float]) -> list[float]:
    """Holm step-down adjustment of a list of p-values (order preserved)."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    adj = [0.0] * m
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (m - rank) * pvals[idx])
        adj[idx] = min(1.0, running)
    return adj


def dunn_posthoc(groups: dict[str, list[float]]) -> list[dict[str, Any]]:
    """Dunn's post-hoc test (rank-based, tie-corrected) with Holm adjustment.

    Returns a list of ``{"a","b","z","p_raw","p_holm"}`` for every group pair.
    Empty when fewer than 2 non-empty groups.
    """
    g = _nonempty_groups(groups)
    labels = list(g.keys())
    if len(labels) < 2:
        return []

    data: list[float] = []
    grp_of: list[str] = []
    for label in labels:
        for v in g[label]:
            data.append(v)
            grp_of.append(label)

    n = len(data)
    if n < 2:
        return []

    arr = np.asarray(data, dtype=float)
    ranks = stats.rankdata(arr)
    grp_arr = np.asarray(grp_of)

    _, counts = np.unique(arr, return_counts=True)
    tie_sum = float(np.sum(counts.astype(float) ** 3 - counts))
    sigma2 = (n * (n + 1) / 12.0) - tie_sum / (12.0 * (n - 1)) if n > 1 else 0.0

    mean_rank: dict[str, float] = {}
    size: dict[str, int] = {}
    for label in labels:
        mask = grp_arr == label
        mean_rank[label] = float(np.mean(ranks[mask]))
        size[label] = int(np.sum(mask))

    pairs: list[tuple[str, str]] = []
    zs: list[float] = []
    raw: list[float] = []
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            a, b = labels[i], labels[j]
            denom = math.sqrt(sigma2 * (1.0 / size[a] + 1.0 / size[b])) if sigma2 > 0 else 0.0
            if denom == 0:
                z, p = 0.0, 1.0
            else:
                z = (mean_rank[a] - mean_rank[b]) / denom
                p = 2.0 * float(stats.norm.sf(abs(z)))
            pairs.append((a, b))
            zs.append(z)
            raw.append(p)

    p_holm = _holm(raw)
    return [
        {"a": a, "b": b, "z": z, "p_raw": pr, "p_holm": ph}
        for (a, b), z, pr, ph in zip(pairs, zs, raw, p_holm)
    ]


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------

def summarize(samples: list[float]) -> dict[str, Any]:
    """Descriptive summary of a sample list (None fields when empty)."""
    if not samples:
        return {"n": 0, "median": None, "mean": None, "std": None,
                "q1": None, "q3": None, "min": None, "max": None}
    arr = np.asarray(samples, dtype=float)
    # Percentiles use the project-wide nearest-rank convention (analysis._stats),
    # so a metric's q1/q3 here match its per-run chart.  Mean/std stay on numpy.
    return {
        "n": int(arr.size),
        "median": float(_stats.median(samples)),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0,
        "q1": float(_stats.percentile(samples, 25)),
        "q3": float(_stats.percentile(samples, 75)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
    }


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
