# Brainstorm: Real-population statistics analysis task

**Started:** 2026-07-22   **Last matured:** 2026-07-22   **Status:** Handed off (plan drafted)

## Dispatch decision (resolved)
GUI runs via a **new `per_country` dispatch**: task ignores model/strategy ticks, runs once per
selected country on the mapped real population. Chosen over per_combo+dedupe (avoids phantom
model/strategy dependency and wasted no-op subprocesses) and over CLI-only (must be a GUI task).
Requirement from user: the task's GUI label/description must explicitly state what it does.
Plan: docs/development/plans/pending/real-population-reference-stats.md

## Real goal (north star)
Produce **standalone publication figures** of the real (API-sourced) population — the dataset
treated as ground truth / reference in the scientific paper. One figure per demographic category
showing the proportion of each category value. These are reference-distribution assets for the
manuscript, not a diagnostic comparison against synthetic data.

## Where it stands (matured form)
A new **analysis-GUI task** that operates on a **single real population standalone** (no synthetic
comparison), **country-agnostic** (works for any supported country — SCB/ISTAT/SSB — chosen at run
time, like the rest of the pipeline).

For each category in the country's **analyzed axis set** (`ComparisonScheme.attributes`,
config-driven; Sweden = 14, excludes deprecated `birth_location`), render a **bar plot**:
- **x-axis** = the category's values
- **y-axis** = proportion in **percent, fixed [0, 100%]** (hardcoded; matches the paper's convention)
- **value labels** printed on top of each bar (keeps rare/tiny bars legible)
- **background gridlines**: gray dashed horizontal lines at **25% / 50% / 75% / 100%** spanning the figure

Outputs, **per category figure**:
- **PNG** (raster)
- **SVG** (vector, for the manuscript)
- **CSV** — one row per category value with `count`, `total`, `proportion` (0–1), `percent` (0–100);
  self-describing, backs both the figure and any paper table

Plus, once per run:
- **Combined multi-panel figure** — all analyzed categories tiled into a single "reference population
  overview" figure (PNG + SVG).

Scope: **univariate marginals only.** Conditional/joint views explicitly out of scope.

## Codebase reality (from background scan)
- **PARTIALLY exists.** All proportional output today lives inside two-population comparisons;
  no standalone real-only analysis path exists.
- Reusable: `utils/marginals.py::compute_proportions` (single-pop proportions),
  `utils/figures.py::save_figure` (PNG+SVG dual-save), bar styles in `fidelity/charts.py`,
  axis source `fidelity/scheme.py::ComparisonScheme`, registry + output-dir wiring
  (`analysis_output_dir(id, base)`).
- Must build new: single-population driver script, single-series bar figures (labels + dashed
  gridlines + fixed 0–100% axis), combined panel, and a **CSV writer for the raw proportion vector**
  (existing `write_csv_summary` emits comparison metrics, not proportions).
- Adding a task = 3 structural edits: registry entry (`analysis_registry.yaml`) + backing script
  (`scripts/analyze/`) + workflow node (`analysis_workflow.yaml`, likely `depends_on: [mapping]`).

## Decisions (all resolved)
- Purpose: publication reference figures (not QA / not reusable-distribution schema).
- Standalone real population; no synthetic comparison.
- Country-agnostic.
- Category set: **analyzed set only** (config-driven, excludes deprecated).
- Univariate only; no conditional/joint views.
- Y-axis: percent, fixed [0, 100%].
- Value labels on bars.
- Dashed gray gridlines at 25/50/75/100%.
- Per-figure outputs: PNG + SVG + CSV (count, total, proportion, percent).
- Also a combined multi-panel overview figure (PNG + SVG).

## Open questions
- (Minor, defer to planning) Bar ordering — natural/config order vs sorted by size. Assume config order.
- (Minor) Task id / label / output-folder name — settle at plan time (e.g. `real_population_stats`).
- (Minor) Combined-panel layout (columns, per-panel sizing) — settle at plan time.

## Session log
- 2026-07-22 — Idea located; purpose fixed to publication reference figures. Scope fixed to univariate
  per-category proportion bars, y in percent [0,100%], PNG+SVG+CSV per figure. Codebase scanned
  (PARTIALLY exists). Decisions locked: country-agnostic, analyzed set only, value labels, dashed
  25/50/75/100% gridlines, plus a combined multi-panel overview figure. Status → Matured.
