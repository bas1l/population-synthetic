"""Resume behaviour of ``IdentityGeneratorConfigurable`` against a ``PersonaWriter``.

The property under test is **resume-faithfulness**: category K's rendered prompt
after a resume must be byte-identical to the prompt an uninterrupted run would
have produced. It holds because ``_build_context_block`` is a pure function of
``resolved``'s contents *and insertion order*, and the checkpoint restores both --
so these tests compare whole prompt sequences, not just the returned persona.

The companion property is the shared lifecycle: a resumed persona continues its
``call_index`` and appends to its telemetry log, so ``(persona_id, call_index)``
stays unique across the seam and no downstream consumer has to dedupe.

No live LLM call is made. ``CrashingContext`` replaces the generator's call seam:
it returns canned values keyed by ``expected_key`` and can be told to abort at a
chosen category, standing in for a ``taskkill`` mid-persona.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from population_synthetic.generators.synthetic.identity_generator_configurable import (
    IdentityGeneratorConfigurable,
    resolve_category_order,
)
from population_synthetic.generators.synthetic.llm_interaction_log import LLMInteractionEntry
from population_synthetic.generators.synthetic.persona_writer import PersonaWriter
from population_synthetic.generators.synthetic.resolution_context import ResolutionContext

_REPO_ROOT = Path(__file__).resolve().parents[1]
_STRATEGY_DIR = _REPO_ROOT / "config" / "synthetic" / "axes" / "strategies"
_CUMULATIVE = _STRATEGY_DIR / "all_pick_dag.yaml"   # context: cumulative
_CONTEXT_FREE = _STRATEGY_DIR / "all_pick.yaml"     # context: none

_VALUE_MARKER = "__VAL"

FINGERPRINT = {"strategy_sha256": "a" * 64, "schema_sha256": "b" * 64, "model_key": "fake:model"}


class Abort(RuntimeError):
    """Stands in for the process dying mid-persona."""


class CrashingContext(ResolutionContext):
    """Records every prompt, returns canned values, optionally aborts at a category."""

    def __init__(self, recorder: "CrashingGenerator", abort_at: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._recorder = recorder
        self._abort_at = abort_at

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
        if category == self._abort_at:
            raise Abort(f"killed while resolving {category}")
        # Mirror the real seam's counter and telemetry emission -- they are what
        # the checkpoint carries across the seam, so a fake that skipped them would
        # test nothing about the lifecycle.
        call_index = self._next_call_index()
        self._recorder.prompts.append((category, prompt))
        if self.interaction_collector is not None:
            self.interaction_collector.record(
                LLMInteractionEntry(
                    category=category,
                    method=method,
                    step=step,
                    prompt=prompt,
                    raw_response="",
                    persona_id=self.persona_id,
                    call_index=call_index,
                )
            )
        if expected_key == "value":
            return f"{category}{_VALUE_MARKER}"
        if expected_key == "candidates":
            return [f"{category}{_VALUE_MARKER}"]
        if expected_key == "weights":
            return [1.0]
        return {"distribution": "uniform"}


class CrashingGenerator(IdentityGeneratorConfigurable):
    """Generator whose call seam is a ``CrashingContext``."""

    def __init__(self, abort_at: str | None = None) -> None:
        super().__init__(client=object())
        self.persona_id = "persona_00000"
        self.prompts: list[tuple[str, str]] = []  # (category, prompt)
        self._abort_at = abort_at

    def _build_resolution_context(self, system_instruction: str) -> ResolutionContext:
        return CrashingContext(
            self,
            abort_at=self._abort_at,
            client=self.client,
            system_instruction=system_instruction,
            persona_id=self.persona_id,
            call_index=self._call_index,
            interaction_collector=self.interaction_collector,
        )


def _write_schema(tmp_path: Path, strategy_path: Path) -> str:
    """A minimal flat schema covering every category the strategy declares."""
    data = yaml.safe_load(strategy_path.read_text(encoding="utf-8"))
    schema = {
        "instruction": ["You are generating a persona."],
        "categories": {name: {"description": f"desc for {name}"} for name in data["categories"]},
    }
    path = tmp_path / "flat_schema.json"
    path.write_text(json.dumps(schema), encoding="utf-8")
    return str(path)


def _run(
    persona_dir: Path,
    schema_file: str,
    strategy_path: Path,
    *,
    abort_at: str | None = None,
    discard: bool = False,
    log_llm: bool = False,
    fingerprint: dict | None = None,
) -> CrashingGenerator:
    """One run of one persona, wired exactly as the parallel runner wires it."""
    gen = CrashingGenerator(abort_at=abort_at)
    writer = PersonaWriter(persona_dir, fingerprint or FINGERPRINT, discard=discard)
    gen.writer = writer
    if log_llm:
        gen.interaction_collector = writer.telemetry
    try:
        resolved, _ = gen.generate_identity(schema_file, strategy_file=str(strategy_path))
        writer.finalize(resolved)
    finally:
        writer.close()
    return gen


# -- checkpointing -----------------------------------------------------------


def test_checkpoint_tracks_every_resolved_category(tmp_path):
    persona = tmp_path / "persona_00000"
    schema_file = _write_schema(tmp_path, _CUMULATIVE)
    order = resolve_category_order(str(_CUMULATIVE))

    with pytest.raises(Abort):
        _run(persona, schema_file, _CUMULATIVE, abort_at=order[3])

    payload = json.loads((persona / "identity.partial.json").read_text(encoding="utf-8"))
    assert list(payload["resolved"]) == order[:3]
    assert payload["fingerprint"] == FINGERPRINT
    assert payload["call_index"] > 0


def test_finalize_clears_the_checkpoint_on_a_complete_run(tmp_path):
    persona = tmp_path / "persona_00000"
    schema_file = _write_schema(tmp_path, _CUMULATIVE)

    gen = _run(persona, schema_file, _CUMULATIVE)

    assert not (persona / "identity.partial.json").exists()
    identity = json.loads((persona / "identity.json").read_text(encoding="utf-8"))
    assert list(identity) == resolve_category_order(str(_CUMULATIVE))
    assert len(gen.prompts) > 0


# -- resume-faithfulness -----------------------------------------------------


@pytest.mark.parametrize("strategy_path", [_CUMULATIVE, _CONTEXT_FREE])
def test_resumed_prompts_are_byte_identical_to_an_uninterrupted_run(tmp_path, strategy_path):
    schema_file = _write_schema(tmp_path, strategy_path)
    order = resolve_category_order(str(strategy_path))
    interrupt_at = order[4]

    baseline = _run(tmp_path / "baseline", schema_file, strategy_path)

    crashed_dir = tmp_path / "resumed"
    with pytest.raises(Abort):
        _run(crashed_dir, schema_file, strategy_path, abort_at=interrupt_at)
    resumed = _run(crashed_dir, schema_file, strategy_path)

    # The tail the resumed run actually re-issued must match the baseline's tail
    # exactly -- same categories, same rendered prompt bytes, same order.
    tail_start = next(i for i, (cat, _) in enumerate(baseline.prompts) if cat == interrupt_at)
    assert resumed.prompts == baseline.prompts[tail_start:]

    assert json.loads((crashed_dir / "identity.json").read_text(encoding="utf-8")) == json.loads(
        (tmp_path / "baseline" / "identity.json").read_text(encoding="utf-8")
    )


def test_resume_replays_only_the_unresolved_tail(tmp_path):
    schema_file = _write_schema(tmp_path, _CUMULATIVE)
    order = resolve_category_order(str(_CUMULATIVE))
    persona = tmp_path / "persona_00000"

    with pytest.raises(Abort):
        _run(persona, schema_file, _CUMULATIVE, abort_at=order[4])
    resumed = _run(persona, schema_file, _CUMULATIVE)

    # At most one category's worth of work is re-paid, not all four already done.
    replayed = [cat for cat, _ in resumed.prompts]
    assert set(replayed) == set(order[4:])


def test_stale_fingerprint_forces_a_full_regeneration(tmp_path):
    schema_file = _write_schema(tmp_path, _CUMULATIVE)
    order = resolve_category_order(str(_CUMULATIVE))
    persona = tmp_path / "persona_00000"

    with pytest.raises(Abort):
        _run(persona, schema_file, _CUMULATIVE, abort_at=order[4])

    edited = {**FINGERPRINT, "strategy_sha256": "c" * 64}
    resumed = _run(persona, schema_file, _CUMULATIVE, fingerprint=edited)

    # Splicing two regimes into one persona is the failure the fingerprint exists
    # to prevent, so every category is regenerated under the new one.
    assert [cat for cat, _ in resumed.prompts][: len(order)] == order


def test_force_discards_the_checkpoint(tmp_path):
    schema_file = _write_schema(tmp_path, _CUMULATIVE)
    order = resolve_category_order(str(_CUMULATIVE))
    persona = tmp_path / "persona_00000"

    with pytest.raises(Abort):
        _run(persona, schema_file, _CUMULATIVE, abort_at=order[4])
    forced = _run(persona, schema_file, _CUMULATIVE, discard=True)

    assert [cat for cat, _ in forced.prompts][: len(order)] == order


# -- shared lifecycle --------------------------------------------------------


def _telemetry_keys(persona: Path) -> list[tuple[str, int]]:
    text = (persona / "llm_interactions.jsonl").read_text(encoding="utf-8")
    return [
        (json.loads(line)["persona_id"], json.loads(line)["call_index"])
        for line in text.splitlines()
        if line.strip()
    ]


def test_resume_continues_call_index_without_duplicating_correlation_keys(tmp_path):
    schema_file = _write_schema(tmp_path, _CUMULATIVE)
    order = resolve_category_order(str(_CUMULATIVE))
    persona = tmp_path / "persona_00000"

    with pytest.raises(Abort):
        _run(persona, schema_file, _CUMULATIVE, abort_at=order[4], log_llm=True)
    _run(persona, schema_file, _CUMULATIVE, log_llm=True)

    keys = _telemetry_keys(persona)
    assert len(keys) == len(set(keys)), "resume duplicated a (persona_id, call_index) pair"
    indices = [i for _, i in keys]
    assert indices == sorted(indices)
    assert indices[0] == 1


def test_force_restarts_call_index_and_truncates_the_telemetry_log(tmp_path):
    schema_file = _write_schema(tmp_path, _CUMULATIVE)
    order = resolve_category_order(str(_CUMULATIVE))
    persona = tmp_path / "persona_00000"

    with pytest.raises(Abort):
        _run(persona, schema_file, _CUMULATIVE, abort_at=order[4], log_llm=True)
    _run(persona, schema_file, _CUMULATIVE, discard=True, log_llm=True)

    keys = _telemetry_keys(persona)
    # Truncated in lockstep with the discarded checkpoint: a restarted counter over
    # retained records would double-count every call in the cost analysis.
    assert [i for _, i in keys] == list(range(1, len(keys) + 1))


def test_generation_without_a_writer_is_unchanged(tmp_path):
    # The writer is optional: with none injected, nothing is persisted and the
    # returned persona is exactly what the pre-checkpoint code produced.
    schema_file = _write_schema(tmp_path, _CUMULATIVE)
    gen = CrashingGenerator()
    resolved, _ = gen.generate_identity(schema_file, strategy_file=str(_CUMULATIVE))
    assert list(resolved) == resolve_category_order(str(_CUMULATIVE))
    assert list(tmp_path.glob("**/identity*.json")) == []
