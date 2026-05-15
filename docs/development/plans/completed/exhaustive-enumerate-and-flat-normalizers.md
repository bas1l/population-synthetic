# Plan: Exhaustive Enumerate Prompt & Flat Identity Normalizer Expansion

**Date:** 2026-05-09
**Author:** Claude Code
**Status:** In Progress
**Base Branch:** `feature/configurable-identity-pipeline`
**Branch:** `feature/configurable-identity-pipeline`

---

## Overview

Fix two issues that degrade the configurable identity pipeline's demographic fidelity when compared against SCB reference data. First, replace the hardcoded "5-8 candidates" enumerate prompt with an exhaustive enumeration instruction. Second, expand the flat identity normalizers in the extraction pipeline to handle Swedish-language and free-form values that the generative LLM produces.

## Problem Statement

Seed012 (configurable, `generate_evaluate_random_pick`) scores far below seed007 (sequential) on the radar chart comparison against the SCB reference population. Investigation of the 10 generated `identity.json` files reveals two compounding root causes:

1. **Truncated candidate lists:** The enumerate prompt hardcodes "list 5-8 plausible candidates", collapsing multi-option fields (e.g., `region` has 21 counties) to only the most prominent values.

2. **Normalization failures:** The LLM generates free-form values — often in Swedish — that `_extract_flat()` in `extract_population_from_pipeline.py` cannot map to comparison labels. Unlike seed007 (which samples from a fixed vocabulary), seed012's values are unconstrained.

**Observed failures across all 10 seed012 personas (sampled):**

| Field | Example LLM output | Expected label | Result |
|-------|-------------------|----------------|--------|
| `biological_sex` | `"XY"` | `"Male"` | Unknown |
| `employment_status` | `"Heltidsanställd"`, `"Anställd"` | `"Employed"` | Unknown |
| `education_level` | `"Kandidatexamen"`, `"Magisterexamen"`, `"Högskoleexamen"`, `"Gymnasieutbildning"` | `"University Degree"` / `"High School"` | Unknown |
| `civil_status` | `"Skild"`, `"Gift"`, `"Cohabiting"`, `"Separated"` | `"Divorced"`, `"Married"` | Raw passthrough |
| `socioeconomic_class` | `"Medelklass"`, `"Arbetarklass"`, `"Högre medelklass"`, `"Välbärgad frilansare"` | `"Middle Class"`, `"Working Class"` | Unknown |
| `current_environment_type` | `"Förort (Suburb)"`, `"By"`, `"Mindre stad/tätort"` | `"Suburban"`, `"Rural/Countryside"` | Unknown |
| `industry_sector` | `"Finansiella tjänster"`, `"Vård och omsorg"`, `"Detaljhandel"` | `"Retail & Service"`, `"Healthcare/Social Work"` | Unknown |
| `employment_type` | `"Tillsvidareanställning"`, `"Projektanställning"`, `"Ej tillämpligt"` | `"Permanent Full-Time"`, `"Not Applicable"` | Unknown |
| `ethnicity` | `"Chaldean"`, `"Finnish"` | `"Non-European"`, `"Nordic"` | Unknown |
| `birth_location` | `"Bagdad, Irak"`, `"Polen"` | `"Outside Europe"`, `"Europe (Other)"` | Unknown / wrong default |
| `income_source` | `"Kapitalinkomster"`, `"Änkepension"` | `"Capital income"`, `"Pension"` | Wrong default |
| `housing_tenure` | `"Friköpt radhus"` | `"Owner-occupied (villa/house)"` | Unknown |

## Goals

### In Scope
1. Replace "5-8 candidates" with exhaustive enumeration in the configurable identity generator's enumerate prompt
2. Expand `_extract_flat()` normalizers to handle Swedish-language values and free-form phrasing for all 17 compared fields
3. Fix `_normalize_civil_status()` to handle Swedish terms and English variants beyond exact matches
4. Fix `_birth_location_from_flat()` to correctly classify non-Swedish European countries (currently defaults to "Sweden")

### Out of Scope
- Modifying the LLM's system instruction or schema to constrain output vocabulary
- Modifying `_extract_sequential()` or `_extract_batch()` (those work correctly with their respective formats)
- Changing the comparison pipeline (`compare_populations.py`, `StatisticalEvaluator`)
- Adding new comparison dimensions beyond the existing 17

## Success Criteria

- [ ] Enumerate prompt no longer hardcodes candidate count
- [ ] All 10 existing seed012 identities extract without "Unknown" for any of the 17 comparison fields (re-run extraction only, no re-generation needed)
- [ ] `_normalize_civil_status()` correctly maps Swedish terms (`"Skild"`, `"Gift"`, `"Sambo"`) and English variants (`"Cohabiting"`, `"Separated"`)
- [ ] `_birth_location_from_flat()` correctly classifies `"Polen"` as `"Europe (Other)"`, `"Bagdad, Irak"` as `"Outside Europe"`
- [ ] Re-running `compare_pipeline_to_scb.py` on seed012 produces an improved radar chart

---

## Technical Design

### Approach

**Enumerate prompt:** Replace the count constraint with an open-ended exhaustive instruction. The LLM should list all plausible options given the context, not an arbitrary subset.

**Normalizers:** Expand each normalization function in `_extract_flat()` with Swedish-language keyword mappings derived from the actual seed012 outputs. This is a keyword-matching approach — add Swedish terms to the existing `any(k in raw_lower ...)` checks. No structural changes to the normalization pattern.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Expand normalizers with Swedish keywords | Non-invasive, handles existing data, no re-generation needed | Must maintain keyword lists | **Chosen** |
| Constrain LLM to output English-only controlled vocabulary | Eliminates normalization issues at source | Changes generative behavior, limits LLM creativity, doesn't help with existing data | Rejected (per user preference) |
| Use LLM-based normalization (send raw value + target labels, ask LLM to match) | Perfect accuracy | Expensive, adds API calls to extraction pipeline | Rejected |

### Architecture Changes

No new modules or classes. Two files modified:

1. `identity_generator_configurable.py` — prompt text change only
2. `extract_population_from_pipeline.py` — keyword additions to existing normalizer functions + rewrite of `_normalize_civil_status()`

---

## Implementation Plan

### Phase 1: Fix Enumerate Prompt
**Goal:** Remove the 5-8 candidate count constraint

**Tasks:**
- [x] Task 1.1 — Update `_build_enumerate_prompt()` numeric branch: replace `"list 5-8 plausible candidate numbers"` with `"list all plausible candidate numbers"`
- [x] Task 1.2 — Update `_build_enumerate_prompt()` categorical branch: replace `"list 5-8 plausible candidate values"` with `"list an exhaustive set of all plausible candidate values for '{category_name}' given the context. Include every realistic option — do not limit or truncate the list."`

**Files Modified:**
- `anxiety_synthetic/patient_generator/identity/identity_generator_configurable.py` — lines 137-159 (`_build_enumerate_prompt`)

**Dependencies:** None

### Phase 2: Expand Flat Identity Normalizers
**Goal:** Handle Swedish-language and free-form values in all 17 comparison fields

**Tasks:**

- [x] Task 2.1 — `_normalize_education()`: Add Swedish keywords `"kandidat"`, `"magister"`, `"högskolex"`, `"högskole"` → `"University Degree"`; `"gymnasie"` → `"High School (Gymnasieskola)"`

- [x] Task 2.2 — `_normalize_employment()`: Add Swedish keywords `"anställd"`, `"heltid"`, `"deltid"` → `"Employed"`; `"pensionär"`, `"sjukpension"` already partially work (check `"pension"` is there); `"studerande"` → `"Student"`

- [x] Task 2.3 — Rewrite `_normalize_civil_status()`: Currently only handles two exact strings. Expand to keyword-based matching like other normalizers: `"skild"`, `"frånskild"`, `"separated"` → `"Divorced"`; `"gift"`, `"cohabiting"`, `"sambo"` → `"Married"`; `"änka"`, `"änkling"`, `"widow"` → `"Widowed"`; `"singel"`, `"ogift"` → `"Single/Never Married"`

- [x] Task 2.4 — `_normalize_socioeconomic()`: Add Swedish keywords `"medelklass"`, `"övre medelklass"`, `"högre medelklass"`, `"akademiker"` → `"Middle Class"`; `"arbetarklass"`, `"lägre medelklass"` → `"Working Class"`; `"välbärgad"`, `"överklasss"` → `"Wealthy"`; `"fattigdom"` → `"Poverty"`

- [x] Task 2.5 — `_extract_flat()` environment type block: Add Swedish keywords `"förort"`, `"suburb"` (not just `"suburban"`) → `"Suburban"`; `"by"`, `"landsbygd"`, `"tätort"`, `"mindre stad"` → `"Rural/Countryside"` or `"Suburban"` as appropriate; `"storstad"`, `"innerstad"` → `"Urban Metropolis"`. Fix the `"city"` check that incorrectly classifies suburbs containing "city" as Urban Metropolis

- [x] Task 2.6 — `_extract_flat()` industry sector: Add Swedish industry mappings: `"vård"`, `"sjukvård"`, `"omsorg"` → `"Healthcare/Social Work"`; `"finansiell"`, `"bank"` → map to closest label; `"detaljhandel"`, `"handel"` → `"Retail & Service"`; `"utbildning"`, `"forskning"` → `"Education"`; `"offentlig förvaltning"` → `"Public Administration/Defense"`; `"teknik"`, `"it"` → `"IT/Technology"`; `"kultur"`, `"kreativ"` → `"Other Services"`; `"tillverkning"`, `"industri"` → `"Manufacturing/Industry"`

- [x] Task 2.7 — `_extract_flat()` employment type: Add `"tillsvidareanställning"` (without "deltid") → `"Permanent Full-time"`; `"projektanställning"`, `"visstidsanställning"` → `"Temporary Full-time"`; `"konsultanställning"` → `"Permanent Full-time"` or `"Self-Employed"` as appropriate; `"ej tillämpligt"`, `"ej relevant"` → `"Not Applicable"`

- [x] Task 2.8 — `_normalize_ethnicity()`: Add `"finnish"`, `"finsk"` → `"Nordic"`; `"chaldean"`, `"assyrisk"` → `"Non-European"`; `"östeuropeisk"` → `"European"`

- [x] Task 2.9 — `_birth_location_from_flat()`: Add European country names (Swedish and English) that should map to `"Europe (Other)"`: `"polen"`, `"poland"`, `"tyskland"`, `"germany"`, `"frankrike"`, `"france"`, etc. Add non-European indicators: `"irak"`, `"iraq"`, `"syrien"`, `"syria"`, `"somalia"`, `"iran"`, `"afghanistan"`, `"bagdad"`, `"damaskus"`, etc. Fix the default fallback from `"Sweden"` to checking if the value contains a known non-Swedish location first

- [x] Task 2.10 — `_extract_flat()` income source: Add Swedish keywords: `"anställningsinkomst"`, `"lön"` → `"Employment income"`; `"kapitalinkomst"` → `"Capital income"`; `"änkepension"`, `"sjukpension"` → `"Pension"`; `"socialbidrag"`, `"försörjningsstöd"` → `"Social transfers/benefits"`; `"egenföretagare"`, `"egen verksamhet"` → `"Business/self-employment income"`

- [x] Task 2.11 — `_extract_flat()` biological sex: Add `"xy"` → `"Male"`; `"xx"` → `"Female"`; `"man"` (exact, case-insensitive) → `"Male"`; `"kvinna"` → `"Female"`

- [x] Task 2.12 — `_extract_flat()` housing tenure: Add `"friköpt"`, `"äganderätt"` → `"Owner-occupied (villa/house)"`; `"radhus"` as additional indicator for owner-occupied

**Files Modified:**
- `scripts/extract_population_from_pipeline.py` — normalizer functions and `_extract_flat()` inline normalization blocks

**Dependencies:** None (independent of Phase 1)

---

## Testing Plan

### Unit Tests
- [ ] No test suite exists — manual verification only

### Manual Verification
- [ ] Re-run extraction on all 10 existing seed012 identities: `python scripts/extract_population_from_pipeline.py --seed-root <seed012_path> --output data/test_extraction.json`
- [ ] Verify zero "Unknown" values in the 17 comparison fields across all 10 personas
- [ ] Spot-check that Swedish values map to the correct English labels (not just "not Unknown")
- [ ] Re-run comparison: `python scripts/compare_pipeline_to_scb.py --seed-root <seed012_path>`
- [ ] Compare new radar.png against current — all dimensions should improve from the current near-zero values
- [ ] Verify seed007 (sequential format) extraction is unaffected — re-run extraction on seed007 and confirm no regressions

### Edge Cases
- [ ] Mixed-language values like `"Magisterexamen (Master's degree)"` — should match on either language
- [ ] Values with parenthetical qualifiers like `"Employed (full-time)"`, `"Anställd (deltid)"`
- [ ] Swedish-only values with no English equivalent in the string
- [ ] `biological_sex: "XY"` — chromosomal notation
- [ ] `birth_location: "Polen"` — Swedish country name that currently defaults to "Sweden"
- [ ] `current_environment_type: "Suburb of a major city"` — contains "city" substring, must not map to "Urban Metropolis"

---

## Documentation Plan

- [ ] No documentation updates needed — this is an internal normalization fix

---

## Rollback Plan

1. `git checkout HEAD -- anxiety_synthetic/patient_generator/identity/identity_generator_configurable.py` (revert enumerate prompt)
2. `git checkout HEAD -- scripts/extract_population_from_pipeline.py` (revert normalizer changes)
3. No breaking changes to other components

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Swedish keyword list is incomplete — future LLM outputs use terms we didn't anticipate | High | Low | Log warnings for unmapped values; expand iteratively as new terms appear |
| Exhaustive enumerate prompt produces very large candidate lists, increasing token usage | Med | Low | Acceptable tradeoff for better distribution coverage; the evaluate step filters anyway |
| Some Swedish terms are ambiguous across categories (e.g., "vård" could mean different things) | Low | Low | Normalize within field context, not globally |
| The `"city"` substring check for Urban Metropolis produces false positives for suburban/rural locations mentioning a city | High (observed) | Med | Reorder checks: test for "suburb"/"förort" BEFORE testing for "city" |

---

## References

- Parent plan: `docs/development/plans/active/configurable-identity-pipeline.md`
- Generative methods plan: `docs/development/plans/active/generative-identity-methods.md`
- Seed012 manifest: `config/seed_manifests/synthetic_pipeline_config_seed012.yaml`
- Configurable generator: `anxiety_synthetic/patient_generator/identity/identity_generator_configurable.py`
- Extraction pipeline: `scripts/extract_population_from_pipeline.py`
- Comparison pipeline: `scripts/compare_pipeline_to_scb.py`
- Seed012 outputs: `<db_root>/seed_012_generate-evaluate-random-pick-identity/`
