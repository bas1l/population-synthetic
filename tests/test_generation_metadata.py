"""Tests for the generation_metadata analysis process (Phase 3, task 3.5).

Covers the four computation layers in isolation and one end-to-end integration:

- ``_stats.mean``/``stddev``          -- known-answer + the ``n<2`` / empty guards.
- ``persona_metrics.reduce_persona``  -- time span, token sums, calls, retry/error
                                         rates; missing-timestamp and null-token gating.
- ``cost.persona_cost``               -- priced arithmetic, None-gating, fail-fast on
                                         an unpriced-but-tokened model, zero for ollama.
- ``combo_aggregator.aggregate_combo``-- per-metric n counts only non-null
                                         contributors; single-persona std None; skips.
- ``summarize(...)``                  -- a tiny 01_Raw fixture (one tokened combo, one
                                         genuinely token-less combo) -> CSV+JSON, with
                                         column presence, None-gating, pricing metadata,
                                         charts, and the --force vs skip idempotency.

Token-gating here is DATA-driven, not provider-driven: the token-less combo uses a
model that IS in the pricing table (``claude_opus``) but whose fixture entries carry
genuinely-null token fields, proving cost still gates to None on absent data.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from population_synthetic.analysis.generation_metadata import summarize
from population_synthetic.analysis.generation_metadata.combo_aggregator import (
    DISTRIBUTION_STATS,
    METRIC_NAMES,
    SCALAR_METRIC_NAMES,
    aggregate_combo,
)
from population_synthetic.analysis.generation_metadata.cost import persona_cost
from population_synthetic.analysis.generation_metadata.interaction_parser import parse_interactions
from population_synthetic.analysis.generation_metadata.persona_metrics import (
    PersonaMetrics,
    reduce_persona,
)
from population_synthetic.analysis.generation_metadata.pricing import PricingTable, load_pricing_table
from population_synthetic.analysis.population_cap import cap_combo
from population_synthetic.analysis.utils._stats import mean, stddev
from population_synthetic.analysis.utils.registry import analysis_output_dir

# --------------------------------------------------------------------------- #
# (a) stats primitives
# --------------------------------------------------------------------------- #


def test_mean_known_answer_and_empty():
    assert mean([2.0, 4.0, 6.0]) == pytest.approx(4.0)
    assert mean([5.0]) == pytest.approx(5.0)
    assert mean([]) is None


def test_stddev_known_answer_and_n_lt_2():
    # sample (n-1) stddev of {2,4,6}: var = (4+0+4)/2 = 4 -> sqrt = 2.0
    assert stddev([2.0, 4.0, 6.0]) == pytest.approx(2.0)
    assert stddev([7.0]) is None      # n < 2 -> undefined
    assert stddev([]) is None
    # population denominator is defined at n == 1.
    assert stddev([7.0], sample=False) == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# (b) persona_metrics.reduce_persona
# --------------------------------------------------------------------------- #


def test_reduce_persona_full_record():
    entries = [
        {
            "request_sent_at": "2026-07-23T10:00:00",
            "response_received_at": "2026-07-23T10:00:10",
            "prompt_tokens": 100,
            "completion_tokens": 40,
            "total_tokens": 140,
            "attempt": 1,
            "error": None,
        },
        {
            "request_sent_at": "2026-07-23T10:00:10",
            "response_received_at": "2026-07-23T10:00:30",
            "prompt_tokens": 200,
            "completion_tokens": 60,
            "total_tokens": 260,
            "attempt": 2,
            "error": "timeout",
        },
    ]
    pm = reduce_persona(entries)
    assert pm.time_seconds == pytest.approx(30.0)   # 10:00:00 -> 10:00:30
    assert pm.input_tokens == 300
    assert pm.output_tokens == 100
    assert pm.total_tokens == 400
    assert pm.n_calls == 2
    assert pm.retry_rate == pytest.approx(0.5)      # one of two calls attempt > 1
    assert pm.error_rate == pytest.approx(0.5)      # one of two calls has an error


def test_reduce_persona_missing_timestamps_gives_none_time():
    entries = [
        {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25},
    ]
    pm = reduce_persona(entries)
    assert pm.time_seconds is None                  # fewer than two usable timestamps
    assert pm.input_tokens == 30                    # tokens still summed


def test_reduce_persona_null_tokens_gate_to_none():
    entries = [
        {"request_sent_at": "2026-07-23T10:00:00", "response_received_at": "2026-07-23T10:00:05"},
        {"request_sent_at": "2026-07-23T10:00:05", "response_received_at": "2026-07-23T10:00:11"},
    ]
    pm = reduce_persona(entries)
    assert pm.input_tokens is None                  # absent stays distinct from 0
    assert pm.output_tokens is None
    assert pm.total_tokens is None
    assert pm.time_seconds == pytest.approx(11.0)   # timestamps still yield a span
    assert pm.n_calls == 2


def test_reduce_persona_empty_entries():
    pm = reduce_persona([])
    assert pm.n_calls == 0
    assert pm.time_seconds is None
    assert pm.input_tokens is None
    assert pm.retry_rate is None
    assert pm.error_rate is None


def test_reduce_persona_sums_cache_tokens():
    entries = [
        {"prompt_tokens": 2, "completion_tokens": 40, "cache_read_tokens": 1000,
         "cache_creation_tokens": 0},
        {"prompt_tokens": 2, "completion_tokens": 60, "cache_read_tokens": 1000,
         "cache_creation_tokens": 500},
    ]
    pm = reduce_persona(entries)
    assert pm.cache_read_tokens == 2000
    assert pm.cache_creation_tokens == 500


def test_reduce_persona_cache_tokens_none_when_absent():
    # Legacy entries with no cache fields -> the sums stay None (absent != 0).
    entries = [{"prompt_tokens": 100, "completion_tokens": 40}]
    pm = reduce_persona(entries)
    assert pm.cache_read_tokens is None
    assert pm.cache_creation_tokens is None


# --------------------------------------------------------------------------- #
# interaction_parser: cache-token round-trip incl. legacy logs
# --------------------------------------------------------------------------- #


def test_parser_round_trips_cache_tokens_and_defaults_legacy(tmp_path: Path):
    log = tmp_path / "llm_interactions.jsonl"
    lines = [
        # New-format line carrying the cache fields.
        {"category": "persona_realism", "method": "judge", "step": "round_0",
         "prompt": "p", "raw_response": "r", "prompt_tokens": 2, "completion_tokens": 40,
         "cache_read_tokens": 1000, "cache_creation_tokens": 500},
        # Legacy line lacking the cache fields entirely -> parsed as None (no KeyError).
        {"category": "persona_realism", "method": "judge", "step": "round_1",
         "prompt": "p", "raw_response": "r", "prompt_tokens": 2, "completion_tokens": 60},
    ]
    with open(log, "w", encoding="utf-8") as fh:
        for rec in lines:
            fh.write(json.dumps(rec) + "\n")

    entries = parse_interactions(log)
    assert entries[0]["cache_read_tokens"] == 1000
    assert entries[0]["cache_creation_tokens"] == 500
    # Legacy line: keys present (normalised) and defaulted to None.
    assert entries[1]["cache_read_tokens"] is None
    assert entries[1]["cache_creation_tokens"] is None

    # The reduce layer sums across the mixed log (absent counts as absent, not 0).
    pm = reduce_persona(entries)
    assert pm.cache_read_tokens == 1000
    assert pm.cache_creation_tokens == 500


# --------------------------------------------------------------------------- #
# (c) cost.persona_cost
# --------------------------------------------------------------------------- #


def _pricing() -> PricingTable:
    return PricingTable(
        rates={
            "claude_haiku": (1.0, 5.0),
            "ollama_llama31_8b": (0.0, 0.0),
        },
        observed_date="2026-07-23",
        source="unit-test",
        currency="USD_per_1M_tokens",
    )


def test_persona_cost_priced_arithmetic():
    # 300 input * 1.0/1e6 + 100 output * 5.0/1e6 = 0.0003 + 0.0005 = 0.0008
    cost = persona_cost("claude_haiku", 300, 100, _pricing())
    assert cost == pytest.approx(0.0008)


def test_persona_cost_none_when_tokens_absent():
    assert persona_cost("claude_haiku", None, None, _pricing()) is None


def test_persona_cost_zero_for_ollama():
    assert persona_cost("ollama_llama31_8b", 1000, 2000, _pricing()) == pytest.approx(0.0)


def test_persona_cost_raises_when_tokened_but_unpriced():
    with pytest.raises(KeyError):
        persona_cost("some_unpriced_model", 100, 50, _pricing())


def _pricing_with_cache() -> PricingTable:
    return PricingTable(
        rates={"claude_haiku": (1.0, 5.0)},
        observed_date="2026-07-23",
        source="unit-test",
        currency="USD_per_1M_tokens",
        cache_multipliers={"read": 0.1, "write": 1.25},
    )


def test_persona_cost_without_cache_tokens_is_unchanged():
    # A pricing table WITH a cache block must still return the plain token-only
    # cost when no cache tokens are supplied (backward-compat with existing callers).
    priced = _pricing_with_cache()
    assert persona_cost("claude_haiku", 300, 100, priced) == pytest.approx(0.0008)
    # Explicit zeros are the same as omission.
    assert persona_cost(
        "claude_haiku", 300, 100, priced, cache_read_tokens=0, cache_creation_tokens=0
    ) == pytest.approx(0.0008)
    # None cache tokens (as summed from a persona with no cache telemetry) also gate off.
    assert persona_cost(
        "claude_haiku", 300, 100, priced, cache_read_tokens=None, cache_creation_tokens=None
    ) == pytest.approx(0.0008)


def test_persona_cost_with_cache_tokens_adds_multiplied_input():
    # base = 300*1/1e6 + 100*5/1e6 = 0.0008
    # cache read     = 1000 * 1.0 * 0.10 / 1e6 = 0.0001
    # cache creation =  500 * 1.0 * 1.25 / 1e6 = 0.000625
    cost = persona_cost(
        "claude_haiku", 300, 100, _pricing_with_cache(),
        cache_read_tokens=1000, cache_creation_tokens=500,
    )
    assert cost == pytest.approx(0.0008 + 0.0001 + 0.000625)


def test_persona_cost_cache_tokens_without_multipliers_raises():
    # Cache tokens supplied but the pricing config omitted the cache_multipliers
    # block -> fail-fast (never silently priced at a default).
    with pytest.raises(ValueError, match="cache_multipliers"):
        persona_cost("claude_haiku", 300, 100, _pricing(), cache_read_tokens=1000)


def test_real_pricing_config_has_cache_multipliers():
    table = load_pricing_table()
    assert table.cache_multipliers == {"read": 0.1, "write": 1.25}
    assert table.cache_mults() == (0.1, 1.25)


# --------------------------------------------------------------------------- #
# (d) combo_aggregator.aggregate_combo
# --------------------------------------------------------------------------- #


def test_aggregate_combo_per_metric_n_and_std():
    # Two personas contribute time (5s, 15s); only one contributes tokens/cost.
    p1 = PersonaMetrics(
        time_seconds=5.0, input_tokens=100, output_tokens=40, total_tokens=140,
        n_calls=2, retry_rate=0.0, error_rate=0.0,
    )
    p2 = PersonaMetrics(
        time_seconds=15.0, input_tokens=None, output_tokens=None, total_tokens=None,
        n_calls=3, retry_rate=0.5, error_rate=0.0,
    )
    personas = [("persona_0001", p1, 0.0008), ("persona_0002", p2, None)]

    summary = aggregate_combo("swedish", "claude_haiku", "all_pick", personas)

    assert summary.n_personas == 2
    assert summary.has_token_data is True
    # time: both personas contribute -> n=2, mean=10, std defined
    assert summary.metrics["time"]["n"] == 2
    assert summary.metrics["time"]["mean"] == pytest.approx(10.0)
    assert summary.metrics["time"]["std"] == pytest.approx(7.0710678, rel=1e-4)
    # input_tokens: only p1 contributes -> n=1, std None
    assert summary.metrics["input_tokens"]["n"] == 1
    assert summary.metrics["input_tokens"]["mean"] == pytest.approx(100.0)
    assert summary.metrics["input_tokens"]["std"] is None
    # cost: only p1 has a cost -> n=1
    assert summary.metrics["cost"]["n"] == 1
    assert summary.metrics["cost"]["mean"] == pytest.approx(0.0008)


def test_aggregate_combo_single_persona_std_none_and_skips():
    p1 = PersonaMetrics(
        time_seconds=None, input_tokens=None, output_tokens=None, total_tokens=None,
        n_calls=1, retry_rate=0.0, error_rate=0.0,
    )
    summary = aggregate_combo(
        "swedish", "claude_opus", "all_pick",
        [("persona_0001", p1, None)],
        prior_skipped=[{"slug": "s", "persona": "persona_0002", "reason": "no interaction file"}],
    )
    # calls: single contributor -> mean defined, std None
    assert summary.metrics["calls"]["n"] == 1
    assert summary.metrics["calls"]["std"] is None
    assert summary.has_token_data is False
    # time was None -> recorded as a skip, plus the prior skip carried through
    reasons = [s["reason"] for s in summary.skipped]
    assert any("timestamps" in r for r in reasons)
    assert any("no interaction file" in r for r in reasons)


def test_metric_names_is_single_source_of_truth():
    # Guard against re-listing drift: the report/chart layers import this tuple.
    assert METRIC_NAMES == (
        "time", "input_tokens", "output_tokens", "total_tokens",
        "calls", "retry_rate", "error_rate", "cost",
    )


# --------------------------------------------------------------------------- #
# pricing config loads (real config on disk)
# --------------------------------------------------------------------------- #


def test_real_pricing_config_loads():
    table = load_pricing_table()
    assert table.observed_date
    assert "claude_haiku" in table
    # ollama models are priced at a genuine zero (not absent).
    assert table.get("ollama_llama31_8b") == (0.0, 0.0)


# --------------------------------------------------------------------------- #
# (e) integration: summarize over a tiny 01_Raw fixture
# --------------------------------------------------------------------------- #

_TOKENED_SLUG = "swedish_all_pick_claude_haiku"
_TOKENLESS_SLUG = "swedish_all_pick_claude_opus"


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


def _tokened_entries() -> list[dict]:
    return [
        {
            "request_sent_at": "2026-07-23T10:00:00",
            "response_received_at": "2026-07-23T10:00:10",
            "prompt_tokens": 100,
            "completion_tokens": 40,
            "total_tokens": 140,
            "attempt": 1,
            "error": None,
        },
        {
            "request_sent_at": "2026-07-23T10:00:10",
            "response_received_at": "2026-07-23T10:00:20",
            "prompt_tokens": 200,
            "completion_tokens": 60,
            "total_tokens": 260,
            "attempt": 1,
            "error": None,
        },
    ]


def _tokenless_entries() -> list[dict]:
    # Genuinely-null token fields (data-driven gate), timestamps present.
    return [
        {"request_sent_at": "2026-07-23T11:00:00", "response_received_at": "2026-07-23T11:00:07", "attempt": 1},
        {"request_sent_at": "2026-07-23T11:00:07", "response_received_at": "2026-07-23T11:00:20", "attempt": 1},
    ]


def _build_raw_fixture(output_base: Path) -> None:
    raw = output_base / "01_Raw"
    # Tokened combo: two personas so std is defined.
    for pid in ("persona_0001", "persona_0002"):
        _write_jsonl(raw / _TOKENED_SLUG / pid / "llm_interactions.jsonl", _tokened_entries())
    # Token-less combo: one persona.
    _write_jsonl(raw / _TOKENLESS_SLUG / "persona_0001" / "llm_interactions.jsonl", _tokenless_entries())


def _cap_raw_fixture(output_base: Path, n: int = 100) -> None:
    """Run the real population_cap over every 01_Raw combo into the capped mirror.

    generation_metadata now reads the capped mirror exclusively (never 01_Raw), so the
    true pipeline order is cap -> summarize. ``n`` is deliberately larger than any
    combo's persona count, so every fixture persona is retained and the summarize
    assertions still hold over the full fixture.
    """
    raw = output_base / "01_Raw"
    cap_stage = analysis_output_dir("population_cap", output_base)
    for slug_dir in sorted(p for p in raw.iterdir() if p.is_dir()):
        cap_combo(slug_dir, n, 0, cap_stage / slug_dir.name)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_summarize_writes_csv_json_and_charts(tmp_path: Path):
    _build_raw_fixture(tmp_path)
    _cap_raw_fixture(tmp_path)
    written = summarize(output_base=tmp_path, countries=["swedish"], charts=True)

    assert "swedish" in written
    csv_path = written["swedish"]["csv"]
    json_path = written["swedish"]["json"]
    assert csv_path.is_file()
    assert json_path.is_file()

    # --- CSV columns: identity + <metric>_<stat> per metric + scalar columns ---
    rows = _read_csv(csv_path)
    header = set(rows[0].keys())
    for base in ("model", "method", "n_personas", "has_token_data"):
        assert base in header
    for metric in METRIC_NAMES:
        for suffix in DISTRIBUTION_STATS:  # mean, std, median, q1, q3, n
            assert f"{metric}_{suffix}" in header
    for scalar in SCALAR_METRIC_NAMES:  # latency_p95, latency_max, success_rate
        assert scalar in header

    by_model = {r["model"]: r for r in rows}
    assert set(by_model) == {"claude_haiku", "claude_opus"}

    # Tokened combo: token metrics + cost present.
    haiku = by_model["claude_haiku"]
    assert haiku["has_token_data"] == "True"
    assert haiku["input_tokens_mean"] != ""      # 300 per persona
    assert float(haiku["input_tokens_mean"]) == pytest.approx(300.0)
    assert float(haiku["output_tokens_mean"]) == pytest.approx(100.0)
    # cost per persona: 300*1e-6*price_in + 100*1e-6*price_out (claude_haiku = 1/5)
    assert float(haiku["cost_mean"]) == pytest.approx(300 * 1.0 / 1e6 + 100 * 5.0 / 1e6)
    assert int(haiku["time_n"]) == 2
    # Distribution stats: two personas each 300 input tokens -> median 300, q1/q3 defined.
    assert float(haiku["input_tokens_median"]) == pytest.approx(300.0)
    assert haiku["input_tokens_q1"] != ""
    assert haiku["input_tokens_q3"] != ""
    # Scalar diagnostics: no errors -> success_rate 1.0; no timing -> latency empty.
    assert float(haiku["success_rate"]) == pytest.approx(1.0)
    assert haiku["latency_p95"] == ""
    assert haiku["latency_max"] == ""

    # Token-less combo: token/cost gated to empty (None), time still present.
    opus = by_model["claude_opus"]
    assert opus["has_token_data"] == "False"
    assert opus["input_tokens_mean"] == ""
    assert opus["cost_mean"] == ""
    assert opus["time_mean"] != ""

    # --- JSON pricing provenance + structure ---
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["process"] == "generation_metadata"
    assert payload["country"] == "swedish"
    assert set(payload["pricing"]) >= {"observed_date", "source", "currency"}
    assert payload["metrics"] == list(METRIC_NAMES)
    assert payload["scalar_metrics"] == list(SCALAR_METRIC_NAMES)
    assert len(payload["combos"]) == 2

    # --- JSON: per-combo diagnostics block + scalar fields inside metrics ---
    combo = next(c for c in payload["combos"] if c["model"] == "claude_haiku")
    assert "diagnostics" in combo
    diag = combo["diagnostics"]
    assert diag["summary"]["total_entries"] == 4  # two personas x two calls
    assert "per_category" in diag and "value_diversity" in diag
    # Distribution stat set present per metric; scalar fields flat alongside.
    for stat in DISTRIBUTION_STATS:
        assert stat in combo["metrics"]["input_tokens"]
    for scalar in SCALAR_METRIC_NAMES:
        assert scalar in combo["metrics"]
    assert combo["metrics"]["success_rate"] == pytest.approx(1.0)

    # --- charts: a PNG+SVG pair per non-empty metric ---
    charts_dir = csv_path.parent / "charts"
    assert charts_dir.is_dir()
    pngs = list(charts_dir.glob("swedish_*.png"))
    assert pngs, "expected at least one metric heatmap"
    for png in pngs:
        assert png.with_suffix(".svg").is_file()


def test_summarize_force_vs_skip(tmp_path: Path):
    _build_raw_fixture(tmp_path)
    _cap_raw_fixture(tmp_path)

    first = summarize(output_base=tmp_path, countries=["swedish"], charts=False)
    csv_path = first["swedish"]["csv"]
    mtime_before = csv_path.stat().st_mtime_ns

    # Without force: existing output is skipped (nothing rewritten).
    second = summarize(output_base=tmp_path, countries=["swedish"], charts=False)
    assert "swedish" not in second
    assert csv_path.stat().st_mtime_ns == mtime_before

    # With force: recomputed and rewritten.
    third = summarize(output_base=tmp_path, countries=["swedish"], charts=False, force=True)
    assert "swedish" in third
    assert csv_path.stat().st_mtime_ns >= mtime_before
