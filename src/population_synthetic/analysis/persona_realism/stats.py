"""stats.py -- pure combination-level realism statistics.

The second pure layer (guide 02 sect. 8): it takes a combination's
:class:`~population_synthetic.analysis.persona_realism.reduce.ComboRealism` (and
the SCB real-population ``ComboRealism`` as the dispersion reference) and computes
a :class:`RealismStats` bundle -- an impossibility rate with a bootstrap CI, a
typicality-dispersion characterisation with a distance to the SCB reference and a
variance-equality test, and a judge self-consistency (reliability) block.

It must NOT know about rendering, paths, the judge, or config resolution. Every
tunable (bootstrap iterations/seed/ci_level, the Krippendorff level for
typicality, the tail threshold, the Levene centring) is a **parameter supplied by
the caller from config** -- nothing is hardcoded (config is the single source of
truth; the caller reads ``JudgeConfig`` and passes the values in). All heavy
statistics reuse the shared
:mod:`population_synthetic.analysis.utils.stats_tests` primitives; numeric
summaries reuse :mod:`population_synthetic.analysis.utils._stats`. Nothing is
re-implemented here.

Two measurement principles govern the choices (guide 03):

* **Reliability != validity.** The Krippendorff-alpha / ICC block measures whether
  the judge agrees *with itself* across the N rounds -- its precision, NOT its
  correctness. It is named ``reliability`` and must never be presented as
  accuracy; the hard-rules subset (``validation.py``) is the only validity anchor.
* **Typicality is ordinal (0-10), not interval.** The bootstrap sampling unit is
  the **persona** (not the round). Dispersion is reported three ways so no single
  interval-assuming number stands alone: ``variance`` (the interval-treatment
  view, flagged as such), ``entropy`` (distribution shape over the integer
  typicality buckets -- assumes no spacing), and ``tail_coverage`` (a rank-based
  threshold: the share of personas reaching into the unusual low-typicality tail).
  The reliability metric on ``can_exist`` uses the **nominal** level (a boolean has
  no interval meaning); the reliability metric on typicality defaults to the
  **ordinal** level (respecting that a 0-10 rating is a rank, not an interval) and
  is overridable via config.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from population_synthetic.analysis.persona_realism.reduce import ComboRealism
from population_synthetic.analysis.utils import _stats
from population_synthetic.analysis.utils.stats_tests import (
    bootstrap_ci,
    icc,
    krippendorff_alpha,
    variance_equality_test,
)

__all__ = ["RealismStats", "compute_realism_stats"]

# The dispersion measures compared combo-vs-SCB, in a fixed order (single source
# for the distance-to-reference keys).
_DISPERSION_MEASURES: tuple[str, ...] = ("variance", "entropy", "tail_coverage")

# Label used for the SCB reference group inside the variance-equality test.
_SCB_GROUP = "scb_reference"


@dataclass(frozen=True)
class RealismStats:
    """Combination-level realism statistics (the Phase-4/5 consumption contract).

    ``n_personas`` / ``n_failed`` are carried verbatim from the
    :class:`ComboRealism` so every reader sees the successful base and the dropped
    count next to the metrics.

    ``impossibility`` is the :func:`bootstrap_ci` result over the per-persona 0/1
    impossibility indicators (``point`` == the rate, ``lo``/``hi`` the CI, ``n`` ==
    the resampled persona count) augmented with ``rate``, ``impossible_count``,
    ``successful_count`` and ``failed_count``. Degenerate (no successful persona) ->
    ``point``/``lo``/``hi`` ``None`` with a ``note``.

    ``dispersion`` carries this combo's ``variance``/``entropy``/``tail_coverage``
    over the can_exist typicality means, the ``distance_to_scb`` per measure, and a
    ``variance_equality`` Levene/Brown-Forsythe result (this combo vs SCB). An
    empty can_exist set -> measures ``None`` with a ``note``.

    ``reliability`` carries ``can_exist_alpha`` (nominal Krippendorff over the
    boolean rounds), ``typicality_alpha`` (Krippendorff at ``typicality_level``),
    ``typicality_icc`` (ICC(1,1) over rounds, only when the typicality matrix is
    rectangular and fully scored), and the ``typicality_level`` used. Each sub-dict
    self-reports a skipped ``note`` on degenerate input (e.g. a single round) --
    never a bare ``NaN``.
    """

    combo_label: str
    n_personas: int
    n_failed: int
    impossibility: dict[str, Any]
    dispersion: dict[str, Any]
    reliability: dict[str, Any]


def _dispersion(sample: list[float], *, tail_threshold: float) -> dict[str, Any]:
    """Characterise the spread of a can_exist per-persona typicality-mean sample.

    Returns ``{n, variance, entropy, tail_coverage, tail_threshold}``. On an empty
    sample every measure is ``None`` with a ``note`` (an empty can_exist set is a
    skip, not a zero-spread distribution). ``variance`` is the **sample** variance
    (``None`` for ``n < 2`` -- a single point has no spread), reported as the
    interval-treatment view. ``entropy`` is the Shannon entropy (bits) over the
    typicality means rounded to their nearest integer 0-10 bucket -- a
    spacing-free, distribution-shape view. ``tail_coverage`` is the share of
    personas with mean typicality ``<= tail_threshold`` -- the rank-based reach into
    the unusual (low-typicality) tail.
    """
    n = len(sample)
    if n == 0:
        return {
            "n": 0, "variance": None, "entropy": None, "tail_coverage": None,
            "tail_threshold": tail_threshold, "note": "no can_exist personas; dispersion undefined",
        }
    sd = _stats.stddev(sample)  # sample SD (n-1); None for n < 2
    variance = sd * sd if sd is not None else None
    counts: dict[str, int] = {}
    for value in sample:
        bucket = str(int(round(value)))
        counts[bucket] = counts.get(bucket, 0) + 1
    entropy = _stats.shannon_entropy(counts)
    tail_coverage = sum(1 for value in sample if value <= tail_threshold) / n
    return {
        "n": n, "variance": variance, "entropy": entropy,
        "tail_coverage": tail_coverage, "tail_threshold": tail_threshold,
    }


def _typicality_icc(matrix: tuple[tuple[int | None, ...], ...]) -> dict[str, Any]:
    """ICC(1,1) over per-persona typicality rounds, gated to the valid subset.

    ICC needs a rectangular, fully-numeric ``subjects x rounds`` matrix. A round
    the judge deemed impossible has *no* typicality (``None``), and a failed round
    is simply absent -- so only personas whose every round scored a typicality, all
    with the same round count, are usable. Below two such personas, or on a ragged
    remainder, this returns an explicit skipped-reason rather than letting
    :func:`icc` raise -- Krippendorff's alpha (which handles the ``None`` gaps
    natively) remains the primary typicality-reliability metric.
    """
    complete = [list(row) for row in matrix if row and all(t is not None for t in row)]
    n = len(complete)
    if n < 2:
        return {"icc": None, "n": n, "model": "ICC(1,1)",
                "note": "need >=2 personas whose every round scored a typicality"}
    widths = {len(row) for row in complete}
    if len(widths) != 1:
        return {"icc": None, "n": n, "model": "ICC(1,1)",
                "note": "ragged round counts (some rounds failed); ICC needs a rectangular matrix "
                        "-- see typicality_alpha (Krippendorff handles the gaps)"}
    return icc(complete)


def compute_realism_stats(
    combo: ComboRealism,
    scb_ref: ComboRealism | None,
    *,
    bootstrap: dict[str, Any],
    typicality_level: str = "ordinal",
    tail_threshold: float = 3.0,
    variance_center: str = "median",
) -> RealismStats:
    """Compute the :class:`RealismStats` for one combination against the SCB reference.

    Parameters
    ----------
    combo:
        The combination's reduced :class:`ComboRealism`.
    scb_ref:
        The SCB real-population :class:`ComboRealism` used as the dispersion
        reference. ``None`` skips the distance/variance-equality comparison (with a
        recorded ``note``) rather than raising -- e.g. when *combo* itself is the
        real reference and no separate baseline applies.
    bootstrap:
        The config bootstrap block ``{iterations, seed, ci_level}`` -- passed
        straight to :func:`bootstrap_ci` so the RNG seed is the one recorded in run
        metadata. Missing keys raise a ``KeyError`` (fail-fast, no silent default).
    typicality_level:
        Krippendorff level for the typicality-reliability metric --
        ``ordinal`` (default; typicality is a rank) or ``interval``. Sourced from
        config by the caller. ``can_exist`` reliability is always ``nominal``.
    tail_threshold:
        Typicality at or below which a persona counts toward ``tail_coverage``.
    variance_center:
        Levene centring for the variance-equality test (``median`` == the robust
        Brown-Forsythe default, ``mean`` == classic Levene).
    """
    iterations = bootstrap["iterations"]
    seed = bootstrap["seed"]
    ci_level = bootstrap["ci_level"]

    # --- Impossibility rate + bootstrap CI (sampling unit = persona) ---------- #
    ci = bootstrap_ci(
        list(combo.impossible_indicators),
        iterations=iterations,
        ci_level=ci_level,
        seed=seed,
    )
    impossibility = {
        **ci,
        "rate": ci["point"],
        "impossible_count": combo.impossible_count,
        "successful_count": combo.n_personas,
        "failed_count": combo.n_failed,
    }

    # --- Typicality dispersion vs SCB ----------------------------------------- #
    combo_sample = list(combo.typicality_means)
    dispersion = _dispersion(combo_sample, tail_threshold=tail_threshold)
    if scb_ref is None:
        dispersion["scb_reference"] = None
        dispersion["distance_to_scb"] = {m: None for m in _DISPERSION_MEASURES}
        dispersion["variance_equality"] = {
            "statistic": None, "p": None, "note": "no SCB reference provided",
        }
    else:
        scb_sample = list(scb_ref.typicality_means)
        scb_disp = _dispersion(scb_sample, tail_threshold=tail_threshold)
        dispersion["scb_reference"] = scb_ref.combo_label
        dispersion["distance_to_scb"] = {
            m: (abs(dispersion[m] - scb_disp[m])
                if dispersion[m] is not None and scb_disp[m] is not None else None)
            for m in _DISPERSION_MEASURES
        }
        dispersion["variance_equality"] = variance_equality_test(
            {combo.combo_label: combo_sample, _SCB_GROUP: scb_sample},
            center=variance_center,
        )

    # --- Reliability across rounds (self-consistency, NOT validity) ----------- #
    can_exist_data = [[1 if flag else 0 for flag in row] for row in combo.can_exist_rounds_by_persona]
    typicality_data = [list(row) for row in combo.typicality_rounds_by_persona]
    reliability = {
        "can_exist_alpha": krippendorff_alpha(can_exist_data, level="nominal"),
        "typicality_alpha": krippendorff_alpha(typicality_data, level=typicality_level),
        "typicality_icc": _typicality_icc(combo.typicality_rounds_by_persona),
        "typicality_level": typicality_level,
        "measures": "self-consistency across rounds (reliability), not correctness",
    }

    return RealismStats(
        combo_label=combo.combo_label,
        n_personas=combo.n_personas,
        n_failed=combo.n_failed,
        impossibility=impossibility,
        dispersion=dispersion,
        reliability=reliability,
    )
