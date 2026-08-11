# Plan: GUI Workflow "Bypass" Flag

**Date:** 2026-08-11
**Author:** Basil
**Status:** In Progress
**Base Branch:** `dev`
**Branch:** `feature/gui-workflow-bypass-flag`

> Base-branch note: the working branch at authoring time was
> `feature/severity-driver-attribution`, which is unrelated to this change. Per the
> standing rule (branch from `dev`, never from `main`, never stack on an unrelated
> in-progress feature), this plan is rooted at `dev`.

---

## Overview

Add a third per-node checkbox — **Bypass** — to the analysis-workflow DAG nodes in the
Flow Runner GUI, beside the existing **Enabled** and **Force**. A bypassed task is **not
executed** but is nevertheless entered into `WorkflowState.completed_tasks`, so its
dependents unlock and run. It is a user assertion that the task's outputs already exist
on disk; the GUI performs **no verification of any kind**.

## Problem Statement

The workflow DAG has exactly one "do not run this" control today: `enabled: false`. In
`execute_workflow` (`src/population_synthetic/gui/workflow_runner.py:188-193`) a disabled
task lands in `SKIPPED_DISABLED` and is never passed to `mark_completed`, so every
dependent falls through the dependency gate
(`workflow_runner.py:196-201`, `workflow_state.py:200-203`) into `SKIPPED_DEP`.

The consequence: there is no way to re-run only a **downstream** slice of the DAG. To
re-run `realism_ranking` alone, the user must also re-run its whole upstream chain
(`validate_raw → mapping → validate_mapped → population_cap → persona_realism`). Those
gate stages are *the* expensive ones: `validate_raw` and `validate_mapped` walk every
persona directory of every combination, `mapping` re-maps the full raw pool, and
`population_cap` re-copies the capped mirror. On a 50-combination sweep this is tens of
minutes of pure I/O spent re-deriving a result the user already knows is on disk and
current.

The workaround in use — disable the upstream tasks and accept that everything downstream
dep-skips, then hand-run the one script from the CLI — defeats the point of the GUI
workflow and bypasses its combo guards and option translation.

## Goals

### In Scope

1. A persisted per-task `bypass` boolean in `config/gui/flows/analysis_workflow.yaml`,
   editable from a third node checkbox in the workflow graph.
2. A new terminal run state `TaskStatus.BYPASSED` that **counts as completed** for
   dependency gating while remaining visually and textually distinct from `COMPLETED`.
3. Ladder placement: Bypass is evaluated **before** the dependency gate and **before**
   the combo-count guard, but **after** the Enabled master switch.
4. A modal pre-run confirmation (OK / Cancel) listing every task that will be bypassed,
   plus a loud console banner emitted by the Qt-free execution core.
5. Headless test coverage of the new gating and ladder ordering.

### Out of Scope

- **Any verification** that a bypassed task's outputs exist (no directory `stat`, no file
  read, no freshness check). Explicitly rejected — see Alternatives Considered.
- A right-click **"Bypass all upstream"** convenience action on a node. Desirable, but a
  separate UX increment; this plan only lands the per-node primitive.
- Bypass for the `script`-kind flows (`config/gui/flows/generate_parallel.yaml` and
  siblings). Those use the `actions:` schema and have no DAG, no dependency gate, and
  therefore nothing to unlock.
- Any change to the backing analysis scripts, the analysis registry, or the CLI. Bypass
  is purely GUI-side orchestration and emits **no** CLI flag.
- Persisting run statuses. Node run-state stays transient, as today.

## Success Criteria

- [ ] Each of the 15 tasks in `analysis_workflow.yaml` carries `bypass: false`, and the
      key round-trips through `WorkflowConfigModel` save with comments intact.
- [ ] Ticking **Bypass** on `population_cap` and running with only `fidelity` also
      enabled results in: zero `population_cap` subprocesses, `population_cap` shown
      `BYPASSED`, and `fidelity` actually executing.
- [ ] A task that is `enabled: false` and `bypass: true` yields `SKIPPED_DISABLED` and its
      dependents still `SKIPPED_DEP` — Bypass is inert on a disabled task.
- [ ] A bypassed task whose upstream **failed** this run still reports `BYPASSED`, and its
      own dependents run.
- [ ] A bypassed task violating its `min_combos` / `max_combos` guard still reports
      `BYPASSED` (no `!! SKIP` banner).
- [ ] Pressing Run with ≥1 enabled+bypassed task shows a modal listing them; **Cancel**
      starts no run at all; **OK** proceeds.
- [ ] The console records a bypass block for every bypassed task.
- [ ] The Bypass checkbox is greyed (not cleared) whenever Enabled is unticked.
- [ ] Node text is not clipped with three checkboxes on the narrowest node.
- [ ] `pytest tests/test_workflow_state.py tests/test_workflow_runner.py` passes;
      `ruff check src/` clean.

## Definitions

- **Bypassed**: the task performed **zero** subprocess invocations this run *and* its name
  is in `WorkflowState.completed_tasks` *and* `state.status[name] is TaskStatus.BYPASSED`.
  All three conditions, testable directly.
- **Counts as completed**: membership of `completed_tasks` only — the set `can_run()`
  tests against (`workflow_state.py:203`). It does **not** mean `TaskStatus.COMPLETED`;
  the two statuses stay distinct in the console, the graph, and the status dict.
- **Inert**: the `bypass` value is read, found irrelevant, and neither acted on nor
  mutated. A disabled task's persisted `bypass: true` survives untouched on disk.
- **No verification**: the implementation must contain no filesystem access whatsoever on
  the bypass path — no `Path.exists()`, `is_dir()`, `stat()`, `glob()`, or read. This is a
  reviewable, greppable property of the diff, not an aspiration.
- **Loud**: rendered with the 60-char `_BANNER_RULE` separator, in the same register as
  the existing `!! SKIP` guard banner (`workflow_runner.py:207`).

---

## Technical Design

### Approach

Bypass reuses the existing gating mechanism rather than adding a parallel one. The
dependency gate is set membership in `completed_tasks`; the minimal correct change is a
second write path into that set (`mark_bypassed`) that records a different status. No
second bookkeeping structure, no change to `can_run`, `ordered_tasks`, or `validate`.

The per-task ladder in `execute_workflow` gains one branch. Final order:

| # | Condition | Status | Enters `completed_tasks`? |
|---|-----------|--------|---------------------------|
| 0 | run aborted | `ABORTED` | no |
| 1 | `not task.enabled` | `SKIPPED_DISABLED` | no |
| 2 | **`task.bypass`** | **`BYPASSED`** | **yes** |
| 3 | dependency unmet | `SKIPPED_DEP` | no |
| 4 | combo guard violated | `SKIPPED_GUARD` | no |
| 5 | executed, exit 0 / nonzero | `COMPLETED` / `FAILED` | yes / no |

Rows 1 and 2 encode the two agreed decisions: Enabled remains the master switch (1 before
2), and a bypass is an assertion about the **disk**, not about this run, so it is immune
to what happened upstream and to the combo guard (2 before 3 and 4).

Splitting the responsibilities keeps the core headlessly testable: the **Qt-free core**
owns the console banner and the state transition; **`main_window`** owns the modal, which
is pure Qt and cannot live in the core.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| `bypass` flag + `mark_bypassed` into `completed_tasks` | Reuses the single existing gate; ~1 branch in the ladder; distinct status preserved | Adds a third checkbox to already-busy nodes | **Chosen** |
| Reuse `TaskStatus.COMPLETED` for bypassed tasks | Zero new status, no overlay/colour work | Destroys the audit trail — the run report would claim work happened that did not; indistinguishable in console and graph | Rejected |
| A "start from this node" run mode (pick an entry point, everything upstream implicitly assumed) | One control instead of N checkboxes; no per-task persisted state to go stale | Cannot express a non-contiguous assumption (e.g. bypass `mapping` but still run `validate_mapped`); needs reverse-reachability UI; a much larger change | Rejected for now; the per-node primitive composes into it later |
| Transient (session-only) bypass, never written to YAML | A stale bypass cannot survive into a later session | Inconsistent with `enabled`/`force`, which both persist; a multi-day sweep would have to re-tick every run; the round-trip model exists precisely to persist node state | Rejected (decision 3) |
| Bypass gated by a `supports_bypass:` key, mirroring `supports_force` | Symmetric with Force | `supports_force` exists because `--force` is a *script* capability; bypass is a GUI orchestration concept that applies uniformly to every task. A gate would be config with no possible `false` value | Rejected — no gate key |
| Cheap `03_Analysis/{id}/` existence check before honouring a bypass | Turns a silent stale-output run into a loud skip for microseconds | User decision 4 is explicit: zero-check. The dispatch granularity (per-combo / per-country / slugs) also means a bare directory says nothing about *which* combos are present, so the check would be reassurance without a guarantee — the worst kind | Rejected (decision 4) |

### Architecture & Module Contracts

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `analysis_workflow.yaml` | Declare `bypass: false` per task | — | Any script, any CLI flag |
| `WorkflowConfigModel` | Round-trip read/write of the `bypass` key | task name → bool; (name, bool) → mutated ruamel tree + dirty flag | Run semantics; what bypass *means* |
| `WorkflowState` / `WorkflowTask` | Parse `bypass`; own `mark_bypassed` and the `BYPASSED` status | plain snapshot → typed DAG; `mark_bypassed(name)` → `completed_tasks` ∪ {name}, status `BYPASSED` | Qt; the filesystem; the console format |
| `execute_workflow` (core) | Ladder branch #2 + the loud console banner + the run-opening bypass summary | state, combos, callables → emitted events, mutated state | Qt; `QMessageBox`; subprocesses (already injected) |
| `WorkflowTaskNode` | Render + emit the third checkbox; grey it when Enabled is off; paint the `BYPASSED` overlay | model reads → `bypass_changed(name, bool)` | The YAML file; the runner |
| `WorkflowGraphView` | Relay `bypass_changed` upward | node signal → view signal | The model |
| `main_window` | Write-back slot; pre-run modal listing bypassed tasks | signal → `set_task_bypass`; Run click → confirm/cancel | The ladder ordering |

Key signatures:

```python
# workflow_state.py
class TaskStatus(Enum):
    ...
    BYPASSED = "bypassed"          # not executed; user-asserted complete

@dataclass
class WorkflowTask:
    ...
    bypass: bool                    # no default — parsed from a required YAML key

_REQUIRED_TASK_KEYS = ("label", "script", "dispatch", "enabled", "bypass", "options", "depends_on")

class WorkflowState:
    def mark_bypassed(self, name: str) -> None:
        """Enter *name* into ``completed_tasks`` with status ``BYPASSED``.

        The task was NOT executed and NOTHING was verified — this records the
        user's assertion that its outputs already exist, so dependents unlock.
        """

# workflow_config_model.py
def get_task_bypass(self, name: str) -> bool: ...
def set_task_bypass(self, name: str, bypass: bool) -> None: ...
```

`bypass` is a **required** task key, unlike `force`. `force` is optional because it is
gated behind `supports_force` (a script capability); `bypass` has no gate, so an absent
key is a genuine config error and must raise — consistent with `enabled` and with the
project's config-is-the-single-source-of-truth invariant. This makes the test helper
`tests/test_workflow_runner.py::_task` and any hand-written snapshot fail loudly until
updated, which is the intended contract change.

`validate()` is deliberately **not** extended: `enabled: false` + `bypass: true` is a
legal, inert combination, not a config error (the GUI simply greys the box).

---

## Implementation Plan

### Phase 1: Config + engine (headless, Qt-free)
**Goal:** `bypass` exists end-to-end in the data model and the ladder; provable without a display.

- [x] 1.1 — Add `bypass: false` to all 15 tasks in `config/gui/flows/analysis_workflow.yaml`,
      each with a short trailing comment (`# assume already done -> unlock dependents, run nothing`);
      update the file's header comment (line 6) from `enabled/force` to `enabled/bypass/force`.
      *(The shipped file carries 13 tasks, not 15 — every one of them got the key.)*
- [x] 1.2 — `WorkflowConfigModel.get_task_bypass` / `set_task_bypass`, mirroring the force
      pair at `workflow_config_model.py:76-95` (raise `KeyError` on a missing key,
      `ValueError` on a non-boolean).
- [x] 1.3 — `TaskStatus.BYPASSED`; `WorkflowTask.bypass`; move `"bypass"` into
      `_REQUIRED_TASK_KEYS`; parse via the existing `_bool("bypass")` with no default.
- [x] 1.4 — `WorkflowState.mark_bypassed(name)` (adds to `completed_tasks`, sets
      `BYPASSED`); extend the `mark_completed` docstring to say bypass is the other writer.
- [x] 1.5 — Ladder branch #2 in `execute_workflow`: after the disabled check, before
      `can_run`. Emits the loud banner, `mark_bypassed`, `TaskFinished(name, BYPASSED)`,
      `continue`. No `TaskStarted` (nothing starts).
- [x] 1.6 — Run-opening summary: before the walk, if any task is `enabled and bypass`,
      emit one `ConsoleLine` naming them all.
- [x] 1.7 — Update the module docstrings that enumerate the execution semantics
      (`workflow_runner.py:15-27`, `workflow_state.py:1-18`).

**Files Modified:**
- `config/gui/flows/analysis_workflow.yaml` — 15 × `bypass: false` + header comment
- `src/population_synthetic/gui/workflow_config_model.py` — accessor pair
- `src/population_synthetic/gui/workflow_state.py` — status, field, required key, `mark_bypassed`
- `src/population_synthetic/gui/workflow_runner.py` — ladder branch, banners, docstring

**Dependencies:** None

### Phase 2: Graph node + write-back
**Goal:** the flag is reachable, visible, and persisted from the GUI.

- [x] 2.1 — Third `QCheckBox("Bypass")` in `WorkflowTaskNode`, always present (no
      `supports_` gate), initialised from `model.get_task_bypass`, emitting
      `bypass_changed(name, bool)`.
- [x] 2.2 — Node width: the current width comes from the label only
      (`workflow_graph_items.py:98`) and three checkboxes will overflow `_MIN_NODE_W`.
      After building `inner`, measure `inner.sizeHint().width()`, then
      `prepareGeometryChange()` + `self.setRect(0, 0, node_w, _NODE_H)` and resize the
      proxy to match, where
      `node_w = max(_MIN_NODE_W, label_w + _H_PADDING, inner.sizeHint().width() + 2*_INSET)`.
- [x] 2.3 — Enabled → Bypass interlock: `self._cb_bypass.setEnabled(self._enabled)` at
      construction and inside `_on_enabled_changed`. Grey only — never clear the value.
- [x] 2.4 — Bypass → Force interlock: grey Force while Bypass is checked (nothing runs, so
      Force is meaningless). Value untouched. *Reviewer note: this is the one addition
      beyond the four agreed decisions; drop it if unwanted.*
- [x] 2.5 — `_STATUS_OVERLAY[TaskStatus.BYPASSED]` — fill `#e3e0f0`, border `#5c4b99`,
      width 2.0, `dim=False`, glyph `»`. Distinct from green `COMPLETED` and amber
      `SKIPPED_*`; undimmed, because a bypassed node is *accounted for*, not skipped.
- [x] 2.6 — `bypass_changed` signal on `WorkflowGraphView` + node connection
      (`workflow_graph_view.py:56-61,148`).
- [x] 2.7 — `main_window._on_task_bypass_changed` mirroring `:572-577`
      (`set_task_bypass` + `_refresh_title`), wired at `:221`.

**Files Modified:**
- `src/population_synthetic/gui/widgets/workflow_graph_items.py` — checkbox, width, interlocks, overlay
- `src/population_synthetic/gui/widgets/workflow_graph_view.py` — signal relay
- `src/population_synthetic/gui/main_window.py` — write-back slot + connection

**Dependencies:** Phase 1

### Phase 3: Pre-run confirmation + docs
**Goal:** a bypass can never be applied silently.

- [x] 3.1 — In `main_window._run_workflow`, after `state.validate()` and before
      `reset_statuses()`: collect `[t.name for t in state.ordered_tasks() if t.enabled and t.bypass]`.
      If non-empty, `QMessageBox.warning` with `Ok | Cancel`, **default Cancel**, listing
      the task labels and stating plainly that nothing is checked and their outputs are
      assumed present. `Cancel` → `return` before any runner is constructed.
- [x] 3.2 — Disabled tasks are excluded from that list (their bypass is inert).
- [x] 3.3 — `docs/development/gui.md`: add Bypass to the orchestration-field lists
      (`:120-122`, `:142`) and insert the ladder entry into the `WorkflowRunner` bullet
      list (`:150-163`), stating the ordering and the zero-verification contract.
- [x] 3.4 — `CLAUDE.md`: extend the GUI/workflow description to name the bypass flag as a
      GUI-only orchestration concept invisible to every script.

**Files Modified:**
- `src/population_synthetic/gui/main_window.py` — pre-run modal
- `docs/development/gui.md` — contract text
- `CLAUDE.md` — one-line mention

**Dependencies:** Phase 2

---

## Testing Plan

### Unit Tests

`tests/test_workflow_state.py`:
- [x] A task snapshot missing `bypass` raises `ValueError` naming the key.
- [x] `bypass: "yes"` (non-boolean) raises.
- [x] `mark_bypassed("x")` → `"x" in completed_tasks` **and** `status["x"] is BYPASSED`.
- [x] After `mark_bypassed("map")`, `can_run("compare")` (which depends on `map`) is True.
- [x] `validate()` accepts `enabled: false` + `bypass: true` without raising.

`tests/test_workflow_runner.py` (extend `_task` with `bypass=False`):
- [x] Bypassed task: `recorder.script_calls("map.py") == 0`, status `BYPASSED`, dependent
      `compare` executed and `COMPLETED`.
- [x] Bypassed task emits **no** `TaskStarted` event.
- [x] `enabled=False, bypass=True` → `SKIPPED_DISABLED`, dependent `SKIPPED_DEP`.
- [x] Upstream `FAILED` + downstream bypassed → downstream `BYPASSED`, and the
      downstream's own dependent runs.
- [x] Bypassed task with `min_combos=2` and 1 combo checked → `BYPASSED`, and no line
      starts with `!! SKIP`.
- [x] The run-opening console summary names every enabled+bypassed task.
- [x] Abort while a bypassed task is pending → `ABORTED`, not `BYPASSED` (row 0 wins).

`tests/test_workflow_graph_items.py` (new, or a `pytest.importorskip("PyQt5")` guard in
an existing GUI test module):
- [x] Every `TaskStatus` member has an `_STATUS_OVERLAY` entry — guards the bare dict
      lookup at `workflow_graph_items.py:169` against a `KeyError` at paint time.

### Integration Tests
- [x] The real `config/gui/flows/analysis_workflow.yaml` loads into a `WorkflowState` and
      `validate()`s — i.e. all 15 tasks carry the new required key.
- [x] Round-trip: `set_task_bypass(..., True)` → save → reload → value is `True` and the
      file's comments/key order survive (the existing ruamel round-trip assertions).

### Manual Verification
- [ ] Launch `python -m population_synthetic.gui.main`, open Analysis Workflow: three
      checkboxes render on every node with no clipped text at default zoom.
- [ ] Untick Enabled on a node → Bypass greys out, its tick state unchanged; re-tick →
      it returns.
- [ ] Tick Bypass on `validate_raw`, `mapping`, `validate_mapped`, `population_cap`;
      Run → modal lists exactly those four → **Cancel** → nothing runs, no status changes.
- [ ] Same again → **OK** → the four nodes turn violet with `»` within a second, no
      subprocess for them, and `fidelity` starts immediately.
- [ ] Save, quit, relaunch → the four still show Bypass ticked.

### Edge Cases
- [ ] Every task bypassed → run completes instantly, all nodes `BYPASSED`, zero
      subprocesses, `finished_all(aborted=False)`.
- [ ] Bypass on the DAG root (`validate_raw`) — no dependencies to satisfy; must not
      special-case.
- [ ] Bypass on a leaf (`realism_ranking`) — nothing downstream; harmless no-op run.
- [ ] Bypass ticked on a task that is *also* the target of a `--force` tick → nothing
      runs; Force is inert (and greyed per 2.4).

---

## Documentation Plan

- [x] `docs/development/gui.md` — orchestration-field lists + the `WorkflowRunner` ladder,
      including the "no verification" contract and the ordering rationale.
- [x] `CLAUDE.md` — one line in the GUI/workflow paragraph: bypass is GUI-only and emits
      no CLI flag.
- [x] `config/gui/flows/analysis_workflow.yaml` — header comment + per-task inline comment.
- [x] Module docstrings in `workflow_runner.py` / `workflow_state.py` /
      `workflow_graph_items.py` (each currently enumerates "Enabled / Force").
- [x] No `docs/guides/` page and no changelog entry — this is a GUI affordance, not a
      pipeline capability.

---

## Rollback Plan

1. **Before merge:** delete the feature branch. Nothing outside it is touched.
2. **Data considerations:** none. No analysis output, no schema, no persona data is
   affected; the only on-disk change is 15 added lines in one GUI config file. A
   `bypass:` key left in the YAML against reverted code raises loudly at flow load
   (`unknown key(s) ['bypass']`) rather than mis-running — revert the YAML with the code.
3. **Rollback procedure:** revert the phase commits in reverse order (3 → 2 → 1). Phase 1
   is the only one whose revert requires the YAML revert to accompany it.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| A persisted `bypass: true` is forgotten and a later run silently reports green on stale outputs | **High** | **High** | The pre-run modal (Phase 3) is unskippable and defaults to Cancel; the console summary is permanent in the log; the node paints violet, not green |
| Three checkboxes clip or overflow the node rect | Med | Low | Task 2.2 derives width from the measured `sizeHint`, not from the label alone; manual check at default zoom |
| `_STATUS_OVERLAY` missing the new key → `KeyError` mid-paint | Med | Med | Task 2.5 plus the exhaustiveness test over `TaskStatus` members |
| Making `bypass` a required key breaks existing snapshots/tests | **High** (by design) | Low | Intended loud contract change; `_task()` helper updated in Phase 1's test pass; the real flow YAML is covered by the integration test |
| Ladder placement debated later (bypass before vs. after the dep gate) | Low | Med | Fixed by decision 2 and pinned by the "upstream FAILED → downstream BYPASSED" test, so a silent reordering fails CI |
| Scope creep into "start from this node" run mode | Med | Med | Explicitly out of scope; the per-node flag is a strict subset that composes into it later |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — config + engine | ~120 lines across 4 files + tests | None |
| Phase 2 — node + write-back | ~70 lines across 3 files | Phase 1 |
| Phase 3 — modal + docs | ~40 lines + doc edits | Phase 2 |

---

## References

- Execution ladder: `src/population_synthetic/gui/workflow_runner.py:162-230`
- Dependency gate: `src/population_synthetic/gui/workflow_state.py:200-213`
- Node checkboxes: `src/population_synthetic/gui/widgets/workflow_graph_items.py:128-152`
- Workflow contract: `docs/development/gui.md:138-167`

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- CLAUDE.md
- config/gui/flows/analysis_workflow.yaml
- docs/development/gui.md
- docs/development/plans/active/gui-workflow-bypass-flag.md
- src/population_synthetic/gui/main_window.py
- src/population_synthetic/gui/widgets/workflow_graph_items.py
- src/population_synthetic/gui/widgets/workflow_graph_view.py
- src/population_synthetic/gui/workflow_config_model.py
- src/population_synthetic/gui/workflow_runner.py
- src/population_synthetic/gui/workflow_state.py
- tests/test_real_population_stats.py
- tests/test_workflow_commands.py
- tests/test_workflow_graph_items.py
- tests/test_workflow_runner.py
- tests/test_workflow_state.py

## Implementation Notes

- The flow YAML on `dev` carries **13** tasks, not the 15 this plan assumed; `bypass: false`
  was added to all 13. The missing nodes (including `realism_ranking`) exist only on
  `feature/severity-driver-attribution`. Because `bypass` is a **required** key, merging this
  branch into any branch that adds a task node will produce a YAML that raises
  `missing required key(s) ['bypass']` at flow load — a clean text merge with a broken
  result. The merge must add `bypass: false` to each node the other branch contributed.
- The Manual Verification and Edge Case boxes remain unticked: they need a live GUI session
  and were not exercised by the automated run.
