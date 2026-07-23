"""Reduce one persona's LLM-call telemetry to a per-persona metric record.

Consumes the *normalized call entries* produced by the reused
``run_analytics.per_run.interaction_parser`` -- a list of dicts with all
``LLMInteractionEntry`` fields guaranteed present (``None`` when absent). This
module knows nothing about slugs, country/model/strategy, file layout, pricing,
or charts: it takes entries in and returns a ``PersonaMetrics`` record.

Reduction rules (authoritative -- see the plan Definitions):
- **wall-clock time**: latest ``response_received_at`` minus earliest
  ``request_sent_at`` across the persona's calls, in seconds; per entry, the
  precise ``request_sent_at``/``response_received_at`` telemetry is used when
  present, else that entry falls back to its ``timestamp``. Requires >= 2 usable
  timestamps overall, else ``None`` (the persona is excluded from the time mean
  and counted as skipped by the aggregator).
- **input/output/total tokens**: sum of ``prompt_tokens`` / ``completion_tokens``
  / ``total_tokens`` across calls; ``None`` (not ``0``) when the provider
  reported no value for that field on any call -- "absent" stays distinct from a
  genuine zero.
- **n_calls**: number of interaction entries.
- **retry_rate**: fraction of calls with ``attempt > 1`` (``None`` when no calls).
- **error_rate**: fraction of calls with a non-null ``error`` (``None`` when no calls).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from population_synthetic.analysis.run_analytics.per_run.aggregator import _parse_iso
from population_synthetic.analysis.run_analytics.per_run.interaction_parser import (
    find_interaction_file,
    parse_interactions,
)

__all__ = [
    "PersonaMetrics",
    "reduce_persona",
    "find_interaction_file",
    "parse_interactions",
    "load_persona_entries",
]


@dataclass(frozen=True)
class PersonaMetrics:
    """One persona's per-persona generation metrics.

    Token metrics and derived cost are ``None`` (not ``0``) when the provider
    reported no token telemetry for the persona -- "absent" is kept distinct from
    a genuine zero. ``time_seconds`` is ``None`` when fewer than two usable
    timestamps are available. Populated in Phase 2.
    """

    time_seconds: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    n_calls: int = 0
    retry_rate: float | None = None
    error_rate: float | None = None


def _time_points(entries: list[dict[str, Any]]) -> list[datetime]:
    """Collect the usable wall-clock timestamps across a persona's calls.

    Per entry: use the precise ``request_sent_at``/``response_received_at``
    telemetry when present; if neither is present, fall back to the entry's
    ``timestamp``. Unparseable/absent values are dropped. The returned pool's
    min and max bracket the persona's wall-clock span.
    """
    points: list[datetime] = []
    for entry in entries:
        req = _parse_iso(entry.get("request_sent_at"))
        resp = _parse_iso(entry.get("response_received_at"))
        if req is not None:
            points.append(req)
        if resp is not None:
            points.append(resp)
        if req is None and resp is None:
            ts = _parse_iso(entry.get("timestamp"))
            if ts is not None:
                points.append(ts)
    return points


def _token_sum(entries: list[dict[str, Any]], field: str) -> int | None:
    """Sum *field* across calls; ``None`` when no call reported it (not ``0``)."""
    present = [entry[field] for entry in entries if entry.get(field) is not None]
    if not present:
        return None
    return sum(present)


def reduce_persona(entries: list[dict[str, Any]]) -> PersonaMetrics:
    """Reduce one persona's normalized call entries to a ``PersonaMetrics`` record.

    An empty entry list yields an all-``None`` record with ``n_calls == 0`` (a
    persona whose interaction file exists but is empty contributes nothing to any
    metric mean). See the module docstring for the per-field rules.
    """
    n_calls = len(entries)

    points = _time_points(entries)
    time_seconds = (max(points) - min(points)).total_seconds() if len(points) >= 2 else None

    input_tokens = _token_sum(entries, "prompt_tokens")
    output_tokens = _token_sum(entries, "completion_tokens")
    total_tokens = _token_sum(entries, "total_tokens")

    if n_calls > 0:
        retry_rate = sum(1 for e in entries if (e.get("attempt") or 1) > 1) / n_calls
        error_rate = sum(1 for e in entries if e.get("error") is not None) / n_calls
    else:
        retry_rate = None
        error_rate = None

    return PersonaMetrics(
        time_seconds=time_seconds,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        n_calls=n_calls,
        retry_rate=retry_rate,
        error_rate=error_rate,
    )


def load_persona_entries(persona_dir: Path | str) -> list[dict[str, Any]] | None:
    """Return the normalized call entries for one persona dir, or ``None``.

    Thin reuse of the ``interaction_parser`` contract: locates the persona's
    ``llm_interactions.{jsonl,json}`` file and parses it into normalized entry
    dicts. Returns ``None`` when the persona has no interaction file (a loud skip
    is the caller's responsibility, per the workflow-owns-idempotency rule).
    """
    path = find_interaction_file(persona_dir)
    if path is None:
        return None
    return parse_interactions(path)
