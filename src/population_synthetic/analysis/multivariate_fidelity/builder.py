"""builder.py -- Build and persist the standalone multivariate-fidelity envelope.

Wraps the shared multivariate computation
(:meth:`~population_synthetic.analysis.fidelity.evaluator.StatisticalEvaluator.compute_multivariate`)
for one mapped synthetic population against its country's mapped real population, and
aggregates a set of those envelopes into a per-country roll-up table. Nothing here
re-implements a metric: the whole ``multivariate`` block comes back unchanged from the
comparison evaluator, so this process scores identically to the comparison process and
merely persists to its own ``03_Analysis/multivariate_fidelity/`` folder.

The built structures are directly JSON/CSV-serialisable; :func:`write_multivariate_fidelity_json`,
:func:`write_multivariate_fidelity_csv`, and (for the reused pairwise-association CSV)
:func:`~population_synthetic.analysis.fidelity.evaluator.write_association_csv` persist them.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

from population_synthetic.analysis.fidelity.evaluator import StatisticalEvaluator
from population_synthetic.analysis.fidelity.scheme import ComparisonScheme
from population_synthetic.analysis.utils.axes import decompose_slug
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values


def build_multivariate_fidelity(
    real_pop: dict,
    synthetic_pop: dict,
    scheme: ComparisonScheme,
    *,
    slug: str,
    country: str,
) -> dict[str, Any]:
    """Compute the multivariate block for one combo and wrap it in a serialisable envelope.

    Instantiates the shared :class:`StatisticalEvaluator` (real = population A, synthetic =
    population B) and calls *only* ``compute_multivariate()`` -- never ``generate_report()`` --
    so the marginal / joint-chi-squared / coherence comparison is not recomputed here. The
    returned envelope wraps the block under the ``multivariate`` key so the reused association
    CSV writer and heatmap (which read ``report["multivariate"]``) work unchanged.
    """
    evaluator = StatisticalEvaluator(real_pop, synthetic_pop, scheme=scheme)
    multivariate = evaluator.compute_multivariate()
    return {
        "slug": slug,
        "country": country,
        "n_synthetic": synthetic_pop["metadata"]["n"],
        "multivariate": multivariate,
    }


def write_multivariate_fidelity_json(envelope: dict[str, Any], out_path: str | Path) -> Path:
    """Write one combo's multivariate-fidelity envelope to *out_path*."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(envelope, fh, indent=2, ensure_ascii=False)
    return out_path


def _mean_grounded_joint_tv(multivariate: dict[str, Any]) -> float:
    """Mean joint TV over the grounded pairs (finite values only), NaN when none."""
    pairs = multivariate.get("joint_fidelity", {}).get("pairs", [])
    values = [
        p["joint_tv"]
        for p in pairs
        if p.get("grounded")
        and isinstance(p.get("joint_tv"), (int, float))
        and not math.isnan(p["joint_tv"])
    ]
    if not values:
        return float("nan")
    return sum(values) / len(values)


def aggregate_multivariate_fidelity(envelopes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Roll a country's multivariate-fidelity envelopes up into one summary row per combo.

    Each row carries the combo's identity (``slug``/``strategy``/``model``) and the four
    headline multivariate-fidelity scalars pulled straight from its multivariate block:
    ``c2st_auc``, ``mean_abs_delta_v``, ``frobenius_norm``, and ``mean_grounded_joint_tv``
    (the mean joint TV over the grounded pairs, NaN when a combo has none). ``strategy`` /
    ``model`` are decomposed from the slug against the axis registries; a non-axis slug
    (e.g. a legacy ``seed_*`` run) yields empty strings, mirroring the comparison summary.
    """
    country_ids = sorted({c["id"] for c in discover_axis_values("countries")})
    strategy_ids = sorted({s["id"] for s in discover_axis_values("strategies")})
    model_ids = sorted({m["id"] for m in discover_axis_values("models")})

    rows: list[dict[str, Any]] = []
    for envelope in envelopes:
        slug = envelope["slug"]
        multivariate = envelope["multivariate"]
        decomposed = decompose_slug(slug, country_ids, strategy_ids, model_ids)
        rows.append({
            "slug": slug,
            "strategy": decomposed[1] if decomposed else "",
            "model": decomposed[2] if decomposed else "",
            "c2st_auc": multivariate["c2st"]["auc"],
            "mean_abs_delta_v": multivariate["association"]["mean_abs_delta_v"],
            "frobenius_norm": multivariate["association"]["frobenius_norm"],
            "mean_grounded_joint_tv": _mean_grounded_joint_tv(multivariate),
        })
    return rows


def write_multivariate_fidelity_csv(rows: list[dict[str, Any]], out_path: str | Path) -> Path:
    """Write the per-country multivariate-fidelity roll-up (one row per combo) to CSV."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "slug", "strategy", "model", "c2st_auc",
                "mean_abs_delta_v", "frobenius_norm", "mean_grounded_joint_tv",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return out_path
