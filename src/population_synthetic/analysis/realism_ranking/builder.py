"""builder.py -- every cross-combination realism claim, as pure computation.

Takes the loader's :class:`~population_synthetic.analysis.realism_ranking.loader.CompetitorRecord`
list and produces the ranking document plus its flat CSV rows. It touches no path, no
figure, and no config file: paths belong to the CLI edge, rendering to ``charts.py``,
and config values arrive as arguments (config is the single source of truth, read
fail-fast by the caller).

The two axes are kept explicitly apart because their directions are opposite and
conflating them inverts the interpretation:

============  ==========================  =========================  ==================
Axis          Quantity                    Real population's role     Direction
============  ==========================  =========================  ==================
A: validity   impossibility rate          ordinary ranked competitor lower is better
B: coverage   typicality dispersion       the target to match        near zero is better
============  ==========================  =========================  ==================

On Axis A the real population is ranked like everything else, so the question "are
conditionally-chain-sampled personas themselves internally incoherent?" is *asked*
rather than assumed away. On Axis B it is the target: the observed LLM failure mode is
mode collapse, so matching the real spread is the goal and maximising it is not --
``distance_to_scb`` near zero is good, and a large distance is bad in either direction.

Statistical-honesty rules enforced throughout (guide 03):

* every rate carries its denominator, and the denominator is never used as a divisor
  when it is zero;
* every p-value is accompanied by an effect size and the name of the multiple-comparison
  correction applied to its family;
* a test that cannot be computed (a group below two samples, zero variance, a missing
  optional dependency, a non-convergent fit) is recorded in ``skipped_tests`` with a
  reason -- silence downstream reads as "this was tested and found null";
* the bootstrap uses one seeded local generator, and the seed is stamped in provenance;
* the pseudo-replication and one-run-per-combination confounds are emitted as
  machine-readable caveats, not left to prose.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from population_synthetic.analysis.realism_ranking.loader import CompetitorRecord
from population_synthetic.analysis.utils.stats_tests import (
    bootstrap_ci,
    bootstrap_difference_ci,
    dunn_posthoc,
    holm_adjust,
    kruskal_test,
    summarize,
    two_proportion_test,
    variance_equality_test,
)

__all__ = [
    "CAVEATS",
    "CORRECTION",
    "DISPERSION_MEASURES",
    "build_ranking",
    "summary_rows",
    "scb_contrast_rows",
]

#: The multiple-comparison correction applied to every family of tests here. Stated
#: explicitly in the output so a reader never has to infer it from the numbers.
CORRECTION = "holm"

#: The dispersion measures contrasted against the real population on Axis B, in a
#: fixed order (single source for the distance keys).
DISPERSION_MEASURES: tuple[str, ...] = ("variance", "entropy", "tail_coverage")

#: Confounds that survive this analysis and must travel with its numbers.
CAVEATS: tuple[dict[str, str], ...] = (
    {
        "id": "pseudo_replication",
        "text": (
            "Personas within one combination come from a single generation run and share "
            "its prompt, model state and sampling seed, so they are not independent draws "
            "from that combination's population. Treating them as independent narrows every "
            "interval and inflates every test statistic reported here; the p-values are "
            "therefore optimistic, and small differences between combinations should not be "
            "read as established."
        ),
    },
    {
        "id": "single_run_per_combination",
        "text": (
            "Each combination was generated exactly once, so run-level variance is "
            "completely confounded with the model x method cell. A difference attributed "
            "here to a model or a method could equally be one unusually good or bad run of "
            "that cell; separating them needs replicate generation runs, which this design "
            "does not have."
        ),
    },
)


@dataclass(frozen=True)
class _Skip:
    test: str
    reason: str


def _library_versions() -> dict[str, str | None]:
    """Resolved versions of every library whose output lands in this document."""
    versions: dict[str, str | None] = {}
    for name in ("numpy", "scipy", "statsmodels", "scikit_posthocs"):
        try:
            module = __import__(name)
            versions[name] = getattr(module, "__version__", None)
        except ImportError:
            versions[name] = None
    return versions


# --------------------------------------------------------------------------- #
# Axis A -- impossibility ranking (all competitors, the real one included)     #
# --------------------------------------------------------------------------- #


def _axis_a_ranking(
    records: Sequence[CompetitorRecord], *, bootstrap: dict[str, Any]
) -> list[dict[str, Any]]:
    """Rank every competitor by impossibility rate, with a seeded bootstrap CI.

    Ordering is by point rate ascending (lower is better) with the slug as a stable
    tie-break; ties are made explicit through equal ``rank`` values rather than being
    broken arbitrarily. A competitor with no successful persona has no rate and is
    ranked last with ``rate: None`` -- never with an imputed 0, which would read as
    perfect coherence.

    CI overlap is *displayed* by the charts, never asserted as a test: non-overlapping
    intervals imply a difference, but overlapping ones do not imply its absence.
    """
    entries: list[dict[str, Any]] = []
    for record in records:
        indicators = record.impossible_indicators
        ci = bootstrap_ci(
            list(indicators),
            iterations=bootstrap["iterations"],
            ci_level=bootstrap["ci_level"],
            seed=bootstrap["seed"],
        )
        entries.append({
            "slug": record.slug,
            "country": record.country,
            "model": record.model,
            "strategy": record.strategy,
            "is_real_reference": record.is_real_reference,
            "rate": ci["point"],
            "ci_lo": ci["lo"],
            "ci_hi": ci["hi"],
            "ci_level": ci["ci_level"],
            "impossible_count": int(sum(indicators)),
            # The denominator travels with the rate, always.
            "denominator": record.n_personas,
            "n_failed": record.n_failed,
        })

    entries.sort(key=lambda e: (e["rate"] is None, e["rate"] if e["rate"] is not None else 0.0,
                                e["slug"]))
    rank = 0
    previous: float | None = math.nan
    for position, entry in enumerate(entries, start=1):
        if entry["rate"] != previous:
            rank = position
            previous = entry["rate"]
        entry["rank"] = rank
    return entries


# --------------------------------------------------------------------------- #
# Axis A -- pairwise contrasts against the real competitor                     #
# --------------------------------------------------------------------------- #


def _axis_a_contrasts(
    synthetic: Sequence[CompetitorRecord],
    real: CompetitorRecord,
    *,
    bootstrap: dict[str, Any],
) -> list[dict[str, Any]]:
    """Each synthetic competitor vs the real one: rate difference, CI, test, effect.

    Holm-corrected across the whole family of contrasts, because asking the same
    question once per competitor is exactly the situation an uncorrected p-value
    mis-reports. ``diff > 0`` means the synthetic competitor is **less** coherent than
    the real population (a higher impossibility rate).
    """
    real_indicators = list(real.impossible_indicators)
    rows: list[dict[str, Any]] = []
    for record in synthetic:
        indicators = list(record.impossible_indicators)
        test = two_proportion_test(
            int(sum(indicators)), len(indicators),
            int(sum(real_indicators)), len(real_indicators),
        )
        diff_ci = bootstrap_difference_ci(
            indicators, real_indicators,
            iterations=bootstrap["iterations"],
            ci_level=bootstrap["ci_level"],
            seed=bootstrap["seed"],
        )
        rows.append({
            "slug": record.slug,
            "model": record.model,
            "strategy": record.strategy,
            "reference": real.slug,
            "rate": test["p_a"],
            "reference_rate": test["p_b"],
            "diff": test["diff"],
            "diff_ci_lo": diff_ci["lo"],
            "diff_ci_hi": diff_ci["hi"],
            "effect_h": test["h"],
            "effect_magnitude": test["h_magnitude"],
            "p_raw": test["p"],
            "n": len(indicators),
            "reference_n": len(real_indicators),
            "note": test.get("note"),
        })

    testable = [row for row in rows if row["p_raw"] is not None]
    if testable:
        adjusted = holm_adjust([row["p_raw"] for row in testable])
        for row, p_holm in zip(testable, adjusted):
            row["p_holm"] = p_holm
    for row in rows:
        row.setdefault("p_holm", None)
        row["correction"] = CORRECTION
    return rows


# --------------------------------------------------------------------------- #
# Axis B -- typicality dispersion vs the real target                           #
# --------------------------------------------------------------------------- #


def _dispersion_measures(record: CompetitorRecord) -> dict[str, float | None]:
    """This competitor's own dispersion block, keyed by measure.

    Lifted from the per-combination report rather than recomputed: the judging task
    already published these numbers under its own configured ``tail_threshold``, and
    recomputing them here with a possibly-different threshold would silently produce
    two versions of the same statistic.
    """
    return {measure: record.dispersion.get(measure) for measure in DISPERSION_MEASURES}


def _axis_b_contrast(
    synthetic: Sequence[CompetitorRecord],
    real: CompetitorRecord,
    *,
    variance_center: str,
) -> list[dict[str, Any]]:
    """Distance to the real population's dispersion, per measure, plus a Levene test.

    Direction: **near zero is better**. The real population is the target here, not a
    floor to beat -- a combination whose typicality variance is far *below* the real
    one has mode-collapsed, which is the failure this axis exists to catch, so the
    absolute distance is the quantity of interest in both directions.
    """
    real_measures = _dispersion_measures(real)
    real_typicality = list(real.typicality_means)
    rows: list[dict[str, Any]] = []
    for record in synthetic:
        measures = _dispersion_measures(record)
        distance = {
            measure: (
                abs(measures[measure] - real_measures[measure])
                if measures[measure] is not None and real_measures[measure] is not None
                else None
            )
            for measure in DISPERSION_MEASURES
        }
        rows.append({
            "slug": record.slug,
            "model": record.model,
            "strategy": record.strategy,
            "target": real.slug,
            "dispersion": measures,
            "target_dispersion": real_measures,
            "distance_to_scb": distance,
            "variance_equality": variance_equality_test(
                {record.slug: list(record.typicality_means), "real_reference": real_typicality},
                center=variance_center,
            ),
            "n": len(record.typicality_means),
            "target_n": len(real_typicality),
        })
    return rows


# --------------------------------------------------------------------------- #
# Factor significance -- model vs method                                       #
# --------------------------------------------------------------------------- #


def _factor_groups(
    records: Sequence[CompetitorRecord], factor: str
) -> dict[str, list[float]]:
    """Pool per-persona typicality means by *factor* (``model`` or ``strategy``)."""
    groups: dict[str, list[float]] = {}
    for record in records:
        key = getattr(record, factor)
        groups.setdefault(key, []).extend(record.typicality_means)
    return {key: values for key, values in groups.items() if values}


def _factor_significance(
    records: Sequence[CompetitorRecord], factor: str, skips: list[_Skip]
) -> dict[str, Any]:
    """Kruskal-Wallis + Dunn/Holm over per-persona typicality means, grouped by *factor*.

    The real competitor is **held out** by the caller: it is not a model x method cell,
    so including it would compare a factor level against a non-level and unbalance the
    design. It enters the analysis only through the pairwise contrasts above.
    """
    groups = _factor_groups(records, factor)
    usable = {key: values for key, values in groups.items() if len(values) >= 2}
    if len(usable) < 2:
        skips.append(_Skip(
            test=f"kruskal_by_{factor}",
            reason=f"need >=2 {factor} levels with >=2 typicality observations, got {len(usable)}",
        ))
        return {"kruskal": None, "dunn": [], "groups": {}, "correction": CORRECTION}

    return {
        "kruskal": kruskal_test(usable),
        "dunn": dunn_posthoc(usable),
        "groups": {key: summarize(values) for key, values in sorted(usable.items())},
        "correction": CORRECTION,
        "unit": "per-persona mean typicality over the can_exist subset",
    }


def _mixed_logit_can_exist(
    records: Sequence[CompetitorRecord], skips: list[_Skip]
) -> dict[str, Any] | None:
    """Logit-linked mixed model of ``can_exist`` on model + method, clustered by combination.

    One binary observation per persona, fixed effects for the model and the method, and
    a **random intercept by combination** -- the level at which pseudo-replication
    actually happens (every persona of a combination shares one generation run). Fitted
    with ``statsmodels``' variational-Bayes binomial mixed GLM, which is the mixed-model
    form available for a binary outcome.

    Returns ``None`` and records a reason when the optional ``[analysis]`` extra is
    absent, when the design is degenerate (fewer than two levels on either factor, or a
    single combination), or when the fit does not converge. It is never silently
    omitted: a missing test that leaves no trace reads downstream as a test that was run
    and found nothing.
    """
    try:
        import numpy as np
        import pandas as pd
        from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM
    except ImportError as exc:
        skips.append(_Skip(
            test="mixed_logit_can_exist",
            reason=f"optional analysis dependency missing ({exc}); install with: pip install -e .[analysis]",
        ))
        return None

    rows = [
        {
            "can_exist": 0 if row.can_exist_majority is False else 1,
            "model": record.model,
            "method": record.strategy,
            "combination": record.slug,
        }
        for record in records
        for row in record.personas
    ]
    frame = pd.DataFrame(rows)
    if frame.empty:
        skips.append(_Skip(test="mixed_logit_can_exist", reason="no personas to fit"))
        return None
    if frame["model"].nunique() < 2 or frame["method"].nunique() < 2:
        skips.append(_Skip(
            test="mixed_logit_can_exist",
            reason=(
                f"degenerate design: {frame['model'].nunique()} model level(s) x "
                f"{frame['method'].nunique()} method level(s); need >=2 of each"
            ),
        ))
        return None
    if frame["combination"].nunique() < 2:
        skips.append(_Skip(
            test="mixed_logit_can_exist",
            reason="a random intercept by combination needs >=2 combinations",
        ))
        return None
    if frame["can_exist"].nunique() < 2:
        skips.append(_Skip(
            test="mixed_logit_can_exist",
            reason="the outcome is constant (every persona judged the same way); the logit is undefined",
        ))
        return None

    try:
        fit = BinomialBayesMixedGLM.from_formula(
            "can_exist ~ C(model) + C(method)", {"combination": "0 + C(combination)"}, frame,
        ).fit_vb(verbose=False)
    except Exception as exc:  # noqa: BLE001 - any fit failure is a recorded skip
        skips.append(_Skip(test="mixed_logit_can_exist", reason=f"fit did not converge: {exc}"))
        return None

    params = {
        str(name): float(value)
        for name, value in zip(fit.model.exog_names, np.asarray(fit.fe_mean).ravel())
    }
    sds = {
        str(name): float(value)
        for name, value in zip(fit.model.exog_names, np.asarray(fit.fe_sd).ravel())
    }
    return {
        "method": "BinomialBayesMixedGLM (variational Bayes), logit link",
        "formula": "can_exist ~ C(model) + C(method), random intercept by combination",
        "n_observations": int(frame.shape[0]),
        "n_combinations": int(frame["combination"].nunique()),
        "fixed_effects_mean": params,
        "fixed_effects_sd": sds,
        "interpretation": (
            "Posterior means on the log-odds scale with their posterior SDs. A coefficient "
            "whose interval excludes zero by more than ~2 SD is the mixed-model analogue of "
            "a significant factor level; the random intercept absorbs the run-level "
            "clustering that makes the unclustered tests optimistic."
        ),
    }


# --------------------------------------------------------------------------- #
# Assembly                                                                     #
# --------------------------------------------------------------------------- #


def build_ranking(
    records: Sequence[CompetitorRecord],
    country: str,
    *,
    bootstrap: dict[str, Any],
    variance_center: str,
    skipped_combinations: Sequence[tuple[str, str]] = (),
) -> dict[str, Any]:
    """Assemble one country's complete ranking document.

    *records* must all belong to *country* and must already have passed the loader's
    completeness and homogeneity gates. *bootstrap* is the judge config's block
    (``iterations``/``seed``/``ci_level``), reused verbatim so the intervals here are
    seeded identically to the per-combination ones.
    """
    skips: list[_Skip] = []
    real = next((r for r in records if r.is_real_reference), None)
    synthetic = [r for r in records if not r.is_real_reference]

    ranking = _axis_a_ranking(records, bootstrap=bootstrap)

    if real is None:
        reason = (
            f"real_{country} was not among the consumable combinations, so there is nothing "
            "to contrast against. Judge it with "
            f"scripts/analyze/analyze_persona_realism.py --slug real_{country}."
        )
        skips.append(_Skip(test="axis_a_scb_contrast", reason=reason))
        skips.append(_Skip(test="axis_b_dispersion_contrast", reason=reason))
        contrasts: list[dict[str, Any]] = []
        dispersion_contrast: list[dict[str, Any]] = []
    else:
        contrasts = _axis_a_contrasts(synthetic, real, bootstrap=bootstrap)
        dispersion_contrast = _axis_b_contrast(synthetic, real, variance_center=variance_center)

    # Factor tests run over the synthetic competitors only: the real population is not
    # a model x method cell and would unbalance the design.
    by_model = _factor_significance(synthetic, "model", skips)
    by_method = _factor_significance(synthetic, "strategy", skips)
    mixed = _mixed_logit_can_exist(synthetic, skips)

    provenance = dict(records[0].provenance) if records else {}
    return {
        "process": "realism_ranking",
        "country": country,
        "n_competitors": len(records),
        "n_synthetic": len(synthetic),
        "real_competitor": real.slug if real is not None else None,
        "axis_definitions": {
            "A": {
                "quantity": "impossibility rate (share of internally-contradictory personas)",
                "real_population_role": "ordinary ranked competitor -- no privileged position",
                "direction": "lower is better, for every competitor including the real one",
            },
            "B": {
                "quantity": "typicality dispersion (variance / entropy / tail coverage)",
                "real_population_role": "the target to match",
                "direction": (
                    "distance to the real population near zero is better -- the failure mode "
                    "being guarded against is mode collapse, so a spread far below the real "
                    "one is as bad as one far above it"
                ),
            },
        },
        "axis_a": {
            "ranking": ranking,
            "scb_contrast": contrasts,
            "correction": CORRECTION,
        },
        "axis_b": {
            "dispersion_contrast": dispersion_contrast,
            "measures": list(DISPERSION_MEASURES),
            "variance_center": variance_center,
        },
        "factor_significance": {
            "by_model": by_model,
            "by_method": by_method,
            "mixed_logit_can_exist": mixed,
            "correction": CORRECTION,
            "real_competitor_held_out": True,
        },
        "caveats": [dict(caveat) for caveat in CAVEATS],
        "skipped_combinations": [
            {"slug": slug, "reason": reason} for slug, reason in skipped_combinations
        ],
        "skipped_tests": [{"test": skip.test, "reason": skip.reason} for skip in skips],
        "provenance": {
            "bootstrap_seed": bootstrap["seed"],
            "bootstrap_iterations": bootstrap["iterations"],
            "ci_level": bootstrap["ci_level"],
            "library_versions": _library_versions(),
            "judge_model": provenance.get("judge_model"),
            "prompt_template_sha256": provenance.get("prompt_template_sha256"),
            "n_rounds": provenance.get("n_rounds"),
            "consumed_artifacts": [str(record.report_path) for record in records],
        },
    }


def summary_rows(ranking: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the Axis A ranking into ``realism_summary.csv`` rows (rank order)."""
    by_slug = {row["slug"]: row for row in ranking["axis_b"]["dispersion_contrast"]}
    rows: list[dict[str, Any]] = []
    for entry in ranking["axis_a"]["ranking"]:
        distance = (by_slug.get(entry["slug"], {}).get("distance_to_scb") or {})
        rows.append({
            "rank": entry["rank"],
            "slug": entry["slug"],
            "country": entry["country"],
            "model": entry["model"],
            "strategy": entry["strategy"],
            "is_real_reference": entry["is_real_reference"],
            "impossibility_rate": entry["rate"],
            "ci_lo": entry["ci_lo"],
            "ci_hi": entry["ci_hi"],
            "impossible_count": entry["impossible_count"],
            "denominator": entry["denominator"],
            "n_failed": entry["n_failed"],
            "dist_variance": distance.get("variance"),
            "dist_entropy": distance.get("entropy"),
            "dist_tail_coverage": distance.get("tail_coverage"),
        })
    return rows


def scb_contrast_rows(ranking: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten both axes' contrasts against the real population into CSV rows."""
    dispersion = {row["slug"]: row for row in ranking["axis_b"]["dispersion_contrast"]}
    rows: list[dict[str, Any]] = []
    for contrast in ranking["axis_a"]["scb_contrast"]:
        axis_b = dispersion.get(contrast["slug"], {})
        distance = axis_b.get("distance_to_scb") or {}
        variance_equality = axis_b.get("variance_equality") or {}
        rows.append({
            "slug": contrast["slug"],
            "model": contrast["model"],
            "strategy": contrast["strategy"],
            "reference": contrast["reference"],
            "rate": contrast["rate"],
            "reference_rate": contrast["reference_rate"],
            "rate_diff": contrast["diff"],
            "rate_diff_ci_lo": contrast["diff_ci_lo"],
            "rate_diff_ci_hi": contrast["diff_ci_hi"],
            "effect_h": contrast["effect_h"],
            "effect_magnitude": contrast["effect_magnitude"],
            "p_raw": contrast["p_raw"],
            "p_holm": contrast["p_holm"],
            "correction": contrast["correction"],
            "n": contrast["n"],
            "reference_n": contrast["reference_n"],
            "dist_variance": distance.get("variance"),
            "dist_entropy": distance.get("entropy"),
            "dist_tail_coverage": distance.get("tail_coverage"),
            "variance_equality_stat": variance_equality.get("statistic"),
            "variance_equality_p": variance_equality.get("p"),
        })
    return rows
