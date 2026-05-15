# Plan: SCB Population Sex-Conditioning Fixes

**Date:** 2026-05-07
**Author:** Basil
**Status:** In Progress
**Base Branch:** `dev`
**Branch:** `feature/scb-population-modularization`

---

## Overview

Three fields in the SCB population generator lose real conditioning structure because queries combine sexes (`"1+2"`) or parsers discard dimensions the query already captures. This plan fixes these three fields so that education, employment type, and birth country distributions are conditioned on sex (and age group where applicable), improving population realism.

## Problem Statement

The distribution analysis report (`docs/scb_population_distribution_analysis.md`) identified that 4 of 14 SCB fields lose conditioning structure. Three of these are straightforward fixes:

1. **education_by_age** — query has no `Kon` dimension, so education distributions are identical for males and females within each age group. In Sweden, women hold university degrees at higher rates than men in younger cohorts.
2. **employment_type** — both attachment and hours queries use `Kon: ["1+2"]`. The full-time/part-time gender gap is 15-25 percentage points in Sweden.
3. **birth_country_detail** — the query already fetches sex- and age-separated data, but the parser immediately sums it all away. Immigration patterns are strongly cohort-specific (e.g., Syria in younger cohorts).

The fourth field (employment x education correlation) requires finding a different SCB table and is deferred.

## Goals

### In Scope
1. Add sex conditioning to education distributions (query + parser)
2. Add sex conditioning to employment type distributions (query + parser)
3. Preserve age/sex structure in birth country detail distributions (parser only)
4. Update data types and sampling chain to use the new conditioning dimensions

### Out of Scope
- Employment x education cross-tabulation (Priority 1 — requires new SCB table research)
- Industry sector age/sex conditioning (Priority 5 — requires table metadata investigation)
- The 5 "marginal by design" fields (housing, household, socioeconomic, parental, industry)
- Adding new SCB tables or changing table IDs

## Success Criteria

- [ ] `parse_education_by_age` returns `{(age_group, sex) -> {education -> P}}` with distinct distributions for Male vs Female
- [ ] `parse_employment_type_combined` returns `{(age_group, sex) -> {type -> P}}` with distinct distributions for Male vs Female
- [ ] `parse_birth_country_detail` returns `{(age_group, sex) -> {country -> P}}` with distinct distributions across age groups
- [ ] `generate_scb_population.py --n 10000 --seed 1253` runs without errors
- [ ] Summing across the new sex dimension recovers approximately the old marginal distributions
- [ ] No silent fallbacks or hardcoded data introduced

---

## Technical Design

### Approach

Each fix follows the same 4-layer cascade: **query** (fetch_service.py) → **parser** (parsers.py) → **data type** (data.py) → **sampling** (sample_service.py). The pattern is identical to how `civil_status_by_age_sex` already works — keyed on `(age_group, sex)` tuple. We reuse that established pattern.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Per-individual API calls | Maximum conditioning fidelity | 14 API calls × N individuals; no statistical benefit over bulk with correct parsing | Rejected |
| Fix queries + parsers (bulk) | Same fidelity, single API call per table, established pattern | Requires parser rewrites | Chosen |
| Rename fields (e.g., `education_by_age_sex`) | Clearer naming | Unnecessary churn, internal-only types | Rejected |

### Architecture Changes

No new modules or classes. Changes are internal to the existing `scb_population` package:

**Type changes in `PopulationDistributions` dataclass:**
```
education_by_age:       dict[str, dict[str, float]]  →  dict[tuple[str, str], dict[str, float]]
employment_type_by_age: dict[str, dict[str, float]]  →  dict[tuple[str, str], dict[str, float]]
birth_country_detail:   dict[str, float]              →  dict[tuple[str, str], dict[str, float]]
```

The outer key becomes `(age_group, sex)` for all three, matching the existing `civil_status_by_age_sex` pattern.

---

## Implementation Plan

### Phase 0: Metadata Verification
**Goal:** Confirm SCB tables support the dimensions we need before changing queries.
**Started:** 2026-05-07
**Completed:** 2026-05-07

- [x] Task 0.1 — Query metadata for education table (`UF/UF0506/UF0506B/Utbildning`) to confirm `Kon` dimension exists with values `["1", "2"]`
- [x] Task 0.2 — Query metadata for employment attachment table (`AM/AM0401/AM0401I/AKURLSysAnkAr`) to confirm `Kon` supports `["1", "2"]` individually
- [x] Task 0.3 — Query metadata for working hours table (`AM/AM0401/AM0401S/NAKUSysselOkArbtidAr`) to confirm same

**Files Modified:** None (read-only verification using `SCBPxWebClient.get_table_metadata()`)

**Dependencies:** None

**Gate:** If the education table lacks `Kon`, Phase 2 is dropped. If attachment/hours tables don't support split sex, Phase 3 is dropped.

### Phase 1: birth_country_detail — Parser-Only Fix
**Goal:** Preserve the age/sex structure that the query already fetches but the parser currently discards.
**Started:** 2026-05-07
**Completed:** 2026-05-07

- [x] Task 1.1 — Rewrite `parse_birth_country_detail()` to accumulate counts per `(age_group, sex)` instead of summing across all ages/sexes
- [x] Task 1.2 — Add `age_group_map` parameter to parser; pass it from `fetch_birth_country_detail()`
- [x] Task 1.3 — Update `birth_country_detail` field type in `PopulationDistributions` dataclass
- [x] Task 1.4 — Update sampling Step 11 to use `(age_group, biological_sex)` key with fallback

**Files Modified:**
- `anxiety_synthetic/scb_population/parsers.py` — Rewrite `parse_birth_country_detail()` (lines 626-659)
- `anxiety_synthetic/scb_population/fetch_service.py` — Pass `age_group_map` to parser call (line 308-310)
- `anxiety_synthetic/scb_population/data.py` — Update type annotation (line 20)
- `anxiety_synthetic/scb_population/sample_service.py` — Update Step 11 (lines 122-130)

**Dependencies:** None

### Phase 2: education_by_age — Add Sex to Query + Parser
**Goal:** Education distributions conditioned on both age group and sex.
**Started:** 2026-05-07
**Completed:** 2026-05-07

- [x] Task 2.1 — Add `Kon: ["1", "2"]` to the education query in `fetch_education_by_age()`
- [x] Task 2.2 — Rewrite `parse_education_by_age()` to detect sex dimension, iterate over it, and key results on `(age_group, sex)`
- [x] Task 2.3 — Update `education_by_age` field type in `PopulationDistributions` dataclass
- [x] Task 2.4 — Update sampling Step 2 to use `(age_group, biological_sex)` key with fallback
- [x] Task 2.5 — Delete stale education cache files so new query hits the API

**Files Modified:**
- `anxiety_synthetic/scb_population/fetch_service.py` — Add `Kon` to query (lines 42-49)
- `anxiety_synthetic/scb_population/parsers.py` — Rewrite `parse_education_by_age()` (lines 41-80)
- `anxiety_synthetic/scb_population/data.py` — Update type annotation (line 8)
- `anxiety_synthetic/scb_population/sample_service.py` — Update Step 2 (lines 33-41)

**Dependencies:** Phase 0 (education table must support `Kon`)

### Phase 3: employment_type — Split Sex in Queries + Parser
**Goal:** Employment type distributions conditioned on age group and sex.
**Started:** 2026-05-07
**Completed:** 2026-05-07

- [x] Task 3.1 — Change `Kon: ["1+2"]` to `Kon: ["1", "2"]` in both `query_attach` and `query_hours`
- [x] Task 3.2 — Rewrite `parse_employment_type_combined()` to handle sex dimension in both attachment and hours parsing blocks
- [x] Task 3.3 — Update outer-product combination loop to iterate `(age_group, sex)` tuples
- [x] Task 3.4 — Update `employment_type_by_age` field type in `PopulationDistributions` dataclass
- [x] Task 3.5 — Update sampling Step 7 to use `(age_group, biological_sex)` key with fallback
- [x] Task 3.6 — Delete stale attachment and hours cache files

**Files Modified:**
- `anxiety_synthetic/scb_population/fetch_service.py` — Split sex in both queries (lines 204, 216)
- `anxiety_synthetic/scb_population/parsers.py` — Rewrite `parse_employment_type_combined()` (lines 292-431)
- `anxiety_synthetic/scb_population/data.py` — Update type annotation (line 15)
- `anxiety_synthetic/scb_population/sample_service.py` — Update Step 7 (lines 81-93)

**Dependencies:** Phase 0 (tables must support split sex)

---

## Testing Plan

### Manual Verification
- [ ] `python scripts/generate_scb_population.py --n 10000 --seed 1253` completes without errors
- [ ] Inspect parsed education distributions: Male and Female distributions differ within the same age group
- [ ] Inspect parsed employment_type distributions: women show higher part-time rates than men
- [ ] Inspect parsed birth_country_detail distributions: country distributions vary by age group
- [ ] Sum across sex dimension in each distribution and verify marginals approximately match pre-change values

### Integration Tests
- [ ] Run `compare_populations.py` between a pre-change and post-change population to quantify the impact
- [ ] Generate two populations with different seeds and verify both complete successfully

### Edge Cases
- [ ] Age groups near boundaries (18-24, 75-85) have valid distributions
- [ ] Foreign-born individuals (birth_location != "Sweden") correctly sample from age/sex-conditioned country distributions
- [ ] "Not Applicable" employment type still assigned to non-employed individuals
- [ ] Fallback logic triggers correctly when an (age_group, sex) combination is missing

---

## Documentation Plan

- [ ] Update `docs/scb_population_distribution_analysis.md` — mark P2, P3, P4 as resolved
- [ ] Update `docs/scb_population_and_comparison.md` if it references the old distribution types

---

## Rollback Plan

All changes are within the existing feature branch:

1. Each phase can be reverted independently by restoring the 4 modified files to their pre-phase state
2. Cache files: if reverted, old cached responses will still work since they match the old queries
3. No database migrations or breaking external API changes — the individual record dict keys are unchanged

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Education table lacks `Kon` dimension | Medium | Medium | Phase 0 gates this; if absent, check sister tables `UF0506A`/`UF0506C`; drop P3 if none work |
| AKU tables suppress cells for small sex×age×category combinations | Low | Low | Parser already handles `None`/0 values; normalize only over non-zero cells |
| Stale cache serves old responses after query change | Certain | Low | Delete relevant cache files before running with new queries |
| Field type changes break `compare_populations.py` | None | None | Script reads individual dicts by attribute name, not internal distribution types |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 0: Metadata verification | Small | None |
| Phase 1: birth_country_detail | Small | None |
| Phase 2: education_by_age | Medium | Phase 0 |
| Phase 3: employment_type | Medium | Phase 0 |

---

## Deferred Work

The following improvements were identified in the distribution analysis but deferred because they require researching new SCB tables or involve higher uncertainty. They are ordered by expected impact on population realism.

### Priority 1 (Highest Impact): Employment × Education Correlation

**The problem:** The parser at `parsers.py:138` copies the same employment distribution to every education level within each age group:
```python
result[age_group] = {edu: normalized for edu in EDUCATION_LABELS}
```
This destroys the education-employment correlation — one of the strongest statistical relationships in labor economics. University graduates have substantially higher employment rates than those with no formal education, but the current generator treats them identically.

**Why it's hard:** The current employment table (`AM/AM0401/AM0401A/AKURLBefAr`) has no education dimension — it only provides labour status × age × sex. Fixing this requires finding a different SCB table that cross-tabulates education level with employment status (and ideally age and sex). Candidate tables like `AM/AM0401/AM0401B/AKUBefSUNAr` (AKU population by SUN education level) may exist but need metadata verification and new label mappings.

**What the fix would look like:** If a suitable table is found, the parser gets a full rewrite. The data type changes from `dict[str, dict[str, dict[str, float]]]` (age_group → education → status → P, currently fake) to `dict[tuple[str, str], dict[str, dict[str, float]]]` (age_group, sex → education → status → P, with real education conditioning). If no cross-tab table exists, the fallback is to drop the fake education key entirely and condition employment on `(age_group, sex)` only — still an improvement over the current state.

### Priority 5: Industry Sector Age/Sex Conditioning

**The problem:** The industry sector query uses `Kon: ["1+2"]` (combined sexes) and `Alder: ["tot15-74"]` (all ages combined), producing a flat marginal distribution. In reality, industry distribution varies substantially by sex (healthcare skews female, construction skews male) and age.

**Why it's hard:** The table (`AM/AM0401/AM0401I/AKURLSysSNI07Ar`) likely supports age bands and split sex, but AKU survey tables have small samples. A full age × sex × SNI cross-tabulation may produce many suppressed cells (`..`) due to statistical uncertainty. The parser would need to handle sparse data gracefully, and the resulting distributions might be unreliable for narrow demographic slices.

**What the fix would look like:** Change `Kon: ["1+2"]` to `["1", "2"]` and `Alder: ["tot15-74"]` to age bands. Update parser to key on `(age_group, sex)`. If suppression is too severe, fall back to sex-only conditioning (no age).

### Marginal-by-Design Fields (5 fields)

Five fields are sampled as marginals not because of query/parser bugs, but because the current SCB tables don't cross-tabulate the relevant conditioning variables:

| Field | Missing Conditioning | Would Need |
|-------|---------------------|------------|
| socioeconomic | education, employment | SCB table cross-tabulating income by education or employment status |
| parental_structure | age (uses children's data for adults) | Adult family structure table, not child-focused `LE0102` |
| housing_tenure | age, income | SCB table with age or income breakdown for tenure |
| household_size | age, civil status | SCB table with age or civil status breakdown |
| industry_sector | age, sex | See Priority 5 above |

These require dedicated research into the SCB PxWeb table catalog to find suitable alternatives. Each would follow the same query → parser → type → sampling pattern established by this plan.

---

## References

- Analysis report: `docs/scb_population_distribution_analysis.md`
- SCB client: `anxiety_synthetic/utils/scb_client.py`
- Category mappings: `config/assets/scb_reference/category_mappings.json`
