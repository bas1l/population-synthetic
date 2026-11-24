"""The four generation methods, each exercised as an independent class.

Before ``Category`` existed the methods were branches of an ``if/elif`` chain over
a ``method`` string, so none could be constructed, prompted or asserted on without
running a whole persona. These tests are the coverage that dispatch made
impossible: each class is built from a schema fragment, resolved against a fake
call seam holding no client, and checked on three axes -- the value it returns, the
telemetry labels it emits, and the exact bytes of every prompt it renders.

The prompt goldens are the load-bearing part. They were captured from the
pre-refactor implementation (``git show`` of the pre-Phase-2
``identity_generator_configurable.py``) and must not be "corrected" to match new
output: the benchmark compares runs made months apart, so a silent wording change
invalidates every earlier result rather than improving a later one.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import yaml

from population_synthetic.generators.synthetic.category import (
    _METHOD_MAP,
    GenerateEvaluatePickCategory,
    GenerateEvaluateRandomPickCategory,
    GeneratePickCategory,
    PickCategory,
    build_categories,
    build_category,
)
from population_synthetic.generators.synthetic.identity_generator_configurable import (
    IdentityGeneratorConfigurable,
)

# One numeric and one categorical schema fragment, plus the rendered context block
# and candidate list the goldens below were captured with. Changing any of them
# invalidates the goldens.
CATEGORICAL_SCHEMA = {"description": "Employment status of the person."}
NUMERIC_SCHEMA = {"description": "Age in years.", "min": 18, "max": 99, "type": "integer"}
CONTEXT_BLOCK = "age: 34\nbiological_sex: female"
CANDIDATES = ["employed", "unemployed", "student"]
WEIGHTS = [0.6, 0.3, 0.1]

# Verbatim output of the pre-refactor prompt builders. See the module docstring.
GOLDEN_PROMPTS = {
    "pick_categorical": (
        "Context:\nage: 34\nbiological_sex: female\n\n"
        "Given the context above, pick a single appropriate value for 'employment_status'. "
        "Employment status of the person. "
        'Return JSON: {"value": "<your choice>"}. No explanation.'
    ),
    "pick_numeric": (
        "Context:\nage: 34\nbiological_sex: female\n\n"
        "Given the context above, pick a single integer for 'age' between 18 and 99. "
        "Age in years. "
        'Return JSON: {"value": <number>}. No explanation.'
    ),
    "enumerate_categorical": (
        "Context:\nage: 34\nbiological_sex: female\n\n"
        "Given the context above, list up to 20 of the most plausible candidate values "
        "for 'employment_status' given the context. "
        "Prioritize the most realistic and likely options. "
        "Employment status of the person. "
        'Return JSON: {"candidates": ["value1", ...]}. No duplicates.'
    ),
    "enumerate_numeric": (
        "Context:\nage: 34\nbiological_sex: female\n\n"
        "Given the context above, list all plausible candidate numbers for 'age' "
        "between 18 and 99. "
        "Age in years. "
        'Return JSON: {"candidates": [n1, n2, ...]}.'
    ),
    "evaluate": (
        "Context:\nage: 34\nbiological_sex: female\n\n"
        "Assign probability weights to these 3 candidates for 'employment_status' "
        "given the context. "
        "Weights must sum to 1.0. "
        "You MUST return exactly 3 weights. "
        'Return JSON: {"weights": [0.x, 0.y, ...]} in the same order as candidates: '
        "['employed', 'unemployed', 'student']."
    ),
    "select_unweighted": (
        "Context:\nage: 34\nbiological_sex: female\n\n"
        "From the following candidates for 'employment_status', pick the single most "
        "appropriate value given the context. "
        'Return JSON: {"value": "<chosen>"}. '
        "Candidates: ['employed', 'unemployed', 'student']."
    ),
    "select_weighted": (
        "Context:\nage: 34\nbiological_sex: female\n\n"
        "From the following candidates for 'employment_status' -- each paired with the "
        "probability you assigned it -- pick the single most appropriate value given the "
        "context and those probabilities. "
        'Return JSON: {"value": "<chosen>"}. '
        'Candidates: {"employed": 0.6, "unemployed": 0.3, "student": 0.1}.'
    ),
    "numeric_distribution": (
        "Context:\nage: 34\nbiological_sex: female\n\n"
        "Specify a probability distribution for 'age' between 18 and 99 given the context. "
        "Age in years. "
        'Return JSON: {"distribution": "normal"|"uniform"|"beta", "mean": <n>, "std": <n>} '
        "(mean/std only for normal). Use 'uniform' for no preference."
    ),
}


class FakeContext:
    """A call seam with no client, no telemetry and no filesystem.

    Duck-typed rather than a ``ResolutionContext`` subclass on purpose: a category
    must depend on the *shape* of the seam (``call_json`` + ``retry_until_success``)
    and on nothing the real context happens to own.
    """

    def __init__(self, answers: dict[str | None, Any], *, retry_until_success: bool = False) -> None:
        self.answers = answers
        self.retry_until_success = retry_until_success
        self.prompts: list[str] = []
        self.labels: list[tuple[str, str, str]] = []  # (category, method, step)

    def call_json(
        self,
        prompt: str,
        *,
        expected_key: str | None = None,
        response_schema: dict | None = None,
        category: str = "",
        method: str = "",
        step: str = "",
    ) -> Any:
        self.prompts.append(prompt)
        self.labels.append((category, method, step))
        return self.answers[expected_key]


def _categorical_answers() -> dict[str | None, Any]:
    return {"value": "employed", "candidates": list(CANDIDATES), "weights": list(WEIGHTS)}


# -- construction ------------------------------------------------------------


@pytest.mark.parametrize(
    "category_class",
    [PickCategory, GeneratePickCategory, GenerateEvaluatePickCategory,
     GenerateEvaluateRandomPickCategory],
)
def test_every_method_is_constructible_on_its_own(category_class):
    category = category_class("employment_status", CATEGORICAL_SCHEMA, depends_on=["age"])
    assert category.name == "employment_status"
    assert category.schema is CATEGORICAL_SCHEMA
    assert category.depends_on == ("age",)
    # The method token is the class's own identity, and the registry agrees with it.
    assert _METHOD_MAP[category.method] is category_class


def test_method_map_covers_exactly_the_implemented_methods():
    assert set(_METHOD_MAP) == {
        "pick", "generate_pick", "generate_evaluate_pick", "generate_evaluate_random_pick"
    }


# -- resolution against a fake seam ------------------------------------------


def test_pick_resolves_in_one_call():
    ctx = FakeContext(_categorical_answers())
    value = PickCategory("employment_status", CATEGORICAL_SCHEMA).resolve(CONTEXT_BLOCK, ctx)
    assert value == "employed"
    assert ctx.labels == [("employment_status", "pick", "pick")]


def test_generate_pick_enumerates_then_selects():
    ctx = FakeContext(_categorical_answers())
    value = GeneratePickCategory("employment_status", CATEGORICAL_SCHEMA).resolve(CONTEXT_BLOCK, ctx)
    assert value == "employed"
    assert [step for _, _, step in ctx.labels] == ["enumerate", "select"]


def test_generate_evaluate_pick_weights_before_selecting():
    ctx = FakeContext(_categorical_answers())
    value = GenerateEvaluatePickCategory("employment_status", CATEGORICAL_SCHEMA).resolve(
        CONTEXT_BLOCK, ctx
    )
    assert value == "employed"
    assert [step for _, _, step in ctx.labels] == ["enumerate", "evaluate", "select"]


def test_generate_evaluate_random_pick_samples_instead_of_selecting():
    ctx = FakeContext(_categorical_answers())
    value = GenerateEvaluateRandomPickCategory("employment_status", CATEGORICAL_SCHEMA).resolve(
        CONTEXT_BLOCK, ctx
    )
    # The last step is arithmetic, not a call: no select prompt is ever sent.
    assert [step for _, _, step in ctx.labels] == ["enumerate", "evaluate"]
    assert value in CANDIDATES


def test_generate_evaluate_random_pick_draws_a_numeric_within_bounds():
    ctx = FakeContext({None: {"distribution": "uniform"}})
    value = GenerateEvaluateRandomPickCategory("age", NUMERIC_SCHEMA).resolve(CONTEXT_BLOCK, ctx)
    assert [step for _, _, step in ctx.labels] == ["distribution"]
    assert isinstance(value, int)
    assert NUMERIC_SCHEMA["min"] <= value <= NUMERIC_SCHEMA["max"]


@pytest.mark.parametrize(
    ("category_class", "answer", "expected"),
    [
        (PickCategory, 140, 99),          # above the ceiling
        (PickCategory, 3, 18),            # below the floor
        (PickCategory, 33.6, 34),         # rounded to the declared integer type
        (GeneratePickCategory, 140, 99),
    ],
)
def test_numeric_answers_are_clamped_into_the_declared_bounds(category_class, answer, expected):
    ctx = FakeContext({"value": answer, "candidates": [20, 30], "weights": [0.5, 0.5]})
    assert category_class("age", NUMERIC_SCHEMA).resolve(CONTEXT_BLOCK, ctx) == expected


def test_weight_count_mismatch_beyond_tolerance_is_retried_then_raises():
    # Three candidates, one weight: far outside the 10% reconcile tolerance, so the
    # evaluate step is re-asked until the budget runs out rather than silently padded.
    ctx = FakeContext({"candidates": list(CANDIDATES), "weights": [1.0], "value": "employed"})
    with pytest.raises(ValueError, match="Weight/candidate count mismatch"):
        GenerateEvaluatePickCategory("employment_status", CATEGORICAL_SCHEMA).resolve(
            CONTEXT_BLOCK, ctx
        )
    assert [step for _, _, step in ctx.labels].count("evaluate") == 3


# -- prompt goldens ----------------------------------------------------------


def test_pick_prompts_are_byte_identical_to_the_pre_refactor_builder():
    categorical = FakeContext(_categorical_answers())
    PickCategory("employment_status", CATEGORICAL_SCHEMA).resolve(CONTEXT_BLOCK, categorical)
    assert categorical.prompts == [GOLDEN_PROMPTS["pick_categorical"]]

    numeric = FakeContext({"value": 34})
    PickCategory("age", NUMERIC_SCHEMA).resolve(CONTEXT_BLOCK, numeric)
    assert numeric.prompts == [GOLDEN_PROMPTS["pick_numeric"]]


def test_generate_pick_prompts_are_byte_identical_to_the_pre_refactor_builder():
    ctx = FakeContext(_categorical_answers())
    GeneratePickCategory("employment_status", CATEGORICAL_SCHEMA).resolve(CONTEXT_BLOCK, ctx)
    assert ctx.prompts == [
        GOLDEN_PROMPTS["enumerate_categorical"],
        GOLDEN_PROMPTS["select_unweighted"],
    ]


def test_generate_pick_numeric_enumerate_prompt_is_byte_identical():
    ctx = FakeContext({"candidates": [20, 30], "value": 34})
    GeneratePickCategory("age", NUMERIC_SCHEMA).resolve(CONTEXT_BLOCK, ctx)
    assert ctx.prompts[0] == GOLDEN_PROMPTS["enumerate_numeric"]


def test_generate_evaluate_pick_prompts_are_byte_identical_to_the_pre_refactor_builder():
    ctx = FakeContext(_categorical_answers())
    GenerateEvaluatePickCategory("employment_status", CATEGORICAL_SCHEMA).resolve(CONTEXT_BLOCK, ctx)
    assert ctx.prompts == [
        GOLDEN_PROMPTS["enumerate_categorical"],
        GOLDEN_PROMPTS["evaluate"],
        GOLDEN_PROMPTS["select_weighted"],
    ]


def test_numeric_distribution_prompt_is_byte_identical_to_the_pre_refactor_builder():
    ctx = FakeContext({None: {"distribution": "uniform"}})
    GenerateEvaluateRandomPickCategory("age", NUMERIC_SCHEMA).resolve(CONTEXT_BLOCK, ctx)
    assert ctx.prompts == [GOLDEN_PROMPTS["numeric_distribution"]]


# -- build-time method validation --------------------------------------------


def test_build_category_rejects_an_unimplemented_method():
    with pytest.raises(ValueError, match="Unknown method 'telepathy'"):
        build_category("employment_status", {"method": "telepathy"}, CATEGORICAL_SCHEMA)


def test_build_category_rejects_a_missing_method():
    with pytest.raises(ValueError, match="Unknown method ''"):
        build_category("employment_status", {"depends_on": []}, CATEGORICAL_SCHEMA)


def test_build_categories_rejects_a_bad_method_before_building_the_good_ones():
    """The whole list is validated up front, so no category is ever half-resolved."""
    config = {
        "age": {"method": "pick", "depends_on": []},
        "employment_status": {"method": "telepathy", "depends_on": ["age"]},
    }
    schema = {"age": NUMERIC_SCHEMA, "employment_status": CATEGORICAL_SCHEMA}
    with pytest.raises(ValueError, match="employment_status"):
        build_categories(["age", "employment_status"], config, schema)


def test_generation_spends_no_call_before_an_unknown_method_is_caught(tmp_path):
    """End-to-end: a typo in a strategy YAML costs nothing, not fifteen categories.

    The previous ``if/elif`` dispatch discovered an unknown method only when the walk
    reached it, so the run paid for every category before it -- and, once resume
    existed, would have failed at the same category on every retry round having
    re-paid nothing.
    """
    strategy = tmp_path / "typo.yaml"
    strategy.write_text(
        yaml.safe_dump({
            "family": "all_pick",
            "version": 1,
            "categories": {
                "age": {"method": "pick", "depends_on": []},
                "employment_status": {"method": "telepathy", "depends_on": ["age"]},
            },
        }),
        encoding="utf-8",
    )
    schema = tmp_path / "flat_schema.json"
    schema.write_text(
        json.dumps({
            "instruction": ["You are generating a persona."],
            "categories": {"age": NUMERIC_SCHEMA, "employment_status": CATEGORICAL_SCHEMA},
        }),
        encoding="utf-8",
    )

    seam = FakeContext(_categorical_answers())
    generator = IdentityGeneratorConfigurable(object())
    generator._build_resolution_context = lambda _system_instruction: seam

    with pytest.raises(ValueError, match="Unknown method 'telepathy'"):
        generator.generate_identity(str(schema), strategy_file=str(strategy))

    assert seam.prompts == [], "a category resolved before the method error was raised"
