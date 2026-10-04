"""Every ``claude`` CLI call is an independent conversation, and stale verdicts are refused.

Offline tests (a fake ``subprocess.Popen`` stands in for the CLI) for:

* :class:`ClaudeCodeClient` -- one fresh process per call, the prompt on stdin only,
  minimal launch flags, no session flag, a neutral working directory, process cleanup
  on timeout / error results, and honest ``temperature_applied`` / ``context_isolation``
  metadata;
* the persona-realism runner's context-isolation gate -- a verdict cache written under
  the old shared-conversation regime is neither reused nor topped up without
  ``--force``, and a client that cannot vouch for isolation may not write the cache;
* the artifact layer and the ``realism_ranking`` homogeneity gate refusing to mix regimes.

A live probe (two real calls; the second must not recover a secret set by the first)
runs only with ``RUN_LIVE_CLAUDE=1``.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import population_synthetic.clients.claude_code_client as ccc
from population_synthetic.analysis.model_ranking.loader import scheme_attributes
from population_synthetic.analysis.persona_realism import artifacts as A
from population_synthetic.analysis.persona_realism.config import JudgeConfig
from population_synthetic.analysis.persona_realism.runner import (
    JUDGE_CONTEXT_ISOLATION,
    run_combo_judgements,
)
from population_synthetic.analysis.realism_ranking.loader import _assert_homogeneous
from tests.test_persona_realism_smoke import (
    _CONFIG_DIR,
    _cfg,
    _stub_factory,
    _StubClient,
    _synthetic_population,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SESSION_FLAGS = {"--continue", "-c", "--resume", "-r", "--session-id", "--fork-session",
                  "--input-format"}


# --------------------------------------------------------------------------- #
# fake CLI                                                                     #
# --------------------------------------------------------------------------- #


class _FakeProc:
    """One fake ``claude -p`` process: answers with how many prompts IT has received.

    A stateful CLI reusing one conversation would report 2 on the second call; a
    fresh process per call can only ever report 1.
    """

    def __init__(self, registry: list[_FakeProc], argv, *, mode: str, **kwargs) -> None:
        self.argv = list(argv)
        self.cwd = kwargs.get("cwd")
        self.cwd_was_empty = self.cwd is not None and not any(Path(self.cwd).iterdir())
        self.pid = 40000 + len(registry)
        self.mode = mode
        self.inputs: list[str] = []
        self.returncode: int | None = None
        self.killed = False
        registry.append(self)

    def communicate(self, input=None, timeout=None):  # noqa: A002 -- Popen's own name
        self.inputs.append(input)
        if self.mode == "hang":
            raise subprocess.TimeoutExpired(cmd="claude", timeout=timeout)
        self.returncode = 0
        if self.mode == "garbage":
            return "not json at all", ""
        payload = {
            "type": "result",
            "is_error": self.mode == "error",
            "result": "model refused" if self.mode == "error" else f"messages_seen={len(self.inputs)}",
            "session_id": f"session-{self.pid}",
            "usage": {"input_tokens": 500, "output_tokens": 5,
                      "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
        }
        return json.dumps(payload), ""

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


@pytest.fixture
def fake_cli(monkeypatch):
    """Patch the client's Popen; return (registry, set_mode)."""
    registry: list[_FakeProc] = []
    state = {"mode": "ok"}
    monkeypatch.setattr(ccc.shutil, "which", lambda name: "C:/fake/claude.exe")
    monkeypatch.setattr(
        ccc.subprocess, "Popen",
        lambda argv, **kw: _FakeProc(registry, argv, mode=state["mode"], **kw),
    )
    taskkills: list[list[str]] = []

    def _fake_run(argv, **kw):
        taskkills.append(list(argv))
        for proc in registry:
            if str(proc.pid) in argv:
                proc.kill()
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(ccc.subprocess, "run", _fake_run)
    monkeypatch.setattr(ccc.os, "killpg", lambda pgid, sig: None, raising=False)
    monkeypatch.setattr(ccc.os, "getpgid", lambda pid: pid, raising=False)

    def set_mode(mode: str) -> None:
        state["mode"] = mode

    return registry, set_mode


def _client(**kw) -> ccc.ClaudeCodeClient:
    return ccc.ClaudeCodeClient(model_name="claude-sonnet-5", base_delay=0.0, max_delay=0.0, **kw)


# --------------------------------------------------------------------------- #
# client                                                                       #
# --------------------------------------------------------------------------- #


def test_each_call_is_a_fresh_process_that_sees_only_its_own_prompt(fake_cli):
    registry, _ = fake_cli
    client = _client(default_config={"temperature": 0.0})

    first = client.generate_content("The secret word is PELICAN.", system_instruction="SYS")
    second = client.generate_content("What was the secret word?", system_instruction="SYS")

    # Two calls, two processes; each process saw exactly one prompt: its own.
    assert len(registry) == 2
    assert first == "messages_seen=1" and second == "messages_seen=1"
    assert registry[0].inputs == ["The secret word is PELICAN."]
    assert registry[1].inputs == ["What was the secret word?"]
    assert "PELICAN" not in " ".join(registry[1].argv + registry[1].inputs)


def test_launch_is_minimal_and_never_resumes_a_session(fake_cli):
    registry, _ = fake_cli
    client = _client()
    client.generate_content("p1", system_instruction="SYS")
    client.generate_content("p2", system_instruction="SYS")

    for proc in registry:
        argv = proc.argv
        assert argv[:2] == ["claude", "-p"]
        assert not _SESSION_FLAGS & set(argv)
        # flag followed by an empty value: no tools, no setting sources
        assert argv[argv.index("--tools") + 1] == ""
        assert argv[argv.index("--setting-sources") + 1] == ""
        assert "--strict-mcp-config" in argv and "--no-session-persistence" in argv
        assert argv[argv.index("--output-format") + 1] == "json"
        assert argv[argv.index("--system-prompt") + 1] == "SYS"
        # The prompt travels on stdin, never in argv.
        assert not any(arg in ("p1", "p2") for arg in argv)
        # Neutral working directory: an empty temp dir, never the repository.
        assert proc.cwd is not None and proc.cwd_was_empty
        assert Path(proc.cwd).resolve() != _REPO_ROOT
        assert not Path(proc.cwd).exists()  # removed after the call
    assert registry[0].cwd != registry[1].cwd


def test_metadata_is_honest_about_isolation_and_temperature(fake_cli):
    client = _client(default_config={"temperature": 0.0})
    client.generate_content("p", system_instruction="SYS")
    meta = client.last_metadata
    assert meta["context_isolation"] == ccc.CONTEXT_ISOLATION == JUDGE_CONTEXT_ISOLATION
    assert meta["temperature_applied"] is False
    assert meta["status"] == "ok"
    assert meta["prompt_tokens"] == 500 and meta["completion_tokens"] == 5
    assert meta["cache_read_tokens"] == 0 and meta["cache_creation_tokens"] == 0
    assert meta["session_id"].startswith("session-")


def test_timeout_kills_every_process_and_raises_timeout(fake_cli):
    registry, set_mode = fake_cli
    set_mode("hang")
    client = _client(max_retries=2)
    with pytest.raises(RuntimeError, match="failed after 2 attempts"):
        client.generate_content("p", system_instruction="SYS")
    assert len(registry) == 2  # one fresh process per attempt
    assert all(proc.killed and proc.poll() is not None for proc in registry)
    assert client.last_metadata["error_category"] == "timeout"


def test_error_result_raises_model_limitation_and_leaves_no_process(fake_cli):
    registry, set_mode = fake_cli
    set_mode("error")
    client = _client(max_retries=1)
    with pytest.raises(RuntimeError, match="error result"):
        client.generate_content("p", system_instruction="SYS")
    assert all(proc.poll() is not None for proc in registry)
    assert client.last_metadata["error_category"] == "model_limitation"


def test_unparsable_stdout_raises_instead_of_returning_empty(fake_cli):
    _, set_mode = fake_cli
    set_mode("garbage")
    client = _client(max_retries=1)
    with pytest.raises(RuntimeError, match="no parsable result"):
        client.generate_content("p", system_instruction="SYS")


# --------------------------------------------------------------------------- #
# runner gate                                                                  #
# --------------------------------------------------------------------------- #


def _strip_tag(combo_dir: Path) -> None:
    """Turn every persona cache into a pre-fix (untagged) one."""
    for path in combo_dir.glob("persona_[0-9]*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.pop("context_isolation", None)
        path.write_text(json.dumps(payload), encoding="utf-8")


def test_runner_stamps_the_isolation_tag_into_every_cache(tmp_path):
    attrs = scheme_attributes("swedish")
    combo_dir = tmp_path / "combo"
    run_combo_judgements(_synthetic_population(attrs), "combo", attrs, combo_dir, _cfg(),
                         client_factory=_stub_factory())
    for path in combo_dir.glob("persona_[0-9]*.json"):
        assert json.loads(path.read_text(encoding="utf-8"))["context_isolation"] == JUDGE_CONTEXT_ISOLATION


def test_runner_refuses_to_reuse_or_top_up_an_untagged_cache(tmp_path):
    attrs = scheme_attributes("swedish")
    population = _synthetic_population(attrs)
    combo_dir = tmp_path / "combo"
    cfg1 = dataclasses.replace(_cfg(), n_rounds=1)
    run_combo_judgements(population, "combo", attrs, combo_dir, cfg1, client_factory=_stub_factory())
    _strip_tag(combo_dir)

    # Complete cache: not silently skipped.
    with pytest.raises(ValueError, match="--force"):
        run_combo_judgements(population, "combo", attrs, combo_dir, cfg1, client_factory=_stub_factory())
    # Partial cache: not topped up (that would mix regimes inside one persona).
    cfg2 = dataclasses.replace(_cfg(), n_rounds=2)
    with pytest.raises(ValueError, match="context_isolation"):
        run_combo_judgements(population, "combo", attrs, combo_dir, cfg2, client_factory=_stub_factory())

    # Plan-only judges nothing, so it may still read the old cache (artifact rewrite).
    planned = run_combo_judgements(population, "combo", attrs, combo_dir, cfg1, plan_only=True,
                                   client_factory=_stub_factory())
    assert planned.skipped == 4

    # --force re-judges from scratch under the current regime.
    forced = run_combo_judgements(population, "combo", attrs, combo_dir, cfg1, force=True,
                                  client_factory=_stub_factory())
    assert forced.written == 4
    for path in combo_dir.glob("persona_[0-9]*.json"):
        assert json.loads(path.read_text(encoding="utf-8"))["context_isolation"] == JUDGE_CONTEXT_ISOLATION


def test_runner_refuses_a_client_that_does_not_vouch_for_isolation(tmp_path):
    class _LeakyClient(_StubClient):
        def generate_content(self, user, *, model, system_instruction):
            out = super().generate_content(user, model=model, system_instruction=system_instruction)
            self.last_metadata.pop("context_isolation")
            return out

    attrs = scheme_attributes("swedish")
    with pytest.raises(RuntimeError, match="independent conversation"):
        run_combo_judgements(_synthetic_population(attrs), "combo", attrs, tmp_path / "combo",
                             _cfg(), client_factory=lambda: _LeakyClient())


# --------------------------------------------------------------------------- #
# config, artifacts, ranking gate                                              #
# --------------------------------------------------------------------------- #


def test_judge_config_refuses_a_temperature_the_cli_cannot_apply(tmp_path):
    for name in ("judge.yaml", "judge_prompt.md"):
        (tmp_path / name).write_text((_CONFIG_DIR / name).read_text(encoding="utf-8"), encoding="utf-8")
    JudgeConfig.load(tmp_path)  # the shipped config declares none
    with (tmp_path / "judge.yaml").open("a", encoding="utf-8") as fh:
        fh.write("\ntemperature: 0.0\n")
    with pytest.raises(ValueError, match="temperature"):
        JudgeConfig.load(tmp_path)


def test_artifacts_stamp_the_cache_regime_and_refuse_a_mixed_combo(tmp_path):
    attrs = scheme_attributes("swedish")
    combo_dir = tmp_path / "combo"
    cfg = _cfg()
    run_combo_judgements(_synthetic_population(attrs), "combo", attrs, combo_dir, cfg,
                         client_factory=_stub_factory())
    A.write_combo_artifacts(combo_dir, "combo", cfg=cfg, dpi=60, force=True)
    provenance = json.loads((combo_dir / "combo.json").read_text(encoding="utf-8"))["provenance"]
    assert provenance["context_isolation"] == JUDGE_CONTEXT_ISOLATION
    assert provenance["temperature"] is None and provenance["temperature_applied"] is False

    # One persona from the old regime: the combination's statistics would pool two.
    first = sorted(combo_dir.glob("persona_[0-9]*.json"))[0]
    payload = json.loads(first.read_text(encoding="utf-8"))
    payload.pop("context_isolation")
    first.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="mixed context-isolation"):
        A.write_combo_artifacts(combo_dir, "combo", cfg=cfg, dpi=60, force=True)


def test_ranking_refuses_a_consumption_set_mixing_regimes():
    def _rec(slug, tag):
        return SimpleNamespace(slug=slug, provenance={
            "judge_model": "m", "prompt_template_sha256": "h", "n_rounds": 1, "context_isolation": tag,
        })

    _assert_homogeneous([_rec("a", JUDGE_CONTEXT_ISOLATION), _rec("b", JUDGE_CONTEXT_ISOLATION)],
                        cap_active=False)
    for cap_active in (False, True):
        with pytest.raises(ValueError, match="context_isolation"):
            _assert_homogeneous(
                [_rec("a", JUDGE_CONTEXT_ISOLATION), _rec("b", A.UNTAGGED_CONTEXT_ISOLATION)],
                cap_active=cap_active,
            )
        with pytest.raises(ValueError, match="context_isolation"):
            _assert_homogeneous([_rec("a", JUDGE_CONTEXT_ISOLATION), _rec("b", None)], cap_active=cap_active)


# --------------------------------------------------------------------------- #
# opt-in live probe                                                            #
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(os.environ.get("RUN_LIVE_CLAUDE") != "1", reason="live claude CLI probe; set RUN_LIVE_CLAUDE=1")
def test_live_second_call_cannot_recover_a_secret_from_the_first():
    client = ccc.ClaudeCodeClient(model_name="claude-sonnet-5", timeout=120)
    client.generate_content("The secret word is PELICAN. Reply only OK.", system_instruction="Be terse.")
    answer = client.generate_content(
        "What was the secret word? If you do not know, reply UNKNOWN.", system_instruction="Be terse."
    )
    assert "PELICAN" not in answer.upper()
