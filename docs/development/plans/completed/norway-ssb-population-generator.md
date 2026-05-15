# Plan: Norway (SSB) Population Generator

**Date:** 2026-05-10
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/configurable-identity-pipeline`
**Branch:** `feature/norway-ssb-population-generator`

---

## Overview

Add Norway as the first international country supported by the population generator. Statistics Norway (SSB) uses PxWebApi v2 — co-developed with SCB — which returns the same json-stat2 format. This validates the PxWeb client abstraction before tackling Tier-2 (non-PxWeb) countries. All new code lives in an independent `ssb_population/` module; integration with SCB scripts is deferred.

## Problem Statement

The SCB population generator is hard-wired to Sweden. Every table ID, variable code, and label mapping is Swedish-specific with no abstraction point. Adding a second country means copying the entire stack and substituting values — there is no base class, no config-driven table lookup, and no rate-limiting layer (SCB has only soft cache-based limits). Norway is the ideal pilot: identical protocol, full dimensional coverage, zero auth, and cultural/clinical proximity to Sweden.

## Goals

### In Scope
1. Refactor `SCBPxWebClient` to subclass a new `BasePxWebClient` that owns cache logic
2. Create `SSBPxWebClient` with GET-based PxWebApi v2 queries and a 30/min rate limiter
3. Implement `anxiety_synthetic/ssb_population/` (constants, parsers, fetch service, sample service) returning the shared `PopulationDistributions` dataclass
4. Create `config/assets/ssb_reference/category_mappings.json` with Norwegian variable code mappings
5. Create `scripts/generate_ssb_population.py` — standalone entry point for Norwegian population generation
6. Create `scripts/analyze_ssb_population.py` — single-file analysis plots for a Norwegian population

### Out of Scope
- Integration of SCB and SSB entry points into a single `--country` script (future)
- Comparison scripts updated to cross-compare Norwegian vs Swedish populations (future)
- Any other international country (Denmark, Finland, Iceland, etc.)
- Changes to the identity generation pipeline or patient persona generation
- KLASS API integration for runtime classification validation

---

## Success Criteria

- [ ] `python scripts/generate_ssb_population.py --n 500 --seed 42` completes without errors and writes a valid JSON file
- [ ] Output contains `metadata.country = "Norway"`, `metadata.source = "SSB PxWebApi v2"`, and 500 individuals each with all 17 demographic fields populated
- [ ] No HTTP 429 errors from SSB during generation (rate limiter firing correctly)
- [ ] `python scripts/analyze_ssb_population.py ssb_test.json` produces plots in `data/analysis/<stem>/`
- [ ] Two Norwegian populations can be compared with the unchanged `scripts/compare_populations.py`
- [ ] `python scripts/generate_scb_population.py --n 50 --seed 1` still works identically (backward compatibility of `SCBPxWebClient` refactor)
- [ ] Distribution shapes are plausible: age peak ~30–50, ~50% employed, Oslo/Viken-area dominant region

---

## Technical Design

### Approach

Extract shared cache infrastructure from `SCBPxWebClient` into a `BasePxWebClient`. `SCBPxWebClient` becomes a thin POST-based subclass; `SSBPxWebClient` is a GET-based subclass with a token-bucket rate limiter. The Norwegian fetch service and sample service are parallel to the Swedish ones — sharing only the `PopulationDistributions` dataclass and the age-group constants. No forced shared base for fetch/sample services yet; that refactor comes when a third country is added.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Parallel independent module (`ssb_population/`) | Zero risk to existing SCB code; clean separation; matches user's "independent code" requirement | Some logic duplication (sampling chain) | **Chosen** |
| Single parameterised `FetchService` for all countries | DRY, unified interface | Requires touching working SCB code now; harder to review | Rejected — defer to Tier-2 integration phase |
| Separate script with `--country` flag | Single entry point | Couples SCB and SSB code paths prematurely | Rejected — proof-of-concept first |
| Use `pxweb` or `dapla-statbank-client` wrapper | Less HTTP boilerplate | Adds external dependency; hides caching layer we already have | Rejected |

### Architecture Changes

```
anxiety_synthetic/
  utils/
    pxweb_client.py       NEW  BasePxWebClient (cache logic)
    scb_client.py         MOD  SCBPxWebClient(BasePxWebClient), interface unchanged
    ssb_client.py         NEW  SSBPxWebClient(BasePxWebClient), GET + rate limiter
  ssb_population/
    __init__.py           NEW
    constants.py          NEW  Norwegian table IDs and variable codes
    parsers.py            NEW  json-stat2 parsing + Norwegian label normalisation
    fetch_service.py      NEW  SSBFetchService → PopulationDistributions
    sample_service.py     NEW  SSBSampleService (11-step conditional chain)
config/assets/
  ssb_reference/
    category_mappings.json  NEW  Norwegian code → schema label mappings
scripts/
  generate_ssb_population.py  NEW  CLI entry point
  analyze_ssb_population.py   NEW  Analysis plots
```

**Reused without modification:**
- `anxiety_synthetic/scb_population/data.py:PopulationDistributions` (imported by SSB fetch service)
- `anxiety_synthetic/scb_population/constants.py:VALID_AGE_GROUPS, AGE_GROUP_BOUNDS` (imported by SSB constants)
- `anxiety_synthetic/scb_population/_helpers.py` (json-stat2 dimension extraction, imported by SSB parsers)
- `scripts/compare_populations.py` (works on SSB output as-is since output format is already schema-normalised)

---

## Implementation Plan

### Phase 1: Client Abstraction
**Goal:** Extract cache logic into `BasePxWebClient`; create `SSBPxWebClient` with rate limiting. SCB behaviour unchanged.

- [x] Task 1.1 — Create `anxiety_synthetic/utils/pxweb_client.py` with `BasePxWebClient(cache_dir, cache_ttl_days)` containing `_cache_path()`, `_load_from_cache()`, `_save_to_cache()` extracted from `scb_client.py:73-99`
- [x] Task 1.2 — Modify `anxiety_synthetic/utils/scb_client.py`: `SCBPxWebClient(BasePxWebClient)`, move cache calls to inherited methods, keep `fetch_table()` and `get_table_metadata()` signatures identical
- [x] Task 1.3 — Create `anxiety_synthetic/utils/ssb_client.py`: `SSBPxWebClient(BasePxWebClient)` with GET-based `fetch_table(table_id, query_params)`, token-bucket rate limiter (≥2.1s between calls to stay under 30/min), URL-length guard (fall back to POST body if >2100 chars), `ssb_` cache prefix, `get_table_metadata(table_id)`
- [x] Task 1.4 — Smoke-test: confirm `SCBPxWebClient` still fetches `BE0101` correctly

**Files Modified:**
- `anxiety_synthetic/utils/pxweb_client.py` — new file, ~60 lines
- `anxiety_synthetic/utils/scb_client.py` — refactor to subclass, ~20 line change
- `anxiety_synthetic/utils/ssb_client.py` — new file, ~100 lines

**Dependencies:** None

### Phase 2: Norwegian Table Discovery and Mappings
**Goal:** Identify all SSB table IDs for the 16 dimensions; build `category_mappings.json`.

- [x] Task 2.1 — Use `SSBPxWebClient.get_table_metadata()` to verify dimension variable codes for the known tables (05810, 09429, 09174, 11081, 09817, 04859, 07459)
- [x] Task 2.2 — Identify missing table IDs for: civil status (Sivilstand), household size, working hours, employment type, income deciles, parental structure — via SSB Statbank search (`https://www.ssb.no/en/statbank`)
- [x] Task 2.3 — Create `config/assets/ssb_reference/category_mappings.json` with sections: `age_groups`, `education` (NUS codes → schema), `employment`, `civil_status` (Ugift/Gift/Skilt/Enke → schema), `region` (11 fylke codes + urban/suburban/rural), `birth_location`, `industry_sector` (NACE Rev.2 → schema), `housing_tenure`, `urbanization`, `birth_country_detail`
- [x] Task 2.4 — Create `anxiety_synthetic/ssb_population/constants.py` with all table ID constants and variable code constants; import `VALID_AGE_GROUPS` and `AGE_GROUP_BOUNDS` from `scb_population.constants`

**Files Modified:**
- `config/assets/ssb_reference/category_mappings.json` — new file
- `anxiety_synthetic/ssb_population/constants.py` — new file, ~50 lines

**Dependencies:** Phase 1 (needs `SSBPxWebClient` to call metadata endpoints)

### Phase 3: Fetch Service
**Goal:** Implement `SSBFetchService` — 16 fetch methods that return `PopulationDistributions`.

- [x] Task 3.1 — Create `anxiety_synthetic/ssb_population/parsers.py`: import `_helpers.py` json-stat2 extractor; add Norwegian label normalisers (`parse_sex()`, `parse_education()`, `parse_civil_status()`, `parse_region()`, `parse_industry()`, etc.)
- [x] Task 3.2 — Create `anxiety_synthetic/ssb_population/fetch_service.py`: `SSBFetchService` class with `fetch_age_sex()`, `fetch_education_by_age()`, `fetch_employment_by_sex_education()`, and one method per remaining dimension; each method calls `SSBPxWebClient.fetch_table()` then the appropriate parser
- [x] Task 3.3 — Implement `SSBFetchService.load_all(client) -> PopulationDistributions` orchestrating all fetches and constructing the dataclass
- [x] Task 3.4 — For dimensions with sparse SSB data (income deciles, parental structure): implement simplified 2–3 category fallback distributions rather than raising

**Files Modified:**
- `anxiety_synthetic/ssb_population/parsers.py` — new file, ~150 lines
- `anxiety_synthetic/ssb_population/fetch_service.py` — new file, ~300 lines

**Dependencies:** Phase 2

### Phase 4: Sample Service and Entry Points
**Goal:** Implement `SSBSampleService`; create generation and analysis scripts.

- [x] Task 4.1 — Create `anxiety_synthetic/ssb_population/sample_service.py`: replicate the 11-step conditional sampling chain from `scb_population/sample_service.py`; replace Swedish label maps with Norwegian equivalents (`_NUS_TO_EMPLOYMENT_EDU`, `_EMPLOYMENT_TO_INC_KEY`, `_NORWAY_LABELS`); keep identical `sample_population(distributions, rng, n) -> list[dict]` signature
- [x] Task 4.2 — Create `anxiety_synthetic/ssb_population/__init__.py` (empty)
- [x] Task 4.3 — Create `scripts/generate_ssb_population.py`: `--n`, `--seed`, `--output` CLI args; flow: `SSBPxWebClient` → `SSBFetchService.load_all()` → `SSBSampleService.sample_population()` → JSON output with `metadata.country = "Norway"` and `metadata.source = "SSB PxWebApi v2"`
- [x] Task 4.4 — Create `scripts/analyze_ssb_population.py`: parallel to `scripts/analyze_scb_population.py`; loads Norwegian population JSON (already schema-normalised, no raw→flat conversion needed); produces distribution plots in `data/analysis/<stem>/`

**Files Modified:**
- `anxiety_synthetic/ssb_population/sample_service.py` — new file, ~280 lines
- `anxiety_synthetic/ssb_population/__init__.py` — new file, empty
- `scripts/generate_ssb_population.py` — new file, ~100 lines
- `scripts/analyze_ssb_population.py` — new file, ~150 lines

**Dependencies:** Phase 3

---

## Testing Plan

### Unit Tests
*(No test suite currently. Verification is manual/smoke-test.)*

### Integration Tests
- [ ] Verify `SCBPxWebClient` still fetches live SCB data after refactor — run `generate_scb_population.py --n 50`
- [ ] Verify `SSBPxWebClient` fetches table 07459 metadata without errors
- [ ] Verify `SSBFetchService.load_all()` completes without HTTP 429 (rate limiter working)

### Manual Verification
- [ ] `python scripts/generate_ssb_population.py --n 500 --seed 42 --output ssb_test.json` — check exit code 0
- [ ] Inspect `ssb_test.json`: `metadata.country == "Norway"`, `len(individuals) == 500`, all 17 fields present in `individuals[0]`
- [ ] `python scripts/analyze_ssb_population.py ssb_test.json` — plots appear in `data/analysis/ssb_test/`
- [ ] `python scripts/compare_populations.py ssb_test.json ssb_test2.json` (two seeds) — comparison report generated
- [ ] `python scripts/generate_scb_population.py --n 50 --seed 1` — still works, confirming SCB backward compat

### Edge Cases
- [ ] Large query hitting URL length limit (>2100 chars) — verify POST fallback fires
- [ ] SSB table unavailable / HTTP error — verify informative exception raised (not silent fallback)
- [ ] Dimension with zero-count cells in distribution — verify sampling fallback activates and logs warning
- [ ] `--seed 0` — verify deterministic output across two runs

---

## Documentation Plan

- [x] Update `CLAUDE.md` — add `ssb_population/` to Architecture section; add `generate_ssb_population.py` and `analyze_ssb_population.py` to Commands section
- [ ] No README update required (CLAUDE.md is the canonical dev reference for this project)

---

## Rollback Plan

All changes are additive (new files + subclassing). If the `SCBPxWebClient` refactor breaks something:

1. Restore `scb_client.py` from git (`git checkout HEAD -- anxiety_synthetic/utils/scb_client.py`)
2. Delete `anxiety_synthetic/utils/pxweb_client.py`
3. All SCB generation is restored; SSB module becomes inert (no callers)

No database migrations, no data file changes, no breaking interface changes.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| SSB table IDs in findings are wrong/outdated | Med | Med | Verify all table IDs via `get_table_metadata()` before implementing fetch methods; SSB Statbank search as fallback |
| Some dimensions missing from SSB (parental structure, income) | High | Low | Implement simplified 2–3 category fallback; document in `category_mappings.json` |
| PxWebApi v2 response schema differs from SCB json-stat2 in edge cases | Low | Med | Test all 16 dimension fetches against live API before building sample service |
| Rate limiter too conservative / too aggressive | Low | Low | Log rate-limit sleeps; tune from 2.1s if 429s still occur |
| `SCBPxWebClient` refactor introduces regression | Low | High | Run SCB smoke-test immediately after Phase 1 before proceeding |

---

## References

- Research: `docs/development/plans/pending/investigate-international-statistical-apis-findings.md`
- SSB PxWebApi v2 docs: `https://data.ssb.no/api/pxwebapi/v2/openapi.json`
- SSB table browser: `https://www.ssb.no/en/statbank`
- SSB KLASS API (classification codes): `https://data.ssb.no/api/klass/v1/`
