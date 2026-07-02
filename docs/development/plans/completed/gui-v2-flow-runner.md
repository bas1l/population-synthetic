# Plan: gui_v2 — config-driven Flow Runner GUI

**Date:** 2026-07-01 (amended 2026-07-02: dependency-linked Analysis Workflow; ComboTree → flat axis lists; `targets` dispatch dropped)
**Author:** Basil
**Status:** Completed (2026-07-02)
**Base Branch:** `feature/model-performance-comparison`
**Branch:** `feature/gui-v2-flow-runner`

---

## Overview

Build a **new, parallel PyQt5 GUI** (`src/population_synthetic/gui_v2/`) modelled
on the reference *AnalysisRunnerGUI* in
`F:\GitHub\touch_projects\social-touch-semi-controlled-analysis`. It adopts that
GUI's cleaner idioms — a two-tier config (a menu YAML of flows + one **editable,
round-trip** config YAML per flow) and a **shape-dispatching options editor** —
while keeping the existing `src/population_synthetic/gui/` launcher **fully
intact as a fallback**. Besides single-script flows, the Analysis category gets
one **workflow** flow: a DAG of analysis tasks with `depends_on` edges rendered
as a node graph with per-node Enabled checkboxes and a **single Run** that
executes the enabled chain in dependency order (reference parity with its
`DagConfigHandler`/`TaskExecutor`/`dag_graph_view` trio).

## Problem Statement

The current launcher (`gui/`) works but has structural friction: (1) options are
transient CLI overrides that are **never persisted** — every launch starts from
scratch; (2) two disjoint config systems (`config/gui/launcher.yaml` for
flows/params vs `config/synthetic/axes/` for model/strategy/country) meet only
through a hardcoded `requires_manifest` boolean; (3) there is dead/duplicated
code (`widgets/action_selector.py`, two override-command builders); (4) the
Analysis group is six flat, independent bullet points even though three of them
form a real data pipeline — `map_populations` writes
`03_Analysis/mapped/*.json`, `compare_all_pipelines.py` consumes those, and
`compare_model_performance.py` consumes the comparison reports — with the
ordering expressed only in a label string ("run before Compare"), so nothing
stops a user running Compare before Map. The reference GUI solves these with an
editable-per-flow-YAML model, a declarative option editor, and a `depends_on`
DAG with gated chained execution. We want those ergonomics without risking the
working launcher, hence a parallel build.

## Goals

### In Scope
1. New `gui_v2` package with its own entry point
   (`python -m population_synthetic.gui_v2.main`), coexisting with the old GUI.
2. Two-tier config under `config/gui/v2/`: a `menu.yaml` listing flows grouped by
   category + one **round-trip editable** YAML per flow (options + selection +
   force), edited and **saved back** from the GUI (ruamel round-trip).
3. Three-column layout `Flows | [Options | Workflow/DAG] | Axis selection` over a
   reused console + Run/Abort bar, plus a Save/Save-As toolbar.
4. Right column = **three flat checkable axis lists** (models / strategies /
   countries, cartesian product), reusing `CheckableAxisList`
   (`gui/widgets/checkable_axis_list.py`) in the style of the existing
   `ExperimentSelector` (`gui/widgets/manifest_selector.py`) — the same
   models × strategies × countries selection mechanism the current launcher
   uses — with the selection persisted into the flow YAML instead of
   `config/gui/state.json`.
5. Shape-dispatching options editor (enum dropdowns, bool checkboxes, typed line
   edits, conditional visibility) driven by declarative tables.
6. Execution reuses the existing `CombinationRunner` + `_kill_process_tree` and
   the scripts' existing CLI contract — **no script rewrites**.
7. DAG View tab in v1 (reusing the existing `DagGraphWidget`) for strategy DAGs.
8. **Analysis Workflow flow (`kind: workflow`)**: a DAG YAML of analysis tasks
   (`{script, dispatch, enabled, options, depends_on, min/max_combos}`), a
   node-graph panel with per-node Enabled/Force checkboxes, and a
   `WorkflowRunner` that executes the enabled chain GUI-side in dependency
   order — a failed or disabled task skips its dependents while independent
   branches continue. Chain: `map_populations → compare_synth_real →
   model_performance`, side branch `map_populations → compare_pops`, plus two
   isolated `llm_metrics` nodes.

### Out of Scope
- Any modification to the existing `gui/` package, `config/gui/launcher.yaml`, or
  `config/gui/state.json` (the old GUI must remain byte-for-byte functional).
- Rewriting generation/analysis scripts to read a flow-level config file.
- Cross-combo parallelism (batch stays sequential, as today).
- A run-history/session browser of completed runs on disk (future work).
- Removing the old GUI (deferred until gui_v2 is proven).
- Persisting workflow run states (node statuses are per-run, never written to
  YAML).

## Success Criteria

- [ ] `python -m population_synthetic.gui.main` (old GUI) still launches unchanged.
- [ ] `python -m population_synthetic.gui_v2.main` launches: 3 columns + console +
      Run/Abort bar; flows grouped by category from `menu.yaml`.
- [ ] Selecting a flow loads its editable YAML; editing an option marks the title
      dirty (`*`); Ctrl+S writes it back with **comments/order preserved**.
- [ ] Right column shows the three checkable axis lists; checked
      models × strategies × countries define the combo set; "Combos: N" reflects
      the cartesian-product count; selection round-trips via the flow YAML
      `selection:` block.
- [ ] A three-axis flow runs each checked combo via
      `--model-id/--strategy-id/--country-id` (+ overrides, + `--force` for
      generate flows).
- [ ] DAG View tab renders the strategy DAG for the first checked combo.
- [ ] The Analysis Workflow renders 6 nodes (2 isolated); toggling a node's
      Enabled checkbox grays it and round-trips via Ctrl+S.
- [ ] A workflow Run with ≥2 checked combos executes map → compare →
      model_performance in dependency order with per-task console banners; a
      nonzero exit in map marks it red and skips both dependents, while enabled
      llm_metrics islands still run.
- [ ] `compare_pops` with ≠2 checked combos produces a **loud** console skip
      warning + amber node; the run continues.
- [ ] A cycle or unknown `depends_on` target in the workflow YAML makes the flow
      fail to load with a clear error (fail-fast).
- [ ] Abort kills the whole process tree (no orphaned `claude`/`ollama`
      grandchildren); remaining workflow nodes show ABORTED.
- [ ] `ruff check src/` passes on the new package.

---

## Technical Design

### Key decision — execution contract

The reference launches a script that **re-reads its own YAML**. Our scripts
instead run **one combo per invocation** and accept
`--model-id/--strategy-id/--country-id` (or `--manifest`) **plus override flags**
— confirmed in `scripts/generate/generate_identities_parallel.py` (`main()`
~L213–316) and `scripts/analyze/compare_pipeline_to_scb.py` (`build_parser()`
~L52–122); the axis-ID branch calls the same `compose_manifest(...)` a loaded
manifest would use.

**Decision: gui_v2 keeps the reference's "edit + save a per-flow YAML" UX, but on
Run it TRANSLATES that YAML into CLI invocations of the existing scripts. The
spawned scripts do NOT read the flow YAML.** This must be stated in a code
comment to prevent a future dev wiring a non-existent `--flow-config` arg. It
reuses our proven `CombinationRunner` + `_kill_process_tree` verbatim and needs
zero script changes.

The contract extends to the workflow: chained execution is **GUI-side** — a
`WorkflowRunner` thread walks the DAG in dependency order, builds each task's
CLI invocation(s) via pure builders in `commands.py`, runs them as subprocesses,
and marks the task completed on exit code 0.

Dispatch shapes (all routed through `commands.py`):

- `three_axis` (single-script generate/compare flows): each checked combo → one
  `[python, script, --model-id, --strategy-id, --country-id, <overrides>,
  (--force)]` invocation via `CombinationRunner`.
- Workflow task `dispatch: per_combo`: same per-combo arg vector, one
  invocation per checked combo, run sequentially inside the task's turn.
- Workflow task `dispatch: slugs`: ONE invocation with one
  `--slug {country}_{strategy}_{model}` per checked combo (slug via
  `axis_slug()`, `generators/synthetic/manifest_loader.py` ~L148).

**`--targets` dispatch is dropped entirely.** Investigation of
`scripts/analyze/map_populations.py` (~L134–144) showed `--targets` entries must
be **manifest file paths**, which composed-axis combos do not have on disk; the
axis-ID mode (~L279, L309–320) composes the manifest and upserts `_index.json`
correctly. So `map_populations` dispatches `per_combo`, and the previously
planned `targets.py` module and `axis_mode: targets` are removed (nothing else
used them).

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Extend the existing `gui/` in place | No duplication | High risk to the one working launcher; the user explicitly wants a fallback | Rejected |
| New `gui_v2`, GUI translates flow YAML → per-combo CLI (reuse `CombinationRunner`) | No script rewrites; reuses battle-tested runner + process-tree kill; keeps old GUI intact | v2 couples to old `gui.main_window` by import; "save before run" is persistence-only | **Chosen** |
| New `gui_v2`, rewrite scripts to read the flow YAML directly (true reference parity) | Purest adoption of reference model | Large blast radius across many scripts; breaks the CLI contract shared with headless use | Rejected |
| Right column = tri-state checkable tree grouped by model | Folder-toggle convenience | Diverges from the proven three-axis selection the user wants to keep; new widget to build | Rejected — user constraint: keep the current models × strategies × countries mechanism |
| Right column = three flat checkable axis lists (reuse `CheckableAxisList`) | Identical selection semantics to today's launcher; widget reused unmodified | Checking "everything for one model" stays a two-click affair | **Chosen** |
| Workflow ordering hardcoded in Python (reference's `stage_runner.py` stage list) | Simple | Violates config-single-source-of-truth; a second place to maintain order | Rejected — order derived from `depends_on` via topological sort |
| Workflow guard violations abort the whole run | Strictest fail-fast | One opt-in side branch (compare_pops) would block the main chain | Rejected — loud console skip + amber node; run continues |

### Architecture Changes

New package (nothing in old `gui/` changes):

```
src/population_synthetic/gui_v2/
  __init__.py
  main.py                    # entry: HighDPI attrs before QApplication, sys.excepthook, parse menu, show window
  menu_config.py             # FlowEntry dataclass (+ kind field) + parse_menu_config()  (port of reference runner_config.py)
  flow_config_model.py       # FlowConfigModel — ruamel round-trip                       (slim port of reference dag_config_model.py)
  workflow_config_model.py   # WorkflowConfigModel(FlowConfigModel) — per-task accessors
  workflow_state.py          # WorkflowTask + WorkflowState (Qt-free): validate, ordered_tasks, can_run, mark_completed, status map
  workflow_runner.py         # WorkflowRunner(QThread) — walks the DAG, generalizes CombinationRunner
  commands.py                # pure build_per_combo_cmds / build_slugs_cmd, shared by script flows + workflow tasks
  main_window.py             # FlowRunnerWindow(QMainWindow)                             (port of reference runner_window.py, minus Prefect)
  widgets/
    __init__.py
    flow_selector.py         # left column, category-grouped exclusive buttons           (port of reference workflow_selector.py)
    flow_options_panel.py    # center Options tab, shape-dispatching editor              (slim port of reference task_detail_panel.py)
    axis_selector.py         # right column, three reused CheckableAxisList widgets bound to the flow YAML selection block
    workflow_graph_items.py  # port of reference dag_graph_items.py: node with Enabled/Force checkboxes + run-state overlay
    workflow_graph_view.py   # port of reference dag_graph_view.py: grandalf Sugiyama + .layout.json sidecar
    collapsible_section.py   # copied from reference (~60 lines)
```

**Reused by import (no edits to old files):**
- `gui/widgets/console_widget.py` → `ConsoleWidget`, `ProcessOutputReader`
- `gui/widgets/checkable_axis_list.py` → `CheckableAxisList` (axis selector)
- `gui/widgets/dag_graph_widget.py` → `DagGraphWidget` (center DAG tab, strategy DAGs)
- `gui/main_window.py` → `CombinationRunner`, `_kill_process_tree` (execution;
  import-time is side-effect free — no QApplication)
- `generators/synthetic/manifest_loader.py` → `discover_axis_values`,
  `compose_manifest`, `axis_slug` (axis discovery + strategy DAG path + slugs)

The workflow graph items are a **port of the reference's**
(`src/utils/gui/analysis_runner_gui/dag_graph_items.py` — `DagTaskNode` with
embedded checkbox `QGraphicsProxyWidget`s, disabled = gray + 0.55 opacity), not
an adaptation of the in-repo `gui/widgets/dag_graph_items.py` (`DagCategoryNode`
has no checkbox and the old GUI must stay untouched). Both use the same grandalf
layout + `.layout.json` sidecar pattern, so the port is mechanical. New over the
reference: a `set_task_status(name, TaskStatus)` overlay — PENDING = category
color, RUNNING = thick blue border, COMPLETED = green border + ✓, FAILED = red
border + ✗, SKIPPED_* = amber @ 0.55 opacity.

**New dependency:** add `ruamel.yaml>=0.18` to the `[gui]` extra in
`pyproject.toml` (currently `gui = ["PyQt5>=5.15", "grandalf>=0.8"]`). `PyQt5` and
`grandalf` already present.

### Config schema

**Menu YAML — `config/gui/v2/menu.yaml`:** a flow entry gains an optional
`kind: script | workflow` (default `script`). A `kind: workflow` entry has **no
top-level `script`** — scripts live per task in its config. Fail-fast:
`kind: workflow` with a `script` key → error; `kind: script` without one →
error. (Missing *files* keep the warn-and-skip behavior.)

```yaml
categories:
  - name: Generate
    flows:
      - name: LLM Synthetic Population
        kind: script                 # default; may be omitted
        script: scripts/generate/generate_identities_parallel.py
        config: config/gui/v2/flows/generate_parallel.yaml
        axis_mode: three_axis
  - name: Analysis
    flows:
      - name: Pipeline vs Reference
        script: scripts/analyze/compare_pipeline_to_scb.py
        config: config/gui/v2/flows/compare_scb.yaml
        axis_mode: three_axis
      - name: Analysis Workflow
        kind: workflow
        config: config/gui/v2/flows/analysis_workflow.yaml
```
`FlowEntry` = `{name, kind, script: Path | None, config: Path, category: str,
axis_mode: str | None}`. Parser skips entries whose `script`/`config` files are
missing (warn, keep launching), mirroring the reference.

**Per-flow editable YAML (option keys are CLI flag names, dash form):**
```yaml
# config/gui/v2/flows/generate_parallel.yaml
# options keys are CLI flag names; the GUI turns them into per-combo CLI args
# (the script does NOT read this file).
options:
  n: 100                     # --n
  workers: 8                 # --workers
  retry-until-success: false # --retry-until-success (flag when true)
selection:
  models:     [claude_haiku]
  strategies: [all_pick]
  countries:  [swedish]
force: false                 # generate flows only
```
`compare_scb.yaml` uses the same shape, **omits `force`**, with options
`output-base` / `no-charts` / `radar-tv-only`. Per-option UI metadata (enum
choices, labels, ranges) is NOT stored in the YAML — it lives in declarative
tables in `flow_options_panel.py`, keyed by option name.

**Workflow YAML — `config/gui/v2/flows/analysis_workflow.yaml`** (the DAG is
config-only; no Python stage list):

```yaml
# Analysis workflow DAG. The GUI walks tasks in dependency order and TRANSLATES
# each into CLI invocations of the task's script (scripts do NOT read this file).
# dispatch:
#   per_combo — one invocation per checked combo: --model-id/--strategy-id/--country-id
#   slugs     — one invocation total, with one --slug {country}_{strategy}_{model} per combo
tasks:
  map_populations:
    label: Map Populations
    script: scripts/analyze/map_populations.py
    dispatch: per_combo
    enabled: true
    supports_force: true          # node shows a Force checkbox -> --force
    force: false
    options:
      output-base:                # --output-base (blank = script default)
    depends_on: []

  compare_synth_real:
    label: Compare Synthetic to Real
    script: scripts/analyze/compare_all_pipelines.py
    dispatch: slugs
    enabled: true
    options:
      no-charts: false            # --no-charts (flag when true)
      radar-tv-only: false        # --radar-tv-only
      output-base:
    depends_on: [map_populations]

  model_performance:
    label: Model Performance (models x methods)
    script: scripts/analyze/compare_model_performance.py
    dispatch: slugs
    enabled: true
    min_combos: 2                 # guard: loud skip below 2 checked combos
    options:
      no-charts: false
      per-attribute-charts: false
      strict: false
      output-base:
    depends_on: [compare_synth_real]

  compare_pops:
    label: Compare Two Populations
    script: scripts/analyze/compare_populations.py
    dispatch: slugs
    enabled: false                # opt-in: needs EXACTLY 2 combos
    min_combos: 2
    max_combos: 2
    options:
      output:                     # --output (blank = script default)
      no-charts: false
    depends_on: [map_populations]

  llm_metrics_per_run:            # independent — isolated node
    label: LLM Metrics (per-run)
    script: scripts/analyze/analyze_run.py
    dispatch: per_combo
    enabled: false
    supports_force: true
    force: false
    options:
      charts:                     # --charts DIR (blank = default)
      verbose: false
    depends_on: []

  llm_metrics_cross_run:          # independent — isolated node
    label: LLM Metrics (cross-run)
    script: scripts/analyze/compare_runs.py
    dispatch: slugs
    enabled: false
    options:
      metrics:                    # --metrics KEY... (blank = all)
    depends_on: []

selection:                        # shared by ALL tasks in the chain
  models:     [claude_haiku]
  strategies: [all_pick]
  countries:  [swedish]
```

Validation is **fail-fast at flow load** (`WorkflowState.validate()`): unknown
`depends_on` target → raise; cycle (Kahn leftover, members named) → raise;
`script` missing on disk → raise; `dispatch` not in `{per_combo, slugs}` →
raise; `min_combos > max_combos` → raise.

### Workflow execution semantics

`_on_run` (workflow branch): save dirty model → build `WorkflowState` from a
plain snapshot → `validate()` → combos = cartesian product of the axis
selector's checked ids (same as `gui/manifest_model.py` `combinations()`) →
empty-selection warning like the old GUI → `WorkflowRunner(state, combos)`.

Per task, in `ordered_tasks()` order (Kahn topological sort, YAML authoring
order as FIFO tie-break — deterministic):

1. **Disabled** → status `SKIPPED_DISABLED`, console one-liner, not completed.
2. **Deps not completed** → `SKIPPED_DEP`, console
   `-- SKIP model_performance (dependency 'compare_synth_real' did not complete)`.
3. **Guard violated** (`min_combos`/`max_combos` vs checked-combo count) →
   `SKIPPED_GUARD` + **loud** banner:
   `!! SKIP compare_pops: needs exactly 2 selected combinations, got 3`
   (our fail-fast-leaning variant of the reference's silent skip; the run
   continues). Not marked completed → dependents dep-skip.
4. **Run**: `CombinationRunner`-style banner
   (`TASK 3/6: compare_synth_real — compare_all_pipelines.py` + slug list);
   `per_combo` tasks show a `combo i/N` sub-banner per invocation and the
   **first nonzero exit fails the whole task** (remaining combos not run).
5. All invocations exit 0 → `mark_completed`, `COMPLETED`; else `FAILED` with
   `!! TASK FAILED (exit N): <task> — dependents will be skipped`. The loop
   continues → independent branches (compare_pops side branch, llm islands)
   still execute.

**Abort**: flag + `_kill_process_tree` on the live process; current task →
FAILED (aborted), all not-yet-run tasks → ABORTED; status bar "Aborted";
`closeEvent` aborts a live runner. `task_finished` drives
`WorkflowGraphView.set_task_status`, so the graph doubles as the run report.
Node run-states are transient — never written to YAML.

Center column for a `kind: workflow` flow = `[Workflow | Options]` tabs;
clicking a node retargets the shape-dispatching `FlowOptionsPanel` onto that
task's `options` mapping (reference `task_detail_panel` behavior, editor
unchanged).

---

## Implementation Plan

### Phase 1: Dependency + scaffolding + window shell
**Goal:** A launchable window listing flows, with a reused console — no editing yet.

**Started:** 2026-07-02
**Completed:** 2026-07-02

- [x] 1.1 — Add `ruamel.yaml>=0.18` to the `[gui]` extra in `pyproject.toml`.
- [x] 1.2 — Create `gui_v2/` package (`__init__.py` files) + `menu_config.py`
      (`FlowEntry` incl. `kind` + `parse_menu_config`, kind/script fail-fast
      validation, missing-file warnings).
- [x] 1.3 — Author `config/gui/v2/menu.yaml` + placeholder flow YAMLs.
- [x] 1.4 — `main.py` (HighDPI attrs before QApplication, `sys.excepthook`, parse
      menu, show window) — port of reference launch script.
- [x] 1.5 — `widgets/flow_selector.py` (category-grouped exclusive buttons,
      `flow_changed` signal); `main_window.py` shell wiring FlowSelector + reused
      `ConsoleWidget` + Run/Abort bar (buttons inert this phase).

**Files Modified:**
- `pyproject.toml` — add ruamel to `[gui]`.
- `src/population_synthetic/gui_v2/{__init__,main,menu_config,main_window}.py` — new.
- `src/population_synthetic/gui_v2/widgets/{__init__,flow_selector}.py` — new.
- `config/gui/v2/menu.yaml`, `config/gui/v2/flows/*.yaml` — new.

**Dependencies:** None.

### Phase 2: FlowConfigModel round-trip + Save toolbar
**Goal:** Load a flow's YAML, edit programmatically, save back losslessly.

**Started:** 2026-07-02
**Completed:** 2026-07-02

- [x] 2.1 — `flow_config_model.py` (`FlowConfigModel`: ruamel round-trip, dirty,
      atomic save/save_as/reload, typed accessors, `_native_type` normalization).
- [x] 2.2 — Save (Ctrl+S) / Save As (Ctrl+Shift+S) `QToolBar`; dirty title `*`;
      confirm-discard on flow switch and on close.
- [x] 2.3 — `_load_flow(entry)` wires FlowSelector → model.

**Files Modified:**
- `src/population_synthetic/gui_v2/flow_config_model.py` — new.
- `src/population_synthetic/gui_v2/main_window.py` — toolbar + load/dirty logic.

**Dependencies:** Phase 1.

### Phase 3: FlowOptionsPanel (shape dispatch) + DAG tab
**Goal:** Center column edits options by type and shows the strategy DAG.

**Started:** 2026-07-02
**Completed:** 2026-07-02

- [x] 3.1 — `widgets/collapsible_section.py` (copied from reference).
- [x] 3.2 — `widgets/flow_options_panel.py`: shape dispatch (enum→combo,
      bool→checkbox, int/float→line edit/spin with cast-back, `None`→placeholder
      line edit, str→line edit, list/dict→raw-YAML dialog fallback); declarative
      `_OPTION_ENUMS`/`_OPTION_VISIBILITY`/optional `_OPTION_GROUPS`; emits
      `option_changed` → mark dirty.
- [x] 3.3 — Center column = `QTabWidget [Options | DAG View]`; DAG tab reuses
      `DagGraphWidget.populate(strategy_path)` where `strategy_path =
      compose_manifest(*first_checked_combo).strategy_path`. *Implementation
      note:* the reused widget parses the strategy file with `json.loads`, but
      `compose_manifest().strategy_path` is the axis strategy **YAML** itself
      (the old GUI's DAG tab silently shows "Invalid strategy file" for these);
      gui_v2 wraps the widget in a thin `_StrategyDagView` subclass that
      converts the YAML to a JSON twin in a per-user temp cache before
      delegating — the old widget stays byte-for-byte untouched.

**Files Modified:**
- `src/population_synthetic/gui_v2/widgets/{collapsible_section,flow_options_panel}.py` — new.
- `src/population_synthetic/gui_v2/main_window.py` — center tabs + DAG refresh.

**Dependencies:** Phase 2.

### Phase 4: AxisSelector (three flat checkable lists)
**Goal:** Right column selection driving combos, persisted per-flow — the same
models × strategies × countries mechanism as the current launcher.

**Started:** 2026-07-02
**Completed:** 2026-07-02

- [x] 4.1 — `widgets/axis_selector.py`: compose three reused `CheckableAxisList`
      widgets (`gui/widgets/checkable_axis_list.py`, imported unmodified)
      populated from `discover_axis_values`; `bind(model)` restores checks from
      the flow YAML `selection:` block and writes changes back (mark dirty);
      "Combos: N" label showing the cartesian-product count. **Does not touch
      `config/gui/state.json`.**
- [x] 4.2 — "Force reprocessing" checkbox shown for generate flows only, bound to
      `model.get_force()`.
- [x] 4.3 — `three_axis` and `workflow` flows both show the same selector; the
      checked combos feed per-combo invocations or `--slug` lists at run time.

**Files Modified:**
- `src/population_synthetic/gui_v2/widgets/axis_selector.py` — new.
- `src/population_synthetic/gui_v2/main_window.py` — bind selector on flow load.

**Dependencies:** Phase 3.

### Phase 5: Execution (single-script flows)
**Goal:** Run and abort `three_axis` flows end to end.

**Started:** 2026-07-02
**Completed:** 2026-07-02

- [x] 5.1 — `commands.py`: pure `build_per_combo_cmds(script, combos, options,
      force)` and `build_slugs_cmd(script, combos, options)` (bool→flag when
      true, `None`/blank→omit — same rules as `CombinationRunner`; slugs via
      `axis_slug`).
- [x] 5.2 — `_on_run`: save model; `three_axis` → build combos from checked
      axis ids; guard empty selection + >20-combo confirm (port from old
      `_run`); construct `ActionEntry` + `CombinationRunner(combos, action,
      overrides, force)` (imported from `gui.main_window`); wire
      `combo_started/line_received/cr_line_received/finished_all` to console +
      status; `runner.start()`. *Note:* `three_axis` dispatch runs through the
      reused `CombinationRunner`, which builds each per-combo command
      internally with the same translation rules as
      `commands.build_per_combo_cmds`; the pure builders are the reusable
      implementation for the Phase 6/7 workflow tasks and headless tests.
- [x] 5.3 — `_on_abort` (`runner.abort()` / `_kill_process_tree`); `closeEvent`
      cleanup + dirty confirm; Run/Abort state machine.

**Files Modified:**
- `src/population_synthetic/gui_v2/commands.py` — new.
- `src/population_synthetic/gui_v2/main_window.py` — run/abort/poll wiring.

**Dependencies:** Phase 4.

### Phase 6: Workflow engine (headless)
**Goal:** DAG parse/validate/order/gate + command building, fully unit-testable
without Qt.

**Started:** 2026-07-02
**Completed:** 2026-07-02

- [x] 6.1 — `workflow_state.py`: `WorkflowTask` dataclass + `WorkflowState`
      (mirror of reference `DagConfigHandler`,
      `src/_vendor/_vendor_pipeline_config_manager.py`): `validate()` (cycle +
      unknown-dep + missing-script + bad-dispatch + min>max fail-fast),
      `ordered_tasks()` (Kahn with authoring-order tie-break), `can_run(name)`
      = enabled ∧ deps ⊆ completed, `mark_completed(name)`, per-run
      `status: dict[str, TaskStatus]`
      (`PENDING/RUNNING/COMPLETED/FAILED/SKIPPED_DISABLED/SKIPPED_DEP/
      SKIPPED_GUARD/ABORTED`).
- [x] 6.2 — `workflow_config_model.py`: `WorkflowConfigModel(FlowConfigModel)` —
      `get_task_names/is_task_enabled/set_task_enabled/get_task_force/
      set_task_force/get_task_options/set_task_option/get_task_dependencies/
      get_task_meta` (ruamel round-trip), `to_plain()` snapshot for
      `WorkflowState`.
- [x] 6.3 — Author `config/gui/v2/flows/analysis_workflow.yaml` (schema above);
      add the workflow entry to `menu.yaml`. *(Both authored in Phase 1;
      verified against the schema in this phase — no drift.)*
- [x] 6.4 — Extend `commands.py` if any per-task quirk emerges (target: none —
      workflow tasks reuse the Phase-5 builders unchanged). *(None emerged —
      builders unchanged.)*

**Files Modified:**
- `src/population_synthetic/gui_v2/{workflow_state,workflow_config_model}.py` — new.
- `config/gui/v2/flows/analysis_workflow.yaml`, `config/gui/v2/menu.yaml` — new/extended.

**Dependencies:** Phase 2 (FlowConfigModel); parallel to Phases 3–5.

### Phase 7: Workflow graph panel + runner wiring
**Goal:** Run the whole enabled Analysis chain from one button, with live node
states.

**Started:** 2026-07-02
**Completed:** 2026-07-02

- [x] 7.1 — Port reference `dag_graph_items.py`/`dag_graph_view.py` →
      `widgets/workflow_graph_items.py`/`workflow_graph_view.py` (Enabled
      checkbox always, Force iff `supports_force`; grandalf Sugiyama per
      connected component; `.layout.json` sidecar next to the flow YAML;
      disabled = gray @ 0.55 opacity). Checkbox toggles write through
      `WorkflowConfigModel` → dirty `*`.
- [x] 7.2 — Run-state overlay: `TaskStatus` colors + `set_task_status(name,
      status)` repaint (pending/running/completed/failed/skipped/aborted).
- [x] 7.3 — `workflow_runner.py`: `WorkflowRunner(QThread)` per the execution
      semantics above. Factored as a Qt-free `execute_workflow(state, combos,
      run_cmd, emit, is_aborted)` core (injected `run_cmd(cmd)->int` and
      `emit(event)`) that the `QThread` drives — signals `task_started`,
      `task_finished(name, status)`, `line_received`, `cr_line_received`,
      `finished_all(aborted)`; the thread's `run_cmd` streams a `Popen` (byte
      read → CR progress), abort via lazily-imported `_kill_process_tree`.
- [x] 7.4 — `main_window.py`: `kind: workflow` branch — center
      `[Workflow | Options]` tabs in a `QStackedWidget` (script flows keep
      `[Options | DAG View]`), node click retargets the options panel onto
      that task via a `_TaskOptionsAdapter`, Run/Abort wiring, status-bar task
      progress, `closeEvent` abort.

**Files Modified:**
- `src/population_synthetic/gui_v2/workflow_runner.py` — new.
- `src/population_synthetic/gui_v2/widgets/{workflow_graph_items,workflow_graph_view}.py` — new.
- `src/population_synthetic/gui_v2/main_window.py` — workflow branch wiring.

**Dependencies:** Phases 3, 5, 6.

### Phase 8: Polish
**Goal:** Rough edges and nicer editing.

**Started:** 2026-07-02
**Completed:** 2026-07-02

- [x] 8.1 — Grouped options via `CollapsibleSection` where a flow declares groups.
      *(Already satisfied in Phase 3: `flow_options_panel._insert_grouped`
      renders declared groups inside `CollapsibleSection` blocks, ungrouped
      options render flat, with fail-fast if `_OPTION_GROUPS` is declared but an
      option is unclassified. `_OPTION_GROUPS` is intentionally left empty — the
      shipped flows declare no groups, so shipped UX is unchanged; verified.)*
- [x] 8.2 — Minimal raw-YAML fallback dialog for list/dict options.
      *(Already satisfied in Phase 3: `_RawYamlDialog` — ruamel round-trip,
      fail-fast `QMessageBox.critical` on `YAMLError` keeping the dialog open,
      round-trips list/dict values back into the model via `set_option`;
      verified.)*
- [ ] 8.3 — Remove dead `gui/widgets/action_selector.py` **only if** confirmed
      unused. *(Deferred — out of scope: belongs to the old `gui/` package,
      which must stay byte-for-byte untouched.)*

**Dependencies:** Phase 7.

---

## Testing Plan

### Unit Tests
- [ ] `parse_menu_config` — valid menu parses to `FlowEntry` list; missing
      `script`/`config` files are skipped with a warning; `kind: workflow` +
      `script` raises; `kind: script` without `script` raises.
- [ ] `FlowConfigModel` round-trip — load → `set_option`/`set_selection`/`set_force`
      → save → reload yields the mutated values; comments/key order preserved;
      `_native_type` keeps ints as ints (not `"5"`).
- [x] `WorkflowState.validate` — unknown `depends_on` raises; 2-node and
      self-loop cycles raise naming the members; missing script raises; bad
      `dispatch` raises; `min_combos > max_combos` raises.
      *(tests/test_workflow_state.py)*
- [x] `WorkflowState.ordered_tasks` — for the shipped `analysis_workflow.yaml`:
      map < compare_synth_real < model_performance; compare_pops after map;
      authoring-order tie-break deterministic across runs.
- [x] Gating — disabled task `can_run` False; dep-incomplete False; after
      `mark_completed(map_populations)`, compare_synth_real True while
      model_performance stays False; a guard-skip does not mark completed →
      dependents blocked.
- [x] `build_per_combo_cmds` — N combos → N vectors `[py, script, --model-id, m,
      --strategy-id, s, --country-id, c, (--force)]`; bool-false/None/blank
      options omitted. *(tests/test_workflow_commands.py)*
- [x] `build_slugs_cmd` — one vector with one `--slug
      {country}_{strategy}_{model}` per combo (via `axis_slug`) + flag/value
      options.
- [x] `WorkflowConfigModel` — `set_task_enabled/set_task_force/set_task_option`
      → save → reload preserves comments/order and value types.

### Integration Tests
- [ ] `three_axis` dispatch — checked axis ids produce the expected
      `--model-id/--strategy-id/--country-id (+ overrides, + --force)` command
      list (assert the arg vector `CombinationRunner` would build).
- [x] Simulated workflow run (injected `run_cmd` exit codes) — map fails ⇒
      compare_synth_real + model_performance end `SKIPPED_DEP` while an enabled
      llm island still runs; compare_pops with 3 combos ⇒ `SKIPPED_GUARD` and
      the loud warning line is present in the emitted output.
      *(tests/test_workflow_runner.py — tests the Qt-free `execute_workflow`
      core with injected `run_cmd`/`emit`, cleaner than monkeypatching `Popen`;
      also covers the happy path in order + abort marking ABORTED.)*

### Manual Verification
- [ ] Old GUI regression: `python -m population_synthetic.gui.main` unchanged.
- [ ] Launch gui_v2; flows grouped by category; pick a generate flow; edit `n`;
      title shows `*`; Ctrl+S; reopen YAML → value changed, comments preserved.
- [ ] Check axis ids in the three lists → "Combos: N" updates; Save →
      `selection:` block written flow-style.
- [ ] Run a cheap combo (n=1 on an offline ollama model) → console streams; banner
      `RUN 1/1: model × strategy × country`.
- [ ] Analysis Workflow happy path over 2 cheap combos: map → compare →
      performance banners in order; all three nodes end green.
- [ ] Abort mid-map → no orphaned `claude`/`ollama` processes; current node red,
      remaining nodes ABORTED; status "Aborted".
- [ ] Drag workflow nodes; restart GUI → layout restored from
      `analysis_workflow.layout.json`.

### Edge Cases
- [ ] Empty selection on a `three_axis` or workflow flow → warning, no run.
- [ ] >20 combos → confirmation dialog.
- [ ] Flow YAML with a `None`/`~` option → renders as "(default)" and round-trips.
- [ ] Close window with unsaved edits → discard confirmation.
- [ ] Workflow YAML with a cycle / unknown dep → flow fails to load with a clear
      error message in the console (fail-fast).
- [ ] compare_pops enabled with 1 or 3 checked combos → loud skip, run continues.

---

## Documentation Plan

- [x] Update `CLAUDE.md` Quick Start / Commands to mention
      `python -m population_synthetic.gui_v2.main` (note the old GUI remains).
      *(Added a line in the Quick Start bash block next to the old GUI line.)*
- [x] Add a short section to `docs/architecture/` (or a new
      `docs/development/gui-v2.md`) describing the two-tier config, the
      "GUI translates flow YAML → CLI" execution contract, and the workflow
      contract (GUI-side chaining, loud-skip guards, exit-code-0 completion).
      *(New `docs/development/gui-v2.md`; pointer row added to the CLAUDE.md
      Documentation table.)*
- [x] Inline comment in `main_window._on_run` and `workflow_runner.py` stating
      scripts do NOT read the flow YAML. *(Verified present — also in
      `commands.py`, `flow_config_model.py`, `workflow_config_model.py`,
      `workflow_state.py`, and the workflow branch of `_on_run`.)*

---

## Rollback Plan

1. **Before merge:** gui_v2 is additive; the old GUI is untouched, so reverting is
   deleting `src/population_synthetic/gui_v2/`, `config/gui/v2/`, and the
   `ruamel.yaml` line in `pyproject.toml`.
2. **Data considerations:** No migrations. gui_v2 never reads/writes
   `config/gui/state.json` or `launcher.yaml`. Flow YAMLs under `config/gui/v2/`
   are self-contained; workflow node run-states are never persisted.
3. **Rollback procedure:** `git revert` the feature merge (or delete the branch
   before merge). No state reset required.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Importing `CombinationRunner`/`_kill_process_tree` couples v2 to old `gui.main_window` | Med | Low | Import-time is side-effect free; if old GUI is later removed, extract the ~70-line runner into `gui_v2/execution.py` |
| ruamel `ScalarInt/Float` re-serialized as strings after line-edit | Med | Med | Normalize via `_native_type` before `set_option` (copy reference helper) |
| Dash-form option keys diverge from actual script flags | Med | High | Keep keys == CLI flags; document at top of each flow YAML; nicer labels go in `_OPTION_LABELS`, never the YAML key |
| Dev later assumes scripts read the flow YAML | Low | Med | Explicit code comment + doc note that Save is persistence only |
| New `ruamel.yaml` dependency | Low | Low | Proven reference choice; pin `>=0.18` |
| Two similar DAG-item widgets in the repo (old `gui/widgets/dag_graph_items.py` category nodes vs new workflow nodes) | Med | Low | Workflow items live only in gui_v2; consolidation deferred until the old GUI is retired |
| Base branch is a feature branch (`feature/model-performance-comparison`), not `main` | Med | Med | Intentional: the workflow references `compare_model_performance.py`, which only exists on that branch; merge order is enforced by `/plan-finish` cascade |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 (scaffold + shell) | ~0.5 day | None |
| Phase 2 (config model + save) | ~0.5 day | Phase 1 |
| Phase 3 (options + DAG tab) | ~1 day | Phase 2 |
| Phase 4 (axis selector) | ~0.5 day | Phase 3 |
| Phase 5 (execution) | ~0.5 day | Phase 4 |
| Phase 6 (workflow engine) | ~0.5 day | Phase 2 (parallel to 3–5) |
| Phase 7 (workflow panel + runner) | ~1 day | Phases 3, 5, 6 |
| Phase 8 (polish) | ~0.5 day | Phase 7 |

---

## References

- Draft/scratch plans: `C:\Users\basil\.claude\plans\analyse-how-the-gui-luminous-grove.md`,
  `C:\Users\basil\.claude\plans\analyse-how-the-project-purring-canyon.md` (workflow amendment)
- Reference GUI: `F:\GitHub\touch_projects\social-touch-semi-controlled-analysis`
  (`src/utils/gui/analysis_runner_gui/`, `src/utils/pipeline/dag_config_model.py`,
  `src/_vendor/_vendor_pipeline_config_manager.py` `DagConfigHandler`,
  `src/_vendor/_vendor_task_executor.py`, `src/analysis/pipeline/stage_runner.py`,
  `configs/analyse_workflow_processing_dag.yaml`)
- Current GUI: `src/population_synthetic/gui/` (reuse `console_widget`,
  `checkable_axis_list`, `dag_graph_widget`, `CombinationRunner`,
  `_kill_process_tree`)
- Axis composition: `src/population_synthetic/generators/synthetic/manifest_loader.py`

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- CLAUDE.md
- config/gui/v2/flows/analysis_workflow.yaml
- config/gui/v2/flows/compare_scb.yaml
- config/gui/v2/flows/generate_parallel.yaml
- config/gui/v2/menu.yaml
- docs/development/gui-v2.md
- docs/development/plans/active/gui-v2-flow-runner.md
- pyproject.toml
- src/population_synthetic/gui_v2/__init__.py
- src/population_synthetic/gui_v2/commands.py
- src/population_synthetic/gui_v2/flow_config_model.py
- src/population_synthetic/gui_v2/main.py
- src/population_synthetic/gui_v2/main_window.py
- src/population_synthetic/gui_v2/menu_config.py
- src/population_synthetic/gui_v2/widgets/__init__.py
- src/population_synthetic/gui_v2/widgets/axis_selector.py
- src/population_synthetic/gui_v2/widgets/collapsible_section.py
- src/population_synthetic/gui_v2/widgets/flow_options_panel.py
- src/population_synthetic/gui_v2/widgets/flow_selector.py
- src/population_synthetic/gui_v2/widgets/workflow_graph_items.py
- src/population_synthetic/gui_v2/widgets/workflow_graph_view.py
- src/population_synthetic/gui_v2/workflow_config_model.py
- src/population_synthetic/gui_v2/workflow_runner.py
- src/population_synthetic/gui_v2/workflow_state.py
- tests/test_workflow_commands.py
- tests/test_workflow_runner.py
- tests/test_workflow_state.py

---
