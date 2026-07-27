"""Unit and integration tests for the Ollama server-concurrency policy.

Covers :mod:`population_synthetic.generators.synthetic.ollama_concurrency` -- the
decision layer that brings a host's ``OLLAMA_NUM_PARALLEL`` in line with a run,
loads the model, and proves the server can serve before the first persona.

Four properties carry the feature and each has dedicated coverage:

1. **The skip check.** A restart is idempotent in end state but not in side effects:
   each one evicts the loaded model and kills any in-flight request from another user
   of that GPU. A GUI Run over five strategies must therefore issue exactly *one*
   ``/reconfigure``, not five.
2. **Reconfigure does not load a model.** Measured: it returns in 0.44 s with
   ``/api/ps`` still reporting ``{"models": []}``. The warm-up is a separate step that
   runs regardless of the reconfigure outcome, and it must follow a restart, never
   precede it -- warming first would simply be discarded.
3. **Observed, never requested.** Five outcome states, with ``mismatch`` ("verified
   wrong") and ``failed`` ("could not verify") never collapsed, and ``observed``
   always from a ``/status`` read-back.
4. **The gate proves rather than assumes.** ``/reconfigure`` returning 200 means
   Docker recreated the container; the port, the parallelism and the residency are
   three separate facts, none of which follows from the others.

No test touches the network or performs a real restart -- the control client and the
HTTP session are both injected fakes (``tests/_ollama_fakes.py``).
"""

from __future__ import annotations

import logging

import pytest
import requests

from population_synthetic.clients.ollama_control_client import ControlServiceError
from population_synthetic.generators.synthetic.ollama_concurrency import (
    OUTCOME_ALREADY_CORRECT,
    OUTCOME_APPLIED,
    OUTCOME_FAILED,
    OUTCOME_MISMATCH,
    OUTCOME_NO_CONTROL_URL,
    READINESS_NOT_READY,
    READINESS_READY,
    REASON_MODEL_NOT_RESIDENT,
    REASON_NUM_PARALLEL_MISMATCH,
    REASON_PORT_TIMEOUT,
    REASON_UNREACHABLE,
    check_worker_drift,
    ensure_num_parallel,
    preflight,
    probe,
    resident_model,
    wait_until_serving,
    warm_up,
)

from ._ollama_fakes import BASE_URL, CONTROL_URL, FakeControlClient, FakeResponse, FakeSession, ps_body

MODEL = "qwen3:14b"
OTHER_MODEL = "mistral-nemo:12b"
REFUSED = requests.exceptions.ConnectionError("connection refused")


def _routes(*, ps=None, tags=None, chat=None) -> dict:
    """Assemble inference-port routes, defaulting to a healthy, model-less server."""
    return {
        "/api/ps": ps if ps is not None else FakeResponse(ps_body(None)),
        "/api/tags": tags if tags is not None else FakeResponse({"models": []}),
        "/api/chat": chat if chat is not None else FakeResponse({"message": {"content": "ready"}}),
    }


def _preflight(control, session, **kwargs):
    """Run a pre-flight with the poll loop collapsed so tests never sleep."""
    kwargs.setdefault("gate_budget_s", 1.0)
    kwargs.setdefault("gate_interval_s", 0.0)
    return preflight(control, BASE_URL, MODEL, kwargs.pop("desired", 4), session=session, **kwargs)


# ---------------------------------------------------------------------------
# ensure_num_parallel -- the five outcome states
# ---------------------------------------------------------------------------


def test_already_correct_when_running_and_value_matches() -> None:
    """The skip path issues no restart at all and reports the observed value."""
    control = FakeControlClient(env={"OLLAMA_NUM_PARALLEL": "4"})

    outcome = ensure_num_parallel(control, MODEL, 4)

    assert outcome.outcome == OUTCOME_ALREADY_CORRECT
    assert (outcome.requested, outcome.observed) == (4, 4)
    assert outcome.elapsed_seconds is None
    assert outcome.control_url == CONTROL_URL
    assert control.count("reconfigure") == 0


def test_container_not_running_is_not_already_correct() -> None:
    """A running container is a *partial* marker; both conditions must hold.

    The value matches, so a check that looked only at ``OLLAMA_NUM_PARALLEL`` would
    skip -- and leave the run pointed at a stopped container.
    """
    control = FakeControlClient(env={"OLLAMA_NUM_PARALLEL": "4"}, container_running=False)

    outcome = ensure_num_parallel(control, MODEL, 4)

    assert outcome.outcome == OUTCOME_APPLIED
    assert control.count("reconfigure") == 1


def test_applied_when_read_back_confirms_the_request() -> None:
    control = FakeControlClient(env={"OLLAMA_NUM_PARALLEL": "1"})

    outcome = ensure_num_parallel(control, MODEL, 4)

    assert outcome.outcome == OUTCOME_APPLIED
    assert (outcome.requested, outcome.observed) == (4, 4)
    assert outcome.elapsed_seconds is not None and outcome.elapsed_seconds >= 0.0
    assert control.count("reconfigure") == 1


def test_mismatch_when_the_read_back_returns_a_different_value() -> None:
    """A 200 is not proof: the service applied 2 while reporting success for 4.

    ``mismatch`` is "verified wrong" and must never be collapsed into ``failed``
    ("could not verify") -- they mean different things for any later timing analysis.
    """

    def apply_something_else(client, _model, _num_parallel):
        client.env["OLLAMA_NUM_PARALLEL"] = "2"

    control = FakeControlClient(env={"OLLAMA_NUM_PARALLEL": "1"}, on_reconfigure=apply_something_else)

    outcome = ensure_num_parallel(control, MODEL, 4)

    assert outcome.outcome == OUTCOME_MISMATCH
    assert (outcome.requested, outcome.observed) == (4, 2)
    assert "4" in outcome.detail and "2" in outcome.detail


def test_failed_when_the_initial_status_read_fails() -> None:
    control = FakeControlClient(status_error=ControlServiceError("unreachable at /status"))

    outcome = ensure_num_parallel(control, MODEL, 4)

    assert outcome.outcome == OUTCOME_FAILED
    assert outcome.observed is None
    assert control.count("reconfigure") == 0
    assert "/status" in outcome.detail


def test_failed_when_the_reconfigure_call_fails() -> None:
    control = FakeControlClient(reconfigure_error=ControlServiceError("timed out after 120s"))

    outcome = ensure_num_parallel(control, MODEL, 4)

    assert outcome.outcome == OUTCOME_FAILED
    assert outcome.observed is None  # never the requested value
    assert "120s" in outcome.detail


def test_failed_when_the_read_back_itself_fails() -> None:
    """The restart may have worked, but we cannot say so -- ``failed``, not ``applied``."""

    def break_status(client, _model, _num_parallel):
        client.status_error = ControlServiceError("service went away")

    control = FakeControlClient(on_reconfigure=break_status)

    outcome = ensure_num_parallel(control, MODEL, 4)

    assert outcome.outcome == OUTCOME_FAILED
    assert outcome.observed is None
    assert "read-back" in outcome.detail


def test_read_back_declaring_nothing_is_failed_not_mismatch() -> None:
    """"Could not verify" is a distinct fact from "verified wrong"."""

    def drop_the_key(client, _model, _num_parallel):
        client.env.pop("OLLAMA_NUM_PARALLEL", None)

    control = FakeControlClient(on_reconfigure=drop_the_key)

    outcome = ensure_num_parallel(control, MODEL, 4)

    assert outcome.outcome == OUTCOME_FAILED
    assert outcome.observed is None


def test_no_control_url_when_no_client_is_bound() -> None:
    """An explicit ``--base-url``, or a host without a control service, lands here."""
    outcome = ensure_num_parallel(None, MODEL, 4)

    assert outcome.outcome == OUTCOME_NO_CONTROL_URL
    assert outcome.requested == 4
    assert outcome.observed is None
    assert outcome.control_url is None
    assert "ollama_hosts.yaml" in outcome.detail


# ---------------------------------------------------------------------------
# resident_model / probe -- Ollama's own state, on the inference port
# ---------------------------------------------------------------------------


def test_resident_model_reads_the_inference_port_not_the_control_port() -> None:
    session = FakeSession(_routes(ps=FakeResponse(ps_body(MODEL))))

    assert resident_model(BASE_URL, session=session) == MODEL
    assert session.calls[0][1] == f"{BASE_URL}/api/ps"


@pytest.mark.parametrize(
    "responder",
    [
        pytest.param(FakeResponse(ps_body(None)), id="nothing-loaded"),
        pytest.param(REFUSED, id="unreachable"),
        pytest.param(requests.exceptions.Timeout("slow"), id="timeout"),
        pytest.param(FakeResponse({}, status_code=500), id="server-error"),
        pytest.param(FakeResponse({"models": "qwen3:14b"}), id="malformed-models"),
        pytest.param(FakeResponse(["qwen3:14b"]), id="malformed-root"),
        pytest.param(FakeResponse(status_code=200, text="not json"), id="non-json"),
    ],
)
def test_resident_model_is_none_rather_than_a_guess(responder) -> None:
    """Unloaded and unknowable both yield ``None``; neither is ever guessed at."""
    assert resident_model(BASE_URL, session=FakeSession(_routes(ps=responder))) is None


def test_probe_reports_every_fact_it_could_establish() -> None:
    control = FakeControlClient(env={"OLLAMA_NUM_PARALLEL": "4"})
    session = FakeSession(_routes(ps=FakeResponse(ps_body(MODEL))))

    state = probe(control, BASE_URL, MODEL, session=session)

    assert state.reachable is True
    assert state.container_running is True
    assert state.num_parallel == 4
    assert state.resident_model == MODEL
    assert state.vram_fully_loaded is True


def test_probe_marks_unknown_facts_none_rather_than_defaulting_them() -> None:
    """No control endpoint bound: unknown, which is not the same as ``False``."""
    session = FakeSession(_routes(ps=REFUSED))

    state = probe(None, BASE_URL, MODEL, session=session)

    assert state.reachable is None
    assert state.container_running is None
    assert state.num_parallel is None
    assert state.resident_model is None
    assert state.vram_fully_loaded is None


def test_probe_reports_the_control_service_as_unreachable_when_it_refuses() -> None:
    control = FakeControlClient(status_error=ControlServiceError("refused"))

    state = probe(control, BASE_URL, MODEL, session=FakeSession(_routes()))

    assert state.reachable is False
    assert state.num_parallel is None


def test_probe_names_the_model_actually_loaded_when_it_is_not_the_one_wanted() -> None:
    session = FakeSession(_routes(ps=FakeResponse(ps_body(OTHER_MODEL))))

    state = probe(None, BASE_URL, MODEL, session=session)

    assert state.resident_model == OTHER_MODEL
    # VRAM occupancy is only meaningful for the model this run is about.
    assert state.vram_fully_loaded is None


def test_probe_detects_a_kv_cache_spilled_to_cpu() -> None:
    """``size_vram < size`` is the cliff the POC measured: 2-3x throughput collapse."""
    session = FakeSession(_routes(ps=FakeResponse(ps_body(MODEL, size=10_000, size_vram=6_000))))

    assert probe(None, BASE_URL, MODEL, session=session).vram_fully_loaded is False


# ---------------------------------------------------------------------------
# wait_until_serving -- the window between "container recreated" and "port bound"
# ---------------------------------------------------------------------------


def test_wait_until_serving_returns_immediately_when_the_port_is_up() -> None:
    session = FakeSession(_routes())

    waited = wait_until_serving(BASE_URL, budget_s=1.0, interval_s=0.0, session=session)

    assert waited is not None and waited >= 0.0
    assert session.count("/api/tags") == 1


def test_wait_until_serving_polls_through_the_refusal_window() -> None:
    """Ollama bound its port 14.68 s after ``/reconfigure`` returned, on the slow host."""
    session = FakeSession(_routes(tags=[REFUSED, REFUSED, FakeResponse({"models": []})]))

    waited = wait_until_serving(BASE_URL, budget_s=5.0, interval_s=0.0, session=session)

    assert waited is not None
    assert session.count("/api/tags") == 3


def test_wait_until_serving_returns_none_when_the_budget_elapses() -> None:
    """A timeout is recorded, not raised: the per-persona client validates too."""
    session = FakeSession(_routes(tags=REFUSED))

    assert wait_until_serving(BASE_URL, budget_s=0.0, interval_s=0.0, session=session) is None
    assert session.count("/api/tags") == 1  # at least one attempt is always made


# ---------------------------------------------------------------------------
# warm_up -- what actually loads a model
# ---------------------------------------------------------------------------


def test_warm_up_is_skipped_when_the_model_is_already_resident() -> None:
    session = FakeSession(_routes(ps=FakeResponse(ps_body(MODEL))))

    outcome = warm_up(BASE_URL, MODEL, session=session)

    assert outcome.performed is False
    assert outcome.error is None
    assert session.count("/api/chat") == 0


def test_warm_up_issues_one_discarded_chat_when_the_model_is_absent() -> None:
    session = FakeSession(_routes(ps=FakeResponse(ps_body(None))))

    outcome = warm_up(BASE_URL, MODEL, session=session)

    assert outcome.performed is True
    assert outcome.load_seconds is not None
    assert session.count("/api/chat") == 1
    _, _, payload = [call for call in session.calls if call[1].endswith("/api/chat")][0]
    assert payload["model"] == MODEL
    assert payload["options"]["num_predict"] == 4
    assert payload["stream"] is False


@pytest.mark.parametrize(
    "responder",
    [
        pytest.param(REFUSED, id="unreachable"),
        pytest.param(FakeResponse({"models": "nonsense"}), id="malformed"),
    ],
)
def test_warm_up_runs_anyway_when_api_ps_cannot_be_read(responder) -> None:
    """One redundant warm-up is cheap; a skipped one bills a cold load to persona_00000."""
    session = FakeSession(_routes(ps=responder))

    assert warm_up(BASE_URL, MODEL, session=session).performed is True
    assert session.count("/api/chat") == 1


@pytest.mark.parametrize(
    "responder",
    [
        pytest.param(requests.exceptions.Timeout("600s elapsed"), id="timeout"),
        pytest.param(REFUSED, id="unreachable"),
        pytest.param(FakeResponse({}, status_code=500), id="server-error"),
    ],
)
def test_warm_up_failure_is_recorded_and_never_fatal(responder, caplog) -> None:
    session = FakeSession(_routes(chat=responder))

    with caplog.at_level(logging.WARNING):
        outcome = warm_up(BASE_URL, MODEL, session=session)

    assert outcome.performed is True
    assert outcome.error is not None and MODEL in outcome.error
    assert "first persona" in caplog.text


# ---------------------------------------------------------------------------
# preflight -- PROBE -> ACT -> GATE, and the ordering that is not interchangeable
# ---------------------------------------------------------------------------


def test_fully_warm_path_issues_no_action_at_all() -> None:
    """Right parallelism, right model resident: ACT does nothing, GATE still passes."""
    control = FakeControlClient(env={"OLLAMA_NUM_PARALLEL": "4"})
    session = FakeSession(_routes(ps=FakeResponse(ps_body(MODEL))))

    result = _preflight(control, session)

    assert result.reconfigure.outcome == OUTCOME_ALREADY_CORRECT
    assert result.warm_up.performed is False
    assert result.readiness.state == READINESS_READY
    assert control.count("reconfigure") == 0
    assert session.count("/api/chat") == 0


@pytest.mark.parametrize(
    ("resident", "wanted", "workers"),
    [
        # The two real same-worker-count collisions in today's axis config.
        pytest.param("mistral-nemo:12b", "qwen3:14b", 4, id="nemo-then-qwen3-at-4"),
        pytest.param("gemma2:9b", "llama3.3:70b-instruct-q4_K_M", 1, id="gemma2-then-llama70b-at-1"),
    ],
)
def test_same_worker_count_different_model_skips_restart_but_still_warms_up(resident, wanted, workers) -> None:
    """The resident model is deliberately not part of the skip condition.

    Reconfiguring does not load a model, so restarting on a residency mismatch would
    cost a container restart and still leave the model unloaded.
    """
    control = FakeControlClient(env={"OLLAMA_NUM_PARALLEL": str(workers)})
    session = FakeSession(_routes(ps=FakeResponse(ps_body(resident))))

    result = preflight(control, BASE_URL, wanted, workers, session=session, gate_budget_s=1.0, gate_interval_s=0.0)

    assert result.reconfigure.outcome == OUTCOME_ALREADY_CORRECT
    assert control.count("reconfigure") == 0
    assert result.warm_up.performed is True
    assert session.count("/api/chat") == 1


def test_applied_reconfigure_still_triggers_a_warm_up() -> None:
    """Measured real behaviour: after a reconfigure ``/api/ps`` is ``{"models": []}``.

    A test asserting that ``applied`` implies "model loaded" would encode the exact
    conflation this design corrected by measurement.
    """
    control = FakeControlClient(env={"OLLAMA_NUM_PARALLEL": "1"})
    session = FakeSession(_routes(ps=FakeResponse(ps_body(None))))

    result = _preflight(control, session)

    assert result.reconfigure.outcome == OUTCOME_APPLIED
    assert result.warm_up.performed is True
    assert session.count("/api/chat") == 1


def test_warm_up_follows_the_reconfigure_never_precedes_it() -> None:
    """Ordering is not interchangeable: a restart evicts whatever was warmed first."""
    ledger: list[str] = []
    control = FakeControlClient(env={"OLLAMA_NUM_PARALLEL": "1"}, ledger=ledger)
    session = FakeSession(_routes(ps=FakeResponse(ps_body(None))), ledger=ledger)

    _preflight(control, session)

    assert ledger.index("reconfigure") < ledger.index("/api/chat")
    # And the port poll sits between them: a chat fired at a container Docker has
    # recreated but Ollama has not yet bound to would simply fail.
    assert ledger.index("reconfigure") < ledger.index("/api/tags") < ledger.index("/api/chat")


def test_warm_up_runs_even_without_a_control_service() -> None:
    """A host with no control endpoint benefits from the warm-up just as much."""
    session = FakeSession(_routes(ps=FakeResponse(ps_body(None))))

    result = preflight(None, BASE_URL, MODEL, 4, session=session, gate_budget_s=1.0, gate_interval_s=0.0)

    assert result.reconfigure.outcome == OUTCOME_NO_CONTROL_URL
    assert result.warm_up.performed is True


# ---------------------------------------------------------------------------
# preflight -- the gate
# ---------------------------------------------------------------------------


def test_gate_is_ready_after_a_successful_reconfigure_and_warm_up() -> None:
    control = FakeControlClient(env={"OLLAMA_NUM_PARALLEL": "1"})
    # One /api/ps read per stage: PROBE (empty, the reconfigure evicted everything),
    # the warm-up's own check (still empty), then GATE (loaded).
    session = FakeSession(
        _routes(ps=[FakeResponse(ps_body(None)), FakeResponse(ps_body(None)), FakeResponse(ps_body(MODEL))])
    )

    result = _preflight(control, session)

    assert result.reconfigure.outcome == OUTCOME_APPLIED
    assert result.warm_up.performed is True
    assert result.readiness.state == READINESS_READY
    assert result.readiness.reason is None
    assert result.readiness.waited_seconds is not None


def test_gate_survives_the_port_refusal_window() -> None:
    control = FakeControlClient(env={"OLLAMA_NUM_PARALLEL": "1"})
    session = FakeSession(
        _routes(
            ps=[FakeResponse(ps_body(None)), FakeResponse(ps_body(None)), FakeResponse(ps_body(MODEL))],
            tags=[REFUSED, REFUSED, FakeResponse({"models": []})],
        )
    )

    result = _preflight(control, session, gate_budget_s=5.0)

    assert result.readiness.state == READINESS_READY
    assert session.count("/api/tags") == 3


def test_gate_records_port_timeout_and_the_run_still_proceeds(caplog) -> None:
    control = FakeControlClient(env={"OLLAMA_NUM_PARALLEL": "1"})
    session = FakeSession(_routes(tags=REFUSED))

    with caplog.at_level(logging.WARNING):
        result = _preflight(control, session, gate_budget_s=0.0)

    assert result.readiness.state == READINESS_NOT_READY
    assert result.readiness.reason == REASON_PORT_TIMEOUT
    # Nothing to warm up against a port that never answered.
    assert session.count("/api/chat") == 0
    assert "not_ready(port_timeout)" in caplog.text


def test_gate_reports_a_silently_reverted_parallelism() -> None:
    """Port up, model resident, but ``/status`` disagrees with what was requested."""

    def revert_after_reconfigure(client, _model, _num_parallel):
        client.env["OLLAMA_NUM_PARALLEL"] = "1"

    control = FakeControlClient(env={"OLLAMA_NUM_PARALLEL": "1"}, on_reconfigure=revert_after_reconfigure)
    session = FakeSession(_routes(ps=FakeResponse(ps_body(MODEL))))

    result = _preflight(control, session)

    assert result.reconfigure.outcome == OUTCOME_MISMATCH
    assert result.readiness.reason == REASON_NUM_PARALLEL_MISMATCH


def test_gate_reports_an_unaffirmed_residency() -> None:
    """A gate proves; it never assumes the model got loaded."""
    control = FakeControlClient(env={"OLLAMA_NUM_PARALLEL": "4"})
    session = FakeSession(_routes(ps=FakeResponse(ps_body(None)), chat=FakeResponse({}, status_code=500)))

    result = _preflight(control, session)

    assert result.warm_up.error is not None
    assert result.readiness.reason == REASON_MODEL_NOT_RESIDENT


def test_gate_reports_an_unreachable_control_service() -> None:
    control = FakeControlClient(status_error=ControlServiceError("refused"))
    session = FakeSession(_routes(ps=FakeResponse(ps_body(MODEL))))

    result = _preflight(control, session)

    assert result.reconfigure.outcome == OUTCOME_FAILED
    assert result.readiness.reason == REASON_UNREACHABLE


def test_gate_does_not_report_a_mismatch_it_never_observed() -> None:
    """With no control endpoint the parallelism is unknown, not wrong."""
    session = FakeSession(_routes(ps=FakeResponse(ps_body(MODEL))))

    result = preflight(None, BASE_URL, MODEL, 4, session=session, gate_budget_s=1.0, gate_interval_s=0.0)

    assert result.readiness.state == READINESS_READY


def test_vram_spill_warns_and_proceeds(caplog) -> None:
    control = FakeControlClient(env={"OLLAMA_NUM_PARALLEL": "4"})
    session = FakeSession(_routes(ps=FakeResponse(ps_body(MODEL, size=10_000, size_vram=6_000))))

    with caplog.at_level(logging.WARNING):
        result = _preflight(control, session)

    assert result.readiness.state == READINESS_READY
    assert result.readiness.vram_fully_loaded is False
    assert "spilled to CPU" in caplog.text


# ---------------------------------------------------------------------------
# check_worker_drift -- /models validates, it never overrides
# ---------------------------------------------------------------------------


def test_drift_check_is_silent_when_config_and_server_agree() -> None:
    control = FakeControlClient(models={MODEL: 4})
    assert check_worker_drift(control, MODEL, 4) is None


def test_drift_check_names_both_values_and_leaves_config_authoritative() -> None:
    control = FakeControlClient(models={MODEL: 2})

    message = check_worker_drift(control, MODEL, 6)

    assert message is not None
    assert "6" in message and "2" in message
    assert "authoritative" in message
    # The configured value is reported unchanged; nothing is clamped.
    assert control.count("reconfigure") == 0


def test_drift_check_reports_a_model_unknown_to_the_server() -> None:
    """An alias absent from ``/models`` is reported, never raised, never blocking."""
    control = FakeControlClient(models={OTHER_MODEL: 4})

    message = check_worker_drift(control, MODEL, 4)

    assert message is not None and "unknown to the control service" in message


def test_drift_check_reports_rather_than_raises_when_models_cannot_be_read() -> None:
    control = FakeControlClient(models_error=ControlServiceError("unreachable"))

    assert "Could not validate" in check_worker_drift(control, MODEL, 4)


def test_drift_check_is_silent_without_a_control_service() -> None:
    assert check_worker_drift(None, MODEL, 4) is None


# ---------------------------------------------------------------------------
# Integration -- the GUI five-combo scenario, the plan's central claim
# ---------------------------------------------------------------------------


def test_five_sequential_calls_issue_exactly_one_reconfigure() -> None:
    """One Run press over five strategies must restart the container once, not five times.

    Without the skip check each redundant restart evicts the loaded model and kills
    any in-flight request from another user of that GPU -- and on the Windows host
    costs ~123 s of pre-flight apiece.
    """
    control = FakeControlClient(env={"OLLAMA_NUM_PARALLEL": "1"})

    outcomes = [ensure_num_parallel(control, MODEL, 4).outcome for _ in range(5)]

    assert outcomes == [OUTCOME_APPLIED] + [OUTCOME_ALREADY_CORRECT] * 4
    assert control.count("reconfigure") == 1


class _EvolvingHost:
    """A host whose residency changes the way a real one's does, not on a script.

    Residency is *caused*, not scheduled: ``POST /reconfigure`` recreates the container
    and takes the loaded model with it, and the warm-up ``/api/chat`` is what puts one
    back. Holding that state here -- rather than handing ``/api/ps`` a fixed list of
    answers -- is what lets a sequence of pre-flights be asserted on: each one sees the
    server the previous one left behind, and no assertion depends on how many
    ``/api/ps`` reads a stage happens to make.
    """

    def __init__(self, resident: str | None = None) -> None:
        self.resident = resident

    def ps(self) -> FakeResponse:
        return FakeResponse(ps_body(self.resident))

    def chat(self) -> FakeResponse:
        self.resident = MODEL
        return FakeResponse({"message": {"content": "ready"}})

    def reconfigured(self, client, _model: str, num_parallel: int) -> None:
        """The ``on_reconfigure`` hook: the value is applied and the model is evicted."""
        client.env["OLLAMA_NUM_PARALLEL"] = str(num_parallel)
        self.resident = None


def test_five_sequential_calls_issue_exactly_one_warm_up() -> None:
    """The same Run press must load the model once, not once per strategy.

    The warm-up is the expensive half of the pre-flight -- 83.4 s of cold load on the
    Windows host -- and it is deliberately *not* conditional on the reconfigure having
    been skipped, so "one reconfigure" does not imply "one warm-up". Combo 1 finds
    nothing resident because its own reconfigure evicted it and pays the load; combos
    2-5 find the model still resident and skip, which is the property that makes the
    per-combo pre-flight cheap enough to run unconditionally.
    """
    host = _EvolvingHost()
    control = FakeControlClient(env={"OLLAMA_NUM_PARALLEL": "1"}, on_reconfigure=host.reconfigured)
    session = FakeSession(_routes(ps=host.ps, chat=host.chat))

    results = [_preflight(control, session) for _ in range(5)]

    assert session.count("/api/chat") == 1
    assert control.count("reconfigure") == 1
    assert [r.warm_up.performed for r in results] == [True] + [False] * 4
    assert [r.reconfigure.outcome for r in results] == [OUTCOME_APPLIED] + [OUTCOME_ALREADY_CORRECT] * 4
    # Every combo still starts from a proven-ready server, including the four that
    # neither restarted nor warmed anything -- skipping is not the same as assuming.
    assert [r.readiness.state for r in results] == [READINESS_READY] * 5
