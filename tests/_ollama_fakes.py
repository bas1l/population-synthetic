"""Injected fakes for the Ollama control-service and inference-port tests.

Shared by ``test_ollama_control_client.py`` and ``test_ollama_concurrency.py``.

Everything the control feature does is a side effect on a shared GPU server: it
restarts a container, evicts a loaded model and kills any in-flight request from
another user. **No test may therefore touch the network or perform a real restart**
-- the pyramid stays upright and the suite stays runnable with the servers off.
These fakes are *injected* (via the ``session=`` seam on the client and the policy
functions), not monkeypatched, so the production call path is exercised unchanged.

Both fakes can share one ``ledger`` list, which is what makes call **order**
assertable across the two ports: "the warm-up followed the reconfigure" is a claim
about the interleaving of a control-service call and an inference call.
"""

from __future__ import annotations

from typing import Any

import requests

from population_synthetic.clients.ollama_control_client import parse_num_parallel

_UNSET = object()

CONTROL_URL = "http://host.invalid:11435"
BASE_URL = "http://host.invalid:11434"


class FakeResponse:
    """Minimal stand-in for ``requests.Response``.

    ``payload`` left unset makes :meth:`json` raise ``ValueError``, which is how a
    non-JSON body reaches the client's decode arm.
    """

    def __init__(self, payload: Any = _UNSET, status_code: int = 200, text: str = "") -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self) -> Any:
        if self._payload is _UNSET:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._payload


class FakeSession:
    """Replays scripted responses per endpoint path and records every call.

    *routes* maps a URL suffix (``"/api/ps"``) to a responder or a list of responders
    consumed in order (the last one repeats). A responder is a :class:`FakeResponse`,
    an ``Exception`` instance to raise -- which is how the connection-refused window
    between "Docker recreated the container" and "Ollama bound its port" is reproduced
    without a real restart -- or a zero-argument callable returning either of those.

    The callable form exists because a scripted list can only express *when* a state
    changes, never *what* changed it. Residency is causal: a reconfigure evicts the
    model and a warm-up loads it, so across several sequential pre-flights the answer
    to ``/api/ps`` depends on calls made to other endpoints in between. A callable
    responder can read that state at call time; a fixed list would instead bake in the
    number of ``/api/ps`` reads each stage happens to make today.
    """

    def __init__(self, routes: dict[str, Any], ledger: list[str] | None = None) -> None:
        self._routes = {path: (r if isinstance(r, list) else [r]) for path, r in routes.items()}
        self.calls: list[tuple[str, str, Any]] = []
        self.ledger = ledger if ledger is not None else []

    def count(self, path: str) -> int:
        """How many calls were made to the endpoint whose URL ends with *path*."""
        return sum(1 for _, url, _ in self.calls if url.endswith(path))

    def get(self, url: str, timeout: Any = None) -> FakeResponse:
        return self._respond("GET", url, None)

    def post(self, url: str, json: Any = None, timeout: Any = None) -> FakeResponse:
        return self._respond("POST", url, json)

    def close(self) -> None:  # pragma: no cover - lifecycle parity only
        pass

    def _respond(self, method: str, url: str, payload: Any) -> FakeResponse:
        self.calls.append((method, url, payload))
        for path, responders in self._routes.items():
            if url.endswith(path):
                self.ledger.append(path)
                responder = responders.pop(0) if len(responders) > 1 else responders[0]
                if callable(responder):  # Exception and FakeResponse instances are not.
                    responder = responder()
                if isinstance(responder, Exception):
                    raise responder
                return responder
        raise AssertionError(f"FakeSession received an unrouted {method} {url}")


class FakeControlClient:
    """Duck-typed stand-in for :class:`OllamaControlClient`, recording every call.

    The default ``on_reconfigure`` writes the requested value into ``env``, which is
    what a healthy service does. Overriding it reproduces the states that matter and
    cannot be provoked on demand against a real server: a service that returns 200
    without applying (``mismatch``), one whose ``/status`` stops answering after the
    restart, and one that declares no ``OLLAMA_NUM_PARALLEL`` at all.
    """

    def __init__(
        self,
        control_url: str = CONTROL_URL,
        *,
        env: dict[str, str] | None = None,
        container_running: bool = True,
        models: dict[str, int] | None = None,
        status_error: Exception | None = None,
        models_error: Exception | None = None,
        reconfigure_error: Exception | None = None,
        on_reconfigure: Any = None,
        ledger: list[str] | None = None,
    ) -> None:
        self.control_url = control_url
        self.env = dict(env) if env is not None else {"OLLAMA_NUM_PARALLEL": "1"}
        self.container_running = container_running
        self._models = dict(models) if models is not None else {}
        self.status_error = status_error
        self.models_error = models_error
        self.reconfigure_error = reconfigure_error
        self._on_reconfigure = on_reconfigure
        self.calls: list[str] = []
        self.ledger = ledger if ledger is not None else []

    def count(self, name: str) -> int:
        """How many times endpoint *name* (``"reconfigure"``, ``"status"``) was called."""
        return self.calls.count(name)

    def status(self) -> dict[str, Any]:
        self._record("status")
        if self.status_error is not None:
            raise self.status_error
        return {
            "container_running": self.container_running,
            "container_id": "deadbeef",
            "env": dict(self.env),
        }

    def current_num_parallel(self) -> int | None:
        return parse_num_parallel(self.status()["env"])

    def models(self) -> dict[str, int]:
        self._record("models")
        if self.models_error is not None:
            raise self.models_error
        return dict(self._models)

    def reconfigure(self, model: str, num_parallel: int) -> dict[str, Any]:
        self._record("reconfigure")
        if self.reconfigure_error is not None:
            raise self.reconfigure_error
        if self._on_reconfigure is not None:
            self._on_reconfigure(self, model, num_parallel)
        else:
            self.env["OLLAMA_NUM_PARALLEL"] = str(num_parallel)
        return {
            "model": model,
            "num_parallel": num_parallel,
            "context_length": 8192,
            "container_id": "cafebabe",
            "elapsed_seconds": 0.44,
        }

    def _record(self, name: str) -> None:
        self.calls.append(name)
        self.ledger.append(name)


def ps_body(model: str | None, *, size: int = 8_000_000_000, size_vram: int | None = None) -> dict[str, Any]:
    """Build an ``/api/ps`` body with *model* loaded, or nothing loaded when ``None``."""
    if model is None:
        return {"models": []}
    return {
        "models": [
            {
                "name": model,
                "model": model,
                "size": size,
                "size_vram": size if size_vram is None else size_vram,
            }
        ]
    }
