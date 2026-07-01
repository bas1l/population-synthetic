# Plan: Unify the GUI Analysis section on Models × Strategies × Countries axis selection

**Date:** 2026-07-01
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/homogenize-real-synthetic-naming`
**Branch:** `feature/unify-gui-analysis-axis-selection`

---

## Overview

Make **every** feature in the GUI's **Analysis** section select synthetic data (and its
country/real counterpart) through the same Models × Strategies × Countries checkbox selector
already used by *Map Populations*. In doing so, remove *Pipeline vs Reference* and *All Pipelines
vs Reference* and merge them into one **Compare Synthetic to Real** action that runs a single
aggregate comparison over the axis-selected pipelines; and convert *Compare Two Populations* and
both *LLM Metrics* actions to the same axis-selection pattern.

## Problem Statement

The Analysis group in `config/gui/launcher.yaml` mixes two incompatible selection idioms:

- **Axis-driven** (`requires_manifest: true`) — shows the shared `ExperimentSelector` (Models ×
  Strategies × Countries checkboxes) and runs the script **once per combo** via `CombinationRunner`
  with `--model-id/--strategy-id/--country-id`. Used by *Map Populations* and *Pipeline vs Reference*.
- **Ad-hoc params** (`requires_manifest: false`) — no axis selector; a flat form of free-text
  filters / file browsers. Used by *All Pipelines vs Reference*, *Compare Two Populations*, and both
  *LLM Metrics* actions.

This is inconsistent and error-prone. Concretely, *Compare Two Populations* passes `--pop_a/--pop_b`
as flags to a script that declares them **positional** and additionally **requires** a `--country`
the YAML never supplies — so the action cannot succeed from the GUI today. Free-text
model/strategy filters for *All Pipelines vs Reference* invite typos that a checkbox list prevents.
Unifying on the axis selector removes these failure modes and gives one mental model across Analysis.

## Goals

### In Scope
1. Remove the `compare_scb` (*Pipeline vs Reference*) and `compare_all` (*All Pipelines vs
   Reference*) actions and merge them into one **Compare Synthetic to Real** action that runs a
   single aggregate comparison (per-pipeline reports + the combined radar-grid/summary) over the
   axis-checked pipelines.
2. Convert **Compare Two Populations** to select **two synthetic pipelines** (two axis combos) and
   compare them against each other.
3. Convert **LLM Metrics (per-run)** to analyse each selected run (one per combo) and **LLM Metrics
   (cross-run)** to aggregate across the selected runs — both via the axis selector.
4. Introduce an explicit, config-declared run-mode (`none | per_combo | batch`) so the selector
   visibility and invocation style are driven by config, not an implicit boolean.

### Out of Scope
- The parallel `gui_v2` rebuild (see `pending/gui-v2-flow-runner.md`). This plan refactors the
  **existing** `gui/` launcher in place; it does not build or block the v2 GUI.
- Folding the mapping stage into Compare. **Map Populations stays a separate manual step**; Compare
  fails loudly when `mapped/_index.json` is missing (locked with the user).
- Any change to the **Generate Population** group actions.
- Deleting `scripts/analyze/compare_pipeline_to_scb.py` — it is delisted from the GUI but kept as a
  CLI tool.

## Success Criteria

- [ ] The Analysis section shows the axis selector for **all** its actions (Map, Compare Synthetic
      to Real, Compare Two Populations, both LLM Metrics).
- [ ] `compare_scb` and `compare_all` no longer appear in the GUI; **Compare Synthetic to Real**
      produces per-slug reports, the country radar grid, and `comparison_summary.json` over exactly
      the checked combos.
- [ ] **Compare Two Populations** requires exactly two checked combos and emits an A-vs-B report
      over their mapped populations; a friendly message is shown for ≠2 selections.
- [ ] **LLM Metrics (per-run)** writes one `run_analytics.json` per selected slug; **cross-run**
      aggregates across the selected slugs.
- [ ] Each new/changed action runs end-to-end from the GUI, and the new CLI flags work standalone.
- [ ] `ruff check src/` and `pytest` pass.

---

## Technical Design

### Approach

The GUI is fully config-driven (`config/gui/launcher.yaml` → generic widgets); there are **no
per-feature widget classes**. The axis selector (`ExperimentSelector` / `CheckableAxisList`) is
already reusable. The only genuinely new machinery is a **batch run-mode**: today `requires_manifest:
true` runs a script once per combo, but the aggregate features (compare-all, cross-run) need the
*whole selection* in one process. We make the two existing modes explicit and add a third:

| mode | selector shown | invocation |
|------|----------------|------------|
| `none` | no | single subprocess, params only (= old `requires_manifest: false`) |
| `per_combo` | yes | `CombinationRunner`, once per combo with `--model-id/--strategy-id/--country-id` (= old `requires_manifest: true`) |
| `batch` (**new**) | yes | **single** subprocess; every checked combo emitted as one repeated `--slug {country}_{strategy}_{model}` flag, plus the action's params |

Batch mode uses the canonical slug (`{country}_{strategy}_{model}` — what `compose_manifest`
produces and `decompose_slug` parses) as the uniform interface. Each batch backend filters its
existing data (`mapped/_index.json`, the mapped file, or the `run_analytics` records) down to the
selected slugs — no new comparison/analysis logic is written.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Add a `batch` run-mode emitting per-combo `--slug` flags | Reuses `ExperimentSelector` verbatim; slug is the existing join key; backends filter existing data | Adds one code path to `_run`; four scripts gain a slug entry point | **Chosen** |
| Keep once-per-combo for everything (drop aggregate views) | Least GUI code | Loses the combined radar-grid/summary and cross-run aggregation the user wants | Rejected |
| Pass per-axis **sets** (`--model/--strategy/--country`) in batch | `compare_all_pipelines.py` already accepts these | Ambiguous for exact-pair selection (Compare Two Populations); cartesian-of-sets ≠ explicit combos | Rejected (slug is more precise) |
| Build the new axis UX in `gui_v2` instead | Cleaner long-term architecture | Larger effort; user asked to fix the **current** Analysis section now | Deferred to `gui-v2-flow-runner.md` |

### Architecture Changes

New/changed integration points (no new packages, no new widgets):

- `ActionEntry` gains `axis_mode` (normalised) and optional `min_combos`/`max_combos`.
- `LauncherWindow._run` gains a `batch` branch that reuses the existing single-process plumbing
  (`ProcessOutputReader` + `_poll_timer`).
- A shared `axis_slug(model, strategy, country)` helper centralises the slug format (currently
  inlined in `compose_manifest`).
- Four analyze scripts gain a slug/axis entry point that filters their existing inputs.

---

## Implementation Plan

### Phase 1: GUI run-mode plumbing
**Goal:** Make run-mode explicit and add the `batch` invocation path.

**Started:** 2026-07-01
**Completed:** 2026-07-01

- [x] Add `axis_mode: str` to `ActionEntry`, normalised on parse to `none|per_combo|batch`; when
      absent, derive from `requires_manifest` (`true→per_combo`, `false→none`) so Generate actions
      are untouched. Add optional `min_combos`/`max_combos` and parse them.
- [x] Show `ExperimentSelector` when `axis_mode in {"per_combo","batch"}` (replace the
      `requires_manifest` check).
- [x] Add the `batch` branch to `_run`: read `selection.combinations()`, validate
      `min_combos/max_combos` (friendly `QMessageBox`), build
      `[python, script] + ["--slug", axis_slug(m,s,c)]*N + overrides`, launch one subprocess reusing
      the existing reader/poll plumbing.
- [x] Add `axis_slug(model_id, strategy_id, country_id)` to `manifest_loader.py` and reuse it inside
      `compose_manifest`; import it in `main_window.py`.

**Files Modified:**
- `src/population_synthetic/gui/launcher_config.py` — `ActionEntry` fields + parsing.
- `src/population_synthetic/gui/widgets/configuration_panel.py` — selector visibility.
- `src/population_synthetic/gui/main_window.py` — `batch` branch in `_run`.
- `src/population_synthetic/generators/synthetic/manifest_loader.py` — `axis_slug` helper.

**Dependencies:** None

### Phase 2: Backend slug/axis entry points
**Goal:** Let the four analyze scripts accept the axis selection.

**Started:** 2026-07-01
**Completed:** 2026-07-01

- [x] `compare_all_pipelines.py` — add a repeatable `--slug` filter (keep only `_index.json` entries
      whose slug is selected, alongside existing `--model/--strategy/--country` CLI filters).
      Aggregate output unchanged.
- [x] `compare_populations.py` — add a `--slug` mode (exactly two): load
      `{output_base}/03_Analysis/mapped/{slug}.json` for each, derive `--country` from the slugs via
      `decompose_slug` and validate both share one country, run the existing `StatisticalEvaluator`
      A-vs-B path; fail loudly if a mapped file is missing. Keep the positional-file CLI mode.
- [x] `analyze_run.py` — accept `--model-id/--strategy-id/--country-id` (+ `--force`): resolve
      `axis_slug(...)` → `{output_base}/01_Raw/{slug}` and analyse that run. Keep `run_dir`/`--all`.
- [x] `compare_runs.py` — add a repeatable `--slug` filter restricting the loaded `run_analytics`
      records; derive country from the slugs. Keep `--metrics`/`--root`/`--country`.

**Files Modified:**
- `scripts/analyze/compare_all_pipelines.py`
- `scripts/analyze/compare_populations.py`
- `scripts/analyze/analyze_run.py`
- `scripts/analyze/compare_runs.py`

**Dependencies:** Phase 1 (for `axis_slug`)

### Phase 3: Rewire `config/gui/launcher.yaml` (analysis group)
**Goal:** Point the GUI at the new actions/modes.

**Started:** 2026-07-01
**Completed:** 2026-07-01

- [x] Keep `map_populations` → `axis_mode: per_combo`.
- [x] Remove `compare_scb` and `compare_all`.
- [x] Add `compare_synth_real` → `compare_all_pipelines.py`, `axis_mode: batch`; params `no-charts`,
      `radar-tv-only`; label "Compare Synthetic to Real".
- [x] Replace `compare_pops` → `compare_populations.py`, `axis_mode: batch`, `min_combos: 2`,
      `max_combos: 2`; params `output` (optional), `no-charts`; drop `pop_a`/`pop_b`.
- [x] `llm_metrics_per_run` → `axis_mode: per_combo`; drop `all`; keep `charts`, `verbose`.
- [x] `llm_metrics_cross_run` → `axis_mode: batch`; keep `metrics`; drop `root`/`country`.

**Files Modified:**
- `config/gui/launcher.yaml` — analysis group.

**Dependencies:** Phases 1 & 2

---

## Testing Plan

### Unit Tests
- [ ] `axis_slug(model, strategy, country)` returns `{country}_{strategy}_{model}` and matches the
      slug `compose_manifest` derives for the same axes.
- [ ] `parse_launcher_config` normalises `axis_mode` (explicit values pass through; absent derives
      from `requires_manifest`) and parses `min_combos`/`max_combos`.
- [ ] `compare_populations.py` slug mode raises loudly on a missing mapped file and on two slugs of
      different countries.

### Integration Tests
- [ ] `compare_all_pipelines.py --slug A --slug B` restricts the aggregate to exactly A and B.
- [ ] `compare_runs.py --slug ...` restricts the cross-run records to the selected slugs.

### Manual Verification
- [ ] `python -m population_synthetic.gui.main`: Map Populations (per_combo) writes
      `mapped/{slug}.json`, `real_{country}.json`, `_index.json`.
- [ ] Compare Synthetic to Real (batch): several combos → one subprocess → per-slug reports under
      `03_Analysis/comparison/{slug}/`, the country radar grid, `comparison_summary.json`; with no
      prior mapping it fails loudly pointing at Map Populations.
- [ ] Compare Two Populations (batch, exactly 2): ≠2 shows the count message; exactly 2 → A-vs-B
      report over the two mapped pipelines.
- [ ] LLM Metrics per-run → one `run_analytics.json` per selected slug; cross-run → aggregated
      stats/charts over the selection.

### Edge Cases
- [ ] Zero combos checked in a batch action → clear "no selection" message, no subprocess.
- [ ] A checked combo with no mapped/raw output → skipped with a logged reason, run continues.
- [ ] `--force` appended by `CombinationRunner` is accepted by `analyze_run.py` (per_combo).

---

## Documentation Plan

- [ ] Update `docs/architecture/commands.md` (and any GUI notes) for the renamed/merged actions.
- [ ] Update `docs/scb_population_and_comparison.md` two-stage flow wording if it names the old
      action labels.
- [ ] Note the new `axis_mode`/`--slug` contract where the launcher config schema is documented.
- [ ] CLAUDE.md: only if the Analysis command examples change materially.

---

## Rollback Plan

Pure additive/config change on a feature branch; no data migrations.

1. **Before merge:** revert the branch; the old `gui/` + `launcher.yaml` behaviour returns
   unchanged. `compare_pipeline_to_scb.py` was never deleted.
2. **Data considerations:** none — no on-disk formats change; `mapped/` and `comparison/` layouts
   are untouched.
3. **Rollback procedure:** `git revert` the merge (or delete the unmerged branch); no state reset
   needed.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Overlap/duplication with the planned `gui_v2` rebuild | Med | Med | This plan is in-place v1 work the user asked for now; keep changes minimal and config-driven so v2 can supersede it cleanly. Confirm sequencing with user. |
| `batch` slug flags drift from `compose_manifest`'s slug format | Low | High | Centralise in one `axis_slug` helper reused by both; unit-test equality against `compose_manifest`. |
| A backend script's existing CLI contract breaks | Low | Med | New flags are additive; positional/`--all`/filter modes retained; covered by integration spot-checks. |
| `CombinationRunner` unconditionally appends `--force` for per_combo actions | Med | Low | Ensure `analyze_run.py` accepts `--force` (it is the only new per_combo script). |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 (GUI run-mode) | ~half day | None |
| Phase 2 (backend flags) | ~half day | Phase 1 |
| Phase 3 (launcher.yaml) | ~1 hour | Phases 1 & 2 |

---

## References

- Scratch plan: `C:\Users\basil\.claude\plans\analyse-the-gui-analysis-delightful-trinket.md`
- Related (parallel, not superseded): `docs/development/plans/pending/gui-v2-flow-runner.md`
- Two-stage map→compare design: `docs/scb_population_and_comparison.md`,
  `docs/architecture/comparison-mapping.md`

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- config/gui/launcher.yaml
- docs/development/plans/active/unify-gui-analysis-axis-selection.md
- scripts/analyze/analyze_run.py
- scripts/analyze/compare_all_pipelines.py
- scripts/analyze/compare_populations.py
- scripts/analyze/compare_runs.py
- src/population_synthetic/generators/synthetic/manifest_loader.py
- src/population_synthetic/gui/launcher_config.py
- src/population_synthetic/gui/main_window.py
- src/population_synthetic/gui/widgets/configuration_panel.py
