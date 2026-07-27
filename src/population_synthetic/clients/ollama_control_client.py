"""OllamaControlClient -- HTTP client for one host's Ollama control service.

The control service is a small FastAPI process living **next to** Ollama (port
``:11435`` beside Ollama's ``:11434``), not part of it. Ollama exposes no endpoint
for changing ``OLLAMA_NUM_PARALLEL``; the control service does it by recreating the
container. Its verified contract (``GET /openapi.json``, identical on both hosts)::

    POST /reconfigure  {model*, num_parallel?, context_length?}
                    -> {model, num_parallel, context_length, container_id, elapsed_seconds}
    GET  /status       -> {container_running: bool, container_id: str|null, env: {OLLAMA_*: str}}
    GET  /models       -> [{model: str, num_parallel: int}]
    GET  /health       -> {status: "ok"}

Scope (module contract): this module speaks HTTP to exactly the control endpoint it
is handed. It knows nothing about model axes, worker counts, config files or the
host registry -- the endpoint is resolved in the orchestration layer, like every
other piece of configuration, and the *decisions* taken with these responses belong
to :mod:`population_synthetic.generators.synthetic.ollama_concurrency`.

Failure policy: every transport failure and every malformed body raises
:class:`ControlServiceError` naming the exact endpoint probed, mirroring the error
idiom of :meth:`OllamaClient._validate_server`. Response bodies are validated at the
boundary rather than ``.get()``-ed through, because a 200 from this service is
unvalidated boundary data, not proof that a setting took. The one deliberate
exception is :func:`parse_num_parallel`, which returns an explicit ``None`` absent
marker: "the server does not declare a parallelism" is a legitimate state, whereas a
substituted default would silently misreport what the server is actually doing.
"""

from __future__ import annotations

from typing import Any, Mapping

import requests

# Timeouts are measured rather than guessed.
#
# ``/reconfigure`` recreates a Docker container: measured at 0.44 s on the Linux
# host and 9.83 s on the Windows host (2026-07-27), so 120 s is a wide margin. It
# is also the value all three POC sweep scripts use.
RECONFIGURE_TIMEOUT_S = 120
# ``/status``, ``/models`` and ``/health`` are trivial reads (~20 ms), so they take
# the same 10 s as ``OllamaClient._validate_server``'s ``/api/tags`` probe.
READ_TIMEOUT_S = 10

# The container environment variable the whole feature exists to align.
NUM_PARALLEL_ENV_KEY = "OLLAMA_NUM_PARALLEL"


class ControlServiceError(RuntimeError):
    """The control service could not be reached, or answered something unusable.

    Raised for transport failures (connection refused, timeout, non-2xx) and for
    well-transported but malformed bodies alike: from the caller's point of view
    both mean "no trustworthy answer", and both must be distinguishable from a
    *verified* wrong answer, which is not an error at all.
    """


def parse_num_parallel(env: Mapping[str, Any]) -> int | None:
    """Return ``int(env["OLLAMA_NUM_PARALLEL"])``, or ``None`` when unknowable.

    ``None`` is an explicit absent marker for two distinct-but-equivalent cases:
    the key is absent, or its value does not parse as an integer. Neither may be
    substituted with a default -- a run that records ``num_parallel=1`` because
    the key was missing is indistinguishable from one that really ran at 1, and
    the two have wall-clock figures differing by ~2x.
    """
    raw = env.get(NUM_PARALLEL_ENV_KEY)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


class OllamaControlClient:
    """Thin, fail-fast HTTP client over one control endpoint.

    *control_url* is required and has no default: the endpoint comes from the host
    registry (``config/synthetic/ollama_hosts.yaml``), and a client that could pick
    a machine on its own would restart the wrong GPU's container while the outputs
    looked perfectly normal.

    *session* exists as an injection seam for tests, so the unit suite can exercise
    body validation without a network or a real container restart.
    """

    def __init__(
        self,
        control_url: str,
        timeout: int = RECONFIGURE_TIMEOUT_S,
        *,
        session: Any | None = None,
    ) -> None:
        if not control_url or not str(control_url).strip():
            raise ValueError(
                f"OllamaControlClient requires an explicit control_url, got {control_url!r}. "
                f"Resolve it from the Ollama host registry (config/synthetic/ollama_hosts.yaml) "
                f"before constructing the client."
            )
        self.control_url = str(control_url).rstrip("/")
        self._timeout = timeout
        self._session = session if session is not None else requests.Session()

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _read(self, path: str, timeout: int) -> Any:
        """GET *path* and return the decoded body, or raise ControlServiceError."""
        endpoint = f"{self.control_url}{path}"
        try:
            resp = self._session.get(endpoint, timeout=timeout)
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as e:
            raise ControlServiceError(
                f"Ollama control service unreachable at {endpoint}. "
                f"Ensure the service is running on that host. Original error: {e}"
            ) from e
        except requests.exceptions.Timeout as e:
            raise ControlServiceError(
                f"Ollama control service timed out at {endpoint} after {timeout}s. Original error: {e}"
            ) from e
        except requests.exceptions.HTTPError as e:
            raise ControlServiceError(
                f"Ollama control service at {endpoint} returned HTTP {_status_code(e)}. Original error: {e}"
            ) from e
        return _decode_json(resp, endpoint)

    def _write(self, path: str, payload: dict[str, Any], timeout: int) -> Any:
        """POST *payload* to *path* and return the decoded body, or raise."""
        endpoint = f"{self.control_url}{path}"
        try:
            resp = self._session.post(endpoint, json=payload, timeout=timeout)
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as e:
            raise ControlServiceError(
                f"Ollama control service unreachable at {endpoint}. "
                f"Ensure the service is running on that host. Original error: {e}"
            ) from e
        except requests.exceptions.Timeout as e:
            raise ControlServiceError(
                f"Ollama control service timed out at {endpoint} after {timeout}s "
                f"(payload {payload!r}). Original error: {e}"
            ) from e
        except requests.exceptions.HTTPError as e:
            raise ControlServiceError(
                f"Ollama control service at {endpoint} returned HTTP {_status_code(e)} "
                f"for payload {payload!r}. Original error: {e}"
            ) from e
        return _decode_json(resp, endpoint)

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    def health(self) -> bool:
        """Return ``True`` when ``/health`` answers 2xx; ``False`` otherwise.

        The cheapest possible "is this service there at all" probe. It is a bool
        rather than a raise because reachability is the question being asked --
        an unreachable control service is a legitimate, recorded run state
        (``no_control_url``'s sibling, ``failed``), not an exceptional one.
        """
        try:
            self._read("/health", READ_TIMEOUT_S)
        except ControlServiceError:
            return False
        return True

    def status(self) -> dict[str, Any]:
        """Return the validated ``/status`` body.

        Guarantees for the caller: ``container_running`` is present and a bool, and
        ``env`` is a mapping. Anything else raises rather than being ``.get()``-ed
        through, because the two fields are exactly the evidence the skip decision
        rests on.
        """
        endpoint = f"{self.control_url}/status"
        body = self._read("/status", READ_TIMEOUT_S)
        if not isinstance(body, dict):
            raise ControlServiceError(
                f"Malformed /status body from {endpoint}: expected a JSON object, got {type(body).__name__}: {body!r}"
            )
        if not isinstance(body.get("container_running"), bool):
            raise ControlServiceError(
                f"Malformed /status body from {endpoint}: 'container_running' must be a bool, "
                f"got {body.get('container_running')!r}."
            )
        if not isinstance(body.get("env"), dict):
            raise ControlServiceError(
                f"Malformed /status body from {endpoint}: 'env' must be a mapping, got {body.get('env')!r}."
            )
        return body

    def models(self) -> dict[str, int]:
        """Return ``{model_name: recommended_num_parallel}`` from ``/models``.

        The recommendation **validates** the configured worker counts; it never
        overrides them. Config stays the single source of truth so the same commit
        yields the same concurrency on any day, server up or down.
        """
        endpoint = f"{self.control_url}/models"
        body = self._read("/models", READ_TIMEOUT_S)
        if not isinstance(body, list):
            raise ControlServiceError(
                f"Malformed /models body from {endpoint}: expected a JSON array, got {type(body).__name__}: {body!r}"
            )
        recommended: dict[str, int] = {}
        for entry in body:
            if not isinstance(entry, dict):
                raise ControlServiceError(
                    f"Malformed /models body from {endpoint}: every entry must be an object "
                    f"{{model, num_parallel}}, got {entry!r}."
                )
            name = entry.get("model")
            num_parallel = entry.get("num_parallel")
            if not isinstance(name, str) or not name:
                raise ControlServiceError(
                    f"Malformed /models entry from {endpoint}: 'model' must be a non-empty string, got {name!r}."
                )
            # ``bool`` is an ``int`` in Python, so an unguarded isinstance would
            # accept ``num_parallel: true`` as one slot.
            if not isinstance(num_parallel, int) or isinstance(num_parallel, bool):
                raise ControlServiceError(
                    f"Malformed /models entry from {endpoint}: 'num_parallel' for {name!r} must be an int, "
                    f"got {num_parallel!r}."
                )
            recommended[name] = num_parallel
        return recommended

    def current_num_parallel(self) -> int | None:
        """Return the server's live ``OLLAMA_NUM_PARALLEL``, or ``None`` if unknowable.

        Raises :class:`ControlServiceError` when ``/status`` itself cannot be read or
        is malformed -- "could not ask" and "asked, and the server declares nothing"
        are different facts and the caller classifies them differently.
        """
        return parse_num_parallel(self.status()["env"])

    def reconfigure(self, model: str, num_parallel: int) -> dict[str, Any]:
        """Recreate the Ollama container with ``OLLAMA_NUM_PARALLEL=num_parallel``.

        **This does not load a model.** Measured 2026-07-27: the call returns with a
        new ``container_id`` while ``/api/ps`` still reports ``{"models": []}``. The
        ``model`` field is what the service uses to derive/validate a recommended
        parallelism, not an instruction to load. Loading is the warm-up's job.

        The returned body is *not* evidence that the setting took: the caller must
        read it back from ``/status``.
        """
        if not isinstance(num_parallel, int) or isinstance(num_parallel, bool) or num_parallel < 1:
            raise ValueError(
                f"reconfigure() requires a positive int num_parallel, got {num_parallel!r} for model {model!r}."
            )
        if not model:
            raise ValueError(f"reconfigure() requires a model tag, got {model!r}.")

        endpoint = f"{self.control_url}/reconfigure"
        body = self._write("/reconfigure", {"model": model, "num_parallel": num_parallel}, self._timeout)
        if not isinstance(body, dict):
            raise ControlServiceError(
                f"Malformed /reconfigure body from {endpoint}: expected a JSON object, "
                f"got {type(body).__name__}: {body!r}"
            )
        return body

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        close = getattr(self._session, "close", None)
        if callable(close):
            close()


def _status_code(error: requests.exceptions.HTTPError) -> Any:
    """Return the HTTP status behind *error*, or ``"unknown"`` when absent."""
    return error.response.status_code if error.response is not None else "unknown"


def _decode_json(resp: Any, endpoint: str) -> Any:
    """Decode *resp* as JSON, raising ControlServiceError naming *endpoint*."""
    try:
        return resp.json()
    except ValueError as e:
        body = getattr(resp, "text", "")
        raise ControlServiceError(
            f"Ollama control service at {endpoint} returned a non-JSON body: {body[:200]!r}. Original error: {e}"
        ) from e
