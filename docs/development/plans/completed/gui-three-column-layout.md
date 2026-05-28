# Plan: GUI Three-Column Layout Restructuring

**Date:** 2026-05-22
**Author:** Basil
**Status:** Completed
**Completed:** 2026-05-28 07:28
**Base Branch:** `feature/composable-experiment-config`
**Branch:** `feature/gui-three-column-layout`

---

## Overview

Restructure the PyQt5 GUI from a two-panel layout (sidebar + tabs) into a three-column layout that separates task selection, configuration, and visualization into distinct vertical columns. This enables clearer workflow, better scalability for new actions and parameters, and a more logical information architecture.

## Problem Statement

The current GUI packs experiment axes, action radio buttons, dynamic parameters, and Run/Abort buttons into a single 280px left sidebar. As more actions and configuration options are added, the sidebar becomes cramped and conflates "what to do" with "how to configure it." The experiment axes are always visible even for actions that don't use them (like SCB/SSB population generation), and there's no visual grouping of related actions.

## Goals

### In Scope
1. Three-column layout: task selector (left), configuration (middle), visualization (right)
2. Group actions into "Generate Population" and "Compare Population" sections
3. Rename actions to reflect their purpose (e.g., "Generate N Identities" -> "LLM Synthetic Population")
4. Merge SCB and SSB population generation into a single "Database Population" action with a source selector
5. Conditionally show experiment axes only for LLM-based actions
6. Move all parameters to the middle column
7. Rename "Experiment" and "Axes" to "Generation Settings" / "Model Selection"

### Out of Scope
- Adding new actions or scripts beyond the existing six (+ extract)
- Comparison-specific parameter panels (future extension, not this plan)
- Theming, styling, or visual polish beyond basic layout
- Changes to the DAG View or Overview widget internals
- Changes to the console widget

## Success Criteria

- [ ] GUI launches with three distinct vertical columns
- [ ] Left column shows actions grouped under "Generate Population" and "Compare Population" headers
- [ ] Middle column shows "Generation Settings" (Model/Strategy/Country) only when an LLM action is selected
- [ ] Middle column shows task-specific parameters for all actions
- [ ] Right column (Overview + DAG View) takes the majority of the window width
- [ ] All six actions execute correctly via Run button
- [ ] SCB and SSB population generation work via a single "Database Population" action with source dropdown
- [ ] Window resize distributes space proportionally (right column stretches most)

---

## Technical Design

### Approach

Introduce two new composite widgets (`TaskSelector`, `ConfigurationPanel`) that wrap and reorganize existing widgets rather than rewriting them. The existing `ExperimentSelector` and `ParameterPanel` are composed inside `ConfigurationPanel`; `ActionSelector` is replaced by `TaskSelector`. The `main_window.py` layout switches from a two-widget `QSplitter` to a three-widget `QSplitter`.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Compose existing widgets in new containers | Minimal rewrite, preserves tested widget logic | Adds wrapper layer | Chosen |
| Rewrite all widgets from scratch | Clean slate, optimal layout code | High risk, duplicates tested logic | Rejected |
| Use QDockWidget for floating panels | User-resizable, detachable | Overly complex for fixed 3-column layout, unfamiliar UX | Rejected |

### Architecture Changes

```
main_window.py
  QSplitter(Horizontal)
  ├── TaskSelector (NEW, ~200px fixed)
  │     └── Grouped radio buttons + Run/Abort
  ├── ConfigurationPanel (NEW, stretch=1)
  │     ├── ExperimentSelector (existing, conditionally visible)
  │     └── ParameterPanel (existing)
  └── QTabWidget (existing, stretch=3)
        ├── ManifestOverview (existing)
        └── DagGraphWidget (existing)
```

Key integration points:
- `TaskSelector` emits `action_changed` (same signal contract as current `ActionSelector`)
- `ConfigurationPanel` re-emits `manifest_changed` from its internal `ExperimentSelector`
- `ConfigurationPanel.update_for_action()` toggles experiment selector visibility and repopulates parameters
- `LauncherConfig` dataclass replaces the raw `list[ActionEntry]` passed to the window

---

## Implementation Plan

### Phase 1: Data Layer
**Started:** 2026-05-22
**Completed:** 2026-05-22
**Goal:** Update config format and data model to support action groups and choice parameters without changing any UI code.

- [x] Task 1.1 — Update `gui_launcher.yaml`: add `groups` list, add `group` field to actions, rename labels, merge `gen_scb_pop` + `gen_ssb_pop` into `gen_db_pop` with `source` choice parameter, add `extract_pop` action
- [x] Task 1.2 — Update `launcher_config.py`: add `ActionGroup` dataclass, add `LauncherConfig` container dataclass with `actions_by_group()`, add `group` field to `ActionEntry`, add `choices` field to `ActionParameter`, update `parse_launcher_config` return type
- [x] Task 1.3 — Create `scripts/generate_db_population.py`: thin dispatcher that accepts `--source`, `--n`, `--seed`, `--output` and delegates to the correct existing script

**Files Modified:**
- `config/gui_launcher.yaml` — restructure with groups, renames, merged SCB/SSB
- `src/population_synth/gui/launcher_config.py` — new dataclasses, updated parser
- `scripts/generate_db_population.py` — new dispatcher script

**Dependencies:** None

### Phase 2: New Widgets
**Started:** 2026-05-22
**Completed:** 2026-05-22
**Goal:** Create the two new composite widgets that will form the left and middle columns.

- [x] Task 2.1 — Create `task_selector.py`: `TaskSelector` widget with grouped radio buttons under section headers (`QLabel` per group), single exclusive `QButtonGroup`, Run/Abort buttons at bottom. Signals: `action_changed`, `run_clicked`, `abort_clicked`
- [x] Task 2.2 — Create `configuration_panel.py`: `ConfigurationPanel` that composes `ExperimentSelector` and `ParameterPanel`. Exposes `update_for_action(action)` (toggles experiment selector visibility), `current_manifest()`, `get_overrides()`, `force` property, and re-emits `manifest_changed`
- [x] Task 2.3 — Add `choice` parameter type to `parameter_panel.py`: `QComboBox` in `_build_widget`, handle in `get_overrides`

**Files Modified:**
- `src/population_synth/gui/widgets/task_selector.py` — new file
- `src/population_synth/gui/widgets/configuration_panel.py` — new file
- `src/population_synth/gui/widgets/parameter_panel.py` — add QComboBox for choice type

**Dependencies:** Phase 1

### Phase 3: Layout Restructure
**Started:** 2026-05-22
**Completed:** 2026-05-22
**Goal:** Rewire the main window to use the three-column layout with the new widgets.

- [x] Task 3.1 — Rename labels in `manifest_selector.py`: remove "Experiment" `QLabel`, rename "Axes" `QGroupBox` to "Model Selection"
- [x] Task 3.2 — Rewrite `main_window.py` constructor: three-panel `QSplitter` with `TaskSelector` (fixed ~200px), `ConfigurationPanel` (stretch=1), right tabs (stretch=3). Update constructor to accept `LauncherConfig`
- [x] Task 3.3 — Rewire signals in `main_window.py`: connect `TaskSelector` signals, connect `ConfigurationPanel.manifest_changed`, update `_on_action_changed` to delegate to `ConfigurationPanel.update_for_action()`, update `_run` and `_build_command` to access manifest/overrides/force via `ConfigurationPanel`
- [x] Task 3.4 — Update `main.py` entry point: pass `LauncherConfig` to `LauncherWindow`, widen default window to `1300x750`

**Files Modified:**
- `src/population_synth/gui/widgets/manifest_selector.py` — two string renames
- `src/population_synth/gui/main_window.py` — layout rewrite, signal rewiring, updated constructor
- `src/population_synth/gui/main.py` — updated constructor call, wider window

**Dependencies:** Phase 2

### Phase 4: Verification
**Goal:** Test all actions end-to-end in the new layout.

- [ ] Task 4.1 — Launch GUI, verify three-column layout renders with correct proportions
- [ ] Task 4.2 — Click each LLM action: confirm Generation Settings visible, parameters populate, Overview/DAG update
- [ ] Task 4.3 — Click Database Population: confirm Generation Settings hidden, source dropdown + n/seed/output visible
- [ ] Task 4.4 — Click each Compare action: confirm Generation Settings shown/hidden correctly, parameters populate
- [ ] Task 4.5 — Run at least one action, verify subprocess command is correct in console output
- [ ] Task 4.6 — Test Abort, test window resize behavior

**Dependencies:** Phase 3

---

## Testing Plan

### Manual Verification
- [ ] GUI launches without errors
- [ ] Three columns render at correct proportions (left narrow, middle medium, right wide)
- [ ] Selecting LLM Synthetic Population shows Generation Settings + n/workers parameters
- [ ] Selecting LLM Single Identity shows Generation Settings, no extra parameters
- [ ] Selecting Database Population hides Generation Settings, shows source/n/seed/output
- [ ] Selecting Pipeline vs Reference shows Generation Settings, no extra parameters
- [ ] Selecting Two Populations hides Generation Settings, shows pop_a/pop_b/output
- [ ] Selecting Extract Population hides Generation Settings, shows seed-root/output (or minimal params)
- [ ] Changing Model/Strategy/Country updates Overview and DAG View
- [ ] Run button builds correct subprocess command for each action type
- [ ] Abort button terminates running process
- [ ] Window resize: right column takes most of the extra space

### Edge Cases
- [ ] No axis values available (empty dropdowns) — LLM actions should still be selectable, Run warns about missing manifest
- [ ] Rapid switching between LLM and non-LLM actions — no layout glitches
- [ ] Very small window size — columns don't overlap or crash

---

## Documentation Plan

- [ ] Update CLAUDE.md Architecture section to mention the three-column GUI layout
- [ ] Update any GUI-related docs in `docs/development/` if they reference the old sidebar layout

---

## Rollback Plan

1. All changes are on a feature branch — revert by not merging
2. The existing `action_selector.py` is not deleted, only un-imported — can be restored by reverting `main_window.py`
3. The existing `gui_launcher.yaml` format is backward-compatible if the new `groups` key is ignored
4. No database or data changes — purely UI restructuring

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Layout jumps when toggling experiment selector visibility | Medium | Low | Use `setVisible()` not add/remove; stretch spacer absorbs space |
| `_build_command` breaks for merged SCB/SSB action | Low | Medium | Dispatcher script isolates routing logic from GUI |
| Signal disconnect when widgets move between containers | Low | High | Compose (not move) existing widgets; same signal API |
| Window too wide for small screens at 1300px default | Low | Low | QSplitter allows manual resize; columns have sensible minimums |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1: Data Layer | Small | None |
| Phase 2: New Widgets | Medium | Phase 1 |
| Phase 3: Layout Restructure | Medium | Phase 2 |
| Phase 4: Verification | Small | Phase 3 |

---

## References

- Active plan: `docs/development/plans/active/composable-experiment-config.md` (Phase 3 built the current GUI)
- Completed plan: `docs/development/plans/completed/gui-pipeline-launcher.md` (original GUI design)
