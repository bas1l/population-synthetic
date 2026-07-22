# Plan: Real-Population Reference Statistics Analysis Task

**Date:** 2026-07-22
**Author:** Basil
**Status:** In Progress
**Base Branch:** `dev`
**Branch:** `feature/real-population-reference-stats`

---

## Overview

Add a new standalone analysis task that renders **publication-ready reference figures** of the
real, API-sourced population. For each analyzed demographic category it produces a bar plot of the
category-value proportions (percent), emitted as **PNG + SVG + CSV**, plus one **combined
multi-panel overview** figure. The task operates on a single real population per country (no
synthetic comparison) and is exposed as a first-class GUI workflow task via a new **`per_country`**
dispatch mode.

## Problem Statement

The manuscript treats the real (SCB/ISTAT/SSB) population as ground truth, but the repo has **no
standalone real-population statistics path**: every proportional/marginal artifact today is produced
*inside* a two-population comparison (real-vs-synthetic in `fidelity/`, real-vs-real in
`cross_country`). There is no way to emit clean, self-contained per-category reference figures of
the real distribution for the paper. This forces manual extraction of the real side out of
comparison outputs and provides no per-figure proportion CSV for paper tables.

## Goals

### In Scope
1. A new analysis subpackage `analysis/real_population_stats/` that, for a single real population,
   computes per-category proportions and renders one bar figure per analyzed category.
2. Per-figure output triad: **PNG + SVG + CSV** (CSV = raw per-category `count, total, proportion,
   percent`).
3. Figure styling for publication: x = category values; y = **percent, fixed [0, 100]**; value
   labels printed on each bar; gray dashed horizontal reference lines at 25/50/75/100%.
4. One additional **combined multi-panel overview** figure (all analyzed categories tiled) as
   PNG + SVG.
5. **Country-agnostic** operation (any country in `known_country_ids()`), analyzing the
   **config-driven analyzed axis set** (`ComparisonScheme.attributes`, deprecated axes excluded).
6. A backing CLI script `scripts/analyze/analyze_real_population_stats.py`, registered in
   `analysis_registry.yaml`, resolving its output dir via the registry (`03_Analysis/
   real_population_stats/`).
7. A new **`per_country`** GUI dispatch mode so the task is runnable from the Flow Runner workflow
   (one run per selected country; model/strategy ticks ignored), with an explicit, self-describing
   registry `label`/`description`.

### Out of Scope
- Any synthetic population, comparison, or fidelity metric (this is real-only, single-population).
- Conditional / joint / multivariate views (strictly univariate marginals).
- Bespoke per-country styling or manual figure curation (task is uniform across countries).
- Retrofitting `cross_country` onto `per_country` (noted as a future follow-up, not done here).
- Changing the `mapping` task or the shape of `real_{country}.json`.

## Success Criteria

- [x] Running the task for a country writes, under `03_Analysis/real_population_stats/<country>/`,
      exactly one `<attr>.png`, one `<attr>.svg`, and one `<attr>.csv` per analyzed attribute, plus
      `overview.png` and `overview.svg`.
- [x] Every bar figure has a y-axis fixed to [0, 100]% with dashed gray reference lines at
      25/50/75/100% and a percent label on each bar.
- [x] Each CSV has one row per config category value with columns `value, count, total, proportion,
      percent`; proportions match `compute_proportions` for the same input (asserted in a test).
- [x] The task appears as one row in the GUI analysis workflow, runs once per **distinct selected
      country** (verified: ticking 3 models × 2 strategies × 1 country → 1 invocation), and its
      label/description explicitly state it operates on the real reference population and ignores
      model/strategy.
- [x] Task is idempotent: re-running without `--force` skips already-computed countries; with
      `--force` it overwrites. Missing `real_{country}.json` fails loudly with a message pointing to
      the `mapping` task.
- [x] `ruff check src/` clean; `pytest` green including new unit + integration tests.

## Definitions

- **Analyzed axis set:** the ordered attribute list from `ComparisonScheme.attributes` as returned
  by `load_scheme(country)` — i.e. `_index.json` `attributes` with `deprecated_attributes` removed
  (Sweden = 14, excludes `birth_location`). The task iterates exactly this list; it does **not**
  hardcode any attribute names.
- **Proportion:** `count(category_value) / total_non_null(attr)`, identical to
  `compute_proportions`, using the evaluator's `attr_value` so `age` is binned into `age_group`
  consistently. **Percent** = proportion × 100.
- **total_non_null (N):** number of records with a non-null value for the attribute; the denominator
  behind every proportion, carried into the CSV so a genuine 0% is distinguishable from a small N.
- **Absent category:** a config axis value with zero occurrences → `count=0, proportion=0.0` (a real
  zero, emitted). Distinct from an **all-null attribute** (no non-null records at all) → figure/CSV
  skipped for that attribute with a logged WARNING (not silently dropped).
- **per_country dispatch:** a GUI dispatch mode that collapses the checked model×strategy×country
  combos to their **distinct country ids** and invokes the script once per country with only
  `--country-id` (plus `--force`/options).

---

## Technical Design

### Approach

A new leaf **pipe-and-filter analytics stage**: reads one mapped real population
(`03_Analysis/mapping/real_{country}.json`) → aggregates per-category proportions (pure
computation) → renders figures + writes CSV (pure sinks). It reuses the existing single-population
arithmetic (`compute_proportions`), the dual PNG+SVG writer (`save_figure`), the config-driven axis
source (`load_scheme`), and the registry output-dir wiring (`analysis_output_dir`,
`resolve_output_base`). The only genuinely new computation is a stats helper that additionally
carries per-category **counts and N** (the shared `compute_proportions` returns proportions only),
and a proportion-vector CSV writer (the existing `write_csv_summary` emits comparison metrics, not
proportions).

To make it a first-class GUI task without a phantom model/strategy dependency, a new `per_country`
dispatch is added to the GUI engine (the current `_VALID_DISPATCH` allowlist rejects anything but
`per_combo`/`slugs`, and `cli` is not workflow-runnable).

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **New `per_country` dispatch** | Semantically honest (1 run/country); no wasted subprocesses; reusable for future real-only tasks; no phantom model/strategy dep | Touches 4 GUI engine files + tests + `gui.md` | **Chosen** |
| Reuse `per_combo` + dedupe in script | Zero engine changes; mirrors `map_populations.py` real-file cache | Redundant no-op subprocess spawns; phantom model/strategy dependency; combo guards meaningless; UI row implies model/strategy matter | Rejected |
| CLI-only (`dispatch: cli`, like `cross_country`) | Trivial; matches existing real-only precedent | Not reachable from GUI — contradicts the "new GUI task" goal | Rejected |
| Extend `fidelity/charts.py` bar plotter to a single-series mode | Reuses one plotter | Overloads a comparison module with a standalone concern; couples publication styling to comparison code | Rejected |

### Architecture & Module Contracts

New subpackage `src/population_synthetic/analysis/real_population_stats/`. Computation, rendering,
and I/O are separated (computation never renders; plotters never compute or resolve paths; the
orchestrator owns paths and config).

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `stats.py::compute_category_stats` | Per-category counts/N/proportion/percent for one attribute | `(individuals: list[dict], attr: str, categories: list[str])` → `(rows: list[CategoryStat], extra_categories: list[str])` | matplotlib, file paths, country id, registry |
| `charts.py::plot_category_bars` | Render one single-series percent bar figure (fixed 0–100, dashed 25/50/75/100 lines, on-bar labels) | `(rows, attr, title?)` → `matplotlib.figure.Figure` | file paths, CSV, disk, dpi/format |
| `charts.py::plot_overview_panel` | Tile all attributes' bars into one grid figure | `(stats_by_attr: dict[str, list[CategoryStat]])` → `Figure` | file paths, disk |
| `csv_writer.py::write_proportions_csv` | Write the per-category proportion table | `(rows, path: Path)` → written `Path` | matplotlib, country, scheme |
| `artifacts.py::write_real_population_stats` | Orchestrate: iterate analyzed axes, compute, render, save PNG+SVG+CSV, build overview | `(real_pop: dict, scheme: ComparisonScheme, out_dir: Path, *, dpi: int, force: bool)` → `list[Path]` | how the population/scheme were loaded, GUI, dispatch |
| `scripts/analyze/analyze_real_population_stats.py` | CLI edge: parse args, resolve base/out dir, load scheme + `real_{country}.json`, call orchestrator, idempotent skip | `--country-id … --output-base --force --dpi` → files on disk | plotting internals, proportion math |
| `gui/commands.py::build_per_country_cmds` | Collapse checked combos to distinct countries → one cmd each | `(script, combos, force, options)` → `list[list[str]]` (one per country, `--country-id` only) | analysis internals, matplotlib |

`CategoryStat` is a small frozen dataclass (or TypedDict): `{value: str, count: int, total: int,
proportion: float, percent: float}`.

```
src/population_synthetic/analysis/real_population_stats/
├── __init__.py
├── stats.py          # compute_category_stats (+ CategoryStat)
├── charts.py         # plot_category_bars, plot_overview_panel  (pure render, return Figure)
├── csv_writer.py     # write_proportions_csv
└── artifacts.py      # write_real_population_stats  (orchestrator)

scripts/analyze/analyze_real_population_stats.py   # CLI, registry-driven

Output layout:  {output_base}/03_Analysis/real_population_stats/{country}/
    {attr}.png / {attr}.svg / {attr}.csv   (one set per analyzed attribute)
    overview.png / overview.svg
```

**Reuse (unchanged):** `analysis/utils/marginals.py::compute_proportions`,
`analysis/utils/figures.py::save_figure` (derives `.svg` itself), `analysis/fidelity/scheme.py::
load_scheme` + `ComparisonScheme.attributes/.categories`, `analysis/utils/registry.py::
analysis_output_dir/resolve_output_base`, `analysis/utils/country_config.py::known_country_ids/
real_for_country`. `stats.py` derives values via the same `attr_value` the evaluator/
`compute_proportions` use, and a unit test asserts its proportions equal `compute_proportions`
output to prevent divergence.

**Engine change contract (`per_country`):** `gui/workflow_state.py` `_VALID_DISPATCH` gains
`"per_country"`; `gui/commands.py` gains `build_per_country_cmds`; `gui/workflow_runner.py::
_run_task` gains a `per_country` branch + status banner. All three are additive — existing
`per_combo`/`slugs` paths are untouched.

---

## Implementation Plan

### Phase 1: Computation + I/O core (subpackage, no GUI)
**Goal:** A working, tested library + CLI that produces the figures/CSV for a country from the CLI.

**Started:** 2026-07-22
**Completed:** 2026-07-22

- [x] 1.1 — Create `analysis/real_population_stats/stats.py`: `CategoryStat` + `compute_category_stats`
      (counts + N + proportion + percent via `attr_value`; absent category → 0; all-null → signal to
      caller; return `extra_categories` and log WARNING like `compute_proportions`).
- [x] 1.2 — `charts.py`: `plot_category_bars` (single-series, y fixed [0,100], `axhline` dashed gray
      at 25/50/75/100, `bar_label` percent on each bar, headless `Agg` backend, returns `Figure`)
      and `plot_overview_panel` (grid tiling; returns `Figure`).
- [x] 1.3 — `csv_writer.py`: `write_proportions_csv` (columns `value,count,total,proportion,percent`).
- [x] 1.4 — `artifacts.py`: `write_real_population_stats` orchestrator — iterate `scheme.attributes`,
      compute, `save_figure(fig, out_dir/country/f"{attr}.png", dpi=dpi)` (PNG+SVG), write CSV, skip
      all-null attrs with a logged reason, build + save `overview.*`, return written paths.
- [x] 1.5 — `scripts/analyze/analyze_real_population_stats.py`: argparse (`--country-id` append,
      `--output-base`, `--force`, `--dpi` default 200, `--no-charts` optional); `resolve_output_base`
      → `analysis_output_dir("real_population_stats", base)`; load `real_{country}.json` from
      `analysis_output_dir("mapping", base, for_read=True)` (fail-fast if missing → point to mapping
      task); `load_scheme(country)`; per-country idempotent skip unless `--force`.

**Implementation note:** `write_real_population_stats` gained one additive keyword param beyond the
contract table, `charts: bool = True`, so `--no-charts` (task 1.5) has somewhere to plug in without
inventing a second orchestrator entry point; when `False` it writes only the per-attribute CSVs and
skips all figure rendering (including the overview). The registry entry for `real_population_stats`
was deliberately **not** added in this phase (see Phase 2, task 2.1): `test_registry_has_all_ten_processes`
asserts the registry's id set exactly equals the current ten ids, so adding an eleventh id now would
fail that existing test. The CLI script correctly calls `analysis_output_dir("real_population_stats",
base)` and was confirmed (by manual run) to raise the expected `KeyError` naming all current ids until
Phase 2 adds the entry — the library (`artifacts.write_real_population_stats` called directly, bypassing
the registry) was smoke-tested end-to-end against the real `real_swedish.json` mapped population
(14 attributes → 44 files incl. overview; CSV proportions verified bit-identical to `compute_proportions`;
idempotent skip / `--force` overwrite / all-null skip / `--no-charts` all verified manually).

**Files Modified:**
- `src/population_synthetic/analysis/real_population_stats/{__init__,stats,charts,csv_writer,artifacts}.py` — new
- `scripts/analyze/analyze_real_population_stats.py` — new

**Dependencies:** None (mapping output assumed present at run time; validated by fail-fast).

### Phase 2: Registry + GUI `per_country` dispatch
**Goal:** The task is a first-class, self-describing GUI workflow task running once per country.

**Started:** 2026-07-22
**Completed:** 2026-07-22

- [x] 2.1 — Add `real_population_stats` entry to `config/analysis/analysis_registry.yaml`
      (`dispatch: per_country`; explicit label/description stating "real reference population only,
      once per country, ignores model/strategy"; `folder: real_population_stats`).
- [x] 2.2 — `gui/workflow_state.py`: add `"per_country"` to `_VALID_DISPATCH`.
- [x] 2.3 — `gui/commands.py`: `build_per_country_cmds(script, combos, force, options)` — dedupe
      `country_id` from combos (stable order), one cmd each with `--country-id` (+ `--force` first,
      options last).
- [x] 2.4 — `gui/workflow_runner.py::_run_task`: add `per_country` branch dispatching to
      `build_per_country_cmds`, with a status banner naming the countries.
- [x] 2.5 — Add workflow node to `config/gui/flows/analysis_workflow.yaml`
      (`enabled: true`, `options: {}`, `depends_on: [mapping]`, `supports_force: true`,
      `force: false`).

**Implementation note:** two existing tests enumerated the registry/shipped-workflow id sets
exactly and needed updating for the eleventh id, exactly as anticipated for
`test_registry_has_all_ten_processes` (renamed to `test_registry_has_all_eleven_processes`,
`tests/test_analysis_registry.py`): the shipped-workflow ordering test
(`test_shipped_workflow_ordering`, `tests/test_workflow_state.py`) also asserts an exact task-name
set from the real `analysis_workflow.yaml` and was updated the same way (added
`real_population_stats` to the expected set + an ordering assertion that it comes after `mapping`).
Both are exact-set assertions, not loosened. Full `pytest` (482 tests) and `ruff check src/` are
green.

**Files Modified:**
- `config/analysis/analysis_registry.yaml` — new process entry
- `config/gui/flows/analysis_workflow.yaml` — new node
- `src/population_synthetic/gui/workflow_state.py` — `_VALID_DISPATCH`
- `src/population_synthetic/gui/commands.py` — `build_per_country_cmds`
- `src/population_synthetic/gui/workflow_runner.py` — dispatch branch + banner
- `tests/test_analysis_registry.py` — updated exact-set test for the 11th id
- `tests/test_workflow_state.py` — updated exact-set test for the shipped workflow's 11th node

**Dependencies:** Phase 1.

### Phase 3: Tests + documentation
**Goal:** Verified behavior and updated docs.

**Started:** 2026-07-22
**Completed:** 2026-07-22

- [x] 3.1 — Unit tests (stats, csv_writer, charts-return-Figure, per_country cmd builder, workflow
      validation) — see Testing Plan.
- [x] 3.2 — Integration test: run the script on a small `real_{country}.json` fixture → assert the
      full artifact set, idempotent skip, `--force` overwrite, and fail-fast on missing input.
- [x] 3.3 — Docs: `docs/development/gui.md` (document `per_country` dispatch shape);
      `docs/architecture/commands.md` (new command); `docs/architecture/sub-packages.md` +
      `CLAUDE.md` analysis-registry paragraph (new subpackage/task); changelog entry.

**Implementation note:** the changelog sub-item was **not completed** — `docs/changelogs/` does not
exist anywhere in this repository (confirmed via `git log --all` for any past add/remove under that
path); there is no established entry format to match, so inventing one from nothing would be a new,
unreviewed documentation convention rather than following an existing one. Flagged as a boundary
tension rather than silently fabricated. All other 3.3 doc targets were updated as specified.

**Files Modified:**
- `tests/test_real_population_stats.py` — new (27 unit tests: stats, csv_writer, charts, per_country
  cmd builder, registry/workflow wiring)
- `tests/test_real_population_stats_integration.py` — new (4 integration tests: full artifact set,
  idempotent skip, `--force` overwrite, fail-fast on missing mapped input)
- `docs/development/gui.md`, `docs/architecture/commands.md`, `docs/architecture/sub-packages.md`,
  `CLAUDE.md` — updated (changelog entry skipped, see note above)

**Dependencies:** Phase 2.

---

## Testing Plan

### Unit Tests
- [x] `compute_category_stats`: proportions equal `compute_proportions` for the same input; counts
      sum to `total`; `total` = non-null count; absent config value → `count=0, proportion=0.0`;
      all-null attribute → signalled (not a silent zero); `age` binned to `age_group`.
- [x] `compute_category_stats` returns `extra_categories` for data values not in the config axis
      (and logs WARNING); those are not plotted.
- [x] `write_proportions_csv`: exact columns/rows; percent = proportion×100; round-trip parses.
- [x] `plot_category_bars` / `plot_overview_panel` return a `Figure` (no disk writes); y-limits
      [0,100]; the 4 reference lines and bar labels are present.
- [x] `build_per_country_cmds`: 3×2×1(SE) combos → 1 cmd (`--country-id swedish`); SE+IT → 2 cmds;
      `--force` and options placed correctly; model/strategy flags absent.
- [x] `WorkflowState.validate()` accepts a `per_country` node; a `per_country` registry entry loads.

### Integration Tests
- [x] End-to-end script run on a small fixture `real_swedish.json` → asserts one PNG+SVG+CSV per
      analyzed attr + `overview.png/svg`; second run without `--force` skips (mtimes unchanged);
      `--force` overwrites.
- [x] Missing `real_{country}.json` → script raises with a message naming the `mapping` task.

### Manual Verification
- [ ] Run `mapping` then "Real Reference Population Stats" from the GUI with 2+ models ticked and one
      country → confirm exactly one invocation and one country output folder.
- [ ] Open a generated SVG: y-axis 0–100%, dashed gray lines at 25/50/75/100%, percent labels on
      bars, x = category values.

### Edge Cases
- [ ] High-cardinality attribute (e.g. `region`) renders legibly with on-bar labels under fixed
      0–100% axis (overview panel remains readable).
- [ ] Attribute entirely null → figure/CSV skipped with logged reason; overview notes the omission.
- [ ] Country with no `real_{country}.json` yet (mapping not run) → fail-fast.

---

## Documentation Plan

- [x] Update `CLAUDE.md` analysis-registry paragraph + `docs/architecture/sub-packages.md` with the
      new subpackage and task id.
- [x] Update `docs/architecture/commands.md` with the new command.
- [x] Update `docs/development/gui.md`: document the `per_country` dispatch shape alongside
      `per_combo`/`slugs`.
- [ ] Add changelog entry under `docs/changelogs/`. **Not done** — `docs/changelogs/` does not exist
      in this repo (no prior entries, no established format to match); see the Phase 3 implementation
      note.
- [x] Inline docstrings on each new module stating its single responsibility and what it must not
      know about (already in place from Phase 1).

---

## Rollback Plan

1. **Before merge:** all work is on `feature/real-population-reference-stats`; abandon the branch to
   revert with zero impact on `dev`.
2. **Data considerations:** no migrations; the task only *writes* a new `03_Analysis/
   real_population_stats/` folder and reads existing `mapping` output — deleting that folder fully
   reverses its data effect.
3. **Rollback procedure:** revert the two engine commits (registry/workflow + `per_country`
   dispatch) and the subpackage; the additive `_VALID_DISPATCH` / `_run_task` changes do not affect
   existing `per_combo`/`slugs` tasks, so reverting is isolated.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `per_country` engine change regresses existing dispatch | Low | High | Changes are strictly additive; unit tests cover both existing modes and the new one; `_VALID_DISPATCH` allowlist keeps validation loud |
| `compute_category_stats` diverges from `compute_proportions` (double source of truth for proportions) | Med | Med | Reuse the same `attr_value`; add a test asserting equality with `compute_proportions`; consider extending the shared util to also return counts if divergence risk feels high at implementation |
| Fixed 0–100% y-axis makes rare-category bars unreadable | Med | Low | On-bar percent labels (agreed requirement); overview panel is an at-a-glance aid, per-figure CSV carries exact numbers |
| Combined overview panel too crowded for 14 axes | Med | Low | Grid layout with generous figure size; if unreadable, degrade to a paginated/summarised panel (noted, not blocking) |
| Task run before `mapping` (no real file) | Med | Low | `depends_on: [mapping]` in the workflow + CLI fail-fast pointing to the mapping task |
| Country/config mismatch surfaces `extra_categories` | Low | Low | Existing WARNING log path; not plotted (config is source of truth) |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — computation + I/O core + CLI | ~0.5–1 day | None |
| Phase 2 — registry + `per_country` dispatch | ~0.5 day | Phase 1 |
| Phase 3 — tests + docs | ~0.5 day | Phase 2 |

---

## References

- Brainstorm: `docs/development/brainstorms/real-population-stats-task.md`
- Reuse targets: `analysis/utils/marginals.py`, `analysis/utils/figures.py`,
  `analysis/fidelity/scheme.py`, `analysis/utils/registry.py`, `analysis/utils/country_config.py`
- Precedents: `scripts/analyze/map_populations.py` (per-country real file cache),
  `scripts/analyze/rank_models.py` (registry-consuming script template),
  `scripts/analyze/compare_real_countries.py` (real-only, `dispatch: cli` precedent)
- Contracts: `docs/development/gui.md` (task-naming + dispatch shapes),
  `config/analysis/analysis_registry.yaml`, `config/gui/flows/analysis_workflow.yaml`

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- CLAUDE.md
- config/analysis/analysis_registry.yaml
- config/gui/flows/analysis_workflow.yaml
- docs/architecture/commands.md
- docs/architecture/sub-packages.md
- docs/development/brainstorms/real-population-stats-task.md
- docs/development/gui.md
- docs/development/plans/active/real-population-reference-stats.md
- scripts/analyze/analyze_real_population_stats.py
- src/population_synthetic/analysis/real_population_stats/__init__.py
- src/population_synthetic/analysis/real_population_stats/artifacts.py
- src/population_synthetic/analysis/real_population_stats/charts.py
- src/population_synthetic/analysis/real_population_stats/csv_writer.py
- src/population_synthetic/analysis/real_population_stats/stats.py
- src/population_synthetic/gui/commands.py
- src/population_synthetic/gui/workflow_runner.py
- src/population_synthetic/gui/workflow_state.py
- tests/test_analysis_registry.py
- tests/test_real_population_stats.py
- tests/test_real_population_stats_integration.py
- tests/test_workflow_state.py
