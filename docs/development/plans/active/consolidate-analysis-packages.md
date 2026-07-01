# Plan: Consolidate analysis packages under `population_synthetic.analysis`

**Date:** 2026-07-01
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/extract-mapping-task`
**Branch:** `feature/consolidate-analysis-packages`

---

## Overview

Introduce a single `population_synthetic.analysis` parent package with **one
subpackage per process** — `mapping/`, `comparison/`, `llm_metrics/`, plus a
small `utils/` for shared infra. Today the mapping and population-comparison
processes are entangled inside one `comparison/` package, and `llm_metrics/`
sits separately at the top level. This is a **pure structural move** (`git mv` +
import rewrite) — no behavior, output, CLI, or schema change.

## Problem Statement

The post-generation tooling implements three distinct processes, but the
directory layout hides that:

1. **Mapping** — transform raw population data (national-statistics *or* LLM
   pipeline identities) into the canonical comparable schema.
2. **Population comparison** — statistically score and chart one population
   against a reference.
3. **LLM metrics** — post-run analytics on identity-generation LLM calls.

Processes (1) and (2) are mixed inside `src/population_synthetic/comparison/`, and
(3) lives in a sibling `src/population_synthetic/llm_metrics/`. Nothing signals that
these three form the "analysis" family, and the mapping-vs-comparison split is
invisible from the listing. This impedes navigation and blurs the
`comparison → mapping` dependency boundary.

## Goals

### In Scope
1. Create `src/population_synthetic/analysis/` as the parent of all three processes.
2. Split the current `comparison/` package into `analysis/mapping/` and
   `analysis/comparison/`.
3. Move `llm_metrics/` wholesale to `analysis/llm_metrics/`.
4. Place the shared `country_config.py` helper in a new `analysis/utils/`.
5. Rewrite every affected import (intra-package, scripts, tests) and keep the
   full test suite green — proving behavior is unchanged.

### Out of Scope
- Any logic, metric, statistic, chart, or schema change.
- Back-compat re-export shims at old paths — all call sites are in-repo and
  updated directly (same decision as the precedent `analysis-subpackage-layout`
  plan).
- Promoting functions into subpackage `__init__.py` namespaces — `__init__.py`
  files stay docstring-only; imports remain module-qualified.
- Rewriting path references inside **completed** plan docs under
  `docs/development/plans/completed/` (historical record).

## Success Criteria

- [x] `src/population_synthetic/analysis/` contains exactly four subpackages
      (`mapping`, `comparison`, `llm_metrics`, `utils`) plus a top-level
      `__init__.py`; no analysis module remains at `population_synthetic/` top level.
- [x] `python -m pytest tests/` passes unchanged, including the aggregator
      golden snapshot (`tests/data/expected_metrics.json` **not** edited).
- [x] `ruff check src/ scripts/` introduces no new lint (the move left no import
      unused; only the pre-existing E501/F401/I001 baseline remains).
- [x] The import smoke test and all entry-point `--help` invocations resolve
      (see Testing Plan).
- [x] `comparison → mapping` remains the only cross-process dependency direction
      (no `mapping → comparison`).

---

## Technical Design

### Approach

Mechanical Move-Module + import rewrite done as **one atomic restructure** so the
suite is green at the end (a half-moved package does not import). Use `git mv` to
preserve history. The repo convention is fully-qualified absolute imports
(`population_synthetic.analysis.<sub>.<module>`), so all rewritten imports use the new
absolute paths — including same-subpackage siblings that currently use an
absolute `population_synthetic.comparison.*` / `population_synthetic.llm_metrics.*`
prefix. Existing **relative** imports inside `reference_mapper/` and
`synthetic_mapper/` (`.base`, `.factory`, …) are unaffected.

`pyproject.toml` needs **no change** — `setuptools.packages.find (where=["src"])`
auto-discovers the new subpackages; the editable install resolves them without a
reinstall.

This reuses the exact methodology proven in
`docs/development/plans/completed/analysis-subpackage-layout.md`.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| `analysis/{mapping,comparison,llm_metrics,utils}` (chosen) | Folder == process; mapping/comparison split becomes visible; one clean parent | Import-path churn across scripts + tests | **Chosen** (user-directed) |
| Keep `comparison/` mixed, just nest under `analysis/` | Less churn | Mapping and comparison stay entangled — the primary problem persists | Rejected |
| `scheme.py` / `country_config.py` in `comparison/` | Fewer folders | `scheme` reaching into mapping, and mapping's map stage importing `country_config`, would create/reverse a `mapping ↔ comparison` cycle | Rejected |
| Back-compat shims at old paths | External imports unchanged | No external consumers; adds surface; hides new structure | Rejected |

### Architecture Changes

```
src/population_synthetic/analysis/
├── __init__.py                 # NEW — parent docstring: the three analysis processes
├── mapping/                    # raw -> canonical schema (process 1)
│   ├── __init__.py             # NEW — docstring
│   ├── mapping_engine.py
│   ├── flatten_raw.py
│   ├── extractor.py            # synthetic_mapper facade
│   ├── normalizer.py           # reference_mapper facade
│   ├── reference_mapper/       # (whole subpackage moved; relative imports intact)
│   └── synthetic_mapper/       # (whole subpackage moved; relative imports intact)
├── comparison/                 # statistical scoring + charts (process 2)
│   ├── __init__.py             # NEW — docstring
│   ├── evaluator.py
│   ├── charts.py
│   └── scheme.py               # bridge: comparison-purpose, reads mapping config
├── llm_metrics/                # LLM-call analytics (process 3) — moved wholesale
│   ├── __init__.py
│   ├── shared/_stats.py
│   ├── per_run/…
│   └── cross_run/…
└── utils/                      # NEW — cross-process shared infra
    ├── __init__.py             # NEW — docstring
    └── country_config.py
```

**Placement rationale (from exploration):**
- `scheme.py` is comparison-purpose but reads mapping config
  (`reference_mapper.factory._mapper_class`, `reference_mapper.mappings.index_path/load_index`).
  It lands in `comparison/`; the resulting `comparison → mapping` dependency is
  clean and one-directional.
- `country_config.py` is used by both the map stage and comparison consumers and
  has no internal comparison imports → its own `analysis/utils/` subpackage
  (user-selected), so neither process implicitly owns shared infra.
- `mapping_engine.py` ↔ `synthetic_mapper._text_helpers` and
  `synthetic_mapper` ↔ `reference_mapper.mappings` couplings stay entirely inside
  `mapping/` — unaffected.

**Prefix substitutions (import rewrite):**

| Old | New |
|-----|-----|
| `population_synthetic.comparison.{mapping_engine,flatten_raw,extractor,normalizer}` | `population_synthetic.analysis.mapping.<m>` |
| `population_synthetic.comparison.{reference_mapper,synthetic_mapper}` | `population_synthetic.analysis.mapping.<pkg>` |
| `population_synthetic.comparison.{evaluator,charts,scheme}` | `population_synthetic.analysis.comparison.<m>` |
| `population_synthetic.comparison.country_config` | `population_synthetic.analysis.utils.country_config` |
| `population_synthetic.llm_metrics.*` | `population_synthetic.analysis.llm_metrics.*` |

Unchanged cross-package imports (keep as-is):
`llm_metrics/cross_run/comparison_loader.py` → `population_synthetic.identity.manifest_loader`;
`utils/country_config.py` → `population_synthetic.identity.manifest_loader`, `population_synthetic._paths`.

---

## Implementation Plan

### Phase 1: Move modules + rewrite all imports (atomic)
**Goal:** The package is reorganized and the whole suite is green; no half-moved
intermediate state is committed.

- [x] 1.1 — Create the new tree with docstring-only `__init__.py` files:
      `analysis/__init__.py`, `analysis/mapping/__init__.py`,
      `analysis/comparison/__init__.py`, `analysis/utils/__init__.py`
      (no `__all__`, no re-exports — matches existing convention).
- [x] 1.2 — `git mv` the modules (preserve history):
      - `comparison/{mapping_engine,flatten_raw,extractor,normalizer}.py`,
        `comparison/reference_mapper/`, `comparison/synthetic_mapper/` → `analysis/mapping/`
      - `comparison/{evaluator,charts,scheme}.py` → `analysis/comparison/`
      - `comparison/country_config.py` → `analysis/utils/`
      - `llm_metrics/` → `analysis/llm_metrics/`
      - Delete the now-empty old `comparison/__init__.py` and the empty
        `comparison/` dir.
- [x] 1.3 — Rewrite intra-package absolute imports:
      - `mapping/mapping_engine.py` → `…mapping.synthetic_mapper._text_helpers`
      - `mapping/flatten_raw.py` → `…mapping.mapping_engine`
      - `mapping/extractor.py` → `…mapping.synthetic_mapper`
      - `mapping/normalizer.py` → `…mapping.reference_mapper.{factory,mappings,raw_format}`
      - `mapping/reference_mapper/base.py` → `…mapping.mapping_engine`
      - `mapping/synthetic_mapper/base.py` → `…mapping.mapping_engine`, `…mapping.reference_mapper.mappings`
      - `mapping/synthetic_mapper/factory.py` → `…mapping.reference_mapper.mappings`
      - `comparison/charts.py` → `…comparison.evaluator`
      - `comparison/evaluator.py` → `…comparison.scheme`
      - `comparison/scheme.py` → `…mapping.reference_mapper.{factory,mappings}`
      - `llm_metrics/per_run/{charts,aggregator}.py` → `…llm_metrics.shared._stats`
      - `llm_metrics/cross_run/comparison_stats.py` → `…llm_metrics.shared._stats`
      - `llm_metrics/cross_run/run_comparison.py` → `…llm_metrics.{cross_run.comparison_loader, cross_run.comparison_stats, shared._stats}`
- [x] 1.4 — Rewrite script imports.
- [x] 1.5 — Rewrite test imports.

**Files Modified:**
- ~20 moved modules (paths change; ~13 also get import edits) under
  `src/population_synthetic/analysis/{mapping,comparison,llm_metrics,utils}/`
- Scripts: `scripts/analyze/{map_populations,compare_populations,compare_countries,compare_pipeline_to_scb,compare_pipeline_to_istat,compare_all_pipelines,analyze_run,compare_runs}.py`,
  `scripts/generate/extract_population_from_pipeline.py`
- Tests: `tests/{test_mapping_engine,test_reference_mapper_base,test_synthetic_mapper_base,test_mapper_delegation,test_extractor_characterization,test_scheme_index,test_evaluator,test_synthetic_reference_vocab_subset,test_aggregator,test_call_context,test_joiner,test_log_parser,test_run_comparison,test_stats}.py`

**Dependencies:** None

### Phase 2: Validate + document
**Goal:** Prove behavior is unchanged and update the living docs.

- [x] 2.1 — `python -m pytest tests/` green (golden snapshot unmodified).
- [x] 2.2 — `ruff check src/ scripts/` clean; drop any now-unused import.
- [x] 2.3 — Import smoke test + entry-point `--help` all resolve.
- [x] 2.4 — Update living docs (leave completed plans untouched):
      `CLAUDE.md` (Architecture section + old package-path references),
      `docs/architecture/sub-packages.md` (replace `comparison/` + `llm_metrics/`
      entries with the new `analysis/{mapping,comparison,llm_metrics,utils}` layout),
      `docs/architecture/comparison-mapping.md` (update module paths).

**Files Modified:**
- `CLAUDE.md`, `docs/architecture/sub-packages.md`,
  `docs/architecture/comparison-mapping.md`

**Dependencies:** Phase 1

---

## Testing Plan

### Unit Tests
- [x] All 14 affected test files resolve against the new import paths and pass.
- [x] Aggregator golden snapshot passes with `tests/data/expected_metrics.json`
      unchanged (a diff means an import rewrite altered behavior — rework, never
      edit the snapshot).

### Integration Tests
- [x] Full `python -m pytest tests/` green after Phase 1.

### Manual Verification
- [x] Import smoke test (editable install picks up new subpackages, no reinstall):
      ```bash
      python -c "import population_synthetic.analysis.mapping.mapping_engine, \
        population_synthetic.analysis.comparison.evaluator, \
        population_synthetic.analysis.llm_metrics.per_run.aggregator, \
        population_synthetic.analysis.utils.country_config"
      ```
- [x] `python scripts/analyze/map_populations.py --help`,
      `compare_pipeline_to_scb.py --help`, `analyze_run.py --help`,
      `compare_runs.py --help` all resolve imports.

### Edge Cases
- [x] `__file__`-relative path math: confirm moved modules derive paths from
      `population_synthetic._paths.PROJECT_ROOT` (not local `Path(__file__).parents[N]`),
      so deeper nesting shifts no resolved path. (Exploration found none — verify.)

---

## Documentation Plan

- [x] Update `CLAUDE.md` Architecture section + old package-path references.
- [x] Update `docs/architecture/sub-packages.md` (new `analysis/` layout).
- [x] Update `docs/architecture/comparison-mapping.md` (module paths).
- [x] Docstring-only `__init__.py` for `analysis/`, `analysis/mapping/`,
      `analysis/comparison/`, `analysis/utils/` naming each process.
- [x] No user-facing README/command change (CLI + outputs unchanged).

---

## Rollback Plan

Pure structural refactor on a feature branch; nothing deployed or migrated.

1. The move is a single coherent Phase-1 commit — `git revert` it (or reset the
   branch) to return to the prior layout; `git mv` preserves history either way.
2. No data/schema/output change, so nothing to migrate or reset.
3. A golden-snapshot diff is the stop signal: it means an import rewrite changed
   behavior (impossible for a pure move) — rework, never edit the snapshot.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| A missed import site leaves an unresolvable module | Med | Med | Import map is exhaustive (grep-derived from three Explore sweeps); Phase 2.1/2.3 catch any miss immediately |
| Editable install fails to discover new subpackages | Low | Med | `setuptools.find` auto-includes `__init__.py` subpackages; Phase 2.3 verifies via `--help`; `pip install -e .` if needed |
| `git mv` history not preserved on Windows | Low | Low | Use `git mv` (not delete+add); verify with `git log --follow` on one moved file |
| `scheme.py` split re-introduces a mapping↔comparison cycle | Low | Med | `scheme` in `comparison/` importing `mapping/` is one-way; nothing in `mapping/` imports `comparison/` — verified in exploration |
| Scope creep into namespace re-exports / shims | Med | Low | Out-of-scope section explicit; `__init__.py` stays docstring-only |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — move + rewrite imports | ~2-3 hours | None |
| Phase 2 — validate + document | ~1 hour | Phase 1 |

---

## References

- Precedent (same methodology): `docs/development/plans/completed/analysis-subpackage-layout.md`
- Architecture wiki: `docs/architecture/sub-packages.md`, `docs/architecture/comparison-mapping.md`

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- CLAUDE.md
- docs/architecture/commands.md
- docs/architecture/comparison-mapping.md
- docs/architecture/configuration.md
- docs/architecture/design-principles.md
- docs/architecture/sub-packages.md
- docs/development/plans/active/consolidate-analysis-packages.md
- scripts/analyze/analyze_run.py
- scripts/analyze/compare_all_pipelines.py
- scripts/analyze/compare_countries.py
- scripts/analyze/compare_pipeline_to_istat.py
- scripts/analyze/compare_pipeline_to_scb.py
- scripts/analyze/compare_populations.py
- scripts/analyze/compare_runs.py
- scripts/analyze/map_populations.py
- scripts/generate/extract_population_from_pipeline.py
- src/population_synthetic/analysis/__init__.py
- src/population_synthetic/analysis/comparison/__init__.py
- src/population_synthetic/analysis/comparison/charts.py
- src/population_synthetic/analysis/comparison/evaluator.py
- src/population_synthetic/analysis/comparison/scheme.py
- src/population_synthetic/analysis/llm_metrics/ (moved wholesale from src/population_synthetic/llm_metrics/)
- src/population_synthetic/analysis/mapping/ (mapping_engine, flatten_raw, extractor, normalizer, reference_mapper/, synthetic_mapper/ — moved from comparison/)
- src/population_synthetic/analysis/mapping/__init__.py
- src/population_synthetic/analysis/utils/__init__.py
- src/population_synthetic/analysis/utils/country_config.py
- src/population_synthetic/comparison/ (deleted — old __init__.py removed, package emptied)
- tests/ (14 affected test files + _mapping_fixtures.py — import paths rewritten)

---
