# Italy (ISTAT/Eurostat) Population Data Sources

**Date:** 2026-05-26
**Status:** Current

---

## Overview

The Italy population generator produces synthetic individuals by conditional chained sampling from real demographic distributions fetched from two live statistical APIs:

- **Eurostat** (JSON-stat 2.0) -- EU-level datasets filtered to `geo=IT`
- **ISTAT** (SDMX REST, CSV format) -- Italian national statistical institute, child dataflows with 15-second rate limiting

All distributions are derived exclusively from API data. No field uses hardcoded probability distributions, fallback approximations, or parametric models as its primary source. If an API does not provide data for a field, that field is dropped from the output rather than substituted with invented values. The pipeline fails fast on API errors — no silent fallbacks.

---

## Field-by-Field Data Source Matrix

| # | Output Field | API Source | Dataset / Dataflow ID | Protocol | Dimensions Used | Notes |
|---|---|---|---|---|---|---|
| 1 | `age` + `biological_sex` | Eurostat | `demo_pjan` | JSON-stat | age (Y18..Y85), sex (M/F) | Single-year ages, joint distribution |
| 2 | `education_level` | ISTAT | `52_1194_DF_DCCV_POPTIT1_UNT2020_1` | SDMX CSV | EDU_LEV_HIGHEST, SEX, AGE | Conditional on (age_group, sex). ISCED 0-8 mapped to 3 levels |
| 3 | `employment_status` | ISTAT | `150_938_DF_DCCV_OCCUPATIT1_17` + `52_1194_DF_*_1` | SDMX CSV | SEX, EDU_LEV_HIGHEST, OBS_VALUE | Conditional on (sex, education). Employment rate derived from ratio of employed counts (150_938) to total population (52_1194). Categories: Employed, Not Employed |
| 4 | `socioeconomic_class` | ISTAT | `32_292_DF_DCCV_REDNETFAMFONTERED_6` | SDMX CSV | SEX_MAIN_PERCEPTOR, AGE_MAIN_EARNIER, OBS_VALUE | Conditional on (age_group, sex). Observed income values classified directly into 4 classes via AROP/OECD thresholds relative to global median |
| 5 | `birth_location` | Eurostat | `migr_pop1ctz` | JSON-stat | citizen (country codes) | 3 categories: Italy, Europe (Other), Outside Europe |
| 6 | `region` | Eurostat | `demo_r_pjangrp3` | JSON-stat | geo (NUTS2 codes) | 20 Italian regions. Fallback dataset: `demo_r_d2jan` |
| 7 | `parental_structure` | Eurostat | `ilc_lvph02` | JSON-stat | hhcomp (A1, A1_DCH, A2, A2_DCH*, A_GE3*) | 5 categories: Living Alone, Single Parent, Couple without Children, Nuclear Family, Extended Family |
| 8 | `civil_status` | ISTAT | `22_289_DF_DCIS_POPRES1_25` | SDMX CSV | MARITAL_STATUS, AGE, SEX | Conditional on (age_group, sex). 6 statuses: Single, Married, Divorced, Widowed, Separated, Civil Partnership |
| 9 | `industry_sector` | ISTAT | `150_938_DF_DCCV_OCCUPATIT1_14` | SDMX CSV | OCCUPATION_2011 | Employed persons only. ATECO 2007 single-letter NACE codes (A-U) |
| 10 | `employment_type` | ISTAT | `150_938_DF_DCCV_OCCUPATIT1_18` | SDMX CSV | FULL_PART_TIME, PERM_TEMP_EMPLOYEES | Employed persons only. Composite: contract (Permanent/Temporary/Unspecified) x hours (Full-time/Part-time). Contract type is "Unspecified" when the PERM_TEMP dimension has no per-status variation |
| 11 | `housing_tenure` | Eurostat | `ilc_lvho02` | JSON-stat | tenure (OWN*/RENT*), incgrp=TOTAL, hhcomp=TOTAL | 2 categories: Owner-occupied, Rental |
| 12 | `household_size` | Eurostat | `ilc_lvph03` | JSON-stat | n_person (1, 2, 3, 4, 5, GE6) | 6 categories from API labels. Unit: percentage of households |
| 13 | `birth_country_detail` | Eurostat | `migr_pop1ctz` | JSON-stat | citizen (per-country codes) | Top origin countries for non-Italy-born. Reuses same dataset as birth_location (cache hit) |
| 14 | `ethnicity_map` | -- | -- | -- | -- | Empty dict (no API source; same as Sweden/Norway) |

### Fields Not in Output (No API Source)

| Field | Reason Dropped |
|---|---|
| `income_source` | No available API cross-tabulates income source composition by employment status. ISTAT `32_292` has the codelist defined but `LABPROF_STATUS_C_MAIN_EARNER` is always published as total (code 99). Eurostat `ilc_di06` covers 1995-2001 only (stale). The cross-tabulation exists only in EU-SILC microdata files, which are not API-accessible. |
| `religiosity` | No statistical source (same as Sweden/Norway) |
| `health_status` | No statistical source (same as Sweden/Norway) |

---

## API Protocols

### Eurostat JSON-stat 2.0

- **Base URL:** `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset_id}`
- **Method:** GET with query parameters (`geo=IT`, `format=JSON`, `sinceTimePeriod=YYYY`)
- **Response:** JSON-stat 2.0 -- same format as SCB/SSB. Flat index with row-major strides over `id`/`size` arrays
- **Rate limiting:** None required (public API, generous limits)
- **Cache:** `config/assets/eurostat_cache/`, 90-day TTL
- **Authentication:** None

### ISTAT SDMX REST (CSV)

- **Base URL:** `https://esploradati.istat.it/SDMXWS/rest/data/{agency},{dataflow_id},{version}`
- **Method:** GET with `format=csv`, `startPeriod`/`endPeriod` constraints
- **Response:** CSV rows parsed via `csv.DictReader` into `list[dict]`
- **Rate limiting:** 15-second minimum between requests (ISTAT enforces ~5 req/min hard limit)
- **Cache:** `config/assets/istat_cache/`, 90-day TTL
- **Authentication:** None
- **Known issue:** The ISTAT SDMX JSON serializer (`format=jsondata`) is broken -- all observations are null. CSV format works correctly. See `docs/development/debug/istat-sdmx-api-null-observations-discovery-2026-05-26.md`

---

## ISTAT Dataflow Architecture

ISTAT organises datasets as parent/child dataflow hierarchies. The parent ID identifies a thematic area; child suffixes (`_1`, `_6`, `_14`, `_17`, `_18`) select specific cross-tabulations within that area.

| Parent ID | Theme | Children Used |
|---|---|---|
| `52_1194` | Population census (UNT2020) | `_1` -- education by age/sex |
| `150_938` | Labour Force Survey (occupati) | `_14` -- industry/occupation, `_17` -- employment by education, `_18` -- FT/PT + contract type |
| `32_292` | Household income (EU-SILC) | `_6` -- income by age of earner |
| `22_289` | Resident population | `_25` -- civil status by age/sex |

### Date Range Constraints

Each dataflow family requires specific time period constraints:

| Family | `startPeriod` | `endPeriod` | Reason |
|---|---|---|---|
| `52_1194` (education) | 2020 | 2023 | UNT2020 census-based; requires `startPeriod <= 2020` |
| `150_938` (employment) | 2022 | 2023 | LFS data available from 2022 |
| `32_292` (income) | 2020 | 2023 | EU-SILC data from 2020 |
| `22_289` (civil status) | 2023 | 2024 | Latest available year |

---

## Eurostat Dataset Details

### `demo_pjan` -- Population by age and sex

Single-year age codes (`Y0`, `Y1`, ..., `Y99`, `Y_OPEN`). Filtered to ages 18-85 and sex M/F (Total excluded). Latest year selected automatically.

### `demo_r_pjangrp3` -- Population by NUTS2 region

20 Italian NUTS2 regions (ITC1-ITG2). Sums over age groups and sexes per region. Fallback dataset `demo_r_d2jan` used if primary lacks Italian NUTS2 codes.

### `ilc_lvph02` -- Population by household type

Dimension `hhcomp` with 17 category codes. Mapped to 5 schema labels:

| Eurostat Code | Schema Label |
|---|---|
| `A1` (one adult, no dep. children) | Living Alone |
| `A1_DCH` (one adult with dep. children) | Single Parent |
| `A2` (two adults, no dep. children) | Couple without Children |
| `A2_DCH1`, `A2_DCH2`, `A2_DCH_GE3` (two adults + children) | Nuclear Family |
| `A_GE3`, `A_GE3_DCH` (three or more adults) | Extended Family |

Sub-codes for age/sex splits (A1_LT65, A1_GE65, F1, M1) and aggregate codes (TOTAL, DCH, NDCH) are skipped.

### `ilc_lvph03` -- Households by size

Dimension `n_person` with 6 categories: `1` (1 person), `2` (2 persons), `3` (3 persons), `4` (4 persons), `5` (5 persons), `GE6` (6 or more). Unit is percentage (PC). Labels from the API are used directly.

### `ilc_lvho02` -- Housing tenure

Dimension `tenure` mapped to Owner-occupied (OWN, OWN_L, OWN_NL) and Rental (RENT, RENT_MKT, RENT_FR). Filtered to `incgrp=TOTAL`, `hhcomp=TOTAL`.

### `migr_pop1ctz` -- Population by citizenship

Used for two fields:
1. **birth_location** -- Aggregated to 3 categories (Italy / Europe Other / Outside Europe) based on ISO 3166-1 alpha-2 codes and EU27 membership
2. **birth_country_detail** -- Top origin countries for non-Italian citizens, with minor countries aggregated to "Other"

---

## Sampling Chain

The sample service draws one individual through a 10-step conditional chain:

1. **Joint (age, sex)** from `age_sex` -- produces integer age (18-85) and sex label
2. **Education | (age_group, sex)** from `education_by_age` -- 3 ISCED levels
3. **Employment | (sex, education)** from `employment_by_sex_education` -- Employed / Unemployed / Not in labour force
4. **Marginals** -- birth_location, region, parental_structure (independent draws)
5. **Socioeconomic | (age_group, sex)** from `socioeconomic` -- 4 income classes
6. **Civil status | (age_group, sex)** from `civil_status_by_age_sex` -- 6 statuses
7. **Industry sector** (employed only) from `industry_sector` -- NACE sectors
8. **Employment type | (age_group, sex)** (employed only) from `employment_type_by_age` -- contract x hours
9. **Housing tenure** (marginal) + **Household size** (marginal)
10. **Birth country detail | (age_group, sex)** -- non-Italy-born only

---

## Known Limitations

- **Employment status granularity:** The employment rate is derived from the ratio of employed persons (ISTAT `150_938_17`) to total population (ISTAT `52_1194`). The two-category output (Employed / Not Employed) cannot distinguish Unemployed from Not-in-labour-force because no available ISTAT cross-tabulation provides the full ILO status breakdown by education level.
- **Socioeconomic distribution coarseness:** Each (age_group, sex) cell typically has few API income values (from different income sources/age aggregations). Classifying these directly into 4 classes produces coarse distributions. The classification uses only observed API values and published AROP/OECD thresholds — no parametric model.
- **Civil status endpoint instability:** ISTAT `22_289` is known to time out or reset connections. The pipeline will fail fast on timeout — clear the ISTAT cache and retry.
- **Employment type contract dimension:** When the PERM_TEMP_EMPLOYEES dimension in `150_938_18` has no per-status variation (only total codes), the contract type is labeled "Unspecified" rather than assumed.
- **Age range:** Filtered to 18-85 at parse time. Data outside this range is discarded.
- **Education granularity:** ISTAT education codes collapsed to 3 categories (No Formal Education, High School, University Degree) for cross-country schema compatibility.
- **Birth country detail:** Marginal distribution (aggregated across all ages and sexes) is applied identically to every (age_group, sex) cell. The Eurostat `migr_pop1ctz` query does not cross-tabulate citizenship by age and sex simultaneously.
