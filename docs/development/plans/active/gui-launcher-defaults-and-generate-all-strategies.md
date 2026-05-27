# Plan: GUI Launcher — Default Workflow + Generate All Strategies

**Date:** 2026-05-27
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/italy-istat-population-generator`
**Branch:** `feature/gui-launcher-defaults-and-generate-all-strategies`

---

## Overview

Two usability improvements to the GUI launcher. First, the default selected workflow on startup is changed from "LLM Single Identity" to "LLM Synthetic Population", which is the primary day-to-day workflow. Second, a "Generate all strategies" checkbox is added to the "LLM Synthetic Population" action; when checked, the script iterates over every available strategy axis ID and runs a full generation pass for each one sequentially using the selected model and country.

## Problem Statement

The GUI currently selects "LLM Single Identity" on startup due to a hardcoded `button_index == 0` check, requiring a manual click every session to reach the most-used workflow. Additionally, benchmarking a model across all strategies requires running the GUI multiple times or writing ad-hoc shell scripts — there is no first-class way to fire all strategies in one action.

## Goals

### In Scope
1. "LLM Synthetic Population" is pre-selected when the GUI opens
2. A "Generate all strategies" bool parameter appears on the "LLM Synthetic Population" action
3. When checked, all strategies in `config/strategies/` are run sequentially; per-strategy output goes to each strategy's configured output directory

### Out of Scope
- Parallelising strategy runs against each other (sequential only)
- Extending the feature to other actions (e.g., "Generate all models")
- GUI progress indication beyond what is printed to the console

## Success Criteria

- [ ] GUI opens with "LLM Synthetic Population" pre-selected; no click required
- [ ] "Generate all strategies" checkbox is visible and unchecked by default in the action's parameter panel
- [ ] With the checkbox unchecked, Run behaves identically to before
- [ ] With the checkbox checked, clicking Run produces a banner per strategy in the console and runs each strategy sequentially to completion
- [ ] `--generate-all-strategies` can also be used directly from the CLI outside the GUI

---

## Technical Design

### Approach

**Default workflow** — thread a `default_action_id` field through `LauncherConfig` and `gui_launcher.yaml` so the `TaskSelector` widget knows which radio button to pre-select rather than always picking index 0.

**Generate all strategies** — add `--generate-all-strategies` to `generate_identities_parallel.py`. When the flag is present the script uses `discover_axis_values("strategies")` to enumerate all strategy axis IDs, then re-invokes itself as a subprocess for each strategy (without the flag). Using `stdout=sys.stdout, stderr=sys.stderr` in the subprocess call forwards each sub-run's output through the parent's stdout, which the GUI reads via PIPE — so all output appears in the console widget with no extra plumbing.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Re-invoke self as subprocess per strategy | Zero refactoring of existing generation logic; output flows to GUI automatically | Two-level subprocess tree | **Chosen** |
| Extract inner generation loop into helper + loop in-process | Single process, clean | Requires significant refactoring of tightly-coupled `main()` initialisation code | Rejected |
| GUI-level loop (LauncherWindow spawns one process per strategy) | Keeps script simple | GUI tracks only one `self._process`; multi-process management is complex | Rejected |
| New standalone script `generate_all_strategies.py` | Clean separation | Duplicates CLI arg surface; harder to keep in sync | Rejected |

### Architecture Changes

No new files. Minimal changes to four existing files:

- `config/gui_launcher.yaml` — new top-level `default_action` key; new parameter on `generate_parallel`
- `src/population_synth/gui/launcher_config.py` — new `default_action_id` field on `LauncherConfig`; parsed in `parse_launcher_config()`
- `src/population_synth/gui/widgets/task_selector.py` — use `default_action_id` instead of `button_index == 0`
- `scripts/generate_identities_parallel.py` — `--generate-all-strategies` flag + loop at top of `main()`

---

## Implementation Plan

### Phase 1: Default workflow

**Goal:** Make "LLM Synthetic Population" the pre-selected action on startup.

- [x] Task 1.1 — `config/gui_launcher.yaml`: add `default_action: generate_parallel` at the top level
- [x] Task 1.2 — `launcher_config.py`: add `default_action_id: str | None = None` to `LauncherConfig`; in `parse_launcher_config()` assign `raw.get("default_action")`
- [x] Task 1.3 — `task_selector.py`: replace `if button_index == 0:` with `if action.id == default_id:` where `default_id = config.default_action_id or config.actions[0].id`

**Files Modified:**
- `config/gui_launcher.yaml` — add `default_action` key
- `src/population_synth/gui/launcher_config.py` — `LauncherConfig` field + parser
- `src/population_synth/gui/widgets/task_selector.py` — radio selection logic

**Dependencies:** None

### Phase 2: Generate all strategies

**Goal:** Add the checkbox parameter and script-level loop.

- [x] Task 2.1 — `config/gui_launcher.yaml`: add `generate-all-strategies` bool parameter to the `generate_parallel` action's `parameters` list
- [x] Task 2.2 — `generate_identities_parallel.py`: add `--generate-all-strategies` argument (`action="store_true"`)
- [x] Task 2.3 — `generate_identities_parallel.py`: immediately after `args = parser.parse_args()`, insert the all-strategies early-exit block:
  - Validate `args.model_id` and `args.country_id` are present (exit with error if not)
  - Call `discover_axis_values("strategies")` from `manifest_loader`
  - For each strategy item, print banner, build sub-command from `sys.executable, __file__` with `--model-id`, `--strategy-id`, `--country-id`, `--n`, `--workers`, `--force`, `--retry-until-success` (only those that are set), then `subprocess.run(sub_cmd, stdout=sys.stdout, stderr=sys.stderr)`
  - `sys.exit(0)` after the loop

**Files Modified:**
- `config/gui_launcher.yaml` — `generate-all-strategies` parameter
- `scripts/generate_identities_parallel.py` — flag + loop

**Dependencies:** Phase 1 (logically independent, but ship together)

---

## Testing Plan

### Manual Verification
- [ ] Launch GUI — confirm "LLM Synthetic Population" is pre-selected without clicking
- [ ] Switch to another action and relaunch — confirm it still defaults to "LLM Synthetic Population"
- [ ] Confirm "Generate all strategies" checkbox appears unchecked under "LLM Synthetic Population"
- [ ] Confirm other actions do not show the checkbox
- [ ] Run with checkbox unchecked — confirm identical behaviour to before
- [ ] Run with checkbox checked (model + country selected, small n) — confirm console shows a banner per strategy and each strategy runs in sequence
- [ ] Run `python scripts/generate_identities_parallel.py --model-id claude_haiku --country-id swedish --generate-all-strategies --n 1 --workers 1` directly from CLI — confirm same sequential behaviour

### Edge Cases
- [ ] If `--generate-all-strategies` is passed without `--model-id` / `--country-id`, script exits with a clear error message (not a traceback)

---

## Documentation Plan

- [ ] Update `CLAUDE.md` — add `--generate-all-strategies` to the "Commands" section example for `generate_identities_parallel.py`

---

## Rollback Plan

All changes are confined to four files with no schema migrations or data changes. To revert:

1. `git revert` the feature branch commits, or `git checkout main -- <file>` for each changed file
2. No state is written by the GUI changes themselves; any already-generated persona data is unaffected

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `default_action_id` references an action that was skipped (script not found) | Low | Medium | Fall back to `config.actions[0].id` if the default id is not in the loaded action list |
| Sub-subprocess stdout not appearing in GUI console | Low | High | The approach (`stdout=sys.stdout`) is proven for this pattern; verify manually during testing |
| `discover_axis_values("strategies")` returns an empty list | Low | Low | Print a warning and exit cleanly rather than running zero strategies silently |
