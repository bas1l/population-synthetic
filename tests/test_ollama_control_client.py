"""Unit tests for the Ollama control-service transport client.

Covers :mod:`population_synthetic.clients.ollama_control_client`. Two properties are
under test:

1. **Every answer is validated at the boundary.** A 200 from this service is
   unvalidated boundary data, not proof that anything took. A body missing
   ``container_running``, an ``env`` that is not a mapping, a ``/models`` array whose
   entries are not ``{model, num_parallel}`` -- each raises, naming the endpoint,
   rather than being ``.get()``-ed through into a decision about restarting a
   container.
2. **Absent is not zero.** ``current_num_parallel()`` returns an explicit ``None``
   when the server declares no ``OLLAMA_NUM_PARALLEL``. A substituted default would
   make a run that recorded ``1`` because the key was missing indistinguishable from
   one that really ran at 1 -- and their wall-clock figures differ by ~2x.

No test touches the network: the session is injected.
"""

from __future__ import annotations

import pytest
import requests

from population_synthetic.clients.ollama_control_client import (
    READ_TIMEOUT_S,
    RECONFIGURE_TIMEOUT_S,
    ControlServiceError,
    OllamaControlClient,
    parse_num_parallel,
)

from ._ollama_fakes import CONTROL_URL, FakeResponse, FakeSession


def _client(routes: dict, **kwargs) -> OllamaControlClient:
    """Build a client whose transport is the injected fake."""
    return OllamaControlClient(CONTROL_URL, session=FakeSession(routes), **kwargs)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["", "   ", None])
def test_requires_an_explicit_control_url(value) -> None:
    """There is no default endpoint: the registry is the only source for it."""
    with pytest.raises(ValueError, match="control_url"):
        OllamaControlClient(value)  # type: ignore[arg-type]


def test_trailing_slash_is_normalized_away() -> None:
    """``http://h:11435/`` and ``http://h:11435`` address the same service."""
    client = OllamaControlClient(f"{CONTROL_URL}/", session=FakeSession({}))
    assert client.control_url == CONTROL_URL


def test_timeouts_are_the_measured_constants() -> None:
    """The two timeouts are measurement-derived, not guessed -- pin them."""
    # /reconfigure recreates a container: 0.44 s measured on Linux, 9.83 s on Windows.
    assert RECONFIGURE_TIMEOUT_S == 120
    # /status, /models, /health are ~20 ms reads; same budget as _validate_server.
    assert READ_TIMEOUT_S == 10


# ---------------------------------------------------------------------------
# /status -- validated at the boundary
# ---------------------------------------------------------------------------


def test_status_returns_the_validated_body() -> None:
    body = {"container_running": True, "container_id": "abc", "env": {"OLLAMA_NUM_PARALLEL": "4"}}
    assert _client({"/status": FakeResponse(body)}).status() == body


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(["not", "an", "object"], id="array-root"),
        pytest.param("running", id="scalar-root"),
        pytest.param({"env": {}}, id="no-container_running"),
        pytest.param({"container_running": "true", "env": {}}, id="container_running-not-bool"),
        pytest.param({"container_running": True}, id="no-env"),
        pytest.param({"container_running": True, "env": "OLLAMA_NUM_PARALLEL=4"}, id="env-not-mapping"),
        pytest.param({"container_running": True, "env": None}, id="env-null"),
    ],
)
def test_malformed_status_body_raises_naming_the_endpoint(body) -> None:
    """A malformed ``/status`` raises rather than yielding a partial answer.

    ``container_running`` and ``env`` are exactly the evidence the skip decision
    rests on; guessing at either would either restart a healthy container or leave a
    mis-tuned one alone.
    """
    with pytest.raises(ControlServiceError, match="/status") as excinfo:
        _client({"/status": FakeResponse(body)}).status()
    assert CONTROL_URL in str(excinfo.value)


# ---------------------------------------------------------------------------
# current_num_parallel -- explicit absent marker
# ---------------------------------------------------------------------------


def test_current_num_parallel_reads_the_declared_value() -> None:
    body = {"container_running": True, "env": {"OLLAMA_NUM_PARALLEL": "6"}}
    assert _client({"/status": FakeResponse(body)}).current_num_parallel() == 6


@pytest.mark.parametrize(
    "env",
    [
        pytest.param({}, id="absent"),
        pytest.param({"OLLAMA_MAX_LOADED_MODELS": "1"}, id="other-keys-only"),
        pytest.param({"OLLAMA_NUM_PARALLEL": ""}, id="empty"),
        pytest.param({"OLLAMA_NUM_PARALLEL": "many"}, id="unparseable"),
        pytest.param({"OLLAMA_NUM_PARALLEL": "4.5"}, id="not-an-int"),
        pytest.param({"OLLAMA_NUM_PARALLEL": None}, id="null"),
    ],
)
def test_current_num_parallel_is_none_when_unknowable(env) -> None:
    """Absent or unparseable yields ``None`` -- never ``0``, never a default."""
    body = {"container_running": True, "env": env}
    observed = _client({"/status": FakeResponse(body)}).current_num_parallel()
    assert observed is None


def test_parse_num_parallel_is_the_single_parsing_rule() -> None:
    """The pure parser is shared with the policy layer, so the rule lives once."""
    assert parse_num_parallel({"OLLAMA_NUM_PARALLEL": "12"}) == 12
    assert parse_num_parallel({"OLLAMA_NUM_PARALLEL": 12}) == 12
    assert parse_num_parallel({}) is None


def test_current_num_parallel_propagates_a_transport_failure() -> None:
    """"Could not ask" is not "asked, and it declares nothing" -- so this raises."""
    routes = {"/status": requests.exceptions.ConnectionError("refused")}
    with pytest.raises(ControlServiceError):
        _client(routes).current_num_parallel()


# ---------------------------------------------------------------------------
# /models -- validated at the boundary
# ---------------------------------------------------------------------------


def test_models_returns_a_name_to_recommendation_map() -> None:
    body = [{"model": "qwen3:14b", "num_parallel": 4}, {"model": "gemma2:9b", "num_parallel": 1}]
    assert _client({"/models": FakeResponse(body)}).models() == {"qwen3:14b": 4, "gemma2:9b": 1}


def test_models_accepts_an_empty_catalogue() -> None:
    """An empty list is well-formed: the service simply declares no models."""
    assert _client({"/models": FakeResponse([])}).models() == {}


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"models": []}, id="object-root"),
        pytest.param("qwen3:14b", id="scalar-root"),
        pytest.param(["qwen3:14b"], id="entries-not-objects"),
        pytest.param([{"num_parallel": 4}], id="entry-without-model"),
        pytest.param([{"model": "", "num_parallel": 4}], id="entry-with-empty-model"),
        pytest.param([{"model": "qwen3:14b"}], id="entry-without-num_parallel"),
        pytest.param([{"model": "qwen3:14b", "num_parallel": "4"}], id="num_parallel-as-string"),
        pytest.param([{"model": "qwen3:14b", "num_parallel": True}], id="num_parallel-as-bool"),
    ],
)
def test_malformed_models_body_raises_naming_the_endpoint(body) -> None:
    """``bool`` is rejected explicitly: ``True == 1`` would pass an unguarded check."""
    with pytest.raises(ControlServiceError, match="/models"):
        _client({"/models": FakeResponse(body)}).models()


# ---------------------------------------------------------------------------
# /reconfigure
# ---------------------------------------------------------------------------


def test_reconfigure_posts_the_documented_payload() -> None:
    session = FakeSession({"/reconfigure": FakeResponse({"model": "qwen3:14b", "num_parallel": 4})})
    client = OllamaControlClient(CONTROL_URL, session=session)

    client.reconfigure("qwen3:14b", 4)

    method, url, payload = session.calls[0]
    assert (method, url) == ("POST", f"{CONTROL_URL}/reconfigure")
    assert payload == {"model": "qwen3:14b", "num_parallel": 4}


@pytest.mark.parametrize(
    "num_parallel",
    [
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
        pytest.param("4", id="string"),
        pytest.param(True, id="bool"),
    ],
)
def test_reconfigure_rejects_a_non_positive_int(num_parallel) -> None:
    """Caller error fails before any container is touched."""
    with pytest.raises(ValueError, match="num_parallel"):
        _client({"/reconfigure": FakeResponse({})}).reconfigure("qwen3:14b", num_parallel)


def test_reconfigure_rejects_an_empty_model() -> None:
    with pytest.raises(ValueError, match="model"):
        _client({"/reconfigure": FakeResponse({})}).reconfigure("", 4)


def test_reconfigure_rejects_a_non_object_body() -> None:
    with pytest.raises(ControlServiceError, match="/reconfigure"):
        _client({"/reconfigure": FakeResponse(["ok"])}).reconfigure("qwen3:14b", 4)


# ---------------------------------------------------------------------------
# Transport error arms -- one per failure mode, never a bare except
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        pytest.param(requests.exceptions.ConnectionError("refused"), "unreachable", id="connection"),
        pytest.param(requests.exceptions.Timeout("slow"), "timed out", id="timeout"),
    ],
)
def test_transport_failures_map_to_control_service_error(error, expected) -> None:
    """Each arm re-raises naming the exact endpoint probed, as _validate_server does.

    With the host selectable per run, "which machine did this run actually talk to"
    must be answerable from the failure message alone.
    """
    with pytest.raises(ControlServiceError, match=expected) as excinfo:
        _client({"/status": error}).status()
    assert f"{CONTROL_URL}/status" in str(excinfo.value)


@pytest.mark.parametrize("status_code", [400, 404, 500, 503])
def test_non_2xx_maps_to_control_service_error_naming_the_code(status_code: int) -> None:
    with pytest.raises(ControlServiceError, match=str(status_code)) as excinfo:
        _client({"/status": FakeResponse({}, status_code=status_code)}).status()
    assert f"{CONTROL_URL}/status" in str(excinfo.value)


def test_non_json_body_maps_to_control_service_error() -> None:
    """An HTML error page from a reverse proxy is a malformed body, not a status."""
    routes = {"/status": FakeResponse(status_code=200, text="<html>502 Bad Gateway</html>")}
    with pytest.raises(ControlServiceError, match="non-JSON"):
        _client(routes).status()


def test_reconfigure_timeout_names_the_payload() -> None:
    """A restart that outruns its 120 s budget must say what it was trying to set."""
    routes = {"/reconfigure": requests.exceptions.Timeout("too slow")}
    with pytest.raises(ControlServiceError, match="num_parallel"):
        _client(routes).reconfigure("llama3.3:70b", 6)


# ---------------------------------------------------------------------------
# /health -- reachability is a question, not an exception
# ---------------------------------------------------------------------------


def test_health_is_true_when_the_service_answers() -> None:
    assert _client({"/health": FakeResponse({"status": "ok"})}).health() is True


@pytest.mark.parametrize(
    "responder",
    [
        pytest.param(requests.exceptions.ConnectionError("refused"), id="unreachable"),
        pytest.param(FakeResponse({}, status_code=500), id="server-error"),
        pytest.param(FakeResponse(status_code=200, text="not json"), id="malformed"),
    ],
)
def test_health_is_false_rather_than_raising(responder) -> None:
    """An absent control service is a recorded run state, not an exceptional one."""
    assert _client({"/health": responder}).health() is False
