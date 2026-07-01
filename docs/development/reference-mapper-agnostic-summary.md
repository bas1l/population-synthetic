# Summary — Making `reference_mapper`'s base class field- and label-agnostic

**Branch:** `feature/db-grounded-comparison-scheme` · **Date:** 2026-06-30
**Plan:** `docs/development/plans/completed/reference-mapper-agnostic-base.md`

## Goal

`comparison/reference_mapper/base.py` was billed as the country-agnostic shared layer
but leaked concrete database knowledge. The task, in two requests:

1. The base class must be **agnostic to database fields** — no SCB-named mapping
   sub-keys, no hardcoded field set in the orchestrator.
2. The base class must also be **agnostic to any labels** — no canonical category
   strings in code, and no privileged domestic-birth handling.

`AbstractReferenceMapper` was already a clean contract; both leaks were in the
concrete `BaseReferenceMapper`.

## What was wrong

- **Source-system sub-keys baked into shared code.** `base.py` read
  `mappings.get("education", {}).get("sun2020_level_mappings", {})`,
  `.get("aku_label_mappings")`, `.get("scb_label_mappings")`, etc. — keys named after
  Swedish systems (SUN2020, AKU, SCB). They exist only in `config/mapping/scb/`, so for
  Italy every lookup returned `{}` and the mapper silently passed raw values through.
  It only "worked" because the ISTAT reference is already pre-coded to schema labels.
- **The orchestrator hardcoded the field set** as 14 `rec["biological_sex"] = …` lines.
- **Canonical labels hardcoded in code:** `"Male"`/`"Female"`, the
  `"Permanent Full-time"`/`"Self-Employed"` employment-type table, `"Not Applicable"`
  defaults.
- **Privileged domestic handling:** `DOMESTIC_NAME` / `DOMESTIC_BIRTH_LABELS` class
  attributes plus a bespoke `map_birth_country_detail`, only because the domestic raw
  label (`"born in Sweden"`) was missing from its own mapping table.

## What changed

### Config (`config/mapping/{scb,istat}/`)
- Renamed every reference-mapper sub-key to a **role-based** name, identical across
  countries (these keys are read only by `base.py`):
  - `sun2020_level_mappings` / `aku_label_mappings` / `scb_label_mappings` /
    `region_label_mappings` → `reference_label_mappings`
  - `attachment_label_mappings` / `hours_label_mappings` →
    `reference_attachment_mappings` / `reference_hours_mappings`
  - `scb_decile_mappings` → `reference_decile_mappings`
  - `parental_structure` `mappings[*].scb_codes` → `reference_codes`
- Moved all remaining labels out of code into the JSON:
  - new `biological_sex.json` (scb + istat) with `reference_label_mappings`
  - `employment_type.json`: `reference_composite_mappings` (the combination table) +
    `reference_none_default`
  - `industry_sector.json`: `reference_none_default`
  - `birth_country_detail.json`: domestic raw labels (`"born in Sweden"`, `"Sverige"`,
    …) added as ordinary `reference_label_mappings` entries

ISTAT files needed almost nothing renamed (that reference is pre-coded → passthrough);
the rename was SCB-only.

### Code (`src/population_synthetic/comparison/reference_mapper/`)
- **`base.py`** rewritten:
  - `__init__` builds all lookups from the uniform role-based keys via a small
    declarative table (`_LABEL_ATTRS`, `_MAPPING_BLOCK` for the two files whose stem
    differs from the attribute name).
  - `normalize_individual` loops over an `attr -> handler` registry — no field name
    appears as an imperative literal.
  - Contains **no canonical category string**; only structural tokens remain
    (`label`/`code`/`decile`, `attachment`/`hours`, the `|` separator, role keys).
  - Deleted `map_biological_sex`, `map_birth_country_detail`, and the `DOMESTIC_*`
    attributes.
- **`AbstractReferenceMapper`** now declares only `MAPPINGS_SUBDIR` +
  `normalize_individual`.
- **`sweden.py` / `italy.py`** reduced to a single `MAPPINGS_SUBDIR` attribute each.

### Docs
- `CLAUDE.md` and `docs/database_mapper_philosophy.md` updated to describe the
  field-/label-agnostic base and the single remaining per-country attribute.
- Plan archived at `docs/development/plans/completed/reference-mapper-agnostic-base.md`.

## A real bug caught mid-refactor

The mapping file *stem* differs from the schema *attribute name* for
`education`→`education_level`, `employment`→`employment_status`,
`socioeconomic`→`socioeconomic_class`. The first generic-loop version read
`mappings.get(attr)` and missed the block, producing raw labels. Fixed with the
`_MAPPING_BLOCK` indirection (record field uses the attribute name; mapping lookup
uses the file stem).

## Verification

- **Behavioural equivalence:** the refactored mapper's distinct output per attribute is
  identical to the pre-refactor `_scheme.json` category sets for both the SCB (n=10000)
  and ISTAT (n=10000) references.
- `pytest`: 69 passed. `ruff` on `reference_mapper/`: clean.

## Files touched

- `src/population_synthetic/comparison/reference_mapper/{base,sweden,italy}.py`
- `config/mapping/scb/*.json` (13 files renamed; `biological_sex.json` added;
  `employment_type`/`industry_sector`/`birth_country_detail` extended)
- `config/mapping/istat/{biological_sex,employment_type,industry_sector,birth_country_detail}.json`
- `CLAUDE.md`, `docs/database_mapper_philosophy.md`
- `docs/development/plans/completed/reference-mapper-agnostic-base.md`

## Deferred

- Scheme-driven **hard validation** (raise when a reference label falls outside
  `_scheme.json`). Kept separate; the silent-passthrough behaviour is unchanged.
- The vestigial `scb_codes` in non-parental SCB files (not read by the reference
  mapper) were left alone to avoid touching population generation.

## Not done

- Nothing is committed. Changes are working-tree only.

---

## Follow-up (2026-06-30): fully field-agnostic via self-declaration

**Plan:** `docs/development/plans/active/reference-mapper-fully-field-agnostic.md`
**Branch:** `feature/reference-mapper-fully-field-agnostic`

The refactor above made the orchestrator loop over a registry, but that registry was still
a hardcoded column of field literals in `base.py` — `_LABEL_ATTRS` (11 field names),
`_MAPPING_BLOCK` (`education`/`employment` stem→attr), the literal `_handlers` keys
(`id`/`age`/`socioeconomic_class`/`parental_structure`/`employment_type`), and three
field-named methods (`map_socioeconomic`, `map_parental_structure`, `map_employment_type`).
The leak had been relocated, not removed.

### What changed now

- **`base.py` is a generic handler-kind engine.** It holds a fixed library of five generic
  *handler kinds* keyed by algorithm name (never by field): `passthrough`, `label`,
  `composite`, `decile_coded`, `substring_coded`. Each is a factory
  `(attr, block) -> Callable[[record], value]` that closes over the output schema attribute
  and that attribute's own mapping block.
- **The field set is discovered from config.** Each per-attribute mapping JSON self-declares
  `"reference_handler": "<kind>"` (and `"reference_attr"` when the file stem differs from the
  schema attribute). `__init__` scans the loaded mappings and registers one handler per block
  that declares a `reference_handler`; blocks without it (`_scheme` and the synthetic-only
  `age_groups`/`ethnicity`/`urbanization` files) are skipped. Adding/removing a comparison
  field is now a config-only change.
- **Removed all residual field literals:** `_LABEL_ATTRS`, `_MAPPING_BLOCK`, and the three
  field-named methods are gone. `base.py` (both classes) contains zero field-name strings —
  only role sub-keys and handler-kind names remain. Two stub files (`id.json`, `age.json`,
  each `{"reference_handler": "passthrough"}`) were added to both `config/mapping/{scb,istat}/`.
- **Fail-fast:** unknown handler kind, or no block declaring a handler, raises `ValueError`.

### Behavioural verification

Diffed the post-refactor output against the pre-refactor golden snapshot over the real
SCB (n=10000) and ISTAT (n=10000) references, per-attribute distinct sets *and* full
per-record dicts:

- **SCB:** byte-identical — distinct sets and all 10000 records.
- **ISTAT:** identical except **one documented, harmless change** — the `income_source`
  key, which Italy's reference never populates (always `None`), is now **absent** from each
  output record rather than present-with-`None`. ISTAT has no `income_source.json` and
  `_scheme.json` already excludes it, so nothing downstream relies on the key. All other
  attributes' distinct sets and record values are identical.

Each country's per-attribute distinct set is a subset of its `_scheme.json` categories
(reported, not hard-validated — scheme hard validation remains deferred). `pytest`: 69
passed. `ruff check` on `base.py`: clean.
