# Plan: Batch Comparison Script for All LLM Synthetic Populations

**Date:** 2026-05-25
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/ensure-n-generation`
**Branch:** `feature/compare-all-pipelines`

---

## Overview

Add a new script `scripts/compare_all_pipelines.py` that discovers all model × strategy × country combinations via the axis system, runs the existing comparison logic against each one sequentially, and produces a cross-model summary. This requires first refactoring the inline `extract_population()` out of `compare_pipeline_to_scb.py` into the shared comparison module.

## Problem Statement

The project generates synthetic populations using 7 LLM models × 5 strategies × 1 country. Each combination's output lives at `{output_base}/01_Raw/{country_id}_{strategy_id}_{model_id}/`. The existing `compare_pipeline_to_scb.py` compares **one** pipeline output at a time. To evaluate all models, a user must manually invoke the script 35 times and mentally aggregate the results. There is no way to get a cross-model summary or batch-run comparisons.

## Goals

### In Scope
1. Refactor `extract_population()` into `comparison/extractor.py` as a shared utility
2. New script that auto-discovers all axis combinations and runs comparisons sequentially
3. CLI filters for `--country`, `--model`, `--strategy` to run subsets
4. Per-combination output (JSON report, CSV summary, charts) matching existing script output
5. Aggregated summary table printed to stdout and saved as `comparison_summary.json`

### Out of Scope
- Parallel execution of comparisons (sequential is sufficient for now)
- GUI integration (future enhancement)
- Norwegian reference population support (only Swedish exists)
- Cross-model comparison (model A vs model B) — this compares each model vs SCB reference

## Success Criteria

- [ ] `extract_population()` is importable from `population_synth.comparison.extractor`
- [ ] `compare_pipeline_to_scb.py` still works identically after the refactor
- [ ] `compare_all_pipelines.py --country swedish` discovers all 35 combos, skips those without output, compares those with data
- [ ] `--model` and `--strategy` filters correctly restrict which combos are compared
- [ ] Each compared combo produces JSON + CSV + charts in `comparison_output_dir`
- [ ] Summary table prints to stdout with model, strategy, n, mean TV distance, coherence score
- [ ] `comparison_summary.json` is written to `{output_base}/03_Analysis/`

---

## Technical Design

### Approach

Reuse the existing axis discovery system (`discover_axis_values`, `compose_manifest`) to enumerate combinations and resolve paths. Loop through each combination, check if pipeline output exists, and delegate to the same `StatisticalEvaluator` used by the existing script. Load and normalize the reference population once upfront.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Axis discovery via `compose_manifest()` | Aligned with composable experiment system; filters map to axis IDs naturally | Requires axis YAML files to exist for each model | **Chosen** |
| Filesystem scan of `01_Raw/` directories | Works without axis files; finds any output | No structured metadata; can't derive `comparison_output_dir`; fragile slug parsing | Rejected |
| Wrapper shell script calling `compare_pipeline_to_scb.py` | Zero Python code; reuses existing script as-is | No shared summary; Windows compatibility issues; no structured output | Rejected |

### Architecture Changes

**Moved function:**
- `extract_population(seed_root)` moves from `scripts/compare_pipeline_to_scb.py` (lines 51-80) into `src/population_synth/comparison/extractor.py`
- The `sys.exit(1)` on zero files becomes `raise ValueError(...)` (fail-fast, but caller-friendly)

**New script structure:**
```
scripts/compare_all_pipelines.py
├── CLI argument parsing
├── Axis discovery + filtering
├── Reference population loading (once)
├── Main loop: for each (model, strategy, country)
│   ├── compose_manifest() → paths
│   ├── Check output dir exists with persona files
│   ├── extract_population() → pipeline_pop
│   ├── StatisticalEvaluator → report
│   ├── Write JSON + CSV + charts
│   └── Collect summary metrics
├── Print summary table
└── Write comparison_summary.json
```

---

## Implementation Plan

### Phase 1: Refactor `extract_population()`
**Started:** 2026-05-25
**Completed:** 2026-05-25

**Goal:** Make the extraction function importable from the comparison module

- [x] Move `extract_population()` from `scripts/compare_pipeline_to_scb.py:51-80` into `src/population_synth/comparison/extractor.py`
- [x] Replace `sys.exit(1)` on zero files with `raise ValueError(f"No persona_*/identity.json files found under {seed_root}")`
- [x] Keep `print()` progress messages (stdout, harmless for both scripts)
- [x] Update `scripts/compare_pipeline_to_scb.py` import: add `extract_population` to the existing `from population_synth.comparison.extractor import ...` line
- [x] Remove the inline function definition and the `import sys` if no longer needed elsewhere

**Files Modified:**
- `src/population_synth/comparison/extractor.py` — Add `extract_population()` function at the end of the module
- `scripts/compare_pipeline_to_scb.py` — Replace inline function with import; wrap call in try/except to preserve `sys.exit(1)` behavior for CLI usage

**Dependencies:** None

### Phase 2: New `compare_all_pipelines.py` script
**Started:** 2026-05-25
**Completed:** 2026-05-25

**Goal:** Batch comparison across all discovered axis combinations

- [x] Create `scripts/compare_all_pipelines.py`
- [x] CLI arguments: `--country` (default "swedish"), `--model` (repeatable, optional), `--strategy` (repeatable, optional), `--reference` (default SCB), `--no-charts`, `--radar-tv-only`
- [x] Axis discovery: call `discover_axis_values("models")`, `discover_axis_values("strategies")`, filter by CLI args and `--country`
- [x] Reference population: load and normalize once using `load_mappings()` + `normalize_if_raw()`
- [x] Main loop over `(model_id, strategy_id, country_id)` tuples:
  - `compose_manifest()` to get `parallel_output_dir` and `comparison_output_dir`
  - Check `parallel_output_dir` exists and contains `persona_*/identity.json` — skip with log if not
  - `extract_population(seed_root)` — catch `ValueError` and log as skipped
  - `StatisticalEvaluator(reference_pop, pipeline_pop).generate_report()`
  - Write JSON report to `comparison_output_dir/{slug}.json`
  - Write CSV via `write_csv_summary()`
  - Generate charts (unless `--no-charts`) via `plot_comparison_charts()` + `plot_radar_comparison()`
  - Collect summary: model, strategy, n, mean TV distance across attributes, coherence score
- [x] Print formatted summary table to stdout after all comparisons
- [x] Write `comparison_summary.json` to `{output_base}/03_Analysis/`

**Files Modified:**
- `scripts/compare_all_pipelines.py` — **New file**

**Dependencies:** Phase 1

---

## Testing Plan

### Manual Verification
- [ ] Run `compare_pipeline_to_scb.py --manifest config/seed_manifests/identity_manifest_014_claude_haiku.yaml` — confirm output is identical to before the refactor
- [ ] Run `compare_all_pipelines.py --country swedish` — confirm it discovers all model×strategy combos, skips missing output, produces reports
- [ ] Run with filters: `compare_all_pipelines.py --model claude_haiku --strategy all_pick` — confirm only that combo is compared
- [ ] Spot-check one combo's JSON/CSV/chart output against what `compare_pipeline_to_scb.py` produces for the same input
- [ ] Verify summary table prints with correct columns and `comparison_summary.json` is written

### Edge Cases
- [ ] No pipeline output exists for any combo — script prints "no comparisons to run" and exits cleanly
- [ ] One combo has output but all personas fail extraction — logged as error, other combos continue
- [ ] `--model` filter specifies an ID that doesn't exist in axis files — error with clear message
- [ ] `--reference` points to nonexistent file — fail-fast with clear error

---

## Documentation Plan

- [ ] Update CLAUDE.md commands section with new script usage examples
- [ ] Add docstring to the new script with usage examples

---

## Rollback Plan

1. Revert the `extract_population()` refactor by restoring the inline function in `compare_pipeline_to_scb.py` and removing it from `extractor.py`
2. Delete `scripts/compare_all_pipelines.py`
3. No data migrations or breaking changes — all output files are new artifacts

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `extract_population()` refactor breaks existing script | Low | High | Phase 1 tested in isolation before Phase 2 |
| Long runtime for 35 combos with charts | Medium | Low | `--no-charts` flag; `--model`/`--strategy` filters for subset runs |
| Axis YAML files missing for some models | Low | Low | Script logs "skipping" and continues |
| `comparison_output_dir` not writable (OneDrive path) | Low | Medium | Existing scripts already write there; same path resolution |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1: Refactor extract_population | Small (~20 lines moved) | None |
| Phase 2: New script | Medium (~150–200 lines) | Phase 1 |

---

## References

- Prior conversation: 2026-05-24 session `306f16bd` — initial design discussion
- Existing script: `scripts/compare_pipeline_to_scb.py`
- Axis system: `src/population_synth/identity/manifest_loader.py` (`discover_axis_values`, `compose_manifest`)
- Related completed plan: `docs/development/plans/completed/comparison-pipeline-outputs.md`
