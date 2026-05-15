# Plan: SCB comparison — keep detailed categories, fix birth_location bug, drop injected fields

**Date:** 2026-05-11
**Author:** Basil
**Status:** In Progress
**Started:** 2026-05-11
**Base Branch:** `feature/socioeconomic-class-from-real-income-brackets`
**Branch:** `feature/scb-comparison-detailed-categories`

**Source audit:** [`docs/scb02_comparison_category_mapping_2026-05-11.md`](../../../scb02_comparison_category_mapping_2026-05-11.md) (companion: [`docs/audit_scb_comparison_api_rooting_2026-05-11.md`](../../../audit_scb_comparison_api_rooting_2026-05-11.md))

---

## Overview

Stop the SCB-comparison normalizer from aggregating away signal on four fields (`education_level`, `household_size`, `income_source`, `birth_country_detail`), fix the `birth_location` bug where the schema declares a `Nordic Country` bucket the SCB query never fetches, and remove the two purely-injected fields (`ethnicity`, `current_environment_type`) whose information is fully contained in their source field. Update the pipeline-side identity generator schemas in the same change so comparisons stay meaningful.

## Problem Statement

The audit document inventories three classes of issue in `normalize_scb_to_schema()` (`scripts/compare_populations.py:95-265`) and the comparison schema (`config/assets/scb_reference/category_mappings.json`):

1. **Lossy aggregation on four fields.** SCB returns 8 raw education levels, 7 household-size cells, 6 income sources, and 21 country-of-birth labels (20 foreign codes + Sweden). The current normalizer collapses each to ~4 schema buckets — destroying signal that scb02 carries verbatim and obscuring genuine pipeline-vs-population differences in those distributions.
2. **Unreachable schema bucket on `birth_location`.** The schema declares `Nordic Country`, but `fetch_service.py:80` queries only `["FSV", "FEU", "FUEU"]`. The SCB API never returns a Nordic row, so every comparison reports 0/non-zero divergence on that bucket.
3. **Two injected fields with no SCB source.** `ethnicity` is a hand-curated map applied to `birth_location` (`compare_populations.py:180`); `current_environment_type` is a hand-curated map applied to `region` (`compare_populations.py:185`). Both are restatements of their source field. The audit's companion document flags both as Severity-1 violations of "no hardcoded statistical data".

Without a fix, comparisons of pipeline-generated populations against the scb02 reference under-report the true divergence on the four detailed fields and over-report it on `birth_location`.

## Goals

### In Scope
1. Replace the four aggregation maps in `category_mappings.json` with 1-to-1 cleaned/short label rewrites that preserve the raw partition (8 / 7 / 6 / 21 buckets).
2. Drop the `ethnicity` and `current_environment_type` outputs from `normalize_scb_to_schema()` and from the schema config.
3. Widen the SCB `fetch_birth_location()` query to include the Nordic-region Fodelseland code (verified live before editing) so future SCB populations carry the fourth bucket.
4. Update both pipeline identity-generator configs so the LLM emits the new detailed values: `simulation_config_004_swedish_generative.json` (used by seeds 010-013) and `simulation_config_003_swedish_flat.json` (used by seed009).
5. Drop `ethnicity_broad_global_approx` and `current_environment_type` from the pipeline strategy and both identity configs.

### Out of Scope
- **SSB parity.** The Norwegian SSB pipeline shares the same comparison schema. After this change, `config/assets/ssb_reference/category_mappings.json`, `anxiety_synthetic/ssb_population/constants.py`, and `ssb_population/fetch_service.py` will be inconsistent on the four detailed fields, and the SSB sampler will still emit `ethnicity` and a region-derived `current_environment_type` that are no longer compared. Track as a separate follow-up plan.
- **scb02 dataset regeneration.** scb02 is frozen and will never carry `Nordic Country` records. Future SCB populations (scb03+) will. A consistent baseline requires regenerating scb02; that is a separate task.
- **Probability calibration** for the new value lists in `simulation_config_003_swedish_flat.json` — initial values from the scb02 audit distributions are sufficient for this change; live-marginal calibration is follow-up work.
- LLM prompt rewording in either identity config beyond enumerating the new candidate value sets.

## Success Criteria

- [ ] `scripts/compare_populations.py` invoked on any two raw-SCB populations emits `marginals` rows for `education_level` (8 categories), `household_size` (7), `income_source` (6), `birth_country_detail` (21).
- [ ] The same comparison report does **not** contain `ethnicity` or `current_environment_type` rows.
- [ ] A freshly-generated SCB population (`scripts/generate_scb_population.py --n 200 --seed 99`) produces a non-zero `Nordic Country` count in its `birth_location` distribution.
- [ ] A regenerated identity sample from seed013 (`config/seed_manifests/synthetic_pipeline_config_seed013.yaml`) produces `identity.json` files whose `education_level`, `household_size`, `income_source`, `birth_country_detail` values are drawn from the new 8/7/6/21 cleaned-label sets.
- [ ] The same identity files do **not** contain `ethnicity_broad_global_approx` or `current_environment_type` keys.
- [ ] `scripts/compare_pipeline_to_scb.py --seed-root <regenerated seed013> --reference data/scb_api/scb_population_pop-10000_02.json` runs end-to-end and the JSON report's `marginals` for the four detailed fields show counts on both sides (modulo the Sweden override on `birth_country_detail`).

---

## Technical Design

### Approach

Treat the comparison schema as the source of truth for category space, and edit it once: in `category_mappings.json`. The normalizer in `compare_populations.py` already pulls from this config for the four detailed fields, so changing the JSON from aggregation maps to 1-to-1 rewrites preserves the signal without code changes for those fields. Only two lines need to be deleted from the normalizer (the `ethnicity` and `current_environment_type` writes). The SCB query widening is a one-element addition to a `values` list — `parse_birth_location()` already labels rows from the API response and the `region_label_mappings` block already maps the Nordic raw labels.

The pipeline-side update is two configs (`simulation_config_003_swedish_flat.json` and `simulation_config_004_swedish_generative.json`) plus the comparison strategy (`compared_only_generate_evaluate_random_pick.json`). Removing the two injected fields from the pipeline avoids generating data that nothing compares against.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Keep current aggregation, raw labels verbatim | No new mapping table to maintain | Long verbose labels (`"post-secondary education 3 years or more (ISCED97 5A)"`) clutter charts/reports | Rejected |
| Cleaned/short 1-to-1 labels (e.g. `Post-Secondary 3+ yrs (ISCED 5A)`) | Same partition, readable, only one new mapping table per field | Adds a small mapping layer to keep in sync with SCB API label changes | **Chosen** |
| Drop `Nordic Country` from `birth_location` schema (collapse to 3 buckets) | One config edit, no SCB query change | Loses the Nordic specificity going forward; schema and audit doc would need to lose a category | Rejected |
| Widen SCB `fetch_birth_location` to add Nordic code (`FN` suspected) | Schema and query become consistent; future SCB pops carry Nordic data | Requires verifying the actual Fodelseland value code via SCB metadata before editing; scb02 stays without Nordic until regenerated | **Chosen** |
| SCB-side normalizer only; defer pipeline-side schema realignment | Smaller diff, single concern | Pipeline still emits 4-bucket aggregations while SCB emits 8/7/6/21 — comparisons would show pure category-space divergence on the four detailed fields | Rejected |
| Update both sides + keep the injected fields | Less to delete | The two injected fields are pure restatements of birth_location/region — keeping them is duplication | Rejected |
| Update both sides + drop the two injected fields from pipeline too | Removes useless duplication; saves LLM calls in the strategy | Pipeline outputs lose `ethnicity_broad_global_approx` and `current_environment_type` keys (acceptable — they were schema-mismatched anyway) | **Chosen** |

### Architecture Changes

No new modules. Edits cluster in three areas:

```
scripts/
└── compare_populations.py            # remove 2 normalizer lines + 2 loaders

anxiety_synthetic/scb_population/
└── fetch_service.py                  # widen birth_location values list (1 element)

config/assets/
├── scb_reference/category_mappings.json                       # rewrite 4 maps; delete 2 blocks
└── identity/configurable/
    ├── simulation_config_004_swedish_generative.json          # rewrite 4 descriptions; delete 2 blocks
    ├── simulation_config_003_swedish_flat.json                # rewrite 4 value lists; delete 2 entries
    └── strategies/compared_only_generate_evaluate_random_pick.json  # delete 2 entries
```

### Proposed cleaned labels

Final wording can be tuned in implementation as long as the partition is preserved:

- **education_level (8):** `Pre-Secondary < 9 yrs (ISCED 1)`, `Pre-Secondary 9-10 yrs (ISCED 2)`, `Upper Secondary ≤ 2 yrs (ISCED 3C)`, `Upper Secondary 3 yrs (ISCED 3A)`, `Post-Secondary < 3 yrs (ISCED 4+5B)`, `Post-Secondary 3+ yrs (ISCED 5A)`, `Post-Graduate (ISCED 6)`, `Unknown / Not reported`
- **household_size (7):** `1 person`, `2 persons`, `3 persons`, `4 persons`, `5 persons`, `6 persons`, `7+ persons`
- **income_source (6):** `Wage / Business`, `Capital`, `Pension`, `Insurance / Allowance`, `Social Assistance`, `Sickness / Activity Compensation`
- **birth_country_detail (21):** `Sweden`, `Syria`, `Iraq`, `Finland`, `Poland`, `Iran`, `Afghanistan`, `Somalia`, `Yugoslavia`, `Bosnia and Herzegovina`, `Turkey`, `India`, `Germany`, `Eritrea`, `Thailand`, `China`, `Romania`, `Norway`, `Denmark`, `Ukraine`, `United Kingdom`. (Per memory `feedback_birth_country_aggregation.md`, `Yugoslavia` stays as its own label — it is not rolled into Serbia/Kosovo/Croatia.)

---

## Implementation Plan

### Phase 1: SCB metadata verification + mapping config rewrite

**Goal:** Confirm the Nordic Fodelseland value code, then update `category_mappings.json` so the 4 detailed-field maps preserve the raw partition and the two injected blocks are removed.

- [x] Verify the Nordic Fodelseland code by fetching SCB PxWeb metadata for `BE/BE0101/BE0101E/FolkmFodlandHVD` via `SCBPxWebClient.fetch_table_metadata()` (see `anxiety_synthetic/utils/scb_client.py`). Expected code: `FN` ("Norden utom Sverige"). **Actual finding:** The table `FolkmFodlandHVD` only exposes 5 codes (`TOT`, `FSV`, `FEU`, `FUEU`, `OKANT`) — no Nordic-specific code exists; the `FN` code does not appear in this or any other available SCB birth-location table. Phase 2 will document this constraint: the Nordic bucket cannot be widened from this table's grouped API.
- [x] In `config/assets/scb_reference/category_mappings.json`:
  - [x] Replace `education.sun2020_level_mappings` with 16-entry map (8 Swedish + 8 English raw labels → 8 cleaned labels). Added `output_categories` array of 8 new labels. Kept `education.mappings` scb_codes intact (still referenced by legacy code paths).
  - [x] Replace `household_size.scb_label_mappings` with 7 raw → 7 cleaned rewrites; updated `output_categories` to 7-element list.
  - [x] Replace `income_source.scb_label_mappings` with 6 raw → 6 cleaned rewrites; updated `output_categories`.
  - [x] Replace `birth_country_detail.scb_label_mappings` with 40-entry map (20 ISO codes + 20 full English label forms from SCB API) → 20 country names + `Sweden` = 21 total. Updated `output_categories`. Sweden override in `compare_populations.py:245-246` unchanged.
  - [x] Delete the entire `ethnicity` block.
  - [x] Delete the `region.county_env_type` sub-block. `region.scb_label_mappings` kept.

**Files Modified:**
- `config/assets/scb_reference/category_mappings.json` — 4 map rewrites + 2 block deletions

**Dependencies:** None

### Phase 2: Normalizer cleanup + birth_location query widening

**Goal:** Drop the two injected-field writes from the SCB normalizer and widen the SCB query so the Nordic bucket becomes reachable.

- [x] In `scripts/compare_populations.py::normalize_scb_to_schema()`:
  - Delete the loader for `ethnicity_from_birth` (line 104).
  - Delete the loader for `county_env_map` (line 106).
  - Delete the line `rec["ethnicity"] = ethnicity_from_birth.get(...)` (line 180).
  - Delete the line `rec["current_environment_type"] = county_env_map.get(...)` (line 185).
  - Also removed `"ethnicity"` and `"current_environment_type"` from `DEMOGRAPHIC_ATTRIBUTES` so no marginal row is emitted for those fields.
  - Verified no other call sites reference `ethnicity_from_birth` or `county_env_map`. The four detailed-field lookups (`edu_map`, `hh_size_map`, `income_map`, `bc_detail_map`) needed no code change — the Phase-1 JSON edits change their semantics from aggregation to 1-to-1.
- [x] `fetch_birth_location()` query widening — **BLOCKED: Nordic code `FN` confirmed not to exist in SCB table `BE/BE0101/BE0101E/FolkmFodlandHVD`.** The table only exposes codes `TOT`, `FSV`, `FEU`, `FUEU`, `OKANT`. No query change was made; the values list remains `["FSV", "FEU", "FUEU"]`. The `Nordic Country` bucket in the `birth_location` schema will remain unreachable from live SCB data at this grouped API level (pre-existing limitation, documented in the Risks section).

**Files Modified:**
- `scripts/compare_populations.py` — 4 line deletions in `normalize_scb_to_schema`
- `anxiety_synthetic/scb_population/fetch_service.py` — 1 line edit in `fetch_birth_location`

**Dependencies:** Phase 1

### Phase 3: Pipeline-side identity generator alignment

**Goal:** Make the LLM emit the new detailed value sets and stop generating the two dropped fields.

- [x] `config/assets/identity/configurable/simulation_config_004_swedish_generative.json` (used by seeds 010-013):
  - Rewrite the `description` field for `education_level`, `household_size`, `income_source`, `birth_country_detail` to enumerate the new candidate values explicitly (e.g. append `"Choose exactly one of the following values: …"`). The LLM needs the candidate set in the prompt — without enumeration, the generative config will produce variant strings.
  - Delete the `ethnicity_broad_global_approx` block (lines 29-32).
  - Delete the `current_environment_type` block (lines 33-35).
- [x] `config/assets/identity/configurable/simulation_config_003_swedish_flat.json` (used only by seed009):
  - Replace the 4-element lists for `education_level`, `household_size`, `income_source`, `birth_country_detail` with the new detailed-value lists. Initialise probabilities from the scb02 raw distributions in the audit doc; exact tuning is out of scope.
  - Delete the `ethnicity_broad_global_approx` and `current_environment_type` entries.
- [x] `config/assets/identity/configurable/strategies/compared_only_generate_evaluate_random_pick.json`:
  - Delete the `current_environment_type` entry (line 18).
  - Delete the `ethnicity_broad_global_approx` entry (line 19).
  - Keep `birth_country_detail` with `depends_on: ["birth_location"]` — the LLM still needs that context to choose Sweden vs a foreign country.

**Files Modified:**
- `config/assets/identity/configurable/simulation_config_004_swedish_generative.json` — 4 description rewrites + 2 block deletions
- `config/assets/identity/configurable/simulation_config_003_swedish_flat.json` — 4 list rewrites + 2 entry deletions
- `config/assets/identity/configurable/strategies/compared_only_generate_evaluate_random_pick.json` — 2 entry deletions

**Dependencies:** Phase 1 (the candidate values come from the same source)

---

## Testing Plan

### Manual verification

- [ ] **SCB metadata check** (Phase 1, before any edit): `SCBPxWebClient.fetch_table_metadata("BE/BE0101/BE0101E/FolkmFodlandHVD")` and read the `Fodelseland` variable's value list. Confirm the code for "Norden utom Sverige".
- [ ] **Fresh small SCB pop** confirms Nordic bucket is populated:
  ```
  python scripts/generate_scb_population.py --n 200 --seed 99 --output /tmp/scb_test.json
  python scripts/analyze_scb_population.py /tmp/scb_test.json
  ```
  Expect `birth_location` distribution to include `Nordic Country` with non-zero count.
- [ ] **Regenerate seed013** (or a small slice via `target_ids: start=0 stop=20`):
  ```
  python scripts/generate_persona_and_report.py
  ```
  Spot-check 2-3 `persona_*/identity.json` files: `education_level`, `household_size`, `income_source`, `birth_country_detail` carry one of the new clean labels; `ethnicity_broad_global_approx` and `current_environment_type` are absent.
- [ ] **Run the pipeline-vs-scb02 comparison**:
  ```
  python scripts/compare_pipeline_to_scb.py \
    --seed-root <db_root>/seed_013_compared-only-identity \
    --reference data/scb_api/scb_population_pop-10000_02.json
  ```
  In the JSON/CSV report:
  - `marginals` contains `education_level` with 8 categories, `household_size` with 7, `income_source` with 6, `birth_country_detail` with 21 (modulo `Sweden` override and zero-count tail buckets).
  - `marginals` does **not** contain `ethnicity` or `current_environment_type`.
  - `birth_location` row matches the existing 3-bucket reality on scb02 (frozen) but shows 4 categories on the freshly-generated `/tmp/scb_test.json` from the previous step.

### Edge cases

- [ ] Re-running `compare_populations.py` against pairs of pre-existing analysed SCB populations (e.g. `scb_population_pop-10000_02.json` vs another) confirms the 4 detailed fields now expose the new categories rather than the old 4-bucket aggregations — and the comparison still runs end-to-end without crashing on the missing `ethnicity` / `current_environment_type` keys.
- [ ] A pipeline persona with `birth_location == "Native (Born in Sweden)"` (the pipeline label, see `compare_pipeline_to_scb.py` extractor) still gets `birth_country_detail = "Sweden"` after the Sweden override at `compare_populations.py:245-246` — confirm by spot check.
- [ ] A persona whose pipeline `birth_country_detail` is one of the 14 previously-aggregated codes (e.g. `Norway`, `Denmark`, `Ukraine`) now shows up under its own label rather than under `Other`.

---

## Documentation Plan

- [ ] Update the `### SCB Population` section of `CLAUDE.md` to note that the comparison schema preserves raw category granularity for `education_level` (8), `household_size` (7), `income_source` (6), `birth_country_detail` (21), and that `ethnicity` and `current_environment_type` are no longer derived/compared.
- [ ] No new user-guide doc — the change is internal to the comparison pipeline.
- [ ] When the audit document `docs/scb02_comparison_category_mapping_2026-05-11.md` is next updated (e.g. against scb03), regenerate the per-field tables to reflect the new partitions; until then, the existing audit doc remains historically accurate for scb02 under the old normalizer.

---

## Rollback Plan

The change is self-contained to one normalizer function, one fetch query, three identity-config files, and one strategy file. Rollback is a single `git revert` of the merge commit.

1. **Before-merge rollback:** abandon the feature branch; the base branch is unaffected.
2. **Post-merge rollback:** `git revert` the merge commit. The deleted `ethnicity` / `current_environment_type` writes and aggregation maps are recoverable from history. scb02 reference file is untouched (no regeneration in this plan).
3. **Data considerations:** No DB migrations. Existing pipeline persona JSONs from earlier seeds remain valid — they retain their old field values; the comparison normalizer simply ignores the absent fields. Newly-generated personas use the new detailed labels.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Confirmed Nordic Fodelseland code differs from suspected `FN` | Med | Low | Phase 1 verification step queries the actual SCB metadata and uses whatever code is reported |
| LLM (in `simulation_config_004_swedish_generative.json`) ignores the enumerated candidate set and produces label variants | Med | Med | The strategy `generate_evaluate_random_pick` already uses the LLM's enumerated candidates as the sample space; if drift appears, tighten the description with `Choose exactly one of …` and add a normalising spot-check |
| `scripts/compare_pipeline_to_scb.py` extractor (`extract_individual` in `extract_population_from_pipeline.py`) hard-codes the old 4-bucket labels and silently drops the new detailed values | Med | High | Read `extract_population_from_pipeline.py` during Phase 3 implementation; if it filters by allowed value list, update that list to match the new partitions |
| Existing comparison reports pre-dating this change reference `ethnicity` / `current_environment_type` rows that no longer exist | Low | Low | Audit doc was generated before the change and is historically accurate; future comparisons regenerate with the new schema |
| scb02 (frozen) stays without Nordic Country records, so pipeline-vs-scb02 still shows zero on that bucket on the SCB side | High | Low | Documented; resolved only by regenerating scb02 (out of scope here) |
| SSB pipeline becomes inconsistent with the SCB comparison schema | High | Med | Documented as out-of-scope follow-up plan; the inconsistency is contained to the SSB code path and SSB-vs-SCB comparisons |

---

## References

- Source audit: `docs/scb02_comparison_category_mapping_2026-05-11.md`
- Companion audit: `docs/audit_scb_comparison_api_rooting_2026-05-11.md`
- Internal plan scratch: `C:\Users\basil\.claude\plans\analyse-docs-scb02-comparison-category-m-harmonic-wolf.md`
- Related plan (this branch's parent): `docs/development/plans/active/socioeconomic-class-from-real-income-brackets.md`
- Related future plan: SSB parity for the same changes — to be opened in `pending/` after this lands
- Related future plan: scb03 regeneration with widened `birth_location` query — to be opened separately
