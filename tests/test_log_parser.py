"""Tests for log-line parsing, including the optional ``corr=`` suffix (Phase 4)."""

from __future__ import annotations

from population_synthetic.analysis.llm_metrics.per_run.log_parser import _parse_corr, _try_parse_call

_TS = "2026-05-21 10:00:00"


def test_parse_ollama_with_corr():
    msg = (
        "ollama call: model=m base_url=u elapsed_ms=500 "
        "prompt_tokens=100 completion_tokens=10 corr=persona_00001:3"
    )
    rec = _try_parse_call(msg, _TS)
    assert rec["provider"] == "ollama"
    assert rec["prompt_tokens"] == 100
    assert rec["completion_tokens"] == 10
    assert rec["persona_id"] == "persona_00001"
    assert rec["call_index"] == 3


def test_parse_ollama_without_corr_is_backward_compatible():
    msg = "ollama call: model=m base_url=u elapsed_ms=500 prompt_tokens=100 completion_tokens=10"
    rec = _try_parse_call(msg, _TS)
    assert rec["prompt_tokens"] == 100
    assert rec["persona_id"] is None
    assert rec["call_index"] is None


def test_parse_openai_compat_with_corr():
    msg = (
        "openai_compat call: model=gpt base_url=u elapsed_ms=250 "
        "prompt_tokens=5 completion_tokens=2 corr=persona_00007:11"
    )
    rec = _try_parse_call(msg, _TS)
    assert rec["provider"] == "openai_compat"
    assert rec["persona_id"] == "persona_00007"
    assert rec["call_index"] == 11


def test_parse_claude_with_corr():
    msg = "claude call: model=sonnet t_launch_ms=100 t_inference_ms=200 corr=persona_00002:5"
    rec = _try_parse_call(msg, _TS)
    assert rec["provider"] == "claude"
    assert rec["elapsed_ms"] == 300.0
    assert rec["prompt_tokens"] is None
    assert rec["persona_id"] == "persona_00002"
    assert rec["call_index"] == 5


def test_parse_corr_helper():
    assert _parse_corr("persona_00001:7") == ("persona_00001", 7)
    assert _parse_corr(None) == (None, None)
    assert _parse_corr("") == (None, None)
    assert _parse_corr("nocolon") == (None, None)
