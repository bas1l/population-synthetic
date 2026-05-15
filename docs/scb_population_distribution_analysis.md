# SCB Population Generator — Distribution Analysis Report

**Date:** 2026-05-07
**Scope:** Audit of all 14 SCB API fetches to determine whether bulk querying produces the same distributions as per-individual filtered queries, and to identify conditioning structure lost by the current approach.

---

## Background

The SCB population generator fetches aggregate statistics from 14 SCB PxWeb API tables, normalizes them into probability distributions, and samples individuals locally. The question: does fetching all data in one bulk call per table produce the same distributions as making narrower, per-individual API calls filtered to that person's already-sampled attributes (age, sex, education, employment)?

## Bulk vs. Per-Individual API Calls

The SCB PxWeb API only serves aggregate cross-tabulations (population counts by category), not individual-level microdata. Individual-level microdata exists in SCB's MONA platform but is restricted to approved researchers and cannot be downloaded. There is no "sample me a random person" endpoint — randomization must happen client-side regardless of approach.

Given this constraint, there are two possible strategies:

**Current approach (bulk):** Fetch entire tables in one call per dimension, parse into probability distributions client-side, then sample locally from those distributions.

**Alternative (per-individual filtering):** After sampling early attributes (e.g., age=27, sex=Male), make a new API call for each subsequent field filtered to those specific values (e.g., fetch education counts for 27-year-old males only), normalize that narrow slice, and sample from it.

**Are these equivalent?** Not always. They produce the same result **only when the bulk query separates the conditioning dimensions and the parser preserves them.** Specifically:

- **Equivalent (5 fields):** When the query requests dimensions separately (e.g., `Kon: ["1", "2"]` not `"1+2"`) and the parser groups results by those dimensions, slicing the bulk result is mathematically identical to a filtered query. This holds for: age_sex, birth_location, region, civil_status, income_source.

- **Not equivalent (4 fields):** When the query combines dimensions (e.g., `Kon: ["1+2"]`) or the parser sums across dimensions it received, the bulk result is a marginal average that differs from what a per-individual filtered query would return. This affects: education (sex pooled), employment (sex pooled + education ignored), employment_type (sex pooled), birth_country_detail (age/sex summed away by parser despite being in the query).

- **Marginal by design (5 fields):** Some fields are intentionally sampled as marginals with no conditioning. Bulk and per-individual queries would both return the same marginal, but neither captures the real conditional structure. This affects: socioeconomic, parental_structure, industry_sector, housing_tenure, household_size.

**Practical implication:** Making per-individual API calls would not improve the generator unless the parsers are also updated to preserve the conditioning dimensions. For 4 fields, the fix is straightforward: separate sex in the query and/or stop summing across dimensions in the parser. For the 5 marginal fields, improvement requires finding SCB tables that cross-tabulate with the relevant conditioning variables.

## Summary

| Verdict | Count | Fields |
|---------|-------|--------|
| Bulk = per-individual (no difference) | 5/14 | age_sex, birth_location, region, civil_status, income_source |
| Bulk hides real conditioning structure | 4/14 | education, employment, employment_type, birth_country_detail |
| Marginal by design (not a bulk limitation) | 5/14 | socioeconomic, parental_structure, industry_sector, housing_tenure, household_size |

---

## Field-by-Field Analysis

### 1. age_sex — NO DIFFERENCE

- **Query:** `Region: "00"`, `Alder: [18..85]`, `Kon: ["1", "2"]` (separate sexes)
- **Parser:** Aggregates single years into 7 age bands, normalizes joint (age_group, sex) distribution
- **Sampling:** Marginal (Step 1) — sampled first as the root of the dependency chain
- **Analysis:** The query correctly separates sexes. Bulk and per-individual produce identical results because summing cell-level counts client-side is equivalent to letting the API filter.

### 2. education_by_age — SEX CONDITIONING LOST

- **Query:** `Region: "00"`, `Alder: [18..74]`, `UtbildningsNiva: [all 8 levels]` — **sex is not a query dimension**
- **Parser:** Groups by age band, normalizes education distribution per band. Produces `{age_group -> {education -> P}}`
- **Sampling:** Conditional on age_group only (Step 2)
- **Analysis:** The query implicitly pools males and females. Education distributions differ by sex in Sweden (e.g., higher share of women hold university degrees in younger cohorts). A per-individual query filtered to (age, sex) would yield a different education distribution than the current sex-pooled one.
- **Impact:** Unknown magnitude without re-running queries with sex separation. Likely moderate — the gender gap in Swedish higher education is well-documented.

### 3. employment_by_age — EDUCATION CONDITIONING LOST + SEX POOLED

- **Query:** `Kon: ["1+2"]` (both sexes combined), `Alder: [pre-grouped bands]`, `Arbetskraftstillh: ["SYS", "ALOS", "EIAKR"]`
- **Parser:** Iterates employment statuses by age, then **assigns the same employment distribution to all education levels within each age group** — the conditioning key `(age_group, education)` exists in the output, but all education levels share identical probabilities.
- **Sampling:** Conditional on (age_group, education_level) at Step 3 — but the education dimension has no effect due to the parser's design.
- **Analysis:** Two independent issues:
  1. **Sex pooling:** The `"1+2"` filter combines both sexes. Employment rates differ by sex.
  2. **Artificial education independence:** The parser copies the same age-level employment distribution across all education labels. In reality, university graduates have substantially higher employment rates than those with no formal education. This is not a limitation of bulk querying — it is a parser design choice that ignores education-employment correlation entirely.
- **Impact:** High. Education is one of the strongest predictors of employment status.

### 4. birth_location — NO DIFFERENCE

- **Query:** `Alder: ["TOT1"]` (all ages), `Kon: ["1+2"]` (both sexes), `Fodelseland: ["FSV", "FEU", "FUEU"]`
- **Parser:** Normalizes across 3 birth regions (Sweden, EU, Outside-EU)
- **Sampling:** Marginal (Step 4)
- **Analysis:** Explicitly marginal query. Bulk and per-individual produce identical results. Note: birth location does vary by age cohort (immigration waves), but this is a deliberate modeling simplification, not a bulk-vs-filtered issue.

### 5. region — NO DIFFERENCE

- **Query:** `Region: [all 21 county codes]`, `Alder: [18..85]`, `Kon: ["1", "2"]`
- **Parser:** Sums across all ages and both sexes per county, normalizes
- **Sampling:** Marginal (Step 4)
- **Analysis:** Marginal by design. Summing client-side is equivalent to a marginal API query. Regional concentration does vary by age (younger populations in Stockholm), but this is an intentional simplification.

### 6. socioeconomic — MARGINAL BY DESIGN

- **Query:** `Region: "00"`, `Inkomstkomponenter: ["300"]`, `Inkomstsum: ["D1"..."D10"]`
- **Parser:** Maps deciles to 4 income classes, assigns equal weight per decile
- **Sampling:** Marginal (Step 4)
- **Analysis:** Marginal over age, sex, education, and employment. In reality, socioeconomic class correlates strongly with education and employment status. A per-individual query conditioned on (education, employment) would yield very different distributions. This is a modeling limitation, not a bulk-vs-filtered issue.

### 7. parental_structure — MARGINAL BY DESIGN

- **Query:** `Alder: ["0-17"]` (children's age), `Kon: ["5+6"]`, `UtlBakgrund: ["TotalC"]`, `UtbNivaForalder: ["30"]`
- **Parser:** Maps family codes to structure types, normalizes
- **Sampling:** Marginal (Step 4)
- **Analysis:** The query fetches family structure data for children aged 0-17, then applies this distribution to adults aged 18-85. This is a conceptual mismatch — an adult's current family situation differs from childhood family structure. Bulk vs. per-individual makes no difference here; the issue is the data source itself.

### 8. civil_status — NO DIFFERENCE

- **Query:** `Region: "00"`, `Civilstand: ["OG", "G", "ANKL", "SK"]`, `Alder: [18..85]`, `Kon: ["1", "2"]` (separate sexes)
- **Parser:** Builds conditional distribution `{(age_group, sex) -> {status -> P}}`
- **Sampling:** Conditional on (age_group, biological_sex) at Step 5
- **Analysis:** The query correctly separates both age and sex. The parser preserves both conditioning dimensions. Bulk and per-individual produce identical results.

### 9. industry_sector — MARGINAL BY DESIGN

- **Query:** `Kon: ["1+2"]` (both sexes combined), `Alder: ["tot15-74"]` (all ages combined), `SNI2007: [12 industry codes]`
- **Parser:** Normalizes across industry codes, returns `{industry -> P}`
- **Sampling:** Marginal, applied only if employed (Step 6)
- **Analysis:** The query is maximally marginal — no age, sex, or education structure. Industry distribution varies substantially by all three (e.g., healthcare skews female, construction skews male and older). A per-individual query filtered to (age, sex, education) would produce materially different distributions. This is a modeling limitation — the SCB table does support age and sex breakdowns.

### 10. employment_type — SEX CONDITIONING LOST

- **Query (attachment):** `Kon: ["1+2"]` (both sexes combined), `Alder: [pre-grouped bands]`
- **Query (hours):** `Kon: ["1+2"]` (both sexes combined), `Alder: [pre-grouped bands]`
- **Parser:** Parses attachment and hours separately by age, takes outer product to produce combined employment types, normalizes per age group
- **Sampling:** Conditional on (employment_status, age_group) at Step 7
- **Analysis:** Both queries use `"1+2"` (combined sexes). Full-time vs. part-time employment has one of the largest gender gaps in Swedish labor statistics (~15-25 percentage points). A per-individual query filtered to sex would yield substantially different distributions — women are far more likely to work part-time.
- **Impact:** High. This is a well-documented and large effect.

### 11. housing_tenure — MARGINAL BY DESIGN

- **Query:** `Region: "00"`, `Hustyp: ["SMAHUS", "FLERBOST"]`, `Upplatelseform: ["1", "2", "3"]`
- **Parser:** Normalizes across tenure categories
- **Sampling:** Marginal (Step 8)
- **Analysis:** Marginal over age, sex, income, and family structure. In reality, tenure correlates with age (younger = rental), income, and household composition. A per-individual query could condition on these. This is a modeling limitation.

### 12. household_size — MARGINAL BY DESIGN

- **Query:** `Region: "00"`, `Hushallsstorlek: [7 size categories]`
- **Parser:** Normalizes across size categories
- **Sampling:** Marginal (Step 9)
- **Analysis:** Marginal over all individual attributes. Household size correlates with age, civil status, and parental structure. A per-individual query could condition on these. This is a modeling limitation.

### 13. income_source — NO DIFFERENCE

- **Query:** `Region: "00"`, `Sysselsattning: [5 employment types]`, `Alder: [5 age bands]`, `Inkomstkomponenter: [6 types]`
- **Parser:** Builds conditional distribution `{(employment, age_group) -> {source -> P}}`
- **Sampling:** Conditional on (employment_status, age_group) at Step 10
- **Analysis:** The query correctly cross-tabulates employment and age. The parser preserves both conditioning dimensions. Bulk and per-individual produce identical results.

### 14. birth_country_detail — AGE/SEX CONDITIONING LOST

- **Query:** `Fodelseland: [top country codes]`, `Alder: [18..85]`, `Kon: ["1", "2"]` (separate sexes)
- **Parser:** Sums counts across **all ages and both sexes** per country, normalizes to marginal `{country -> P}`
- **Sampling:** Conditional on birth_location at Step 11 (only sampled for non-Sweden birth locations)
- **Analysis:** The query is structured to capture age and sex variation in country of origin — but the parser immediately discards this by summing across both dimensions. Immigration patterns in Sweden are strongly cohort-specific (e.g., large influx from Syria in 2015 affects younger cohorts more; Finnish immigration was predominantly older cohorts). The query already fetches the data needed for conditioning, but the parser throws it away.
- **Impact:** Moderate to high for realism of foreign-born individuals. The fix would be to preserve the (age_group, sex) structure in the parser rather than summing.

---

## Prioritized Improvement Opportunities

Ranked by expected impact on population realism:

| Priority | Field | Issue | Fix |
|----------|-------|-------|-----|
| 1 | employment_by_age | Education-employment correlation destroyed by parser | Query with education dimension or use a table that cross-tabulates education x employment; remove the forced-uniform distribution across education levels |
| 2 | employment_type | Sex pooled via `"1+2"` | Query with `Kon: ["1", "2"]` separately; condition on (age_group, sex) at sampling time |
| 3 | education_by_age | Sex pooled (implicit) | Add `Kon` as a query dimension; condition on (age_group, sex) at sampling time |
| 4 | birth_country_detail | Parser sums away age/sex structure that the query already fetches | Preserve (age_group, sex) keys in parsed output; condition at sampling time |
| 5 | industry_sector | Marginal over age/sex/education | Add `Kon` and `Alder` as query dimensions; condition at sampling time |
| 6 | socioeconomic | Marginal over education/employment | Investigate SCB tables that cross-tabulate income by education or employment |
| 7 | housing_tenure | Marginal over age/income | Investigate SCB tables with age or income breakdown |
| 8 | household_size | Marginal over age/family | Investigate SCB tables with age or civil status breakdown |

---

## Conclusion

5 out of 14 fields produce identical distributions whether queried in bulk or per-individual. 4 fields lose real conditioning structure (sex, education, or age/sex) — either because the query combines sexes (`"1+2"`) or because the parser sums away dimensions the query already captures. The remaining 5 fields are marginal by design choice, not by API limitation.

The most impactful gap is the artificial independence between education and employment status: the parser forces all education levels to share the same employment distribution within each age group, ignoring one of the strongest statistical relationships in labor economics.
