# Plan: Condition Swedish `employment_status` on age

**Date:** 2026-07-15
**Author:** Basil
**Status:** In Progress
**Base Branch:** `dev`
**Branch:** `feature/sweden-employment-status-by-age`

---

## Overview

The Sweden generator currently draws `employment_status` from `P(status | sex, education)`,
even though the source SCB LFS table `NAKUBefUtbNivAr` (AM0401P) can be sliced by age. This
plan makes the pipeline actually request and condition on age — `P(status | age_group, sex,
education)` — adding an age dimension to the fetch query, a new age-keyed distribution, and an
age-aware Step-3 sampler lookup. Age is the strongest driver of labour-force participation
(students, prime-age workers, retirees), so this is a direct fidelity gain.

## Problem Statement

The Sweden generation explorer flags exactly one **unused-but-available** conditioning
dimension: the `employment` node carries `verdict: "option"` with `option.dims: ["age"]`
(`docs/architecture/sweden-generation-explorer/js/data.js:35-43`). This was confirmed real across
all three pipeline layers:

- **Fetch** — `fetch_employment_by_sex_education` (`sweden/fetch_service.py:88-103`) selects
  only `Arbetskraftstillh × UtbildningsNiva × Kon` — **no `Alder` code**. Age is dropped at the
  query level, not marginalized by the parser.
- **Parse** — `parse_employment_by_sex_education` (`sweden/parsers.py:110-205`) keys
  `{sex: {edu: {status: prob}}}` — no age dimension.
- **Sample** — Step 3 (`sweden/sample_service.py:136-154`) draws employment from
  `(sex_label, education_level)` only; `age_group` (already computed at line 114) is ignored.

Every other conditional Swedish attribute that *can* condition on age *does*
(`education_by_age`, `employment_type_by_age`, `civil_status_by_age_sex`, `socioeconomic`).
Employment status is the lone exception, which both lowers fidelity and leaves a standing
`"option"` verdict in the explorer.

## Goals

### In Scope
1. Add an `Alder` selection to the `NAKUBefUtbNivAr` fetch query so employment data arrives
   sliced by age.
2. Add a new, **Sweden-only**, age-keyed distribution
   `employment_by_age_sex_education` keyed `(age_group, sex) -> {edu: {status: prob}}`.
3. Condition the Sweden sampler's Step 3 on `(age_group, sex, education)` with a multi-stage
   fallback mirroring the existing `education` (Step 2) and `employment_type` (Step 7) patterns.
4. Update the generation-explorer `employment` node so it no longer advertises an unused filter
   (`verdict: "option"` → `"equivalent"`).
5. Add unit tests for the new parser and the age-conditioned sampler path (none exist today).

### Out of Scope
- **Norway and Italy.** Both share `PopulationDistributions.employment_by_sex_education` and
  must be left byte-for-byte unchanged. This plan is additive and Sweden-only.
- Reshaping the shared `employment_by_sex_education` field.
- The coarser cross-country `global` mapping tier (`config/mapping/scb`) — untouched.
- Any change to the fidelity/comparison scoring stages.

## Success Criteria

- [ ] `scripts/generate/generate_scb_population.py --n 1000 --seed 42` runs to completion with
      the new `Alder` code (no fail-fast on an unknown SCB code).
- [ ] Generated `employment_status` visibly varies by age (e.g. `65-74`/`75-85` skew toward
      non-employed/retired; prime-age bands skew toward employed).
- [ ] New parser test passes: `(age_group, sex)` keys, inner dists sum to 1.0, out-of-range
      bands dropped, fully-suppressed subgroups skipped (not raised).
- [ ] New sampler test passes: age-band data is used when present; a `75-85` person is served
      by the fallback rather than raising.
- [ ] `pytest` full suite green; Norway/Italy sampling behaviour unchanged.
- [ ] `ruff check src/` clean.
- [ ] Explorer `employment` node shows `verdict: "equivalent"`, `used: ["age","sex","education"]`.

---

## Technical Design

### Approach

Mirror the two age-conditioned patterns already proven in the Sweden generator rather than
inventing anything new:

- **`education_by_age`** — parser age handling (`resolve_age_group` + `VALID_AGE_GROUPS` filter,
  `parsers.py:90-96`) and the sampler's 3-stage fallback (`sample_service.py:117-133`).
- **`employment_type_by_age`** — the `(age_group, sex)` tuple-keyed dataclass shape and the
  Step-7 fallback chain (`sample_service.py:194-211`).

The one hard constraint: `employment_by_sex_education` (`generators/real/data.py:25`) is
**shared** — Norway (`norway/sample_service.py:167`) and Italy (`italy/sample_service.py:124`)
both populate and read it as `{sex: {edu: {status}}}`. So we **add a new field** rather than
reshape the existing one. The new field is defaulted, so Norway/Italy construction is untouched.

Age bands: SCB LFS (AM0401) tables expose 10-year bands. `resolve_age_group` bins by the band's
lower-bound integer, and the `age_group_map` override (always `{}` today) is the intended escape
hatch for a band whose lower bound would misbucket. We request bands that align 1:1 with
`VALID_AGE_GROUPS` and route the youngest via the map. `resolve_age_group` lives in
`generators/real/helpers.py:29-44`; `VALID_AGE_GROUPS` / `AGE_GROUP_BOUNDS` at `helpers.py:14-19`.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **Add a new Sweden-only age-keyed field** (`employment_by_age_sex_education`), default-valued | Norway/Italy fully insulated; mirrors `employment_type_by_age` exactly; additive | One extra dataclass field | **Chosen** |
| **Re-key the shared `employment_by_sex_education` to `(age_group, sex)`** | No new field | Breaks Norway + Italy parsers/samplers (shape mismatch); reshapes a shared contract | Rejected |
| **Keep employment age-blind; document as a known limitation** | Zero code | Leaves the explorer's `option` verdict and the fidelity gap in place; contradicts the user request | Rejected |

### Architecture Changes

- **New dataclass field** on the shared `PopulationDistributions`
  (`generators/real/data.py`), defaulted via `dataclasses.field(default_factory=dict)` and
  appended **last** so no positional/keyword construction site breaks:
  `employment_by_age_sex_education: dict[tuple[str, str], dict[str, dict[str, float]]]`.
  The existing `employment_by_sex_education` is left exactly as-is.
- **New parser** `parse_employment_by_age_sex_education` in `sweden/parsers.py`, adapted from
  the current `parse_employment_by_sex_education`.
- **Fetch** gains an `Alder` selection and passes an `age_group_map` override; Sweden's
  `load_all` populates the new field and passes `employment_by_sex_education={}` (Sweden stops
  using the shared field).
- **Sampler** Step 3 becomes age-aware.
- **Explorer** node metadata edited by hand (the embed script injects only population data, not
  the DAG nodes).

Design principles applied (per data-pipeline-engineering guides): single source of truth for age
bands (`helpers.py`), fail-fast retained at the whole-distribution level, no synthetic
distributions (all probabilities still from a real SCB response), and the shared cross-country
contract left stable (backward-compatible additive change).

---

## Implementation Plan

### Phase 1: Distribution plumbing (data + fetch + parse)
**Goal:** Employment data arrives sliced by age and lands in a new age-keyed field.

**Started:** 2026-07-15

> **⛔ BLOCKER (2026-07-15) — Phase 1 premise is invalid; implementation halted.**
> Live SCB PxWeb metadata for `AM/AM0401/AM0401P/NAKUBefUtbNivAr` (fetched via
> `SCBPxWebClient.get_table_metadata`) shows the table has **no `Alder` variable**. Its
> full variable set is `Arbetskraftstillh`, `UtbildningsNiva`, `Kon`, `ContentsCode`,
> `Tid` — age is aggregated into the fixed universe "Population aged 15-74". Adding an
> `Alder` selection to this query would be rejected by the API (fail-fast), so tasks
> 1.3–1.5 as written cannot be implemented.
>
> The whole education sub-family (`AM/AM0401/AM0401P/*`) is fixed at "aged 15-74" with no
> age breakdown. SCB LFS does not publish the 4-way cross-tab
> `labour_status × age × sex × education` in any single table. The two relevant marginals:
> - `AM/AM0401/AM0401P/NAKUBefUtbNivAr` — labour status × **education** × sex (no age) [current source]
> - `AM/AM0401/AM0401A/AKURLBefAr` — labour status × **age** × sex (no education);
>   `Alder` codes: `15-24, 25-34, 35-44, 45-54, 55-64, 65-74` (plus totals/overlaps).
>
> **Decision:** no source-code changes made this phase. Achieving `P(status | age, sex,
> education)` requires a design revision (e.g. combine the two tables via an
> independence assumption like the existing `parse_employment_type_combined` attachment×hours
> merge, or drop education in favour of age). That is out of Phase 1's stated scope and
> needs the plan author's decision before proceeding. Task 1.1 (the additive dataclass
> field) is harmless but was left undone to avoid a dangling, unused field ahead of a
> possible redesign.

- [ ] 1.1 — `data.py`: import `field` from `dataclasses`; append
      `employment_by_age_sex_education: dict[tuple[str, str], dict[str, dict[str, float]]] =
      field(default_factory=dict)` to `PopulationDistributions`. Leave
      `employment_by_sex_education` unchanged.
- [ ] 1.2 — **Confirm the real `Alder` value codes** `NAKUBefUtbNivAr` exposes (one-off GET of
      the PxWeb table URL or the SCB web UI — `SCBPxWebClient` has no metadata method). Fail-fast
      will catch a wrong code, but verify to avoid a wasted live run.
- [ ] 1.3 — `sweden/parsers.py`: add `parse_employment_by_age_sex_education(raw, age_group_map)`
      adapted from `parse_employment_by_sex_education` — detect the 4th `Alder` dimension,
      add its stride, compute `age_group = resolve_age_group(age_raw, age_group_map)`,
      `if age_group not in VALID_AGE_GROUPS: continue`, key by `(age_group, sex)`. Keep `".."`/
      `None` → `0.0` suppression; **change the fully-suppressed raise (`parsers.py:194-198`) into
      a skip** (drop that subgroup — the sampler fallback covers it), and raise **only** if the
      whole result is empty. Normalize each innermost `{status: prob}` to 1.0.
- [ ] 1.4 — `sweden/fetch_service.py`: rename `fetch_employment_by_sex_education` →
      `fetch_employment_by_age_sex_education`; add the `Alder` selection to the query
      (recommended `["15-24","25-34","35-44","45-54","55-64","65-74"]`, mirroring the AM0401
      attachment query at `:227-229`, or a finer youngest band if the table offers one); call
      the new parser with `age_group_map={"15-24": "18-24"}` (route the youngest band; avoid any
      band straddling a pipeline cut without a matching map entry).
- [ ] 1.5 — `sweden/fetch_service.py` `load_all` (`:330-374`): wire the renamed fetcher into
      `employment_by_age_sex_education=...` and pass `employment_by_sex_education={}` for Sweden.

**Files Modified:**
- `src/population_synthetic/generators/real/data.py` — new defaulted field + `field` import
- `src/population_synthetic/generators/real/sweden/parsers.py` — new age-aware parser
- `src/population_synthetic/generators/real/sweden/fetch_service.py` — `Alder` query + rename + `load_all` wiring

**Dependencies:** None

### Phase 2: Age-conditioned sampling
**Goal:** Step 3 draws employment from `(age_group, sex, education)`.

- [ ] 2.1 — `sweden/sample_service.py`: rewrite Step 3 (`:136-154`) to look up
      `distributions.employment_by_age_sex_education.get((age_group, sex_label))` (age_group is
      already in scope from `:114`), then `_resolve_edu_key(education_level, dist)`.
- [ ] 2.2 — Add the multi-stage fallback: (1) exact `(age_group, sex_label)`; (2) same
      age_group, other sex; (3) same sex, other age_group (`reversed(list(VALID_AGE_GROUPS))` —
      covers `75-85`); (4) else raise `ValueError` naming age_group, sex, education.
      `_resolve_edu_key` (`:77-90`) and `is_employed` logic unchanged.

**Files Modified:**
- `src/population_synthetic/generators/real/sweden/sample_service.py` — Step 3 age-conditioned lookup

**Dependencies:** Phase 1

### Phase 3: Explorer + docs
**Goal:** The explorer and architecture docs reflect the now-fetched age conditioning.

- [ ] 3.1 — `docs/architecture/sweden-generation-explorer/js/data.js` employment node (`:35-43`):
      `verdict: "equivalent"`, `used: ["age","sex","education"]`, `option: null`,
      `caption: "| age, sex, education"`, add `Alder [...]` to `query`, rewrite `note`.
      Also revisit the `CATALOG_SOURCES.employment` block in the same file (the "By
      output category" tab): the `used` table / `intro` change once age is fetched.
- [ ] 3.2 — Update any architecture-doc prose that describes employment as sex×education-only
      (e.g. `docs/architecture/comparison-mapping.md` if it enumerates conditioning), if present.

**Files Modified:**
- `docs/architecture/sweden-generation-explorer/js/data.js` — employment node metadata (+ `CATALOG_SOURCES.employment`)
- `docs/architecture/*.md` — conditioning descriptions (only if they name the old behaviour)

**Dependencies:** Phase 2

---

## Testing Plan

### Unit Tests
- [ ] `parse_employment_by_age_sex_education`: small json-stat2 fixture with an `Alder`
      dimension → asserts `(age_group, sex)` keys, inner `{edu: {status}}` sums to 1.0,
      out-of-range bands dropped, `15-24` routed to `18-24` via `age_group_map`.
- [ ] Parser suppression: a fully-suppressed `(age_group, sex, edu)` subgroup is skipped, not
      raised; an all-empty result still raises.
- [ ] `SampleService.sample_one`: minimal `PopulationDistributions` with the new field populated
      for a couple of `(age_group, sex)` keys → a person in a populated band draws from that
      band; a `75-85` person is served by the fallback (no raise).

### Integration Tests
- [ ] Full `pytest` run green — sampling, mapping, fidelity, multivariate, comparison, workflow,
      run_analytics — confirming no regression.
- [ ] `test_norway_sampler.py` still green (shared field untouched); spot-check Italy sampling.

### Manual Verification
- [ ] `python scripts/generate/generate_scb_population.py --n 1000 --seed 42 --output scb_pop.json`
      completes; inspect the output: cross-tabulate `employment_status` by age band and confirm
      the expected age gradient.
- [ ] Open the explorer and confirm the employment node no longer renders as an unused `option`.

### Edge Cases
- [ ] `75-85` individuals (no `75+` band fetched) → served by sampler fallback stage 3.
- [ ] A band the table does not actually expose → fetch fails loudly (fail-fast), not silently.
- [ ] Cross-sex fallback still works when a `(age_group, sex)` key is absent for one sex.

---

## Documentation Plan

- [ ] Update `docs/architecture/sweden-generation-explorer/js/data.js` (Phase 3.1).
- [ ] Update any architecture prose that states employment is sex×education-only.
- [ ] No new CLI commands; README/CLAUDE.md need no changes (behaviour, not interface, changes).

---

## Rollback Plan

The change is additive and Sweden-only.

1. Revert the feature commits (single feature branch) — the shared
   `employment_by_sex_education` field was never mutated, so Norway/Italy need no attention.
2. No data migrations, no persisted state: distributions are re-fetched live each generation
   run, so reverting the code fully restores prior behaviour.
3. If only the age slicing misbehaves, the safest partial rollback is to revert Phase 1.4/1.5
   (drop the `Alder` selection and re-point `load_all` at the sex×education field); Phases 2–3
   then no-op against an empty new field via the existing fallback.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `NAKUBefUtbNivAr` does not expose the requested `Alder` codes | Med | Med | Task 1.2 verifies codes before the run; fail-fast surfaces a wrong code immediately rather than silently |
| A requested band straddles a pipeline cut (e.g. `15-24`) and silently drops population | Med | Med | Use bands aligned to `VALID_AGE_GROUPS`; route the youngest via `age_group_map={"15-24":"18-24"}`; parser drops only out-of-range, never straddles unmapped |
| Finer age slicing yields more fully-suppressed small cells | Med | Low | Parser skips fully-suppressed subgroups; sampler's 3-stage fallback fills gaps; whole-distribution emptiness still raises |
| Accidental change to shared `employment_by_sex_education` shape | Low | High | Explicitly additive; new defaulted field; Norway/Italy tests in the suite guard against regression |
| `75-85` employment unavailable (table caps at 74) | High | Low | Sampler fallback borrows `65-74` — the same approximation `employment_type` already makes |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — plumbing (data/fetch/parse) | ~half day | None |
| Phase 2 — sampler | ~1–2 hrs | Phase 1 |
| Phase 3 — explorer/docs | ~1 hr | Phase 2 |

---

## References

- Approved planning scratch: `~/.claude/plans/plan-a-code-change-mighty-alpaca.md`
- Related plan: `docs/development/plans/active/native-highfidelity-mapping-sweden.md`
- Explorer: `docs/architecture/sweden-generation-explorer/js/data.js` (employment node `:35-43`)
- Core invariants: project `CLAUDE.md` (no synthetic distributions, config-as-source, fail-fast)

---
