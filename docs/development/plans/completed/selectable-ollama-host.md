# Plan: Selectable Ollama Host

**Date:** 2026-07-27
**Author:** Basil
**Status:** Completed
**Completed:** 2026-07-27 14:26
**Base Branch:** `dev`
**Branch:** `feature/selectable-ollama-host`

---

## Overview

Identity generation with `--provider ollama` currently hardwires one machine. This adds a
config-sourced registry of Ollama inference hosts, a `--ollama-host` CLI flag, and a GUI
dropdown to select between them, with each host carrying its own per-model parallel-worker
counts because worker capacity is a function of (model x GPU VRAM).

## Problem Statement

A second Ollama backend now exists on the Windows workstation that runs the GUI
(`192.168.0.37`, RTX 4070 Ti SUPER 16 GB, reachable at `http://localhost:11434`,
documented in the home-lab notes under `docs/ollama/windows-local-stack-usage.md`). It
holds 4 of the 9 modelled Ollama models with digest-identical weights on a faster GPU.
There is currently no way to target it.

The endpoint `http://192.168.0.19:11434` is duplicated in **10 tracked non-doc locations**:
all 9 `config/synthetic/axes/models/ollama_*.yaml` files (`model_config.base_url`) plus
`_DEFAULT_BASE_URL` in `src/population_synthetic/clients/ollama_client.py:22`. That is ten
copies of one fact, and the copy inside the client is a silent fallback: a run that fails to
supply a URL is dispatched to the Linux server and produces normal-looking output attributed
to the wrong GPU.

Two properties of the second host shape the design:

1. It runs `OLLAMA_NUM_PARALLEL=1` today, so requests beyond the first queue rather than
   batch. Selecting it is a correctness and provenance win before it is a speed win.
2. It holds only `deepseek-r1:14b`, `gemma4:e4b`, `mistral-nemo:12b` and
   `llama3.1:8b-instruct-q4_K_M`. The other five `ollama_*` model axes must fail before a
   single persona is generated.

## Goals

### In Scope

1. A single authoritative registry of Ollama endpoints at `config/synthetic/ollama_hosts.yaml`.
2. Per-host, per-model worker counts: `parameters.parallel.workers` in each
   `ollama_*.yaml` becomes a `{host_id: n}` map.
3. A `--ollama-host` flag on both generate scripts, and a config-sourced **Ollama Host**
   dropdown in the GUI flow-options panel.
4. Removal of every duplicated and fallback copy of the base URL.
5. Fail-fast when a selected (host, model) pair is unsupported, naming the hosts that do
   support it.
6. Provenance: the resolved host id, URL and worker count recorded in both
   `run_metadata.json` and `manifest_snapshot.yaml`.

### Out of Scope

- **Measuring the 4070 Ti SUPER worker counts.** That assessment is happening elsewhere and
  the numbers will be supplied later; this plan builds the mechanism that consumes them.
- Recreating the Windows container at a higher `OLLAMA_NUM_PARALLEL`.
- Generalising the registry to non-Ollama providers (Gemini / Claude / openai_compat /
  openrouter). No second consumer exists today.
- De-duplicating the client-construction blocks in the two generate scripts
  (`generate_identities_parallel.py:145-184` and `generate_identity.py:252-280`).
- The per-persona `OllamaClient` construction that re-runs `/api/tags` validation N times
  and prevents connection reuse.
- Teaching the `generation_metadata` analysis to group or split by host. The provenance
  stamping here makes that possible later.

## Success Criteria

- [ ] `grep -r "192.168.0.19" src/ scripts/` returns **zero** hits, and within `config/` the
      only live hit is `config/synthetic/ollama_hosts.yaml`. The 15 frozen
      `identity_manifest_0NN_*.yaml` seed manifests are excluded — they are historical
      records of past runs, not live configuration. `template_identity_manifest.yaml` is
      **not** excluded: its documented fallback chain no longer exists and must be corrected.
- [ ] `OllamaClient(model_name="x")` with no `base_url` raises `TypeError`; with
      `OLLAMA_BASE_URL` set in the environment it still raises (the env read is gone).
- [ ] Generating `ollama_llama33_70b` against `windows_4070tis` raises before any persona
      directory is created, and the message names `linux_3060`.
- [ ] `run_metadata.json` and `manifest_snapshot.yaml` both record `ollama_host`,
      the resolved `base_url`, and the resolved scalar `workers`.
- [ ] The GUI's **Ollama Host** dropdown lists both host labels, sourced from the registry
      (no hardcoded Python list), and its selection round-trips through Save.
- [ ] **Extension check:** adding a hypothetical third host requires editing
      `ollama_hosts.yaml` plus one key per model axis and **zero `.py` files**.
- [ ] `ruff check src/` clean, `pytest` green, and `ruff check scripts/` introduces **no new
      findings** versus the base branch. `scripts/` carries 26 pre-existing E501s unrelated to
      this work; fixing them is out of scope and would obscure the diff.

## Definitions

- **host id:** a key under `hosts:` in `config/synthetic/ollama_hosts.yaml`. It is the only
  identifier that appears in CLI flags, GUI config, axis-file worker maps, and run
  provenance. Not a hostname, not a URL.
- **supported (host, model) pair:** the model axis file's
  `parameters.parallel.workers` map contains that host id as a key. Absence of the key
  **is** the unsupported signal — there is no separate availability list to keep in sync.
  A present key asserts both "the weights are pulled on that host" and "this worker count
  has been assessed for it".
- **`server_num_parallel`:** the value of the `OLLAMA_NUM_PARALLEL` environment variable in
  that host's Ollama process, as declared by a human in the registry. It is **not** a worker
  count and is never used as one. Its sole use is emitting a warning when a resolved worker
  count exceeds it. The code cannot verify it — Ollama exposes it on no endpoint.
- **resolved worker count:** the single `int` produced by
  `compose_manifest()` from `workers[host_id]`. Downstream code sees only this scalar and
  never the map.

---

## Technical Design

### Approach

A three-part split along the existing dependency direction (orchestration → stages →
helpers):

1. **Registry** — one YAML file plus a small fail-fast accessor, mirroring the shape of the
   existing `analysis/model_ranking/hosting.py` (`load_hosting_config` / `classify_hosting`).
2. **Normalization** — `compose_manifest()` is the single point where the `{host_id: n}`
   map collapses to a scalar and where the base URL is resolved. This follows the
   established explicit field-by-field composition table in
   `plans/completed/composable-experiment-config.md`; no downstream module learns that hosts
   exist.
3. **Selection** — the host id travels as `--ollama-host` only, per the inviolable GUI
   execution contract in `docs/development/gui.md` (the GUI translates `options:` into CLI
   flags; spawned scripts never read the flow YAML, and no `--flow-config` argument exists
   or may be added).

The client becomes configuration-free: `base_url` is a required constructor parameter. It
stops reading the environment and stops carrying a default, so it can no longer choose a
machine on its own.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Worker map in axis YAML, keyed by host id | Model owns its own VRAM knee; availability falls out of the same structure; adding a host is config-only | Schema break across 9 files | **Chosen** |
| Worker override map in the host registry | Zero axis-file edits | Model knowledge leaks into the host file; the 3060 becomes an implicit default | Rejected |
| Host-specific axis file variants (`ollama_deepseek_r1_14b__windows.yaml`) | No schema change | Fans 9 files into 18+; the matrix-manifest approach already rejected in `composable-experiment-config.md` for exactly this reason | Rejected |
| Separate `available_models` list per host | Explicit | Second authority to keep in sync with the worker map; guaranteed to drift | Rejected |
| Runtime probe of `/api/tags` to determine availability | Self-maintaining | Network call at startup; couples validation to server uptime; still cannot yield a worker count | Rejected |
| Per-host client subclasses | — | "Massive duplication; no real benefit at inference layer" — precedent set in `plans/completed/openai-compat-european-providers.md` | Rejected |
| Keep `_DEFAULT_BASE_URL`, let `--ollama-host` win | Minimal blast radius | Leaves the silent-wrong-GPU failure mode intact | Rejected |
| Provider-agnostic `llm_hosts.yaml` covering all five providers | Future-proof | Speculative generality with one consumer; only Ollama has the (model x VRAM) worker problem | Rejected — named `ollama_hosts.yaml` |

### Architecture & Module Contracts

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `config/synthetic/ollama_hosts.yaml` | Declare every Ollama endpoint and its human-asserted server settings | — | models, workers, axes |
| `generators/synthetic/ollama_hosts.py` | Load + validate the registry; resolve a host id to an `OllamaHost` | `host_id \| None` → `OllamaHost` | models, workers, the GUI, argparse |
| `generators/synthetic/manifest_loader.py` | **The one normalization point.** Collapse `workers[host_id]` → scalar; resolve `base_url` from the host | `(model_id, strategy_id, country_id, host_id)` → `ManifestConfig` | Qt, argparse, output paths |
| `clients/ollama_client.py` | Speak HTTP to one endpoint | `(model_name, base_url, ...)` → completions | the registry, host ids, env vars, YAML |
| `scripts/generate/generate_identities_parallel.py` | Orchestrate: parse flags, compose once, fan out | CLI args → persona dirs + provenance | how workers were chosen per host |
| `gui/widgets/flow_options_panel.py` | Render a dropdown from the registry | registry → `QComboBox` | base URLs, worker counts, argparse |

Dependency direction stays one-way: orchestration (scripts, GUI) → composition
(`manifest_loader`) → helpers (`ollama_hosts`, `clients`). The client gains no imports.

**Registry shape:**

```yaml
# config/synthetic/ollama_hosts.yaml
# The single authoritative list of Ollama inference endpoints.
# Per-model worker counts live in the model axis files
# (parameters.parallel.workers), keyed by the host ids defined here.
default_host: linux_3060      # used only when --ollama-host is omitted on the CLI
hosts:
  linux_3060:
    label: "Linux server - RTX 3060 12 GB"
    base_url: "http://192.168.0.19:11434"
    gpu: "NVIDIA RTX 3060, 12 GB"
    # Human-declared OLLAMA_NUM_PARALLEL of that host's Ollama process.
    # NOT a worker count -- never used as one. Warning threshold only;
    # Ollama exposes this on no endpoint, so the code cannot verify it.
    server_num_parallel: 4
  windows_4070tis:
    label: "Windows PC - RTX 4070 Ti SUPER 16 GB"
    base_url: "http://localhost:11434"
    gpu: "NVIDIA RTX 4070 Ti SUPER, 16 GB"
    server_num_parallel: 1    # container is at NUM_PARALLEL=1 today
```

**Axis-file shape** (representative — `ollama_deepseek_r1_14b.yaml`, currently
`base_url` at line 6 and `workers: 2` at line 16):

```yaml
model_config:
  provider: "ollama"
  model: "deepseek-r1:14b"
  # base_url removed -- the endpoint is a host property, chosen per run
  # (config/synthetic/ollama_hosts.yaml)
  generation_config: { ... unchanged ... }
parameters:
  parallel:
    # Per-host worker count. A host absent from this map does not serve this model.
    # linux_3060: VRAM-max knee per docs/development/ollama-parallelism-poc/REPORT.md
    #   (peak 1.60x). Only effective if that host's OLLAMA_NUM_PARALLEL matches;
    #   else requests queue.
    workers:
      linux_3060: 2
      windows_4070tis: 1      # placeholder -- awaiting external worker assessment
```

`linux_3060` values are today's scalars, unchanged: gemma4:e4b 12, llama3.2:3b 10,
Lucie-7B 7, llama3.1:8b 6, mistral-nemo:12b 4, qwen3:14b 4, deepseek-r1:14b 2,
gemma2:9b 1, llama3.3:70b 1. The five models absent from the Windows box
(`ollama_llama32_3b`, `ollama_lucie_7b`, `ollama_qwen3_14b`, `ollama_gemma2_9b`,
`ollama_llama33_70b`) get a `linux_3060` key only.

### Recorded decisions

**Deleting `_DEFAULT_BASE_URL` and the `OLLAMA_BASE_URL` env read.** The documented
precedence chain in `plans/completed/add-ollama-client.md` was: explicit arg → env →
hardcoded default. Both lower tiers go. The hardcoded default is a stale IP that silently
sends a whole sweep to the wrong GPU while the outputs look normal — a silent wrong number
is strictly worse than a crash. The env read is the same class of hidden input and violates
"stages should not reach back out to read global config or the environment"; the client is a
stage. The escape hatch for an ad-hoc endpoint remains the explicit `--base-url` flag,
resolved in the orchestration layer where all other config is resolved.

**Scalar → map is a hard break, not a compatible widening.** `compose_manifest()` raises if
`parameters.parallel.workers` is not a mapping. Accepting the old scalar would reintroduce a
host-implicit default, which is the bug being removed.

**The file-manifest path is deliberately untouched.** `manifest_loader.py:96`
(`parallel.get("workers")`) serves the frozen `identity_manifest_0NN_*.yaml` seed manifests,
which are historical records consumed by the analysis side, and the analysis side does not
read workers. This asymmetry gets an explicit comment so it does not read as an accidental
fallback.

---

## Implementation Plan

### Phase 1: Registry and accessor
**Goal:** One authoritative source of endpoints, with fail-fast loading.

- [x] 1.1 — Write `config/synthetic/ollama_hosts.yaml` with both hosts as shown above.
- [x] 1.2 — Add `src/population_synthetic/generators/synthetic/ollama_hosts.py`:
      frozen `OllamaHost` dataclass (`id, label, base_url, gpu, server_num_parallel`);
      `load_hosts(path=None) -> dict[str, OllamaHost]` raising on missing file, malformed
      YAML, empty `hosts`, or any host missing a required key; `resolve_host(host_id | None)
      -> OllamaHost` where `None` resolves `default_host` and an unknown id raises listing
      valid ids; `host_ids() -> list[str]`.
- [x] 1.3 — Anchor the config path via the existing `PROJECT_ROOT` helper in `_paths.py`;
      no hardcoded path literal.
- [x] 1.4 — Register the file in `docs/architecture/configuration.md` beside the existing
      `config/analysis/model_ranking/provider_hosting.json` entry.

**Files Modified:**
- `config/synthetic/ollama_hosts.yaml` — new
- `src/population_synthetic/generators/synthetic/ollama_hosts.py` — new
- `docs/architecture/configuration.md` — register the file

**Dependencies:** None

### Phase 2: Schema change and normalization
**Goal:** Worker counts become per-host; composition collapses them to a scalar.

- [x] 2.1 — In all 9 `config/synthetic/axes/models/ollama_*.yaml`: delete
      `model_config.base_url`; convert `parameters.parallel.workers` to the per-host map;
      preserve and extend each file's existing provenance comment.
- [x] 2.2 — `compose_manifest()` gains an `ollama_host_id: str | None` parameter. When the
      composed provider is `ollama` it resolves the host, sets `ManifestConfig.base_url`
      from it, and collapses `workers[host.id]` to the scalar `parallel_workers`.
      `ManifestConfig` keeps a **scalar** `parallel_workers` — no new field, no map
      downstream.
- [x] 2.3 — Availability gate lives here: raise if `host.id not in workers`, naming the
      model id, the host id and label, and the host ids that do have an entry.
- [x] 2.4 — Raise if `workers` is not a mapping (old scalar shape).
- [x] 2.5 — Add a non-raising query helper `workers_for_host(model_data, host_id) -> int |
      None` for the GUI summary panel, which needs to display rather than crash.
- [x] 2.6 — Comment the untouched file-manifest path at `manifest_loader.py:96` explaining
      why it keeps its scalar.
- [x] 2.7 — `OllamaClient.__init__`: make `base_url` a required parameter; delete
      `_DEFAULT_BASE_URL` (L22) and the env-var read (L45-49). Include the endpoint in the
      `_validate_server()` `ConnectionError` message.

**Files Modified:**
- `config/synthetic/axes/models/ollama_*.yaml` (9 files) — schema change
- `src/population_synthetic/generators/synthetic/manifest_loader.py` — host param, collapse, gate
- `src/population_synthetic/clients/ollama_client.py` — required `base_url`, fallbacks removed

**Dependencies:** Phase 1

### Phase 3: CLI and provenance
**Goal:** Scripts can select a host, and every run records which one it used.

- [x] 3.1 — `generate_identities_parallel.py`: add `--ollama-host` near `--base-url`
      (L250-254), `choices=ollama_hosts.host_ids()`, `default=None`; pass it into
      `compose_manifest()`.
- [x] 3.2 — An explicit `--base-url` still wins over the host's URL (documented escape
      hatch).
- [x] 3.3 — `--ollama-auto-workers` (L381-395) now reads the already-collapsed scalar
      `m.parallel_workers`; its behaviour is unchanged from the caller's point of view.
- [x] 3.4 — Warn (do not raise) when the resolved worker count exceeds the host's
      `server_num_parallel`: requests will queue rather than batch. It is an unverifiable
      declared value, so it must not gate a run.
- [x] 3.5 — Stamp `ollama_host` and the resolved `base_url` into `run_metadata.json` beside
      the existing `workers` / `ollama_auto_workers` keys (L469-470), and into
      `manifest_snapshot.yaml`. Without this, wall-clock and latency figures from two GPUs
      pool indistinguishably in the `generation_metadata` analysis and provenance is
      unrecoverable after the fact.
- [x] 3.6 — Same flag and resolution in `generate_identity.py` (Ollama branch L258-260).

**Files Modified:**
- `scripts/generate/generate_identities_parallel.py` — flag, resolution, warning, provenance
- `scripts/generate/generate_identity.py` — flag, resolution

**Dependencies:** Phase 2

### Phase 4: GUI dropdown
**Goal:** Host selection from the Flow Runner, config-sourced.

- [x] 4.1 — `config/gui/flows/generate_parallel.yaml`: add `ollama-host: linux_3060` under
      `options:`. Required — `FlowConfigModel.set_option` (`flow_config_model.py:109-115`)
      raises on keys absent from the YAML, so the Python table alone renders nothing.
- [x] 4.2 — `flow_options_panel.py`: add `_populate_ollama_host_enum()` alongside
      `_populate_judge_model_enum()` (L75-105), filling `_OPTION_ENUMS["ollama-host"]` with
      `(host.label, host.id)` pairs from the registry. Keep that function's contract
      verbatim: log a warning on any read/parse failure, leave the key out of the table so
      the row degrades to free text, **never raise at import**.
- [x] 4.3 — No `("(default)", None)` sentinel: with the fallbacks gone there is no implicit
      default, and an explicit host on every run is the point.
- [x] 4.4 — `_OPTION_LABELS["ollama-host"] = "Ollama Host"`.
- [x] 4.5 — `population_summary.py`: the "Workers" column (L35, L123) uses
      `workers_for_host()` with the flow's current `ollama-host` value, rendering an em dash
      when the model has no entry for that host.
- [x] 4.6 — No change to `commands.py` or `execution.py`: `_option_args` (L41-50) and
      `CombinationRunner` (`execution.py:100-114`) already translate any option key to
      `--key value`.

**Files Modified:**
- `config/gui/flows/generate_parallel.yaml` — new option key
- `src/population_synthetic/gui/widgets/flow_options_panel.py` — enum populator, label
- `src/population_synthetic/gui/widgets/population_summary.py` — host-aware Workers column

**Dependencies:** Phase 3

---

## Testing Plan

### Unit Tests

- [x] `tests/test_ollama_hosts.py` — `load_hosts` raises on: missing file, malformed YAML,
      empty `hosts`, a host missing `base_url`, a host missing `label`. (Also: non-mapping
      root, non-mapping host entry, missing `gpu` / `server_num_parallel`, and a
      non-positive-int `server_num_parallel` including the `bool` trap.)
- [x] `resolve_host(None)` returns the `default_host` entry.
- [x] `resolve_host("nope")` raises and the message lists both valid ids.
- [x] `host_ids()` order is stable (drives argparse `choices` and dropdown order).
- [x] `OllamaClient(model_name="x")` with no `base_url` raises `TypeError`.
      (`tests/test_ollama_client_endpoint.py`.)
- [x] `OllamaClient` with `OLLAMA_BASE_URL` set in a monkeypatched environment still raises —
      the env read is gone. (No test asserted the old default; nothing needed replacing. An
      AST-level test additionally asserts no `_DEFAULT_BASE_URL`, no endpoint literal and no
      `os` import survive in the client module, since both removed tiers were *silent*
      fallbacks a behavioural test cannot observe.)
- [x] Table-driven collapse test: `(model_id, host_id) -> expected int` across all 9 axes x
      both hosts, including the unsupported cells. (`tests/test_ollama_host_composition.py`;
      the expected table sits at the top of the module, and a guard asserts it stays
      exhaustive against the axis files on disk and the registry's host ids.)
- [x] `compose_manifest` raises when `workers` is a scalar (old shape).
- [x] `workers_for_host()` returns `None` rather than raising for an unsupported pair
      (asserted on every one of the 18 cells), while still raising on a malformed shape.

### Integration Tests

- [x] `compose_manifest("ollama_deepseek_r1_14b", ..., ollama_host_id="windows_4070tis")`
      yields `base_url == "http://localhost:11434"` and a scalar `parallel_workers`.
- [x] `compose_manifest("ollama_llama33_70b", ..., ollama_host_id="windows_4070tis")` raises
      and the message contains both `ollama_llama33_70b` and `linux_3060`.
- [x] `tests/test_flow_options_panel_enum.py` — extend with the `ollama-host` case mirroring
      the existing `judge-model` assertions: config-sourced label/id pairs, no `(default)`
      sentinel, `option_widget_kind("ollama-host", "linux_3060") == "enum"`, label override.
- [x] Command-builder test: an `ollama-host` option produces `--ollama-host <id>` in the
      arg vector. (`tests/test_workflow_commands.py`.)

### Manual Verification

- [ ] Both endpoints answer `curl.exe -s http://localhost:11434/api/tags` and
      `curl.exe -s http://192.168.0.19:11434/api/tags`.
- [ ] Availability gate fires with no persona directory created:
      `python scripts/generate/generate_identities_parallel.py --model-id ollama_llama33_70b
      --strategy-id all_pick --country-id swedish_02 --ollama-host windows_4070tis --n 1`
- [ ] Small end-to-end run on the new host, then inspect `run_metadata.json` and
      `manifest_snapshot.yaml` for `ollama_host: windows_4070tis`, its `base_url`, and the
      resolved `workers`:
      `... --model-id ollama_deepseek_r1_14b --strategy-id all_pick --country-id swedish_02
      --ollama-host windows_4070tis --ollama-auto-workers --n 4`
- [ ] GUI: `python -m population_synthetic.gui.main` → *Generate → LLM Synthetic
      Population*. The **Ollama Host** dropdown lists both labels; switching it updates the
      Population Summary "Workers" column; the choice round-trips through Save into
      `config/gui/flows/generate_parallel.yaml`; the console shows `--ollama-host <id>`.
- [ ] Same-weights sanity check: one persona per host with `ollama_deepseek_r1_14b`; both
      valid, since the two hosts' weights are digest-identical.
- [ ] Extension check: add a throwaway third host to the registry, confirm it appears in the
      dropdown and in `--help` choices with no Python edit, then revert.

### Edge Cases

- [x] Registry file present but `hosts:` empty → raise naming the file.
- [x] `default_host` names a host absent from `hosts:` → raise at load, not at use.
- [x] Axis file lists a host id that is not in the registry → raise at composition.
      **Coverage boundary:** an axis whose worker map declares *only* unregistered ids raises
      for every selectable host (tested). A *stray extra* unregistered key alongside a valid
      one is invisible to composition — the gate only checks that the selected host is
      present — so that case is caught instead by a repo-wide test asserting every worker-map
      key across all 9 axis files is a registered host id. See Residual risk below.
- [ ] Resolved workers > `server_num_parallel` → warning logged, run proceeds.
      **Not automated:** the warning is emitted inline in
      `generate_identities_parallel.py::main`, not in an importable helper, so asserting it
      would require either extracting a function (production change, out of scope for the
      test pass) or a live run. Manual verification only.
- [x] Non-Ollama provider with `--ollama-host` supplied → the flag is inert; composition
      must not attempt host resolution for `gemini` / `claude` / `openrouter`. (Asserted for
      `claude_sonnet`, `gemini_flash`, `openrouter_gpt55`, including with an *unregistered*
      host id that would raise if it were resolved.)
- [x] Selected host unreachable → `ConnectionError` at client construction naming the
      endpoint. (Transport error injected through a monkeypatched `requests.Session.get`; no
      network access.)

---

## Documentation Plan

- [x] `docs/architecture/configuration.md` — register `config/synthetic/ollama_hosts.yaml`.
      (Done in Phase 1; verified present and accurate.)
- [x] `docs/architecture/axis-composition.md` — the changed
      `parameters.parallel.workers` shape and the removal of `model_config.base_url`.
      (New "Ollama model axes: per-host workers, no `base_url`" section with the fail-fast
      table and the `workers_for_host` twin.)
- [x] `docs/development/gui.md` — note `ollama-host` as the second config-sourced enum in
      the "Two-tier config" section. (Table of both config-sourced enums, the
      no-sentinel rationale, the shared degrade-gracefully contract, and the config-only
      extension path.)
- [x] `docs/ollama_server_models.md` — currently asserts a single server at L3; document
      both hosts and which models each holds. (Rewritten: host registry table, the full
      9 x 2 availability/worker matrix with provenance for both columns, the 4070 Ti SUPER
      KV/slot + spill table, host-selection examples, and the add-a-host recipe. The older
      non-axis Linux inventory is preserved in a clearly-labelled subsection.)
- [x] `CLAUDE.md` — Environment & Secrets currently says Ollama needs no key; add that the
      endpoint is selected via `--ollama-host` from the registry.
- [x] Inline: the `server_num_parallel` comment block in the registry, and the untouched
      file-manifest path comment in `manifest_loader.py`. (The Windows entry additionally
      records that its per-model VRAM ceilings now far exceed its `NUM_PARALLEL=1`, so the
      queueing warning fires by design until the container is retuned.)

---

## Rollback Plan

1. **Before merge:** the work is one feature branch; `git checkout dev` discards it.
2. **Data considerations:** no migrations and no stored state. Existing outputs under
   `01_Raw` are unaffected — the new provenance keys are additive to
   `run_metadata.json` / `manifest_snapshot.yaml`, and readers of those files
   (`generation_metadata`) ignore unknown keys.
3. **Breaking changes to revert, in order:**
   - The axis-file schema (scalar → map) is the only breaking change. Reverting the 9 YAML
     files restores the old shape; they must be reverted together with
     `manifest_loader.py` or composition fails.
   - `git revert` the client commit to restore `_DEFAULT_BASE_URL` and the env read.
   - Remove `ollama-host` from `config/gui/flows/generate_parallel.yaml` — leaving it with
     the Python table gone would trip `FlowConfigModel`'s unknown-key guard.
4. **Partial rollback is available:** Phase 4 (GUI) can be reverted alone, leaving the CLI
   flag working.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| A stale scalar `workers:` survives in one of the 9 axis files | Med | High — silent wrong concurrency | `compose_manifest` raises on non-mapping `workers`; table-driven test covers all 9 x 2 |
| `server_num_parallel` is mistaken for a worker count in later work | Med | High — the RESULTS.md-era error | Field name is not `num_parallel`; a comment in the registry and a Definitions entry state it is warning-only; it is never read into any worker variable |
| Windows host stays at `NUM_PARALLEL=1`, feature looks broken | High | Low | Warning at 3.4 says requests will queue; Out of Scope states this explicitly |
| Removing the `OLLAMA_BASE_URL` env read breaks an unnoticed workflow | Low | Med | `--base-url` remains as the explicit override; the change is called out in the plan and the CLAUDE.md doc update |
| GUI enum populator raises at import and breaks the whole GUI | Low | High | Copy `_populate_judge_model_enum`'s degrade-gracefully contract verbatim; unit-test the failure path |
| `--ollama-host` silently ignored for non-Ollama providers confuses a user | Low | Low | Host resolution is inside the `provider == "ollama"` branch; edge-case test asserts inertness |
| GUI summary panel crashes on an unsupported (host, model) cell | Med | Med | `workers_for_host()` returns `None` instead of raising; panel renders an em dash |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — Registry and accessor | ~1 file + ~80 LOC + tests | None |
| Phase 2 — Schema change and normalization | 9 YAML edits + ~60 LOC across 2 modules | Phase 1 |
| Phase 3 — CLI and provenance | ~40 LOC across 2 scripts | Phase 2 |
| Phase 4 — GUI dropdown | ~40 LOC + 1 YAML key | Phase 3 |

---

## References

- Home-lab notes: `docs/ollama/windows-local-stack-usage.md` (external repo) — the new
  host's architecture, env vars, installed models, and endpoint comparison table.
- `docs/development/ollama-parallelism-poc/REPORT.md` — provenance of the `linux_3060`
  worker values. Note it **supersedes** `RESULTS.md` in the same directory; do not cite the
  latter.
- `docs/development/ollama-parallelism-server-report.md` — the `:11435` control API, absent
  on the Windows host.
- `docs/development/plans/completed/composable-experiment-config.md` — explicit
  field-by-field composition table (the `parallel_workers` and `base_url` source rules).
- `docs/development/plans/completed/add-ollama-client.md` — the URL precedence chain this
  plan collapses.
- `docs/development/plans/completed/openai-compat-european-providers.md` — precedent against
  per-endpoint client subclasses.
- `docs/development/gui.md` — the GUI-translates-YAML→CLI execution contract.

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- CLAUDE.md
- config/gui/flows/generate_parallel.yaml
- config/synthetic/axes/models/ollama_deepseek_r1_14b.yaml
- config/synthetic/axes/models/ollama_gemma2_9b.yaml
- config/synthetic/axes/models/ollama_gemma4_e4b.yaml
- config/synthetic/axes/models/ollama_llama31_8b.yaml
- config/synthetic/axes/models/ollama_llama32_3b.yaml
- config/synthetic/axes/models/ollama_llama33_70b.yaml
- config/synthetic/axes/models/ollama_lucie_7b.yaml
- config/synthetic/axes/models/ollama_mistral_nemo_12b.yaml
- config/synthetic/axes/models/ollama_qwen3_14b.yaml
- config/synthetic/manifests/template_identity_manifest.yaml
- config/synthetic/ollama_hosts.yaml
- docs/architecture/axis-composition.md
- docs/architecture/configuration.md
- docs/development/gui.md
- docs/development/plans/active/selectable-ollama-host.md
- docs/ollama_server_models.md
- scripts/generate/generate_identities_parallel.py
- scripts/generate/generate_identity.py
- src/population_synthetic/clients/ollama_client.py
- src/population_synthetic/generators/synthetic/manifest_loader.py
- src/population_synthetic/generators/synthetic/ollama_hosts.py
- src/population_synthetic/gui/main_window.py
- src/population_synthetic/gui/widgets/flow_options_panel.py
- src/population_synthetic/gui/widgets/population_summary.py
- tests/test_flow_options_panel_enum.py
- tests/test_ollama_client_endpoint.py
- tests/test_ollama_host_composition.py
- tests/test_ollama_hosts.py
- tests/test_workflow_commands.py
