# Fix Identity-vs-SCB Comparison Divergences

## Context

On 2026-05-18 we generated 100 LLM identities using `simulation_config_004_swedish_generative.json` with strategy `compared_only_generate_evaluate_random_pick.json` (gemini-2.5-flash, 8 parallel workers, 96 succeeded / 4 failed) and compared them against the SCB 10k reference population.

Seven of 16 compared attributes show statistically significant divergence (chi-squared p < 0.05). The root causes fall into three categories: **missing normalizer mappings**, **LLM vocabulary drift**, and **distributional bias**.

Comparison artifacts:
- `data/analysis/config_004_vs_scb10k/comparison_report.json`
- `data/analysis/config_004_vs_scb10k/comparison_report.csv`
- `data/analysis/config_004_vs_scb10k/comparison_report/` (charts + radar)

---

## Divergence 1: civil_status (p = 1.86e-17, TV = 0.310)

**Problem:** The extractor normalizer is missing several Swedish-language civil status values that the LLM generates.

**Unmapped values observed:** `Änklig`, `Registrerad partner`, `Änkeman`, `Ensamstående`

**Expected vocabulary** (from `config/assets/scb_reference/category_mappings.json` lines 429-458):
- `Single/Never Married`, `Married`, `Widowed`, `Divorced`

**Fix location:** `src/population_synth/comparison/extractor.py` -- the flat-identity extraction path for civil_status. Also update `pipeline_label_mappings` in `category_mappings.json`.

**Required mappings to add:**
| LLM value | Should map to |
|---|---|
| `Änklig` | `Widowed` |
| `Änkeman` | `Widowed` |
| `Registrerad partner` | `Married` |
| `Ensamstående` | `Single/Never Married` |

---

## Divergence 2: socioeconomic_class (p = 5.54e-10, TV = 0.353)

**Problem (dual):**
1. **Normalizer gap:** The LLM generates Swedish occupational-class labels instead of the 4-bucket income-relative scheme (Poverty / Working Class / Middle Class / Wealthy). 8 of 96 identities (8.3%) fall to "Non-standard label".
2. **Distributional bias:** Even mapped values diverge from SCB — the LLM likely over-represents middle class.

**Unmapped values observed:** `Mellanstora tjänstemän`, `Högre tjänstemän`, `Mellan-tjänstemän`, `Mellan tjänstemän`, `Kvalificerad tjänsteman`, `Nedre mellanklass`, `Låginkomsttagare`

**Expected vocabulary:** `Poverty`, `Working Class`, `Middle Class`, `Wealthy`

**Fix location:** `src/population_synth/comparison/extractor.py` -- socioeconomic_class normalizer.

**Required mappings to add:**
| LLM value | Should map to |
|---|---|
| `Högre tjänstemän` | `Wealthy` |
| `Mellanstora tjänstemän` / `Mellan-tjänstemän` / `Mellan tjänstemän` / `Kvalificerad tjänsteman` | `Middle Class` |
| `Nedre mellanklass` | `Working Class` |
| `Låginkomsttagare` | `Poverty` |

**Deeper issue:** The LLM is generating the Swedish SEI occupational classification scheme instead of the income-relative 4-bucket scheme. Consider whether the simulation config description for `socioeconomic_class` should be more explicit about the expected categories.

---

## Divergence 3: employment_status (p = 0.919 but TV = 0.281)

**Problem:** The chi-squared p-value is misleadingly high because 3 entire categories (`Retired`, `Student`, `Non-standard label`) are unmapped -- they're present in the LLM output but get bucketed as unknown, making the test unreliable.

**Unmapped values observed:** `Pensionär` -> `Retired`, `Studerande`/`Student` -> `Student`, plus 1 non-standard label (`Arbetstränade`)

**Why this matters:** `Retired` and `Student` ARE valid SCB categories (see `category_mappings.json` lines 99, 103, 148-158). The extractor DOES handle these for pipeline format but may not be mapping them correctly for flat-identity format.

**Fix location:** `src/population_synth/comparison/extractor.py` -- verify the flat-identity employment_status extraction path handles `Retired` and `Student` as valid output categories, not as unmapped.

**Additional mapping:** `Arbetstränade` / `Arbetsträning` -> could map to `Unemployed` or be flagged explicitly.

---

## Divergence 4: employment_type (p = 7.22e-11, TV = 0.331)

**Problem:** The LLM generates a wide variety of Swedish-language employment type values that aren't in the normalizer. 9 unmapped categories observed.

**Unmapped values observed:** `Aktiebolag (ägare)`, `Ägare och anställd i eget aktiebolag`, `Anställning för viss tid då arbetstagaren uppnått pensionsåldern`, `Vikarie`, `Volontärarbete`, `Anställd i eget aktiebolag`, `Egenanställd`, `Aktiebolag (AB)`, `Arbetsträning`

**Expected vocabulary** (from `category_mappings.json` lines 524+):
- `Permanent Full-time`, `Permanent Part-time`, `Temporary Full-time`, `Temporary Part-time`, `Self-Employed`, `Not Applicable`

**Required mappings to add:**
| LLM value | Should map to |
|---|---|
| `Aktiebolag (ägare)` / `Aktiebolag (AB)` / `Anställd i eget aktiebolag` / `Ägare och anställd i eget aktiebolag` / `Egenanställd` | `Self-Employed` |
| `Vikarie` | `Temporary Full-time` |
| `Volontärarbete` / `Arbetsträning` | `Not Applicable` |
| `Anställning för viss tid då arbetstagaren uppnått pensionsåldern` | `Temporary Full-time` |

**Fix location:** `src/population_synth/comparison/extractor.py` -- `_SELF` and `_TEMP_MISC` keyword lists (lines 1405-1412) and the `_normalize_employment_type` fallback.

---

## Divergence 5: parental_structure (p = 7.01e-7, TV = 0.270)

**Problem:** The LLM generates diverse free-text descriptions of parental structure that don't match the normalizer's expected labels. 8 of 96 (8.3%) unmapped.

**Unmapped values observed:** `Shared residency (separated parents)`, `Two heterosexual parents`, `Shared custody (parents living separately)`, `Shared custody (parents live separately, child lives in two homes)`, `Separated parents (shared custody)`, `Skilda föräldrar med växelvis boende`, `Shared custody (separated parents)`, `One biological parent`

**Expected vocabulary** (from SCB table 06083):
- `Two parents`, `One parent`, `Other/Shared custody`, `Reconstituted family`

**Required mappings to add:**
| LLM value pattern | Should map to |
|---|---|
| `Shared custody` / `Shared residency` / `Separated parents` / `Skilda föräldrar med växelvis boende` | `Other/Shared custody` |
| `Two heterosexual parents` / `Two biological/adoptive heterosexual parents` | `Two parents` |
| `One biological parent` | `One parent` |

**Fix location:** `src/population_synth/comparison/extractor.py` -- parental_structure normalizer.

---

## Divergence 6: industry_sector (p = 6.33e-45, TV = 0.321)

**Problem:** Distributional bias. The LLM over-represents certain sectors. No unmapped categories, so this is purely a distributional issue -- the LLM's probabilistic weighting of industry sectors doesn't match real SCB distributions.

**Max single-field difference:** 0.294 (29.4 percentage points on one sector).

**This is NOT a normalizer problem.** This divergence reflects the core limitation of LLM-based generation: without real statistical priors, the model's "common sense" about Swedish industry sector distributions deviates significantly from reality.

**Possible approaches:**
1. Accept as inherent LLM limitation (population realism comes from SCB sampling layer, not LLM)
2. Add constrained candidate lists to the simulation config with real SCB sector labels
3. Investigate whether `generate_evaluate_random_pick` is producing skewed weight distributions for this field

---

## Divergence 7: education_level (p = 8.71e-7, TV = 0.278)

**Problem (dual):**
1. **Normalizer gap:** 2 of 96 identities have non-standard education labels (e.g., `Realskoleexamen`, `Ingen formell utbildning`)
2. **Distributional bias:** Even mapped values diverge (max diff 0.207)

**Required mappings to add:**
| LLM value | Should map to |
|---|---|
| `Realskoleexamen` | `Upper secondary (gymnasie)` or equivalent ISCED level |
| `Ingen formell utbildning` | `Pre-primary / Primary` |

**Fix location:** `src/population_synth/comparison/extractor.py` -- education_level normalizer.

---

## Divergence 8: income_source (p = 8.55e-20, TV = 0.191)

**Problem:** Distributional bias only -- no unmapped categories. The LLM over-represents `Wage / Business` and under-represents transfer income types.

**Same root cause as industry_sector:** LLM probability weights don't match real SCB income source distributions.

---

## Summary: Fix Priority

### Priority 1 -- Normalizer mapping gaps (fixes ~50% of divergence signal)

Expand the extractor normalizer in `src/population_synth/comparison/extractor.py` for:
- `civil_status` -- 4 new Swedish-language mappings
- `socioeconomic_class` -- 7 new Swedish occupational-class mappings
- `employment_type` -- 9 new Swedish-language mappings (mostly self-employment variants)
- `parental_structure` -- 8 new free-text pattern mappings
- `education_level` -- 2 new historical/edge-case mappings
- `employment_status` -- verify flat-identity path handles `Retired`/`Student` correctly; add `Arbetsträning`

### Priority 2 -- Distributional bias (structural, harder)

Fields with no mapping issues but significant distributional divergence:
- `industry_sector` (TV = 0.321)
- `income_source` (TV = 0.191)
- `education_level` distribution (after fixing mappings)
- `socioeconomic_class` distribution (after fixing mappings)

These reflect inherent LLM bias and are expected when comparing LLM-generated personas against real population data. The project's design principle is that population realism comes from the SCB sampling layer, not from LLM prompts -- so these divergences validate the architectural decision to keep the two approaches separate.

### Priority 3 -- housing_tenure (borderline, p = 0.072)

4 of 96 identities have non-standard housing tenure labels. Worth adding mappings but not urgent since p > 0.05.
