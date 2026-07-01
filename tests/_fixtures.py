"""Shared in-memory fixtures for the analysis-pipeline tests.

The parse->join->aggregate core is I/O-free, so these fixtures are plain Python
lists -- no filesystem is needed.  ``ENRICHED_ENTRIES`` mimics the output of
:func:`joiner.join_entries` (interaction fields + token/timing fields) for a
small two-persona run that exercises every metric family:

- two personas (``persona_00001``, ``persona_00002``),
- multiple categories with a shared value (so entropy is non-trivial),
- a retry entry (``step`` ending in ``_retry``) carrying an ``error``,
- token + latency data on every call (so the token-gated metrics compute).
"""

from __future__ import annotations

from typing import Any

# Enriched entries (post-join): interaction fields + prompt_tokens /
# completion_tokens / elapsed_ms.  Timestamps are spaced so wall-clock spans and
# the +/-2s join window are both well-defined.
ENRICHED_ENTRIES: list[dict[str, Any]] = [
    {
        "category": "first_name",
        "method": "pick",
        "step": "pick",
        "prompt": "pick a first name",          # len 17
        "raw_response": '{"value": "Anna"}',     # len 17
        "parsed_value": {"value": "Anna"},
        "error": None,
        "attempt": 1,
        "timestamp": "2026-05-21T10:00:00.000000",
        "persona_id": "persona_00001",
        "prompt_tokens": 100,
        "completion_tokens": 10,
        "elapsed_ms": 500.0,
    },
    {
        "category": "age",
        "method": "generate_evaluate_pick",
        "step": "enumerate",
        "prompt": "enumerate plausible ages",    # len 24
        "raw_response": '{"value": [40, 41, 42]}',
        "parsed_value": {"value": [40, 41, 42]},
        "error": None,
        "attempt": 1,
        "timestamp": "2026-05-21T10:00:01.000000",
        "persona_id": "persona_00001",
        "prompt_tokens": 200,
        "completion_tokens": 30,
        "elapsed_ms": 1500.0,
    },
    {
        "category": "age",
        "method": "generate_evaluate_pick",
        "step": "pick_retry",
        "prompt": "pick one age",                # len 12
        "raw_response": "not json",
        "parsed_value": None,
        "error": "JSONDecodeError: Expecting ',' delimiter",
        "attempt": 2,
        "timestamp": "2026-05-21T10:00:02.000000",
        "persona_id": "persona_00001",
        "prompt_tokens": 210,
        "completion_tokens": 5,
        "elapsed_ms": 800.0,
    },
    {
        "category": "age",
        "method": "generate_evaluate_pick",
        "step": "pick",
        "prompt": "pick one age",                # len 12
        "raw_response": '{"value": 42}',
        "parsed_value": {"value": 42},
        "error": None,
        "attempt": 3,
        "timestamp": "2026-05-21T10:00:03.000000",
        "persona_id": "persona_00001",
        "prompt_tokens": 220,
        "completion_tokens": 8,
        "elapsed_ms": 900.0,
    },
    {
        "category": "first_name",
        "method": "pick",
        "step": "pick",
        "prompt": "pick a first name",          # len 17
        "raw_response": '{"value": "Bjorn"}',
        "parsed_value": {"value": "Bjorn"},
        "error": None,
        "attempt": 1,
        "timestamp": "2026-05-21T10:00:10.000000",
        "persona_id": "persona_00002",
        "prompt_tokens": 100,
        "completion_tokens": 12,
        "elapsed_ms": 600.0,
    },
    {
        "category": "age",
        "method": "generate_evaluate_pick",
        "step": "pick",
        "prompt": "pick one age",                # len 12
        "raw_response": '{"value": 42}',
        "parsed_value": {"value": 42},
        "error": None,
        "attempt": 1,
        "timestamp": "2026-05-21T10:00:12.000000",
        "persona_id": "persona_00002",
        "prompt_tokens": 230,
        "completion_tokens": 9,
        "elapsed_ms": 1100.0,
    },
]

RUN_SUMMARY: dict[str, Any] = {"elapsed_s": 12.0, "success": 2, "failed": 0}


def entries_without_tokens() -> list[dict[str, Any]]:
    """Return a copy of ENRICHED_ENTRIES with all token/timing fields stripped.

    Mimics a Claude/Gemini-CLI run where the provider reports no token counts, so
    the token-gated metric families must be omitted (set to ``None``).
    """
    out: list[dict[str, Any]] = []
    for e in ENRICHED_ENTRIES:
        copy = dict(e)
        copy.pop("prompt_tokens", None)
        copy.pop("completion_tokens", None)
        copy.pop("elapsed_ms", None)
        out.append(copy)
    return out
