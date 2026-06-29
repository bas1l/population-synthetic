"""Correlation context for matching log-file call records to JSONL entries.

Parallel identity runs write every persona's call records into a single shared
``logs/run_*.log`` while each persona's interaction entries go to its own
``llm_interactions.jsonl``.  Joining the two by timestamp proximity is ambiguous
when calls interleave.  This module carries a ``(persona_id, call_index)``
correlation key from the generator (which knows both) to the client (which emits
the log line) via a :class:`contextvars.ContextVar`, so the join can be exact.

A ``ContextVar`` is per-thread and per-process: each parallel worker sets and
reads its own value with no cross-talk, and no client method signature changes.
The generator calls :func:`set_correlation` immediately before each
``generate_content`` call; the client appends :func:`format_corr_token` to its
log line.  When unset (single non-parallel runs, or callers that don't
participate) the token is empty and the joiner falls back to timestamp proximity.
"""

from __future__ import annotations

import contextvars

# (persona_id, call_index) for the in-flight LLM call, or None when not set.
_CORRELATION: contextvars.ContextVar[tuple[str | None, int | None] | None] = (
    contextvars.ContextVar("llm_call_correlation", default=None)
)


def set_correlation(persona_id: str | None, call_index: int | None) -> None:
    """Record the correlation key for the next ``generate_content`` call."""
    _CORRELATION.set((persona_id, call_index))


def get_correlation() -> tuple[str | None, int | None] | None:
    """Return the current ``(persona_id, call_index)`` key, or ``None``."""
    return _CORRELATION.get()


def format_corr_token() -> str:
    """Return a ``" corr=<persona_id>:<call_index>"`` log suffix, or ``""``.

    Empty when the correlation context is unset or incomplete, so log lines for
    non-participating callers are byte-for-byte unchanged.
    """
    corr = _CORRELATION.get()
    if not corr:
        return ""
    persona_id, call_index = corr
    if persona_id is None or call_index is None:
        return ""
    return f" corr={persona_id}:{call_index}"
