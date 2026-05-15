# Plan: Generative Identity Methods Refactor

**Date:** 2026-05-09
**Author:** Claude Code
**Status:** In Progress
**Base Branch:** `feature/configurable-identity-pipeline`
**Branch:** `feature/configurable-identity-pipeline`

---

## Overview

Refactor the configurable identity generator to use LLM-generated values from scratch instead of predefined schema lists. Replace the four processing "modes" (`select`, `refine_random`, `refine_deterministic`, `autofill`) with four "methods" (`pick`, `generate_pick`, `generate_evaluate_pick`, `generate_evaluate_random_pick`) that compose three fundamental steps: enumerate candidates, evaluate probabilities, and select a value.

## Problem Statement

The current configurable identity generator relies on predefined value lists with probabilities baked into the schema (e.g., `[{"value": "Employed", "probability": 0.65}, ...]`). The LLM's role is limited to adjusting these existing probabilities. This constrains persona diversity to the predefined option set and doesn't leverage the LLM's ability to generate contextually appropriate values from scratch. The method names (`select`, `refine_random`, `refine_deterministic`) are also unclear about what each step actually does.

## Goals

### In Scope
1. Rename "mode" to "method" in all strategy files and generator code
2. Four new methods: `pick`, `generate_pick`, `generate_evaluate_pick`, `generate_evaluate_random_pick`
3. LLM generates values from scratch (no predefined value lists in schema)
4. New schema format with category descriptions instead of value/probability arrays
5. Numeric categories (age, Big Five) use adapted prompts for each method, including distribution-based sampling for `generate_evaluate_random_pick`
6. Remove `AUTOFILL_REGISTRY` and all autofill logic — conditional fields handled by LLM through dependency context
7. Four strategy preset files with new naming

### Out of Scope
- Modifying existing sequential or batch identity generators
- Downstream consumer updates (narrative/report generators)
- LLM batching optimization (grouping multiple categories into fewer API calls)
- Adding new identity categories beyond the existing 34

## Success Criteria

- [ ] Strategy files use `"method"` key (not `"mode"`)
- [ ] All four methods produce valid, coherent identity values
- [ ] Schema contains no predefined value lists — only descriptions and numeric ranges
- [ ] `AUTOFILL_REGISTRY` and all associated code removed
- [ ] Old strategy files with `"mode"` key produce a clear migration error
- [ ] Numeric categories work with all four methods (distribution spec for `generate_evaluate_random_pick`)
- [ ] End-to-end: seed_009 produces valid `identity.json` with each of the 4 strategy presets
- [ ] Existing sequential/batch seeds unaffected

---

## Technical Design

### Approach

Replace the schema-driven probability refinement model with a fully generative model where the LLM proposes values from scratch. The three fundamental steps are:

| Step | Name | Action |
|------|------|--------|
| I | **Enumerate** | LLM generates a list of plausible candidate values given resolved context |
| II | **Evaluate** | LLM assigns probability weights to each candidate (sum = 1.0) |
| III | **Select** | Pick the final value (LLM or Python random) |

Each method composes these steps differently:

| Method | Steps Used | LLM Calls | Final Selection |
|--------|-----------|-----------|-----------------|
| `pick` | III only | 1 | LLM directly picks a value |
| `generate_pick` | I + III | 2 | LLM generates candidates, LLM picks one |
| `generate_evaluate_pick` | I + II + III | 3 | LLM generates, evaluates, LLM picks |
| `generate_evaluate_random_pick` | I + II + Python | 2 + Python | LLM generates, evaluates, `random.choices()` |

**Numeric category adaptation:**
- `pick`: LLM picks a number within min/max range
- `generate_pick`: LLM enumerates candidate numbers, LLM picks one
- `generate_evaluate_pick`: LLM enumerates numbers, LLM scores them, LLM picks
- `generate_evaluate_random_pick`: LLM specifies a distribution function (e.g., `{"distribution": "normal", "mean": 45, "std": 12, "min": 18, "max": 90}`), Python samples from it

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Fully generative (LLM creates values from scratch) | Maximum flexibility, no predefined constraints | More LLM calls, output validation needed | **Chosen** |
| Keep predefined lists, just rename modes | Minimal code change, fewer LLM calls | Still constrained to predefined options | Rejected |
| Hybrid (predefined for some categories, generative for others) | Balance of control and flexibility | Complex dual-path logic, confusing config | Rejected |

### Architecture Changes

**Removed components:**
- `AUTOFILL_REGISTRY` dict and rule functions (`_birth_location_to_country`, `_employment_conditional`)
- `_process_select()`, `_process_refine()`, `_process_autofill()` methods
- `SchemaProbabilityRefiner` import and `self.refiner` in configurable generator

**New components in `identity_generator_configurable.py`:**

```
Helper methods:
  _call_llm_json()                        — Generic LLM call + JSON parse + retry
  _build_context_block()                  — Format resolved context for prompts
  _is_numeric_category()                  — Check if category has min/max range

Prompt builders:
  _build_pick_prompt()                    — Direct single-value pick
  _build_enumerate_prompt()               — Ask LLM for candidate list
  _build_evaluate_prompt()                — Ask LLM to assign probabilities
  _build_select_prompt()                  — Ask LLM to choose from list
  _build_numeric_distribution_prompt()    — Ask LLM for distribution spec (method d, numeric)

Method processors:
  _process_pick()                         — 1 LLM call
  _process_generate_pick()                — 2 LLM calls
  _process_generate_evaluate_pick()       — 3 LLM calls
  _process_generate_evaluate_random_pick() — 2 LLM + Python
```

**New config files:**
```
config/assets/identity/configurable/
  simulation_config_004_swedish_generative.json   (NEW — descriptions, no value lists)
  strategies/
    all_pick.json                                  (NEW — replaces all_select.json)
    all_generate_pick.json                         (NEW — no predecessor)
    all_generate_evaluate_pick.json                (NEW — replaces all_refine_deterministic.json)
    all_generate_evaluate_random_pick.json         (NEW — replaces all_refine_random.json)
```

**Unchanged:** `SchemaProbabilityRefiner` stays in `identity_generator_sequential.py` for the sequential generator. Factory, services, and pipeline script require no structural changes (only manifest path updates).

---

## Implementation Plan

### Phase 1: New Schema File
**Goal:** Create the generative schema with descriptions instead of value lists

**Started:** 2026-05-09
**Completed:** 2026-05-09

**Tasks:**
- [x] Task 1.1 — Create `simulation_config_004_swedish_generative.json` with all 34 categories
- [x] Task 1.2 — Each categorical field becomes `{"description": "..."}` with optional `"constraints"` field
- [x] Task 1.3 — Numeric fields keep `min`/`max`/`type` and add `"description"`
- [x] Task 1.4 — Rewrite `instruction` array for generative approach (remove "update probability" language)

**Files Created:**
- `config/assets/identity/configurable/simulation_config_004_swedish_generative.json`

**Dependencies:** None

### Phase 2: Strategy Files
**Goal:** Create 4 new strategy files with `"method"` key and new method names

**Started:** 2026-05-09
**Completed:** 2026-05-09

**Tasks:**
- [x] Task 2.1 — Create `all_pick.json` (all categories → `"method": "pick"`, empty `depends_on`)
- [x] Task 2.2 — Create `all_generate_pick.json` (all → `"method": "generate_pick"`, with dependency DAG from existing refine presets)
- [x] Task 2.3 — Create `all_generate_evaluate_pick.json` (all → `"method": "generate_evaluate_pick"`, same DAG)
- [x] Task 2.4 — Create `all_generate_evaluate_random_pick.json` (all → `"method": "generate_evaluate_random_pick"`, same DAG)

**Files Created:**
- `config/assets/identity/configurable/strategies/all_pick.json`
- `config/assets/identity/configurable/strategies/all_generate_pick.json`
- `config/assets/identity/configurable/strategies/all_generate_evaluate_pick.json`
- `config/assets/identity/configurable/strategies/all_generate_evaluate_random_pick.json`

**Dependencies:** None

### Phase 3: Core Generator Rewrite
**Goal:** Replace old mode processors with new method processors and prompt builders

**Started:** 2026-05-09
**Completed:** 2026-05-09

**Tasks:**
- [x] Task 3.1 — Remove `AUTOFILL_REGISTRY`, rule functions, and `_process_autofill()`
- [x] Task 3.2 — Remove `_process_select()` and `_process_refine()`
- [x] Task 3.3 — Remove `SchemaProbabilityRefiner` import and `self.refiner`
- [x] Task 3.4 — Implement `_call_llm_json()` with retry logic (max 3 retries)
- [x] Task 3.5 — Implement `_build_context_block()` and `_is_numeric_category()`
- [x] Task 3.6 — Implement prompt builders: `_build_pick_prompt()`, `_build_enumerate_prompt()`, `_build_evaluate_prompt()`, `_build_select_prompt()`, `_build_numeric_distribution_prompt()`
- [x] Task 3.7 — Implement `_process_pick()`
- [x] Task 3.8 — Implement `_process_generate_pick()`
- [x] Task 3.9 — Implement `_process_generate_evaluate_pick()`
- [x] Task 3.10 — Implement `_process_generate_evaluate_random_pick()` (categorical: `random.choices()`; numeric: sample from LLM-specified distribution via `scipy.stats` or `numpy`)
- [x] Task 3.11 — Rewrite `generate_identity()` dispatch: `"mode"` → `"method"`, new method names, migration error for old `"mode"` key
- [x] Task 3.12 — Add probability normalization (if LLM probabilities don't sum to 1.0, normalize and log warning)

**Files Modified:**
- `anxiety_synthetic/patient_generator/identity/identity_generator_configurable.py` — full rewrite of processing logic

**Dependencies:** Phase 1 (schema format), Phase 2 (strategy format)

### Phase 4: Integration Updates
**Goal:** Point seed_009 to new schema and strategy files
**Started:** 2026-05-09
**Completed:** 2026-05-09

**Tasks:**
- [x] Task 4.1 — Update `synthetic_pipeline_config_seed009.yaml`: `prompt_file` → `simulation_config_004_swedish_generative.json`, `strategy_file` → `all_pick.json`
- [x] Task 4.2 — Update the existing plan doc (`configurable-identity-pipeline.md`) with a note about this refactor

**Files Modified:**
- `config/seed_manifests/synthetic_pipeline_config_seed009.yaml`
- `docs/development/plans/active/configurable-identity-pipeline.md`

**Dependencies:** Phase 3

### Phase 5: Cleanup
**Goal:** Remove old strategy files and verify nothing references them

**Started:** 2026-05-09
**Completed:** 2026-05-09

**Tasks:**
- [x] Task 5.1 — Delete `strategies/all_select.json`
- [x] Task 5.2 — Delete `strategies/all_refine_random.json`
- [x] Task 5.3 — Delete `strategies/all_refine_deterministic.json`

**Files Deleted:**
- `config/assets/identity/configurable/strategies/all_select.json`
- `config/assets/identity/configurable/strategies/all_refine_random.json`
- `config/assets/identity/configurable/strategies/all_refine_deterministic.json`

**Dependencies:** Phase 4 (confirm new files work first)

---

## Testing Plan

### Unit Tests
- [ ] `_build_dag()` with valid dependencies returns correct topological order
- [ ] `_build_dag()` raises `ValueError` on cycles
- [ ] `_build_dag()` raises `ValueError` on undeclared dependencies
- [ ] `_process_pick()` returns a string for categorical categories
- [ ] `_process_pick()` returns an int within range for numeric categories
- [ ] `_process_generate_pick()` makes exactly 2 LLM calls (enumerate + select)
- [ ] `_process_generate_evaluate_pick()` makes exactly 3 LLM calls
- [ ] `_process_generate_evaluate_random_pick()` makes 2 LLM calls and uses `random.choices()` for categorical
- [ ] `_process_generate_evaluate_random_pick()` samples from LLM-specified distribution for numeric
- [ ] Strategy file with `"mode"` key raises migration error
- [ ] Unknown method name raises `ValueError`
- [ ] Probability normalization handles probabilities not summing to 1.0

### Integration Tests
- [ ] Full pipeline run with seed_009 + `all_pick.json` produces valid flat `identity.json`
- [ ] Full pipeline run with `all_generate_evaluate_random_pick.json` produces coherent persona
- [ ] All 34 categories present in output

### Manual Verification
- [ ] Spot-check 2-3 generated identities for internal coherence
- [ ] Verify employed personas get sensible industry/employment_type values via LLM context (no autofill needed)
- [ ] Verify existing sequential seeds still work unchanged
- [ ] Compare persona quality across the 4 method presets

### Edge Cases
- [ ] Category with 0 dependencies and `pick` method (no context)
- [ ] LLM returns malformed JSON — retry logic activates
- [ ] LLM probabilities don't sum to 1.0 — normalization applies
- [ ] Distribution spec for numeric with extreme parameters — clamped to min/max

---

## Documentation Plan

- [ ] Update `CLAUDE.md` Architecture section to reflect new method names and generative approach
- [ ] Update existing plan doc with refactor note

---

## Rollback Plan

1. **Restore old generator code:** `git checkout HEAD -- anxiety_synthetic/patient_generator/identity/identity_generator_configurable.py`
2. **Restore old strategy files:** `git checkout HEAD -- config/assets/identity/configurable/strategies/`
3. **Restore seed manifest:** `git checkout HEAD -- config/seed_manifests/synthetic_pipeline_config_seed009.yaml`
4. **No breaking changes to other generators:** Sequential and batch modes are completely untouched

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LLM returns malformed JSON in enumerate/evaluate steps | High | High | Retry logic with max 3 attempts; validate JSON structure before use |
| LLM probabilities don't sum to 1.0 | Med | Low | Normalize by dividing each by sum; log warning |
| 3-call methods are slow (~102 API calls for all 34 categories with `generate_evaluate_pick`) | High | Med | Expected tradeoff; `pick` is the fast default; future batching is out of scope |
| LLM generates culturally inappropriate values without predefined constraints | Med | Med | System instruction emphasizes Swedish context; category descriptions provide guardrails |
| Distribution sampling for numeric `generate_evaluate_random_pick` produces out-of-range values | Low | Low | Clamp to min/max after sampling |
| Removing autofill breaks conditional fields (employment_type when not employed) | Med | Med | LLM handles this through dependency context — employment_type depends on employment_status, and the LLM sees "Unemployed" in context |

---

## References

- Parent plan: `docs/development/plans/active/configurable-identity-pipeline.md`
- Notebook sketch: `docs/workflow-snapshot.jpeg`
- Current generator: `anxiety_synthetic/patient_generator/identity/identity_generator_configurable.py`
- Current schema: `config/assets/identity/configurable/simulation_config_003_swedish_flat.json`
- Current strategies: `config/assets/identity/configurable/strategies/all_*.json`
- Seed manifest: `config/seed_manifests/synthetic_pipeline_config_seed009.yaml`
