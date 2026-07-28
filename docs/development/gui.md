# gui — config-driven Flow Runner GUI

`gui` (`python -m population_synthetic.gui.main`, requires the `.[gui]`
extra) is the **sole** PyQt5 launcher — the deprecated v1 launcher package (the
old `LauncherWindow`) has been removed. Its runner and widget substrate now
lives inside `gui` itself: `gui/execution.py` holds `CombinationRunner`
and `_kill_process_tree`, and `gui/widgets/` holds `console_widget.py`
(`ConsoleWidget`), `dag_graph_widget.py`/`dag_graph_items.py` (`DagGraphWidget`),
`checkable_axis_list.py` (`CheckableAxisList`), and `persona_count_worker.py`
(`PersonaCountWorker`) — all self-contained. `gui` adopts a two-tier,
editable-YAML config model and a DAG-based
Analysis Workflow. This page documents the three contracts a maintainer needs
before changing it.

## Two-tier config

Configuration lives under `config/gui/`:

- **`menu.yaml`** — the catalogue: categories → flows. Each flow entry is
  `{name, kind, script, config, axis_mode}`. `kind: script` (default) points at
  a single script; `kind: workflow` has **no** top-level `script` (scripts live
  per task in its config). Missing `script`/`config` *files* warn-and-skip;
  `kind`/`script` **mismatches raise** (fail-fast).
- **one round-trip YAML per flow** (`config/gui/flows/*.yaml`) — the flow's
  editable state: `options:` (keys are CLI flag names in dash form),
  `selection:` (checked `models`/`strategies`/`countries`), and `force:` for
  generate flows. The GUI loads it with ruamel round-trip, edits it in place,
  and **saves it back losslessly** (comments + key order preserved). Per-option
  UI metadata (enum choices, labels, groups) is **not** in the YAML — it lives
  in declarative tables in `widgets/flow_options_panel.py`, keyed by option name.

Two of those enum tables are themselves **config-sourced**, filled at import by
populator functions rather than hardcoded in Python:

| Option | Source config | Entries |
|--------|---------------|---------|
| `judge-model` | `config/analysis/persona_realism/judge.yaml` (`model_options`) | `("(default)", None)` sentinel + one `(m, m)` pair per model |
| `ollama-host` | `config/synthetic/ollama_hosts.yaml` (`hosts:`) | one `(host.label, host.id)` pair per host — **no** `(default)` sentinel |

`ollama-host` deliberately has no sentinel: a saved `None` would omit the flag and
let the run silently resolve the registry's `default_host`, which is the
wrong-GPU failure the option exists to prevent. An explicit host every run is the
point. Both populators share the same degrade-gracefully contract — any
read/parse failure logs a warning and leaves the key **out** of the enum table, so
its row falls back to the free-text field; neither may raise at import, or
`import population_synthetic.gui...` would break the whole GUI.

Adding a host is therefore config-only: declare it in `ollama_hosts.yaml`, add one
key per model axis `workers` map, and it appears in both the dropdown and the
`--ollama-host` argparse `choices` with zero `.py` edits.

### Reconfigure Ollama Host — pressing Run can restart the server

The *LLM Synthetic Population* flow carries `ollama-reconfigure: true`, rendered as
a **Reconfigure Ollama Host** checkbox (a plain bool needs no enum table — shape
dispatch gives it a checkbox; only the friendly label is declared, in
`_OPTION_LABELS`). It is **on by default**, so pressing **Run** does more than start
Python: before the first persona of a combo, the script sets the selected host's
`OLLAMA_NUM_PARALLEL` to that combo's resolved worker count, which means
**recreating that host's Ollama container** — evicting whatever model was loaded and
killing any in-flight request from another user of that GPU. It then warms the model
up and waits for the server to serve again.

Two things bound that. The restart is skipped when the server already reports the
requested value, so a Run over N combos of one model restarts **at most once** and a
correctly-configured server is never touched; and the box can be unticked, which
restores the previous behaviour exactly (the argparse default is `False`, so the flow
YAML is the only thing that turns it on). The option is inert for non-Ollama providers
and for hosts declaring no `control_url`.

What the console pane shows while that happens is three numbered lines —
`[1/3] PROBE`, `[2/3] ACT`, `[3/3] GATE` — emitted once per combo whether or not the
pre-flight acted, each naming the facts behind its verdict (see
[Ollama hosts](../ollama_server_models.md#watching-it-from-the-console) for a sample).
Over a five-combo Run that is what makes "one restart, four skips" visible rather than
merely claimed.

The GUI knows none of this. It renders a boolean and lets the arg-vector machinery
emit a bare `--ollama-reconfigure`; control URLs, HTTP and the five outcome states
live entirely on the script side. See
[Ollama hosts](../ollama_server_models.md) for the control API and the outcomes.

## Execution contract — GUI translates flow YAML → CLI

**The spawned scripts never read the flow YAML.** On Run, the GUI *translates*
the flow's `options` + `selection` into CLI invocations of the existing
scripts (`--model-id/--strategy-id/--country-id` + override flags, `--force`,
or `--slug` lists). There is **no** `--flow-config` argument, and one must never
be added — the flow YAML is a GUI-side persistence/UX artifact only. This reuses
the proven `CombinationRunner` + `_kill_process_tree` from `gui/execution.py`,
so no script rewrites are needed. The pure command builders live in
`gui/commands.py` (`build_per_combo_cmds`, `build_slugs_cmd`) and are shared
by both single-script flows and workflow tasks. This invariant is asserted in
inline comments in `main_window._on_run`, `workflow_runner.py`, and
`commands.py`.

Dispatch shapes:

- **`three_axis`** (single-script generate/compare flows): each checked combo →
  one per-combo invocation, run through `CombinationRunner`.
- **workflow task `dispatch: per_combo`**: one invocation per checked combo.
- **workflow task `dispatch: slugs`**: one invocation total, with one
  `--slug {country}_{strategy}_{model}` per checked combo.
- **workflow task `dispatch: per_country`**: collapses the checked combos to
  their **distinct `country_id` values** (stable, first-seen order) and emits
  one invocation per country with **`--country-id` only** — model/strategy
  ticks are ignored, since the backing script (e.g.
  `analyze_real_population_stats.py`) operates on the real reference
  population alone. Built by `gui/commands.py::build_per_country_cmds`;
  ticking 3 models × 2 strategies × 1 country yields exactly one invocation.

## Task-naming contract — one registry, three aligned names

An analysis process has **one canonical id**, and it is used three times over: it
is the GUI workflow task **key** (the node id in `analysis_workflow.yaml`), the
registry **key** in `config/analysis/analysis_registry.yaml`, and the
`03_Analysis/` **output-folder** name the backing script writes to. These three
can never drift because they are the same string.

The flow YAML now carries **orchestration only** — per task: `depends_on`,
`options`, `enabled`, and the force/combo guards (`supports_force`,
`min_combos`/`max_combos`). It no longer carries `label`, `description`,
`script`, or `dispatch`: those four are **owned by the registry** and merged in
at read time by `WorkflowConfigModel.get_task_meta` (via `get_process(id)`),
which fails loudly if a flow task id is not a registered process.
`WorkflowState.to_plain()` enriches each task with the registry
`label`/`script`/`dispatch` so the runner snapshot stays complete without
re-duplicating them on disk. When a task node is clicked, the workflow options
pane shows a read-only, mouse-selectable **description** sourced from the
registry (`get_task_meta(name)["description"]`).

The single accessor `analysis/utils/registry.py` also gives every script its
output dir (`analysis_output_dir(id, base)`) and resolves the output base
(`resolve_output_base`), so no script hardcodes `03_Analysis` or a folder name.
See the canonical id → label → folder → script table in
[Commands](../architecture/commands.md).

## Workflow contract — GUI-side dependency chaining

The **Analysis Workflow** flow (`config/gui/flows/analysis_workflow.yaml`) is
a DAG of tasks whose node ids are the canonical ids above; each task carries the
orchestration fields (`{enabled, options, depends_on, min/max_combos, force}`),
while `script`/`dispatch` are resolved from the registry.
Ordering is **derived from `depends_on`** by topological sort (Kahn, YAML
authoring order as the deterministic tie-break) — there is no hardcoded Python
stage list. `WorkflowState.validate()` fails loudly at flow load on: unknown
`depends_on` target, a cycle (members named), a missing script on disk, a
`dispatch` outside `{per_combo, slugs, per_country}`, or `min_combos > max_combos`.

`WorkflowRunner` (a `QThread` over a Qt-free `execute_workflow` core) walks the
enabled chain GUI-side:

- **Disabled** task → `SKIPPED_DISABLED`, not completed.
- **Dependency did not complete** → `SKIPPED_DEP`.
- **Guard violated** (checked-combo count vs `min_combos`/`max_combos`) →
  `SKIPPED_GUARD` with a **loud** console banner; the run continues.
- **Run** → on **exit code 0** the task is marked `COMPLETED`, which unlocks its
  dependents; the first nonzero exit fails the task (`FAILED`) and its
  dependents dep-skip, while independent branches (the `multivariate_fidelity`
  and `pairwise_comparison` side branches -- both `slugs`-dispatch, depending
  only on `mapping` -- and the isolated `generation_metadata` island) still run.
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
(`model_ranking`) recomputes nothing: it consumes the capped fidelity reports and
reads the `n` they record, so a capped Compare run feeds it a capped ranking. It
therefore exposes no cap option of its own.
