"""Unit tests for the durable-overwrite helpers in ``utils/atomic_io``.

The module exists so that a killed run can never leave a half-written file that a
later run then trusts. These tests exercise the three properties that guarantee
it: the destination is only ever replaced by a complete file, a serialiser that
raises leaves no residue, and concurrent writers to one path cannot collide on a
temporary name (the generation runner writes from a thread pool).
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from population_synthetic.utils import atomic_write_json, atomic_write_text


def _temp_residue(directory: Path) -> list[Path]:
    """Every leftover temp file the helpers could have produced in ``directory``."""
    return [p for p in directory.iterdir() if p.name.endswith(".tmp")]


class Unserializable:
    """A value ``json.dump`` refuses, so the failure happens mid-write."""


def test_atomic_write_text_creates_parents_and_writes(tmp_path):
    target = tmp_path / "nested" / "deeper" / "out.txt"
    atomic_write_text(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"
    assert _temp_residue(target.parent) == []


def test_atomic_write_json_overwrites_previous_content(tmp_path):
    target = tmp_path / "out.json"
    atomic_write_json(target, {"a": 1, "b": 2})
    atomic_write_json(target, {"a": 9})
    # Overwrite, not merge or append: the file is the whole authoritative state.
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 9}


def test_atomic_write_json_preserves_key_insertion_order(tmp_path):
    target = tmp_path / "out.json"
    payload = {"zulu": 1, "alpha": 2, "mike": 3}
    atomic_write_json(target, payload)
    # Guards the sort_keys trap: the checkpoint's key order is the DAG order the
    # prompts were built from, so sorting it would break resume-faithfulness.
    assert list(json.loads(target.read_text(encoding="utf-8"))) == ["zulu", "alpha", "mike"]


def test_serializer_failure_leaves_no_temp_residue(tmp_path):
    target = tmp_path / "out.json"
    with pytest.raises(TypeError):
        atomic_write_json(target, {"ok": 1, "bad": Unserializable()})
    assert not target.exists()
    assert _temp_residue(tmp_path) == []


def test_serializer_failure_leaves_the_previous_file_intact(tmp_path):
    target = tmp_path / "out.json"
    atomic_write_json(target, {"generation": 1})
    with pytest.raises(TypeError):
        atomic_write_json(target, {"generation": Unserializable()})
    # All-or-nothing: a reader sees the old complete file, never a torn new one.
    assert json.loads(target.read_text(encoding="utf-8")) == {"generation": 1}
    assert _temp_residue(tmp_path) == []


def test_base_exception_during_write_leaves_no_temp_residue(tmp_path):
    target = tmp_path / "out.txt"

    class Interrupt(BaseException):
        """Stands in for the KeyboardInterrupt/SystemExit class of kill."""

    def _boom(_handle):
        raise Interrupt

    from population_synthetic.utils.atomic_io import _atomic_write

    with pytest.raises(Interrupt):
        _atomic_write(target, _boom, encoding="utf-8")
    assert _temp_residue(tmp_path) == []


def test_concurrent_writes_to_one_path_yield_a_valid_file(tmp_path):
    target = tmp_path / "contended.json"
    n_writers = 16

    def _write(i: int) -> None:
        atomic_write_json(target, {"writer": i, "payload": ["x"] * 500})

    with ThreadPoolExecutor(max_workers=n_writers) as pool:
        list(pool.map(_write, range(n_writers)))

    # Unique temp names (mkstemp) mean no two writers interleave into one file, so
    # the survivor is exactly one writer's complete payload.
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["writer"] in range(n_writers)
    assert data["payload"] == ["x"] * 500
    assert _temp_residue(tmp_path) == []
