# Plan: Align Strategy Files with SCB-Comparable Categories

**Date:** 2026-05-20
**Author:** Basil
**Status:** Completed
**Completed:** 2026-05-20 18:11
**Base Branch:** `feature/claude-code-client-persistent-stream`
**Branch:** `feature/align-strategies-scb-comparable`

---

## Overview

Add the two missing SCB-comparable categories (`current_environment_type`, `ethnicity_broad_global_approx`) to the simulation config, remove all non-compared categories from the 4 `all_*` strategy files, and create 4 new Claude Sonnet manifests. This ensures generated identities contain exactly the 17 fields the comparison extractor evaluates against SCB data.

## Problem Statement

The comparison extractor (`src/population_synth/comparison/extractor.py`) extracts 17 fields from `identity.json` files. Two of those — `ethnicity` (read from `ethnicity_broad_global_approx`, line 1318) and `current_environment_type` (line 1323) — are absent from `simulation_config_004_swedish_generative.json` and were recently removed from all strategy files. This causes `Non-standard label` for both fields in comparison results.

Additionally, the `all_*` strategies currently generate 32 categories, but only 17 are compared against SCB. The 15 non-compared categories (personality traits, gender_identity, etc.) add LLM calls without contributing to the comparison pipeline.

## Goals

### In Scope
1. Add `current_environment_type` and `ethnicity_broad_global_approx` to `simulation_config_004_swedish_generative.json`
2. Remove all non-compared categories from the 4 `all_*` strategy files (keeping only the 17 SCB-comparable ones)
3. Create 4 new Claude Sonnet manifests (022–025) mirroring the existing Haiku manifests

### Out of Scope
- Changes to the comparison extractor itself
- Changes to the `compared_only_generate_evaluate_random_pick.json` or `debug_minimal.json` strategy files
- Changes to `simulation_config_003_swedish_flat.json`
- Batch mode manifests

## Success Criteria

- [ ] `simulation_config_004` contains all 17 categories the extractor reads from flat identity.json
- [ ] Each `all_*` strategy file contains exactly 17 categories matching the extractor's field list
- [ ] Running manifest 014 produces an `identity.json` with `current_environment_type` and `ethnicity_broad_global_approx` keys
- [ ] Running the extractor on that output yields no `Non-standard label` for ethnicity or current_environment_type
- [ ] 4 Claude Sonnet manifests (022–025) exist and load correctly

---

## Technical Design

### Approach

Minimal delta: add 2 category descriptions to the simulation config, delete 15 category entries from each strategy file, and re-add the 2 missing ones. Each strategy keeps its own method and preserves existing `depends_on` DAG edges (dropping any that reference removed categories).

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Remove non-compared categories from strategies | Fewer LLM calls, exact alignment with comparison pipeline | Loses ability to generate full personality profiles | **Chosen** — user's stated goal |
| Keep all categories, just add the 2 missing | No removals needed | Wastes LLM calls on 15 non-compared fields | Rejected |
| Create new `scb_only_*` strategy variants | Preserves original `all_*` strategies | File proliferation, same categories duplicated | Rejected |

### Architecture Changes

No new modules or classes. Only data file changes (JSON configs + YAML manifests).

---

## Implementation Plan

### Phase 1: Simulation Config
**Goal:** Add the 2 missing categories so the LLM can generate them

- [x] Add `current_environment_type` category description to `simulation_config_004_swedish_generative.json`
- [x] Add `ethnicity_broad_global_approx` category description to `simulation_config_004_swedish_generative.json`

**Files Modified:**
- `config/assets/identity/configurable/simulation_config_004_swedish_generative.json` — Add 2 category entries after `housing_tenure`

**Dependencies:** None

### Phase 2: Strategy Files
**Goal:** Trim each strategy to exactly the 17 SCB-comparable categories

**The 17 categories to keep:**
`age`, `biological_sex`, `region`, `birth_location`, `birth_country_detail`, `civil_status`, `household_size`, `education_level`, `employment_status`, `employment_type`, `industry_sector`, `socioeconomic_class`, `income_source`, `housing_tenure`, `parental_structure`, `current_environment_type`, `ethnicity_broad_global_approx`

**The 15 categories to remove:**
`gender_identity`, `sexual_orientation`, `somatotype`, `disabilities_visible`, `sibling_constellation`, `childhood_atmosphere`, `religious_alignment`, `openness`, `conscientiousness`, `extraversion`, `agreeableness`, `neuroticism`, `cognitive_style`, `financial_behavior`, `social_media_usage`, `tone_baseline`, `speaking_pace`

- [x] `all_pick.json` — Remove 15 non-compared categories, add `current_environment_type` and `ethnicity_broad_global_approx`
- [x] `all_generate_pick.json` — Same removals/additions; drop `depends_on` references to removed categories (e.g. `religious_alignment` was removed entirely, `financial_behavior` removed, etc.)
- [x] `all_generate_evaluate_pick.json` — Same pattern
- [x] `all_generate_evaluate_random_pick.json` — Same pattern

**Files Modified:**
- `config/assets/identity/configurable/strategies/all_pick.json`
- `config/assets/identity/configurable/strategies/all_generate_pick.json`
- `config/assets/identity/configurable/strategies/all_generate_evaluate_pick.json`
- `config/assets/identity/configurable/strategies/all_generate_evaluate_random_pick.json`

**Dependencies:** Phase 1 (simulation config must have the categories before strategies reference them)

### Phase 3: Claude Sonnet Manifests
**Goal:** Create 4 new manifests for Claude Sonnet, one per strategy

- [x] Create `identity_manifest_022_claude_sonnet.yaml` — all_pick
- [x] Create `identity_manifest_023_claude_sonnet.yaml` — all_generate_pick
- [x] Create `identity_manifest_024_claude_sonnet.yaml` — all_generate_evaluate_pick
- [x] Create `identity_manifest_025_claude_sonnet.yaml` — all_generate_evaluate_random_pick

**Files Created:**
- `config/seed_manifests/identity_manifest_022_claude_sonnet.yaml`
- `config/seed_manifests/identity_manifest_023_claude_sonnet.yaml`
- `config/seed_manifests/identity_manifest_024_claude_sonnet.yaml`
- `config/seed_manifests/identity_manifest_025_claude_sonnet.yaml`

**Dependencies:** Phase 2 (strategies must be correct before manifests reference them)

---

## Testing Plan

### Manual Verification
- [ ] Load each manifest with `load_manifest()` — confirm no validation errors
- [ ] Run `generate_identity.py --manifest config/seed_manifests/identity_manifest_014_claude_haiku.yaml` — confirm output contains `current_environment_type` and `ethnicity_broad_global_approx`
- [ ] Run the extractor on the output identity — confirm no `Non-standard label` for ethnicity or current_environment_type
- [ ] Verify each strategy file has exactly 17 category entries

### Edge Cases
- [ ] Confirm `depends_on` in DAG strategies don't reference any removed category
- [ ] Confirm `compared_only_generate_evaluate_random_pick.json` and `debug_minimal.json` are untouched

---

## Documentation Plan

- [ ] No doc changes needed — CLAUDE.md already documents manifests and the comparison pipeline

---

## Rollback Plan

All changes are to data files (JSON + YAML). Rollback via `git checkout` on the affected files.

1. `git checkout HEAD -- config/assets/identity/configurable/simulation_config_004_swedish_generative.json`
2. `git checkout HEAD -- config/assets/identity/configurable/strategies/all_*.json`
3. Delete the 4 new manifest files

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LLM generates values the extractor can't normalize | Med | Med | Extractor already has fuzzy matching; existing normalization functions handle free-form LLM output |
| `depends_on` references a removed category | Low | High | Manually verify each strategy's DAG after edits |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 | 5 min | None |
| Phase 2 | 15 min | Phase 1 |
| Phase 3 | 10 min | Phase 2 |

---

## References

- Comparison extractor: `src/population_synth/comparison/extractor.py` (lines 1263–1476 for flat extraction)
- Approved design notes: `C:\Users\basil\.claude\plans\i-want-to-generate-mellow-wave.md`
