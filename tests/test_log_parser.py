"""Tests for log-line parsing, including the optional ``corr=`` suffix (Phase 4)."""

from __future__ import annotations

from population_synthetic.analysis.generation_metadata.log_parser import (
    _parse_corr,
    _split_log_line,
    _try_parse_call,
)

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


# --- Regression: the "_ElapsedFormatter" [+elapsed] suffix ------------------
#
# This is the bug the generation script's log formatter silently introduced:
# every real call line failed _RE_TIMESTAMP and all token/latency data was
# dropped for any run made with `generate_identities_parallel.py`.

def test_split_log_line_with_elapsed_prefix_parses():
    line = (
        "2026-07-06 15:45:27 [+1.2s] INFO: ollama call: model=m base_url=u "
        "elapsed_ms=500 prompt_tokens=100 completion_tokens=10"
    )
    ts, msg = _split_log_line(line)
    assert ts == "2026-07-06 15:45:27"
    assert msg == (
        "ollama call: model=m base_url=u elapsed_ms=500 "
        "prompt_tokens=100 completion_tokens=10"
    )


def test_split_log_line_without_elapsed_prefix_still_parses():
    line = (
        "2026-05-21 15:45:27 INFO: ollama call: model=m base_url=u "
        "elapsed_ms=500 prompt_tokens=100 completion_tokens=10"
    )
    ts, msg = _split_log_line(line)
    assert ts == "2026-05-21 15:45:27"
    assert msg is not None


def test_ollama_line_with_elapsed_prefix_end_to_end():
    line = (
        "2026-07-06 15:45:27 [+1.2s] INFO: ollama call: model=m base_url=u "
        "elapsed_ms=500 prompt_tokens=100 completion_tokens=10 corr=persona_00001:1"
    )
    ts, msg = _split_log_line(line)
    assert msg is not None
    rec = _try_parse_call(msg, ts)
    assert rec["provider"] == "ollama"
    assert rec["prompt_tokens"] == 100
    assert rec["completion_tokens"] == 10
    assert rec["persona_id"] == "persona_00001"
    assert rec["call_index"] == 1


# --- Claude line with prompt_tokens/completion_tokens (Phase 2) -------------

def test_parse_claude_with_tokens():
    msg = (
        "claude call: model=sonnet t_launch_ms=100 t_inference_ms=200 "
        "prompt_tokens=50 completion_tokens=20 corr=persona_00002:5"
    )
    rec = _try_parse_call(msg, _TS)
    assert rec["provider"] == "claude"
    assert rec["prompt_tokens"] == 50
    assert rec["completion_tokens"] == 20
    assert rec["persona_id"] == "persona_00002"
    assert rec["call_index"] == 5


def test_parse_claude_without_tokens_stays_none():
    msg = "claude call: model=sonnet t_launch_ms=100 t_inference_ms=200 corr=persona_00002:5"
    rec = _try_parse_call(msg, _TS)
    assert rec["prompt_tokens"] is None
    assert rec["completion_tokens"] is None


# --- Gemini call line --------------------------------------------------------

def test_parse_gemini_with_tokens_and_corr():
    msg = (
        "gemini call: model=gemini-2.5-flash elapsed_ms=750 "
        "prompt_tokens=42 completion_tokens=17 corr=persona_00003:2"
    )
    rec = _try_parse_call(msg, _TS)
    assert rec["provider"] == "gemini"
    assert rec["model"] == "gemini-2.5-flash"
    assert rec["elapsed_ms"] == 750.0
    assert rec["prompt_tokens"] == 42
    assert rec["completion_tokens"] == 17
    assert rec["persona_id"] == "persona_00003"
    assert rec["call_index"] == 2


def test_parse_gemini_without_corr_is_backward_compatible():
    msg = "gemini call: model=gemini-2.5-flash elapsed_ms=750 prompt_tokens=42 completion_tokens=17"
    rec = _try_parse_call(msg, _TS)
    assert rec["provider"] == "gemini"
    assert rec["persona_id"] is None
    assert rec["call_index"] is None
