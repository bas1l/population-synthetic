"""builder.py -- Build the per-country cross-model performance comparison.

Assembles, for one country's :class:`~population_synthetic.analysis.performance.loader.ComboPerformance`
records, the combo × attribute TV-similarity score matrix, the overall ranking
(mean TV-similarity descending, coherence score as tie-break), and the factor
statistics: Kruskal-Wallis omnibus + Dunn/Holm post-hoc (from the shared
``analysis.utils.stats_tests``) grouped **by model** (each model's samples are
its per-attribute TV-similarities pooled across strategies) and **by strategy**
(pooled across models).

Statistical caveat (recorded in the output's ``stats.caveats``): the
per-attribute values of one combo are correlated (they describe the same
population) and every combo scores the same attribute set, so the samples are
pseudo-replicates -- the p-values are indicative evidence for ranking, not
strict inference. Rigorous inference would need replicate runs per combo.

The built structure is directly JSON-serialisable; :func:`write_performance_json`
and :func:`write_performance_csv` persist it.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from population_synthetic.analysis.performance.loader import ComboPerformance
from population_synthetic.analysis.utils import _stats
from population_synthetic.analysis.utils.stats_tests import dunn_posthoc, kruskal_test, summarize

_CAVEATS = (
    "Samples are per-attribute TV-similarities pooled across the other factor: attributes are "
    "correlated within a combo and shared across combos (pseudo-replication), and pooling assumes "
    "a balanced model x strategy grid. P-values are indicative, not strict inference."
)


def _mean(values: list[float]) -> float:
    if not values:
        return float("nan")
    return sum(values) / len(values)


def _group_tv_samples(
    records: list[ComboPerformance],
    key: Callable[[ComboPerformance], str],
) -> dict[str, list[float]]:
    """Concatenate per-attribute TV-similarities across records sharing a group key."""
    groups: dict[str, list[float]] = {}
    for r in records:
        groups.setdefault(key(r), []).extend(r.tv_similarity.values())
    return groups


def _order_by_median_desc(groups: dict[str, list[float]]) -> list[str]:
    """Order group labels by descending median (best first; empty groups last)."""
    def sort_key(label: str) -> tuple[int, float, str]:
        vals = groups[label]
        if not vals:
            return (1, 0.0, label)
        return (0, -float(_stats.median(vals)), label)

    return sorted(groups.keys(), key=sort_key)


def _factor_block(
    records: list[ComboPerformance],
    key: Callable[[ComboPerformance], str],
) -> dict[str, Any]:
    groups = _group_tv_samples(records, key)
    n_combos: dict[str, int] = {}
    for r in records:
        label = key(r)
        n_combos[label] = n_combos.get(label, 0) + 1
    return {
        "order": _order_by_median_desc(groups),
        "groups": {label: summarize(vals) for label, vals in groups.items()},
        "kruskal": kruskal_test(groups),
        "dunn": dunn_posthoc(groups),
        "n_combos_per_group": n_combos,
    }


def build_performance_comparison(
    records: list[ComboPerformance],
    attributes: list[str],
    *,
    skipped: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Build the serialisable performance comparison for one country's records.

    *skipped* (``(slug, reason)`` pairs from the loader) is recorded in the
    metadata so consumers can see grid gaps. Raises when fewer than two combos
    are available (nothing to compare) or the records span multiple countries.
    """
    if len(records) < 2:
        raise ValueError(
            f"Need at least 2 combos to compare, got {len(records)}. "
            "Run scripts/analyze/compare_all_pipelines.py to produce more comparison reports."
        )
    countries = {r.country for r in records}
    if len(countries) != 1:
        raise ValueError(
            f"build_performance_comparison compares one country at a time, got {sorted(countries)}"
        )
    country = next(iter(countries))

    overall_mean = {r.slug: _mean(list(r.tv_similarity.values())) for r in records}
    coherence_score = {r.slug: float(r.coherence["score"]) for r in records}

    def rank_key(r: ComboPerformance) -> tuple[float, float, str]:
        mean = overall_mean[r.slug]
        # NaN overall (no scorable attribute) ranks last.
        return (-mean if mean == mean else float("inf"), -coherence_score[r.slug], r.slug)

    ranked = sorted(records, key=rank_key)
    ranking = [r.slug for r in ranked]

    combos: dict[str, Any] = {}
    for rank, r in enumerate(ranked, start=1):
        per_attribute: dict[str, Any] = {}
        for attr in attributes:
            metric = r.marginals[attr]
            per_attribute[attr] = {
                "tv_similarity": r.tv_similarity.get(attr, float("nan")),
                **{k: metric[k] for k in ("tv_distance", "kl_divergence", "chi_sq_p", "max_diff") if k in metric},
            }
        combos[r.slug] = {
            "model": r.model,
            "strategy": r.strategy,
            "n": r.n_synthetic,
            "overall": {
                "tv_similarity_mean": overall_mean[r.slug],
                "rank": rank,
                "coherence_score": coherence_score[r.slug],
            },
            "per_attribute": per_attribute,
            "coherence": {
                "score": coherence_score[r.slug],
                "n_plausible": r.coherence.get("n_plausible"),
                "n_total": r.coherence.get("n_total"),
                "flagged_count": len(r.coherence.get("flagged", [])),
            },
            # Optional multivariate summaries (reference only; ranking is unchanged).
            "multivariate": {
                "c2st_auc": r.c2st_auc,
                "mean_delta_v": r.mean_delta_v,
            },
            "nan_attributes": [a for a in attributes if a not in r.tv_similarity],
        }

    return {
        "metadata": {
            "country": country,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n_combos": len(records),
            "models": sorted({r.model for r in records}),
            "strategies": sorted({r.strategy for r in records}),
            "attributes": list(attributes),
            "skipped": [{"slug": slug, "reason": reason} for slug, reason in (skipped or [])],
        },
        "combos": combos,
        "ranking": ranking,
        "stats": {
            "metric": "tv_similarity",
            "by_model": _factor_block(records, lambda r: r.model),
            "by_strategy": _factor_block(records, lambda r: r.strategy),
            "caveats": _CAVEATS,
        },
    }


def write_performance_json(result: dict[str, Any], out_path: str | Path) -> Path:
    """Write the performance comparison to *out_path*."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)
    return out_path


def write_performance_csv(result: dict[str, Any], out_path: str | Path) -> Path:
    """Write the per-combo score matrix as CSV (one row per combo, rank order)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    attributes: list[str] = result["metadata"]["attributes"]

    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["rank", "model", "strategy", "slug", "n", "overall_tv_similarity", "coherence_score",
             "c2st_auc", "mean_delta_v"]
            + [f"tv_similarity__{attr}" for attr in attributes]
        )
        for slug in result["ranking"]:
            combo = result["combos"][slug]
            multivariate = combo.get("multivariate") or {}
            writer.writerow(
                [
                    combo["overall"]["rank"],
                    combo["model"],
                    combo["strategy"],
                    slug,
                    combo["n"],
                    combo["overall"]["tv_similarity_mean"],
                    combo["overall"]["coherence_score"],
                    multivariate.get("c2st_auc"),
                    multivariate.get("mean_delta_v"),
                ]
                + [combo["per_attribute"][attr]["tv_similarity"] for attr in attributes]
            )
    return out_path
