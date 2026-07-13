# Plan: Promote gui_v2 to sole GUI, remove the deprecated v1 `gui` package

**Date:** 2026-07-13
**Author:** Basil
**Status:** Completed
**Completed:** 2026-07-13 20:08
**Base Branch:** `dev`
> Note: the working tree was on `fix/fidelity-resilient-charts-cleanup` when this
> plan was written. This feature must be **isolated** from that fix and from
> `feature/force-processing-analysis-tasks`. Create `feature/promote-gui-v2-remove-v1`
> from an up-to-date `dev` — never from `main`, and NOT stacked on either
> in-flight branch.
**Branch:** `feature/promote-gui-v2-remove-v1`

---

## Overview

Make `gui_v2` (the config-driven Flow Runner) the only GUI by extracting the
handful of shared-substrate pieces it still imports from the deprecated v1
`gui` package into `gui_v2`, then deleting the `gui` package and its v1-only
config wholesale. The result: one GUI package, no dead launcher, no
`gui_v2 → gui` back-dependency.

## Problem Statement

`gui_v2` superseded the original `gui` launcher for day-to-day use, but the old
package was retained as a "shared-widget substrate": `gui_v2` still imports six
pieces from `gui` (a runner, a process-kill helper, a dataclass, and three/four
widgets). This leaves a deprecated, unshipped-but-imported window
(`LauncherWindow`) and its config schema in the tree, a confusing second entry
point (`python -m population_synthetic.gui.main`), two parallel DAG-item widget
sets, and a documented rule that "the package must not be removed." It is
technical debt and a maintenance/onboarding hazard.

## Goals

### In Scope
1. Extract every symbol `gui_v2` imports from `gui` into `gui_v2` (clean split of
   the three mixed modules; whole-file move of the four clean ones).
2. Delete the `gui` package entirely, plus its v1-only config
   (`config/gui/launcher.yaml`, `config/gui/layouts/`, `config/gui/state.json`).
3. Update all packaging + documentation references so no `gui.main` /
   `population_synthetic.gui` reference remains.
4. Preserve the grid-snapping already added to the strategy-DAG widget (the
   moved `dag_graph_*` files carry it).

### Out of Scope
- Any behavioural change to `gui_v2` (this is a move/delete + rewire, not a
  feature change). The strategy-DAG grid-snapping is already implemented on the
  working tree and merely rides along with the file move.
- Renaming the `gui_v2` package to `gui` (keep the `gui_v2` name; a package
  rename is a larger, separate churn with no functional benefit). Revisit later
  if desired.
- Changes to `config/gui/v2/` (the live Flow Runner config stays put).

## Success Criteria

- [ ] `grep -rn "population_synthetic\.gui\b\|population_synthetic\.gui\." src/ scripts/ tests/` returns **zero** hits (only `gui_v2` remains).
- [ ] `src/population_synthetic/gui/` no longer exists.
- [ ] `python -m population_synthetic.gui_v2.main` launches; generate flows show the strategy DAG (with snapping + grid), workflow flows show the task DAG (with snapping + grid).
- [ ] `python -c "import population_synthetic.gui_v2.main_window"` and `...workflow_runner`, `...widgets.axis_selector`, `...widgets.population_summary` all import cleanly.
- [ ] `ruff check src/` passes; `pytest` passes (no test imports `gui`, so this is a regression guard).
- [ ] No `gui.main` / v1-launcher reference remains in `README.md`, `CLAUDE.md`, `docs/architecture/{commands,configuration}.md`, `docs/development/gui-v2.md`.

---

## Technical Design

### Approach

`gui_v2`'s dependencies on `gui` fall into two clean categories — **whole-file
moves** (the symbol's entire module is shared) and **symbol extractions** (the
module mixes a shared symbol with v1-only code). Verified during research:
`CombinationRunner`/`_kill_process_tree` depend only on `ActionEntry` + stdlib,
and `PersonaCountWorker` depends only on glob/count helpers — neither drags in
v1-only code — so both extractions are clean.

#### What `gui_v2` imports from `gui` today

| Symbol needed by gui_v2 | Current location | Disposition |
|---|---|---|
| `ActionEntry` | `gui/launcher_config.py` (+ `LauncherConfig`, `ActionParameter`, `parse_launcher_config` — v1-only) | **Extract** → `gui_v2/execution.py` |
| `CombinationRunner`, `_kill_process_tree` | `gui/main_window.py` (+ `LauncherWindow` — v1-only) | **Extract** → `gui_v2/execution.py` |
| `PersonaCountWorker` | `gui/widgets/manifest_overview.py` (+ `ManifestOverview` — v1-only) | **Extract** → `gui_v2/widgets/persona_count_worker.py` |
| `ConsoleWidget`, `ProcessOutputReader` | `gui/widgets/console_widget.py` | **Move whole file** → `gui_v2/widgets/console_widget.py` |
| `DagGraphWidget`, `DagCategoryNode`, `DagEdge` | `gui/widgets/dag_graph_widget.py`, `dag_graph_items.py` | **Move whole files** → `gui_v2/widgets/` (carry snapping) |
| `CheckableAxisList` | `gui/widgets/checkable_axis_list.py` | **Move whole file** → `gui_v2/widgets/checkable_axis_list.py` |

#### v1-only — delete
`gui/main.py`, `gui/manifest_model.py`, `gui/launcher_config.py` (after extracting
`ActionEntry`), `gui/main_window.py` (after extracting the runner),
`gui/widgets/manifest_overview.py` (after extracting the worker),
`gui/widgets/{action_selector,configuration_panel,parameter_panel,manifest_selector,task_selector}.py`,
and the two `__init__.py`. Then remove the now-empty `gui/` tree.
Config: `config/gui/launcher.yaml`, `config/gui/layouts/`, `config/gui/state.json`.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Extract shared substrate into `gui_v2`, delete `gui` | One GUI package; no back-dependency; removes dead window/config | Must split 3 mixed modules; touches import sites + docs | **Chosen** |
| Leave `gui` as a substrate library, delete only `gui/main.py` + `LauncherWindow` | Smaller diff | Keeps a confusing half-package; `gui_v2 → gui` back-dependency persists; two `__init__` trees | Rejected |
| Rename `gui_v2` → `gui` after removal | "Clean" final name | Extra churn across every import + doc + entry point; no functional gain; risk during a fidelity-active period | Deferred (out of scope) |
| Move shared bits to a new neutral `gui_common` package | Neither GUI "owns" the other | `gui_v2` is now the only consumer — a third package is over-engineering | Rejected |

### Architecture Changes

New/target `gui_v2` layout (added files marked `＋`):

```
src/population_synthetic/gui_v2/
  execution.py                    ＋ _kill_process_tree, ActionEntry, CombinationRunner
  main_window.py                    (rewire imports)
  workflow_runner.py                (rewire _kill_process_tree import)
  widgets/
    console_widget.py             ＋ moved from gui/widgets/
    dag_graph_items.py            ＋ moved from gui/widgets/ (has snapping)
    dag_graph_widget.py           ＋ moved from gui/widgets/ (has snapping)
    checkable_axis_list.py        ＋ moved from gui/widgets/
    persona_count_worker.py       ＋ PersonaCountWorker extracted from manifest_overview
    axis_selector.py                (rewire CheckableAxisList import)
    population_summary.py           (rewire PersonaCountWorker import)
```

`src/population_synthetic/gui/` — **removed.**

Import-rewrite map (the only edits to existing `gui_v2` code):
- `gui_v2/main_window.py`: `ActionEntry, CombinationRunner` ← `gui_v2.execution`;
  `ConsoleWidget` ← `gui_v2.widgets.console_widget`;
  `DagGraphWidget` ← `gui_v2.widgets.dag_graph_widget`.
- `gui_v2/workflow_runner.py`: `_kill_process_tree` ← `gui_v2.execution` (currently
  a function-local import at line ~254).
- `gui_v2/widgets/axis_selector.py`: `CheckableAxisList` ← `gui_v2.widgets.checkable_axis_list`.
- `gui_v2/widgets/population_summary.py`: `PersonaCountWorker` ← `gui_v2.widgets.persona_count_worker`.

---

## Implementation Plan

### Phase 1: Extract the shared substrate into gui_v2
**Goal:** Every symbol gui_v2 needs lives in gui_v2; gui_v2 still also works via old imports (not yet rewired), so nothing is broken mid-phase.

- [x] Create `gui_v2/execution.py` with `_kill_process_tree`, `ActionEntry` (dataclass), and `CombinationRunner`, copied verbatim from `gui/` (drop the v1-only imports; keep `axis_slug`/`discover_axis_values` only if referenced — verify).
- [x] Move `gui/widgets/console_widget.py` → `gui_v2/widgets/console_widget.py` (unchanged content).
- [x] Move `gui/widgets/dag_graph_items.py` and `dag_graph_widget.py` → `gui_v2/widgets/` (they already carry the grid-snapping edits; keep the local `GRID_SIZE`).
- [x] Move `gui/widgets/checkable_axis_list.py` → `gui_v2/widgets/checkable_axis_list.py`.
- [x] Create `gui_v2/widgets/persona_count_worker.py` with `PersonaCountWorker` extracted from `manifest_overview.py` (drop the `ExperimentSelection` import — verify it is unused by the worker).

**Phase 1 Started:** 2026-07-13
**Phase 1 Completed:** 2026-07-13

**Files Modified:** listed above (all additions/moves under `gui_v2/`).
**Dependencies:** None.

### Phase 2: Rewire gui_v2 imports to the new locations
**Goal:** gui_v2 no longer imports from `gui`.

- [x] `gui_v2/main_window.py` — repoint the four `from population_synthetic.gui...` imports.
- [x] `gui_v2/workflow_runner.py` — repoint `_kill_process_tree`.
- [x] `gui_v2/widgets/axis_selector.py` — repoint `CheckableAxisList`.
- [x] `gui_v2/widgets/population_summary.py` — repoint `PersonaCountWorker`.
- [x] Smoke-import every rewired module; confirm `grep -rn "population_synthetic\.gui\b\|population_synthetic\.gui\." src/` is empty (outside the `gui/` package itself, which Phase 3 deletes).

**Phase 2 Started:** 2026-07-13
**Phase 2 Completed:** 2026-07-13

**Files Modified:** the four gui_v2 files above.
**Dependencies:** Phase 1.

### Phase 3: Delete the v1 package and its config
**Goal:** `gui/` and v1 config are gone.

- [x] `git rm -r src/population_synthetic/gui/`.
- [x] `git rm config/gui/launcher.yaml config/gui/state.json` and `git rm -r config/gui/layouts/` (keep `config/gui/v2/`).
- [x] Re-run the grep guard over `src/ scripts/ tests/`.

**Phase 3 Started:** 2026-07-13
**Phase 3 Completed:** 2026-07-13

**Files Modified:** deletions only.
**Dependencies:** Phase 2.

### Phase 4: Packaging + documentation sweep
**Goal:** No dangling references anywhere.

- [x] `pyproject.toml` — confirm the `[gui]` extra stays (still needed by gui_v2) and that no `console_scripts`/entry point references `gui.main` (research showed none — verify).
- [x] `README.md` — remove the "deprecated `gui` retained as fallback" lines (13, 152, 196–197); leave only gui_v2.
- [x] `CLAUDE.md` — drop the deprecated `python -m population_synthetic.gui.main` line (34).
- [x] `docs/architecture/commands.md` (108) and `configuration.md` (20) — remove the v1 launcher mentions.
- [x] `docs/development/gui-v2.md` — rewrite the "reuses gui widgets… the package must not be removed" section (lines ~5–9) to describe the now-internal `gui_v2/execution.py` + moved widgets.
- [x] Grep docs for any remaining `gui.main` / `population_synthetic.gui` prose.

**Phase 4 Started:** 2026-07-13
**Phase 4 Completed:** 2026-07-13

**Files Modified:** `README.md`, `CLAUDE.md`, `docs/architecture/commands.md`, `docs/architecture/configuration.md`, `docs/development/gui-v2.md`. (`pyproject.toml` verified only — no edit needed: no `console_scripts`/`[project.scripts]` section exists, and `[tool.setuptools.packages.find]` uses auto-discovery with no hardcoded package list.)
**Dependencies:** Phase 3.

---

## Testing Plan

### Unit / Import Tests
- [ ] `python -c "import population_synthetic.gui_v2.main_window, population_synthetic.gui_v2.workflow_runner, population_synthetic.gui_v2.execution"` — clean.
- [ ] `python -c "import population_synthetic.gui_v2.widgets.axis_selector, population_synthetic.gui_v2.widgets.population_summary, population_synthetic.gui_v2.widgets.dag_graph_widget, population_synthetic.gui_v2.widgets.console_widget, population_synthetic.gui_v2.widgets.persona_count_worker"` — clean.
- [ ] `ruff check src/` — passes.
- [ ] `pytest` — passes (regression guard; no test imports `gui`).

### Manual Verification
- [ ] Launch `python -m population_synthetic.gui_v2.main`.
- [ ] Select a **generate** (script) flow → strategy DAG renders; nodes drag-snap to the grid; faint gridlines visible.
- [ ] Select the **analysis workflow** flow → task DAG renders; per-node checkboxes + snapping + gridlines intact.
- [ ] Run a small generate combo and a workflow task → console streams, Abort kills the process tree (confirms the moved `CombinationRunner`/`_kill_process_tree`).
- [ ] Population Summary tab still ticks live counts (confirms the moved `PersonaCountWorker`).

### Edge Cases
- [ ] `python -m population_synthetic.gui.main` now fails with `ModuleNotFoundError` (expected — entry point removed).
- [ ] A stale `config/gui/launcher.yaml` reference (if any external script cached it) fails loudly rather than silently.

---

## Documentation Plan

- [x] `README.md` — single-GUI description, drop fallback lines.
- [x] `CLAUDE.md` — drop the deprecated launcher line.
- [x] `docs/development/gui-v2.md` — rewrite the substrate/reuse section.
- [x] `docs/architecture/commands.md`, `configuration.md` — remove v1 launcher mentions.

## Rollback Plan

1. **Before merge:** the entire change lives on `feature/promote-gui-v2-remove-v1`; the branch is a pure move/delete + rewire. Revert = delete the branch (nothing merged).
2. **After merge:** `git revert` the merge commit restores `gui/` and its config verbatim (all deletions are tracked moves). No data migrations, no state files consumed by other tools.
3. **Data considerations:** none — `gui/` produces no artifacts other tools read; `.layout.json` sidecars are written by the (moved) widgets and are unaffected by the package location.

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| A shared symbol secretly pulls a v1-only import when moved | Low | Med | Research already traced `CombinationRunner` + `PersonaCountWorker` deps; Phase 1 verifies each moved module imports in isolation before Phase 3 deletes anything. |
| A `.layout.json` sidecar path changes because the widget moved packages | Low | Low | Sidecar path is derived from the *strategy/flow file* path, not the widget module — unaffected. Confirm in manual verification. |
| Hidden importer outside `src/` (a notebook, an external script) references `population_synthetic.gui` | Low | Low | Grep guard covers `src/ scripts/ tests/`; note in PR that any out-of-repo caller must switch to `gui_v2`. |
| Doc drift — a missed `gui.main` mention | Med | Low | Phase 4 ends with a repo-wide grep for `gui.main` / `population_synthetic.gui`. |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — extract substrate | ~45 min | None |
| Phase 2 — rewire imports | ~15 min | Phase 1 |
| Phase 3 — delete v1 | ~10 min | Phase 2 |
| Phase 4 — docs/packaging sweep | ~20 min | Phase 3 |

---

## References

- Related (completed): `docs/development/plans/completed/gui-v2-flow-runner.md` — the original v2 build; its Risks table foresaw this ("if old GUI is later removed, extract the ~70-line runner into `gui_v2/execution.py`") and flagged the two DAG-item widget sets for consolidation.
- Prerequisite context: strategy-DAG grid-snapping was added to `gui/widgets/dag_graph_{items,widget}.py` (and `gui_v2/widgets/workflow_graph_{items,view}.py`) on the working tree before this plan; those `gui/` files move into `gui_v2` in Phase 1.

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- CLAUDE.md
- README.md
- config/gui/launcher.yaml
- docs/architecture/commands.md
- docs/architecture/configuration.md
- docs/development/gui-v2.md
- docs/development/plans/active/promote-gui-v2-remove-v1.md
- src/population_synthetic/gui/__init__.py
- src/population_synthetic/gui/launcher_config.py
- src/population_synthetic/gui/main.py
- src/population_synthetic/gui/main_window.py
- src/population_synthetic/gui/manifest_model.py
- src/population_synthetic/gui/widgets/__init__.py
- src/population_synthetic/gui/widgets/action_selector.py
- src/population_synthetic/gui/widgets/checkable_axis_list.py
- src/population_synthetic/gui/widgets/configuration_panel.py
- src/population_synthetic/gui/widgets/console_widget.py
- src/population_synthetic/gui/widgets/dag_graph_items.py
- src/population_synthetic/gui/widgets/dag_graph_widget.py
- src/population_synthetic/gui/widgets/manifest_overview.py
- src/population_synthetic/gui/widgets/manifest_selector.py
- src/population_synthetic/gui/widgets/parameter_panel.py
- src/population_synthetic/gui/widgets/task_selector.py
- src/population_synthetic/gui_v2/execution.py
- src/population_synthetic/gui_v2/main_window.py
- src/population_synthetic/gui_v2/widgets/axis_selector.py
- src/population_synthetic/gui_v2/widgets/checkable_axis_list.py
- src/population_synthetic/gui_v2/widgets/console_widget.py
- src/population_synthetic/gui_v2/widgets/dag_graph_items.py
- src/population_synthetic/gui_v2/widgets/dag_graph_widget.py
- src/population_synthetic/gui_v2/widgets/persona_count_worker.py
- src/population_synthetic/gui_v2/widgets/population_summary.py
- src/population_synthetic/gui_v2/workflow_runner.py

> Note: `config/gui/state.json` and `config/gui/layouts/` were also removed (untracked/gitignored, so absent from `git status`). Unrelated pre-existing working-tree changes that merely rode along with the branch checkout (openrouter model configs, `comparison-metrics*`, `swedish-token-cost-by-model.md`, `config/gui/v2/flows/generate_parallel.yaml`, `gui_v2/widgets/workflow_graph_{items,view}.py`, `uniform-analysis-output-naming.md`) are **excluded** from this plan's commit scope.
