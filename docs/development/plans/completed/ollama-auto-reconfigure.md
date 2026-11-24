# Plan: Ollama Auto-Reconfigure

**Date:** 2026-07-27
**Author:** Basil
**Status:** Completed
**Completed:** 2026-07-28 10:51
**Base Branch:** `dev`
**Branch:** `feature/ollama-auto-reconfigure`

---

## Overview

A generation run already knows which model it will use and how many workers it wants, but the
Ollama server's `OLLAMA_NUM_PARALLEL` is set by hand and the two drift apart silently. This adds
an orchestration-layer pre-flight step that calls each host's control API (`:11435`) to set the
server's parallelism to match the run, skipping the call when it is already correct, and records
the **observed** result rather than the requested one.

## Problem Statement

Server-side batching is what makes concurrent workers worth anything. Decoding is
memory-bandwidth-bound: a batch of *B* requests reads the model weights once and emits *B*
tokens, so batching is close to free and measured at **1.6x-3.4x** in
`docs/development/ollama-parallelism-poc/REPORT.md`. Without it, N client threads simply queue.

Both halves must match. Today only the client half is configured. `parameters.parallel.workers`
in each `ollama_*` axis file gives the client its count; the server's `OLLAMA_NUM_PARALLEL` is a
container environment variable a human sets. Right now **both hosts sit at `NUM_PARALLEL=1`**,
so every run with more than one worker queues rather than batches — the exact condition the
`selectable-ollama-host` branch added a warning for.

Three consequences:

1. **The warning is the only mechanism.** It tells you the run is mis-tuned and then proceeds
   anyway. Nothing acts on it.
2. **`server_num_parallel` in the registry is a hand-asserted claim.** It was already wrong once:
   `linux_3060` shipped as `4` with no source, silently suppressing the warning for three models,
   and was corrected only after a live `/status` read (`4fc7e38`).
3. **Run telemetry cannot be trusted across runs.** `run_metadata.json` records the *requested*
   worker count. A run that queued at `NUM_PARALLEL=1` and one that batched at 6 are
   indistinguishable afterwards, yet their wall-clock and latency figures differ by ~2x.

The capability to fix this has existed since 2026-07-02 and was never wired in. A bespoke control
service on `:11435` exposes `POST /reconfigure {model, num_parallel}`, which restarts the
container with the new setting. Only the four benchmark scripts under
`docs/development/ollama-parallelism-poc/` have ever called it; `git grep` over `src/` and
`scripts/` returns nothing. It ran on the Linux server only — **as of 2026-07-27 it is deployed
on the Windows host too**, so the feature is symmetric and worth building.

## Goals

### In Scope

1. An optional `control_url` per host in `config/synthetic/ollama_hosts.yaml`.
2. A minimal, fail-fast control-API client covering `/health`, `/status`, `/models`,
   `/reconfigure`.
3. A pre-flight step in `generate_identities_parallel.py` that brings the server's
   `NUM_PARALLEL` in line with the run's resolved worker count.
4. **Skip the restart when `/status` already reports the right value** — required, not an
   optimisation (see Definitions).
5. Read-back verification: the effective value is confirmed from `/status`, never assumed from
   an HTTP 200.
6. Provenance: the **observed** `num_parallel`, the outcome state, and `elapsed_seconds`
   recorded in `run_metadata.json`.
7. A drift check: compare the axis file's worker map against `GET /models` and warn on
   disagreement. Config stays authoritative.
8. GUI: a checkbox on the *LLM Synthetic Population* flow, default on, so pressing **Run**
   reconfigures.

### Out of Scope

- **Making `/models` authoritative for worker counts.** Config remains the source of truth;
  `/models` only validates. Decided explicitly — see Alternatives.
- Changing any worker value in the axis files. (Separately: `gemma4_e4b: 84` is a VRAM-fit
  ceiling, not a measured throughput knee, and deserves its own sweep. Not this plan.)
- `context_length`. `/reconfigure` accepts it; we always leave it at the server's 8192.
- Hoisting a single reconfigure above the GUI's per-combo subprocess loop. The skip check makes
  the repeated calls cheap; restructuring `execution.py` is not justified.
- Any coordination, locking, or "is someone else using this GPU" check.
- Deploying, versioning, or managing the `:11435` service itself.
- `generate_identity.py`. It generates one persona at concurrency 1 and has no
  `--ollama-auto-workers` and no warning block; there is nothing to reconfigure for.

## Success Criteria

- [x] A GUI Run over 5 strategies x 1 model issues **exactly one** `/reconfigure`; combos 2-5
      log `already_correct` and do not restart the container. *(Asserted against a recording fake
      in `test_five_sequential_calls_issue_exactly_one_reconfigure`; not yet observed live.)*
- [x] The same Run issues **exactly one** warm-up: combo 1 loads the model (because
      `/reconfigure` leaves nothing resident), combos 2-5 find it already resident and skip.
      *(Asserted across five sequential `preflight` calls against a stateful recording fake — the
      reconfigure evicts, the warm-up loads — in `test_five_sequential_calls_issue_exactly_one_warm_up`;
      not yet observed live.)*
- [ ] `persona_00000` of combo 1 shows no cold-load outlier — its wall-clock is comparable to
      `persona_00001`, with the load time attributed to the pre-flight instead.
- [x] **No persona is generated until the readiness gate reports `ready` or records
      `not_ready(<reason>)`.** The gate is a precondition of the pipeline, not a log line.
      *(By inspection: `_ollama_preflight` runs before the filter chain and before any
      `OllamaClient` is constructed, and always records a readiness block.)*
- [x] The atomistic host check has been run **on both hosts** and their results recorded in the
      plan, including the `/api/tags`-after-reconfigure latency that sizes the gate's budget.
      *(See Baseline measurements, 2026-07-27.)*
- [ ] After a run against `windows_4070tis` with `deepseek-r1:14b` and 6 workers,
      `GET :11435/status` reports `OLLAMA_NUM_PARALLEL=6`.
- [x] `run_metadata.json` records `ollama_reconfigure: {outcome, requested, observed,
      elapsed_seconds, control_url}` where `observed` comes from a `/status` read-back, never
      from the `/reconfigure` response body alone.
- [x] With the control service stopped, a run still completes; the outcome is `failed`, a warning
      names the endpoint, and `observed` is `null` — not silently the requested value.
- [x] A host with no `control_url` (or `--base-url` given, so no host is bound) behaves exactly
      as today: warn and proceed, outcome `no_control_url`.
- [ ] The drift check warns when an axis worker value disagrees with `/models`, and is silent
      today — all 13 (model, host) pairs currently agree. *(Warning behaviour is unit-tested;
      "silent today" needs a live `/models` read on both hosts.)*
- [x] No test performs a real restart; the control client is exercised through an injected fake.
- [x] `ruff check src/` clean, `pytest` green. *(921 passed, 2026-07-27.)*

## Definitions

- **control API:** the bespoke FastAPI service on port `:11435`, adjacent to Ollama but not part
  of it. Ollama itself cannot change `NUM_PARALLEL` over HTTP — the service does it by recreating
  the container. Verified contract (`GET /openapi.json`, 2026-07-27), identical on both hosts:
  ```
  POST /reconfigure  {model*: str, num_parallel?: int, context_length?: int}
                  -> {model, num_parallel, context_length, container_id, elapsed_seconds}
  GET  /status       -> {container_running: bool, container_id: str|null, env: {OLLAMA_*: str}}
  GET  /models       -> [{model: str, num_parallel: int}]
  GET  /health       -> {status: "ok"}
  ```
- **already correct** (the reconfigure skip condition): **both** of
  1. `GET :11435/status` → `container_running == true`
  2. `GET :11435/status` → `int(env["OLLAMA_NUM_PARALLEL"]) == requested`

  A running container alone is a *partial* marker and must not count (`02` §5).

  **The resident model is deliberately NOT part of this condition.** Measured on
  `linux_3060`, 2026-07-27: `POST /reconfigure {"model":"mistral-nemo:12b","num_parallel":4}`
  returned in **0.44 s** with a new `container_id`, `/status` correctly showed
  `OLLAMA_NUM_PARALLEL=4` — and `/api/ps` returned `{"models":[]}`. **Reconfiguring does not
  load a model.** The `model` field is used by the service to derive/validate `num_parallel`
  (`benchmark.py:62-80` calls it with no `num_parallel` purely to *learn* the recommended
  count); it is not an instruction to load. Making a resident-model mismatch trigger a
  reconfigure would therefore restart the container and still leave the model unloaded — pure
  cost, no effect, and in the degenerate case one restart per combo.

- **warm-up:** a single discarded `/api/chat` with `num_predict: 4`, issued during pre-flight
  when `GET :11434/api/ps` shows the desired model is not resident. This — not the reconfigure —
  is what loads the model. All four POC scripts do exactly this
  (`sweep_matrix.py:239-243`, `oom_probe.py:48-68`, `cliff_sweep.py:89-91`,
  `benchmark.py:162-166`).

  **Why it belongs in pre-flight.** With `OLLAMA_MAX_LOADED_MODELS=1`, whichever model a run
  needs is loaded lazily by its first real generation call. Without a warm-up, that cold load is
  billed to `persona_00000` — measured `load_duration` 2.8 s on the Linux server, but ~57 s on
  the Windows SMR disk per the host notes. That is a fabricated outlier in exactly the
  per-persona wall-clock `generation_metadata` measures, produced by a feature whose purpose is
  to make those timings trustworthy. Moving it into pre-flight attributes it honestly.

  The two real same-worker-count collisions make this concrete rather than theoretical: on
  `linux_3060`, `mistral-nemo:12b` and `qwen3:14b` both want 4, and `gemma2:9b` and
  `llama3.3:70b` both want 1. Running `qwen3` while `mistral-nemo` is resident at
  `NUM_PARALLEL=4` correctly skips the reconfigure — and still needs the warm-up.
- **observed `num_parallel`:** the value read from `GET /status` **after** the reconfigure
  returns. Never the number we sent, and never the number echoed in the `/reconfigure` response
  body — a 200 is unvalidated boundary data, not proof the setting took.
- **outcome:** exactly one of five states, recorded verbatim in `run_metadata.json`:

  | outcome | meaning |
  |---|---|
  | `already_correct` | `/status` matched; no restart issued |
  | `applied` | reconfigure issued, read-back confirms the requested value |
  | `mismatch` | reconfigure issued, read-back returned a *different* value |
  | `failed` | service unreachable, non-2xx, timeout, or malformed body |
  | `no_control_url` | host has no `control_url`, or no host is bound |

  `mismatch` and `failed` are distinct facts and must not be collapsed: "verified wrong" and
  "could not verify" mean different things for any later timing analysis.
- **required, not an optimisation:** the skip check is mandatory because a restart is idempotent
  in *end state* but not in *side effects* — each redundant restart evicts the loaded model and
  kills any in-flight request from another user of that GPU. A GUI Run over the current
  `generate_parallel.yaml` selection is 5 combos, so without the skip one button press causes
  five restarts.

---

## Technical Design

### Approach

An **orchestration-layer pre-flight step**, run once per script invocation, before the filter
chain is entered and before any `OllamaClient` is constructed.

This placement is forced by the layering rules in `02` §2/§4. Generation stages must be pure
functions of their inputs — "no hidden global state, no in-place mutation of shared structures" —
and a stage that restarts a container violates that maximally. Config is resolved once at the
edge (`02` §7) and the *resolved outcome* is passed down as plain data; no stage ever reaches out
to the control service.

The pre-flight is **three ordered stages — PROBE, ACT, GATE** — and the pipeline does not start
until the gate passes or is explicitly recorded as failed.

```
resolve host -> resolve workers -> [ PROBE -> ACT -> GATE ] -> generate personas
                                        |       |       |
  ┌─────────────────────────────────────┘       |       |
  │ STAGE 1 — PROBE  (read-only, ~20 ms)        |       |
  │   GET :11435/status  -> container_running, env.OLLAMA_NUM_PARALLEL
  │   GET :11434/api/ps  -> resident model, size_vram vs size
  │   => desired state already in place?  (num_parallel == desired AND model resident)
  │
  ├─────────────────────────────────────────────┘       |
  │ STAGE 2 — ACT  (only what is actually needed)       |
  │   num_parallel wrong  -> POST /reconfigure          |  (measured 0.44 s)
  │                          NOTE: this RESTARTS the container and
  │                          EVICTS the resident model -> warm-up becomes mandatory
  │   model not resident  -> POST /api/chat {num_predict: 4}, reply discarded
  │   nothing wrong       -> do nothing at all
  │
  └─────────────────────────────────────────────────────┘
    STAGE 3 — GATE  (prove the server can serve, before the pipeline)
      poll GET :11434/api/tags until 200        (500 ms interval, 60 s budget)
      GET :11435/status  -> container_running AND num_parallel == desired
      GET :11434/api/ps  -> desired model resident
                         -> size_vram == size, else WARN "KV spilled to CPU"
      => ready | not_ready(<reason>)
```

**The gate is mandatory and is the only thing that authorises the pipeline to start.** It is not
an optimisation and not a log line: `ready` is a precondition of generating the first persona.
Its three reads are cheap (~20 ms total) and they are the same reads as STAGE 1, so the code is
one probe function called twice — before and after acting.

**Why polling `/api/tags` is required.** `POST /reconfigure` returns when *Docker* reports the
container recreated (0.44 s measured), **not** when Ollama inside it is accepting connections.
Between those two moments the endpoint refuses connections. The POC never noticed because it
immediately fired a warm-up with a 300–900 s timeout that absorbed the gap. Relying on that here
would push a connection error into the first persona instead of failing cleanly in pre-flight.
`OllamaClient._validate_server` (`clients/ollama_client.py:85-107`) already probes `/api/tags`
for exactly this purpose and is the shape to reuse — but it is constructed *per persona*, far too
late to serve as the gate.

**Ordering matters and is not interchangeable.** A reconfigure evicts the resident model, so
whenever STAGE 2 reconfigures, the warm-up must follow it, never precede it. Warming first and
reconfiguring second would discard the load and leave the model unresident — the same conflation
this plan already made once and corrected by measurement.

**When the gate fails.** Record `not_ready` with the reason and **still proceed** — consistent
with the error boundary below, since the run is functionally correct at any parallelism and the
per-persona client does its own `_validate_server`. The gate's value is that the failure is named
in pre-flight and recorded in provenance, rather than surfacing as an opaque error mid-run.

**Failure is tolerated, never swallowed.** The run is correct at any `NUM_PARALLEL` — only slower
— so per `02` §8 this is optional-input territory: "return an explicit, documented absent marker
and make downstream code branch on it visibly", not a bare `except: pass`. Hence the five-state
outcome rather than a boolean, specific exception arms rather than `except Exception`, and the
outcome persisted so a later analysis can filter on it. `03` §6 supplies the obligation directly:
"Report what was dropped. Silent exclusion reads downstream as 'everything was included' when it
wasn't."

**Readiness is a gate, not an assumption.** `POST /reconfigure` returning 200 means Docker
recreated the container, nothing more — measured at 0.44 s with `/api/ps` still reporting
`{"models":[]}`. Three separate facts must each be confirmed before the pipeline starts, and
none of them follows from the others: the HTTP port is accepting connections
(`/api/tags` poll), the parallelism actually took (`/status` read-back), and the model is
resident and fully on GPU (`/api/ps`). The POC confirmed none of these — it fired a warm-up with
a 300–900 s timeout and inferred success from the reply.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|---|---|---|---|
| Pre-flight in the script, GUI passes a flag | One code path for GUI and CLI; honours the GUI contract (GUI translates options to flags, scripts never read the flow YAML) | Per-combo subprocesses repeat the call — mitigated by the skip check | **Chosen** |
| GUI itself POSTs `/reconfigure` before spawning | One call per Run press, no repetition | Puts server-mutation logic in the GUI; CLI runs never benefit; splits the logic in two | Rejected |
| Always reconfigure, no skip check | Simplest | 5 restarts per Run press on the current selection; each evicts the model and kills other users' in-flight work | Rejected |
| Make `GET /models` authoritative for worker counts | Kills hand-transcription and the stale-value bug class outright | No offline runs; GUI needs the server up; tests need a fake for a *config* read; the same commit yields different concurrency on different days | Rejected — config stays authoritative, `/models` validates only |
| Sync command that rewrites axis maps from `/models` | Offline + reproducible, refresh is one command | Third moving part, and a sync step that can be forgotten | Rejected (revisit if drift warnings become frequent) |
| Fail the run when reconfigure fails | Timing telemetry is never contaminated | Turns a slow run into no run, for a service that is not required for correctness | Rejected — record the outcome instead |
| Reuse an existing HTTP/retry helper | — | None exists. `src/utils/` has no HTTP; retry is duplicated inline in all four clients | N/A — client brings its own |

### Architecture & Module Contracts

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|---|---|---|---|
| `config/synthetic/ollama_hosts.yaml` | Declare each host's endpoints | — | models, workers, axes |
| `generators/synthetic/ollama_hosts.py` | Load + validate the registry | `host_id \| None` → `OllamaHost` | HTTP, control API, argparse |
| `clients/ollama_control_client.py` **(new)** | Speak HTTP to one control endpoint | `(control_url)` → typed responses | model axes, workers, config files, the registry |
| `generators/synthetic/ollama_concurrency.py` **(new)** | Decide + carry out skip/reconfigure/verify; return an outcome | `(control_client, base_url, model, desired) → ReconfigureOutcome` | argparse, Qt, output paths, YAML |
| `scripts/generate/generate_identities_parallel.py` | Orchestrate: resolve, pre-flight once, generate, record | CLI args → persona dirs + provenance | HTTP mechanics, response shapes |
| `gui/widgets/flow_options_panel.py` | Render the checkbox | flow YAML → `QCheckBox` | control URLs, HTTP, outcomes |

Dependency direction stays one-way: orchestration → policy (`ollama_concurrency`) → transport
(`ollama_control_client`). The control client is a **deep module** (`05` §4): one small surface
hiding HTTP, timeouts and error mapping. Two hosts is two — per `05` §6 (YAGNI) and §3 ("don't
abstract until you see the third case"), this is a two-entry config-driven client, **not** a
server-management framework.

**Registry shape** — `control_url` is optional and must be declared last (all existing
`OllamaHost` fields are non-default):

```yaml
  linux_3060:
    label: "Linux server - RTX 3060 12 GB"
    base_url: "http://192.168.0.19:11434"
    control_url: "http://192.168.0.19:11435"   # optional; absent = no auto-reconfigure
    gpu: "NVIDIA RTX 3060, 12 GB"
    server_num_parallel: 1
```

It is **not** added to `_REQUIRED_HOST_KEYS` (`ollama_hosts.py:39`). A host without it still
loads and still runs; it simply yields `no_control_url`.

**Client contract** — mirrors the error idiom of `OllamaClient._validate_server`
(`clients/ollama_client.py:85-107`): three distinct `except` arms, each re-raised naming the
exact endpoint probed.

```python
@dataclass(frozen=True)
class ReconfigureOutcome:
    outcome: str                 # already_correct | applied | mismatch | failed | no_control_url
    requested: int | None
    observed: int | None         # from GET /status read-back; None when unverifiable
    elapsed_seconds: float | None
    control_url: str | None
    detail: str | None           # error text for failed/mismatch

class OllamaControlClient:
    def __init__(self, control_url: str, timeout: int = 120) -> None: ...
    def status(self) -> dict            # {container_running, container_id, env}
    def models(self) -> dict[str, int]  # {model_name: recommended_num_parallel}
    def current_num_parallel(self) -> int | None
    def reconfigure(self, model: str, num_parallel: int) -> dict
```

Timeout 120 s matches the three POC sweep scripts (`sweep_matrix.py:99-101`,
`oom_probe.py:50-54`, `cliff_sweep.py:89`); `/status`, `/models` and `/health` use 10 s, matching
`_validate_server`.

### Recorded decision — mutating shared infrastructure

The engineering guides cover layering, idempotency and error boundaries but say **nothing** about
mutating state shared with other users. This is therefore an explicit decision rather than a
derived one (`05` §9, ADR).

A generation run will restart a container on a GPU server that also serves Open WebUI and, on the
Linux host, ComfyUI. That is accepted because the run is about to monopolise that GPU for minutes
anyway, and running it mis-tuned wastes the same GPU for roughly twice as long. Three constraints
bound the blast radius: the skip check means a correctly-configured server is never touched; the
call happens once, before generation, not between personas; and the feature is a checkbox that
can be turned off. No locking or in-use detection is attempted — `/status` reports
`container_running`, not whether a request is in flight.

---

## Implementation Plan

### Phase 1: Registry gains `control_url`
**Goal:** Hosts can declare a control endpoint; absence is legal.

**Started:** 2026-07-27
**Completed:** 2026-07-27

- [x] 1.1 — Add `control_url: str | None = None` as the last field of `OllamaHost`
      (`ollama_hosts.py:42-55`), with a comment stating that absence means no auto-reconfigure.
- [x] 1.2 — In `_build_host` (`:90-114`), materialise it as
      `str(entry["control_url"]) if entry.get("control_url") is not None else None`. Do **not**
      add it to `_REQUIRED_HOST_KEYS`.
- [x] 1.3 — Validate shape when present: must be a non-empty string starting `http://` or
      `https://`; raise naming the host id and the file otherwise.
- [x] 1.4 — Add `control_url` to both hosts in `config/synthetic/ollama_hosts.yaml`
      (`http://192.168.0.19:11435` and `http://localhost:11435`).

**Files Modified:** `src/population_synthetic/generators/synthetic/ollama_hosts.py`,
`config/synthetic/ollama_hosts.yaml`

**Dependencies:** None

### Phase 2: Control client + concurrency policy
**Goal:** A tested, fail-fast client and the decision logic, with no orchestration knowledge.

**Started:** 2026-07-27
**Completed:** 2026-07-27

- [x] 2.1 — New `src/population_synthetic/clients/ollama_control_client.py` implementing the
      contract above. Own `requests.Session`. Specific `except` arms for `ConnectionError`,
      `Timeout`, `HTTPError` — never bare `Exception`.
- [x] 2.2 — Validate response bodies at the boundary (`02` §3): `/status` must contain
      `container_running` and an `env` mapping; `/models` must be a list of `{model,
      num_parallel}`. Raise a specific error on a malformed body rather than `.get()`-ing
      through it.
- [x] 2.3 — `current_num_parallel()` returns `int(env["OLLAMA_NUM_PARALLEL"])`, or `None` when
      the key is absent or unparseable — an explicit absent marker, never a substituted default.
- [x] 2.4 — New `src/population_synthetic/generators/synthetic/ollama_concurrency.py` with
      `ensure_num_parallel(control_client, base_url, model, desired) -> ReconfigureOutcome`,
      implementing **two independent steps in order**:
      (a) *reconfigure* — skip when `already correct` (the two `/status` conditions), else
          `POST /reconfigure`, then read back from `/status` and classify the outcome;
      (b) *warm-up* — read `GET {base_url}/api/ps`; if the desired model is not resident, issue
          one `/api/chat` with `num_predict: 4` and discard the reply.
      Step (b) runs regardless of step (a)'s outcome, including `already_correct` and
      `no_control_url` — the model still has to be loaded, and a host with no control service
      benefits from the warm-up just as much. Pure policy; injected clients, no network in tests.
- [x] 2.4b — `resident_model(base_url) -> str | None` reading `GET {base_url}/api/ps` on the
      **inference** port (`:11434`), not the control port. `cliff_sweep.py:71-81` already reads
      this endpoint and is the shape to follow. Returns `None` when nothing is loaded, and
      `None` — never a guess — when the body is unparseable. This is why the policy takes
      `base_url` as well as the control client: the loaded model is Ollama's own state and
      `/status` does not expose it.
- [x] 2.4c — Timeouts, from measurement rather than guesswork: `/reconfigure` **120 s** (the POC
      value; measured 0.44 s, so the margin is large), `/status` `/models` `/health` **10 s**
      (matching `_validate_server`), warm-up `/api/chat` **600 s** — it must absorb a cold load,
      measured 2.8 s on `linux_3060` but ~57 s on the Windows SMR disk and far longer for 70B.
      A warm-up timeout is a warning, never fatal.
- [x] 2.4d — `probe(control_client, base_url, model) -> ServerState` — the single read-only
      function used by **both** STAGE 1 and STAGE 3. Returns
      `{reachable, container_running, num_parallel, resident_model, vram_fully_loaded}`, each
      field `None` when unknown rather than defaulted. Calling it twice is what makes
      "did acting achieve what we wanted?" a comparison rather than an assumption.
- [x] 2.4e — `wait_until_serving(base_url, budget_s=60, interval_s=0.5) -> float | None` —
      polls `GET {base_url}/api/tags` until 200, returning seconds waited, or `None` on timeout.
      Required because `/reconfigure` returns when Docker has recreated the container, not when
      Ollama is listening. Reuse the error-arm idiom of `OllamaClient._validate_server`
      (`clients/ollama_client.py:85-107`) — that function probes the same endpoint for the same
      purpose, but runs per persona, far too late to gate on.
- [x] 2.4f — `ReadinessOutcome`: `ready | not_ready`, with `reason` (`port_timeout`,
      `num_parallel_mismatch`, `model_not_resident`, `unreachable`) and `waited_seconds`. Warn
      and proceed on `not_ready` — the gate's job is to name and record the failure in
      pre-flight, not to abort a run that is functionally correct anyway.
- [x] 2.4g — Warn (do not fail) when `/api/ps` reports `size_vram < size`: the KV cache has
      spilled to CPU, which collapses throughput 2-3x per `REPORT.md`. This is the "cliff" the
      POC measured, and the requested `num_parallel` is the likely cause.
- [x] 2.5 — `check_worker_drift(client, model, configured) -> str | None` returning a warning
      message when `/models` disagrees with the configured worker count, else `None`. Config is
      never overridden.

**Files Modified:** two new modules under `clients/` and `generators/synthetic/`

**Dependencies:** Phase 1

### Phase 3: Orchestration pre-flight + provenance
**Goal:** Runs tune the server once, and record what actually happened.

**Started:** 2026-07-27
**Completed:** 2026-07-27

- [x] 3.1 — Add `--ollama-reconfigure` (`action="store_true"`, default `False`) to
      `generate_identities_parallel.py`, beside `--ollama-auto-workers` (`:304-311`).
- [x] 3.2 — Insert the pre-flight at **`:445`** — immediately after `--ollama-auto-workers`
      resolution and before the `server_num_parallel` warning block (`:447-461`). This is the
      first point where `args.workers` is final and `ollama_host` is bound, and it precedes every
      `OllamaClient` construction (each of which probes `/api/tags`).
- [x] 3.3 — Gate on `ollama_host is not None` **and** `args.ollama_reconfigure` **and**
      `ollama_host.control_url is not None`. An explicit `--base-url` leaves `ollama_host` as
      `None` by design (`:408-409`); never reconfigure a host the run is not using.
- [x] 3.4 — Keep the existing `server_num_parallel` warning, but suppress it when the outcome is
      `already_correct` or `applied` — the condition it warns about no longer holds. Still warn
      on `mismatch`, `failed` and `no_control_url`.
- [x] 3.5 — Log each outcome at an appropriate level: INFO for `already_correct` / `applied`
      (including `elapsed_seconds`), WARNING for `mismatch` / `failed`. Note that the log-file
      handler is attached later (`:496-499`), so pre-flight output reaches the console only —
      either accept that or move the handler earlier; decide and state it in the code.
- [x] 3.6 — Record `parameters.ollama_reconfigure` in `run_metadata.json` (built `:519-547`) as
      the full outcome object. `observed` comes from the read-back and is `null` when
      unverifiable. Never record `requested` as if it were applied. Record the **warm-up
      separately** — `{performed: bool, model, load_seconds, error}` — because a warm-up that
      failed means `persona_00000`'s wall-clock still carries a cold load, and a later timing
      analysis must be able to see that. Record the **readiness gate** as a third block —
      `{state, reason, waited_seconds, vram_fully_loaded}` — so a run that generated against a
      server that never became ready is identifiable afterwards rather than merely slow-looking.
- [x] 3.7 — Run the drift check alongside the pre-flight and log its warning if any.

**Files Modified:** `scripts/generate/generate_identities_parallel.py`

**Dependencies:** Phase 2

### Phase 4: GUI checkbox
**Goal:** Pressing **Run** reconfigures, by default.

**Started:** 2026-07-27
**Completed:** 2026-07-27

- [x] 4.1 — Add `ollama-reconfigure: true` under `options:` in
      `config/gui/flows/generate_parallel.yaml`. Required — `FlowConfigModel.set_option`
      (`flow_config_model.py:109-115`) raises on keys absent from the YAML.
- [x] 4.2 — `_OPTION_LABELS["ollama-reconfigure"] = "Reconfigure Ollama Host"` in
      `flow_options_panel.py`. No enum needed: a bool renders as a checkbox via existing shape
      dispatch.
- [x] 4.3 — No change to `commands.py` or `execution.py`. `_option_args` (`commands.py:41-50`)
      and `CombinationRunner` (`execution.py:109-114`) already emit a bare flag for `True`.
      Verify; report rather than edit if not. **Verified, both unchanged:** `_option_args`
      (`commands.py:41-50`) and the inline override loop in `CombinationRunner.run`
      (`execution.py:109-114`) each test `isinstance(value, bool)` first and append `f"--{key}"`
      with no value when true.

**Files Modified:** `config/gui/flows/generate_parallel.yaml`,
`src/population_synthetic/gui/widgets/flow_options_panel.py`

**Dependencies:** Phase 3

---

## Testing Plan

All tests use an **injected fake client**. No test performs a real restart or touches the
network (`05` §8 — keep the pyramid upright).

### Unit Tests
- [x] `control_url` absent → host loads, `control_url is None`.
- [x] `control_url` present but malformed (empty, no scheme) → raises naming host id and file.
- [x] `current_num_parallel()` returns `None` when `env` lacks `OLLAMA_NUM_PARALLEL` or it is
      unparseable — not `0`, not a default.
- [x] Malformed `/status` body (no `container_running`, `env` not a mapping) → raises.
- [x] Malformed `/models` body → raises.
- [x] Table-driven outcome classification, one row per state:
      `already_correct` (running + value matches), `applied` (read-back matches),
      `mismatch` (read-back differs), `failed` (each of ConnectionError / Timeout / non-2xx /
      bad body), `no_control_url`.
- [x] `container_running == false` with a matching value → **not** `already_correct` (partial
      marker must not satisfy the complete check).
- [x] **Same worker count, different resident model → skip the reconfigure, still warm up.**
      Server at `NUM_PARALLEL=4` with `mistral-nemo:12b` resident, run wants `qwen3:14b` at 4 →
      `already_correct`, **zero** `/reconfigure` calls, **one** warm-up `/api/chat`. Add the
      `gemma2:9b` / `llama3.3:70b` pair at 1 as a second row. These are the real collisions in
      today's config.
- [x] **Reconfigure leaves nothing resident.** After `applied`, `/api/ps` returns
      `{"models":[]}` → a warm-up is still issued. This is the measured real behaviour and the
      reason warm-up is a separate step; a test asserting `applied` implies "model loaded"
      would encode the bug this plan already had once.
- [x] Desired model already resident and `NUM_PARALLEL` correct → **no** `/reconfigure` and
      **no** warm-up. The fully-warm path must be free.
- [x] `/api/ps` unreachable or malformed → `resident_model` returns `None` → warm up anyway.
      One redundant warm-up is cheap; skipping it would silently bill a cold load to
      `persona_00000`.
- [x] Warm-up fails or times out → warning, run proceeds, outcome records the warm-up
      separately from the reconfigure outcome. It must never be fatal.
- [x] **Gate: port not yet listening.** `/api/tags` refuses connections for the first N polls
      then answers 200 → `ready`, `waited_seconds` recorded. This is the window between Docker
      recreating the container and Ollama binding its port.
- [x] **Gate: port never comes up** within the 60 s budget → `not_ready(port_timeout)`, warned
      and recorded, run still proceeds.
- [x] **Gate: parallelism silently reverted.** Port up and model resident, but `/status` reports
      a different `num_parallel` than requested → `not_ready(num_parallel_mismatch)`.
- [x] **Gate ordering.** When STAGE 2 reconfigures, the warm-up is issued *after* it; assert the
      call order against a recording fake. Warming first would be discarded by the restart.
- [x] **Fully-warm path is free.** Desired parallelism and model both already in place → PROBE
      finds nothing to do, ACT issues zero calls, GATE passes on the reads it already has.
- [x] `size_vram < size` → warning naming the spill, run proceeds.
- [x] `check_worker_drift` returns `None` on agreement and a message naming both values on
      disagreement, and never mutates the configured value.

### Integration Tests
- [x] Five sequential `ensure_num_parallel` calls with the same (model, desired) against a fake
      that records calls → exactly **one** `/reconfigure`, four `already_correct`. This is the
      GUI 5-combo scenario and the plan's central claim.
- [x] Pre-flight is skipped entirely when `--base-url` is given (no host bound).
- [x] Pre-flight is skipped for non-Ollama providers.
- [x] `run_metadata.json` contains the full outcome object with `observed` from read-back;
      on `failed`, `observed is None`.
- [x] The `server_num_parallel` warning is suppressed on `applied` and still emitted on `failed`.
- [x] GUI: `ollama-reconfigure: true` produces a bare `--ollama-reconfigure` in the arg vector.
      (`test_workflow_commands.py` — read from the shipped `generate_parallel.yaml`, not a
      literal; plus a shape-dispatch/label check in `test_flow_options_panel_enum.py`.)

### Baseline measurements (both hosts, 2026-07-27 — already done)

The atomistic check was run end-to-end against **both** hosts before this plan was finalised.
`linux_3060`: `mistral-nemo:12b` @ 4. `windows_4070tis`: `deepseek-r1:14b` @ 6.

| | `linux_3060` | `windows_4070tis` |
|---|---|---|
| `POST /reconfigure` `elapsed_seconds` | 0.44 s | **9.83 s** |
| `/api/tags` 200 after reconfigure returned | not measured | **14.68 s** (first poll: `RemoteDisconnected`) |
| `/api/ps` immediately after reconfigure | `{"models":[]}` | `{"models":[]}` |
| `/status` read-back vs requested | 4 == 4 | 6 == 6 |
| warm-up `load_duration` | 2.8 s | **83.4 s** |
| `size_vram` vs `size` after warm-up | full GPU | 13.93 / 13.93 GB, no spill |
| **total pre-flight** | ~3 s | **~123 s** |

**Behaviour is identical across hosts; only cost differs (20-30x).** Both refuse to load a model
on reconfigure, both read back correctly, both expose the same OpenAPI schema. No per-host
special-casing is required — the same three-stage logic is correct for both.

Three constants are fixed by these numbers rather than guessed:
- **Gate budget 60 s** — 14.68 s observed on the slower host, ~4x margin.
- **Warm-up timeout 600 s** — 98 s total observed on the slower host, and 70B models are absent
  from that host but present on Linux.
- **The skip check's value is ~10 minutes per GUI Run** — Windows pre-flight is ~123 s, and the
  current 5-strategy selection would pay it five times without the skip, plus five evictions.

The 83.4 s cold load is the strongest single argument for the pre-flight warm-up: at ~30 s per
persona it would make `persona_00000` a 4x outlier, corrupting that combo's mean.

### Manual Verification
- [ ] Re-run the atomistic check on whichever host is retuned, to confirm the constants above
      still hold after any container change.
- [ ] `GET :11435/status` on both hosts before and after a run; confirm the value changed and
      matches the axis worker count.
- [ ] GUI Run over the current 5-strategy selection; confirm one restart in the console and four
      `already_correct` lines.
- [ ] Stop the control service; confirm the run still completes and records `failed`.
- [ ] Compare wall-clock for the same combo before and after, to confirm batching is real.

### Edge Cases
- [ ] Desired workers exceeds the model's `/models` ceiling → drift warning fires; decide and
      document whether to clamp or proceed (proposal: warn and proceed, config is authoritative).
- [ ] Model name in the axis file is absent from `/models` (e.g. an alias) → drift check reports
      "unknown to server", does not raise, does not block the reconfigure.
- [ ] `/reconfigure` returns 200 but the read-back shows the old value → `mismatch`, warn, proceed.
- [ ] Control service reachable but Ollama itself down → `/reconfigure` fails; outcome `failed`;
      the later `OllamaClient._validate_server` raises with its own clear message.
- [ ] Two combos with **different** models in one Run → two restarts, unavoidable and correct.

---

## Documentation Plan

- [x] `docs/ollama_server_models.md` — the `control_url` column, the `:11435` contract, the
      five outcome states, and that both hosts now have the service.
- [x] `docs/architecture/configuration.md` — the new optional registry key.
- [x] `docs/development/gui.md` — the new checkbox and what pressing Run now does to the server.
- [x] `CLAUDE.md` — Environment & Secrets: `--ollama-reconfigure` and the fact that a run may
      restart the host's container.
- [x] Inline: the ADR paragraph above, recorded where the pre-flight lives, explaining *why* a
      pipeline is permitted to restart shared infrastructure and why failure is tolerated
      (`05` §5 — comments explain why, not what).

---

## Rollback Plan

1. **Before merge:** one feature branch; `git checkout dev` discards it.
2. **Data considerations:** none. `run_metadata.json` gains one additive key that existing
   readers ignore. No migrations, no stored state.
3. **Partial rollback:** removing `ollama-reconfigure` from the flow YAML disables the feature
   entirely while leaving the CLI flag available — the default is `False` in argparse, so the
   GUI is the only thing that turns it on.
4. **Full revert:** the four phases are independent commits; reverting Phase 3 alone leaves an
   unused client and an unused registry key, both inert.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A run restarts a container someone else is actively using | Med | Med | Skip check means a correct server is never touched; call happens once, pre-run; checkbox can be turned off. Accepted and recorded as an ADR — no locking attempted |
| Skip check has a bug → 5 restarts per Run press | Low | High | It is the plan's central claim, so it gets a dedicated integration test asserting call counts against a recording fake |
| Cold load billed to `persona_00000`, inflating the first per-persona wall-clock | High without warm-up | Med | A pre-flight warm-up runs whenever `/api/ps` shows the desired model is not resident, independently of the reconfigure outcome. Any ambiguity resolves toward warming up |
| Someone re-conflates "reconfigure" with "model loaded" during implementation | Med | Med | Measured and recorded in Definitions: reconfigure returns in 0.44 s leaving `models: []`. A dedicated test asserts a warm-up still follows an `applied` outcome |
| Pipeline starts before Ollama is listening → opaque connection error mid-run | Med | Med | STAGE 3 polls `/api/tags` to 200 before any persona is generated. `/reconfigure` returning 200 only means Docker recreated the container |
| Gate budget too small on the slow host | Low | Med | Measured: 14.68 s on `windows_4070tis`, 60 s budget, ~4x margin. Re-measure if a host is retuned |
| Windows host behaves differently from Linux | Resolved | — | Both checked 2026-07-27 (see Baseline measurements). Behaviour identical, cost 20-30x higher on Windows. No per-host branching needed |
| Pre-flight cost (~123 s on Windows) makes short runs feel slow | Med | Low | Paid only when the model or parallelism actually changes; the skip path is ~20 ms. This is the cost the warm-up *moves* out of `persona_00000`, not new cost |
| `/reconfigure` returns 200 without applying | Low | High | Read-back from `/status` is mandatory; `mismatch` is a distinct recorded outcome, never collapsed into `applied` |
| Reconfigure fails silently and timing telemetry is contaminated | Med | Med | `observed` is `null` on failure and the outcome is persisted, so later analysis can filter. The requested value is never recorded as applied |
| Restart exceeds the 120 s timeout | Low | Med | Timeout matches the three POC sweeps; a timeout is a specific `except` arm yielding `failed`, and the run proceeds |
| `gemma4_e4b: 84` is faithfully applied but far past the useful knee | Med | Med | Out of scope here, flagged in Goals: 84 is a VRAM ceiling, not a measured knee, and per-slot efficiency was ~28% at 12 slots on the 3060 |
| Control service present on one host only in future | Low | Low | `control_url` is optional by construction; `no_control_url` is a first-class outcome |
| Pre-flight logs miss the run log file (handler attached later) | High | Low | Called out in task 3.5 — either move the handler or accept console-only, but decide explicitly |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|---|---|---|
| Phase 1 — Registry `control_url` | ~20 LOC + config | None |
| Phase 2 — Client + policy | ~180 LOC across 2 new modules + tests | Phase 1 |
| Phase 3 — Pre-flight + provenance | ~60 LOC in one script | Phase 2 |
| Phase 4 — GUI checkbox | ~5 LOC + 1 YAML key | Phase 3 |

---

## References

- `docs/development/plans/completed/selectable-ollama-host.md` — the host registry this extends;
  its `server_num_parallel` field becomes verifiable rather than merely asserted.
- `docs/development/ollama-parallelism-poc/REPORT.md` — measured 1.6x-3.4x from server-side
  batching; the per-model ceilings. Supersedes `RESULTS.md` in the same directory.
- `docs/development/ollama-parallelism-server-report.md` — the original request that produced the
  `:11435` service; "Both halves are required."
- `docs/development/ollama-parallelism-poc/{benchmark,sweep_matrix,cliff_sweep,oom_probe}.py` —
  the only existing callers; source of the 120 s timeout and the synchronous-POST assumption.
- `docs/development/gui.md` — the GUI-translates-YAML-to-CLI execution contract.

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- CLAUDE.md
- config/gui/flows/generate_parallel.yaml
- config/synthetic/ollama_hosts.yaml
- docs/architecture/configuration.md
- docs/development/gui.md
- docs/development/plans/active/ollama-auto-reconfigure.md
- docs/ollama_server_models.md
- scripts/generate/generate_identities_parallel.py
- src/population_synthetic/clients/ollama_control_client.py
- src/population_synthetic/generators/synthetic/ollama_concurrency.py
- src/population_synthetic/generators/synthetic/ollama_hosts.py
- src/population_synthetic/gui/widgets/flow_options_panel.py
- tests/_ollama_fakes.py
- tests/test_flow_options_panel_enum.py
- tests/test_ollama_concurrency.py
- tests/test_ollama_control_client.py
- tests/test_ollama_hosts.py
- tests/test_ollama_preflight_cli.py
- tests/test_workflow_commands.py
