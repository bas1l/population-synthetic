"""Shared fixtures for the cross-model performance-comparison tests.

The extract/build core is I/O-free, so most fixtures are plain dicts and
:class:`ComboPerformance` records built by :func:`make_report` / :func:`make_combo`
over a minimal three-attribute scheme.  :func:`build_workspace` materialises the
on-disk layout the loader walks (``mapped/_index.json`` +
``comparison/{slug}/{slug}.json``) under a ``tmp_path``.

The tests inject ``AXIS_IDS`` / ``ATTRIBUTES`` explicitly so they do not depend
on the repository's live axis and mapping config.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from population_synthetic.analysis.model_ranking.loader import ComboPerformance
from population_synthetic.analysis.utils.registry import analysis_output_dir

ATTRIBUTES = ["age_group", "biological_sex", "education_level"]

# (country_ids, strategy_ids, model_ids) registries for decompose_slug.
AXIS_IDS = (["swedish"], ["all_pick", "all_generate_pick"], ["claude_haiku", "gemini_flash"])


def make_report(
    tv_by_attr: dict[str, float],
    *,
    coherence_score: float = 0.9,
    n_synth: int = 100,
    flagged: list[dict[str, Any]] | None = None,
    multivariate: dict[str, Any] | None = None,
    joint_chi_sq: dict[str, float] | None = None,
) -> dict[str, Any]:
    """A minimal comparison-report dict shaped like StatisticalEvaluator.generate_report.

    *multivariate* is added verbatim as the optional top-level ``multivariate``
    block when supplied; omitted entirely otherwise (mirroring pre-change reports).
    """
    marginals = {
        attr: {
            "chi_sq_p": 0.5,
            "kl_divergence": 0.1,
            "tv_distance": tv,
            "max_diff": 0.05,
        }
        for attr, tv in tv_by_attr.items()
    }
    report: dict[str, Any] = {
        "metadata": {
            "generated_at": "2026-07-02T00:00:00+00:00",
            "population_a": {"source": "real", "n": 1000},
            "population_b": {"source": "pipeline", "n": n_synth},
        },
        "marginals": marginals,
        "joint_chi_sq": joint_chi_sq or {},
        "coherence": {
            "score": coherence_score,
            "n_plausible": int(round(coherence_score * n_synth)),
            "n_total": n_synth,
            "flagged": flagged or [],
        },
    }
    if multivariate is not None:
        report["multivariate"] = multivariate
    return report


def make_multivariate(
    *,
    c2st_auc: float = 0.62,
    mean_delta_v: float = 0.11,
    pairs: list[dict[str, Any]] | None = None,
    joint_fidelity_pairs: list[dict[str, Any]] | None = None,
    combination_checks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A minimal ``multivariate`` block matching the evaluator's report shape.

    *joint_fidelity_pairs* / *combination_checks* default to empty blocks (the
    JSON-only degenerate case); pass explicit lists to exercise the grounded
    joint-TV and k-way plausibility table/figure writers.
    """
    if pairs is None:
        pairs = [
            {"attr_x": "age_group", "attr_y": "biological_sex",
             "v_real": 0.30, "v_syn": 0.22, "abs_delta_v": 0.08},
            {"attr_x": "age_group", "attr_y": "education_level",
             "v_real": 0.40, "v_syn": 0.26, "abs_delta_v": 0.14},
            {"attr_x": "biological_sex", "attr_y": "education_level",
             "v_real": 0.15, "v_syn": 0.05, "abs_delta_v": 0.10},
        ]
    return {
        "c2st": {"auc": c2st_auc, "p_value": 0.01, "method": "sklearn", "balanced_n": 100},
        "association": {"pairs": pairs, "mean_abs_delta_v": mean_delta_v, "frobenius_norm": 0.2},
        "joint_fidelity": {"pairs": joint_fidelity_pairs or []},
        "combination_plausibility": {"checks": combination_checks or []},
    }


def make_combo(
    *,
    slug: str,
    strategy: str,
    model: str,
    tv_by_attr: dict[str, float],
    country: str = "swedish",
    coherence_score: float = 0.9,
    n_synth: int = 100,
    c2st_auc: float | None = None,
    mean_delta_v: float | None = None,
) -> ComboPerformance:
    """A ComboPerformance built directly (for builder tests, no filesystem)."""
    return ComboPerformance(
        slug=slug,
        country=country,
        strategy=strategy,
        model=model,
        n_synthetic=n_synth,
        marginals={
            attr: {"chi_sq_p": 0.5, "kl_divergence": 0.1, "tv_distance": tv, "max_diff": 0.05}
            for attr, tv in tv_by_attr.items()
        },
        tv_similarity={attr: 1.0 - tv for attr, tv in tv_by_attr.items() if tv == tv},
        coherence={
            "score": coherence_score,
            "n_plausible": int(round(coherence_score * n_synth)),
            "n_total": n_synth,
            "flagged": [],
        },
        c2st_auc=c2st_auc,
        mean_delta_v=mean_delta_v,
    )


def build_workspace(
    tmp_path: Path,
    entries: list[dict[str, Any]],
) -> Path:
    """Materialise ``mapped/_index.json`` + per-slug comparison reports under *tmp_path*.

    Each entry: ``{"slug", "country", "report" (dict | None), "skipped" (bool, optional)}``.
    ``report=None`` leaves the index entry in place but writes no comparison
    report (the loader's missing-report case); ``skipped=True`` marks the entry
    skipped during mapping. Returns *tmp_path* (the output_base).
    """
    mapped_dir = analysis_output_dir("mapping", tmp_path)
    comparison_dir = analysis_output_dir("fidelity", tmp_path)
    mapped_dir.mkdir(parents=True, exist_ok=True)

    index = []
    for entry in entries:
        slug = entry["slug"]
        skipped = bool(entry.get("skipped"))
        index.append(
            {
                "slug": slug,
                "country": entry["country"],
                "synthetic_file": None if skipped else f"{slug}.json",
                "real_file": f"real_{entry['country']}.json",
                "n": 100,
                "skipped": skipped,
            }
        )
        report = entry.get("report")
        if report is not None and not skipped:
            report_dir = comparison_dir / slug
            report_dir.mkdir(parents=True, exist_ok=True)
            with open(report_dir / f"{slug}.json", "w", encoding="utf-8") as fh:
                json.dump(report, fh)

    with open(mapped_dir / "_index.json", "w", encoding="utf-8") as fh:
        json.dump(index, fh)
    return tmp_path
