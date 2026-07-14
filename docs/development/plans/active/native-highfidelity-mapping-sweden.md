# Plan: Native High-Fidelity Mapping Tier (Sweden)

**Date:** 2026-07-14
**Author:** Basil
**Status:** In Progress
**Base Branch:** `dev`
**Branch:** `feature/native-highfidelity-mapping-sweden`

---

## Overview

Introduce a **two-tier mapping architecture**. Today, both the real SCB population and
the LLM-synthetic population are collapsed into a single coarse per-country schema
(`config/mapping/scb`) purely so they can share a comparison axis — which also dumbs the
**real** data down below its native resolution. This plan adds a **native, high-fidelity
tier** (`config/mapping/scb_native`) that maps the synthetic population onto the real
data's *own* category values, so within-country fidelity is scored at full resolution.
The existing coarse schema is retained and reframed as the **global / cross-country tier**
("prestep") to be wired up later when comparing countries.

## Problem Statement

The current `config/mapping/scb/*.json` files define one canonical `values` set per
attribute into which **both** mappers collapse: the real mapper via the `real` matcher
block, the synthetic mapper via the `synthetic` block. That canonical set was chosen for
cross-country / LLM-reproducibility reasons and, for several attributes, is **coarser than
the resolution the real SCB pipeline actually produces**. Concretely (verified against live
config + source):

| attribute | coarse values | native (real) values | verdict |
|---|---|---|---|
| industry_sector | 9 | 12 | **GAIN** — 12 SNI2007 groups folded to 8 sectors (+ Not Applicable) |
| employment_type | 6 | 9 | **GAIN** — 3 attachment × 3 hours composite folded to 5 (+ N/A) |
| parental_structure | 3 | 6 | **GAIN** — 6 family types folded to 3 (stepparent/blended lost into Nuclear) |
| age_group | 7 | 68 | GAIN but numeric (single-year); **deferred**, see Out of Scope |
| employment_status | 2 | 2 | REAL-LIMITED — SCB extract can't separate students/retirees |
| socioeconomic_class | 4 | 4 | SAME — parser already collapses 26 income brackets upstream |
| biological_sex, education_level, birth_location, region, civil_status, housing_tenure, household_size, income_source, birth_country_detail | = | = | SAME — 1:1 relabel, no resolution lost |

Only **3 categorical attributes** (`industry_sector`, `employment_type`,
`parental_structure`) actually lose native real granularity to the coarse collapse. Because
the real data is collapsed to match the LLM, the fidelity scores can't currently reveal
whether the LLM reproduces the *fine-grained* real distribution — which is exactly the
signal a demographic-fidelity benchmark should measure.

This matters for the LLM-population-fidelity manuscript: the "strategy > model" finding is
currently measured on a lossy axis. A native tier tests fidelity at the resolution the real
statistics actually carry.

## Goals

### In Scope
1. Add a `config/mapping/scb_native/` tier whose `values` sets restore native real
   resolution for the 3 GAIN attributes, and are identical to the coarse schema for the
   other attributes.
2. Author `synthetic` matcher blocks for the 3 GAIN attributes at native resolution, and
   confirm `real` blocks pass raw SCB labels through at native resolution.
3. Point Sweden's **within-country** map + score pipeline at the native tier (via the
   country axis YAML), so the default Sweden fidelity report is high-resolution.
4. Retain the existing coarse `config/mapping/scb/` untouched and reframe it (in docs) as
   the future global / cross-country tier.
5. Keep the existing coarse comparison path runnable (opt-in) so native-vs-coarse score
   deltas can be measured for the paper.

### Out of Scope
- **The global / cross-country collapse itself** (native → global value lookup, Sweden vs
  Italy vs Norway harmonization). Design sketch only; implementation deferred until
  cross-country analysis is actually built.
- **Italy (`istat`) native tier.** Sweden-first. Italy follows the same pattern later.
- **`age_group` fine binning.** 68 single-year bins make chi-sq / joint cells too sparse;
  choosing a finer-but-safe bin scheme (e.g. 5-year) is a separate numeric-binning decision,
  not matcher authoring. Left at the current 7 bins for this pass.
- **Changing the multivariate/scheme tuning** (`config/analysis/fidelity/scb.json`
  joint_pairs / coherence / C2ST) beyond what's required for the extra categories to load.

## Success Criteria

- [ ] `config/mapping/scb_native/` exists with a full 15-attribute `_index.json` and per-attribute files; the 3 GAIN attributes expose native-resolution `values` (12 / 9 / 6), the other 12 match the coarse schema.
- [ ] `map_populations.py` produces `real_swedish.json` at native resolution (industry_sector shows up to 12 distinct values, parental_structure up to 6, employment_type up to 9) with **no** raw SCB label reported as `unmapped`.
- [ ] A synthetic population maps onto the native schema; the fraction of synthetic values routed to `on_miss`/`Other` is reported per attribute (baseline metric for authoring quality).
- [ ] `score_fidelity_sweden.py` runs against the native mapped files and emits a full fidelity report (all 15 attributes, radar, JSON, CSV) with no schema-mismatch errors.
- [ ] The coarse pipeline still runs when explicitly selected (regression: existing `config/mapping/scb` outputs unchanged).
- [ ] `pytest` green (sampling, mapping, fidelity, multivariate, comparison, workflow, run_analytics).

---

## Technical Design

### Approach

Layered mapping. The **native tier** becomes the primary raw→canonical mapping for
within-country work; the **global tier** (current coarse config) becomes a downstream
collapse used only for cross-country comparison.

```
                      ┌─────────────────────────── within-country fidelity (NOW) ───┐
raw SCB / LLM  ──►  NATIVE tier (config/mapping/scb_native)  ──►  score_fidelity  ──►  high-res report
                                    │
                                    └──►  GLOBAL collapse (native→global, DEFERRED)  ──►  cross-country compare
```

The native tier is derived from the current coarse config: **copy the 12 SAME/REAL-LIMITED
attribute files verbatim** (their coarse `values` already equal native resolution), and
**expand only the 3 GAIN attribute files** — widen their `values` set and extend the `real`
and `synthetic` matcher blocks to the finer categories.

The mapping engine, both mapper hierarchies, and the scheme loader already select their
config directory by a single knob (`parameters.mappings` in the country axis YAML, mirrored
by `MAPPINGS_SUBDIR` on the mapper classes and the scheme loader). Repointing Sweden to the
native dir is therefore a config + small dir-resolution change, **not** an engine rewrite.
No changes to `mapping_engine.resolve()` semantics are required — it is already a symmetric
resolver over `(raw, block, values)`.

### Why the real block is near-identity

For the 3 GAIN attributes the raw SCB labels are *already* the native categories (12 SNI
groups; the attachment×hours composite; the 6 LE0102T17 family types). The current coarse
`real` block deliberately merges them. The native `real` block simply maps each raw label to
its own clean canonical name (1:1) instead of merging — mechanically simpler than the coarse
block, no new matcher tiers needed.

### Where the effort actually is

Authoring the **native `synthetic` matcher blocks** for the 3 GAIN attributes. The LLM emits
free-text; the existing synthetic cascades resolve to the coarse buckets. Native resolution
needs finer keyword rules to separate, e.g., manufacturing vs construction; permanent vs
temporary vs self-employed × full/part-time; nuclear vs blended/stepparent vs single-parent.
This is the core risk (see Risks): the LLM text may not carry enough signal, inflating
`on_miss → Other`. The `on_miss` rate per attribute is therefore a first-class success metric.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **Layered: native primary + coarse reframed as global** | Matches user intent ("redirect current mapping into a cross-country prestep"); native is single source; minimal engine change | Some config duplication for the 12 identical attrs | **Chosen** |
| Parallel independent dirs (raw→native and raw→coarse both authored from scratch) | Lowest coupling to existing outputs | Duplicates synthetic matcher authoring across both tiers; two sources of truth | Rejected |
| Edit coarse config in place to native resolution (no second dir) | No duplication | Destroys the cross-country axis; breaks the deferred global tier; not reversible for cross-country compare | Rejected |
| Derive native `values` from the real population at runtime | No hand-authored value lists | Violates "config is single source of truth / fail-loud"; unstable chart axes | Rejected |

### Architecture Changes

- **New:** `config/mapping/scb_native/` — `_index.json` + 15 attribute files. 12 copied from
  `scb/`, 3 expanded (`industry_sector.json`, `employment_type.json`,
  `parental_structure.json`).
- **Modified:** `config/synthetic/axes/countries/swedish.yaml` — `parameters.mappings` →
  `config/mapping/scb_native` (within-country default).
- **Modified (mapper/scheme dir resolution):** `SwedishSyntheticMapper` /
  `SwedishRealMapper` `MAPPINGS_SUBDIR`, and the fidelity scheme loader's subdir, must resolve
  to `scb_native` for Sweden — kept in sync with the YAML. Confirm whether one knob can drive
  all three (preferred) rather than three edits.
- **Possibly modified:** `config/analysis/fidelity/scb.json` — only if the extra categories
  need it to load; attribute *names* are unchanged so joint_pairs/coherence keys stay valid.
- **Docs:** `config/mapping/scb/README.md` gains a note that it is now the (deferred) global
  tier; a new `config/mapping/scb_native/README.md` documents the native tier.

---

## Implementation Plan

### Phase 1: Native config scaffold (no behavior change yet)
**Goal:** Create the native tier dir with the 12 unchanged attributes; pipeline still points at coarse.
**Started:** 2026-07-14 · **Completed:** 2026-07-14

- [x] 1.1 — Create `config/mapping/scb_native/` and copy the 12 SAME/REAL-LIMITED attribute files + `_index.json` verbatim from `config/mapping/scb/`.
- [x] 1.2 — Author `industry_sector.json` at 12 native values: split the coarse merges (manufacturing|construction; trade|transport|accommodation; info-comm|financial-business) into their SNI2007 groups; `real` block 1:1 from raw labels; extend `synthetic` cascade.
- [x] 1.3 — Author `employment_type.json` at 9 native values: restore the 3×3 attachment×hours grid; `real` composite matcher over `{attachment}|{hours}`; extend `synthetic` block.
- [x] 1.4 — Author `parental_structure.json` at 6 native values (natural-parent, mother+stepparent, father+stepparent, single-mother, single-father, other-than-parents); `real` 1:1; extend `synthetic` block.
- [x] 1.5 — Add `config/mapping/scb_native/README.md`.

**Files Modified:** new files under `config/mapping/scb_native/`.
**Dependencies:** None.

### Phase 2: Real-side validation at native resolution
**Goal:** Prove the real SCB population maps onto native with zero `unmapped`.
**Started:** 2026-07-14 · **Completed:** 2026-07-14

- [x] 2.1 — Run `map_populations.py` against a scratch config pointed at `scb_native` (temporary, not the committed YAML) and inspect `real_swedish.json`. *(Done via a scratch script constructing the Swedish real mapper pointed at `config/mapping/scb_native`; `swedish.yaml` left untouched. Mapped all 10 000 real individuals cleanly.)*
- [x] 2.2 — Assert every raw SCB label for the 3 GAIN attributes resolves (no `unmapped`); fix `real` matchers until clean. **Zero `unmapped`** against the real population — no matcher fixes were required. Observed native distributions: `industry_sector` 12 SNI groups + `Not Applicable` (1342); `employment_type` all 9 attachment×hours cells + `Not Applicable` (1342), incl. raw `self-employed + family workers` resolving via the `self-employed` `contains` rule; `parental_structure` all 6 family types (Natural Parents 7431, Single Mother 1402, Single Father 466, Mother+Stepparent 458, Father+Stepparent 173, Other Than Parents 70).
- [x] 2.3 — Confirm the 12 copied attributes are byte-for-byte equivalent in output to the coarse run. **All 12 SAME attributes produce identical marginals** across `config/mapping/scb` vs `config/mapping/scb_native` (age 68 cats, biological_sex 2, education_level 8, employment_status 2, birth_location 3, socioeconomic_class 4, region 21, civil_status 4, housing_tenure 3, household_size 7, income_source 6, birth_country_detail 21).

**Files Modified:** `config/mapping/scb_native/*.json` (matcher fixes only).
**Dependencies:** Phase 1.

### Phase 3: Synthetic-side authoring + on_miss baseline
**Goal:** Map a real synthetic population onto native; measure `on_miss`/`Other` rates.
**Started:** 2026-07-14 · **Completed:** 2026-07-14

- [x] 3.1 — Map an existing synthetic manifest onto `scb_native`; compute per-attribute `on_miss`/`Other` fraction for the 3 GAIN attributes. *(Mapped 4 existing Swedish runs via a scratch script pointed at `scb_native`, `swedish.yaml` untouched. Primary authoring target: `swedish_all_pick_claude_haiku` (n=500, the most string-diverse run — 56/43/39 distinct raw values for the 3 GAIN attrs), cross-checked on `swedish_all_pick_claude_sonnet` (100), `swedish_all_pick_claude_opus` (100), `swedish_all_generate_pick_claude_sonnet` (100). **Baseline on_miss (haiku 500):** industry_sector 7.8%, employment_type 58.4%, parental_structure 83.4%.)*
- [x] 3.2 — Iterate the native `synthetic` cascades to reduce `on_miss` where the LLM text carries signal; document residual (irreducible) `on_miss`. *(Edited `employment_type.json` + `parental_structure.json`; `industry_sector.json` left as-is — already 0–7.8%. **Post-edit on_miss:** industry_sector 0–7.8% (residual = generic "services"/"Tjänster", genuinely ambiguous → stays `Other`); employment_type 0%; parental_structure 0%. **Caveat (irreducible residual):** driving employment_type and parental_structure on_miss to 0 collapses them to a single modal cell — 100% `Permanent Full-time` and 100% `Natural Parents` on every run — because the LLM free-text almost never states work-hours bands / permanent-vs-temporary, nor stepparent/single-parent status. The minority native classes DO resolve when explicitly stated (27/27 unit cases pass, e.g. "Two-parent household (mother and stepfather)" → Mother and Stepparent, "visstidsanställning, heltid" → Temporary Full-time), but the synthetic populations effectively never emit that signal. **industry_sector is the only genuine native-resolution win** (spreads across 8+ of 12 categories). **Recommendation → Phase 4:** keep `employment_type` COARSE-in-native (both tiers collapse to Permanent Full-time from synthetic text — native gains nothing but a misleadingly fine axis the synthetic can never populate); `parental_structure` is borderline (degrades gracefully to modal Natural Parents, directionally correct vs real 74% Natural, and would capture minority classes from a richer generator) — keep native but flag that with current runs it reads ~100% Natural Parents.)*

**Files Modified:** `config/mapping/scb_native/{employment_type,parental_structure}.json` (industry_sector unchanged).
**Dependencies:** Phase 2.

### Phase 4: Repoint Sweden's within-country pipeline
**Goal:** Make native the default for Sweden map + score.
**Started:** 2026-07-14 · **Completed:** 2026-07-14

- [x] 4.1 — Set `parameters.mappings: config/mapping/scb_native` in `swedish.yaml`.
- [x] 4.2 — Ensure `SwedishSyntheticMapper` / `SwedishRealMapper` / scheme loader resolve `scb_native` consistently (single knob if feasible). *(YAML is the single source of truth; both Swedish `MAPPINGS_SUBDIR` class defaults set to `scb_native` to match it; the fidelity scheme's default directory now resolves through the new fail-loud guard `country_config.assert_mapping_dir_consistency`, which raises if the YAML and either mapper class default disagree. The analysis-tuning filename is decoupled in `scheme._analysis_path` — it strips the `_native` tier suffix so `scb_native` reuses the shared attribute-name-keyed `config/analysis/fidelity/scb.json` (unchanged). Italy path unaffected.)*
- [x] 4.3 — Full `map_populations.py` → `score_fidelity_sweden.py` run; confirm all 15 attributes score, radar/JSON/CSV emitted, no schema mismatch. *(Scored `seed_022_all_pick_sonnet` (n=100). All 15 marginals scored; radar + per-attribute bars + JSON report + marginals CSV + association/c2st/joint_fidelity/combination/joint_chi_sq/coherence CSVs + all multivariate figures emitted; zero schema-mismatch / unmapped errors. Real mapped n=10000 at native resolution.)*
- [x] 4.4 — Verify multivariate block loads (watch chi-sq cell sparsity on the widened attributes). *(Multivariate ran: C2ST sklearn AUC=0.998 p=0.005; Cramér's V mean|dV|=0.1365 over 105 pairs; 8 joint-TV pairs; combination check impossible=0 rare=0. None of the configured joint pairs / coherence triple involve the 3 widened attributes, so widening introduces NO joint-cell sparsity — they are scored on their marginal chi-sq only. Marginal chi-sq expected-cell sparsity (expected = real_prop × 100): industry_sector 4/13 cells <5 (none <1); employment_type 5/10 <5 (none <1, synthetic degenerate to 1 cell); parental_structure 4/6 <5 (1 cell <1: "Other Than Parents"=0.70). The evaluator has NO expected<5 validity guard — it drops only expected==0 cells and returns NaN when <2 valid categories remain; with small-but-positive minority cells it still computes a finite chi-sq p (industry 1.2e-77, employment 1.8e-12, parental 1.8e-6). No crash, no silent drop; the huge divergences make the "significant" verdict unambiguous even though the exact p is inflated by the sub-5 minority cells.)*

**Files Modified:** `config/synthetic/axes/countries/swedish.yaml`; `src/population_synthetic/analysis/mapping/{synthetic_mapper,real_mapper}/sweden.py` (`MAPPINGS_SUBDIR` → `scb_native`); `src/population_synthetic/analysis/fidelity/scheme.py` (`_analysis_path` suffix-strip + `_scheme_dir` guard call); `src/population_synthetic/analysis/utils/country_config.py` (new `assert_mapping_dir_consistency` guard).
**Dependencies:** Phase 3.

### Phase 5: Docs + global-tier reframing (design only)
**Goal:** Document the two tiers; sketch the deferred global collapse.
**Started:** 2026-07-14 · **Completed:** 2026-07-14

- [x] 5.1 — Note in `config/mapping/scb/README.md` that it is now the (deferred) global/cross-country tier. *(Top-of-file tier note added; cross-links to `config/mapping/scb_native/README.md`.)*
- [x] 5.2 — Add a "Global tier (deferred)" design note: native→global is a per-attribute value→bucket lookup defined only for the collapsing attributes (identical attributes pass through), authored when cross-country analysis is built. *(Appended "Global tier (deferred) — design only" section to `config/mapping/scb/README.md`: native→global finite value→bucket lookup, fail-loud, only for collapsing attrs; Italy gets its own `istat_native` by the same pattern.)*
- [x] 5.3 — Update `docs/architecture/comparison-mapping.md` + `CLAUDE.md` mapping description for the two-tier model. *(New "Mapping tiers: native vs global" section in the wiki page documenting the `parameters.mappings` source-of-truth + `assert_mapping_dir_consistency` guard + `_analysis_path` suffix-strip; CLAUDE.md `mapping/` description gets a lean two-tier sentence + wiki pointer.)*

**Files Modified:** docs only.
**Dependencies:** Phase 4.

---

## Testing Plan

### Unit Tests
- [ ] Native `industry_sector` real matcher: each of the 12 raw SNI labels → its own native value.
- [ ] Native `employment_type` composite matcher: representative `{attachment}|{hours}` pairs → the 9 grid cells.
- [ ] Native `parental_structure` real matcher: the 6 LE0102T17 family types → 6 distinct values (stepparent variants NOT folded into Nuclear).
- [ ] Synthetic cascade: representative LLM strings route to the intended native value; unmatched → `on_miss` default.
- [ ] `_index.json` loads for `scb_native`; scheme builds 15 attributes.

### Integration Tests
- [ ] `map_populations.py` on `scb_native`: real has zero `unmapped`; synthetic `on_miss` rate reported.
- [ ] `score_fidelity_sweden.py` end-to-end on native mapped files: full artifact set, no schema-mismatch.
- [ ] Regression: coarse `scb` run output unchanged vs pre-change baseline.

### Manual Verification
- [ ] Diff native `real_swedish.json` marginals vs coarse: the 3 GAIN attributes show more categories; the other 12 identical.
- [ ] Spot-check the fidelity radar renders all 15 attributes on the native axis.

### Edge Cases
- [ ] Sparse joint tables: a 12-category attribute in a joint chi-sq with adequate vs inadequate cell counts — confirm graceful behavior, not a crash.
- [ ] Synthetic value seen in native but absent in real (and vice versa) — tabulation still aligns on the `values` axis.

---

## Documentation Plan

- [ ] `config/mapping/scb_native/README.md` — native tier purpose, per-attribute resolution.
- [ ] `config/mapping/scb/README.md` — reframe as deferred global tier.
- [ ] Update `CLAUDE.md` + `docs/architecture/comparison-mapping.md` for the two-tier model.
- [ ] Changelog entry.

---

## Rollback Plan

1. **Config-only, fully reversible.** The change is additive (new dir) plus a one-line YAML
   repoint. To revert: set `swedish.yaml` `parameters.mappings` back to `config/mapping/scb`
   and revert the mapper/scheme subdir edits.
2. **Data considerations:** No migrations. Mapped/scored outputs are regenerated artifacts;
   re-running the coarse pipeline restores prior outputs bit-for-bit.
3. **Rollback procedure:** revert the feature branch merge; `config/mapping/scb_native/` can
   be left in place (inert) or deleted.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LLM free-text lacks signal to resolve 12/9/6-way native categories → high `on_miss`/`Other`, diluting the fidelity benefit | High | Med | Treat `on_miss` rate as a success metric; document irreducible residual; if a GAIN attribute can't be resolved from LLM text, keep it coarse in native (per-attribute opt-out) rather than forcing it |
| Widened categories make chi-sq / joint cells sparse, distorting metrics | Med | Med | Watch cell counts in Phase 4.4; if sparse, note in report or fall back that attribute; do not silently drop |
| Three separate subdir knobs (YAML, mapper `MAPPINGS_SUBDIR`, scheme loader) drift out of sync | Med | Med | Prefer a single source (country YAML) driving all three; add a startup assertion that they agree |
| Duplication between `scb` and `scb_native` for 12 identical attrs invites divergence over time | Low | Low | Note in README they must track until the global tier is formalized as a native→global overlay |
| `config/analysis/fidelity/scb.json` assumes coarse category counts somewhere | Low | Med | Verify it references attribute names not value counts; add native variant only if needed |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — native scaffold + 3 GAIN files | ~0.5 day | None |
| Phase 2 — real-side validation | ~0.25 day | Phase 1 |
| Phase 3 — synthetic authoring + on_miss baseline | ~1 day (main effort) | Phase 2 |
| Phase 4 — repoint + full run | ~0.5 day | Phase 3 |
| Phase 5 — docs + global sketch | ~0.25 day | Phase 4 |

---

## References

- Related plan: `docs/development/plans/pending/uniform-analysis-output-naming.md`
- Mapping architecture: `docs/architecture/comparison-mapping.md`, `config/mapping/scb/README.md`
- Evidence (native vs coarse): `fetch_service.py`, `parsers.py`, `constants.py`, `config/mapping/scb/*.json`, `fidelity/evaluator.py`, `fidelity/scheme.py`

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- CLAUDE.md
- config/mapping/scb/README.md
- config/mapping/scb_native/README.md
- config/mapping/scb_native/_index.json
- config/mapping/scb_native/age.json
- config/mapping/scb_native/biological_sex.json
- config/mapping/scb_native/birth_country_detail.json
- config/mapping/scb_native/birth_location.json
- config/mapping/scb_native/civil_status.json
- config/mapping/scb_native/education.json
- config/mapping/scb_native/employment.json
- config/mapping/scb_native/employment_type.json
- config/mapping/scb_native/household_size.json
- config/mapping/scb_native/housing_tenure.json
- config/mapping/scb_native/income_source.json
- config/mapping/scb_native/industry_sector.json
- config/mapping/scb_native/parental_structure.json
- config/mapping/scb_native/region.json
- config/mapping/scb_native/socioeconomic.json
- config/synthetic/axes/countries/swedish.yaml
- docs/architecture/comparison-mapping.md
- docs/development/plans/active/native-highfidelity-mapping-sweden.md
- src/population_synthetic/analysis/fidelity/scheme.py
- src/population_synthetic/analysis/mapping/real_mapper/sweden.py
- src/population_synthetic/analysis/mapping/synthetic_mapper/sweden.py
- src/population_synthetic/analysis/utils/country_config.py

---
