# Findings: Unknown / Unmatched SCB Labels (seed013)

**Date:** 2026-05-10
**Companion to:** `investigate-unknown-unmatched-scb-labels.md`
**Source data:** `data/comparison_report.json` + `seed_013_compared-only-identity/persona_*/identity.json` (n=100)

---

## 1. How the comparison surfaces "unmapped"

`StatisticalEvaluator._marginal_metrics` (`scripts/compare_populations.py:295`) defines:

```python
unmapped = [c for c in counts_b if c not in counts_a and c is not None]
```

So `unmapped` means **"label present in pipeline (B) but absent from SCB reference (A)"**. There are three distinct root causes that all surface as "unmapped":

| Root cause | What it actually means | Fix layer |
|---|---|---|
| **Free-text drift** | LLM emitted a value the *pipeline-side* normalizer in `extract_population_from_pipeline.py` could not map → ends up as `"Unknown"` | `_extract_flat` keyword maps |
| **Schema / canonical gap** | SCB-side normalizer (`compare_populations.normalize_scb_to_schema`) never produces this label, so even a perfectly-extracted pipeline value cannot match | `category_mappings.json` and/or SCB fetch coverage |
| **Statistical sparsity** | Both sides could in principle produce the value, but the SCB sample (n=10000) happens to contain zero | Not a bug — accept |

## 2. Per-attribute audit

Counts below are personas in seed013 (n=100) whose extracted value is `Unknown` after `extract_population_from_pipeline._extract_flat`. The "Raw values dropped" column lists the LLM strings that fell through.

### 2.1 `employment_status` — 12 Unknown + "Retired" canonical-missing

| Class | Count | Raw LLM value | Suggested mapping |
|---|---|---|---|
| alias_missing | 5 | `Parental leave`, `On parental leave`, `Parental leave (Föräldraledig)` | **Employed** (SCB AKU: parental leave keeps employment relationship) |
| alias_missing | 4 | `Long-term sick leave`, `Long-term sick leave/Disability`, `On sick leave`, `On long-term sick leave`, `On long-term sick leave / Receiving disability benefits` | **Employed** for short/medium term sick leave; **Unemployed** for permanent disability pension. Default to **Employed** unless "disability" is also present |
| alias_missing | 1 | `Military service` | **Employed** |
| alias_missing | 1 | `Arbetssökande` | **Unemployed** (Swedish "job-seeker") |
| canonical_missing | 19+10 | LLM `Retired`/`Student` (correctly mapped) | SCB pop_a only has `Employed`/`Unemployed` because the AKU fetch returns only `sysselsatta` + `arbetslösa`. Need to extend `FetchService` to include `pensionärer` and `studerande` rows or accept the mismatch. |

**Recommended action:** extend `_normalize_employment` regex with Swedish keywords:

```python
if any(k in raw_lower for k in ("parental leave", "föräldraledig", "föräldrale",
                                  "sick leave", "sjukskriven", "sjukpenning",
                                  "military service", "värnplikt")):
    return "Employed"
if "arbetssök" in raw_lower:
    return "Unemployed"
if any(k in raw_lower for k in ("disability pension", "sjukersättning", "förtidspension")):
    return "Retired"  # SCB AKU classifies these as outside labour force
```

Plus a separate **SCB-fetch fix**: `scb_population/fetch_service.py` should pull `ArbetsmarknadsstStatus` codes 4, 5, 6, 7 (student / pensioner / other inactive) so `Retired` and `Student` exist in pop_a. Without that, every retired pipeline persona is flagged "unmapped" by construction. This is the **dominant driver of the 63% coherence score** — 19 of 37 flagged personas have `employment_status=Retired` paired with age groups where pop_a's joint distribution is empty by construction.

### 2.2 `education_level` — 3 Unknown

| Raw LLM value | Suggested mapping | Reason |
|---|---|---|
| `Completed Upper Secondary School` (1) | High School (Gymnasieskola) | "secondary" not in keyword list |
| `Upper secondary education` (1) | High School (Gymnasieskola) | same |
| `Doktorsexamen` (1) | University Degree | "doktor" not in keyword list |

**Fix:** add `"secondary"`, `"doktor"`, `"licentiat"` to the university keywords in `_normalize_education`.

### 2.3 `birth_location` — 39 Unknown (largest pipeline-side gap)

The schema treats `birth_location` as a 4-class categorical (Sweden / Nordic Country / Europe (Other) / Outside Europe). The LLM treats it as a free-text place-of-birth field, producing 70+ distinct values, mostly Swedish counties and cities.

| Class | Examples | Count | Suggested mapping |
|---|---|---|---|
| Swedish region with `län` suffix | `Stockholms län`, `Skåne län`, `Västra Götalands län`, `Dalarnas län`, etc. | 27 | **Sweden** — extend `_birth_location_from_flat` to strip `" län"` then look up `REGION_LABELS` |
| Swedish city not in `_CITY_TO_COUNTY` | `Kalix`, `Sorsele`, `Hedemora`, `Robertsfors kommun`, `Oskarshamn`, `Västervik`, `Avesta`, `Timrå` | 8 | **Sweden** — these are all Swedish municipalities. Could expand `_CITY_TO_COUNTY` or simpler heuristic: if the value resolves to a Swedish region or contains `kommun`/`stad`, treat as Sweden |
| Compound `City, Region/Country` | `Avesta, Dalarnas län`, `Born in Stockholms län`, `Born in Jönköpings län` | 3 | **Sweden** — strip `Born in `, split on comma |
| Foreign country (mappable) | `Kosovo`, `United Kingdom`, `Middle East`, `Born in a Middle Eastern country` | 4 | **Outside Europe** for Kosovo/Middle East; **Europe (Other)** for UK |

**Strongly recommended:** add an explicit enum to the prompt for `birth_location`. The schema description says "immigration or migration status" but the LLM ignores this and writes geography. Constraining to `["Native (Born in Sweden)", "Domestic Migrant (Same country, different region)", "International Immigrant", "Refugee/Displaced"]` would eliminate this entire class of drift in one change.

### 2.4 `current_environment_type` — 23 Unknown

All 23 are variants of `Small town` / `Smaller town` / `Town`. The schema has only `Urban Metropolis`, `Suburban`, `Rural/Countryside` — there is no "small town" bucket.

**Fix (one-liner):** add `"small town", "smaller town", "town"` to the suburban keyword list in `_extract_flat` (line ~1141). Justification: SCB's `Tatortsgrad` aggregates "större städer och täta kommuner" (codes 2-3) under Suburban, which is the closest match to a "small town".

### 2.5 `socioeconomic_class` — 2 Unknown

| Raw LLM value | Suggested mapping |
|---|---|
| `Economically Vulnerable` | Poverty (or Working Class) |
| `Professional Class` | Middle Class |

**Fix:** add keywords `"vulnerable"` → Poverty, `"professional"` → Middle Class to `_normalize_socioeconomic`.

### 2.6 `parental_structure` — 12 Unknown

| Raw LLM value | Count | Suggested mapping |
|---|---|---|
| `Single biological parent`, `Single-mother household`, `Single father family` | 3 | Single Parent (need to add `"single biological"`, `"-mother household"`) |
| `Biological parent and step-parent`, `Biological parent and step-parent(s)` | 2 | Nuclear Family (current code matches `stepparent` but not the hyphenated form) |
| `Two-parent household`, `Two-parent, biological`, `Biological two-parent household` | 3 | Nuclear Family (need `"two-parent"`) |
| `Two mothers (same-sex parents)` | 1 | Nuclear Family |
| `Other relative(s)`, `Grandparents or other relatives` | 2 | Single Parent (closest schema label for "raised by relatives") |
| `Residential care` | 1 | Single Parent (closest schema label for institutional care) |

**Fix:** extend `_normalize_parental_structure` keyword list with `"two-parent", "step-parent", "single biological", "single-mother", "single-father", "same-sex", "relative", "residential", "grandparent"`.

### 2.7 `industry_sector` — 30 Unknown (largest after birth_location)

The flat extractor's industry keyword list is heavily Swedish-biased and misses many English NACE-style outputs:

| Raw LLM value | Count | Suggested mapping |
|---|---|---|
| `Manufacturing`, `Manufacturing/Industry (specialized consulting)`, `Tillverkningsindustri` | 4 | Manufacturing & Industry (add `"manufacturing"`) |
| `Transportation and Storage`, `Transportation and storage` | 3 | Retail & Service (add `"transportation"`, `"transport"`) |
| `Engineering Services`, `Professional, Scientific, and Technical Activities` (×3 variants) | 5 | IT & Technology (add `"engineering"`, `"professional, scientific"`) |
| `Legal Services`, `Juridik, ekonomi och konsulttjänster`, `Verksamhet inom juridik...`, `Företagstjänster`, `Business and Management Consulting` | 6 | IT & Technology (per `category_mappings.json`: financial/business services → IT & Technology) |
| `Wholesale and retail trade`, `Handel (detalj- och partihandel)`, `Handel (Retail)`, `Retail and Wholesale Trade...` | 4 | Retail & Service (add `"wholesale"`, `"trade"`, `"handel"`) |
| `Construction`, `Energy and Utilities`, `Utilities (Energy, Water, Waste Management)` | 3 | Manufacturing & Industry (per mappings: construction folded here) |
| `Library and Information Services` | 1 | Education (libraries grouped with education) |
| `Public Administration and Defence`, `Public Administration and Defense`, `Public Administration and Defence; Compulsory Social Security` | 3 | Public Administration (add `"public administration"`) |
| `Vård och omsorg`, `Vård och omsorg (Healthcare and Social Work)`, `Healthcare & Social Care`, `Socialtjänst`, `Healthcare and Life Sciences Consulting`, `Healthcare & Wellness (Private Practice)` | 6 | Healthcare & Social (add `"vård"`, `"social"`, `"omsorg"` as already there + better English coverage) |
| `Forskning och utveckling (Research and Development)`, `Utbildning (Education)` | 2 | Education |
| `Marknadsföring, PR och kommunikation`, `Media and Communication`, `Arts, Entertainment, and Recreation`, `Design (Graphic, Web, UI/UX, Product)` | 4 | Other (per mappings: personal/cultural services) |
| `Biotechnology and Pharmaceuticals` | 1 | Manufacturing & Industry |

**Recommended:** rewrite the `industry_sector` block in `_extract_flat` (lines ~1204-1228) using the canonical NACE-aligned keyword set from `category_mappings.json#industry_sector.scb_label_mappings`. Roughly 30 personas would shift from Unknown into proper buckets.

### 2.8 `ethnicity` — 5 Unknown

These come from `ethnicity_broad_global_approx` LLM outputs that don't hit the keywords. Likely values like `Mixed European-Asian`, `Other`, `Prefer not to say`. The fallback derivation from `birth_location` only works if `birth_location` itself isn't Unknown — which it often is (39 Unknown). Fixing birth_location upstream resolves most of these.

### 2.9 `employment_type` — 0 pipeline Unknown, but 3 unmapped in report

| Raw LLM value | Pipeline result | Why unmapped in B vs A |
|---|---|---|
| `Permanent` (4) | passes through unchanged → `"Permanent"` | SCB has only `Permanent Full-time`/`Permanent Part-time` (with hours suffix) |
| `Permanent contract` (2) | passes through → `"Permanent contract"` | same |
| `Project-based employment` (1) | passes through → `"Project-based employment"` | SCB has no such bucket |

**Fix:** in `_extract_flat`'s employment_type block (lines ~1231-1251), if `permanent` matches but neither `full`/`heltid` nor `part`/`deltid` is present, **default to `Permanent Full-time`** (the SCB modal value, ~74% of permanent contracts). For `project-based`/`Tidsbegränsad`/`Visstid` without hours, default to `Temporary Full-time`. This is the documented SCB convention — full-time is the default unless part-time is specified.

### 2.10 `income_source` — 0 pipeline Unknown, 1 unmapped in report

`Business/self-employment` (10 personas) is in the schema's `output_categories` (`category_mappings.json:466`) but **never appears in SCB pop_a**, because the SCB `scb_label_mappings` folds `"wage and business income"` → `"Employment income"` (income code 300 mixes wages + business). 

**Two options:**
- (A) Drop `Business/self-employment` from the pipeline schema and treat self-employment as `Employment income`. Lossy but matches SCB exactly.
- (B) Add `"business and self-employment income": "Business/self-employment"` to `scb_label_mappings`, then split the SCB code 300 query by employment status (employed → Employment income; self-employed → Business/self-employment).

Option (A) is the lower-risk change since SCB has no clean way to separate the two from the existing income table.

### 2.11 `birth_country_detail` — 9 unmapped, mostly statistical sparsity

| Raw LLM value | Class | Notes |
|---|---|---|
| `Syria`, `Bosnia` | mapping mismatch | Pipeline produces short name; SCB pop_a contains `Syrian Arab Republic`, `Bosnia and Herzegovina` — never matched. **Fix:** add label-keyed entries to `birth_country_detail.scb_label_mappings` (currently only ISO codes). |
| `Serbia`, `Kosovo`, `Yemen`, `Lebanon`, `Croatia`, `Palestine`, `Chile` | acceptable_unmappable | Not in `BIRTH_COUNTRY_DETAIL_LABELS` Top-8. Should collapse to `"Other"` per schema, but the extractor passes them through verbatim. **Fix:** in `_extract_flat`, if the raw country isn't in `BIRTH_COUNTRY_DETAIL_LABELS`, return `"Other"`. |

### 2.12 `region` — 1 Unknown (one persona has empty value)

Single empty string from the LLM. Negligible. Optionally add a fallback to derive from `birth_location` if both are populated.

---

## 3. Prioritised fix list

Ranked by personas-rescued-per-line-changed.

### P0 — Mechanical normalizer extensions (high impact, low risk)
1. **`industry_sector` Swedish/English keyword expansion** in `_extract_flat` — rescues ~30 personas. Use NACE labels from `category_mappings.json` as authoritative source.
2. **`birth_location` Swedish-county recognition** in `_birth_location_from_flat` — strip `" län"`, accept any value found in `REGION_LABELS` or `_CITY_TO_COUNTY` as `"Sweden"`. Rescues ~30 personas.
3. **`current_environment_type` "small town" → Suburban** — rescues 23 personas with one keyword addition.
4. **`employment_type` default-to-full-time** when only attachment is specified — eliminates 3 unmapped categories (`Permanent`, `Permanent contract`, `Project-based employment`).
5. **`employment_status` Swedish leave keywords** (parental, sick, military) → Employed; `arbetssök` → Unemployed — rescues 12 personas.
6. **`parental_structure` extended keyword set** (two-parent, step-parent hyphenated, single biological, residential, relatives) — rescues 12 personas.

### P1 — Schema constraint at the prompt layer (large semantic improvement, requires re-run)
7. **Add explicit enum to `birth_location` prompt** in `simulation_config_004_swedish_generative.json`. The current free-text description produces geography instead of immigration-status categories. Constraining to the 4 schema values eliminates the entire class of drift.
8. **Add explicit enum to `employment_status` prompt** — drives the LLM to pick from `["Employed", "Unemployed", "Student", "Retired"]` instead of inventing categories like "Parental leave" or "Long-term sick leave/Disability". Reduces noise even after extending normalizers.
9. **Add explicit enum to `industry_sector`, `employment_type`, `socioeconomic_class`, `parental_structure`** for the same reason. Trade-off: reduces prose diversity but these fields are categorical anyway.

### P2 — SCB-side coverage gaps (root cause of coherence failure)
10. **Extend SCB AKU fetch to include Retired/Student rows** (`ArbetsmarknadsstStatus` codes 4-7). This is the **single biggest contributor to the 63% coherence score** — 19 of the 37 flagged personas are `Retired` paired with age groups where pop_a has zero retirees by construction. Without this fix, no amount of pipeline-side cleanup can lift coherence above ~80%.
11. **Add label-keyed entries to `birth_country_detail.scb_label_mappings`** to handle SCB returning country names instead of ISO codes (`"Syrian Arab Republic"` → `"Syria"`, etc.).
12. **Decide: drop `Business/self-employment` from pipeline schema** OR split SCB income code 300 by employment status. Option (A) recommended — simpler and lossless against current SCB tables.

### P3 — Minor / acceptable
13. `education_level`: add `"secondary"`, `"doktor"`, `"licentiat"` keywords (3 personas).
14. `socioeconomic_class`: add `"vulnerable"`, `"professional"` (2 personas).
15. `birth_country_detail`: collapse non-Top-8 to `"Other"` in extractor (handles long tail).
16. `region`: empty-string fallback (1 persona).

---

## 4. Expected impact on metrics

If P0 + P1 + P2 are all applied:
- **Marginal `unmapped` lists**: shrink from ~22 distinct labels to ≤3 (statistical sparsity in `birth_country_detail` only).
- **`employment_status` joint coherence (age × employment)**: should rise dramatically once SCB pop_a contains `Retired`/`Student`. Estimated coherence jump from 63% to ~85-90%.
- **`industry_sector` TV distance**: 0.46 → likely ~0.20 once 30 personas reclassify.
- **`birth_location` TV distance**: 0.42 → likely ~0.15 once Swedish-county strings map to `Sweden`.

If only P0 is applied (no schema/SCB changes):
- Reduces total Unknown count from ~127 to ~10 across all fields.
- Coherence score barely moves (still bounded by SCB pop_a not having Retired/Student).
- **Conclusion:** P2 fix #10 is mandatory for meaningful coherence improvement; P0 fixes are mandatory for clean marginal comparisons.
