# Plan: Enforce the full-N rule in `population_cap`

**Date:** 2026-08-18
**Author:** Basil
**Status:** In Progress
**Base Branch:** `dev`
**Branch:** `feature/enforce-full-n-cap-exclusion`

---

## Overview

A model x method combination that cannot supply `N` clean personas is currently capped to
whatever it has and flows into every downstream analysis as an ordinary, unmarked
competitor. This plan makes the validation gate's last stage refuse such a combination
outright: it writes no capped outputs, so every mapped-file consumer skips it through the
skip predicate they already honour.

## Problem Statement

`cap_combo` warns on a shortfall and proceeds (`analysis/population_cap/cap.py:189-200`),
and `select_indices` returns every index when `n >= total` by design
(`analysis/utils/sampling.py:57`). The shortfall is recorded only in the stage-level
`population_cap/_index.json`; the `_mapped/_index.json` that every consumer actually
enumerates deliberately mirrors the mapping-stage schema and drops `requested_n`
(`scripts/analyze/cap_populations.py:127-141`). Its `skipped` flag is
`synthetic_file is None`, i.e. true only at **zero** mapped personas.

The consequence is that one clean persona out of a requested hundred is analysed as a full
competitor by all seven mapped-file consumers -- `score_fidelity_all.py:198`,
`score_multivariate_fidelity.py:146` (C2ST/MMD, the most sample-size-sensitive metric in
the repository), `scan_consistency.py:125`, `analyze_persona_realism.py:274`,
`model_ranking/loader.py:182`, `realism_ranking/loader.py:559`,
`method_significance/marginal_charts.py:129` -- and, through the fidelity reports, enters
Page's L, Friedman, Nemenyi and the mixed model as an equal block in `method_significance`.

Exactly one consumer knows about thinness: the model x method heatmap, via
`analysis/utils/cap_index.py` and `model_ranking/charts.py::_model_method_rows`. It marks
and demotes; it does not exclude, it is skipped entirely under `--no-charts`
(`rank_models.py:220`), and the performance JSON/CSV that feed the manuscript tables carry
no thin flag at all.

## Goals

### In Scope

1. Make `clean_available >= n` a precondition for a combination having capped outputs at
   all: below it, no persona mirror and no capped mapped file are written, and any
   existing ones are removed.
2. Keep the exclusion **recorded**, not silent: the full shortfall stays in
   `population_cap/_index.json`, and the reason travels on the `_mapped/_index.json` entry
   so consumers can print why a combination is absent.
3. Re-evaluate the rule on every invocation, so an output base already populated by the
   previous behaviour is cleaned without requiring `--force`.
4. Update the two prose sources that state the old policy, and the seven consumer skip
   messages that would otherwise report a wrong reason.

### Out of Scope

- Any change to what makes a persona valid (`validate_raw` / `validate_mapped` are
  untouched).
- A tolerance band, a config knob, or an `--allow-short` override. The threshold is strict
  and has no escape hatch; a knob re-opens the hole this plan closes.
- Removing the now-unreachable Tier-1/Tier-2 thin-cell machinery in
  `model_ranking/charts.py` and `analysis/utils/cap_index.py`. It becomes defence in depth
  and is deliberately left in place (see Risks).
- Back-filling generation for combinations that fall short. Deciding whether to generate
  more personas for an excluded combination is an operator decision, not this gate's.

## Success Criteria

- [ ] For a combination with `clean_available < n`, `population_cap` writes no
      `population_cap/{slug}/` directory and no `population_cap/_mapped/{slug}.json`, and
      deletes either if present from an earlier run.
- [ ] Its `_mapped/_index.json` entry carries `synthetic_file: null`, `skipped: true`, and
      a non-empty `skip_reason` naming the counts.
- [ ] Its `population_cap/_index.json` record is present and carries `excluded: true`,
      `clean_available`, and `requested_n`.
- [ ] All seven mapped-file consumers skip the combination with no code change to their
      selection logic, and `model_ranking`'s `--strict` does not fail on it.
- [ ] A no-force re-run on an output base capped under the old behaviour withdraws every
      combination that is now short.
- [ ] The per-combo CLI exits 0 on an exclusion, so the GUI node does not go red and
      dependents still unlock.
- [ ] `pytest` passes, including the inverted under-generation tests.

## Definitions

- **clean persona**: a `persona_*` directory whose id appears with a truthy `passed` in
  **both** `validate_raw/{slug}.csv` and `validate_mapped/{slug}.csv`, **and** which exists
  as a directory under `01_Raw/{slug}/`. A passing id with no directory on disk is not
  countable -- there is nothing to copy.
- **full-N**: `clean_available >= requested_n` for that combination's own slug. The
  boundary is inclusive; `clean_available == n` is full-N. This is the same rule
  `analysis/utils/cap_index.py` already states, now enforced rather than merely reported.
- **excluded**: the verdict on a combination that is not full-N. It is a verdict, not an
  error: it is logged loudly, recorded in both indexes, and exits 0.
- **withdrawn**: the physical act of ensuring an excluded combination has no capped
  outputs -- removing `population_cap/{slug}/` and `population_cap/_mapped/{slug}.json` if
  present. Idempotent: absent artifacts are a no-op.

---

## Technical Design

### Approach

Enforcement rides on a contract that already exists. Every mapped-file consumer gates on
the identical predicate `entry.get("skipped") is True or entry.get("synthetic_file") is
None`, and in `model_ranking/loader.py` that check short-circuits *before* the `--strict`
missing-report raise (line 210 vs 227). Writing an excluded combination into
`_mapped/_index.json` with `synthetic_file: null` therefore removes it from all seven
consumers with no edit to any of their selection paths.

The rule is evaluated **inside** `cap_combo`, before the mirror/force check, so a library
caller cannot bypass it and so an existing mirror cannot shield a stale short population.
Per `02-architecture-principles-and-patterns.md` section 5, "skip if already done" must key
on a *complete*-output marker; `dest_dir.exists()` is a partial one -- it means a cap ran,
not that a valid cap ran. Only the expensive re-copy stays gated on `--force`.

The shortfall is an *explicit absent*, never a silent one (section 8 of the same guide, and
the checklist's "no silently dropped data"): the stage index keeps the full record and the
mapped index carries `skip_reason`, which the consumers print instead of their current
hardcoded "skipped during mapping" string.

`CleanSelection` is the typed intermediate (checklist: "structured intermediates typed or
validated at the boundary") and the single reader of the rule's input, so `cap_combo` and
the CLI's re-run path cannot disagree about how many clean personas a combination has.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Exclude at the cap: write no capped outputs for a short combination | One edit site; all seven consumers enforced through a predicate they already honour; `--strict` unaffected; N becomes a real invariant | `generation_metadata` loses the combination's telemetry; a grid hole must be read from the index rather than from the consumer's own output | **Chosen** |
| Keep the data, filter at each consumer (`requested_n` on the mapped entry + per-consumer gate) | Separates "excluded from statistical claims" from "excluded from cost telemetry"; shortfall auditable at every stage | Eight edit sites including `generation_metadata`, which reads no index today; every future consumer must remember the gate; drift risk is exactly what the config invariant exists to prevent | Rejected |
| Exclude the mapped file but keep the persona mirror | Preserves cost/token/retry telemetry for thin combinations, avoiding the selection bias noted under Risks | Two rules instead of one; a combination half-present in the capped stage is a state nothing else in the pipeline has | Rejected (raised and declined) |
| Fail the batch on a shortfall | Impossible to overlook | A single short combination blocks an otherwise valid sweep; the GUI node goes red and dependents never unlock | Rejected |
| Tolerance band or `--allow-short` override | Operator flexibility for exploratory runs | Re-opens the hole; a run that used the override is indistinguishable downstream from one that did not | Rejected |

### Architecture & Module Contracts

| Module / layer | Responsibility | Inputs -> Outputs | Must NOT know about |
|----------------|----------------|-------------------|---------------------|
| `cap.clean_selection` | Read the two validity CSVs and intersect them to this combo's clean persona dirs | `(raw_slug_dir, validate_raw_csv, validate_mapped_csv)` -> `CleanSelection` | the cap `n`, seeds, destinations, what "downstream" is |
| `cap.CleanSelection` | Typed carrier of the two gate counts and the surviving dirs | -- | file formats, mapping, indexes |
| `cap.withdraw_combo` | Ensure an excluded combo has no capped outputs; return its excluded summary | `(slug, country, clean, n, seed, dest_dir, mapped_dest_dir)` -> `CapSummary` | which consumers read the index, chart/report semantics |
| `cap.cap_combo` | Apply the full-N rule, then seeded-select and materialize the two capped outputs | as today -> `CapSummary` (now with `excluded`) | the CLI, the GUI, the registry |
| `cap_populations.main` | Resolve paths, decide whether the re-copy may be skipped, upsert both indexes, report | CLI args -> files + exit code | how selection works, how statistics are computed |
| `cap_populations._mapped_index_entry` | Project a `CapSummary` onto the mapped-index contract | `CapSummary` -> dict | everything else |

Signatures introduced in `analysis/population_cap/cap.py`:

```python
class CleanSelection(NamedTuple):
    raw_passed: int
    mapped_passed: int
    dirs: list[Path]

    @property
    def clean_available(self) -> int: ...


def clean_selection(
    raw_slug_dir: Path, validate_raw_csv: Path, validate_mapped_csv: Path
) -> CleanSelection: ...


def withdraw_combo(
    *, slug: str, country: str, clean: CleanSelection, n: int, seed: int,
    dest_dir: Path, mapped_dest_dir: Path,
) -> CapSummary: ...
```

`CapSummary` gains `excluded: bool` and `exclusion_reason: str | None`.
The `_mapped/_index.json` entry gains `skip_reason: str | None`; consumers that find it
absent or null keep printing their existing message, so the contract is additive and old
index files stay readable.

Control flow inside `cap_combo` after the change:

```
validate n  ->  raw_slug_dir exists?
            ->  clean_selection(...)                          # the rule's input, read once
            ->  clean_available < n ?  -> withdraw_combo(...)  -> return EXCLUDED summary
            ->  dest_dir exists? (raise unless force; rmtree)
            ->  seeded select  ->  mirror copy  ->  capped mapped file  ->  real reference
            ->  return summary (excluded=False)
```

---

## Implementation Plan

### Phase 1: The rule, in the library
**Goal:** `cap_combo` alone enforces full-N; no caller can bypass it.

- [x] 1.1 — Add `CleanSelection` (NamedTuple, with `clean_available` property) and
      `clean_selection(...)` to `cap.py`, built on the existing `read_passed_ids` and
      `_clean_persona_dirs`.
- [x] 1.2 — Add `withdraw_combo(...)`: log the exclusion at WARNING with both gate counts,
      `rmtree_resilient(dest_dir)` if present, `unlink` a stale
      `mapped_dest_dir/{slug}.json` if present, return a `CapSummary` with
      `selected=0`, `selected_ids=[]`, `truncated=False`, `synthetic_file=None`,
      `real_file=None`, `mapped_n=0`, `excluded=True`, `exclusion_reason=<counts>`.
- [x] 1.3 — Add `excluded` and `exclusion_reason` to `CapSummary`; set
      `excluded=False, exclusion_reason=None` on the success return.
- [x] 1.4 — Reorder `cap_combo`: `clean_selection` and the exclusion branch move **above**
      the `dest_dir.exists()` / `force` check. Delete the two now-dead warning blocks
      (`clean_available == 0` and `clean_available < n`) -- both route through
      `withdraw_combo`.
- [x] 1.5 — Rewrite the module docstring's closing paragraph to state the exclusion policy
      and its strictness.
- [x] 1.6 — Re-export `CleanSelection`, `clean_selection`, `withdraw_combo` from
      `population_cap/__init__.py`.

**Files Modified:**
- `src/population_synthetic/analysis/population_cap/cap.py` — the rule, the withdrawal, the
  summary fields, the docstring
- `src/population_synthetic/analysis/population_cap/__init__.py` — exports

**Dependencies:** None

### Phase 2: The CLI, and clean re-runs
**Goal:** An already-populated output base is cleaned without `--force`; both indexes tell
the truth; an exclusion is not a failure.

- [ ] 2.1 — `_mapped_index_entry`: add `"skip_reason": summary["exclusion_reason"]`.
- [ ] 2.2 — Replace the blanket no-force early return with a re-evaluation: call
      `clean_selection(...)` and return early **only** when `clean_available >= args.n`.
      Otherwise fall through to `cap_combo`, which returns at its exclusion branch before
      reaching its own mirror check, so `force=False` is safe.
- [ ] 2.3 — Branch the closing log on `summary["excluded"]`: a WARNING naming the counts
      and stating that downstream analyses will skip the slug, else the existing INFO line.
- [ ] 2.4 — Confirm the exclusion path exits 0 and still upserts both index entries.
- [ ] 2.5 — Update the script's module docstring (it currently promises the cap "selects
      `--n` of them" unconditionally).

**Files Modified:**
- `scripts/analyze/cap_populations.py` — index entry, re-run evaluation, logging, docstring

**Dependencies:** Phase 1

### Phase 3: Truthful reporting downstream
**Goal:** No consumer reports a wrong reason, and no document states the old policy.

- [ ] 3.1 — In each of the seven consumers, print `entry.get("skip_reason")` when present
      and fall back to the existing "skipped during mapping (no mapped synthetic file)"
      string when absent: `score_fidelity_all.py:248`,
      `score_multivariate_fidelity.py:191`, `scan_consistency.py:193`,
      `analyze_persona_realism.py:294`, `model_ranking/loader.py:211`,
      `realism_ranking/loader.py` (the `skipped.append` in its discovery walk),
      `method_significance/marginal_charts.py:151`.
- [ ] 3.2 — Rewrite the `population_cap` description in
      `config/analysis/analysis_registry.yaml` (it states every combination is capped and
      that "no task analyzes more than N", which becomes "and none analyzes a combination
      that never reached N").
- [ ] 3.3 — Update the header of `analysis/utils/capped_source.py`, which describes the
      capped outputs as always present for a generated combo.
- [ ] 3.4 — Update the `CLAUDE.md` analysis-registry paragraph describing what
      `population_cap` does.

**Files Modified:**
- `scripts/analyze/score_fidelity_all.py`, `scripts/analyze/score_multivariate_fidelity.py`,
  `scripts/analyze/scan_consistency.py`, `scripts/analyze/analyze_persona_realism.py`
- `src/population_synthetic/analysis/model_ranking/loader.py`,
  `src/population_synthetic/analysis/realism_ranking/loader.py`,
  `src/population_synthetic/analysis/method_significance/marginal_charts.py`
- `config/analysis/analysis_registry.yaml`,
  `src/population_synthetic/analysis/utils/capped_source.py`, `CLAUDE.md`

**Dependencies:** Phase 2

### Phase 4: Tests
**Goal:** The inverted contract is pinned, including the re-run path that protects existing
output bases.

- [ ] 4.1 — Invert `test_cap_combo_under_generation_copies_all_and_warns`
      (`tests/test_population_cap.py:285`) into
      `test_cap_combo_under_generation_excludes_the_combo`.
- [ ] 4.2 — Update `test_cap_combo_zero_persona_dirs_handled` (line 341): zero clean
      personas is now the same rule, so `dest` must not exist and no capped mapped file is
      written.
- [ ] 4.3 — New: a previously capped combination that no longer reaches N is withdrawn on a
      **no-force** re-run (mirror and mapped file both removed).
- [ ] 4.4 — New: `withdraw_combo` is idempotent -- calling it twice with nothing on disk is
      a no-op and returns the same summary.
- [ ] 4.5 — New: the `_mapped/_index.json` entry for an excluded combination satisfies the
      consumers' skip predicate and carries a non-empty `skip_reason`.
- [ ] 4.6 — New: `clean_available == n` is full-N (the inclusive boundary) and produces
      normal capped outputs.

**Files Modified:**
- `tests/test_population_cap.py`

**Dependencies:** Phase 1-2 (4.5 also Phase 2)

---

## Testing Plan

### Unit Tests
- [ ] `clean_selection` counts only ids passing both CSVs *and* present as directories.
- [ ] `clean_available < n` -> excluded summary, no mirror, no capped mapped file.
- [ ] `clean_available == n` -> full-N, mirror and mapped file written, `truncated is False`.
- [ ] `clean_available > n` -> unchanged behaviour, `truncated is True`, exactly `n` copied.
- [ ] Zero clean personas -> excluded (not an empty capped output).
- [ ] `withdraw_combo` removes a stale mirror and a stale mapped file, and is idempotent.
- [ ] `CapSummary` for an excluded combo carries `excluded`, `clean_available`,
      `requested_n`, `exclusion_reason`.

### Integration Tests
- [ ] Cap a combo short, then run the `model_ranking` loader over the resulting
      `_mapped/_index.json` with `strict=True`: the combo appears in `skipped`, the call
      does not raise, and no record is produced.
- [ ] Cap a combo at full N, then short (no `--force` between runs): the second run leaves
      neither artifact behind and both index entries reflect the exclusion.
- [ ] `analyze_persona_realism`'s combo enumeration omits an excluded slug.

### Manual Verification
- [ ] Run the GUI analysis workflow's `population_cap` node with `force: false` on the
      existing output base; confirm short combos are withdrawn, the node completes green,
      and dependents unlock.
- [ ] Inspect `03_Analysis/population_cap/_index.json`: every excluded combination has a
      record with its counts.
- [ ] Re-run `fidelity` and `model_ranking`; confirm the excluded combinations are absent
      from the reports and named in the skip output with the shortfall reason.

### Edge Cases
- [ ] `n = 1` with exactly one clean persona (full-N at the smallest possible cap).
- [ ] A combination whose `01_Raw` directory exists but whose validity CSVs are missing --
      must still raise `FileNotFoundError` from `read_passed_ids`, not be treated as short.
- [ ] `real_{country}.json` shared with a non-excluded sibling combo: withdrawing one combo
      must not delete the country's copied real reference.
- [ ] An index file written before this change (no `skip_reason` key) still reads.

---

## Documentation Plan

- [ ] Update `CLAUDE.md`'s analysis-registry paragraph for `population_cap`.
- [ ] Update the `population_cap` description in `config/analysis/analysis_registry.yaml`.
- [ ] Update the module docstrings of `analysis/population_cap/cap.py`,
      `analysis/utils/capped_source.py`, and `scripts/analyze/cap_populations.py`.
- [ ] Note in the architecture wiki page that documents the gate that `population_cap` now
      has a pass/fail verdict per combination, not only a cap.

---

## Rollback Plan

1. **Before deployment:** the change is confined to the gate and to log/prose; revert the
   feature branch's commits to restore the previous behaviour.
2. **Data considerations:** the withdrawal *deletes* capped outputs for short
   combinations. Nothing unique is lost -- `01_Raw/{slug}/` and `03_Analysis/mapping/` are
   never mutated, so re-running `population_cap --force` after a revert rematerializes
   exactly what was removed (the draw is seeded and reproducible). Downstream artifacts
   already written for a since-excluded combination are *not* cleaned by this change; drop
   the relevant `03_Analysis/{process}/` outputs and re-run if a mixed state appears.
3. **Rollback procedure:** revert the branch merge; re-run the analysis workflow from
   `population_cap` with force enabled.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `generation_metadata` loses cost/token/retry data for excluded combinations; since a combination is often short *because* the model failed often, the cost and reliability tables become optimistically biased | High | Med | Accepted deliberately (the alternative was raised and declined). The shortfall counts remain in `population_cap/_index.json`, so attrition can be reported separately -- the pending model/method cost-and-attrition figures plan can read it |
| An `--n` higher than any combination achieved silently empties the whole grid | Low | High | Per-combo WARNING on every exclusion, a record in the stage index, and the GUI's existing `min_combos: 2` guard on `model_ranking`; the operator sees N warnings, not silence |
| Withdrawal deletes a mirror an operator still wanted | Low | Med | `01_Raw` is untouched and the draw is seeded, so `--force` rematerializes it identically |
| Existing output bases keep stale short data because the gate is never re-run | Med | High | Phase 2.2 makes a plain no-force run withdraw them; documented as a required one-time re-run of the `population_cap` node |
| The thin-cell machinery in `model_ranking/charts.py` becomes unreachable and rots | Med | Low | Left in place as defence in depth and noted here; removal is a separate decision once the new gate has run on real data |
| A consumer added later forgets the skip predicate | Low | High | The predicate is the pre-existing convention in all seven consumers; the absent `{slug}.json` also makes a forgetful consumer fail loudly on open rather than silently include |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — the rule | ~90 lines changed in 2 files | None |
| Phase 2 — CLI & re-runs | ~30 lines in 1 file | Phase 1 |
| Phase 3 — reporting & prose | ~10 lines across 7 files + 3 docs | Phase 2 |
| Phase 4 — tests | ~120 lines in 1 file | Phase 1-2 |

---

## References

- Related plan: `docs/development/plans/pending/pipeline-model-method-cost-and-attrition-figures.md`
- Prior work: the validation-gate reorder that introduced `validate_raw` /
  `validate_mapped` / `population_cap`
- `~/.claude/knowledge/data-pipeline-engineering/02-architecture-principles-and-patterns.md`
  sections 3, 5, 8 and the review checklist

---
