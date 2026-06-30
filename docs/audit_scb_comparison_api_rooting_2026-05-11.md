# Audit: SCB Comparison Pipeline — API Rooting of Categories and Proportions

**Date:** 2026-05-11
**Auditor:** Claude (Opus 4.7)
**Scope:** Verify that every field, category, and proportion on the SCB-reference side of the comparison pipeline (`scripts/analyze/compare_populations.py` + wrapper `scripts/analyze/compare_pipeline_to_scb.py`) traces back to a live SCB PxWeb API table — with no hand-curated injection or aggregation.
**Reference population:** `data/scb_api/scb_population_pop-10000_02.json` ("scb02")

---

## TL;DR

1. **scb02 itself is clean.** All 15 fields are sampled from distributions populated by live SCB PxWeb fetches in `anxiety_synthetic/scb_population/fetch_service.py`. No hardcoded weights, no static substitutions in the generator. The full per-field distributions (every observed value with count and %) are tabulated in [§ Raw scb02 distributions (input side)](#raw-scb02-distributions-input-side) below.
2. **The comparison pipeline contaminates the SCB side.** `scripts/analyze/compare_populations.py::normalize_scb_to_schema` (lines 95–262) transforms each scb02 record before comparison via `config/assets/scb_reference/category_mappings.json` — a hand-curated JSON.
3. **Two violation classes were found**:
   - **Category injection** — 2 fields (`current_environment_type`, `ethnicity`) have **zero SCB API source**.
   - **Aggregation** — 8 fields collapse API-native categories into hand-chosen buckets (education, socioeconomic, parental, industry, household_size, employment_type, birth_country_detail, income_source).
4. **`birth_location`** has a mismatch bug: the SCB query fetches 3 buckets but the comparison defines 4 (`Nordic Country` is permanently empty).

---

## Methodology

- Direct read of `anxiety_synthetic/scb_population/*.py` (generator side — fetch, sample, parsers, constants, data).
- Direct read of `scripts/analyze/compare_populations.py` (comparison-side normalization).
- Direct read of `scripts/analyze/compare_pipeline_to_scb.py` (wrapper that re-uses the same normalizer).
- Direct read of `config/assets/scb_reference/category_mappings.json` (hand-curated mappings).
- Inspection of `data/scb_api/scb_population_pop-10000_02.json` metadata header and sample records.
- Cross-checked against `parsers.py::parse_urbanization_by_county` (orphan code) and `constants.py::URBANIZATION_TABLE` (defined but unused).

---

## Raw scb02 distributions (input side)

This section enumerates **every field** present on the 10,000 scb02 records, with **every observed value** and its percentage. It documents what the comparison pipeline *receives* as input, before any normalization. A subsequent revision (Task 2) will map each comparison-side category back to the raw fields below and document its transformation.

Denominators: **10,000** for all fields except `industry_sector` and `employment_type`, which are conditional on employment and use **8,534** (the count of `employment_status == employed`).

### 1. `age` (integer, 18-85)

Min 18, max 85, mean 48.98. Binned into the 7 standard age groups for display only — raw is integer.

| Bin | Count | % |
|---|---|---|
| 18-24 | 1,025 | 10.25% |
| 25-34 | 1,697 | 16.97% |
| 35-44 | 1,720 | 17.20% |
| 45-54 | 1,609 | 16.09% |
| 55-64 | 1,528 | 15.28% |
| 65-74 | 1,264 | 12.64% |
| 75-85 | 1,157 | 11.57% |

### 2. `biological_sex` (2 values)

| Value | Count | % |
|---|---|---|
| men | 5,138 | 51.38% |
| women | 4,862 | 48.62% |

### 3. `education_level` (8 values — SCB English ISCED97 labels)

| Value | Count | % |
|---|---|---|
| post-secondary education 3 years or more (ISCED97 5A) | 2,416 | 24.16% |
| upper secondary education 3 years (ISCED97 3A) | 2,375 | 23.75% |
| upper secondary education, 2 years or less (ISCED97 3C) | 1,887 | 18.87% |
| post-secondary education, less than 3 years (ISCED97 4+5B) | 1,635 | 16.35% |
| primary and secondary education 9-10 years (ISCED97 2) | 1,048 | 10.48% |
| primary and secondary education less than 9 years (ISCED97 1) | 259 | 2.59% |
| no information about level of educational attainment | 254 | 2.54% |
| post-graduate education (ISCED97 6) | 126 | 1.26% |

### 4. `employment_status` (2 values)

| Value | Count | % |
|---|---|---|
| employed | 8,534 | 85.34% |
| unemployed | 1,466 | 14.66% |

### 5. `socioeconomic_class` (10 deciles)

| Value | Count | % |
|---|---|---|
| Decile 2 | 1,039 | 10.39% |
| Decile 5 | 1,013 | 10.13% |
| Decile 6 | 1,012 | 10.12% |
| Decile 10 | 1,005 | 10.05% |
| Decile 8 | 999 | 9.99% |
| Decile 9 | 998 | 9.98% |
| Decile 3 | 994 | 9.94% |
| Decile 4 | 991 | 9.91% |
| Decile 7 | 976 | 9.76% |
| Decile 1 | 973 | 9.73% |

### 6. `birth_location` (3 values — only 3, not 4)

| Value | Count | % |
|---|---|---|
| born in Sweden | 7,919 | 79.19% |
| born outside the EU | 1,522 | 15.22% |
| born in another EU Member State | 559 | 5.59% |

### 7. `region` (21 counties)

| Value | Count | % |
|---|---|---|
| Stockholm county | 2,285 | 22.85% |
| Västra Götaland county | 1,661 | 16.61% |
| Skåne county | 1,398 | 13.98% |
| Östergötland county | 430 | 4.30% |
| Uppsala county | 387 | 3.87% |
| Jönköping county | 357 | 3.57% |
| Halland county | 324 | 3.24% |
| Örebro county | 308 | 3.08% |
| Gävleborg county | 304 | 3.04% |
| Södermanland county | 283 | 2.83% |
| Dalarna county | 279 | 2.79% |
| Västerbotten county | 276 | 2.76% |
| Värmland county | 267 | 2.67% |
| Norrbotten county | 243 | 2.43% |
| Västmanland county | 241 | 2.41% |
| Västernorrland county | 233 | 2.33% |
| Kalmar county | 222 | 2.22% |
| Kronoberg county | 179 | 1.79% |
| Blekinge county | 134 | 1.34% |
| Jämtland county | 133 | 1.33% |
| Gotland county | 56 | 0.56% |

### 8. `civil_status` (4 values)

| Value | Count | % |
|---|---|---|
| single | 4,313 | 43.13% |
| married | 4,102 | 41.02% |
| divorced | 1,241 | 12.41% |
| widowers/widows | 344 | 3.44% |

### 9. `industry_sector` (12 SNI2007 sections — employed only, n=8,534)

| Value | Count | % of employed |
|---|---|---|
| financial operations, business services | 1,638 | 19.19% |
| human health and social work activities | 1,326 | 15.54% |
| education | 893 | 10.46% |
| manufacturing, mining and quarrying, energy and environment | 869 | 10.18% |
| trade | 811 | 9.50% |
| public administration etc. | 725 | 8.49% |
| construction | 525 | 6.15% |
| information and communication | 516 | 6.05% |
| personal and cultural services | 440 | 5.16% |
| transport | 394 | 4.62% |
| accommodation and food services | 253 | 2.96% |
| agriculture, forestry, fishing | 144 | 1.69% |

### 10. `employment_type` (9 cells: 3 attachment × 3 hours — employed only, n=8,534)

| Value | Count | % of employed |
|---|---|---|
| permanent employees - 35+ hours | 4,378 | 51.30% |
| permanent employees - 20-34 hours | 933 | 10.93% |
| self-employed + family workers - 35+ hours | 841 | 9.85% |
| temporary employees - 35+ hours | 594 | 6.96% |
| permanent employees - 1-19 hours | 508 | 5.95% |
| self-employed + family workers - 20-34 hours | 391 | 4.58% |
| self-employed + family workers - 1-19 hours | 356 | 4.17% |
| temporary employees - 20-34 hours | 274 | 3.21% |
| temporary employees - 1-19 hours | 259 | 3.03% |

### 11. `housing_tenure` (3 values)

| Value | Count | % |
|---|---|---|
| owner-occupied dwellings | 4,009 | 40.09% |
| rented dwellings | 3,451 | 34.51% |
| tenant-owned dwellings | 2,540 | 25.40% |

### 12. `household_size` (7 values)

| Value | Count | % |
|---|---|---|
| 1 person | 4,113 | 41.13% |
| 2 persons | 3,019 | 30.19% |
| 4 persons | 1,190 | 11.90% |
| 3 persons | 1,140 | 11.40% |
| 5 persons | 363 | 3.63% |
| 6 persons | 113 | 1.13% |
| 7 persons or more | 62 | 0.62% |

### 13. `income_source` (6 values)

| Value | Count | % |
|---|---|---|
| wage and business income | 6,660 | 66.60% |
| capital income | 1,648 | 16.48% |
| sickness compensation, parental allowance, labour market assistance etc. | 1,117 | 11.17% |
| pensions | 408 | 4.08% |
| social assistance | 127 | 1.27% |
| sickness and activity compensation | 40 | 0.40% |

### 14. `birth_country_detail` (20 foreign countries)

Note: `birth_country_detail` is sampled for every record (denominator = 10,000), but its interpretation is conditional on `birth_location` — a Sweden-born person carries one of the 20 foreign labels below as their sampled value, even though they are flagged as Swedish on the comparison side. The interaction between this field and `birth_location` belongs to Task 2.

| Value | Count | % |
|---|---|---|
| Syrian Arab Republic | 1,176 | 11.76% |
| Finland | 1,137 | 11.37% |
| Iraq | 1,013 | 10.13% |
| Poland | 726 | 7.26% |
| Iran (Islamic Republic of) | 670 | 6.70% |
| Somalia | 487 | 4.87% |
| Yugoslavia | 484 | 4.84% |
| Bosnia and Herzegovina | 459 | 4.59% |
| Afghanistan | 454 | 4.54% |
| Turkey | 443 | 4.43% |
| Germany | 397 | 3.97% |
| India | 341 | 3.41% |
| Eritrea | 333 | 3.33% |
| Thailand | 311 | 3.11% |
| Denmark | 292 | 2.92% |
| Norway | 290 | 2.90% |
| China | 264 | 2.64% |
| Romania | 260 | 2.60% |
| Ukraine | 236 | 2.36% |
| United Kingdom | 227 | 2.27% |

### 15. `parental_structure` (6 values)

| Value | Count | % |
|---|---|---|
| married or cohabiting natural parents | 7,411 | 74.11% |
| single mother | 1,430 | 14.30% |
| single father | 490 | 4.90% |
| married or cohabiting mother and stepparent | 443 | 4.43% |
| married or cohabiting father and stepparent | 145 | 1.45% |
| living with persons other than parents | 81 | 0.81% |

---

## Generator Side — Clean (verification)

`scripts/generate/generate_scb_population.py` → `FetchService.load_all()` → `SampleService.sample_one()` produces 15 fields per person. Every field's value is drawn from a `PopulationDistributions` dict populated entirely by live SCB PxWeb API responses:

| Field in scb02 | SCB Table |
|---|---|
| `age`, `biological_sex` | BE/BE0101/BE0101A/BefolkningNy |
| `education_level` | UF/UF0506/UF0506B/Utbildning |
| `employment_status` | AM/AM0401/AM0401P/NAKUBefUtbNivAr |
| `birth_location` | BE/BE0101/BE0101E/FolkmFodlandHVD |
| `region` | BE/BE0101/BE0101A/BefolkningNy (county filter) |
| `socioeconomic_class` (decile) | HE/HE0110/HE0110F/TabVX10InkStrukt |
| `parental_structure` | LE/LE0102/LE0102B/LE0102T17 |
| `civil_status` | BE/BE0101/BE0101A/BefolkningNy (civil_status filter) |
| `industry_sector` | AM/AM0401/AM0401I/AKURLSysSNI07Ar |
| `employment_type` (attachment + hours) | AM/AM0401/AM0401I/AKURLSysAnkAr + AM/AM0401/AM0401S/NAKUSysselOkArbtidAr |
| `housing_tenure` | BO/BO0104/BO0104D/BO0104T04 |
| `household_size` | BE/BE0101/BE0101S/HushallT03 |
| `income_source` | HE/HE0110/HE0110F/TabVX13InkStruktN |
| `birth_country_detail` | BE/BE0101/BE0101E/FodelselandArK |

**Constants in `constants.py`** (table IDs, COUNTY_CODES, BIRTH_COUNTRY_TOP_CODES, age ranges, ContentsCodes) are **API query parameters**, not data substitutes — they tell PxWeb which slice to return.

**Bridge maps in `sample_service.py`** (`_SUN2020_TO_AKU_EDU`, `_AKU_TO_INC_EMP`, `_AGE_GROUP_TO_INC_AGE`, etc.) are **label normalization** to reconcile inconsistent labels across SCB tables, not statistical data.

**One borderline pattern** (not currently flagged for fix): within-table fallbacks in `sample_service.py` (lines 113–127, 134–141, 158–163, 180–189, 215–227, 237–241) borrow distributions from an opposite-sex or adjacent-age slice when the primary `(age_group, sex)` cell is empty in the SCB response. Substituted data is still API-derived but not the exact requested joint slice. Whether to treat these as fallbacks-to-fix or acceptable substitutions remains an open question.

---

## Comparison Side — Violations

All transformations below happen in `scripts/analyze/compare_populations.py::normalize_scb_to_schema` (lines 95–262), driven by `config/assets/scb_reference/category_mappings.json`. The wrapper script `scripts/analyze/compare_pipeline_to_scb.py:40` imports the same function, so all violations propagate.

### Severity 1 — Pure injection (no SCB API source)

#### 1.1 `current_environment_type`

- **File:line:** `compare_populations.py:106, 185`; map at `category_mappings.json:258-280`
- **What SCB returns:** *nothing for this field — no query exists in `FetchService`*
- **Output categories (3):** `Urban Metropolis`, `Suburban`, `Rural/Countryside`
- **Source:** Hand-curated 21-row `region.county_env_type` map.

| Output bucket | Counties (hand-assigned) |
|---|---|
| Urban Metropolis | Stockholm, Skåne, Västra Götaland |
| Suburban | Uppsala, Södermanland, Östergötland, Jönköping, Kronoberg, Kalmar, Blekinge, Halland, Örebro, Västmanland, Dalarna, Gävleborg, Västernorrland, Västerbotten, Norrbotten |
| Rural/Countryside | Värmland, Jämtland, Gotland |

The JSON's own description (`category_mappings.json:227`) admits this should come from SCB table `MI/MI0810/MI0810A/BefLandInvKvmTO`. That table is **never fetched**. `parse_urbanization_by_county()` exists at `parsers.py:245` but is orphaned (not called by `FetchService.load_all`); `URBANIZATION_TABLE` is defined at `constants.py:23` but unused.

#### 1.2 `ethnicity`

- **File:line:** `compare_populations.py:104, 180`; map at `category_mappings.json:186-194`
- **What SCB returns:** *nothing — SCB does not publish ethnicity*
- **Output categories (4):** `Swedish`, `Nordic`, `European`, `Non-European`
- **Source:** Hand-curated derivation from birth_location (Sweden → Swedish; Nordic Country → Nordic; Europe (Other) → European; Outside Europe → Non-European). Conflates birth country with ethnicity.

---

### Severity 2 — Aggregation (hand-chosen bucket boundaries beyond the API)

#### 2.1 `education_level`

- **File:line:** `compare_populations.py:101, 172`; map at `category_mappings.json:23-40`
- **SCB raw (8 levels from `UF/UF0506` queried at `fetch_service.py:42`):** `förgymnasial < 9 år`, `förgymnasial 9-10 år`, `gymnasial ≤ 2 år`, `gymnasial 3 år`, `eftergymnasial < 3 år`, `eftergymnasial ≥ 3 år`, `forskarutbildning`, `uppgift saknas`
- **Output (4 buckets):**

| Output | Aggregated from |
|---|---|
| No Formal Education | förgymnasial<9år + förgymnasial 9-10år + **uppgift saknas** (editorial) |
| High School (Gymnasieskola) | gymnasial ≤ 2 år + gymnasial 3 år |
| Vocational (Yrkeshögskola) | eftergymnasial < 3 år |
| University Degree | eftergymnasial ≥ 3 år + forskarutbildning |

#### 2.2 `socioeconomic_class`

- **File:line:** `compare_populations.py:116-120, 195`; map at `category_mappings.json:116-140`
- **SCB raw (10 deciles from `HE0110F` queried at `fetch_service.py:116`):** `Decile 1` … `Decile 10`
- **Output (4 buckets):**

| Output | From |
|---|---|
| Poverty | D1+D2 |
| Working Class | D3+D4+D5 |
| Middle Class | D6+D7+D8 |
| Wealthy | D9+D10 |

#### 2.3 `parental_structure`

- **File:line:** `compare_populations.py:122-126, 202`; map at `category_mappings.json:195-224`
- **SCB raw (from `LE0102B`):** `married or cohabiting natural parents`, `married or cohabiting mother and stepparent`, `married or cohabiting father and stepparent`, `single mother`, `single father`, `lone parent with children`, `living with persons other than parents`
- **Output (4 buckets):**

| Output | From |
|---|---|
| Nuclear Family | natural parents + **stepparent variants** (signal loss) |
| Single Parent | single mother + single father + lone parent |
| Couple without Children | couple without children |
| Living Alone | living alone + living with persons other than parents |

#### 2.4 `industry_sector`

- **File:line:** `compare_populations.py:108, 210`; map at `category_mappings.json:303-316`
- **SCB raw (12 SNI2007 sections from `AM0401I` queried at `fetch_service.py:166-169`):** agriculture/forestry/fishing, manufacturing+mining+energy, construction, trade, transport, accommodation/food, information/communication, financial/business, public admin, education, human health/social, personal/cultural
- **Output (8 buckets, of which 4 are aggregated):**

| Output | From |
|---|---|
| Agriculture & Forestry | agriculture |
| Manufacturing & Industry | manufacturing + construction |
| Retail & Service | trade + transport + accommodation/food |
| IT & Technology | info/comm + financial/business |
| Public Administration | public admin |
| Education | education |
| Healthcare & Social | health/social |
| Other | personal/cultural |

#### 2.5 `household_size`

- **File:line:** `compare_populations.py:112, 239`; map at `category_mappings.json:431-438`
- **SCB raw (7 from `BE0101S` queried at `fetch_service.py:235`):** `1 person`, `2 persons`, `3 persons`, `4 persons`, `5 persons`, `6 persons`, `7 persons or more`
- **Output (4 buckets):**

| Output | From |
|---|---|
| 1 person | 1 person |
| 2 persons | 2 persons |
| 3-4 persons | 3 + 4 |
| 5+ persons | 5 + 6 + 7+ |

#### 2.6 `employment_type`

- **File:line:** `compare_populations.py:213-229`; maps at `category_mappings.json:318-340`
- **SCB raw joint space:** 3 attachment × 3 hours = 9 cells available
  - Attachment: `permanent employees`, `temporary employees`, `self-employed + family workers`
  - Hours: `1-19 hours`, `20-34 hours`, `35+ hours`
- **Output (6 buckets):**

| Output | From (attachment / hours) |
|---|---|
| Permanent Full-time | permanent / 35+ |
| Permanent Part-time | permanent / (1-19 or 20-34) — 2 cells merged |
| Temporary Full-time | temporary / 35+ |
| Temporary Part-time | temporary / (1-19 or 20-34) — 2 cells merged |
| Self-Employed | self-employed / any — 3 cells merged |
| Not Applicable | non-employed (no SCB source — fallback) |

#### 2.7 `birth_country_detail`

- **File:line:** `compare_populations.py:114, 250-255`; map at `category_mappings.json:512-534`
- **SCB raw (20 ISO codes queried at `fetch_service.py:269`):** SY, IQ, FI, PL, IR, AF, SO, YU, BA, TR, IN, DE, ER, TH, CN, RO, NO, DK, UA, GB (plus `Sweden` direct)
- **Output (8 buckets):**

| Output | From |
|---|---|
| Sweden | Sweden (direct) |
| Finland | FI |
| Iraq | IQ |
| Poland | PL |
| Syria | SY |
| Somalia | SO |
| Bosnia and Herzegovina | BA |
| Other | IR + AF + **YU** + TR + IN + DE + ER + TH + CN + RO + NO + DK + UA + GB (14 countries collapsed, including the `YU → Other` policy violation) |

**Policy note:** The project's birth-country aggregation memory explicitly forbids rolling Serbia/Kosovo/Croatia into "Yugoslavia". `YU → Other` here is consistent with that policy in letter but loses the country specificity entirely — open question whether YU should remain visible as its own (historical-code) bucket.

#### 2.8 `income_source` (re-classified from Severity 3)

- **File:line:** `compare_populations.py:113, 241`; map at `category_mappings.json:466-473`
- **SCB raw (6 income components from `HE0110F` queried at `fetch_service.py:252`):** wage and business income, capital income, pensions, sickness and activity compensation, sickness compensation/parental allowance/labour market assistance, social assistance
- **Output (4 buckets):**

| Output | From |
|---|---|
| Employment income | wage and business income |
| Capital income | capital income |
| Pension | pensions |
| Social transfers | sickness/activity comp + sickness/parental/labour market + social assistance (**3 merged**) |

---

### Severity 3 — Pure rewrites (acceptable; same concept, different string)

| Field | SCB raw | Comparison output | Rewrite type |
|---|---|---|---|
| `biological_sex` | men, women | Male, Female | Capitalization 1-to-1 |
| `civil_status` | single, married, widowers/widows, divorced (OG/G/ÄNKL/SK) | Single/Never Married, Married, Widowed, Divorced | 1-to-1 |
| `region` | `Stockholm county` … `Norrbotten county` (21) | `Stockholm` … `Norrbotten` (21) | Strip `" county"` suffix |
| `housing_tenure` | rented, tenant-owned, owner-occupied (3) | Rental apartment, Tenant-owned apartment (bostadsrätt), Owner-occupied (villa/house) (3) | 1-to-1 |
| `age_group` | integer years 18-85 | 7 bins (18-24, 25-34, 35-44, 45-54, 55-64, 65-74, 75-85) | Standard binning |

---

### Adjacent bug — `birth_location` 3 vs 4 mismatch

- **SCB query** (`fetch_service.py:80`) asks for 3 buckets: `FSV` (born in Sweden) / `FEU` (born in EU) / `FUEU` (born outside EU).
- **Comparison mapping** (`category_mappings.json:138-184`) defines 4 buckets: `Sweden` / `Nordic Country` / `Europe (Other)` / `Outside Europe`.
- **Consequence:** The `Nordic Country` bucket on the SCB side is permanently empty (no SCB query value maps to it). The comparison reports a category the SCB data cannot populate.
- **Fix options:** (a) widen the SCB query to fetch Nordic separately, or (b) collapse the comparison to 3 buckets matching the fetch.

---

## Critical files

| File | Role |
|---|---|
| `scripts/analyze/compare_populations.py` | `normalize_scb_to_schema()` (lines 95–262) — entire contamination surface |
| `config/assets/scb_reference/category_mappings.json` | All hand-curated transforms |
| `scripts/analyze/compare_pipeline_to_scb.py:40` | Wrapper that imports the normalizer; auto-inherits any fix |
| `anxiety_synthetic/scb_population/parsers.py:245` | Orphan `parse_urbanization_by_county()` |
| `anxiety_synthetic/scb_population/fetch_service.py:282` | `load_all()` — would need a `fetch_urbanization_by_county()` call to back a real env_type |
| `anxiety_synthetic/scb_population/constants.py:23` | `URBANIZATION_TABLE` defined but unused |

---

## Verification procedure for any future remediation

1. Regenerate scb02 if generator changed: `python scripts/generate/generate_scb_population.py --n 10000 --seed 3002120581 --output data/scb_api/scb_population_pop-10000_02.json`.
2. Run one seed through comparison: `python scripts/analyze/compare_pipeline_to_scb.py --seed-root <seed_007 path>` and open the JSON report.
3. For each compared field, the SCB-side category list in the report must equal the raw label set returned by the corresponding SCB query (modulo pure 1-to-1 rewrites). No category may appear that wasn't fetched; no API category may be silently merged with another.
4. Re-run the comparison loop across seeds 007–013 and confirm no regressions in the statistical tests.

---

## Outstanding decisions (pending user input)

- **Severity 1 fields**: drop both, or wire MI/MI0810 to back environment_type?
- **Severity 2 fields**: emit raw API categories for all 8, or keep specific aggregations (e.g., socioeconomic OECD bands, household_size 5+ collapse) as defensible derived views?
- **`employment_type`**: split into attachment + hours, expand to 3×3=9 raw cells, or drop?
- **`birth_location`**: widen SCB query for Nordic, or collapse comparison to 3?
- **`YU` policy reconciliation**: keep as separate historical bucket vs roll into `Other`.
- **Sample-service within-table fallbacks**: out of scope for this audit but flagged as borderline against the project's no-fallback rule.
