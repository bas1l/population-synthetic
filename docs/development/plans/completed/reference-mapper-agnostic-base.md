# Make the reference mapper's base class field-agnostic

**Status: completed (2026-06-30).** SCB sub-keys renamed to role-based names;
`base.py` rewritten to a declarative `attr -> handler` registry with a generic
label-lookup loop. Verified: refactored mapper output is identical to pre-refactor
for both the SCB (n=10000) and ISTAT (n=10000) references (every produced category
set equals its `_scheme.json` list); 69 tests pass; `reference_mapper/` lints clean.
One subtlety handled: the mapping file stem differs from the schema attribute name for
`education`/`employment` (and `socioeconomic`), so the generic loop maps the attribute
name to its mapping block via `_MAPPING_BLOCK`.

## Problem

`comparison/reference_mapper/base.py` is presented as the country-agnostic shared
layer, but `BaseReferenceMapper` leaks concrete database-field knowledge in two ways:

1. **SCB-named mapping sub-keys baked into shared code.**
   `mappings.get("education", {}).get("sun2020_level_mappings", {})`,
   `.get("aku_label_mappings", …)`, `.get("scb_label_mappings", …)`, etc. These
   keys are named after the *Swedish source systems* (SUN2020, AKU, SCB), so they
   only exist in `config/mapping/scb/*.json`. The ISTAT files use a different shape,
   so for Italy every `.get(...)` returns `{}` and the mapper silently falls back to
   passing the raw value through. The "one shared loop serves every country" claim is
   only true by accident (the ISTAT reference is already pre-coded to schema labels,
   so passthrough happens to be correct).

2. **The orchestrator hardcodes the field set line-by-line.**
   `normalize_individual` contains 14 `rec["biological_sex"] = …`,
   `rec["education_level"] = …` assignments — the schema contract baked into an
   imperative method.

The `AbstractReferenceMapper` contract itself is already clean (3 class attributes +
one `@abstractmethod`); the leak is entirely in the concrete `BaseReferenceMapper`.

## Key facts established

- The reference-mapper-only sub-keys (`sun2020_level_mappings`, `aku_label_mappings`,
  `scb_label_mappings`, `region_label_mappings`, `attachment_label_mappings`,
  `hours_label_mappings`, `scb_decile_mappings`, and `mappings[*].scb_codes` for
  `parental_structure`) are read **only** by `base.py`. `pipeline_label_mappings`,
  `output_categories`, `isced_levels`/`ilo_codes`, and `mappings[*].schema_label`
  belong to the synthetic side or generation and must not be touched.
- The ISTAT reference (`data/istat_api/istat_population.json`) already emits canonical
  schema labels ("University Degree", "Employed", "Married"); the SCB reference
  (`data/scb_api/scb_population_pop-10000_02.json`) emits raw coded labels
  ("post-graduate education (ISCED97 6)", "employed", "widowers/widows"). So Sweden
  needs real translation tables; Italy needs passthrough.

## Design

Name the mapping sub-keys for their **role in the reference pipeline**, not for the
source system that produced them, and drive the orchestrator from a declarative
handler registry instead of 14 hardcoded lines.

- One uniform label table per simple attribute: `reference_label_mappings`
  (replaces `sun2020_level_mappings` / `aku_label_mappings` / `scb_label_mappings` /
  `region_label_mappings`).
- `employment_type`: `reference_attachment_mappings` + `reference_hours_mappings`.
- `socioeconomic`: `reference_decile_mappings`; `mappings[*].reference_codes`.
- `parental_structure`: `mappings[*].reference_codes`.

Because the ISTAT files are pre-coded, they need **no** `reference_*` blocks — base
reads `{}` and the already-correct schema label passes through. So the JSON rename
touches SCB files only.

`BaseReferenceMapper` becomes:
- `__init__` builds a generic `attr -> label-map` dict by reading the uniform
  `reference_label_mappings` key for every simple attribute, plus prepared structures
  for the few special attributes.
- A declarative `attr -> handler` registry (ordered so `birth_location` precedes
  `birth_country_detail`). The default handler is the generic label lookup; the
  special attributes (`biological_sex`, `socioeconomic_class`, `parental_structure`,
  `employment_type`, `birth_country_detail`) keep their existing named methods — this
  is genuine, country-neutral processing logic that belongs in the concrete base.
- `normalize_individual` loops over the registry: `rec[attr] = handler(record, rec)`.
  No attribute name, no source-system key, appears as an imperative literal.

Output of `normalize_individual` is **byte-for-byte unchanged** — same keys, same
values, same defaults — so `evaluator.py`, the compare scripts, and the tests are
unaffected.

## Steps

1. Rename sub-keys in `config/mapping/scb/`:
   - `education.json`: `sun2020_level_mappings` -> `reference_label_mappings`
   - `employment.json`: `aku_label_mappings` -> `reference_label_mappings`
   - `birth_location.json`: `region_label_mappings` -> `reference_label_mappings`
   - `region/civil_status/industry_sector/housing_tenure/household_size/income_source/birth_country_detail.json`:
     `scb_label_mappings` -> `reference_label_mappings`
   - `employment_type.json`: `attachment_label_mappings` -> `reference_attachment_mappings`,
     `hours_label_mappings` -> `reference_hours_mappings`
   - `socioeconomic.json`: `scb_decile_mappings` -> `reference_decile_mappings`
   - `parental_structure.json`: `mappings[*].scb_codes` -> `reference_codes`
2. Rewrite `base.py`: generic label-map construction + handler registry + loop-based
   `normalize_individual`. Keep `AbstractReferenceMapper` unchanged.
3. Verify: `pytest` green; run an SCB and an ISTAT comparison smoke test and confirm
   the normalized output is identical to pre-refactor.

## Phase 2 — label-agnostic base (completed 2026-06-30)

Follow-up: `BaseReferenceMapper` must also hold **no canonical category label**, and
the domestic-birth collapse must not be privileged over other fields.

- Moved every remaining hardcoded label into the mapping JSON:
  - `biological_sex` "Male"/"Female" -> new `config/mapping/{scb,istat}/biological_sex.json`
    (`reference_label_mappings`); the attribute now uses the generic label handler.
  - `employment_type` combination table ("Permanent Full-time" etc.) ->
    `reference_composite_mappings`; the "Not Applicable" fallback -> `reference_none_default`.
  - `industry_sector` "Not Applicable" fallback -> `reference_none_default`.
- Domestic-birth collapse is now data: the domestic raw labels ("born in Sweden",
  "Sverige", …) are ordinary `reference_label_mappings` entries in
  `birth_country_detail.json`. This let `map_birth_country_detail`, `map_biological_sex`,
  and the `DOMESTIC_NAME`/`DOMESTIC_BIRTH_LABELS` class attributes be **deleted**.
  `AbstractReferenceMapper` now declares only `MAPPINGS_SUBDIR` + `normalize_individual`;
  the country subclasses hold only `MAPPINGS_SUBDIR`. (Note: with the domestic collapse
  data-driven, `birth_country_detail` no longer depends on `birth_location`, so the
  handler signature simplified to `handler(record)` and the registry no longer needs a
  dependency order.)
- `base.py` now contains no canonical category string (verified by grep); only
  structural tokens remain (`label`/`code`/`decile`, `attachment`/`hours`, the `|`
  composite separator, the role-based sub-key names).

Re-verified: SCB + ISTAT normalized output still identical to the scheme; 69 tests
pass; `reference_mapper/` lints clean. Docs updated (`CLAUDE.md`,
`database_mapper_philosophy.md`).

## Out of scope (deferred)

- Scheme-driven hard validation (raise when a reference label falls outside
  `_scheme.json` categories). Discussed but kept separate; the silent-passthrough wart
  is unchanged by this refactor. See `report-unmapped.md`.
- Renaming the vestigial `scb_codes` in non-parental SCB files (not read by the
  reference mapper; left alone to avoid touching generation).
