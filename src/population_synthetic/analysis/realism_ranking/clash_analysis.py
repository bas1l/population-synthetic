"""clash_analysis.py -- each combination's worst-clash states against the reference population.

The clash half of the individual-level analysis: every judged individual is counted once,
in one of four exclusive states -- no clash, or a worst clash of rank 1, 2 or 3 (S1-S3) --
and each population is compared with the reference on that distribution. The state of an
individual is its worst-clash category (``worst_clash_split``, S3 split by stage 2) read
through the ``clash_analysis.states`` map of ``worst_clash_split.yaml``; a category listed
under ``clash_analysis.excluded`` (the SCB category limitation C, and pipeline errors) takes the individual out
of the analysis altogether, from every numerator **and** every denominator, and the count
it removed is published per competitor so a reader always sees the denominator.

Published per population:

* the rates of ``clash_analysis.rates`` (any clash, a worst clash of rank 2 or 3, a rank-3
  clash), each with its Clopper-Pearson interval;
* per synthetic combination and rate, the difference from the reference with a joint
  bootstrap interval, the two-sided Fisher exact p and its Holm correction over the
  combinations, and a verdict (lower / higher / indistinguishable at ``alpha``);
* the TV similarity of its four-state distribution to the reference's, with a bootstrap
  interval and the reference self-resampling baseline at its own n;

and across combinations: the rates pooled per strategy and per model with their difference
from the reference, the additive model + strategy decomposition of each
``decomposed_rates`` difference (type II shares, F, within-block permutation p, share
intervals), and the attribute pairs of the rank-3 clashes counted per individual.

The unit of every test across combinations is the combination; individuals enter only
through the bootstrap and the per-combination Fisher tests (the pseudo-replication caveat
of the ranking applies to the latter). Every interval is taken over one set of joint
bootstrap replicates, each resampling every combination within itself and the reference
once, under the ``typicality_closeness`` resampling settings.

Pure: takes finished one-hot unit rows and the validated options; reads no record, path or
config.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from population_synthetic.analysis.realism_ranking.typicality_closeness import closeness_options
from population_synthetic.analysis.utils.histogram_resampling import (
    joint_bootstrap_histograms,
    reference_self_resampling,
)
from population_synthetic.analysis.utils.stats_tests import (
    clopper_pearson_interval,
    fisher_exact_test,
    holm_adjust,
    percentile_interval,
)
from population_synthetic.analysis.utils.two_way_decomposition import (
    additive_two_way_anova,
    additive_two_way_effect_sizes,
    within_block_permutation_test,
)

__all__ = [
    "CLASH_STATES",
    "ClashGroup",
    "clash_analysis",
    "clash_analysis_options",
]

#: The four worst-clash states of the analysis, least to most severe: the rank ladder
#: itself (structural, like the severity levels), whose members are config's.
CLASH_STATES: tuple[str, ...] = ("none", "S1", "S2", "S3")

MODEL = "model"
STRATEGY = "strategy"

_OPTION_KEYS: tuple[str, ...] = ("excluded", "states", "rates", "decomposed_rates", "alpha")


def clash_analysis_options(spec: Any, categories: Sequence[str]) -> dict[str, Any]:
    """Validate the ``clash_analysis`` bundle of ``worst_clash_split.yaml`` (fail-fast).

    *categories* are the split's declared worst-clash categories. ``excluded`` plus the
    members of ``states`` must list every one of them exactly once; ``states`` must be
    exactly :data:`CLASH_STATES`, with ``none``/``S1``/``S2`` each holding only itself;
    every rate lists distinct states; ``decomposed_rates`` names declared rates; ``alpha``
    lies in (0, 1). Nothing is defaulted.
    """
    if not isinstance(spec, Mapping):
        raise ValueError(f"clash_analysis config must be a mapping, got {type(spec).__name__}")
    missing = [k for k in _OPTION_KEYS if k not in spec]
    unknown = sorted(set(spec) - set(_OPTION_KEYS))
    if missing or unknown:
        raise ValueError(f"clash_analysis config: missing {missing}, unknown {unknown}; "
                         f"the keys are {list(_OPTION_KEYS)}")
    excluded = [str(c) for c in (spec["excluded"] or ())]
    states_spec = spec["states"]
    if not isinstance(states_spec, Mapping) or list(states_spec) != list(CLASH_STATES):
        raise ValueError(f"clash_analysis.states must map exactly {list(CLASH_STATES)} in that order, "
                         f"got {states_spec!r}")
    states = {state: [str(c) for c in (states_spec[state] or ())] for state in CLASH_STATES}
    for state in CLASH_STATES[:3]:
        if states[state] != [state]:
            raise ValueError(f"clash_analysis.states.{state} must hold only {state!r}, got {states[state]}")
    if not states["S3"]:
        raise ValueError("clash_analysis.states.S3 must hold at least one category")
    listed = excluded + [c for members in states.values() for c in members]
    if sorted(listed) != sorted(categories) or len(set(listed)) != len(listed):
        raise ValueError(
            "clash_analysis.excluded and clash_analysis.states must together list every worst-clash "
            f"category exactly once; categories {sorted(categories)}, listed {sorted(listed)}"
        )
    rates_spec = spec["rates"]
    if not isinstance(rates_spec, Mapping) or not rates_spec:
        raise ValueError(f"clash_analysis.rates must be a non-empty mapping, got {rates_spec!r}")
    rates: dict[str, list[str]] = {}
    for name, members in rates_spec.items():
        members = [str(s) for s in (members or ())]
        if not members or len(set(members)) != len(members) or set(members) - set(CLASH_STATES):
            raise ValueError(f"clash_analysis.rates.{name} must list distinct states of {list(CLASH_STATES)}, "
                             f"got {members}")
        rates[str(name)] = members
    decomposed = [str(r) for r in (spec["decomposed_rates"] or ())]
    if set(decomposed) - set(rates) or len(set(decomposed)) != len(decomposed):
        raise ValueError(f"clash_analysis.decomposed_rates must name distinct declared rates {list(rates)}, "
                         f"got {decomposed}")
    alpha = spec["alpha"]
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not 0.0 < float(alpha) < 1.0:
        raise ValueError(f"clash_analysis.alpha must lie strictly in (0, 1), got {alpha!r}")
    return {"excluded": excluded, "states": states, "rates": rates,
            "decomposed_rates": decomposed, "alpha": float(alpha)}


@dataclass(frozen=True)
class ClashGroup:
    """One population of the analysis: its coordinates, its analysed individuals and its exclusions.

    ``units`` is ``(n, 4)``, one one-hot row per analysed individual over
    :data:`CLASH_STATES`; ``n_excluded`` the individuals the excluded categories removed;
    ``rank3_pairs`` the sorted attribute pairs of its rank-3 clashes, each counted once
    per individual holding it.
    """

    slug: str
    model: str
    strategy: str
    units: np.ndarray
    n_excluded: int
    rank3_pairs: Mapping[tuple[str, str], int]


def _rate_matrix(rates: Mapping[str, Sequence[str]]) -> np.ndarray:
    """``(4, R)`` 0/1 matrix: which states each rate counts."""
    return np.array([[1.0 if state in members else 0.0 for members in rates.values()]
                     for state in CLASH_STATES])


def _interval(replicates: np.ndarray, ci_level: float) -> dict[str, float]:
    lo, hi = percentile_interval(replicates, ci_level=ci_level)
    return {"ci_lo": lo, "ci_hi": hi}


def _tv_similarity(hist: np.ndarray, reference: np.ndarray) -> np.ndarray:
    p = hist / hist.sum(axis=-1, keepdims=True)
    q = reference / reference.sum(axis=-1, keepdims=True)
    return 1.0 - 0.5 * np.abs(p - q[..., None, :]).sum(axis=-1)


def _verdict(diff: float, p_holm: float, alpha: float) -> str:
    if p_holm >= alpha:
        return "indistinguishable"
    return "lower" if diff < 0 else "higher"


def _pooled(
    groups: Sequence[ClashGroup],
    observed: np.ndarray,
    boot: np.ndarray,
    reference_rates: np.ndarray,
    boot_reference_rates: np.ndarray,
    rate_names: Sequence[str],
    weights: np.ndarray,
    *,
    factor: str,
    levels: Sequence[str],
    ci_level: float,
) -> list[dict[str, Any]]:
    """Each level's rates over its combinations' analysed individuals, minus the reference's."""
    out = []
    for level in levels:
        idx = [i for i, g in enumerate(groups) if getattr(g, factor) == level]
        hist = observed[idx].sum(axis=0)
        n = int(hist.sum())
        counts = hist @ weights
        boot_hist = boot[:, idx, :].sum(axis=1)
        boot_rates = (boot_hist @ weights) / n
        row: dict[str, Any] = {"level": level, "n_combinations": len(idx), "n": n,
                               "n_excluded": int(sum(groups[i].n_excluded for i in idx))}
        for r, name in enumerate(rate_names):
            diff_reps = boot_rates[:, r] - boot_reference_rates[:, r]
            row[name] = {"count": int(round(counts[r])), "rate": float(counts[r] / n),
                         "diff": float(counts[r] / n - reference_rates[r]),
                         **{f"diff_{k}": v for k, v in _interval(diff_reps, ci_level).items()}}
        out.append(row)
    return out


def _decomposition(
    values: np.ndarray,
    replicates: np.ndarray,
    factors: Mapping[str, Sequence[str]],
    *,
    opts: Mapping[str, Any],
    rate: str,
    skips: list[tuple[str, str]],
) -> dict[str, Any]:
    anova = additive_two_way_anova(values, factors)
    intervals: dict[str, Any] | None
    try:
        reps = additive_two_way_effect_sizes(replicates, factors)
        intervals = {name: {"share": _interval(reps["factors"][name]["share"], float(opts["ci_level"]))}
                     for name in (STRATEGY, MODEL)}
    except ValueError as exc:
        skips.append((f"clash_analysis[{rate}].decomposition_intervals",
                      f"the bootstrap intervals of the decomposition are undefined: {exc}"))
        intervals = None
    return {
        "outcome": f"{rate} rate of the combination minus the reference's",
        "anova": anova,
        "permutation": {
            factor: within_block_permutation_test(
                values, factors, factor=factor,
                iterations=opts["permutation_iterations"], seed=opts["permutation_seed"],
            )
            for factor in (STRATEGY, MODEL)
        },
        "intervals": intervals,
    }


def _counts(units: np.ndarray) -> dict[str, int]:
    hist = units.sum(axis=0)
    return {state: int(round(hist[i])) for i, state in enumerate(CLASH_STATES)}


def clash_analysis(
    groups: Sequence[ClashGroup],
    reference: ClashGroup,
    *,
    models: Sequence[str],
    strategies: Sequence[str],
    spec: Mapping[str, Any],
    resampling: Mapping[str, Any],
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """Build the clash-analysis block over *groups* against *reference*.

    *groups* are the present synthetic combinations in the caller's canonical order (it
    fixes the joint draw order and the row order); *models* / *strategies* the published
    level orders. *spec* is the validated :func:`clash_analysis_options` bundle and
    *resampling* the ``typicality_closeness`` resampling bundle. Returns ``(block, skips)``.

    Raises ``ValueError`` when there is no group, a population has no analysed
    individual, a unit row is not one-hot over the four states, or coordinates repeat or
    fall outside the given levels.
    """
    opts = closeness_options(resampling)
    ci_level = float(opts["ci_level"])
    alpha = float(spec["alpha"])
    if not groups:
        raise ValueError("clash_analysis needs at least one synthetic combination")
    seen: set[tuple[str, str]] = set()
    for group in [*groups, reference]:
        units = np.asarray(group.units, dtype=float)
        if units.ndim != 2 or units.shape[1] != len(CLASH_STATES) or units.shape[0] == 0:
            raise ValueError(f"clash_analysis: {group.slug!r} needs a non-empty (n, {len(CLASH_STATES)}) "
                             f"unit array, got shape {units.shape}")
        if not np.array_equal(units.sum(axis=1), np.ones(units.shape[0])) or not np.isin(units, (0.0, 1.0)).all():
            raise ValueError(f"clash_analysis: {group.slug!r} has a unit row that is not one-hot")
    for group in groups:
        if group.model not in models or group.strategy not in strategies:
            raise ValueError(f"Combination {group.slug!r} ({group.model!r}, {group.strategy!r}) is not on the "
                             f"given factor levels (models={list(models)}, strategies={list(strategies)}).")
        if (group.model, group.strategy) in seen:
            raise ValueError(f"Two combinations claim ({group.model!r}, {group.strategy!r}).")
        seen.add((group.model, group.strategy))

    rate_names = list(spec["rates"])
    weights = _rate_matrix(spec["rates"])
    skips: list[tuple[str, str]] = []
    ref_units = np.asarray(reference.units, dtype=float)
    observed = np.stack([np.asarray(g.units, dtype=float).sum(axis=0) for g in groups])
    obs_ref = ref_units.sum(axis=0)
    sizes = observed.sum(axis=1)
    n_ref = int(obs_ref.sum())
    boot, boot_ref = joint_bootstrap_histograms(
        [g.units for g in groups], ref_units,
        iterations=opts["bootstrap_iterations"], seed=opts["bootstrap_seed"],
    )
    ref_counts = obs_ref @ weights
    ref_rates = ref_counts / n_ref
    boot_ref_rates = (boot_ref @ weights) / n_ref
    counts = observed @ weights
    rates = counts / sizes[:, None]
    boot_rates = (boot @ weights) / sizes[None, :, None]
    diff = rates - ref_rates[None, :]
    boot_diff = boot_rates - boot_ref_rates[:, None, :]
    tv = _tv_similarity(observed, obs_ref)
    boot_tv = _tv_similarity(boot, boot_ref)

    noise: dict[int, dict[str, float]] = {}
    for n in sorted({*(int(s) for s in sizes), n_ref}):
        sample, again = reference_self_resampling(ref_units, n_sample=n, iterations=opts["noise_iterations"],
                                                  seed=opts["noise_seed"])
        values = _tv_similarity(sample[:, None, :], again)[:, 0]
        noise[n] = {"mean": float(values.mean()),
                    "bound": float(np.quantile(values, 1.0 - float(opts["noise_quantile"])))}

    p_raw = {name: [fisher_exact_test(int(round(counts[g, r])), int(sizes[g]), int(round(ref_counts[r])), n_ref)["p"]
                    for g in range(len(groups))]
             for r, name in enumerate(rate_names)}
    p_holm = {name: holm_adjust(list(ps)) for name, ps in p_raw.items()}

    def _rates_of(count_row: np.ndarray, n: int) -> dict[str, Any]:
        out = {}
        for r, name in enumerate(rate_names):
            k = int(round(count_row[r]))
            lo, hi = clopper_pearson_interval(k, n, ci_level=ci_level)
            out[name] = {"count": k, "n": n, "rate": k / n, "ci_lo": lo, "ci_hi": hi}
        return out

    competitors: list[dict[str, Any]] = []
    for g, group in enumerate(groups):
        n = int(sizes[g])
        vs_reference = {}
        for r, name in enumerate(rate_names):
            vs_reference[name] = {
                "diff": float(diff[g, r]),
                **{f"diff_{k}": v for k, v in _interval(boot_diff[:, g, r], ci_level).items()},
                "p_fisher": p_raw[name][g], "p_holm": p_holm[name][g],
                "verdict": _verdict(float(diff[g, r]), p_holm[name][g], alpha),
            }
        competitors.append({
            "slug": group.slug, "model": group.model, "strategy": group.strategy, "is_real_reference": False,
            "n_judged": n + group.n_excluded, "n_excluded": group.n_excluded, "n": n,
            "counts": _counts(np.asarray(group.units, dtype=float)),
            "rates": _rates_of(counts[g], n),
            "vs_reference": vs_reference,
            "tv_similarity": {"value": float(tv[g]), **_interval(boot_tv[:, g], ci_level),
                              "noise_mean": noise[n]["mean"], "noise_bound": noise[n]["bound"]},
        })
    competitors.append({
        "slug": reference.slug, "model": reference.model, "strategy": reference.strategy, "is_real_reference": True,
        "n_judged": n_ref + reference.n_excluded, "n_excluded": reference.n_excluded, "n": n_ref,
        "counts": _counts(ref_units), "rates": _rates_of(ref_counts, n_ref),
        "vs_reference": None, "tv_similarity": None,
    })

    holm_summary = {
        name: {verdict: sum(1 for row in competitors[:-1] if row["vs_reference"][name]["verdict"] == verdict)
               for verdict in ("lower", "higher", "indistinguishable")}
        for name in rate_names
    }
    total_hist = observed.sum(axis=0)
    totals = {
        "n_combinations": len(groups),
        "n_judged": int(sizes.sum()) + sum(g.n_excluded for g in groups),
        "n_excluded": sum(g.n_excluded for g in groups),
        "n_combinations_with_exclusions": sum(1 for g in groups if g.n_excluded),
        "n": int(sizes.sum()),
        "counts": {state: int(round(total_hist[i])) for i, state in enumerate(CLASH_STATES)},
        "rates": {name: {"count": int(round(c)), "rate": float(c / sizes.sum())}
                  for name, c in zip(rate_names, total_hist @ weights)},
    }

    present_models = [m for m in models if any(g.model == m for g in groups)]
    present_strategies = [s for s in strategies if any(g.strategy == s for g in groups)]
    pooled = {
        factor: _pooled(groups, observed, boot, ref_rates, boot_ref_rates, rate_names, weights,
                        factor=factor, levels=levels, ci_level=ci_level)
        for factor, levels in ((STRATEGY, present_strategies), (MODEL, present_models))
    }

    factors = {MODEL: [g.model for g in groups], STRATEGY: [g.strategy for g in groups]}
    decomposition = {
        name: _decomposition(diff[:, rate_names.index(name)], boot_diff[:, :, rate_names.index(name)], factors,
                             opts=opts, rate=name, skips=skips)
        for name in spec["decomposed_rates"]
    }

    pair_counts: dict[tuple[str, str], int] = {}
    for group in groups:
        for pair, k in group.rank3_pairs.items():
            pair_counts[pair] = pair_counts.get(pair, 0) + int(k)
    rank3_pairs = [{"attr_a": a, "attr_b": b, "n_individuals": k}
                   for (a, b), k in sorted(pair_counts.items(), key=lambda item: (-item[1], item[0]))]

    block = {
        "unit": (
            "the individual, counted once in the state of its worst clash; the combination is the unit "
            "of every test across combinations (the decomposition and its permutation tests)"
        ),
        "states": list(CLASH_STATES),
        "state_categories": {state: list(members) for state, members in spec["states"].items()},
        "excluded_categories": list(spec["excluded"]),
        "excluded_note": (
            "an individual whose worst-clash category is listed in excluded_categories is removed from "
            "every numerator and denominator of this block; n_excluded counts them per competitor"
        ),
        "rates": {name: list(members) for name, members in spec["rates"].items()},
        "decomposed_rates": list(spec["decomposed_rates"]),
        "alpha": alpha,
        "tests": {
            "per_combination": "two-sided Fisher exact test of each rate against the reference, Holm-corrected "
                               "over the combinations of each rate",
            "rate_intervals": "Clopper-Pearson",
            "decomposition": "additive two-way model + strategy on the rate difference, type II; "
                             "within-block permutation of the F statistic",
        },
        "reference_slug": reference.slug,
        "reference_n": n_ref,
        "models": present_models,
        "strategies": present_strategies,
        "resampling": {**opts,
                       "bootstrap_method": "joint individual-level percentile bootstrap (each combination "
                                           "within itself, the reference once per replicate)",
                       "noise_method": "TV similarity of n individuals drawn from the reference against an "
                                       "independent redraw of the reference at its own n, per distinct n; "
                                       "bound = the (1 - noise_quantile) quantile"},
        "noise_baseline": {"headline_n": n_ref,
                           "by_n": [{"n": n, "tv_similarity": v} for n, v in sorted(noise.items())]},
        "totals": totals,
        "holm_summary": holm_summary,
        "competitors": competitors,
        "pooled": pooled,
        "decomposition": decomposition,
        "rank3_pairs": {
            "counting_unit": "individuals in state S3: each distinct attribute pair of a rank-3 clash counted "
                             "once per individual holding it (an individual may hold several pairs)",
            "n_individuals": int(total_hist[CLASH_STATES.index("S3")]),
            "pairs": rank3_pairs,
        },
    }
    return block, skips
