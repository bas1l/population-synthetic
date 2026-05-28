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

- [x] Script runs end-to-end without errors: `python scripts/prototype_istat_api.py`
- [x] At least 4 ISTAT dataflows return valid data (population, education, employment, income)
- [x] At least 1 Eurostat dataset returns valid data for Italy
- [x] All raw responses cached in `config/assets/istat_cache/`
- [x] Console output shows dimension names, value counts, and data samples for each probe
- [x] No rate limit violations (no IP blocks triggered)
- [x] Written assessment of coverage: which fields map cleanly, which have gaps

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
- [x] Probe 2: Population by age/sex — Eurostat `demo_pjan` (ISTAT `22_289` consistently times out; see Findings)
- [x] Probe 3: Education levels — dataflow `52_1194_DF_DCCV_POPTIT1_UNT2020_1` (`52_912` returned 404)
- [x] Probe 4: Employment — dataflow `150_938`, Italy national, latest year
- [x] Probe 5: Income — dataflow `32_292`, Italy national, latest year
- [x] Print dimension names, dimension value counts, total observations, and 5-10 sample rows per probe

**Files Modified:**
- `scripts/prototype_istat_api.py` — Add probe functions

**Dependencies:** Phase 1

### Phase 3: Eurostat Probes and Coverage Report
**Goal:** Test Eurostat as supplement and produce coverage assessment

- [x] Probe 6: Eurostat population by age group — `demo_pjangroup` (`demo_pjanmarst` discontinued, returns 404)
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

## Investigation Findings

These findings are the primary output of this plan. A future implementer building `src/population_synth/population/italy/` should read this before writing any code.

### SDMX JSON response format (ISTAT)

ISTAT returns SDMX-JSON 2.0. The top-level envelope is `{meta, data, errors}` — **not** `{structure, dataSets}` as in SDMX-JSON 1.0. The mapping is:

| What you want | Path |
|---|---|
| Dimension list (series dims) | `data["data"]["structures"][0]["dimensions"]["series"]` |
| Dimension list (obs dims) | `data["data"]["structures"][0]["dimensions"]["observation"]` |
| Series dict | `data["data"]["dataSets"][0]["series"]` |
| Each dimension entry | `{"id": "SEX", "values": [{"id": "1", "name": "males"}, ...]}` |
| Each series key | Colon-separated positional indices, e.g. `"0:1:2:0:3:0"` |
| Each observation | `series[key]["observations"]` → `{"0": [value, ...], "1": [value, ...]}` |

Observation index maps to TIME_PERIOD via `dimensions["observation"][0]["values"]`.

### Eurostat JSON-stat format

Eurostat returns JSON-stat 2.0 (same format as for `ilc_lvho02`). Top-level keys include `id`, `size`, `dimension`, `value`:

| What you want | Path |
|---|---|
| Dimension order | `data["id"]` — ordered list of dimension IDs |
| Dimension labels | `data["dimension"][dim_id]["category"]["label"]` — `{code: name}` dict |
| Values | `data["value"]` — `{flat_index: value}` dict (sparse; missing = null) |
| Flat index → dim codes | Row-major stride over `data["size"]` in `data["id"]` order |

### Confirmed working dataflow IDs

| Field | Source | Dataflow ID | Dimensions confirmed |
|---|---|---|---|
| age_group | Eurostat | `demo_pjan` | age (103 single-year), sex (3), geo, time |
| sex | Eurostat | `demo_pjan` | — same — |
| education | ISTAT | `52_1194_DF_DCCV_POPTIT1_UNT2020_1` | EDU_LEV_HIGHEST (7), SEX (3), AGE (17), REF_AREA (6) |
| employment_status | ISTAT | `150_938` | SEX (3), AGE (16), EDU_LEV_HIGHEST (4), OCCUPATION_2011 (13), FULL_PART_TIME (3), PERM_TEMP_EMPLOYEES (3), REF_AREA (133) |
| income_bracket | ISTAT | `32_292` | HOUSEHOLD_TYPOLOGY (10), NUMBER_HOUSEHOLD_COMP (6), FAM_MAIN_INCOME_SOURCE (5), REF_AREA (36) |
| housing_tenure | Eurostat | `ilc_lvho02` | tenure (7), hhcomp (17), incgrp (3), geo, time |
| marital_status | ISTAT | `22_289_DF_DCIS_POPRES1_25` | (not probed — endpoint too large; see below) |

### Dataset IDs that did NOT work

| Planned ID | Problem | Correct alternative |
|---|---|---|
| `52_912` (education) | 404 — does not exist | `52_1194_DF_DCCV_POPTIT1_UNT2020_1` |
| `demo_pjanmarst` (Eurostat marital status) | 404 — dataset discontinued | ISTAT `22_289_DF_DCIS_POPRES1_25` (untested, likely too large) |

### Critical finding: ISTAT population endpoints are too slow

All ISTAT resident population endpoints (`22_289`, `22_289_DF_DCIS_POPRES1_1`, `22_315`, `22_389`, `DF_DCSS_POPRES_SERIES_TV_1`) timed out at 30–45 seconds. Root cause: these dataflows cover all 7,900+ Italian municipalities × many age/sex/marital combinations, producing millions of series. The server does not respond within a usable timeout.

**Implication for the real client:** Do NOT use ISTAT `22_289` for age/sex/region distributions. Use Eurostat instead:
- Age × sex: `demo_pjan` (single-year ages, confirmed working, ~17 KB response)
- Age × sex × region (NUTS2): `demo_r_pjangrp3` or `demo_r_d2jan` (untested — check Eurostat)
- Marital status: Eurostat `demo_pjanmarst` is discontinued; try `demo_pjanind` or ISTAT bulk download

**Workaround if ISTAT population data is required:** Use the DSD endpoint (`GET /rest/datastructure/IT1/DCIS_POPRES1`) to read dimension metadata (fast, ~15 KB), then construct a minimal key filter for a single REF_AREA+year before fetching data. The DSD confirmed dimensions: `FREQ, REF_AREA, DATA_TYPE, SEX, AGE, MARITAL_STATUS`.

### Rate limiting

12-second gap between ISTAT requests worked without incident. No 429 responses, no IP block. The documented 5 req/min limit appears to apply per-endpoint or per-session. Caching all responses on first run is essential.

### XML dataflow listing

The dataflow listing (`GET /rest/dataflow/IT1`) returns SDMX-ML XML with namespace-prefixed tags: `<structure:Dataflow id="..." ...>`. Count `<structure:Dataflow` (not `<Dataflow `) to get the total. As of 2026-05-25: **4,850 dataflows** confirmed in the IT1 agency.

### Field coverage summary for real implementation

| Status | Fields | Notes |
|---|---|---|
| **Clean** (Eurostat) | age_group, sex | `demo_pjan`, works today |
| **Clean** (ISTAT) | education, employment_status, income_bracket | Probed and confirmed |
| **Needs investigation** | region | Eurostat `demo_r_*` family; ISTAT too slow |
| **Needs investigation** | marital_status | ISTAT has it (`22_289_DF_DCIS_POPRES1_25`) but endpoint too large; try bulk or Eurostat |
| **Needs investigation** | housing_tenure | Eurostat `ilc_lvho02` works but is EU-SILC (survey, not census) |
| **Needs investigation** | migration_background | ISTAT `29_348` (residence permits) exists; needs code mapping |
| **Gap — no source** | occupation | ISTAT employment has `OCCUPATION_2011` (13 classes) but not standalone |
| **Gap — proxy only** | household_size | ISTAT income `32_292` has `NUMBER_HOUSEHOLD_COMP`; not a population marginal |
| **Gap — not in statistics** | religiosity | No official source; use prior distribution or drop field |
| **Gap — complex** | health_status | EHIS survey exists but multi-table, irregular cadence |

---

## References

- Prior research: `docs/development/plans/pending/investigate-international-statistical-apis-findings.md` (Italy = Tier 3)
- Prior research: `docs/development/plans/pending/investigate-international-statistical-apis.md`
- Norway precedent: `docs/development/plans/completed/norway-ssb-population-generator.md`
- ISTAT SDMX API: `https://esploradati.istat.it/SDMXWS/rest/`
- Eurostat API: `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/`
- Probe script: `scripts/prototype_istat_api.py`
- Cached responses: `config/assets/istat_cache/` (git-ignored; re-run script to regenerate)
