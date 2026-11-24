# Plan: Fix context leak in the `all_pick` context-free baseline

**Date:** 2026-07-21
**Author:** Basil
**Status:** Completed
**Started:** 2026-07-22
**Completed:** 2026-07-22 15:05
**Base Branch:** `feature/method-marginal-progression-charts`
**Branch:** `feature/fix-all-pick-context-leak`

---

## Overview

`all_pick` is the manuscript's intended **context-free baseline**, but the runtime prepends the full
accumulated persona to every prompt, so it is not actually context-free. This plan adds an explicit
strategy-level `context: none` flag and wires it through `IdentityGeneratorConfigurable` so that
**only** `all_pick` generates each field without any prior-attribute context, leaving every other
strategy byte-for-byte unchanged.

## Problem Statement

In `src/population_synthetic/generators/synthetic/identity_generator_configurable.py`:

- `generate_identity` (lines 674–709) accumulates every resolved value into one shared `resolved`
  dict and passes the **whole** dict to every `_process_*` method.
- `_build_context_block(resolved)` (lines 252–255) serialises **all** accumulated key/values into
  every prompt (`Context:\n{...}\n\nGiven the context above, ...`).
- `depends_on` is consumed **only** by `_build_dag` (lines 77, 88) for topological ordering — it
  never filters context.

Consequently `all_pick` (`config/synthetic/axes/strategies/all_pick.yaml`, every field
`depends_on: []`), documented as the "no context" baseline in
`docs/development/manuscript-motivation-map.md`, the strategies `README.md`, and the completed
`add-all-pick-dag-strategy.md` plan, still receives the full persona on every field. This "context
leak" is why `all_pick` (0.298) and `all_pick_dag` (0.303) come out nearly identical — the DAG edges
barely matter because context leaks either way. It also invalidates the intended clean "no-context
vs context" contrast (the "1→2 context effect size" experiment) in the manuscript.

## Goals

### In Scope
1. Make `all_pick` genuinely context-free: no prior-attribute values appear in any of its prompts.
2. Keep every other strategy's runtime behavior identical to today (full accumulated context).
3. Add regression test coverage for both the fix and the untouched-strategy guarantee.

### Out of Scope
- Any change to `all_pick_dag`, `all_generate_pick`, `all_generate_evaluate_pick`,
  `all_generate_evaluate_random_pick`, or the `_process_*` / `_build_*` prompt builders.
- Converting `depends_on` into a context gate anywhere (rejected — it would alter the DAG
  strategies; see Alternatives).
- Re-running the manuscript benchmark or updating result numbers.

## Success Criteria

- [x] `all_pick.yaml` carries `context: none`; no other strategy file is modified.
- [x] Under `all_pick`, every field's prompt contains the first-category sentinel and none of the
      previously resolved values.
- [x] Under `all_pick_dag`, a dependent field's prompt still contains earlier resolved values.
- [x] `_load_strategy` raises `ValueError` on an unrecognised `context` value (fail-fast).
- [x] `pytest` and `ruff check src/` are green.

## Definitions

- **context-free (for `all_pick`):** every LLM prompt built for that generation run contains no
  previously-resolved attribute value — `_build_context_block` returns its empty-branch sentinel
  ("This is the first category. Use the system instruction as context.") for every field.
- **`context` mode:** a top-level strategy-YAML key. `none` ⇒ context-free as defined above;
  `cumulative` (default when the key is absent) ⇒ current behavior (full accumulated `resolved`
  dict serialised into every prompt).

---

## Technical Design

### Approach

Add an optional top-level `context` key to the strategy YAML, defaulting to `cumulative`. The loader
reads and validates it; the generation loop passes an **empty** context view to the per-category
processors when the mode is `none`, otherwise the real `resolved` dict (unchanged). The persona
`resolved` dict is still fully accumulated and returned — only what the *prompt* sees changes.

An explicit flag is required (not `depends_on`/method inference) because `all_pick` and `all_pick_dag`
both use `method: pick` and differ *only* by `depends_on`; no per-field property isolates one without
also changing the other. A strategy-level flag set on `all_pick.yaml` alone is the only mechanism
that touches exactly one strategy.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Strategy-level `context: none` flag on `all_pick` only | Touches exactly one strategy; explicit; config-driven | Adds a new (small) config key + one validation path | **Chosen** |
| Filter context to each field's `depends_on` everywhere | Principled; makes every strategy honor its DAG | Changes `all_pick_dag` and all `generate_*` strategies — violates "only this method" | Rejected |
| Gate on `method == "pick"` → no context | No new config key | Also strips `all_pick_dag` (same method) — collapses the two arms | Rejected |
| Per-field "empty `depends_on` ⇒ no context" | Config-driven, no new key | Still alters `all_pick_dag` root fields | Rejected |

### Architecture & Module Contracts

The change is confined to the strategy-loading and dispatch seams of one class. No new modules.

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `_load_strategy` | Parse + validate strategy YAML | `filepath` → `(categories: dict, context_mode: str)` | prompt wording, LLM client, DAG order |
| `generate_identity` loop | Select per-field context view before dispatch | `context_mode`, live `resolved` → `context_view` (`{}` or `resolved`) passed to `_process_*` | how a prompt renders context; per-method prompt shape |
| `_process_*` / `_build_context_block` | Render prompt from whatever context dict they receive | unchanged | which strategy is running; the `context` flag |

Contract detail — `_load_strategy` currently returns just `categories` and has a **single** caller
(`generate_identity`), so widening the return to a tuple is safe and local.

```
config/synthetic/axes/strategies/all_pick.yaml
  + context: none                     # new top-level key

identity_generator_configurable.py
  _load_strategy(filepath) -> (categories, context_mode)   # was: -> categories
  generate_identity():
    categories, context_mode = self._load_strategy(strategy_file)
    ...
    for category_name in ordered_categories:
        context_view = {} if context_mode == "none" else resolved
        value = self._process_<method>(category_name, category_schema, context_view, system_instruction)
        resolved[category_name] = value        # unchanged accumulation
```

---

## Implementation Plan

### Phase 1: Loader + config

**Goal:** Introduce and validate the `context` mode; mark `all_pick` context-free.

- [x] Add `context: none` to `config/synthetic/axes/strategies/all_pick.yaml` and update its
      `description` to state fields are generated with no persona context.
- [x] In `_load_strategy`, read top-level `context` (default `cumulative`); raise `ValueError` for
      any value other than `cumulative`/`none`; return `(categories, context_mode)`.

**Files Modified:**
- `config/synthetic/axes/strategies/all_pick.yaml` — new key + description.
- `src/population_synthetic/generators/synthetic/identity_generator_configurable.py` — `_load_strategy`.

**Dependencies:** None

### Phase 2: Generation loop

**Goal:** Feed the empty context view to processors under `context: none`.

- [x] Capture `context_mode` from `_load_strategy` in `generate_identity`.
- [x] Compute `context_view = {} if context_mode == "none" else resolved` inside the per-category
      loop and pass it to the four `_process_*` dispatch calls (lines 682–696) in place of `resolved`.
- [x] Leave `resolved[category_name] = value` accumulation and the returned `resolved` untouched.

**Files Modified:**
- `src/population_synthetic/generators/synthetic/identity_generator_configurable.py` — `generate_identity`.

**Dependencies:** Phase 1

### Phase 3: Tests + docs

**Goal:** Lock in the behavior and record the change.

- [x] New `tests/test_identity_generator_configurable.py` (see Testing Plan).
- [x] `docs/architecture/diagrams/synthetic_strategies/README.md` — note `all_pick` is now truly
      context-free via `context: none`, while the DAG/`generate_*` strategies still accumulate.
- [x] One-line note in `docs/development/manuscript-motivation-map.md` that the `all_pick` leak is
      fixed (clean no-context arm restored).

**Files Modified:**
- `tests/test_identity_generator_configurable.py` — new.
- `docs/architecture/diagrams/synthetic_strategies/README.md`, `docs/development/manuscript-motivation-map.md`.

**Dependencies:** Phase 2

---

## Testing Plan

### Unit Tests
- [x] `all_pick` context-free: patch `_call_llm_json` to capture prompts; run `generate_identity`
      with `all_pick.yaml` + a minimal in-memory flat schema and a stub client; assert every captured
      prompt contains the first-category sentinel and none of the earlier resolved values.
- [x] `all_pick_dag` regression guard: same harness with `all_pick_dag.yaml`; assert a dependent
      field's prompt **does** contain a previously resolved value (proves other strategies untouched).
- [x] `_load_strategy` fail-fast: a strategy with `context: bogus` raises `ValueError`; absent key
      yields `cumulative`.

### Integration Tests
- [x] Full `pytest` run stays green (existing suites exercise the untouched strategies indirectly).

### Manual Verification
- [x] Load `all_pick.yaml` and one other strategy via `_load_strategy`; confirm `context_mode` is
      `none` vs `cumulative`.
- [x] `ruff check src/` clean.

### Edge Cases
- [x] First category already gets empty context under `cumulative` — confirm `none` does not change
      the first field's prompt (only the later fields differ).
- [x] Numeric field under `all_pick` — value clamping still applies (uses `category_schema`, not
      context), so no regression.

---

## Documentation Plan

- [x] Update `all_pick.yaml` description (Phase 1).
- [x] Update `docs/architecture/diagrams/synthetic_strategies/README.md` (Phase 3).
- [x] One-line note in `docs/development/manuscript-motivation-map.md` (Phase 3).
- [x] CLAUDE.md: no change needed (no architecture-level contract change).

---

## Rollback Plan

1. Revert the feature branch merge commit, or
2. Remove `context: none` from `all_pick.yaml` (restores full-context behavior immediately, since
   absent key ⇒ `cumulative`), and revert the two-line loader/loop change.
3. No data migration, no on-disk format change — generated personas retain the same schema.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `_load_strategy` has an unnoticed second caller | Low | Med | Grep confirmed single caller; test suite covers `generate_identity` path |
| Empty-context sentinel wording is treated as "real" context by a model | Low | Low | Reuses the existing first-category path already in production; no new wording |
| Existing prior results conflated (pre/post-fix `all_pick` outputs mixed) | Med | Med | Fix is behavior-changing for `all_pick` only; regenerate `all_pick` before comparing to `all_pick_dag` |

---

## References

- Related Plans: `docs/development/plans/completed/add-all-pick-dag-strategy.md`
- Related Docs: `docs/development/manuscript-motivation-map.md`,
  `docs/architecture/diagrams/synthetic_strategies/README.md`
- Source: `src/population_synthetic/generators/synthetic/identity_generator_configurable.py`
  (`_load_strategy`, `generate_identity`, `_build_context_block`)

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- config/synthetic/axes/strategies/all_pick.yaml
- docs/architecture/diagrams/synthetic_strategies/README.md
- docs/development/plans/active/fix-all-pick-context-leak.md
- src/population_synthetic/generators/synthetic/identity_generator_configurable.py
- tests/test_identity_generator_configurable.py

<!-- Intentionally EXCLUDED from the commit: docs/development/manuscript-motivation-map.md —
     it was already untracked (separate 2026-07-20 work) before this plan; it carries a one-line
     "leak fixed" note from Phase 3 but committing the whole file here would entangle unrelated
     work. Left in the working tree for a separate commit. -->

