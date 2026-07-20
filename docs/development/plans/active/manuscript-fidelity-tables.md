# Plan: Manuscript fidelity heatmap-tables (models + methods)

**Date:** 2026-07-20
**Author:** Basil
**Status:** In Progress
**Base Branch:** `dev`
**Branch:** `feature/manuscript-fidelity-tables`

---

## Overview

**What:** Two manuscript-grade heatmap-table figures for the LLM-population-fidelity paper,
rendered from the existing `model_ranking` performance JSON: (1) a **models** table (rows =
models at a single global-best strategy, columns = the demographic axes + Overall) and (2) a
**methods** table (rows = strategies, cells = mean across models). Both highlight the best cell
per column and are sorted by an Overall column.

**Why:** The primary manuscript message is "model X is best overall." The existing
`plot_performance_heatmap` is an internal viridis artifact showing every model×strategy combo — too
dense and not print-styled. These two focused tables carry the model story and the method story
cleanly, with hosted-vs-local provenance made visible.

**How:** Add the missing per-strategy × per-attribute aggregation to the builder JSON, derive
model hosting (local vs API) from config, and author two new pure-consumer renderers routed through
the shared `save_figure` (PNG + SVG). Wire both into `scripts/analyze/rank_models.py`.

## Problem Statement

The current `model_ranking` output has one heatmap (`plot_performance_heatmap`): rows = every
model×strategy combo, viridis, data-driven color scale, PNG only. For the manuscript we need:
- **Focused rows** — models at one comparable strategy (not the full combo cross-product), and a
  separate strategies view.
- **Provenance visible** — which models are hosted/API vs local (Ollama).
- **Best-per-column highlighting** and **Overall-sorted rows** to make "model X wins" scannable.
- **Vector output (SVG)** for print, plus grayscale/colorblind consideration.

Two data gaps block this today:
1. No per-strategy × per-attribute mean exists in the JSON (only a flat per-strategy pooled sample).
2. Model hosting (local vs API) is not surfaced anywhere the charts can read, and there is no
   config that groups the four `provider` values into `local`/`hosted`.

## Goals

### In Scope
1. A **models** heatmap-table: rows = models at the single global-best strategy, columns = the
   country's demographic axes + Overall; cell = TV-similarity; best cell per column highlighted;
   rows sorted by Overall; **dual sequential colormaps** encoding hosting (hosted vs local).
2. A **methods** heatmap-table: rows = strategies, columns = same axes + Overall; cell = mean over
   models of that strategy's per-axis TV-similarity; best cell per column highlighted; rows sorted
   by Overall; single sequential colormap (no provenance split).
3. Config-sourced hosting classification (`provider` → `local`/`hosted`), fail-fast on unknown.
4. Both figures emitted as PNG + SVG via the shared `save_figure` helper.
5. Wire both into `rank_models.py` so they regenerate on every ranking run.

### Out of Scope
- Changing or restyling the existing `plot_performance_heatmap` / leaderboard / scatter charts.
- Italy-specific styling work (renderers must run for any country, but manuscript target is Sweden).
- Blending coherence / C2ST into the Overall column — metric is locked to TV-similarity.
- Any manuscript LaTeX/PPTX propagation (a separate `sync-manuscript` concern).
- GUI Flow Runner exposure of a new flag.

## Success Criteria

- [ ] Running `python scripts/analyze/rank_models.py --country swedish` writes
      `03_Analysis/model_ranking/swedish_models_table.png` + `.svg` and
      `swedish_methods_table.png` + `.svg`.
- [ ] Models table: one row per model, all at the same (global-best) strategy; rows sorted by
      Overall descending; each column's maximum cell is rendered bold + boxed.
- [ ] Models table: hosted models use one hue family, local (Ollama) models use a different hue
      family; cell darkness is comparable across families (shared normalization).
- [ ] Methods table: one row per strategy; cell = mean across models of that strategy/attribute
      TV-similarity; Overall column = mean across that strategy's per-attribute means; best cell per
      column bold + boxed; rows sorted by Overall descending.
- [ ] `provider_hosting` config missing/unknown-provider raises loudly (no silent default).
- [ ] `pytest` passes, including new tests for the methods-matrix aggregation and hosting classifier.
- [ ] `ruff check src/` clean.

## Definitions

- **TV-similarity:** `1 - tv_distance` for a given attribute, as already stored on
  `ComboPerformance.tv_similarity[attr]` and `combos[slug].per_attribute[attr].tv_similarity`.
- **Overall (a row's):** mean of that row's per-attribute TV-similarities, NaN attributes excluded.
  For a model row this is `combos[slug].overall.tv_similarity_mean`; for a method row it is the mean
  over models of per-attribute means (computed in the new `methods_matrix`).
- **Global-best strategy:** the strategy maximizing the mean-over-models Overall TV-similarity —
  i.e. `argmax` over strategies of the methods-matrix Overall column. Applied uniformly to every
  model row in the models table (apples-to-apples).
- **Hosting / provenance:** a model is **local** iff its `model_config.provider == "ollama"`;
  otherwise **hosted** (API). The grouping of each provider string into `local`/`hosted` is read
  from config, not hardcoded in Python.
- **Best cell per column:** the row index with the maximum finite TV-similarity in that column
  (ties → first in row order). Rendered bold + a drawn rectangle border. Applied per attribute
  column and to the Overall column.
- **Manuscript-grade:** distinct renderer from the internal viridis heatmap; vector (SVG) output,
  print-oriented sizing/annotation, sequential (not rainbow) colormaps.

---

## Technical Design

### Approach

Keep aggregation in the **builder** (JSON is the single serialized contract) and keep the new
**charts as pure consumers** of `result`, mirroring the existing separation where
`plot_performance_heatmap` reads only the built dict. Two data additions flow into `result`:

1. `metadata.model_hosting`: `{model_id: "local"|"hosted"}`, derived from each model's
   `model_config.provider` via a config map. Computed in `rank_models.py` (which already calls
   `discover_axis_values("models")` and has the parsed YAML dicts) and passed into the builder so it
   is embedded in the JSON.
2. `methods_matrix`: per-strategy × per-attribute mean TV-similarity across models, plus a per-
   strategy Overall. Computed in the builder directly from `records`.

The two renderers live in a **new module** `analysis/model_ranking/manuscript_tables.py` to keep
manuscript styling separate from the internal `charts.py` (the brainstorm explicitly rejected
restyling `plot_performance_heatmap` in place). They reuse existing conventions: deferred
`matplotlib.use("Agg")`, NaN→grey via masked arrays, Overall-divider `axvline`, `dpi=150`,
`plt.close` on every path — but save via `save_figure` for the PNG+SVG pair.

Provenance is a **shared normalization + two colormaps** problem: compute one `Normalize(vmin, vmax)`
over all finite cells, then color each row's cells with `Blues` (hosted) or `Oranges` (local)
evaluated at `norm(value)`. Darkness therefore encodes score comparably; hue family encodes hosting.
Numeric annotations and the bold+box best-cell markers make cross-family reading unambiguous even
where two sequential ramps are hard to compare by eye.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| New `manuscript_tables.py` module | Separates manuscript vs internal styling; no regression risk to existing charts | One more file | **Chosen** |
| Restyle `plot_performance_heatmap` in place | Less code | Couples internal + manuscript needs; brainstorm rejected it | Rejected |
| Provenance via in-code `id.startswith("ollama_")` | No new config | Violates no-hardcoded-config; brittle to new providers | Rejected |
| Provenance via new `hosting:` key on all 20 model YAMLs | Fully explicit per model | Touches 20 files; redundant with `provider` | Rejected |
| One small `provider_hosting.json` map (provider→class) | Single source of truth; fail-fast; extensible | New config file | **Chosen** |
| Methods-matrix aggregation in the chart | Fewer builder changes | Aggregation logic hidden in a renderer; not serialized/testable | Rejected |
| Methods-matrix as a builder block in `result` | JSON-serialized, unit-testable, charts stay pure | Builder change | **Chosen** |
| Dual colormap by hosting (chosen encoding "A") | Score gradient + provenance in one channel | Cross-family score comparison harder in grayscale | **Chosen** (mitigated by numbers + bold/box) |

### Architecture & Module Contracts

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `config/analysis/model_ranking/provider_hosting.json` | Declare provider→`local`/`hosted` grouping | (static) → JSON map | model ids, charts, countries |
| `model_ranking/hosting.py` (new) | Classify each model as local/hosted from config | `model_yaml_dicts`, `hosting_config` → `{model_id: "local"\|"hosted"}` | matplotlib, attribute lists, ranking |
| `model_ranking/builder.py` (edit) | Also emit `methods_matrix` + embed `metadata.model_hosting` | `records, attributes, model_hosting?` → `result` dict | colormaps, figure sizing, hosting *rules* (receives the map) |
| `model_ranking/manuscript_tables.py` (new) | Render the two manuscript tables | `result, out_path` → `Path\|None` (+ SVG sibling) | how hosting was derived, how methods_matrix was aggregated, file discovery |
| `scripts/analyze/rank_models.py` (edit) | Load hosting config, build map, call builder + 2 renderers | CLI args → written PNG/SVG paths | colormap internals, aggregation math |

```
config/analysis/model_ranking/provider_hosting.json      # {"ollama":"local","claude":"hosted",...}
src/population_synthetic/analysis/model_ranking/
  hosting.py             # classify_hosting(model_dicts, hosting_config) -> dict[str,str]
  builder.py             # + methods_matrix, + metadata.model_hosting  (edit)
  manuscript_tables.py   # plot_model_fidelity_table(result, out) ; plot_method_fidelity_table(result, out)
scripts/analyze/rank_models.py                            # wire config + 2 new chart calls (edit)
```

Chart function signatures (mirroring existing `plot_*` contract — return `Path | None`):
```python
def plot_model_fidelity_table(result: dict[str, Any], out_path: str | Path) -> Path | None
def plot_method_fidelity_table(result: dict[str, Any], out_path: str | Path) -> Path | None
```
Builder edit (keeps existing call working; new arg optional):
```python
def build_performance_comparison(records, attributes, *, skipped=None,
                                 model_hosting: dict[str, str] | None = None) -> dict[str, Any]
```
`result["methods_matrix"]` shape:
```json
{ "attributes": ["age_group", ...],
  "strategies": ["all_pick", ...],
  "cells": { "all_pick": { "age_group": 0.91, ..., "overall": 0.84 }, ... } }
```

### Global-best-strategy rule (locked)
`argmax` over strategies of `methods_matrix.cells[strategy].overall`. Ties broken by
`STRATEGY_COMPLEXITY_ORDER` (prefer the simpler strategy). The chosen strategy id is written into the
models-table title and returned/logged so the manuscript caption can cite it.

---

## Implementation Plan

### Phase 1: Data — hosting classification + methods matrix
**Goal:** All data the renderers need is present in `result`, config-sourced and unit-tested. No
charts yet.

**Started:** 2026-07-20
**Completed:** 2026-07-20

- [x] Task 1.1 — Add `config/analysis/model_ranking/provider_hosting.json` mapping every known
      provider (`ollama, claude, gemini, openrouter, openai_compat`) to `local`/`hosted`
      (`ollama` → `local`, rest → `hosted`).
- [x] Task 1.2 — New `model_ranking/hosting.py`: `load_hosting_config(path)` (fail-fast if missing
      /malformed) and `classify_hosting(model_dicts, hosting_config) -> {model_id: class}`, reading
      `model_config.provider`; raise loudly on a provider absent from the config map.
- [x] Task 1.3 — In `builder.py`, add a `_methods_matrix(records, attributes)` helper: for each
      strategy, for each attribute, mean over models of `r.tv_similarity.get(attr)` (skip NaN/missing);
      Overall = mean of that strategy's per-attribute means. Attach as `result["methods_matrix"]`.
- [x] Task 1.4 — Extend `build_performance_comparison` with optional `model_hosting` kwarg; write it
      to `result["metadata"]["model_hosting"]` (default `{}` when not supplied — existing callers
      unaffected).

**Files Modified:**
- `config/analysis/model_ranking/provider_hosting.json` — new config map.
- `src/population_synthetic/analysis/model_ranking/hosting.py` — new classifier.
- `src/population_synthetic/analysis/model_ranking/builder.py` — methods_matrix + metadata.model_hosting.

**Dependencies:** None

### Phase 2: Renderers — two manuscript tables
**Goal:** Pure-consumer renderers producing PNG+SVG from `result`.

**Started:** 2026-07-20
**Completed:** 2026-07-20

- [x] Task 2.1 — `manuscript_tables.py` scaffold: deferred Agg import, shared helpers for the
      Overall divider, cell text color threshold, and the **bold+box best-per-column** marker
      (`ax.add_patch(Rectangle(...))` + bold text on the column argmax, per attribute column and Overall).
- [x] Task 2.2 — `plot_model_fidelity_table`: pick global-best strategy from `methods_matrix`; filter
      `combos` to that strategy → one row per model; sort rows by `overall.tv_similarity_mean`;
      build values array (attributes + Overall); shared `Normalize` over finite cells; color rows by
      `metadata.model_hosting` using two sequential colormaps (hosted vs local); NaN→grey; annotate;
      best-per-column bold+box; title cites the chosen strategy; `save_figure(..., dpi=150)`.
- [x] Task 2.3 — `plot_method_fidelity_table`: rows = strategies from `methods_matrix.cells` sorted
      by `overall` desc; single sequential colormap; NaN→grey; annotate; best-per-column bold+box;
      `save_figure(..., dpi=150)`.
- [x] Task 2.4 — Return `None` on empty/all-NaN input (match existing chart contract); `plt.close`
      on every return path (handled by `save_figure`, but guard early returns before a fig exists).

**Files Modified:**
- `src/population_synthetic/analysis/model_ranking/manuscript_tables.py` — new renderers.

**Dependencies:** Phase 1

### Phase 3: Wiring
**Goal:** Tables regenerate on every ranking run.

**Started:** 2026-07-20
**Completed:** 2026-07-20

- [x] Task 3.1 — In `rank_models.py`, load `provider_hosting.json`, build `model_hosting` from the
      `discover_axis_values("models")` dicts (via `classify_hosting`), and pass it into
      `build_performance_comparison`.
- [x] Task 3.2 — Import and call `plot_model_fidelity_table` and `plot_method_fidelity_table` inside
      the `if not args.no_charts:` block, writing `{country}_models_table.png` and
      `{country}_methods_table.png`; add the `is not None` print guards.
- [x] Task 3.3 — Update the module docstring output list (rank_models.py header) to mention the two
      new artifacts (PNG+SVG each).

**Files Modified:**
- `scripts/analyze/rank_models.py` — config load, builder arg, two chart calls, docstring.

**Dependencies:** Phase 2

---

## Testing Plan

### Unit Tests
- [x] `classify_hosting` maps a `provider: ollama` dict → `local`, a `claude`/`gemini`/`openrouter`
      dict → `hosted`.
- [x] `classify_hosting` / `load_hosting_config` raise on an unknown provider and on a missing config
      file (fail-fast).
- [x] `_methods_matrix` computes the correct per-strategy per-attribute mean across a small synthetic
      `records` set, excludes NaN attributes, and the per-strategy Overall equals the mean of its
      per-attribute means.
- [x] `build_performance_comparison` embeds `metadata.model_hosting` when supplied and defaults to
      `{}` when not (backward compat).

### Integration Tests
- [x] From a built `result` fixture, `plot_model_fidelity_table` returns a `Path`, and both `.png`
      and `.svg` exist; row count == number of distinct models; the strategy cited in the title is the
      methods-matrix Overall argmax.
- [x] `plot_method_fidelity_table` returns a `Path`; row count == number of strategies; both formats
      written; rows are Overall-sorted.

### Manual Verification
- [x] Run `python scripts/analyze/rank_models.py --country swedish`; open the four new files; confirm
      hosted vs local hue families, bold+boxed column winners, Overall-sorted rows, correct axis
      labels (14 SCB axes + Overall). (2026-07-20: script run with `--force` over the live
      `03_Analysis/` outputs; all four files — `swedish_models_table.{png,svg}` and
      `swedish_methods_table.{png,svg}` — written.)
- [ ] Sanity-check the models table's Overall winner against the existing leaderboard's top model at
      the chosen strategy.

### Edge Cases
- [x] A model row whose combo is missing at the global-best strategy (strategy not run for that
      model) → row omitted (documented) rather than a crash or a NaN row.
- [ ] An attribute that is NaN for all rows in a column → grey column, no best-cell box drawn.
- [ ] Only one strategy present → methods table has one row; global-best strategy trivially that one.
- [ ] A country with no local (Ollama) models → models table uses only the hosted colormap (no error).

---

## Documentation Plan

- [x] Update `docs/architecture/commands.md` — note the two new `model_ranking` outputs.
- [x] Update `docs/architecture/configuration.md` — document `config/analysis/model_ranking/provider_hosting.json`.
- [x] Add a short note in the `model_ranking` section of the sub-packages wiki about the manuscript tables.
- [x] Update the brainstorm file status → Handed off (link this plan).
- [x] Inline docstrings on the two renderers describing the encoding (dual colormap, bold+box).

## Rollback Plan

1. The change is purely additive (new module, new config, new optional builder kwarg, new chart calls).
   To revert: delete `manuscript_tables.py`, `hosting.py`, `provider_hosting.json`; revert the
   `builder.py` and `rank_models.py` edits (git revert the feature commits).
2. **Data considerations:** none — no migrations. Existing JSON gains two additive keys; older
   consumers ignoring them are unaffected.
3. Existing charts and the `result` contract for them are untouched, so partial rollback is safe.

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Two sequential colormaps hard to compare in grayscale print | Med | Med | Numeric annotations + bold/box column winners carry the exact signal; pick colorblind-safe families (e.g. Blues/Oranges); revisit as a styling tweak if reviewers object |
| Global-best strategy differs from reader's expectation | Low | Med | Cite the chosen strategy in title + caption; rule is documented and deterministic |
| New provider added later without a hosting entry | Med | Low | Fail-fast raise names the missing provider; one-line config fix |
| Missing combos at the global-best strategy drop model rows silently | Low | Med | Log dropped models explicitly (no silent truncation, per engineering standard) |
| Scope creep into restyling existing charts | Low | Low | Out-of-scope stated; new module isolates changes |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 (data + config + tests) | ~half day | None |
| Phase 2 (two renderers) | ~1 day | Phase 1 |
| Phase 3 (wiring + docs) | ~2 hours | Phase 2 |

---

## References

- Brainstorm: `docs/development/brainstorms/fidelity-heatmap-tables.md`
- Existing template renderer: `src/population_synthetic/analysis/model_ranking/charts.py::plot_performance_heatmap`
- Shared save helper: `src/population_synthetic/analysis/utils/figures.py::save_figure`
- SVG dual-output rationale: `docs/development/plans/active/fidelity-radar-svg-export.md`
- Provider values: `src/population_synthetic/generators/synthetic/manifest_loader.py`

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- config/analysis/model_ranking/provider_hosting.json
- docs/architecture/commands.md
- docs/architecture/configuration.md
- docs/architecture/sub-packages.md
- docs/development/brainstorms/fidelity-heatmap-tables.md
- docs/development/plans/active/manuscript-fidelity-tables.md
- scripts/analyze/rank_models.py
- src/population_synthetic/analysis/model_ranking/builder.py
- src/population_synthetic/analysis/model_ranking/hosting.py
- src/population_synthetic/analysis/model_ranking/manuscript_tables.py
- tests/test_manuscript_tables.py
- tests/test_model_hosting.py
- tests/test_performance_builder.py
