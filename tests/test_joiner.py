"""Tests for :func:`joiner.join_entries` timestamp-proximity behaviour.

Phase 4 extends the joiner with an exact correlation-ID match and keeps this
timestamp path as the fallback for legacy runs; these tests pin the fallback so
that extension cannot silently regress it.
"""

from __future__ import annotations

from population_synthetic.analysis.generation_metadata.joiner import join_entries


def _log(ts, pt=100, ct=10, ms=500.0):
    return {"timestamp": ts, "prompt_tokens": pt, "completion_tokens": ct, "elapsed_ms": ms}


def test_match_within_tolerance_attaches_tokens():
    jsonl = [{"timestamp": "2026-05-21T10:00:00.000000"}]
    logs = [_log("2026-05-21 10:00:01")]  # 1s away, within default 2s
    out = join_entries(jsonl, logs)
    assert out[0]["prompt_tokens"] == 100
    assert out[0]["completion_tokens"] == 10
    assert out[0]["elapsed_ms"] == 500.0


def test_no_match_outside_tolerance():
    jsonl = [{"timestamp": "2026-05-21T10:00:00.000000"}]
    logs = [_log("2026-05-21 10:00:05")]  # 5s away, outside 2s
    out = join_entries(jsonl, logs)
    assert out[0]["prompt_tokens"] is None
    assert out[0]["completion_tokens"] is None
    assert out[0]["elapsed_ms"] is None


def test_one_to_one_matching():
    # Two entries, one log record close to the first; the second stays unmatched.
    jsonl = [
        {"timestamp": "2026-05-21T10:00:00.000000"},
        {"timestamp": "2026-05-21T10:00:00.500000"},
    ]
    logs = [_log("2026-05-21 10:00:00")]
    out = join_entries(jsonl, logs)
    assert out[0]["prompt_tokens"] == 100
    assert out[1]["prompt_tokens"] is None


def test_no_logs_defaults_to_none():
    jsonl = [{"timestamp": "2026-05-21T10:00:00.000000"}]
    out = join_entries(jsonl, [])
    assert out[0]["prompt_tokens"] is None
    assert out[0]["completion_tokens"] is None
    assert out[0]["elapsed_ms"] is None


def test_original_fields_preserved():
    jsonl = [{"timestamp": "2026-05-21T10:00:00.000000", "category": "age", "method": "pick"}]
    out = join_entries(jsonl, [_log("2026-05-21 10:00:00")])
    assert out[0]["category"] == "age"
    assert out[0]["method"] == "pick"


# --- Phase 4: exact correlation-ID matching ---------------------------------

def _corr_log(ts, pid, cidx, pt):
    return {
        "timestamp": ts, "persona_id": pid, "call_index": cidx,
        "prompt_tokens": pt, "completion_tokens": 1, "elapsed_ms": 10.0,
    }


def test_corr_exact_match_beats_timestamp():
    # Entries share a timestamp; logs are 5 min away (outside tolerance) and in
    # reversed order -- only the corr key can attribute them correctly.
    jsonl = [
        {"timestamp": "2026-05-21T10:00:00.000000", "persona_id": "persona_00001", "call_index": 1},
        {"timestamp": "2026-05-21T10:00:00.000000", "persona_id": "persona_00002", "call_index": 1},
    ]
    logs = [
        _corr_log("2026-05-21 10:05:00", "persona_00002", 1, 222),
        _corr_log("2026-05-21 10:05:00", "persona_00001", 1, 111),
    ]
    out = join_entries(jsonl, logs)
    assert out[0]["prompt_tokens"] == 111  # persona_00001
    assert out[1]["prompt_tokens"] == 222  # persona_00002


def test_mixed_corr_and_timestamp_fallback():
    # First entry has a corr key (exact); second has none (timestamp fallback).
    jsonl = [
        {"timestamp": "2026-05-21T10:00:00.000000", "persona_id": "persona_00001", "call_index": 1},
        {"timestamp": "2026-05-21T10:00:10.000000"},  # no corr
    ]
    logs = [
        _log("2026-05-21 10:00:10", pt=50),  # no corr, near the second entry
        _corr_log("2026-05-21 10:00:00", "persona_00001", 1, 99),
    ]
    out = join_entries(jsonl, logs)
    assert out[0]["prompt_tokens"] == 99  # corr-matched (and removed from pool)
    assert out[1]["prompt_tokens"] == 50  # timestamp fallback


def test_corr_distinct_call_indices_not_confused():
    # Same persona, two calls -- each call_index attaches to its own record.
    jsonl = [
        {"timestamp": "2026-05-21T10:00:00.000000", "persona_id": "persona_00001", "call_index": 1},
        {"timestamp": "2026-05-21T10:00:00.100000", "persona_id": "persona_00001", "call_index": 2},
    ]
    logs = [
        _corr_log("2026-05-21 10:00:00", "persona_00001", 2, 20),
        _corr_log("2026-05-21 10:00:00", "persona_00001", 1, 10),
    ]
    out = join_entries(jsonl, logs)
    assert out[0]["prompt_tokens"] == 10  # call_index 1
    assert out[1]["prompt_tokens"] == 20  # call_index 2


# --- Phase 4: JSONL-native telemetry is preferred over the text-log join ----

def test_jsonl_native_tokens_preferred_over_log_join():
    # The JSONL entry already carries its own (non-None) telemetry -- the
    # matched log record's values must NOT overwrite it.
    jsonl = [
        {
            "timestamp": "2026-05-21T10:00:00.000000",
            "prompt_tokens": 999,
            "completion_tokens": 99,
            "elapsed_ms": 42.0,
        }
    ]
    logs = [_log("2026-05-21 10:00:00", pt=1, ct=1, ms=1.0)]
    out = join_entries(jsonl, logs)
    assert out[0]["prompt_tokens"] == 999
    assert out[0]["completion_tokens"] == 99
    assert out[0]["elapsed_ms"] == 42.0


def test_jsonl_native_partial_fields_fill_from_log_only_where_missing():
    # elapsed_ms is JSONL-native (non-None) and must survive; prompt/completion
    # tokens are absent on the JSONL side and must be backfilled from the log.
    jsonl = [
        {
            "timestamp": "2026-05-21T10:00:00.000000",
            "elapsed_ms": 42.0,
            "prompt_tokens": None,
            "completion_tokens": None,
        }
    ]
    logs = [_log("2026-05-21 10:00:00", pt=100, ct=10, ms=500.0)]
    out = join_entries(jsonl, logs)
    assert out[0]["elapsed_ms"] == 42.0  # JSONL-native wins
    assert out[0]["prompt_tokens"] == 100  # backfilled from the log
    assert out[0]["completion_tokens"] == 10  # backfilled from the log


def test_no_log_match_keeps_jsonl_native_values():
    # No log entry matches at all -- JSONL-native telemetry must still surface.
    jsonl = [
        {
            "timestamp": "2026-05-21T10:00:00.000000",
            "prompt_tokens": 999,
            "completion_tokens": 99,
            "elapsed_ms": 42.0,
        }
    ]
    out = join_entries(jsonl, [])
    assert out[0]["prompt_tokens"] == 999
    assert out[0]["completion_tokens"] == 99
    assert out[0]["elapsed_ms"] == 42.0
