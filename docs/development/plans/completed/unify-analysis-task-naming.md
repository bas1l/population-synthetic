# Plan: Unify Analysis Task Naming (GUI ↔ Output Folders via one registry)

**Date:** 2026-07-20
**Author:** Basil
**Status:** Completed
**Completed:** 2026-07-20 17:28
**Base Branch:** `dev`
**Branch:** `feature/unify-analysis-task-naming`

---

## Overview

Every analysis process currently carries up to five independently-invented names (GUI task key,
GUI label, script filename, output folder, Python subpackage) that do not align. This plan
introduces a single **analysis registry** — one config file plus one accessor module — that
defines each process's canonical id, human label, description, output folder, and backing script.
Both the GUI and the analysis scripts read from it, so the GUI task key and the on-disk output
folder are guaranteed to derive from one canonical id. A per-task description is also surfaced in
the GUI.

## Problem Statement

For each analysis task the key, label, script name and output folder diverge with no rule relating
them (e.g. GUI key `compare_synth_real` → label "Compare Synthetic to Real" → script
`score_fidelity_all.py` → folder `fidelity/`). Consequences:

- The `"03_Analysis"` stage name and each subprocess folder name are hardcoded string literals
  repeated across ~9 scripts plus their tests. Renaming any folder means editing every script.
- `_resolve_output_base` is copy-pasted verbatim into each script.
- Two scripts (`score_fidelity.py`, `compare_real_countries.py`) escape the `03_Analysis/` tree
  entirely, writing to a relative `data/` folder.
- The GUI task keys are a separate invented vocabulary that drifts from the folder/subpackage names,
  so a user cannot infer which folder a task produces, and vice-versa.

This violates the project's **"config is the single source of truth"** invariant and makes the
pipeline layout fragile and hard to learn.

## Goals

### In Scope
1. Define one canonical id per analysis process, equal to its output-folder name and its GUI task
   key (anchor = existing subpackage/folder names).
2. Add a centralized **analysis registry** (`config/analysis/analysis_registry.yaml` +
   `analysis/utils/registry.py`) that is the single source of truth for id → {label, description,
   folder, script, dispatch}, consumed by BOTH the GUI and the scripts.
3. Rename the GUI workflow task keys to the canonical ids and surface each task's `description` in
   the GUI when the task node is clicked.
4. Replace every hardcoded `output_base/"03_Analysis"/"<name>"` construction and the duplicated
   `_resolve_output_base` with registry-backed helpers.
5. Fold the two escapee scripts (`score_fidelity.py`, `compare_real_countries.py`) under
   `03_Analysis/` with canonical folder names.

### Out of Scope
- Renaming the script *files* themselves (e.g. `score_fidelity_all.py` → `fidelity.py`). The
  registry records the script per process; filenames stay put this iteration.
- Renaming the Python analysis *subpackages* (`analysis/fidelity/`, etc.).
- Changing the per-slug vs flat nesting scheme or the multivariate double-nested charts anomaly
  (tracked separately; noted under Risks).
- Adding `cross_country` as a new GUI task (its folder is standardized, but it stays CLI-only).
- Any change to generation flows (`generate_parallel.yaml`) beyond consistency.

## Success Criteria

- [x] A single YAML file lists every analysis process with `id`, `label`, `description`, `folder`,
      `script`, `dispatch`; loading it fails loudly on missing/malformed entries.
- [x] Every analysis script derives its output directory from the registry accessor; grep finds no
      remaining hardcoded `"03_Analysis"` literal outside `analysis/utils/registry.py` (and tests
      that assert the constant).
- [x] `_resolve_output_base` exists in exactly one module; no copy in any script.
- [x] In `analysis_workflow.yaml`, each task's key equals the registry canonical id, and the task's
      output folder (derived from the registry) equals that id's folder.
- [x] Clicking an analysis task node in the GUI shows a read-only description sourced from the
      registry `description`.
- [x] `score_fidelity.py` and `compare_real_countries.py` write under `03_Analysis/` by default.
- [x] `pytest` passes (updated to reference registry-derived paths). — 465 passed (2026-07-20).

## Definitions

- **Canonical id**: the single lowercase snake_case identifier for an analysis process. It is
  simultaneously the GUI workflow task key, the `03_Analysis/` output-folder name, and the registry
  key. There is exactly one per process.
- **Analysis registry**: `config/analysis/analysis_registry.yaml`, the authoritative mapping from
  canonical id to its metadata, plus the `analysis/utils/registry.py` accessor that loads it.
- **Unified** (for this plan): for every process, GUI task key == registry id == output-folder name
  (character-for-character), and the label/description/script are looked up from the registry rather
  than duplicated in the flow YAML.
- **Escapee script**: an analysis script whose default output path is not under
  `output_base/03_Analysis/` (currently `score_fidelity.py`, `compare_real_countries.py`).

---

## Technical Design

### Approach

Introduce a registry as the single source of truth and route every consumer through it:

1. **`config/analysis/analysis_registry.yaml`** — one entry per process (canonical id as the key).
2. **`analysis/utils/registry.py`** — loads and validates the YAML (fail-fast), and exposes:
   - `ANALYSIS_STAGE_DIR = "03_Analysis"` (the one place this literal lives).
   - `get_process(process_id) -> AnalysisProcess` dataclass (`id, label, description, folder,
     script, dispatch`); raises `KeyError`/`ValueError` on unknown or malformed id.
   - `analysis_output_dir(process_id, output_base) -> Path` = `output_base / ANALYSIS_STAGE_DIR /
     process.folder`.
   - `resolve_output_base(cli_value) -> Path` — the single home for the previously copy-pasted
     resolver (reads `--output-base` else `experiment_defaults.yaml`).
3. **Scripts** replace inline `output_base / "03_Analysis" / "<name>"` and their local
   `_resolve_output_base` with `analysis_output_dir(...)` / `resolve_output_base(...)`.
4. **GUI** — `analysis_workflow.yaml` task keys become the canonical ids; each task keeps only
   GUI-orchestration fields (`depends_on`, `options`, `force`/combos, node position). Label,
   description, script and dispatch are resolved from the registry inside
   `WorkflowConfigModel.get_task_meta`, so those four are never duplicated in the flow YAML. A
   read-only description widget is added to the workflow options pane.

The canonical ids (anchor = subpackage/folder names) are:

| Canonical id (= GUI key = folder) | Label | Script | dispatch | Folder change |
|---|---|---|---|---|
| `mapping` | Map Populations | `map_populations.py` | per_combo | `mapped/` → `mapping/` (back-compat read) |
| `fidelity` | Compare Synthetic to Real | `score_fidelity_all.py` | slugs | none |
| `multivariate_fidelity` | Multivariate Joint Fidelity | `score_multivariate_fidelity.py` | slugs | none |
| `consistency` | Consistency Scan (unrealistic combos) | `scan_consistency.py` | slugs | none |
| `model_ranking` | Model Performance (models × methods) | `rank_models.py` | slugs | none |
| `method_significance` | Method Significance (per-category) | `analyze_method_significance.py` | slugs | none |
| `pairwise_comparison` | Compare Two Populations | `score_fidelity.py` | slugs | `data/comparison_report.json` → `03_Analysis/pairwise_comparison/` |
| `run_analytics_per_run` | LLM Metrics (per-run) | `analyze_run.py` | per_combo | none (`run_analytics/{slug}/`) |
| `run_analytics_cross_run` | LLM Metrics (cross-run) | `compare_run_analytics.py` | slugs | none (`run_analytics/_comparison/`) |
| `cross_country` | Cross-Country (real vs real) | `compare_real_countries.py` | n/a (CLI only) | `data/cross_country/` → `03_Analysis/cross_country/` |

Note: `run_analytics_per_run` and `run_analytics_cross_run` are two distinct GUI tasks that share
the `run_analytics/` folder tree (per-slug subfolder vs the `_comparison/` rollup). Their registry
`folder` values are `run_analytics` and `run_analytics/_comparison` respectively.

### The `mapped` → `mapping` rename

To make GUI-key == folder hold with zero exceptions, the mapping output folder is renamed
`mapped/` → `mapping/`. Because all readers now go through `analysis_output_dir("mapping", base)`,
this is a one-line registry value plus a **back-compat fallback** in the accessor: if
`03_Analysis/mapping/` is absent but a legacy `03_Analysis/mapped/` exists, the accessor returns the
legacy path (with a deprecation log) so existing on-disk data keeps working until re-mapped. This
avoids a forced data migration.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Anchor on subpackage/folder names + central registry (this plan) | Least output churn; folders already ≈ subpackages; one source of truth; satisfies core invariant | Requires GUI-model change to resolve meta from registry; one folder rename (`mapped`) | **Chosen** |
| Anchor on GUI keys, rename folders to match | Keys are intent-descriptive | Breaks every existing `03_Analysis/` path and diverges from Python package names | Rejected |
| Fresh vocabulary, rename all layers incl. scripts | Cleanest theoretical end-state | Maximal churn/risk: scripts, docs, menu.yaml, external callers, tests | Rejected |
| Align GUI keys only, no registry | Fast, low-risk | Leaves ~9× hardcoded folder literals; future renames still touch every script; two sources of truth for label | Rejected |
| Keep `mapped/` folder, id `mapping` (no rename) | No data migration | GUI key ≠ folder for one process — breaks the unify guarantee | Rejected in favor of rename + back-compat shim |

### Architecture & Module Contracts

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `config/analysis/analysis_registry.yaml` | Authoritative id → {label, description, folder, script, dispatch} table | (static config) | Python code, GUI widgets, `output_base` value |
| `analysis/utils/registry.py` | Load+validate registry; build output paths; resolve output base | `process_id`, `output_base` → `AnalysisProcess`, `Path` | Which specific script/GUI is calling; per-country logic; slug format |
| Analysis scripts (`scripts/analyze/*.py`) | Compute their analysis; ask registry where to write | `--output-base`, manifests → files under `analysis_output_dir(id, base)` | The literal `"03_Analysis"`; sibling processes' folder names |
| `WorkflowConfigModel.get_task_meta` | Merge flow-YAML orchestration fields with registry metadata | task key → meta dict incl. `label, description, script, dispatch` | Widget rendering; script internals |
| `FlowRunnerWindow` workflow pane | Render the description of the selected task | `get_task_meta(name)["description"]` → QLabel text | Registry file format; script paths |
| `config/gui/flows/analysis_workflow.yaml` | Orchestration only: node ids (= canonical ids), `depends_on`, `options`, force/combos | (static config) | label/description/script/folder (now owned by registry) |

```
config/analysis/analysis_registry.yaml        # NEW — single source of truth
src/population_synthetic/analysis/utils/
    registry.py                               # NEW — loader + AnalysisProcess + path helpers
scripts/analyze/*.py                          # EDIT — use registry helpers, drop local resolver
src/population_synthetic/gui/
    workflow_config_model.py                  # EDIT — get_task_meta merges registry meta
    main_window.py                            # EDIT — description widget in workflow options pane
config/gui/flows/analysis_workflow.yaml       # EDIT — task keys → canonical ids; strip duplicated meta
```

Registry entry shape (illustrative):

```yaml
# config/analysis/analysis_registry.yaml
stage_dir: "03_Analysis"
processes:
  fidelity:
    label: "Compare Synthetic to Real"
    description: >
      Scores each synthetic population against the real reference: per-attribute
      total-variation similarity, joint chi-squared, and coherence. Writes one
      report per (country, strategy, model) combo.
    folder: "fidelity"
    script: "scripts/analyze/score_fidelity_all.py"
    dispatch: "slugs"
  mapping:
    label: "Map Populations"
    description: "Maps raw generated + real populations to the canonical schema."
    folder: "mapping"
    legacy_folder: "mapped"        # back-compat read fallback
    script: "scripts/analyze/map_populations.py"
    dispatch: "per_combo"
  # ... one entry per canonical id
```

---

## Implementation Plan

### Phase 1: Registry foundation (no behavior change)
**Goal:** Stand up the registry + accessor and prove it reproduces today's paths.
**Started:** 2026-07-20
**Completed:** 2026-07-20

- [x] 1.1 — Author `config/analysis/analysis_registry.yaml` with all 10 processes (values matching
      current folders exactly, `mapping.folder: mapped` for now to keep Phase 1 behavior-preserving).
- [x] 1.2 — Add `analysis/utils/registry.py`: `AnalysisProcess` dataclass, `load_registry()` (fail-fast
      on missing file / missing required key / unknown extra key), `get_process`, `analysis_output_dir`,
      `resolve_output_base`, `ANALYSIS_STAGE_DIR`.
- [x] 1.3 — Unit-test the accessor against known-good paths for every id.

**Files Modified:**
- `config/analysis/analysis_registry.yaml` — new
- `src/population_synthetic/analysis/utils/registry.py` — new
- `tests/test_analysis_registry.py` — new

**Dependencies:** None

### Phase 2: Migrate scripts to the registry
**Goal:** Every analysis script resolves its output dir + output base via the registry.
**Started:** 2026-07-20
**Completed:** 2026-07-20

- [x] 2.1 — Replace each script's local `_resolve_output_base` with `registry.resolve_output_base`.
- [x] 2.2 — Replace each `output_base / "03_Analysis" / "<name>"` with
      `analysis_output_dir("<id>", output_base)` in: `map_populations.py`, `score_fidelity_all.py`,
      `score_fidelity_italy.py`, `score_fidelity_sweden.py`, `score_multivariate_fidelity.py`,
      `scan_consistency.py`, `rank_models.py`, `analyze_method_significance.py`, `analyze_run.py`,
      `compare_run_analytics.py`.
- [x] 2.3 — Update `tests/` that assert hardcoded `03_Analysis/...` paths to read from the registry.

**Files Modified:**
- `scripts/analyze/*.py` (the 10 above) — swap in registry helpers
- `tests/*` referencing analysis output paths — read from registry

**Dependencies:** Phase 1

### Phase 3: Fold in escapees + `mapped`→`mapping` rename
**Goal:** No analysis script writes outside `03_Analysis/`; mapping folder aligned.
**Started:** 2026-07-20
**Completed:** 2026-07-20

- [x] 3.1 — Point `score_fidelity.py` default output to `analysis_output_dir("pairwise_comparison", base)`.
      Migrated fully to registry accessors (dropped its local `_resolve_output_base`, `_DEFAULTS_PATH`,
      and the `03_Analysis`/`mapped` literals); report+CSV default to
      `{base}/03_Analysis/pairwise_comparison/comparison_report.json` and charts to the same folder;
      `--output`/`--charts-dir`/`--output-base` overrides preserved.
- [x] 3.2 — Point `compare_real_countries.py` default output to `analysis_output_dir("cross_country", base)`;
      report defaults to `.../cross_country/cross_country_report.json`, charts to `.../cross_country/charts/`;
      added `--output-base`; `--output`/`--charts-dir` overrides preserved.
- [x] 3.3 — Set `mapping.folder: mapping` + `legacy_folder: mapped` in the registry; added the optional
      `legacy_folder` field on `AnalysisProcess` and a `for_read` back-compat read in
      `analysis_output_dir(process_id, output_base, *, for_read=False) -> Path` (writers get the canonical
      `mapping/`; readers with `for_read=True` fall back to legacy `mapped/` + a deprecation log only when
      the canonical folder is absent but the legacy one exists). Registry tests cover write-to-`mapping/`,
      legacy-only fallback, prefer-canonical-when-both, and neither-exists.
- [x] 3.4 — Routed all downstream mapped-dir readers through `analysis_output_dir("mapping", base, for_read=True)`:
      `score_fidelity_all.py`, `score_multivariate_fidelity.py`, `scan_consistency.py`,
      `score_fidelity_sweden.py`, `score_fidelity_italy.py`, `score_fidelity.py`, and
      `model_ranking/loader.py` (which also now resolves the fidelity dir via the registry).
      Eliminated the last `03_Analysis` path literal in `src/` (`generators/synthetic/manifest_loader.py`
      now builds `comparison_output_dir` via `analysis_output_dir("fidelity", base)`).
      NOTE: `attribute_power_analysis.py` was **not** changed — it reads the config mapping *tier*
      (`config/mapping/scb_native/_index.json`, resolved from the country axis YAML), NOT the analysis-stage
      `03_Analysis/mapped/` output; its `_index.json` has a different schema. The prior-phase assumption that
      it reads the analysis mapped dir was a misidentification; routing it through the registry would break it.

**Files Modified:**
- `scripts/analyze/score_fidelity.py`, `scripts/analyze/compare_real_countries.py` — default paths + registry migration
- `src/population_synthetic/analysis/utils/registry.py` — `legacy_folder` field + `for_read` fallback
- `config/analysis/analysis_registry.yaml` — `mapping.folder: mapping` + `legacy_folder: mapped`
- `scripts/analyze/{score_fidelity_all,score_multivariate_fidelity,scan_consistency,score_fidelity_sweden,score_fidelity_italy}.py` — `for_read=True` on mapped reads
- `src/population_synthetic/analysis/model_ranking/loader.py` — registry-routed mapped + fidelity dirs
- `src/population_synthetic/generators/synthetic/manifest_loader.py` — registry-routed fidelity dir
- `tests/test_analysis_registry.py` — rename + legacy-fallback coverage

**Dependencies:** Phase 2

### Phase 4: GUI unification + description area
**Goal:** GUI task keys == canonical ids; label/description/script sourced from registry; description shown.
**Started:** 2026-07-20
**Completed:** 2026-07-20

- [x] 4.1 — Renamed task keys in `analysis_workflow.yaml` to canonical ids (map_populations→`mapping`,
      compare_synth_real→`fidelity`, joint_fidelity→`multivariate_fidelity`, consistency_scan→`consistency`,
      model_performance→`model_ranking`, compare_pops→`pairwise_comparison`,
      llm_metrics_per_run→`run_analytics_per_run`, llm_metrics_cross_run→`run_analytics_cross_run`;
      method_significance unchanged); fixed every `depends_on`; removed `label`/`script`/`dispatch` from
      all tasks (grep confirms none remain), kept `options`/force/combos/deps. Preserved the pre-existing
      `method_significance.force: true` edit.
- [x] 4.2 — `WorkflowConfigModel.get_task_meta` now resolves `label`/`description`/`script`/`dispatch`
      from the registry (`get_process(name)`), keeping GUI-only `supports_force`/`min_combos`/`max_combos`
      from the flow YAML; returns `description`; fails loudly (`KeyError`) when a flow task id is not a
      registered process. Registry import is a module-level leaf import (no cycle with the gui package).
      `to_plain()` enriches each task with the registry `label`/`script`/`dispatch` so the WorkflowState
      snapshot (runner path + tests) stays complete without re-duplicating those fields on disk.
- [x] 4.3 — Added `self._workflow_task_desc` (word-wrapped, mouse-selectable, subtle `#888` QLabel) to the
      workflow options pane in `main_window._build_ui`, between the "Task options" header and
      `self._workflow_options_panel`; set from `get_task_meta(name)["description"]` in
      `_on_workflow_node_clicked` (hidden when empty) and cleared on workflow-flow (re)load.
- [x] 4.4 — Confirmed: `gui/commands.py` receives `script: Path` from `WorkflowTask.script`, which now
      flows from the registry via `to_plain()` enrichment → `WorkflowState._parse_task`; no change needed.

**Files Modified:**
- `config/gui/flows/analysis_workflow.yaml` — keys → ids, strip duplicated meta, keep orchestration
- `src/population_synthetic/gui/workflow_config_model.py` — registry-merged `get_task_meta`
- `src/population_synthetic/gui/main_window.py` — description widget + populate
- `src/population_synthetic/gui/commands.py` — verify script resolution path

**Dependencies:** Phase 1 (registry), Phase 2/3 for folder correctness

### Phase 5: Docs + cleanup
**Goal:** Documentation reflects the unified scheme; no stray literals.
**Started:** 2026-07-20
**Completed:** 2026-07-20

- [x] 5.1 — Updated `docs/development/gui.md` (new "Task-naming contract" section: task key ==
      canonical id == folder; label/description/script/dispatch registry-owned via `get_task_meta`,
      NOT the flow YAML; flow YAML carries only orchestration; per-task description shown on node
      click; revised stale task-key references `joint_fidelity`/`compare_pops`/`map_populations`/
      `llm_metrics`/`rank_models` → canonical ids) and `CLAUDE.md` (new registry note in the
      Architecture section + `mapped/`→`mapping/` legacy read-fallback).
- [x] 5.2 — Updated `docs/architecture/commands.md` (`mapped/`→`mapping/` path refs + new "Analysis
      registry (canonical id → label → folder → script)" reference table) and `sub-packages.md`
      (`mapped/_index.json`→`mapping/_index.json`; documented `analysis/utils/registry.py` in the
      utils bullet). Also `configuration.md` (new registry inventory entry + run-analytics-defaults
      clarification), `comparison-mapping.md` (`mapped/`→`mapping/` path refs),
      `config/analysis/comparison_targets.yaml` comment, and
      `docs/swedish_synthetic_populations_and_analysis_outputs.md` (Stage A folder + legacy note).
- [x] 5.3 — Grep-swept the whole repo for `03_Analysis` / `mapped` folder-path literals. No
      functional hardcoded literal remains in code outside `analysis/utils/registry.py`
      (`ANALYSIS_STAGE_DIR`) and its config YAML; all other code hits are docstrings/help-text/
      comments or intentional test asserts. Residuals live only in historical completed/dated
      docs, user-specific manifest `comparison_output_dir` absolute paths, and the now-orphaned
      `analysis_subdir`/`task_subdir` keys in `analyze_defaults.yaml` (registry supersedes them;
      dual-source cleanup explicitly out of scope per the Risks table).

**Files Modified:**
- `docs/development/gui.md`, `CLAUDE.md`, `docs/architecture/{commands,sub-packages,configuration,comparison-mapping}.md`
- `config/analysis/comparison_targets.yaml` (comment), `docs/swedish_synthetic_populations_and_analysis_outputs.md`

**Dependencies:** Phases 1–4

---

## Testing Plan

### Unit Tests
- [ ] `analysis_output_dir(id, base)` returns the correct path for every registry id.
- [ ] `load_registry` raises on: missing file, missing required key, unknown id lookup, duplicate id.
- [ ] `resolve_output_base` honors `--output-base` then falls back to `experiment_defaults.yaml`.
- [ ] `mapping` back-compat: returns `mapping/` when present, else legacy `mapped/` with a warning.
- [ ] `get_task_meta` merges registry label/description/script/dispatch for a flow task id; raises
      when a flow task id is not in the registry.

### Integration Tests
- [ ] Run `map_populations.py` then `score_fidelity_all.py` against a fixture output-base; assert
      outputs land in `03_Analysis/mapping/` and `03_Analysis/fidelity/`.
- [ ] `score_fidelity.py` and `compare_real_countries.py` default outputs land under `03_Analysis/`.

### Manual Verification
- [ ] Launch GUI (`python -m population_synthetic.gui.main`); open Analysis Workflow; click each task
      node; confirm the description text updates and matches the registry.
- [ ] Run one analysis task from the GUI end-to-end; confirm the folder produced matches the task id.

### Edge Cases
- [ ] Legacy on-disk `mapped/` with no `mapping/` — downstream scoring still finds the data.
- [ ] A registry id present in the flow YAML but with no matching script file — fails loudly.

---

## Documentation Plan

- [x] Update `CLAUDE.md` analysis section: canonical-id scheme + registry as source of truth.
- [x] Update `docs/development/gui.md`: task key == canonical id == folder; description field contract.
- [x] Update `docs/architecture/commands.md` and `sub-packages.md`: registry-derived output paths.
- [x] Add a short reference table (canonical id → label → folder → script) to the wiki (commands.md).

---

## Rollback Plan

1. **Before merge:** work is on `feature/unify-analysis-task-naming`; abandon the branch to revert.
2. **Data considerations:** no destructive migration — the `mapped`→`mapping` change keeps a
   back-compat read of the legacy folder, so existing outputs remain consumable. New GUI-produced
   folders are additive.
3. **Rollback procedure:** revert the feature merge commit; the registry file and accessor are new
   files (deletable); flow-YAML key renames revert with the merge.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Missed hardcoded `03_Analysis`/`mapped` literal in a script or test | Med | Med | Phase 5 grep-sweep as a success criterion; CI test asserts no stray literal |
| GUI `get_task_meta` refactor breaks script-flow (non-workflow) rendering | Med | High | Description widget lives in the workflow pane only; `FlowOptionsPanel`/`_TaskOptionsAdapter` untouched (per GUI investigation) |
| `depends_on` references break when task keys are renamed | Med | High | Rename keys and their `depends_on` targets in one commit; add a load-time check that every dep resolves |
| Existing on-disk `mapped/` data orphaned by rename | Med | Med | `legacy_folder` back-compat read; deprecation log; no forced move |
| Two config sources for `output_base` drift (`experiment_defaults` vs `analyze_defaults`) | Low | Med | Out of scope here, but `resolve_output_base` centralization makes a future single-source fix trivial; note in follow-up |
| Registry becomes a second source of truth vs flow YAML for label/description | Low | Med | Flow YAML strips label/script/dispatch entirely; registry is sole owner (enforced by get_task_meta merge + test) |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — Registry foundation | S | None |
| Phase 2 — Migrate scripts | M | Phase 1 |
| Phase 3 — Escapees + mapped rename | S–M | Phase 2 |
| Phase 4 — GUI unification + description | M | Phase 1 (+2/3) |
| Phase 5 — Docs + cleanup | S | Phases 1–4 |

---

## References

- Related Plans: `docs/development/plans/completed/` (fidelity + method-significance work)
- Architecture: `docs/development/gui.md`, `docs/architecture/sub-packages.md`,
  `docs/architecture/commands.md`

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- CLAUDE.md
- config/analysis/analysis_registry.yaml
- config/analysis/comparison_targets.yaml
- config/gui/flows/analysis_workflow.yaml
- docs/architecture/commands.md
- docs/architecture/comparison-mapping.md
- docs/architecture/configuration.md
- docs/architecture/sub-packages.md
- docs/development/gui.md
- docs/development/plans/active/unify-analysis-task-naming.md
- docs/swedish_synthetic_populations_and_analysis_outputs.md
- scripts/analyze/analyze_method_significance.py
- scripts/analyze/analyze_run.py
- scripts/analyze/compare_real_countries.py
- scripts/analyze/compare_run_analytics.py
- scripts/analyze/map_populations.py
- scripts/analyze/rank_models.py
- scripts/analyze/scan_consistency.py
- scripts/analyze/score_fidelity.py
- scripts/analyze/score_fidelity_all.py
- scripts/analyze/score_fidelity_italy.py
- scripts/analyze/score_fidelity_sweden.py
- scripts/analyze/score_multivariate_fidelity.py
- src/population_synthetic/analysis/consistency/__init__.py
- src/population_synthetic/analysis/consistency/rules.py
- src/population_synthetic/analysis/model_ranking/loader.py
- src/population_synthetic/analysis/utils/registry.py
- src/population_synthetic/generators/synthetic/manifest_loader.py
- src/population_synthetic/gui/main_window.py
- src/population_synthetic/gui/workflow_config_model.py
- tests/_performance_fixtures.py
- tests/test_analysis_registry.py
- tests/test_joint_fidelity.py
- tests/test_workflow_commands.py
- tests/test_workflow_state.py
