# Plan: Synthetic Population Object Model & Crash-Safe Persistence

**Date:** 2026-07-29
**Author:** Basil
**Status:** In Progress
**Base Branch:** `dev`
**Branch:** `feature/synthetic-population-object-model`

---

## Overview

Replace the flat `resolved: dict` accumulator and runner-owned file writes inside
`IdentityGeneratorConfigurable` with a small domain object graph —
`SyntheticPopulation` → `Persona` → `Category` (polymorphic per generation method) +
`PersonaWriter`. The writer owns every file belonging to one persona and their shared
lifecycle, which makes per-category incremental persistence structural rather than a
convention, so an aborted run no longer discards the categories a persona has already paid for.

## Problem Statement

Three defects, in descending severity.

**1. Non-atomic writes behind an exists-only resume gate (silent corruption).**
`scripts/generate/generate_identities_parallel.py:220-222` writes `identity.json` with a plain
`open(..., "w")` + `json.dump` — no tmp+replace, no fsync. The resume gate at `:147-150` is
`if not force and out_file.exists()`. The GUI's Abort issues `taskkill /F /T`
(`gui/execution.py:37-59`), so a kill mid-`json.dump` leaves a truncated `identity.json` that
the gate then treats as complete **forever**. Only `validate_raw` catches it, and only as
`"<unreadable>"`; recovery requires a full `--force` rerun of the combo.

**2. The in-flight persona is all-or-nothing.**
`identity_generator_configurable.py:765-808` walks 14–17 categories, accumulating into a
method-local `resolved` dict, and re-raises on the first failing category (`:800-805`). The dict
is garbage the instant the exception propagates. Every category already resolved — and every LLM
call already paid for — is lost. At `--workers N`, an abort discards up to N partial personas.
The existing log line already reports exactly what is thrown away:
`"failed after resolving %d/%d categories"`.

**3. Retry rounds destroy telemetry, and appending naively would corrupt it.**
`LLMInteractionCollector._ensure_open` opens mode `"w"` (`llm_interaction_log.py:59`), and the
runner passes `force=True` on every retry round (`generate_identities_parallel.py:840`), so a
retry discards the failed attempt's token/latency records. Reported cost therefore
**under-counts actual spend**. But the naive fix (open `"a"`) is worse: `persona_id` +
`call_index` are the correlation keys joining this file to the shared run log, `_call_index`
restarts at 0 on a fresh generator instance, and `generation_metadata` **sums records without
deduping** — so appending across rounds silently inflates cost, retry counts and latency
percentiles.

Structurally, all three trace to the same cause: **no object owns a persona's files.** The
identity write lives in the runner, the telemetry write lives in a collector injected by the
runner, and nothing owns the relationship between them.

Secondarily, the per-category dispatch is an `if/elif` chain over a `method` string
(`identity_generator_configurable.py:779-799`) with four `_process_*` methods on one class.
The five generation methods are the primary comparison axis of the manuscript, yet none is
independently constructible or testable.

## Goals

### In Scope

1. A shared atomic-write helper, used by all new durable writes.
2. `PersonaWriter` — one object owning `identity.json`, `identity.partial.json` and
   `llm_interactions.jsonl` for one persona, and enforcing their shared lifecycle.
3. Per-category checkpointing with a fingerprint, so an interrupted persona resumes from its
   last resolved category.
4. A content-validating resume gate replacing the exists-only check.
5. Splitting the fused `force` flag into "bypass the identity skip" (retry rounds) vs
   "discard the checkpoint" (`--force` only).
6. `Category` ABC with one subclass per generation method, replacing the `if/elif` dispatch.
7. `Persona` — owns its ordered categories, context mode, and writer.
8. `SyntheticPopulation` — passive collection + resume policy, owned by
   `IdentityGeneratorConfigurable`.
9. Minimal test coverage for `BaseIdentityGenerator` / `FactoryIdentityGenerator`, which
   currently have none.

### Out of Scope

- **Signal handling / graceful drain.** Explicitly rejected: the design assumes the process can
  die at any instruction. A SIGINT handler cannot help against `taskkill /F` or power loss, and
  would create a second, weaker recovery path.
- **Sub-category resume.** Resuming *within* a category (e.g. after `enumerate`, before
  `evaluate`) requires persisting the `candidates`/`weights` locals. Not attempted.
- **Migrating the two existing atomic-write call sites** (`analysis/persona_realism/runner.py:434`,
  `gui/flow_config_model.py:184`) onto the new helper. `runner.py:434` has a real latent bug
  (predictable `.tmp` name, no cleanup on failure), but it is in a tested subsystem and deserves
  its own change.
- **Moving parallelism into `SyntheticPopulation`.** The runner keeps its `ThreadPoolExecutor`.
- **Any change to the real-population half** (`generators/real/`). It has no partial state to lose.
- **Reproducibility/seeding of generation.** See Definitions — generation is currently unseeded,
  and this plan does not change that.

## Success Criteria

- [ ] A `taskkill /F /T` mid-run, followed by a plain re-run of the same command, completes the
      run and produces personas whose `identity.json` files are all parseable and complete.
- [ ] After such a kill+resume, no persona directory contains an `identity.partial.json`.
- [ ] After such a kill+resume, every `llm_interactions.jsonl` has unique
      `(persona_id, call_index)` pairs.
- [x] A persona interrupted after resolving K categories re-runs at most one category's worth of
      LLM calls, not K+1.
- [x] A truncated/zero-byte `identity.json` is detected and regenerated on the next run without
      `--force`.
- [x] `_build_dag` output is byte-identical to pre-refactor for all 10 selectable strategies;
      `tests/test_identity_generator_configurable.py:320` passes **unmodified**.
- [ ] For every strategy, a resumed persona's prompt for category K is byte-identical to the
      prompt an uninterrupted run would have produced. *(Asserted for `all_pick_dag`
      (`context: cumulative`) and `all_pick` (`context: none`); not yet swept over all 10.)*
- [x] `identity.json` remains a flat single-level object; no nesting is introduced.
- [x] Each of the four `Category` subclasses is constructible and testable without a live client.
- [x] `ruff check src/` clean; full `pytest` green.

## Definitions

These terms are load-bearing; implementation must not drift on interpretation.

- **Complete persona (generation-side):** `identity.json` parses as JSON, is a flat object, and
  every key in this run's `resolved_category_order` is present and non-empty. This is
  deliberately a *different* predicate from `validate_raw`'s, which derives expected keys from
  the country's mapping `_index.json`. They are safe to keep separate because
  `_assert_strategy_covers_country` (`generate_identities_parallel.py:355-387`) already
  guarantees **strategy categories ⊇ country required keys**, so a persona complete under the
  generation predicate is necessarily complete under `validate_raw`'s. Generation's gate is the
  stricter of the two. Do not "unify" them without re-establishing that containment.

- **Valid checkpoint:** `identity.partial.json` parses, its `schema_version` matches, and its
  `fingerprint` block equals the current run's fingerprint. Any other state — unparseable,
  truncated, wrong version, mismatched fingerprint — is *discarded*, not repaired, and logged at
  WARNING. Parse failure and fingerprint mismatch are different facts and get different log
  messages.

- **Fingerprint:** `{strategy_sha256, schema_sha256, model_key, category_order}` where the two
  hashes are over the file bytes of the strategy YAML and the simulation-config JSON, and
  `model_key` is `f"{provider}:{model}"`. Derived from existing identifiers
  (`serialize_manifest`, `axis_ids`) rather than a new config-identity scheme.

- **Shared lifecycle (the central invariant):** `llm_interactions.jsonl` is truncated **if and
  only if** the checkpoint is discarded. Resume → JSONL opens `"a"` *and* `call_index` continues
  from the checkpoint. Fresh start → JSONL truncates *and* `call_index` starts at 0. This is
  what keeps `(persona_id, call_index)` unique without asking any downstream consumer to dedupe.

- **Resume-faithful:** category K's rendered prompt after resume is byte-identical to the prompt
  an uninterrupted run would have produced. Provable because
  `_build_context_block` (`identity_generator_configurable.py:347-350`) is a pure function of
  `resolved`'s **contents and insertion order**, and the checkpoint restores both. Consequence:
  the checkpoint must never be written with `sort_keys=True`.

- **NOT determinism.** Resume-faithful is *not* reproducibility. Generation is unseeded: the
  path uses global `np.random.*` (`:675,680,682`) and `random.choices` (`:729`), and there is no
  `seed`/`default_rng` anywhere in `src/` generation or `scripts/generate/`. Two runs of the same
  config already differ. Resume does not make this worse and does not need to checkpoint RNG
  state — but nobody should later assume resume guarantees bit-identical output.

---

## Technical Design

### Approach

Introduce the object graph in three shippable stages, keeping `generate_identity()`'s external
signature stable until the final stage. Stage 1 delivers the crash-safety fix on its own,
against the existing flat `resolved` dict — so the highest-severity defect ships without waiting
for the refactor. Stages 2 and 3 then move behaviour into the new classes with the persistence
contract already in place and already tested.

```
IdentityGeneratorConfigurable      strategy/schema loading, DAG build, client ownership
  └── SyntheticPopulation          persona set + resume policy (passive; no thread pool)
        └── Persona                ordered Category[], context mode, writer
              ├── Category (ABC)   one subclass per generation method
              │     ├── PickCategory
              │     ├── GeneratePickCategory
              │     ├── GenerateEvaluatePickCategory
              │     └── GenerateEvaluateRandomPickCategory
              └── PersonaWriter    identity.json + identity.partial.json + llm_interactions.jsonl
```

`ResolutionContext` is the seam that keeps `Category` ignorant of both the client and the
filesystem: it wraps `_call_llm_json` (currently `identity_generator_configurable.py:262-345`)
together with the correlation counter and the telemetry sink, exposing a single
`call_json(prompt, *, category, method, step)`.

Parallelism is unchanged: the runner keeps its `ThreadPoolExecutor` and continues to build one
client + one generator per worker thread. This preserves the property that
`ClaudeCodeClient`'s persistent subprocess and reader thread are never shared, and keeps
`_call_index` per-persona by construction.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **Checkpoint: atomic full rewrite of a small JSON** | File on disk is always complete and valid; no torn tail to reason about; one durability path for everything; matches the pipeline guides' "overwrite, don't append" rule for authoritative state | ~17 tmp+replace ops per persona (negligible for a <2 KB file) | **Chosen** |
| Checkpoint: append-only JSONL | Cheaper per write; mirrors the existing `llm_interaction_log` idiom | Reader must detect and drop torn trailing lines and reconstruct order; puts *authoritative* state in an append log, which the guides advise against | Rejected |
| Whole-persona-only durability (atomic write, no checkpoint) | Much smaller change; fixes the corruption defect alone | Leaves defect 2 entirely — an abort still discards every category the in-flight personas resolved | Rejected |
| `Category` as a passive dataclass | Minimal diff; no behaviour risk to the five methods | Keeps the `if/elif` chain and four `_process_*` methods on one class; the five methods stay individually unconstructible, which is the axis the manuscript compares | Rejected |
| `SyntheticPopulation` owns the thread pool | Cleaner domain model; runner shrinks to arg-parsing | Client-per-worker allocation must move inside it; one generator instance would span threads, so `_call_index` and client state stop being per-persona by construction | Rejected |
| Signal handler / graceful drain | Lets in-flight personas finish on Ctrl-C | Cannot help against the GUI's `taskkill /F /T`, nor power loss; creates a second, weaker recovery path alongside the kill-safe one | Rejected |
| Reuse `validate_raw`'s completeness predicate in the resume gate | One definition of "complete" | Inverts pipeline layering (generation would import from the downstream analysis half); the two derive expected keys from different config sources | Rejected — see Definitions for the containment argument |
| Transport-level retry only (status quo, per `ensure-n-generation.md`) | Already implemented; rides out flaky endpoints inside the client | Does nothing for a killed process, which is the case in question | Insufficient — retained, but complemented |

### Prior decisions this reverses or extends

- **`ensure-n-generation.md`** deliberately chose `force=True` on retry rounds *"to ensure
  regeneration regardless of any partial artifacts from previous failed attempts"* — live at
  `generate_identities_parallel.py:840`. This plan **reverses** that for the checkpoint
  specifically: a retry round now bypasses the `identity.json` skip but **keeps** the checkpoint.
  `--force` remains a full discard.
- **`force-processing-analysis-tasks.md`** establishes force as batch-wide, not per-unit, and
  warns against new resume-flag vocabulary. Honoured: **no `--resume` flag is added**; `--force`
  stays the only escape hatch.
- **`enrich-persona-generation-telemetry.md`** establishes `llm_interactions.jsonl` as the
  crash-safe source of truth for per-call telemetry, with `persona_id` + `call_index` as
  correlation keys and new fields required to be optional/defaulted. Honoured by the shared
  lifecycle invariant; no field is removed or made mandatory.
- **`cap-population-to-n.md`** — persona dirs are copied wholesale into the capped mirror.
  Because the checkpoint is deleted on success, a complete persona has no extra file to copy, so
  the mirror is unaffected. This is a second, independent reason to delete rather than retain.
- **`remove-sequential-identity-system.md`** removed a *generation strategy*, not a persistence
  mechanism ("no migrations, no schema changes, no stored state"). Nothing here resurrects it.
  Its residual constraint — keep `identity.json` flat, never reintroduce a nested shape — is
  carried into Success Criteria.

### Architecture & Module Contracts

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `utils/atomic_io.py` | Durable overwrite of one file | `(path, text\|obj)` → file replaced atomically | JSON schemas, personas, the pipeline |
| `generators/synthetic/persona_writer.py::PersonaWriter` | Every file for **one** persona and their shared lifecycle | resolved values + telemetry entries → `identity.json`, `identity.partial.json`, `llm_interactions.jsonl` | Strategies, methods, prompts, the DAG, other personas |
| `generators/synthetic/category.py::Category` (ABC) | Resolve **one** attribute via **one** method | rendered context + `ResolutionContext` → scalar | Paths, persona dirs, file IO, other categories, `resolved` |
| `generators/synthetic/resolution_context.py::ResolutionContext` | One LLM call: retry budget, correlation, telemetry emission | prompt → parsed JSON value | Category semantics, prompts' meaning, output paths |
| `generators/synthetic/persona.py::Persona` | Walk categories in DAG order, accumulate values, checkpoint after each | category list + context mode → flat `dict[str, str\|int\|float]` | Paths, slugs, `output_base`, serialization format |
| `generators/synthetic/synthetic_population.py::SyntheticPopulation` | The persona set and which members need work | `n`, resume state → pending indices, `Persona` by index | Threading, prompts, LLM methods, file formats |
| `IdentityGeneratorConfigurable` | Strategy/schema loading, DAG build, client ownership, wiring | config paths → `SyntheticPopulation` | Per-category prompt construction (moves to `Category`) |

Sketch of the two contracts that carry the most weight:

```python
# persona_writer.py
class PersonaWriter:
    def __init__(self, persona_dir: Path, fingerprint: dict, *, discard: bool = False) -> None: ...
    def resume(self) -> ResumeState | None:
        """Valid checkpoint -> (resolved, call_index); else None. Never raises on a
        corrupt checkpoint -- discards it and logs. Sets telemetry append/truncate mode."""
    def checkpoint(self, resolved: dict, call_index: int) -> None:
        """Atomic rewrite of identity.partial.json. Never sort_keys."""
    @property
    def telemetry(self) -> LLMInteractionCollector: ...
    def finalize(self, resolved: dict) -> None:
        """Atomic write of identity.json, THEN unlink the partial. Order is load-bearing."""
    def close(self) -> None: ...

# category.py
class Category(ABC):
    name: str
    schema: dict
    depends_on: tuple[str, ...]

    @abstractmethod
    def resolve(self, context: str, ctx: ResolutionContext) -> str | int | float: ...
```

**Ordering constraints (connascence of execution order — comment the *why* at each site):**

1. `tmp.write()` → `flush()` → `fsync()` → `os.replace()`. Never reorder.
2. Temp filenames must be per-worker unique (`mkstemp` in the target dir), never a predictable
   `<name>.tmp` — the runner is parallel.
3. `checkpoint()` is written **after** the category's value is in `resolved`, never before.
4. `finalize()` writes `identity.json` **before** unlinking the partial. A crash between the two
   leaves both files; the next run's gate sees a valid `identity.json`, skips, and cleans the
   stale partial.
5. `resume()` must set the telemetry append/truncate mode **before** the first `record()`.

**Method→class registry.** `_METHOD_MAP: dict[str, type[Category]]` is a structural constant
(same category as dataset ids and label maps), not config data. An unknown `method` string must
raise **before** the resolution loop starts — today it fires only when the loop reaches the
offending category (`:796-799`), which under resume would fail again on every retry.

---

## Implementation Plan

### Phase 1: Durable persistence (ships crash-safety alone)
**Goal:** Kill-safety and per-category checkpointing, against the existing flat `resolved` dict.
No domain classes yet.

**Started:** 2026-08-01
**Completed:** 2026-08-01

- [x] 1.1 — Add `src/population_synthetic/utils/atomic_io.py`: `atomic_write_text`,
      `atomic_write_json`. `mkstemp` in the target directory, `flush` + `fsync`, `os.replace`,
      `unlink(missing_ok=True)` on `BaseException`. Export from `utils/__init__.py`.
- [x] 1.2 — Add `generators/synthetic/persona_writer.py` with `PersonaWriter` and the
      `ResumeState` DTO, per the contract above. Compose (do not replace)
      `LLMInteractionCollector`, so `LLMInteractionEntry`'s schema is untouched.
- [x] 1.3 — Add append-mode support to `LLMInteractionCollector` — an `append: bool = False`
      constructor arg selecting the `_ensure_open` mode. Fold
      `analysis/persona_realism/runner.py:98` `_AppendingCollector` onto it in the same commit,
      or leave it and note the duplication explicitly. *(Folded — `_AppendingCollector` is
      deleted and `_flush_telemetry` now passes `append=` to the shared collector.)*
- [x] 1.4 — Compute the fingerprint in the runner (both hashes + `model_key` + category order)
      and pass it to each `PersonaWriter`. *(Built by
      `generators/synthetic/run_fingerprint.py::build_run_fingerprint`, a new module so both
      entry-point scripts share one definition and `PersonaWriter` stays strategy-agnostic.)*
- [x] 1.5 — Inject the writer into the generator by attribute assignment beside
      `interaction_collector` (`generate_identities_parallel.py:213-216`); close it in the same
      `finally` (`:237-243`). *(The collector now comes from `writer.telemetry`, so the writer
      owns the handle and `writer.close()` closes it.)*
- [x] 1.6 — In `generate_identity()`: pre-seed `resolved` and `self._call_index` from
      `writer.resume()`, filter `ordered_categories` to the unresolved tail, and call
      `writer.checkpoint(...)` immediately after `resolved[category_name] = value` (`:807`).
- [x] 1.7 — Replace the write at `:220-222` with `writer.finalize(...)`.
- [x] 1.8 — Replace the exists-only gate at `:147-150` with the content-validating predicate
      (parse + flat + all `resolved_category_order` keys present and non-empty).
- [x] 1.9 — Split the fused flag at `:840`: `bypass_identity_skip` (true on retry rounds) vs
      `discard_checkpoint` (true only for `args.force`). Update `_generate_one`'s signature.
- [x] 1.10 — Write `run_metadata.json` via `atomic_write_json` at both sites (`:802-805`, `:880-881`).

**Files Modified:**
- `src/population_synthetic/utils/atomic_io.py` — new
- `src/population_synthetic/utils/__init__.py` — export the helpers
- `src/population_synthetic/generators/synthetic/persona_writer.py` — new
- `src/population_synthetic/generators/synthetic/run_fingerprint.py` — new (fingerprint builder,
  shared by both entry-point scripts)
- `src/population_synthetic/generators/synthetic/llm_interaction_log.py` — `append` mode
- `src/population_synthetic/analysis/persona_realism/runner.py` — `_AppendingCollector` folded away
- `src/population_synthetic/generators/synthetic/base_identity_generator.py` — `writer` slot
- `src/population_synthetic/generators/synthetic/identity_generator_configurable.py` — resume pre-seed, per-category checkpoint call
- `scripts/generate/generate_identities_parallel.py` — fingerprint, writer injection, gate, force split, atomic run metadata
- `scripts/generate/generate_identity.py` — same injection on the single-persona path

**Dependencies:** None

### Phase 2: `Persona` and polymorphic `Category`
**Goal:** Replace the `if/elif` dispatch with a class per generation method, and move the
category walk onto `Persona`. `generate_identity()`'s signature stays stable.

**Started:** 2026-08-01
**Completed:** 2026-08-01

- [x] 2.1 — Add `resolution_context.py::ResolutionContext`; move `_call_llm_json`
      (`:262-345`) onto it along with `_call_index` and the telemetry emission.
      *(`_extract_json` / `_extract_expected_key` travelled with it as module-level
      helpers; the counter is exposed read-only plus a `resume_from()` setter.)*
- [x] 2.2 — Add `category.py`: `Category` ABC + `PickCategory`, `GeneratePickCategory`,
      `GenerateEvaluatePickCategory`, `GenerateEvaluateRandomPickCategory`. Move the four
      `_process_*` bodies (`:544-729`) and their prompt builders (`:401-485`) onto them verbatim.
      *(Two non-public intermediates — `_CandidateCategory` for the enumerate step,
      `_WeightedCategory` for the evaluate loop — hold what the subclasses share.)*
- [x] 2.3 — Add `_METHOD_MAP` and validate **every** category's method at build time, before
      resolution starts.
- [x] 2.4 — Add `persona.py::Persona`: holds ordered categories, context mode, writer; owns the
      walk, `_build_context_block`, and the per-category `writer.checkpoint(...)` call.
      *(`_resume_prefix` moved here too — it is part of the walk.)*
- [x] 2.5 — Reduce `IdentityGeneratorConfigurable.generate_identity()` to: build categories from
      config → construct `Persona` → `persona.generate(ctx)` → return `(resolved, {})`.
- [x] 2.6 — Move the weight-reconcile helper (`_reconcile_weight_count`, `:510-542`) to wherever
      its two callers land. *(Module-level in `category.py` with `_normalize_weights` and
      `_candidate_probabilities`; all three are pure functions of their arguments.)*

**Files Modified:**
- `src/population_synthetic/generators/synthetic/resolution_context.py` — new
- `src/population_synthetic/generators/synthetic/category.py` — new
- `src/population_synthetic/generators/synthetic/persona.py` — new
- `src/population_synthetic/generators/synthetic/identity_generator_configurable.py` — large reduction
- `tests/test_category.py`, `tests/test_persona.py`, `tests/test_prompt_stability.py` — new
- `tests/test_identity_generator_configurable.py`, `tests/test_identity_generator_resume.py` —
  their test doubles move from the old `_call_llm_json` seam to `ResolutionContext`

**Dependencies:** Phase 1

### Phase 3: `SyntheticPopulation` and runner rewiring
**Goal:** Give the persona set a home and move the resume policy out of the runner's loop body.

- [ ] 3.1 — Add `synthetic_population.py::SyntheticPopulation`: constructed from `(n, output_dir,
      fingerprint, category blueprint)`; exposes `pending_indices(force=...)` and
      `persona(index) -> Persona`. Passive — no threading.
- [ ] 3.2 — `IdentityGeneratorConfigurable` builds and owns the `SyntheticPopulation`.
- [ ] 3.3 — Rewire `generate_identities_parallel.py`: the runner keeps its `ThreadPoolExecutor`
      and per-worker client/generator construction, but asks the population for the pending set
      and for `Persona` objects instead of open-coding the skip logic.
- [ ] 3.4 — Record `resumed: true` plus the resumed/skipped index counts in `run_metadata.json`,
      so a resumed run is distinguishable from a clean one.

**Files Modified:**
- `src/population_synthetic/generators/synthetic/synthetic_population.py` — new
- `src/population_synthetic/generators/synthetic/identity_generator_configurable.py` — owns the population
- `scripts/generate/generate_identities_parallel.py` — loop body delegates to the population

**Dependencies:** Phase 2

---

## Testing Plan

### Unit Tests
- [x] `atomic_write_json` leaves no `.tmp` residue when the serializer raises mid-write.
- [x] Concurrent `atomic_write_json` to the *same* path from N threads yields a valid file
      (no interleaved temp-name collision).
- [x] `PersonaWriter.resume()` on: absent / zero-byte / truncated / stale-fingerprint / wrong
      `schema_version` / valid checkpoint — returns `None` for the first five, state for the last.
- [x] Parse failure and fingerprint mismatch produce *different* log messages.
- [x] `finalize()` removes the partial; a pre-existing stale partial next to a valid
      `identity.json` is cleaned on the next run.
- [x] Checkpoint round-trip preserves **key insertion order** (guards the `sort_keys` trap).
- [x] Each of the four `Category` subclasses resolves against a fake `ResolutionContext` with no
      live client.
- [x] An unknown `method` string raises **before** any category resolves.
- [x] Every prompt every strategy renders is byte-identical to the pre-refactor implementation
      (`tests/test_prompt_stability.py` pins a sha256 of the full
      `(category, method, step, prompt)` stream per strategy YAML), plus per-builder golden
      strings in `tests/test_category.py`.
- [x] `_build_dag` output unchanged for all 10 selectable strategies —
      `tests/test_identity_generator_configurable.py:320` passes unmodified.
- [x] First coverage for `BaseIdentityGenerator` and `FactoryIdentityGenerator`.

### Integration Tests
- [x] Resume-faithfulness: a persona interrupted after K categories produces, for category K+1, a
      prompt byte-identical to the uninterrupted run's. Run for both `context: cumulative` and
      `context: none`.
- [x] Shared lifecycle: resume → JSONL appended and `call_index` monotonic, no duplicate
      `(persona_id, call_index)`. Fresh/`--force` → JSONL truncated and `call_index` restarts.
- [x] Retry round keeps the checkpoint; `--force` discards it.
- [ ] `validate_raw` passes on a resumed run's output (exercises the containment argument).
- [ ] End-to-end smoke with a fake client over `_debug_minimal.yaml`.

### Manual Verification
- [ ] Launch a real GUI run, press **Abort** mid-generation, inspect: partial files present, no
      truncated `identity.json`. Press **Run** again; confirm completion and that no
      `identity.partial.json` survives.
- [ ] Repeat with the process killed by `taskkill /F /T` directly.
- [ ] Run `generation_metadata` over a killed-and-resumed combo; confirm cost/latency figures are
      plausible and no duplicate correlation keys are reported.

### Edge Cases
- [x] Kill during `finalize()`, between the identity write and the partial unlink.
- [x] Kill during `checkpoint()` itself.
- [x] Strategy YAML edited between two runs of the same slug (fingerprint mismatch path).
- [x] `--force` on a directory holding both a valid identity and a stale partial.
- [ ] A persona that fails every retry round: leaves a partial, no `identity.json`; `validate_raw`
      must still classify it correctly. *(First half covered; the `validate_raw` classification
      is not yet asserted.)*
- [ ] Property/fuzz test: interrupt at N random points, assert on-disk state is always either
      "old valid" or "new valid" — never torn.

---

## Documentation Plan

- [ ] Update `CLAUDE.md` — note that generation is crash-safe/resumable and that `--force` is the
      only checkpoint discard.
- [ ] Update `docs/architecture/sub-packages.md` — the new classes and their boundaries.
- [ ] Update `docs/architecture/axis-composition.md` — the run-dir layout gains
      `identity.partial.json`.
- [ ] New `docs/development/aborted-and-resumed-runs.md` — the resume protocol, the shared
      lifecycle invariant, and why there is no signal handler. No such doc exists today.
- [ ] Amend `docs/development/swedish-token-usage-by-model.md` — the ~45% token-record match
      caveat should improve; note that historical figures under-count spend.
- [ ] Inline `why` comments at every ordering-sensitive site listed under Architecture.

---

## Rollback Plan

1. **Per phase.** Each phase is a separate commit series on the branch and independently
   revertable. Phase 1 is the only one that changes on-disk behaviour.
2. **Data considerations.** No migration. `identity.json` keeps its flat shape and existing runs
   remain readable. `identity.partial.json` is new and additive; deleting every
   `**/identity.partial.json` returns a run dir to pre-change state with no loss of completed
   personas.
3. **Procedure.** Revert the phase commits; existing runs continue to work under the old
   exists-only gate. The one non-reverting effect is telemetry: JSONL files that were *appended*
   during the new behaviour will contain more records than the old code would have written —
   harmless (they are strictly more complete), but worth noting for cost comparisons that
   straddle the change.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Refactor silently changes prompt text, invalidating cross-run comparability of existing results | Med | **High** | Byte-equality test on the rendered context block and on each method's prompts, run against all 10 strategies before Phase 2 merges |
| `_build_dag` ordering drifts during the move | Low | High | Existing determinism tests must pass **unmodified**; treat any edit to them as a red flag |
| Appended telemetry shifts reported cost upward vs previously published figures | **High** | Med | It is a *correction* (old figures under-counted abandoned attempts). Document in the manuscript notes; state the direction of the shift explicitly |
| Cost/latency stats corrupted by duplicate `(persona_id, call_index)` | Med | High | The shared-lifecycle invariant, plus an integration test asserting uniqueness after resume |
| Checkpoint resumed against a changed strategy, splicing two generation regimes into one persona | Low | **High** | Fingerprint over strategy + schema bytes + model + category order; mismatch discards and logs at WARNING |
| Failed personas now leave a directory behind (the writer creates it early), interacting with the skip logic | Med | Low | Already true when `--log-llm` is on; the gate keys on `identity.json` specifically, and the checkpoint deliberately has a different filename |
| `os.replace` on Windows fails when the target is open by another process (e.g. an editor, the GUI's persona counter) | Low | Med | The GUI counter only globs and stats; add a narrow retry on `PermissionError` with a clear log line rather than a blanket except |
| Scope creep from Phase 2/3 delaying the crash-safety fix | Med | Med | Phase 1 is deliberately self-sufficient and ships alone |
| `BaseIdentityGenerator` gains a field with no existing test coverage | High | Low | Phase 1 task 1.2 + the first coverage for the ABC and factory |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — durable persistence | ~2 days | None |
| Phase 2 — Persona + Category | ~2–3 days | Phase 1 |
| Phase 3 — SyntheticPopulation | ~1 day | Phase 2 |

---

## References

- Related plans (completed): `ensure-n-generation.md`, `enrich-persona-generation-telemetry.md`,
  `force-processing-analysis-tasks.md`, `cap-population-to-n.md`,
  `remove-sequential-identity-system.md`, `fix-all-pick-context-leak.md`,
  `composable-experiment-config.md`
- Prior art in-repo: `analysis/persona_realism/runner.py` (per-item cache + top-up resume;
  note its known weakness — it records `judge_model` but never compares it on resume, which is
  precisely the failure mode the fingerprint here prevents)
- Guides: `docs/data-pipeline-engineering/02-architecture-principles-and-patterns.md` §5
  (idempotency, "overwrite don't append", complete-output markers), §8 (error boundaries),
  §3 (DTOs validated at the boundary); `05-code-craftsmanship-and-maintainability.md` §2
  (information hiding, connascence of execution order)

---
