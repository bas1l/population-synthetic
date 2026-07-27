"""ollama_concurrency.py -- server-side concurrency policy for an Ollama run.

Server-side batching is what makes concurrent workers worth anything: a batch of
*B* decode requests reads the model weights once and emits *B* tokens, measured at
1.6x-3.4x in ``docs/development/ollama-parallelism-poc/REPORT.md``. Both halves must
match -- the client's worker count comes from the axis file, the server's
``OLLAMA_NUM_PARALLEL`` from its container environment -- and this module is the
policy that brings the second into line with the first.

The pre-flight is **three ordered stages**, and :func:`preflight` runs them:

* **PROBE** (:func:`probe`) -- read-only, ~20 ms. What is the server doing now?
* **ACT** -- only what is actually needed: :func:`ensure_num_parallel` when the
  parallelism is wrong, :func:`warm_up` when the model is not resident.
* **GATE** (:func:`probe` again, plus :func:`wait_until_serving`) -- prove the
  server can serve *before* the first persona is generated.

**Ordering is not interchangeable.** ``POST /reconfigure`` recreates the container
and therefore evicts whatever model was loaded (measured: it returns in 0.44 s with
``/api/ps`` reporting ``{"models": []}``), so the warm-up must follow it, never
precede it. And ``/reconfigure`` returns when *Docker* has recreated the container,
not when Ollama is listening -- 14.68 s later on the Windows host -- so the port
poll sits between the reconfigure and the warm-up rather than after both.

**Failure is tolerated, never swallowed.** A run is correct at any parallelism, only
slower, so nothing here is fatal: every function returns an explicit outcome record
with an absent marker (``None``) where a fact could not be established, and the
orchestration layer records that verbatim in ``run_metadata.json``. The observed
value is always read back; the requested one is never recorded as if it had been
applied.

Scope (module contract): this module decides and carries out. It knows nothing about
argparse, Qt, output paths or YAML, and it never reads config -- ``base_url``,
``model`` and ``desired`` arrive resolved from the orchestration layer. Its only
downward dependency is the transport client
(:mod:`population_synthetic.clients.ollama_control_client`).

Deviation from the plan's task 2.4, recorded here deliberately: the reconfigure step
and the warm-up step are two sibling functions composed by :func:`preflight`, rather
than one function doing both. A warm-up that failed means ``persona_00000``'s
wall-clock still carries a cold load, and a later timing analysis must be able to see
that -- which requires the warm-up to have its own outcome record rather than being
folded into :class:`ReconfigureOutcome`. ``ensure_num_parallel`` consequently takes no
``base_url``: an unused parameter would be a lie about what the function touches.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import requests

from population_synthetic.clients.ollama_control_client import (
    READ_TIMEOUT_S,
    ControlServiceError,
    OllamaControlClient,
    parse_num_parallel,
)

logger = logging.getLogger(__name__)

# Measured constants (2026-07-27, both hosts) rather than guessed ones.
#
# A cold load must fit inside the warm-up: 2.8 s on ``linux_3060`` but 83.4 s on the
# Windows host's SMR disk, and longer still for a 70B model. A warm-up timeout is a
# warning, never fatal, so a generous budget costs nothing when it is not needed.
WARM_UP_TIMEOUT_S = 600
# Ollama bound its port 14.68 s after ``/reconfigure`` returned on the slower host;
# 60 s is ~4x that. Re-measure if a host is retuned.
GATE_BUDGET_S = 60
GATE_POLL_INTERVAL_S = 0.5
# Enough tokens to prove the model answers, few enough that decode time is noise
# next to the load it is there to trigger. Every POC script uses this shape.
WARM_UP_NUM_PREDICT = 4
WARM_UP_PROMPT = "Reply with the single word: ready."
# ``size_vram / size`` below this means the KV cache spilled to CPU, which collapses
# throughput 2-3x (the "cliff" the POC measured). Mirrors ``cliff_sweep.py``.
VRAM_FULLY_LOADED_FRACTION = 0.999

# The five reconfigure outcome states. ``mismatch`` ("verified wrong") and ``failed``
# ("could not verify") are distinct facts and are never collapsed: they mean
# different things for any later timing analysis.
OUTCOME_ALREADY_CORRECT = "already_correct"
OUTCOME_APPLIED = "applied"
OUTCOME_MISMATCH = "mismatch"
OUTCOME_FAILED = "failed"
OUTCOME_NO_CONTROL_URL = "no_control_url"

# Readiness states and the reasons a gate can refuse.
READINESS_READY = "ready"
READINESS_NOT_READY = "not_ready"
REASON_PORT_TIMEOUT = "port_timeout"
REASON_NUM_PARALLEL_MISMATCH = "num_parallel_mismatch"
REASON_MODEL_NOT_RESIDENT = "model_not_resident"
REASON_UNREACHABLE = "unreachable"


# ---------------------------------------------------------------------------
# Outcome records -- plain, frozen, serializable data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ServerState:
    """One read-only snapshot of a host, taken by :func:`probe`.

    Every field is ``None`` when the fact could not be established, never a
    substituted default: comparing a before-snapshot with an after-snapshot is what
    turns "did acting achieve what we wanted?" into a measurement rather than an
    assumption, and a defaulted field would silently answer "yes".
    """

    # Did the control service answer ``/status``? ``None`` when no control endpoint
    # is bound, which is a different statement from "it did not answer".
    reachable: bool | None
    container_running: bool | None
    num_parallel: int | None
    # What Ollama itself reports loaded, which ``/status`` does not expose. ``None``
    # when nothing is loaded *or* ``/api/ps`` could not be read -- both resolve the
    # same way downstream (warm up anyway), so they are not distinguished.
    resident_model: str | None
    vram_fully_loaded: bool | None


@dataclass(frozen=True)
class ReconfigureOutcome:
    """What the reconfigure step did, and what was observed afterwards."""

    outcome: str  # already_correct | applied | mismatch | failed | no_control_url
    requested: int | None
    observed: int | None  # from GET /status read-back; None when unverifiable
    elapsed_seconds: float | None
    control_url: str | None
    detail: str | None  # error text for failed/mismatch


@dataclass(frozen=True)
class WarmUpOutcome:
    """Whether the model was loaded in pre-flight, and what that cost.

    Recorded separately from :class:`ReconfigureOutcome` because a warm-up that
    failed means ``persona_00000`` still carries the cold load its wall-clock was
    supposed to be free of -- a fact a later timing analysis must be able to see.
    """

    # True when a ``/api/chat`` call was issued (even if it then failed); False when
    # the model was already resident and nothing needed loading.
    performed: bool
    model: str
    # Wall-clock of the warm-up call: the cold-load cost moved out of persona_00000.
    load_seconds: float | None
    error: str | None


@dataclass(frozen=True)
class ReadinessOutcome:
    """The gate's verdict: may the pipeline start, and if not, why not."""

    state: str  # ready | not_ready
    reason: str | None  # port_timeout | num_parallel_mismatch | model_not_resident | unreachable
    waited_seconds: float | None
    vram_fully_loaded: bool | None


@dataclass(frozen=True)
class PreflightOutcome:
    """The three pre-flight facts, each recorded in its own block.

    They are kept apart deliberately: "the parallelism was applied", "the model was
    loaded" and "the server was ready" are independent, and a run can succeed at one
    while failing another.
    """

    reconfigure: ReconfigureOutcome
    warm_up: WarmUpOutcome
    readiness: ReadinessOutcome


# ---------------------------------------------------------------------------
# Inference-side reads (:11434) -- Ollama's own state, not the control service's
# ---------------------------------------------------------------------------


def _http(session: Any | None) -> Any:
    """Return *session*, or a fresh ``requests.Session`` when none was injected."""
    return session if session is not None else requests.Session()


def _entry_name(entry: dict[str, Any]) -> str | None:
    """Return an ``/api/ps`` entry's model tag, tolerating either key Ollama uses."""
    for key in ("model", "name"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _find_entry(entries: list[dict[str, Any]], model: str) -> dict[str, Any] | None:
    """Return the ``/api/ps`` entry for *model*, or ``None`` when it is not loaded."""
    for entry in entries:
        if _entry_name(entry) == model:
            return entry
    return None


def _vram_fully_loaded(entry: dict[str, Any]) -> bool | None:
    """Return whether *entry* sits entirely in VRAM, or ``None`` when unknowable."""
    size = entry.get("size")
    size_vram = entry.get("size_vram")
    if not isinstance(size, (int, float)) or not isinstance(size_vram, (int, float)):
        return None
    if size <= 0:
        return None
    return (size_vram / size) >= VRAM_FULLY_LOADED_FRACTION


def _read_running_models(
    base_url: str,
    *,
    session: Any | None = None,
    timeout_s: int = READ_TIMEOUT_S,
) -> list[dict[str, Any]] | None:
    """Return the ``GET {base_url}/api/ps`` model list, or ``None`` when unknowable.

    ``None`` means "could not find out" -- unreachable, timed out, non-2xx, or a body
    that is not the documented ``{"models": [...]}``. It is never a guess, and the
    caller resolves the ambiguity toward warming up: one redundant warm-up is cheap,
    whereas skipping a needed one silently bills a cold load to ``persona_00000``.
    """
    endpoint = f"{base_url.rstrip('/')}/api/ps"
    try:
        resp = _http(session).get(endpoint, timeout=timeout_s)
        resp.raise_for_status()
        body = resp.json()
    except (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.HTTPError,
        ValueError,
    ) as e:
        logger.debug("Could not read %s: %s", endpoint, e)
        return None

    if not isinstance(body, dict):
        logger.debug("Malformed body from %s: expected an object, got %r", endpoint, body)
        return None
    models = body.get("models")
    if not isinstance(models, list) or any(not isinstance(entry, dict) for entry in models):
        logger.debug("Malformed 'models' from %s: %r", endpoint, models)
        return None
    return models


def resident_model(
    base_url: str,
    *,
    session: Any | None = None,
    timeout_s: int = READ_TIMEOUT_S,
) -> str | None:
    """Return the model Ollama currently has loaded at *base_url*, or ``None``.

    Reads the **inference** port (``:11434``), not the control port: the loaded model
    is Ollama's own state and ``/status`` does not expose it. ``None`` means either
    "nothing is loaded" or "the answer was unreadable" -- never a guess.

    With ``OLLAMA_MAX_LOADED_MODELS=1`` there is at most one entry; when there are
    several, the first is reported.
    """
    entries = _read_running_models(base_url, session=session, timeout_s=timeout_s)
    if not entries:
        return None
    return _entry_name(entries[0])


def wait_until_serving(
    base_url: str,
    budget_s: float = GATE_BUDGET_S,
    interval_s: float = GATE_POLL_INTERVAL_S,
    *,
    session: Any | None = None,
) -> float | None:
    """Poll ``GET {base_url}/api/tags`` until 200; return seconds waited, else ``None``.

    Required because ``POST /reconfigure`` returns when Docker has recreated the
    container, not when Ollama is accepting connections; between those two moments
    the endpoint refuses connections. Without this, that gap surfaces as a connection
    error inside the first persona instead of as a named pre-flight failure.

    ``None`` means the budget elapsed without a 200. That is recorded, warned about,
    and not fatal -- the per-persona client does its own ``/api/tags`` validation and
    will raise with its own clear message if the server really never comes back.
    """
    endpoint = f"{base_url.rstrip('/')}/api/tags"
    http = _http(session)
    started = time.perf_counter()
    deadline = started + budget_s
    while True:
        try:
            resp = http.get(endpoint, timeout=READ_TIMEOUT_S)
            resp.raise_for_status()
            return time.perf_counter() - started
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.HTTPError,
        ) as e:
            last_error = e
        if time.perf_counter() >= deadline:
            logger.debug("%s never answered 200 within %.1fs: %s", endpoint, budget_s, last_error)
            return None
        time.sleep(interval_s)


# ---------------------------------------------------------------------------
# STAGE 1 / STAGE 3 -- the single read-only probe, called twice
# ---------------------------------------------------------------------------


def probe(
    control_client: OllamaControlClient | None,
    base_url: str,
    model: str,
    *,
    session: Any | None = None,
) -> ServerState:
    """Return a :class:`ServerState` snapshot of *base_url* and its control service.

    Read-only and cheap (~20 ms). The same function serves STAGE 1 and STAGE 3:
    calling it before and after acting is what makes "did acting achieve what we
    wanted?" a comparison rather than an assumption.
    """
    reachable: bool | None = None
    container_running: bool | None = None
    num_parallel: int | None = None

    if control_client is not None:
        try:
            status = control_client.status()
        except ControlServiceError as e:
            logger.debug("Control service probe failed at %s: %s", control_client.control_url, e)
            reachable = False
        else:
            reachable = True
            container_running = status["container_running"]
            num_parallel = parse_num_parallel(status["env"])

    entries = _read_running_models(base_url, session=session)
    resident: str | None = None
    vram_fully_loaded: bool | None = None
    if entries:
        entry = _find_entry(entries, model)
        if entry is not None:
            resident = model
            vram_fully_loaded = _vram_fully_loaded(entry)
        else:
            # Something else is loaded. Report it: with MAX_LOADED_MODELS=1 that is
            # exactly what the warm-up is about to evict.
            resident = _entry_name(entries[0])

    return ServerState(
        reachable=reachable,
        container_running=container_running,
        num_parallel=num_parallel,
        resident_model=resident,
        vram_fully_loaded=vram_fully_loaded,
    )


# ---------------------------------------------------------------------------
# STAGE 2a -- bring OLLAMA_NUM_PARALLEL in line with the run
# ---------------------------------------------------------------------------


def ensure_num_parallel(
    control_client: OllamaControlClient | None,
    model: str,
    desired: int,
) -> ReconfigureOutcome:
    """Make the server's ``OLLAMA_NUM_PARALLEL`` equal *desired*, and report what happened.

    The skip check is **required, not an optimisation**: a restart is idempotent in
    end state but not in side effects -- each redundant one evicts the loaded model
    and kills any in-flight request from another user of that GPU. A GUI Run over
    five strategies would otherwise restart the container five times.

    "Already correct" is the conjunction of *both* ``/status`` conditions -- the
    container is running **and** the value matches. A running container alone is a
    partial marker and must not satisfy a complete check.

    The resident model is deliberately not part of the condition: reconfiguring does
    not load a model, so a resident-model mismatch triggering a reconfigure would
    restart the container and still leave the model unloaded -- pure cost, no effect.
    Loading is :func:`warm_up`'s job.
    """
    if control_client is None:
        return ReconfigureOutcome(
            outcome=OUTCOME_NO_CONTROL_URL,
            requested=desired,
            observed=None,
            elapsed_seconds=None,
            control_url=None,
            detail=(
                "No control endpoint is bound for this run, so server-side parallelism was left as-is. "
                "Declare 'control_url' for the host in config/synthetic/ollama_hosts.yaml to enable it."
            ),
        )

    control_url = control_client.control_url

    try:
        status = control_client.status()
    except ControlServiceError as e:
        return ReconfigureOutcome(
            outcome=OUTCOME_FAILED,
            requested=desired,
            observed=None,
            elapsed_seconds=None,
            control_url=control_url,
            detail=str(e),
        )

    observed_before = parse_num_parallel(status["env"])
    if status["container_running"] and observed_before == desired:
        return ReconfigureOutcome(
            outcome=OUTCOME_ALREADY_CORRECT,
            requested=desired,
            observed=observed_before,
            elapsed_seconds=None,
            control_url=control_url,
            detail=None,
        )

    started = time.perf_counter()
    try:
        control_client.reconfigure(model, desired)
    except ControlServiceError as e:
        return ReconfigureOutcome(
            outcome=OUTCOME_FAILED,
            requested=desired,
            observed=None,
            elapsed_seconds=time.perf_counter() - started,
            control_url=control_url,
            detail=str(e),
        )
    elapsed = time.perf_counter() - started

    # A 200 is unvalidated boundary data, not proof the setting took. The observed
    # value is what a later analysis will trust, so it comes from a fresh read.
    try:
        observed = control_client.current_num_parallel()
    except ControlServiceError as e:
        return ReconfigureOutcome(
            outcome=OUTCOME_FAILED,
            requested=desired,
            observed=None,
            elapsed_seconds=elapsed,
            control_url=control_url,
            detail=f"Reconfigure to {desired} returned 200 but the /status read-back failed: {e}",
        )

    if observed == desired:
        return ReconfigureOutcome(
            outcome=OUTCOME_APPLIED,
            requested=desired,
            observed=observed,
            elapsed_seconds=elapsed,
            control_url=control_url,
            detail=None,
        )
    if observed is None:
        # Read-back succeeded but declares nothing: "could not verify", not
        # "verified wrong". The distinction is the whole point of five states.
        return ReconfigureOutcome(
            outcome=OUTCOME_FAILED,
            requested=desired,
            observed=None,
            elapsed_seconds=elapsed,
            control_url=control_url,
            detail=(
                f"Reconfigure to {desired} returned 200 but /status declares no "
                f"OLLAMA_NUM_PARALLEL, so the effective value could not be verified."
            ),
        )
    return ReconfigureOutcome(
        outcome=OUTCOME_MISMATCH,
        requested=desired,
        observed=observed,
        elapsed_seconds=elapsed,
        control_url=control_url,
        detail=f"Reconfigure requested OLLAMA_NUM_PARALLEL={desired} but /status reports {observed}.",
    )


# ---------------------------------------------------------------------------
# STAGE 2b -- load the model, so persona_00000 does not pay for it
# ---------------------------------------------------------------------------


def warm_up(
    base_url: str,
    model: str,
    *,
    session: Any | None = None,
    timeout_s: int = WARM_UP_TIMEOUT_S,
) -> WarmUpOutcome:
    """Load *model* with one discarded ``/api/chat``, unless it is already resident.

    This -- not the reconfigure -- is what loads a model. Without it, the cold load
    is billed to ``persona_00000``: measured 2.8 s on the Linux host but 83.4 s on
    the Windows host, a 4x outlier in exactly the per-persona wall-clock
    ``generation_metadata`` measures. Moving it into pre-flight attributes it
    honestly.

    Never fatal: a failed or timed-out warm-up is recorded and warned about, and the
    run proceeds paying the load inside the first persona instead.
    """
    entries = _read_running_models(base_url, session=session)
    if entries is not None and _find_entry(entries, model) is not None:
        return WarmUpOutcome(performed=False, model=model, load_seconds=None, error=None)

    endpoint = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": WARM_UP_PROMPT}],
        "stream": False,
        "options": {"num_predict": WARM_UP_NUM_PREDICT},
    }
    started = time.perf_counter()
    try:
        resp = _http(session).post(endpoint, json=payload, timeout=timeout_s)
        resp.raise_for_status()
    except (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.HTTPError,
    ) as e:
        elapsed = time.perf_counter() - started
        message = f"Warm-up of {model!r} at {endpoint} failed after {elapsed:.1f}s: {e}"
        logger.warning("%s -- the cold load will be billed to the first persona instead.", message)
        return WarmUpOutcome(performed=True, model=model, load_seconds=elapsed, error=message)

    # The reply itself is discarded; only the load it triggered mattered.
    return WarmUpOutcome(
        performed=True,
        model=model,
        load_seconds=time.perf_counter() - started,
        error=None,
    )


# ---------------------------------------------------------------------------
# Drift check -- /models validates the config, it never overrides it
# ---------------------------------------------------------------------------


def check_worker_drift(
    control_client: OllamaControlClient | None,
    model: str,
    configured: int,
) -> str | None:
    """Return a warning when ``/models`` disagrees with *configured*, else ``None``.

    The configured value is never overridden and never clamped: config is the single
    source of truth, so that the same commit yields the same concurrency on any day,
    server up or down. ``/models`` exists here purely to catch a hand-transcribed
    worker count that has gone stale.
    """
    if control_client is None:
        return None

    try:
        recommended = control_client.models()
    except ControlServiceError as e:
        return f"Could not validate the worker count for {model!r} against {control_client.control_url}/models: {e}"

    if model not in recommended:
        return (
            f"Model {model!r} is unknown to the control service at {control_client.control_url}/models "
            f"(it declares {sorted(recommended)}), so the configured worker count {configured} could not "
            f"be validated. Proceeding with the configured value."
        )
    if recommended[model] != configured:
        return (
            f"Worker-count drift for {model!r}: config declares {configured}, "
            f"{control_client.control_url}/models recommends {recommended[model]}. "
            f"Config is authoritative, so {configured} is used unchanged."
        )
    return None


# ---------------------------------------------------------------------------
# The composed pre-flight: PROBE -> ACT -> GATE
# ---------------------------------------------------------------------------


def preflight(
    control_client: OllamaControlClient | None,
    base_url: str,
    model: str,
    desired: int,
    *,
    session: Any | None = None,
    gate_budget_s: float = GATE_BUDGET_S,
    gate_interval_s: float = GATE_POLL_INTERVAL_S,
    warm_up_timeout_s: int = WARM_UP_TIMEOUT_S,
) -> PreflightOutcome:
    """Bring the host into the state this run needs, then prove it, before generating.

    The gate is a precondition of the pipeline, not a log line -- but ``not_ready``
    does not abort the run. The run is functionally correct at any parallelism and
    the per-persona client validates the server itself; the gate's value is that a
    failure is *named in pre-flight and recorded in provenance* rather than surfacing
    as an opaque error mid-run.

    The port poll sits between the reconfigure and the warm-up, one step earlier than
    a literal reading of the three stages would put it, because a warm-up fired at a
    container Docker has recreated but Ollama has not yet bound to would simply fail.
    """
    before = probe(control_client, base_url, model, session=session)
    logger.debug("Pre-flight probe of %s: %s", base_url, before)

    reconfigure_outcome = ensure_num_parallel(control_client, model, desired)

    # Only a real restart can have taken the port away.
    restarted = reconfigure_outcome.outcome in (OUTCOME_APPLIED, OUTCOME_MISMATCH)
    waited_seconds = wait_until_serving(
        base_url,
        budget_s=gate_budget_s if restarted else 0.0,
        interval_s=gate_interval_s,
        session=session,
    )

    if waited_seconds is None:
        warm_up_outcome = WarmUpOutcome(
            performed=False,
            model=model,
            load_seconds=None,
            error=(
                f"Skipped: {base_url} did not answer /api/tags within {gate_budget_s:.0f}s, "
                f"so there was nothing to warm up."
            ),
        )
    else:
        warm_up_outcome = warm_up(base_url, model, session=session, timeout_s=warm_up_timeout_s)

    after = probe(control_client, base_url, model, session=session)
    readiness = _classify_readiness(after, desired, model, waited_seconds)

    _log_preflight(reconfigure_outcome, warm_up_outcome, readiness, model, desired, base_url)
    return PreflightOutcome(
        reconfigure=reconfigure_outcome,
        warm_up=warm_up_outcome,
        readiness=readiness,
    )


def _classify_readiness(
    state: ServerState,
    desired: int,
    model: str,
    waited_seconds: float | None,
) -> ReadinessOutcome:
    """Turn the post-act snapshot into a single ready/not_ready verdict.

    Three separate facts must each hold, and none follows from the others: the port
    accepts connections, the parallelism actually took, and the model is resident.

    The two content checks are deliberately asymmetric, because the reason codes mean
    different things. ``num_parallel_mismatch`` names a *verified* disagreement, so an
    unknown parallelism (no control endpoint bound) cannot produce it -- a run against
    a host with no control service is ``no_control_url``, not a mismatch it never
    observed. ``model_not_resident`` names an *unaffirmed* residency, so an unreadable
    ``/api/ps`` does produce it: a gate proves, it does not assume, and the verdict is
    recorded rather than fatal.
    """
    reason: str | None = None
    if waited_seconds is None:
        reason = REASON_PORT_TIMEOUT
    elif state.reachable is False:
        reason = REASON_UNREACHABLE
    elif state.num_parallel is not None and state.num_parallel != desired:
        reason = REASON_NUM_PARALLEL_MISMATCH
    elif state.resident_model != model:
        reason = REASON_MODEL_NOT_RESIDENT

    return ReadinessOutcome(
        state=READINESS_READY if reason is None else READINESS_NOT_READY,
        reason=reason,
        waited_seconds=waited_seconds,
        vram_fully_loaded=state.vram_fully_loaded,
    )


def _log_preflight(
    reconfigure_outcome: ReconfigureOutcome,
    warm_up_outcome: WarmUpOutcome,
    readiness: ReadinessOutcome,
    model: str,
    desired: int,
    base_url: str,
) -> None:
    """Emit one line per pre-flight fact, at the level that fact deserves."""
    if reconfigure_outcome.outcome in (OUTCOME_ALREADY_CORRECT, OUTCOME_APPLIED):
        logger.info(
            "Ollama pre-flight: OLLAMA_NUM_PARALLEL=%s (%s) for %s on %s%s",
            reconfigure_outcome.observed,
            reconfigure_outcome.outcome,
            model,
            base_url,
            "" if reconfigure_outcome.elapsed_seconds is None else f" in {reconfigure_outcome.elapsed_seconds:.2f}s",
        )
    else:
        logger.warning(
            "Ollama pre-flight: could not set OLLAMA_NUM_PARALLEL=%d (%s): %s",
            desired,
            reconfigure_outcome.outcome,
            reconfigure_outcome.detail,
        )

    if warm_up_outcome.performed and warm_up_outcome.error is None:
        logger.info(
            "Ollama pre-flight: warmed up %s in %.1fs (cold load attributed here, not to persona_00000).",
            model,
            warm_up_outcome.load_seconds or 0.0,
        )

    if readiness.state == READINESS_NOT_READY:
        logger.warning(
            "Ollama pre-flight gate: not_ready(%s) for %s on %s -- proceeding anyway, "
            "the run is correct but its timings may not be comparable.",
            readiness.reason,
            model,
            base_url,
        )
    if readiness.vram_fully_loaded is False:
        logger.warning(
            "Ollama pre-flight: %s is not fully resident in VRAM on %s -- the KV cache has spilled to CPU, "
            "which collapses throughput 2-3x. OLLAMA_NUM_PARALLEL=%d is the likely cause.",
            model,
            base_url,
            desired,
        )
