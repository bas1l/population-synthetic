"""End-to-end kill-and-resume smoke over the real generation stack.

Everything below the CLI is real here -- ``main()``'s argument resolution, the
strategy/schema loading, the DAG, ``SyntheticPopulation``'s resume plan, the four
``Category`` classes, ``ResolutionContext``, ``Persona`` and ``PersonaWriter``.
Only the transport is faked: a scripted client that returns canned JSON and can be
told to fail one category, which is how a killed persona is simulated without
killing the test process.

The run is driven three times over one output directory, which is the whole point:

1. a first pass in which every persona fails partway, leaving checkpoints;
2. a resumed pass that finishes them, re-paying for at most the failed category;
3. a third pass over an already-complete directory, which must generate nothing.

Each pass's ``run_metadata.json`` is asserted on, because a resumed run and a clean
one are otherwise indistinguishable after the fact and their cost figures are not
interchangeable.

``_debug_minimal.yaml`` is used deliberately: two ``pick`` categories, so a whole
persona costs two calls and the *second* one is the seam a checkpoint sits on.
"""

from __future__ import annotations

import json
import logging
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.validate_raw.validate import validate_raw_combo
from tests._driver import load_parallel_driver

_STRATEGY = PROJECT_ROOT / "config" / "synthetic" / "axes" / "strategies" / "_debug_minimal.yaml"
_CATEGORIES = ("biological_sex", "birth_location")
_FAILING_CATEGORY = "birth_location"
_N = 3


class _ScriptedClient:
    """Returns canned JSON, and fails on one category while ``fail`` is set.

    Class-level state because the runner constructs one client per worker and the
    test needs to count calls across all of them.
    """

    fail: bool = False
    calls: int = 0

    def __init__(self, model_name: str, default_config: dict | None = None) -> None:
        self.model_name = model_name
        self.retry_until_success = False
        self.last_metadata: dict[str, Any] = {}

    def generate_content(self, prompt: str, system_instruction: str = "", **kwargs: Any) -> str:
        type(self).calls += 1
        self.last_metadata = {"provider": "fake", "model": self.model_name}
        if type(self).fail and f"'{_FAILING_CATEGORY}'" in prompt:
            # Neither 'auth' nor 'model_limitation', so it exhausts the JSON-parse
            # budget rather than escaping it -- the same shape as a flaky endpoint.
            self.last_metadata["error_category"] = "server_error"
            raise RuntimeError("scripted transport failure")
        return json.dumps({"value": "scripted"})

    def get_current_configuration(self) -> dict:
        return {"model": self.model_name}


@pytest.fixture
def driver(monkeypatch):
    """The real driver, with only the provider module replaced."""
    module = load_parallel_driver()
    stub = types.ModuleType("population_synthetic.clients.gemini_client")
    stub.GeminiClient = _ScriptedClient
    monkeypatch.setitem(sys.modules, "population_synthetic.clients.gemini_client", stub)
    _ScriptedClient.fail = False
    _ScriptedClient.calls = 0

    root = logging.getLogger()
    handlers = list(root.handlers)
    level = root.level
    yield module
    # main() attaches a run-log FileHandler per invocation, and this test invokes it
    # three times; without this the handlers (and their open files) outlive the test.
    for handler in root.handlers:
        if handler not in handlers:
            handler.close()
    root.handlers = handlers
    root.setLevel(level)


def _schema(tmp_path: Path) -> Path:
    path = tmp_path / "flat_schema.json"
    path.write_text(
        json.dumps(
            {
                "instruction": ["You are generating a persona."],
                "categories": {name: {"description": f"desc for {name}"} for name in _CATEGORIES},
            }
        ),
        encoding="utf-8",
    )
    return path


def _run(driver, monkeypatch, schema: Path, out: Path, *, force: bool = False) -> dict:
    argv = [
        "generate_identities_parallel.py",
        "--mode", "configurable",
        "--config", str(schema),
        "--strategy", str(_STRATEGY),
        "--provider", "gemini",
        "--model", "fake-model",
        "--n", str(_N),
        "--workers", "2",
        "--output-dir", str(out),
    ]
    if force:
        argv.append("--force")
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(driver, "_completed", 0, raising=False)
    monkeypatch.setattr(driver, "_failed", 0, raising=False)
    driver.main()
    return json.loads((out / "run_metadata.json").read_text(encoding="utf-8"))


def _persona_dirs(out: Path) -> list[Path]:
    return sorted(out.glob("persona_*"))


def _telemetry_keys(persona_dir: Path) -> list[tuple[str, int]]:
    text = (persona_dir / "llm_interactions.jsonl").read_text(encoding="utf-8")
    return [
        (json.loads(line)["persona_id"], json.loads(line)["call_index"])
        for line in text.splitlines()
        if line.strip()
    ]


def test_a_killed_run_resumes_and_says_so_in_its_metadata(driver, monkeypatch, tmp_path):
    schema = _schema(tmp_path)
    out = tmp_path / "combo"

    # -- pass 1: every persona dies on its second category ---------------------
    _ScriptedClient.fail = True
    first = _run(driver, monkeypatch, schema, out)

    assert first["resume"] == {
        "resumed": False,
        "skipped_complete": 0,
        "resumed_from_checkpoint": 0,
        "pending": _N,
    }
    assert len(_persona_dirs(out)) == _N
    for persona in _persona_dirs(out):
        assert not (persona / "identity.json").exists()
        checkpoint = json.loads((persona / "identity.partial.json").read_text(encoding="utf-8"))
        assert list(checkpoint["resolved"]) == [_CATEGORIES[0]]

    # A persona that failed every round leaves a partial and no identity, and the
    # downstream gate must read that as an unfinished slot -- not as a corrupt one,
    # and not as a pass.
    failed = validate_raw_combo("combo", out, list(_CATEGORIES), tmp_path / "failed.csv")
    assert (failed["passed"], failed["failed"], failed["missing_identity"]) == (0, _N, _N)

    calls_after_first = _ScriptedClient.calls

    # -- pass 2: the same command again, no flags ------------------------------
    _ScriptedClient.fail = False
    second = _run(driver, monkeypatch, schema, out)

    assert second["resume"] == {
        "resumed": True,
        "skipped_complete": 0,
        "resumed_from_checkpoint": _N,
        "pending": _N,
    }
    for persona in _persona_dirs(out):
        identity = json.loads((persona / "identity.json").read_text(encoding="utf-8"))
        assert list(identity) == list(_CATEGORIES)
        # The kill-safety criterion: nothing partial survives a completed persona.
        assert not (persona / "identity.partial.json").exists()
        keys = _telemetry_keys(persona)
        assert len(keys) == len(set(keys)), "resume duplicated a (persona_id, call_index) pair"

    # Only the category that failed is re-paid: one call per persona, not two.
    assert _ScriptedClient.calls - calls_after_first == _N

    # -- pass 3: nothing left to do -------------------------------------------
    calls_after_second = _ScriptedClient.calls
    third = _run(driver, monkeypatch, schema, out)

    assert third["resume"] == {
        "resumed": True,
        "skipped_complete": _N,
        "resumed_from_checkpoint": 0,
        "pending": 0,
    }
    # A fully-complete rerun is a true no-op: no client is even constructed.
    assert _ScriptedClient.calls == calls_after_second


def test_force_reports_a_clean_run_and_regenerates_everything(driver, monkeypatch, tmp_path):
    schema = _schema(tmp_path)
    out = tmp_path / "combo"

    _run(driver, monkeypatch, schema, out)
    calls_after_first = _ScriptedClient.calls

    forced = _run(driver, monkeypatch, schema, out, force=True)

    # --force inherits nothing by construction, so it can never report resumed.
    assert forced["resume"] == {
        "resumed": False,
        "skipped_complete": 0,
        "resumed_from_checkpoint": 0,
        "pending": _N,
    }
    assert _ScriptedClient.calls - calls_after_first == _N * len(_CATEGORIES)
    for persona in _persona_dirs(out):
        # Truncated in lockstep with the discarded checkpoint: a restarted counter
        # over retained records would double-count every call in the cost analysis.
        assert [index for _, index in _telemetry_keys(persona)] == [1, 2]
