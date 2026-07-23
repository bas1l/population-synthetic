"""Unit tests for the persona-realism judge parse boundary and prompt rendering.

The parser (``judge.parse_round_verdict``) is the single fail-loud normalization
point: canonical JSON must yield a ``RoundVerdict``; every malformed or
contract-violating shape must RAISE. No live CLI calls are made -- raw strings
are fed to the parser directly, and the runner is exercised with a stub client.
"""

from __future__ import annotations

import json

import pytest

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.persona_realism import judge, prompt
from population_synthetic.analysis.persona_realism.judge import (
    Issue,
    RoundVerdict,
    parse_round_verdict,
)

_CONFIG_DIR = PROJECT_ROOT / "config" / "analysis" / "persona_realism"


# --------------------------------------------------------------------------
# judge.parse_round_verdict -- canonical happy paths
# --------------------------------------------------------------------------

def test_parse_canonical_possible_verdict():
    raw = json.dumps({
        "reasoning": "an ordinary profile",
        "can_exist": True,
        "typicality": 8,
        "issues": [
            {"attributes": ["age_group", "income"], "severity": "S1",
             "explanation": "slightly high for the age"},
        ],
    })
    verdict = parse_round_verdict(raw)
    assert isinstance(verdict, RoundVerdict)
    assert verdict.can_exist is True
    assert verdict.typicality == 8
    assert verdict.reasoning == "an ordinary profile"
    assert verdict.issues == (
        Issue(attributes=("age_group", "income"), severity="S1",
              explanation="slightly high for the age"),
    )
    # issues is an immutable tuple, not a list
    assert isinstance(verdict.issues, tuple)


def test_parse_canonical_impossible_verdict():
    raw = json.dumps({
        "can_exist": False,
        "typicality": None,
        "issues": [
            {"attributes": ["age_group", "education_level"], "severity": "S3",
             "explanation": "doctorate too young"},
        ],
    })
    verdict = parse_round_verdict(raw)
    assert verdict.can_exist is False
    assert verdict.typicality is None
    assert verdict.issues[0].severity == "S3"


def test_parse_empty_issues_list_allowed_when_possible():
    raw = json.dumps({"can_exist": True, "typicality": 10, "issues": []})
    verdict = parse_round_verdict(raw)
    assert verdict.issues == ()


@pytest.mark.parametrize("boundary", [0, 10])
def test_parse_typicality_boundaries(boundary):
    raw = json.dumps({"can_exist": True, "typicality": boundary, "issues": []})
    assert parse_round_verdict(raw).typicality == pytest.approx(boundary)


def test_parse_tolerates_code_fence():
    inner = json.dumps({"can_exist": True, "typicality": 5, "issues": []})
    raw = f"```json\n{inner}\n```"
    assert parse_round_verdict(raw).typicality == 5


# --------------------------------------------------------------------------
# judge.parse_round_verdict -- contract violations must RAISE
# --------------------------------------------------------------------------

def test_malformed_json_raises():
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_round_verdict("{not json at all")


def test_empty_response_raises():
    with pytest.raises(ValueError, match="empty response"):
        parse_round_verdict("   ")


def test_non_object_json_raises():
    with pytest.raises(ValueError, match="must be a JSON object"):
        parse_round_verdict("[1, 2, 3]")


def test_missing_can_exist_raises():
    raw = json.dumps({"typicality": 5, "issues": []})
    with pytest.raises(ValueError, match="'can_exist'"):
        parse_round_verdict(raw)


def test_can_exist_not_bool_raises():
    raw = json.dumps({"can_exist": "yes", "typicality": 5, "issues": []})
    with pytest.raises(ValueError, match="must be a boolean"):
        parse_round_verdict(raw)


def test_typicality_out_of_range_raises():
    raw = json.dumps({"can_exist": True, "typicality": 11, "issues": []})
    with pytest.raises(ValueError, match="out of range"):
        parse_round_verdict(raw)


def test_typicality_negative_raises():
    raw = json.dumps({"can_exist": True, "typicality": -1, "issues": []})
    with pytest.raises(ValueError, match="out of range"):
        parse_round_verdict(raw)


def test_typicality_null_when_possible_raises():
    raw = json.dumps({"can_exist": True, "typicality": None, "issues": []})
    with pytest.raises(ValueError, match="must be an integer"):
        parse_round_verdict(raw)


def test_typicality_non_null_when_impossible_raises():
    raw = json.dumps({
        "can_exist": False, "typicality": 3,
        "issues": [{"attributes": ["a", "b"], "severity": "S3", "explanation": "x"}],
    })
    with pytest.raises(ValueError, match="must be null"):
        parse_round_verdict(raw)


def test_typicality_bool_rejected():
    raw = json.dumps({"can_exist": True, "typicality": True, "issues": []})
    with pytest.raises(ValueError, match="must be an integer"):
        parse_round_verdict(raw)


def test_typicality_float_rejected():
    # json numbers may be float; a non-integer typicality is a contract violation.
    raw = '{"can_exist": true, "typicality": 5.5, "issues": []}'
    with pytest.raises(ValueError, match="must be an integer"):
        parse_round_verdict(raw)


def test_missing_issues_raises():
    raw = json.dumps({"can_exist": True, "typicality": 5})
    with pytest.raises(ValueError, match="'issues'"):
        parse_round_verdict(raw)


def test_issues_not_list_raises():
    raw = json.dumps({"can_exist": True, "typicality": 5, "issues": {"a": 1}})
    with pytest.raises(ValueError, match="must be a list"):
        parse_round_verdict(raw)


def test_bad_severity_raises():
    raw = json.dumps({
        "can_exist": True, "typicality": 5,
        "issues": [{"attributes": ["a", "b"], "severity": "S9", "explanation": "x"}],
    })
    with pytest.raises(ValueError, match="invalid severity"):
        parse_round_verdict(raw)


def test_missing_severity_raises():
    raw = json.dumps({
        "can_exist": True, "typicality": 5,
        "issues": [{"attributes": ["a", "b"], "explanation": "x"}],
    })
    with pytest.raises(ValueError, match="invalid severity"):
        parse_round_verdict(raw)


def test_issue_attributes_wrong_length_raises():
    raw = json.dumps({
        "can_exist": True, "typicality": 5,
        "issues": [{"attributes": ["a", "b", "c"], "severity": "S1", "explanation": "x"}],
    })
    with pytest.raises(ValueError, match="exactly two attributes"):
        parse_round_verdict(raw)


def test_issue_attributes_non_string_raises():
    raw = json.dumps({
        "can_exist": True, "typicality": 5,
        "issues": [{"attributes": ["a", 3], "severity": "S1", "explanation": "x"}],
    })
    with pytest.raises(ValueError, match="must be strings"):
        parse_round_verdict(raw)


def test_impossible_without_s3_raises():
    # can_exist false but the only issue is S2 -> contract violation.
    raw = json.dumps({
        "can_exist": False, "typicality": None,
        "issues": [{"attributes": ["a", "b"], "severity": "S2", "explanation": "x"}],
    })
    with pytest.raises(ValueError, match="S3"):
        parse_round_verdict(raw)


# --------------------------------------------------------------------------
# judge.judge_persona -- one call via a stub client (no live CLI)
# --------------------------------------------------------------------------

class _StubClient:
    def __init__(self, response: str):
        self._response = response
        self.calls: list[dict] = []

    def generate_content(self, prompt_str: str, **kwargs) -> str:
        self.calls.append({"prompt": prompt_str, **kwargs})
        return self._response


def test_judge_persona_passes_model_and_system():
    resp = json.dumps({"can_exist": True, "typicality": 7, "issues": []})
    client = _StubClient(resp)
    verdict = judge.judge_persona(client, "SYS", "USER", "claude-fable-5")
    assert verdict.typicality == 7
    assert client.calls[0]["model"] == "claude-fable-5"
    assert client.calls[0]["system_instruction"] == "SYS"
    assert client.calls[0]["prompt"] == "USER"


# --------------------------------------------------------------------------
# prompt.py -- template parsing + persona rendering
# --------------------------------------------------------------------------

def test_load_real_prompt_template_splits_sections():
    # Regression guard: the real template mentions the sentinels inside its header
    # comment; exact-line matching must ignore those and split on the real lines.
    system_str, user_tmpl = prompt.load_prompt_template(_CONFIG_DIR / "judge_prompt.md")
    assert system_str.startswith("You are a careful demographic realism judge")
    assert "<!-- SYSTEM -->" not in system_str
    assert "<!-- USER -->" not in user_tmpl
    assert user_tmpl.count("{persona_block}") == 1
    # The system section's literal JSON-schema braces must survive verbatim.
    assert '"can_exist"' in system_str


def test_parse_template_missing_sentinel_raises():
    with pytest.raises(ValueError, match="SYSTEM"):
        prompt.parse_prompt_template("<!-- USER -->\n{persona_block}\n")


def test_parse_template_missing_placeholder_raises():
    text = "<!-- SYSTEM -->\nsome system\n<!-- USER -->\nno placeholder here\n"
    with pytest.raises(ValueError, match="persona_block"):
        prompt.parse_prompt_template(text)


def test_parse_template_duplicate_placeholder_raises():
    text = "<!-- SYSTEM -->\nsys\n<!-- USER -->\n{persona_block}{persona_block}\n"
    with pytest.raises(ValueError, match="exactly one"):
        prompt.parse_prompt_template(text)


def test_render_persona_block_orders_by_analyzed_attrs():
    persona = {"age_group": "25-34", "sex": "female", "birth_location": "SE"}
    block = prompt.render_persona_block(persona, ["sex", "age_group"])
    assert block == "sex: female\nage_group: 25-34"
    # birth_location (deprecated / not in analyzed list) is excluded
    assert "birth_location" not in block


def test_render_persona_block_missing_axis_raises():
    with pytest.raises(KeyError, match="income"):
        prompt.render_persona_block({"age_group": "25-34"}, ["age_group", "income"])


def test_build_prompts_substitutes_only_persona_block():
    persona = {"sex": "male"}
    system_str, user_str = prompt.build_prompts(
        persona, ["sex"], "SYSTEM {keep}", "before {persona_block} after"
    )
    # system passed through verbatim (literal braces preserved)
    assert system_str == "SYSTEM {keep}"
    assert user_str == "before sex: male after"
