# Plan: Figure Selection — publish chosen figures to `04_Figures`

**Date:** 2026-08-27 (revived 2026-08-27)
**Author:** Basil
**Status:** Completed (with open items)
**Completed:** 2026-09-16 18:48
**Base Branch:** `feature/publication-figure-presentation-layer`
**Branch:** `feature/figure-selection-04-figures`

---

## Overview

`03_Analysis` currently holds ~2,100 figures across 13 process folders, in six different
path shapes. A manuscript cites about a dozen of them and a deck uses a different two
dozen; today that selection is made by hand and staged outside the repo
(`Manuscripts/40_llm-population-fidelity-benchmark/figures selection/`), so the roster
lives nowhere version-controlled and nothing records which run produced a given image.

This plan adds `figure_selection`, the **terminal node of the analysis DAG**: a task that
computes nothing, draws nothing and reads a config-declared roster of figures, copying each
one — in all three published formats — out of `03_Analysis` into a sibling stage folder
`04_Figures`, under both its source filename and a manuscript figure number.

## Problem Statement

1. **The roster is not config.** Which figures the paper uses is a research decision made
   repeatedly and recorded only in a hand-curated OneDrive folder. It cannot be diffed,
   reviewed, or re-run after a fresh sweep.
2. **Re-running the analysis silently invalidates the staged copies.** A new sweep rewrites
   `03_Analysis` but not the staged folder; nothing detects the drift.
3. **No provenance.** Given `impossibility_forest.png` in the staged folder, nothing records
   which `output_base`, which country and which process wrote it, or when.
4. **Manual copying loses the vector siblings.** The presentation layer emits PNG + SVG + EPS
   for every figure; hand-copying takes the PNG, and the EPS — the one format all four target
   venues accept — is left behind.
5. **Figure numbers are nowhere.** The manuscript cites "Figure 3"; nothing in the repo maps
   that number to a file.

## Goals

### In Scope

1. A new registry-declared analysis process `figure_selection`, terminal in the DAG.
2. A second stage folder `04_Figures`, sibling of `03_Analysis`, with its literal defined
   exactly once — in the registry YAML, read only by `analysis/utils/registry.py`.
3. A config-declared roster, `config/analysis/figure_selection.yaml`, holding **named sets**
   (`manuscript`, `deck`, `supplementary`, …) selected at run time with `--set`.
4. Two parallel emissions of the same set: `as_generated/` (source filenames, traceable) and
   `numbered/` (`F01_`, `F02_`, … in citation order, from config).
5. All three formats per entry — PNG, SVG, EPS — with the format list sourced from
   `figures.OUTPUT_SUFFIXES`, not re-declared.
6. A provenance manifest per emitted set: source path, size, mtime, SHA-256, both
   destination names, plus the `output_base` and country the run resolved.
7. Fail-fast throughout: unknown set, unknown process id, missing figure, missing sibling
   format, duplicate figure number, colliding source basename — every one raises, naming
   what collided, and nothing partial is left on disk.

### Out of Scope

- **Drawing or modifying any figure.** This task copies bytes. It imports no chart module and
  makes no publication decision; it is downstream of the presentation boundary, not part of it.
- **Captions or caption text.** The roster carries a number and a slug, not prose.
- **Any change to `03_Analysis`.** The source tree is read-only to this task.
- **Syncing to OneDrive / the manuscript tree.** `04_Figures` is the deliverable; moving it
  onward stays manual.
- **Auto-discovering figures.** A figure enters a set because a human listed it.

---

## Design

### 1. The second stage folder

`config/analysis/analysis_registry.yaml` gains one top-level key beside `stage_dir`:

```yaml
stage_dir: "03_Analysis"
figures_stage_dir: "04_Figures"
```

`analysis/utils/registry.py` gains `FIGURES_STAGE_DIR`, loaded the same way as
`ANALYSIS_STAGE_DIR`. No literal enters Python.

**Contract change.** Every process entry currently must declare `folder`. A figures-stage
process owns the stage root itself and has no per-process subfolder, so the entry gains an
optional `stage:` key (`"analysis"` — the documented default when absent — or `"figures"`),
and `folder` becomes required **only** for analysis-stage processes. A figures-stage entry
that declares `folder` raises, as does an analysis-stage entry that omits it. `AnalysisProcess`
gains `stage: str = "analysis"`; `analysis_output_dir()` raises if called with a figures-stage
id, and a new `figures_output_dir()` serves that stage.

### 2. Output layout

```
04_Figures/
  {country}/
    {set}/
      as_generated/
        swedish_02_model_method_heatmap.{png,svg,eps}
        swedish_02_attrition_funnel.{png,svg,eps}
        impossibility_forest.{png,svg,eps}
      numbered/
        F01_model_method_heatmap.{png,svg,eps}
        F02_attrition_funnel.{png,svg,eps}
        F03_impossibility_forest.{png,svg,eps}
      _index.json
```

Country is the outermost level because two of the six source path shapes put the country in
the **directory** rather than the filename (`realism_ranking/{country}/impossibility_forest`),
so without it Sweden and Italy overwrite each other in `as_generated/`. Set sits above the
naming folders so that one purpose's figures stay together in both namings.

### 3. The selection config

`config/analysis/figure_selection.yaml`:

```yaml
sets:
  manuscript:
    - n: 1
      name: model_method_heatmap
      source: "model_ranking/{country}_model_method_heatmap"
    - n: 2
      name: attrition_funnel
      source: "validation_attrition/{country}_attrition_funnel"
    - n: 3
      name: impossibility_forest
      source: "realism_ranking/{country}/impossibility_forest"
    - n: 4
      name: radar_best_model
      source: "fidelity/{slug}/{slug}/{slug}_radar_tv"
      slug: {model: claude_sonnet, strategy: all_pick_v2}
```

- `source` is an **extension-less stem** relative to `03_Analysis`. Its first segment is a
  registry process id and is validated against the registry.
- Two placeholders. `{country}` is the run's country id. `{slug}` is available only when the
  entry declares a `slug:` block, and is composed through `manifest_loader.axis_slug` — the
  existing single source of truth for the slug format — so the roster stays portable across
  countries and can never disagree with the folder names the producing task wrote.
- `n` is the manuscript figure number and orders `numbered/`. `name` is its filename slug.
- Both are ignored by `as_generated/`, which takes the source stem verbatim.

Covering all six live path shapes with these two placeholders is the acceptance test for the
schema; the shapes are recorded in the Notes section below.

### 4. Validation (all fail-fast, all before any byte is copied)

| Condition | Behaviour |
|---|---|
| `--set` names an unknown set | raise, listing the known sets |
| `source`'s first segment is not a registry process id | raise, naming the id |
| `{slug}` used without a `slug:` block (or vice versa) | raise |
| a resolved stem has no `.png` on disk | raise, listing **every** missing entry, not the first |
| `.png` present but `.svg` or `.eps` missing | raise — a partial format set is never copied |
| two entries in a set share `n` | raise, naming both |
| two entries resolve to the same `as_generated` basename | raise, naming both sources |
| destination holds files this task did not write | warn, list them, copy anyway |

The whole set is resolved and validated first; the copy phase runs only if every entry
passed, so a failing run leaves `04_Figures` untouched.

### 5. Re-runs

The task overwrites the files it is about to write. Files in the destination that are not in
the current `_index.json` are reported at WARNING and left alone — they are usually a
previous, larger set. `--force` clears the set's two naming folders first, so a shrinking
roster leaves nothing stale behind.

### 6. DAG position and dispatch

Registry entry: `dispatch: "per_country"` — the roster is per country, and model/strategy
ticks are irrelevant (combo-specific entries pin their own slug).

Workflow `depends_on` lists the figure-producing tasks **that are enabled in the workflow**:

```
fidelity, model_ranking, method_significance, real_population_stats,
generation_metadata, persona_realism, realism_ranking, validation_attrition,
cost_efficiency
```

`multivariate_fidelity`, `consistency` and `pairwise_comparison` also draw figures but ship
`enabled: false`, and `cross_country` is not in the workflow at all. Depending on them would
park this node at `SKIPPED_DEP` forever — the trap `CLAUDE.md` already documents for
`generation_metadata`. They are deliberately omitted: `depends_on` provides ordering only,
and the real guard is the missing-file check, which raises naming the figure if a set cites
one of them and it was never produced.

The node ships `enabled: false` — a sweep should not fail at the last step because the
roster has not been curated yet — with `supports_force: true`.

---

## Implementation Steps

### Phase 1: The stage folder and the registry contract

- [x] 1.1 — Add `figures_stage_dir: "04_Figures"` to `analysis_registry.yaml`, documented in
      its header block beside `stage_dir`.
- [x] 1.2 — `registry.py`: load it into `FIGURES_STAGE_DIR`; add `stage` to `AnalysisProcess`
      (default `"analysis"`); make `folder` conditionally required; raise on a figures-stage
      entry that declares `folder` and on an unknown `stage` value.
- [x] 1.3 — Add `figures_output_dir(output_base, *, country, set_name, naming)`; make
      `analysis_output_dir` raise when handed a figures-stage id.
- [x] 1.4 — Tests: both stage literals resolve from config; a figures-stage entry without
      `folder` loads; one with `folder` raises; `analysis_output_dir` on a figures-stage id
      raises; the 17 existing processes are unaffected.

### Phase 2: The selection config and its loader

- [x] 2.1 — Write `config/analysis/figure_selection.yaml` with the `manuscript` set populated
      from the figures currently staged in the OneDrive selection folder.
- [x] 2.2 — `analysis/figure_selection/config.py`: load, validate and materialise
      `FigureEntry` / `FigureSet` dataclasses. Every failure mode in the table above raises
      here, before any filesystem work.
- [x] 2.3 — `analysis/figure_selection/resolve.py`: stem + country (+ optional slug block) →
      the three concrete source paths, via `figures.OUTPUT_SUFFIXES` and
      `manifest_loader.axis_slug`.
- [x] 2.4 — Unit tests over all six live path shapes, plus each raise path.

### Phase 3: The copier and the manifest

- [x] 3.1 — `analysis/figure_selection/export.py`: resolve-all → validate-all → copy, emitting
      both namings.
- [x] 3.2 — Write `_index.json`: per entry `n`, `name`, source stem, resolved source paths,
      byte sizes, mtimes, SHA-256, both destination filenames; plus `output_base`, country,
      set name and run timestamp at the top level.
- [x] 3.3 — Unwritten-file warning; `--force` clearing.
- [x] 3.4 — Integration test over a fixture `03_Analysis` tree: both namings emitted, three
      formats each, manifest round-trips, and a failing entry leaves the destination untouched.

### Phase 4: Script and wiring

- [x] 4.1 — `scripts/analyze/select_figures.py`: `--country-id` (repeatable), `--set`,
      `--output-base`, `--force`. Docstring in the house style of the other analyze scripts.
- [x] 4.2 — Registry entry `figure_selection` (`stage: figures`, `dispatch: per_country`,
      script path, label, description).
- [x] 4.3 — Workflow entry: `enabled: false`, `supports_force: true`, `depends_on` as listed
      above, options `{set: manuscript, output-base: }`.
- [x] 4.4 — Update `analysis_workflow.layout.json` with the new node's position.
- [x] 4.5 — GUI smoke test: the node renders, its dependencies resolve, and `--set` reaches
      the command vector.

### Phase 5: Live run and documentation

- [x] 5.1 — Run against the live `swedish_02` tree; confirm every entry in `manuscript`
      resolves and all three formats land.
- [x] 5.2 — Update `CLAUDE.md`: the second stage folder, the terminal DAG node, and the
      conditional-`folder` registry contract.
- [x] 5.3 — Update `docs/architecture/sub-packages.md` and `docs/architecture/configuration.md`.
- [x] 5.4 — Update `docs/development/figure-conventions.md` with how a figure gets a number
      and how `04_Figures` is produced.

---

## Testing Plan

### Unit
- [x] Registry: both stage literals; conditional `folder`; every new raise path.
- [x] Config loader: unknown set; non-registry process id; duplicate `n`; colliding basename;
      `{slug}` without a `slug:` block.
- [x] Resolver: all six live path shapes resolve to three existing paths in a fixture tree.
- [x] Format list is `figures.OUTPUT_SUFFIXES`, not a local literal.

### Integration
- [x] A full set copies into both namings with all three formats and a valid `_index.json`.
- [x] One missing `.eps` aborts the whole run and leaves `04_Figures` byte-identical.
- [x] `--force` removes a figure dropped from the roster; without it the file survives and is
      reported.
- [x] Two countries into one `04_Figures` do not collide.

### Manual
- [x] Live `swedish_02` run; the 19-entry `manuscript` set published 114 files (19 x 3 formats x 2
      namings) and the EPS files carry the presentation layer's own bounding boxes.
- [ ] GUI: node appears last, unlocks only after its nine upstreams, and honours `bypass`.

### Edge cases
- [x] A set of one figure.
- [x] An entry citing a disabled process (`consistency`) — must raise naming the figure, not
      the process.
- [x] A country whose analysis was never run — raises on the first entry, copies nothing.

---

## Notes

The six live path shapes in `03_Analysis`, which the two placeholders must cover:

| Shape | Example |
|---|---|
| `{proc}/{country}_{name}` | `model_ranking/swedish_02_model_method_heatmap` |
| `{proc}/{country}/{name}` | `realism_ranking/swedish_02/impossibility_forest` |
| `{proc}/{country}/{slug}/{name}` | `persona_realism/swedish_02/{combo}/typicality` |
| `{proc}/{slug}/{slug}/{slug}_{attr}` | `fidelity/{combo}/{combo}/{combo}_age_group` |
| `{proc}/charts/{combo}/{name}` | `generation_metadata/charts/{combo}/latency_by_category` |
| `{proc}/{country}_{sub}/{model}/{attr}` | `method_significance/swedish_02_marginal_progression/claude_haiku/age_group` |

Two of those six shapes carry a segment that is **not** a placeholder, resolved in
Phase 2 by writing it out as a literal (a stem is a template; a literal segment is its
default, and both segments are country-independent so nothing is lost):

- `method_significance/{country}_marginal_progression/claude_haiku/{attr}` — the model
  is a research decision about which panel is published, so the roster records it.
- `generation_metadata/charts/{strategy}_{model}/{name}` — that folder is keyed
  `{strategy}_{model}` with **no country in it**, so it is not an axis slug at all and
  `{slug}` (which is `axis_slug`, `{country}_{strategy}_{model}`) does not describe it.
  Two countries' generation-metadata charts therefore share one folder upstream; that
  is the producing task's convention, not this one's, and is left untouched.

Figure counts on the live tree (PNG): fidelity 1219, generation_metadata 578,
method_significance 187, persona_realism 117, real_population_stats 15, the remaining
processes single digits.

## Rollback

Additive throughout. Reverting means deleting the new package, script, config and the two
registry/workflow entries; the only edit to existing code is the conditional-`folder` rule in
`registry.py`, which no current process exercises.

## Modified Files

- `config/analysis/analysis_registry.yaml`
- `config/analysis/figure_selection.yaml` *(new)*
- `config/gui/flows/analysis_workflow.yaml`
- `config/gui/flows/analysis_workflow.layout.json` *(git-ignored operator state -- `.gitignore` excludes `*.layout.json`, so the new node's position is a working-tree change only)*
- `scripts/analyze/select_figures.py` *(new)*
- `src/population_synthetic/analysis/figure_selection/__init__.py` *(new)*
- `src/population_synthetic/analysis/figure_selection/config.py` *(new)*
- `src/population_synthetic/analysis/figure_selection/resolve.py` *(new)*
- `src/population_synthetic/analysis/figure_selection/export.py` *(new)*
- `src/population_synthetic/analysis/utils/registry.py`
- `src/population_synthetic/utils/atomic_io.py` *(gains `atomic_copy_file`, the binary sibling of `atomic_write_text`, so a published figure is never a truncated one)*
- `tests/test_figure_selection.py` *(new)*
- `tests/test_analysis_registry.py`
- `tests/test_workflow_state.py` *(the shipped-DAG ordering assertions gain the terminal node)*
- `CLAUDE.md`
- `docs/architecture/sub-packages.md`
- `docs/architecture/configuration.md`
- `docs/development/figure-conventions.md`