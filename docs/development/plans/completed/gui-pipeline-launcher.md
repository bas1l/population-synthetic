# Plan: GUI Pipeline Launcher

**Date:** 2026-05-20
**Author:** Basil
**Status:** Completed
**Completed:** 2026-05-20 18:11
**Base Branch:** `feature/compare-pipeline-manifest-support`
**Branch:** `feature/gui-pipeline-launcher`

---

## Overview

Build a PyQt5 desktop application that provides a visual interface for the project's CLI scripts: manifest selection, action dispatch (generate identity, compare with SCB, etc.), parameter overrides, live subprocess output, and an interactive category dependency DAG visualization. Adapted from the reference architecture in `docs/architecture/gui-dag-launcher-reference.md`, selectively adopting its process-separation principle and subprocess execution pattern while skipping layers that don't apply (DAG config editing, session resolution, dual model classes).

## Problem Statement

All project workflows currently require manual CLI invocation with `--manifest` flags and explicit argument construction. Users must remember script names, flag syntax, and valid parameter combinations. There is no way to browse available manifests, preview their configuration, or visualize the category dependency graph that drives persona generation. This creates friction for iterative experimentation and makes the system harder to hand off to collaborators who are less familiar with the CLI.

## Goals

### In Scope
1. Manifest browser — dropdown listing all valid manifests from `config/seed_manifests/`, with a formatted overview of the selected manifest's configuration
2. Action selector — radio buttons for each registered script (generate single, generate parallel, compare SCB, generate SCB/SSB population, compare populations)
3. Parameter panel — dynamic form fields with smart defaults from manifest, passed as CLI overrides (manifest file never modified)
4. Subprocess execution — launch scripts via `subprocess.Popen`, stream stdout to a console widget, abort button
5. Category DAG visualization — interactive QGraphicsScene rendering of the strategy file's dependency graph, color-coded by generation method
6. Action registry — declarative `gui_launcher.yaml` so adding new scripts requires zero Python changes

### Out of Scope
- Manifest editing (manifests are read-only in the GUI)
- Real-time progress tracking beyond stdout parsing
- Results parsing / embedded charts (future enhancement)
- Prefect or any external orchestrator integration
- Multi-run queuing or scheduling

## Success Criteria

- [ ] `pip install -e ".[gui]"` installs PyQt5 without breaking the core package
- [ ] `python scripts/launch_gui.py` opens the launcher window
- [ ] Manifest dropdown lists all valid manifests; invalid ones are skipped with a warning
- [ ] Selecting a manifest updates the overview panel with name, provider, model, mode, strategy, parallel settings
- [ ] Selecting "Generate Single Identity" + manifest → Run → console shows live script output
- [ ] Selecting "Generate N Identities" → parameter fields auto-fill from manifest's parallel settings; overrides are passed as CLI args
- [ ] Abort button terminates the running subprocess
- [ ] DAG View tab renders the strategy's 17-category dependency graph with method-based coloring
- [ ] All actions registered in `gui_launcher.yaml` are functional from the GUI

---

## Technical Design

### Approach

Adapted from the reference architecture's 5-layer design. The core principle is preserved: **GUI and execution engine never share a Python process.** The GUI composes a CLI command and launches it via `subprocess.Popen`. YAML manifests on disk are the interface contract.

| Reference Layer | Decision | Rationale |
|---|---|---|
| Layer 1: Launcher Config | **Adapt** → `gui_launcher.yaml` | Declarative action registry. Adding a new action = editing YAML. |
| Layer 2: DAG Config Format | **Skip** | Strategy JSON files already define the category DAG. |
| Layer 3: Dual Model Classes | **Skip** | Manifests are read-only. No `ruamel.yaml` round-trip editing needed. |
| Layer 4: GUI Shell | **Adapt** → 2-column + console layout | Reference's 3rd column (session configs) has no equivalent here. |
| Layer 5: Execution Engine | **Adopt** | `ConsoleWidget` + `ProcessOutputReader` pattern from reference Section 5.2/5.7. |

### Layout

```
+--------------------------------------------------------------------+
|  Population Synth Launcher                                          |
+--------------------------------------------------------------------+
|                    |                                                 |
|  LEFT PANEL        |  RIGHT PANEL (QTabWidget)                      |
|  (~280px fixed)    |  (stretch)                                     |
|                    |                                                 |
|  -- Manifest --    |  [Overview] [DAG View]                         |
|  [v] manifest_022  |                                                 |
|                    |  OVERVIEW TAB:                                  |
|  -- Action --      |    Name: Claude Sonnet - all_pick              |
|  (*) Generate 1    |    Provider: claude | Model: sonnet            |
|  ( ) Generate N    |    Mode: configurable                          |
|  ( ) Compare SCB   |    Strategy: all_generate_evaluate_random_pick |
|  ( ) Gen SCB Pop   |    Parallel: 100 identities, 2 workers        |
|                    |    Config: simulation_config_004_swedish...     |
|  -- Parameters --  |                                                 |
|  N: [100]          |  DAG VIEW TAB:                                  |
|  Workers: [2]      |    (interactive category dependency graph)      |
|                    |                                                 |
|  [RUN]   [ABORT]   |                                                 |
+--------------------------------------------------------------------+
|  CONSOLE (bottom, collapsible)                                      |
|  > Generating persona 12/100...                                    |
+--------------------------------------------------------------------+
|  Status: Running...                                        [Clear]  |
+--------------------------------------------------------------------+
```

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|---|---|---|---|
| PyQt5 desktop app | Matches reference, mature, full subprocess control | GUI dependency, Windows-specific testing | **Chosen** |
| Streamlit web app | Fast to prototype, no Qt dependency | No subprocess control, requires running server, poor fit for long-running tasks | Rejected |
| Textual TUI | No GUI dependency, terminal-native | Limited graph visualization, less discoverable for non-CLI users | Rejected |
| 3-column layout (from reference) | Matches reference exactly | 3rd column (session configs) has no equivalent; wastes space | Rejected — 2-column used |

| DAG Approach | Pros | Cons | Decision |
|---|---|---|---|
| QGraphicsScene (manual layout) | Interactive zoom/pan, no new deps, full control | More code (~200 lines) | **Chosen** |
| Graphviz SVG → QSvgWidget | Professional Sugiyama layout, minimal code | Requires graphviz system binary on Windows | Rejected |
| Matplotlib embed | Zero new deps | Static image, no interactivity | Rejected |

### Architecture Changes

New sub-package `src/population_synth/gui/` with 8 modules + 2 `__init__.py` files. No existing modules are modified (only `pyproject.toml` gets a new optional dependency group).

**Reused existing code (no duplication):**
- `manifest_loader.load_manifest()` and `ManifestConfig` dataclass — manifest parsing
- `identity_generator_configurable._build_dag()` logic — Kahn's algorithm for topological sort (reimplemented as a standalone utility in the DAG widget, since calling a private method from another class is inappropriate)
- `_paths.PROJECT_ROOT` — path resolution

```
src/population_synth/gui/
    __init__.py
    main.py                     # QApplication entry point
    launcher_config.py          # Parse gui_launcher.yaml -> ActionEntry
    manifest_model.py           # Thin wrapper: ManifestDisplayInfo around ManifestConfig
    main_window.py              # LauncherWindow (QMainWindow) — signal wiring
    widgets/
        __init__.py
        manifest_selector.py    # QComboBox + refresh button
        action_selector.py      # QButtonGroup of QRadioButtons
        parameter_panel.py      # Dynamic form: int->QSpinBox, bool->QCheckBox, file->browse
        manifest_overview.py    # Read-only QFormLayout summary
        console_widget.py       # QPlainTextEdit + ProcessOutputReader (QThread)
        dag_graph_widget.py     # QGraphicsScene with topological layer positioning

config/gui_launcher.yaml        # Declarative action registry
scripts/launch_gui.py           # Convenience entry point
```

---

## Implementation Plan

### Phase 1: Foundation — Config and Models
**Goal:** Action registry YAML, parser, and manifest display model.
**Started:** 2026-05-20
**Completed:** 2026-05-20

- [x] Task 1.1 — Create `config/gui_launcher.yaml` with all 6 actions (generate_one, generate_parallel, compare_scb, gen_scb, gen_ssb, compare_pops), their script paths, `requires_manifest` flags, and parameter schemas
- [x] Task 1.2 — Create `src/population_synth/gui/__init__.py` and `src/population_synth/gui/widgets/__init__.py`
- [x] Task 1.3 — Create `launcher_config.py` with `ActionParameter` and `ActionEntry` dataclasses and `parse_launcher_config()` function. Validate script paths exist; skip missing with warnings
- [x] Task 1.4 — Create `manifest_model.py` with `ManifestDisplayInfo` wrapper: `display_name`, `strategy_name` properties, `load_all(manifests_dir)` class method that scans `*.yaml` and skips invalid manifests
- [x] Task 1.5 — Add `gui = ["PyQt5>=5.15"]` optional dependency group to `pyproject.toml`

**Files Created:**
- `config/gui_launcher.yaml`
- `src/population_synth/gui/__init__.py`
- `src/population_synth/gui/widgets/__init__.py`
- `src/population_synth/gui/launcher_config.py`
- `src/population_synth/gui/manifest_model.py`

**Files Modified:**
- `pyproject.toml` — add `[gui]` optional dependency

**Dependencies:** None

### Phase 2: Core Widgets
**Goal:** All individual widgets functional in isolation.
**Started:** 2026-05-20
**Completed:** 2026-05-20

- [x] Task 2.1 — Create `manifest_selector.py`: QComboBox populated from `ManifestDisplayInfo.load_all()`, signal `manifest_changed(ManifestDisplayInfo)`, refresh button
- [x] Task 2.2 — Create `action_selector.py`: QRadioButtons from `list[ActionEntry]`, signal `action_changed(ActionEntry)`, grouped in a QGroupBox
- [x] Task 2.3 — Create `parameter_panel.py`: dynamic QFormLayout from `list[ActionParameter]`; type dispatch: `int`→QSpinBox, `bool`→QCheckBox, `str`→QLineEdit, `file`→QLineEdit+QPushButton+QFileDialog; `default_from_manifest` auto-fill; `get_overrides() -> dict` returns only non-default values
- [x] Task 2.4 — Create `manifest_overview.py`: read-only QFormLayout showing name, provider, model, mode, strategy, config path, parallel settings, generation config; updates via `populate(ManifestDisplayInfo)`
- [x] Task 2.5 — Create `console_widget.py`: QPlainTextEdit (monospace, dark bg, read-only), 10K line cap, auto-scroll toggle, ANSI stripping, carriage-return handling; `ProcessOutputReader(QThread)` with `line_received`/`cr_line_received` signals; `clear()` method

**Files Created:**
- `src/population_synth/gui/widgets/manifest_selector.py`
- `src/population_synth/gui/widgets/action_selector.py`
- `src/population_synth/gui/widgets/parameter_panel.py`
- `src/population_synth/gui/widgets/manifest_overview.py`
- `src/population_synth/gui/widgets/console_widget.py`

**Dependencies:** Phase 1

### Phase 3: Main Window and Entry Points
**Goal:** Fully functional MVP — select manifest, select action, run script, see output.
**Started:** 2026-05-20
**Completed:** 2026-05-20

- [x] Task 3.1 — Create `main_window.py` (LauncherWindow): 2-column layout via QSplitter (left fixed ~280px, right stretch), bottom console via vertical QSplitter, status bar, Run/Abort buttons
- [x] Task 3.2 — Wire signal flow: `ManifestSelector.manifest_changed` → update overview + parameters; `ActionSelector.action_changed` → update parameter panel + toggle manifest selector enabled state; `RunButton.clicked` → `_build_command()` + `subprocess.Popen` + pipe to console; `AbortButton.clicked` → `process.terminate()`
- [x] Task 3.3 — Implement `_build_command(action, manifest, overrides)`: compose `[sys.executable, script, --manifest, path, --override-key, value, ...]` argument list; handle bool flags (present/absent), int/str values, file paths
- [x] Task 3.4 — Implement process lifecycle: `QTimer(500ms)` polling for completion, status bar update on finish ("Finished (exit 0)" / "Failed (exit 1)"), Run button disable during execution, Abort button enable during execution
- [x] Task 3.5 — Create `main.py`: `QApplication`, parse `gui_launcher.yaml`, create `LauncherWindow`, `app.exec_()`
- [x] Task 3.6 — Create `scripts/launch_gui.py`: `from population_synth.gui.main import main; main()`

**Files Created:**
- `src/population_synth/gui/main_window.py`
- `src/population_synth/gui/main.py`
- `scripts/launch_gui.py`

**Dependencies:** Phase 2

### Phase 4: DAG Graph Visualization
**Goal:** Interactive category dependency graph in a "DAG View" tab.
**Started:** 2026-05-20
**Completed:** 2026-05-20

- [x] Task 4.1 — Create `dag_graph_widget.py` with `DagGraphWidget(QGraphicsView)`: loads strategy JSON, extracts `categories` dict, builds adjacency list
- [x] Task 4.2 — Implement topological sort (Kahn's algorithm) to assign each category to a depth layer; standalone function, not calling the private `_build_dag()` from `identity_generator_configurable.py`
- [x] Task 4.3 — Implement node positioning: y = layer depth * vertical spacing, x = index-within-layer * horizontal spacing, centered per layer
- [x] Task 4.4 — Implement node rendering: `QGraphicsRectItem` with rounded corners, `QGraphicsTextItem` label inside, color by method (`pick`=#d0e8ff, `generate_pick`=#d0ffd0, `generate_evaluate_pick`=#ffe0b0, `generate_evaluate_random_pick`=#ffd0d0)
- [x] Task 4.5 — Implement edge rendering: `QGraphicsLineItem` or `QGraphicsPathItem` with arrowheads from dependency to dependent
- [x] Task 4.6 — Implement interactions: scroll wheel zoom, middle-click pan (via `setDragMode`), node tooltips showing category name + method + depends_on list
- [x] Task 4.7 — Add "DAG View" tab to `main_window.py` QTabWidget; `populate(ManifestDisplayInfo)` reads strategy path and renders; shows "No strategy file" message when strategy_path is None
- [x] Task 4.8 — Implement `fit_in_view()` to auto-scale the graph to fit the widget on first load

**Files Created:**
- `src/population_synth/gui/widgets/dag_graph_widget.py`

**Files Modified:**
- `src/population_synth/gui/main_window.py` — add DAG View tab

**Dependencies:** Phase 3

---

## Testing Plan

### Manual Verification
- [ ] `pip install -e ".[gui]"` succeeds in the `popsynth` conda env
- [ ] `python scripts/launch_gui.py` opens the window without errors
- [ ] Manifest dropdown lists all valid manifests (currently ~15); template_identity_manifest.yaml is excluded or shown but marked as template
- [ ] Selecting a manifest updates the overview tab with correct field values (cross-check against the YAML file)
- [ ] Selecting "Generate Single Identity" + a Claude Haiku manifest → Run → console shows identity generation output → exit code 0 in status bar
- [ ] Selecting "Generate N Identities" with n=2, workers=1 → Run → console shows parallel generation → two persona directories created
- [ ] Selecting "Compare Pipeline vs SCB" with an existing pipeline output → Run → comparison report generated
- [ ] Abort button terminates a running generation mid-stream
- [ ] DAG View tab displays the 17-node category graph for a manifest with a strategy file
- [ ] DAG View tab shows "No strategy file" for a batch-mode manifest
- [ ] Zoom in/out with scroll wheel on DAG graph
- [ ] All 6 registered actions can be launched from the GUI

### Edge Cases
- [ ] No manifests in directory → dropdown is empty, Run button disabled
- [ ] Manifest with missing strategy file → overview shows "N/A", DAG tab shows message
- [ ] Action that doesn't require manifest (Gen SCB Pop) → manifest selector disabled, parameters still editable
- [ ] Script fails (e.g., missing API key) → console shows error, status bar shows "Failed (exit 1)"
- [ ] User closes window while subprocess is running → subprocess is terminated on close

---

## Documentation Plan

- [ ] Update `CLAUDE.md` Commands section with `python scripts/launch_gui.py` and `pip install -e ".[gui]"`
- [ ] Update `CLAUDE.md` Architecture section with `gui/` sub-package description
- [ ] Add inline docstrings to public classes and methods (one-line max)

---

## Rollback Plan

All GUI code is in a new sub-package (`src/population_synth/gui/`) with no modifications to existing modules. Rollback = delete the sub-package directory, remove the `[gui]` dependency from `pyproject.toml`, and delete `config/gui_launcher.yaml` + `scripts/launch_gui.py`.

No database, no migrations, no breaking changes to existing APIs.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| PyQt5 installation issues in conda env | Medium | Medium | Document `pip install -e ".[gui]"` as separate step; test in `popsynth` env before shipping |
| ANSI escape codes corrupt console output | Low | Low | `ProcessOutputReader` strips ANSI via regex (from reference pattern) |
| Long-running parallel generation (100+) freezes GUI | Low | High | Process separation guarantees GUI stays responsive; stdout piped via QThread |
| Strategy JSON schema changes break DAG view | Low | Medium | DAG widget validates JSON structure and shows "Invalid strategy" gracefully |
| Windows subprocess termination doesn't kill child processes | Medium | Medium | Use `process.terminate()` which sends SIGTERM equivalent on Windows; document that forceful kill may be needed for stuck processes |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|---|---|---|
| Phase 1: Foundation | 3-4 hours | None |
| Phase 2: Core Widgets | 8-10 hours | Phase 1 |
| Phase 3: Main Window + Entry Points | 4-6 hours | Phase 2 |
| Phase 4: DAG Visualization | 4-6 hours | Phase 3 |
| **Total** | **~3-4 days** | |

---

## References

- Reference architecture: `docs/architecture/gui-dag-launcher-reference.md`
- Existing manifest loader: `src/population_synth/identity/manifest_loader.py`
- Existing DAG builder: `src/population_synth/identity/identity_generator_configurable.py` (`_build_dag()`)
- Strategy files: `config/assets/identity/configurable/strategies/*.json`
- Claude Code plan analysis: `C:\Users\basil\.claude\plans\analyse-gui-dag-launcher-reference-md-ho-noble-cookie.md`
