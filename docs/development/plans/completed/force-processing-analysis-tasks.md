# Plan: Force-processing option for the remaining Analysis workflow tasks

**Date:** 2026-07-13
**Author:** Basil
**Status:** Completed
**Completed:** 2026-07-13 14:31
**Base Branch:** `feature/synthetic-population-size-cap`
**Branch:** `feature/force-processing-analysis-tasks`

---

## Overview

Extend the `--force` / **Force** checkbox mechanism — today wired only to `map_populations`
(and the already-conforming `llm_metrics_per_run`) — to the remaining Analysis workflow tasks:
`compare_synth_real`, `joint_fidelity`, `model_performance`, and `compare_pops`. Each gains
**idempotent skip-if-output-exists** behaviour plus a `--force` flag that overrides it, mirroring
`map_populations.py`.

## Problem Statement

The GUI Force checkbox and `--force` flag are a complete vertical slice, but only `map_populations`
benefits from it. The other four analysis tasks are all `dispatch: slugs`, and **none of their
scripts skip when their outputs already exist** — they unconditionally recompute and overwrite on
every run. Consequently:

1. Re-running the analysis chain to add one new combo re-scores every already-scored combo (wasteful
   for the expensive C2ST / multivariate metrics).
2. There is no Force checkbox on those nodes, so the interaction is inconsistent with `map_populations`.

Adding "force" is genuinely **two-layered** per task: first give the script an idempotent
skip-if-exists path (the thing force overrides), then add `--force` to override it and plumb the flag
through the `slugs` dispatch path (which currently cannot emit `--force` at all).

## Goals

### In Scope
1. `build_slugs_cmd` learns a `force` parameter and emits `--force`; the workflow runner passes
   `task.force` into it.
2. Each of the four scripts gains a `--force` flag and a skip-if-output-exists path, preserving the
   **Full comparison output** invariant (per-country roll-ups/summaries/radar grids stay complete
   even when some per-slug units are skipped).
3. The four task blocks in `analysis_workflow.yaml` declare `supports_force: true` + `force: false`.
4. Headless tests updated/added for the new `build_slugs_cmd` signature and the per-script skip logic.

### Out of Scope
- Changing default behaviour to anything other than "skip existing, `--force` to recompute" (matches
  `map_populations`). Note this is a behaviour change on re-runs: previously these scripts always
  overwrote; after this change an un-forced re-run skips already-present outputs.
- Any change to `map_populations` or `llm_metrics_per_run` (already conform).
- Per-slug force granularity within a single `slugs` invocation (force is batch-wide, exactly as the
  Force checkbox is a single per-task toggle).
- Reworking the aggregation math or output schemas.

## Success Criteria

- [ ] Checking **Force** on `compare_synth_real`, `joint_fidelity`, `model_performance`, or
      `compare_pops` in the GUI appends `--force` to the translated CLI invocation.
- [ ] With Force **off**, re-running a task skips slugs/countries whose output files already exist and
      logs a `SKIP (exists)` line per skipped unit.
- [ ] With Force **off**, the per-country aggregates (`comparison_summary.json`, radar grid,
      multivariate roll-up JSON/CSV, C2ST scatter, model-ranking outputs) still include the skipped
      units (reloaded from disk), so no artifact regresses vs. a full run.
- [ ] With Force **on**, every selected unit is recomputed and overwritten.
- [ ] `ruff check src/` clean; `pytest` green (including updated `test_workflow_commands.py` and new
      per-script skip tests).

---

## Technical Design

### Approach

Follow the `map_populations.py` pattern verbatim: an idempotent per-unit guard
(`if not force and <output>.exists(): reuse/skip`) plus a `--force` argparse flag. The subtlety that
governs the design is the **Full comparison output** hard rule (CLAUDE.md): the two fidelity scripts
build per-country aggregates from the units processed *in memory*. A naive skip would drop
already-done slugs from those aggregates. The fix is exactly what `map_populations` does when it skips
a mapped file — **reload the existing per-slug artifact from disk** so it still feeds the roll-up.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Skip + reload existing per-slug report into the aggregate | Preserves Full-output invariant; matches `map_populations` idempotency exactly | Slightly more code per script (a load-back branch) | **Chosen** |
| Skip and simply omit skipped units from aggregates | Less code | Violates Full comparison output invariant; roll-ups/radar silently regress | Rejected |
| Force at per-slug granularity (per-slug checkboxes) | Fine control | No UI affordance; `slugs` dispatch is one batch invocation; large scope creep | Rejected |
| Timestamp/hash-based staleness detection | Auto-recompute on input change | Over-engineered; no existing precedent; input provenance not tracked | Rejected |

### Architecture Changes

No new modules. Touch points:

- `src/population_synthetic/gui_v2/commands.py` — `build_slugs_cmd(script, combos, options, force)`;
  append `--force` after the script path, before the `--slug` list (mirrors `build_per_combo_cmds`).
- `src/population_synthetic/gui_v2/workflow_runner.py` — `_run_task` passes `task.force` into
  `build_slugs_cmd`.
- The four analysis scripts — add `--force` + skip-if-exists.
- `config/gui/v2/flows/analysis_workflow.yaml` — `supports_force: true` + `force: false` on four tasks.

The GUI node/state/model layers already surface a Force checkbox for any task with
`supports_force: true` (`workflow_graph_items.py`, `workflow_state.py`, `workflow_config_model.py`),
so **no GUI-layer code changes are required** — only the YAML declaration.

**Per-script skip unit and guard:**

| Script | Skip unit | Output checked for existence | Aggregate that must stay complete |
|--------|-----------|------------------------------|-----------------------------------|
| `score_fidelity_all.py` | per slug | `fidelity/{slug}/{slug}.json` | `comparison_summary.json`, per-country radar grid |
| `score_multivariate_fidelity.py` | per slug | `multivariate_fidelity/{slug}/{slug}.json` | per-country roll-up JSON/CSV, C2ST scatter |
| `rank_models.py` | per country | `model_ranking/{country}_performance.json` | none (pure aggregation; skip whole country) |
| `score_fidelity.py` | single file | `--output` path (`.json`) | none (single report) |

---

## Implementation Plan

### Phase 1: Command-builder plumbing
**Goal:** The `slugs` dispatch path can emit `--force`.

- [x] 1.1 — `commands.build_slugs_cmd`: add `force: bool` param; append `--force` after `str(script)`,
      before the slug loop (parallel to `build_per_combo_cmds`). Update the module docstring.
- [x] 1.2 — `workflow_runner._run_task`: pass `task.force` into `build_slugs_cmd`.
- [x] 1.3 — Update `test_workflow_commands.py`: the two `build_slugs_cmd` calls take `force=`; add a
      `test_slugs_with_force_inserts_flag` (flag position asserted) and a no-force omission case.

**Files Modified:**
- `src/population_synthetic/gui_v2/commands.py` — new `force` param + `--force` emission
- `src/population_synthetic/gui_v2/workflow_runner.py` — pass `task.force`
- `tests/test_workflow_commands.py` — signature + new assertions

**Dependencies:** None

### Phase 2: Per-script `--force` + skip-if-exists
**Goal:** Each script skips existing outputs unless forced, keeping aggregates complete.

- [x] 2.1 — `score_fidelity.py`: add `--force`; in slug/positional mode, if `--output` exists and not
      `--force`, print `SKIP (exists)` and exit 0. (Single output; simplest.)
- [x] 2.2 — `rank_models.py`: add `--force`; per country, if `{country}_performance.json` exists and
      not `--force`, skip that country with a `SKIP (exists)` line. Guard against `processed == 0`
      still exiting 0 when all countries were skip-existing (distinguish "skipped existing" from
      "nothing to do").
- [x] 2.3 — `score_fidelity_all.py`: add `--force`; per slug, if `fidelity/{slug}/{slug}.json` exists
      and not `--force`, **load it back** (report + n) so it still contributes to `summary_rows`,
      `radar_grid_data`, and `comparison_summary.json`; log `SKIP (exists)`. Recompute only when
      forced or absent.
- [x] 2.4 — `score_multivariate_fidelity.py`: add `--force`; per slug, if
      `multivariate_fidelity/{slug}/{slug}.json` exists and not `--force`, **load the envelope back**
      so it still feeds `aggregate_multivariate_fidelity` (roll-up + scatter); log `SKIP (exists)`.
      Recompute only when forced or absent.
- [x] 2.5 — Extend each script's module docstring `--force` line and usage examples.

**Files Modified:**
- `scripts/analyze/score_fidelity.py`
- `scripts/analyze/rank_models.py`
- `scripts/analyze/score_fidelity_all.py`
- `scripts/analyze/score_multivariate_fidelity.py`

**Dependencies:** None (independent of Phase 1; can proceed in parallel)

### Phase 3: Workflow YAML + wiring verification
**Goal:** GUI surfaces the Force checkbox on the four tasks and translates it correctly.

- [x] 3.1 — `analysis_workflow.yaml`: add `supports_force: true` + `force: false` (with a
      `# node shows a Force checkbox -> --force` comment matching `map_populations`) to
      `compare_synth_real`, `joint_fidelity`, `model_performance`, `compare_pops`.
- [x] 3.2 — Confirm no other GUI-layer edits needed (checkbox is data-driven off `supports_force`).

**Files Modified:**
- `config/gui/v2/flows/analysis_workflow.yaml`

**Dependencies:** Phase 1 (flag must be emitted for the checkbox to have effect)

---

## Testing Plan

### Unit Tests
- [ ] `build_slugs_cmd(..., force=True)` inserts `--force` immediately after the script path, before
      the first `--slug`.
- [ ] `build_slugs_cmd(..., force=False)` omits `--force`.
- [ ] Round-trip: `analysis_workflow.yaml` still loads via `WorkflowConfigModel`; the four tasks
      report `supports_force is True` and `get_task_force(...) is False`.
- [ ] Per-script skip: with an existing output file and no `--force`, the script logs `SKIP (exists)`
      and does not rewrite it (assert mtime unchanged or a write-spy not called).
- [ ] Per-script force: with `--force`, the output is rewritten.

### Integration Tests
- [ ] `score_fidelity_all.py` on a 2-slug index where slug A already has a report and slug B does not:
      un-forced run skips A (reloaded) + scores B; `comparison_summary.json` contains **both** rows.
- [ ] `score_multivariate_fidelity.py` analogous: per-country roll-up contains both slugs after a
      partial (one-existing) un-forced run.

### Manual Verification
- [ ] Launch `gui_v2`, load the Analysis workflow: the four nodes now render a **Force** checkbox.
- [ ] Run once (populate outputs), run again un-forced → console shows `SKIP (exists)` lines and
      aggregates are unchanged/complete.
- [ ] Check Force on one node, run → that task recomputes; others still skip.

### Edge Cases
- [ ] `rank_models.py`: all countries skip-existing → exits 0 (not the "no reports found" error path).
- [ ] `score_fidelity_all.py`: skipped-reloaded slug whose stored report predates a scheme change —
      document that force is the remedy (no silent staleness detection).
- [ ] Corrupt/partial existing output (unreadable JSON) → fail loudly per fail-fast, not silent skip.

---

## Documentation Plan

- [ ] Update `docs/architecture/commands.md` — note `--force` on the four analyze scripts.
- [ ] Update `docs/development/gui-v2.md` — Force checkbox now applies to the four analysis tasks;
      note the skip-existing default on re-runs.
- [ ] Update each script's module docstring (covered in Phase 2.5).
- [ ] No CLAUDE.md architecture change required (hub doc; no new subpackage).

---

## Rollback Plan

1. **Before merge:** work is on `feature/force-processing-analysis-tasks`; abandon the branch to
   revert entirely.
2. **Data considerations:** no migrations. Outputs are regenerable analysis artifacts. If a skip path
   ever yields a stale aggregate, re-run the task with Force checked to fully recompute.
3. **Rollback procedure:** revert the feature commits (or drop the branch); `analysis_workflow.yaml`
   reverting to no `supports_force` removes the checkboxes; scripts revert to always-overwrite.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Skip path omits reloaded slug from aggregate → incomplete radar/roll-up (Full-output violation) | Med | High | Explicit reload-existing-report branch (Phase 2.3/2.4); integration test asserts both slugs present |
| Behaviour change surprises: un-forced re-run now skips instead of overwriting | Med | Med | Documented in Out-of-Scope + gui-v2 doc; matches `map_populations`; Force restores old behaviour |
| Stale output silently reused after an input/scheme change | Low | Med | Documented; Force is the remedy; fail loudly on unreadable existing output |
| `build_slugs_cmd` signature change breaks other callers | Low | Med | Grep callers (only `workflow_runner` + tests); update together |
| `rank_models` all-skip mistaken for "no reports" error exit | Low | Low | Distinguish skipped-existing from empty in the `processed == 0` guard (Phase 2.2 / edge-case test) |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — plumbing | ~30 min | None |
| Phase 2 — per-script skip/force | ~2 hr | None (parallel to P1) |
| Phase 3 — YAML + verify | ~15 min | Phase 1 |

---

## References

- Related Plans: `docs/development/plans/completed/` (synthetic-population-size-cap introduced
  `--n-synthetic`/`--sample-seed` on the same four scripts — same argparse surface to extend)
- Pattern source: `scripts/analyze/map_populations.py` (`_map_one_target` skip-if-exists + `--force`)
- Plumbing: `src/population_synthetic/gui_v2/commands.py`, `workflow_runner.py`

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- config/gui/v2/flows/analysis_workflow.yaml
- docs/development/plans/active/force-processing-analysis-tasks.md
- scripts/analyze/rank_models.py
- scripts/analyze/score_fidelity.py
- scripts/analyze/score_fidelity_all.py
- scripts/analyze/score_multivariate_fidelity.py
- src/population_synthetic/gui_v2/commands.py
- src/population_synthetic/gui_v2/workflow_runner.py
- tests/test_workflow_commands.py
