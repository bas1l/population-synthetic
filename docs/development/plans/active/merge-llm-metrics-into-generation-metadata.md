# Plan: Merge run_analytics (LLM metrics) into generation_metadata

**Date:** 2026-07-23
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/generation-metadata-analysis-task`
**Branch:** `feature/merge-llm-metrics-into-generation-metadata`

> **Base-branch dependency (read first):** this plan modifies the `generation_metadata`
> subpackage, which exists ONLY on `feature/generation-metadata-analysis-task` (commit
> `a21b7df`) and is not yet in `dev`. Two options: (a) merge that branch into `dev` first via
> `/plan-finish`, then branch this from `dev`; or (b) stack this branch directly on
> `feature/generation-metadata-analysis-task` (base recorded above). Decide before
> `/plan-implement`. Recommended: (a) — finish the first branch, then branch from `dev`.

---

## Overview

Consolidate the three LLM-analytics tasks into one. `run_analytics_per_run` and
`run_analytics_cross_run` are **removed as standalone tasks**; all their logic is **absorbed
into `generation_metadata`**, which becomes the single LLM-metrics task writing to one folder
(`03_Analysis/generation_metadata/`) as a **single enriched per-country summary**: the CSV
carries flattenable scalar columns; the `{country}_summary.json` carries the deep nested
per-combo diagnostics and the country-level cross-factor significance results.

## Problem Statement

There are currently three overlapping LLM-analytics tasks (see the completed plan
`generation-metadata-analysis-task.md` and the comparison in the architecture notes). They
duplicate per-persona timing/token parsing three ways, split cost/means (generation_metadata)
from distribution/significance (cross_run) from deep diagnostics (per_run) across two output
folders, and force the user to run a two-stage pipeline (`analyze_run.py --all` →
`compare_run_analytics.py`) plus a separate task to get the full picture. One task with one
output answers every question — cost, means±std, distribution shape, significance, and deep
diagnostics — from a single command over `01_Raw`.

## Goals

### In Scope
1. Relocate all pure-library run_analytics modules into `generation_metadata/`; make it
   self-contained (no `run_analytics` imports anywhere).
2. Absorb **per-run deep diagnostics** (per-combo): error taxonomy, per-category retry,
   value diversity (entropy), latency percentiles (median/p95/max), tokens/sec,
   prompt-size growth, response verbosity, token budget by step type, success_rate,
   token_match_rate — into the `{country}_summary.json` nested per combo.
3. Absorb **cross-run significance** (per country): Kruskal-Wallis + Dunn/Holm across the
   model factor and the method factor, per comparison metric — into the JSON (full results)
   and the CSV (per-combo significance-group labels).
4. Enrich the CSV scalar columns: add `<metric>_median`, `<metric>_q1`, `<metric>_q3` for the
   distribution metrics, plus `latency_p95`, `latency_max`, `success_rate`.
5. Extend `scripts/analyze/summarize_generation_metadata.py` to cover the removed scripts'
   surface (`--verbose` console diagnostics, `--metrics` subset for the comparison); remove
   `analyze_run.py` and `compare_run_analytics.py`.
6. Merge charts: per-metric mean-heatmaps (existing) + per-combo diagnostic charts +
   cross-factor comparison charts (box/grouped-bar/heatmap with significance stars), all under
   `generation_metadata/charts/`, all PNG+SVG via `save_figure`.
7. Remove the two `run_analytics_*` registry entries, GUI nodes, and the `run_analytics/`
   subpackage; update all references (tests, docs).

### Out of Scope
- Migrating or back-reading existing on-disk `03_Analysis/run_analytics/` output (different
  schema; left orphaned — see Rollback).
- Changing the pricing model, the cost metric, or `model_pricing.yaml`.
- Changing the shared stats in `analysis/utils/` (reused as-is).
- The method_significance / model_ranking tasks (unrelated).

## Success Criteria

- [ ] `grep -r "run_analytics" src/ config/ scripts/ tests/` returns **zero** functional
      references (only historical docs/plan mentions may remain).
- [ ] `python scripts/analyze/summarize_generation_metadata.py --country swedish` produces a
      single `03_Analysis/generation_metadata/swedish_summary.{csv,json}` + `charts/` that
      contains: cost + I/O-token-split means, median/q1/q3, latency p95/max, success_rate
      (CSV); deep per-combo diagnostics + KW/Dunn results (JSON); comparison charts.
- [ ] CSV has, per distribution metric, `_mean`,`_std`,`_median`,`_q1`,`_q3`,`_n` columns and
      per-combo significance-group columns per factor.
- [ ] JSON contains a `diagnostics` block per combo and a `significance` block per country
      (KW p-value + Dunn matrix per metric per factor).
- [ ] `analyze_run.py` and `compare_run_analytics.py` no longer exist; registry has one
      `generation_metadata` process; GUI has one node.
- [ ] Relocated engine keeps its behavior: `test_aggregator`, `test_joiner`, `test_log_parser`,
      `test_call_context` pass against the new import paths.
- [ ] New tests cover the previously-untested cross-factor comparison logic.
- [ ] `ruff check src/ scripts/` clean on touched files; full `pytest` green.

## Definitions

- **combo**: `(country, model, method/strategy)`; a run slug `{country}_{strategy}_{model}` is
  exactly one combo. `run_analytics`'s "per-run" == this plan's "per-combo".
- **scalar metric**: a per-combo quantity reducible to a single number (mean, median, p95,
  rate, cost) → belongs in the CSV.
- **deep diagnostic**: a per-combo quantity that is a dict/distribution (per-category error
  taxonomy, per-category entropy, per-step token budget, tokens/sec series) → belongs in the
  JSON only; NOT flattened to CSV columns. This is the concrete resolution of the
  "full absorption" + "single enriched summary" tension.
- **cross-factor significance**: per country, for each comparison metric, a Kruskal-Wallis
  omnibus + Dunn/Holm post-hoc computed once across the **model** factor and once across the
  **method** factor. Country-level result → JSON `significance`; each combo's group membership
  → CSV `<metric>_<factor>_group` label.
- **self-contained**: after this plan, no module under `generation_metadata/` imports from
  `population_synthetic.analysis.run_analytics.*`, and that package no longer exists.

---

## Technical Design

### Approach

De-risk by **relocating before deleting**. Phase 1 moves the pure-library run_analytics
modules into `generation_metadata/` and repoints the (already-existing) live imports + the
existing tests, changing NO behavior and keeping the suite green. Only then do later phases
wire the absorbed logic into the summary output and finally delete the emptied package,
registry entries, GUI nodes, and scripts.

The CSV/JSON split is the design's backbone: `combo_aggregator` + `report_writer` already own
the scalar-column path (`METRIC_NAMES` → `<metric>_{mean,std,n}` CSV). We (a) extend the
scalar path with distribution stats via `analysis/utils/stats_tests.summarize()` and new
scalar metrics, and (b) add a parallel **diagnostics path**: per combo, run the relocated
`compute_metrics()` over the combo's joined entries and attach the nested result to the JSON
only. Cross-factor significance is a third, country-level path computed over the per-combo
distribution samples using the shared `kruskal_test`/`dunn_posthoc`.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Relocate library code into generation_metadata, then delete package | Self-contained subpackage (matches one-subpackage-per-process rule); clean removal | Moves several files | **Chosen** |
| Keep run_analytics package, import from it internally | Less file movement | Violates "remove entirely"; leaves dead task code + package | Rejected (user chose remove) |
| Leave parsers in run_analytics, only remove tasks | Minimal | generation_metadata still coupled to a "removed" package; confusing | Rejected |
| Flatten deep diagnostics into CSV | One artifact type | Impossible cleanly (per-category/per-step dicts); explodes columns | Rejected → JSON nesting |
| Move parsers to analysis/utils | Generic home | After removal only generation_metadata uses them → belongs in the subpackage, not utils | Rejected (per analysis-subpackage-layout rule) |

### Architecture & Module Contracts

Relocations into `src/population_synthetic/analysis/generation_metadata/` (behavior preserved):

| From (run_analytics) | To (generation_metadata) | Responsibility | Must NOT know about |
|---|---|---|---|
| `per_run/interaction_parser.py` | `interaction_parser.py` | Parse `llm_interactions.{jsonl,json}` → normalized entries | slugs, cost, charts |
| `per_run/log_parser.py` | `log_parser.py` | Parse `logs/run_*.log` call lines + summary | JSONL, cost, charts |
| `per_run/joiner.py` | `joiner.py` | Join log records ↔ JSONL entries | cost, charts, slugs |
| `per_run/aggregator.py` | `diagnostics.py` | `compute_metrics()` deep per-combo diagnostics (+ `_parse_iso`) | slugs, cost, pricing, CSV schema |
| `per_run/charts.py` | (fold into) `charts.py` | Per-combo diagnostic charts | parsing, cost math |
| `cross_run/comparison_loader.py` | `comparison.py` | `MetricSpec`/`METRIC_SPECS`, sample extraction from a combo's metrics | on-disk `run_analytics.json` layout (reads in-memory instead) |
| `cross_run/run_comparison.py` | `comparison.py` | `build_comparison()` KW/Dunn by factor + model×method matrix | file I/O, CSV schema |
| `cross_run/comparison_charts.py` | (fold into) `charts.py` | Box/grouped-bar/heatmap + significance stars | parsing, cost |
| `per_run/console_report.py` | (fold into) the script or a `console.py` | `--verbose` console tables | file layout |

Extended existing modules (contracts unchanged, capabilities added):

| Module | Added responsibility | Inputs → Outputs | Must NOT know about |
|---|---|---|---|
| `persona_metrics.py` | Repoint imports to local `diagnostics`/`interaction_parser` | (unchanged) | slugs, pricing, charts |
| `combo_aggregator.py` | Extend `METRIC_NAMES` scalar set (median/q1/q3 via `summarize`; latency p95/max; success_rate); attach per-combo `diagnostics` (from `compute_metrics`) and hold distribution samples for significance | `list[PersonaMetrics]` + joined entries → `ComboSummary{metrics, diagnostics, samples, skipped}` | file layout, pricing $, chart styling |
| (new) significance path in `combo_aggregator.py` or `comparison.py` | Per country: KW/Dunn across model & method factors per metric | `list[ComboSummary]` → `{metric:{model:{p,groups}, method:{p,groups}}}` | file I/O, charts |
| `report_writer.py` | Emit enriched CSV columns + JSON `diagnostics` (per combo) + `significance` (per country) | combos + significance + metadata → `.csv`+`.json` | how metrics computed |
| `charts.py` | Add diagnostic + comparison charts, all via `save_figure` (PNG+SVG) | combos, significance, out_dir → PNG+SVG | parsing, cost math |
| `__init__.py::summarize` | Orchestrate: parse+join per combo → diagnostics + scalar aggregate → country significance → write; carry `--verbose`/`--metrics` | args → artifacts | — |

Shared, reused unchanged: `analysis/utils/stats_tests.py` (`kruskal_test`, `dunn_posthoc`,
`_holm`, `summarize`), `analysis/utils/_stats.py`, `analysis/utils/axes.py`,
`analysis/utils/figures.py::save_figure`, `analysis/utils/registry.py`.

Removed: `src/population_synthetic/analysis/run_analytics/` (whole package),
`scripts/analyze/analyze_run.py`, `scripts/analyze/compare_run_analytics.py`, the two
`run_analytics_*` registry entries, the two GUI nodes.

```
src/population_synthetic/analysis/generation_metadata/
  __init__.py            # summarize(): orchestrate parse→diagnostics→aggregate→significance→write
  interaction_parser.py  # (relocated)
  log_parser.py          # (relocated)
  joiner.py              # (relocated)
  diagnostics.py         # (relocated aggregator.compute_metrics + _parse_iso)
  comparison.py          # (relocated MetricSpec/METRIC_SPECS + build_comparison KW/Dunn)
  persona_metrics.py     # imports repointed to local modules
  combo_aggregator.py    # + median/q1/q3, latency p95/max, success_rate, diagnostics, samples
  cost.py                # unchanged
  pricing.py             # unchanged
  report_writer.py       # + enriched CSV cols, JSON diagnostics + significance blocks
  charts.py              # + diagnostic charts + comparison charts (all save_figure)
  console.py             # (optional) relocated console_report for --verbose
```

---

## Implementation Plan

### Phase 1: Relocate & self-contain (no behavior change)
**Goal:** Move pure-library run_analytics modules into `generation_metadata/`; repoint all
imports (live code + tests); suite stays green. `run_analytics/` package still exists but is
now unused by production code (deleted in Phase 5).

**Started:** 2026-07-23
**Completed:** 2026-07-23

- [x] 1.1 — Move `interaction_parser.py`, `log_parser.py`, `joiner.py` into
      `generation_metadata/`; move `aggregator.py` → `diagnostics.py`; move
      `comparison_loader.py` + `run_comparison.py` → merged `comparison.py`. Preserve public
      APIs verbatim.
- [x] 1.2 — Repoint `persona_metrics.py:32-33` imports to the local `diagnostics`/
      `interaction_parser`.
- [x] 1.3 — Repoint test imports: `tests/test_aggregator.py`, `tests/test_joiner.py`,
      `tests/test_log_parser.py`, `tests/test_call_context.py` → new module paths.
- [x] 1.4 — Fold `per_run/charts.py` + `cross_run/comparison_charts.py` into
      `generation_metadata/charts.py` (as internal helpers, converted to `save_figure`
      PNG+SVG); fold `console_report.py` → `console.py` (or leave for Phase 4). Run suite green.

**Files:** `generation_metadata/{interaction_parser,log_parser,joiner,diagnostics,comparison,charts,console}.py`, `persona_metrics.py`, the 4 test files.
**Dependencies:** None (base branch has generation_metadata).

### Phase 2: Deep per-combo diagnostics + enriched scalar columns
**Goal:** The summary gains distribution stats (CSV) and deep diagnostics (JSON).

**Started:** 2026-07-23
**Completed:** 2026-07-23

- [x] 2.1 — In `summarize`/`_collect_personas`: per combo, build joined entries
      (interaction_parser + log_parser + joiner) and run `diagnostics.compute_metrics()`.
- [x] 2.2 — Extend `combo_aggregator`: for each distribution metric add median/q1/q3 via
      `stats_tests.summarize()`; add scalar `latency_p95`, `latency_max`, `success_rate`; store
      the per-persona sample lists on `ComboSummary` for Phase 3; attach the `compute_metrics`
      dict as `ComboSummary.diagnostics`.
- [x] 2.3 — Extend `report_writer`: CSV gains `<metric>_{median,q1,q3}` + the new scalar
      columns; JSON gains a per-combo `diagnostics` block. Keep `None`-gating.
- [x] 2.4 — Charts: add per-combo diagnostic charts (latency, error taxonomy, entropy) into
      `charts/`.

**Files:** `__init__.py`, `combo_aggregator.py`, `report_writer.py`, `charts.py`.
**Dependencies:** Phase 1.

### Phase 3: Cross-factor significance
**Goal:** Per-country KW/Dunn across model & method factors, in JSON + CSV group labels.

**Started:** 2026-07-23
**Completed:** 2026-07-23

- [x] 3.1 — Absorb `comparison.build_comparison` to consume the in-memory per-combo distribution
      samples (NOT on-disk `run_analytics.json`); compute KW + Dunn/Holm per comparison metric
      per factor; derive per-combo significance-group labels. Respect `--metrics` subset.
      *Added `build_summary_comparison` (rich, chart-ready, over `list[ComboSummary]` reusing the
      relocated `_group_samples`/`_order_by_median`/`_aggregate`) + `significance_from_comparison`
      (reduced view: KW `{H,p,df}`, Dunn Holm p-matrix, per-group compact-letter-display letters)
      with an `n<2`/`<2 groups` skip guard; comparison metric set = the 8 `METRIC_NAMES` samples,
      token families gated on telemetry. `summarize(...)` gained a `metrics=` subset kwarg.*
- [x] 3.2 — `report_writer`: JSON `significance` block per country (p-values + Dunn matrices);
      CSV per-combo `<metric>_<factor>_group` columns. *Group columns appended after
      `success_rate`, metric-outer/factor-inner (`<metric>_model_group`, `<metric>_method_group`);
      significance block left unrounded to preserve tiny p-values.*
- [x] 3.3 — Charts: comparison box/grouped-bar/heatmap with significance stars (from folded
      comparison_charts). *Wired `plot_run_comparison(comparison, charts/{country}_comparison)`
      into `summarize` under `charts=True`.*
- [x] 3.4 — **Tests for the previously-untested comparison logic** (known-answer KW/Dunn,
      group labelling, factor grouping). *`tests/test_gm_comparison.py`: 12 tests — factor
      pooling, known-answer KW (H=7.2, df), n<2 / <2-group guards, `--metrics` subset, CLD
      (separated differ / overlapping share / straddling middle carries both), `group_label`
      lookup, and a 2x2 integration fixture asserting CSV group columns + JSON `significance`.*

**Files:** `comparison.py`, `combo_aggregator.py`/`__init__.py`, `report_writer.py`, `charts.py`, `tests/test_generation_metadata.py`.
**Dependencies:** Phase 2.

### Phase 4: Script consolidation
**Goal:** One CLI covers everything; old scripts gone.

**Started:** 2026-07-23
**Completed:** 2026-07-23

- [x] 4.1 — Extend `summarize_generation_metadata.py`: add `--verbose` (console diagnostics via
      `console.py`) and `--metrics KEY...` (comparison subset). Keep existing flags.
      *`--metrics KEY [KEY ...]` (nargs="+") validated fail-fast against the 8 `METRIC_NAMES`
      (`time, input_tokens, output_tokens, total_tokens, calls, retry_rate, error_rate, cost`),
      threaded to `summarize(metrics=...)`. `--verbose` renders each written combo's deep
      diagnostics via `console.print_metrics`; wired through a new backward-compatible
      `summarize(on_combo=...)` hook (`on_combo(summary, raw_slug_dir)`, fired per combo of each
      written country) so nothing is recomputed. Docstring/`--help` updated to describe the unified
      cost+tokens+timing+diagnostics+significance output. Added `tests/test_summarize_gm_cli.py`
      (2 subprocess tests: unknown-key fail-fast, valid subset accepted).*
- [x] 4.2 — Done in Phase 5 (atomic removal). Deleted `analyze_run.py` and
      `compare_run_analytics.py` together with the package + registry entries + GUI nodes + tests.
- [x] 4.3 — Live end-to-end run for `swedish` proving the single artifact set. *Ran against a temp
      base junctioned to the real `01_Raw` (removed afterward; real data never touched). Produced
      ONE `swedish_summary.csv` (71 cols: 8 metrics x {mean,std,median,q1,q3,n} + latency_p95/max +
      success_rate + 16 `<metric>_<factor>_group` cols; 44 combos), ONE `swedish_summary.json`
      (per-combo `metrics` + 44 `diagnostics` blocks + 1 country `significance` block + pricing),
      and `charts/` (310 PNG+SVG: heatmaps + comparison + per-combo diagnostics). `--verbose` on a
      single slug printed the full compute_metrics console tables.*

**Files:** `scripts/analyze/summarize_generation_metadata.py` (+ deletions).
**Dependencies:** Phase 3.

### Phase 5: Remove run_analytics + update tests & docs
**Goal:** Zero functional run_analytics references.

**Started:** 2026-07-23
**Completed:** 2026-07-23

- [x] 5.1 — Deleted `src/population_synthetic/analysis/run_analytics/` package (whole dir).
- [x] 5.2 — Removed both `run_analytics_*` entries from `config/analysis/analysis_registry.yaml`;
      enriched the `generation_metadata` entry to describe the absorbed diagnostics + significance.
- [x] 5.3 — Removed both `run_analytics_*` nodes from `config/gui/flows/analysis_workflow.yaml`
      (surgical) and their positions from `analysis_workflow.layout.json` (the isolated node coords).
- [x] 5.4 — `tests/test_analysis_registry.py`: dropped both ids from `_EXPECTED_FOLDERS`.
      `tests/test_workflow_state.py`: dropped both ids from the ordering set; repointed
      `test_disabled_task_cannot_run` to `pairwise_comparison` (the last remaining disabled node),
      completing `mapping` first so `enabled: false` is the isolated blocker under test.
- [x] 5.5 — Purged the dead on-disk cross-run path from `generation_metadata/comparison.py`
      (`load_run_records`, `build_comparison`, `comparison_to_json`, `write_comparison_json`,
      `RunRecord`, `extract_comparison_metrics`, `MetricSpec`/`METRIC_SPECS`/`METRIC_SPECS_BY_KEY`,
      and the `run_analytics.json`/`run_analytics_root` literals + now-unused imports); kept the shared
      `_group_samples`/`_order_by_median`/`_aggregate` (retyped to `ComboSummary`) plus the whole
      in-memory `build_summary_comparison`/`significance_from_comparison` path. Also deleted the
      now-orphaned `config/analysis/analyze_defaults.yaml` (read only by the two deleted scripts).
- [x] 5.6 — Updated docs: `CLAUDE.md`, `docs/architecture/{commands.md,configuration.md,sub-packages.md,README.md}`,
      `docs/development/gui.md`, `docs/swedish_synthetic_populations_and_analysis_outputs.md`,
      `docs/development/swedish-token-usage-by-model.md`, `scripts/README.md`, and root `README.md`.
      Repointed src docstrings in `analysis/__init__.py` + `analysis/utils/{axes,stats_tests,_stats}.py`.
- [x] 5.7 — `grep -r run_analytics src/ config/ scripts/ tests/` → zero functional hits; full `pytest` green.

**Files:** registry, GUI yaml, 2 test files, docs, package deletion.
**Dependencies:** Phase 4.

---

## Testing Plan

### Unit Tests
- [ ] Relocated engine tests pass at new paths (aggregator/joiner/log_parser/call_context).
- [ ] `summarize()` distribution columns: median/q1/q3 match `stats_tests.summarize` on a fixture.
- [ ] latency_p95/max, success_rate correct on a synthetic combo.
- [ ] Cross-factor significance: known-answer KW/Dunn; group labels correct; `--metrics` subset honored.
- [ ] Deep diagnostics JSON block present per combo; token-gated families `None` when no tokens.

### Integration Tests
- [ ] Fixture `01_Raw` with ≥3 combos over ≥2 models & ≥2 methods (one token-less) → one
      `{country}_summary.{csv,json}` with scalar cols + `diagnostics` + `significance`; charts written.
- [ ] `--force` re-run vs skip; `--verbose` prints without error.

### Manual Verification
- [ ] Real `swedish` run; spot-check a combo's median vs mean, a KW p-value, and a diagnostics block.
- [ ] GUI: single `generation_metadata` node runs; no run_analytics nodes present.

### Edge Cases
- [ ] Country with <2 combos in a factor → significance `None`/skipped, not a crash.
- [ ] Single-persona combo → std/q1/q3 `None`; diagnostics still emitted.
- [ ] Combo with no `logs/` (JSONL only) → joiner degrades gracefully (latency may be `None`).

---

## Documentation Plan

- [ ] `CLAUDE.md` — collapse the three-task description into one; remove run_analytics mentions.
- [ ] `docs/architecture/commands.md` — remove analyze_run/compare_run_analytics; update generation_metadata command + registry table.
- [ ] `docs/architecture/{configuration.md,sub-packages.md,README.md}` — package list + folder paths.
- [ ] `docs/development/gui.md` — remove run_analytics island note.
- [ ] `docs/swedish_synthetic_populations_and_analysis_outputs.md` — Stage D output description.
- [ ] `docs/development/swedish-token-usage-by-model.md`, `scripts/README.md` — references.

---

## Rollback Plan

1. Everything is on `feature/merge-llm-metrics-into-generation-metadata`; the prior state is
   the tip of `feature/generation-metadata-analysis-task`. Revert = delete this branch.
2. **On-disk data:** existing `03_Analysis/run_analytics/` output is left orphaned (different
   schema, no fallback). It is not deleted by this plan; users may remove it manually. New runs
   write only under `03_Analysis/generation_metadata/`.
3. Phase 1 is behavior-preserving; if later phases go wrong, the relocation alone is a safe
   intermediate state (suite green, run_analytics still present until Phase 5).

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Cross-run comparison logic is untested → subtle regressions when absorbed | High | High | Phase 3.4 writes known-answer tests; preserve `build_comparison` logic verbatim during relocation, refactor only after tests pass |
| Live import coupling breaks mid-refactor | Med | Med | Phase 1 repoints imports first, keeps suite green before any deletion |
| CSV column explosion / unreadable | Med | Med | Deep diagnostics go to JSON only; CSV limited to scalars (median/q1/q3, p95/max, rates, cost, group labels) |
| `--all`/`run_dir`/positional args of old scripts have no equivalent | Low | Low | generation_metadata discovers `01_Raw` unconditionally (covers `--all`); document the dropped single-`run_dir` mode |
| Orphaned run_analytics output confuses users | Med | Low | Document in Rollback + docs; optional manual cleanup |
| Base-branch stacking confusion | Med | Med | Explicit base-branch note at top; recommend finishing first branch into dev before implementing |
| Significance with tiny factor groups (Ollama-only country) | Med | Low | Guard n<2 per group → significance `None`, recorded skip |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 (relocate) | ~0.5–1 day | None |
| Phase 2 (diagnostics + scalar) | ~1 day | Phase 1 |
| Phase 3 (significance) | ~1 day | Phase 2 |
| Phase 4 (script) | ~0.5 day | Phase 3 |
| Phase 5 (removal + docs) | ~0.5 day | Phase 4 |

---

## References

- Prior plan: `docs/development/plans/completed/generation-metadata-analysis-task.md` (or
  `active/` until finished) — the task being extended.
- Reused stats: `src/population_synthetic/analysis/utils/stats_tests.py`.
- Absorbed engines: `src/population_synthetic/analysis/run_analytics/per_run/aggregator.py`,
  `.../cross_run/{comparison_loader.py,run_comparison.py}`.

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- CLAUDE.md
- README.md
- config/analysis/analysis_registry.yaml
- config/analysis/analyze_defaults.yaml
- config/gui/flows/analysis_workflow.yaml
- docs/architecture/README.md
- docs/architecture/commands.md
- docs/architecture/configuration.md
- docs/architecture/sub-packages.md
- docs/development/gui.md
- docs/development/plans/active/merge-llm-metrics-into-generation-metadata.md
- docs/development/swedish-token-usage-by-model.md
- docs/swedish_synthetic_populations_and_analysis_outputs.md
- scripts/README.md
- scripts/analyze/analyze_run.py
- scripts/analyze/compare_run_analytics.py
- scripts/analyze/summarize_generation_metadata.py
- src/population_synthetic/analysis/__init__.py
- src/population_synthetic/analysis/generation_metadata/__init__.py
- src/population_synthetic/analysis/generation_metadata/charts.py
- src/population_synthetic/analysis/generation_metadata/combo_aggregator.py
- src/population_synthetic/analysis/generation_metadata/comparison.py
- src/population_synthetic/analysis/generation_metadata/console.py
- src/population_synthetic/analysis/generation_metadata/diagnostics.py
- src/population_synthetic/analysis/generation_metadata/interaction_parser.py
- src/population_synthetic/analysis/generation_metadata/joiner.py
- src/population_synthetic/analysis/generation_metadata/log_parser.py
- src/population_synthetic/analysis/generation_metadata/persona_metrics.py
- src/population_synthetic/analysis/generation_metadata/report_writer.py
- src/population_synthetic/analysis/run_analytics/__init__.py
- src/population_synthetic/analysis/run_analytics/cross_run/__init__.py
- src/population_synthetic/analysis/run_analytics/cross_run/comparison_charts.py
- src/population_synthetic/analysis/run_analytics/cross_run/comparison_loader.py
- src/population_synthetic/analysis/run_analytics/cross_run/run_comparison.py
- src/population_synthetic/analysis/run_analytics/per_run/__init__.py
- src/population_synthetic/analysis/run_analytics/per_run/aggregator.py
- src/population_synthetic/analysis/run_analytics/per_run/charts.py
- src/population_synthetic/analysis/run_analytics/per_run/console_report.py
- src/population_synthetic/analysis/run_analytics/per_run/interaction_parser.py
- src/population_synthetic/analysis/run_analytics/per_run/joiner.py
- src/population_synthetic/analysis/run_analytics/per_run/log_parser.py
- src/population_synthetic/analysis/utils/_stats.py
- src/population_synthetic/analysis/utils/axes.py
- src/population_synthetic/analysis/utils/stats_tests.py
- tests/test_aggregator.py
- tests/test_analysis_registry.py
- tests/test_call_context.py
- tests/test_generation_metadata.py
- tests/test_gm_comparison.py
- tests/test_joiner.py
- tests/test_log_parser.py
- tests/test_summarize_gm_cli.py
- tests/test_workflow_state.py
