# scb02 → Comparison-Side Categories: Per-Field Mapping

**Date:** 2026-05-11
**Reference population:** `data/scb_api/scb_population_pop-10000_02.json` ("scb02"), n = 10,000
**Companion audit:** [`docs/audit_scb_comparison_api_rooting_2026-05-11.md`](audit_scb_comparison_api_rooting_2026-05-11.md)
**Comparison code:** `scripts/compare_populations.py::normalize_scb_to_schema` (lines 95–262)
**Mapping config:** `config/assets/scb_reference/category_mappings.json`

This document consolidates the audit's three category tables into a single per-field view: for each field scb02 carries, the raw SCB categories (with counts and percentages) and the exact transformation applied by `normalize_scb_to_schema` before comparison with the pipeline.

**Denominators:** 10,000 for every field except `industry_sector` and `employment_type`, which are conditional on `employment_status == employed` (n = 8,534).

---

## Legend

| Type | Meaning |
|---|---|
| **No transformation** | The comparison output equals the raw value byte-for-byte. |
| **1-to-1 rewrite** | The raw string is rewritten to a different string but the category space is preserved (size and partition unchanged). |
| **Binning** | A continuous variable (here: integer age) is partitioned into a finite set of buckets. |
| **Aggregation** | Multiple raw categories are merged into a single comparison bucket — signal loss. |
| **Injection** | The comparison field has no SCB API source on scb02. Values are derived from a hand-curated map applied to another field. |
| **Bug** | The comparison defines a category the SCB query cannot produce. |

---

## 1. `age` — Binning (integer → 7 bins)

- **Transformation type:** Binning (integer → labelled bin); also passes through as `age` unchanged.
- **SCB source:** `BE/BE0101/BE0101A/BefolkningNy`
- **Comparison code:** `compare_populations.py:151-157`; bins defined in `category_mappings.json` `age_groups.groups`.

**Raw scb02 distribution** (integer 18–85, mean 48.98) — shown grouped into the same 7 display bins:

| Bin | Count | % |
|---|---|---|
| 18-24 | 1,025 | 10.25% |
| 25-34 | 1,697 | 16.97% |
| 35-44 | 1,720 | 17.20% |
| 45-54 | 1,609 | 16.09% |
| 55-64 | 1,528 | 15.28% |
| 65-74 | 1,264 | 12.64% |
| 75-85 | 1,157 | 11.57% |

**Mapping (raw → output):**

| Raw integer range | Output `age_group` |
|---|---|
| 18–24 | `18-24` |
| 25–34 | `25-34` |
| 35–44 | `35-44` |
| 45–54 | `45-54` |
| 55–64 | `55-64` |
| 65–74 | `65-74` |
| 75–85 | `75-85` |

Notes: The raw integer `age` is also emitted as a separate field on the comparison record (no transformation on that copy).

---

## 2. `biological_sex` — 1-to-1 rewrite (2 → 2)

- **Transformation type:** 1-to-1 rewrite (capitalization).
- **SCB source:** `BE/BE0101/BE0101A/BefolkningNy`
- **Comparison code:** `compare_populations.py:159-169`; literals in code (not JSON).

**Raw scb02 distribution:**

| Value | Count | % |
|---|---|---|
| men | 5,138 | 51.38% |
| women | 4,862 | 48.62% |

**Mapping (raw → output):**

| Raw | Output |
|---|---|
| men | Male |
| women | Female |

---

## 3. `education_level` — Aggregation (8 → 4)

- **Transformation type:** Aggregation.
- **SCB source:** `UF/UF0506/UF0506B/Utbildning`
- **Comparison code:** `compare_populations.py:171-172`; map at `category_mappings.json` `education.sun2020_level_mappings`.

**Raw scb02 distribution** (8 levels, ISCED97 English labels):

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

**Mapping (raw → output):**

| Output bucket | Raw values merged |
|---|---|
| No Formal Education | primary and secondary education less than 9 years (ISCED97 1) + primary and secondary education 9-10 years (ISCED97 2) + no information about level of educational attainment |
| High School (Gymnasieskola) | upper secondary education, 2 years or less (ISCED97 3C) + upper secondary education 3 years (ISCED97 3A) |
| Vocational (Yrkeshogskola) | post-secondary education, less than 3 years (ISCED97 4+5B) |
| University Degree | post-secondary education 3 years or more (ISCED97 5A) + post-graduate education (ISCED97 6) |

Notes: `uppgift saknas` / `no information about level of educational attainment` is folded into `No Formal Education` (editorial — these are missing-data records, not zero-education records).

---

## 4. `employment_status` — 1-to-1 rewrite (2 → 2)

- **Transformation type:** 1-to-1 rewrite (capitalization).
- **SCB source:** `AM/AM0401/AM0401P/NAKUBefUtbNivAr`
- **Comparison code:** `compare_populations.py:174-175`; map at `category_mappings.json` `employment.aku_label_mappings`.

**Raw scb02 distribution:**

| Value | Count | % |
|---|---|---|
| employed | 8,534 | 85.34% |
| unemployed | 1,466 | 14.66% |

**Mapping (raw → output):**

| Raw | Output |
|---|---|
| employed | Employed |
| unemployed | Unemployed |

Notes: The mapping config also defines `Student` and `Retired` output labels for AKU label variants, but scb02 only carries `employed` / `unemployed`.

---

## 5. `socioeconomic_class` — Aggregation (10 deciles → 4 — stale on scb02)

- **Transformation type:** Aggregation (intended, historical).
- **SCB source on scb02:** `HE/HE0110/HE0110F/TabVX10InkStrukt` (deciles; the model in force at the time scb02 was generated).
- **Comparison code:** `compare_populations.py:187-198`; mapping config at `category_mappings.json` `socioeconomic.mappings`.

**Raw scb02 distribution** (10 deciles — the decile-based model):

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

**Mapping (raw → output) — as the audit documents the intended aggregation:**

| Output bucket | Raw values merged |
|---|---|
| Poverty | Decile 1 + Decile 2 |
| Working Class | Decile 3 + Decile 4 + Decile 5 |
| Middle Class | Decile 6 + Decile 7 + Decile 8 |
| Wealthy | Decile 9 + Decile 10 |

Notes (important): The recent commit `ed04d79` replaced the decile model with real income-bracket buckets (Poverty / Working Class / Middle Class / Wealthy, derived from `HE/HE0110/HE0110A/SamForvInk1` via Eurostat AROP and OECD/Pew thresholds, conditional on age × sex). The current `category_mappings.json` `socioeconomic.mappings` block no longer carries `scb_codes` arrays for the decile-to-bucket map, so `socio_code_to_schema` is built empty at runtime. On scb02 records (which still carry `Decile N`), the comparison passes the raw decile through unchanged — none of the 4 schema buckets are produced. To actually compare scb02 by socioeconomic_class, scb02 must be regenerated under the new model, or a fresh decile-to-bucket fallback re-added.

### How the new bracket → class derivation works (Sweden-only)

SCB table `HE/HE0110/HE0110A/SamForvInk1` returns Sweden-only counts of people in **26 fixed SEK brackets** (`0`, `1-19`, `20-39`, … `800-999`, `1000+`, all in thousands of SEK; defined in `anxiety_synthetic/scb_population/constants.py:43-70`), cross-tabulated by age band × sex. For each `(age_group, sex)` cell, `median_from_brackets()` (`anxiety_synthetic/utils/income_class.py:13-27`) finds the bracket whose midpoint sits at the cumulative-count 50th percentile — a Swedish-population median, recomputed per cell from each SCB response. No other country's data ever enters the calculation. `classify_brackets()` (`income_class.py:30-91`) then assigns each bracket to a class by where its midpoint falls relative to that median; brackets that straddle a threshold are split proportionally by width.

| Constant | Value | Class assigned | Origin of the multiplier name |
|---|---|---|---|
| `_POVERTY_UPPER` | 0.60 × median | Poverty (income < 60 % of median) | Eurostat AROP (At-Risk-Of-Poverty) cutoff |
| `_WORKING_UPPER` | 1.00 × median | Working Class (60–100 % of median) | OECD lower-middle floor |
| `_MIDDLE_UPPER` | 2.00 × median | Middle Class (100–200 %) and Wealthy (≥ 200 %) | OECD / Pew middle-class band |

The "Eurostat / OECD / Pew" attributions are only the **conceptual origin of the three fractions** (0.60 / 1.00 / 2.00) — they are hard-coded Python constants, not values fetched from any EU or OECD API. The multiplication base is purely the Swedish median.

Caveat from `income_class.py:4-7`: SCB reports individual gross income, while the official Eurostat AROP rate uses equivalised disposable household income — so calling the bottom bucket "Poverty (AROP)" here is a relative-position classifier, not the official Eurostat poverty measurement.

---

## 6. `birth_location` — 1-to-1 rewrite (3 fetched → 3 emitted), with **bug** (schema declares 4)

- **Transformation type:** 1-to-1 rewrite + **bug** (one declared bucket can never be populated).
- **SCB source:** `BE/BE0101/BE0101E/FolkmFodlandHVD`
- **Comparison code:** `compare_populations.py:177-180`; map at `category_mappings.json` `birth_location.region_label_mappings`.

**Raw scb02 distribution** (the SCB query returns only 3 buckets):

| Value | Count | % |
|---|---|---|
| born in Sweden | 7,919 | 79.19% |
| born outside the EU | 1,522 | 15.22% |
| born in another EU Member State | 559 | 5.59% |

**Mapping (raw → output):**

| Raw | Output |
|---|---|
| born in Sweden | Sweden |
| born in another EU Member State | Europe (Other) |
| born outside the EU | Outside Europe |
| *(no raw value)* | `Nordic Country` — declared in schema, permanently empty on scb02 |

Notes: The 4-bucket comparison schema declares `Nordic Country` (Norway/Denmark/Finland/Iceland), but the SCB query at `fetch_service.py:80` only requests FSV/FEU/FUEU. Until the query is widened or the schema is collapsed to 3, comparisons will report 0 / non-zero divergence on Nordic Country every time the pipeline emits any such record.

---

## 7. `region` — 1-to-1 rewrite (21 → 21)

- **Transformation type:** 1-to-1 rewrite (strip `" county"` suffix).
- **SCB source:** `BE/BE0101/BE0101A/BefolkningNy` (county filter)
- **Comparison code:** `compare_populations.py:182-185`; map at `category_mappings.json` `region.scb_label_mappings`.

**Raw scb02 distribution:**

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

**Mapping (raw → output):** each `"<Name> county"` → `"<Name>"` (e.g. `Stockholm county` → `Stockholm`). 21 such rows; the partition is preserved.

---

## 8. `civil_status` — 1-to-1 rewrite (4 → 4)

- **Transformation type:** 1-to-1 rewrite.
- **SCB source:** `BE/BE0101/BE0101A/BefolkningNy` (`Civilstand` variable)
- **Comparison code:** `compare_populations.py:206-207`; map at `category_mappings.json` `civil_status.scb_label_mappings`.

**Raw scb02 distribution:**

| Value | Count | % |
|---|---|---|
| single | 4,313 | 43.13% |
| married | 4,102 | 41.02% |
| divorced | 1,241 | 12.41% |
| widowers/widows | 344 | 3.44% |

**Mapping (raw → output):**

| Raw | Output |
|---|---|
| single | Single/Never Married |
| married | Married |
| divorced | Divorced |
| widowers/widows | Widowed |

---

## 9. `industry_sector` — Aggregation (12 → 8, employed only, n = 8,534)

- **Transformation type:** Aggregation.
- **SCB source:** `AM/AM0401/AM0401I/AKURLSysSNI07Ar` (SNI2007 sections)
- **Comparison code:** `compare_populations.py:209-210`; map at `category_mappings.json` `industry_sector.scb_label_mappings`. Non-employed records get `Not Applicable` (synthetic fallback).

**Raw scb02 distribution** (12 SNI2007 sections, employed only):

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

**Mapping (raw → output):**

| Output bucket | Raw values merged |
|---|---|
| Agriculture & Forestry | agriculture, forestry, fishing |
| Manufacturing & Industry | manufacturing, mining and quarrying, energy and environment + construction |
| Retail & Service | trade + transport + accommodation and food services |
| IT & Technology | information and communication + financial operations, business services |
| Public Administration | public administration etc. |
| Education | education |
| Healthcare & Social | human health and social work activities |
| Other | personal and cultural services |
| Not Applicable | *(synthetic — emitted for any non-employed record; no SCB raw)* |

---

## 10. `employment_type` — Aggregation (9 attachment × hours cells → 6, employed only, n = 8,534)

- **Transformation type:** Aggregation (joint 3×3 cells collapsed to 6 buckets).
- **SCB source:** attachment from `AM/AM0401/AM0401I/AKURLSysAnkAr`; hours from `AM/AM0401/AM0401S/NAKUSysselOkArbtidAr`
- **Comparison code:** `compare_populations.py:212-233`; attachment/hours maps at `category_mappings.json` `employment_type.attachment_label_mappings` / `hours_label_mappings`.

**Raw scb02 distribution** (joint cells, employed only):

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

**Mapping (raw → output):**

| Output bucket | Attachment / Hours cells merged |
|---|---|
| Permanent Full-time | permanent / 35+ |
| Permanent Part-time | permanent / 20-34 + permanent / 1-19 (2 cells) |
| Temporary Full-time | temporary / 35+ |
| Temporary Part-time | temporary / 20-34 + temporary / 1-19 (2 cells) |
| Self-Employed | self-employed + family workers / 35+ + ...20-34 + ...1-19 (3 cells — all hours merged for self-employed) |
| Not Applicable | *(synthetic — emitted for any non-employed record; no SCB raw)* |

Notes: For `Self-Employed`, the hours dimension is collapsed entirely — the comparison cannot distinguish full-time vs part-time self-employment.

---

## 11. `housing_tenure` — 1-to-1 rewrite (3 → 3)

- **Transformation type:** 1-to-1 rewrite.
- **SCB source:** `BO/BO0104/BO0104D/BO0104T04`
- **Comparison code:** `compare_populations.py:235-236`; map at `category_mappings.json` `housing_tenure.scb_label_mappings`.

**Raw scb02 distribution:**

| Value | Count | % |
|---|---|---|
| owner-occupied dwellings | 4,009 | 40.09% |
| rented dwellings | 3,451 | 34.51% |
| tenant-owned dwellings | 2,540 | 25.40% |

**Mapping (raw → output):**

| Raw | Output |
|---|---|
| owner-occupied dwellings | Owner-occupied (villa/house) |
| rented dwellings | Rental apartment |
| tenant-owned dwellings | Tenant-owned apartment (bostadsrätt) |

Notes: The mapping config also declares an `Other` output category, but no scb02 raw value maps to it — it is never emitted.

---

## 12. `household_size` — Aggregation (7 → 4)

- **Transformation type:** Aggregation.
- **SCB source:** `BE/BE0101/BE0101S/HushallT03`
- **Comparison code:** `compare_populations.py:238-239`; map at `category_mappings.json` `household_size.scb_label_mappings`.

**Raw scb02 distribution:**

| Value | Count | % |
|---|---|---|
| 1 person | 4,113 | 41.13% |
| 2 persons | 3,019 | 30.19% |
| 4 persons | 1,190 | 11.90% |
| 3 persons | 1,140 | 11.40% |
| 5 persons | 363 | 3.63% |
| 6 persons | 113 | 1.13% |
| 7 persons or more | 62 | 0.62% |

**Mapping (raw → output):**

| Output bucket | Raw values merged |
|---|---|
| 1 person | 1 person |
| 2 persons | 2 persons |
| 3-4 persons | 3 persons + 4 persons |
| 5+ persons | 5 persons + 6 persons + 7 persons or more |

---

## 13. `income_source` — Aggregation (6 → 4)

- **Transformation type:** Aggregation.
- **SCB source:** `HE/HE0110/HE0110F/TabVX13InkStruktN`
- **Comparison code:** `compare_populations.py:241-242`; map at `category_mappings.json` `income_source.scb_label_mappings`.

**Raw scb02 distribution:**

| Value | Count | % |
|---|---|---|
| wage and business income | 6,660 | 66.60% |
| capital income | 1,648 | 16.48% |
| sickness compensation, parental allowance, labour market assistance etc. | 1,117 | 11.17% |
| pensions | 408 | 4.08% |
| social assistance | 127 | 1.27% |
| sickness and activity compensation | 40 | 0.40% |

**Mapping (raw → output):**

| Output bucket | Raw values merged |
|---|---|
| Employment income | wage and business income |
| Capital income | capital income |
| Pension | pensions |
| Social transfers | sickness compensation, parental allowance, labour market assistance etc. + social assistance + sickness and activity compensation (3 merged) |

Notes: The mapping config also lists an `Business/self-employment` output category, but no scb02 raw value maps to it — it is never emitted.

---

## 14. `birth_country_detail` — Aggregation (20 ISO codes + Sweden → 8)

- **Transformation type:** Aggregation (most foreign countries collapsed to `Other`).
- **SCB source:** `BE/BE0101/BE0101E/FodelselandArK` (foreign countries — Sweden born flagged via the `birth_location` field).
- **Comparison code:** `compare_populations.py:244-261`; map at `category_mappings.json` `birth_country_detail.scb_label_mappings`.

**Raw scb02 distribution** (20 foreign-country values sampled across all 10,000 records, regardless of `birth_location`):

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

**Mapping (raw → output):**

| Output bucket | Raw values |
|---|---|
| Sweden | *(forced when `birth_location` resolves to `Sweden` — overrides any sampled foreign value)* |
| Finland | Finland (FI) |
| Iraq | Iraq (IQ) |
| Poland | Poland (PL) |
| Syria | Syrian Arab Republic (SY) |
| Somalia | Somalia (SO) |
| Bosnia and Herzegovina | Bosnia and Herzegovina (BA) |
| Other | Iran (IR) + Afghanistan (AF) + Yugoslavia (YU) + Turkey (TR) + India (IN) + Germany (DE) + Eritrea (ER) + Thailand (TH) + China (CN) + Romania (RO) + Norway (NO) + Denmark (DK) + Ukraine (UA) + United Kingdom (GB) — 14 codes collapsed |

Notes: 
- The override at `compare_populations.py:245-246` (Sweden-born → `birth_country_detail = "Sweden"`) means every record with `birth_location == Sweden` carries `Sweden` here regardless of the sampled `birth_country_detail` value, so the raw `birth_country_detail` distribution above includes labels that the comparison never sees for ~80% of records.
- `Yugoslavia → Other` is the audit's open policy question: the project's birth-country aggregation memory forbids rolling Serbia/Kosovo/Croatia *into* Yugoslavia, but YU itself becoming `Other` loses the country specificity entirely.

---

## 15. `parental_structure` — Aggregation (6 raw → 3 emitted on scb02; schema has 4)

- **Transformation type:** Aggregation.
- **SCB source:** `LE/LE0102/LE0102B/LE0102T17`
- **Comparison code:** `compare_populations.py:200-204`; map at `category_mappings.json` `parental_structure.mappings`.

**Raw scb02 distribution:**

| Value | Count | % |
|---|---|---|
| married or cohabiting natural parents | 7,411 | 74.11% |
| single mother | 1,430 | 14.30% |
| single father | 490 | 4.90% |
| married or cohabiting mother and stepparent | 443 | 4.43% |
| married or cohabiting father and stepparent | 145 | 1.45% |
| living with persons other than parents | 81 | 0.81% |

**Mapping (raw → output):**

| Output bucket | Raw values merged |
|---|---|
| Nuclear Family | married or cohabiting natural parents + married or cohabiting mother and stepparent + married or cohabiting father and stepparent (stepparent variants folded in — signal loss) |
| Single Parent | single mother + single father |
| Living Alone | living with persons other than parents |
| Couple without Children | *(declared in schema; no scb02 raw value — never emitted)* |

Notes: Stepparent families being folded into `Nuclear Family` is editorial — those records are structurally distinct from intact natural-parent families and the comparison cannot recover the distinction. `Couple without Children` is also declared but unreachable from scb02's 6 observed raw values.

---

## 16. `ethnicity` — **Injection** (no SCB source; derived from `birth_location`)

- **Transformation type:** Injection.
- **SCB source:** none — SCB does not publish ethnicity. SCB does not publish ethnicity data; this field is generated entirely by a hand-curated map applied to `birth_location`.
- **Comparison code:** `compare_populations.py:180`; map at `category_mappings.json` `ethnicity.mappings`.

**Raw scb02 distribution:** field does not exist on scb02 records.

**Mapping (`birth_location` schema value → ethnicity output):**

| `birth_location` (post-mapping) | Ethnicity output |
|---|---|
| Sweden | Swedish |
| Nordic Country | Nordic (unreachable on scb02 — see field 6 bug) |
| Europe (Other) | European |
| Outside Europe | Non-European |

Notes: Conflates country of birth with ethnicity (e.g. a UK-born ethnically-Indian person becomes `European`; a Sweden-born child of Syrian parents becomes `Swedish`). The audit flags this as a Severity-1 violation.

---

## 17. `current_environment_type` — **Injection** (no SCB source; derived from `region`)

- **Transformation type:** Injection.
- **SCB source:** none on scb02. The intended source `MI/MI0810/MI0810A/BefLandInvKvmTO` (locality-density share by county) is **never fetched** — `parse_urbanization_by_county()` at `parsers.py:245` is orphan code, `URBANIZATION_TABLE` at `constants.py:23` is unused, and `FetchService.load_all()` makes no call to it.
- **Comparison code:** `compare_populations.py:185`; map at `category_mappings.json` `region.county_env_type`.

**Raw scb02 distribution:** field does not exist on scb02 records.

**Mapping (`region` schema value → environment output, hand-assigned):**

| Environment output | Counties |
|---|---|
| Urban Metropolis | Stockholm, Skåne, Västra Götaland (3) |
| Suburban | Uppsala, Södermanland, Östergötland, Jönköping, Kronoberg, Kalmar, Blekinge, Halland, Örebro, Västmanland, Dalarna, Gävleborg, Västernorrland, Västerbotten, Norrbotten (15) |
| Rural/Countryside | Värmland, Jämtland, Gotland (3) |

Notes: The 21-row county-to-env map is hand-curated. The audit flags this as a Severity-1 violation; either drop `current_environment_type` from the comparison or wire `MI/MI0810` into `fetch_service.load_all()` and base the bucketing on real urbanization share.

---

## Summary

| # | Comparison field | Raw n cats | Output n cats | Type | SCB source on scb02 | Notes |
|---|---|---|---|---|---|---|
| 1 | `age` / `age_group` | ∞ (integer 18–85) | 7 bins (plus passthrough int) | Binning | BE/BE0101/BE0101A/BefolkningNy | — |
| 2 | `biological_sex` | 2 | 2 | 1-to-1 rewrite | BE/BE0101/BE0101A/BefolkningNy | — |
| 3 | `education_level` | 8 | 4 | Aggregation | UF/UF0506/UF0506B/Utbildning | `uppgift saknas` folded into `No Formal Education` |
| 4 | `employment_status` | 2 | 2 | 1-to-1 rewrite | AM/AM0401/AM0401P/NAKUBefUtbNivAr | — |
| 5 | `socioeconomic_class` | 10 deciles | 4 (intended) / 10 (actual, stale) | Aggregation (stale) | HE/HE0110/HE0110F/TabVX10InkStrukt | `category_mappings.json` decile→bucket map removed in commit `ed04d79`; scb02 currently passes deciles through unmapped |
| 6 | `birth_location` | 3 | 3 emitted + 1 unreachable (`Nordic Country`) | 1-to-1 rewrite + **bug** | BE/BE0101/BE0101E/FolkmFodlandHVD | Schema declares `Nordic Country` but query never fetches it |
| 7 | `region` | 21 | 21 | 1-to-1 rewrite | BE/BE0101/BE0101A/BefolkningNy | Strip `" county"` suffix |
| 8 | `civil_status` | 4 | 4 | 1-to-1 rewrite | BE/BE0101/BE0101A/BefolkningNy | — |
| 9 | `industry_sector` | 12 | 8 (+ `Not Applicable` for non-employed) | Aggregation | AM/AM0401/AM0401I/AKURLSysSNI07Ar | n = 8,534 (employed only) |
| 10 | `employment_type` | 9 (3 attachment × 3 hours) | 6 (+ `Not Applicable`) | Aggregation | AM/AM0401/AM0401I + AM/AM0401/AM0401S | Hours collapsed for self-employed |
| 11 | `housing_tenure` | 3 | 3 (`Other` declared but unreached) | 1-to-1 rewrite | BO/BO0104/BO0104D/BO0104T04 | — |
| 12 | `household_size` | 7 | 4 | Aggregation | BE/BE0101/BE0101S/HushallT03 | — |
| 13 | `income_source` | 6 | 4 (`Business/self-employment` declared but unreached) | Aggregation | HE/HE0110/HE0110F/TabVX13InkStruktN | 3 social-transfer types merged |
| 14 | `birth_country_detail` | 20 + Sweden | 8 | Aggregation | BE/BE0101/BE0101E/FodelselandArK | `YU → Other` policy note; Sweden override |
| 15 | `parental_structure` | 6 | 3 emitted (schema has 4) | Aggregation | LE/LE0102/LE0102B/LE0102T17 | Stepparent variants → `Nuclear Family` (signal loss) |
| 16 | `ethnicity` | — | 4 (3 reachable on scb02) | **Injection** | none | Derived from `birth_location` |
| 17 | `current_environment_type` | — | 3 | **Injection** | none (orphan `MI/MI0810`) | Hand-curated 21-county map |
