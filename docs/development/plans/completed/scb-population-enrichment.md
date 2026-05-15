# Plan: SCB Population Enrichment

**Date:** 2026-05-06
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/scb-population-comparison`
**Branch:** `feature/scb-population-enrichment`

---

## Overview

Expand the SCB population generator from 10 demographic fields to ~18 by adding characteristics sourced directly from Statistics Sweden's (SCB) PxWeb API. The goal is statistical realism: each generated person should reflect the full breadth of Swedish demographic data available, enabling richer population comparisons. No changes are made to the LLM identity generation pipeline.

## Problem Statement

The current generator models only the most basic demographics (age, sex, education, employment, family, income tier, birth location, environment). Several fields are weak:

- `current_environment_type` is entirely **hardcoded** (40/40/20%) — no SCB data backs it
- `employment_status = Employed` carries no sector or contract-type information
- Marital/cohabitation status, housing tenure, household size, and health-related worklessness are absent

For a population meant to represent Sweden's adult working-age population in an anxiety research context, these gaps limit the realism and comparability of generated cohorts.

## Goals

### In Scope
1. Replace the hardcoded `current_environment_type` with SCB-backed region/county (`region`) data
2. Add at least 6 new SCB-sourced demographic fields to each generated person record
3. Extend `compare_populations.py` to include all new fields in marginal distribution comparisons
4. Update `category_mappings.json` with labels for each new characteristic

### Out of Scope
- Changes to the LLM identity generation pipeline (`simulation_config_001.json`, narrative prompts)
- Changes to `extract_population_from_pipeline.py` (pipeline persona extraction — only needed if personas start emitting the new fields)
- Real-time SCB data (cached 90-day TTL is sufficient)
- Hardcoded statistical distributions of any kind — all probabilities must come from SCB API responses
- Sub-county geographic granularity (municipality-level)

## Success Criteria

- [ ] Every generated person record includes all new fields with no `null` values
- [ ] `current_environment_type` is derived from real SCB regional data, not hardcoded percentages
- [ ] `compare_populations.py` reports marginal distributions for all new fields
- [ ] Spot-checks: `civil_status` distribution matches published SCB figures (e.g. ~45% married among 30-64 age group); `industry_sector` distribution matches ~12% healthcare, ~7% education
- [ ] Employed persons all have an `industry_sector` and `employment_type`; retired/unemployed/student have `Not Applicable`
- [ ] Two independently seeded populations of 10,000 show similar distributions (TV distance < 0.05 per field)

---

## Technical Design

### Approach

Each new characteristic follows the **existing pattern** already established in `generate_scb_population.py`:

1. `fetch_xxx_data()` — calls `scb_client` to fetch and cache a PxWeb table
2. `sample_xxx(person_attrs)` — weighted random draw from the fetched distribution
3. Entry in `category_mappings.json` — maps raw SCB codes to schema labels
4. Field added to `_generate_person()` return dict
5. Column added to the marginal comparison loop in `compare_populations.py`

The **discovery step** for each new field: query `GET /api/v2/sv/ssd/{table_path}` on the SCB PxWeb API to confirm table ID and variable codes before writing the fetch call.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|---|---|---|---|
| Add all fields unconditionally (marginal only) | Simple, uniform implementation | Ignores known real-world correlations (e.g. industry varies by age) | Rejected for high-value conditional fields |
| Conditional sampling for all fields | Most realistic | Complex; some marginal tables don't publish cross-tabs | Conditional only where SCB publishes cross-tab data |
| Replace `current_environment_type` with raw Län (21 counties) | Maximum geographic fidelity | Increases cardinality significantly; harder to compare | Keep both: raw `region` (Län) + derived `current_environment_type` |
| Source non-SCB data (e.g. health registers) | Richer health data | Outside the established SCB client pattern | Out of scope |

### Architecture Changes

No new modules or classes. All additions are new methods on the existing `SCBPopulationGenerator` class in `generate_scb_population.py`. The `category_mappings.json` schema is extended with new top-level keys. `compare_populations.py` needs its field list extended.

---

## New Characteristics

### 1. `region` — County / Län
- **SCB table:** `BE/BE0101/BE0101A/BefolkningNy` with Län dimension (or dedicated regional table)
- **Categories:** 21 Swedish counties (Stockholm, Västra Götaland, Skåne, Uppsala, …)
- **Sampling:** Marginal from population distribution by county
- **Replaces hardcoded:** `current_environment_type` is re-derived using SCB's official H-region or DEGURBA urban/rural classification, fetched from the API — no static percentages

### 2. `civil_status` — Marital / Cohabitation Status
- **SCB table:** `BE/BE0101/BE0101C` or `LE/LE0102` household tables
- **Categories:** Married, Registered partner, Cohabiting (sambo), Single/never married, Divorced, Widowed
- **Sampling:** Conditional on age_group × biological_sex

### 3. `industry_sector` — Occupation / Industry
- **SCB table:** `AM/AM0208` or `NV/NV0109` — employment by SNI2007 classification
- **Categories:** Healthcare & Social, Education, IT & Technology, Manufacturing & Industry, Retail & Service, Public Administration, Agriculture & Forestry, Other
- **Sampling:** Conditional on employment_status (Employed only); others → `Not Applicable`

### 4. `employment_type` — Contract Type
- **SCB table:** AKU survey — permanent vs. temporary, full-time vs. part-time
- **Categories:** Permanent Full-time, Permanent Part-time, Temporary Full-time, Temporary Part-time, Self-Employed
- **Sampling:** Conditional on employment_status (Employed only); others → `Not Applicable`

### 5. `housing_tenure` — Dwelling Ownership
- **SCB table:** `BO/BO0104` — dwelling type / ownership form
- **Categories:** Owner-occupied (villa/house), Tenant-owned apartment (bostadsrätt), Rental apartment, Other
- **Sampling:** Conditional on socioeconomic_class × age_group

### 6. `household_size` — Number of People in Household
- **SCB table:** `LE/LE0102` household composition tables
- **Categories:** 1 person, 2 persons, 3–4 persons, 5+ persons
- **Sampling:** Conditional on parental_structure

### 7. `income_source` — Primary Income Type
- **SCB table:** `HE/HE0110` (already cached) — income breakdown by source already in the table
- **Categories:** Employment income, Business/self-employment, Pension, Social transfers, Capital income
- **Sampling:** Conditional on employment_status × age_group

### 8. `birth_country_detail` — Country of Birth (Detailed)
- **SCB table:** `BE/BE0101/BE0101E/FolkmFodlandHVD` (already cached — more granular breakdown available)
- **Categories:** Sweden, Finland, Iraq, Poland, Syria, Somalia, Bosnia, other top-15 origin countries, Other
- **Sampling:** Conditional on birth_location (non-Sweden persons only get a country assigned)

### 9. `disability_status` — Long-term Sick Leave / Disability
- **SCB table:** `AF/AF0103` or SCB health statistics
- **Categories:** None, Long-term sick leave (>60 days), Registered disability
- **Sampling:** Conditional on age_group × employment_status

---

## Implementation Plan

### Phase 1: Discovery & Region Fix
**Goal:** Confirm all SCB table IDs and fix the hardcoded `current_environment_type`

**Started:** 2026-05-06
**Completed:** 2026-05-06

- [x] Query SCB PxWeb metadata API for each target table to confirm IDs and variable codes
- [x] Implement `fetch_region_data()` and `sample_region()` using real Län distribution
- [x] Derive `current_environment_type` from county density mapping instead of hardcoded 40/40/20
- [x] Add `region` and updated `current_environment_type` mappings to `category_mappings.json`
- [x] Run a 1,000-person test and verify regional distribution matches SCB figures

**Files Modified:**
- `scripts/generate_scb_population.py` — add region fetch/sample, update env_type derivation
- `config/assets/scb_reference/category_mappings.json` — add `region` section and county→env_type mapping

**Dependencies:** None

### Phase 2: Civil Status, Industry, Employment Type
**Goal:** Add the three highest-value new characteristics

**Started:** 2026-05-06
**Completed:** 2026-05-06

- [x] Implement `fetch_civil_status_data()` and `sample_civil_status(age_group, biological_sex)`
- [x] Implement `fetch_industry_sector_data()` and `sample_industry_sector(employment_status, age_group, education_level)`
- [x] Implement `fetch_employment_type_data()` and `sample_employment_type(employment_status)`
- [x] Add all three sections to `category_mappings.json`
- [x] Verify conditional distributions are plausible (married rates rise with age, industry matches sector employment shares)

**Files Modified:**
- `scripts/generate_scb_population.py`
- `config/assets/scb_reference/category_mappings.json`

**Dependencies:** Phase 1

### Phase 3: Housing, Household Size, Income Source, Birth Country Detail
**Goal:** Add remaining characteristics using already-cached or closely related tables

**Started:** 2026-05-06
**Completed:** 2026-05-06

- [x] Implement `fetch_housing_tenure_data()` and `sample_housing_tenure(socioeconomic_class, age_group)`
- [x] Implement `fetch_household_size_data()` and `sample_household_size(parental_structure)`
- [x] Implement `sample_income_source(employment_status, age_group)` from already-cached HE0110 data
- [x] Implement `sample_birth_country_detail(birth_location)` from already-cached BE0101E data
- [x] Add all sections to `category_mappings.json`

**Files Modified:**
- `scripts/generate_scb_population.py`
- `config/assets/scb_reference/category_mappings.json`

**Dependencies:** Phase 1

### Phase 4: Disability Status & Comparison Integration
**Goal:** Add disability/sick-leave field and extend comparison tool to cover all new fields

**Started:** 2026-05-06
**Completed:** 2026-05-06

- [ ] ~~Implement `fetch_disability_data()` and `sample_disability_status(age_group, employment_status)`~~
  **Dropped:** No suitable SCB PxWeb table found. The plan required three categories: "None, Long-term sick leave (>60 days), Registered disability". SCB PxWeb contains `LE/LE0101/LE0101H/LE01012021H02` (disability prevalence %, binary) and `AM/AM0401/AM0401K/NAKUFranvOrsakNAr` (weekly reference-week absence, not long-term), but neither provides the required three-way categorical distribution. Long-term sick-leave data originates from Försäkringskassan (Swedish Social Insurance Agency) and is not published via SCB PxWeb. Per project rules, the field is dropped rather than substituted with hardcoded rates.
- [x] Extend `compare_populations.py` field list to include all 8 implemented new characteristics: `region`, `civil_status`, `industry_sector`, `employment_type`, `housing_tenure`, `household_size`, `income_source`, `birth_country_detail`
- [ ] Run full 10,000-person generation with both seeds and verify comparison report includes all fields
- [ ] Spot-check all new field distributions against published SCB statistics

**Files Modified:**
- `scripts/generate_scb_population.py`
- `config/assets/scb_reference/category_mappings.json`
- `scripts/compare_populations.py`

**Dependencies:** Phases 2 & 3

---

## Testing Plan

### Manual Verification
- [ ] Generate 1,000-person population; confirm every record has all new fields with no `null`
- [ ] Generate 10,000-person population; confirm `industry_sector` distribution: ~12% Healthcare & Social, ~7% Education, ~5% Public Administration (matches SCB employment surveys)
- [ ] Confirm `civil_status` for 45-54 age group: ~55% Married or Cohabiting (matches SCB family statistics)
- [ ] Confirm `housing_tenure` for Poverty class: majority Rental apartment
- [ ] Confirm `region` distribution: Stockholm + Västra Götaland + Skåne account for ~50% of population
- [ ] Confirm employed persons: all have `industry_sector` ≠ `Not Applicable` and `employment_type` ≠ `Not Applicable`
- [ ] Confirm retired persons: `industry_sector = Not Applicable`, `employment_type = Not Applicable`
- [ ] Run comparison between two seeds of 10,000: TV distance < 0.05 for every new field

### Edge Cases
- [ ] Population of 100: all fields populated, no crash on small samples
- [ ] `birth_country_detail` for birth_location = Sweden: value should be "Sweden" for all
- [ ] `income_source` for Poverty class, Retired: should predominantly be Social transfers or Pension

---

## Documentation Plan

- [ ] Update `docs/scb_population_and_comparison.md` with new field descriptions
- [ ] Update `CLAUDE.md` architecture section to list all 18+ fields

---

## Rollback Plan

All changes are additive — new fields are added to the output dict; no existing fields are removed or renamed except `current_environment_type` which is re-derived (same values, different source).

1. If a SCB table is unavailable (API down, table retired), the fetch raises an error — no hardcoded substitution. The cache covers the common case; if the cache is also absent, the script fails loudly with a descriptive message pointing to the missing table.
2. If a characteristic's SCB table cannot be found at all (table retired, no equivalent), that characteristic is dropped from the plan entirely rather than substituted with static values.
3. Git revert of `generate_scb_population.py` restores the 10-field output with zero data loss.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| SCB table ID has changed or been retired | Medium | Medium | Verify all table IDs via metadata API in Phase 1 before writing fetch calls |
| Cross-tab data not published for desired conditioning (e.g. housing by income × age) | Medium | Low | Fall back to marginal distribution if cross-tab unavailable |
| `disability_status` data behind a different API or not in PxWeb | Medium | Low | Find the correct SCB table (e.g. health statistics via AF or HS subject area); if no table exists, drop the field entirely — no hardcoded rates |
| Region mapping county→environment_type is subjective | Low | Low | Use SCB's own DEGURBA / H-region classification where available |
| Large generated JSONs slow down pipeline comparison | Low | Low | No change to sampling loop structure; 18 fields vs 10 is negligible overhead |

---

## References

- Related plan: `docs/development/plans/active/scb-population-comparison.md`
- SCB PxWeb API: used in `anxiety_synthetic/utils/scb_client.py`
- Category mappings: `config/assets/scb_reference/category_mappings.json`
- Comparison tool: `scripts/compare_populations.py`
