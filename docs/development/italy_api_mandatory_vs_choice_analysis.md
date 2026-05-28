# Italy Pipeline: API-Mandatory vs. Implementation Choice Analysis

**Date:** 2026-05-26
**Status:** Discussion in progress
**Context:** Audit of what the ISTAT/Eurostat APIs mandate vs. what our code chooses to do with the data

---

## Field 1: `age_sex` — Eurostat `demo_pjan`

**API dimensions & available filters:**
| Dimension | Available values |
|-----------|-----------------|
| `age` | `Y0`–`Y99`, `Y_OPEN`, `TOTAL` |
| `sex` | `T` (total), `M`, `F` |
| `geo` | `IT` (+ all EU countries) |
| `time` | 2023–2025 |

**Mandatory from API:** The API returns population counts per (age, sex, geo, time). The values are absolute counts — integers. The joint distribution shape is entirely API-driven.

**Implementation choices:**
| Choice | What we do | Alternatives the API supports |
|--------|-----------|-------------------------------|
| Age range filter | Keep `Y18`–`Y85` only | Could use `Y0`–`Y99`, `Y_OPEN` |
| Sex filter | Keep `M`/`F`, exclude `T` | Could include `T` |
| Geo filter | `IT` only | Any EU country code |
| Time filter | `sinceTimePeriod=2023`, pick latest year | Could pick any year back to ~1960 |
| Label mapping | `M`→"Male", `F`→"Female" | Direct codes |

**Verdict:** CLEAN. All probabilities come from API counts. Filtering to 18–85 and M/F are schema-level choices, not invented data.

---

## Field 2: `education_by_age` — ISTAT `52_1194_DF_DCCV_POPTIT1_UNT2020_1`

**API dimensions & available filters:**
| Dimension | Available values |
|-----------|-----------------|
| `AGE` | `Y15-19`, `Y20-24`, `Y25-29`, `Y30-34`, `Y35-39`, `Y40-44`, `Y45-49`, `Y50-54`, `Y55-59`, `Y60-64`, `Y_GE65`, plus aggregates (`Y15-24`, `Y25-34`, `Y15-89`, `Y20-64`, `Y_GE15`, `Y15-64`) |
| `SEX` | `1` (M), `2` (F), `9` (total) |
| `EDU_LEV_HIGHEST` | `3`, `4`, `5`, `6`, `7`, `11`, `99` (ISCED levels + total) |
| `REF_AREA` | `IT` + 5 macro-regions (`ITC`, `ITD`/`ITH`, `ITE`, `ITF`, `ITG`) |
| `FREQ` | `A` (annual), `Q` (quarterly) |
| `TIME_PERIOD` | 2020–2023 |

**Mandatory from API:** Returns population counts by (age_group, sex, education_level). The distribution per cell is entirely API-driven.

**Implementation choices:**
| Choice | What we do | Alternatives the API supports |
|--------|-----------|-------------------------------|
| Education aggregation | Collapse ISCED 0–8 to 3 labels: "No Formal Education" (codes 3,4), "High School" (codes 5,6), "University Degree" (codes 7,11) | Could keep all 7 distinct ISCED levels |
| Age groups used | 5-year bands (`Y15-19` through `Y_GE65`), skip aggregates | Could use 10-year bands or the aggregate codes |
| Sex filter | `1`→Male, `2`→Female, skip `9` (total) | Could use total |
| Ref area | National (`IT`) | Could use macro-regional breakdown |
| Code 99 handling | Skipped (total across education levels) | Could include as check |

**Verdict:** AGGREGATION (Sev 1). The 7→3 education collapse is a design choice for cross-country schema compatibility. All probabilities come from API counts.

---

## Field 3: `employment_by_sex_education` — ISTAT `150_938_DF_DCCV_OCCUPATIT1_17` + `52_1194_DF_*_1`

**API dimensions for 150_938_17 (employed counts):**
| Dimension | Available values |
|-----------|-----------------|
| `AGE` | `Y15-89` only (single national aggregate) |
| `SEX` | `1` (M), `2` (F), `9` (total) |
| `EDU_LEV_HIGHEST` | `11`, `13`, `7`, `99` |
| `REF_AREA` | `IT` + 27 regional codes |
| `FREQ` | `A`, `Q` |
| `TIME_PERIOD` | 2022–2024 |

**API dimensions for 52_1194 (total population):** (same as Field 2 above)

**Mandatory from API:** 150_938_17 returns employed person counts by (sex, education). 52_1194 returns total population by (sex, education, age_group). Neither dataset provides an employment *rate* directly — only counts.

**Implementation choices:**
| Choice | What we do | Alternatives the API supports |
|--------|-----------|-------------------------------|
| **Cross-dataset ratio** | Derive employment rate = employed(150_938) / total(52_1194) | Could use employed counts alone as marginal, or find a different dataset |
| Output categories | "Employed" / "Not Employed" (2 categories) | ILO standard has 3: Employed / Unemployed / Not in labour force — but no ISTAT cross-tab provides this by education |
| Age handling | 150_938_17 has `Y15-89` only — we use this national total | No per-age-group breakdown available in this dataset |
| Education mapping | Match ISCED codes between the two datasets | Could skip education conditioning entirely |
| REF_AREA | National (`IT`) | Could use regional codes (27 available in 150_938) |

**Verdict:** The cross-dataset ratio is an implementation choice. Both numerator and denominator come from real API data. The 2-category limitation is API-mandated — no available cross-tabulation provides ILO 3-status by education.

---

## Field 4: `socioeconomic` — ISTAT `32_292_DF_DCCV_REDNETFAMFONTERED_6`

**API dimensions & available filters:**
| Dimension | Available values |
|-----------|-----------------|
| `AGE_MAIN_EARNIER` | `TOTAL`, `Y_UN35`, `Y35-44`, `Y45-54`, `Y55-64`, `Y_GE65` |
| `SEX_MAIN_PERCEPTOR` | `9` only (total — **no per-sex breakdown exists**) |
| `FAM_MAIN_INCOME_SOURCE` | `1` (employment), `2` (self-employment), `3` (pensions), `4` (transfers), `9` (total) |
| `DATA_TYPE` | `REDD_MEDIANO_FAM` (median family income), `REDD_MEDIO_FAM` (mean family income) |
| `IMPUTED_RENTS` | `1` (with imputed rents), `2` (without) |
| `REF_AREA` | `IT` + 5 macro-regions |
| `TIME_PERIOD` | 2020–2023 |

**Mandatory from API:** Returns income values (EUR) by (age_group_of_main_earner, income_source). These are **income amounts**, not categories. The API does NOT provide socioeconomic class labels.

**Implementation choices:**
| Choice | What we do | Alternatives the API supports |
|--------|-----------|-------------------------------|
| **Income → class classification** | Classify each observed income value against AROP/OECD thresholds (0.60×, 1.00×, 2.00× global median) | Could use different threshold methodology, or use income amounts directly |
| **Global median calculation** | Compute median from all observed income values in the dataset | Could use Eurostat's published AROP threshold (€10,827 for Italy 2022) as external reference |
| Sex handling | API only has `9` (total) — we apply to both Male and Female | No alternative — API doesn't provide per-sex data |
| Income source filter | Use all income source codes, skip `99` (total) | Could filter to specific sources |
| Data type | Use median income (`REDD_MEDIANO_FAM`) | Could use mean (`REDD_MEDIO_FAM`) |
| Imputed rents | Code 2 (without imputed rents) preferred | Could use code 1 (with) |

**Verdict:** The AROP/OECD thresholds are published methodology — not invented probabilities. The classification is an implementation choice, but the **input values are entirely API data**. The sex limitation is API-mandated.

---

## Field 5: `birth_location` — Eurostat `migr_pop1ctz`

**API dimensions & available filters:**
| Dimension | Available values |
|-----------|-----------------|
| `citizen` | 287 country codes (ISO 3166-1 alpha-2) |
| `age` | 27 age groups (`Y_LT1`, `Y1`–`Y4` individually, `Y5-9`, `Y10-14`, ..., `Y85-89`, `Y_GE90`, `TOTAL`) |
| `sex` | `T`, `M`, `F` |
| `geo` | `IT` (+ all EU) |
| `time` | 2022–2025 |

**Mandatory from API:** Returns population counts by citizenship country. The API provides per-country counts.

**Implementation choices:**
| Choice | What we do | Alternatives the API supports |
|--------|-----------|-------------------------------|
| **Category aggregation** | Collapse 287 countries → 3 labels: "Italy", "Europe (Other)", "Outside Europe" | Could keep all 287, or group differently |
| EU membership reference | Use EU27 membership list to determine "Europe" | Could use geographic Europe instead |
| Age/sex handling | Marginal (aggregate across age and sex) | Could condition on age group and sex |

**Verdict:** AGGREGATION (Sev 1). The 287→3 collapse is a design choice. All underlying counts are API data.

---

## Field 6: `region` — Eurostat `demo_r_pjangrp3`

**API dimensions & available filters:**
| Dimension | Available values |
|-----------|-----------------|
| `geo` | All NUTS2 codes (20 Italian: `ITC1`–`ITG2`, plus other EU) |
| `age` | `TOTAL` + age groups |
| `sex` | `T`, `M`, `F` |
| `time` | 2022–2025 |

**Mandatory from API:** Returns population counts per NUTS2 region. Distribution shape is entirely API-driven.

**Implementation choices:**
| Choice | What we do | Alternatives the API supports |
|--------|-----------|-------------------------------|
| Geo filter | 20 Italian NUTS2 codes | Could include NUTS3 (provinces) via different dataset |
| Age/sex filter | `age=TOTAL`, `sex=T` | Could condition on age and sex |
| Label mapping | NUTS2 code → region name (e.g. `ITC1`→"Piemonte") | Direct codes |
| Fallback dataset | `demo_r_d2jan` if primary fails | Could fail fast instead |

**Verdict:** CLEAN. The fallback dataset is a structural resilience choice (same API, different table), not a synthetic distribution.

---

## Field 7: `parental_structure` — Eurostat `ilc_lvph02`

**API dimensions & available filters:**
| Dimension | Available values |
|-----------|-----------------|
| `hhcomp` | 17 codes: `TOTAL`, `A1`, `A1_LT65`, `A1_GE65`, `A1_DCH`, `F1`, `M1`, `A2`, `A2_DCH1`, `A2_DCH2`, `A2_DCH_GE3`, `A_GE3`, `A_GE3_DCH`, `A_GE3_NDCH`, `DCH`, `NDCH`, `A1_DCH_LT18`, `A2_NDCH` |
| `geo` | `IT` (+ all EU) |
| `time` | 2020–2025 |

**Mandatory from API:** Returns population counts/percentages per household composition type.

**Implementation choices:**
| Choice | What we do | Alternatives the API supports |
|--------|-----------|-------------------------------|
| **Category aggregation** | 17 codes → 5 labels: "Living Alone", "Single Parent", "Couple without Children", "Nuclear Family", "Extended Family" | Could keep finer granularity (e.g. distinguish 1-child from 3-child families) |
| Skip codes | `TOTAL`, `DCH`, `NDCH`, age/sex sub-codes (`A1_LT65`, `F1`, `M1`) | Could include age/sex breakdowns |

**Verdict:** AGGREGATION (Sev 1). The 17→5 collapse is documented. All probabilities from API counts.

---

## Field 8: `civil_status_by_age_sex` — ISTAT `22_289_DF_DCIS_POPRES1_25`

**API dimensions & available filters:**
| Dimension | Available values |
|-----------|-----------------|
| `MARITAL_STATUS` | Expected: single, married, divorced, widowed, separated, civil union codes |
| `AGE` | Expected: age groups |
| `SEX` | Expected: `1`, `2`, `9` |
| `REF_AREA` | Expected: `IT` + regions |

**NOTE:** No cached data exists — the ISTAT endpoint has never been successfully fetched. Dimensions above are inferred from the dataflow schema, not observed data.

**Mandatory from API:** Would return population counts by (marital_status, age, sex). Conditional distribution would be entirely API-driven.

**Implementation choices:**
| Choice | What we do | Alternatives |
|--------|-----------|-------------------------------|
| Retry logic | 3 attempts, 30s between | Could fail immediately, or try harder |
| **Data source** | ISTAT only | Eurostat `cens_01rms` (census marital status) may have similar data |

**Verdict:** Currently BLOCKED — ISTAT API down. This field needs discussion about alternative data sources.

---

## Field 9: `industry_sector` — ISTAT `150_938_DF_DCCV_OCCUPATIT1_14`

**API dimensions & available filters:**
| Dimension | Available values |
|-----------|-----------------|
| `AGE` | `Y15-89` (single aggregate) |
| `SEX` | `1`, `2`, `9` |
| `OCCUPATION_2011` | `10`, `101`, `102`, `103`, `20`, `201`, `202`, `30`, `301`, `302`, `40`, `50`, `99` |
| `REF_AREA` | `IT` + 5 macro-regions |
| `FREQ` | `A`, `Q` |
| `TIME_PERIOD` | 2022–2024 |

**Mandatory from API:** Returns employed person counts by occupation code. These are ATECO 2007 / NACE occupation groupings.

**Implementation choices:**
| Choice | What we do | Alternatives the API supports |
|--------|-----------|-------------------------------|
| Label mapping | Occupation codes → sector labels | Could keep numeric codes |
| Hierarchy handling | Use leaf codes only, skip parent aggregates (`10`, `20`, `30`) | Could use parent-level only |
| Conditioning | Marginal (all employed) | API has sex dimension — could condition on sex |
| Scope | Employed persons only | Mandated by data — these are occupation codes |

**Verdict:** CLEAN. Distribution comes entirely from API counts. Label mapping is structural.

---

## Field 10: `employment_type_by_age` — ISTAT `150_938_DF_DCCV_OCCUPATIT1_18`

**API dimensions & available filters:**
| Dimension | Available values |
|-----------|-----------------|
| `AGE` | `Y15-89` (single aggregate) |
| `SEX` | `1`, `2`, `9` |
| `FULL_PART_TIME` | `1` (full-time), `2` (part-time), `9` (total) |
| `POSIZ_PROF` | `1` (employee), `2` (self-employed), `9` (total) |
| `PERM_TEMP_EMPLOYEES` | `9` only (**no per-status breakdown exists**) |
| `REF_AREA` | `IT` + 27 regional codes |
| `FREQ` | `A`, `Q` |

**Mandatory from API:** Returns employed person counts by (full/part-time × professional status). The `PERM_TEMP_EMPLOYEES` dimension has NO variation — only total.

**Implementation choices:**
| Choice | What we do | Alternatives the API supports |
|--------|-----------|-------------------------------|
| Composite key | `"{contract}\|{hours}"` format | Could keep as two separate fields |
| Contract type | "Unspecified" (since `PERM_TEMP_EMPLOYEES=9` only) | No alternative — API doesn't provide per-contract data |
| Age handling | `Y15-89` only — applied to all age groups uniformly | No per-age breakdown available |
| Sex conditioning | Parsed per sex | Could use total only |

**Verdict:** CLEAN. The "Unspecified" contract type reflects actual API limitation, not invented data.

---

## Field 11: `housing_tenure` — Eurostat `ilc_lvho02`

**API dimensions & available filters:**
| Dimension | Available values |
|-----------|-----------------|
| `tenure` | `OWN`, `OWN_L` (with loan), `OWN_NL` (without loan), `RENT`, `RENT_MKT` (market rent), `RENT_FR` (reduced/free), `TOTAL` |
| `incgrp` | `TOTAL`, plus income quintile codes |
| `hhcomp` | 17 household composition codes |
| `geo` | `IT` (+ all EU) |
| `time` | 2020–2025 |

**Mandatory from API:** Returns percentages by tenure status.

**Implementation choices:**
| Choice | What we do | Alternatives the API supports |
|--------|-----------|-------------------------------|
| **Category aggregation** | 7 codes → 2: "Owner-occupied" (`OWN*`), "Rental" (`RENT*`) | Could keep 6 distinct categories |
| Filter | `incgrp=TOTAL`, `hhcomp=TOTAL` | Could condition on income group or household composition |

**Verdict:** AGGREGATION (Sev 1). The 6→2 collapse is a design choice.

---

## Field 12: `household_size` — Eurostat `ilc_lvph03`

**API dimensions & available filters:**
| Dimension | Available values |
|-----------|-----------------|
| `n_person` | `1`, `2`, `3`, `4`, `5`, `GE6` |
| `geo` | `IT` (+ all EU) |
| `time` | 2020–2025 |

**Mandatory from API:** Returns percentage of households by size. Labels used directly from API.

**Implementation choices:**
| Choice | What we do | Alternatives the API supports |
|--------|-----------|-------------------------------|
| Labels | Use API labels directly | No transformation |
| Unit | Percentages (PC) | Only option available |

**Verdict:** CLEAN. No aggregation, no filtering, no label transformation.

---

## Field 13: `birth_country_detail` — Eurostat `migr_pop1ctz` (same dataset as Field 5)

**API dimensions:** Same as Field 5 (287 citizen codes × age × sex).

**Mandatory from API:** Per-country population counts for non-Italian citizens.

**Implementation choices:**
| Choice | What we do | Alternatives the API supports |
|--------|-----------|-------------------------------|
| Top-N selection | Keep top origin countries, aggregate rest to "Other" | Could keep all 287 |
| Conditioning | Marginal (same distribution for all age_group × sex) | API has age and sex dimensions — could produce conditional distributions |
| Scope | Non-Italy-born only | Design choice in sampling chain |

**Verdict:** AGGREGATION (Sev 1). Minor countries aggregated to "Other". The marginal-only approach is a limitation we could address since the API supports age×sex cross-tabs.

---

## Field 14: `income_source_by_employment_age` — empty `{}`

**Potential API source:** ISTAT `32_292_6` has `FAM_MAIN_INCOME_SOURCE` with codes `1` (employment), `2` (self-employment), `3` (pensions), `4` (transfers), `9` (total).

**Why dropped:** The API returns income amounts by income source, but does NOT cross-tabulate income source composition by employment status. The `LABPROF_STATUS_C_MAIN_EARNER` dimension is always published as code `99` (total). Without employment×income_source cross-tabulation, we cannot condition income source on employment status as the schema requires.

**Verdict:** DROPPED (Sev 0). Correct response to missing cross-tabulation.

---

## Field 15: `ethnicity_map` — empty `{}`

No API source exists. **Verdict:** DROPPED (Sev 0).

---

## Summary: What's Mandatory vs. What's a Choice

| Category | Examples | Rule |
|----------|---------|------|
| **API-mandated structure** | Only `SEX=9` in income data; only `Y15-89` in employment; `PERM_TEMP=9` only | We must work with what the API provides — no inventing missing breakdowns |
| **API-mandated limitation** | No ILO 3-status by education; no income source × employment cross-tab | Drop the field or simplify output categories |
| **Filtering choices** | Age 18–85, sex M/F only, geo=IT, latest year | We choose which subset to use. Could be wider or narrower |
| **Aggregation choices** | ISCED 7→3 education, 287→3 birth location, 6→2 tenure, 17→5 parental | We choose how to bucket. Could keep finer granularity |
| **Cross-dataset derivation** | Employment rate = 150_938 / 52_1194 | We choose to combine two datasets. Both are real API data, but the ratio is our construction |
| **Classification methodology** | AROP/OECD thresholds for socioeconomic class | Published methodology applied to real API values. The thresholds are external reference, not invented |
| **Label mapping** | NUTS2→region names, sex codes→labels, ISCED codes→names | Structural transformation, no probability impact |

---

## Open Questions

1. **Civil status (Field 8):** ISTAT API is down. Should we try Eurostat `cens_01rms` as alternative, or wait for ISTAT to recover?
2. **Aggregation granularity:** Several fields collapse API categories (education 7→3, tenure 6→2, parental 17→5). Are these acceptable trade-offs for cross-country schema compatibility, or should we keep finer granularity?
3. **Cross-dataset ratio (Field 3):** The employment rate derived from two datasets is mathematically sound but is our construction. Is this acceptable?
4. **Socioeconomic classification (Field 4):** AROP/OECD thresholds applied to API income values. The thresholds are published methodology but the classification step is ours. Is this acceptable?
