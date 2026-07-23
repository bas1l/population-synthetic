"""Aggregate a combo's per-persona records into per-metric distribution stats.

Consumes the per-persona :class:`PersonaMetrics` records (and their
already-computed USD costs) for a single ``country x model x method`` combo and
reduces them to a :class:`ComboSummary`: for each metric, the arithmetic mean,
sample standard deviation, median/q1/q3, and ``n`` (the count of personas
contributing a non-null value for THAT metric -- per-metric, not per-combo). It
also carries the combo identity, a ``skipped`` list recording personas excluded
from a metric (no interaction file, or too few timestamps for the wall-clock
span), the per-persona value samples (for downstream significance testing), a
few combo-level scalar diagnostics (latency p95/max, success rate) derived from
the pre-computed deep-diagnostics dict, and that deep-diagnostics dict itself.

This module knows nothing about file layout, pricing dollar values (costs arrive
already computed), how the diagnostics dict was assembled, or chart styling.
Distribution stats come from the shared ``analysis/utils`` primitives (single
source of truth): mean/std from ``_stats`` and median/q1/q3 from
``stats_tests.summarize``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from population_synthetic.analysis.generation_metadata.persona_metrics import PersonaMetrics
from population_synthetic.analysis.utils._stats import mean, percentile, stddev
from population_synthetic.analysis.utils.stats_tests import summarize as _summarize

__all__ = ["METRIC_NAMES", "DISTRIBUTION_STATS", "SCALAR_METRIC_NAMES", "ComboSummary", "aggregate_combo"]

# Canonical per-metric names and their fixed presentation order. This is the
# single source of truth consumed by the report writer's CSV columns and the
# per-metric charts, so those can never drift from what the aggregator emits.
# Every name here is a *distribution* metric: it reduces to one value per persona
# and is summarised as ``{mean, std, median, q1, q3, n}``.
METRIC_NAMES: tuple[str, ...] = (
    "time",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "calls",
    "retry_rate",
    "error_rate",
    "cost",
)

# Per-distribution-metric statistic column order (single source of truth for the
# ``<metric>_<stat>`` CSV/JSON column set). ``mean``/``std`` come from ``_stats``
# (std ``None`` for ``n < 2``); ``median``/``q1``/``q3`` from ``stats_tests`` (q1/q3
# ``None`` for ``n < 2`` -- undefined for a single point, matching std's gate).
DISTRIBUTION_STATS: tuple[str, ...] = ("mean", "std", "median", "q1", "q3", "n")

# Combo-level *scalar* diagnostics (one number per combo, not a per-persona
# distribution) derived from the deep-diagnostics dict. Fixed order = CSV column
# order. ``latency_*`` are token-gated (``None`` without token/timing telemetry);
# ``success_rate`` is the call-level ``1 - error_rate`` and needs no tokens.
SCALAR_METRIC_NAMES: tuple[str, ...] = ("latency_p95", "latency_max", "success_rate")


@dataclass(frozen=True)
class ComboSummary:
    """Per-combo aggregate: identity + per-metric distribution stats + diagnostics.

    ``metrics`` maps each name in :data:`METRIC_NAMES` to a dict keyed by
    :data:`DISTRIBUTION_STATS` (``mean``/``std``/``median``/``q1``/``q3``/``n``),
    where the stats are ``None`` when undefined (no contributors, or ``n < 2`` for
    ``std``/``q1``/``q3``) and ``n`` is the count of personas that contributed a
    non-null value for that metric. ``has_token_data`` records the combo-level
    token gate: when ``False`` the token/cost metric families naturally have
    ``n == 0`` and all stats ``None``.

    ``samples`` holds, per metric, the raw per-persona value list actually used
    for the stats above -- retained so the country-level significance path (Phase
    3) can test across combos without re-parsing. ``scalar_metrics`` maps each
    name in :data:`SCALAR_METRIC_NAMES` to its single value (``None`` when
    ungated). ``diagnostics`` is the deep per-combo ``compute_metrics`` dict
    (nested per-category / per-step structures), serialised to JSON only -- never
    flattened to the CSV.
    """

    country: str
    model: str
    strategy: str
    n_personas: int
    has_token_data: bool
    metrics: dict[str, dict[str, float | int | None]]
    skipped: list[dict[str, str]]
    samples: dict[str, list[float]] = field(default_factory=dict)
    scalar_metrics: dict[str, float | None] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _metric_value(pm: PersonaMetrics, cost: float | None, name: str) -> float | int | None:
    """Return one persona's value for metric *name* (``None`` when ungated/absent)."""
    return {
        "time": pm.time_seconds,
        "input_tokens": pm.input_tokens,
        "output_tokens": pm.output_tokens,
        "total_tokens": pm.total_tokens,
        "calls": pm.n_calls,
        "retry_rate": pm.retry_rate,
        "error_rate": pm.error_rate,
        "cost": cost,
    }[name]


def _distribution_stats(present: list[float]) -> dict[str, float | int | None]:
    """Summarise one metric's per-persona values into the fixed stat set.

    ``mean``/``std`` come from ``_stats`` (std ``None`` for ``n < 2``);
    ``median``/``q1``/``q3`` from ``stats_tests.summarize`` (a metric with a single
    contributor has a defined median but ill-defined quartiles, so ``q1``/``q3``
    are gated to ``None`` at ``n < 2`` -- consistent with ``std``).
    """
    n = len(present)
    summ = _summarize(present)  # {n, median, mean, std, q1, q3, min, max}
    return {
        "mean": mean(present),
        "std": stddev(present),
        "median": summ["median"],
        "q1": summ["q1"] if n >= 2 else None,
        "q3": summ["q3"] if n >= 2 else None,
        "n": n,
    }


def _overall_latencies(diagnostics: dict[str, Any] | None) -> list[float]:
    """Collect every per-call ``elapsed_ms`` from the diagnostics dict.

    Source is the ``tokens_per_second`` per-entry list, which retains one
    ``elapsed_ms`` per call (unlike ``latency_by_category``, whose per-category
    percentiles cannot be recombined into an overall p95). Returns ``[]`` when
    diagnostics are absent or latency is token-gated (``tokens_per_second`` is
    ``None``), which the caller maps to ``None`` latency scalars.
    """
    if not diagnostics:
        return []
    tps = diagnostics.get("tokens_per_second")
    if not tps:
        return []
    return [e["elapsed_ms"] for e in tps if e.get("elapsed_ms") is not None]


def _scalar_metrics(diagnostics: dict[str, Any] | None) -> dict[str, float | None]:
    """Derive the combo-level scalar diagnostics from the deep-diagnostics dict.

    - ``latency_p95`` / ``latency_max``: overall nearest-rank p95 and max over all
      per-call ``elapsed_ms`` (token-gated -> ``None`` when no timing telemetry).
    - ``success_rate``: call-level ``1 - error_rate`` == ``(entries - errors) /
      entries`` (``None`` only when the combo has no entries at all).
    """
    lats = _overall_latencies(diagnostics)
    latency_p95 = percentile(lats, 95) if lats else None
    latency_max = max(lats) if lats else None

    summary = (diagnostics or {}).get("summary") or {}
    total = summary.get("total_entries") or 0
    errors = summary.get("total_errors") or 0
    success_rate = (total - errors) / total if total else None

    return {
        "latency_p95": latency_p95,
        "latency_max": latency_max,
        "success_rate": success_rate,
    }


def aggregate_combo(
    country: str,
    model: str,
    strategy: str,
    personas: list[tuple[str, PersonaMetrics, float | None]],
    *,
    prior_skipped: list[dict[str, str]] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> ComboSummary:
    """Aggregate one combo's personas into a :class:`ComboSummary`.

    Parameters
    ----------
    country, model, strategy:
        The combo identity.
    personas:
        One ``(persona_id, PersonaMetrics, cost)`` triple per persona that HAD an
        interaction file. ``cost`` is the persona's pre-computed USD cost (``None``
        when ungated).
    prior_skipped:
        Skip records the caller already knows about (e.g. personas with no
        interaction file), merged verbatim into the summary's ``skipped`` list.
    diagnostics:
        The combo's deep-diagnostics dict from ``diagnostics.compute_metrics`` over
        the combo's (joined) entries. Attached verbatim to the summary and mined
        for the scalar latency/success-rate metrics. ``None`` (the default, used by
        unit tests that exercise only the distribution path) yields empty
        diagnostics and ``None`` scalar metrics.
    """
    skipped: list[dict[str, str]] = list(prior_skipped or [])

    # Per-persona wall-clock exclusions surface as skip records so the JSON report
    # says *why* a persona did not contribute to the time mean.
    for persona_id, pm, _cost in personas:
        if pm.time_seconds is None:
            skipped.append(
                {
                    "persona": persona_id,
                    "metric": "time",
                    "reason": "fewer than two usable timestamps for wall-clock span",
                }
            )

    has_token_data = any(
        pm.input_tokens is not None or pm.output_tokens is not None for _pid, pm, _c in personas
    )

    metrics: dict[str, dict[str, float | int | None]] = {}
    samples: dict[str, list[float]] = {}
    for name in METRIC_NAMES:
        present = [
            v for _pid, pm, cost in personas if (v := _metric_value(pm, cost, name)) is not None
        ]
        samples[name] = present
        metrics[name] = _distribution_stats(present)

    return ComboSummary(
        country=country,
        model=model,
        strategy=strategy,
        n_personas=len(personas),
        has_token_data=has_token_data,
        metrics=metrics,
        skipped=skipped,
        samples=samples,
        scalar_metrics=_scalar_metrics(diagnostics),
        diagnostics=diagnostics or {},
    )
