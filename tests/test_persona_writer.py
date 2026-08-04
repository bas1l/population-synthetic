"""Unit tests for ``PersonaWriter`` -- the checkpoint, the gate, and the lifecycle.

Three guarantees are under test here, and each maps to a defect the writer exists
to close:

* a checkpoint is resumed only when it provably describes *this* run's regime, and
  every other on-disk state (absent, empty, torn, stale, wrong version) is
  discarded rather than repaired;
* ``identity.json`` is judged by content, not existence, so a truncated file left
  by a killed ``json.dump`` is regenerated instead of trusted forever;
* the telemetry log truncates if and only if the checkpoint is discarded, which is
  what keeps ``(persona_id, call_index)`` unique across a resume seam.
"""

from __future__ import annotations

import json
import logging

import pytest

from population_synthetic.generators.synthetic.llm_interaction_log import LLMInteractionEntry
from population_synthetic.generators.synthetic.persona_writer import (
    CHECKPOINT_SCHEMA_VERSION,
    PersonaWriter,
)

CATEGORIES = ["age", "biological_sex", "region"]

FINGERPRINT = {
    "strategy_sha256": "a" * 64,
    "schema_sha256": "b" * 64,
    "model_key": "ollama:llama3.2",
    "category_order": CATEGORIES,
}


def _writer(tmp_path, *, discard: bool = False, fingerprint: dict | None = None) -> PersonaWriter:
    return PersonaWriter(tmp_path, fingerprint or FINGERPRINT, discard=discard)


def _write_checkpoint(tmp_path, payload: dict) -> None:
    (tmp_path / "identity.partial.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _valid_payload(resolved: dict | None = None, call_index: int = 7) -> dict:
    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "fingerprint": FINGERPRINT,
        "call_index": call_index,
        "resolved": resolved if resolved is not None else {"age": 41, "biological_sex": "female"},
    }


# -- resume ------------------------------------------------------------------


def test_resume_returns_none_when_no_checkpoint_exists(tmp_path):
    assert _writer(tmp_path).resume() is None


def test_resume_returns_none_on_zero_byte_checkpoint(tmp_path):
    (tmp_path / "identity.partial.json").write_text("", encoding="utf-8")
    writer = _writer(tmp_path)
    assert writer.resume() is None
    assert not (tmp_path / "identity.partial.json").exists()


def test_resume_returns_none_on_truncated_checkpoint(tmp_path):
    # Exactly what a kill mid-write used to leave behind.
    (tmp_path / "identity.partial.json").write_text('{"schema_version": 1, "resol', encoding="utf-8")
    assert _writer(tmp_path).resume() is None


def test_resume_returns_none_on_stale_fingerprint(tmp_path):
    payload = _valid_payload()
    payload["fingerprint"] = {**FINGERPRINT, "strategy_sha256": "c" * 64}
    _write_checkpoint(tmp_path, payload)
    assert _writer(tmp_path).resume() is None


def test_resume_returns_none_on_wrong_schema_version(tmp_path):
    payload = _valid_payload()
    payload["schema_version"] = CHECKPOINT_SCHEMA_VERSION + 1
    _write_checkpoint(tmp_path, payload)
    assert _writer(tmp_path).resume() is None


def test_resume_returns_none_on_malformed_payload(tmp_path):
    payload = _valid_payload()
    payload["resolved"] = ["age", "biological_sex"]
    _write_checkpoint(tmp_path, payload)
    assert _writer(tmp_path).resume() is None


def test_resume_returns_state_on_valid_checkpoint(tmp_path):
    _write_checkpoint(tmp_path, _valid_payload())
    state = _writer(tmp_path).resume()
    assert state is not None
    assert state.resolved == {"age": 41, "biological_sex": "female"}
    assert state.call_index == 7
    # A valid checkpoint is kept: the run is about to continue writing to it.
    assert (tmp_path / "identity.partial.json").exists()


def test_resume_is_memoised_across_calls(tmp_path):
    _write_checkpoint(tmp_path, _valid_payload())
    writer = _writer(tmp_path)
    assert writer.resume() is writer.resume()


def test_discard_drops_a_valid_checkpoint(tmp_path):
    _write_checkpoint(tmp_path, _valid_payload())
    writer = _writer(tmp_path, discard=True)
    assert writer.resume() is None
    assert not (tmp_path / "identity.partial.json").exists()


def test_parse_failure_and_fingerprint_mismatch_log_differently(tmp_path, caplog):
    torn = tmp_path / "torn"
    torn.mkdir()
    (torn / "identity.partial.json").write_text("{not json", encoding="utf-8")

    stale = tmp_path / "stale"
    stale.mkdir()
    payload = _valid_payload()
    payload["fingerprint"] = {**FINGERPRINT, "model_key": "ollama:other"}
    (stale / "identity.partial.json").write_text(json.dumps(payload), encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        _writer(torn).resume()
        torn_messages = [r.getMessage() for r in caplog.records]
        caplog.clear()
        _writer(stale).resume()
        stale_messages = [r.getMessage() for r in caplog.records]

    assert len(torn_messages) == 1 and len(stale_messages) == 1
    # Different facts, different investigations -- so they must read differently.
    assert torn_messages[0] != stale_messages[0]
    assert "unreadable" in torn_messages[0]
    assert "different generation regime" in stale_messages[0]


# -- checkpoint / finalize ---------------------------------------------------


def test_checkpoint_round_trip_preserves_key_insertion_order(tmp_path):
    writer = _writer(tmp_path)
    resolved = {"region": "Skane", "age": 33, "biological_sex": "male"}
    writer.checkpoint(resolved, call_index=4)

    restored = _writer(tmp_path).resume()
    assert restored is not None
    assert list(restored.resolved) == ["region", "age", "biological_sex"]
    assert restored.call_index == 4


def test_finalize_writes_the_identity_then_removes_the_checkpoint(tmp_path):
    writer = _writer(tmp_path)
    writer.checkpoint({"age": 20}, call_index=1)
    writer.finalize({"age": 20, "biological_sex": "female", "region": "Skane"})

    identity = json.loads((tmp_path / "identity.json").read_text(encoding="utf-8"))
    assert identity == {"age": 20, "biological_sex": "female", "region": "Skane"}
    assert not (tmp_path / "identity.partial.json").exists()


def test_stale_checkpoint_beside_a_complete_identity_is_cleaned(tmp_path):
    # The state a kill between finalize()'s two steps leaves behind.
    writer = _writer(tmp_path)
    writer.finalize({"age": 20, "biological_sex": "female", "region": "Skane"})
    _write_checkpoint(tmp_path, _valid_payload())

    next_run = _writer(tmp_path)
    assert next_run.has_complete_identity(CATEGORIES)
    next_run.discard_stale_checkpoint()
    assert not (tmp_path / "identity.partial.json").exists()


# -- completeness gate -------------------------------------------------------


def test_has_complete_identity_true_for_a_finished_persona(tmp_path):
    _writer(tmp_path).finalize({"age": 20, "biological_sex": "female", "region": "Skane"})
    assert _writer(tmp_path).has_complete_identity(CATEGORIES)


def test_has_complete_identity_false_when_absent(tmp_path):
    assert not _writer(tmp_path).has_complete_identity(CATEGORIES)


def test_has_complete_identity_false_for_a_truncated_file(tmp_path):
    (tmp_path / "identity.json").write_text('{"age": 20, "biological_', encoding="utf-8")
    assert not _writer(tmp_path).has_complete_identity(CATEGORIES)


def test_has_complete_identity_false_for_a_zero_byte_file(tmp_path):
    (tmp_path / "identity.json").write_text("", encoding="utf-8")
    assert not _writer(tmp_path).has_complete_identity(CATEGORIES)


@pytest.mark.parametrize("empty_value", [None, "", "   "])
def test_has_complete_identity_false_when_a_category_is_empty(tmp_path, empty_value):
    _writer(tmp_path).finalize({"age": 20, "biological_sex": empty_value, "region": "Skane"})
    assert not _writer(tmp_path).has_complete_identity(CATEGORIES)


def test_has_complete_identity_false_when_a_category_is_missing(tmp_path):
    _writer(tmp_path).finalize({"age": 20, "biological_sex": "female"})
    assert not _writer(tmp_path).has_complete_identity(CATEGORIES)


def test_has_complete_identity_false_for_a_nested_object(tmp_path):
    _writer(tmp_path).finalize(
        {"age": 20, "biological_sex": "female", "region": {"name": "Skane"}}
    )
    assert not _writer(tmp_path).has_complete_identity(CATEGORIES)


def test_has_complete_identity_rejects_an_empty_requirement(tmp_path):
    _writer(tmp_path).finalize({"age": 20})
    with pytest.raises(ValueError, match="resolved category order"):
        _writer(tmp_path).has_complete_identity([])


# -- shared lifecycle --------------------------------------------------------


def _record(writer: PersonaWriter, index: int) -> None:
    writer.telemetry.record(
        LLMInteractionEntry(
            category="age",
            method="pick",
            step="pick",
            prompt="p",
            raw_response="r",
            persona_id="persona_00000",
            call_index=index,
        )
    )


def _telemetry_lines(tmp_path) -> list[dict]:
    text = (tmp_path / "llm_interactions.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_telemetry_truncates_when_starting_fresh(tmp_path):
    first = _writer(tmp_path)
    _record(first, 1)
    first.close()

    second = _writer(tmp_path)
    _record(second, 1)
    second.close()

    # No checkpoint to resume from, so the second pass owns the whole file.
    assert len(_telemetry_lines(tmp_path)) == 1


def test_telemetry_appends_when_resuming(tmp_path):
    first = _writer(tmp_path)
    _record(first, 1)
    first.checkpoint({"age": 20}, call_index=1)
    first.close()

    second = _writer(tmp_path)
    assert second.resume() is not None
    _record(second, 2)
    second.close()

    entries = _telemetry_lines(tmp_path)
    keys = [(e["persona_id"], e["call_index"]) for e in entries]
    assert keys == [("persona_00000", 1), ("persona_00000", 2)]
    assert len(set(keys)) == len(keys)


def test_telemetry_truncates_when_the_checkpoint_is_discarded(tmp_path):
    first = _writer(tmp_path)
    _record(first, 1)
    first.checkpoint({"age": 20}, call_index=1)
    first.close()

    forced = _writer(tmp_path, discard=True)
    _record(forced, 1)
    forced.close()

    # Discarding the checkpoint restarts call_index, so the old records MUST go:
    # keeping them would duplicate (persona_id, call_index) and inflate cost.
    assert len(_telemetry_lines(tmp_path)) == 1


def test_telemetry_mode_is_decided_before_the_first_record_either_order(tmp_path):
    first = _writer(tmp_path)
    _record(first, 1)
    first.checkpoint({"age": 20}, call_index=1)
    first.close()

    # Touching .telemetry BEFORE resume() must reach the same verdict: the property
    # resolves the resume decision itself rather than trusting call order.
    second = _writer(tmp_path)
    _record(second, 2)
    assert second.resume() is not None
    second.close()

    assert len(_telemetry_lines(tmp_path)) == 2


def test_close_is_safe_when_no_telemetry_was_ever_opened(tmp_path):
    _writer(tmp_path).close()
    assert not (tmp_path / "llm_interactions.jsonl").exists()


def test_resume_continues_past_attempts_spent_after_the_last_checkpoint(tmp_path):
    """The failing-category case: retries spend indices the checkpoint never saw.

    A category that exhausts its retry budget records one telemetry entry per
    attempt and then raises, so the persona's last checkpoint is older than the
    highest index actually spent. Resuming from the checkpoint alone would hand
    those indices out twice.
    """
    first = _writer(tmp_path)
    _record(first, 1)
    first.checkpoint({"age": 20}, call_index=1)
    for index in (2, 3, 4):  # the failing category's three attempts
        _record(first, index)
    first.close()

    state = _writer(tmp_path).resume()

    assert state is not None
    assert state.resolved == {"age": 20}
    assert state.call_index == 4


def test_a_torn_telemetry_line_does_not_cost_the_readable_indices(tmp_path):
    # A kill mid-append leaves a partial trailing line; the records before it are
    # still evidence of indices that were spent.
    first = _writer(tmp_path)
    _record(first, 1)
    first.checkpoint({"age": 20}, call_index=1)
    _record(first, 2)
    first.close()
    with (tmp_path / "llm_interactions.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"persona_id": "persona_00000", "call_i')

    assert _writer(tmp_path).resume().call_index == 2


def test_has_checkpoint_reports_presence_without_consuming_it(tmp_path):
    writer = _writer(tmp_path)
    assert writer.has_checkpoint is False

    _write_checkpoint(tmp_path, _valid_payload())
    # A stale-fingerprint checkpoint is still *present*: the counting query must not
    # reach the verdict that deletes it, which belongs to the attempt that generates.
    stale = PersonaWriter(tmp_path, {**FINGERPRINT, "strategy_sha256": "c" * 64})
    assert stale.has_checkpoint is True
    assert (tmp_path / "identity.partial.json").exists()
