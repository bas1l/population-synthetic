"""Round-trip test: the corr token the generator emits parses back to its key.

This ties the emit side (:mod:`clients.call_context`) to the parse side
(:mod:`analysis.log_parser`), proving the on-the-wire string format agrees.
"""

from __future__ import annotations

from population_synth.analysis.llm_metrics.per_run.log_parser import _try_parse_call
from population_synth.clients.call_context import format_corr_token, set_correlation

_TS = "2026-05-21 10:00:00"


def test_corr_token_roundtrips_through_log_parser():
    set_correlation("persona_00003", 7)
    token = format_corr_token()
    assert token == " corr=persona_00003:7"

    msg = (
        "ollama call: model=m base_url=u elapsed_ms=10 "
        "prompt_tokens=1 completion_tokens=1" + token
    )
    rec = _try_parse_call(msg, _TS)
    assert rec["persona_id"] == "persona_00003"
    assert rec["call_index"] == 7


def test_unset_or_incomplete_correlation_emits_empty_token():
    # Single-run path: persona_id is None -> no corr suffix, log line unchanged.
    set_correlation(None, 4)
    assert format_corr_token() == ""
