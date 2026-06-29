# Plan: Analysis Pipeline — Two-Level Subpackage Layout

**Date:** 2026-06-29
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/analysis-separation-of-concerns`
**Branch:** `feature/analysis-subpackage-layout`

---

## Overview

Reorganize the flat `src/population_synth/analysis/` package into three
subpackages — `shared/`, `per_run/`, `cross_run/` — so the folder structure
mirrors the actual workflow: the per-run pipeline (parse → join → aggregate →
report) produces `run_analytics.json`, which the cross-run pipeline (load →
test → build → visualize) consumes. Pure structural move; no behavior, output,
or CLI change.

## Problem Statement

After the separation-of-concerns refactor the package has eleven flat modules.
Each is single-concern, but the **workflow** — which files form the per-run
pipeline, which form the cross-run pipeline, and what is shared — is not visible
from the directory listing. The pipeline is a "two-level" analytics pipeline
(per-unit then cross-unit, per the engineering standard `01 §5`), and the two
levels map 1:1 to the two entry-point scripts (`analyze_run.py`,
`compare_runs.py`). Grouping the modules by level makes the dataflow legible at
a glance and keeps each whole pipeline in one folder.

## Goals

### In Scope
1. Create `analysis/shared/`, `analysis/per_run/`, `analysis/cross_run/`
   subpackages, each with an `__init__.py` whose docstring names the pipeline
   and its stage order.
2. Move each module into the subpackage matching its role (see Architecture).
3. Rewrite every affected import: 4 intra-package modules, 2 scripts, 6 test
   files.
4. Keep all public functions, output schemas, chart filenames, and CLI flags
   identical — proven by the existing test suite (golden snapshot included).

### Out of Scope
- Any change to logic, metric definitions, statistics, or chart output.
- Adding back-compat re-export shims at `analysis/__init__.py`. There are no
  consumers outside this repo; all call sites (scripts + tests) are updated
  directly. (Re-export shims would defeat the legibility goal and add surface.)
- Promoting module functions into subpackage `__init__.py` namespaces
  (`from analysis.per_run import compute_metrics`). Keep `__init__.py` files
  docstring-only for now (YAGNI); imports stay module-qualified.
- The deferred clarity/DRY items (timestamp-parse, color constants, matplotlib
  boilerplate) from the prior plan — still separate work.

## Success Criteria

- [ ] `analysis/` contains exactly three subpackages (`shared`, `per_run`,
      `cross_run`) plus the top-level `__init__.py`; no analytics module remains
      at the top level.
- [ ] `python -m pytest tests/` passes unchanged, including
      `test_compute_metrics_matches_golden_snapshot` (snapshot file **not**
      edited).
- [ ] `ruff check src/ scripts/` is clean (no unused/again-flagged imports).
- [ ] `python scripts/analyze_run.py --help` and
      `python scripts/compare_runs.py --help` succeed (imports resolve).
- [ ] No file under `analysis/` imports "upward" across levels except through
      `shared/` (per_run and cross_run do not import each other).

---

## Technical Design

### Approach

Mechanical Move-Module + import rewrite, done as one atomic restructure so the
test suite is green at the end of the move phase (a half-moved package does not
import). Use `git mv` to preserve history. The project convention is
fully-qualified absolute imports (`population_synth.analysis.<sub>.<module>`),
so all rewritten imports use the new absolute paths — including same-subpackage
sibling imports inside `cross_run/`.

`pyproject.toml` uses `setuptools.packages.find` with `where = ["src"]`, which
auto-discovers any subpackage containing an `__init__.py`; no build-config change
is needed, and the editable install picks up the new subdirs at import time
without reinstall (verified in Phase 2).

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Two-level subpackages (chosen) | Folder == workflow; each pipeline in one place; maps to the two scripts | Import-path churn across scripts + tests | **Chosen** (user-selected) |
| Group by layer (`io/`, `compute/`, `stats/`, `report/`) | Tidy by responsibility type | Splits one run across 3 folders — hurts workflow legibility | Rejected |
| Keep flat + dataflow map in `__init__.py` | Zero churn | Structure still not visible in the listing | Rejected (user chose folders) |
| Add back-compat shims at `analysis/__init__.py` | External imports unchanged | No external consumers; adds surface; hides the new structure | Rejected |

### Architecture Changes

```
analysis/
├── __init__.py                  # top-level package docstring: the two-level workflow
├── shared/
│   ├── __init__.py
│   └── _stats.py                # stdlib numeric primitives (median/percentile/entropy)
├── per_run/                     # pipeline A (analyze_run.py): one run → analytics + report
│   ├── __init__.py              #   docstring: parse → join → aggregate → visualize/report
│   ├── interaction_parser.py
│   ├── log_parser.py
│   ├── joiner.py
│   ├── aggregator.py
│   ├── charts.py
│   └── console_report.py
└── cross_run/                   # pipeline B (compare_runs.py): many analytics → comparison
    ├── __init__.py              #   docstring: load → test → build → visualize
    ├── comparison_loader.py
    ├── comparison_stats.py
    ├── run_comparison.py
    └── comparison_charts.py
```

**Import rewrite map (the complete set):**

Intra-package (4 modules):
- `per_run/charts.py`: `population_synth.analysis._stats` → `population_synth.analysis.shared._stats` (2 lines)
- `per_run/aggregator.py`: `population_synth.analysis._stats` → `...shared._stats` (1 line)
- `cross_run/comparison_stats.py`: `from population_synth.analysis import _stats` → `from population_synth.analysis.shared import _stats` (1 line)
- `cross_run/run_comparison.py`: `_stats` → `shared._stats`; `comparison_loader` → `cross_run.comparison_loader`; `comparison_stats` → `cross_run.comparison_stats` (3 import statements)

`cross_run/comparison_loader.py` keeps its cross-package
`from population_synth.identity.manifest_loader import discover_axis_values`
unchanged. `interaction_parser`, `log_parser`, `joiner`, `console_report`,
`comparison_charts` have no intra-analysis imports.

Scripts (8 import lines):
- `scripts/analyze_run.py` → `aggregator`, `charts`, `console_report`,
  `interaction_parser`, `joiner`, `log_parser` all become `...analysis.per_run.<m>`
- `scripts/compare_runs.py` → `comparison_charts`, `run_comparison` become
  `...analysis.cross_run.<m>`

Tests (6 files):
- `test_aggregator.py` → `analysis.per_run.aggregator`
- `test_call_context.py` → `analysis.per_run.log_parser`
- `test_joiner.py` → `analysis.per_run.joiner`
- `test_log_parser.py` → `analysis.per_run.log_parser`
- `test_run_comparison.py` → `analysis.cross_run.run_comparison`
- `test_stats.py` → `analysis.shared._stats`

---

## Implementation Plan

### Phase 1: Move modules into subpackages + rewrite all imports (atomic)
**Goal:** The package is reorganized and the whole suite is green; no half-moved
intermediate state is committed.

**Started:** 2026-06-29
**Completed:** 2026-06-29

- [x] 1.1 — Create `shared/`, `per_run/`, `cross_run/` directories each with an
      `__init__.py` carrying a concern/dataflow docstring (per_run: parse → join
      → aggregate → visualize/report; cross_run: load → test → build → visualize;
      shared: numeric primitives used by both).
- [x] 1.2 — `git mv` `_stats.py` → `shared/`; `interaction_parser.py`,
      `log_parser.py`, `joiner.py`, `aggregator.py`, `charts.py`,
      `console_report.py` → `per_run/`; `comparison_loader.py`,
      `comparison_stats.py`, `run_comparison.py`, `comparison_charts.py` →
      `cross_run/`.
- [x] 1.3 — Rewrite the 4 intra-package import statements per the map above
      (`charts`, `aggregator`, `comparison_stats`, `run_comparison`).
- [x] 1.4 — Rewrite the 8 import lines in `scripts/analyze_run.py` and
      `scripts/compare_runs.py`.
- [x] 1.5 — Rewrite the imports in all 6 test files per the map above.
- [x] 1.6 — Add a top-level `analysis/__init__.py` docstring describing the
      two-level workflow (the ASCII dataflow), replacing the current one-line
      comment.

**Files Modified:**
- `src/population_synth/analysis/{shared,per_run,cross_run}/__init__.py` — NEW
- `src/population_synth/analysis/__init__.py` — workflow docstring
- 11 moved modules (paths change; 4 of them also get import edits)
- `scripts/analyze_run.py`, `scripts/compare_runs.py`
- `tests/test_aggregator.py`, `tests/test_call_context.py`, `tests/test_joiner.py`,
  `tests/test_log_parser.py`, `tests/test_run_comparison.py`, `tests/test_stats.py`

**Dependencies:** None

### Phase 2: Validate + document
**Goal:** Prove behavior is unchanged and update the architecture docs.

**Started:** 2026-06-29
**Completed:** 2026-06-29

- [x] 2.1 — `python -m pytest tests/` — full suite green incl. golden snapshot
      (snapshot file unmodified). If anything fails, fix the import path, never
      the snapshot.
- [x] 2.2 — `ruff check src/ scripts/` clean on touched files; remove any import
      left unused by the move.
- [x] 2.3 — `python scripts/analyze_run.py --help` and
      `python scripts/compare_runs.py --help` both succeed (confirms editable
      install discovers the new subpackages without reinstall).
- [x] 2.4 — Update CLAUDE.md `analysis/` sub-package section to describe the
      new `shared/` `per_run/` `cross_run/` layout and the two-level workflow.

**Files Modified:**
- `CLAUDE.md` — analysis sub-package description

**Dependencies:** Phase 1

---

## Testing Plan

### Unit Tests
- [ ] All 6 existing test files pass against the new import paths.
- [ ] `test_compute_metrics_matches_golden_snapshot` passes with
      `tests/data/expected_metrics.json` unchanged.

### Integration Tests
- [ ] Full `pytest tests/` green after Phase 1.

### Manual Verification
- [ ] `analyze_run.py --help` and `compare_runs.py --help` resolve imports.
- [ ] (If a sample run dir is handy) `analyze_run.py <dir>` and
      `compare_runs.py --root <llm_metrics>` produce identical JSON/PNG/console
      output to the pre-move commit.

### Edge Cases
- [ ] Editable install resolves `population_synth.analysis.per_run.*` etc.
      without a `pip install -e .` reinstall (path-based discovery).

---

## Documentation Plan

- [ ] Update CLAUDE.md `analysis/` section (the module list and the workflow).
- [ ] Subpackage `__init__.py` docstrings naming each pipeline and stage order.
- [ ] Top-level `analysis/__init__.py` dataflow docstring.
- [ ] No README user-facing change (commands/outputs unchanged).

---

## Rollback Plan

Pure structural refactor on a feature branch; nothing deployed or migrated.

1. The move is a single coherent Phase-1 commit — `git revert` it (or reset the
   branch) to return to the flat layout; `git mv` preserves history either way.
2. No data/schema/output change, so nothing to migrate or reset.
3. A golden-snapshot diff is the stop signal: it means an import rewrite changed
   behavior (it should not be possible for a pure move) — rework, never edit the
   snapshot.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| A missed import site leaves an unresolvable module | Med | Med | The import map in this plan is exhaustive (grep-derived); Phase 2.1/2.3 catch any miss immediately |
| Editable install fails to discover new subpackages | Low | Med | `setuptools.find` auto-includes `__init__.py` subpackages; Phase 2.3 verifies via `--help`; reinstall `pip install -e .` if needed |
| `git mv` history not preserved on Windows | Low | Low | Use `git mv` (not delete+add); verify with `git log --follow` on one moved file |
| Scope creep into namespace re-exports / shims | Med | Low | Out-of-scope section explicit; `__init__.py` stays docstring-only |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — move + rewrite imports | ~2-3 hours | None |
| Phase 2 — validate + document | ~1 hour | Phase 1 |

---

## References

- Predecessor: `docs/development/plans/active/analysis-pipeline-separation-of-concerns.md`
  (this plan builds on its module split)
- Standard: `docs/data-pipeline-engineering/01-system-classification.md` (§5
  two-level pattern), `02-architecture-principles-and-patterns.md` (§2 layering)
- Safety net: `tests/` (6 files incl. the aggregator golden snapshot)

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
<!-- The 11 analysis modules are git RENAMES (old flat path -> new subpackage path);
     stage both the new path and the corresponding deleted old path so the rename commits cleanly. -->
- CLAUDE.md
- docs/development/plans/active/analysis-subpackage-layout.md
- scripts/analyze_run.py
- scripts/compare_runs.py
- src/population_synth/analysis/__init__.py
- src/population_synth/analysis/cross_run/__init__.py
- src/population_synth/analysis/cross_run/comparison_charts.py
- src/population_synth/analysis/cross_run/comparison_loader.py
- src/population_synth/analysis/cross_run/comparison_stats.py
- src/population_synth/analysis/cross_run/run_comparison.py
- src/population_synth/analysis/per_run/__init__.py
- src/population_synth/analysis/per_run/aggregator.py
- src/population_synth/analysis/per_run/charts.py
- src/population_synth/analysis/per_run/console_report.py
- src/population_synth/analysis/per_run/interaction_parser.py
- src/population_synth/analysis/per_run/joiner.py
- src/population_synth/analysis/per_run/log_parser.py
- src/population_synth/analysis/shared/__init__.py
- src/population_synth/analysis/shared/_stats.py
- tests/test_aggregator.py
- tests/test_call_context.py
- tests/test_joiner.py
- tests/test_log_parser.py
- tests/test_run_comparison.py
- tests/test_stats.py

Rename sources (old flat paths, now deleted — stage these deletions too):
- src/population_synth/analysis/_stats.py
- src/population_synth/analysis/aggregator.py
- src/population_synth/analysis/charts.py
- src/population_synth/analysis/comparison_charts.py
- src/population_synth/analysis/comparison_loader.py
- src/population_synth/analysis/comparison_stats.py
- src/population_synth/analysis/console_report.py
- src/population_synth/analysis/interaction_parser.py
- src/population_synth/analysis/joiner.py
- src/population_synth/analysis/log_parser.py
- src/population_synth/analysis/run_comparison.py

**Explicitly EXCLUDE (pre-existing, unrelated to this plan):**
CLAUDE.md is INCLUDED above; but do NOT stage: `scripts/compare_all_pipelines.py`,
`scripts/compare_pipeline_to_istat.py`, `src/population_synth/comparison/extractor.py`,
`src/population_synth/comparison/normalizer.py`, `src/population_synth/population/norway/*`,
`config/assets/*/category_mappings.json` (deletions), `config/comparison/`,
`config/assets/istat_cache/`, `scripts/_throwaway_*.py`, `identity.json`,
`llm_interactions.jsonl`, `logs/`, `run_metadata.json`.

---
