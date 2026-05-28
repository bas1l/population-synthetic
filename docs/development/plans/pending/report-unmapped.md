# Plan: Unmapped Category Report Script

**Date:** 2026-05-25
**Author:** Basil
**Status:** Draft
**Base Branch:** `feature/prototype-istat-api`
**Branch:** `feature/report-unmapped`

---

## Overview

Add `scripts/report_unmapped.py` — a read-only script that discovers all model × strategy × country combinations via the axis system, opens each existing `{slug}.json` report in `03_Analysis/`, and prints a consolidated view of unmapped categories. Unmapped category data is already stored in each per-combo JSON report but is inaccessible without opening 35 files individually.

## Problem Statement

`compare_all_pipelines.py` writes `{slug}.json` reports that include `marginals[attr].unmapped` (categories in the pipeline output with no matching entry in the SCB reference) and `unknown_count_b` (personas mapped to `"Non-standard label"`). These warnings are visible in the GUI console during the run but are not surfaced in any aggregated form afterwards. Surveying unmapped issues across all models and strategies requires manually opening every individual report file.

## Goals

### In Scope
1. Read existing `{slug}.json` files using the same axis discovery as `compare_all_pipelines.py`
2. Print a per-combo block showing unmapped categories per attribute and `unknown_count_b`
3. Optional `--output` flag to write the aggregated data as JSON
4. Same `--country`, `--model`, `--strategy` CLI filters as `compare_all_pipelines.py`

### Out of Scope
- Writing or modifying any report files
- Re-running comparisons
- Surfacing per-persona extraction-level logger warnings (those are not in the JSON reports)
- GUI integration

## Success Criteria

- [ ] Script prints one block per combo; combos with no unmapped data print `(none)` explicitly
- [ ] Unmapped category values and `unknown_count_b` counts match the corresponding `{slug}.json`
- [ ] Combos with no JSON report file are skipped with a clear log message
- [ ] `--model`/`--strategy` filters correctly restrict output
- [ ] `--output` writes a valid JSON file with all combos' data

---

## Technical Design

### Approach

Reuse `discover_axis_values` + `compose_manifest` to enumerate combinations and resolve `comparison_output_dir`. For each combo, open `{comparison_output_dir}/{slug}.json` if it exists and extract `unmapped` and `unknown_count_b` from `marginals`. No new imports beyond what `compare_all_pipelines.py` already uses.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Axis discovery via `compose_manifest()` | Same pattern as existing scripts; filters map naturally | Requires axis YAML files to exist | **Chosen** |
| Filesystem scan of `03_Analysis/` dirs | Works without axis files | Fragile slug parsing; can't validate combos against axes | Rejected |

### Architecture Changes

No existing files modified. New read-only script only.

```
scripts/report_unmapped.py
├── CLI argument parsing (--country, --model, --strategy, --output)
├── Axis discovery + filtering (same as compare_all_pipelines.py)
├── Loop over combos:
│   ├── compose_manifest() → comparison_output_dir
│   ├── Open {slug}.json if exists, else skip
│   └── Collect unmapped + unknown_count_b per attribute
├── Print formatted per-combo blocks to stdout
└── Optionally write JSON to --output path
```

---

## Implementation Plan

### Phase 1: New `report_unmapped.py` script
**Goal:** Implement the full script in one phase (it is small — ~80 lines)

- [ ] Create `scripts/report_unmapped.py`
- [ ] CLI arguments: `--country` (repeatable, default `swedish`), `--model` (repeatable, optional), `--strategy` (repeatable, optional), `--output` (optional path)
- [ ] Copy `_split_csv()` helper from `compare_all_pipelines.py` and apply to filter args
- [ ] Axis discovery + filter validation (raise `ValueError` on unknown IDs, same as `compare_all_pipelines.py`)
- [ ] Loop: `compose_manifest()` → open `{comparison_output_dir}/{slug}.json` → extract `unmapped` + `unknown_count_b` from `marginals`
- [ ] Stdout output: one block per combo, header `[{slug}]  n={n}`, one line per attribute with unmapped values and `(unknown_b=N)`, `(none)` when clean
- [ ] `--output`: write list of `{slug, n, unmapped, unknown_count_b}` dicts as JSON

**Files Modified:**
- `scripts/report_unmapped.py` — **New file**

**Dependencies:** None (reads existing output files; no changes to comparison pipeline)

---

## Testing Plan

### Manual Verification
- [ ] Run `python scripts/report_unmapped.py` — confirm one block per combo, `(none)` for clean combos
- [ ] Spot-check one combo: open the corresponding `{slug}.json` manually and verify the printed unmapped categories and counts match `marginals[attr].unmapped` and `unknown_count_b`
- [ ] Run `--model claude_haiku --strategy all_pick` — confirm only that combo appears
- [ ] Run `--output report.json` — confirm file is written and parses as valid JSON

### Edge Cases
- [ ] No `{slug}.json` exists for any combo — all skipped, prints "No report files found"
- [ ] `--model` specifies unknown ID — raises clear `ValueError` before reading any files
- [ ] All combos are clean (no unmapped) — every block shows `(none)`

---

## Documentation Plan

- [ ] Update CLAUDE.md commands section with usage example for `report_unmapped.py`

---

## Rollback Plan

1. Delete `scripts/report_unmapped.py`
2. No data files or existing code are touched — zero rollback risk

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `{slug}.json` schema differs from expected (old run format) | Low | Low | Skip gracefully with a warning if `marginals` key missing |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1: New script | Small (~80 lines) | None |

---

## References

- Existing script: `scripts/compare_all_pipelines.py` (axis discovery + `_split_csv` pattern)
- Report format: `src/population_synth/comparison/evaluator.py` (`generate_report()`, `_marginal_metrics()`)
- Output location: `config/experiment_defaults.yaml` → `output_base/03_Analysis/{slug}/{slug}.json`
