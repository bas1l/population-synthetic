# Plan: Analysis Pipeline — Separation of Concerns Refactor

**Date:** 2026-06-29
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/italy-identity-comparison-pipeline`
**Branch:** `feature/analysis-separation-of-concerns`

---

## Overview

Three behavior-preserving structural refactors of `src/population_synth/analysis/`
to enforce the project's one-file/one-concern style: (1) split the multi-concern
`run_comparison.py` into stats / loader / builder modules, (2) decompose the
325-line `compute_metrics` function into one helper per metric family, and (3)
lift the console-report formatters out of `scripts/analyze_run.py` into a
dedicated presentation module. No metric values, output schemas, or CLI behavior
change.

## Problem Statement

The parsing and charting layers are cleanly separated (one file, one concern),
but three hotspots mix responsibilities and hurt readability and testability:

- **`run_comparison.py`** (~520 lines) spans four layers of the
  architecture-standard layering table at once — config/registry, DTO,
  transformation, **I/O**, **statistics**, build, and serialization. The
  hypothesis tests (Kruskal/Dunn/Holm) live here while the other numeric
  primitives live in `_stats.py`, so "where are the statistics" has two answers.
  `load_run_records` welds filesystem walking to metric reshaping, so the
  reshaping cannot be tested without a filesystem.
- **`aggregator.compute_metrics`** is a single ~325-line function computing 12
  independent metric families inline, separated only by banner comments. No
  family can be read, named, or unit-tested in isolation.
- **`scripts/analyze_run.py`** mixes orchestration (CLI, config, batch loop) with
  ~200 lines of console-table formatting across nine `_print_*` functions. The
  presentation concern (metrics dict → text table) is self-contained and belongs
  in its own module, mirroring how `charts.py` already separates PNG rendering.

This is technical debt in the maintainability sense: the design is correct but
change-amplifying — touching one metric family means scrolling past eleven
others, and the comparison stats can't move without dragging I/O along.

## Goals

### In Scope
1. Split `run_comparison.py` into focused modules (stats, loader, builder).
2. Decompose `compute_metrics` into one private helper per metric family, with
   `compute_metrics` reduced to a thin assembler.
3. Extract the `_print_*` console formatters from `analyze_run.py` into
   `analysis/console_report.py`.
4. Keep all public entry points, output JSON schemas, chart filenames, and CLI
   flags byte-for-byte identical (proven by the existing golden snapshot test).

### Out of Scope
- Any change to metric definitions, statistical methods, or chart appearance.
- The higher-tier findings from the architecture review (typed DTOs / schema
  versioning, provenance stamping, parser tests, effect sizes, rate
  denominators). Those are separate plans; this one is *structure only*.
- De-duplicating timestamp parsing, color constants, or the matplotlib
  deferred-import boilerplate (tracked as a follow-up clarity pass; may be folded
  in opportunistically only where a move already touches the code).
- Renaming any public function or changing import paths used outside
  `analysis/` (the two scripts are the only external callers and are updated
  here).

## Success Criteria

- [ ] `run_comparison.py` no longer performs filesystem I/O and no longer defines
      the hypothesis tests; both live in dedicated modules.
- [ ] `compute_metrics` body is a short assembler (target < 40 lines) calling one
      named helper per metric family.
- [ ] `analyze_run.py` contains no `_print_*` table-formatting code; it imports a
      reporter module instead.
- [ ] `pytest tests/` passes unchanged, including the
      `test_compute_metrics_matches_golden_snapshot` golden test (the snapshot
      file is **not** modified).
- [ ] `ruff check src/ scripts/` is clean.
- [ ] `python scripts/analyze_run.py <run_dir>` and
      `python scripts/compare_runs.py` produce identical console output, JSON, and
      chart files to `main` for a sample run (manual diff).

---

## Technical Design

### Approach

Pure mechanical refactoring via Extract Function and Move Function, in small
test-backed steps. The existing test suite (`test_aggregator` golden + behavioral,
`test_run_comparison` for Holm/Dunn/slug/summarize, `test_stats`, `test_joiner`)
is the safety net; tests must stay green at every step. Each phase is independent
and independently revertable.

Module boundaries follow the standard's layering table: I/O → transformation →
statistical → computation → presentation, dependencies pointing one way.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Split into focused modules (chosen) | Each file one concern; stats testable without I/O; matches existing parser/chart layering | Touches import sites in 2 scripts + tests | **Chosen** |
| Keep files, only extract private functions within them | Smaller diff | `run_comparison.py` still spans 4 layers; stats still split across 2 homes | Rejected — doesn't fix the core issue |
| Collapse comparison stats into `_stats.py` | One home for all numbers | `_stats.py` is stdlib-only by design; KW/Dunn need scipy/numpy — would pollute its dependency surface | Rejected — keep `_stats.py` dependency-light; new `comparison_stats.py` carries the scipy/numpy stats |

### Architecture Changes

New modules under `src/population_synth/analysis/`:

```
analysis/
├── _stats.py               # unchanged — stdlib numeric primitives
├── comparison_stats.py     # NEW — kruskal_test, _holm, dunn_posthoc, summarize, _nonempty_groups
├── comparison_loader.py    # NEW — RunRecord, MetricSpec, METRIC_SPECS, decompose_slug,
│                           #       extract_comparison_metrics, load_run_records
├── run_comparison.py       # SLIMMED — build_comparison, comparison_to_json,
│                           #           write_comparison_json, group/aggregate helpers
├── aggregator.py           # compute_metrics becomes assembler + per-family helpers
├── console_report.py       # NEW — all _print_* formatters + _fmt_* helpers
├── charts.py               # unchanged
├── comparison_charts.py    # unchanged
├── interaction_parser.py   # unchanged
├── log_parser.py           # unchanged
└── joiner.py               # unchanged
```

Decision on `MetricSpec`/`METRIC_SPECS`/`RunRecord`: these are the data contract
shared by loader, builder, and the comparison charts. Placing them in
`comparison_loader.py` keeps the registry next to the extraction that produces
samples for it. `run_comparison.py` and `compare_runs.py` re-import them. To avoid
churn in `compare_runs.py` (which imports `METRIC_SPECS`, `METRIC_SPECS_BY_KEY`,
`build_comparison`, `load_run_records`, `write_comparison_json` from
`run_comparison`), `run_comparison.py` will **re-export** the moved names so the
existing import line keeps working:

```python
from population_synth.analysis.comparison_loader import (
    METRIC_SPECS, METRIC_SPECS_BY_KEY, RunRecord, MetricSpec,
    decompose_slug, extract_comparison_metrics, load_run_records,
)
```

This makes Phase 1 a non-breaking move and lets the script import-site update be
optional cleanup rather than a hard dependency.

---

## Implementation Plan

### Phase 1: Split `run_comparison.py`
**Goal:** One file per concern in the cross-run path; stats and I/O leave the
builder module.

**Started:** 2026-06-29
**Completed:** 2026-06-29

- [x] 1.1 — Create `comparison_stats.py`; move `_nonempty_groups`, `kruskal_test`,
      `_holm`, `dunn_posthoc`, and `summarize` (plus their `numpy`/`scipy` imports).
- [x] 1.2 — Create `comparison_loader.py`; move `MetricSpec`, `METRIC_SPECS`,
      `METRIC_SPECS_BY_KEY`, `RunRecord`, `decompose_slug`,
      `extract_comparison_metrics`, `load_run_records`, and the
      `discover_axis_values` import.
- [x] 1.3 — Slim `run_comparison.py` to `_aggregate`, `_group_samples`,
      `_order_by_median`, `build_comparison`, `comparison_to_json`,
      `write_comparison_json`; import stats from `comparison_stats` and the
      registry/loader from `comparison_loader`.
- [x] 1.4 — Add re-exports in `run_comparison.py` for the moved public names so
      `compare_runs.py` and `tests/test_run_comparison.py` import paths stay valid.
- [x] 1.5 — Run `pytest tests/test_run_comparison.py` and full suite; `ruff check`.

**Files Modified:**
- `src/population_synth/analysis/run_comparison.py` — slimmed to builder/serializer.
- `src/population_synth/analysis/comparison_stats.py` — NEW (hypothesis tests).
- `src/population_synth/analysis/comparison_loader.py` — NEW (registry + I/O + extraction).

**Dependencies:** None

### Phase 2: Decompose `compute_metrics`
**Goal:** `compute_metrics` becomes an assembler; each metric family is a named,
independently testable helper.

**Started:** 2026-06-29
**Completed:** 2026-06-29

- [x] 2.1 — Extract one private helper per family, each taking `entries`
      (and `persona_ids`/`has_token_data`/`run_summary` as needed) and returning
      its sub-dict: `_summary(...)`, `_per_category(...)`, `_method_distribution(...)`,
      `_prompt_size_growth(...)`, `_response_verbosity(...)`,
      `_wall_clock_per_persona(...)`, `_value_diversity(...)`, and a
      `_token_metrics(...)` that returns the five token-gated sub-dicts together.
- [x] 2.2 — Reduce `compute_metrics` to: empty-guard, compute shared
      `persona_ids`/`has_token_data`, call helpers, assemble the 12-key dict.
- [x] 2.3 — Keep `_parse_iso`, `_classify_step`, `_resolved_value`, `_persona_id`
      as module helpers (used by the new family helpers).
- [x] 2.4 — Run `pytest tests/test_aggregator.py`; the golden snapshot MUST pass
      unchanged. Full suite + `ruff check`.

**Files Modified:**
- `src/population_synth/analysis/aggregator.py` — function decomposition only.

**Dependencies:** None (independent of Phase 1)

### Phase 3: Extract console reporter from `analyze_run.py`
**Goal:** Orchestration and presentation in separate files.

**Started:** 2026-06-29
**Completed:** 2026-06-29

- [x] 3.1 — Create `analysis/console_report.py`; move `_COL_SEP`, `_fmt_pct`,
      `_fmt_float`, and all nine `_print_*` functions, plus the `_print_metrics`
      dispatcher. Expose a public `print_metrics(metrics, run_dir, verbose)`.
- [x] 3.2 — Update `analyze_run.py` to import and call
      `console_report.print_metrics`; remove the moved code.
- [x] 3.3 — Confirm `analyze_run.py` retains only orchestration: config load,
      directory detection, per-persona/batch processing, JSON export, `--all`,
      `main`.
- [x] 3.4 — Manual run of `analyze_run.py <run_dir>` and `--verbose`; diff console
      output against `main`. `ruff check`.

**Files Modified:**
- `scripts/analyze_run.py` — presentation code removed, imports reporter.
- `src/population_synth/analysis/console_report.py` — NEW (console formatting).

**Dependencies:** None (independent of Phases 1–2)

---

## Testing Plan

### Unit Tests
- [ ] Existing `test_run_comparison.py` passes against the new module layout
      (imports resolved via re-export or updated paths).
- [ ] Existing `test_aggregator.py` golden snapshot passes **with no change to
      `tests/data/expected_metrics.json`** — the proof the decomposition is
      behavior-preserving.
- [ ] Existing `test_stats.py` and `test_joiner.py` pass unchanged.
- [ ] (Optional, low-cost) Add a direct unit test for one extracted aggregator
      helper (e.g. `_value_diversity`) now that it is callable in isolation.

### Integration Tests
- [ ] Full `pytest tests/` green after each phase.

### Manual Verification
- [ ] `python scripts/analyze_run.py <sample_run_dir>` — console output identical
      to `main`.
- [ ] `python scripts/analyze_run.py <sample_batch_dir> --verbose --output /tmp/a.json --charts /tmp/c`
      — JSON and PNG set identical to `main`.
- [ ] `python scripts/compare_runs.py --root <llm_metrics>` — comparison JSON and
      chart filenames identical to `main`.

### Edge Cases
- [ ] Empty entries (`compute_metrics([], None)`) still returns the zeroed
      12-key structure.
- [ ] Token-less run still omits the five token-gated metric groups.
- [ ] `compare_runs.py` with `--metrics` subset and `--country` filter behaves as
      before.

---

## Documentation Plan

- [ ] Update the `analysis/` sub-package description in CLAUDE.md to list the new
      modules (`comparison_stats.py`, `comparison_loader.py`, `console_report.py`)
      and their concerns.
- [ ] Module docstrings on each new file stating its single concern (matching the
      style of existing analysis modules).
- [ ] No README user-facing changes (commands and outputs are unchanged).

---

## Rollback Plan

Pure refactor on a feature branch; nothing is deployed or migrated.

1. Each phase is an independent commit — revert the offending commit(s) with
   `git revert` or reset the branch; the others stand alone.
2. No data, schema, or output changes, so there is nothing to migrate or reset.
3. If the golden snapshot ever diverges, that is the stop signal: the refactor
   changed behavior and the commit must be reworked, never the snapshot.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Import path break for `compare_runs.py` / tests after the move | Med | Med | Re-export moved names from `run_comparison.py` (Phase 1.4); run full suite before commit |
| Accidental behavior change in `compute_metrics` decomposition | Low | High | Golden snapshot test gates every commit; snapshot file must not be edited |
| Circular import between `comparison_loader` and `run_comparison` | Low | Med | Strict one-way deps: builder imports loader+stats; neither imports the builder |
| Scope creep into the deferred clarity/DRY items | Med | Low | Out-of-scope section is explicit; only fold in a dedup if a move already touches that exact code |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — split run_comparison | ~half day | None |
| Phase 2 — decompose compute_metrics | ~half day | None |
| Phase 3 — extract console reporter | ~2-3 hours | None |

Phases are independent and may be done/committed in any order.

---

## References

- Source analysis: separation-of-concerns review of `analysis/` (this conversation)
- Standard: `docs/data-pipeline-engineering/02-architecture-principles-and-patterns.md`
  (§2 separation/layering), `05-code-craftsmanship-and-maintainability.md`
  (§2 cohesion, §5 function size, §7 refactoring)
- Safety net: `tests/test_aggregator.py`, `tests/test_run_comparison.py`,
  `tests/test_stats.py`, `tests/test_joiner.py`

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- docs/development/plans/active/analysis-pipeline-separation-of-concerns.md
- scripts/analyze_run.py
- src/population_synth/analysis/aggregator.py
- src/population_synth/analysis/comparison_loader.py
- src/population_synth/analysis/comparison_stats.py
- src/population_synth/analysis/console_report.py
- src/population_synth/analysis/run_comparison.py
