# Plan: Homogenize ground-truth vs generated naming onto `real` / `synthetic`

**Date:** 2026-07-01
**Author:** Basil
**Status:** In Progress
**Base Branch:** `dev`
**Branch:** `feature/homogenize-real-synthetic-naming`

---

## Overview

The ground-truth (national-statistics) population concept is named **two** different
ways today — `reference` in code identifiers and `database` in the JSON config block
key, comparison-script variables, output artifacts, one dispatcher script, and one
philosophy doc. Collapse **both** onto a single term, **`real`**, so the codebase has
exactly one symmetric antonym pair: **`real` ↔ `synthetic`**. All identifiers stay
**bare** — no `_data` suffix anywhere. Along the way, reconcile two pre-existing
asymmetries between the two mapper sides (loader verbs and the concept split itself).

## Problem Statement

The concept "real demographic data fetched from national statistics APIs (SCB/ISTAT/
SSB), used as the comparison ground truth" carries two competing names:

- **`reference`** — the code layer: `generators/reference/`, `analysis/mapping/
  reference_mapper/`, `AbstractReferenceMapper`/`BaseReferenceMapper`/
  `SwedishReferenceMapper`/`ItalianReferenceMapper`, `get_reference_mapper`,
  `load_reference_population`, `reference_pop` (≈189 occurrences across ≈53 files).
- **`database`** — the config/data layer: the `"database"` JSON block key in every
  `config/mapping/{scb,istat}/*.json`, script vars (`database_pop`, `database_file`),
  the `--mapped-database` CLI flag, artifacts `database_{swedish,italian}.json`, the
  `generate_db_population.py` dispatcher, and `docs/database_mapper_philosophy.md`.

Neither term is accurate: `database` implies a DBMS (the source is live HTTP APIs), and
`reference` is a comparison-only *role* that misdescribes the `generators/reference/`
package, where no comparison happens. The split forces a reader to hold two words for
one thing — e.g. a class called `BaseReferenceMapper` reads `block["database"]`. The
counterpart term `synthetic` is already consistent, so this plan changes only the
ground-truth side (plus the two asymmetries below).

Two pre-existing asymmetries to fix while we are here:
1. **Loader-verb mismatch** — the real side exposes `load_reference_population` +
   `normalize_population`; the synthetic side exposes `load_raw_population` +
   `map_population`. Different verbs for mirror-image operations.
2. **The concept split itself** — `reference` (code) vs `database` (config/vars) for the
   same thing; collapsing to `real` resolves it.

## Goals

### In Scope
1. Rename the code layer `reference` → `real`: the `generators/reference/` package, the
   `reference_mapper/` package, the four `*ReferenceMapper` classes, `get_reference_mapper`,
   `load_reference_population`, and all `reference_*` variables/docstrings.
2. Rename the config/data layer `database` → `real`: the `"database"` JSON block key in
   all `config/mapping/{scb,istat}/*.json` (coordinated with the engine/base/tests that
   read it), the `--mapped-database` flag, the `database_file` manifest key, the
   `database_{swedish,italian}.json` artifact names, `generate_db_population.py`, and
   `database_*` script variables.
3. Homogenize the two mapper sides' public API onto a symmetric pair (proposed:
   `load_real_population`/`load_synthetic_population` + `map_population` on both sides).
4. Keep every identifier **bare** — no `_data` suffix introduced anywhere.
5. Rename the philosophy doc + diagrams dir and update live docs/wiki links.
6. Full `pytest` + `ruff check src/` pass at the prior baseline under the new names.

### Out of Scope
- **`config/database/caches/`** — this names an API *response cache*, not the real-
  population concept. It is a separate `cache`/`api_cache` rename tracked as a follow-up
  (touches the 5 clients that hard-code the path). **Not** part of this homogenization.
- The **`population_synthetic`** distribution/import package name (the project stem) —
  unchanged; out of scope.
- Historical plan records under `docs/development/plans/{completed,archived}/` and
  `docs/development/debug/` — point-in-time artifacts, left as-is (same policy as the
  prior rename plan).
- Regenerating diagram *artifacts* (`*.svg`/`*.dot`/`*.png`); the diagrams dir is renamed
  and its source/README updated, but binary re-render is a separate refresh.
- Any change to `synthetic`-side identifiers beyond the loader-verb homogenization in
  Goal 3 (`synthetic` is already consistent).

## Success Criteria

- [ ] `grep -rn '\breference\b' src/ scripts/ tests/` returns **zero** matches referring
  to the ground-truth concept (only unrelated senses, if any, remain — verified by eye).
- [ ] `grep -rn '"database"' config/ src/ tests/` returns **zero** matches (the block key
  is now `"real"` everywhere; `config/database/caches/` path is the only `database`
  token left, and only because it is out of scope).
- [ ] No `*ReferenceMapper` class, no `reference_mapper/` or `generators/reference/`
  directory, no `load_reference_population`/`normalize_population`/`get_reference_mapper`
  symbol remains.
- [ ] No identifier contains `_data` as a real/synthetic suffix (bare-only invariant held).
- [ ] Both mapper packages expose the same verb pair (symmetric loader + `map_population`).
- [ ] `pytest` passes at the prior baseline (125 passed per the last rename record).
- [ ] `ruff check src/` shows **zero new** errors vs the base branch.
- [ ] A `map_populations.py` → `compare_pipeline_to_scb.py` run produces
  `real_swedish.json` and a comparison report identical in content to a pre-rename run
  (byte-for-byte on the numbers; only filenames/keys changed).

---

## Technical Design

### Approach

A mechanical, package-scoped identifier rename on a dedicated feature branch, executed as
ordered token substitutions with `git mv` for directories/files (to preserve history),
then reinstall + full test/ruff verification. Because the two competing terms map to
**one** target (`real`), the substitutions are: `reference → real` (code) and
`database → real` (config/vars/artifacts). Word-boundary-guarded replacement per token,
run once per scope, grep-verified after each phase.

The **config block key** rename (`"database"` → `"real"`) is the one change that must be
**atomic across code + config + tests** in a single phase, per the project's "config is
the single source of truth" invariant: the JSON key, the `block["database"]` reader in
`reference_mapper/base.py`, the engine/`flatten_raw` references, and every fixture/test
string move together or the suite breaks loudly (which is the desired fail-fast signal).

The loader-verb homogenization (Goal 3) is a small, deliberate API change folded into the
real-side rename so the symmetric pair lands in the same commit as the class rename.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Collapse both terms onto **`real`**, bare (this plan) | One accurate antonym pair `real`↔`synthetic`; fixes the DBMS-implying `database` and the role-misfit `reference`; matches field idiom | Wide diff (~53 code files + 26 config files + tests/docs) | **Chosen** |
| Keep `reference`, only drop `database`→`reference` | Smaller diff; `reference` already dominant | Keeps the inaccurate comparison-only *role* name on the `generators/` package; `reference` is generic | Rejected |
| Adopt `real_data`/`synthetic_data` (with `_data`) | Self-documenting config keys | `_data` redundant everywhere a noun is already attached (`_mapper`, `_file`, `_pop`); introduces a brand-new suffix convention; verbose | Rejected (user decision: no `_data`) |
| `empirical` / `observed` instead of `real` | More precise statistically | Less immediately readable; `real`↔`synthetic` is the field-standard pair and already appears in repo prose | Rejected (user chose `real`) |

### Architecture Changes

Directory / symbol moves (internal module structure otherwise unchanged):

```
src/population_synthetic/
  generators/reference/            ->  generators/real/
  analysis/mapping/reference_mapper/  ->  analysis/mapping/real_mapper/
      AbstractReferenceMapper      ->  AbstractRealMapper
      BaseReferenceMapper          ->  BaseRealMapper
      SwedishReferenceMapper       ->  SwedishRealMapper
      ItalianReferenceMapper       ->  ItalianRealMapper
      get_reference_mapper         ->  get_real_mapper
      load_reference_population     ->  load_real_population
      normalize_population          ->  map_population        (homogenize verb)

config/mapping/{scb,istat}/*.json:
      "database": {...}            ->  "real": {...}          (sibling of "synthetic")

scripts/:
      generate/generate_db_population.py  ->  generate_real_population.py
      --mapped-database / mapped_database ->  --mapped-real / mapped_real
      "database_file" (manifest key)      ->  "real_file"
      database_{swedish,italian}.json     ->  real_{swedish,italian}.json
      database_pop / reference_pop (vars) ->  real_pop

synthetic side (homogenization only):
      load_raw_population           ->  load_synthetic_population
      map_population                ->  (unchanged; now the shared verb both sides use)

docs/:
      database_mapper_philosophy.md       ->  real_mapper_philosophy.md
      architecture/diagrams/database/     ->  architecture/diagrams/real/
```

**Naming rule enforced (bare, no `_data`):** `real`/`synthetic` glue directly to their
noun everywhere — `RealMapper`, `real_mapper/`, `real_pop`, `real_file`, `--mapped-real`,
`"real"` block key, `real_swedish.json`. `_data` is never appended.

---

## Implementation Plan

### Phase 1: Real-side code rename (`reference` → `real`) + verb homogenization
**Goal:** Rename the code layer and land the symmetric mapper API in one move.

**Started:** 2026-07-01
**Completed:** 2026-07-01

- [x] Task 1.1 — `git mv src/population_synthetic/generators/reference src/population_synthetic/generators/real`
- [x] Task 1.2 — `git mv src/population_synthetic/analysis/mapping/reference_mapper .../real_mapper`
- [x] Task 1.3 — Rename classes `Abstract/Base/Swedish/Italian ReferenceMapper` → `...RealMapper` and `get_reference_mapper` → `get_real_mapper` (definitions + all call sites)
- [x] Task 1.4 — Rename `load_reference_population` → `load_real_population`; rename `normalize_population` → `map_population` (real side now mirrors the synthetic side's verb)
- [x] Task 1.5 — Rename synthetic loader `load_raw_population` → `load_synthetic_population` (the other half of the symmetric pair)
- [x] Task 1.6 — Word-boundary replace remaining `reference` identifiers/docstrings (`reference_pop`, "reference population", `reference_mapper` import paths) across `src/`
- [x] Task 1.7 — Update `__init__.py` `__all__` exports in both mapper packages

**Files Modified:**
- `src/population_synthetic/generators/real/**` — dir move + internal `reference` docstrings/constants (`italy/constants.py`, `norway/constants.py`, `sweden/parsers.py`, `italy/parsers.py`, sample services)
- `src/population_synthetic/analysis/mapping/real_mapper/**` — dir move, class + function renames (`base.py`, `factory.py`, `italy.py`, `sweden.py`, `loader.py`, `mappings.py`, `raw_format.py`, `__init__.py`)
- `src/population_synthetic/analysis/mapping/synthetic_mapper/{loader.py,__init__.py}` — `load_raw_population` → `load_synthetic_population`
- `src/population_synthetic/analysis/mapping/{mapping_engine.py,flatten_raw.py,normalizer.py,extractor.py}` — `reference` references
- `src/population_synthetic/analysis/comparison/{scheme.py,evaluator.py,charts.py}` — `reference` references
- `src/population_synthetic/analysis/utils/country_config.py` — `reference` config keys/paths (12 hits)
- `src/population_synthetic/analysis/__init__.py`, `analysis/llm_metrics/per_run/joiner.py` — stray `reference` mentions

**Dependencies:** None

### Phase 2: Config block key rename (`"database"` → `"real"`) — atomic code+config+tests
**Goal:** Flip the JSON block key and every reader/fixture in one coordinated change so the
"config is the single source of truth" invariant holds and any miss fails loudly.

**Started:** 2026-07-01
**Completed:** 2026-07-01

- [x] Task 2.1 — In all `config/mapping/scb/*.json` and `config/mapping/istat/*.json`, rename the `"database"` block key → `"real"` (sibling of `"values"`/`"synthetic"`)
- [x] Task 2.2 — Update the reader `rules_block = block["database"]` → `block["real"]` in `real_mapper/base.py` and any engine/`flatten_raw.py` references to the `"database"` key
- [x] Task 2.3 — Update test fixtures/assertions that hard-code the `"database"` key: `tests/_mapping_fixtures.py`, `tests/test_mapper_delegation.py`, `tests/test_scheme_index.py`, `tests/test_synthetic_reference_vocab_subset.py` (the `("database","synthetic")` iteration → `("real","synthetic")`)
- [x] Task 2.4 — Grep-verify: no `"database"` key remains under `config/mapping/`, `src/`, or `tests/`

**Files Modified:**
- `config/mapping/scb/*.json` (14) + `config/mapping/istat/*.json` (13) — block key rename (27 total)
- `config/mapping/scb/README.md`, `config/mapping/istat/README.md` — key-name mentions kept in sync with the JSON shape
- `src/population_synthetic/analysis/mapping/real_mapper/base.py`, `.../flatten_raw.py`, `.../mapping_engine.py` — key readers + docstrings
- `tests/_mapping_fixtures.py`, `tests/test_mapper_delegation.py`, `tests/test_scheme_index.py` — fixture strings
- `git mv tests/test_synthetic_reference_vocab_subset.py tests/test_synthetic_real_vocab_subset.py` — renamed + `("database","synthetic")` → `("real","synthetic")`
- `git mv tests/test_reference_mapper_base.py tests/test_real_mapper_base.py` — renamed + `BaseReferenceMapper` → `BaseRealMapper`, block-key fixtures
- `tests/test_norway_sampler.py`, `tests/test_income_class.py` — fixed stale Phase-1 imports (`generators.reference.*` → `generators.real.*`) left for this phase
- `tests/test_synthetic_mapper_base.py` — docstring cross-reference to the renamed `test_real_mapper_base.py`

**Dependencies:** Phase 1 (package/symbol names must already be `real_*`)

### Phase 3: Scripts, CLI, artifacts, manifest keys (`database`/`reference` → `real`)
**Goal:** Rename the user-facing surface — flags, output filenames, manifest keys, and the
dispatcher script — and the analyze-script variables.

**Started:** 2026-07-01
**Completed:** 2026-07-01

- [x] Task 3.1 — `git mv scripts/generate/generate_db_population.py scripts/generate/generate_real_population.py`; update its docstring/`--help` ("statistical database" → "statistics API")
- [x] Task 3.2 — Rename CLI flag `--mapped-database` → `--mapped-real` (dest `mapped_database` → `mapped_real`) in `compare_pipeline_to_scb.py` and `compare_pipeline_to_istat.py`
- [x] Task 3.3 — Rename artifact outputs `database_{swedish,italian}.json` → `real_{swedish,italian}.json` (writer in `map_populations.py`, readers in the compare scripts + `compare_all_pipelines.py`)
- [x] Task 3.4 — Rename `_index.json` manifest key `"database_file"` → `"real_file"` (writer `map_populations.py`, reader `compare_all_pipelines.py`)
- [x] Task 3.5 — Rename script variables `database_pop`/`reference_pop` → `real_pop`, `n_reference` → `n_real`, and update the `map_population`/`load_real_population` import lines
- [x] Task 3.6 — Update `scripts/dev/draw_generation_dags.py` output path `diagrams/database/` → `diagrams/real/`

**Files Modified:**
- `scripts/generate/generate_real_population.py` — rename + wording
- `scripts/analyze/{map_populations.py,compare_pipeline_to_scb.py,compare_pipeline_to_istat.py,compare_all_pipelines.py,compare_populations.py,compare_countries.py}` — flags, artifact names, manifest key, imports, vars
- `scripts/dev/draw_generation_dags.py` — diagrams path
- `scripts/README.md` — command references

**Dependencies:** Phases 1–2

### Phase 4: Docs, diagrams dir, and wiki links
**Goal:** Rename the philosophy doc + diagrams dir and update every *live* doc that
describes current names; leave historical records untouched.

**Started:** 2026-07-01
**Completed:** 2026-07-01

- [x] Task 4.1 — `git mv docs/database_mapper_philosophy.md docs/real_mapper_philosophy.md`; rewrite title "The Database (Reference) Mapper" → "The Real-Population Mapper", drop the `reference_mapper (database)` dual-naming, use `real`/`real_mapper` throughout
- [x] Task 4.2 — `git mv docs/architecture/diagrams/database docs/architecture/diagrams/real`; update its `README.md` and any index that links it
- [x] Task 4.3 — Update live wiki pages that name the concept: `CLAUDE.md` (Architecture section + the doc table link), `docs/architecture/{README.md,sub-packages.md,comparison-mapping.md,commands.md}`, `docs/scb_population_and_comparison.md`
- [x] Task 4.4 — Leave `docs/development/plans/{completed,archived}/` and `docs/development/debug/` unchanged (point-in-time records)

**Files Modified:**
- `git mv docs/database_mapper_philosophy.md docs/real_mapper_philosophy.md` — full rewrite (title, class/function names, `database`→`real` block key, `comparison/`→`analysis/mapping/` stale paths corrected)
- `git mv docs/architecture/diagrams/database docs/architecture/diagrams/real` — nested oddly under an existing untracked `real/` dir from a prior regenerated-diagram run; resolved by moving `README.md` in and dropping the stale duplicate `.dot`/`.svg`/`.png` in favor of the already-regenerated (post-Phase-1) ones at the top level of `real/`
- `docs/architecture/diagrams/real/README.md`, `docs/architecture/diagrams/README.md`, `docs/architecture/diagrams/synthetic_strategies/README.md` — renamed dir references + link fix
- `CLAUDE.md` — Architecture section, doc-table link, and a stale `generators.reference.sweden` import example in Import Convention
- `docs/architecture/{README.md,sub-packages.md,comparison-mapping.md,commands.md,design-principles.md,configuration.md,axis-composition.md}` — concept/link updates (comparison-mapping.md and sub-packages.md needed the deepest rewrite: class names, verb pair, block-key mentions)
- `docs/scb_population_and_comparison.md` — reviewed, no changes: its "reference"/"database" usages are a different, still-existing standalone workflow (`compare_populations.py`) using generic statistical-role wording ("reference vs observed"), not the renamed identifiers
- Left unchanged (reported, not renamed): `config/database/caches/` (out of scope, unrelated cache concept), `parameters.reference` YAML key in country axis YAMLs (documented in `country_config.py` as intentionally unrenamed pending a follow-up), `docs/mapping_gap_investigation_playbook.md` + `docs/swedish_model_state_and_mapping_2026-06-29.md` + `docs/development/reference-mapper-agnostic-summary.md` (dated point-in-time snapshots already referencing pre-rename architecture, treated like `plans/completed/`)

**Dependencies:** Phases 1–3

### Phase 5: Reinstall & verify
**Goal:** Confirm the rename is complete, symmetric, and behaviour-preserving.

**Started:** 2026-07-01
**Completed:** 2026-07-01

- [x] Task 5.1 — `pip install -e ".[dev]"` (re-register editable install after dir moves)
- [x] Task 5.2 — Grep gates from Success Criteria (no `reference` concept, no `"database"` key, no `_data` suffix)
- [x] Task 5.3 — `pytest` at prior baseline; `ruff check src/` zero new errors
- [x] Task 5.4 — Golden run: `map_populations.py` then `compare_pipeline_to_scb.py`; confirm `real_swedish.json` produced and the report numbers match a pre-rename run

**Files Modified:**
- `config/mapping/scb/README.md`, `config/mapping/istat/README.md` — fixed two stale Phase-2/4 leftovers found during verification: `comparison/reference_mapper/mappings.py` / `comparison/mapping_engine.py` (a path that never matched the real module layout) → `analysis/mapping/real_mapper/mappings.py` / `analysis/mapping/mapping_engine.py`; "SCB/ISTAT reference database" prose → "SCB/ISTAT real population data"

**Dependencies:** Phases 1–4

---

## Testing Plan

### Unit Tests
- [ ] `tests/test_real_mapper_base.py` (renamed from `test_reference_mapper_base.py`) resolves `RealMapper` classes and the `"real"` block key
- [ ] `tests/test_mapper_delegation.py` + `tests/test_scheme_index.py` pass with the `("real","synthetic")` block pair
- [ ] `tests/test_synthetic_real_vocab_subset.py` (renamed) iterates `("real","synthetic")`
- [ ] `tests/test_evaluator.py`, `tests/test_income_class.py` pass (they reference the real side)

### Integration Tests
- [ ] `python scripts/analyze/map_populations.py --help` and a real slug run produce `real_{country}.json` + `"real_file"` in `_index.json`
- [ ] `python scripts/analyze/compare_pipeline_to_scb.py --mapped-real ... --mapped-synthetic ...` runs and emits the full comparison artifact set

### Manual Verification
- [ ] `python scripts/generate/generate_real_population.py --source scb --n 100` runs
- [ ] Grep confirms bare-only: no `real_data`/`synthetic_data` identifier exists
- [ ] Comparison report numbers byte-identical to a pre-rename baseline (only names changed)

### Edge Cases
- [ ] No double-substitution artifacts (e.g. a value that legitimately contains "reference"
  in data is not mangled — word-boundary + eyeball the config diff)
- [ ] `config/database/caches/` path is **untouched** (out of scope) and clients still resolve it
- [ ] A mapping JSON whose raw label matches no `"real"` matcher still resolves to `None`
  (fail-fast/drop behaviour unchanged by the key rename)

---

## Documentation Plan

- [ ] Rename + rewrite `docs/real_mapper_philosophy.md`
- [ ] Update `CLAUDE.md` Architecture section + doc table link (`database_mapper_philosophy` → `real_mapper_philosophy`)
- [ ] Update `docs/architecture/{README,sub-packages,comparison-mapping,commands}.md`
- [ ] Update `scripts/README.md` (`generate_db_population.py` → `generate_real_population.py`, `--mapped-database` → `--mapped-real`)
- [ ] No changelog convention exists; this completed plan record serves as the change note

---

## Rollback Plan

Pure rename on a dedicated feature branch — rollback is trivial and data-free.

1. **Before merge:** discard the branch — `git checkout dev && git branch -D feature/homogenize-real-synthetic-naming`, then `pip install -e ".[dev]"` to restore the old editable registration.
2. **Data considerations:** none — no migrations, no runtime state; regenerating mapped
   files under the old `database_*.json` names is a re-run, not a migration.
3. **Rollback procedure:** revert the rename commit(s); re-run `pip install -e ".[dev]"`.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Config key rename half-applied (JSON changed, reader not) | Med | High | Do it atomically in Phase 2; fail-fast raises loudly; grep-gate before commit |
| Stale mapped artifacts named `database_*.json` linger and a reader silently finds none | Med | Med | Compare scripts already fail-fast on missing input; Phase 5 golden run regenerates under `real_*.json` |
| Word "reference" has unrelated legitimate uses (e.g. "reference" in prose/data) mangled | Low | Med | Word-boundary + concept-scoped review of each diff; only the ground-truth sense is renamed |
| Accidentally renaming `config/database/caches/` (out of scope) | Low | Med | Explicitly excluded; scope Phase 2 to `config/mapping/` only |
| Editable install still points at old `reference/` dir after `git mv` | Med | Med | `pip install -e .` in Phase 5; verify import resolves `real_mapper` |
| Verb homogenization breaks an unnoticed caller of `normalize_population`/`load_raw_population` | Med | Med | Rename definitions + grep all call sites in Phase 1; test suite covers both mappers |
| Rewriting historical plan/debug records | Low | Low | Phases scoped to live code/docs; `completed/`/`archived/`/`debug/` excluded |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 (real-side code + verbs) | ~40 min | None |
| Phase 2 (config key, atomic) | ~30 min | Phase 1 |
| Phase 3 (scripts/CLI/artifacts) | ~30 min | Phases 1–2 |
| Phase 4 (docs/diagrams) | ~25 min | Phases 1–3 |
| Phase 5 (reinstall & verify) | ~20 min | Phases 1–4 |

---

## References

- Related Plans: `docs/development/plans/completed/unified-symmetric-mapping-config.md`
  (established the symmetric `database`/`synthetic` block pair this plan renames),
  `docs/development/plans/completed/rename-distribution-to-population-synthetic.md`
  (prior rename; template + scoping policy for historical docs)
- Design doc renamed by this plan: `docs/database_mapper_philosophy.md` → `docs/real_mapper_philosophy.md`
- Invariants respected: "config is the single source of truth" and "fail-fast" (CLAUDE.md)
- Decision context: conversation choosing `real` over `reference`/`database`/`empirical`,
  and the no-`_data` bare-identifier rule

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- CLAUDE.md
- config/mapping/istat/README.md
- config/mapping/istat/biological_sex.json
- config/mapping/istat/birth_country_detail.json
- config/mapping/istat/birth_location.json
- config/mapping/istat/civil_status.json
- config/mapping/istat/education.json
- config/mapping/istat/employment.json
- config/mapping/istat/employment_type.json
- config/mapping/istat/household_size.json
- config/mapping/istat/housing_tenure.json
- config/mapping/istat/industry_sector.json
- config/mapping/istat/parental_structure.json
- config/mapping/istat/region.json
- config/mapping/istat/socioeconomic.json
- config/mapping/scb/README.md
- config/mapping/scb/biological_sex.json
- config/mapping/scb/birth_country_detail.json
- config/mapping/scb/birth_location.json
- config/mapping/scb/civil_status.json
- config/mapping/scb/education.json
- config/mapping/scb/employment.json
- config/mapping/scb/employment_type.json
- config/mapping/scb/household_size.json
- config/mapping/scb/housing_tenure.json
- config/mapping/scb/income_source.json
- config/mapping/scb/industry_sector.json
- config/mapping/scb/parental_structure.json
- config/mapping/scb/region.json
- config/mapping/scb/socioeconomic.json
- docs/architecture/README.md
- docs/architecture/axis-composition.md
- docs/architecture/commands.md
- docs/architecture/comparison-mapping.md
- docs/architecture/configuration.md
- docs/architecture/design-principles.md
- docs/architecture/diagrams/README.md
- docs/architecture/diagrams/database/README.md (removed → real/)
- docs/architecture/diagrams/database/*.dot|*.svg|*.png (removed → real/)
- docs/architecture/diagrams/real/README.md
- docs/architecture/diagrams/real/italy_generation_dag.dot
- docs/architecture/diagrams/real/italy_generation_dag.png
- docs/architecture/diagrams/real/italy_generation_dag.svg
- docs/architecture/diagrams/real/norway_generation_dag.dot
- docs/architecture/diagrams/real/norway_generation_dag.png
- docs/architecture/diagrams/real/norway_generation_dag.svg
- docs/architecture/diagrams/real/sweden_generation_dag.dot
- docs/architecture/diagrams/real/sweden_generation_dag.png
- docs/architecture/diagrams/real/sweden_generation_dag.svg
- docs/architecture/diagrams/synthetic_strategies/README.md
- docs/architecture/sub-packages.md
- docs/database_mapper_philosophy.md (renamed → docs/real_mapper_philosophy.md)
- docs/development/plans/active/homogenize-real-synthetic-naming.md
- docs/real_mapper_philosophy.md
- scripts/README.md
- scripts/analyze/compare_all_pipelines.py
- scripts/analyze/compare_countries.py
- scripts/analyze/compare_pipeline_to_istat.py
- scripts/analyze/compare_pipeline_to_scb.py
- scripts/analyze/compare_populations.py
- scripts/analyze/map_populations.py
- scripts/dev/draw_generation_dags.py
- scripts/generate/generate_db_population.py (renamed → generate_real_population.py)
- scripts/generate/generate_istat_population.py
- scripts/generate/generate_real_population.py
- scripts/generate/generate_scb_population.py
- scripts/generate/generate_ssb_population.py
- src/population_synthetic/analysis/__init__.py
- src/population_synthetic/analysis/comparison/__init__.py
- src/population_synthetic/analysis/comparison/charts.py
- src/population_synthetic/analysis/comparison/evaluator.py
- src/population_synthetic/analysis/comparison/scheme.py
- src/population_synthetic/analysis/mapping/__init__.py
- src/population_synthetic/analysis/mapping/extractor.py
- src/population_synthetic/analysis/mapping/flatten_raw.py
- src/population_synthetic/analysis/mapping/mapping_engine.py
- src/population_synthetic/analysis/mapping/normalizer.py
- src/population_synthetic/analysis/mapping/real_mapper/__init__.py
- src/population_synthetic/analysis/mapping/real_mapper/base.py
- src/population_synthetic/analysis/mapping/real_mapper/factory.py
- src/population_synthetic/analysis/mapping/real_mapper/italy.py
- src/population_synthetic/analysis/mapping/real_mapper/loader.py
- src/population_synthetic/analysis/mapping/real_mapper/mappings.py
- src/population_synthetic/analysis/mapping/real_mapper/raw_format.py
- src/population_synthetic/analysis/mapping/real_mapper/sweden.py
- src/population_synthetic/analysis/mapping/reference_mapper/** (removed → real_mapper/)
- src/population_synthetic/analysis/mapping/synthetic_mapper/__init__.py
- src/population_synthetic/analysis/mapping/synthetic_mapper/base.py
- src/population_synthetic/analysis/mapping/synthetic_mapper/factory.py
- src/population_synthetic/analysis/mapping/synthetic_mapper/loader.py
- src/population_synthetic/analysis/utils/country_config.py
- src/population_synthetic/generators/real/** (renamed from generators/reference/**)
- src/population_synthetic/generators/reference/** (removed → real/)
- tests/_mapping_fixtures.py
- tests/test_evaluator.py
- tests/test_income_class.py
- tests/test_mapper_delegation.py
- tests/test_norway_sampler.py
- tests/test_real_mapper_base.py (renamed from test_reference_mapper_base.py)
- tests/test_reference_mapper_base.py (removed → test_real_mapper_base.py)
- tests/test_scheme_index.py
- tests/test_synthetic_mapper_base.py
- tests/test_synthetic_real_vocab_subset.py (renamed from test_synthetic_reference_vocab_subset.py)
- tests/test_synthetic_reference_vocab_subset.py (removed → test_synthetic_real_vocab_subset.py)

_Excluded (unrelated pre-existing change, not part of this plan): `config/gui/launcher.yaml`._
