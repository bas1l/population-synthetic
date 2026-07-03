# Plan: Standalone joint-fidelity analysis subpackage

**Date:** 2026-07-03
**Author:** Basil (with Claude)
**Status:** In Progress
**Base Branch:** `feature/multivariate-joint-fidelity`
**Branch:** `feature/joint-fidelity-independent`

---

## Overview

Promote the multivariate / joint-fidelity metrics (added to the comparison evaluator in the
[multivariate-joint-fidelity-evaluation](multivariate-joint-fidelity-evaluation.md) plan) into a
**standalone analysis process** that can run independently of the full compare stage. Where the
comparison evaluator computes the `multivariate` block as one part of a full per-combo comparison
report, this subpackage recomputes *only* that block over the already-mapped populations and writes
it to its own `03_Analysis/joint_fidelity/` folder. This lets the joint-fidelity story be
regenerated (and iterated on) without rerunning — or touching the outputs of — the comparison,
performance, or paper stages.

## Problem Statement

Joint fidelity currently only exists inside the comparison evaluator's report. To see updated
multivariate numbers you must rerun the whole compare pipeline, which rewrites every comparison
artifact and couples joint-fidelity iteration to the primary leaderboard outputs. The joint-fidelity
metrics are the newest and most experimental part of the stack, so they need a cheap, additive,
isolated way to be recomputed over the mapped index alone.

## Goals

### In Scope
1. **`analysis/joint_fidelity/` subpackage** — a standalone process that sits after the map stage and
   depends only on `map_populations`:
   - `builder.py` — `build_joint_fidelity()` (per-combo envelope reusing the shared
     `StatisticalEvaluator.compute_multivariate()`), `aggregate_joint_fidelity()` (per-country
     roll-up), plus JSON/CSV writers.
   - `charts.py` — thin orchestration reusing `comparison.charts.plot_association_heatmap` for the
     per-combo `|ΔV|` heatmap plus a self-contained cross-combo C2ST-vs-grounded-TV scatter.
   - `__init__.py` — package exports.
2. **`scripts/analyze/analyze_joint_fidelity.py`** — driver that iterates
   `{output_base}/03_Analysis/mapped/_index.json`, recomputes the joint-fidelity block per combo, and
   persists per-combo envelopes (JSON + association CSV + heatmap), a per-country roll-up (JSON/CSV),
   and the cross-combo scatter under `{output_base}/03_Analysis/joint_fidelity/`. Supports
   `--country`, `--slug`, `--output-base`, `--no-charts` filters.
3. **Wire into the gui_v2 analysis workflow** — add a `joint_fidelity` task to
   `config/gui/v2/flows/analysis_workflow.yaml` as a `slugs`-dispatch side branch depending only on
   `map_populations` (parallel to `compare_pops`), and cover it in `tests/test_workflow_state.py`
   (ordering + membership).
4. **Tests** — `tests/test_joint_fidelity.py` for the builder/aggregation/writer contract.
5. **Docs** — document the subpackage in `CLAUDE.md`, `docs/architecture/sub-packages.md`, and
   `docs/architecture/comparison-mapping.md`.

### Out of Scope
- **New metrics** — this is a repackaging of the existing `multivariate` block, not new statistics.
  Any change to what the block contains belongs to the multivariate-joint-fidelity-evaluation plan.
- **Writing under `comparison/` or `performance/`** — the process is strictly additive; it never
  touches those outputs.

## Success Criteria

- [x] `analyze_joint_fidelity.py` recomputes the joint-fidelity block over the mapped index and writes
      only under `03_Analysis/joint_fidelity/`.
- [x] The `joint_fidelity` gui_v2 task runs as an independent side branch (depends only on
      `map_populations`) and `test_workflow_state.py` asserts its ordering + membership.
- [x] `tests/test_joint_fidelity.py` passes.
- [x] The subpackage is documented in the architecture wiki and CLAUDE.md.

## Files Modified

- `src/population_synthetic/analysis/joint_fidelity/{__init__,builder,charts}.py` (new)
- `scripts/analyze/analyze_joint_fidelity.py` (new)
- `tests/test_joint_fidelity.py` (new)
- `config/gui/v2/flows/analysis_workflow.yaml`
- `tests/test_workflow_state.py`
- `CLAUDE.md`, `docs/architecture/sub-packages.md`, `docs/architecture/comparison-mapping.md`,
  `docs/development/gui-v2.md`
