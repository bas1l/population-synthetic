"""Orchestration-edge tests for the Ollama pre-flight in the parallel generator.

The pre-flight is the one step of a generation run with a side effect on a machine
other people share: it restarts a container, evicts whatever model was loaded and
kills any in-flight request from another user of that GPU. **No test here may touch
the network or perform a real restart** -- the control client is injected (either as
a :class:`FakeControlClient` handed to the helper, or as a factory that fails the
test if it is ever constructed), and the inference port is served by a
:class:`FakeSession`.

Two levels are exercised, because the guarantees live at two levels:

* the **helper** (``_ollama_preflight``) decides whether to act at all and turns the
  policy layer's records into the three provenance blocks;
* the **CLI** (``main``) supplies the conditions that helper branches on, and lands
  the blocks in ``run_metadata.json``.

Testing only one would leave the join untested: a skip that the helper honours but
the CLI never reaches, or a record the CLI writes under a key nothing reads.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from typing import Any

import pytest

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.clients.ollama_control_client import ControlServiceError
from population_synthetic.generators.synthetic import ollama_concurrency
from population_synthetic.generators.synthetic.ollama_hosts import OllamaHost

from ._ollama_fakes import BASE_URL, CONTROL_URL, FakeControlClient, FakeResponse, FakeSession, ps_body

MODEL = "deepseek-r1:14b"
OTHER_MODEL = "mistral-nemo:12b"
WORKERS = 6

CONFIG = PROJECT_ROOT / "config" / "synthetic" / "simulation_configs" / "simulation_config_004_swedish_generative.json"
STRATEGY = PROJECT_ROOT / "config" / "synthetic" / "axes" / "strategies" / "all_pick.yaml"

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


def _host(control_url: str | None = CONTROL_URL) -> OllamaHost:
    """A registry host pointed at the fakes' unroutable endpoints."""
    return OllamaHost(
        id="fake_host",
        label="Fake host",
        base_url=BASE_URL,
        gpu="Fake GPU",
        server_num_parallel=1,
        control_url=control_url,
    )


def _boom_factory(*args: Any, **kwargs: Any) -> Any:
    """A control-client factory that fails the test if it is ever constructed."""
    raise AssertionError(f"the control client must not be constructed here (got {args!r})")


def _warm_session(model: str = MODEL, ledger: list[str] | None = None) -> FakeSession:
    """Inference-port fake for one full pre-flight: probe, warm-up, probe again.

    ``/api/ps`` answers "nothing loaded" for the first probe and for the warm-up's own
    residency check, then "loaded" for the closing probe -- which is the measured real
    sequence, since ``/reconfigure`` recreates the container without loading anything.
    """
    return FakeSession(
        {
            "/api/ps": [
                FakeResponse(ps_body(None)),
                FakeResponse(ps_body(None)),
                FakeResponse(ps_body(model)),
            ],
            "/api/tags": FakeResponse({"models": []}),
            "/api/chat": FakeResponse({"message": {"role": "assistant", "content": "ready"}}),
        },
        ledger=ledger,
    )


# ---------------------------------------------------------------------------
# Helper level: when the pre-flight declines to act at all
# ---------------------------------------------------------------------------


def test_flag_off_leaves_the_host_untouched() -> None:
    """Without ``--ollama-reconfigure`` nothing is probed and nothing is recorded.

    The three blocks are null rather than an outcome object: "the feature was off" is
    a different fact from "it ran and found nothing to do", and a later timing
    analysis must be able to tell them apart.
    """
    driver = _load_driver()
    record = driver._ollama_preflight(
        _host(), "ollama", MODEL, WORKERS, requested=False, control_client_factory=_boom_factory
    )
    assert record == {"reconfigure": None, "warm_up": None, "readiness": None, "server_state": None}


def test_preflight_is_skipped_for_non_ollama_providers() -> None:
    """A bound host and the flag set still change nothing when the run is not Ollama.

    Guards the same inertness the ``--ollama-host`` flag already has: a stray flag on
    a Gemini or Claude run must not reach out to any server.
    """
    driver = _load_driver()
    for provider in ("gemini", "claude", "openrouter", "openai_compat"):
        record = driver._ollama_preflight(
            _host(), provider, MODEL, WORKERS, requested=True, control_client_factory=_boom_factory
        )
        assert record == {"reconfigure": None, "warm_up": None, "readiness": None, "server_state": None}


def test_no_host_bound_records_no_control_url_without_probing() -> None:
    """``--base-url`` leaves no host bound, so there is nothing legitimate to restart.

    The run is hitting a machine the registry does not describe; reconfiguring the
    registry's host instead would restart the wrong GPU while the outputs looked
    perfectly normal.
    """
    driver = _load_driver()
    record = driver._ollama_preflight(
        None, "ollama", MODEL, WORKERS, requested=True, control_client_factory=_boom_factory
    )
    assert record["reconfigure"]["outcome"] == ollama_concurrency.OUTCOME_NO_CONTROL_URL
    assert record["reconfigure"]["observed"] is None
    assert record["reconfigure"]["control_url"] is None
    # Never established, so never invented.
    assert record["warm_up"] is None
    assert record["readiness"] is None
    assert record["server_state"] is None


def test_host_without_control_url_records_no_control_url() -> None:
    """A host declaring no control endpoint behaves exactly as it did before."""
    driver = _load_driver()
    record = driver._ollama_preflight(
        _host(control_url=None), "ollama", MODEL, WORKERS, requested=True,
        control_client_factory=_boom_factory,
    )
    assert record["reconfigure"]["outcome"] == ollama_concurrency.OUTCOME_NO_CONTROL_URL
    assert record["warm_up"] is None


# ---------------------------------------------------------------------------
# Helper level: when it does act
# ---------------------------------------------------------------------------


def test_applied_records_observed_from_the_read_back() -> None:
    """``observed`` is the value ``/status`` reports afterwards, not the one requested.

    A 200 from ``/reconfigure`` is unvalidated boundary data. The whole provenance
    block is worthless if it merely echoes the request.
    """
    driver = _load_driver()
    client = FakeControlClient(env={"OLLAMA_NUM_PARALLEL": "1"}, models={MODEL: WORKERS})
    record = driver._ollama_preflight(
        _host(), "ollama", MODEL, WORKERS, requested=True,
        control_client_factory=lambda url: client, session=_warm_session(),
    )

    assert record["reconfigure"]["outcome"] == ollama_concurrency.OUTCOME_APPLIED
    assert record["reconfigure"]["requested"] == WORKERS
    assert record["reconfigure"]["observed"] == WORKERS
    assert record["reconfigure"]["control_url"] == CONTROL_URL
    assert client.count("reconfigure") == 1

    # The restart left nothing resident, so the warm-up is what loaded the model.
    assert record["warm_up"]["performed"] is True
    assert record["warm_up"]["model"] == MODEL
    assert record["warm_up"]["error"] is None
    assert record["readiness"]["state"] == ollama_concurrency.READINESS_READY


def test_failed_records_a_null_observed_never_the_requested_value() -> None:
    """With the control service down, ``observed`` is null and the run still proceeds.

    Recording the requested value here would make a run that queued at
    ``NUM_PARALLEL=1`` indistinguishable from one that batched at six -- the exact
    contamination this provenance exists to prevent.
    """
    driver = _load_driver()
    client = FakeControlClient(status_error=ControlServiceError("unreachable at /status"))
    record = driver._ollama_preflight(
        _host(), "ollama", MODEL, WORKERS, requested=True,
        control_client_factory=lambda url: client, session=_warm_session(),
    )

    assert record["reconfigure"]["outcome"] == ollama_concurrency.OUTCOME_FAILED
    assert record["reconfigure"]["observed"] is None
    assert record["reconfigure"]["requested"] == WORKERS
    assert client.count("reconfigure") == 0
    # Not fatal, and the gate names why rather than leaving the run merely slow-looking.
    assert record["readiness"]["state"] == ollama_concurrency.READINESS_NOT_READY
    assert record["readiness"]["reason"] == ollama_concurrency.REASON_UNREACHABLE


def test_drift_between_config_and_the_server_is_warned_alongside_the_preflight(caplog) -> None:
    """``/models`` validates the configured worker count; it never overrides it."""
    driver = _load_driver()
    client = FakeControlClient(env={"OLLAMA_NUM_PARALLEL": str(WORKERS)}, models={MODEL: 2})
    with caplog.at_level(logging.WARNING):
        record = driver._ollama_preflight(
            _host(), "ollama", MODEL, WORKERS, requested=True,
            control_client_factory=lambda url: client, session=_warm_session(),
        )

    assert any("drift" in r.getMessage().lower() for r in caplog.records)
    assert any(str(WORKERS) in r.getMessage() and "2" in r.getMessage() for r in caplog.records)
    # Config stays authoritative: the run is still tuned to the configured count.
    assert record["reconfigure"]["observed"] == WORKERS


def test_drift_agreement_is_stated_rather_than_left_silent(caplog) -> None:
    """Silence cannot distinguish "the check agreed" from "the check never ran"."""
    driver = _load_driver()
    client = FakeControlClient(env={"OLLAMA_NUM_PARALLEL": str(WORKERS)}, models={MODEL: WORKERS})
    with caplog.at_level(logging.INFO):
        driver._ollama_preflight(
            _host(), "ollama", MODEL, WORKERS, requested=True,
            control_client_factory=lambda url: client, session=_warm_session(),
        )

    agreed = [r.getMessage() for r in caplog.records if "drift" in r.getMessage().lower()]
    assert len(agreed) == 1
    assert MODEL in agreed[0] and str(WORKERS) in agreed[0]
    assert not any(r.levelno >= logging.WARNING for r in caplog.records if "drift" in r.getMessage().lower())


def test_server_state_block_records_the_evidence_behind_the_verdicts() -> None:
    """A finished run must be auditable, not only a live one.

    ``resident_model`` is the sharpest case: which model the host actually had loaded
    -- and therefore which one this run's warm-up evicted -- is recoverable from
    nothing else once the run is over.
    """
    driver = _load_driver()
    client = FakeControlClient(env={"OLLAMA_NUM_PARALLEL": "1"}, models={MODEL: WORKERS})
    session = FakeSession(
        {
            "/api/ps": [
                FakeResponse(ps_body(OTHER_MODEL)),
                FakeResponse(ps_body(None)),
                FakeResponse(ps_body(MODEL)),
            ],
            "/api/tags": FakeResponse({"models": []}),
            "/api/chat": FakeResponse({"message": {"role": "assistant", "content": "ready"}}),
        }
    )
    record = driver._ollama_preflight(
        _host(), "ollama", MODEL, WORKERS, requested=True,
        control_client_factory=lambda url: client, session=session,
    )

    before = record["server_state"]["before"]
    after = record["server_state"]["after"]
    assert before["resident_model"] == OTHER_MODEL
    assert before["num_parallel"] == 1
    # Not the model this run wanted, so its VRAM occupancy was never measured.
    assert before["vram_fully_loaded"] is None
    assert after["resident_model"] == MODEL
    assert after["num_parallel"] == WORKERS

    # It lands in run_metadata.json as JSON, and the absent facts stay null there.
    round_tripped = json.loads(json.dumps(record))["server_state"]
    assert round_tripped["before"]["vram_fully_loaded"] is None
    assert round_tripped["after"]["resident_model"] == MODEL


def test_a_fully_warm_host_costs_nothing() -> None:
    """Parallelism already right and model already resident: zero restarts, zero loads."""
    driver = _load_driver()
    client = FakeControlClient(env={"OLLAMA_NUM_PARALLEL": str(WORKERS)}, models={MODEL: WORKERS})
    session = FakeSession(
        {"/api/ps": FakeResponse(ps_body(MODEL)), "/api/tags": FakeResponse({"models": []})}
    )
    record = driver._ollama_preflight(
        _host(), "ollama", MODEL, WORKERS, requested=True,
        control_client_factory=lambda url: client, session=session,
    )

    assert record["reconfigure"]["outcome"] == ollama_concurrency.OUTCOME_ALREADY_CORRECT
    assert client.count("reconfigure") == 0
    assert record["warm_up"]["performed"] is False
    assert session.count("/api/chat") == 0
    assert record["readiness"]["state"] == ollama_concurrency.READINESS_READY


# ---------------------------------------------------------------------------
# CLI level: the conditions the helper branches on, and the provenance file
# ---------------------------------------------------------------------------


@pytest.fixture
def cli(tmp_path, monkeypatch):
    """Run ``main()`` with generation stubbed out, and return the parsed metadata.

    ``_generate_one`` is replaced at module scope (``main`` resolves it as a global at
    submit time), so no client of any provider is ever constructed. The run's file
    handler is detached afterwards: it is added to the *root* logger and never
    removed, so leaving it would keep writing every later test's log lines into a
    deleted temp directory. The root *level* is restored for the same reason --
    ``--log-level`` sets it globally, and a run left at DEBUG would change what every
    later test in the session captures.
    """
    driver = _load_driver()
    root = logging.getLogger()
    before = list(root.handlers)
    before_level = root.level

    def _run(argv: list[str]) -> dict[str, Any]:
        out_dir = tmp_path / f"run_{len(list(tmp_path.iterdir()))}"
        monkeypatch.setattr(
            driver, "_generate_one", lambda **kw: (kw["index"], True, "ok"), raising=True
        )
        monkeypatch.setattr(
            sys, "argv",
            [
                "generate_identities_parallel.py",
                "--mode", "configurable",
                "--config", str(CONFIG),
                "--strategy", str(STRATEGY),
                "--n", "1",
                "--workers", str(WORKERS),
                "--output-dir", str(out_dir),
                *argv,
            ],
        )
        driver.main()
        return json.loads((out_dir / "run_metadata.json").read_text(encoding="utf-8"))

    yield _run

    root.setLevel(before_level)
    for handler in list(root.handlers):
        if handler not in before:
            root.removeHandler(handler)
            handler.close()


def test_cli_base_url_run_skips_the_preflight_entirely(cli, monkeypatch, caplog) -> None:
    """``--base-url`` overrides the registry host, so no control client is built.

    The integration-level twin of the helper test above: this pins that the CLI
    really does leave ``ollama_host`` unbound on that path, which is what makes the
    skip reachable at all.
    """
    driver = _load_driver()
    monkeypatch.setattr(driver, "OllamaControlClient", _boom_factory, raising=True)

    with caplog.at_level(logging.WARNING):
        metadata = cli([
            "--provider", "ollama", "--model", MODEL,
            "--ollama-host", "windows_4070tis",
            "--base-url", "http://elsewhere.invalid:11434",
            "--ollama-reconfigure",
        ])

    params = metadata["parameters"]
    assert params["ollama_host"] is None
    assert params["ollama_reconfigure"]["outcome"] == ollama_concurrency.OUTCOME_NO_CONTROL_URL
    assert params["ollama_reconfigure"]["observed"] is None
    assert params["ollama_warm_up"] is None
    assert params["ollama_readiness"] is None


def test_cli_log_level_lowers_the_root_logger_not_just_a_handler(cli) -> None:
    """The only lever that works is the root level.

    A file handler set to DEBUG under a root logger left at INFO is inert -- the
    record is dropped by ``Logger.isEnabledFor`` before any handler is consulted --
    so the run log silently never received the detail its handler level advertised.
    """
    root = logging.getLogger()

    cli(["--provider", "claude", "--model", "sonnet"])
    assert root.level == logging.INFO

    cli(["--provider", "claude", "--model", "sonnet", "--log-level", "DEBUG"])
    assert root.level == logging.DEBUG
    # And nothing between the logger and the run log file subtracts from that, so the
    # log an operator reads afterwards matches the console they watched.
    file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
    assert file_handlers
    assert all(h.level == logging.NOTSET for h in file_handlers)


def test_cli_non_ollama_provider_records_three_null_blocks(cli, monkeypatch) -> None:
    """A cloud run carries the keys with null values -- present, and honestly empty."""
    driver = _load_driver()
    monkeypatch.setattr(driver, "OllamaControlClient", _boom_factory, raising=True)

    metadata = cli(["--provider", "claude", "--model", "sonnet", "--ollama-reconfigure"])

    params = metadata["parameters"]
    assert params["ollama_reconfigure"] is None
    assert params["ollama_warm_up"] is None
    assert params["ollama_readiness"] is None


def test_cli_records_every_block_and_suppresses_the_stale_warning(cli, monkeypatch, caplog) -> None:
    """On ``applied`` the declared ``server_num_parallel`` is stale, so it must not warn.

    Six workers against a host declaring ``OLLAMA_NUM_PARALLEL=1`` is exactly the
    condition the warning exists for -- and exactly the condition the pre-flight has
    just removed.
    """
    driver = _load_driver()
    applied = {
        "reconfigure": {
            "outcome": ollama_concurrency.OUTCOME_APPLIED, "requested": WORKERS,
            "observed": WORKERS, "elapsed_seconds": 9.83, "control_url": CONTROL_URL, "detail": None,
        },
        "warm_up": {"performed": True, "model": MODEL, "load_seconds": 83.4, "error": None},
        "readiness": {
            "state": ollama_concurrency.READINESS_READY, "reason": None,
            "waited_seconds": 14.68, "vram_fully_loaded": True,
        },
        "server_state": {
            "before": {
                "reachable": True, "container_running": True, "num_parallel": 1,
                "resident_model": "mistral-nemo:12b", "vram_fully_loaded": None,
            },
            "after": {
                "reachable": True, "container_running": True, "num_parallel": WORKERS,
                "resident_model": MODEL, "vram_fully_loaded": True,
            },
        },
    }
    seen: dict[str, Any] = {}

    def _stub(host, provider, model, workers, *, requested, **kwargs):
        seen.update(host=host, provider=provider, model=model, workers=workers, requested=requested)
        return applied

    monkeypatch.setattr(driver, "_ollama_preflight", _stub, raising=True)

    with caplog.at_level(logging.WARNING):
        metadata = cli([
            "--provider", "ollama", "--model", MODEL,
            "--ollama-host", "windows_4070tis", "--ollama-reconfigure",
        ])

    # The helper is handed the resolved values, not the raw CLI ones.
    assert seen["provider"] == "ollama" and seen["model"] == MODEL
    assert seen["workers"] == WORKERS and seen["requested"] is True
    assert seen["host"].id == "windows_4070tis"

    params = metadata["parameters"]
    assert params["ollama_reconfigure"] == applied["reconfigure"]
    assert params["ollama_warm_up"] == applied["warm_up"]
    assert params["ollama_readiness"] == applied["readiness"]
    assert params["ollama_server_state"] == applied["server_state"]
    assert not any("exceeds the declared OLLAMA_NUM_PARALLEL" in r.getMessage() for r in caplog.records)


def test_cli_failed_outcome_still_warns_and_records_a_null_observed(cli, monkeypatch, caplog) -> None:
    """``failed`` means "could not verify", so the warning's condition still stands."""
    driver = _load_driver()
    failed = {
        "reconfigure": {
            "outcome": ollama_concurrency.OUTCOME_FAILED, "requested": WORKERS, "observed": None,
            "elapsed_seconds": None, "control_url": CONTROL_URL,
            "detail": "Ollama control service unreachable at http://localhost:11435/status.",
        },
        "warm_up": {"performed": True, "model": MODEL, "load_seconds": 0.1, "error": "refused"},
        "readiness": {
            "state": ollama_concurrency.READINESS_NOT_READY,
            "reason": ollama_concurrency.REASON_UNREACHABLE,
            "waited_seconds": 0.0, "vram_fully_loaded": None,
        },
        "server_state": {
            "before": {
                "reachable": False, "container_running": None, "num_parallel": None,
                "resident_model": None, "vram_fully_loaded": None,
            },
            "after": {
                "reachable": False, "container_running": None, "num_parallel": None,
                "resident_model": None, "vram_fully_loaded": None,
            },
        },
    }
    monkeypatch.setattr(driver, "_ollama_preflight", lambda *a, **k: failed, raising=True)

    with caplog.at_level(logging.WARNING):
        metadata = cli([
            "--provider", "ollama", "--model", MODEL,
            "--ollama-host", "windows_4070tis", "--ollama-reconfigure",
        ])

    params = metadata["parameters"]
    assert params["ollama_reconfigure"]["observed"] is None
    assert params["ollama_reconfigure"]["detail"]
    # The warm-up is recorded separately: persona_00000 still carries the cold load.
    assert params["ollama_warm_up"]["error"] == "refused"
    assert any("exceeds the declared OLLAMA_NUM_PARALLEL" in r.getMessage() for r in caplog.records)
