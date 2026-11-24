"""typicality_closeness.py -- how close each combination's typicality distribution is to the reference.

The combination-level half of the typicality analysis: **one value per synthetic
combination** (n = the number of present combinations, 58 on the full swedish_02 grid),
saying how close that combination's distribution of judge typicality scores is to the
reference population's, and what drives it -- the model, the strategy, or neither.

The unit of analysis is the combination, never the individual. Individuals of one
combination come from one generation run and are not independent draws, so no test here
treats them as observations; they enter only through the individual-level bootstrap,
which resamples them to put an interval on each combination-level number.

Three outcomes over the ``K`` score levels (``p`` the combination's distribution, ``q``
the reference's):

* **TV similarity** (primary) -- ``1 - 1/2 sum_k |p_k - q_k|``, the same measure the
  attribute-level fidelity score uses (:mod:`~population_synthetic.analysis.utils.distribution_distance`).
  Higher is closer.
* **Cliff's delta** (sensitivity) -- ``P(X > Y) - P(X < Y)`` for ``X`` from the
  combination and ``Y`` from the reference, through the Mann-Whitney identity on the two
  histograms. Zero is closest; the sign says which side the combination sits on.
* **Cramer distance** (sensitivity) -- the L2 distance between the two CDFs over the
  ordered cut points; order-aware where TV is not. Lower is closer.

Everything is computed from the Phase 3 primitives only: the additive two-way
decomposition and its permutation test (:mod:`~population_synthetic.analysis.utils.two_way_decomposition`),
the complete-block tests (:func:`~population_synthetic.analysis.utils.stats_tests.friedman_test`,
:func:`~population_synthetic.analysis.utils.stats_tests.paired_t_pairwise`,
:func:`~population_synthetic.analysis.utils.stats_tests.conover_friedman_pairwise`) and
the resampling (:mod:`~population_synthetic.analysis.utils.histogram_resampling`).

**Every interval comes from one joint bootstrap.** Each replicate resamples the
individuals of every combination within that combination **and** the reference's
individuals once, then recomputes every outcome and every statistic from those
histograms. The reference is shared by every combination-vs-reference outcome, so
redrawing it once per replicate is what carries its sampling error (n = 100 on the live
data) into a statistic computed across combinations.

This module is pure: it takes finished unit-weight rows per population (the caller
decides the histogram basis) and the resolved resampling options, and reads no record,
path or config. The caller passes the groups in its canonical order, because the joint
draw order follows the input order.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from population_synthetic.analysis.utils.distribution_distance import (
    cramer_distance,
    total_variation_similarity,
)
from population_synthetic.analysis.utils.histogram_resampling import (
    joint_bootstrap_histograms,
    reference_self_resampling,
)
from population_synthetic.analysis.utils.stats_tests import (
    cliffs_delta_from_histograms,
    complete_block_matrix,
    conover_friedman_pairwise,
    friedman_test,
    paired_t_pairwise,
    percentile_interval,
    shapiro_wilk_test,
)
from population_synthetic.analysis.utils.two_way_decomposition import (
    additive_two_way_anova,
    additive_two_way_effect_sizes,
    additive_two_way_residuals,
    within_block_permutation_test,
)

__all__ = [
    "CLOSENESS_OPTION_KEYS",
    "CLOSENESS_OUTCOMES",
    "ClosenessGroup",
    "closeness_options",
    "typicality_closeness",
]

#: The two factors of the design, by the name every result is keyed on.
MODEL = "model"
STRATEGY = "strategy"

#: The resampling tunables this block requires from its caller. None has a default here:
#: they are read from config at the CLI edge and passed verbatim, like ``bootstrap``.
CLOSENESS_OPTION_KEYS: tuple[str, ...] = (
    "ci_level",
    "bootstrap_iterations",
    "bootstrap_seed",
    "permutation_iterations",
    "permutation_seed",
    "noise_iterations",
    "noise_seed",
    "noise_quantile",
)


@dataclass(frozen=True)
class ClosenessGroup:
    """One synthetic combination: its coordinates and its individuals' unit-weight rows.

    ``units`` is ``(n, K)``; each row sums to 1 (see
    :mod:`~population_synthetic.analysis.utils.histogram_resampling`).
    """

    slug: str
    model: str
    strategy: str
    units: np.ndarray


@dataclass(frozen=True)
class _Outcome:
    """One closeness outcome: how it is computed from histograms and how it is read.

    ``compute`` takes the combination histograms ``(..., G, K)`` and the reference
    histogram ``(..., K)`` (weights, not yet normalised) and returns ``(..., G)``.
    ``noise_tail`` names which side of the noise distribution bounds it: ``"lower"``
    for a similarity (noise alone pulls it down from 1), ``"upper"`` for a distance, and
    ``"abs_upper"`` for a signed outcome whose noise is centred on zero (the bound is on
    its magnitude).
    """

    role: str
    definition: str
    direction: str
    compute: Callable[[np.ndarray, np.ndarray], np.ndarray]
    noise_tail: str


def _normalised(hist: np.ndarray) -> np.ndarray:
    return hist / hist.sum(axis=-1, keepdims=True)


def _tv_similarity(groups: np.ndarray, reference: np.ndarray) -> np.ndarray:
    return np.asarray(total_variation_similarity(_normalised(groups), _normalised(reference)[..., None, :]))


def _cliffs_delta(groups: np.ndarray, reference: np.ndarray) -> np.ndarray:
    return np.asarray(cliffs_delta_from_histograms(groups, reference[..., None, :]))


def _cramer(groups: np.ndarray, reference: np.ndarray) -> np.ndarray:
    return np.asarray(cramer_distance(_normalised(groups), _normalised(reference)[..., None, :]))


#: The published outcomes, primary first. The ids are the JSON keys and CSV values.
CLOSENESS_OUTCOMES: Mapping[str, _Outcome] = {
    "tv_similarity": _Outcome(
        role="primary",
        definition="1 - 1/2 sum_k |p(k) - q(k)| over the score levels; the attribute-fidelity measure",
        direction="higher is closer; 1 means the two distributions are identical",
        compute=_tv_similarity,
        noise_tail="lower",
    ),
    "cliffs_delta": _Outcome(
        role="sensitivity",
        definition=(
            "P(X > Y) - P(X < Y), X a combination individual's score and Y a reference "
            "individual's, on the two weighted histograms (Mann-Whitney identity)"
        ),
        direction=(
            "zero is closest; positive means the combination's individuals are judged more "
            "typical than the reference's. Location only -- it is not the per-persona-mean "
            "delta of typicality_effects"
        ),
        compute=_cliffs_delta,
        noise_tail="abs_upper",
    ),
    "cramer_distance": _Outcome(
        role="sensitivity",
        definition="sqrt(sum_{c < K-1} (F_p(c) - F_q(c))^2), the L2 distance between the CDFs",
        direction="lower is closer; order-aware (mass moved further costs more)",
        compute=_cramer,
        noise_tail="upper",
    ),
}


def closeness_options(options: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the caller's resolved options, adding nothing (as ``_typicality_options``)."""
    missing = [key for key in CLOSENESS_OPTION_KEYS if key not in options]
    unknown = sorted(set(options) - set(CLOSENESS_OPTION_KEYS))
    if missing or unknown:
        raise ValueError(
            f"Malformed closeness options (missing={missing}, unknown={unknown}); the "
            f"required keys are {list(CLOSENESS_OPTION_KEYS)}. They are read from config at "
            "the CLI edge -- this module holds no defaults for them."
        )
    resolved = {key: options[key] for key in CLOSENESS_OPTION_KEYS}
    for key in ("ci_level", "noise_quantile"):
        if not 0.0 < float(resolved[key]) < 1.0:
            raise ValueError(f"closeness option {key!r} must lie strictly in (0, 1), got {resolved[key]!r}")
    return resolved


def _noise_summary(values: np.ndarray, tail: str, quantile: float) -> dict[str, float]:
    """Mean and the noise bound of one outcome's reference-vs-itself replicates."""
    if tail == "abs_upper":
        magnitude = np.abs(values)
        return {"mean": float(values.mean()), "mean_abs": float(magnitude.mean()),
                "bound": float(np.quantile(magnitude, quantile))}
    level = quantile if tail == "upper" else 1.0 - quantile
    return {"mean": float(values.mean()), "bound": float(np.quantile(values, level))}


def _noise_baseline(
    reference_units: np.ndarray, sizes: Sequence[int], opts: Mapping[str, Any]
) -> dict[int, dict[str, dict[str, float]]]:
    """Per sample size, each outcome's value between two draws of the reference itself.

    One call per size with the **same** seed, so each size's baseline depends only on the
    reference, that size and the seed -- never on which other sizes are present.
    """
    baseline: dict[int, dict[str, dict[str, float]]] = {}
    for n in sorted(set(int(size) for size in sizes)):
        sample, reference = reference_self_resampling(
            reference_units, n_sample=n,
            iterations=opts["noise_iterations"], seed=opts["noise_seed"],
        )
        baseline[n] = {
            name: _noise_summary(
                spec.compute(sample[:, None, :], reference)[:, 0],
                spec.noise_tail, float(opts["noise_quantile"]),
            )
            for name, spec in CLOSENESS_OUTCOMES.items()
        }
    return baseline


def _interval(replicates: np.ndarray, ci_level: float) -> dict[str, float | None]:
    lo, hi = percentile_interval(replicates, ci_level=ci_level)
    return {"lo": lo, "hi": hi}


def _decomposition(
    values: np.ndarray,
    replicates: np.ndarray,
    factors: Mapping[str, Sequence[str]],
    *,
    ci_level: float,
    outcome: str,
    skips: list[tuple[str, str]],
) -> dict[str, Any]:
    """The additive model + strategy decomposition, its residual check and its intervals.

    The point values are :func:`additive_two_way_anova`'s; the intervals are percentile
    intervals of the same statistics over the joint-bootstrap replicates. A replicate on
    which an effect size is undefined makes the interval undefined -- recorded as a skip,
    never folded in.
    """
    anova = additive_two_way_anova(values, factors)
    if anova["df_residual"] > 0:
        residual_normality = shapiro_wilk_test(additive_two_way_residuals(values, factors))
    else:
        residual_normality = {"W": None, "p": None, "n": len(values),
                              "note": "no residual degrees of freedom; there is no residual to test"}
    strategy, model = anova["factors"][STRATEGY], anova["factors"][MODEL]
    derived: dict[str, Any] = {
        "partial_omega_sq_strategy_minus_model": {
            "point": (None if strategy["partial_omega_sq"] is None or model["partial_omega_sq"] is None
                      else strategy["partial_omega_sq"] - model["partial_omega_sq"]),
        },
        "ss_ratio_strategy_over_model": {
            "point": None if not model["ss"] else strategy["ss"] / model["ss"],
        },
    }
    intervals: dict[str, Any] | None = None
    try:
        reps = additive_two_way_effect_sizes(replicates, factors)
        with np.errstate(divide="ignore", invalid="ignore"):
            omega_diff = reps["factors"][STRATEGY]["partial_omega_sq"] - reps["factors"][MODEL]["partial_omega_sq"]
            ss_ratio = reps["factors"][STRATEGY]["ss"] / reps["factors"][MODEL]["ss"]
        intervals = {
            "factors": {
                name: {stat: _interval(reps["factors"][name][stat], ci_level)
                       for stat in ("share", "F", "partial_eta_sq", "partial_omega_sq", "omega_sq")}
                for name in (STRATEGY, MODEL)
            },
            "share_residual": _interval(reps["share_residual"], ci_level),
            "share_overlap": _interval(reps["share_overlap"], ci_level),
        }
    except ValueError as exc:
        skips.append((
            f"typicality_closeness[{outcome}].decomposition_intervals",
            f"the bootstrap intervals of the decomposition are undefined: {exc}",
        ))
        omega_diff = ss_ratio = None
    for key, reps_of in (("partial_omega_sq_strategy_minus_model", omega_diff),
                         ("ss_ratio_strategy_over_model", ss_ratio)):
        try:
            derived[key].update({"lo": None, "hi": None} if reps_of is None else _interval(reps_of, ci_level))
        except ValueError as exc:
            # e.g. a replicate whose model SS is exactly zero gives an infinite ratio
            skips.append((f"typicality_closeness[{outcome}].{key}", f"interval undefined: {exc}"))
            derived[key].update({"lo": None, "hi": None})
    return {
        "anova": anova,
        "residual_normality": residual_normality,
        "intervals": intervals,
        "derived": derived,
        "ci_level": ci_level,
    }


def _kendalls_w_interval(
    replicates: np.ndarray, index: np.ndarray, *, transpose: bool, ci_level: float
) -> dict[str, Any]:
    """Percentile interval of Kendall's W recomputed on every bootstrap replicate."""
    ws: list[float] = []
    for replicate in replicates:
        matrix = replicate[index]
        result = friedman_test(matrix.T if transpose else matrix)
        if result["kendalls_w"] is None:
            return {"lo": None, "hi": None,
                    "note": f"W undefined on a bootstrap replicate ({result.get('note')}); no interval"}
        ws.append(result["kendalls_w"])
    return _interval(np.asarray(ws), ci_level)


def _complete_blocks(
    values: np.ndarray,
    replicates: np.ndarray,
    groups: Sequence[ClosenessGroup],
    *,
    models: Sequence[str],
    strategies: Sequence[str],
    ci_level: float,
    outcome: str,
    skips: list[tuple[str, str]],
) -> dict[str, Any]:
    """Friedman + Kendall's W both ways, and the strategy / model post hocs, on complete blocks.

    A model is a complete block when it has a combination under every strategy; the
    others are dropped (listed), never imputed. The strategy direction takes the complete
    models as blocks; the model direction takes the strategies as blocks over the same
    complete models.
    """
    column = {(g.model, g.strategy): i for i, g in enumerate(groups)}
    cells = {m: {s: (float(values[column[(m, s)]]) if (m, s) in column else None) for s in strategies}
             for m in models}
    matrix, complete, dropped = complete_block_matrix(cells, models, strategies)
    out: dict[str, Any] = {"complete_models": complete, "dropped_models": dropped,
                           "strategies": list(strategies)}
    if len(complete) < 2:
        skips.append((f"typicality_closeness[{outcome}].complete_blocks",
                      f"need >= 2 models with every strategy present, got {len(complete)}"))
        out.update({"strategy": None, "model": None, "strategy_pairs": None, "model_pairs": None})
        return out

    index = np.array([[column[(m, s)] for s in strategies] for m in complete])
    out["strategy"] = {
        "friedman": friedman_test(matrix),
        "kendalls_w_ci": _kendalls_w_interval(replicates, index, transpose=False, ci_level=ci_level),
        "blocks": "complete models",
    }
    out["model"] = {
        "friedman": friedman_test(matrix.T),
        "kendalls_w_ci": _kendalls_w_interval(replicates, index, transpose=True, ci_level=ci_level),
        "blocks": "strategies",
    }
    paired = paired_t_pairwise(matrix, labels=list(strategies), confidence_level=ci_level)
    out["strategy_pairs"] = {
        "strategy_summary": {
            s: {"mean": float(matrix[:, j].mean()),
                "sd": float(matrix[:, j].std(ddof=1)) if matrix.shape[0] > 1 else None,
                "n": int(matrix.shape[0])}
            for j, s in enumerate(strategies)
        },
        "paired_t": paired,
        "difference_normality": {
            f"{strategies[i]}|{strategies[j]}": shapiro_wilk_test(matrix[:, j] - matrix[:, i])
            for i in range(len(strategies)) for j in range(i + 1, len(strategies))
        },
        "conover": _conover(matrix, strategies, outcome=outcome, factor=STRATEGY, skips=skips),
    }
    out["model_pairs"] = {
        "conover": _conover(matrix.T, complete, outcome=outcome, factor=MODEL, skips=skips),
    }
    return out


def _conover(
    matrix: np.ndarray, labels: Sequence[str], *, outcome: str, factor: str, skips: list[tuple[str, str]]
) -> dict[str, Any] | None:
    try:
        return conover_friedman_pairwise(matrix, labels=list(labels))
    except ImportError as exc:
        skips.append((f"typicality_closeness[{outcome}].conover_{factor}", str(exc)))
        return None


def typicality_closeness(
    groups: Sequence[ClosenessGroup],
    *,
    reference_slug: str,
    reference_units: np.ndarray,
    models: Sequence[str],
    strategies: Sequence[str],
    options: Mapping[str, Any],
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """Build the closeness block over *groups* against one reference population.

    *groups* are the present synthetic combinations (withdrawn cells and combinations
    without a scored individual are not passed -- absent, never zero), in the caller's
    canonical order; that order fixes the joint draw order and the row order. *models*
    and *strategies* are the published level orders of the two factors, and every
    group's coordinates must be among them. *options* is the resolved
    :data:`CLOSENESS_OPTION_KEYS` bundle.

    Returns ``(block, skips)``; *skips* lists ``(test, reason)`` for every statistic that
    could not be computed, for the caller's ``skipped_tests``.

    Raises ``ValueError`` on a malformed option bundle, an empty group list, a group whose
    coordinates are not among the given levels, or duplicate coordinates.
    """
    opts = closeness_options(options)
    ci_level = float(opts["ci_level"])
    if not groups:
        raise ValueError("typicality_closeness needs at least one synthetic combination")
    seen: set[tuple[str, str]] = set()
    for group in groups:
        if group.model not in models or group.strategy not in strategies:
            raise ValueError(
                f"Combination {group.slug!r} ({group.model!r}, {group.strategy!r}) is not on the "
                f"given factor levels (models={list(models)}, strategies={list(strategies)})."
            )
        if (group.model, group.strategy) in seen:
            raise ValueError(f"Two combinations claim ({group.model!r}, {group.strategy!r}).")
        seen.add((group.model, group.strategy))
    present_models = [m for m in models if any(g.model == m for g in groups)]
    present_strategies = [s for s in strategies if any(g.strategy == s for g in groups)]

    skips: list[tuple[str, str]] = []
    reference_units = np.asarray(reference_units, dtype=float)
    observed_groups = np.stack([np.asarray(g.units, dtype=float).sum(axis=0) for g in groups])
    observed_reference = reference_units.sum(axis=0)
    boot_groups, boot_reference = joint_bootstrap_histograms(
        [g.units for g in groups], reference_units,
        iterations=opts["bootstrap_iterations"], seed=opts["bootstrap_seed"],
    )
    sizes = [int(np.asarray(g.units).shape[0]) for g in groups]
    n_reference = int(reference_units.shape[0])
    noise = _noise_baseline(reference_units, [*sizes, n_reference], opts)

    observed = {name: spec.compute(observed_groups, observed_reference) for name, spec in CLOSENESS_OUTCOMES.items()}
    replicated = {name: spec.compute(boot_groups, boot_reference) for name, spec in CLOSENESS_OUTCOMES.items()}

    combinations: list[dict[str, Any]] = []
    for g_index, (group, n) in enumerate(zip(groups, sizes)):
        row: dict[str, Any] = {"slug": group.slug, "model": group.model, "strategy": group.strategy, "n": n}
        for name in CLOSENESS_OUTCOMES:
            lo, hi = percentile_interval(replicated[name][:, g_index], ci_level=ci_level)
            row[name] = {
                "value": float(observed[name][g_index]), "ci_lo": lo, "ci_hi": hi,
                "noise_mean": noise[n][name]["mean"], "noise_bound": noise[n][name]["bound"],
            }
            if "mean_abs" in noise[n][name]:
                row[name]["noise_mean_abs"] = noise[n][name]["mean_abs"]
        combinations.append(row)

    factors = {MODEL: [g.model for g in groups], STRATEGY: [g.strategy for g in groups]}
    by_outcome: dict[str, Any] = {}
    for name in CLOSENESS_OUTCOMES:
        values, reps = observed[name], replicated[name]
        by_outcome[name] = {
            "decomposition": _decomposition(values, reps, factors, ci_level=ci_level, outcome=name, skips=skips),
            "permutation": {
                factor: within_block_permutation_test(
                    values, factors, factor=factor,
                    iterations=opts["permutation_iterations"], seed=opts["permutation_seed"],
                )
                for factor in (STRATEGY, MODEL)
            },
            "complete_blocks": _complete_blocks(
                values, reps, groups, models=present_models, strategies=present_strategies,
                ci_level=ci_level, outcome=name, skips=skips,
            ),
        }

    block = {
        "unit": (
            "the combination: one value per present synthetic combination, the reference held "
            "out. Individuals are never test units here -- one generation run per combination "
            "makes them non-independent -- and enter only through the bootstrap"
        ),
        "n_combinations": len(groups),
        "reference_slug": reference_slug,
        "reference_n": n_reference,
        "models": present_models,
        "strategies": present_strategies,
        "outcomes": {
            name: {"role": spec.role, "definition": spec.definition, "direction": spec.direction}
            for name, spec in CLOSENESS_OUTCOMES.items()
        },
        "resampling": {
            **opts,
            "bootstrap_method": (
                "joint individual-level percentile bootstrap: every replicate resamples each "
                "combination within itself and the reference once, and every interval in this "
                "block is taken over the same replicates"
            ),
            "noise_method": (
                "reference self-resampling: n individuals drawn from the reference against an "
                "independent redraw of the reference at its own n, per distinct n"
            ),
            "noise_bound": (
                "tv_similarity: the (1 - noise_quantile) quantile (noise alone pulls similarity "
                "down); cramer_distance: the noise_quantile quantile; cliffs_delta: the "
                "noise_quantile quantile of |delta| (its noise is centred on zero)"
            ),
        },
        "noise_baseline": {
            "headline_n": n_reference,
            "by_n": [{"n": n, **outcomes} for n, outcomes in sorted(noise.items())],
        },
        "combinations": combinations,
        "by_outcome": by_outcome,
    }
    return block, skips
