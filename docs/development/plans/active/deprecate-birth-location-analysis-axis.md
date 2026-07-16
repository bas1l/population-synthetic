# Plan: Deprecate `birth_location` as an Analysis Axis

**Date:** 2026-07-16
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/scb-source-improvements`
**Branch:** `feature/deprecate-birth-location-analysis-axis`

---

## Overview

Introduce a config-driven "deprecated axis" concept and apply it to Sweden's `birth_location`.
The attribute stays fully present in the sampler output and mapped populations (data retained),
but is excluded from every analysis stage (marginals, bar charts, TV radar, multivariate/C2ST,
model-ranking, method-significance, consistency). This removes the noise that
`birth_location`'s structural independence from `birth_country_detail` injects into fidelity
analysis, without deleting the field or regenerating any population.

## Problem Statement

Swedish personas carry two birthplace fields drawn as **independent** marginals joined only by a
binary Sweden/non-Sweden gate (`sample_service.py:257`): `birth_location` (coarse Sweden/EU/non-EU,
from `FolkmFodlandHVD`) and `birth_country_detail` (top-20 countries, from `FodelselandArK`).
Nothing forces the sampled country into the coarse EU/non-EU bucket, so contradictory pairs occur
(e.g. "born outside the EU" + "Germany"). `birth_country_detail` already encodes the full
birthplace signal we care about (it resolves to `"Sweden"` for natives via the gate, and to the
specific country otherwise). The coarse `birth_location` axis therefore contributes a contradictory,
lower-value signal to fidelity scoring and comparison charts.

We want `birth_location` out of the **analysis** entirely, while keeping the raw field in the
generated data for traceability and to preserve the internal native-vs-foreign gate.

## Goals

### In Scope
1. A general, config-declared **deprecated-axis** mechanism honored by the analysis pipeline.
2. Mark `birth_location` deprecated for Sweden (`scb_native` and `scb` mapping tiers).
3. `birth_location` excluded from all analysis stages that read `ComparisonScheme.attributes`.
4. `birth_location` still emitted by the sampler and still mapped into canonical populations.

### Out of Scope
- Removing `birth_location` from the sampler output dict (`sample_service.py:284`) — explicitly retained.
- Removing the `birth_location.json` mapping block or its `refine_from: birth_country_detail` wiring.
- Regenerating the reference population or persona sets.
- Any change to Norway (`ssb`) or Italy (`istat`) axes.
- The legacy `_scheme.json` path (`_scheme_from_legacy`) — no country in use routes through it for Sweden.
- Fixing the underlying independence bug (a separate, larger effort; deprecation sidesteps it).

## Success Criteria

- [x] A `deprecated_attributes` key is declared in `config/mapping/scb_native/_index.json` (and `scb/_index.json`) listing `birth_location`.
- [x] `ComparisonScheme.attributes` for Sweden no longer contains `birth_location` (14 axes, was 15).
- [x] A fidelity/comparison run for Sweden emits **no** `birth_location` marginal, bar chart, or radar spoke, and one-hot/C2ST excludes it. *(Verified at the seam: every artifact-emitting stage reads `scheme.attributes`, which excludes `birth_location`; a full run was not executed.)*
- [x] The mapped population still contains a `birth_location` field per persona (data retained).
- [x] Mapper unit tests (`test_real_mapper_base.py`, `test_synthetic_mapper_base.py`, `test_mapper_delegation.py`, `test_sweden_parsers.py`) remain green unchanged.
- [x] A malformed `deprecated_attributes` entry (name not present in `attributes`) fails loudly.

## Definitions

- **Deprecated axis**: an attribute name listed in `_index.json` `attributes` **and** in a sibling
  `deprecated_attributes` array. It is still mapped and emitted into canonical population data, but is
  removed from `ComparisonScheme.attributes`/`.categories`, and thus invisible to every analysis stage.
- **Retained (data)**: present in both the raw sampler output and the mapped canonical population
  dict; only its participation in *analysis* is removed.
- **Analysis pipeline**: any stage consuming `ComparisonScheme.attributes` — marginal fidelity, bar
  charts, TV radar, multivariate/C2ST, model-ranking, method-significance, consistency validation.

---

## Technical Design

### Approach

Add a top-level `deprecated_attributes` array to the mapping `_index.json`, and filter those names
out at the **single analysis chokepoint**, `_scheme_from_index` (`analysis/fidelity/scheme.py:308`).
`ComparisonScheme.attributes` is the sole source every analysis stage reads, so filtering there
propagates everywhere with no per-stage edits. The mapper path (`real_mapper/base.py`,
`synthetic_mapper/base.py`) reads `index["attributes"]` directly and is left untouched, so the field
is still mapped and emitted.

The marker lives beside the axis list it modifies (same `_index.json`), keeping the per-attribute
JSON files pure filename→block references and preserving the mapper's expectation that
`attributes` values are filename strings.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| `deprecated_attributes` list in `_index.json` + filter at `_scheme_from_index` | One code site; general/reusable; marker co-located with axis list; mapper untouched; data retained | Introduces a new config key (documented) | **Chosen** |
| `"deprecated": true` inside each `birth_location.json` block | Travels with the attribute | Marker scattered per-file; still needs the same chokepoint filter; less discoverable | Rejected |
| Delete `birth_location` from `_index.json` `attributes` | Simplest removal | Also drops it from the **mapper** (loses retained data); breaks `refine_from`; forces population regen; irreversible | Rejected |
| Per-stage exclusion lists | Explicit per stage | N edit sites; drift risk; violates single-source-of-truth | Rejected |

### Architecture & Module Contracts

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `_index.json` (`scb_native`, `scb`) | Declare comparison axis order + which axes are deprecated | (file) → `attributes` dict + `deprecated_attributes` list | Country identity, analysis internals |
| `_scheme_from_index` (`scheme.py`) | Build `ComparisonScheme` from index, honoring deprecation | index dict → `ComparisonScheme` (deprecated axes filtered from `attributes`/`categories`) | Which downstream stage consumes the axis |
| Mapper base (`real`/`synthetic`) | Map every attribute in `attributes` into canonical data | raw identity → canonical dict incl. `birth_location` | The `deprecated_attributes` list (ignores it entirely) |

Filter contract at `_scheme_from_index` (~line 313):
- Read `deprecated = list(index.get("deprecated_attributes", []))` (default empty → current behavior).
- **Fail loudly** if any name in `deprecated` is absent from `index["attributes"]` (config error).
- Build `attributes` and `categories` skipping deprecated names.
- **Fail loudly** if the filtered `attributes` list is empty (mirrors the non-empty guarantee `load_index` gives for `attributes`).

---

## Implementation Plan

### Phase 1: Deprecation mechanism (loader/scheme)
**Goal:** Teach `_scheme_from_index` to honor `deprecated_attributes`; default behavior unchanged.

**Started:** 2026-07-16
**Completed:** 2026-07-16

- [x] Task 1.1 — In `_scheme_from_index` (`scheme.py`), read `index.get("deprecated_attributes", [])`.
- [x] Task 1.2 — Validate each deprecated name exists in `index["attributes"]`; raise `ValueError`/`KeyError` if not (fail-fast).
- [x] Task 1.3 — Exclude deprecated names when building both `attributes` (line 313) and `categories` (loop 315-325).
- [x] Task 1.4 — Raise if the filtered `attributes` is empty.
- [x] Task 1.5 — (Optional) Extend `load_index` (`real_mapper/mappings.py:51-76`) to type-check `deprecated_attributes` is a list of strings when present; leave `attributes` semantics for the mapper unchanged.

**Files Modified:**
- `src/population_synthetic/analysis/fidelity/scheme.py` — filter deprecated axes in `_scheme_from_index`.
- `src/population_synthetic/analysis/mapping/real_mapper/mappings.py` — (optional) validate `deprecated_attributes` shape.

**Dependencies:** None

### Phase 2: Mark `birth_location` deprecated (config)
**Goal:** Declare the deprecation for Sweden's mapping tiers.

**Started:** 2026-07-16
**Completed:** 2026-07-16

- [x] Task 2.1 — Add `"deprecated_attributes": ["birth_location"]` to `config/mapping/scb_native/_index.json`.
- [x] Task 2.2 — Add the same to `config/mapping/scb/_index.json` (keep the two Sweden tiers in sync).
- [x] Task 2.3 — Add a short note in each `_index.json` `description` (or the tier README) explaining the marker and that the field is retained in data.

**Files Modified:**
- `config/mapping/scb_native/_index.json` — add `deprecated_attributes`.
- `config/mapping/scb/_index.json` — add `deprecated_attributes`.
- `config/mapping/scb_native/README.md`, `config/mapping/scb/README.md` — (optional) document the concept.

**Dependencies:** Phase 1

### Phase 3: Verify propagation & docs
**Goal:** Confirm every analysis stage honors the deprecation and record it.

**Started:** 2026-07-16
**Completed:** 2026-07-16

- [x] Task 3.1 — Verified at the analysis seam: `_scheme_from_index(scb_native, scb.json)` builds a 14-axis scheme with `birth_location` absent from `.attributes`/`.categories` and `birth_country_detail` retained. All named downstream consumers (`evaluator.py`, `charts.py`, `artifacts.py`, `multivariate.py`, `model_ranking/loader.py`, `method_significance/builder.py`, `consistency/rules.py`) read `scheme.attributes`/`.categories` — no hardcoded 15. A full end-to-end fidelity run was not executed (no seam-independent value beyond the scheme + consumer audit).
- [x] Task 3.2 — Confirmed the real mapper still emits `birth_location` in the canonical dict (`BaseRealMapper.normalize_individual` over the shared fixture, and `config/mapping/{scb_native,scb}/_index.json` still list `birth_location` in `attributes`). Data retained.
- [x] Task 3.3 — Updated `CLAUDE.md` "Full comparison output" invariant: the analyzed axis is `ComparisonScheme.attributes` (config-driven, not a fixed 15); notes `deprecated_attributes` and Sweden's 14 axes.
- [x] Task 3.4 — Updated `docs/architecture/comparison-mapping.md` documenting the `deprecated_attributes` key, its chokepoint (`_scheme_from_index`), and its fail-loud behavior.
- [x] Task 3.5 — Kept the `scripts/dev/audit_persona_realism.py` list (it audits raw persona *data*, which retains `birth_location`) and added a comment noting the analysis deprecation.

**Files Modified:**
- `CLAUDE.md`, `docs/architecture/comparison-mapping.md` — document the mechanism.
- `scripts/dev/audit_persona_realism.py` — (optional) consistency.

**Dependencies:** Phase 2

---

## Testing Plan

### Unit Tests
- [x] New test: `_scheme_from_index` with a `deprecated_attributes` entry omits it from `.attributes` and `.categories`.
- [x] New test: `deprecated_attributes` naming a non-existent attribute raises loudly.
- [x] New test: `deprecated_attributes` that would empty the axis list raises loudly.
- [x] New test: absent `deprecated_attributes` key → identical behavior to today (regression guard).
- [x] New test: `load_index` rejects a `deprecated_attributes` that is not a list of strings.

### Integration Tests
- [x] Load the real Sweden scheme (`scb_native`) and assert `birth_location` not in `scheme.attributes`, length 14.
- [x] Assert existing mapper tests still emit `birth_location` in the canonical dict (unchanged).

### Manual Verification
- [ ] Run `score_fidelity` / `compare_real_countries` for Sweden; inspect `03_Analysis/` for absence of `birth_location` chart and its presence-free radar/marginals CSV.
- [ ] Open a mapped population file; confirm `birth_location` field present per persona.

### Edge Cases
- [ ] Norway/Italy schemes (no `deprecated_attributes`) unaffected — full axis count retained.
- [x] Consistency scan (`scb_native.yaml`) still validates — no rule references `birth_location` (grep-confirmed), so no predicate becomes invalid.

---

## Documentation Plan

- [x] Update `CLAUDE.md` — note the deprecated-axis concept and Sweden's 14 analyzed axes.
- [x] Update `docs/architecture/comparison-mapping.md` — the `deprecated_attributes` key and chokepoint.
- [ ] Update memory `project-birth-field-realism-discrepancy.md` — record the deprecation resolution.

---

## Rollback Plan

1. Remove `"deprecated_attributes"` from the two `_index.json` files → analysis reverts to 15 axes.
2. Revert the `scheme.py` filter (single function) → default `index.get(..., [])` was a no-op anyway.
3. No data migration: populations were never regenerated; the field was always retained.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| A future consistency rule references the now-deprecated `birth_location`, failing `set(scheme.attributes)` validation (`rules.py:191`) | Low | Med | Documented; current `scb_native.yaml` has no such rule. If one is added, deprecate the rule in the same pass or add to `_EXTRA_ATTRS`. |
| Multivariate one-hot silently drops the attr (already skips absent categories) masking a config typo | Low | Low | Fail-fast validation of `deprecated_attributes` names in Phase 1 catches typos before analysis. |
| `scb` (global) tier diverges from `scb_native` if only one is updated | Low | Low | Task 2.2 updates both in the same phase. |
| Downstream reader assumes 15 axes | Low | Low | No hardcoded 15-count exists in the analysis path (verified); only prose/docs, updated in Phase 3. |

---

## References

- Memory: `project-birth-field-realism-discrepancy.md` (defect classes, gate mechanics)
- Chokepoint: `src/population_synthetic/analysis/fidelity/scheme.py:308-345`
- Gate/output: `src/population_synthetic/generators/real/sweden/sample_service.py:255-292`
- Related plan: `docs/development/plans/active/scb-source-improvements-implementation.md`

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- CLAUDE.md
- config/mapping/scb/_index.json
- config/mapping/scb_native/_index.json
- docs/architecture/comparison-mapping.md
- docs/development/plans/active/deprecate-birth-location-analysis-axis.md
- src/population_synthetic/analysis/fidelity/scheme.py
- src/population_synthetic/analysis/mapping/real_mapper/mappings.py
- tests/test_scheme_index.py
