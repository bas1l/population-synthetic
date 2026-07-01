# Plan: Make `BaseReferenceMapper` / `AbstractReferenceMapper` fully field-agnostic

**Date:** 2026-06-30
**Author:** Basil
**Status:** Completed
**Completed:** 2026-06-30 21:55
**Base Branch:** `feature/db-grounded-comparison-scheme`
**Branch:** `feature/reference-mapper-fully-field-agnostic`

---

## Overview

Make `comparison/reference_mapper/base.py` genuinely agnostic of which demographic
fields the reference database provides: the two base classes should define only the
API/contract and a generic processing engine, while the field set and each field's
processing algorithm live entirely in config. Achieved by having each per-attribute
mapping JSON **self-declare** a `reference_handler` kind, with the base discovering the
field set by scanning for that key.

## Problem Statement

The prior refactor (`docs/development/reference-mapper-agnostic-summary.md`) bills
`BaseReferenceMapper` as "field-agnostic", but the class still hardcodes the entire
database field set in code:

- `_LABEL_ATTRS` — a tuple of 11 field names (`biological_sex`, `education_level`, …)
- `_MAPPING_BLOCK` — `{"education_level": "education", "employment_status": "employment"}`
- the `_handlers` registry — literal keys `"id"`, `"age"`, `"socioeconomic_class"`,
  `"parental_structure"`, `"employment_type"`
- three field-named methods (`map_socioeconomic`, `map_parental_structure`,
  `map_employment_type`) that each know a specific field's coded structure

The "declarative registry it loops over" is itself a column of field literals baked into
the shared class — so the leak was relocated, not removed. This matters because the base
is supposed to be the country-agnostic, field-agnostic API layer: adding or removing a
comparison field should be a config-only change, and a new country should never need to
touch `base.py`. Today it would.

## Goals

### In Scope
1. `BaseReferenceMapper` and `AbstractReferenceMapper` contain **zero field-name literals**
   — only role sub-keys (`reference_label_mappings`, …) and handler-kind names remain.
2. The field set + each field's handler kind is declared in config (data), discovered at
   construction; adding/removing a field requires no code change.
3. Behavioural equivalence: per-attribute distinct outputs over the real SCB and ISTAT
   references are unchanged (one documented, harmless exception — see below).
4. Fail-fast on malformed config (unknown handler kind; no declared fields).

### Out of Scope
- Scheme-driven **hard validation** (raising when a reference label falls outside
  `_scheme.json`) — already deferred in the prior summary; silent passthrough is unchanged.
- Any change to `synthetic_mapper/` (intentionally per-attribute and country-divergent),
  the evaluator, charts, or the compare scripts.
- Touching the synthetic-only mapping files (`age_groups.json`, `ethnicity.json`,
  `urbanization.json`) beyond leaving them without a `reference_handler` key.

## Success Criteria

- [x] No field name appears as a string literal in `base.py` (both classes).
- [x] `AbstractReferenceMapper` remains a pure contract (`MAPPINGS_SUBDIR` + abstract
      `normalize_individual`), unchanged.
- [x] Per-country, per-attribute `sorted(set(values) - {None})` from the refactored mapper
      equals the pre-refactor golden snapshot for SCB and ISTAT.
- [x] Per-record output dicts are identical except the documented ISTAT `income_source`
      key-absence difference.
- [~] `pytest` green (existing 69 still pass) and `ruff check src/` clean. — pytest 69 passed;
      `ruff` clean on `base.py` (the only src file this plan changed) but NOT on full `src/`:
      17 pre-existing errors remain in unrelated working-tree files (`normalizers_se.py`,
      `factory.py`, `loader.py`, `gui/*`) from the broader branch, out of this plan's scope.
- [x] New fail-fast unit tests pass. — `tests/test_reference_mapper_base.py` adds 3 tests
      (no-declaring-block, unknown-kind, passthrough); full suite now 72 passed, ruff clean.

---

## Technical Design

### Approach

Turn `BaseReferenceMapper` into a **generic handler-kind engine**. The class holds a fixed
library of generic *handler kinds* keyed by algorithm name (never by field), each a factory
`(attr, block) -> Callable[[record], value]` that closes over the attribute name and that
attribute's own mapping block. The field→handler binding lives in config: each per-attribute
JSON self-declares `"reference_handler": "<kind>"` (and `"reference_attr"` when the output
schema key differs from the file stem). `__init__` scans the loaded mappings and registers a
handler for every block that declares one.

Selected over the central-manifest alternative (user decision): each field's full contract —
labels *and* algorithm — stays in one file, and discovery-by-key naturally excludes the
synthetic-only mapping files that lack `reference_handler`.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Self-declaring files (`reference_handler` per JSON) | Each field owns its full contract in one place; discovery auto-excludes synthetic-only files; new field = new file, zero code | `id`/`age` need stub files; a missing field is silent (not fail-fast) | **Chosen** |
| Central `_reference_fields.json` manifest per country | One ordered list = whole schema; clean `id`/`age` rows; fail-fast on missing field | Splits attr↔block knowledge from the tables; extra file type | Rejected |
| Keep hardcoded registry (status quo) | No work | Not field-agnostic; new country/field edits `base.py` | Rejected |

### Architecture Changes

`base.py` — delete `_LABEL_ATTRS`, `_MAPPING_BLOCK`, and the three field-named methods.
Add a class-level `_HANDLER_KINDS: ClassVar[dict[str, Callable]]` of five generic factories,
all sharing the `(attr, block)` signature:

- `passthrough(attr, block)` → `lambda r: r.get(attr)` (covers `id`, `age`)
- `label(attr, block)` → current `_label_handler` logic (`reference_label_mappings` CI lookup
  + `reference_none_default`)
- `composite(attr, block)` → current `map_employment_type` logic, reading `attr`; keeps the
  already-composite `|` passthrough and never consults the `mappings` block
- `decile_coded(attr, block)` → current `map_socioeconomic` logic (decile CI map, numeric
  `Decile N` fallback, `mappings[*].reference_codes`, raw passthrough)
- `substring_coded(attr, block)` → current `map_parental_structure` + `_match_parental` logic

`__init__` builds the registry by scanning:

```python
self._handlers = {}
for stem, block in mappings.items():
    if not isinstance(block, dict) or "reference_handler" not in block:
        continue                       # skips _scheme, age_groups, ethnicity, urbanization
    kind = block["reference_handler"]
    factory = self._HANDLER_KINDS.get(kind)
    if factory is None:
        raise ValueError(f"Unknown reference handler kind {kind!r} in {stem!r}")
    attr = block.get("reference_attr", stem)   # output schema key
    self._handlers[attr] = factory(attr, block)
if not self._handlers:
    raise ValueError("reference mapper found no fields declaring 'reference_handler'")
```

The handler reads `record.get(attr)` (schema attr, e.g. `education_level`) while its tables
come from `block` (the `education.json` content) — resolving stem ≠ attr with no
`_MAPPING_BLOCK`. `normalize_individual` body is unchanged. `AbstractReferenceMapper`,
`sweden.py`, `italy.py`, `factory.py`, `loader.py`, `mappings.py`, `__init__.py` are untouched.

**Config self-declaration** (additive keys; the synthetic side reading `pipeline_label_mappings`
is unaffected):

```
label:           biological_sex, birth_location, region, civil_status, industry_sector,
                 housing_tenure, household_size, income_source (scb only), birth_country_detail
label + reference_attr: education.json→education_level, employment.json→employment_status
decile_coded + reference_attr: socioeconomic.json→socioeconomic_class
substring_coded: parental_structure.json
composite:       employment_type.json
passthrough:     new stub id.json, age.json  →  { "reference_handler": "passthrough" }
```

---

## Implementation Plan

### Phase 1: Config self-declaration
**Goal:** Every reference-emitted field declares its handler in config.

- [x] 1.1 — Add `reference_handler` (+ `reference_attr` where stem ≠ attr) to each SCB
      attribute JSON per the table above.
- [x] 1.2 — Add the same to each ISTAT attribute JSON, **omitting** `income_source` (no such
      file in Italy; `_scheme.json` already excludes it).
- [x] 1.3 — Add stub `id.json` and `age.json` (`{"reference_handler": "passthrough"}`) to both
      `config/mapping/scb/` and `config/mapping/istat/`.

**Files Modified:**
- `config/mapping/scb/*.json` (14 attribute files) + new `id.json`, `age.json`
- `config/mapping/istat/*.json` (13 attribute files) + new `id.json`, `age.json`

**Dependencies:** None

### Phase 2: Capture golden snapshot (pre-refactor)
**Goal:** Lock in current behaviour before touching `base.py`.

- [x] 2.1 — Scratchpad script: for SCB and ISTAT, `load_reference_population` →
      `normalize_population` over `data/scb_api/scb_population_pop-10000_02.json` and
      `data/istat_api/istat_population.json`; dump per-attribute distinct sets and the full
      per-record output list to the scratchpad.

**Files Modified:** none (scratchpad only)

**Dependencies:** None (run on current `base.py`)

### Phase 3: Rewrite the engine
**Goal:** `base.py` becomes field-literal-free.

- [x] 3.1 — Add `_HANDLER_KINDS` with the five generic factories (verbatim lifts of current
      algorithms, parameterized by `attr`).
- [x] 3.2 — Replace `__init__` with the scanning registry build; delete `_LABEL_ATTRS`,
      `_MAPPING_BLOCK`, `_label_handler`, `map_socioeconomic`, `_match_parental`,
      `map_parental_structure`, `map_employment_type`.
- [x] 3.3 — Update the `base.py` module docstring to describe discovery-by-`reference_handler`.

**Files Modified:**
- `src/population_synth/comparison/reference_mapper/base.py`

**Dependencies:** Phase 1

### Phase 4: Verify + document
**Goal:** Prove equivalence and update the prose.

- [x] 4.1 — Re-run the Phase 2 snapshot; diff (expect identical except ISTAT `income_source`
      key dropped). — PASS: SCB byte-identical (distinct + 10000 records); ISTAT identical
      except the documented `income_source` key-absence (distinct + 10000 records).
- [x] 4.2 — `pytest` (69 passed), `ruff check src/` (`base.py` clean; pre-existing unrelated
      errors remain elsewhere — see Success Criteria note).
- [x] 4.3 — Update `CLAUDE.md` reference-mapper paragraph, `docs/database_mapper_philosophy.md`,
      and append a follow-up note to `docs/development/reference-mapper-agnostic-summary.md`.

**Files Modified:**
- `CLAUDE.md`, `docs/database_mapper_philosophy.md`,
  `docs/development/reference-mapper-agnostic-summary.md`

**Dependencies:** Phase 3

---

## Testing Plan

### Unit Tests
- [x] Mappings with no block declaring `reference_handler` → `ValueError`.
- [x] An unknown `reference_handler` value → `ValueError`.
- [x] A `passthrough` stub emits the raw record value for that attr.

  Added in `tests/test_reference_mapper_base.py` (`test_no_declaring_block_raises`,
  `test_unknown_handler_kind_raises`, `test_passthrough_handler_emits_raw_value`);
  construct `BaseReferenceMapper` directly with minimal synthetic `mappings` dicts.

### Integration Tests
- [x] SCB: per-attribute distinct-output sets equal the golden snapshot; each set ⊆
      `config/mapping/scb/_scheme.json` categories. — verified via `phase4_verify.py`.
- [x] ISTAT: same, with the documented `income_source` key-absence difference. — verified;
      all distinct values also ⊆ `config/mapping/istat/_scheme.json`.

### Manual Verification
- [~] Run a compare script end-to-end (e.g. `compare_pipeline_to_istat.py`) and confirm it
      produces a report without error. — Partial: confirmed `get_reference_mapper('swedish')`
      and `get_reference_mapper('italian')` import + construct without error and discover the
      expected handler sets (Italian correctly omits `income_source`). Full end-to-end compare
      not run (needs pipeline output / live data not available here).

### Edge Cases
- [ ] ISTAT `socioeconomic`/`parental_structure` (empty code tables) fall through to
      passthrough, matching pre-coded behaviour.
- [ ] employment_type already-composite `"Permanent|Full-time"` string passes through unchanged.
- [ ] Unrecognised raw value returns verbatim for every handler kind.

---

## Documentation Plan

- [x] Update `CLAUDE.md` — reference-mapper paragraph (registry now config-discovered).
- [x] Update `docs/database_mapper_philosophy.md` — field-agnostic-via-self-declaration.
- [x] Append follow-up note to `docs/development/reference-mapper-agnostic-summary.md`.
- [x] `base.py` module docstring rewritten (Phase 3.3).

---

## Rollback Plan

1. Before merge: changes confined to one feature branch; revert by deleting the branch.
2. Data considerations: no migrations; config edits are additive keys and two new stub files.
3. Rollback procedure: `git revert` the implementation commit(s); `base.py` and the JSON
   edits revert together. No state/cache reset needed (PxWeb caches untouched).

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Subtle behaviour drift when lifting `map_*` into generic factories | Med | High | Golden snapshot diff (Phase 2/4) over real 10k references, per-record equality |
| Output key order changes (alphabetical by stem) breaks a consumer | Low | Low | Consumers use `ind.get(attr)`; dict order is irrelevant to evaluator/scheme |
| ISTAT `income_source` key-absence surprises a caller | Low | Low | `_scheme.json` excludes it; `attr_value`/`ind.get` treat absent == None; documented |
| Adding `id.json`/`age.json` perturbs synthetic-side `load_mappings` | Low | Med | Synthetic code reads specific keys; extra stems are inert; verify via pytest |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 (config) | ~30 JSON edits, small | None |
| Phase 2 (snapshot) | small script | None |
| Phase 3 (engine) | one-file rewrite | Phase 1 |
| Phase 4 (verify+docs) | small | Phase 3 |

---

## References

- Prior work: `docs/development/reference-mapper-agnostic-summary.md`,
  `docs/development/plans/completed/reference-mapper-agnostic-base.md`
- Related: `docs/database_mapper_philosophy.md`, `src/population_synth/comparison/scheme.py`
- Internal scratch plan: `.claude/plans/analyse-docs-development-reference-mappe-elegant-waterfall.md`

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- CLAUDE.md
- config/mapping/istat/age.json
- config/mapping/istat/birth_country_detail.json
- config/mapping/istat/birth_location.json
- config/mapping/istat/biological_sex.json
- config/mapping/istat/civil_status.json
- config/mapping/istat/education.json
- config/mapping/istat/employment.json
- config/mapping/istat/employment_type.json
- config/mapping/istat/household_size.json
- config/mapping/istat/housing_tenure.json
- config/mapping/istat/id.json
- config/mapping/istat/industry_sector.json
- config/mapping/istat/parental_structure.json
- config/mapping/istat/region.json
- config/mapping/istat/socioeconomic.json
- config/mapping/scb/age.json
- config/mapping/scb/birth_country_detail.json
- config/mapping/scb/birth_location.json
- config/mapping/scb/biological_sex.json
- config/mapping/scb/civil_status.json
- config/mapping/scb/education.json
- config/mapping/scb/employment.json
- config/mapping/scb/employment_type.json
- config/mapping/scb/household_size.json
- config/mapping/scb/housing_tenure.json
- config/mapping/scb/id.json
- config/mapping/scb/income_source.json
- config/mapping/scb/industry_sector.json
- config/mapping/scb/parental_structure.json
- config/mapping/scb/region.json
- config/mapping/scb/socioeconomic.json
- docs/database_mapper_philosophy.md
- docs/development/plans/active/reference-mapper-fully-field-agnostic.md
- docs/development/reference-mapper-agnostic-summary.md
- src/population_synth/comparison/reference_mapper/base.py
- tests/test_reference_mapper_base.py
