# Plan: Italy Identity & Comparison Pipeline

**Date:** 2026-06-07
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/gui-multi-select-checkboxes`
**Branch:** `feature/italy-identity-comparison-pipeline`

---

## Overview

Bring Italy to full pipeline parity with Sweden by wiring the existing ISTAT/Eurostat population backend into the identity generation and comparison pipelines. Today Italy can generate raw populations from real statistical APIs but cannot run LLM persona generation or evaluate output against reference distributions.

## Problem Statement

Sweden has the complete pipeline working end-to-end: database population (SCB API) -> LLM identity generation -> extraction -> comparison/evaluation with charts. Italy has a fully implemented population generation backend (14 demographic fields, conditional chained sampling, working `generate_istat_population.py`) but:

1. The manifest system and GUI cannot discover Italy (no country config file)
2. No Italian simulation config tells the LLM how to generate Italian personas
3. The comparison pipeline (extractor + normalizer) is hardcoded to Swedish labels, regions, and category mappings
4. No ISTAT category mappings file exists for normalizing raw Italian population data

This prevents running the full research pipeline for Italian synthetic populations.

## Goals

### In Scope
1. Enable LLM-based Italian persona generation via the manifest/axis system and GUI
2. Create ISTAT category mappings for label normalization in the comparison pipeline
3. Make the comparison extractor and normalizer country-aware (support both Sweden and Italy)
4. Create an Italian comparison script (`compare_pipeline_to_istat.py`)

### Out of Scope
- Adding the missing `income_source` field to Italy's population generation (no ISTAT API source identified; fetch_service.py:313 returns `{}`)
- Adding the missing `ethnicity` field (also absent in Sweden's pipeline)
- Norway comparison pipeline (SSB has category mappings but no comparison script yet)
- Refactoring population generation code itself (already working)
- Batch prompt templates for Italy (configurable mode is the primary strategy)

## Success Criteria

- [ ] GUI displays "Italian" in the country selector
- [ ] `--country-id italian` works with `compose_manifest()` to produce a valid manifest
- [ ] LLM identity generation produces coherent Italian personas (Italian regions, education system, cultural references)
- [ ] `compare_pipeline_to_istat.py` produces charts and JSON evaluation report comparing pipeline output against ISTAT reference
- [ ] Existing Swedish pipeline is unaffected (backward compatible)
- [ ] `extractor.extract_population()` correctly normalizes Italian persona identity.json files to canonical labels

---

## Technical Design

### Approach

Add Italy as a parallel country configuration alongside Sweden, reusing the same code paths with country-parameterized label sets and mappings. The statistical evaluator and charts module are already country-agnostic; only the extractor and normalizer need country awareness.

The ISTAT category mappings JSON will mirror the SCB mappings structure (same sub-key names) so the normalizer function works for both countries without branching -- the JSON content determines the translations.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Parameterize existing extractor/normalizer with country | Reuses existing code, single maintenance point | Extractor grows larger (~200 lines of Italian constants) | Chosen |
| Create separate `extractor_it.py` / `normalizer_it.py` | Clean separation, no risk to Swedish pipeline | Code duplication, two files to maintain per field change | Rejected |
| Abstract country into a registry/factory pattern | Cleanest architecture, easy to add Norway later | Over-engineering for 2 countries, significant refactor | Rejected (future consideration) |

### Architecture Changes

No new modules or classes. Changes are additive:

- `extractor.py` gains Italian label constants, city-to-region mapping, and a `country` parameter on public functions
- `normalizer.py` gains parameterized mappings path and Italian birth label set
- New config files follow the existing patterns exactly (country YAML, simulation config JSON, category mappings JSON)

---

## Implementation Plan

### Phase 1: LLM Synthetic Generation Config
**Goal:** Enable the manifest system and GUI to discover and launch Italian identity generation runs.

- [x] Task 1.1 -- Create `config/countries/italian.yaml` with id, label, and reference to simulation config
- [x] Task 1.2 -- Create `config/assets/identity/configurable/simulation_config_005_italian_generative.json` adapted from Swedish config (Italian regions, education system, cultural conventions in instruction and category descriptions)

**Files Created:**
- `config/countries/italian.yaml` -- Country axis config (4 lines, mirrors `swedish.yaml`)
- `config/assets/identity/configurable/simulation_config_005_italian_generative.json` -- LLM simulation config with Italian-adapted instruction array and category descriptions

**Dependencies:** None

### Phase 2: ISTAT Category Mappings
**Goal:** Provide the label translation data the comparison pipeline needs to normalize Italian population data.

- [x] Task 2.1 -- Create `config/assets/istat_reference/category_mappings.json` with all 12 demographic sections, using labels from `population/italy/constants.py` and `population/italy/parsers.py`

Sections needed (labels sourced from Italian constants/parsers):

| Section | Italian canonical labels |
|---------|------------------------|
| education | "No Formal Education", "High School (Liceo/Professionale)", "University Degree" |
| employment | "Employed", "Not Employed" |
| region | 20 NUTS2 region names from `NUTS2_REGION_CODES` |
| civil_status | "Single", "Married", "Divorced", "Widowed", "Separated", "Civil Partnership" |
| industry_sector | "Professional", "Clerical", "Craft", "Elementary" |
| employment_type | "Permanent\|Full-time", "Permanent\|Part-time", "Unspecified\|Full-time", "Unspecified\|Part-time" |
| housing_tenure | "Owner-occupied", "Rental" |
| household_size | "1", "2", "3", "4", "5", "GE6" |
| socioeconomic | "Poverty", "Working Class", "Middle Class", "Wealthy" |
| parental_structure | "Living Alone", "Single Parent", "Couple without Children", "Nuclear Family", "Extended Family" |
| birth_location | "Italy", "Europe (Other)", "Outside Europe" |
| birth_country_detail | 16 top countries + "Other" |

Each section includes `pipeline_label_mappings` for LLM free-text -> canonical label normalization (Italian-language variants).

**Files Created:**
- `config/assets/istat_reference/category_mappings.json` -- Italian label translation data

**Dependencies:** None

### Phase 3: Comparison Pipeline
**Goal:** Make the extractor and normalizer support Italian data alongside Swedish, and create the Italian comparison script.

- [x] Task 3.1 -- `normalizer.py`: Rename `normalize_scb_to_schema()` -> `normalize_raw_to_schema()` and update all callers
- [x] Task 3.2 -- `normalizer.py`: Add `_ITALY_BIRTH_LABELS` frozenset, parameterize birth location detection
- [x] Task 3.3 -- `normalizer.py`: Make `normalize_if_raw()` accept optional `mappings_path` parameter (defaults to SCB for backward compat)
- [x] Task 3.4 -- `normalizer.py`: Handle Italian `employment_type` string format ("Permanent|Full-time") alongside Swedish nested dict format
- [x] Task 3.5 -- `extractor.py`: Make `_load_pipeline_mappings()` accept a `path` parameter, add ISTAT mappings loader
- [x] Task 3.6 -- `extractor.py`: Add Italian label constants (`REGION_LABELS_IT`, `EDUCATION_LABELS_IT`, `BIRTH_LOCATION_LABELS_IT`, `CIVIL_STATUS_LABELS_IT`, `HOUSING_TENURE_LABELS_IT`, `BIRTH_COUNTRY_DETAIL_LABELS_IT`, etc.)
- [x] Task 3.7 -- `extractor.py`: Add `_CITY_TO_REGION_IT` mapping (Roma->Lazio, Milano->Lombardia, Napoli->Campania, Torino->Piemonte, etc.)
- [x] Task 3.8 -- `extractor.py`: Add Italian-specific normalizer functions (`_normalize_education_it`, `_normalize_employment_it`, `_normalize_birth_location_it`, `_normalize_civil_status_it`, `_normalize_housing_tenure_it`)
- [x] Task 3.9 -- `extractor.py`: Add `country` parameter to `extract_individual()` and `extract_population()`, defaulting to `"swedish"` for backward compatibility
- [x] Task 3.10 -- Create `scripts/compare_pipeline_to_istat.py` parallel to `compare_pipeline_to_scb.py` (default reference: `data/istat_api/istat_population.json`, loads ISTAT mappings, passes `country="italian"`)
- [x] Task 3.11 -- Update `scripts/compare_pipeline_to_scb.py` to use renamed `normalize_raw_to_schema` import

**Files Modified:**
- `src/population_synth/comparison/normalizer.py` -- Parameterize mappings, rename function, add Italian birth labels, handle Italian employment_type
- `src/population_synth/comparison/extractor.py` -- Add Italian labels/constants, city mapping, normalizers, country parameter
- `scripts/compare_pipeline_to_scb.py` -- Update renamed import

**Files Created:**
- `scripts/compare_pipeline_to_istat.py` -- Italian comparison script

**Dependencies:** Phase 2 (needs ISTAT category mappings JSON)

---

## Testing Plan

### Manual Verification
- [ ] Generate Italian reference population: `python scripts/generate_istat_population.py --n 1000 --seed 42` -- verify all 14 fields populated
- [ ] Run identity generation with `--country-id italian` for a small batch (n=2) -- verify LLM produces coherent Italian personas
- [ ] Run `compare_pipeline_to_istat.py` on generated output -- verify charts and JSON report are produced
- [ ] Launch GUI -- verify "Italian" appears in the country selector
- [ ] Run existing Swedish pipeline end-to-end -- verify no regressions

### Edge Cases
- [ ] Italian persona with "Not Employed" status maps correctly to comparison schema (Italy uses binary employed/not-employed vs Sweden's 4-category)
- [ ] Italian employment_type string format ("Permanent|Full-time") normalizes correctly through the pipeline
- [ ] Italian regions with special characters (Valle d'Aosta, Trentino-Alto Adige/Sudtirol) are handled
- [ ] `extract_population()` with `country="swedish"` (default) produces identical output to current behavior

---

## Documentation Plan

- [ ] Update CLAUDE.md: add Italian comparison script to Commands section, update Architecture section to note country-aware comparison
- [ ] Update `docs/istat_population_data_sources.md` if any new findings during implementation

---

## Rollback Plan

1. All changes are additive -- new files can be deleted, new parameters have backward-compatible defaults
2. The `normalize_scb_to_schema()` -> `normalize_raw_to_schema()` rename is the only breaking change; revert by restoring old name and updating callers
3. No database migrations or external state changes

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Italian LLM output uses unexpected label variants not covered by pipeline_label_mappings | High | Medium | Start with comprehensive Italian-language mappings, iterate after first batch run |
| ISTAT category labels in parsers.py don't match what the normalizer expects | Medium | Medium | Cross-reference parsers.py output format directly when building category_mappings.json |
| Extractor grows unwieldy with two full country label sets | Low | Low | Acceptable for 2 countries; consider registry pattern if a third country is added |
| Renaming normalize_scb_to_schema breaks callers outside the tracked scripts | Low | High | Grep for all usages before renaming; update all callers in same commit |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1: LLM Config | ~1 hour | None |
| Phase 2: Category Mappings | ~2 hours | None |
| Phase 3: Comparison Pipeline | ~4-6 hours | Phase 2 |

---

## References

- Analysis: `.claude/plans/analyse-the-codebase-i-enchanted-lighthouse.md`
- Italian data sources: `docs/istat_population_data_sources.md`
- Italian constants: `src/population_synth/population/italy/constants.py`
- Swedish reference implementation: `config/assets/scb_reference/category_mappings.json`
- Swedish simulation config: `config/assets/identity/configurable/simulation_config_004_swedish_generative.json`

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- config/assets/identity/configurable/simulation_config_005_italian_generative.json
- config/assets/istat_reference/category_mappings.json
- config/countries/italian.yaml
- docs/development/plans/active/italy-identity-comparison-pipeline.md
- scripts/compare_pipeline_to_istat.py
- src/population_synth/comparison/extractor.py
- src/population_synth/comparison/normalizer.py
