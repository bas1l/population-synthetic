# gui_v2 — config-driven Flow Runner GUI

`gui_v2` (`python -m population_synthetic.gui_v2.main`, requires the `.[gui]`
extra) is the **primary** PyQt5 launcher. The original `gui/` package
(`python -m population_synthetic.gui.main`) is **deprecated** — it still runs as a
fallback and emits a `DeprecationWarning`, but it is retained mainly because
`gui_v2` reuses its widgets and runners (`CombinationRunner`, `_kill_process_tree`,
`ConsoleWidget`, `DagGraphWidget`, `CheckableAxisList`, `PersonaCountWorker`) as
shared substrate — so the package must not be removed. `gui_v2` adopts a two-tier,
editable-YAML config model and a DAG-based Analysis Workflow. This page documents
the three contracts a maintainer needs before changing it.

## Two-tier config

Configuration lives under `config/gui/v2/`:

- **`menu.yaml`** — the catalogue: categories → flows. Each flow entry is
  `{name, kind, script, config, axis_mode}`. `kind: script` (default) points at
  a single script; `kind: workflow` has **no** top-level `script` (scripts live
  per task in its config). Missing `script`/`config` *files* warn-and-skip;
  `kind`/`script` **mismatches raise** (fail-fast).
- **one round-trip YAML per flow** (`config/gui/v2/flows/*.yaml`) — the flow's
  editable state: `options:` (keys are CLI flag names in dash form),
  `selection:` (checked `models`/`strategies`/`countries`), and `force:` for
  generate flows. The GUI loads it with ruamel round-trip, edits it in place,
  and **saves it back losslessly** (comments + key order preserved). Per-option
  UI metadata (enum choices, labels, groups) is **not** in the YAML — it lives
  in declarative tables in `widgets/flow_options_panel.py`, keyed by option name.

## Execution contract — GUI translates flow YAML → CLI

**The spawned scripts never read the flow YAML.** On Run, the GUI *translates*
the flow's `options` + `selection` into CLI invocations of the existing
scripts (`--model-id/--strategy-id/--country-id` + override flags, `--force`,
or `--slug` lists). There is **no** `--flow-config` argument, and one must never
be added — the flow YAML is a GUI-side persistence/UX artifact only. This reuses
the proven `CombinationRunner` + `_kill_process_tree` from `gui/main_window.py`
verbatim, so no script rewrites are needed. The pure command builders live in
`gui_v2/commands.py` (`build_per_combo_cmds`, `build_slugs_cmd`) and are shared
by both single-script flows and workflow tasks. This invariant is asserted in
inline comments in `main_window._on_run`, `workflow_runner.py`, and
`commands.py`.

Dispatch shapes:

- **`three_axis`** (single-script generate/compare flows): each checked combo →
  one per-combo invocation, run through `CombinationRunner`.
- **workflow task `dispatch: per_combo`**: one invocation per checked combo.
- **workflow task `dispatch: slugs`**: one invocation total, with one
  `--slug {country}_{strategy}_{model}` per checked combo.

## Workflow contract — GUI-side dependency chaining

The **Analysis Workflow** flow (`config/gui/v2/flows/analysis_workflow.yaml`) is
a DAG of tasks (`{script, dispatch, enabled, options, depends_on, min/max_combos}`).
Ordering is **derived from `depends_on`** by topological sort (Kahn, YAML
authoring order as the deterministic tie-break) — there is no hardcoded Python
stage list. `WorkflowState.validate()` fails loudly at flow load on: unknown
`depends_on` target, a cycle (members named), a missing script on disk, a
`dispatch` outside `{per_combo, slugs}`, or `min_combos > max_combos`.

`WorkflowRunner` (a `QThread` over a Qt-free `execute_workflow` core) walks the
enabled chain GUI-side:

- **Disabled** task → `SKIPPED_DISABLED`, not completed.
- **Dependency did not complete** → `SKIPPED_DEP`.
- **Guard violated** (checked-combo count vs `min_combos`/`max_combos`) →
  `SKIPPED_GUARD` with a **loud** console banner; the run continues.
- **Run** → on **exit code 0** the task is marked `COMPLETED`, which unlocks its
  dependents; the first nonzero exit fails the task (`FAILED`) and its
  dependents dep-skip, while independent branches (the `joint_fidelity` and
  `compare_pops` side branches -- both `slugs`-dispatch, depending only on
  `map_populations` -- and the isolated `llm_metrics` islands) still run.
- **Abort** → `_kill_process_tree` on the live process; the current task and all
  not-yet-run tasks become `ABORTED`.

Node run-states are **transient** — per run, never written back to the YAML.
The live node-state graph (`widgets/workflow_graph_view.py`) doubles as the run
report.

## Equivalent-size synthetic cap (`n-synthetic` / `sample-seed`)

Synthetic populations now vary in size (models emit different persona counts),
which biases the sample-size-sensitive fidelity metrics (C2ST, joint
chi-squared, per-pair joint TV). The **Compare Synthetic to Real** and
**Multivariate Joint Fidelity** task nodes therefore expose two options that
restore an equivalent population size before scoring:

- **`n-synthetic`** — blank (the default) means no cap, i.e. current behaviour.
  An integer caps every synthetic population to that many individuals via a
  seeded without-replacement draw. Populations smaller than N run in full with a
  loud warning (the equalised size cannot be met).
- **`sample-seed`** — the seed for that draw (default `0`). **Set the same
  `n-synthetic` and `sample-seed` on both the Compare and the Multivariate
  task** so they draw the identical subset of individuals — otherwise the
  marginal and joint reports would be computed over different people.

**Model Performance inherits the cap automatically.** The ranking node
(`rank_models`) recomputes nothing: it consumes the capped fidelity reports and
reads the `n` they record, so a capped Compare run feeds it a capped ranking. It
therefore exposes no cap option of its own.
