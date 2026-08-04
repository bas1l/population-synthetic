"""JSON extraction from responses that carry an inlined reasoning block.

Reasoning models emit their chain-of-thought as literal text inside the response
content, terminated by a bare ``</think>`` whose opening tag the observed model
never sends. The 2026-08-04 ``qwen/qwen3.5-flash-02-23`` run
(``swedish_02_all_generate_evaluate_random_pick_v2_openrouter_qwen35_flash``)
made 3492 calls, of which 3080 failed to parse, and the 11 that did *not* fail
were worse: the extractor scanned ~17 k characters of prose, found the prompt's
own schema sketch (not valid JSON), abandoned the object shape and returned a
throwaway ``[0, 1]`` quoted mid-thought. A list where the caller declared an
object then raised ``AttributeError`` inside the category -- outside every retry
boundary -- and killed the persona at its first attribute.

Both modes are pinned here against an excerpt of the response that produced
them, so the two properties that close them cannot silently regress:

- the reasoning block is removed *before* anything scans for JSON, and
- a JSON fragment quoted inside prose can never outrank the answer that follows
  it, whether that fragment is an unparseable object or a parseable array.

The unchanged-behaviour cases are equally load-bearing: every non-reasoning
provider in the sweep (claude, gemini, ollama) sends text with no ``</think>``
at all, and must take exactly the path it took before.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from population_synthetic.generators.synthetic.category import GenerateEvaluateRandomPickCategory
from population_synthetic.generators.synthetic.resolution_context import (
    ResolutionContext,
    _check_shape,
    _extract_json,
    _strip_reasoning,
)

# -- fixtures from the failing run -------------------------------------------

# Excerpted from `persona_00458/llm_interactions.jsonl`, call_index 1
# (category "age", step "distribution", 2026-08-04T10:31:07) of
# F:\liu-onedrive-nospecial-carac\_Teams\Gauss\02_Data\01_Raw\
#   swedish_02_all_generate_evaluate_random_pick_v2_openrouter_qwen35_flash
# The recorded response is 11 593 characters of near-identical restatement; the
# repetition is dropped here and the four features that made it fail are kept
# verbatim: the unparseable schema sketch the model quotes back from the prompt,
# the throwaway `[0,1]` in the sentence about the Beta support, the single bare
# `</think>`, and the real answer after it. That response was recorded with
# `parsed_value: [0, 1]` while it ends in `{"distribution": "uniform"}`.
REASONING_RESPONSE = """Thinking Process:

1.  **Analyze the Request:**
    *   Role: Demographic simulation engine for a Swedish population.
    *   Task: Generate a value for the 'age' category based on provided context.
    *   Constraint 1: Persona lives in Sweden.
    *   Constraint 2: Output must be ONLY valid JSON. No markdown, no explanation.
    *   Constraint 3: The specific format requested is
        `{"distribution": "normal"|"uniform"|"beta", "mean": <n>, "std": <n>}`.
        It says "Return JSON: {...}". It also mentions "(mean/std only for normal)".
    *   Since this is the *first* category, there is no prior context constraining the age.
    *   Swedish Population Data: The median age in Sweden is around 41 years.
    *   Range: 18 to 90.
    *   Distribution: Uniform.
    *   Regarding the `(mean/std only for normal)` clause: if I select uniform, I will omit them.

    *   Refinement: Should I lean towards a realistic distribution? Without context, Uniform holds.
    *   Let's ensure the JSON is valid.

    *   Final check on constraints:
        *   Only valid JSON.
        *   No markdown.
        *   Follow the specific output format requested in the prompt.
        *   Context: First category (no history).
        *   Logic: No preference -> Uniform.

    *   Wait, looking at the prompt again: "Return JSON:
        {"distribution": "normal"|"uniform"|"beta", "mean": <n>, "std": <n>}".
    *   Is the bare uniform spec sufficient? Yes, following the "(mean/std only for normal)" rule.

    *   Okay, generating JSON.

    *   Wait, I must ensure I don't output markdown code blocks (```json ... ```). Just the raw string.

    *   Wait, the JSON keys must match exactly what was requested. `distribution`, `mean`, `std`.
    *   If I use uniform, I skip `mean` and `std`.

    *   Wait, could I interpret "no preference" as "use uniform"? Yes.
    *   Okay, ready.

    *   Wait, is there any reason to pick Beta? Beta is good for bounded ranges [0,1] scaled.
        Normal is common. Uniform is safest for "no info".

    *   Wait, should the min/max go in the JSON? The prompt didn't ask for them.

    *   Final check: Valid JSON.
</think>

{
  "distribution": "uniform"
}"""

# The same response with the closing tag removed: the reasoning is then
# indistinguishable from ordinary prose, so the answer can only be recovered by
# the last-first balanced-span scan. This is the direct regression pin for
# `'list' object has no attribute 'get'` -- the prose still carries both the
# unparseable sketch and the parseable `[0,1]`.
REASONING_RESPONSE_UNTERMINATED = REASONING_RESPONSE.replace("</think>\n", "")

# Only a reasoning block, cut off at the token ceiling before the answer. Carries
# the unparseable sketch and nothing else that could be mistaken for an answer.
TRUNCATED_REASONING = """Thinking Process:

1.  **Analyze the Request:**
    *   Constraint 3: The specific format requested is
        `{"distribution": "normal"|"uniform"|"beta", "mean": <n>, "std": <n>}`.
    *   Okay, generating JSON. Wait, I need to"""

# The schema the distribution call site declares. Only its `type` is load-bearing
# for the shape guard; the properties are carried so the fixture stays a real one.
DISTRIBUTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"distribution": {"type": "string", "enum": ["normal", "uniform", "beta"]}},
    "required": ["distribution"],
}

NUMERIC_SCHEMA = {"description": "Age in years.", "min": 18, "max": 99, "type": "integer"}
CONTEXT_BLOCK = "age: 34\nbiological_sex: female"


# -- test doubles ------------------------------------------------------------


class _StubClient:
    """Replays scripted raw responses, repeating the last one once they run out.

    Repeating rather than raising is what lets one scripted response drive a whole
    retry budget: the failure being tested is a *deterministic* one, where every
    attempt gets the identical text back.
    """

    def __init__(self, *responses: str) -> None:
        self._responses = list(responses)
        self.calls = 0
        self.last_metadata: dict[str, Any] = {"provider": "stub", "model": "reasoning-stub"}

    def generate_content(self, prompt: str, system_instruction: str = "", **kwargs: Any) -> str:
        self.calls += 1
        return self._responses[min(self.calls - 1, len(self._responses) - 1)]


class _RecordingCollector:
    """Holds the telemetry entries in memory instead of writing them as JSONL."""

    def __init__(self) -> None:
        self.entries: list[Any] = []

    def record(self, entry: Any) -> None:
        self.entries.append(entry)


def _context(client: _StubClient, collector: _RecordingCollector | None = None) -> ResolutionContext:
    """A context on its defaults -- note ``use_structured_output`` stays off.

    That is the configuration the failing run used, and the one the shape guard
    must still fire in: an unconstrained provider is precisely the one that
    returns the wrong shape.
    """
    return ResolutionContext(
        client,
        system_instruction="You are a demographic simulation engine.",
        persona_id="persona_00458",
        interaction_collector=collector,
    )


# -- reasoning-block strip ---------------------------------------------------


def test_reasoning_prose_then_the_answer_yields_the_answer():
    assert _extract_json(REASONING_RESPONSE) == {"distribution": "uniform"}


def test_a_stray_array_in_prose_cannot_outrank_the_trailing_object():
    """The regression pin for ``'list' object has no attribute 'get'``.

    With no closing tag the whole response is scanned, so the unparseable schema
    sketch and the parseable ``[0,1]`` are both in play -- exactly the state that
    used to record a list as the persona's age distribution.
    """
    assert _extract_json(REASONING_RESPONSE_UNTERMINATED) == {"distribution": "uniform"}


def test_a_paired_think_wrapper_yields_the_trailing_object():
    text = '<think>\nWeighing normal against uniform.\n</think>\n{"distribution": "beta"}'
    assert _extract_json(text) == {"distribution": "beta"}


def test_the_payload_is_taken_after_the_last_closing_tag():
    text = (
        'First pass, discarded.</think>\n{"distribution": "normal"}\n'
        'Second pass.</think>\n{"distribution": "uniform"}'
    )
    assert _extract_json(text) == {"distribution": "uniform"}


def test_a_closing_tag_with_nothing_after_it_raises():
    with pytest.raises(json.JSONDecodeError):
        _extract_json("Reasoning that never reached an answer.</think>   \n")


def test_json_before_a_stray_closing_tag_is_still_extracted():
    """The empty-payload fallback: a model that answered first must not be lost."""
    assert _extract_json('{"distribution": "uniform"}\nthinking aloud</think>  \n') == {
        "distribution": "uniform"
    }


def test_text_without_a_closing_tag_is_returned_untouched():
    """Non-reasoning providers (claude, gemini, ollama) take the identical path."""
    text = 'Sure!\n```json\n{"value": 42}\n```'
    assert _strip_reasoning(text) == text


# -- unchanged extraction behaviour ------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"value": 42}', {"value": 42}),
        ('```json\n{"value": 42}\n```', {"value": 42}),
        ('Here you go:\n```\n{"value": 42}\n```\n', {"value": 42}),
        ('{"outer": {"inner": {"value": 42}}}', {"outer": {"inner": {"value": 42}}}),
        ('prefix {"outer": {"inner": 42}} suffix', {"outer": {"inner": 42}}),
        ("[1, 2, 3]", [1, 2, 3]),
        ("The candidates are [1, 2, 3] as listed.", [1, 2, 3]),
    ],
)
def test_extraction_paths_that_predate_the_reasoning_strip(text, expected):
    assert _extract_json(text) == expected


def test_a_brace_inside_a_string_value_does_not_truncate_the_span():
    assert _extract_json('noise {"note": "a } brace"} noise') == {"note": "a } brace"}


def test_no_json_anywhere_raises():
    with pytest.raises(json.JSONDecodeError):
        _extract_json("I would rather not answer that.")


# -- edge cases --------------------------------------------------------------


def test_a_truncated_reasoning_block_with_no_answer_raises():
    with pytest.raises(json.JSONDecodeError):
        _extract_json(TRUNCATED_REASONING)


def test_an_unbalanced_object_after_the_tag_raises():
    """No balanced span and no array: the scan yields nothing and the call retries."""
    with pytest.raises(json.JSONDecodeError):
        _extract_json('Reasoning.</think>\n{"distribution": "unifo')


# -- shape guard -------------------------------------------------------------


def test_a_list_against_a_declared_object_is_a_decode_error():
    with pytest.raises(json.JSONDecodeError, match="declared JSON object"):
        _check_shape([0, 1], DISTRIBUTION_SCHEMA)


def test_a_dict_against_a_declared_object_passes():
    assert _check_shape({"distribution": "uniform"}, DISTRIBUTION_SCHEMA) is None


def test_a_dict_against_a_declared_array_is_a_decode_error():
    with pytest.raises(json.JSONDecodeError, match="declared JSON array"):
        _check_shape({"distribution": "uniform"}, {"type": "array"})


def test_no_schema_imposes_no_constraint():
    assert _check_shape([0, 1], None) is None


def test_a_declared_type_outside_object_and_array_imposes_no_constraint():
    assert _check_shape([0, 1], {"type": "string"}) is None
    assert _check_shape([0, 1], {"type": ["object", "null"]}) is None


# -- call_json integration ---------------------------------------------------


def test_a_wrong_shaped_response_spends_the_budget_instead_of_killing_the_persona():
    """A list where an object was declared costs three attempts, not a persona.

    Before the guard this parsed cleanly, escaped ``call_json``'s ``except`` tuple
    as an ``AttributeError`` raised inside the category, and ended the run at the
    first attribute.
    """
    client = _StubClient("[0, 1]")
    collector = _RecordingCollector()
    ctx = _context(client, collector)

    with pytest.raises(ValueError, match="after 3 attempts"):
        ctx.call_json(
            "Specify a probability distribution for 'age'.",
            response_schema=DISTRIBUTION_SCHEMA,
            category="age", method="generate_evaluate_random_pick", step="distribution",
        )

    assert client.calls == 3
    assert len(collector.entries) == 3
    assert {e.error_category for e in collector.entries} == {"invalid_response"}
    assert all(e.step == "distribution_retry" for e in collector.entries)
    assert all("JSONDecodeError" in e.error for e in collector.entries)


def test_a_reasoning_response_succeeds_on_the_first_attempt():
    client = _StubClient(REASONING_RESPONSE)
    collector = _RecordingCollector()
    ctx = _context(client, collector)

    value = ctx.call_json(
        "Specify a probability distribution for 'age'.",
        response_schema=DISTRIBUTION_SCHEMA,
        category="age", method="generate_evaluate_random_pick", step="distribution",
    )

    assert value == {"distribution": "uniform"}
    assert client.calls == 1
    assert len(collector.entries) == 1
    entry = collector.entries[0]
    assert entry.parsed_value == {"distribution": "uniform"}
    assert entry.attempt == 1
    assert entry.error is None
    assert entry.persona_id == "persona_00458"


def test_numeric_distribution_resolves_a_value_in_bounds_against_a_reasoning_client():
    """End-to-end over the call site that the failing run crashed in."""
    ctx = _context(_StubClient(REASONING_RESPONSE))
    value = GenerateEvaluateRandomPickCategory("age", NUMERIC_SCHEMA).resolve(CONTEXT_BLOCK, ctx)
    assert isinstance(value, int)
    assert NUMERIC_SCHEMA["min"] <= value <= NUMERIC_SCHEMA["max"]
