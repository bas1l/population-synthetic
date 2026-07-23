"""Aggregate a combo's per-persona records into per-metric mean/std/n.

Consumes the per-persona :class:`PersonaMetrics` records (and their
already-computed USD costs) for a single ``country x model x method`` combo and
reduces them to a :class:`ComboSummary`: for each metric, the arithmetic mean,
sample standard deviation, and ``n`` (the count of personas contributing a
non-null value for THAT metric -- per-metric, not per-combo). It also carries the
combo identity and a ``skipped`` list recording personas excluded from a metric
(no interaction file, or too few timestamps for the wall-clock span).

This module knows nothing about file layout, pricing dollar values (costs arrive
already computed), or chart styling. Stats come from the shared
``analysis/utils/_stats`` primitives (single source of truth).
"""

from __future__ import annotations

from dataclasses import dataclass

from population_synthetic.analysis.generation_metadata.persona_metrics import PersonaMetrics
from population_synthetic.analysis.utils._stats import mean, stddev

__all__ = ["METRIC_NAMES", "ComboSummary", "aggregate_combo"]

# Canonical per-metric names and their fixed presentation order. This is the
# single source of truth consumed by the report writer's CSV columns and (Phase 3)
# the per-metric charts, so those can never drift from what the aggregator emits.
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


@dataclass(frozen=True)
class ComboSummary:
    """Per-combo aggregate: identity + per-metric {mean, std, n} + skip reasons.

    ``metrics`` maps each name in :data:`METRIC_NAMES` to ``{"mean", "std", "n"}``
    where ``mean``/``std`` are ``None`` when undefined (no contributors / ``n < 2``)
    and ``n`` is the count of personas that contributed a non-null value for that
    metric. ``has_token_data`` records the combo-level token gate: when ``False``,
    the token/cost metric families naturally have ``n == 0`` and ``mean == None``.
    """

    country: str
    model: str
    strategy: str
    n_personas: int
    has_token_data: bool
    metrics: dict[str, dict[str, float | int | None]]
    skipped: list[dict[str, str]]


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


def aggregate_combo(
    country: str,
    model: str,
    strategy: str,
    personas: list[tuple[str, PersonaMetrics, float | None]],
    *,
    prior_skipped: list[dict[str, str]] | None = None,
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
    for name in METRIC_NAMES:
        present = [
            v for _pid, pm, cost in personas if (v := _metric_value(pm, cost, name)) is not None
        ]
        metrics[name] = {
            "mean": mean(present),
            "std": stddev(present),
            "n": len(present),
        }

    return ComboSummary(
        country=country,
        model=model,
        strategy=strategy,
        n_personas=len(personas),
        has_token_data=has_token_data,
        metrics=metrics,
        skipped=skipped,
    )
