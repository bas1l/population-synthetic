# Plan: Prototype ISTAT API Access

**Date:** 2026-05-25
**Author:** Basil
**Status:** In Progress
**Started:** 2026-05-25
**Base Branch:** `feature/compare-all-pipelines`
**Branch:** `feature/prototype-istat-api`

---

## Overview

Build a standalone probe script that verifies ISTAT (Italy) and Eurostat API access, examines response formats, and caches raw results. This is a prerequisite investigation before committing to a full Italy country implementation. The project's international API research (see `docs/development/plans/pending/investigate-international-statistical-apis-findings.md`) classified Italy as Tier 3 (MEDIUM feasibility) — this prototype validates that assessment with live data.

## Problem Statement

The project supports Sweden (SCB) and Norway (SSB) for demographic distributions. Italy/ISTAT uses SDMX REST instead of PxWeb, so we cannot predict the actual response structure, dimension naming, or data availability from documentation alone. A live probe is needed to:
- Confirm endpoints are reachable and return data
- Reveal the exact SDMX JSON structure for parser design
- Identify which dataflows cover each demographic field
- Test the 5 req/min rate limit boundary
- Compare ISTAT vs Eurostat data granularity

## Goals

### In Scope
1. Standalone probe script that fetches 4-5 ISTAT dataflows and 1-2 Eurostat datasets
2. Local caching of all raw responses for offline inspection
3. Console output summarizing dimensions, value counts, and sample data per dataflow
4. Rate limiting at 12s+ between ISTAT requests
5. Coverage assessment: which of the 14 `PopulationDistributions` fields are available

### Out of Scope
- New client class in `src/population_synth/clients/` (that's for the full implementation)
- New country module in `src/population_synth/population/italy/` (future plan)
- Parsers, label maps, or sample services
- Integration with existing generation scripts or GUI
- Any modifications to existing project code

## Success Criteria

- [ ] Script runs end-to-end without errors: `python scripts/prototype_istat_api.py`
- [ ] At least 4 ISTAT dataflows return valid data (population, education, employment, income)
- [ ] At least 1 Eurostat dataset returns valid data for Italy
- [ ] All raw responses cached in `config/assets/istat_cache/`
- [ ] Console output shows dimension names, value counts, and data samples for each probe
- [ ] No rate limit violations (no IP blocks triggered)
- [ ] Written assessment of coverage: which fields map cleanly, which have gaps

---

## Technical Design

### Approach

Single standalone script using only `requests` (already a project dependency). No new packages, no imports from `population_synth`. Each probe function checks cache first, then fetches with rate limiting, then prints a structured summary.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Raw `requests` script | No dependencies, full control over caching/rate-limiting, inspectable raw JSON | More boilerplate | **Chosen** |
| `istatapi` library | Higher-level API, DataFrame output | Hides response structure we need to understand; adds dependency | Rejected |
| `sdmx1` library | Multi-agency support, structured parsing | Overkill for a probe; hides raw format | Rejected |
| Jupyter notebook | Interactive exploration | Not reproducible as a script; not consistent with project conventions | Rejected |

### Architecture Changes

**None.** This plan adds one script file and one cache directory. No changes to existing code.

```
scripts/
  prototype_istat_api.py          # NEW — standalone probe script

config/assets/
  istat_cache/                    # NEW — cached raw responses (git-ignored)
```

---

## Implementation Plan

### Phase 1: Script Scaffold and Rate Limiter
**Goal:** Working script skeleton with caching and rate limiting infrastructure

- [x] Create `scripts/prototype_istat_api.py` with `main()` entry point
- [x] Implement `_load_cache(key)` / `_save_cache(key, data)` using `config/assets/istat_cache/`
- [x] Implement rate limiter: track last request time, enforce 12s minimum gap between ISTAT calls
- [x] Implement `_fetch_istat(dataflow_id, key_filter, params)` with cache-first + rate-limited GET
- [x] Implement `_fetch_eurostat(dataset_code, params)` with cache-first GET (no rate limit needed)
- [x] Implement `_print_summary(label, data)` to display dimension structure and sample values

**Files Modified:**
- `scripts/prototype_istat_api.py` — New file, entire script

**Dependencies:** None

### Phase 2: ISTAT Probes
**Goal:** Fetch and summarize 4-5 key ISTAT dataflows

- [x] Probe 1: Dataflow listing — `GET /rest/dataflow/IT1` to confirm API is reachable
- [x] Probe 2: Population by age/sex — dataflow `22_289`, Italy national, latest year
- [x] Probe 3: Education levels — dataflow `52_912`, Italy national, latest year
- [x] Probe 4: Employment — dataflow `150_938`, Italy national, latest year
- [x] Probe 5: Income — dataflow `32_292`, Italy national, latest year
- [x] Print dimension names, dimension value counts, total observations, and 5-10 sample rows per probe

**Files Modified:**
- `scripts/prototype_istat_api.py` — Add probe functions

**Dependencies:** Phase 1

### Phase 3: Eurostat Probes and Coverage Report
**Goal:** Test Eurostat as supplement and produce coverage assessment

- [x] Probe 6: Eurostat marital status — `demo_pjanmarst` for Italy, JSON-stat format
- [x] Probe 7: Eurostat housing tenure — `ilc_lvho02` for Italy (if available)
- [x] Print coverage matrix: 14 `PopulationDistributions` fields vs. data source (ISTAT / Eurostat / gap)
- [x] Print overall assessment summary at end of script run

**Files Modified:**
- `scripts/prototype_istat_api.py` — Add Eurostat probes and coverage report

**Dependencies:** Phase 2

---

## Testing Plan

### Manual Verification
- [ ] Run `python scripts/prototype_istat_api.py` — full script completes without error
- [ ] Verify cached files appear in `config/assets/istat_cache/`
- [ ] Re-run script — confirm it uses cache (no API calls, instant completion)
- [ ] Inspect one cached JSON file manually to understand SDMX response structure
- [ ] Confirm no rate limit violation (script takes ~60s for 5 ISTAT probes at 12s intervals)

### Edge Cases
- [ ] API endpoint unreachable (network error) — script should print clear error, not crash
- [ ] Dataflow returns empty data — script should report "no observations" rather than crash
- [ ] Cache directory doesn't exist — script should create it

---

## Documentation Plan

- [ ] Script includes `--help` / argparse usage showing what it does
- [ ] Console output is self-documenting (labeled sections, dimension tables)
- [ ] No external docs needed — this is a throwaway probe, not a shipped feature

---

## Rollback Plan

This plan adds one script and one cache directory. Rollback is trivial:
1. Delete `scripts/prototype_istat_api.py`
2. Delete `config/assets/istat_cache/`

No existing code is modified.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| IP blocked by ISTAT rate limiter | Low | High (1-2 day block) | 12s minimum between requests (well under 5/min); cache everything on first run |
| ISTAT API endpoint changed/down | Low | Med | Fallback to Eurostat-only probes; report in console |
| Dataflow IDs from research are wrong | Med | Low | Script prints available dataflows first; adjust IDs from that list |
| SDMX JSON format differs from docs | Med | Low | Script prints raw structure; we adapt parser design based on actual format |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1: Scaffold | ~30 min | None |
| Phase 2: ISTAT probes | ~30 min | Phase 1 |
| Phase 3: Eurostat + coverage | ~20 min | Phase 2 |

---

## References

- Prior research: `docs/development/plans/pending/investigate-international-statistical-apis-findings.md` (Italy = Tier 3)
- Prior research: `docs/development/plans/pending/investigate-international-statistical-apis.md`
- Norway precedent: `docs/development/plans/completed/norway-ssb-population-generator.md`
- ISTAT SDMX API: `https://esploradati.istat.it/SDMXWS/rest/`
- Eurostat API: `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/`
- Investigation plan: `.claude/plans/investigate-if-information-regarding-purrfect-knuth.md`
