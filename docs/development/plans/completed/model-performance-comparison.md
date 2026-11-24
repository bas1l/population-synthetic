# Plan: Cross-Model Performance Comparison (models × methods per country)

**Date:** 2026-07-02
**Author:** Basil
**Status:** Completed (2026-07-02)
**Base Branch:** `feature/homogenize-real-synthetic-naming`
**Branch:** `feature/model-performance-comparison`

---

## Overview

Add a new analysis task that sits **after** the compare-synthetic-to-real stage: it consumes the
per-combo comparison reports (`{output_base}/03_Analysis/comparison/{slug}/{slug}.json`) and
compares the model × strategy combos **against each other** — per demographic attribute and
overall — within each country, ranking how well each combo matches the real baseline.

## Problem Statement

The compare stage scores each single combo against the real population, but the only cross-combo
artifact is the shallow `comparison_summary.json` (mean TV + coherence per combo) and a radar
grid. There is no ranking, no per-attribute score matrix, and no significance testing of the
model / strategy factors.

## Design decisions

- **Metric**: TV-similarity (`1 − tv_distance`) per attribute + coherence overall drive rankings
  and charts; `kl_divergence` / `chi_sq_p` / `max_diff` are carried through in the JSON for
  reference only.
- **Statistics**: Kruskal-Wallis + Dunn/Holm reused from the shared
  `analysis/utils/stats_tests.py` — per country, grouped by model (samples = per-attribute
  TV-similarities pooled across strategies) and by strategy (pooled across models).
  Pseudo-replication caveat recorded in the JSON output.
- **Placement**: new dedicated process subpackage `src/population_synthetic/analysis/performance/`
  (one subpackage per analysis process, alongside `mapping/`, `comparison/`, `llm_metrics/`).
- **Shared-utils refactor** (prerequisite): helpers consumed across subpackages moved into
  `analysis/utils/` — `_stats.py` (from `llm_metrics/shared/`, package removed), `stats_tests.py`
  (from `llm_metrics/cross_run/comparison_stats.py`), and new `axes.py` (`decompose_slug` /
  `diagnose_slug` from `cross_run/comparison_loader.py` + `STRATEGY_COMPLEXITY_ORDER` from
  `comparison/charts.py`). All import sites updated; no compatibility shims.
- **Outputs** land in `{output_base}/03_Analysis/performance/`:
  `{country}_performance.json`, `{country}_performance.csv`, `{country}_heatmap.png`,
  `{country}_leaderboard.png`, and (flag-gated) `{country}_by_attribute/{attr}_bars.png`.
- **Missing-report policy**: warn + list missing combos, proceed per country when ≥2 combos have
  reports (skip the country otherwise); `--strict` makes any missing report fatal. Malformed
  reports always raise.

## In Scope

1. `performance/loader.py` — `ComboPerformance` DTO, pure `extract_combo_performance`,
   filesystem `load_combo_performances` (discovery via `mapped/_index.json` + `decompose_slug`).
2. `performance/builder.py` — score matrix, ranking (TV-mean desc, coherence tie-break),
   stats wiring, JSON/CSV writers.
3. `performance/charts.py` — heatmap (combos × attributes + overall), leaderboard,
   optional per-attribute grouped bars.
4. `scripts/analyze/compare_model_performance.py` — CLI (`--country/--model/--strategy/--slug`
   filters, `--output-base`, `--no-charts`, `--per-attribute-charts`, `--strict`).
5. GUI action `model_performance` in `config/gui/launcher.yaml` (`axis_mode: batch`,
   `min_combos: 2`).
6. Unit tests: `tests/_performance_fixtures.py`, `tests/test_performance_loader.py`,
   `tests/test_performance_builder.py`.
7. The shared-utils refactor above, plus doc updates (`CLAUDE.md`, `docs/architecture/sub-packages.md`,
   `docs/architecture/commands.md`).

## Out of Scope

- Replicate runs per combo (required for rigorous inference) — single run per combo assumed.
- Composite ranking score mixing TV and coherence (coherence is tie-break/annotation only).
- Cross-country comparison (each country is reported separately).

## Success Criteria

- [ ] `python scripts/analyze/compare_model_performance.py` produces per-country JSON, CSV,
      heatmap, and leaderboard from existing comparison reports.
- [ ] Kruskal-Wallis + Dunn results present per factor (model / strategy) in JSON and console.
- [ ] `--strict` fails on a missing report; default mode warns and proceeds with ≥2 combos.
- [ ] GUI "Model Performance" action runs the script with `--slug` per selected combo and blocks
      single-combo selections.
- [ ] `ruff check` clean; full `pytest` green.
