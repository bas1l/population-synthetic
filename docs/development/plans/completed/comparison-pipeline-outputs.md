# Plan: Comparison Pipeline — Outputs

**Date:** 2026-05-08
**Author:** Basil
**Status:** Completed
**Completed:** 2026-05-09 09:47
**Base Branch:** `feature/persona-scb-field-alignment`
**Branch:** `feature/comparison-pipeline-outputs`

---

## Overview

Build tooling to statistically compare pipeline-generated persona demographics against SCB reference populations, producing JSON reports, CSV summaries, and visual bar charts. Three scripts exist but label mismatches between the pipeline identity schema, the extraction layer, and the SCB normalization framework make cross-population comparisons unreliable — fixing this alignment is the core prerequisite.

## Problem Statement

The generation pipeline produces persona identities with demographic fields (education, employment, region, etc.) using label strings defined in the identity schema config. The SCB population generator produces statistically sampled profiles using label strings from `category_mappings.json`. When these two populations are compared, label mismatches cause fields to appear entirely divergent (0% coherence) even when the underlying distributions are similar. Without reliable comparison, there is no quantitative feedback loop to validate that the pipeline produces demographically realistic personas.

## Goals

### In Scope
1. Fix label alignment between all three systems (pipeline schema → extract script → SCB normalization) for all 18 demographic attributes
2. Bring batch extractor to parity with sequential extractor (add 8 missing fields)
3. Add CSV summary export to comparison reports
4. Add visual side-by-side bar chart comparisons per attribute

### Out of Scope
- Changing the pipeline identity schema labels themselves (those are defined in `simulation_config_002_swedish.json` and managed by the `persona-scb-field-alignment` feature)
- Changing SCB `category_mappings.json` schema labels (those are the canonical reference)
- Adding new statistical tests beyond what `compare_populations.py` already computes
- Automated CI comparison runs

## Success Criteria

- [ ] Running `compare_pipeline_to_scb.py` against a pipeline seed with 50+ personas produces a coherence score > 0% (currently 0% due to label mismatches)
- [ ] All 18 demographic attributes show non-NaN chi-squared p-values when comparing SCB-vs-pipeline populations
- [ ] CSV summary file is written alongside every JSON comparison report
- [ ] PNG bar charts are generated for each attribute under `data/analysis/<comparison_stem>/`
- [ ] Batch-format identities extract all 17 demographic fields (same as sequential)

---

## Technical Design

### Approach

The extract script (`extract_population_from_pipeline.py`) is the translation layer between pipeline identity output and the comparison framework. It must normalize pipeline label strings to match the SCB schema labels produced by `normalize_scb_to_schema` in `compare_populations.py`. The fix is to add normalization functions for the 8 fields that currently pass through raw, and correct the existing normalization targets for fields like `birth_location` where the extract script's labels match neither source.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Fix in extract script (normalize pipeline → SCB labels) | Single translation layer, SCB labels stay canonical | Extract script grows more complex | **Chosen** |
| Fix in compare_populations.py (fuzzy matching at comparison time) | No changes to extract script | Comparison logic becomes fragile, hard to debug mismatches | Rejected |
| Change pipeline identity schema labels to match SCB | Eliminates translation entirely | Breaks existing generated personas, couples pipeline to SCB vocabulary | Rejected |

### Architecture Changes

No new modules. Changes are contained within existing scripts:

```
scripts/
├── extract_population_from_pipeline.py  — Add/fix normalization for 10 fields
├── compare_populations.py               — Add CSV export, add chart generation
└── compare_pipeline_to_scb.py           — Wire CSV/chart options through CLI
```

### Label Alignment Reference

Fields are categorized by their current alignment status across three systems:

**Pipeline identity schema** = labels in `config/assets/identity/simulation_config_002_swedish.json`
**Extract script** = normalization targets in `scripts/extract_population_from_pipeline.py`
**SCB framework** = schema labels produced by `normalize_scb_to_schema` via `config/assets/scb_reference/category_mappings.json`

#### Aligned fields (no changes needed)

| Field | Shared labels |
|-------|--------------|
| `education_level` | `No Formal Education`, `High School (Gymnasieskola)`, `Vocational (Yrkeshogskola)`, `University Degree` |
| `employment_status` | `Employed`, `Unemployed`, `Student`, `Retired` |
| `socioeconomic_class` | `Poverty`, `Working Class`, `Middle Class`, `Wealthy` |
| `household_size` | `1 person`, `2 persons`, `3-4 persons`, `5+ persons` |
| `biological_sex` | `Male`, `Female` |
| `age` / `age_group` | Integer → bucketed (`18-24`, `25-34`, ..., `75+`) — same logic in both systems |
| `ethnicity` | Derived from `birth_location` in both systems: `Swedish`, `Nordic`, `European`, `Non-European` |
| `region` | 21 Swedish county names — pass-through, same strings |

#### Mismatched fields (require normalization fixes)

| Field | Pipeline schema | Extract script (current) | SCB framework (target) | Fix needed |
|-------|----------------|--------------------------|------------------------|------------|
| `birth_location` | `Native (Born in Sweden)`, `International Immigrant`, `Domestic Migrant`, `Refugee/Displaced` | `Sweden`, `Nordic Countries`, `EU/Europe`, `Non-EU` | `Sweden`, `Nordic Country`, `Europe (Other)`, `Outside Europe` | Update extract targets to match SCB; update keyword matching |
| `parental_structure` | `Two Parents (Intact)`, `Single Parent (Mother)`, `Single Parent (Father)`, `Divorced/Split Household`, `Adoptive/Foster Care`, `Orphaned/Ward of State` | `Nuclear Family`, `Single Parent`, `Couple without children`, `Living Alone` | `Nuclear Family`, `Single Parent`, `Couple without Children`, `Living Alone` | Fix casing (`children` → `Children`); verify collapse mapping covers all 6 pipeline variants |
| `civil_status` | `Single/Never Married`, `Married/Cohabiting`, `Divorced/Separated`, `Widowed` | Pass-through (no normalization) | `Single/Never Married`, `Married`, `Divorced`, `Widowed` | Add normalizer: `Married/Cohabiting` → `Married`, `Divorced/Separated` → `Divorced` |
| `industry_sector` | `Agriculture/Forestry/Fishing`, `Manufacturing/Industry`, `Retail & Service`, `IT/Technology`, `Public Administration/Defense`, `Education`, `Healthcare/Social Work`, `Other Services`, `Not Applicable` | Pass-through | `Agriculture & Forestry`, `Manufacturing & Industry`, `Retail & Service`, `IT & Technology`, `Public Administration`, `Education`, `Healthcare & Social`, `Other`, `Not Applicable` | Add normalizer mapping pipeline labels → SCB labels |
| `employment_type` | `Permanent Full-Time`, `Permanent Part-Time`, `Temporary Full-Time`, `Temporary Part-Time`, `Self-Employed/Freelance`, `Not Applicable` | Pass-through | `Permanent Full-time`, `Permanent Part-time`, `Temporary Full-time`, `Temporary Part-time`, `Self-Employed`, `Not Applicable` | Add normalizer: fix capitalization (`-Time` → `-time`), trim `/Freelance` |
| `income_source` | `Employment income`, `Business/self-employment income`, `Pension`, `Social transfers/benefits`, `Capital income` | Pass-through | `Employment income`, `Business/self-employment`, `Pension`, `Social transfers`, `Capital income` | Add normalizer: trim trailing words (`income`, `/benefits`) |
| `housing_tenure` | `Owner-occupied (villa/house)`, `Bostadsrätt (cooperative apartment)`, `Rental apartment`, `Other` | Pass-through | `Owner-occupied (villa/house)`, `Tenant-owned apartment (bostadsrätt)`, `Rental apartment`, `Other` | Add normalizer: `Bostadsrätt (cooperative apartment)` → `Tenant-owned apartment (bostadsrätt)` |
| `birth_country_detail` | `Sweden`, `Finland`, `Iraq`, `Syria`, `Poland`, `Somalia`, `Bosnia and Herzegovina`, `Other` | Pass-through | `Sweden`, `Finland`, `Iraq`, `Syria`, `Poland`, `Somalia`, `Bosnia`, `Other` | Add normalizer: `Bosnia and Herzegovina` → `Bosnia` |
| `current_environment_type` | `Urban Metropolis`, `Suburban`, `Rural/Countryside`, `Nomadic` | `Urban Metropolis`, `Suburban`, `Rural/Countryside` | `Urban Metropolis`, `Suburban`, `Rural/Countryside` | Minor: handle `Nomadic` → `Rural/Countryside` fallback |

---

## Implementation Plan

### Phase 1: Label alignment in extract script
**Started:** 2026-05-08
**Completed:** 2026-05-08
**Goal:** Make `extract_population_from_pipeline.py` produce labels that exactly match the SCB schema so statistical comparisons are meaningful.

**Tasks:**
- [x] 1.1 — Update `BIRTH_LOCATION_LABELS` to `["Sweden", "Nordic Country", "Europe (Other)", "Outside Europe"]` and fix `_normalize_birth_location` keyword mapping accordingly
- [x] 1.2 — Fix `PARENTAL_STRUCTURE_LABELS` casing: `"Couple without children"` → `"Couple without Children"`
- [x] 1.3 — Add `_normalize_civil_status(raw)` — map `Married/Cohabiting` → `Married`, `Divorced/Separated` → `Divorced`, pass through `Single/Never Married` and `Widowed`
- [x] 1.4 — Add `_normalize_industry_sector(raw)` — map each pipeline label to its SCB equivalent (slash→ampersand, trim suffixes)
- [x] 1.5 — Add `_normalize_employment_type(raw)` — fix `-Time` → `-time` capitalization, `Self-Employed/Freelance` → `Self-Employed`
- [x] 1.6 — Add `_normalize_income_source(raw)` — trim `income` suffix from `Business/self-employment income`, trim `/benefits` from `Social transfers/benefits`
- [x] 1.7 — Add `_normalize_housing_tenure(raw)` — map `Bostadsrätt (cooperative apartment)` → `Tenant-owned apartment (bostadsrätt)`
- [x] 1.8 — Add `_normalize_birth_country_detail(raw)` — map `Bosnia and Herzegovina` → `Bosnia`
- [x] 1.9 — Add `_normalize_environment(raw)` fallback for `Nomadic` → `Rural/Countryside`
- [x] 1.10 — Wire all new normalizers into `_extract_sequential` for the 8 fields that currently pass through raw
- [x] 1.11 — Update `ETHNICITY_LABELS` derivation to use the corrected `BIRTH_LOCATION_LABELS`

**Files Modified:**
- `scripts/extract_population_from_pipeline.py` — Add normalization constants and functions, wire into `_extract_sequential`

**Dependencies:** None

### Phase 2: Batch extractor parity
**Started:** 2026-05-08
**Completed:** 2026-05-08
**Goal:** `_extract_batch` extracts the same 17 fields as `_extract_sequential`, so batch-format identities can be compared too.

**Tasks:**
- [x] 2.1 — Add keyword-scanning extraction for the 8 missing fields in `_extract_batch`: `region`, `birth_country_detail`, `civil_status`, `household_size`, `housing_tenure`, `industry_sector`, `employment_type`, `income_source`
- [x] 2.2 — Apply the same normalization functions from Phase 1 to the batch-extracted values

**Files Modified:**
- `scripts/extract_population_from_pipeline.py` — Extend `_extract_batch` return dict and scanning logic

**Dependencies:** Phase 1

### Phase 3: CSV summary output
**Started:** 2026-05-08
**Completed:** 2026-05-08
**Goal:** Every comparison report includes a `.csv` for quick scanning in spreadsheets.

**Tasks:**
- [x] 3.1 — Add `write_csv_summary(report, output_path)` function to `compare_populations.py` that writes one row per attribute with columns: `attribute`, `chi_sq_p`, `kl_divergence`, `tv_distance`, `max_diff`, `unmapped_categories`
- [x] 3.2 — Call `write_csv_summary` from `main()` in `compare_populations.py`, deriving the CSV path from the JSON output path (same stem, `.csv` suffix)
- [x] 3.3 — Wire through `compare_pipeline_to_scb.py` so it also produces the CSV

**Files Modified:**
- `scripts/compare_populations.py` — Add `write_csv_summary`, call from `main()`
- `scripts/compare_pipeline_to_scb.py` — Ensure CSV is produced when calling evaluator

**Dependencies:** None (can be done in parallel with Phase 1)

### Phase 4: Visual comparison outputs
**Started:** 2026-05-08
**Completed:** 2026-05-08
**Goal:** Generate side-by-side bar charts per demographic attribute comparing pop_a vs pop_b distributions.

**Tasks:**
- [x] 4.1 — Add `plot_comparison_charts(pop_a, pop_b, output_dir)` to `compare_populations.py` that produces one PNG per attribute under `output_dir/`
- [x] 4.2 — Use vertical grouped bars for most fields; horizontal grouped bars for high-cardinality fields (`region`, `industry_sector`, `employment_type`, `housing_tenure`, `birth_country_detail`) — matching the pattern in `analyze_scb_population.py`
- [x] 4.3 — Add `--charts-dir` CLI flag to both `compare_populations.py` and `compare_pipeline_to_scb.py` (default: `data/analysis/<comparison_stem>/`)
- [x] 4.4 — Add `--no-charts` flag to skip chart generation

**Files Modified:**
- `scripts/compare_populations.py` — Add plotting function and CLI flags
- `scripts/compare_pipeline_to_scb.py` — Wire chart CLI flags through
- `scripts/analyze_scb_population.py` — Reference only (read existing plot patterns)

**Dependencies:** None (can be done in parallel with Phase 1)

---

## Testing Plan

### Manual Verification
- [ ] Generate an SCB population (`scripts/generate_scb_population.py --n 1000 --seed 42`) and run `compare_pipeline_to_scb.py` against a pipeline seed with 50+ personas — verify coherence > 0%, all marginals have non-NaN p-values
- [ ] Inspect the extracted pipeline population JSON — verify no `Unknown` values for fields that have normalization functions
- [ ] Confirm CSV output matches JSON report values (spot-check 3 fields)
- [ ] Open generated PNG charts and verify both populations appear side-by-side with correct legend labels

### Edge Cases
- [ ] Pipeline persona with `employment_status=Retired` should have `industry_sector=Not Applicable` and `employment_type=Not Applicable` — verify these are extracted correctly and not flagged as unmapped
- [ ] Pipeline persona with `birth_location=Refugee/Displaced` — verify it maps to `Outside Europe` (SCB schema)
- [ ] Batch-format identity with minimal text — verify graceful fallback to `Unknown` for fields not found
- [ ] Comparison where one population is much smaller (n=5 vs n=10000) — verify warning is printed and p-values are still computed

---

## Documentation Plan

- [ ] Update `CLAUDE.md` Architecture > SCB Population section to mention comparison scripts and their purpose
- [ ] Add usage examples for `compare_pipeline_to_scb.py` to `CLAUDE.md` Commands section

---

## Rollback Plan

All changes are additive — normalization functions are new, CSV/chart outputs are new files. Rollback is a branch revert (`git revert` or `git reset`). No data migrations or breaking interface changes.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LLM produces label strings not covered by normalization keywords | Medium | Medium | Log unmapped values as warnings; review after first full pipeline run |
| Batch extractor keyword scanning produces false positives for new fields | Low | Low | Batch format is secondary (sequential is the production path); review manually |
| matplotlib chart generation adds heavy dependency | Low | Low | Already a dependency via `analyze_scb_population.py` |

---

## File Inventory

| File | Role |
|------|------|
| `scripts/extract_population_from_pipeline.py` | **Modified** — Add/fix normalization for 10 fields, extend batch extractor |
| `scripts/compare_populations.py` | **Modified** — Add CSV export, add chart generation |
| `scripts/compare_pipeline_to_scb.py` | **Modified** — Wire CSV/chart CLI flags |
| `scripts/analyze_scb_population.py` | **Read-only** — Reference for plot patterns |
| `config/assets/scb_reference/category_mappings.json` | **Read-only** — Canonical SCB schema labels |
| `config/assets/identity/simulation_config_002_swedish.json` | **Read-only** — Pipeline identity field definitions |
