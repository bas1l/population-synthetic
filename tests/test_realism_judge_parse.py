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
from population_synthetic.analysis.generation_metadata.pricing import load_pricing_table
from population_synthetic.analysis.persona_realism import judge, prompt
from population_synthetic.analysis.persona_realism.judge import (
    Issue,
    RoundVerdict,
    parse_round_verdict,
)
from population_synthetic.analysis.persona_realism.runner import (
    JudgeConfig,
    _default_client_factory,
)
from population_synthetic.analysis.utils.mapping_sentinel import UNMAPPED

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
# JudgeConfig.load + client factory -- config-driven subprocess timeout
# --------------------------------------------------------------------------

def test_judge_config_loads_timeout_seconds():
    cfg = JudgeConfig.load(_CONFIG_DIR)
    assert cfg.timeout_seconds == 600


def test_judge_config_default_model_is_sonnet():
    # Default switched Fable -> Sonnet (2026-07-24): Sonnet is the best coherence-judge
    # tier at low latency/cost; Fable remains a selectable option.
    cfg = JudgeConfig.load(_CONFIG_DIR)
    assert cfg.judge_model == "claude-sonnet-5"
    # The default must still be one of the offered dropdown options.
    assert cfg.judge_model in cfg.model_options


def test_all_dropdown_judge_models_are_priced():
    # Every selectable judge model (the RAW --model string) must have a pricing row,
    # or its cost lookup would fail-fast at run time (persona_cost joins on --model).
    cfg = JudgeConfig.load(_CONFIG_DIR)
    table = load_pricing_table()
    for model in cfg.model_options:
        price_in, price_out = table.get(model)  # KeyError (fail-fast) if unpriced
        assert price_in >= 0 and price_out >= 0
    # Pin the four current dropdown models explicitly as a regression guard.
    assert set(cfg.model_options) == {
        "claude-fable-5", "claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5",
    }


def test_default_client_factory_passes_timeout(monkeypatch):
    """The judge factory threads cfg.timeout_seconds into the client (no live CLI)."""
    import population_synthetic.clients.claude_code_client as ccc_mod

    captured: dict = {}

    class _FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(ccc_mod, "ClaudeCodeClient", _FakeClient)

    cfg = JudgeConfig.load(_CONFIG_DIR)
    _default_client_factory(cfg)

    assert captured["timeout"] == cfg.timeout_seconds
    assert captured["model_name"] == cfg.judge_model
    assert captured["default_config"] == {"temperature": cfg.temperature}


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


def test_render_persona_block_unmapped_axis_renders_token():
    # An analyzed axis genuinely absent from the persona (or an explicit UNMAPPED
    # sentinel) is TOLERATED and rendered as the token line, not raised.
    block = prompt.render_persona_block({"age_group": "25-34"}, ["age_group", "income"])
    assert block == f"age_group: 25-34\nincome: {UNMAPPED}"
    # An explicit sentinel value renders identically.
    block2 = prompt.render_persona_block({"sex": UNMAPPED}, ["sex"])
    assert block2 == f"sex: {UNMAPPED}"


def test_build_prompts_substitutes_only_persona_block():
    persona = {"sex": "male"}
    system_str, user_str = prompt.build_prompts(
        persona, ["sex"], "SYSTEM {keep}", "before {persona_block} after"
    )
    # system passed through verbatim (literal braces preserved)
    assert system_str == "SYSTEM {keep}"
    assert user_str == "before sex: male after"


# --------------------------------------------------------------------------
# prompt.py -- real mapped record shape (raw integer age, NO age_group key)
# --------------------------------------------------------------------------

# The Sweden analyzed axis exactly as ``scheme_attributes("swedish")`` yields it:
# it lists ``age_group`` (a derived axis), while a real mapped record stores the
# raw integer ``age`` instead. Rendering must derive age_group on demand rather
# than KeyError-ing on the absent ``age_group`` key.
_SWEDEN_ANALYZED_ATTRS = [
    "age_group",
    "biological_sex",
    "education_level",
    "employment_status",
    "socioeconomic_class",
    "parental_structure",
    "region",
    "civil_status",
    "industry_sector",
    "employment_type",
    "housing_tenure",
    "household_size",
    "income_source",
    "birth_country_detail",
]


def _real_shaped_sweden_persona() -> dict:
    """A real mapped record: raw integer ``age`` (65), NO ``age_group`` key."""
    return {
        "id": "real-000042",
        "age": 65,  # raw integer, as stored in 03_Analysis/mapping/*.json
        "biological_sex": "male",
        "education_level": "tertiary",
        "employment_status": "employed",
        "socioeconomic_class": "middle",
        "parental_structure": "couple_with_children",
        "region": "Stockholm",
        "civil_status": "married",
        "industry_sector": "health",
        "employment_type": "permanent",
        "housing_tenure": "owned",
        "household_size": 2,
        "income_source": "employment",
        "birth_country_detail": "Sweden",
    }


def test_render_persona_block_derives_age_group_from_raw_age():
    persona = _real_shaped_sweden_persona()
    assert "age_group" not in persona  # precondition: real record has no bin

    block = prompt.render_persona_block(persona, _SWEDEN_ANALYZED_ATTRS)

    # No KeyError, and the age_group line carries a derived bracket string
    # (a bin label such as "65-74"/"65+"), never the raw integer 65.
    age_group_line = next(ln for ln in block.splitlines() if ln.startswith("age_group:"))
    rendered_value = age_group_line.split(": ", 1)[1]
    assert rendered_value != "65"
    assert not rendered_value.isdigit()
    assert any(ch.isdigit() for ch in rendered_value)  # a bin string, e.g. "65-74"
    # Every analyzed axis is present exactly once.
    assert block.count("age_group:") == 1
    assert "biological_sex: male" in block


def test_build_prompts_real_shaped_persona_no_keyerror():
    persona = _real_shaped_sweden_persona()
    system_str, user_str = prompt.build_prompts(
        persona, _SWEDEN_ANALYZED_ATTRS, "SYS", "P: {persona_block}"
    )
    assert system_str == "SYS"
    assert "age_group:" in user_str
    assert "age: 65" not in user_str  # raw age never leaks into the block


def test_render_persona_block_missing_age_renders_unmapped_token():
    persona = _real_shaped_sweden_persona()
    del persona["age"]  # no raw age and no age_group -> genuinely absent
    # Tolerated: the age_group axis renders the UNMAPPED token instead of raising.
    block = prompt.render_persona_block(persona, _SWEDEN_ANALYZED_ATTRS)
    assert f"age_group: {UNMAPPED}" in block
