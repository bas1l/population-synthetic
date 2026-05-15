# Plan: Configurable Identity Generation Pipeline

**Date:** 2026-05-09
**Author:** Claude Code
**Status:** In Progress
**Base Branch:** `feature/comparison-radar-chart`
**Branch:** `feature/configurable-identity-pipeline`

---

## Overview

Add a third identity generation strategy (`"configurable"`) that replaces the rigid level-based paradigm with an explicit per-category dependency graph (DAG). Each category independently declares its processing mode and dependencies in an external strategy JSON file (referenced from the YAML seed manifest), enabling fine-grained experimental comparison of how individual variables affect persona generation.

## Problem Statement

The current identity generation has two incompatible modes:

- **Sequential** processes 4 fixed levels uniformly: level 1 uses raw probabilities, levels 2-4 all get LLM probability refinement + random selection. Every category within a level receives the same treatment — no way to vary the processing mode of a single field.
- **Batch** bypasses the schema entirely, sending a freeform text prompt to the LLM.

This rigidity prevents investigating the impact of individual generation variables (e.g., "what happens if we skip LLM refinement for education but keep it for employment?"). The level abstraction conflates organizational grouping with processing order, making it impossible to express cross-level dependencies or per-category processing strategies.

## Goals

### In Scope
1. New `"configurable"` processing type in the identity generator factory
2. Per-category processing mode declaration (`autofill`, `select`, `refine_deterministic`, `refine_random`) in external strategy JSON files
3. Explicit per-category dependency DAG with topological sort, replacing level-based ordering
4a. One strategy file per processing mode (all_select, all_refine_random, all_refine_deterministic)
4. New flat schema format (no levels, no groups) for configurable mode
5. Flat output format (`{"age": 34, "biological_sex": "Female", ...}`)
6. Autofill rule registry for derived fields (birth_country_detail, employment conditionals)

### Out of Scope
- Modifying existing sequential or batch modes (full backward compatibility)
- Modifying existing schema JSON files
- Downstream consumer updates (narrative/report generators handling flat identity format)
- LLM batching optimization (grouping multiple `refine_*` categories into fewer API calls)
- Adding new identity categories beyond those in the existing Swedish schema

## Success Criteria

- [ ] `FactoryIdentityGenerator.create_generator("configurable", client)` returns `IdentityGeneratorConfigurable`
- [ ] Topological sort correctly orders categories by declared dependencies
- [ ] Cycle detection raises `ValueError` with descriptive message
- [ ] All 4 processing modes produce valid outputs for their respective field types
- [ ] Autofill rules correctly compute `birth_country_detail` and employment conditionals
- [ ] Output `identity.json` is a flat dict with all declared field names as top-level keys
- [ ] End-to-end: pipeline produces persona folders with valid flat `identity.json` using seed_009
- [ ] Existing sequential seeds (e.g., seed_007) continue to work unchanged

---

## Technical Design

### Approach

Introduce a third strategy class (`IdentityGeneratorConfigurable`) into the existing factory pattern. This generator reads a flat schema JSON for field definitions (values, probabilities, ranges) and a strategy JSON file for processing modes and dependencies. The YAML seed manifest references both files via `prompt_file` and `strategy_file` paths. One strategy file per processing mode (all_select, all_refine_random, all_refine_deterministic) keeps the manifest lightweight. The generator builds a DAG, topologically sorts categories, and processes each one according to its declared mode.

The four processing modes map directly to the notebook sketch (workflow-snapshot.jpeg):

| Mode | Sketch notation | Behavior |
|------|----------------|----------|
| `autofill` | CAT -> AUTOFILL -> VALUE | Computed from resolved dependencies via a registered rule function |
| `select` | CAT -> GEN VALUES -> AUTO SELECT -> VALUE | Weighted random from base schema probabilities, no LLM call |
| `refine_deterministic` | CAT -> GEN VALUES -> GEN PROBABILITY -> AUTO SELECT -> VALUE | LLM refines probabilities based on dependency context, pick highest |
| `refine_random` | CAT -> GEN VALUES -> GEN PROBABILITY -> RAN SELECT -> VALUE | LLM refines probabilities based on dependency context, weighted random |

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| New configurable mode as third strategy | Backward compatible, clean separation, enables experiments | More code to maintain | **Chosen** |
| Refactor sequential mode in-place to support per-category config | Less code | Breaks existing configs, risky | Rejected |
| Per-level mode declaration (not per-category) | Simpler config | Still too coarse for variable-impact experiments | Rejected |
| Auto-flatten existing level-based schemas at load time | No new schema files | Mixes concerns, fragile if schema structure changes | Rejected |

### Architecture Changes

New module added to the identity strategy pattern:

```
anxiety_synthetic/patient_generator/identity/
  base_identity_generator.py          (unchanged)
  factory_identity_generator.py       (add "configurable" to registry)
  identity_generator_sequential.py    (unchanged — SchemaProbabilityRefiner and RecursiveFormatter reused via import)
  identity_generator_batch.py         (unchanged)
  identity_generator_configurable.py  (NEW — core generator, DAG, autofill registry)

config/assets/identity/
  batch/                              (unchanged)
  sequential/                         (unchanged)
  configurable/                       (NEW directory)
    simulation_config_003_swedish_flat.json  (NEW — flat schema)
    strategies/                             (NEW directory)
      all_select.json                       (NEW — select mode for all fields)
      all_refine_random.json                (NEW — refine_random mode for all fields)
      all_refine_deterministic.json         (NEW — refine_deterministic mode for all fields)
```

**Key reuse points:**
- `SchemaProbabilityRefiner` from `identity_generator_sequential.py` — used for `refine_*` modes
- `RecursiveFormatter` from `identity_generator_sequential.py` — used for formatted output
- `BaseIdentityGenerator` ABC — implemented by new class
- `FactoryIdentityGenerator` — extended with new strategy entry

**Integration:** `**kwargs` passthrough from pipeline script -> services -> generator for `strategy_file`.

---

## Implementation Plan

### Phase 1: Flat Schema File
**Goal:** Create the flat schema JSON that strips levels/groups from the Swedish schema
**Started:** 2026-05-09
**Completed:** 2026-05-09

**Tasks:**
- [x] Task 1.1 — Create `config/assets/identity/configurable/` directory
- [x] Task 1.2 — Create `simulation_config_003_swedish_flat.json` with:
  - `instruction` array (updated to reference category names instead of levels)
  - `categories` flat dict: all 30 fields from `simulation_config_002_swedish.json` mapped by leaf field name
  - Big Five traits promoted from nested `big_five_traits.openness` to top-level `openness`, etc.
  - Group `description` strings dropped

**Files Created:**
- `config/assets/identity/configurable/simulation_config_003_swedish_flat.json`

**Dependencies:** None

### Phase 2: Core Generator
**Goal:** Implement the configurable identity generator with DAG processing and all 4 modes
**Started:** 2026-05-09
**Completed:** 2026-05-09

**Tasks:**
- [x] Task 2.1 — Create `IdentityGeneratorConfigurable` class extending `BaseIdentityGenerator`
- [x] Task 2.2 — Implement `_build_dag()` with Kahn's algorithm (topological sort + cycle detection)
- [x] Task 2.3 — Implement `_process_select()` for weighted random / numeric range / static values
- [x] Task 2.4 — Implement `_process_refine()` wrapping single fields for `SchemaProbabilityRefiner`, with deterministic (highest probability) and random (weighted `random.choices`) selection
- [x] Task 2.5 — Implement `_process_autofill()` with rule lookup and `None`-means-fallback-to-select semantics
- [x] Task 2.6 — Implement `AUTOFILL_REGISTRY` with 3 initial rules:
  - `age_to_age_group`: bin age into `"18-24"`, `"25-34"`, etc.
  - `birth_location_to_country`: `"Sweden"` in value -> `"Sweden"`, else `"Other"`
  - `employment_conditional`: if status != `"Employed"` -> `"Not Applicable"`, else `None`
- [x] Task 2.7 — Implement `generate_identity()` orchestrating: load flat schema, get category_config, build DAG, process in order, return flat dict
- [x] Task 2.8 — Implement `load_identity()` for loading persisted flat identity files

**Files Created:**
- `anxiety_synthetic/patient_generator/identity/identity_generator_configurable.py`

**Dependencies:** Phase 1 (schema file used during testing)

### Phase 3: Integration Plumbing
**Goal:** Wire the new generator into the factory, services, and pipeline script
**Started:** 2026-05-09
**Completed:** 2026-05-09

**Tasks:**
- [x] Task 3.1 — Add `"configurable": IdentityGeneratorConfigurable` to `_STRATEGY_MAP` in `factory_identity_generator.py`
- [x] Task 3.2 — Modify `run_identity()` in `persona_services.py` to accept `**kwargs` and pass through to `generate_identity()`
- [x] Task 3.3 — Modify TASK 2 block in `generate_persona_and_report.py` to extract `strategy_file` from params and pass as kwarg

**Files Modified:**
- `anxiety_synthetic/patient_generator/identity/factory_identity_generator.py` — add import + strategy map entry
- `anxiety_synthetic/patient_generator/persona_services.py` — `**kwargs` passthrough in `run_identity()`
- `scripts/generate_persona_and_report.py` — extract and forward `strategy_file`

**Dependencies:** Phase 2

### Phase 4: Example Seed Manifest
**Goal:** Create a working seed manifest demonstrating the configurable mode
**Started:** 2026-05-09
**Completed:** 2026-05-09

**Tasks:**
- [x] Task 4.1 — Create `synthetic_pipeline_config_seed009.yaml` with:
  - `processing_type: "configurable"`
  - `prompt_file` pointing to flat schema
  - `strategy_file` pointing to a strategy JSON (e.g., `all_select.json`)
  - Only `generate_identity` task enabled (other tasks disabled for initial testing)
- [x] Task 4.2 — Create strategy JSON files in `config/assets/identity/configurable/strategies/`:
  - `all_select.json` — all fields use `select` mode
  - `all_refine_random.json` — all fields use `refine_random` mode
  - `all_refine_deterministic.json` — all fields use `refine_deterministic` mode

**Files Created:**
- `config/seed_manifests/synthetic_pipeline_config_seed009.yaml`
- `config/assets/identity/configurable/strategies/all_select.json`
- `config/assets/identity/configurable/strategies/all_refine_random.json`
- `config/assets/identity/configurable/strategies/all_refine_deterministic.json`

**Dependencies:** Phase 3

---

## Testing Plan

### Unit Tests
- [ ] `_build_dag()` with a known dependency graph returns valid topological order
- [ ] `_build_dag()` raises `ValueError` on circular dependencies
- [ ] `_build_dag()` raises `ValueError` on references to undeclared categories
- [ ] `_process_select()` samples correctly from probability arrays, numeric ranges, and static values
- [ ] `_process_autofill()` with `birth_location_to_country` rule extracts country correctly
- [ ] `_process_autofill()` falls back to `_process_select()` when rule returns `None` and schema exists
- [ ] `_process_autofill()` raises `ValueError` when rule returns `None` and no schema exists

### Integration Tests
- [ ] `FactoryIdentityGenerator.create_generator("configurable", client)` returns `IdentityGeneratorConfigurable`
- [ ] Full pipeline run with seed_009 produces persona folders with `identity.json`
- [ ] Output `identity.json` is a flat dict (no nested levels/groups)
- [ ] All 30 declared fields are present in output

### Manual Verification
- [ ] Spot-check 2-3 generated identities for coherence (employed persona has valid industry, retired persona has "Not Applicable")
- [ ] Verify existing sequential seed (e.g., seed_007) still works unchanged
- [ ] Compare outputs between two configs varying a single category's mode

### Edge Cases
- [ ] Category with 0 dependencies and `select` mode (no context needed)
- [ ] `autofill` rule returning `None` with valid schema fallback (employed persona's industry_sector)
- [ ] All categories set to `select` (no LLM calls at all — pure random baseline)

---

## Documentation Plan

- [ ] Update `CLAUDE.md` Architecture section to document the configurable identity generation mode
- [ ] Update `CLAUDE.md` Commands section with example seed_009 usage

---

## Refactor Note (2026-05-09)

The identity generation modes have been refactored as part of the "Generative Identity Methods Refactor" plan (`generative-identity-methods.md`). The `"mode"` key in strategy files has been replaced by `"method"`, and four new method names (`pick`, `generate_pick`, `generate_evaluate_pick`, `generate_evaluate_random_pick`) have been introduced in place of the original four modes. The schema format has also been updated — `simulation_config_004_swedish_generative.json` uses per-category `"description"` strings instead of predefined `value`/`probability` arrays, enabling fully generative LLM-driven value selection.

---

## Rollback Plan

1. **Revert factory:** Remove `"configurable"` from `_STRATEGY_MAP` in `factory_identity_generator.py`
2. **Revert plumbing:** Remove `**kwargs` from `run_identity()` and pipeline script
3. **Delete new files:** Remove `identity_generator_configurable.py`, flat schema, seed_009
4. **No breaking changes:** Sequential and batch modes are untouched throughout

No database migrations, no existing file modifications beyond 3 small additions.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LLM refiner receives narrow single-field context (vs. full level) and produces poor refinements | Med | Med | Context dict includes all resolved dependency values; system instruction frames the task. If quality is poor, batch nearby `refine_*` categories in follow-up. |
| Field name collision in flat schema (non-unique leaf names) | Low | High | Verified: all 30 fields in Swedish schema have unique leaf names. Validator in `_build_dag()` will catch duplicates. |
| Downstream consumers (narrative generator) can't parse flat identity format | Med | Med | Out of scope — configurable mode initially runs identity-only (seed_009 disables other tasks). |
| Strategy file gets out of sync with schema | Med | Low | Cross-validation at load time raises ValueError if strategy declares categories not in schema. |
| `SchemaProbabilityRefiner` prompt format expects level-based context structure | Low | Med | Refiner accepts any dict as context and any dict as target schema — format-agnostic. Verified in source code. |

---

## References

- Notebook sketch: `docs/workflow-snapshot.jpeg` (2026-05-09)
- Approved design plan: `.claude/plans/this-snapshot-is-a-swirling-tarjan.md`
- Existing sequential generator: `anxiety_synthetic/patient_generator/identity/identity_generator_sequential.py`
- Existing factory: `anxiety_synthetic/patient_generator/identity/factory_identity_generator.py`
- Swedish schema (source for flattening): `config/assets/identity/sequential/simulation_config_002_swedish.json`
- Service layer: `anxiety_synthetic/patient_generator/persona_services.py`
- Pipeline entry point: `scripts/generate_persona_and_report.py`
