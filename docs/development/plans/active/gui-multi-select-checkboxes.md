# Plan: GUI Multi-Select Checkboxes for Cartesian Product Runs

**Date:** 2026-06-01
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/run-analytics-preprocessor`
**Branch:** `feature/gui-multi-select-checkboxes`

---

## Overview

Replace the three single-select `QComboBox` dropdowns (Model, Strategy, Country) in the GUI launcher with multi-select checkbox lists, enabling the user to select any combination of models, strategies, and countries. The system runs the full cartesian product of checked items sequentially. The `--generate-all-strategies` flag is removed since checkbox multi-select supersedes it.

## Problem Statement

The GUI currently limits users to one model, one strategy, and one country per run. Running a matrix of experiments (e.g. 3 models x 2 strategies x 1 country) requires manually re-selecting and re-launching 6 times. The `--generate-all-strategies` flag partially addresses this for strategies only, with no per-item granularity and no multi-model support.

## Goals

### In Scope
1. Replace three `QComboBox` dropdowns with three checkbox-list widgets showing all axis values
2. Add "All" / "None" convenience buttons per axis
3. Run the cartesian product of selections sequentially with per-combination progress and console banners
4. Update the Overview tab to show a combination count summary for multi-selections
5. Remove the `generate-all-strategies` parameter from the GUI and CLI

### Out of Scope
- Parallel execution of multiple combinations (each combination already uses `--workers` internally)
- Persistent checkbox state across GUI restarts
- Drag-and-drop reordering of run queue
- Changes to the manifest composition layer (`compose_manifest`, `ManifestConfig`)

## Success Criteria

- [ ] Three checkbox lists render with all available axis values (13 models, 5 strategies, 1 country)
- [ ] "All" / "None" buttons check/uncheck all items in their axis
- [ ] Overview tab shows "N runs (X models x Y strategies x Z countries)" for multi-selections
- [ ] Overview tab falls through to single-manifest detail view for 1x1x1 selections
- [ ] Run button executes all combinations sequentially with console separator banners
- [ ] Status bar shows "Running 3/12: claude_haiku x all_pick x swedish" progress
- [ ] Abort stops after the current combination finishes
- [ ] `generate-all-strategies` parameter is absent from the parameter panel
- [ ] DAG view shows the first selected strategy (with label indicating which one)

---

## Technical Design

### Approach

The change is entirely in the GUI layer. The manifest composition infrastructure (`compose_manifest`, `ManifestDisplayInfo.from_axis`) is reused unchanged — each combination in the cartesian product calls it independently. A new `CombinationRunner(QThread)` handles sequential subprocess execution, replacing the current single-`Popen` pattern.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Checkbox lists per axis | Granular per-item control, clear visual state, replaces all-strategies flag | More vertical space needed | **Chosen** |
| Multi-select QListWidget | Built-in Qt widget, less code | Ctrl+click selection is non-obvious, poor discoverability | Rejected |
| Checkable QComboBox (custom delegate) | Compact, dropdown-style | Hidden selection state, complex to implement | Rejected |

### Architecture Changes

New widget: `CheckableAxisList` — reusable checkbox-list component with scroll area support.

New dataclass: `ExperimentSelection` — carries `model_ids`, `strategy_ids`, `country_ids` lists with a `combinations()` method returning the cartesian product.

New QThread: `CombinationRunner` — iterates combinations, spawning one subprocess per combination with stdout forwarding to the console.

Signal rename: `manifest_changed(ManifestDisplayInfo)` becomes `selection_changed(ExperimentSelection)` throughout `ExperimentSelector` -> `ConfigurationPanel` -> `LauncherWindow`.

```
ExperimentSelector                    ConfigurationPanel         LauncherWindow
┌──────────────────────┐             ┌──────────────────┐      ┌─────────────────┐
│ CheckableAxisList x3 │──signal──→  │ selection_changed │──→   │ update overview  │
│ Force checkbox       │             │ first_manifest()  │      │ update DAG       │
│ Refresh button       │             │ current_selection │      │ _run() → Runner  │
└──────────────────────┘             └──────────────────┘      └─────────────────┘
```

---

## Implementation Plan

### Phase 1: New Widget and Dataclass
**Goal:** Create the building blocks without modifying any existing files

- [x] Create `CheckableAxisList` widget with QGroupBox, scroll area, checkboxes, All/None buttons, `selection_changed` signal, `selected_ids()` / `populate()` / `set_selected()` API
- [x] Add `ExperimentSelection` dataclass to `manifest_model.py`

**Files Modified:**
- `src/population_synth/gui/widgets/checkable_axis_list.py` — New file
- `src/population_synth/gui/manifest_model.py` — Add `ExperimentSelection` dataclass

**Dependencies:** None

### Phase 2: Refactor ExperimentSelector and ConfigurationPanel
**Goal:** Replace dropdowns with checkbox lists, update signal chain

- [x] Refactor `ExperimentSelector`: replace 3 `QComboBox` with 3 `CheckableAxisList`, rename signal to `selection_changed`, replace `current_manifest()` with `current_selection()`, add `first_manifest()` convenience method
- [x] Update `ConfigurationPanel`: rename signal, update proxy methods, pass `first_manifest()` to ParameterPanel for default resolution

**Files Modified:**
- `src/population_synth/gui/widgets/manifest_selector.py` — Replace QComboBox with CheckableAxisList, new signal
- `src/population_synth/gui/widgets/configuration_panel.py` — Rename signal, update API

**Dependencies:** Phase 1

### Phase 3: Update Overview and LauncherWindow
**Goal:** Multi-selection summary in overview, sequential combination runner

- [x] Add `populate_selection(ExperimentSelection)` to `ManifestOverview` showing combination count and selected IDs per axis; fall through to detail view for 1x1x1
- [x] Create `CombinationRunner(QThread)` with sequential subprocess execution, progress signals, abort support, and console separator banners
- [x] Refactor `LauncherWindow`: connect `selection_changed`, update `_run()` to use `CombinationRunner`, update `_abort()` and `_check_process()`, add status bar progress, show confirmation dialog for >20 combinations

**Files Modified:**
- `src/population_synth/gui/widgets/manifest_overview.py` — Add multi-selection summary
- `src/population_synth/gui/main_window.py` — Add `CombinationRunner`, refactor run/abort logic

**Dependencies:** Phase 2

### Phase 4: Cleanup
**Goal:** Remove deprecated generate-all-strategies infrastructure

- [x] Remove `generate-all-strategies` parameter from `gui_launcher.yaml`
- [x] Remove `--generate-all-strategies` argparse argument and associated loop from `generate_identities_parallel.py`

**Files Modified:**
- `config/gui_launcher.yaml` — Remove parameter entry (lines 41-45)
- `scripts/generate_identities_parallel.py` — Remove flag and loop

**Dependencies:** Phase 3

---

## Testing Plan

### Manual Verification
- [ ] Launch GUI — three checkbox lists render with correct axis values
- [ ] All/None buttons toggle all checkboxes in their axis
- [ ] Checking items updates overview tab with combination count
- [ ] Single 1x1x1 selection shows full manifest detail in overview
- [ ] DAG view updates to first selected strategy
- [ ] Run with 2x2x1 selection — console shows 4 sequential runs with banners
- [ ] Abort mid-batch stops after current combination
- [ ] Status bar shows per-combination progress during run
- [ ] `generate-all-strategies` checkbox is absent from parameter panel
- [ ] Actions that don't require manifest (Database Population, Compare Two Populations) still work unchanged

### Edge Cases
- [ ] Zero selections on any axis — Run shows warning dialog
- [ ] Large selection (13x5x1 = 65 combinations) — confirmation dialog appears
- [ ] Refresh button preserves checked state where possible
- [ ] Switching between actions (e.g. generate_parallel -> gen_db_pop -> generate_parallel) preserves checkbox state

---

## Documentation Plan

- [ ] Update CLAUDE.md if GUI architecture section exists
- [ ] No user guide changes needed (internal tool)

---

## Rollback Plan

1. All changes are on a feature branch — revert by not merging
2. No data migrations or external API changes
3. The CLI interface (`--model-id`, `--strategy-id`, `--country-id`) is unchanged — only the GUI invocation layer changes

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Vertical space: 3 checkbox lists may be too tall for the middle panel | Medium | Low | Use scroll areas with max-height ~180px per list |
| Accidental large batch (65+ runs) | Medium | Medium | Confirmation dialog for >20 combinations |
| `--generate-all-strategies` removal breaks external scripts | Low | Low | Internal tool only; the flag was GUI-specific |
| Long-running batch blocks user from inspecting results | Low | Low | Each combination writes to its own directory; user can browse output during the run |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1: Widget + Dataclass | Small | None |
| Phase 2: Selector + ConfigPanel | Medium | Phase 1 |
| Phase 3: Overview + Runner | Medium | Phase 2 |
| Phase 4: Cleanup | Small | Phase 3 |

---

## References

- Approved plan sketch: `.claude/plans/analyse-the-gui-and-foamy-seal.md`
- GUI entry point: `scripts/launch_gui.py` -> `src/population_synth/gui/main.py`
- Manifest composition: `src/population_synth/identity/manifest_loader.py` (`compose_manifest`, `discover_axis_values`)

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- config/gui_launcher.yaml
- docs/development/plans/active/gui-multi-select-checkboxes.md
- scripts/generate_identities_parallel.py
- src/population_synth/gui/main_window.py
- src/population_synth/gui/manifest_model.py
- src/population_synth/gui/widgets/checkable_axis_list.py
- src/population_synth/gui/widgets/configuration_panel.py
- src/population_synth/gui/widgets/manifest_overview.py
- src/population_synth/gui/widgets/manifest_selector.py
