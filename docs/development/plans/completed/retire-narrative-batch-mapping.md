# Plan: Retire the Narrative/Batch Path and Its Hardcoded Mapping Layer

**Date:** 2026-06-30
**Author:** Basil
**Status:** Completed
**Completed:** 2026-06-30 21:55
**Base Branch:** `dev`
**Branch:** `feature/retire-narrative-batch-mapping`

> **Base-branch note:** Per the plan-create skill this would record the current
> branch (`feature/synthetic-mapper-config-driven`). It is set to `dev` instead
> because this cleanup logically integrates at `dev` and **depends on** the
> in-flight `refactor-synthetic-mapper-config-driven` and
> `reference-mapper-fully-field-agnostic` work merging to `dev` first (those
> branches established the config-driven engines this plan finishes off). Start
> this branch from `dev` after they land.

---

## Overview

The synthetic and reference mappers are now fully config-driven for the **flat**
identity path and the **reference** path — every label, keyword rule, bucket and
threshold is read from `config/mapping/{scb,istat}/`. All remaining hardcoded
mapping logic in the codebase lives in a **single dead-in-production island**:
the legacy narrative/batch parsing layer under `comparison/extract/`, reachable
only via the `"narrative"` branch of `map_individual`, which no current generator
feeds. This plan deletes that island (and the batch *generator* that produced
narrative output) so the project's mapping logic is 100% config-driven with zero
hardcoded category labels or keyword cascades.

## Problem Statement

The claim "all mapping matches occur in config files, no hardcoded values" is
**currently false**. Two parallel mapping implementations exist:

1. The config-driven handler-kind engines (`synthetic_mapper/`, `reference_mapper/`)
   — clean, zero field-name/label literals.
2. The legacy `extract/` layer (`normalizers_se.py`, `normalizers_it.py`,
   `batch.py`, `prose_inference.py`, `schema_labels.py`) — saturated with
   hardcoded canonical labels, keyword cascades, if/elif chains, occupation→
   industry tables, and numeric thresholds. Some of it (e.g. employment keyword
   rules) is a verbatim duplicate of config already migrated into
   `pipeline_keyword_rules`.

Investigation (2026-06-30) confirms the entire `extract/` island is **dead in
production**:

- No manifest or axis strategy uses `mode: batch`; every entrypoint emits the
  **flat** identity format, which runs through the config-driven engine.
- The only narrative producer, `NarrativeGeneratorBatch`, is reachable solely via
  a hand-typed `--mode batch --config <prompt>` pointing at a prompt file that
  does not ship in the repo.
- The consumer (`_extract_batch` + the `normalizers_se`/`normalizers_it`/
  `prose_inference`/`batch`/`schema_labels` chain) is reachable in production
  only through the `"narrative"` branch — and is kept green solely by one
  characterization fixture (`tests/data/extractor/persona_batch_se/`).
- Three module-level constants in `synthetic_mapper/base.py`
  (`_EUROPEAN_COUNTRIES`, `_NON_EUROPEAN_COUNTRIES`, `match_common_sex`) are
  orphaned — zero callers anywhere.

This is dead code that hardcodes mapping values, contradicts the
config-driven-mapping design goal, and duplicates logic that now lives in config.

## Goals

### In Scope
1. Delete the narrative/batch **consumer** island under `comparison/extract/`
   (`normalizers_se.py`, `normalizers_it.py`, `batch.py`, `prose_inference.py`,
   `schema_labels.py`), relocating the one generic helper still used by the live
   path (`_fuzzy_match`).
2. Remove the narrative dispatch (`SUPPORTS_NARRATIVE`, the `"narrative"` branch)
   and the three dead constants from the synthetic mapper.
3. Delete the narrative/batch **producer**: `NarrativeGeneratorBatch`, its factory
   registration, and the `--mode batch` CLI choice.
4. Trim `extract/mappings.py` to its live generic helpers; remove the dead
   `_json_lookup*` / `_PIPELINE_MAPPINGS` machinery and its hardcoded key list.
5. Update tests, docs (CLAUDE.md), and archive the now-moot pending batch plan.
6. End state: no hardcoded canonical labels or keyword/matching cascades remain in
   `src/population_synth/comparison/`; all mapping is config-driven.

### Out of Scope
- Designing a *new* batch ("all-properties-at-once") generator. If revived later,
  it should emit **flat** fields and flow through the existing config-driven
  engine — a fresh plan, not this one.
- Any change to the config-driven flat-path or reference-path engines beyond
  removing the dead `SUPPORTS_NARRATIVE` hook.
- Re-validating comparison numbers for live runs (flat-path behaviour is
  unchanged; only the never-exercised narrative branch is removed).

## Success Criteria

- [ ] `rg -n "narrative|NarrativeGeneratorBatch|_extract_batch|SUPPORTS_NARRATIVE|match_common_sex|_EUROPEAN_COUNTRIES|_NON_EUROPEAN_COUNTRIES" src/ scripts/ tests/` returns no live references (only, if anything, incidental prose).
- [ ] `rg -n "_normalize_|_json_lookup|prose_inference|schema_labels" src/ scripts/ tests/` returns nothing.
- [ ] No hardcoded canonical category label string literals remain anywhere under `src/population_synth/comparison/` (manual grep audit of the file set below passes).
- [ ] `ruff check src/` is clean (no unused-import / undefined-name errors from the deletions).
- [ ] `pytest` passes with the `persona_batch_se` case removed and the flat cases (`persona_flat_se`, `persona_flat_it`) still green.
- [ ] `--mode batch` is gone from both generate scripts; `--mode configurable` still works end-to-end.
- [ ] CLAUDE.md no longer documents batch mode / narrative parsing as live behaviour.

---

## Technical Design

### Approach

Delete by addressing the two halves of the dead path symmetrically — the
**producer** (generation) and the **consumer** (mapping) — plus the dead
constants. The only non-mechanical step is relocating `_fuzzy_match` (a generic,
label-free substring matcher) out of the to-be-deleted `normalizers_se.py` and
into `extract/mappings.py` alongside the other surviving generic helpers
(`_sep_norm`, `_repair_utf8_double_encoding`), then repointing the one live import
in `synthetic_mapper/base.py`.

This was chosen over migrating the narrative path onto the config engine because
no entrypoint produces narrative identities, and a future batch generator is
better designed to emit flat fields (reusing the existing engine) than to
resurrect a prose parser.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Delete the dead path (this plan) | Achieves the no-hardcoded-values goal directly; removes ~1000 lines of dead, duplicated logic; lowest risk (nothing live uses it) | Retires narrative generation; future batch work starts fresh | **Chosen** |
| Migrate narrative parsing to the config engine | Keeps narrative support config-driven | Large effort to preserve a path nothing feeds; prose parsing doesn't fit the per-field handler model | Rejected |
| Remove only the 3 dead constants | Trivial | Leaves the bulk of the hardcoded island; does **not** make the claim true | Rejected |

### Architecture Changes

- `comparison/extract/` shrinks from 7 modules to 2 (`__init__.py`, `mappings.py`).
  `mappings.py` becomes the home for the live, generic text helpers only.
- `synthetic_mapper/` loses its narrative dispatch; `map_individual` handles only
  the flat path (unrecognised formats → warn + skip, as today).
- `AbstractSyntheticMapper` loses the `SUPPORTS_NARRATIVE` class var; the
  contract narrows to the flat config-driven engine.
- `identity/` loses the `NarrativeGeneratorBatch` strategy; the factory exposes
  only `configurable`.

```
comparison/extract/   (before)              comparison/extract/   (after)
├── __init__.py                             ├── __init__.py
├── mappings.py        (mixed)              └── mappings.py        (generic helpers only:
├── normalizers_se.py  (DELETE)                                    _sep_norm, _repair_utf8_*,
├── normalizers_it.py  (DELETE)                                    _fuzzy_match relocated here)
├── prose_inference.py (DELETE)
├── batch.py           (DELETE)
└── schema_labels.py   (DELETE)
```

---

## Implementation Plan

### Phase 1: Relocate the one live helper, then delete the consumer island
**Started:** 2026-06-30
**Completed:** 2026-06-30
**Goal:** Remove all hardcoded mapping logic from `comparison/` while preserving
the flat path's generic helper.

- [x] 1.1 — Move `_fuzzy_match` from `extract/normalizers_se.py` into
  `extract/mappings.py` (verbatim; it holds no labels). Keep `_age_to_group`
  deleted (dead — bucketing is config-driven via `pipeline_numeric_buckets`).
- [x] 1.2 — Trim `extract/mappings.py`: remove `_json_lookup`, `_json_lookup_it`,
  `_load_pipeline_mappings`, `_PIPELINE_MAPPINGS`, `_PIPELINE_MAPPINGS_IT`,
  `_get_it_mappings`, the hardcoded category-key list (lines ~43–48), and the now
  unused `_MAPPINGS_PATH`/`_ISTAT_MAPPINGS_PATH` / `load_mappings` import. Keep
  `_SEP_RE`, `_sep_norm`, `_UTF8_DOUBLE_ENCODING_REPAIRS`,
  `_repair_utf8_double_encoding`, and the relocated `_fuzzy_match`.
- [x] 1.3 — Delete `extract/normalizers_se.py`, `extract/normalizers_it.py`,
  `extract/prose_inference.py`, `extract/batch.py`, `extract/schema_labels.py`.
- [x] 1.4 — Update `extract/__init__.py` to drop any exports/imports of the
  deleted modules.

**Files Modified:**
- `src/population_synth/comparison/extract/mappings.py` — relocate `_fuzzy_match`; remove dead lookup machinery
- `src/population_synth/comparison/extract/__init__.py` — drop deleted-module references
- (delete) `extract/normalizers_se.py`, `normalizers_it.py`, `prose_inference.py`, `batch.py`, `schema_labels.py`

**Dependencies:** None

### Phase 2: Remove narrative dispatch and dead constants from the mapper
**Started:** 2026-06-30
**Completed:** 2026-06-30
**Goal:** Narrow `synthetic_mapper` to the flat config-driven path only.

- [x] 2.1 — In `synthetic_mapper/base.py`: delete `_EUROPEAN_COUNTRIES`,
  `_NON_EUROPEAN_COUNTRIES`, `match_common_sex`.
- [x] 2.2 — Remove the `"narrative"` branch in `map_individual` (lines ~486–489)
  and the `_extract_batch` import; update the method docstring (no narrative
  dispatch — narrative/unknown formats fall through to the warn-and-skip path).
- [x] 2.3 — Remove the `SUPPORTS_NARRATIVE` ClassVar from `AbstractSyntheticMapper`
  and its docstring mention.
- [x] 2.4 — Repoint the `_fuzzy_match` import to `extract.mappings`; keep the
  `_repair_utf8_double_encoding` / `_sep_norm` imports.
- [x] 2.5 — `sweden.py`: remove `SUPPORTS_NARRATIVE = True` and update the
  docstring (no narrative signal; country divergence is the mapping dir only).
- [x] 2.6 — `italy.py`: update the docstring (drop the `SUPPORTS_NARRATIVE`
  mention).

**Files Modified:**
- `src/population_synth/comparison/synthetic_mapper/base.py`
- `src/population_synth/comparison/synthetic_mapper/sweden.py`
- `src/population_synth/comparison/synthetic_mapper/italy.py`

**Dependencies:** Phase 1

### Phase 3: Delete the narrative/batch producer
**Started:** 2026-06-30
**Completed:** 2026-06-30
**Goal:** Remove the generator that produced narrative output.

- [x] 3.1 — Delete `src/population_synth/identity/identity_generator_batch.py`.
- [x] 3.2 — In `factory_identity_generator.py`: drop the `NarrativeGeneratorBatch`
  import and the `"batch"` registry entry; update the module/class docstrings
  (configurable is the only strategy).
- [x] 3.3 — Remove `"batch"` from the `--mode` argparse choices in
  `scripts/generate/generate_identity.py` (~line 72) and
  `scripts/generate/generate_identities_parallel.py` (~line 219); adjust any help
  text/default.
- [x] 3.4 — Confirm `base_identity_generator.py` needs no change (configurable
  still subclasses it) and that nothing else imports `NarrativeGeneratorBatch`
  (grep).
- [x] 3.5 — Update `config/synthetic/manifests/template_identity_manifest.yaml`
  (remove the commented `batch` option mention).

**Files Modified:**
- (delete) `src/population_synth/identity/identity_generator_batch.py`
- `src/population_synth/identity/factory_identity_generator.py`
- `scripts/generate/generate_identity.py`
- `scripts/generate/generate_identities_parallel.py`
- `config/synthetic/manifests/template_identity_manifest.yaml`

**Dependencies:** Phase 2 (do producer after consumer so the grep audit is meaningful)

### Phase 4: Tests, docs, and pending-plan cleanup
**Started:** 2026-06-30
**Completed:** 2026-06-30
**Goal:** Keep the suite green and the docs truthful.

- [x] 4.1 — `tests/test_extractor_characterization.py`: remove the
  `("persona_batch_se", "swedish")` case from `_CASES`; update
  `test_extract_population_swedish_collects_individuals` to expect only
  `persona_flat_se` (a narrative identity now returns `None`/skips); update the
  module docstring (two flat fixtures + Italian; no narrative).
- [x] 4.2 — Delete the fixture dir `tests/data/extractor/persona_batch_se/` and
  remove the `persona_batch_se` entry from
  `tests/data/extractor/expected_extractor.json`.
- [x] 4.3 — Verify `tests/test_synthetic_mapper_base.py` (flat-only) needs no
  change.
- [x] 4.4 — Update `CLAUDE.md`: remove the `batch` mode semantics, the
  "Narrative/batch parsing is a mapper method (Swedish only; Italian raises)"
  description, both "future all-properties-at-once batch generator is planned"
  notes and the pending-plan reference, and any `--mode batch` usage examples.
- [x] 4.5 — Move `docs/development/plans/pending/batch-generate-all-properties.md`
  to `docs/development/plans/archived/` (narrative batch generation retired; any
  future batch generator is a fresh flat-emitting plan). Add a one-line note at
  the top recording why it was archived.

**Files Modified:**
- `tests/test_extractor_characterization.py`
- `tests/data/extractor/expected_extractor.json` (+ delete `persona_batch_se/` dir)
- `CLAUDE.md`
- `docs/development/plans/pending/batch-generate-all-properties.md` → `archived/`

**Dependencies:** Phases 1–3

---

## Testing Plan

### Unit / Integration Tests
- [ ] `pytest tests/test_extractor_characterization.py` — flat SE + IT golden
  cases pass; `extract_population` collects only the flat Swedish persona.
- [ ] `pytest tests/test_synthetic_mapper_base.py` — flat mapping unaffected.
- [ ] Full `pytest` run green.

### Static Verification
- [ ] `ruff check src/` clean — catches unused imports / undefined names left by
  deletions (e.g. a stale `_extract_batch` or `_fuzzy_match` import).
- [ ] Grep audits from Success Criteria all return empty.

### Manual Verification
- [ ] Run a small configurable generation end-to-end (e.g.
  `--model-id claude_haiku --strategy-id all_pick --country-id swedish --n 2`)
  and confirm flat identities are produced and map cleanly.
- [ ] Run `compare_pipeline_to_scb.py` against an existing flat run and confirm
  the comparison output matches pre-change output (flat path is untouched).

### Edge Cases
- [ ] Feeding a legacy/hand-made `{"narrative": ...}` identity now returns `None`
  (skip + warning), not a crash and not the old hardcoded mapping.
- [ ] `--mode batch` is rejected by argparse with a clear "invalid choice" error.

---

## Documentation Plan

- [ ] Update `CLAUDE.md` (mode semantics, synthetic_mapper description, batch
  generator notes, usage examples) — see Phase 4.4.
- [ ] Archive the pending batch-generator plan with a rationale note — Phase 4.5.
- [ ] No README/user-guide changes expected beyond CLAUDE.md (verify during impl).

---

## Rollback Plan

This is a pure deletion of dead code on a feature branch; rollback is trivial.

1. **Before merge:** the work lives on `feature/retire-narrative-batch-mapping`;
   abandon/delete the branch to revert entirely.
2. **After merge:** `git revert` the squash/merge commit, or restore the deleted
   modules from history (`git checkout <pre-merge-sha> -- src/population_synth/comparison/extract/ src/population_synth/identity/identity_generator_batch.py`).
3. **Data considerations:** none — no migrations, no persisted state, no change to
   any output format produced by live generation.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| A live code path imports a deleted `_normalize_*`/`schema_labels` symbol we missed | Low | Med | Investigation traced all importers; `ruff check` + full `pytest` + grep audit catch any stragglers before merge |
| `_fuzzy_match` relocation subtly changes flat-path behaviour | Low | Med | Move verbatim (no logic change); flat golden tests pin behaviour |
| A future need for narrative/batch generation re-emerges | Low | Low | History + archived plan preserve the design; new batch gen should emit flat fields through the config engine anyway |
| Hidden consumer of `--mode batch` in user scripts outside the repo | Low | Low | Documented removal; argparse fails loudly with "invalid choice" |
| The two in-flight mapper branches haven't merged, causing conflicts | Med | Low | Base off `dev` only after `refactor-synthetic-mapper-config-driven` and `reference-mapper-fully-field-agnostic` land |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1: Relocate helper + delete consumer island | ~1h | None |
| Phase 2: Remove narrative dispatch + dead constants | ~0.5h | Phase 1 |
| Phase 3: Delete producer | ~0.5h | Phase 2 |
| Phase 4: Tests, docs, plan cleanup | ~1h | Phases 1–3 |

---

## References

- Related active plans: `docs/development/plans/active/refactor-synthetic-mapper-config-driven.md`,
  `docs/development/plans/active/reference-mapper-fully-field-agnostic.md`
- Superseded pending plan (to be archived): `docs/development/plans/pending/batch-generate-all-properties.md`
- Investigation (2026-06-30): narrative/batch path confirmed dead in production;
  hardcoded mapping logic confined to the `extract/` island; 3 dead constants in
  `synthetic_mapper/base.py`.

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- CLAUDE.md
- config/synthetic/manifests/template_identity_manifest.yaml
- docs/development/plans/active/retire-narrative-batch-mapping.md
- docs/development/plans/archived/batch-generate-all-properties.md (moved from pending/)
- scripts/generate/generate_identities_parallel.py
- scripts/generate/generate_identity.py
- src/population_synth/comparison/extract/__init__.py
- src/population_synth/comparison/extract/batch.py (deleted)
- src/population_synth/comparison/extract/mappings.py
- src/population_synth/comparison/extract/normalizers_it.py (deleted)
- src/population_synth/comparison/extract/normalizers_se.py (deleted)
- src/population_synth/comparison/extract/prose_inference.py (deleted)
- src/population_synth/comparison/extract/schema_labels.py (deleted)
- src/population_synth/comparison/extractor.py
- src/population_synth/comparison/synthetic_mapper/base.py
- src/population_synth/comparison/synthetic_mapper/italy.py
- src/population_synth/comparison/synthetic_mapper/sweden.py
- src/population_synth/identity/factory_identity_generator.py
- src/population_synth/identity/identity_generator_batch.py (deleted)
- tests/test_extractor_characterization.py

> Note: `tests/data/extractor/` is gitignored — the `persona_batch_se/` fixture
> deletion and `expected_extractor.json` rewrite are local-only (nothing to stage).
