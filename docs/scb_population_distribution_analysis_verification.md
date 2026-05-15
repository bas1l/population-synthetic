# Verification Report: SCB Population Distribution Analysis

**Date:** 2026-05-07
**Scope:** Independent verification of claims made in `scb_population_distribution_analysis.md`, cross-checked against the codebase (`anxiety_synthetic/scb_population/`) and the live SCB PxWeb API.

---

## Methodology

1. **Code audit:** Read all query payloads in `fetch_service.py` and all parser functions in `parsers.py` to confirm the document's claims about query parameters and parser behavior.
2. **Live API calls:** Queried the SCB PxWeb API (v1 at `https://api.scb.se/OV0104/v1/doris/sv/ssd/`) to verify endpoint behavior, variable codes, and the `"1+2"` notation.
3. **Web research:** Cross-referenced statistical claims (gender gaps in education, employment, immigration cohorts) against SCB publications and external sources.

---

## Foundational Claims (API Architecture)

### "The SCB PxWeb API only serves aggregate cross-tabulations, not individual-level microdata."

**Correct.** Confirmed via live API calls. Responses are population counts keyed by category tuples, e.g. `{["00","OG","25","1","2024"]: ["64032"]}` meaning "64,032 unmarried 25-year-old men in Sweden in 2024." There is no individual-record structure anywhere in the API.

### "Individual-level microdata exists in SCB's MONA platform but is restricted to approved researchers and cannot be downloaded."

**Correct.** SCB's official documentation states: "Users can process data online without the microdata ever leaving Statistics Sweden." Access requires a confidentiality assessment under the Public Access to Information and Secrecy Act. Users work through remote Windows connections; aggregated outputs can be exported, but raw microdata cannot. Users sign secrecy clauses.

### "There is no 'sample me a random person' endpoint -- randomization must happen client-side."

**Correct.** The PxWeb API supports only: browsing the table hierarchy (GET), retrieving table metadata (GET), and querying aggregate data with filters (POST with filter types: `item`, `all`, `top`, `agg`, `vs`). No sampling endpoint exists. Person-level generation must be performed client-side from the aggregate distributions.

---

## Correction: The `"1+2"` Notation

The document treats `"1+2"` as if it were a general API aggregation operator that combines values server-side. **This is partially incorrect.** `"1+2"` is a **predefined value code** that exists in some tables but not others:

| Table | `Kon` values available | `"1+2"` available? |
|-------|----------------------|-------------------|
| `AM0401/AKURLBefAr` (employment) | `["1", "2", "1+2"]` | Yes -- labeled "totalt" |
| `BE0101/FolkmFodlandHVD` (foreign-born) | `["1", "2", "1+2"]` | Yes -- labeled "totalt" |
| `BE0101/BefolkningNy` (population) | `["1", "2"]` | **No** -- sending `"1+2"` returns HTTP 400 |
| `UF0506/Utbildning` (education) | `["1", "2"]` | **No** -- not a valid code |

The practical effect described in the document (sex is pooled) is correct for each field. But the mechanism differs: in tables with `"1+2"`, it selects a pre-computed total row; in tables without it, pooling happens because the `Kon` dimension is simply omitted from the query. The document's suggestion to "query with `Kon: ["1", "2"]` separately" is valid -- both `"1"` and `"2"` are available in all tables where `"1+2"` is used.

---

## Statistical Claims

### "Higher share of women hold university degrees in younger cohorts"

**Correct.** SCB's "Women and Men in Sweden -- Facts and Figures 2024" and Q2 2025 gender statistics confirm that female enrollment and degree completion in higher education substantially exceed male rates. The proportion of highly educated women has more than doubled over time; the increase among men has been smaller.

### "Full-time vs. part-time employment gap is ~15-25 percentage points"

**Partially correct -- overstated for the general population.** SCB Q1 2025 data shows:
- General working population: 80% of employed women work full-time vs. 90% of men = **~10 pp gap**
- Parents with 1 child: 29% women part-time vs. 8% men = **21 pp gap**
- Parents with 3+ children: 37% women part-time vs. 13% men = **24 pp gap**
- Eurostat (December 2024): Sweden's gender gap in part-time employment = **13.6 pp**

The claimed range of 15-25 pp is accurate for parents but overstates the general population gap. The characterization as "one of the largest gender gaps" remains reasonable.

### "Immigration patterns are cohort-specific (Syria 2015 / Finland 1960s-70s)"

**Correct.** 163,000 asylum seekers arrived in 2015; Syria was the largest origin (50,000+). The demographic profile skewed young: ~half were children, 30,000+ unaccompanied minors (predominantly boys 13-17). These individuals now appear disproportionately in younger cohorts. Finnish-to-Sweden migration peaked in the 1960s-70s (41,000 in 1970 alone, ~400,000 total). SCB confirms half of Finland-born residents have lived in Sweden 45+ years, placing them in their 70s-80s+.

---

## Field-by-Field Code Verification

Every query parameter and parser behavior described in the document was cross-checked against `fetch_service.py` and `parsers.py`. All 14 fields match.

### 5 "No Difference" Fields -- All Confirmed

| Field | Query | Parser | Verified |
|-------|-------|--------|----------|
| `age_sex` | `Kon: ["1", "2"]` (separate) | Preserves joint (age, sex) distribution | Correct |
| `birth_location` | `Kon: ["1+2"]`, `Alder: ["TOT1"]` | Marginal over 3 birth regions | Correct |
| `region` | `Kon: ["1", "2"]`, all 21 counties | Sums to marginal per county | Correct |
| `civil_status` | `Kon: ["1", "2"]`, `Alder: [18..85]` | Preserves (age_group, sex) conditioning | Correct |
| `income_source` | Cross-tabulates employment x age | Preserves (employment, age_group) conditioning | Correct |

### 4 "Conditioning Lost" Fields -- All Confirmed

| Field | Claimed issue | Code evidence |
|-------|--------------|---------------|
| `education_by_age` | Sex not in query | `Kon` dimension entirely absent from query payload -- sex pooled implicitly |
| `employment_by_age` | Sex pooled + education ignored | `Kon: ["1+2"]`; parser assigns identical employment distribution to all education levels within each age group (same dict comprehension applied across all `EDUCATION_LABELS`) |
| `employment_type` | Sex pooled | Both attachment and hours sub-queries use `Kon: ["1+2"]` |
| `birth_country_detail` | Parser discards age/sex | Query includes `Kon: ["1", "2"]` and `Alder: [18..85]`, but parser sums counts across all ages and both sexes per country, returning a flat `{country -> P}` marginal |

### 5 "Marginal by Design" Fields -- All Confirmed

| Field | Confirmed marginal | Notes |
|-------|--------------------|-------|
| `socioeconomic` | Yes | Income deciles with no conditioning on education/employment |
| `parental_structure` | Yes | Fetches child family structure (age 0-17), applies to adults 18-85 |
| `industry_sector` | Yes | `Kon: ["1+2"]`, `Alder: ["tot15-74"]` -- maximally marginal |
| `housing_tenure` | Yes | No age, income, or household conditioning |
| `household_size` | Yes | No conditioning on any individual attribute |

---

## Summary of Corrections

Only two factual corrections apply to the original document:

1. **`"1+2"` mechanism:** The document implies this is a general API aggregation operator. It is actually a table-specific pre-computed value code. Not all tables support it; some (e.g., `BefolkningNy`, `Utbildning`) will reject it with HTTP 400. This does not change the document's conclusions -- the pooling effect is real -- but the mechanism description should be refined.

2. **Part-time employment gender gap:** The claimed 15-25 pp range applies specifically to parents, not the general working population (~10 pp). Eurostat reports Sweden's overall gap at 13.6 pp. The document should qualify this range or cite the parent-specific context.

All other claims -- the 14-field classification, the query parameters, the parser behaviors, the prioritized improvement list, and the architectural conclusions -- are accurate.

---

## Sources

- SCB PxWeb API v1: `https://api.scb.se/OV0104/v1/doris/sv/ssd/`
- SCB PxWeb API v2: `https://statistikdatabasen.scb.se/api/v2/`
- SCB MONA platform: https://www.scb.se/en/services/ordering-data-and-statistics/microdata/mona--statistics-swedens-platform-for-access-to-microdata/
- SCB Gender Statistics Q1 2025 (part-time work): https://www.scb.se/en/finding-statistics/statistics-by-subject-area/population-and-living-conditions/gender-statistics/gender-statistics/pong/statistical-news/gender-statistics-quarter-1-2025/
- SCB Gender Statistics Q2 2025 (education): https://www.scb.se/en/finding-statistics/statistics-by-subject-area/population-and-living-conditions/gender-statistics/gender-statistics/pong/statistical-news/gender-statistics-quarter-2-2025/
- Women and Men in Sweden 2024: https://www.scb.se/en/finding-statistics/statistics-by-subject-area/population-and-living-conditions/gender-statistics/gender-statistics/produktrelaterat/reports/women-and-men-in-sweden---facts-and-figures-2024/
- Eurostat -- Sweden gender gap in part-time employment (December 2024)
- PxWeb API specification: https://pxdata.stat.fi/API-description_SCB.pdf
