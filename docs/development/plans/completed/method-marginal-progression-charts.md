# Plan: Per-Method Marginal Progression Charts

**Date:** 2026-07-20
**Author:** Basil
**Status:** Completed
**Completed:** 2026-07-22 15:50
**Base Branch:** `dev`
**Branch:** `feature/method-marginal-progression-charts`

---

## Overview

Add a descriptive chart family to the analysis pipeline that, for each **(country, model)**
combination, emits **one grouped-bar figure per demographic attribute** showing per-category
proportions for the **real statistical baseline (e.g. SCB)** overlaid with **each of the 5
generation methods** (strategies), ordered by increasing complexity. The purpose is to read off,
per attribute, which method's proportions sit closest to the real distribution and how the
proportions shift across the method progression.

## Problem Statement

The pipeline currently answers *how well* and *where* a (model, method) combo matches the real
statistics only through **summary scalars** (TV distance, KL, chi-squared p) and their derived
significance tests. It never surfaces the **raw per-category proportions** side by side: the
fidelity evaluator computes the proportion vectors `q_a` (real) and `q_b` (synthetic) internally
but discards them before writing the report (`evaluator.py` `marginals_clean` projection). As a
result there is no artifact that lets a reader visually compare, for a fixed model, the real
baseline against all 5 methods on a single attribute and see the method-complexity trend in the
actual distribution. This plan produces exactly that view.

## Goals

### In Scope
1. A new grouped-bar chart: one figure per **(country, model, attribute)**, with the category
   values on the x-axis, proportion on the y-axis, and **6 series** — the real baseline plus the 5
   methods in `STRATEGY_COMPLEXITY_ORDER`.
2. Recompute per-category proportions from the **mapped population files** (real + each combo),
   using the config-driven category axis of the **same mapping tier** the combos were scored
   against.
3. Country-agnostic implementation: iterate over whatever countries the mapping index contains
   (Sweden today; others automatically when their mapped data exists).
4. Place the plotting + orchestration inside the `method_significance/` subpackage; place the pure
   proportion-math in a shared `analysis/utils/` helper.
5. Emit PNG **and** SVG (via the shared `save_figure` helper), matching repo chart conventions.

### Out of Scope
- Any per-individual "confusion matrix" (true-vs-predicted). Impossible under the current free,
  unseeded generation contract — no per-person ground-truth label exists. Explicitly rejected
  earlier in design.
- New statistics or significance tests. This is a **descriptive** view only; no p-values.
- Changing the generation pipeline, the fidelity report schema, or the mapping stage.
- A new GUI workflow task or a new `analysis_registry.yaml` process id (the charts land under the
  existing `method_significance` output folder).
- Line-chart / stacked variants. Grouped bars only (with the existing horizontal-bar fallback for
  high-cardinality attributes).

## Success Criteria

- [ ] Running the method-significance analysis for Sweden produces, per model, one PNG+SVG per
      analyzed attribute under the method-significance output folder.
- [ ] Each figure shows 6 series (real baseline + 5 methods) at every category value, methods
      ordered simplest→most complex, baseline visually distinct.
- [ ] The x-axis category set and order come from `scheme_category_values(country)` (config), not
      from code; a category absent from a population renders as an explicit `0.0` bar.
- [ ] A method with no mapped population for a (country, model) is skipped for that series and the
      omission is logged — never fabricated or silently zero-filled.
- [ ] High-cardinality attributes fall back to horizontal bars (reusing the existing
      `_HIGH_CARDINALITY_FIELDS` convention).
- [ ] Proportions math lives in `analysis/utils/` and is unit-tested independently of plotting.
- [ ] `ruff check src/` is clean; new unit tests pass under `pytest`.

## Definitions

- **Method / strategy:** one of the 5 canonical generation strategies in
  `STRATEGY_COMPLEXITY_ORDER` (`all_pick`, `all_pick_dag`, `all_generate_pick`,
  `all_generate_evaluate_pick`, `all_generate_evaluate_random_pick`), simplest→most complex.
- **Baseline / real:** the mapped real statistical population `mapping/real_{country}.json`
  (SCB for Sweden). Rendered as the first, visually distinct series.
- **Proportion:** for an attribute, `count(category) / total_non_null` over a population's
  `individuals` list — the same definition the fidelity evaluator uses.
- **Category axis:** the ordered, DB-exact category levels for an attribute from
  `scheme_category_values(country)` of the mapping tier the combos were scored against. A category
  with zero occurrences is a real `0.0` bar (distinct from a category absent from the scheme axis).
- **Combo:** a `(country, strategy, model)` triple; on disk `mapping/{slug}.json` where
  `slug = {country}_{strategy}_{model}`, decoded via `decompose_slug`.
- **Missing cell:** a (country, model, method) with no mapped population file — that method's series
  is omitted for that figure and logged; never zero-filled.

---

## Technical Design

### Approach

Split the feature along the existing architectural seam so the `method_significance` package's
"never recomputes statistics from populations" contract is bent as little as possible:

- **Pure math → `analysis/utils/`.** Promote the per-category proportion computation (today the
  private `_compute_proportions` in `fidelity/charts.py`) into a shared, chart-agnostic,
  country-agnostic helper. It knows nothing about files, countries, strategies, or matplotlib.
- **Population-reading orchestration + plotting → `method_significance/`.** A new module loads the
  mapped populations for a country (real baseline + each combo), assembles the 6-series structure
  per (model, attribute) using the shared math + config-driven category ordering + the strategy
  complexity order, and draws grouped-bar figures via a pure plotting function. This is the
  deliberate, contained departure from the package's report-only input contract; its `__init__.py`
  docstring is updated to record it.

Grouped-bar drawing mirrors the proven `fidelity/charts.py::plot_comparison_charts` conventions,
generalized from 2 series to 6.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Split: math in `utils/`, orchestration+plot in `method_significance/` | Honors requested placement; pure math reusable & testable; contained contract bend | `method_significance` driver now reads populations (documented) | **Chosen** |
| New sibling subpackage `analysis/marginal_progression/` (+ registry id) | Fully honors the report-only contract; cleanest layering | More scaffolding; not "inside method_significance" as requested | Rejected |
| Drop straight into `method_significance/`, no split | Least wiring | Silently erodes the package's stated invariant; couples math to plotting | Rejected |
| Reshape from existing fidelity report JSON | No population read | Impossible — per-category proportions are discarded before the report is written | Rejected (infeasible) |

### Architecture & Module Contracts

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `analysis/utils/marginals.py::compute_proportions` | Per-category proportion vector for one attribute over one population | `(individuals: list[dict], attr: str, categories: list[str]) → dict[str, float]` | matplotlib, countries, strategies, file paths, real-vs-synthetic |
| `method_significance/marginal_charts.py::load_marginal_series` | Read mapped populations for a country, build the 6-series structure per (model, attribute) | `(country, output_base, mapping_tier) → prepared: dict[model][attr] → list[(series_label, dict[cat,float])]` | matplotlib, figure styling |
| `method_significance/marginal_charts.py::plot_marginal_progression` | Pure sink: draw grouped-bar figures from prepared data | `(prepared, country, out_dir) → list[Path]` | how proportions were computed, file loading |
| `analyze_method_significance.py` (driver) | Wire load → plot into the existing per-country run | orchestration only | proportion math, drawing details |

```
src/population_synthetic/analysis/
  utils/
    marginals.py            # NEW: compute_proportions (pure)
  method_significance/
    __init__.py             # EDIT: docstring notes the descriptive-marginal path reads populations
    marginal_charts.py      # NEW: load_marginal_series + plot_marginal_progression
    charts.py               # (reuse _COLOR_SERIES, _HIGH_CARDINALITY_FIELDS conventions)
scripts/analyze/
  analyze_method_significance.py  # EDIT: call the new load+plot per country
```

**Reused, do not reinvent:**
- `analysis/utils/figures.py::save_figure` — PNG + SVG sibling, dpi 150, `Agg`, closes figure,
  returns `Path`.
- `model_ranking/loader.py::scheme_attributes(country)` / `scheme_category_values(country)` —
  config-driven attribute iteration and category ordering.
- `analysis/utils/axes.py::STRATEGY_COMPLEXITY_ORDER` + `decompose_slug` — series order and slug
  decode.
- `mapping` stage index (`mapping/_index.json`) + `mapping/real_{country}.json` /
  `mapping/{slug}.json` — the population source (same enumeration `load_combo_performances` uses,
  but opening populations instead of reports).
- `method_significance/charts.py::_COLOR_SERIES` (7 colors, covers 6 series) and
  `_HIGH_CARDINALITY_FIELDS` (horizontal-bar fallback).
- Grouped-bar template `fidelity/charts.py::plot_comparison_charts` (figsize, bar width 0.35,
  `ylim(0,1)`, xtick rotation, edgecolor).

**Output location & naming:** under `analysis_output_dir("method_significance", output_base)`,
subfolder `{country}_marginal_progression/{model}/{attr}.png` (+ `.svg` sibling from `save_figure`).

### Applicable engineering principles (from data-pipeline-engineering guides)

- **Visualization as a pure sink** (02 §9): `plot_marginal_progression` takes finished data, writes
  files, returns paths; returns nothing for a genuinely empty attribute. Recompute is a separate
  step from draw.
- **matplotlib global state** (02 §9): `Agg` backend, explicitly close every figure (via
  `save_figure`).
- **Config once at the edge** (02 §7): attribute list + category axis from the country scheme; no
  in-code attribute/category literals.
- **"zero" vs "absent"** (03 §6): zero-count category → explicit `0.0` bar; scheme defines the axis;
  surface (log) unmapped/extra categories rather than dropping silently.
- **Error boundaries** (02 §8): missing required real baseline → fail loud with context; missing
  method cell → explicit logged skip.
- **Determinism** (03 §2): no RNG in this chart; if any is added later, seed it.
- **DRY / OCP** (05): reuse proportions + scheme-ordering + save helpers; add as additive functions,
  don't rewrite existing plotters. Refactor `fidelity/charts.py::_compute_proportions` to delegate
  to the new shared helper (keeps a single definition).

---

## Implementation Plan

### Phase 1: Shared proportions helper
**Started:** 2026-07-20 · **Completed:** 2026-07-20
**Goal:** One authoritative, tested per-category proportion function in the utils layer.

- [x] Task 1.1 — Create `analysis/utils/marginals.py` with
      `compute_proportions(individuals, attr, categories) -> tuple[dict[str, float], list[str]]`:
      uses `attr_value` for extraction, counts non-null, returns proportion per requested category
      (explicit 0.0 for absent / all-null), and returns + logs categories seen in data but not in
      `categories` (surfaced, not dropped). Fails loud (`TypeError`) on a `None` axis.
- [x] Task 1.2 — Refactor `fidelity/charts.py::_compute_proportions` to delegate to the new helper
      (single definition; behavior unchanged — the private adapter passes the observed category set
      as the axis and returns the proportions dict).
- [x] Task 1.3 — Unit tests for the helper (normal, zero-count category, all-null attribute,
      extra/unmapped category surfacing, `None`/empty axis, `age_group` derivation).

**Files Modified:**
- `src/population_synthetic/analysis/utils/marginals.py` — NEW helper.
- `src/population_synthetic/analysis/fidelity/charts.py` — delegate to helper.
- `tests/test_marginals.py` — NEW unit tests.

**Dependencies:** None

### Phase 2: Data prep + plotting in method_significance
**Started:** 2026-07-20 · **Completed:** 2026-07-20
**Goal:** Build the 6-series structure from mapped populations and draw the grouped-bar figures.

- [x] Task 2.1 — `marginal_charts.py::load_marginal_series(country, output_base, mapping_tier)`:
      walk `mapping/_index.json`, `decompose_slug` each combo, load `mapping/real_{country}.json`
      (baseline, fail loud if absent) and each combo `{slug}.json`, and assemble
      `prepared[model][attr] = [("real", props), (method_1, props), ...]` ordered by
      `STRATEGY_COMPLEXITY_ORDER`, using the scheme (of the passed `mapping_tier`) for axes.
      Missing method cell → skip that series, log.
- [x] Task 2.2 — `marginal_charts.py::plot_marginal_progression(prepared, country, out_dir)`:
      per (model, attribute) draw a grouped-bar figure (6 offset groups), baseline distinct, methods
      color-ramped from `_COLOR_SERIES`, `ylim(0,1)`, horizontal fallback for
      `_HIGH_CARDINALITY_FIELDS`; save via `save_figure`; return `list[Path]`.
- [x] Task 2.3 — Update `method_significance/__init__.py` docstring to record that the
      descriptive-marginal path reads mapped populations (the other paths remain report-only).

**Files Modified:**
- `src/population_synthetic/analysis/method_significance/marginal_charts.py` — NEW.
- `src/population_synthetic/analysis/method_significance/__init__.py` — docstring note.

**Dependencies:** Phase 1

### Phase 3: Driver wiring
**Started:** 2026-07-20 · **Completed:** 2026-07-20
**Goal:** Emit the new charts as part of the per-country method-significance run.

- [x] Task 3.1 — In `scripts/analyze/analyze_method_significance.py`, after the existing per-country
      processing, resolve the mapping tier for the country and call `load_marginal_series` →
      `plot_marginal_progression`, writing under the method-significance output dir. Guard so an
      empty/missing mapping index logs and skips rather than crashing the whole run.
- [x] Task 3.2 — Log a one-line summary per country (models × attributes × figures written).

**Files Modified:**
- `scripts/analyze/analyze_method_significance.py` — call load+plot per country.

**Dependencies:** Phase 2

---

## Testing Plan

### Unit Tests
- [ ] `compute_proportions` — proportions sum to 1 over present categories; absent category → 0.0;
      all-null attribute → all 0.0 (or documented empty); extra category surfaced not silently
      dropped.
- [ ] `load_marginal_series` (with a tiny synthetic mapping dir fixture) — series ordered
      baseline-first then `STRATEGY_COMPLEXITY_ORDER`; missing method cell omitted + logged; missing
      real baseline raises.

### Integration Tests
- [ ] End-to-end on a small fixture mapping dir: `load_marginal_series` → `plot_marginal_progression`
      writes the expected PNG+SVG set per (model, attribute); paths returned match files on disk.

### Manual Verification
- [ ] Run the method-significance analysis for Sweden on real mapped data; open a couple of figures
      (e.g. `education_level`, a high-cardinality attribute) and confirm 6 series, correct method
      order, baseline distinct, category axis matches config.
- [ ] Confirm SVG siblings exist alongside PNGs.

### Edge Cases
- [ ] Attribute with a single category → single grouped cluster renders without layout errors.
- [ ] High-cardinality attribute → horizontal-bar fallback triggers.
- [ ] A model missing one of the 5 methods → 5 series instead of 6, logged.
- [ ] Attribute with zero data in every population → explicit skip (no empty axes written).

---

## Documentation Plan

- [ ] Update `CLAUDE.md` architecture blurb for `method_significance/` to note the descriptive
      per-method marginal-progression chart family (reads mapped populations).
- [ ] Update the architecture wiki page(s) for the analysis sub-packages / method_significance.
- [ ] Add a short note in the command reference if a new CLI flag is introduced (only if Task 3.1
      adds one; default is always-on).
- [ ] Inline docstrings on the new helper and chart functions describing the contract above.

---

## Rollback Plan

1. The feature is purely additive (one new util module, one new chart module, additive driver
   calls, two docstring/doc edits, one delegation refactor). To revert: delete
   `analysis/utils/marginals.py` and `method_significance/marginal_charts.py`, revert the
   `fidelity/charts.py` delegation, the `__init__.py` docstring, and the
   `analyze_method_significance.py` wiring.
2. **Data considerations:** none — no schema, no migration; only new image files under
   `03_Analysis/method_significance/{country}_marginal_progression/`, which can be deleted freely.
3. **Rollback procedure:** revert the feature branch merge (`--no-ff` merge commit) or `git revert`
   the commits; remove the generated `_marginal_progression` output folders.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Bending `method_significance`'s "no population recompute" contract confuses future readers | Med | Low | Update `__init__.py` docstring + CLAUDE.md; keep pure math in `utils/` |
| Category axis drift between the chart and the scored reports (wrong mapping tier) | Med | Med | Source categories from `scheme_category_values` of the tier the combos were scored against; assert tier consistency |
| 6 series on a high-cardinality attribute is unreadable | Med | Low | Reuse `_HIGH_CARDINALITY_FIELDS` horizontal-bar fallback; dynamic figsize |
| Missing/renamed mapped files crash the whole method-significance run | Low | Med | Fail loud only on missing real baseline; per-combo/per-country missing → logged skip |
| Duplicated proportion logic diverges from fidelity's | Low | Low | Single shared helper; refactor fidelity to delegate |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 | ~0.5 day | None |
| Phase 2 | ~1 day | Phase 1 |
| Phase 3 | ~0.5 day | Phase 2 |

---

## References

- Related design invariant: `method_significance/__init__.py` ("never recomputes statistics from
  populations") — deliberately amended by this plan for the descriptive path.
- Strategy ordering authority: `analysis/utils/axes.py::STRATEGY_COMPLEXITY_ORDER`.
- Grouped-bar template: `analysis/fidelity/charts.py::plot_comparison_charts`.
- Save helper: `analysis/utils/figures.py::save_figure`.
- Config-driven axes: `analysis/model_ranking/loader.py::scheme_attributes` /
  `scheme_category_values`.

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- docs/development/plans/active/method-marginal-progression-charts.md
- scripts/analyze/analyze_method_significance.py
- src/population_synthetic/analysis/fidelity/charts.py
- src/population_synthetic/analysis/method_significance/__init__.py
- src/population_synthetic/analysis/method_significance/marginal_charts.py
- src/population_synthetic/analysis/utils/marginals.py
- tests/test_marginals.py
