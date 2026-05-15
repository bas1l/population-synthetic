# Plan: Batch Extractor — Identity Format Mismatch

**Date:** 2026-05-08
**Author:** Basil
**Status:** Completed
**Completed:** 2026-05-09 09:47
**Base Branch:** `feature/comparison-pipeline-outputs`
**Branch:** `feature/batch-extractor-identity-format`

---

## Problem Statement

`_extract_batch` in `scripts/extract_population_from_pipeline.py` produces `Unknown` for nearly every demographic field when run against batch-format seeds (e.g. seed-08). The root cause is a structural mismatch between the extraction strategy and the actual batch identity format.

### What the extractor expected

Phase 2 implemented keyword scanning: for each field, iterate over known English label strings (e.g. `"Married/Cohabiting"`, `"Permanent Full-Time"`) and check if they appear as substrings in the identity text.

### What the batch format actually contains

Batch identity files (`identity.json`) store a single `"narrative"` key whose value is a semi-structured clinical narrative produced by an LLM following a template with labeled fields (`Age:`, `Gender:`, `Location:`, `Occupation:`) plus Swedish-context prose paragraphs. The narrative contains Swedish keywords (`gift`, `hyresrätt`, `arbetar`) and city names (`Linköping`, `Växjö`) rather than English schema labels.

---

## What Was Changed

All changes confined to `scripts/extract_population_from_pipeline.py`. The generation pipeline is untouched.

### 1. New constants added

- **`_CITY_TO_COUNTY`** — ~60 Swedish city-to-county mappings (e.g. `"linköping"` -> `"Östergötland"`)
- **`_METRO_CITIES`** / **`_LARGE_CITIES`** — city size classification for environment type inference
- **`_OCCUPATION_TO_INDUSTRY`** — ~40 Swedish/English occupation keywords to industry sector labels
- **`_UNIVERSITY_OCCUPATIONS`** — occupations that require a university degree in Sweden (regulated professions)

### 2. New helper functions

- **`_parse_template_fields(text)`** — regex-parses the batch template structure to extract `age`, `gender`, `location`, `occupation` as raw strings
- **`_extract_city_from_location(location_raw)`** — splits "Linköping, Östergötlands län" into just the city
- **`_industry_from_occupation()`** / **`_education_from_occupation()`** — lookup helpers against the new dicts
- **`_employment_type_from_prose()`** — infers employment type from Swedish/English keywords + employment status
- **`_income_source_from_context()`** — infers income source from employment status

### 3. Rewritten `_extract_batch()`

Two-phase approach:
- **Phase 1 — Template field parsing:** Parse labeled bullet-point fields (Age, Gender, Location, Occupation) for age, sex, region, environment, employment status, industry, education
- **Phase 2 — Bilingual prose scanning:** Swedish + English keyword patterns for civil status, housing, household size, birth location, socioeconomic class, parental structure

All existing normalizer functions (`_normalize_education`, `_normalize_employment`, etc.) are reused as fallbacks. No existing functions were modified.

---

## Results (seed-08, n=100)

| Field                    | Before (% Unknown) | After (% Unknown) |
|--------------------------|--------------------:|-------------------:|
| age_group                | 68%                | 0%                 |
| biological_sex           | 17%                | 0%                 |
| current_environment_type | 99%                | 0%                 |
| region                   | 46%                | 0%                 |
| industry_sector          | 92%                | 0%                 |
| employment_type          | 100%               | 0%                 |
| income_source            | 92%                | 0%                 |
| socioeconomic_class      | 100%               | 0%                 |
| birth_location           | 64%                | 0%                 |
| birth_country_detail     | 100%               | 0%                 |
| parental_structure       | varies             | 0%                 |
| education_level          | ~5%                | 1%                 |
| employment_status        | ~11%               | 0%                 |
| civil_status             | 100%               | 4%                 |
| household_size           | 100%               | 2%                 |
| housing_tenure           | 82%                | 3%                 |

Sequential format (seed-07) verified unaffected: 0 warnings, 0 Unknown, 0 skipped.

---

## Remaining Problems (Not Caused by Extraction)

The comparison report still shows significant divergence (p=0.000 on most fields, coherence score 2%). These are **generation-side** problems, not extraction bugs:

### 1. Homogeneous batch output

The batch prompt produces extremely uniform demographics:
- 80% of personas are age 35-44 (vs SCB: spread across 18-85)
- 100% are Employed (vs SCB: mix of employed, unemployed, student, retired)
- 87% are Female (vs SCB: ~50/50)
- 87% have University Degree (vs SCB: spread across 4 levels)
- 100% born in Sweden (vs SCB: ~20% foreign-born)
- Only 7 of 21 counties represented (vs SCB: all 21)

This uniformity is inherent to the batch prompt (`prompt_identity_generation_002_swedish.txt`) — it gives the LLM no demographic constraints, so it converges on a narrow archetype (35-44 year old employed Swedish woman with a university degree).

### 2. Label alignment mismatches — FIXED

Root cause was **case-sensitive lookups** in `normalize_scb_to_schema()`. The SCB API returns labels with different casing than `category_mappings.json` keys (e.g. `"ISCED97 3A"` vs `"isced97 3a"`, `"born in Sweden"` vs `"Born in Sweden"`).

**Bugs found and fixed:**

| Bug | Root cause | Fix location |
|-----|-----------|-------------|
| education_level (TV=1.0→0.18) | Case-sensitive lookup: `"ISCED97 3A"` vs `"isced97 3a"` | `compare_populations.py` — `_ci_map()` + `_ci_get()` |
| birth_location (TV=1.0→0.11) | Case-sensitive lookup: `"born in Sweden"` vs `"Born in Sweden"` | same |
| socioeconomic_class (all unmapped) | `"Decile 5"` format not parsed — map expected `"5"` or `"D5"` | `compare_populations.py` — strip `"Decile "` prefix |
| parental_structure (unmapped) | Raw labels `"married or cohabiting natural parents"` didn't exact-match code `"natural parents"` | `compare_populations.py` — substring matching; `category_mappings.json` — added full-form labels |
| birth_country_detail (unmapped) | Sweden-born got raw label `"born in Sweden"` — `bc_detail_map` only has ISO codes | `compare_populations.py` — derive from birth_location; `sample_service.py` — case fix in `_SWEDEN_LABELS` |
| age_group "75-85" vs "75+" | `_age_to_group()` returned `"75+"` but schema uses `"75-85"` | `compare_populations.py`, `extract_population_from_pipeline.py` |
| industry_sector (batch) | `_industry_from_occupation()` returned raw labels without `_normalize_industry_sector()` | `extract_population_from_pipeline.py` — apply normalizer |

**Seed-007 after fix:** coherence 0% → 71.4%, education TV 1.0 → 0.18, birth_location TV 1.0 → 0.11

**Remaining unmapped (not label bugs):**
- `employment_status` "Retired"/"Student" — SCB AKU table only covers labor force (employed/unemployed); fetch_service needs additional table for "not in labour force" subcategories
- `housing_tenure` "Other" — pipeline artifact with no SCB counterpart
- `income_source` "Business/self-employment" — pipeline distinguishes from employment income; SCB combines as "wage and business income"
- `parental_structure` "Couple without Children" — SCB LE0102 table doesn't have this category

### 3. Coherence score driven by uniformity (seed-008 only)

After label fix, seed-007 coherence is 71.4% (reasonable for n=21). Seed-008 coherence is 99.0% (ironically high because the uniform 35-44/Employed/University tuple now correctly maps to an SCB-plausible cell). The batch prompt diversity problem remains but is a generation concern, not comparison.

---

## Next Steps

- [x] Investigate label alignment: compare pipeline schema labels against SCB reference labels in `category_mappings.json` and fix whichever side is wrong
- [x] Re-run extraction for seed-008 to pick up industry_sector normalizer fix (requires `_normalize_industry_sector()` on `_industry_from_occupation()` output)
- [ ] Consider whether the batch prompt needs demographic diversity constraints (separate plan)
- [ ] Consider adding "not in labour force" subcategories to employment_status fetch (separate plan)
- [x] Commit all fixes on `feature/batch-extractor-identity-format` branch
