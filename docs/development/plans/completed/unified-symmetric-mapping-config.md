# Plan: Unified, symmetric mapping config (retire `_scheme.json` as a filter)

**Date:** 2026-07-01
**Author:** Basil
**Status:** Completed
**Completed:** 2026-07-01 14:49
**Base Branch:** `dev`
**Branch:** `feature/unified-symmetric-mapping-config`

---

## Overview

Replace the comparison pipeline's two disconnected category definitions (the per-attribute
`output_categories`/label-maps and the separate `_scheme.json` filter axis) with **one
symmetric per-attribute definition**: each attribute file declares its unified `values`
once, then a `database` rule block and a `synthetic` rule block, both keyed by unified value
→ `{match: [tokens]}`. A per-country `_index.json` master lists the comparison attributes
and their filenames. Both mappers emit only unified values (or `None`); the comparison axis
simply *is* the unified values, so no filter is needed.

## Problem Statement

Categories live in two places that drift apart. The per-attribute mapping files let the
mappers emit a *looser* label set (`Student`/`Retired` for employment, `Nordic Country` for
birth_location, `Other` for housing_tenure, non-top countries for birth_country_detail),
and `config/mapping/{scb,istat}/_scheme.json` exists **only to filter that drift back out**
of the scored axis (`evaluator.py:112-119` drops/flags anything outside `scheme.categories`).
The reference and synthetic sides use entirely different key vocabularies
(`reference_*` vs `pipeline_*`) and two parallel 5-handler engines. The result is confusing,
asymmetric, and hard to maintain — adding or auditing a category means reconciling several
files by hand.

## Goals

### In Scope
1. Introduce a per-country `_index.json` master (attribute → filename map + `joint_pairs` +
   `coherence_attributes`) and delete `_scheme.json`.
2. Rewrite every `config/mapping/scb/*.json` and `config/mapping/istat/*.json` into the new
   `values` / `database` / `synthetic` shape with an extended match vocabulary.
3. Collapse the two parallel mapper engines into a single shared symmetric resolver.
4. Reconcile both countries' value sets to what the DB actually emits (Sweden drops the
   config-only labels; make Swedish `employment_status` truly binary; fix istat
   `household_size` raw codes → labels).
5. Keep the `ComparisonScheme`/`load_scheme` interface so `evaluator.py`, `charts.py`, and
   the compare scripts are untouched.
6. Update tests and docs.

### Out of Scope
- Norway/SSB (`config/mapping/ssb/`) — not wired into the comparison scheme mechanism.
- A full re-audit of istat value semantics beyond what the current istat `_scheme.json`
  already grounds (its category sets are taken as authoritative `values`).
- Changing the statistical methods in `evaluator.py` (chi-sq/KL/TV/coherence) — only the
  *source* of the category axis changes.
- Regenerating the reference population files (the `EIAKR` fetch change affects only future
  Swedish regenerations; the shipped reference file is already binary).

## Success Criteria

- [x] `config/mapping/{scb,istat}/_scheme.json` deleted; `_index.json` present in both dirs.
- [x] Every per-attribute file uses `values` + `database` + `synthetic`; no `*_handler`,
      `*_label_mappings`, `output_categories`, or `pipeline_keyword_rules` keys remain.
      *(Phase 4 orphan cleanup removed the last 8 dead old-shape files.)*
- [x] One shared resolver (`comparison/mapping_engine.py`) drives both mapper sides; the
      5+5 handler-kind factories are removed.
- [x] Golden equivalence: new reference mapper over
      `data/scb_api/scb_population_pop-10000_02.json` produces distributions identical to the
      old mapper for all 15 attributes **except** the intended drops (no `Retired`/`Student`/
      `Nordic Country`/`Couple without Children`/housing `Other`/beyond-top-21). Same check
      passes for Italy over `data/istat_api/istat_population.json`. *(Verified in Phase 3:
      byte-identical for all non-age attributes both countries.)*
- [ ] `python scripts/analyze/compare_pipeline_to_scb.py` and `compare_pipeline_to_istat.py`
      still emit the JSON report, CSV, all bar charts, and the radar chart, with no
      synthetic-only empty bars. *(Manual verification, not executed in Phase 4 — needs a real
      pipeline run under `output_base`. Mapper/scheme equivalence covered by the golden diffs.)*
- [x] `pytest` green; `ruff check src/` clean. *(119 passed; ruff clean on all touched
      comparison/test files. Pre-existing baseline warnings remain in `gui/` and the
      import-order of `reference_mapper/factory.py` / `synthetic_mapper/loader.py`, which
      Phase 4 did not touch.)*

---

## Technical Design

### Approach

Make the per-attribute file the **single source of truth**, symmetric across the DB and
synthetic sides. A raw value resolves by walking the unified values in declared order and
returning the first whose matcher hits (`equals` exact, `contains` substring, plus richer
matchers for the hard attributes); unmatched → `None`. Because both mappers now emit only
declared `values`, the scored axis equals the `values` and the `_scheme.json` filter is
obsolete. `ComparisonScheme` is repurposed to source its four fields from `_index.json` +
each file's `values`, keeping every downstream consumer unchanged.

Authoritative `values` per attribute come from the *current* `_scheme.json.categories[attr]`
(already DB-grounded for both countries — istat legitimately keeps `Other`/`Extended
Family`/`Couple without Children`; Sweden does not).

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Symmetric `values`/`database`/`synthetic` + shared engine (this plan) | One source of truth; DB & synthetic symmetric; deletes the filter and 10 handler factories | Large one-time config + engine rewrite | **Chosen** |
| Keep `_scheme.json`, just make `output_categories` match it | Smaller change | Preserves the dual-list + two engines; doesn't address asymmetry the user objected to | Rejected |
| Derive scope/joint/coherence from code constants, no master file | No master to maintain | No natural home for attribute→filename map the user asked for; per-country scope needs a branch | Rejected (master file is what the user requested) |
| Bespoke handlers for the complex 5, new format only for simple ones | Avoids inventing matchers | Two file shapes; not uniform | Rejected (user chose "extend the vocabulary") |

### Architecture Changes

**New file shape** — master (`config/mapping/{scb,istat}/_index.json`):

```json
{
  "description": "Master index: comparison attributes -> per-attribute config files.",
  "attributes": {
    "age_group": "age.json",
    "biological_sex": "biological_sex.json",
    "education_level": "education.json",
    "employment_status": "employment.json",
    "birth_location": "birth_location.json",
    "socioeconomic_class": "socioeconomic.json",
    "parental_structure": "parental_structure.json",
    "region": "region.json",
    "civil_status": "civil_status.json",
    "industry_sector": "industry_sector.json",
    "employment_type": "employment_type.json",
    "housing_tenure": "housing_tenure.json",
    "household_size": "household_size.json",
    "income_source": "income_source.json",
    "birth_country_detail": "birth_country_detail.json"
  },
  "joint_pairs": [["age_group","education_level"],["age_group","employment_status"],["education_level","employment_status"]],
  "coherence_attributes": ["age_group","education_level","employment_status"]
}
```

`attributes` key order = axis order. Italy's `_index.json` omits `income_source` (no file),
so scope stays country-driven with no code branch.

**Per-attribute file — simple case** (`biological_sex.json`):

```json
{
  "values": ["Male", "Female"],
  "database": {
    "Male":   {"equals": ["men","male","1"]},
    "Female": {"equals": ["women","female","2"]}
  },
  "synthetic": {
    "Male":   {"contains": ["male","pojke","kille","manlig"], "equals": ["man","xy","m","män"]},
    "Female": {"contains": ["female","kvinna","kvinnlig","kvinnor","flicka","tjej","hona","woman"], "equals": ["xx","hon","f"]}
  }
}
```

- `values` = unified set **and** chart/axis order.
- `database`/`synthetic` keyed by unified value; **key order = match priority** (JSON order
  preserved). First value whose matcher hits wins.
- Matcher precedence within a value: `none_of` veto → `equals` → `all_of` → `contains` →
  numeric. Unmatched after all values → `None` (or attribute-level `on_miss`).

**Extended match vocabulary (the hard 5):**
- `all_of` + `none_of` — `employment_type` synthetic (permanent+full co-occurrence; guarded
  `student → Not Applicable`).
- Numeric `{"int": [3]}` / `{"int_gte": 7}` — `household_size` synthetic. `age` stays a
  passthrough int under the raw `age` key; `age_group` is derived by the existing
  `evaluator.attr_value` binning, so `age.json` only declares the 7 bin labels as `values`.
- Decile-as-`equals` — `socioeconomic` database (`"Poverty": {"equals": ["Decile 1","Decile 2"]}`).
- Composite sub-field matcher — `employment_type` database (raw record has `attachment` +
  `hours` sub-fields): `"Permanent Full-time": {"attachment": {"contains": ["permanent employees"]}, "hours": {"contains": ["35+ hours"]}}`.
- Attribute-level `refine_from: "birth_country_detail"` — `birth_location` synthetic (replaces
  `cross_field_coded`).
- Attribute-level `database.absent: "Not Applicable"` — `industry_sector`, `employment_type`
  (replaces `reference_none_default`).
- Attribute-level `synthetic.on_miss` — default `None`; keep the DB-base-rate defaults
  `industry_sector → "Other"` and `income_source → "Wage / Business"`.
- Attribute-level `synthetic.fuzzy` (default true) — substring-match raw against the `values`
  labels after explicit rules miss; set false where currently disabled (`biological_sex`,
  `civil_status`, `employment_type`, `birth_country_detail`).

**Code changes:**
- New `src/population_synthetic/comparison/mapping_engine.py`: normalization primitives (reuse
  `synthetic_mapper/_text_helpers.py`), matcher evaluators, ordered value-walk with
  `absent`/`refine_from`/`on_miss`. Signature ~ `resolve(raw_record, rules_block, values) -> str | None`.
- `reference_mapper/base.py` and `synthetic_mapper/base.py` gutted to thin loaders that keep
  the persona-skip gate (missing/non-int `age`) and `id` passthrough and delegate to the
  shared engine (reference passes the `database` block; synthetic passes `synthetic`).
- Country subclasses, factories (`get_reference_mapper`/`get_synthetic_mapper`), and the
  two-step API (`load_reference_population`/`normalize_population`,
  `load_raw_population`/`map_population`) preserved — compare-script call sites unchanged.
- `reference_mapper/mappings.py::load_mappings` still globs the dir; add an `_index.json`
  reader.
- `comparison/scheme.py`: `load_scheme(country)` builds the same `ComparisonScheme` from
  `_index.json` + each file's `values` (age_group bins from `age.json`).
- `population/sweden/fetch_service.py:93`: drop `EIAKR` from the `Arbetskraftstillh`
  selection so the Swedish DB can't produce a not-in-labour-force value.

---

## Implementation Plan

### Phase 1: Shared engine + scheme/loader rewiring
**Goal:** New resolver and config plumbing exist and are unit-tested against small fixtures,
before any production config is rewritten.

**Started:** 2026-07-01
**Completed:** 2026-07-01

- [x] 1.1 — Create `comparison/mapping_engine.py`: normalization + matcher evaluators
      (`equals`/`contains`/`all_of`/`none_of`/`int`/`int_gte`/composite) + ordered value-walk
      with `absent`/`refine_from`/`on_miss`/`fuzzy`.
- [x] 1.2 — Add `_index.json` reader to `reference_mapper/mappings.py`.
- [x] 1.3 — Repurpose `comparison/scheme.py::load_scheme` to build `ComparisonScheme` from
      `_index.json` + per-file `values` (age_group bins from `age.json`).

**Files Modified:**
- `src/population_synthetic/comparison/mapping_engine.py` — new resolver.
- `src/population_synthetic/comparison/reference_mapper/mappings.py` — `_index.json` reader.
- `src/population_synthetic/comparison/scheme.py` — build scheme from master + `values`.

**Dependencies:** None

### Phase 2: Thin the mappers onto the shared engine
**Goal:** Both mapper engines delegate to the shared resolver.

**Started:** 2026-07-01
**Completed:** 2026-07-01

- [x] 2.1 — Gut `reference_mapper/base.py` to load master + `database` blocks and delegate;
      keep `id` passthrough. Remove the 5 reference handler-kind factories.
- [x] 2.2 — Gut `synthetic_mapper/base.py` to load master + `synthetic` blocks and delegate;
      keep the persona-skip `age` gate and UTF-8 repair. Remove the 5 pipeline factories.
- [x] 2.3 — Confirm factories, subclasses, and the two-step API signatures are unchanged.

**Files Modified:**
- `src/population_synthetic/comparison/reference_mapper/base.py` — thin delegate.
- `src/population_synthetic/comparison/synthetic_mapper/base.py` — thin delegate.

**Dependencies:** Phase 1

### Phase 3: Config rewrite (30 files) + reconciliation
**Goal:** All SCB + ISTAT attribute files converted; value sets reconciled; masters added;
`_scheme.json` deleted.

**Started:** 2026-07-01
**Completed:** 2026-07-01

- [x] 3.1 — One-off migration script (scratchpad, **not committed**) mechanically inverting
      existing maps → value-keyed blocks (`reference_label_mappings`→`database[value].equals`;
      `mappings[*].reference_codes`→`.contains`; `reference_decile_mappings`→`.equals`;
      `pipeline_label_mappings`→`synthetic[value].equals`; `pipeline_keyword_rules`→
      `synthetic[value].{contains,equals,all_of,none_of}` preserving order; `_scheme`
      categories→`values`).
- [x] 3.2 — Hand-audit the 5 complex attributes (`age`, `household_size`, `socioeconomic`,
      `employment_type`, `birth_location`) after the mechanical pass. (`age.json` = values-only;
      `socioeconomic` database = class-label + Decile-N equals; `employment_type` database =
      hand-written composite matchers, ISTAT synthetic hand-written to the `Unspecified/*` axis;
      `birth_location` synthetic gains `refine_from: birth_country_detail`.)
- [x] 3.3 — Reconcile Sweden: drop `Student`/`Retired` (employment), `Nordic Country`
      (birth_location — fold its countries into `Europe (Other)`), `Couple without Children`
      (parental_structure), `Other` (housing_tenure), `Other` collapse (birth_country_detail).
- [x] 3.4 — Reconcile Italy: keep scheme values verbatim; fix `household_size` raw codes
      (`1`/`GE6`) → labels (`"1 person"`…`"6 persons or more"`).
- [x] 3.5 — Write `_index.json` for both dirs; delete both `_scheme.json`.
- [x] 3.6 — Drop `EIAKR` from `population/sweden/fetch_service.py:93` and remove the
      not-in-labour-force→`Retired` entries from the employment `database` block.

**Files Modified:**
- `config/mapping/scb/*.json`, `config/mapping/istat/*.json` — rewrite; add `_index.json`;
  delete `_scheme.json`.
- `src/population_synthetic/population/sweden/fetch_service.py` — drop `EIAKR`.

**Dependencies:** Phase 2

### Phase 4: Tests & docs
**Goal:** Suite green; docs describe the new structure.

**Started:** 2026-07-01
**Completed:** 2026-07-01

- [x] 4.1 — Update `tests/test_evaluator.py` (scheme now sourced from master + `values`;
      SE employment still `["Employed","Unemployed"]`). *No edit needed: the test already
      sources the scheme via `load_scheme` (index-driven since Phase 1) and asserts the
      binary SE employment axis; it passes unchanged.*
- [x] 4.2 — Rewrite `tests/test_synthetic_mapper_base.py` / `test_reference_mapper_base.py`
      fixtures for the new blocks and shared engine. *New shared fixture
      `tests/_mapping_fixtures.py` (`new_shape_mappings()`); both files now drive the thinned
      base classes end-to-end through `mapping_engine` (id/age passthrough, composite,
      decile, absent, on_miss, refine_from, numeric, age gate, narrative skip, UTF-8 repair).*
- [x] 4.3 — Simplify/replace `tests/test_synthetic_reference_vocab_subset.py` (invariant is
      now trivially "both blocks key only declared `values`"). *Rewritten as a config-integrity
      guard iterating real `config/mapping/{scb,istat}` files.*
- [x] 4.4 — Update `docs/database_mapper_philosophy.md` (scheme-vs-`output_categories`
      section obsolete); add short READMEs to `config/mapping/{scb,istat}` documenting the
      file shape + matcher vocabulary; update `CLAUDE.md` comparison section.

**Orphan cleanup:** deleted the dead non-comparison config files still in the old
handler-kind shape (verified unreferenced by `_index.json`, mappers, `scheme.py`,
`evaluator.py`, and tests): `config/mapping/scb/{ethnicity,urbanization,id,age_groups}.json`
and `config/mapping/istat/{ethnicity,urbanization,id,income_source}.json`.

**Files Modified:**
- `tests/test_evaluator.py`, `tests/test_synthetic_mapper_base.py`,
  `tests/test_reference_mapper_base.py`, `tests/test_synthetic_reference_vocab_subset.py`.
- `docs/database_mapper_philosophy.md`, `config/mapping/scb/README.md`,
  `config/mapping/istat/README.md`, `CLAUDE.md`.

**Dependencies:** Phase 3

---

## Testing Plan

### Unit Tests
- [x] `mapping_engine` — `equals`/`contains` precedence and first-match-wins by value order.
- [x] `mapping_engine` — `all_of` co-occurrence and `none_of` veto (employment_type cases).
- [x] `mapping_engine` — numeric (`int`/`int_gte`) household_size bucketing incl. overflow.
- [x] `mapping_engine` — composite two-field matcher (employment_type attachment×hours).
- [x] `mapping_engine` — `refine_from` cross-field (birth_location via birth_country_detail).
- [x] `mapping_engine` — `absent` default and `on_miss` (None vs literal default).
- [x] `load_scheme` — attributes/categories/joint_pairs/coherence built from master + values;
      country-specific (istat omits income_source; SE employment binary).

### Integration Tests
- [x] Reference mapper end-to-end over the SCB reference file → flat canonical population.
      *Covered by `test_reference_mapper_base.py` + `test_mapper_delegation.py` (base class
      resolves a full record → flat schema through the engine); real-file equivalence proven
      by the Phase-3 golden diffs.*
- [x] Synthetic mapper end-to-end over a sample `identity.json` run → flat canonical pop.
      *Covered by `test_synthetic_mapper_base.py` + `test_mapper_delegation.py`.*

### Manual Verification
- [x] **Golden diff (SCB):** per-attribute `Counter` from old vs new reference mapper over
      `data/scb_api/scb_population_pop-10000_02.json`; only intended drops differ. *Result:*
      **byte-identical for all 14 non-age attributes** — the dropped labels (`Retired`/`Student`/
      `Nordic Country`/`Couple without Children`/housing `Other`) never appear in the already-binary
      shipped reference file, so there is nothing to drop.
- [x] **Golden diff (ISTAT):** same over `data/istat_api/istat_population.json`. *Result:*
      **byte-identical for all 14 attributes.**
- [ ] **Synthetic diff:** map an existing `{output_base}/01_Raw/<slug>/` run old vs new;
      differences only where a previously non-unified label now → unified value or `None`.
- [ ] `compare_pipeline_to_scb.py` + `compare_pipeline_to_istat.py`: JSON + CSV + all bar
      charts + radar generate; no synthetic-only empty bars.

### Edge Cases
- [x] Empty/whitespace raw value → `None` (not a spurious fuzzy match). *`test_mapping_engine`.*
- [x] Missing/non-integer `age` → persona skipped (gate preserved).
      *`test_synthetic_mapper_base::test_age_gate_skips_non_integer_and_missing_age`.*
- [x] `null` industry/employment_type record → `Not Applicable` via `absent`.
      *`test_reference_mapper_base::test_reference_absent_field_uses_absent_directive`.*
- [x] snake_case / kebab-case / double-encoded UTF-8 synthetic values still resolve.
      *`test_mapping_engine` + `test_synthetic_mapper_base::test_utf8_repair_applied_before_matching`.*

---

## Documentation Plan

- [x] Update `CLAUDE.md` comparison section (mapper structure, master file, matcher vocab).
- [x] Rewrite the "comparison scheme" section of `docs/database_mapper_philosophy.md`.
- [x] Add `config/mapping/scb/README.md` and `config/mapping/istat/README.md`.
- [x] Inline docstrings in `mapping_engine.py` documenting matcher precedence. *(Phase 1.)*

---

## Rollback Plan

1. **Before merge:** work lives on `feature/unified-symmetric-mapping-config`; abandon by
   deleting the branch — `dev` is unaffected.
2. **Data considerations:** no data migrations. The only generator change (`EIAKR` drop)
   affects *future* Swedish regenerations only; existing reference files are unchanged and
   remain valid inputs. No breaking change to population file formats.
3. **Rollback procedure:** revert the merge commit; restore `_scheme.json` from history and
   the old `reference_*`/`pipeline_*` config files; the old two-engine code returns with the
   revert. Compare scripts are untouched, so no call-site rollback needed.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Flattening ordered keyword rules → value-keyed blocks changes resolution (esp. `employment_type` interleaved `all_of`) | Med | Med | Golden diff over the 10k reference file + synthetic sample; hand-audit the 5 complex attributes; order value keys to preserve priority |
| istat `household_size` label fix or other value reconciliation shifts a distribution unintentionally | Low | Med | Golden diff must show *only* intended changes; investigate any other delta before merge |
| `refine_from` / composite matchers under-specified for real records | Med | Med | Unit tests with real record shapes from the reference files; integration run end-to-end |
| Charts/CSV ordering changes surprise downstream consumers | Low | Low | `values` order fixes axis order deterministically; verify charts render |
| Scope creep into SSB/Norway | Low | Low | Explicitly out of scope; SSB not wired to the scheme mechanism |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — engine + rewiring | ~0.5 day | None |
| Phase 2 — thin mappers | ~0.5 day | Phase 1 |
| Phase 3 — config rewrite + reconciliation | ~1 day | Phase 2 |
| Phase 4 — tests + docs | ~0.5 day | Phase 3 |

---

## References

- Approved scratch plan: `C:\Users\basil\.claude\plans\we-need-to-plan-adaptive-allen.md`
- Related design doc: `docs/database_mapper_philosophy.md`
- Prior mapper refactors: `docs/development/plans/completed/refactor-synthetic-mapper-config-driven.md`,
  `docs/development/plans/completed/reference-mapper-fully-field-agnostic.md`

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- CLAUDE.md
- config/mapping/istat/_index.json
- config/mapping/istat/_scheme.json
- config/mapping/istat/age.json
- config/mapping/istat/biological_sex.json
- config/mapping/istat/birth_country_detail.json
- config/mapping/istat/birth_location.json
- config/mapping/istat/civil_status.json
- config/mapping/istat/education.json
- config/mapping/istat/employment.json
- config/mapping/istat/employment_type.json
- config/mapping/istat/ethnicity.json
- config/mapping/istat/household_size.json
- config/mapping/istat/housing_tenure.json
- config/mapping/istat/id.json
- config/mapping/istat/income_source.json
- config/mapping/istat/industry_sector.json
- config/mapping/istat/parental_structure.json
- config/mapping/istat/region.json
- config/mapping/istat/README.md
- config/mapping/istat/socioeconomic.json
- config/mapping/istat/urbanization.json
- config/mapping/scb/_index.json
- config/mapping/scb/_scheme.json
- config/mapping/scb/age.json
- config/mapping/scb/age_groups.json
- config/mapping/scb/biological_sex.json
- config/mapping/scb/birth_country_detail.json
- config/mapping/scb/birth_location.json
- config/mapping/scb/civil_status.json
- config/mapping/scb/education.json
- config/mapping/scb/employment.json
- config/mapping/scb/employment_type.json
- config/mapping/scb/ethnicity.json
- config/mapping/scb/household_size.json
- config/mapping/scb/housing_tenure.json
- config/mapping/scb/id.json
- config/mapping/scb/income_source.json
- config/mapping/scb/industry_sector.json
- config/mapping/scb/parental_structure.json
- config/mapping/scb/region.json
- config/mapping/scb/README.md
- config/mapping/scb/socioeconomic.json
- config/mapping/scb/urbanization.json
- docs/database_mapper_philosophy.md
- docs/development/plans/active/unified-symmetric-mapping-config.md
- src/population_synthetic/comparison/mapping_engine.py
- src/population_synthetic/comparison/reference_mapper/base.py
- src/population_synthetic/comparison/reference_mapper/mappings.py
- src/population_synthetic/comparison/scheme.py
- src/population_synthetic/comparison/synthetic_mapper/base.py
- src/population_synthetic/comparison/synthetic_mapper/factory.py
- src/population_synthetic/population/sweden/fetch_service.py
- tests/_mapping_fixtures.py
- tests/test_mapper_delegation.py
- tests/test_mapping_engine.py
- tests/test_reference_mapper_base.py
- tests/test_scheme_index.py
- tests/test_synthetic_mapper_base.py
- tests/test_synthetic_reference_vocab_subset.py
