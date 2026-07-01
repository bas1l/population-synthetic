# Plan: Refactor the synthetic mapper to the reference mapper's config-driven philosophy

**Date:** 2026-06-30
**Author:** Basil
**Status:** Completed
**Completed:** 2026-06-30 21:55
**Base Branch:** `feature/reference-mapper-fully-field-agnostic`
**Branch:** `feature/synthetic-mapper-config-driven`

---

## Overview

Rebuild the **synthetic (pipeline) mapper** so it follows the same field-agnostic, config-discovered architecture the **reference (database) mapper** already uses. Each per-attribute mapping JSON will self-declare its synthetic-side algorithm via a new `pipeline_handler` key (the counterpart of the existing `reference_handler`), a small generic engine will discover the field set from config, and all canonical labels / keyword cascades / city tables move out of Python and into role-based JSON sub-keys. The reference mapper is the gold standard and **must not be modified**.

## Problem Statement

The investigation behind this plan compared the two mappers. The reference mapper (`comparison/reference_mapper/base.py`) is a clean, config-discovered engine that holds **zero field-name literals and zero canonical label strings** — adding/removing a comparison field is a config-only change. The synthetic mapper is architecturally the **opposite**:

- `AbstractSyntheticMapper` declares one `@abstractmethod` per field (13 of them); `BaseSyntheticMapper._map_flat` hardcodes the 17 output keys (`synthetic_mapper/base.py:93-189`).
- Country divergence is implemented as full per-attribute method-override subclasses (`sweden.py`, `italy.py`), plus a `SILENT_UNMAPPED` set and `if`-style country branches.
- Canonical label constants, keyword cascades, and city tables are hardcoded in `extract/schema_labels.py`, `extract/normalizers_se.py`, `extract/normalizers_it.py`.

Both mappers happen to read canonical strings from the *same* `config/mapping/{scb,istat}/*.json` files, so most recent category renames auto-propagate to both sides — the synthetic mapper is **mostly still correct by accident of shared config**. But the hardcoded Python is a standing drift risk and has already produced **one confirmed defect**:

- **`birth_location` can never emit `"Nordic Country"`.** `extract/normalizers_se.py:142-143` and `synthetic_mapper/sweden.py:95-103` collapse Norway/Denmark/Finland/Iceland into `"Europe (Other)"`, but the reference mapper *does* emit `"Nordic Country"` (`config/mapping/scb/birth_location.json:14-24`). Every Swedish comparison therefore has a reference bucket the synthetic distribution can never fill, biasing the `birth_location` TV distance.

(Investigated and found **not** to be bugs: `industry_sector` slash-form constants are input-only and re-normalised to the ampersand canon via `pipeline_label_mappings`; `education.json`'s 4-coarse `mappings[*].schema_label` block is vestigial dead config under a `label` handler.)

Why it matters: the comparison layer is the scientific output of the project. Drift between what the synthetic side can emit and what the reference side produces silently corrupts every TV-distance / chi-squared result, and the current architecture has no guard against it.

## Goals

### In Scope
1. A generic, config-discovered synthetic engine mirroring `BaseReferenceMapper`: field set discovered from a `pipeline_handler` key, one generic handler registered per declaring block, zero field literals / zero label strings, fail-fast on unknown kind or no declaring block.
2. A minimal `pipeline_handler` kind library (5 generic kinds) parameterised entirely by config.
3. Migration of all hardcoded labels / keyword cascades / city tables from `schema_labels.py` / `normalizers_se.py` / `normalizers_it.py` into `pipeline_*` role sub-keys in the existing JSONs (reference_* keys untouched).
4. Country subclasses collapsed to one-line `MAPPINGS_SUBDIR` definitions; `SILENT_UNMAPPED` and country branches eliminated.
5. Fix the `birth_location` Nordic-Country defect as a natural consequence of config-driving that attribute.
6. A vocabulary-subset guard test that statically proves the synthetic emittable vocabulary ⊆ reference output categories per attribute.

### Out of Scope
- **Any modification to the reference mapper** (`comparison/reference_mapper/*`) — read-only template.
- Folding the Swedish narrative/batch path into the handler loop — it stays imperative, Swedish-only code (its labels/keywords are migrated to config, but its coherence-inference logic is not table-driven).
- Adding Italian narrative support (remains `NotImplementedError`).
- Changing the demographic schema, the set of comparison attributes, or the statistical evaluator.
- The cleaner "drop Italian ethnicity/environment keys entirely" behavioural change (flag for a separate reviewed change; default to preserving current keys via config flags so the golden is untouched).

## Success Criteria

- [ ] `BaseSyntheticMapper.__init__` discovers its field set by scanning `pipeline_handler` keys; no field name or canonical label literal remains in the engine.
- [ ] `synthetic_mapper/sweden.py` and `synthetic_mapper/italy.py` are each a one-line `MAPPINGS_SUBDIR` subclass.
- [ ] Unknown `pipeline_handler` kind raises `ValueError`; a mappings set with no declaring block raises `ValueError`.
- [ ] `tests/test_extractor_characterization.py` stays green throughout (behaviour-preserving except the intended new `"Nordic Country"` bucket).
- [ ] A Swedish comparison now produces a `"Nordic Country"` bucket on the synthetic side for Nordic-born personas.
- [x] New vocabulary-subset guard test passes for every registered attribute, both countries.
- [x] `pytest` clean (87 passed); `ruff check` clean on all files changed by this refactor (pre-existing ruff findings elsewhere in `src/` are unrelated).

---

## Technical Design

### Approach

Introduce a parallel `pipeline_handler` dispatch scheme that is the synthetic-side mirror of `reference_handler`, co-located in the *same* JSON files (each file keeps its untouched `reference_*` keys and gains `pipeline_*` keys). A generic `BaseSyntheticMapper` scans the loaded mappings, registers one generic handler per block that declares `pipeline_handler`, and orchestrates per-record mapping exactly as `BaseReferenceMapper.normalize_individual` does. Selected because it is the only approach that achieves true config-driven parity with the (frozen) reference engine and eliminates the drift class wholesale, rather than patching individual fields.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Mirror `reference_handler` with a `pipeline_handler` engine (this plan) | Full parity with the gold standard; field set & labels config-driven; drift becomes a config-only concern; Nordic bug fixed structurally | Largest refactor; keyword-cascade ordering must be reproduced as data | **Chosen** |
| Point-fix only the Nordic bug + audit constants by hand | Minimal change | Leaves the entire hardcoded-Python drift class in place; violates the user directive to match the reference philosophy | Rejected |
| Auto-load all hardcoded constants from JSON but keep the per-field method architecture | Removes label drift | Engine stays field-bound (13 methods, hardcoded `_map_flat`); not field-agnostic; country branches remain | Rejected |

### Architecture Changes

New/rewritten:
- `synthetic_mapper/base.py` — generic engine + `_HANDLER_KINDS` library; `AbstractSyntheticMapper` reduces to `MAPPINGS_SUBDIR` + `map_individual`.
- `synthetic_mapper/sweden.py`, `synthetic_mapper/italy.py` — one-line `MAPPINGS_SUBDIR` subclasses.
- `synthetic_mapper/factory.py` — dict lookup + `load_mappings` (structure copied from `reference_mapper/factory.py`).

Significantly modified:
- `extract/schema_labels.py` — hardcoded label constants and city tables deleted (those with no JSON home move into JSON).
- `extract/normalizers_se.py`, `extract/normalizers_it.py` — `_normalize_*` keyword-cascade bodies emptied as their rules move to `pipeline_keyword_rules`.
- `extract/batch.py` — rewired to source labels/keywords/city tables from config; stays Swedish-only imperative coherence logic.
- `config/mapping/scb/*.json`, `config/mapping/istat/*.json` — gain `pipeline_handler` / `pipeline_attr` / `output_categories` / `pipeline_keyword_rules` / etc.

Preserved (backward-compat): `comparison/extractor.py` (`extract_individual`/`extract_population`), `synthetic_mapper/loader.py` two-step API + `metadata` shape, the `"Non-standard label"` sentinel, `unmapped`/`skipped` accounting, flat-emits-`age`-int vs batch-emits-`age_group`.

#### The engine (`synthetic_mapper/base.py`)

`__init__(mappings)` scans blocks; for each block with a `pipeline_handler` key, look up the kind in `_HANDLER_KINDS`, register `factory(attr, block, self)` under `attr = block.get("pipeline_attr", stem)`. Skip blocks without the key. Fail fast on unknown kind or no declaring block. Mirrors `reference_mapper/base.py:237-258`.

- `pipeline_attr` resolves stem≠schema-key: `education`→`education_level`, `employment`→`employment_status`, `socioeconomic`→`socioeconomic_class`, `urbanization`→`current_environment_type`.
- **Skip gate:** `age.json` sets `pipeline_gate: true`; its `numeric_gate` handler returns a private `_SKIP` sentinel on missing/non-int age, so `map_individual` returns `None` (preserves the persona-skip at `base.py:163`).
- **Unmapped accounting:** thread a shared `unmapped: list[str]` through handlers; on a miss the handler emits the configured sentinel and records `attr=raw` (never returns the raw string as a category — removes the `_CIVIL_STATUS_OUTPUT`/`_EMPLOYMENT_TYPE_OUTPUT` leak-through patches at `sweden.py:119-122,232-234`). Keep the `"%s: unmapped flat fields"` log (`base.py:188`).
- Module functions stay in `base.py`: `is_flat_identity`, UTF-8 repair pre-pass (`base.py:156`), narrative dispatch.

#### The `pipeline_handler` kind library (5 generic kinds)

Each kind is a factory `(attr, block, engine) -> callable(identity) -> value`; the kind names an algorithm, never a field.

| Kind | Algorithm | Config sub-keys | Attributes |
|---|---|---|---|
| `passthrough` | emit `identity.get(attr)` verbatim | — | `id` |
| `numeric_gate` | `int(raw)` or `_SKIP` | `pipeline_gate` | `age` |
| `text_coded` | ordered free-text→canonical resolver (below) | `output_categories`, `pipeline_label_mappings`, `pipeline_keyword_rules`, `pipeline_on_miss`, `pipeline_passthrough_on_separator?`, `pipeline_silent_unmapped?` | biological_sex, education_level, employment_status, civil_status, housing_tenure, industry_sector, income_source, socioeconomic_class, parental_structure, ethnicity, current_environment_type, employment_type (SE), birth_country_detail |
| `numeric_bucket` | int/str→bucket label | `pipeline_numeric_buckets`, `pipeline_bucket_overflow`; also `age→age_group` via `age_groups.json` | household_size |
| `cross_field_coded` | run `text_coded` on a primary field, then refine from another | `pipeline_primary_field`, `pipeline_refine_from`, `pipeline_domestic_label`, `pipeline_refine_buckets` | birth_location |

**`text_coded` resolution order** (the data form of every `_normalize_*` cascade + `match_common_sex`): (1) exact membership in `output_categories` → passthrough; (2) optional `pipeline_passthrough_on_separator` (e.g. `"|"` for Italian employment_type, `italy.py:149-150`); (3) `pipeline_label_mappings` lookup (existing `_json_lookup`); (4) ordered `pipeline_keyword_rules` — JSON array of `{match: "contains"|"equals", any_of?: [...], all_of?: [[...],[...]], label}`, lowercased + separator-normalised (the `all_of` form expresses permanent+full / temporary+part co-occurrence at `sweden.py:214-225`); (5) fuzzy substring vs `output_categories` (existing `_fuzzy_match`); (6) `pipeline_on_miss`: `"non_standard"` (emit `"Non-standard label"` + record) | `"passthrough"` (keep raw, e.g. `birth_country_detail`, `normalizers_se.py:382-386`) | a default-label string (e.g. `income_source`→`"Wage / Business"`, `sweden.py:238`).

**`cross_field_coded` fixes the Nordic bug:** birth_location runs `text_coded` then applies the birth_country_detail refinement table (currently `sweden.py:95-103`) relocated to `birth_location.json` under `pipeline_refine_buckets`, reading the same `output_categories` (which include `"Nordic Country"`), so the handler can emit every label the reference emits.

---

## Implementation Plan

### Phase 1: Config foundation (pure config, no engine yet)
**Goal:** Add `pipeline_handler` / `pipeline_attr` / `output_categories` to the already-table-driven attributes without changing behaviour.

**Started:** 2026-06-30
**Completed:** 2026-06-30

- [x] Task 1.1 — Add `pipeline_handler`/`pipeline_attr` to the straightforward attrs: id, age, biological_sex, education, employment, civil_status, household_size, housing_tenure, income_source, birth_country_detail, ethnicity, region (both `scb/` and `istat/` where present).
- [x] Task 1.2 — Add `output_categories` to JSONs that lack it (employment, birth_location, urbanization, socioeconomic, parental_structure, region, civil_status, industry_sector, employment_type), matching the current emitted vocabulary exactly.
- [x] Task 1.3 — Confirm `reference_*` keys are byte-for-byte untouched in every edited file.

**Files Modified:**
- `config/mapping/scb/*.json`, `config/mapping/istat/*.json` — additive `pipeline_*` / `output_categories` keys only.

**Dependencies:** None

### Phase 2: Generic engine + simple kinds
**Goal:** Stand up the discovery engine and the non-cascade handler kinds.

**Started:** 2026-06-30
**Completed:** 2026-06-30

- [x] Task 2.1 — Rewrite `AbstractSyntheticMapper`/`BaseSyntheticMapper` in `synthetic_mapper/base.py`: `__init__` discovery loop, `_HANDLER_KINDS`, `map_individual`, gate/unmapped threading, UTF-8 pre-pass, narrative dispatch.
- [x] Task 2.2 — Implement `passthrough`, `numeric_gate`, `text_coded`, `numeric_bucket` factories.
- [x] Task 2.3 — Add fail-fast unit test (unknown kind raises; no declaring block raises) mirroring `tests/test_reference_mapper_base.py`.
- [x] Task 2.4 — Run the golden (`tests/test_extractor_characterization.py`).

**Files Modified:**
- `src/population_synth/comparison/synthetic_mapper/base.py` — new field-literal-free discovery engine + `_HANDLER_KINDS` (passthrough, numeric_gate, text_coded, numeric_bucket), `_SKIP` gate sentinel, `map_individual`/`_map_flat` orchestrator, `_legacy_flat_remainder` hook.
- `src/population_synth/comparison/extract/legacy_bridge.py` — **new** TEMPORARY country-agnostic dispatch (`resolve_engine_attr` / `legacy_remainder`) keeping behaviour byte-identical while keyword cascades remain in Python; dissolved attribute-by-attribute in Phases 3-5.
- `src/population_synth/comparison/synthetic_mapper/sweden.py`, `italy.py` — add `MAPPINGS_SUBDIR` (`scb`/`istat`) and a one-line `_legacy_flat_remainder` override delegating to `legacy_bridge`; existing legacy `map_*` methods retained (reached through the bridge).
- `tests/test_synthetic_mapper_base.py` — new fail-fast + passthrough/numeric_gate tests.

**Phase-2 engine ownership (which attrs the engine produces vs. legacy):**
- Engine-native: `id` (passthrough, fed the injected persona id), `age` (numeric_gate, `_SKIP` gate).
- Engine-owned but delegating to the legacy method via `legacy_bridge` (text_coded / numeric_bucket): `biological_sex`, `education_level`, `employment_status`, `civil_status`, `housing_tenure`, `birth_country_detail`, `region`, `household_size`, plus `ethnicity` + `income_source` (Swedish only — no istat blocks).
- Legacy remainder (no `pipeline_handler` yet): `birth_location`, `current_environment_type`, `socioeconomic_class`, `parental_structure`, `employment_type`, `industry_sector` (+ `ethnicity`, `income_source` for Italy).
- The `numeric_bucket` factory implements a config-driven path gated on `pipeline_numeric_buckets`; since that key is not in config yet, `household_size` delegates to the legacy method for now (native bucketing enabled in a later phase).

**Dependencies:** Phase 1

### Phase 3: Migrate keyword cascades into config
**Goal:** Move every `_normalize_*` cascade and inline keyword test into `pipeline_keyword_rules`, emptying the Python bodies attribute-by-attribute.

**Started:** 2026-06-30
**Completed:** 2026-06-30

- [x] Task 3.1 — Per attribute: translated each cascade (order-sensitive — e.g. guarded `lower secondary` before `secondary`; `upper-secondary` 3A vs `upper secondary` 3C preserved by *not* hyphen-collapsing keyword tokens) into ordered `pipeline_keyword_rules`. Engine `text_coded` is now fully native (gated on `pipeline_native`): membership → separator → label → keyword_rules → fuzzy → on_miss. Golden + a 2962-case characterization harness (label keys + cascade tokens + canonical + empty, both countries) stayed at 0 diffs after every attribute.
- [x] Task 3.2 — `match_common_sex` tokens, the `sweden.py` inline housing/industry/employment_type tests (incl. `_PERM`+full `all_of` rules, the `_EMPLOYMENT_TYPE_OUTPUT` gate via `pipeline_on_miss:"non_standard"`, and the guarded-`student` rule via a new `none_of` veto), and `italy.py` sex tokens are all in config.
- [x] Task 3.3 — `_CITY_TO_REGION_IT` is already represented in `istat/region.json` `pipeline_label_mappings`. `_CITY_TO_COUNTY` was relocated to `scb/region.json` under a dedicated **`pipeline_city_region`** key (NOT `pipeline_label_mappings`) and `_METRO_CITIES`/`_LARGE_CITIES` to `urbanization.json` under **`pipeline_city_environment`** — see deviation note below. The Python constants are kept (batch still imports them; Phase 6 removes them).

**Engine kinds/flags added this phase:** `text_coded` native chain plus config flags `pipeline_native`, `pipeline_fuzzy`, `pipeline_on_miss` (`non_standard` | `passthrough` | `passthrough_or_nonstandard` | literal-default), `pipeline_source_key`, `pipeline_silent_unmapped`, `pipeline_empty_raw`, `pipeline_membership`, `pipeline_fuzzy_categories`, `pipeline_fuzzy_relabel`; keyword-rule `none_of` veto; native `numeric_bucket` (`pipeline_numeric_buckets` / `pipeline_bucket_overflow` / `pipeline_bucket_default`).

**New pipeline-only istat blocks** (no `reference_handler`, so the reference mapper ignores them): `istat/ethnicity.json`, `istat/urbanization.json`, `istat/income_source.json` — added so Italy produces ethnicity / current_environment_type / income_source natively (reproducing the shared Swedish-normalizer behaviour the bridge previously supplied) and the bridge clears to birth_location only. `istat/socioeconomic.json` and `istat/parental_structure.json` had their (dead) `pipeline_label_mappings` replaced with the SCB ones, because the shared base `_normalize_*` methods resolve Italian values through the **Swedish** `_json_lookup`.

**Deviation (Task 3.3):** the plan said put the city tables in `pipeline_label_mappings`, but the flat region path consumes that map, and the full `_CITY_TO_COUNTY` includes ~40 small cities not previously resolved on the flat path — adding them would change flat-region behaviour, violating the "only birth_location changes" directive. Data was relocated to `pipeline_city_region` / `pipeline_city_environment` instead (still config-resident for Phase 6 batch).

**`_normalize_*` bodies: KEPT (not emptied).** `extract/batch.py` imports every SCB `_normalize_*` (`batch.py:15-31`) for the narrative path (rewired in Phase 6), so emptying them now would break the batch golden. The engine simply no longer routes through them. The country `map_*` methods are likewise left in place (now dead except `map_birth_location`); Phase 5 collapses them.

**Files Modified:**
- `config/mapping/scb/*.json`, `config/mapping/istat/*.json` — `pipeline_keyword_rules` + flags; new istat blocks; city tables.
- `src/population_synth/comparison/synthetic_mapper/base.py` — native `text_coded`/`numeric_bucket`, flags, `none_of`.
- `src/population_synth/comparison/extract/legacy_bridge.py` — dissolved to birth_location only.

**Dependencies:** Phase 2

### Phase 4: birth_location cross-field handler (fixes Nordic bug)
**Goal:** Config-drive the one cross-field attribute and restore the `"Nordic Country"` bucket.

**Started:** 2026-06-30
**Completed:** 2026-06-30

- [x] Task 4.1 — Implemented `cross_field_coded`; relocated the detail→bucket refinement table to `birth_location.json` `pipeline_refine_buckets` with `pipeline_domestic_label`, and translated the `_birth_location_from_flat` / `_normalize_birth_location` primary cascade (region substring, city membership with `kommun`/`stad` stripping, European/non-European token sets, descriptor cascade, fuzzy, `sverige`) into ordered `pipeline_keyword_rules` — changing ONLY the Nordic target to `"Nordic Country"`. `birth_location` removed from `legacy_bridge.py` (the bridge is now empty: `legacy_remainder` returns `{}` and `resolve_engine_attr` is unreachable — flagged for Phase 5 deletion).
- [x] Task 4.2 — Verified: a 65 702-case before/after characterization sweep (both countries, full cartesian of birth_location × birth_country_detail over every constant token set + city/region table) shows the **only** changes are 1779 Swedish `Europe (Other)` → `Nordic Country` flips (every one has a Nordic token in `birth_location` or `birth_country_detail`); **Italian output is byte-identical (0 diffs)**. Golden stays byte-identical (no fixture persona is Nordic-born), so a new targeted Nordic unit test was added instead.

**Engine/handler details:**
- `cross_field_coded` algorithm: (1) resolve `pipeline_primary_field` (`birth_location`) via a native, silent `text_coded` over the same block (empty primary short-circuits to the miss sentinel, never fuzzy-matching `""`); (2) resolve `pipeline_refine_from` (`birth_country_detail`) through *its own* registered handler; (3) if the resolved detail equals `pipeline_domestic_label` → force domestic (overrides primary); (4) else if primary missed, refine via `pipeline_refine_buckets`.
- `pipeline_refine_buckets` is **dict-or-list**: a dict is an exact, case-sensitive label lookup (mirrors legacy SE `if bcd in {<canonical labels>}`); a list is a case-insensitive keyword-rule cascade (mirrors legacy IT `any(tok in bcd.lower())`). `pipeline_refine_source` selects `"resolved"` (SE, against the canonical label) vs `"raw"` (IT, against the raw bcd substring); `pipeline_refine_default` ("Outside Europe" for SE; omitted for IT).
- Two faithfulness fixes vs a naïve port: (a) `pipeline_membership: false` on both birth_location blocks, because the legacy primary has no already-canonical short-circuit and relies on the `"europe" in "outside europe"` ordering quirk; (b) the case-sensitive dict refine so a lowercase free-text `"denmark"` bcd stays Outside Europe exactly as before.

**Files Modified:**
- `src/population_synth/comparison/synthetic_mapper/base.py` — `cross_field_coded` kind (+ registered in `_HANDLER_KINDS`).
- `src/population_synth/comparison/extract/legacy_bridge.py` — `legacy_remainder` now returns `{}` (bridge empty).
- `config/mapping/scb/birth_location.json`, `config/mapping/istat/birth_location.json` — `pipeline_handler: "cross_field_coded"` + `pipeline_primary_field`/`pipeline_refine_from`/`pipeline_domestic_label`/`pipeline_refine_source`/`pipeline_refine_default`/`pipeline_refine_buckets`/`pipeline_keyword_rules`/`pipeline_membership`/`pipeline_fuzzy`; istat `pipeline_label_mappings` (vestigial, unused) dropped.
- `tests/test_synthetic_mapper_base.py` — new Nordic unit tests (refined-from-detail + primary free-text → `"Nordic Country"`; domestic override; non-Nordic Europe unchanged; Italian has no Nordic bucket).

**Dependencies:** Phase 3

### Phase 5: Country collapse + constant cleanup
**Goal:** Reduce country subclasses to one-liners and delete dead Python.

**Started:** 2026-06-30
**Completed:** 2026-06-30

- [x] Task 5.1 — Collapsed `synthetic_mapper/sweden.py` / `italy.py` to `MAPPINGS_SUBDIR` subclasses. All dead per-attribute `map_*` methods (country + shared base) deleted. Italian specifics are entirely config (Phase-3 istat `pipeline_passthrough_on_separator:"|"`, sex tokens, ethnicity/urbanization/income_source blocks). `SILENT_UNMAPPED` eliminated (the silent behaviour is config-driven via `pipeline_silent_unmapped` on the istat blocks). Narrative support is now a single class flag `SUPPORTS_NARRATIVE: ClassVar[bool]` (True for Sweden, default False for Italy); base `map_individual` consults it and dispatches to `extract/batch.py`'s `_extract_batch` (Swedish) or raises `NotImplementedError` (Italy). Sweden carries `MAPPINGS_SUBDIR` + the one narrative flag; Italy carries only `MAPPINGS_SUBDIR`.
- [x] Task 5.2 — Rewrote `synthetic_mapper/factory.py` as a dict lookup + `load_mappings`, mirroring `reference_mapper/factory.py`. `get_synthetic_mapper(country, mappings_path=None)` now loads `config/mapping/{MAPPINGS_SUBDIR}` and constructs the subclass (public signature/behaviour preserved; `mappings_path` added as an optional, defaulted param).
- [x] Task 5.3 — Deleted `extract/legacy_bridge.py` and removed its import/use from `base.py`; `map_individual`/`_map_flat` now build the flat result purely from the registered engine handlers (no remainder merge, no `_legacy_flat_remainder` hook). The dead `if not native` / `if not buckets` bridge branches in `text_coded` / `numeric_bucket` were removed (all blocks are native and carry buckets).
- [x] Task 5.4 — Deleted the orphaned (zero-importer) constants from `extract/schema_labels.py` after grepping `src/`, `tests/`, `scripts/`: `AGE_GROUPS`, `_EMPLOYMENT_TYPE_OUTPUT`, `_CIVIL_STATUS_OUTPUT`, and the now-dead Italian constants `EMPLOYMENT_LABELS_IT`, `BIRTH_LOCATION_LABELS_IT`, `REGION_LABELS_IT`, `CIVIL_STATUS_LABELS_IT`, `HOUSING_TENURE_LABELS_IT`, `INDUSTRY_SECTOR_LABELS_IT`, `EMPLOYMENT_TYPE_LABELS_IT`, `BIRTH_COUNTRY_DETAIL_LABELS_IT`, `HOUSEHOLD_SIZE_LABELS_IT`, `PARENTAL_STRUCTURE_LABELS_IT`, `SOCIOECONOMIC_LABELS_IT`, `_CITY_TO_REGION_IT`. KEPT (still imported, Phase-6 owns their removal): the Swedish `*_LABELS` + `_CITY_TO_COUNTY`/`_METRO_CITIES`/`_LARGE_CITIES` (batch.py), `INCOME_SOURCE_LABELS` (normalizers_se), `EDUCATION_LABELS_IT` (normalizers_it), and `_OCCUPATION_TO_INDUSTRY`/`_UNIVERSITY_OCCUPATIONS`/`_BULLET_LINE_RE`/`_TEMPLATE_LABEL_ALIASES` (prose_inference).

**Files Modified:**
- `src/population_synth/comparison/synthetic_mapper/{sweden,italy,factory,base}.py`
- `src/population_synth/comparison/extract/schema_labels.py`
- `src/population_synth/comparison/extract/legacy_bridge.py` — **deleted**

**Dependencies:** Phase 4

### Phase 6: Batch path rewire + guard test
**Goal:** Source batch labels from config; add the static drift guard.

**Started:** 2026-06-30
**Completed:** 2026-06-30

- [x] Task 6.1 — Rewired `extract/batch.py` to load its canonical-label vocabularies and city tables from the mapper's `mappings` dict (passed into `_extract_batch(identity, persona_id, mappings)`): the 11 `output_categories`-equal label sets read from `mappings[stem]["output_categories"]`, the city tables from `region.json` `pipeline_city_region` + `urbanization.json` `pipeline_city_environment`. `batch.py` now imports **nothing** from `schema_labels`. The two genuine *input search-alias* lists (civil-status + industry slash-forms, distinct from the canonical emit forms) became batch-local constants `_CIVIL_STATUS_SEARCH_ALIASES` / `_INDUSTRY_SECTOR_SEARCH_ALIASES`. Coherence inference (household size, parental structure, socioeconomic class, environment tiering, civil/birth heuristics) stayed Swedish-only imperative. `persona_batch_se` golden byte-identical.
- [x] Task 6.2 — Added the vocabulary-subset guard test (synthetic emittable vocab ⊆ reference vocab per attribute, both countries) — see below.

**6.1 constant cleanup (deleted vs kept):**
- **Deleted** from `schema_labels.py` (zero remaining importers after the rewire): `_CITY_TO_COUNTY`, `_METRO_CITIES`, `_LARGE_CITIES`, `BIRTH_COUNTRY_DETAIL_LABELS`, `CIVIL_STATUS_LABELS`, `HOUSEHOLD_SIZE_LABELS`, `HOUSING_TENURE_LABELS`, `INDUSTRY_SECTOR_LABELS`, `REGION_LABELS`.
- **Kept (still imported)**: `BIRTH_LOCATION_LABELS`, `EDUCATION_LABELS`, `EMPLOYMENT_LABELS`, `ENVIRONMENT_LABELS`, `ETHNICITY_LABELS`, `INCOME_SOURCE_LABELS`, `PARENTAL_STRUCTURE_LABELS`, `SOCIOECONOMIC_LABELS` (all consumed by `normalizers_se.py`'s `_normalize_*` already-canonical passthrough membership tests); `EDUCATION_LABELS_IT` (`normalizers_it.py`); `_OCCUPATION_TO_INDUSTRY` / `_UNIVERSITY_OCCUPATIONS` / `_BULLET_LINE_RE` / `_TEMPLATE_LABEL_ALIASES` (`prose_inference.py` — structural parsing tables, not label vocab). The `_normalize_*` bodies were left intact: emptying them / routing batch through the engine's `text_coded` handlers is the deferred higher-risk change (engine vs `_normalize_*` resolution differs subtly), and the risk-control directive prioritises a byte-identical `persona_batch_se` golden. Residue is therefore confined to `normalizers_se.py`/`normalizers_it.py`; `schema_labels.py` is fully cleared of the batch-only label constants and all three city tables.

**`pipeline_native` removal:** the now-dead `pipeline_native` config key (the engine never reads it) was stripped from all 28 declaring JSON blocks (`scb/` + `istat/`) and from the one in-code artifact in `base.py`'s `cross_field_coded` primary-block construction. JSON re-validated OK.

**Guard test (`tests/test_synthetic_reference_vocab_subset.py`):** parametrized over `swedish→scb` / `italian→istat`. For every attribute whose block declares **both** a `pipeline_handler` and a `reference_handler` it asserts `synthetic_emittable_vocab(attr) ⊆ reference_vocab(attr)`. Synthetic vocab = `output_categories` ∪ `pipeline_label_mappings` values ∪ `pipeline_keyword_rules` labels ∪ `pipeline_refine_buckets`/`pipeline_refine_default` ∪ numeric-bucket labels (+overflow) ∪ literal `pipeline_on_miss` default, minus the `"Non-standard label"` sentinel and minus raw/passthrough emissions (`pipeline_on_miss` in {non_standard, passthrough, passthrough_or_nonstandard}). Reference vocab = reference `output_categories` ∪ `reference_label_mappings`/`reference_composite_mappings`/`reference_decile_mappings` values ∪ `mappings[*].schema_label` ∪ `reference_none_default`. Skips `id`/`age` (non-categorical) and pipeline-only blocks (istat `ethnicity`/`urbanization`/`income_source`, auto-skipped by the dual-handler gate). Covers ~14 (SE) / 13 (IT) attributes. **Both countries pass.**

**Finding surfaced by the guard:** the Swedish `parental_structure` keyword rules reuse the shared (Italian-derived) cascade, which carries an `"Extended Family"` rule, but the Swedish reference (SCB `Familjetyp`, 4 categories) has no Extended-Family bucket — so a Swedish persona whose free text says "extended"/"multigenerational" maps to a label the SE reference can never score. This is a genuine (pre-existing) cross-side drift. It is recorded as a single documented `_KNOWN_DRIFT` exception so the test passes per directive while any *new* drift still fails; flagged for a follow-up review (prune the rule from SE config, or treat as a non-scored residue) — not changed here (behaviour edit outside this phase's scope).

**Files Modified:**
- `src/population_synth/comparison/extract/batch.py` — config-sourced labels/city tables; batch-local input-alias constants; new `mappings` param.
- `src/population_synth/comparison/extract/schema_labels.py` — deleted 9 orphaned constants (6 label lists + 3 city tables).
- `src/population_synth/comparison/synthetic_mapper/base.py` — pass `self.mappings` into `_extract_batch`; drop dead `pipeline_native` artifact.
- `config/mapping/scb/*.json`, `config/mapping/istat/*.json` — removed the dead `pipeline_native` key (28 blocks).
- `tests/test_synthetic_reference_vocab_subset.py` — new guard test.

**Dependencies:** Phase 5

---

## Testing Plan

### Unit Tests
- [ ] Unknown `pipeline_handler` kind raises `ValueError`.
- [ ] Mappings set with no declaring block raises `ValueError`.
- [ ] `passthrough`, `numeric_gate` (incl. `_SKIP` on non-int age), `text_coded` (each resolution tier + each `pipeline_on_miss` policy), `numeric_bucket` (overflow), `cross_field_coded` (domestic + refinement) behave per config.

### Integration Tests
- [x] `tests/test_extractor_characterization.py` green for `persona_batch_se`, `persona_flat_se`, `persona_flat_it` (behaviour-preserving except Nordic).
- [x] Vocabulary-subset guard passes for every registered attribute, both countries.

### Manual Verification
- [ ] Run `extract_population` on an existing pipeline `seed_root` before vs after; diff per-attribute value counts — only intended difference is SE `birth_location` gaining `"Nordic Country"`.
- [ ] `ruff check src/` clean.

### Edge Cases
- [ ] Persona with missing/non-int age → skipped (gate).
- [ ] Italian `employment_type` arbitrary pipe combo → passthrough.
- [ ] Free-text value matching nothing → `"Non-standard label"` + `unmapped` record (or silenced where configured).
- [ ] Already-canonical LLM output → exact passthrough (no double-mapping).

---

## Documentation Plan

- [ ] Update `CLAUDE.md` `synthetic_mapper/` description to document the `pipeline_handler` config-discovery mechanism (mirroring the existing `reference_handler` writeup).
- [ ] Update the `config/mapping/{scb,istat}/README.md` files to document the `pipeline_*` role keys.
- [ ] Update inline module docstrings in `synthetic_mapper/base.py` to mirror the reference engine's docstring style.

---

## Rollback Plan

1. **Before merge:** all work is on `feature/synthetic-mapper-config-driven`; abandoning the branch reverts everything.
2. **Data considerations:** no migrations; config edits are additive (`pipeline_*` keys) until Phase 5 deletes Python constants — JSON files remain valid for the reference mapper at every step.
3. **Rollback procedure:** `git checkout feature/reference-mapper-fully-field-agnostic` and delete the feature branch; or revert the merge commit. The reference mapper is never touched, so reference-side behaviour cannot regress.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Keyword-cascade ordering subtly re-buckets values when moved to `pipeline_keyword_rules` | Med | High | Migrate attr-by-attr; keep golden green + run distribution diff after each attribute (Phase 3) |
| Golden fixtures need updating for the intended Nordic change | High | Low | Expected; update fixture for the single SE `birth_location` delta with review |
| Batch coherence logic accidentally coupled to a deleted constant | Med | Med | Rewire `batch.py` imports first (Phase 6.1) and run the `persona_batch_se` golden |
| Italian `SILENT_UNMAPPED` removal changes output keys vs golden | Med | Med | Default to preserving current keys via config flags; defer the cleaner omission to a separate reviewed change |
| Reference mapper inadvertently affected by shared-file edits | Low | High | Only additive `pipeline_*` keys; assert `reference_*` keys unchanged (Phase 1.3); reference engine reads only `reference_*` |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 | Small | None |
| Phase 2 | Medium | Phase 1 |
| Phase 3 | Large | Phase 2 |
| Phase 4 | Small | Phase 3 |
| Phase 5 | Small | Phase 4 |
| Phase 6 | Medium | Phase 5 |

---

## References

- Reference engine (read-only template): `src/population_synth/comparison/reference_mapper/base.py`, `factory.py`
- Related plans: `docs/development/plans/pending/fix-identity-comparison-divergences.md`, `docs/development/plans/pending/report-unmapped.md`
- Approved design scratch: `C:\Users\basil\.claude\plans\analyse-how-the-database-encapsulated-frog.md`

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
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
- config/mapping/istat/id.json
- config/mapping/istat/income_source.json
- config/mapping/istat/industry_sector.json
- config/mapping/istat/parental_structure.json
- config/mapping/istat/region.json
- config/mapping/istat/socioeconomic.json
- config/mapping/istat/urbanization.json
- config/mapping/scb/age.json
- config/mapping/scb/biological_sex.json
- config/mapping/scb/birth_country_detail.json
- config/mapping/scb/birth_location.json
- config/mapping/scb/civil_status.json
- config/mapping/scb/education.json
- config/mapping/scb/employment.json
- config/mapping/scb/employment_type.json
- config/mapping/scb/ethnicity.json
- config/mapping/scb/household_size.json
- config/mapping/scb/id.json
- config/mapping/scb/income_source.json
- config/mapping/scb/industry_sector.json
- config/mapping/scb/parental_structure.json
- config/mapping/scb/region.json
- config/mapping/scb/socioeconomic.json
- config/mapping/scb/urbanization.json
- docs/development/plans/active/refactor-synthetic-mapper-config-driven.md
- src/population_synth/comparison/extract/batch.py
- src/population_synth/comparison/extract/schema_labels.py
- src/population_synth/comparison/synthetic_mapper/base.py
- src/population_synth/comparison/synthetic_mapper/factory.py
- src/population_synth/comparison/synthetic_mapper/italy.py
- src/population_synth/comparison/synthetic_mapper/sweden.py
- tests/test_synthetic_mapper_base.py
- tests/test_synthetic_reference_vocab_subset.py

---
