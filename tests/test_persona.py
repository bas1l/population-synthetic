"""The category walk, the context block it renders, and its checkpointing.

``Persona`` is where resume-faithfulness is either preserved or lost, so these
tests pin the two properties it rests on:

* :meth:`Persona._build_context_block` is a pure function of the resolved dict's
  contents **and insertion order** -- never sorted, never annotated;
* the checkpoint is written *after* a value lands, once per category, carrying the
  correlation index as of that moment.

The walk is exercised with stub categories that make no call at all, so a failure
here can only be the walk's own doing.
"""

from __future__ import annotations

from typing import Any

import pytest

from population_synthetic.generators.synthetic.category import Category
from population_synthetic.generators.synthetic.persona import Persona
from population_synthetic.generators.synthetic.persona_writer import ResumeState

# Verbatim output of the pre-refactor ``_build_context_block``. See tests/test_category.py.
GOLDEN_EMPTY_CONTEXT = "This is the first category. Use the system instruction as context."
GOLDEN_CONTEXT = "age: 34\nbiological_sex: female"


class StubCategory(Category):
    """Records the context block it was handed and returns a marker value."""

    method = "stub"

    def resolve(self, context: str, ctx: "FakeContext") -> str:
        ctx.seen.append((self.name, context))
        ctx.spend()
        return f"{self.name}__VAL"


class ExplodingCategory(Category):
    """Fails the way a killed or exhausted category does."""

    method = "stub"

    def resolve(self, context: str, ctx: "FakeContext") -> str:
        raise RuntimeError(f"{self.name} could not be resolved")


class FakeContext:
    """The two members ``Persona`` touches: a call counter it can read and continue."""

    def __init__(self) -> None:
        self.call_index = 0
        self.seen: list[tuple[str, str]] = []

    def spend(self) -> None:
        self.call_index += 1

    def resume_from(self, call_index: int) -> None:
        self.call_index = call_index


class FakeWriter:
    """Captures every checkpoint as an ordered snapshot, never touching a disk."""

    def __init__(self, state: ResumeState | None = None) -> None:
        self._state = state
        self.checkpoints: list[tuple[list[str], int]] = []

    def resume(self) -> ResumeState | None:
        return self._state

    def checkpoint(self, resolved: dict[str, Any], call_index: int) -> None:
        self.checkpoints.append((list(resolved), call_index))


def _categories(*names: str) -> list[Category]:
    return [StubCategory(name, {"description": f"desc for {name}"}) for name in names]


# -- the context block -------------------------------------------------------


def test_empty_context_renders_the_first_category_sentinel():
    assert Persona._build_context_block({}) == GOLDEN_EMPTY_CONTEXT


def test_context_block_is_byte_identical_to_the_pre_refactor_builder():
    assert Persona._build_context_block({"age": 34, "biological_sex": "female"}) == GOLDEN_CONTEXT


def test_context_block_follows_insertion_order_not_sort_order():
    """The property resume-faithfulness rests on: order in, order out."""
    forward = Persona._build_context_block({"b": 1, "a": 2})
    assert forward == "b: 1\na: 2"
    assert forward != Persona._build_context_block({"a": 2, "b": 1})


# -- the walk ----------------------------------------------------------------


def test_cumulative_context_accumulates_every_earlier_value():
    ctx = FakeContext()
    persona = Persona(_categories("age", "biological_sex", "civil_status"), context_mode="cumulative")

    resolved = persona.generate(ctx)

    assert list(resolved) == ["age", "biological_sex", "civil_status"]
    assert [block for _, block in ctx.seen] == [
        GOLDEN_EMPTY_CONTEXT,
        "age: age__VAL",
        "age: age__VAL\nbiological_sex: biological_sex__VAL",
    ]


def test_context_none_shows_no_prior_value_yet_still_accumulates():
    ctx = FakeContext()
    persona = Persona(_categories("age", "biological_sex"), context_mode="none")

    resolved = persona.generate(ctx)

    # Only what the prompt sees changes -- the returned persona is unaffected.
    assert list(resolved) == ["age", "biological_sex"]
    assert {block for _, block in ctx.seen} == {GOLDEN_EMPTY_CONTEXT}


def test_unknown_context_mode_raises():
    with pytest.raises(ValueError, match="context mode"):
        Persona(_categories("age"), context_mode="partial")


def test_a_failing_category_reports_how_much_was_already_resolved():
    ctx = FakeContext()
    persona = Persona(
        [*_categories("age"), ExplodingCategory("civil_status", {})],
        context_mode="cumulative",
    )
    with pytest.raises(RuntimeError, match="civil_status"):
        persona.generate(ctx)


# -- checkpointing -----------------------------------------------------------


def test_a_checkpoint_is_written_after_every_category_and_never_before():
    ctx = FakeContext()
    writer = FakeWriter()
    persona = Persona(_categories("age", "biological_sex"), context_mode="cumulative", writer=writer)

    persona.generate(ctx)

    # Each snapshot already contains the category that triggered it, so a resume can
    # never skip past a category the run did not actually pay for.
    assert writer.checkpoints == [(["age"], 1), (["age", "biological_sex"], 2)]


def test_no_checkpoint_is_attempted_without_a_writer():
    ctx = FakeContext()
    persona = Persona(_categories("age"), context_mode="cumulative")
    assert persona.generate(ctx) == {"age": "age__VAL"}


def test_the_failing_category_leaves_the_previous_checkpoint_intact():
    ctx = FakeContext()
    writer = FakeWriter()
    persona = Persona(
        [*_categories("age"), ExplodingCategory("civil_status", {})],
        context_mode="cumulative",
        writer=writer,
    )
    with pytest.raises(RuntimeError):
        persona.generate(ctx)

    assert writer.checkpoints == [(["age"], 1)]


# -- resume ------------------------------------------------------------------


def test_resume_replays_the_checkpointed_prefix_and_continues_the_counter():
    ctx = FakeContext()
    writer = FakeWriter(ResumeState(resolved={"age": 34, "biological_sex": "female"}, call_index=7))
    persona = Persona(
        _categories("age", "biological_sex", "civil_status"),
        context_mode="cumulative",
        writer=writer,
    )

    resolved = persona.generate(ctx)

    # Only the unresolved tail is re-asked, and it sees the restored prefix verbatim.
    assert [name for name, _ in ctx.seen] == ["civil_status"]
    assert ctx.seen[0][1] == GOLDEN_CONTEXT
    assert list(resolved) == ["age", "biological_sex", "civil_status"]
    assert writer.checkpoints == [(["age", "biological_sex", "civil_status"], 8)]


def test_resume_stops_at_the_first_gap_rather_than_cherry_picking():
    """A hole in the checkpoint must not let a later category skip its turn.

    Restoring past a gap would show some category a context an uninterrupted run
    would never have produced, which is exactly the failure resume-faithfulness
    rules out.
    """
    ctx = FakeContext()
    writer = FakeWriter(ResumeState(resolved={"age": 34, "civil_status": "married"}, call_index=5))
    persona = Persona(
        _categories("age", "biological_sex", "civil_status"),
        context_mode="cumulative",
        writer=writer,
    )

    resolved = persona.generate(ctx)

    assert [name for name, _ in ctx.seen] == ["biological_sex", "civil_status"]
    assert list(resolved) == ["age", "biological_sex", "civil_status"]
    assert resolved["civil_status"] == "civil_status__VAL"


def test_a_writer_with_no_checkpoint_starts_from_the_beginning():
    ctx = FakeContext()
    writer = FakeWriter(None)
    persona = Persona(_categories("age", "biological_sex"), context_mode="cumulative", writer=writer)

    persona.generate(ctx)

    assert [name for name, _ in ctx.seen] == ["age", "biological_sex"]
