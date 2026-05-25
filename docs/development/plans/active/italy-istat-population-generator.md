# Plan: Italy (ISTAT/Eurostat) Population Generator

**Date:** 2026-05-25
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/prototype-istat-api`
**Branch:** `feature/italy-istat-population-generator`

---

## Overview

Build a full Italy population generation pipeline using ISTAT (SDMX REST) and Eurostat (JSON-stat) APIs, mirroring the existing SCB (Sweden) and SSB (Norway) country modules. This is the first country requiring two API clients due to protocol differences. The completed prototype (`scripts/prototype_istat_api.py`) validated API access and identified working dataflows — this plan implements the production pipeline.

## Problem Statement

The project supports Sweden and Norway for generating statistically realistic synthetic populations from live statistical API data. Italy is the next country to add, but ISTAT uses SDMX REST (not PxWeb), and critical population endpoints are too slow. The prototype confirmed that a hybrid ISTAT + Eurostat approach is required, with fundamentally different parsing for each protocol.

## Goals

### In Scope
1. Two new API clients: `EurostatClient` (JSON-stat 2.0) and `ISTATSDMXClient` (SDMX-JSON 2.0)
2. Italy country module (`population/italy/`) with constants, parsers, fetch service, sample service
3. Generation script producing Italian synthetic populations in the same format as SCB/SSB output
4. Full conditional chained sampling (11-step chain) using live API data
5. Local caching for all API responses; 12-second rate limiting for ISTAT

### Out of Scope
- GUI integration (future plan)
- Identity generation manifests for Italy (separate plan)
- Comparison pipeline integration (future)
- NUTS3 or municipality-level granularity (NUTS2 only)
- Fields with no clean statistical source (religiosity, health_status)

## Success Criteria

- [ ] `python scripts/generate_istat_population.py --n 100 --seed 42` produces 100 Italian individuals
- [ ] All 15 `PopulationDistributions` fields populated from live data (no silent fallbacks)
- [ ] Re-run with cache completes instantly (no API calls)
- [ ] Age range 18–85, sex labels match schema, education/employment labels are schema-compliant
- [ ] No ISTAT rate limit violations (12s between requests, all responses cached)
- [ ] Output JSON matches SCB/SSB format (metadata + individuals list)
- [ ] `ruff check src/` passes with no new violations

---

## Technical Design

### Approach

Two new clients extending `BasePxWebClient` for cache infrastructure. Eurostat provides age/sex, region, and housing tenure via JSON-stat 2.0 (same format as SCB/SSB — reusable parser patterns). ISTAT provides education, employment, income, civil status via SDMX-JSON 2.0 (requires new parser infrastructure). The `load_all()` orchestrator takes both clients — an intentional divergence from the single-client pattern in Sweden/Norway.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Dual client (Eurostat + ISTAT) | Clean separation of protocols; reuses json-stat patterns for Eurostat | `load_all` takes two clients instead of one | **Chosen** — protocols are fundamentally incompatible |
| Single hybrid client | One client object | Mixed fetch signatures, confused error handling | Rejected |
| ISTAT-only (no Eurostat) | Single source | Population endpoints timeout; age/sex unavailable | Rejected |
| `istatapi` / `sdmx1` library | Less boilerplate | Hides response structure; adds dependencies; doesn't cache or rate-limit to our spec | Rejected |

### Architecture Changes

```
src/population_synth/
  clients/
    eurostat_client.py              # NEW — EurostatClient(BasePxWebClient)
    istat_client.py                 # NEW — ISTATSDMXClient(BasePxWebClient)
  population/
    italy/
      __init__.py                   # NEW
      constants.py                  # NEW — dataflow IDs, NUTS2 codes, label maps
      parsers.py                    # NEW — SDMX + JSON-stat parsers
      fetch_service.py              # NEW — ISTATFetchService with load_all()
      sample_service.py             # NEW — ISTATSampleService

scripts/
  generate_istat_population.py      # NEW — generation script

config/assets/
  eurostat_cache/                   # NEW — cached Eurostat responses (git-ignored)
  istat_cache/                      # EXISTS — reused from prototype (git-ignored)
```

### Field Coverage Matrix

| # | Field | Source | Dataset/Dataflow ID | Status |
|---|-------|--------|---------------------|--------|
| 1 | `age_sex` | Eurostat | `demo_pjan` | Clean |
| 2 | `education_by_age` | ISTAT | `52_1194_DF_DCCV_POPTIT1_UNT2020_1` | Clean |
| 3 | `employment_by_sex_education` | ISTAT | `150_938` | Clean |
| 4 | `birth_location` | Eurostat | `migr_pop1ctz` (derived) | Derived |
| 5 | `region` | Eurostat | `demo_r_pjangrp3` | Needs validation in Phase 3 |
| 6 | `socioeconomic` | ISTAT | `32_292` | Clean (household-level proxy) |
| 7 | `parental_structure` | ISTAT | Investigate during Phase 5 | Raise if no clean source |
| 8 | `civil_status_by_age_sex` | ISTAT | `22_289_DF_DCIS_POPRES1_25` | Attempt with minimal key filter; raise on timeout |
| 9 | `industry_sector` | ISTAT | `150_938` (OCCUPATION_2011 dim) | Embedded in employment |
| 10 | `employment_type_by_age` | ISTAT | `150_938` (FT/PT + perm/temp dims) | Embedded in employment |
| 11 | `housing_tenure` | Eurostat | `ilc_lvho02` | Clean |
| 12 | `household_size` | ISTAT | `32_292` (NUMBER_HOUSEHOLD_COMP) | Proxy |
| 13 | `income_source_by_employment_age` | ISTAT | `32_292` (FAM_MAIN_INCOME_SOURCE) | Approximate; raise if data unavailable |
| 14 | `birth_country_detail` | Eurostat/ISTAT | `migr_pop1ctz` or `29_348` | Needs investigation in Phase 5 |
| 15 | `ethnicity_map` | — | — | Empty dict (same as SCB/SSB) |

### SDMX-JSON 2.0 Response Format (from prototype)

| What you want | Path |
|---|---|
| Series dimensions | `data["data"]["structures"][0]["dimensions"]["series"]` |
| Observation dimensions | `data["data"]["structures"][0]["dimensions"]["observation"]` |
| Series data | `data["data"]["dataSets"][0]["series"]` |
| Series keys | Colon-separated positional indices (e.g., `"0:1:2:0:3:0"`) |
| Observations | `series[key]["observations"]` → `{"0": [value], "1": [value]}` |

### Eurostat JSON-stat 2.0 Response Format

Same as SCB/SSB: `data["id"]` for dimension order, `data["dimension"][dim]["category"]["label"]` for labels, `data["value"]` for sparse flat-index values with row-major stride over `data["size"]`.

---

## Implementation Plan

### Phase 1: API Clients
**Goal:** Two working API clients with caching and rate limiting

- [x] Create `src/population_synth/clients/eurostat_client.py` — `EurostatClient(BasePxWebClient)`: GET to `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset_code}?format=JSON&...`, cache in `config/assets/eurostat_cache/`, 90-day TTL
- [x] Create `src/population_synth/clients/istat_client.py` — `ISTATSDMXClient(BasePxWebClient)`: GET to `https://esploradati.istat.it/SDMXWS/rest/data/{dataflow_id}/{key_filter}?format=jsondata`, 12s rate limiting (pattern from `SSBPxWebClient._rate_limit()`), cache in `config/assets/istat_cache/`, 90-day TTL
- [x] Add `get_datastructure()` method to `ISTATSDMXClient` for DSD metadata queries
- [x] Update `.gitignore` for `config/assets/eurostat_cache/` directory

**Files Modified:**
- `src/population_synth/clients/eurostat_client.py` — New file
- `src/population_synth/clients/istat_client.py` — New file
- `.gitignore` — Add eurostat_cache entry

**Dependencies:** None

### Phase 2: Constants and SDMX Parser Infrastructure
**Goal:** Italy-specific constants and generic SDMX-JSON 2.0 parser helpers

- [x] Create `src/population_synth/population/italy/__init__.py`
- [x] Create `constants.py` with: Eurostat dataset IDs (`demo_pjan`, `demo_r_pjangrp3`, `ilc_lvho02`, `migr_pop1ctz`), ISTAT dataflow IDs (`52_1194_DF_DCCV_POPTIT1_UNT2020_1`, `150_938`, `32_292`, `22_289_DF_DCIS_POPRES1_25`, `29_348`), NUTS2 region codes (20 regions), sex label map, education ISCED label map, employment ILO label map, civil status label map, ATECO/NACE sector map, income bracket edges in EUR
- [x] Create `parsers.py` skeleton with private SDMX helpers: `_extract_sdmx_dimensions(raw)`, `_extract_sdmx_series(raw)`, `_sdmx_key_to_indices(key)`, `_build_sdmx_dim_lookup(dimensions)`

**Files Modified:**
- `src/population_synth/population/italy/__init__.py` — New file
- `src/population_synth/population/italy/constants.py` — New file
- `src/population_synth/population/italy/parsers.py` — New file (skeleton)

**Dependencies:** None (can parallel with Phase 1)

### Phase 3: Eurostat Parsers and Fetch Methods
**Goal:** Implement Eurostat-sourced fields using reusable JSON-stat patterns from Sweden parsers

- [x] `parse_age_sex(raw)` — Parse `demo_pjan`: filter ages 18–85, normalize sex labels, produce `dict[tuple[int, str], float]`
- [x] `parse_region(raw)` — Parse `demo_r_pjangrp3`: sum over age/sex per NUTS2 region, normalize. Validate this dataset actually covers Italian NUTS2 — if not, fall back to `demo_r_d2jan` or raise
- [x] `parse_housing_tenure(raw)` — Parse `ilc_lvho02`: sum over household composition/income group, map tenure codes to schema labels
- [x] Create `fetch_service.py` with `ISTATFetchService` class (all static methods)
- [x] `fetch_age_sex(eurostat_client)` → `tuple[dict, str]`
- [x] `fetch_region(eurostat_client)` → `tuple[dict, str]`
- [x] `fetch_housing_tenure(eurostat_client)` → `tuple[dict, str]`

**Files Modified:**
- `src/population_synth/population/italy/parsers.py` — Add Eurostat parsers
- `src/population_synth/population/italy/fetch_service.py` — New file

**Dependencies:** Phase 1, Phase 2

### Phase 4: ISTAT SDMX Parsers and Fetch Methods
**Goal:** Implement all ISTAT-sourced fields using the SDMX parser infrastructure

This is the most complex phase — SDMX-JSON 2.0 parsing is fundamentally different from json-stat.

- [x] `parse_education_by_age(raw)` — Parse `52_1194`: decode positional indices for EDU_LEV_HIGHEST, SEX, AGE, map to schema age groups via `resolve_age_group()`, normalize education labels, produce conditional distribution keyed by `(age_group, sex)`
- [x] `parse_employment_by_sex_education(raw)` — Parse `150_938`: extract employment status, sum over unneeded dimensions (OCCUPATION_2011, REF_AREA), produce `{sex: {education: {status: probability}}}`
- [x] `parse_socioeconomic(raw)` — Parse `32_292`: map income brackets to EUR edges, use `classify_brackets()` from `income_class.py` for 4-class classification
- [x] `parse_civil_status_by_age_sex(raw)` — Parse `22_289_DF_DCIS_POPRES1_25`: map MARITAL_STATUS to schema labels, group by `(age_group, sex)`
- [x] `parse_industry_sector(raw)` — Extract OCCUPATION_2011 (13 classes) from `150_938`, map ATECO codes to schema industry labels
- [x] `parse_employment_type_by_age(raw)` — Extract FULL_PART_TIME + PERM_TEMP_EMPLOYEES from `150_938`, build composite `"{contract}|{hours}"` keys
- [x] `parse_household_size(raw)` — Extract NUMBER_HOUSEHOLD_COMP from `32_292`, map to schema labels
- [x] `parse_income_source(raw)` — Extract FAM_MAIN_INCOME_SOURCE from `32_292`, map to income source labels
- [x] Corresponding `fetch_*` methods in `fetch_service.py` for each parser
- [x] `fetch_civil_status_by_age_sex` must use DSD endpoint first to get metadata, then construct minimal key filter for national level + latest year to avoid timeout

**Files Modified:**
- `src/population_synth/population/italy/parsers.py` — Add ISTAT parsers
- `src/population_synth/population/italy/fetch_service.py` — Add ISTAT fetch methods

**Dependencies:** Phase 2, Phase 3

### Phase 5: Derived Fields and load_all Orchestrator
**Goal:** Complete all remaining fields and wire up the orchestrator

- [x] `fetch_birth_location(eurostat_client)` — Derive Italy-born vs foreign-born from Eurostat `migr_pop1ctz`. Produce 3-category distribution: "Italy", "Europe (Other)", "Outside Europe"
- [x] `fetch_birth_country_detail(eurostat_client, istat_client)` — Top-20 origin countries from `migr_pop1ctz` or ISTAT `29_348`. Map to country labels. Raise if unavailable
- [x] `fetch_parental_structure(istat_client)` — Investigate ISTAT family/household dataflows. Raise if no clean source found. No silent fallbacks
- [x] `load_all(eurostat_client: EurostatClient, istat_client: ISTATSDMXClient) -> PopulationDistributions` — Orchestrate all fetch methods, construct dataclass, log INFO after each fetch. Dual-client signature documented as intentional divergence

**Files Modified:**
- `src/population_synth/population/italy/parsers.py` — Add derived-field parsers
- `src/population_synth/population/italy/fetch_service.py` — Add derived fetch methods + `load_all()`

**Dependencies:** Phase 4

### Phase 6: Sample Service
**Goal:** Conditional chained sampler for Italian population data

- [x] Create `sample_service.py` with `ISTATSampleService` (all static methods)
- [x] `sample_one(distributions, rng, individual_id)` — 11-step conditional chained sampling identical to Sweden/Norway:
  1. Joint (age, sex) from `age_sex`
  2. Education | (age_group, sex) from `education_by_age`
  3. Employment | (sex, education) from `employment_by_sex_education`
  4. Marginals: birth_location, region, parental_structure
  5. Socioeconomic | (age_group, sex) from `socioeconomic`
  6. Civil status | (age_group, sex) from `civil_status_by_age_sex`
  7. Industry sector (employed only) from `industry_sector`
  8. Employment type | (age_group, sex) from `employment_type_by_age` (employed only)
  9. Housing tenure (marginal)
  10. Household size (marginal)
  11. Income source | (employment_status, age_group) from `income_source_by_employment_age`
  12. Birth country detail | (age_group, sex) — non-Italy-born only
- [x] `sample_population(distributions, rng, n)` — Loop calling `sample_one()`
- [x] Italy-specific label bridge maps (education → employment key mapping, employment → income key mapping)

**Files Modified:**
- `src/population_synth/population/italy/sample_service.py` — New file

**Dependencies:** Phase 5

### Phase 7: Generation Script and Documentation
**Goal:** End-to-end working pipeline

- [x] Create `scripts/generate_istat_population.py` — argparse with `--n`, `--output`, `--seed`; create both clients; call `load_all()`, `sample_population()`; write JSON output to `data/istat_api/istat_population.json`
- [x] Update `CLAUDE.md` — Add Italy generation command, ISTAT/Eurostat client descriptions, Italy module architecture, cache directory notes

**Files Modified:**
- `scripts/generate_istat_population.py` — New file
- `CLAUDE.md` — Add Italy documentation

**Dependencies:** Phase 6

---

## Testing Plan

### Manual Verification
- [ ] Run `python scripts/generate_istat_population.py --n 10 --seed 42` — full script completes without error
- [ ] Verify cached files appear in `config/assets/istat_cache/` and `config/assets/eurostat_cache/`
- [ ] Re-run script — confirm it uses cache (no API calls, instant completion)
- [ ] Inspect output JSON: all 15 fields populated, age range 18–85, labels schema-compliant
- [ ] Run `ruff check src/` — no new violations
- [ ] Run `python scripts/compare_populations.py` on output to validate distribution shapes

### Edge Cases
- [ ] ISTAT endpoint unreachable — script raises with clear error message, not silent failure
- [ ] ISTAT civil status endpoint timeout — raises loudly (fail-fast)
- [ ] Eurostat dataset returns empty data for Italy — raises, does not substitute zeros
- [ ] Cache directory doesn't exist — client creates it
- [ ] All ages outside 18–85 filtered out — if no data remains, raises

---

## Documentation Plan

- [x] Update `CLAUDE.md` with Italy commands, client docs, architecture notes
- [ ] Script includes `--help` / argparse usage
- [ ] Console output self-documenting (progress messages during fetch)

---

## Rollback Plan

This plan creates new files only. No existing code is modified (except `.gitignore` and `CLAUDE.md`). Rollback is trivial:

1. Delete `src/population_synth/clients/eurostat_client.py`
2. Delete `src/population_synth/clients/istat_client.py`
3. Delete `src/population_synth/population/italy/` directory
4. Delete `scripts/generate_istat_population.py`
5. Revert `.gitignore` and `CLAUDE.md` changes

No existing code is modified beyond documentation.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| ISTAT IP ban (5 req/min hard limit) | Medium | High | 12s rate limiting + full caching. Test cache-only mode after first run |
| Civil status endpoint timeout (22_289) | High | Medium | DSD metadata lookup first, then tight key filter (national level + single year). Raise loudly on timeout — no fallback |
| Employment (150_938) response too large (133 regions) | Medium | Medium | Key filter for national level only (`REF_AREA=IT`), latest year |
| SDMX structure varies between ISTAT dataflows | Medium | Medium | Robust `_extract_sdmx_*` helpers handle both `structures` and `structure` paths |
| Eurostat `demo_r_pjangrp3` doesn't cover Italy NUTS2 | Low | Medium | Validate in Phase 3. Alternative: `demo_r_d2jan` |
| Income data is household-level, not individual | Low | Low | Documented as proxy in constants. Same approach as EU-SILC for housing tenure |
| `parental_structure` has no clean ISTAT source | Medium | Medium | Investigate ISTAT family dataflows in Phase 5. Raise if none found |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1: Clients | ~1 hour | None |
| Phase 2: Constants + SDMX helpers | ~2 hours | None |
| Phase 3: Eurostat parsers + fetch | ~2 hours | Phase 1, 2 |
| Phase 4: ISTAT parsers + fetch | ~6 hours | Phase 2, 3 |
| Phase 5: Derived fields + load_all | ~3 hours | Phase 4 |
| Phase 6: Sample service | ~2 hours | Phase 5 |
| Phase 7: Script + docs | ~1 hour | Phase 6 |

**Total estimated effort:** ~17 hours

---

## References

- Prototype plan: `docs/development/plans/active/prototype-istat-api-access.md` (completed)
- International API research: `docs/development/plans/pending/investigate-international-statistical-apis-findings.md`
- Norway precedent: `docs/development/plans/completed/norway-ssb-population-generator.md`
- Probe script: `scripts/prototype_istat_api.py`
- Cached ISTAT responses: `config/assets/istat_cache/` (git-ignored)
- ISTAT SDMX API: `https://esploradati.istat.it/SDMXWS/rest/`
- Eurostat API: `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/`
