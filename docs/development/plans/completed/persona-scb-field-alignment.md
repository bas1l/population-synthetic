# Plan: Persona Pipeline Field Expansion (SCB Alignment)

**Date:** 2026-05-07
**Author:** Basil
**Status:** Completed
**Completed:** 2026-05-09 09:47
**Base Branch:** `dev`
**Branch:** `feature/persona-scb-field-alignment`

---

## Overview

Add 9 demographic fields to the persona identity schema to match the coverage of the SCB population pipeline. This enables full field-level statistical comparison between LLM-generated personas and real Swedish population data. The new fields cover geography (region, birth country detail), family structure (civil status, household size), housing, employment detail (industry sector, employment type), and economic profile (income source).

## Problem Statement

The persona pipeline generates 21 identity fields, but is missing 9 demographic fields that the SCB pipeline produces. This limits the comparability of the two systems — the comparison framework (`compare_populations.py`) can only compare the 6 shared fields today. The missing fields are all standard Swedish demographic attributes with well-defined categories already documented in `category_mappings.json`.

## Goals

### In Scope
1. Add 9 new fields to the persona identity schema (`simulation_config_002_swedish.json`) at appropriate hierarchical levels
2. Implement conditional logic for employment-dependent fields (industry_sector, employment_type → "Not Applicable" when not employed)
3. Implement conditional logic for origin-dependent fields (birth_country_detail → "Sweden" when birth_location is native)
4. Add computed `age_group` field (derived deterministically from age) to identity output
5. Ensure the LLM probability refinement loop works correctly with expanded schema

### Out of Scope
- Changing the SCB pipeline (handled by separate plan: `scb-raw-data-output.md`)
- Updating narrative generation prompts to explicitly reference new fields (the LLM will naturally incorporate them from identity context passed as prior-level attributes)
- Updating the comparison framework (`compare_populations.py`) — extraction and comparison changes are a downstream concern
- Adding fields that don't exist in the SCB pipeline (e.g., religion, personality traits — these already exist in the persona schema)

## Success Criteria

- [ ] All 9 new fields appear in generated `identity.json` files with valid values
- [ ] `age_group` is computed correctly and included in identity output
- [ ] Non-employed personas have `industry_sector = "Not Applicable"` and `employment_type = "Not Applicable"`
- [ ] Native-born personas have `birth_country_detail = "Sweden"`
- [ ] LLM probability refinement produces valid distributions (all probabilities sum to 1.0) for new fields
- [ ] Existing fields are unaffected — no regression in current identity generation

---

## Technical Design

### Approach

Add new fields to the existing hierarchical identity schema at levels matching their conceptual nature (foundational → psycho-social → functional). The sequential identity generator already iterates through levels and refines probabilities via LLM — new fields are automatically picked up with no generator architecture changes. Conditional overrides (employment-dependent, origin-dependent) are applied after LLM refinement to enforce hard constraints.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Add to existing schema levels (chosen) | Minimal code changes; leverages existing LLM refinement loop; field-agnostic generator | LLM sees more fields per level, increasing token usage | **Chosen** |
| Add as a separate post-processing step | No schema changes; generator untouched | Bypasses LLM correlation refinement; fields would be uncorrelated with existing attributes | Rejected — defeats the purpose of LLM-refined correlations |
| Create a separate "SCB alignment" schema | Clean separation | Duplicates infrastructure; two schemas to maintain; fragmentation | Rejected |

### Architecture Changes

No new modules or classes. Changes are additive to existing files:

```
config/assets/identity/sequential/
└── simulation_config_002_swedish.json  — ADD 9 fields to levels 1-3

anxiety_synthetic/patient_generator/identity/
└── identity_generator_sequential.py    — ADD age_group computation + conditional overrides

scripts/
└── extract_population_from_pipeline.py — ADD extraction for 9 new fields
```

### Field Placement by Level

| Level | Existing Fields | New Fields |
|-------|----------------|------------|
| **Level 1** (Demographic foundation) | age, biological_sex, gender_identity, sexual_orientation, ethnicity_broad, current_environment_type, birth_location, somatotype, disabilities_visible | **region**, **birth_country_detail** |
| **Level 2** (Psycho-social structure) | parental_structure, sibling_constellation, childhood_atmosphere, education_level, socioeconomic_class, religious_alignment, big_five_traits, cognitive_style | **civil_status**, **household_size**, **housing_tenure** |
| **Level 3** (Functional application) | employment_status, financial_behavior, social_media_usage | **industry_sector**, **employment_type**, **income_source** |
| **Level 4** (Surface expression) | tone_baseline, speaking_pace | *(no changes)* |

### Conditional Field Logic

Applied as post-refinement overrides in the generator:

1. **`industry_sector`** — If `employment_status != "Employed"` → force `"Not Applicable"`
2. **`employment_type`** — If `employment_status != "Employed"` → force `"Not Applicable"`
3. **`birth_country_detail`** — If `birth_location == "Native (Born in Sweden)"` → force `"Sweden"`

### Key Design Decisions

1. **Probabilities are initial estimates** — The LLM refines them based on the persona context from prior levels. The initial values approximate Swedish population distributions but don't need to be exact.
2. **`age_group` is computed, not sampled** — It's deterministic from `age` and uses the same bin boundaries as SCB: 18-24, 25-34, 35-44, 45-54, 55-64, 65-74, 75-85.
3. **Conditional overrides are applied AFTER LLM refinement** — The LLM may adjust probabilities for employment-dependent fields, but the hard constraint (non-employed → "Not Applicable") is enforced post-sampling.
4. **Region uses all 21 Swedish counties** — This is the most verbose field (21 options). The LLM can handle this, but if token usage becomes problematic, counties could be grouped into macro-regions in a future iteration.

---

## Implementation Plan

### Phase 1: Update identity schema
**Goal:** Add all 9 new fields with initial probability distributions

**Tasks:**
- [x] Task 1.1 — Add `region` to Level 1 `origin_geography` with 21 Swedish county probability weights (approximate population-proportional: Stockholm 0.23, Västra Götaland 0.17, Skåne 0.14, etc.)
- [x] Task 1.2 — Add `birth_country_detail` to Level 1 `origin_geography` with 8 categories (Sweden 0.75, Finland 0.03, Iraq 0.03, Syria 0.03, Poland 0.02, Somalia 0.02, Bosnia 0.02, Other 0.10)
- [x] Task 1.3 — Add `civil_status` to Level 2 `family_of_origin` with 4 categories (Single/Never Married 0.35, Married 0.40, Divorced 0.15, Widowed 0.10)
- [x] Task 1.4 — Add `household_size` to Level 2 `family_of_origin` with 4 categories (1 person 0.25, 2 persons 0.30, 3-4 persons 0.30, 5+ persons 0.15)
- [x] Task 1.5 — Add `housing_tenure` to Level 2 `sociological_background` with 4 categories (Owner-occupied 0.35, Bostadsrätt 0.25, Rental 0.35, Other 0.05)
- [x] Task 1.6 — Add `industry_sector` to Level 3 `professional_functional` with 9 categories (Agriculture 0.03, Manufacturing 0.15, Retail & Service 0.20, IT 0.12, Public Admin 0.08, Education 0.12, Healthcare 0.17, Other 0.05, Not Applicable 0.08)
- [x] Task 1.7 — Add `employment_type` to Level 3 `professional_functional` with 6 categories (Permanent FT 0.45, Permanent PT 0.10, Temporary FT 0.08, Temporary PT 0.05, Self-Employed 0.07, Not Applicable 0.25)
- [x] Task 1.8 — Add `income_source` to Level 3 `professional_functional` with 5 categories (Employment 0.55, Business 0.05, Pension 0.20, Social transfers 0.15, Capital 0.05)
- [x] Task 1.9 — Verify all new probability lists sum to 1.0

**Files Modified:**
- `config/assets/identity/sequential/simulation_config_002_swedish.json` — Add 9 new fields across levels 1-3

**Dependencies:** None

### Phase 2: Update identity generator
**Goal:** Handle computed fields and conditional logic

**Tasks:**
- [x] Task 2.1 — Add `age_group` computation after `age` is sampled in `_select_attributes()` (or equivalent): map age to bin using boundaries `[(18,24), (25,34), (35,44), (45,54), (55,64), (65,74), (75,85)]`
- [x] Task 2.2 — Add post-refinement conditional override: if `employment_status != "Employed"`, set `industry_sector = "Not Applicable"` and `employment_type = "Not Applicable"` regardless of sampled value
- [x] Task 2.3 — Add post-refinement conditional override: if `birth_location == "Native (Born in Sweden)"`, set `birth_country_detail = "Sweden"` regardless of sampled value
- [ ] Task 2.4 — Verify LLM probability refinement produces valid distributions with expanded schema (test with 3-5 personas)

**Files Modified:**
- `anxiety_synthetic/patient_generator/identity/identity_generator_sequential.py` (or equivalent path) — Add age_group computation; add conditional override logic after attribute selection

**Dependencies:** Phase 1

### Phase 3: Update comparison extractor
**Goal:** Extract new fields from identity.json for population comparison

**Tasks:**
- [x] Task 3.1 — Add extraction logic for `region` from Level 1 `origin_geography`
- [x] Task 3.2 — Add extraction logic for `birth_country_detail` from Level 1 `origin_geography`
- [x] Task 3.3 — Add extraction logic for `civil_status` from Level 2 `family_of_origin`
- [x] Task 3.4 — Add extraction logic for `household_size` from Level 2 `family_of_origin`
- [x] Task 3.5 — Add extraction logic for `housing_tenure` from Level 2 `sociological_background`
- [x] Task 3.6 — Add extraction logic for `industry_sector`, `employment_type`, `income_source` from Level 3 `professional_functional`
- [x] Task 3.7 — Add extraction for computed `age_group` field
- [x] Task 3.8 — Add normalization for any label differences between persona schema values and comparison format

**Files Modified:**
- `scripts/extract_population_from_pipeline.py` — Add field extraction for 9 new fields + age_group from hierarchical identity.json

**Dependencies:** Phase 2

---

## Testing Plan

### Manual Verification
- [ ] Generate 3-5 personas with sequential processing and inspect `identity.json` — all 9 new fields must be present with valid values from the defined categories
- [ ] Verify `age_group` is present and correctly matches the age (e.g., age 42 → "35-44")
- [ ] Verify a non-employed persona (Student/Retired/Unemployed) has `industry_sector = "Not Applicable"` and `employment_type = "Not Applicable"`
- [ ] Verify a native-born persona has `birth_country_detail = "Sweden"`
- [ ] Verify an immigrant persona has a non-Sweden `birth_country_detail`
- [ ] Run `extract_population_from_pipeline.py` on generated personas — verify all new fields are extracted into the comparison format

### Edge Cases
- [ ] Young persona (age 18-20) with employment_status "Student" — verify industry_sector and employment_type are "Not Applicable"
- [ ] Elderly persona (age 75+) with employment_status "Retired" — verify income_source is plausibly "Pension" (LLM-refined, not forced)
- [ ] Refugee/displaced birth_location — verify birth_country_detail is not forced to "Sweden"
- [ ] Region with very low probability (Gotland 0.6%) — verify it can still be sampled

---

## Documentation Plan

- [ ] Update CLAUDE.md Architecture section to list expanded identity fields
- [ ] Update the identity schema level descriptions in CLAUDE.md if they enumerate fields

---

## Rollback Plan

1. **Schema rollback:** Revert `simulation_config_002_swedish.json` to previous version — existing personas are unaffected (they were generated with the old schema).
2. **Generator rollback:** Remove conditional overrides and age_group computation — generator falls back to processing only existing schema fields.
3. **No data migration needed:** New fields simply won't appear in personas generated with the old schema. Old personas remain valid.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LLM struggles with 21-county region list (too many probability values to refine) | Medium | Medium | Test with small population first; if problematic, group into macro-regions (Norrland/Svealand/Götaland) |
| Conditional overrides conflict with LLM-refined probabilities (LLM sets high probability for an industry sector, but employment_status is "Retired") | Low | High | Overrides are applied AFTER sampling, not during refinement — LLM refinement is advisory only for conditional fields |
| Expanded schema increases LLM token usage significantly | Medium | Low | Region is the largest addition (21 values); monitor total prompt size; all other new fields have ≤9 values |
| Existing field distributions shift due to new context during LLM refinement | Low | Medium | Compare identity distributions before/after adding new fields; verify no statistical drift in existing 6 shared fields |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1: Update schema | Small-Medium | None |
| Phase 2: Update generator | Small | Phase 1 |
| Phase 3: Update extractor | Small | Phase 2 |

---

## References

- Identity schema: `config/assets/identity/sequential/simulation_config_002_swedish.json`
- Sequential generator: `anxiety_synthetic/patient_generator/identity/identity_generator_sequential.py`
- Category mappings (reference for field values): `config/assets/scb_reference/category_mappings.json`
- Population extractor: `scripts/extract_population_from_pipeline.py`
- Related plan: `docs/development/plans/pending/scb-raw-data-output.md` (independent, can be implemented in either order)
- Related active plans: `docs/development/plans/active/scb-population-enrichment.md`, `docs/development/plans/active/swedish-persona-generation.md`
