# Plan: Uniform analysis output-folder & task naming

**Date:** 2026-07-13
**Author:** Basil
**Status:** Draft
**Base Branch:** `feature/force-processing-analysis-tasks`
**Branch:** `feature/uniform-analysis-output-naming`

---

## Overview

Rename the `03_Analysis/` output folders, GUI task labels, task ids, and output
filenames so the naming is uniform and self-describing across the analysis pipeline.
This is a **naming-only** change (folders + labels + task ids + output filenames);
no analysis logic, statistics, or Python package names change.

## Problem Statement

The analysis pipeline's naming is inconsistent across three layers — GUI label, task
id, script/subpackage name, and output-folder name — for the same process. Concretely:

- The GUI task **"Model Performance"** writes to `model_ranking/` and emits
  `{country}_performance.*` files — three different words ("performance" / "ranking")
  for one concept.
- The two LLM-call analytics tasks write to a flat `run_analytics/{slug}/` and
  `run_analytics/_comparison/` with no shared parent grouping them.
- The **"Compare Two Populations"** task (`score_fidelity.py`) writes its default
  output to `data/comparison_report.json` — not even under `03_Analysis/` — so its
  output is invisible to anyone browsing the analysis tree.
- The **"Compare Synthetic to Real"** task writes to `fidelity/`, while its multivariate
  sibling writes to `multivariate_fidelity/`; the two related fidelity processes do not
  read as a pair, and the GUI label shares no vocabulary with the folder.

There is **no shared constants module** for `03_Analysis` subfolder names — every folder
name is a repeated string literal — so the inconsistency has accreted per-script.

## Goals

### In Scope
1. Rename **"Model Performance"** → **"Model Ranking"** everywhere: GUI label, task id
   (`model_performance` → `model_ranking`), and output filenames
   (`{country}_performance.*` → `{country}_ranking.*`). Output folder is already
   `model_ranking/`.
2. Group the two LLM-call analytics tasks under a common **`llm_metrics/`** folder with
   `per_run/` and `cross_run/` subfolders (today: flat `run_analytics/{slug}/` and
   `run_analytics/_comparison/`). Rename the export file `run_analytics.json` →
   `llm_metrics.json`.
3. Redirect **"Compare Two Populations"** (`score_fidelity.py`) default output to
   `03_Analysis/compare_two_populations/`, and rename its task id
   (`compare_pops` → `compare_two_populations`).
4. Rename the fidelity pair so they sort adjacently and share vocabulary:
   `fidelity/` → **`fidelity_univariate/`**, `multivariate_fidelity/` →
   **`fidelity_multivariate/`**; GUI labels → **"Univariate Fidelity"** /
   **"Multivariate Fidelity"**; task ids → `fidelity_univariate` / `fidelity_multivariate`.
5. Update the one in-repo consumer that reads these paths by name: the
   `sync-manuscript` skill.
6. Update architecture docs that reference the renamed folders.

### Out of Scope
- **Renaming Python packages.** `analysis/fidelity/`, `analysis/multivariate_fidelity/`,
  and `analysis/run_analytics/` keep their module names — only their *output folders*
  change. Renaming the packages would churn imports project-wide for no user-visible gain.
- **A shared `03_Analysis` paths/constants module.** Worth doing eventually, but this plan
  edits the existing literals in place; introducing a constants module is a separate refactor.
- **Migrating existing on-disk outputs.** New runs write to the new folders; old outputs
  stay under old names. A manual/one-time migration note is provided (see Rollback), but no
  auto-move of the external `output_base` data is performed.
- **Renaming the `mapped/` folder or the `03_Analysis` root** — unchanged.

## Success Criteria

- [ ] A fresh analysis run writes: `mapped/`, `fidelity_univariate/`,
      `fidelity_multivariate/`, `model_ranking/` (with `{country}_ranking.*`),
      `compare_two_populations/` (when that task runs), and
      `llm_metrics/per_run/{slug}/` + `llm_metrics/cross_run/`.
- [ ] `model_ranking`'s report discovery finds `fidelity_univariate/{slug}/{slug}.json`
      (no stale `fidelity/` path) — the map → compare → rank chain runs end-to-end.
- [ ] GUI (`gui_v2`) Analysis Workflow shows labels "Univariate Fidelity", "Multivariate
      Fidelity", "Model Ranking", "Compare Two Populations"; the DAG `depends_on` edges
      resolve against the new task ids.
- [ ] `pytest` passes (any tests asserting on old folder/file names are updated).
- [ ] `sync-manuscript` skill references resolve to the new folder/file names.
- [ ] No remaining references to the old output-folder/filename strings in code or docs
      (grep clean for `run_analytics.json`, `_performance.json`, `"fidelity"`/
      `"multivariate_fidelity"` used as *output paths*, `"_comparison"`).

---

## Technical Design

### Approach

Because there is no shared constants module, each rename is applied at its literal site.
The changes are grouped by the four rename items; within each, the write-side literal and
every consumer/label/doc reference move together in lockstep (critically, `model_ranking`
reads the fidelity folder by hardcoded path, so that consumer must change in the same commit
as the fidelity-folder rename).

The one genuinely structural change is **item 2**: today the run_analytics layout is flat
(`task_subdir/{slug}` and `task_subdir/_comparison`). The target adds an intermediate
`per_run/` level that does not exist, so this needs a code change in `analyze_run.py`
(insert a `per_run` path component), not merely new config values.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **Item 4:** relabel GUI only, keep `fidelity/` folder | Zero code-path changes; no discovery breakage | Folder/label vocabulary still split; folders don't pair | Rejected |
| **Item 4:** rename folder `fidelity/` → `compare_synth_real/`, keep label | Matches GUI label | Breaks `model_ranking` discovery; internal code still says "fidelity"; no pairing with multivariate | Rejected |
| **Item 4:** rename both folders → `fidelity_univariate/` + `fidelity_multivariate/`, labels "Univariate/Multivariate Fidelity" | Folders sort adjacently, read as a matched pair; labels share vocabulary | Touches 6 write sites + the `model_ranking` consumer + docs | **Chosen** |
| Introduce a shared `03_Analysis` paths constants module first | Removes literal duplication permanently | Larger refactor; expands blast radius of a naming change | Rejected (separate future work) |
| Rename Python packages to match folders | Full top-to-bottom consistency | Project-wide import churn, high risk, no user-facing benefit | Rejected |

### Architecture Constraints (from repo conventions)

- **Config is the single source of truth / fail-fast.** The run_analytics output names are
  config-driven (`config/analysis/analyze_defaults.yaml`); item 2 keeps them there and adds
  a `per_run_subdir` key rather than hardcoding the new segment. Any default-fallback
  literals in code (e.g. `comparison_loader.py`) are updated to match so behaviour is
  identical whether or not the key is present.
- **No shared constant today** — accept the repeated-literal reality for this change; do not
  smuggle in a constants-module refactor.

### Architecture Changes

Output-tree before → after:

```
03_Analysis/
  mapped/                         (unchanged)
  fidelity/               ->  fidelity_univariate/
  multivariate_fidelity/  ->  fidelity_multivariate/
  model_ranking/                  (folder unchanged; files {country}_performance.* -> {country}_ranking.*)
  run_analytics/          ->  llm_metrics/
    {slug}/               ->    per_run/{slug}/        (run_analytics.json -> llm_metrics.json)
    _comparison/          ->    cross_run/
  (score_fidelity.py default: data/comparison_report.json) -> compare_two_populations/
```

---

## Implementation Plan

### Phase 1: Item 1 — Model Performance → Model Ranking
**Goal:** One vocabulary ("rank") for the cross-model ranking task.

- [ ] 1.1 GUI v2 flow: task id `model_performance` → `model_ranking`, label
      "Model Performance (models x methods)" → "Model Ranking".
- [ ] 1.2 Legacy GUI launcher: matching id + label.
- [ ] 1.3 `rank_models.py`: output filenames `{country}_performance.json` /
      `.csv` → `{country}_ranking.json` / `.csv` (idempotency check + write + CSV),
      and the module docstring. `heatmap`/`leaderboard`/`c2st_vs_tv`/`by_attribute`
      names are unaffected.
- [ ] 1.4 `sync-manuscript` skill: `performance/{country}_performance.*` →
      `model_ranking/{country}_ranking.*` (fixes both the stale `performance/` folder
      **and** the filename).

**Files Modified:**
- `config/gui/v2/flows/analysis_workflow.yaml` — task id + label (`model_performance` block)
- `config/gui/launcher.yaml` — `id: model_performance` + label (~:140-141)
- `scripts/analyze/rank_models.py` — filename f-strings (~:247, :271, :273) + docstring (~:13-18)
- `.claude/skills/sync-manuscript/SKILL.md` — folder + filename refs (~:113,116,131,138,201-202,406)

**Dependencies:** None

### Phase 2: Item 4 — Fidelity pair rename (do before model_ranking discovery drifts)
**Goal:** `fidelity_univariate/` + `fidelity_multivariate/` matched pair, labels aligned.

- [ ] 2.1 Rename `fidelity/` output-folder literal → `fidelity_univariate/` at all
      write sites and in `model_ranking`'s discovery reader (must move in lockstep).
- [ ] 2.2 Rename `multivariate_fidelity/` output-folder literal → `fidelity_multivariate/`.
- [ ] 2.3 GUI v2 flow: `compare_synth_real` → id `fidelity_univariate`, label
      "Univariate Fidelity"; `joint_fidelity` → id `fidelity_multivariate`, label
      "Multivariate Fidelity"; update the `model_ranking` task's
      `depends_on: [compare_synth_real]` → `[fidelity_univariate]`.
- [ ] 2.4 Legacy launcher: matching id + label for `compare_synth_real`.
- [ ] 2.5 `sync-manuscript` skill: fidelity + multivariate report/figure folder refs.

**Files Modified:**
- `scripts/analyze/score_fidelity_all.py` — `fidelity` folder literal (~:212) + help/docstring (~:33,129)
- `scripts/analyze/score_fidelity_sweden.py` — folder literal (~:219) + help/docstring (~:29,105,269)
- `scripts/analyze/score_fidelity_italy.py` — folder literal (~:200) + help/docstring (~:29,133,185)
- `src/population_synthetic/generators/synthetic/manifest_loader.py` — `comparison_output_dir` literal (~:220)
- `src/population_synthetic/analysis/model_ranking/loader.py` — **discovery path** `fidelity` (~:165) + docstring (~:9-12)
- `scripts/analyze/score_multivariate_fidelity.py` — `multivariate_fidelity` folder literal (~:159-160) + docstring
- `config/gui/v2/flows/analysis_workflow.yaml` — ids/labels for `compare_synth_real`, `joint_fidelity`; `depends_on` edge
- `config/gui/launcher.yaml` — `compare_synth_real` id/label (~:101-102)
- `.claude/skills/sync-manuscript/SKILL.md` — fidelity/multivariate paths + F11-F15 figure refs

**Dependencies:** None (independent of Phase 1; ordered first-ish because 2.1 spans a consumer)

### Phase 3: Item 2 — run_analytics → llm_metrics/{per_run,cross_run}
**Goal:** Grouped LLM-metrics tree; export renamed `llm_metrics.json`.

- [ ] 3.1 `config/analysis/analyze_defaults.yaml`: `task_subdir` `run_analytics` →
      `llm_metrics`; `comparison_subdir` `_comparison` → `cross_run`; add
      `per_run_subdir: per_run`; `json_filename` `run_analytics.json` → `llm_metrics.json`.
- [ ] 3.2 `analyze_run.py`: insert the `per_run` segment so per-run output lands at
      `.../llm_metrics/per_run/{slug}/` (build `task_dir / per_run_subdir / slug`); use
      renamed json filename.
- [ ] 3.3 `compare_run_analytics.py`: root = `llm_metrics`, comparison dir = `cross_run`;
      update help text defaults.
- [ ] 3.4 `run_analytics/cross_run/comparison_loader.py`: update the default
      `json_filename="run_analytics.json"` fallback → `"llm_metrics.json"`, and the
      cosmetic "run_analytics root not found" / glob error strings.

**Files Modified:**
- `config/analysis/analyze_defaults.yaml` — `analytics:` keys (task_subdir, comparison_subdir, json_filename, +per_run_subdir)
- `scripts/analyze/analyze_run.py` — path build (~:116-123)
- `scripts/analyze/compare_run_analytics.py` — root + comparison dir (~:56-65,150) + help (~:109,113)
- `src/population_synthetic/analysis/run_analytics/cross_run/comparison_loader.py` — default fallback + error strings (~:146,156,167,170)

**Dependencies:** None

### Phase 4: Item 3 — Compare Two Populations → compare_two_populations/
**Goal:** `score_fidelity.py` output lives under `03_Analysis/compare_two_populations/`.

- [ ] 4.1 `score_fidelity.py`: change default `--output` from `data/comparison_report.json`
      to a path under `{output_base}/03_Analysis/compare_two_populations/` (resolve
      `output_base` from config, consistent with the other analyze scripts); redirect the
      default charts dir likewise.
- [ ] 4.2 GUI v2 flow: task id `compare_pops` → `compare_two_populations` (label already
      "Compare Two Populations"); no `depends_on` references it.
- [ ] 4.3 Legacy launcher: matching id/options block.

**Files Modified:**
- `scripts/analyze/score_fidelity.py` — `--output` default (~:148), charts default (~:218), output_base resolution
- `config/gui/v2/flows/analysis_workflow.yaml` — `compare_pops` task id (~:62)
- `config/gui/launcher.yaml` — corresponding id/options (~:128-133)

**Dependencies:** None

### Phase 5: Docs sweep
**Goal:** Architecture docs describe the new tree.

- [ ] 5.1 Update folder-name references in the wiki and top-level docs.

**Files Modified:**
- `CLAUDE.md` (~:72-73)
- `docs/architecture/sub-packages.md` (~:32,44-59,68,74-86)
- `docs/architecture/comparison-mapping.md` (~:32-48)
- `docs/swedish_synthetic_populations_and_analysis_outputs.md` (~:174,239-240)
- `src/population_synthetic/analysis/__init__.py` — module docstring (~:16)

**Dependencies:** Phases 1-4 (rename final names first)

---

## Testing Plan

### Unit / Suite
- [ ] `pytest` full suite green; update any test asserting on old folder/file strings.
- [ ] `ruff check src/` clean.

### Integration (end-to-end chain on a small selection)
- [ ] `map_populations.py` → `score_fidelity_all.py` → `rank_models.py`: confirm ranking
      discovers reports under `fidelity_univariate/` and writes `{country}_ranking.*`.
- [ ] `score_multivariate_fidelity.py` writes under `fidelity_multivariate/`.
- [ ] `analyze_run.py` writes `llm_metrics/per_run/{slug}/llm_metrics.json` + `charts/`;
      `compare_run_analytics.py` writes `llm_metrics/cross_run/`.
- [ ] `score_fidelity.py` (no `--output`) writes under `compare_two_populations/`.

### Manual Verification
- [ ] Launch `gui_v2` Analysis Workflow: labels render as renamed; DAG edges resolve;
      a run produces the new folders.

### Edge Cases
- [ ] `compare_run_analytics.py` run against a tree that still has old `run_analytics/`
      output — confirm the loader looks under the new `llm_metrics/` and fails loudly (not
      silently empty) when none present.
- [ ] `rank_models.py` against a tree with only old `fidelity/` reports — confirm it reports
      "run map/compare first" rather than silently ranking nothing.

---

## Documentation Plan

- [ ] Update `CLAUDE.md` architecture/quick-start folder references.
- [ ] Update `docs/architecture/sub-packages.md` and `comparison-mapping.md`.
- [ ] Update `docs/swedish_synthetic_populations_and_analysis_outputs.md`.
- [ ] Update `.claude/skills/sync-manuscript/SKILL.md` (functional consumer, not just docs).

---

## Rollback Plan

1. **Before merge:** the branch is naming-only; `git revert`/branch-delete restores prior names.
2. **Existing on-disk outputs (external `output_base`):**
   - Old runs remain under `fidelity/`, `multivariate_fidelity/`, `run_analytics/`,
     `{country}_performance.*`. New code will **not** find them.
   - To reuse old results without re-running: one-time manual rename on disk
     (`fidelity` → `fidelity_univariate`, `multivariate_fidelity` → `fidelity_multivariate`,
     `run_analytics` → `llm_metrics` + reshuffle `{slug}` under `per_run/` and `_comparison`
     → `cross_run`, `{country}_performance.*` → `{country}_ranking.*`, `run_analytics.json`
     → `llm_metrics.json`). Otherwise re-run map → compare → rank.
3. **Rollback procedure:** revert the feature merge commit; no schema/data migrations to reverse.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `model_ranking` discovery not updated in lockstep with `fidelity/` rename → ranking silently finds nothing | Med | High | Phase 2 changes write-site + `loader.py:165` in the same commit; integration test asserts discovery |
| `sync-manuscript` skill left pointing at old names → manuscript sync breaks later | Med | Med | Skill update is an explicit task in Phases 1 & 2 |
| Existing external `output_base` results orphaned | High | Low | Documented migration note (Rollback §2); naming-only, no data loss |
| Hidden default-fallback literal (e.g. `comparison_loader.py`) missed → inconsistent behavior when config key absent | Low | Med | Phase 3.4 updates fallbacks to match config; grep-clean success criterion |
| Test fixtures asserting old folder/file names | Med | Low | `pytest` run + fix as part of each phase |
| `03_Analysis` literal duplicated (no constant) → a site missed | Med | Med | Final grep-clean gate across all old strings before merge |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 (Model Ranking) | S | None |
| Phase 2 (Fidelity pair) | M | None |
| Phase 3 (llm_metrics) | M (code, not just config) | None |
| Phase 4 (compare_two_populations) | S | None |
| Phase 5 (docs) | S | Phases 1-4 |

---

## References

- Related plan: `docs/development/plans/active/force-processing-analysis-tasks.md` (base branch)
- Trace of every rename site captured during planning (Explore agent): folder literals are
  repeated per-script; no shared `03_Analysis` constants module exists.
