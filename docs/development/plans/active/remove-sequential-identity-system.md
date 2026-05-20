# Plan: Remove the Sequential Identity Generation System

**Date:** 2026-05-18
**Author:** Basil
**Status:** In Progress
**Base Branch:** `main`
**Branch:** `feature/remove-sequential-identity-system`

---

## Overview

Remove the `sequential` persona identity generation strategy (`IdentityGeneratorSequential` and its support classes) end-to-end. The `configurable` strategy now provides a strict superset of what `sequential` does (DAG-driven dependencies, per-category method selection, plus methods `sequential` never had such as `generate_evaluate_random_pick`), so keeping `sequential` adds maintenance surface in the factory, CLI, extractor, asset tree, and current documentation without offering capability that isn't already covered.

## Problem Statement

The `population_synth.identity` package registers three strategies in `FactoryIdentityGenerator._STRATEGY_MAP` (`sequential`, `batch`, `configurable`). Of these:

- `batch` — single-prompt narrative generation; unique role
- `configurable` — DAG-driven, per-category method selection; the current best-in-class structured strategy
- `sequential` — legacy hierarchical `level_*` strategy that predates `configurable`

`sequential` is redundant. It forces the comparison extractor to carry a dedicated `_is_sequential` / `_extract_sequential` branch, the CLI to expose a third `--mode` choice, the asset tree to maintain a `config/assets/identity/sequential/` directory, and the docs to describe a strategy that should no longer be used. Removing it simplifies all four surfaces and reduces the cognitive load for anyone reading the identity package for the first time.

## Goals

### In Scope

1. Delete the sequential generator file and its internal-only helper classes (`SchemaProbabilityRefiner`, `RecursiveFormatter`)
2. Remove the `sequential` registration from `FactoryIdentityGenerator`
3. Remove `--mode sequential` from `scripts/generate_identity.py`
4. Remove sequential-format handling from `src/population_synth/comparison/extractor.py`
5. Delete the `config/assets/identity/sequential/` asset directory
6. Update `README.md` and `CLAUDE.md` to reflect the reduced set of strategies

### Out of Scope

- Historical plan documents under `docs/development/plans/completed/` — they describe past states and are intentionally left authentic
- Pre-existing limitation in `scripts/generate_identity.py` where `configurable` mode requires a `strategy_file` kwarg the script does not currently pass — separate bug, not caused by this removal
- Auto-regenerated artifacts (`src/population_synth.egg-info/SOURCES.txt` — refreshes on next `pip install -e .`)
- Any migration / backward-compat shim for existing pipeline outputs whose `identity.json` uses the `level_*` structure (per user direction, those will be logged as `unrecognised identity format` and skipped)

## Success Criteria

- [ ] `IdentityGeneratorSequential`, `SchemaProbabilityRefiner`, `RecursiveFormatter`, `_extract_sequential`, and `_is_sequential` are absent from `src/` and `scripts/`
- [ ] `FactoryIdentityGenerator._STRATEGY_MAP` contains exactly `{"batch", "configurable"}`
- [ ] `python scripts/generate_identity.py --mode sequential --config x` is rejected by argparse
- [ ] `ruff check src/` passes clean
- [ ] An existing batch-format `identity.json` still extracts successfully through `extract_individual()`
- [ ] A nested `level_*`-format `identity.json` is logged as `unrecognised identity format` and skipped (not a crash)
- [ ] `README.md` and `CLAUDE.md` no longer mention `sequential` as a current strategy
- [ ] `config/assets/identity/sequential/` no longer exists

---

## Technical Design

### Approach

Mechanical removal across six surfaces. Order does not matter functionally, but doing the source-code removal before the doc update keeps the repository in a consistent state mid-branch. The asset directory deletion is independent of the code change.

The extractor's dispatch chain in `extract_individual()` is currently `_is_sequential → narrative → _is_flat → unknown`. Removing the first branch leaves a clean `narrative → _is_flat → unknown` chain — no fallback logic needs to be invented.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Full removal (this plan) | Minimal maintenance surface; one strategy stops being possible to invoke; aligns code and docs | Existing `level_*` `identity.json` files become unreadable for comparison | **Chosen** |
| Soft deprecation (keep extractor) | Existing pipeline outputs still extractable | Preserves dead code in `extractor.py`; defers cleanup; signal to readers is mixed | Rejected — user prefers clean removal |
| Mark deprecated only | Lowest immediate effort | Doesn't actually reduce maintenance surface; "deprecated" code rots in place | Rejected |

### Architecture Changes

- `src/population_synth/identity/` loses one of three concrete strategy implementations. The `BaseIdentityGenerator` contract and the factory pattern are unchanged.
- `src/population_synth/comparison/extractor.py` loses one of three format-detection branches. The auto-detection idiom (a chain of `_is_*` predicates) is preserved.
- No public API renames; no changes to `BaseIdentityGenerator`, `GeminiClient`, or the `PopulationDistributions` data layer.

Verified during planning (via grep):
- `SchemaProbabilityRefiner` and `RecursiveFormatter` are imported only inside `identity_generator_sequential.py` itself. `identity_generator_configurable.py` has its own `_call_llm_json` and does not depend on them.
- No `__init__.py` re-exports the sequential class.
- No test suite imports it (the repo has no test suite).

---

## Implementation Plan

### Phase 1: Source code removal
**Goal:** Remove the strategy implementation and factory registration so `sequential` is no longer dispatchable.
**Started:** 2026-05-18
**Completed:** 2026-05-18

- [x] Delete `src/population_synth/identity/identity_generator_sequential.py`
- [x] In `src/population_synth/identity/factory_identity_generator.py`:
  - Remove the `from .identity_generator_sequential import IdentityGeneratorSequential` import
  - Remove the `"sequential": IdentityGeneratorSequential,` entry from `_STRATEGY_MAP`
  - Update the class docstring (line ~14) and the `create_generator` docstring example (line ~32) to drop the `sequential` reference

**Files Modified:**
- `src/population_synth/identity/identity_generator_sequential.py` — deleted
- `src/population_synth/identity/factory_identity_generator.py` — import + registry + docstrings

**Dependencies:** None

### Phase 2: CLI removal
**Goal:** Stop offering `--mode sequential` to users.
**Started:** 2026-05-18
**Completed:** 2026-05-18

- [x] In `scripts/generate_identity.py`:
  - Update module docstring (lines 4–25): remove the sequential usage example and the `sequential` line in the `Modes:` block
  - Update argparse epilog (lines 45–47): remove the sequential example
  - Change `choices=["sequential", "batch", "configurable"]` → `choices=["batch", "configurable"]`
  - Update `help="Identity generation strategy: sequential, batch, or configurable"` → `help="Identity generation strategy: batch or configurable"`

**Files Modified:**
- `scripts/generate_identity.py` — docstring, argparse choices, help text, epilog

**Dependencies:** Phase 1 (factory no longer accepts `sequential`)

### Phase 3: Extractor cleanup
**Goal:** Remove the comparison extractor's sequential-format handler so the codebase no longer has to understand the legacy `level_*` schema.
**Started:** 2026-05-18
**Completed:** 2026-05-18

- [x] In `src/population_synth/comparison/extractor.py`:
  - Delete the `_extract_sequential(identity, persona_id)` function (begins at line 757, extends to the next `def`)
  - Delete the `_is_sequential(identity)` helper (lines 1634–1635)
  - In `extract_individual()` (lines 1646–1671), remove the `if _is_sequential(identity): attrs = _extract_sequential(...)` branch. The resulting dispatch becomes:
    ```python
    if "narrative" in identity:
        attrs = _extract_batch(identity, persona_id)
    elif _is_flat(identity):
        attrs = _extract_flat(identity, persona_id)
    else:
        logger.warning("%s: unrecognised identity format (keys: %s) -- skipping", persona_id, list(identity))
        return None
    ```

**Files Modified:**
- `src/population_synth/comparison/extractor.py` — delete `_extract_sequential`, `_is_sequential`, simplify `extract_individual` dispatch

**Dependencies:** None (independent of Phases 1–2)

### Phase 4: Asset and documentation cleanup
**Goal:** Bring the asset tree and current-state docs in line with the new strategy set.
**Started:** 2026-05-18
**Completed:** 2026-05-18

- [x] Delete the directory `config/assets/identity/sequential/` (contains `simulation_config_001.json` and `simulation_config_002_swedish.json`)
- [x] Update `README.md`:
  - Line 9: `with sequential, batch, and configurable strategy modes` → `with batch and configurable strategy modes`
  - Lines 55–58 (Modes block): remove the `sequential` bullet
  - Line 110 (Architecture tree): remove the `identity_generator_sequential.py` entry
- [x] Update `CLAUDE.md`:
  - Line 10: `with multiple strategy modes (sequential, batch, configurable)` → `with strategy modes (batch, configurable)`
  - Line 75: `selects sequential, batch, or configurable strategy at runtime` → `selects batch or configurable strategy at runtime`
  - Lines 76–80 (Mode semantics block): remove the `sequential` bullet
  - Line 112: `(batch, configurable, sequential sub-directories)` → `(batch and configurable sub-directories)`

**Files Modified:**
- `config/assets/identity/sequential/` — directory deleted
- `README.md` — three updates
- `CLAUDE.md` — four updates

**Dependencies:** Phases 1–3 (docs should reflect the actual code state)

---

## Testing Plan

> Note: this repository has no automated test suite. Verification is via lint, static greps, and manual smoke runs.

### Unit Tests
- N/A — no test suite exists

### Integration Tests
- N/A — no test suite exists

### Manual Verification
- [ ] **Static check** — `grep -rn "sequential" src/ scripts/ config/ README.md CLAUDE.md` returns zero hits (excluding `docs/development/plans/completed/`, intentionally untouched)
- [ ] **Symbol check** — `grep -rn "IdentityGeneratorSequential\|SchemaProbabilityRefiner\|RecursiveFormatter\|_extract_sequential\|_is_sequential" src/ scripts/` returns zero hits
- [ ] **Lint** — `ruff check src/` passes clean
- [ ] **Factory smoke** — `python -c "from population_synth.identity.factory_identity_generator import FactoryIdentityGenerator; print(sorted(FactoryIdentityGenerator._STRATEGY_MAP.keys()))"` prints `['batch', 'configurable']`
- [ ] **CLI smoke (negative)** — `python scripts/generate_identity.py --mode sequential --config x.json` exits with an argparse error citing the new choices
- [ ] **CLI smoke (positive, requires `GEMINI_API_KEY`)** — `python scripts/generate_identity.py --mode batch --config config/assets/identity/batch/prompt_identity_generation_002_swedish.txt --output /tmp/test_identity.json` writes `{"narrative": "..."}`

### Edge Cases
- [ ] **Extractor on legacy format** — Feed a synthetic `level_*`-shaped `identity.json` through `extract_individual()` and confirm it is logged as `unrecognised identity format` and the function returns `None` (not a crash)
- [ ] **Extractor on batch format** — Confirm an existing batch-format `identity.json` from a prior pipeline run still extracts successfully

---

## Documentation Plan

- [ ] Update `README.md` (Features list, Modes block, Architecture tree) — covered in Phase 4
- [ ] Update `CLAUDE.md` (Project Overview, Architecture, Mode semantics, Configuration) — covered in Phase 4
- [ ] No new user guide or changelog file needed — this is a removal, not a feature

---

## Rollback Plan

This is a pure removal with no data migration. Rollback is `git revert` of the merge commit.

1. **Before merge:** simply delete the feature branch — `main` is unaffected.
2. **After merge:** `git revert -m 1 <merge-sha>` on `main` restores the sequential strategy file, factory entry, extractor handlers, CLI option, asset directory, and doc text. The reverted state will be identical to the pre-merge `main`.
3. **Data considerations:** none. No migrations, no schema changes, no stored state. Any `identity.json` files already on disk are not modified by this change.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| External script or downstream consumer imports `IdentityGeneratorSequential` directly (bypassing the factory) | Low | Medium | grep across this repo returned zero such imports. The package has no published external consumers — only the in-repo `scripts/` use it. |
| Pipeline outputs with `level_*`-format `identity.json` files exist on disk and need to be re-comparable | Medium | Low | User explicitly accepted that those will become unreadable and be logged as `unrecognised identity format`. The skip is non-fatal — comparison continues on remaining personas. |
| The `_extract_sequential` function turns out to share logic with `_extract_flat` or `_extract_batch` that gets accidentally removed | Low | Medium | Audit confirms `_extract_sequential` is self-contained; the helpers it uses are local to the file or shared with the other extractors (which keep them). Lint + the static grep checks above catch any dangling reference. |
| `SchemaProbabilityRefiner` / `RecursiveFormatter` turn out to be imported by something unexpected | Low | Low | grep across the repo: only `identity_generator_sequential.py` itself and two historical plan docs reference them. Safe to delete with the file. |

---

## References

- Approved planning document (internal scratch): `C:\Users\basil\.claude\plans\generate-a-plan-to-glimmering-lagoon.md`
- Related historical plan: `docs/development/plans/completed/configurable-identity-pipeline.md` (introduced the `configurable` strategy that supersedes `sequential`)
- Related historical plan: `docs/development/plans/completed/generative-identity-methods.md` (added the per-category methods that close the capability gap with `sequential`)
