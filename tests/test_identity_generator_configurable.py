"""Unit tests for ``IdentityGeneratorConfigurable`` context handling and DAG order.

Covers the strategy-level ``context`` mode wired through ``_load_strategy`` and
``generate_identity``: the ``all_pick`` context-free baseline (``context: none``),
the ``all_pick_dag`` regression guard (still accumulates cumulative context), and
the fail-fast validation on an unrecognised ``context`` value.

Also covers ``_build_dag`` determinism: the resolved category order must be a pure
function of the strategy YAML, identical across separate interpreter processes with
hash randomisation active.

No live LLM call is made -- a ``RecordingGenerator`` subclass overrides
``_call_llm_json`` to capture every prompt it receives and return canned values
keyed by ``expected_key``. The flat schema is derived from the strategy under test
(so every declared category is present), and the real strategy YAMLs under
``config/synthetic/axes/strategies/`` drive the DAG.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml

from population_synthetic.generators.synthetic.identity_generator_configurable import (
    IdentityGeneratorConfigurable,
    resolve_category_order,
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
        self.steps: list[tuple[str, str, str, str]] = []  # (category, method, step, prompt)

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
        self.steps.append((log_category, log_method, log_step, prompt))
        if expected_key == "value":
            return f"{log_category}{_VALUE_MARKER}"
        if expected_key == "candidates":
            return [f"{log_category}{_VALUE_MARKER}"]
        if expected_key == "weights":
            return [1.0]
        # distribution / free-form (expected_key is None)
        return {"distribution": "uniform"}

    def select_prompts(self) -> list[str]:
        """Every select-step prompt recorded, in call order."""
        return [prompt for _, _, step, prompt in self.steps if step == "select"]


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
        yaml.safe_dump({
            "family": "all_pick",
            "version": 1,
            "categories": {"age": {"method": "pick", "depends_on": []}},
        }),
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
            "family": "all_pick",
            "version": 1,
            "categories": {"age": {"method": "pick", "depends_on": []}},
        }),
        encoding="utf-8",
    )
    gen = RecordingGenerator(client=object())
    with pytest.raises(ValueError, match="context"):
        gen._load_strategy(str(path))


# ---------------------------------------------------------------------------
# _load_strategy -- family / version axis metadata
# ---------------------------------------------------------------------------


def _write_strategy(path, **overrides):
    doc = {
        "family": "all_pick",
        "version": 1,
        "categories": {"age": {"method": "pick", "depends_on": []}},
    }
    doc.update(overrides)
    doc = {k: v for k, v in doc.items() if v is not _ABSENT}
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return path


_ABSENT = object()


@pytest.mark.parametrize("missing", ["family", "version"])
def test_load_strategy_selectable_requires_axis_metadata(tmp_path, missing):
    """A selectable strategy without family/version fails loudly, never defaulted."""
    path = _write_strategy(tmp_path / "selectable.yaml", **{missing: _ABSENT})
    gen = RecordingGenerator(client=object())
    with pytest.raises(ValueError, match=missing):
        gen._load_strategy(str(path))


def test_load_strategy_underscore_prefixed_may_omit_axis_metadata(tmp_path):
    """``_``-prefixed files are co-located definitions, not selectable axis options."""
    path = _write_strategy(tmp_path / "_frozen.yaml", family=_ABSENT, version=_ABSENT)
    gen = RecordingGenerator(client=object())
    categories, context_mode = gen._load_strategy(str(path))
    assert "age" in categories
    assert context_mode == "cumulative"


@pytest.mark.parametrize(
    "overrides",
    [
        {"family": ""},
        {"family": 3},
        {"version": 0},
        {"version": "1"},
        {"version": True},
    ],
)
def test_load_strategy_malformed_axis_metadata_raises(tmp_path, overrides):
    """Malformed family/version raises even on a ``_``-prefixed definition."""
    path = _write_strategy(tmp_path / "_malformed.yaml", **overrides)
    gen = RecordingGenerator(client=object())
    with pytest.raises(ValueError, match="family|version"):
        gen._load_strategy(str(path))


# ---------------------------------------------------------------------------
# _build_dag -- determinism
# ---------------------------------------------------------------------------

_N_PROBE_PROCESSES = 20

# Co-located files in the strategies directory that are NOT strategy definitions
# (no ``categories`` block), so they carry no category order to resolve.
_NON_STRATEGY_FILES = ("_families.yaml",)


def _strategy_files(directory) -> list:
    """Every strategy-definition YAML in *directory* (the family index excluded)."""
    return [p for p in sorted(directory.glob("*.yaml")) if p.name not in _NON_STRATEGY_FILES]


# Runs in a fresh interpreter: resolves every strategy YAML and prints one
# "<file>\t<comma-joined order>" line per file.
_PROBE_SOURCE = textwrap.dedent(
    """
    import sys
    from pathlib import Path

    from population_synthetic.generators.synthetic.identity_generator_configurable import (
        resolve_category_order,
    )

    skip = set(sys.argv[2:])
    for path in sorted(Path(sys.argv[1]).glob("*.yaml")):
        if path.name in skip:
            continue
        print(path.name, ",".join(resolve_category_order(str(path))), sep="\\t")
    """
)


@pytest.fixture(scope="module")
def probe_outputs() -> list[str]:
    """Resolved order for every strategy YAML, collected from N separate processes.

    ``PYTHONHASHSEED`` is *removed* from the child environment rather than pinned:
    the defect under test is CPython's per-process string-hash randomisation, and
    pinning the seed would hide exactly the failure mode this guards against.
    """
    env = {k: v for k, v in os.environ.items() if k != "PYTHONHASHSEED"}
    return [
        subprocess.run(
            [sys.executable, "-c", _PROBE_SOURCE, str(_STRATEGY_DIR), *_NON_STRATEGY_FILES],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout
        for _ in range(_N_PROBE_PROCESSES)
    ]


def test_build_dag_order_is_identical_across_processes(probe_outputs):
    # Guard against a silently empty glob making the equality trivially true.
    n_strategies = len(_strategy_files(_STRATEGY_DIR))
    assert n_strategies > 0
    assert len(probe_outputs[0].splitlines()) == n_strategies

    distinct = set(probe_outputs)
    assert len(distinct) == 1, (
        f"_build_dag returned {len(distinct)} different orders across "
        f"{_N_PROBE_PROCESSES} processes; it must be a pure function of the YAML"
    )


def test_build_dag_breaks_ties_in_declaration_order():
    # Five roots, no edges: every one is in-degree 0 simultaneously, so the whole
    # order is tie-break. It must reproduce the declaration order exactly.
    names = ("region", "age", "housing_tenure", "biological_sex", "civil_status")
    config = {name: {"method": "pick", "depends_on": []} for name in names}
    assert IdentityGeneratorConfigurable._build_dag(config) == list(names)

    # ...and it tracks the declaration, rather than any fixed sequence of its own.
    reversed_config = {name: {"method": "pick", "depends_on": []} for name in reversed(names)}
    assert IdentityGeneratorConfigurable._build_dag(reversed_config) == list(reversed(names))


def test_build_dag_releases_dependents_in_declaration_order():
    # Both children become in-degree 0 on the same release step; declaration order,
    # not alphabetical or hash order, decides which is generated first.
    config = {
        "age": {"method": "pick", "depends_on": []},
        "z_child": {"method": "pick", "depends_on": ["age"]},
        "a_child": {"method": "pick", "depends_on": ["age"]},
    }
    assert IdentityGeneratorConfigurable._build_dag(config) == ["age", "z_child", "a_child"]


def test_build_dag_raises_on_undeclared_dependency():
    config = {"age": {"method": "pick", "depends_on": ["nonexistent"]}}
    with pytest.raises(ValueError, match="nonexistent"):
        IdentityGeneratorConfigurable._build_dag(config)


def test_build_dag_raises_on_cycle():
    config = {
        "age": {"method": "pick", "depends_on": ["civil_status"]},
        "civil_status": {"method": "pick", "depends_on": ["age"]},
    }
    with pytest.raises(ValueError, match="Cycle detected"):
        IdentityGeneratorConfigurable._build_dag(config)


def test_resolved_order_matches_generation_order(tmp_path):
    # The provenance accessor (recorded in run_metadata.json) and the order the
    # generator actually walks must be the same sequence, not two implementations.
    gen = _run(tmp_path, _ALL_PICK_DAG)
    assert [category for category, _ in gen.calls] == resolve_category_order(str(_ALL_PICK_DAG))


# ---------------------------------------------------------------------------
# select-step prompt: generate_evaluate_pick shows weights, generate_pick does not
# ---------------------------------------------------------------------------

_ALL_GENERATE_PICK = _STRATEGY_DIR / "all_generate_pick.yaml"
_ALL_GENERATE_EVALUATE_PICK = _STRATEGY_DIR / "all_generate_evaluate_pick.yaml"


class WeightedRecordingGenerator(RecordingGenerator):
    """Recorder returning a multi-candidate list with uneven weights.

    The base recorder returns a single candidate weighted 1.0, which cannot
    distinguish a select prompt that renders probabilities from one that does not.
    """

    CANDIDATES = ["alpha", "beta", "gamma"]
    WEIGHTS = [0.6, 0.3, 0.1]

    def _call_llm_json(self, prompt, system_instruction, *, expected_key=None, **kwargs) -> Any:
        if expected_key == "candidates":
            super()._call_llm_json(
                prompt, system_instruction, expected_key="__record_only__", **kwargs
            )
            return list(self.CANDIDATES)
        if expected_key == "weights":
            super()._call_llm_json(
                prompt, system_instruction, expected_key="__record_only__", **kwargs
            )
            return list(self.WEIGHTS)
        return super()._call_llm_json(
            prompt, system_instruction, expected_key=expected_key, **kwargs
        )


def _run_weighted(tmp_path: Path, strategy_path: Path) -> WeightedRecordingGenerator:
    gen = WeightedRecordingGenerator(client=object())
    schema_file = _write_schema(tmp_path, strategy_path)
    gen.generate_identity(schema_file, strategy_file=str(strategy_path))
    return gen


def test_generate_evaluate_pick_select_prompt_pairs_candidates_with_probabilities(tmp_path):
    """The evaluate step's weights must reach the select call, not be discarded.

    Regression guard for the defect this method carried: weights were computed,
    normalised and count-reconciled, then never read -- making the 3-call method
    procedurally identical to the 2-call ``generate_pick``.
    """
    gen = _run_weighted(tmp_path, _ALL_GENERATE_EVALUATE_PICK)
    selects = gen.select_prompts()
    assert selects, "no select-step prompt was recorded"

    for prompt in selects:
        # Each candidate appears paired with its probability, as JSON value: probability.
        assert '"alpha": 0.6' in prompt
        assert '"beta": 0.3' in prompt
        assert '"gamma": 0.1' in prompt
        # ...and the prompt says so, rather than offering a bare list.
        assert "paired with the probability" in prompt


def test_generate_pick_select_prompt_has_no_probabilities(tmp_path):
    """``generate_pick`` computes no weights, so its select prompt is unchanged."""
    gen = _run_weighted(tmp_path, _ALL_GENERATE_PICK)
    selects = gen.select_prompts()
    assert selects, "no select-step prompt was recorded"

    for prompt in selects:
        assert "paired with the probability" not in prompt
        assert "0.6" not in prompt
        # The bare candidate list is still offered.
        assert "alpha" in prompt


def test_candidate_probabilities_sums_duplicate_candidates():
    # A repeated candidate must not lose its mass to dict-key collision.
    gen = RecordingGenerator(client=object())
    paired = gen._candidate_probabilities(["a", "b", "a"], [0.5, 0.2, 0.3], "some_category")
    assert paired == {"a": 0.8, "b": 0.2}


def test_candidate_probabilities_rounds_for_legibility():
    gen = RecordingGenerator(client=object())
    paired = gen._candidate_probabilities(["a", "b"], [1 / 3, 2 / 3], "some_category")
    assert paired == {"a": 0.3333, "b": 0.6667}
