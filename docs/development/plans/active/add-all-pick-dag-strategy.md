# Plan: Add `all_pick_dag` Strategy — pick method with dependency DAG

**Date:** 2026-05-20
**Author:** Basil
**Status:** In Progress
**Started:** 2026-05-20
**Completed:** 2026-05-20
**Base Branch:** `dev`
**Branch:** `feature/add-all-pick-dag-strategy`

---

## Overview

Add a new strategy file `all_pick_dag.json` that uses the `pick` method (1 LLM call per category) on all 17 demographic categories while sharing the same dependency DAG used by `all_generate_pick`, `all_generate_evaluate_pick`, and `all_generate_evaluate_random_pick`. This fills a gap in the strategy matrix: currently `all_pick.json` is the only strategy with no inter-category dependencies, making it impossible to benchmark the `pick` method under the same DAG-ordered context conditions as the other methods.

## Problem Statement

`all_pick.json` has `"depends_on": []` for all 17 categories. The other three strategies share a dependency DAG where 12 of 17 categories receive resolved prior values as context. This means the `pick` method cannot be compared fairly against the other methods: any quality difference may be due to the absence of dependency context rather than the method itself. There is no intermediate configuration that isolates the method variable while holding the DAG constant.

## Goals

### In Scope
1. Create `all_pick_dag.json` with `method="pick"` on all categories and the full dependency DAG from `all_generate_pick.json`
2. Create the corresponding `all_pick_dag.layout.json` (node positions for DAG visualisation), copied from `all_generate_pick.layout.json`

### Out of Scope
- Changes to Python runtime code (`identity_generator_configurable.py`)
- New manifests referencing the new strategy (can be added later as needed)
- Modifications to the existing `all_pick.json` (kept as the context-free baseline)

## Success Criteria

- [ ] `all_pick_dag.json` exists in `config/assets/identity/configurable/strategies/`
- [ ] All 17 categories use `"method": "pick"`
- [ ] The `depends_on` DAG is identical to `all_generate_pick.json`
- [ ] `all_pick_dag.layout.json` exists with the same node positions as `all_generate_pick.layout.json`
- [ ] A single identity generation run using the new strategy completes without errors

---

## Technical Design

### Approach

The runtime in `identity_generator_configurable.py` is fully generic:
- `_build_dag()` (lines 45–86) computes topological order from any `depends_on` graph
- The main loop (lines 474–506) iterates in topological order and accumulates results in a `resolved` dict
- `_build_pick_prompt()` (lines 172–195) calls `_build_context_block(resolved)` which formats **all** prior resolved values into the LLM prompt — regardless of `depends_on`
- Method dispatch at lines 480–495 already handles `"method": "pick"`

No code changes are required. Only the two JSON files need to be created.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| New strategy JSON only | Zero code risk, immediate, fully supported | None | **Chosen** |
| Modify `all_pick.json` in-place | One fewer file | Destroys the context-free baseline | Rejected |
| Add a `pick_dag` method type | Explicit in code | Unnecessary — `depends_on` already controls ordering | Rejected |

### Architecture Changes

None. Two new config files only.

---

## Implementation Plan

### Phase 1: Create strategy and layout files
**Goal:** Add both JSON files to the strategies directory.

- [x] Task 1.1 — Create `config/assets/identity/configurable/strategies/all_pick_dag.json` with `method="pick"` on all 17 categories and the DAG from `all_generate_pick.json`
- [x] Task 1.2 — Create `config/assets/identity/configurable/strategies/all_pick_dag.layout.json` by copying node positions from `all_generate_pick.layout.json`

**Files Created:**
- `config/assets/identity/configurable/strategies/all_pick_dag.json` — new strategy
- `config/assets/identity/configurable/strategies/all_pick_dag.layout.json` — layout for DAG visualisation

**Dependencies:** None

---

## Testing Plan

### Manual Verification
- [ ] Run a single identity generation using the new strategy and confirm it completes without errors:
  ```bash
  python scripts/generate_identity.py --provider claude --model haiku --mode configurable \
      --config config/assets/identity/configurable/simulation_config_004_swedish_generative.json \
      --strategy config/assets/identity/configurable/strategies/all_pick_dag.json
  ```
- [ ] Confirm the generated identity JSON contains values for all 17 categories

### Edge Cases
- [ ] Confirm that categories with non-empty `depends_on` (e.g. `civil_status`, `employment_status`) receive the expected prior values as context — inspect by adding a debug print or checking the identity output for internal consistency (e.g. employment_type consistent with employment_status)

---

## Documentation Plan

- [ ] No README or CLAUDE.md updates required — the new file follows existing conventions and the strategy directory is self-documenting

---

## Rollback Plan

1. Delete `config/assets/identity/configurable/strategies/all_pick_dag.json`
2. Delete `config/assets/identity/configurable/strategies/all_pick_dag.layout.json`

No other files are affected.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Typo in a category name breaks DAG validation | Low | Low | Runtime raises `ValueError` immediately on load — caught at first test run |
| Cycle introduced in `depends_on` | Low | Low | `_build_dag()` detects cycles and raises `ValueError` |

---

## References

- Strategy source for DAG: `config/assets/identity/configurable/strategies/all_generate_pick.json`
- Layout source: `config/assets/identity/configurable/strategies/all_generate_pick.layout.json`
- Runtime: `src/population_synth/identity/identity_generator_configurable.py`
