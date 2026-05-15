# Plan: SCB Population Sampler + Pipeline Comparison Framework

**Date:** 2026-05-06
**Author:** Claude Code
**Status:** In Progress
**Base Branch:** `feature/swedish-persona-generation`
**Branch:** `feature/scb-population-comparison`

---

## Overview

Build a separate, LLM-free pipeline that generates a reference population by sampling directly from real Swedish demographic data (SCB / Statistics Sweden), then compare it against the existing persona generation pipeline's output to measure statistical plausibility. The comparison operates at two levels: aggregate distribution matching (marginals) and individual-level coherence (joint distributions).

## Problem Statement

The existing Swedish persona pipeline (seed005/seed006) uses manually-estimated probability distributions (e.g., 75% native Swedish, 45% urban, 35% gymnasieskola). There is no way to know how close these estimates are to reality, nor whether the LLM-refined probability adjustments produce demographically plausible populations. Without a ground-truth reference derived from real population data, the statistical fidelity of generated personas is unmeasured.

## Goals

### In Scope
1. Fetch real Swedish population statistics from SCB's PxWeb API (age, sex, education, employment, birth country, urbanization, income/class, family structure)
2. Build a pure statistical sampler that generates N demographic profiles respecting joint distributions (age-education-employment correlations)
3. Extract comparable demographic data from existing pipeline output (identity.json files)
4. Compare the two populations using chi-squared goodness-of-fit, KL divergence, and joint distribution coherence checks
5. Produce a structured comparison report (console + JSON)

### Out of Scope
- Modifying the existing persona generation pipeline
- Generating narratives, clinical profiles, or LLM content in the SCB pipeline
- Name frequency integration (future work)
- Replacing the manual distributions in existing schema files
- Automatic correction of pipeline distributions based on comparison results

## Success Criteria

- [ ] SCB client fetches at least 6 demographic tables from PxWeb API and caches responses locally
- [ ] Population sampler generates N=100 individuals with plausible Swedish demographics (no impossible combinations like age=5 + employed)
- [ ] Pipeline extractor reads identity.json files from seed006 output and produces matching format
- [ ] Comparison framework computes per-attribute chi-squared p-values and KL divergence
- [ ] Comparison report clearly shows which attributes diverge between pipeline and SCB populations
- [ ] SCB population compared against itself yields perfect match (KL=0, p=1.0)

---

## Technical Design

### Approach

```
+-------------------------------+       +-------------------------------+
|  EXISTING PIPELINE (seed006)  |       |  SCB SAMPLER (new)            |
|  Identity -> Narrative -> ... |       |  Pure statistics, no LLM      |
|  Output: identity.json x N   |       |  Output: scb_population.json  |
+--------------+----------------+       +--------------+----------------+
               |                                       |
               +-------------+    +--------------------+
                              v    v
                    +---------------------+
                    | COMPARISON FRAMEWORK |
                    | Marginals + Joints   |
                    | Chi-sq, KL, coherence|
                    +---------------------+
```

The SCB sampler is a standalone script with no dependency on the pipeline orchestrator, LLM client, or seed manifests. It produces a JSON file of N demographic profiles. A separate extractor script reads existing pipeline output into the same format. The comparison framework then takes any two population files and produces metrics.

**Joint sampling** is key: SCB provides cross-tabulated data (e.g., population by age AND education level). Rather than sampling each attribute independently (which would produce impossible combinations), we use a conditional sampling chain:
1. Sample (age, sex) jointly from population pyramid
2. Sample education | (age) from cross-tabulated education data
3. Sample employment | (age, education) from labour force data
4. Sample remaining attributes from marginals where cross-tabs unavailable

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **Pre-fetch + static JSON** | No runtime API dependency, fast, reproducible | Data becomes stale (annually) | **Chosen** |
| Runtime API calls during sampling | Always up-to-date | Adds latency, network dependency, rate limit risk | Rejected |
| Replace existing schema distributions with SCB data | Improves pipeline directly | Doesn't allow comparison; changes existing behavior | Rejected (different goal) |
| Independent marginal sampling only | Simpler implementation | Produces impossible attribute combinations (age=18 + retired) | Rejected |

### Architecture Changes

**New modules:**
- `anxiety_synthetic/utils/scb_client.py` — PxWeb API client with file-based caching
- `scripts/generate_scb_population.py` — Standalone population sampler
- `scripts/extract_population_from_pipeline.py` — Identity extractor for existing output
- `scripts/compare_populations.py` — Statistical comparison framework

**New data files:**
- `config/assets/scb_cache/` — Raw cached API responses (git-ignored)
- `config/assets/scb_reference/category_mappings.json` — SCB code to schema label mappings

**Modified files:**
- `pyproject.toml` — Add `requests`, `scipy`, `numpy`

---

## Implementation Plan

### Phase 1: SCB API Client
**Goal:** Reliable, cached access to SCB's PxWeb API
**Started:** 2026-05-06
**Completed:** 2026-05-06

- [x] Create `anxiety_synthetic/utils/scb_client.py` with `SCBPxWebClient` class
- [x] Implement `fetch_table(table_path, query)` — POST JSON query, return parsed response
- [x] Implement `get_table_metadata(table_path)` — GET variable codes and value lists
- [x] Implement file-based caching (write raw JSON to `config/assets/scb_cache/`, check TTL before re-fetching)
- [x] Create `config/assets/scb_cache/.gitignore` to exclude cached responses from version control
- [x] Add `requests` to `pyproject.toml` dependencies

**Files Created:**
- `anxiety_synthetic/utils/scb_client.py` — API client (~120 lines)
- `config/assets/scb_cache/.gitignore` — Ignore cached data

**Files Modified:**
- `pyproject.toml` — Add `requests` dependency

**Dependencies:** None

### Phase 2: Population Sampler
**Goal:** Generate N demographic profiles from real SCB distributions with joint sampling
**Started:** 2026-05-06
**Completed:** 2026-05-06

- [x] Create `config/assets/scb_reference/category_mappings.json` with SCB-to-schema label mappings for all attributes
- [x] Create `scripts/generate_scb_population.py` with distribution transformation logic (JSON-stat to probability tables)
- [x] Implement category aggregation (collapse granular SCB codes into schema categories)
- [x] Implement conditional sampling chain: (age, sex) -> education|age -> employment|age,education -> remaining marginals
- [x] Output `scb_population.json` with metadata (tables used, data vintage, timestamp) and N individual profiles
- [x] Add `scipy`, `numpy` to `pyproject.toml` dependencies

**SCB tables to fetch:**

| Schema Field | SCB Table Path | Cross-tab |
|---|---|---|
| age, biological_sex | `BE/BE0101/BE0101A/BefolkningNy` | Joint (age x sex) |
| birth_location, ethnicity | `BE/BE0101/BE0101E/InrUtrFodda` | Foreign-born by world region |
| education_level | `UF/UF0506/Utbildning` | By age group |
| employment_status | `AM/AM0401/AM0401A/NAKUBefAldKN` | By age group |
| current_environment_type | `MI/MI0810` or kommun classification | Marginal (urban/rural) |
| socioeconomic_class | `HE/HE0110/Tab5aDispInkN` | Income by education (proxy) |
| parental_structure | `LE/LE0102/LE0102T08` | Children by family type |

**Category mapping examples:**
- Education SUN2020: pre-gymnasium -> "No Formal Education", gymnasium -> "High School (Gymnasieskola)", post-gymnasium <3yr -> "Vocational (Yrkeshogskola)", post-gymnasium >=3yr + PhD -> "University Degree"
- Employment AKU: employed -> "Employed", unemployed -> "Unemployed", in education -> "Student", retired/other -> "Retired"
- Urbanization: storstad -> "Urban Metropolis", storre stad -> "Suburban", ovriga kommuner -> "Rural/Countryside"
- Socioeconomic: income deciles D1-D2 -> "Poverty", D3-D5 -> "Working Class", D6-D8 -> "Middle Class", D9-D10 -> "Wealthy"

**Files Created:**
- `scripts/generate_scb_population.py` — Sampler script (~300 lines)
- `config/assets/scb_reference/category_mappings.json` — Mapping definitions

**Files Modified:**
- `pyproject.toml` — Add `scipy`, `numpy`

**Dependencies:** Phase 1

### Phase 3: Pipeline Population Extractor
**Goal:** Read existing pipeline identity output into a comparable format
**Started:** 2026-05-06
**Completed:** 2026-05-06

- [x] Create `scripts/extract_population_from_pipeline.py`
- [x] Scan `<seed_root>/persona_*/identity.json` for all persona directories
- [x] Flatten hierarchical identity levels (level_1 through level_4) into flat attribute dict matching the SCB sampler output fields
- [x] Handle both sequential output format (nested levels with selected values) and batch output format (narrative text — may require different extraction logic)
- [x] Output `pipeline_population.json` with same structure as `scb_population.json`

**Files Created:**
- `scripts/extract_population_from_pipeline.py` — Extractor (~150 lines)

**Dependencies:** Phase 1 (for shared output format definition)

### Phase 4: Comparison Framework
**Goal:** Quantitative comparison of two population files
**Started:** 2026-05-06
**Completed:** 2026-05-06

- [x] Create `scripts/compare_populations.py` with `StatisticalEvaluator` class
- [x] Implement per-attribute marginal comparison: observed vs expected frequency distributions
- [x] Implement chi-squared goodness-of-fit test per categorical attribute (scipy.stats.chisquare)
- [x] Implement KL divergence per attribute (with Laplace smoothing for zero-count categories)
- [x] Implement Total Variation distance per attribute
- [x] Implement joint distribution comparison for attribute pairs (age x education, age x employment, education x employment)
- [x] Implement individual coherence scoring: for each pipeline individual, compute probability of their attribute tuple under SCB joint distributions; flag near-zero probability combinations
- [x] Output: console summary table, JSON report (`comparison_report.json`)
- [ ] Optional: matplotlib bar chart visualizations (side-by-side per attribute)

**Aggregate metrics per attribute:**
- Chi-squared p-value (pass if p > 0.05)
- KL divergence (bits — lower is better)
- Total Variation distance (0-1 scale)
- Max absolute difference between categories

**Joint coherence metrics:**
- Cross-tab chi-squared for attribute pairs
- Coherence score: % of pipeline individuals whose (age, education, employment) tuple has non-negligible probability in SCB cross-tabs
- List of flagged implausible individuals

**Files Created:**
- `scripts/compare_populations.py` — Comparison framework (~250 lines)

**Dependencies:** Phase 2, Phase 3

---

## Testing Plan

### Unit Tests
- [ ] SCB client: mock API response, verify JSON-stat parsing and cache read/write
- [ ] Category mapping: verify all SCB codes map to exactly one schema label, probabilities sum to 1.0
- [ ] Conditional sampler: verify N=1000 samples follow expected marginal distributions within tolerance

### Integration Tests
- [ ] End-to-end: run sampler with N=10, verify output JSON is valid and all required fields present
- [ ] Extractor: run on a seed006 persona directory, verify output matches expected format
- [ ] Comparison: run on SCB population vs itself, verify chi-sq p=1.0 and KL=0.0

### Manual Verification
- [ ] Inspect 10 sampled SCB individuals — do attribute combinations look realistic? (e.g., no 80-year-old students, no age=5 employed)
- [ ] Run comparison on seed006 output vs SCB — review report for interpretability
- [ ] Verify cached SCB responses are written to `config/assets/scb_cache/` and not committed to git

### Edge Cases
- [ ] SCB API returns empty data for a table — sampler handles gracefully with warning
- [ ] Seed output directory has 0 persona folders — extractor reports error
- [ ] Population with N < 5 — comparison warns about insufficient sample size for chi-squared validity
- [ ] Category in pipeline output doesn't exist in SCB mappings — flagged as unmapped

---

## Documentation Plan

- [ ] Update CLAUDE.md with SCB comparison framework description under Architecture
- [ ] Add docstring to `scb_client.py` explaining PxWeb API query format
- [ ] Add usage instructions as header comments in each script (generate, extract, compare)

---

## Rollback Plan

Low risk — all new files, no modifications to existing pipeline code.

1. Delete new files: `scb_client.py`, 3 scripts, `scb_cache/`, `scb_reference/`
2. Revert `pyproject.toml` dependency additions
3. No data migrations or pipeline changes to reverse

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| SCB PxWeb API changes query format or table IDs | Low | Med | Pin to v1 endpoint; cache raw responses; metadata discovery validates tables before query |
| Category mapping produces poor fit (SCB codes don't collapse cleanly) | Med | Med | Comparison framework itself will quantify the mapping quality; iterate on mappings |
| Urban/rural classification has no clean 3-way SCB split | High | Low | Use DEGURBA or Tatortsgrad classification; document approximation |
| Fields without SCB data (~40% of schema: psychological, communication) | High | Low | Only compare SCB-grounded fields; clearly label non-comparable attributes in report |
| Small pipeline sample size (N=4-8) makes chi-squared unreliable | High | Med | Document minimum N; recommend generating N=100 for robust evaluation |
| SCB rate limiting during heavy development | Low | Low | File-based cache with 90-day TTL; one fetch per table |

---

## References

- SCB PxWeb API: `https://api.scb.se/OV0104/v1/doris/en/ssd/`
- SCB Statistics Database: `https://www.statistikdatabasen.scb.se/pxweb/en/ssd/`
- SCB Name Statistics: `https://www.scb.se/en/finding-statistics/statistics-by-subject-area/population-and-living-conditions/other-statistics/name-statistics/`
- Related Plan: `docs/development/plans/active/swedish-persona-generation.md`
- Existing Swedish identity schema: `config/assets/identity/sequential/simulation_config_002_swedish.json`
- Existing Swedish seed manifest: `config/seed_manifests/synthetic_pipeline_config_seed006.yaml`
