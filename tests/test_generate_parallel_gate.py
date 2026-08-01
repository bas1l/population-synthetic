"""Orchestration-edge tests for the parallel runner's resume gate and force split.

Two decisions live in ``_generate_one`` and nowhere else, so they are tested here
rather than through the writer:

* **the gate** -- a persona is skipped only when its ``identity.json`` is
  *complete*, not merely present. The exists-only check this replaces treated the
  truncated remains of a killed ``json.dump`` as a finished persona forever.
* **the force split** -- a retry round bypasses the skip but keeps the checkpoint
  (the categories the failed attempt paid for are still valid under the same
  fingerprint), while ``--force`` discards it. The single fused ``force`` flag
  they replace made every retry round throw away the work it was retrying.

No LLM client is constructed: the provider module is stubbed into ``sys.modules``
and the factory is patched to hand back a scripted generator.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from population_synthetic._paths import PROJECT_ROOT

CATEGORIES = ["age", "biological_sex", "region"]
FINGERPRINT = {
    "strategy_sha256": "a" * 64,
    "schema_sha256": "b" * 64,
    "model_key": "gemini:gemini-2.5-flash",
    "category_order": CATEGORIES,
}
PERSONA = {"age": 41, "biological_sex": "female", "region": "Skane"}

_driver: Any = None


def _load_driver() -> Any:
    """Load the CLI driver by file path (``scripts/`` is not an importable package).

    Cached: the module attaches a console handler to the root logger at import, so
    re-importing it per test would multiply that handler across the whole session.
    """
    global _driver
    if _driver is None:
        path = PROJECT_ROOT / "scripts" / "generate" / "generate_identities_parallel.py"
        spec = importlib.util.spec_from_file_location("generate_identities_parallel", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _driver = module
    return _driver


class _FakeClient:
    def __init__(self, model_name: str, default_config: dict | None = None) -> None:
        self.model_name = model_name
        self.retry_until_success = False


class _ScriptedGenerator:
    """Stands in for a real generator; records what the injected writer offered it."""

    def __init__(self) -> None:
        self.client: Any = None
        self.interaction_collector: Any = None
        self.writer: Any = None
        self.persona_id: str | None = None
        self.retry_until_success = False
        self.use_structured_output = False
        self.observed_resume: Any = "not-called"
        self.calls = 0

    def generate_identity(self, config_path: str, **kwargs: Any) -> tuple[dict, dict]:
        self.calls += 1
        self.observed_resume = self.writer.resume()
        return dict(PERSONA), {}


@pytest.fixture
def runner(monkeypatch, tmp_path):
    """The driver with its provider import and generator factory stubbed out."""
    driver = _load_driver()

    stub = types.ModuleType("population_synthetic.clients.gemini_client")
    stub.GeminiClient = _FakeClient
    monkeypatch.setitem(sys.modules, "population_synthetic.clients.gemini_client", stub)

    generator = _ScriptedGenerator()

    class _Factory:
        @staticmethod
        def create_generator(mode: str, client: Any) -> _ScriptedGenerator:
            generator.client = client
            return generator

    monkeypatch.setattr(driver, "FactoryIdentityGenerator", _Factory)
    monkeypatch.setattr(driver, "_completed", 0, raising=False)
    monkeypatch.setattr(driver, "_failed", 0, raising=False)
    return driver, generator


def _generate(driver, tmp_path, **overrides: Any) -> tuple[int, bool, str]:
    kwargs: dict[str, Any] = {
        "index": 0,
        "total": 1,
        "mode": "configurable",
        "provider": "gemini",
        "model": "gemini-2.5-flash",
        "config_path": "unused.json",
        "output_dir": tmp_path,
        "kwargs": {},
        "log_llm": False,
        "fingerprint": FINGERPRINT,
        "required_categories": CATEGORIES,
    }
    kwargs.update(overrides)
    return driver._generate_one(**kwargs)


def _persona_dir(tmp_path) -> Path:
    return tmp_path / "persona_00000"


def _write_checkpoint(persona_dir: Path, resolved: dict, call_index: int = 3) -> None:
    persona_dir.mkdir(parents=True, exist_ok=True)
    (persona_dir / "identity.partial.json").write_text(
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


# -- the gate ----------------------------------------------------------------


def test_complete_persona_is_skipped(runner, tmp_path):
    driver, generator = runner
    persona = _persona_dir(tmp_path)
    persona.mkdir()
    (persona / "identity.json").write_text(json.dumps(PERSONA), encoding="utf-8")

    index, ok, msg = _generate(driver, tmp_path)

    assert (index, ok, msg) == (0, True, "skipped (complete)")
    assert generator.calls == 0


def test_skipping_clears_a_stale_checkpoint(runner, tmp_path):
    driver, _ = runner
    persona = _persona_dir(tmp_path)
    persona.mkdir()
    (persona / "identity.json").write_text(json.dumps(PERSONA), encoding="utf-8")
    _write_checkpoint(persona, {"age": 41})

    _generate(driver, tmp_path)

    # A kill between finalize()'s identity write and its unlink leaves both files;
    # the skip path is the only place that orphan is ever collected.
    assert not (persona / "identity.partial.json").exists()


def test_truncated_identity_is_regenerated_without_force(runner, tmp_path):
    driver, generator = runner
    persona = _persona_dir(tmp_path)
    persona.mkdir()
    (persona / "identity.json").write_text('{"age": 41, "biologic', encoding="utf-8")

    index, ok, msg = _generate(driver, tmp_path)

    # The defect this replaces: the exists-only gate skipped this file forever.
    assert (index, ok, msg) == (0, True, "ok")
    assert generator.calls == 1
    assert json.loads((persona / "identity.json").read_text(encoding="utf-8")) == PERSONA


def test_incomplete_identity_is_regenerated_without_force(runner, tmp_path):
    driver, generator = runner
    persona = _persona_dir(tmp_path)
    persona.mkdir()
    (persona / "identity.json").write_text(json.dumps({"age": 41}), encoding="utf-8")

    _generate(driver, tmp_path)

    assert generator.calls == 1


def test_finalize_leaves_no_checkpoint_behind(runner, tmp_path):
    driver, _ = runner
    _generate(driver, tmp_path)
    assert not (_persona_dir(tmp_path) / "identity.partial.json").exists()
    assert json.loads((_persona_dir(tmp_path) / "identity.json").read_text(encoding="utf-8")) == PERSONA


# -- the force split ---------------------------------------------------------


def test_retry_round_bypasses_the_skip_but_keeps_the_checkpoint(runner, tmp_path):
    driver, generator = runner
    persona = _persona_dir(tmp_path)
    _write_checkpoint(persona, {"age": 41, "biological_sex": "female"}, call_index=5)

    _generate(driver, tmp_path, bypass_identity_skip=True, discard_checkpoint=False)

    assert generator.calls == 1
    assert generator.observed_resume is not None
    assert generator.observed_resume.resolved == {"age": 41, "biological_sex": "female"}
    assert generator.observed_resume.call_index == 5


def test_force_discards_the_checkpoint(runner, tmp_path):
    driver, generator = runner
    persona = _persona_dir(tmp_path)
    _write_checkpoint(persona, {"age": 41, "biological_sex": "female"})

    _generate(driver, tmp_path, bypass_identity_skip=True, discard_checkpoint=True)

    assert generator.calls == 1
    assert generator.observed_resume is None


def test_force_regenerates_a_complete_persona_and_drops_its_stale_partial(runner, tmp_path):
    driver, generator = runner
    persona = _persona_dir(tmp_path)
    persona.mkdir()
    (persona / "identity.json").write_text(json.dumps({"age": 1, "biological_sex": "m", "region": "X"}),
                                           encoding="utf-8")
    _write_checkpoint(persona, {"age": 41})

    _generate(driver, tmp_path, bypass_identity_skip=True, discard_checkpoint=True)

    assert generator.calls == 1
    assert generator.observed_resume is None
    assert not (persona / "identity.partial.json").exists()
    assert json.loads((persona / "identity.json").read_text(encoding="utf-8")) == PERSONA


# -- fail-fast ---------------------------------------------------------------


@pytest.mark.parametrize(
    "missing", [{"fingerprint": None}, {"required_categories": None}, {"required_categories": []}]
)
def test_missing_run_identity_is_refused(runner, tmp_path, missing):
    driver, _ = runner
    with pytest.raises(ValueError, match="fingerprint and resolved category order"):
        _generate(driver, tmp_path, **missing)
