# Plan: SCB Employment × Education Correlation

**Date:** 2026-05-07
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/scb-population-modularization`
**Branch:** `feature/scb-employment-education-correlation`

---

## Overview

The SCB population generator destroys the education–employment correlation by copying the same employment distribution to every education level within each age group. This plan fixes that by finding an SCB table that cross-tabulates employment status with education level, then rewriting the query, parser, data type, and sampling logic so that university graduates have different employment rates than people with no formal education.

## Problem Statement

The parser at `parsers.py:166` does:
```python
result[age_group] = {edu: normalized for edu in EDUCATION_LABELS}
```
This assigns the **identical** employment distribution to all 4 education levels within each age group. The sampling code at `sample_service.py:47` already attempts to condition on `education_level`, but finds the same probabilities regardless.

The root cause: the current employment table `AM/AM0401/AM0401A/AKURLBefAr` has no education dimension — it only provides labour status × age × sex.

Education is one of the strongest predictors of employment status. University graduates in Sweden have substantially higher employment rates than those with no formal education. The current generator treats them identically, reducing population realism.

## Goals

### In Scope
1. Find an SCB table that cross-tabulates employment status with education level (and ideally age and sex)
2. Rewrite the employment query, parser, data type, and sampling logic to use real education-conditioned distributions
3. Condition employment on `(age_group, sex, education_level)` — the full triple
4. Handle AKU cell suppression gracefully

### Out of Scope
- Industry sector age/sex conditioning (Priority 5 — separate plan)
- The 5 "marginal by design" fields (socioeconomic, parental_structure, housing_tenure, household_size, industry_sector)
- Adding new SCB tables for fields other than employment
- Changes to the education query/parser (already fixed in prior work)

## Success Criteria

- [ ] `parse_employment_by_age` returns distributions where "University Degree" and "No Formal Education" have **different** employment probabilities within the same `(age_group, sex)` key
- [ ] `employment_by_age_education` is keyed on `(age_group, sex)` tuples, matching the established `civil_status_by_age_sex` pattern
- [ ] `generate_scb_population.py --n 10000 --seed 1253` runs without errors
- [ ] All employment distributions sum to 1.0
- [ ] No silent fallbacks or hardcoded data introduced
- [ ] Stale cache files cleaned up

---

## Technical Design

### Approach

Replace the current employment table with one that includes an education dimension, then rewrite the 4-layer cascade (query → parser → data type → sampling) following the stride-based pattern already established by `parse_education_by_age` (parsers.py:41–108). The result type changes from `dict[str, dict[str, dict[str, float]]]` (age_group → fake-education → status) to `dict[tuple[str, str], dict[str, dict[str, float]]]` ((age_group, sex) → real-education → status).

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Find cross-tab SCB table | Real education–employment correlation from authoritative data | Requires table research; AKU may have cell suppression | Chosen |
| Hardcode education–employment adjustment factors | No API dependency | Violates "no hardcoded data" constraint; becomes stale | Rejected |
| Drop education key, condition on (age, sex) only | Simpler; still improves over status quo | Loses all education conditioning | Fallback only |
| Per-individual API calls | Maximum conditioning fidelity | 14 API calls × N individuals; no statistical benefit over bulk with correct parsing | Rejected |

### Architecture Changes

No new modules or classes. Changes are internal to the existing `scb_population` package across 5 files.

**Type change in `PopulationDistributions` dataclass:**
```
employment_by_age_education:
  dict[str, dict[str, dict[str, float]]]  →  dict[tuple[str, str], dict[str, dict[str, float]]]
```

The outer key becomes `(age_group, sex)` tuple, the middle key becomes a real education label with genuinely different inner distributions.

---

## Implementation Plan

### Phase 0: Research — Verify Candidate SCB Table
**Goal:** Confirm that an SCB table exists with education × employment × age × sex cross-tabulation.

- [x] Task 0.1 — Query metadata for `AM/AM0401/AM0401B/AKUBefSUNAr` using `SCBPxWebClient.get_table_metadata()`. Inspect whether `Sun2020Niva` (education), `Arbetskraftstillh` (employment status), `Kon` (sex with `["1", "2"]`), and `Alder` (age bands) all exist as dimensions.
- [x] Task 0.2 — If 0.1 fails, browse parent folder `AM/AM0401/AM0401B` and sibling folders (`AM0401C`, `AM0401D`, etc.) to find alternative tables.
- [x] Task 0.3 — Document the exact variable codes, value codes, label texts, content codes, and available years for the chosen table.

**Files Modified:** None (read-only metadata queries)

**Dependencies:** None

**Gate:**

| Outcome | Next Step |
|---------|-----------|
| Table has education × employment × age × sex | Phase 1 (full fix) |
| Table has education × employment × age (no sex) | Phase 1 (adapted — no sex conditioning on employment) |
| No cross-tab table found | Phase 2 (fallback — drop fake education key) |

### Phase 0 Results

**Date completed:** 2026-05-07

#### Task 0.1 — Candidate table `AM/AM0401/AM0401B/AKUBefSUNAr`

The originally hypothesized table does **not exist**. The v1 API returned HTTP 400 for path `AM/AM0401/AM0401B/AKUBefSUNAr`. The `AM0401B` folder contains only working-hours-by-industry tables (e.g., `AKURLAtSNI07Ar`), not education-related tables. The hypothesized variable code `Sun2020Niva` does not appear in any AKU table; the actual education variable code used by AKU/BAS is `UtbildningsNiva`.

#### Task 0.2 — Exhaustive search of AM0401 and AM0210

Browsed the complete AM0401 (Labour Force Surveys) folder tree and AM0210 (Population by Labour Market Status / BAS) folder tree. Key folders explored:

| Folder | Description | Education dimension? |
|--------|-------------|---------------------|
| `AM0401A` | Population by labour status (current table) | No |
| `AM0401B` | Hours worked by industry | No |
| `AM0401I` | Employed persons | No |
| `AM0401J` | Employees | Not explored (irrelevant) |
| `AM0401K` | Persons absent from work | Not explored (irrelevant) |
| `AM0401L` | Unemployed persons | Not explored (irrelevant) |
| `AM0401M` | Persons not in labour force | Not explored (irrelevant) |
| `AM0401N` | Regional data | No |
| **`AM0401P`** | **Level and field of Education** | **Yes** |
| `AM0401Q` | Civil status and children | No |
| `AM0401R` | Born in Sweden / Foreign-born | Yes (+ education, no age) |
| `AM0401S` | Hours worked | No |
| `AM0401U` | NEET (young people) | No |
| `AM0401V` | Older people | No |
| **`AM0210A`** | **BAS — Preliminary monthly** | **Yes (broad age only)** |
| `AM0210C` | BAS — Final monthly | No |
| `AM0210D` | BAS — Final annual | No |
| `AM0210F` | BAS — Employed, final annual | Yes (no age) |
| `AM0210G` | BAS — DeSO/RegSO | No |
| `AM0207H` | RAMS 2004-2018 | No |
| `AM0207Z` | RAMS 2019-2021 | No |
| `AM0208A` | Occupational Register | No |
| `UF0506B` | Educational attainment | No employment dimension |

**Two tables with education × employment were found:**

**1. `AM/AM0401/AM0401P/NAKUBefUtbNivAr` (LFS, recommended)**
- Title: "Population aged 15-74 (AKU) by labour status, level of education and sex"
- Has: `Arbetskraftstillh` × `UtbildningsNiva` × `Kon` — **no age dimension**
- Years: 2005–2025
- Source: Labour Force Survey (AKU) — same source as current employment table

**2. `AM/AM0210/AM0210A/ArbStatusUtbM` (BAS register, not recommended)**
- Title: "Labour market status by region, sex, age, level of education and region of birth"
- Has: `UtbildningsNiva` × `Kon` × `Alder` × `Region` × `Fodelseregion`
- But `Alder` only has 3 broad ranges: `["20-64", "20-65", "20-66"]` — no granular age bands
- Monthly only (no annual), preliminary statistics, data from 2020M01
- Different source (BAS register) than the current employment table (AKU survey)

**No table found anywhere in SCB** that cross-tabulates employment status × education level × granular age bands (e.g., 15-24, 25-34, ...) × sex.

#### Task 0.3 — Chosen table metadata: `NAKUBefUtbNivAr`

**Table path:** `AM/AM0401/AM0401P/NAKUBefUtbNivAr`

**Variable: `Arbetskraftstillh`** (labour status)

| Value | English label | Swedish label |
|-------|--------------|---------------|
| `TOTALT` | total | totalt |
| `ALÖS` | unemployed | arbetslösa |
| `EIAKR` | not in the labour force | ej i arbetskraften |
| `SYS` | employed | sysselsatta |

**Variable: `UtbildningsNiva`** (level of education)

| Value | English label | Swedish label |
|-------|--------------|---------------|
| `TOTALT` | All educational levels | samtliga utbildningsnivåer |
| `21` | primary and lower secondary education | förgymnasial utbildning |
| `3+4` | upper secondary education | gymnasial utbildning |
| `8` | post secondary education | eftergymnasial utbildning |
| `US` | no information about level of educational attainment | uppgift om utbildningsnivå saknas |

**Variable: `Kon`** (sex)

| Value | English label |
|-------|--------------|
| `1` | men |
| `2` | women |
| `1+2` | total |

**Variable: `ContentsCode`** (observations)

| Value | English label | Swedish label |
|-------|--------------|---------------|
| `AM0401VP` | Thousands | 1000-tal |
| `AM0401VQ` | Margin of error +/-, 1000s | Felmarginal +/-, 1000-tal |
| `AM0401VR` | Percent | Procent |
| `AM0401VS` | Margin of error +/-, percent | Felmarginal +/-, procent |

**Variable: `Tid`** (year)
- Values: `2005` through `2025` (21 years)
- Use `2025` for latest data

**Note on education level codes:** The AKU table uses different education codes than the current education table (`UF0506B/Utbildning`). The education table uses SUN 2020 single-digit codes (`1`–`7`, `US`), while the AKU table uses grouped codes (`21`, `3+4`, `8`, `US`). A mapping from these grouped AKU codes to the 4 internal `EDUCATION_LABELS` will be needed in `category_mappings.json`.

**Proposed AKU education → internal label mapping:**

| AKU code | AKU label | Internal label |
|----------|-----------|----------------|
| `21` | primary and lower secondary education | No Formal Education |
| `3+4` | upper secondary education | High School (Gymnasieskola) |
| `8` | post secondary education | University Degree |
| `US` | no information | (distribute proportionally or drop) |

Note: The AKU table has 3 real education levels vs. the 4 internal labels. There is no direct AKU equivalent for "Vocational (Yrkeshogskola)". The implementation will need to either: (a) merge Vocational into the nearest AKU group, or (b) use the AKU `8` code (post-secondary) for both Vocational and University Degree with the same distribution.

#### Gate outcome

**Outcome: Table has education × employment × sex, but NO age dimension.**

This does not match any of the three pre-defined gate outcomes exactly. It is closest to the second row ("Table has education × employment × age (no sex)") but inverted — we have sex but not age.

**Recommendation:** Proceed with a **modified Phase 1**:
- Use `NAKUBefUtbNivAr` for education-conditioned employment distributions
- Condition on `(sex, education_level)` — genuinely different employment rates per education level and sex
- For age conditioning, keep the existing `AKURLBefAr` table for age-only marginals
- The implementation can combine both tables: use the AKU education table for the education×sex factor, and apply it as a correction to the age-specific marginals from the existing table
- Alternatively, use the education×sex table directly without age conditioning on the employment dimension — this is still a major improvement over the current approach where all education levels get identical distributions

### Phase 1: Implementation (if suitable table found)
**Goal:** Employment distributions genuinely conditioned on education level, age group, and sex.

- [x] Task 1.1 — Add `EMPLOYMENT_BY_EDUCATION_TABLE` constant in `constants.py` with the table path from Phase 0
- [x] Task 1.2 — Update `employment_by_age_education` type in `data.py` from `dict[str, ...]` to `dict[tuple[str, str], ...]`
- [x] Task 1.3 — Rewrite `fetch_employment_by_age()` in `fetch_service.py`: switch to new table, add `Sun2020Niva` dimension, change `Kon: ["1+2"]` to `["1", "2"]`, pass `education_mappings` to parser
- [x] Task 1.4 — Rewrite `parse_employment_by_age()` in `parsers.py`: stride-based flat indexing over 4 dimensions (employment × education × age × sex), accumulate into `{(age_group, sex): {education: {status: count}}}`, normalize, handle `".."` cell suppression
- [x] Task 1.5 — Update Step 3 sampling in `sample_service.py`: lookup `(age_group, biological_sex)` then `education_level`, with fallback chain (try other sex → try other age groups → raise)
- [x] Task 1.6 — Add education label mappings in `category_mappings.json` if the AKU table uses different label text than `sun2020_level_mappings`
- [x] Task 1.7 — Delete stale employment cache files from `config/assets/scb_cache/`

**Files Modified:**
- `anxiety_synthetic/scb_population/constants.py` — Add table constant
- `anxiety_synthetic/scb_population/data.py` (line 9) — Update type annotation
- `anxiety_synthetic/scb_population/fetch_service.py` (lines 62–80) — New query + education_mappings param
- `anxiety_synthetic/scb_population/parsers.py` (lines 111–168) — Full parser rewrite
- `anxiety_synthetic/scb_population/sample_service.py` (lines 46–55) — Update Step 3 lookup + fallback
- `config/assets/scb_reference/category_mappings.json` — Possibly add AKU education label mappings

**Dependencies:** Phase 0

### Phase 1 Results

**Date completed:** 2026-05-07

#### Deviations from original plan

The original plan assumed an education x employment x age x sex table would be found. Phase 0 revealed that the best available table (`NAKUBefUtbNivAr`) has **no age dimension** -- it covers ages 15-74 as a single group. The implementation was adapted accordingly:

- **Field renamed:** `employment_by_age_education` -> `employment_by_sex_education` to reflect the actual conditioning dimensions (sex and education, not age).
- **Type changed to:** `dict[str, dict[str, dict[str, float]]]` keyed as `sex_label` -> `education_label` -> `employment_status` -> probability. This is a simpler nesting than the original plan's `dict[tuple[str, str], dict[str, dict[str, float]]]` because age is no longer a dimension.
- **Function renamed:** `fetch_employment_by_age()` -> `fetch_employment_by_sex_education()` and `parse_employment_by_age()` -> `parse_employment_by_sex_education()`.
- **Vocational fallback:** "Vocational (Yrkeshogskola)" has no AKU equivalent. The sampling code falls back to the "University Degree" distribution (both are post-secondary education), with a clear comment explaining the rationale.
- **Sampling fallback chain:** sex -> vocational-to-university -> opposite sex -> raise. No age fallback needed since the table is age-agnostic.

#### Files modified

| File | Change |
|------|--------|
| `anxiety_synthetic/scb_population/constants.py` | Added `EMPLOYMENT_BY_EDUCATION_TABLE` constant |
| `anxiety_synthetic/scb_population/data.py` | Renamed field to `employment_by_sex_education`, updated type |
| `anxiety_synthetic/scb_population/fetch_service.py` | Replaced `fetch_employment_by_age()` with `fetch_employment_by_sex_education()`, updated imports and `load_all()` |
| `anxiety_synthetic/scb_population/parsers.py` | Replaced `parse_employment_by_age()` with `parse_employment_by_sex_education()` using stride-based indexing, removed unused `EDUCATION_LABELS` import |
| `anxiety_synthetic/scb_population/sample_service.py` | Rewrote Step 3 to use sex+education lookup with vocational fallback chain |
| `config/assets/scb_reference/category_mappings.json` | Added `aku_education_label_mappings` section under `employment` |
| `config/assets/scb_cache/data_AM_AM0401_AM0401A_AKURLBefAr_*.json` | Deleted stale cache file |

#### Note on Phase 2

Phase 2 (fallback -- drop fake education key) was **not needed** because Phase 1 succeeded with the `NAKUBefUtbNivAr` table. The employment distribution now genuinely varies by education level and sex.

### Phase 2: Fallback (if no cross-tab table exists)
**Goal:** Remove the fake education duplication; condition employment on `(age_group, sex)` only.

- [ ] Task 2.1 — Rename field `employment_by_age_education` → `employment_by_age_sex` in `data.py` with type `dict[tuple[str, str], dict[str, float]]`
- [ ] Task 2.2 — Update parser: keep existing table, change `Kon: ["1+2"]` to `["1", "2"]`, remove line 166 education duplication, return `{(age_group, sex): {status: P}}`
- [ ] Task 2.3 — Update sampling: lookup becomes `distributions.employment_by_age_sex.get((age_group, biological_sex), {})`
- [ ] Task 2.4 — Rename references in `load_all()` in `fetch_service.py` and `PopulationDistributions` constructor

**Files Modified:**
- `anxiety_synthetic/scb_population/data.py` — Rename field + change type
- `anxiety_synthetic/scb_population/parsers.py` — Simplify parser
- `anxiety_synthetic/scb_population/fetch_service.py` — Split sex in query, rename variable
- `anxiety_synthetic/scb_population/sample_service.py` — Simplified lookup

**Dependencies:** Phase 0 (only if Phase 1 is not viable)

---

## Testing Plan

### Manual Verification
- [ ] `python scripts/generate_scb_population.py --n 10000 --seed 1253` completes without errors
- [ ] Inspect parsed distributions: "University Degree" and "No Formal Education" produce different employment probabilities within the same `(age_group, sex)` key
- [ ] Within the same education level and age group, male and female employment rates differ
- [ ] Sum across sex dimension recovers approximately the old marginal distributions

### Integration Tests
- [ ] Run `compare_populations.py` between a pre-change and post-change population to quantify the impact
- [ ] Generate two populations with different seeds — both complete successfully

### Edge Cases
- [ ] Age groups near boundaries (18–24, 65–74) have valid distributions
- [ ] AKU cell suppression (`".."`) handled without silent fallback — suppressed cells treated as zero, fully-suppressed subgroups skipped with fallback chain
- [ ] All inner employment distributions sum to 1.0 (normalization check)
- [ ] Fallback logic triggers correctly when an `(age_group, sex)` combination is missing

---

## Documentation Plan

- [ ] Update `docs/development/plans/active/scb-population-sex-conditioning.md` — mark Priority 1 as resolved in the Deferred Work section
- [ ] Update `docs/scb_population_distribution_analysis.md` — mark `employment_by_age` as resolved in the prioritized improvements table

---

## Rollback Plan

All changes are within the feature branch:

1. Each phase can be reverted independently by restoring the modified files to their pre-phase state
2. Cache files: if reverted, old cached responses still work since they match the old queries. New table path produces a different cache key, so old and new don't collide.
3. No database migrations or breaking external API changes — the individual record dict keys (`employment_status`, `education_level`) are unchanged

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `AM0401B/AKUBefSUNAr` does not exist or lacks education dimension | Medium | High | Phase 0 gates this; browse sibling folders; fall to Phase 2 if nothing found |
| AKU table uses different education label text than education table | Medium | Low | Create new mappings in `category_mappings.json` from Phase 0 metadata |
| Severe cell suppression for small education × age × sex × employment cells | Medium | Medium | Treat `".."` as zero; skip fully-suppressed subgroups; sampling fallback chain |
| Table only has data up to 2024 (not 2025) | Low | Low | Use 2024 data; AKU tables often lag 6–12 months |
| Old cache files serve stale responses | Low | Low | Different table path = different cache key; delete old cache explicitly |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 0: Research | Small | None |
| Phase 1: Implementation | Medium | Phase 0 |
| Phase 2: Fallback | Small | Phase 0 (only if Phase 1 not viable) |

---

## References

- Distribution analysis: `docs/scb_population_distribution_analysis.md`
- Verification report: `docs/scb_population_distribution_analysis_verification.md`
- Parent plan (sex-conditioning): `docs/development/plans/active/scb-population-sex-conditioning.md`
- Reference parser implementation: `anxiety_synthetic/scb_population/parsers.py:41–108` (`parse_education_by_age`)
- SCB client: `anxiety_synthetic/utils/scb_client.py`
- Category mappings: `config/assets/scb_reference/category_mappings.json`
