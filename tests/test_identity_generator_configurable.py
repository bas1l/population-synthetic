"""Unit tests for ``IdentityGeneratorConfigurable`` context handling.

Covers the strategy-level ``context`` mode wired through ``_load_strategy`` and
``generate_identity``: the ``all_pick`` context-free baseline (``context: none``),
the ``all_pick_dag`` regression guard (still accumulates cumulative context), and
the fail-fast validation on an unrecognised ``context`` value.

No live LLM call is made -- a ``RecordingGenerator`` subclass overrides
``_call_llm_json`` to capture every prompt it receives and return canned values
keyed by ``expected_key``. The flat schema is derived from the strategy under test
(so every declared category is present), and the real strategy YAMLs under
``config/synthetic/axes/strategies/`` drive the DAG.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from population_synthetic.generators.synthetic.identity_generator_configurable import (
    IdentityGeneratorConfigurable,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_STRATEGY_DIR = _REPO_ROOT / "config" / "synthetic" / "axes" / "strategies"
_ALL_PICK = _STRATEGY_DIR / "all_pick.yaml"
_ALL_PICK_DAG = _STRATEGY_DIR / "all_pick_dag.yaml"

# The empty-branch sentinel emitted by ``_build_context_block`` when no prior
# attributes are visible. Under ``context: none`` every prompt must carry it.
_SENTINEL = "This is the first category. Use the system instruction as context."

# Marker suffix appended to every resolved value; a serialised context line would
# read ``<category>: <category>__VAL``. Its absence proves no context leaked.
_VALUE_MARKER = "__VAL"


class RecordingGenerator(IdentityGeneratorConfigurable):
    """Generator that records prompts and returns canned values (no live LLM)."""

    def __init__(self, client: Any):
        super().__init__(client)
        self.calls: list[tuple[str, str]] = []  # (category, prompt)

    def _call_llm_json(
        self,
        prompt: str,
        system_instruction: str,
        *,
        expected_key: str | None = None,
        response_schema: dict | None = None,
        log_category: str = "",
        log_method: str = "",
        log_step: str = "",
    ) -> Any:
        self.calls.append((log_category, prompt))
        if expected_key == "value":
            return f"{log_category}{_VALUE_MARKER}"
        if expected_key == "candidates":
            return [f"{log_category}{_VALUE_MARKER}"]
        if expected_key == "weights":
            return [1.0]
        # distribution / free-form (expected_key is None)
        return {"distribution": "uniform"}


def _schema_from_strategy(strategy_path: Path) -> dict:
    """Build a minimal flat schema covering every category the strategy declares.

    All categories are plain categorical (no ``min``/``max``) so ``pick`` returns
    the canned string token unchanged.
    """
    data = yaml.safe_load(strategy_path.read_text(encoding="utf-8"))
    categories = {name: {"description": f"desc for {name}"} for name in data["categories"]}
    return {"instruction": ["You are generating a persona."], "categories": categories}


def _write_schema(tmp_path: Path, strategy_path: Path) -> str:
    schema_path = tmp_path / "flat_schema.json"
    schema_path.write_text(
        json.dumps(_schema_from_strategy(strategy_path)), encoding="utf-8"
    )
    return str(schema_path)


def _run(tmp_path: Path, strategy_path: Path) -> RecordingGenerator:
    gen = RecordingGenerator(client=object())
    schema_file = _write_schema(tmp_path, strategy_path)
    gen.generate_identity(schema_file, strategy_file=str(strategy_path))
    return gen


# ---------------------------------------------------------------------------
# all_pick -- context-free baseline (context: none)
# ---------------------------------------------------------------------------


def test_all_pick_is_context_free(tmp_path):
    gen = _run(tmp_path, _ALL_PICK)

    n_categories = len(yaml.safe_load(_ALL_PICK.read_text(encoding="utf-8"))["categories"])
    assert len(gen.calls) == n_categories

    for category, prompt in gen.calls:
        # Every prompt shows the first-category sentinel...
        assert _SENTINEL in prompt, f"missing sentinel in prompt for '{category}'"
        # ...and never a previously-resolved value (all values carry the marker).
        assert _VALUE_MARKER not in prompt, f"context leaked into prompt for '{category}'"


def test_all_pick_returns_full_persona(tmp_path):
    # ``context: none`` changes only what the prompt sees; the persona is still
    # fully accumulated and returned.
    gen = RecordingGenerator(client=object())
    schema_file = _write_schema(tmp_path, _ALL_PICK)
    resolved, _ = gen.generate_identity(schema_file, strategy_file=str(_ALL_PICK))

    declared = yaml.safe_load(_ALL_PICK.read_text(encoding="utf-8"))["categories"]
    assert set(resolved.keys()) == set(declared.keys())


# ---------------------------------------------------------------------------
# all_pick_dag -- regression guard (cumulative context retained)
# ---------------------------------------------------------------------------


def test_all_pick_dag_still_leaks_context(tmp_path):
    gen = _run(tmp_path, _ALL_PICK_DAG)

    prompts_by_cat = {category: prompt for category, prompt in gen.calls}

    # ``civil_status`` depends_on [age, biological_sex]; both resolve first, so
    # its prompt must carry their resolved values (proves other strategies are
    # untouched by the all_pick fix).
    civil_prompt = prompts_by_cat["civil_status"]
    assert f"age: age{_VALUE_MARKER}" in civil_prompt
    assert f"biological_sex: biological_sex{_VALUE_MARKER}" in civil_prompt

    # Under cumulative context only the first-resolved category sees the empty
    # sentinel; every later prompt carries accumulated values.
    sentinel_prompts = [cat for cat, prompt in gen.calls if _SENTINEL in prompt]
    assert len(sentinel_prompts) == 1


# ---------------------------------------------------------------------------
# _load_strategy -- context-mode parsing + fail-fast
# ---------------------------------------------------------------------------


def test_load_strategy_all_pick_is_none():
    gen = RecordingGenerator(client=object())
    _, context_mode = gen._load_strategy(str(_ALL_PICK))
    assert context_mode == "none"


def test_load_strategy_dag_defaults_to_cumulative():
    gen = RecordingGenerator(client=object())
    _, context_mode = gen._load_strategy(str(_ALL_PICK_DAG))
    assert context_mode == "cumulative"


def test_load_strategy_absent_key_defaults_to_cumulative(tmp_path):
    path = tmp_path / "no_context.yaml"
    path.write_text(
        yaml.safe_dump({"categories": {"age": {"method": "pick", "depends_on": []}}}),
        encoding="utf-8",
    )
    gen = RecordingGenerator(client=object())
    categories, context_mode = gen._load_strategy(str(path))
    assert context_mode == "cumulative"
    assert "age" in categories


def test_load_strategy_bogus_context_raises(tmp_path):
    path = tmp_path / "bogus_context.yaml"
    path.write_text(
        yaml.safe_dump({
            "context": "bogus",
            "categories": {"age": {"method": "pick", "depends_on": []}},
        }),
        encoding="utf-8",
    )
    gen = RecordingGenerator(client=object())
    with pytest.raises(ValueError, match="context"):
        gen._load_strategy(str(path))
