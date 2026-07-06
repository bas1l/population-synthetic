"""Golden + behavioural tests for :func:`aggregator.compute_metrics`.

The golden snapshot (``tests/data/expected_metrics.json``) pins the *entire*
metrics dict for the shared fixture run.  It is the safety net proving the
Phase 2 (stats consolidation) and Phase 3 (function split) refactors are
behaviour-preserving: this test must stay green and the snapshot must not change.
"""

from __future__ import annotations

import json
from pathlib import Path

from population_synthetic.analysis.run_analytics.per_run.aggregator import compute_metrics

from ._fixtures import ENRICHED_ENTRIES, JSONL_NATIVE_ENTRIES, RUN_SUMMARY, entries_without_tokens

_EXPECTED_PATH = Path(__file__).parent / "data" / "expected_metrics.json"

_TOKEN_GATED_KEYS = [
    "token_consumption_per_persona",
    "token_consumption_per_category",
    "tokens_per_second",
    "latency_by_category",
    "token_budget_by_step_type",
]


def _jsonify(obj):
    """Round-trip through JSON so int/float and key ordering match the snapshot."""
    return json.loads(json.dumps(obj, ensure_ascii=False))


def test_compute_metrics_matches_golden_snapshot():
    expected = json.loads(_EXPECTED_PATH.read_text(encoding="utf-8"))
    actual = _jsonify(compute_metrics(ENRICHED_ENTRIES, RUN_SUMMARY))
    assert actual == expected


def test_all_twelve_top_level_keys_present():
    metrics = compute_metrics(ENRICHED_ENTRIES, RUN_SUMMARY)
    assert set(metrics.keys()) == {
        "summary",
        "per_category",
        "method_distribution",
        "prompt_size_growth",
        "response_verbosity",
        "wall_clock_per_persona",
        "value_diversity",
        "token_consumption_per_persona",
        "token_consumption_per_category",
        "tokens_per_second",
        "latency_by_category",
        "token_budget_by_step_type",
    }


def test_summary_counts():
    summary = compute_metrics(ENRICHED_ENTRIES, RUN_SUMMARY)["summary"]
    assert summary["total_entries"] == 6
    assert summary["total_personas"] == 2
    assert summary["total_retries"] == 1
    assert summary["total_errors"] == 1
    assert summary["token_match_rate"] == 1.0


def test_token_gated_metrics_omitted_without_token_data():
    metrics = compute_metrics(entries_without_tokens(), RUN_SUMMARY)
    for key in _TOKEN_GATED_KEYS:
        assert metrics[key] is None, f"{key} should be None when no token data"
    # Non-gated families are still computed.
    assert metrics["summary"]["token_match_rate"] is None
    assert metrics["per_category"]
    assert metrics["value_diversity"]


def test_empty_entries_returns_zeroed_structure():
    metrics = compute_metrics([], None)
    assert metrics["summary"]["total_entries"] == 0
    assert metrics["per_category"] == {}
    for key in _TOKEN_GATED_KEYS:
        assert metrics[key] is None


# --- Phase 4: JSONL-native telemetry (no text log involved) -----------------

def test_token_gated_metrics_compute_from_jsonl_native_telemetry_without_log():
    """Token-gated metrics must compute directly from JSONL-native tokens.

    ``JSONL_NATIVE_ENTRIES`` is never passed through joiner.join_entries() --
    it represents a run whose text log is unavailable/lost, or was never
    joined.  The token/timing fields live on the entries themselves (Phases
    1-3), so ``compute_metrics`` must token-gate on them all the same.
    """
    metrics = compute_metrics(JSONL_NATIVE_ENTRIES, None)
    for key in _TOKEN_GATED_KEYS:
        assert metrics[key] is not None, f"{key} should compute from JSONL-native tokens"

    assert metrics["summary"]["token_match_rate"] == 0.5  # one entry has tokens, one doesn't
    per_persona = metrics["token_consumption_per_persona"]["persona_00001"]
    assert per_persona["prompt_tokens"] == 100
    assert per_persona["completion_tokens"] == 10


def test_error_category_counts_surfaced_per_category():
    """Structured error_category breakdown sits alongside the free-text taxonomy."""
    per_category = compute_metrics(JSONL_NATIVE_ENTRIES, None)["per_category"]
    assert per_category["age"]["error_category_counts"] == {"network": 1}
    # Free-text taxonomy is unaffected by the new structured breakdown.
    assert per_category["age"]["error_taxonomy"] == {"ConnectionError": 1}
    # Categories with no errors report an empty structured breakdown, not a
    # missing key.
    assert per_category["first_name"]["error_category_counts"] == {}
