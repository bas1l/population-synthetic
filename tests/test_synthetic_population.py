"""The persona set's resume policy, and the objects it hands out.

``SyntheticPopulation`` is where a run decides what it still has to do, so these
tests pin that decision against every on-disk state a killed run can leave:

* an absent slot, a complete one, a truncated one, an incomplete one;
* a checkpoint beside an unfinished identity (resumable) versus one beside a
  finished identity (an orphan the plan must collect);
* ``force``, which must classify every slot as pending without inspecting -- or
  deleting -- anything.

No client, no strategy YAML and no thread pool are involved: the blueprint is a
list of stub categories, which is all the population is contractually allowed to
know about them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from population_synthetic.generators.synthetic.category import Category
from population_synthetic.generators.synthetic.persona import Persona
from population_synthetic.generators.synthetic.persona_writer import PersonaWriter
from population_synthetic.generators.synthetic.synthetic_population import (
    ResumePlan,
    SyntheticPopulation,
)

CATEGORIES = ("age", "biological_sex", "region")
FINGERPRINT = {
    "strategy_sha256": "a" * 64,
    "schema_sha256": "b" * 64,
    "model_key": "gemini:gemini-2.5-flash",
    "category_order": list(CATEGORIES),
}
PERSONA = {"age": 41, "biological_sex": "female", "region": "Skane"}


class StubCategory(Category):
    """Carries a name and nothing else -- all the population may depend on."""

    method = "stub"

    def resolve(self, context: str, ctx: object) -> str:
        return f"{self.name}__VAL"


def _blueprint(*names: str) -> list[Category]:
    return [StubCategory(name, {"description": f"desc for {name}"}) for name in names or CATEGORIES]


def _population(tmp_path: Path, n: int = 3, categories: list[Category] | None = None) -> SyntheticPopulation:
    return SyntheticPopulation(
        n, tmp_path, FINGERPRINT, categories or _blueprint(), context_mode="cumulative"
    )


def _persona_dir(tmp_path: Path, index: int) -> Path:
    return tmp_path / f"persona_{index:05d}"


def _write_identity(tmp_path: Path, index: int, data: dict | str) -> Path:
    persona = _persona_dir(tmp_path, index)
    persona.mkdir(parents=True, exist_ok=True)
    path = persona / "identity.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


def _write_checkpoint(tmp_path: Path, index: int, resolved: dict, call_index: int = 2) -> Path:
    persona = _persona_dir(tmp_path, index)
    persona.mkdir(parents=True, exist_ok=True)
    path = persona / "identity.partial.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "fingerprint": FINGERPRINT,
                "call_index": call_index,
                "resolved": resolved,
            }
        ),
        encoding="utf-8",
    )
    return path


# -- construction ------------------------------------------------------------


@pytest.mark.parametrize("n", [0, -1, 1.5, True, "3"])
def test_a_population_needs_a_positive_integer_size(tmp_path, n):
    with pytest.raises(ValueError, match="positive integer size"):
        SyntheticPopulation(n, tmp_path, FINGERPRINT, _blueprint(), context_mode="cumulative")


def test_an_empty_blueprint_is_refused(tmp_path):
    # An empty requirement would make every parseable identity "complete", turning
    # the resume gate back into the exists-only check it replaces.
    with pytest.raises(ValueError, match="at least one category"):
        SyntheticPopulation(3, tmp_path, FINGERPRINT, [], context_mode="cumulative")


def test_an_unimplemented_context_mode_is_refused_at_construction(tmp_path):
    with pytest.raises(ValueError, match="context mode"):
        SyntheticPopulation(3, tmp_path, FINGERPRINT, _blueprint(), context_mode="partial")


def test_the_blueprint_order_is_the_requirement_order(tmp_path):
    population = _population(tmp_path)
    assert population.category_names == list(CATEGORIES)
    assert len(population) == 3
    assert population.n == 3


# -- slots -------------------------------------------------------------------


def test_slot_layout_is_zero_padded_and_matches_the_validate_raw_glob(tmp_path):
    assert _population(tmp_path).persona_dir(2).name == "persona_00002"


@pytest.mark.parametrize("index", [-1, 3, 99])
def test_an_out_of_range_slot_raises(tmp_path, index):
    with pytest.raises(IndexError, match="outside this population"):
        _population(tmp_path).persona_dir(index)


def test_persona_is_bound_to_its_own_slot_writer(tmp_path):
    population = _population(tmp_path)
    persona = population.persona(1)

    assert isinstance(persona, Persona)
    assert persona.category_names == list(CATEGORIES)
    assert isinstance(persona.writer, PersonaWriter)
    # The writer the walk checkpoints through is the writer that publishes: one
    # lookup, so the two can never disagree about which directory this slot owns.
    persona.writer.checkpoint({"age": 41}, 1)
    assert (_persona_dir(tmp_path, 1) / "identity.partial.json").exists()


def test_each_call_hands_out_a_fresh_writer(tmp_path):
    # Two workers must never share one persona's resume verdict or telemetry handle.
    population = _population(tmp_path)
    assert population.writer(0) is not population.writer(0)


# -- the resume plan ---------------------------------------------------------


def test_an_untouched_run_has_everything_pending_and_nothing_resumed(tmp_path):
    plan = _population(tmp_path).plan()

    assert plan == ResumePlan(pending=(0, 1, 2), complete=(), checkpointed=())
    assert plan.resumed is False


def test_a_complete_persona_is_excluded_from_the_pending_set(tmp_path):
    _write_identity(tmp_path, 1, PERSONA)

    plan = _population(tmp_path).plan()

    assert plan.pending == (0, 2)
    assert plan.complete == (1,)
    assert plan.resumed is True


@pytest.mark.parametrize(
    "content",
    [
        '{"age": 41, "biologic',              # killed mid json.dump
        "",                                    # zero-byte
        json.dumps({"age": 41}),               # missing categories
        json.dumps({"age": 41, "biological_sex": "", "region": "Skane"}),  # empty value
        json.dumps({"age": {"years": 41}, "biological_sex": "f", "region": "X"}),  # nested
        json.dumps([1, 2, 3]),                 # not an object
    ],
    ids=["truncated", "empty-file", "missing-key", "empty-value", "nested", "not-an-object"],
)
def test_an_unfinished_persona_stays_pending(tmp_path, content):
    _write_identity(tmp_path, 0, content)

    assert 0 in _population(tmp_path).plan().pending


def test_a_checkpoint_beside_an_unfinished_persona_is_reported_as_resumable(tmp_path):
    _write_checkpoint(tmp_path, 2, {"age": 41})

    plan = _population(tmp_path).plan()

    assert plan.pending == (0, 1, 2)
    assert plan.checkpointed == (2,)
    assert plan.resumed is True
    # Reported, never consumed: the worker that generates the slot is what decides
    # whether the checkpoint is valid under this run's fingerprint.
    assert (_persona_dir(tmp_path, 2) / "identity.partial.json").exists()


def test_a_checkpoint_beside_a_complete_persona_is_collected_as_an_orphan(tmp_path):
    # The state a kill between finalize()'s two steps leaves behind. Nothing else in
    # the pipeline would ever collect it.
    _write_identity(tmp_path, 0, PERSONA)
    _write_checkpoint(tmp_path, 0, {"age": 41})

    plan = _population(tmp_path).plan()

    assert plan.complete == (0,)
    assert plan.checkpointed == ()
    assert not (_persona_dir(tmp_path, 0) / "identity.partial.json").exists()


def test_force_takes_every_slot_and_inherits_nothing(tmp_path):
    _write_identity(tmp_path, 0, PERSONA)
    checkpoint = _write_checkpoint(tmp_path, 1, {"age": 41})

    plan = _population(tmp_path).plan(force=True)

    assert plan == ResumePlan(pending=(0, 1, 2), complete=(), checkpointed=())
    assert plan.resumed is False
    # Not deleted here: the writer the worker asks for discards it, so a run that
    # died between planning and generating has not already thrown the work away.
    assert checkpoint.exists()


def test_pending_indices_is_the_plan_s_pending_side(tmp_path):
    _write_identity(tmp_path, 1, PERSONA)
    population = _population(tmp_path)

    assert population.pending_indices() == [0, 2]
    assert population.pending_indices(force=True) == [0, 1, 2]


def test_a_fully_complete_rerun_has_nothing_left_to_do(tmp_path):
    for index in range(3):
        _write_identity(tmp_path, index, PERSONA)

    plan = _population(tmp_path).plan()

    assert plan.pending == ()
    assert plan.complete == (0, 1, 2)
    assert plan.resumed is True
