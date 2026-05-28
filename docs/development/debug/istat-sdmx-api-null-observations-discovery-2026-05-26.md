# Investigation Report: ISTAT SDMX API Null Observations — Root Cause & Fix

**Date:** 2026-05-26
**Author:** Basil + Claude
**Status:** Complete — root cause found, fix path identified
**Related:** `docs/development/plans/active/italy-istat-population-generator.md`, `scripts/test_istat_discovery.py`

---

## Problem Statement

The Italy ISTAT population generator (`scripts/generate_istat_population.py`) fails at runtime because all ISTAT SDMX REST API responses contain **null observation values**. The API returns correct data structures (dimensions, series keys, metadata) but every observation value is `null`. This was documented as a post-implementation blocker in the Italy plan (Phase 8).

Affected dataflows:
- `52_1194` — Education by age/sex
- `150_938` — Employment (thousands)
- `32_292` — Net family income
- `22_289` — Resident population (civil status)

All of these are queried via `ISTATSDMXClient.fetch_data()` with `format=jsondata`.

---

## Investigation Methodology

A systematic discovery script (`scripts/test_istat_discovery.py`) was created to:

1. **Parse the ISTAT dataflow catalog** (4,849 dataflows from cached XML) to find relevant child dataflows and alternatives
2. **Search by keyword** (Italian + English) across all dataflow names, descriptions, and layout annotations
3. **Probe candidates** with the JSON format and various key filters
4. **Test the CSV format** as an alternative serializer
5. **Validate Eurostat alternatives** for every demographic field

---

## Root Cause

**The ISTAT SDMX REST API's JSON serializer (`format=jsondata`) is broken.** It returns well-formed SDMX-JSON 2.0 responses with correct dimensions, series keys, and metadata — but all observation values are serialized as `null`.

The CSV serializer (`format=csv`) returns the **same data correctly** with actual numeric values.

### Proof

Dataflow `150_938_DF_DCCV_OCCUPATIT1_1` (Employment by age class), same date range (2021–2023):

| Format | Series | Non-null Obs | Null Obs | Status |
|--------|--------|-------------|----------|--------|
| `format=jsondata` | 576 | **0** | 4,896 | Broken |
| `format=csv` | — | **3,456** | 0 | Working |

This pattern is **systemic** — every ISTAT SDMX dataflow tested exhibits the same behavior. It is not specific to certain dataflows, date ranges, or key filters.

---

## Comprehensive Test Results

### ISTAT Dataflows via CSV Format

All critical ISTAT dataflows return real data when queried with `format=csv`:

| Field | Child Dataflow | CSV Rows | Date Range | Key Dimensions |
|-------|---------------|----------|------------|----------------|
| Education × age × edu level | `52_1194_DF_DCCV_POPTIT1_UNT2020_1` | 4,450 | 2020–2023 | SEX, AGE, EDU_LEV_HIGHEST, CITIZENSHIP |
| Education × region | `52_1194_DF_DCCV_POPTIT1_UNT2020_2` | — | 2020–2023 | REF_AREA, EDU_LEV_HIGHEST |
| Education × nationality | `52_1194_DF_DCCV_POPTIT1_UNT2020_3` | — | 2020–2023 | CITIZENSHIP, EDU_LEV_HIGHEST |
| Employment × gender | `150_938_DF_DCCV_OCCUPATIT1_21` | 1,953 | 2022–2023 | SEX, AGE |
| Employment × age class | `150_938_DF_DCCV_OCCUPATIT1_1` | 3,456 | 2022–2023 | AGE, SEX |
| Employment × education | `150_938_DF_DCCV_OCCUPATIT1_17` | 2,250 | 2022–2023 | EDU_LEV_HIGHEST, SEX |
| Employment × occupation | `150_938_DF_DCCV_OCCUPATIT1_14` | 2,808 | 2022–2023 | OCCUPATION_2011, SEX |
| Employment × NACE sector | `150_938_DF_DCCV_OCCUPATIT1_22` | 5,206 | 2022–2023 | ECON_ACTIVITY_NACE_2007, SEX |
| Employment × prof status + FT/PT | `150_938_DF_DCCV_OCCUPATIT1_18` | — | 2022–2023 | PROF_STATUS, FULL_PART_TIME |
| Employment × temp/perm × age | `150_938_DF_DCCV_OCCUPATIT1_6` | — | 2022–2023 | PERM_TEMP_EMPLOYEES, AGE |
| Income × household size | `32_292_DF_DCCV_REDNETFAMFONTERED_1` | 800 | 2020–2023 | NUM_MEMB, FAM_MAIN_INCOME_SOURCE |
| Income × sex of earner | `32_292_DF_DCCV_REDNETFAMFONTERED_5` | 680 | 2020–2023 | SEX, FAM_MAIN_INCOME_SOURCE |
| Income × age of earner | `32_292_DF_DCCV_REDNETFAMFONTERED_6` | 1,160 | 2020–2023 | AGE, FAM_MAIN_INCOME_SOURCE |
| Income × education of earner | `32_292_DF_DCCV_REDNETFAMFONTERED_7` | — | 2020–2023 | EDU_LEV_HIGHEST, FAM_MAIN_INCOME_SOURCE |
| Income × prof status of earner | `32_292_DF_DCCV_REDNETFAMFONTERED_8` | — | 2020–2023 | PROF_STATUS, FAM_MAIN_INCOME_SOURCE |
| Civil status × sex × age | `22_289_DF_DCIS_POPRES1_25` | 72 | 2023–2024 | SEX, AGE, MARITAL_STATUS |

**Note on education dataflows:** The `52_1194_DF_*_UNT2020_*` dataflows require `startPeriod=2020` or earlier. Requesting `startPeriod=2021` returns 404 (NoRecordsFound) because "UNT2020" indicates data under the previous regulation ending 2020, though data extends to 2023.

### ISTAT Dataflows via JSON Format (all broken)

Every ISTAT SDMX dataflow returns null observations with `format=jsondata`:

| Dataflow | JSON Series | Non-null | Null | Verdict |
|----------|------------|----------|------|---------|
| `150_938_DF_DCCV_OCCUPATIT1_1` | 576 | 0 | 4,896 | **ALL NULL** |
| `150_938_DF_DCCV_OCCUPATIT1_10` | varies | 0 | all | **ALL NULL** |
| `150_938_DF_DCCV_OCCUPATIT1_11`–`_18` | varies | 0 | all | **ALL NULL** |
| `32_292_DF_DCCV_REDNETFAMFONTERED_1` | 160 | 0 | 640 | **ALL NULL** |
| `32_292_DF_DCCV_REDNETFAMFONTERED_5` | 136 | 0 | 544 | **ALL NULL** |
| `172_931_DF_DCCV_NEET1_2` (NEET) | varies | 0 | all | **ALL NULL** |

This confirms the problem is in the ISTAT SDMX-JSON serializer, not in specific dataflows or query parameters. Key filters (`A.IT............`, `A...............`) do not help — the structure is returned but observations remain null.

### Eurostat Alternatives (all working)

All Eurostat JSON-stat 2.0 datasets return correct Italy data:

| Dataset | Field | Non-null Values | Key Dimensions |
|---------|-------|----------------|----------------|
| `edat_lfs_9911` | Education by age/sex (%) | 7,616 | sex, isced11, citizen, age |
| `edat_lfse_03` | Education by sex (15-64) | 2,667 | sex, age, isced11 |
| `lfsa_pganws` | Employment by status | 12,465 | sex, citizen, age, wstatus |
| `lfsa_urgaed` | Unemployment by education | 2,558 | sex, age, isced11 |
| `lfsa_egised` | Employment by ISCO-08 × ISCED | 1,639 | age, sex, isco08, isced11 |
| `lfsa_epgaed` | Employment rates by education | 4,813 | sex, age, isced11, worktime |
| `lfsa_eisn2` | Employment by ISCO-08 × NACE | 5,312 | age, sex, nace_r2, isco08 |
| `ilc_di03` | Mean income by age/sex | 2,376 | age, sex, statinfo |
| `ilc_di01` | Income distribution by quantiles | 1,008 | quantile, statinfo |
| `ilc_di04` | Mean income by household type | 540 | hhcomp, statinfo |
| `ilc_di11` | Median income ratio | 54 | age, sex |
| `lfst_hhnhtych` | Households by type | 1,044 | agechild, n_child, phhcomp |
| `ilc_lvph02` | Households by size | 102 | hhcomp |
| `demo_pjanmarst` | Marital status (discontinued) | **404** | — |
| `cens_01rms` | Census marital status (discontinued) | **404** | — |
| `cens_11ms_r3` | 2011 census marital status | 756 | age, sex, marsta (2011 only) |

**Marital status gap:** No current Eurostat dataset provides population by marital status for Italy. The only option is `cens_11ms_r3` (2011 census, outdated) or the ISTAT `22_289_DF_DCIS_POPRES1_25` via CSV (which has 2023–2024 data).

---

## Catalog Discovery Summary

The ISTAT dataflow catalog (4,849 dataflows, 364 file-only) was searched by keyword for each demographic field. Key structural finding: ISTAT uses a **parent/child dataflow pattern**.

- **Parent dataflow** (e.g., `150_938`): umbrella containing all series; queries return massive responses or timeout
- **Child dataflows** (e.g., `150_938_DF_DCCV_OCCUPATIT1_1` through `_26`): pre-filtered views with specific dimension slices (by age, gender, education, NACE sector, etc.)

| Parent | Children Found | Description |
|--------|---------------|-------------|
| `52_1194` | 3 | Education level: by age, by region, by nationality |
| `150_938` | 26 | Employment: by age, gender, education, NACE, occupation, prof status, FT/PT, temp/perm |
| `32_292` | 9 | Income: by household size, type, children, elderly, sex/age/education/prof status of earner, region |
| `22_289` | 29 | Resident pop: by region (20), by age, marital status, age+marital, dashboard |

Keyword search also identified alternative dataflows outside the known parents (e.g., `172_931` NEET, `151_929` unemployment, census dataflows `DF_DCSS_*`).

---

## Recommended Fix

### Primary Strategy: Switch `ISTATSDMXClient` to CSV Format

Modify `src/population_synth/clients/istat_client.py`:

1. Change `fetch_data()` to use `format=csv` instead of `format=jsondata`
2. Parse CSV responses instead of JSON
3. Cache the CSV text (or parse into dict and cache as JSON)
4. Return parsed data in the same dict structure the existing parsers expect

This is a **client-level change** — the parsers in `italy/parsers.py` would need to be updated to accept the CSV-derived data format, or the client can transform CSV rows into the SDMX-JSON structure the parsers already handle.

### Alternative Strategy: Use Child Dataflows + Specific Date Ranges

Instead of querying parent dataflows, use the specific child dataflow IDs that return the exact dimension slices needed:

| Current (parent) | Recommended (child) |
|-------------------|---------------------|
| `52_1194` (all education) | `52_1194_DF_DCCV_POPTIT1_UNT2020_1` (education × age) |
| `150_938` (all employment) | Multiple: `_1` (age), `_17` (education), `_22` (NACE), `_14` (occupation) |
| `32_292` (all income) | `_1` (household size), `_5` (sex), `_6` (age) |
| `22_289_DF_DCIS_POPRES1_25` | Keep as-is (already a child) |

### Date Range Requirements

| Dataflow Pattern | Required `startPeriod` | Notes |
|-----------------|----------------------|-------|
| `*_UNT2020_*` | 2020 or earlier | "Until 2020" regulation; 404 if `startPeriod > 2020` |
| `150_938_DF_*` | 2022 or earlier | Current regulation; data available 2004–2024 |
| `32_292_DF_*` | 2020 or earlier | Income data; available 2003–2022 |
| `22_289_DF_*` | 2023 or earlier | Civil status; available 2002–2024 |

### Phase 8 Impact

The original Phase 8 plan proposed replacing all ISTAT sources with Eurostat equivalents. With the CSV fix:

- **No longer needed:** Eurostat replacements for education, employment, industry, income
- **Still needed:** Hardcoded values where no API source exists (parental structure)
- **Still valuable:** Eurostat data as validation/cross-check against ISTAT figures
- **Marital status:** ISTAT CSV works (`22_289_DF_DCIS_POPRES1_25`); Eurostat has no current equivalent

---

## Rate Limiting Notes

The ISTAT API enforces a ~5 req/min hard limit. Exceeding this results in connection-level timeouts (not HTTP 429). The existing 12-second interval in `ISTATSDMXClient` is correct and sufficient. However:

- Burst testing across multiple scripts simultaneously triggered blocking
- The `22_289` resident population parent dataflow consistently times out even within rate limits (too many municipality-level series)
- Child dataflows respond within 1–3 seconds when within rate limits

---

## Artifacts

- **Discovery script:** `scripts/test_istat_discovery.py`
- **Cached JSON probes:** `config/assets/istat_cache/discovery_*.json`
- **Cached CSV probes:** `config/assets/istat_cache/discovery_csv_*.csv`
- **Discovery results:** `data/istat_discovery/discovery_results.json`
- **ISTAT dataflow catalog:** `config/assets/istat_cache/dataflow_IT1.txt` (14 MB, 4,849 dataflows)

---

## Reproduction

```bash
# Quick CSV verification (proves the fix works)
python scripts/test_istat_discovery.py --csv-only --field education --max-per-field 3

# Full discovery (all fields, JSON + CSV + Eurostat)
python scripts/test_istat_discovery.py --max-per-field 5

# Catalog keyword search (no API calls)
python scripts/test_istat_discovery.py --skip-probes --keyword "marital status"
```
