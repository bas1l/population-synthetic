# Plan: SCB Raw Data Output

**Date:** 2026-05-07
**Author:** Basil
**Status:** Completed
**Completed:** 2026-05-09 09:47
**Base Branch:** `dev`
**Branch:** `feature/scb-raw-data-output`

---

## Overview

Refactor the SCB population sampler to preserve raw API values (both classification codes and text labels) in the output, instead of transforming them into persona-schema-aligned labels during parsing. All raw→schema transformation moves to comparison time, using the existing `category_mappings.json` as the bridge.

## Problem Statement

The SCB pipeline currently transforms raw PxWeb API values into persona-schema labels inside `parsers.py`. Raw SCB codes (SUN2020, AKU, NACE, civilstånd) and Swedish-language labels are permanently discarded during parsing. This creates two problems:

1. **Data fidelity loss** — Granular classifications get collapsed (10 income deciles → 4 classes, 7+ SUN education codes → 4 labels, individual household sizes → 4 bins). The raw detail cannot be recovered.
2. **Tight coupling** — The SCB pipeline is coupled to the persona pipeline's label scheme. The SCB output should stand alone as a faithful representation of Swedish population statistics.

## Goals

### In Scope
1. SCB output preserves raw codes + labels from the PxWeb API for every field
2. Remove derived/computed fields from output (ethnicity, current_environment_type, age_group) — these are transformations, not raw API data
3. Move all raw→schema mapping logic to comparison time (`scripts/compare_populations.py`)
4. Update `scripts/analyze_scb_population.py` to work with the new raw format
5. `category_mappings.json` remains unchanged — it becomes the comparison-time bridge

### Out of Scope
- Changing the persona pipeline's identity schema or generator
- Adding new SCB fields beyond what the pipeline already fetches
- Modifying the SCB PxWeb API client itself (`scb_client.py`)
- Changing cached API response files

## Success Criteria

- [ ] Generated SCB population JSON contains raw code+label dicts for all categorical fields
- [ ] No persona-schema-aligned labels appear anywhere in the SCB output
- [ ] Derived fields (ethnicity, current_environment_type, age_group) are absent from the output
- [ ] `compare_populations.py` produces statistically identical results to the old pipeline (same chi-squared p-values, same KL divergence) after applying normalization
- [ ] `analyze_scb_population.py` renders plots correctly with raw labels
- [ ] Output metadata includes `output_format: "raw"` version marker

---

## Technical Design

### Approach

Refactor the transformation chain bottom-up: parsers first, then data structures, then sampler, then scripts. The parsers stop applying `category_mappings.json` lookups and instead pass through raw dimension codes and labels from the JSON-stat 2 response. A new `normalize_scb_to_schema()` function in `compare_populations.py` applies `category_mappings.json` at comparison time.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Raw-only output (chosen) | Clean separation of concerns; maximum data fidelity; SCB output is self-contained | Downstream scripts must handle nested dicts; comparison requires explicit normalization step | **Chosen** |
| Dual output (raw + transformed) | Backward compatible; no downstream breakage | Duplicates data; still couples generation to schema; bloated output | Rejected — defeats the purpose |
| Raw output with inline schema mapping | Each field has `{"raw": ..., "schema": ...}` | Still applies transformation at generation time; half-measure | Rejected |

### Architecture Changes

No new modules. Changes are internal to existing files:

```
anxiety_synthetic/scb_population/
├── parsers.py          — MAJOR: Remove all mapping lookups, return raw codes+labels
├── data.py             — UPDATE: Raw-keyed distribution types
├── sample_service.py   — UPDATE: Emit raw dicts, remove derived fields
├── fetch_service.py    — UPDATE: Stop passing mapping dicts to parsers
└── constants.py        — UPDATE: Remove schema label constants

scripts/
├── generate_scb_population.py      — UPDATE: Output serialization
├── analyze_scb_population.py       — UPDATE: Field access for nested dicts
├── compare_populations.py          — UPDATE: Add normalize_scb_to_schema()
└── extract_population_from_pipeline.py — UPDATE: Minor interface changes

config/assets/scb_reference/
└── category_mappings.json           — UNCHANGED (used at comparison time only)
```

### Output Format Change

**Current** individual record (flat schema labels):
```json
{
  "id": 0,
  "age": 42,
  "age_group": "35-44",
  "biological_sex": "Male",
  "education_level": "High School (Gymnasieskola)",
  "employment_status": "Employed",
  "socioeconomic_class": "Middle Class",
  "ethnicity": "Swedish",
  "birth_location": "Sweden",
  "region": "Stockholm",
  "current_environment_type": "Urban Metropolis",
  "civil_status": "Married",
  "industry_sector": "IT & Technology",
  "employment_type": "Permanent Full-time",
  "housing_tenure": "Rental apartment",
  "household_size": "3-4 persons",
  "income_source": "Employment income",
  "birth_country_detail": "Sweden",
  "parental_structure": "Nuclear Family"
}
```

**New** individual record (raw codes + labels):
```json
{
  "id": 0,
  "age": 42,
  "biological_sex": { "code": "1", "label": "men" },
  "education_level": { "code": "330", "label": "gymnasial utbildning, 3 år" },
  "employment_status": { "code": "1", "label": "sysselsatta" },
  "socioeconomic_class": { "decile": "D7" },
  "birth_location": { "label": "Sverige" },
  "region": { "code": "01", "label": "Stockholms län" },
  "civil_status": { "code": "G", "label": "married" },
  "industry_sector": { "code": "J", "label": "information and communication" },
  "employment_type": {
    "attachment": { "label": "permanent employees" },
    "hours": { "label": "35+ hours" }
  },
  "housing_tenure": { "code": "3", "label": "owner-occupied dwellings" },
  "household_size": { "label": "3 persons" },
  "income_source": { "code": "300", "label": "wage and business income" },
  "birth_country_detail": { "code": "SE", "label": "Sverige" },
  "parental_structure": { "label": "sammanboende med barn" }
}
```

**Removed fields** (derived, not from API):
- `age_group` — computed from age
- `ethnicity` — derived from birth_location
- `current_environment_type` — derived from region via hardcoded lookup

**Unchanged:**
- `age` — integer, already raw
- `id` — generated sequence, not from API

### Key Design Decisions

1. **Fields use `{"code": "...", "label": "..."}`** — Both the classification code (SUN2020, AKU, NACE, etc.) and the text label from the API are preserved. Not all fields have explicit codes; those use `{"label": "..."}` only.
2. **`employment_type` keeps composite structure** — Two separate API tables (attachment type + working hours) are stored as `{"attachment": {...}, "hours": {...}}` rather than being combined into a single category string.
3. **`socioeconomic_class` stores the raw decile** — `{"decile": "D7"}` instead of the aggregated class label.
4. **Distributions are at raw granularity** — Probability distributions in `PopulationDistributions` use raw keys. This means education has 7+ categories (not 4), household_size has 7 categories (not 4 bins), etc.
5. **Conditional dependencies use raw keys** — Cross-tabulated distributions (e.g., employment|education) are keyed by raw labels, not schema labels.

---

## Implementation Plan

### Phase 1: Refactor parsers and data structures
**Goal:** Make parsers return raw codes+labels instead of schema-mapped values

**Started:** 2026-05-07
**Completed:** 2026-05-07

**Tasks:**
- [x] Task 1.1 — Define a `RawCategory` TypedDict with `code` (optional) and `label` fields in `data.py` for consistent raw value representation across all fields
- [x] Task 1.2 — Refactor `parse_age_sex()`: return raw sex codes ("1"/"2") + labels ("men"/"women") instead of "Male"/"Female"
- [x] Task 1.3 — Refactor `parse_education_by_age()`: return raw SUN2020 codes + labels at full API granularity (7+ categories). Stop aggregating into 4 schema categories. Remove `sun2020_mappings` parameter.
- [x] Task 1.4 — Refactor `parse_employment_by_sex_education()`: return raw AKU codes + labels. Conditioning keys become raw education labels instead of schema labels. Remove `employment_mappings` and `education_mappings` parameters.
- [x] Task 1.5 — Refactor `parse_birth_location()`: return raw region labels from API. Remove `birth_location_mappings` parameter.
- [x] Task 1.6 — Refactor `parse_region()`: return raw county codes + labels. Remove `region_label_map` parameter.
- [x] Task 1.7 — Refactor `parse_civil_status_by_age_sex()`: return raw civilstånd codes (OG/G/ÄNKL/SK) + labels. Remove `cs_label_map` parameter.
- [x] Task 1.8 — Refactor `parse_industry_sector()`: return raw SNI2007/NACE codes + labels. Remove `sector_label_map` parameter.
- [x] Task 1.9 — Refactor `parse_employment_type_combined()`: return raw attachment labels + raw hours labels as composite. Remove `attachment_map` and `hours_map` parameters.
- [x] Task 1.10 — Refactor `parse_housing_tenure()`: return raw tenure codes + labels. Remove `tenure_label_map` parameter.
- [x] Task 1.11 — Refactor `parse_household_size()`: return raw size labels (individual counts, not binned). Remove `size_label_map` parameter.
- [x] Task 1.12 — Refactor `parse_income_source()`: return raw income component codes + labels. Remove `inc_label_map` parameter.
- [x] Task 1.13 — Refactor `parse_socioeconomic()`: return raw decile identifiers. Remove `decile_map` parameter.
- [x] Task 1.14 — Refactor `parse_parental_structure()`: return raw family type labels. Remove `family_map` parameter.
- [x] Task 1.15 — Refactor `parse_birth_country_detail()`: return raw country codes + labels. Remove `country_label_map` parameter.
- [x] Task 1.16 — Update `PopulationDistributions` dataclass to use raw-keyed distribution dicts
- [x] Task 1.17 — Remove `county_env_type_map` from `PopulationDistributions` (derived field infrastructure)

**Files Modified:**
- `anxiety_synthetic/scb_population/parsers.py` — Remove all mapping lookups in every `parse_*()` function; return raw codes+labels
- `anxiety_synthetic/scb_population/data.py` — Add `RawCategory` type; update `PopulationDistributions` field types

**Dependencies:** None

### Phase 2: Update sampler output
**Goal:** Sampler emits raw code+label dicts; derived fields removed

**Started:** 2026-05-07
**Completed:** 2026-05-07

**Tasks:**
- [x] Task 2.1 — Update `sample_one()` to construct output dicts with raw code+label for each field
- [x] Task 2.2 — Remove ethnicity derivation logic (birth_location → ethnicity lookup)
- [x] Task 2.3 — Remove current_environment_type derivation logic (region → county_env_type lookup)
- [x] Task 2.4 — Remove age_group derivation logic (age → bin lookup)
- [x] Task 2.5 — Output employment_type as composite: `{"attachment": {...}, "hours": {...}}`
- [x] Task 2.6 — Remove or update schema label constants in `constants.py`

**Files Modified:**
- `anxiety_synthetic/scb_population/sample_service.py` — Rewrite `sample_one()` output construction; remove derived field logic
- `anxiety_synthetic/scb_population/constants.py` — Remove schema label constants (e.g., `EDUCATION_LABELS`, `EMPLOYMENT_LABELS`)

**Dependencies:** Phase 1

### Phase 3: Update fetch_service orchestration
**Goal:** Fetch service stops loading/passing mapping dicts to parsers

**Started:** 2026-05-07
**Completed:** 2026-05-07

**Tasks:**
- [x] Task 3.1 — Remove mapping dict parameters from all `fetch_*()` method calls
- [x] Task 3.2 — Update `load_all()` (or equivalent orchestrator) to stop loading `category_mappings.json` for parser use
- [x] Task 3.3 — Ensure raw API response dimension codes and labels are forwarded to parsers without transformation

**Files Modified:**
- `anxiety_synthetic/scb_population/fetch_service.py` — Remove mapping parameters from `fetch_*()` calls; simplify `load_all()`

**Dependencies:** Phase 1

### Phase 4: Update downstream scripts
**Goal:** All scripts work with the new raw format; comparison applies transformation at runtime

**Started:** 2026-05-08
**Completed:** 2026-05-08

**Tasks:**
- [x] Task 4.1 — Update `generate_scb_population.py` output serialization to handle nested dicts
- [x] Task 4.2 — Update `analyze_scb_population.py` to extract display labels from nested code+label dicts for plotting
- [x] Task 4.3 — Implement `normalize_scb_to_schema()` function in `compare_populations.py` that applies `category_mappings.json` mappings to convert raw SCB data to schema labels before statistical comparison
- [x] Task 4.4 — Update `compare_populations.py` main comparison flow to call `normalize_scb_to_schema()` before chi-squared / KL divergence tests
- [x] Task 4.5 — Update `extract_population_from_pipeline.py` if comparison interface changed

**Files Modified:**
- `scripts/generate_scb_population.py` — Output serialization
- `scripts/analyze_scb_population.py` — Field access patterns for nested dicts
- `scripts/compare_populations.py` — Add `normalize_scb_to_schema()` function; update comparison flow
- `scripts/extract_population_from_pipeline.py` — Minor interface updates if needed

**Dependencies:** Phases 2, 3

### Phase 5: Update metadata format
**Goal:** Output metadata signals the new format version

**Started:** 2026-05-08
**Completed:** 2026-05-08

**Tasks:**
- [x] Task 5.1 — Add `output_format: "raw"` field to the output JSON metadata section
- [x] Task 5.2 — Update `tables_used` metadata to include dimension code references where available

**Files Modified:**
- `scripts/generate_scb_population.py` — Metadata construction

**Dependencies:** Phase 4

---

## Testing Plan

### Manual Verification
- [ ] Generate a 100-person SCB population and inspect JSON — all categorical fields must contain `{"code": ..., "label": ...}` dicts (not flat strings)
- [ ] Verify no schema-aligned labels (e.g., "Male", "High School (Gymnasieskola)", "Middle Class") appear in the output
- [ ] Verify derived fields (ethnicity, current_environment_type, age_group) are absent from every individual record
- [ ] Run `compare_populations.py` on old-format pipeline population vs new-format SCB population — verify normalization produces identical statistical results to the old pipeline
- [ ] Run `analyze_scb_population.py` on a new-format population — verify all plots render with readable labels

### Edge Cases
- [ ] Employment_type for non-employed individuals — verify the composite structure handles "Not Applicable" / missing values correctly
- [ ] Birth_country_detail for Swedish-born — verify raw code "SE" is correctly output
- [ ] Income decile edge cases — verify D1 and D10 are correctly represented
- [ ] Conditional distributions — verify employment sampled conditional on raw education keys works correctly (e.g., no KeyError from missing raw key)

---

## Documentation Plan

- [ ] Update CLAUDE.md Architecture section with note about raw SCB output format
- [ ] Update `docs/scb_population_and_comparison.md` (if it exists) with new output format documentation

---

## Rollback Plan

1. **Before merging:** All changes are on a feature branch. `git branch -d feature/scb-raw-data-output` to discard.
2. **After merging:** `git revert <merge-commit>` — no data migrations or external state changes involved.
3. **Cached data:** Existing cached SCB API responses in `.cache/` are unaffected (they store raw API JSON, not parsed output).
4. **Generated populations:** Old-format population JSON files remain valid but are not compatible with the new analysis scripts. Re-generate to get raw format.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Conditional distributions break when keys change from schema to raw | Medium | High | Test each conditional chain (education→employment, sex→civil_status) individually; verify key lookups before sampling |
| Analysis plots unreadable with verbose Swedish labels | Low | Medium | Truncate or rotate axis labels in matplotlib; use short codes where labels are too long |
| employment_type composite format complicates comparison normalization | Medium | Medium | Flatten to single category string at comparison time using outer product logic |
| Parsers rely on mapping dict structure for dimension key discovery | Medium | Medium | Audit each parser to separate "find the right dimension key" logic from "map the label" logic |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1: Refactor parsers + data | Large (15 parser functions) | None |
| Phase 2: Update sampler | Medium | Phase 1 |
| Phase 3: Update fetch_service | Small | Phase 1 |
| Phase 4: Update scripts | Medium | Phases 2, 3 |
| Phase 5: Update metadata | Small | Phase 4 |

---

## References

- Existing category mappings: `config/assets/scb_reference/category_mappings.json`
- SCB PxWeb API client: `anxiety_synthetic/scb_population/scb_client.py`
- Related active plans: `docs/development/plans/active/scb-population-enrichment.md`, `docs/development/plans/active/scb-population-modularization.md`
