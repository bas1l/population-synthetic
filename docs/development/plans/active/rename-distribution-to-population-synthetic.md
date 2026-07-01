# Plan: Rename distribution & import package to `population_synthetic`

**Date:** 2026-07-01
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/extract-mapping-task`
**Branch:** `feature/rename-distribution-population-synthetic`

---

## Overview

Rename the distribution from `population-synth` to `population-synthetic` and the import
package from `population_synth` to `population_synthetic`, so all three names align with the
git repository name (`population-synthetic`). The `src/` layout is **kept** unchanged — only
the package directory inside `src/` is renamed.

## Problem Statement

The project currently carries three subtly different names:

- Git repo / directory: `population-synthetic`
- Distribution (`pyproject.toml`): `population-synth`
- Import package: `population_synth`

Each name individually follows PEP 8 / PyPA conventions (hyphen for the distribution,
underscore for the import package). The inconsistency is that the distribution/import stem
(`synth`) is a *different word* from the repo (`synthetic`), which hurts discoverability and
makes the install/import relationship harder to reason about. Aligning them removes that
friction. This is a cosmetic/consistency change with no behavioural impact.

## Goals

### In Scope
1. Distribution renamed to `population-synthetic` in `pyproject.toml`.
2. Import package directory renamed `src/population_synth/` -> `src/population_synthetic/` (via `git mv`).
3. Every live `population_synth.*` import updated across `src/`, `scripts/`, and `tests/`.
4. Live documentation updated (`CLAUDE.md`, `README.md`, `scripts/README.md`, and docs that
   describe *current* commands).
5. Editable reinstall works and the full test suite + ruff pass under the new namespace.

### Out of Scope
- Removing or changing the `src/` layout (explicitly kept).
- Renaming the git repository or updating the git remote URL (separate, GitHub-side action).
- Rewriting historical plan records under `docs/development/plans/completed/` and `archived/`
  (point-in-time artifacts — left as-is intentionally).
- Regenerating architecture diagram artifacts (`docs/architecture/diagrams/**/*.svg`, `*.dot`);
  these are regenerated from source, not hand-edited, and can be refreshed separately if desired.
- Renaming the `popsynth` conda environment (unrelated to package naming).
- Any PyPI publishing action (project is not published; `version = 0.1.0`).

## Success Criteria

- [x] `grep -rn 'population_synth\b' src/ scripts/ tests/` returns **zero** matches (only `population_synthetic` remains).
- [x] `pyproject.toml` declares `name = "population-synthetic"`.
- [x] `pip install -e .` completes cleanly.
- [x] `python -c "import population_synthetic"` succeeds; `import population_synth` fails (ImportError).
- [x] `pytest` passes at the same pass/fail baseline as before the rename (125 passed).
- [x] `ruff check src/` passes at prior baseline (16 pre-existing errors, identical on base branch — **zero** new errors introduced by the rename).
- [x] `python -m population_synthetic.gui.main` resolves (import path valid).

---

## Technical Design

### Approach

A mechanical, repo-wide identifier rename executed as: (1) move the package directory with
`git mv` so history is preserved, (2) apply a word-boundary-guarded find/replace of the
`population_synth` token across live code and docs, (3) flip the distribution name in
`pyproject.toml`, then (4) reinstall and verify. The `[tool.setuptools.packages.find]
where = ["src"]` config auto-discovers the renamed directory, so no package list edits are
needed.

The rename token is `population_synth` (underscore/import form). The distribution form
`population-synth` (hyphen) exists only in `pyproject.toml` and is handled explicitly.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Rename distribution+import to `population_synthetic` (this plan) | All three names align; import matches repo | Longer import token to type; wide diff | **Chosen** |
| Rename the *git repo* to `population-synth` instead | Zero code changes | Diverges from the descriptive "synthetic" name; still repo!=import stem mismatch resolved only one way | Rejected |
| Leave as-is | No work | Three-name inconsistency persists | Rejected |
| Blanket `sed` across ALL files incl. historical docs | One command | Falsifies historical plan records; rewrites generated diagrams | Rejected |

### Architecture Changes

Only the package directory name changes; internal module structure is untouched.

```
src/
  population_synth/         ->  population_synthetic/
    __init__.py                  (contents unchanged except any self-reference)
    _paths.py                    (parents[2] depth unchanged — verify)
    population/ identity/ comparison/ analysis/ clients/ gui/ utils/
```

The sed word boundary (`population_synth\b`) is critical: without it, a second pass would turn
the already-correct `population_synthetic` into `population_syntheticetic`. Run the replacement
exactly once and verify with grep.

---

## Implementation Plan

### Phase 1: Distribution name + directory move
**Goal:** Establish the new package location and distribution name.

- [x] Task 1.1 — `git mv src/population_synth src/population_synthetic`
- [x] Task 1.2 — Edit `pyproject.toml`: `name = "population-synth"` -> `name = "population-synthetic"`
- [x] Task 1.3 — Verify `[tool.setuptools.packages.find] where = ["src"]` still resolves (no explicit package list to edit)

**Files Modified:**
- `pyproject.toml` — distribution name
- `src/population_synth/` -> `src/population_synthetic/` — directory move

**Dependencies:** None

### Phase 2: Code imports (src / scripts / tests)
**Goal:** Update every live Python import and `-m` module string to the new namespace.

- [x] Task 2.1 — Word-boundary replace `population_synth` -> `population_synthetic` across `src/**/*.py`
- [x] Task 2.2 — Same replace across `scripts/**/*.py` (includes `python -m population_synth...` strings and `launch_gui.py`)
- [x] Task 2.3 — Same replace across `tests/**/*.py` and `tests/_mapping_fixtures.py`
- [x] Task 2.4 — Verify `src/population_synthetic/_paths.py` `parents[2]` still points at repo root (depth unchanged by rename)

**Files Modified:**
- `src/population_synthetic/**/*.py` — ~40 files, import statements
- `scripts/**/*.py` — ~15 files, imports + module-path strings
- `tests/**/*.py` — ~18 files, imports

**Dependencies:** Phase 1

### Phase 3: Live documentation
**Goal:** Update docs that describe the current install/import/commands.

- [x] Task 3.1 — Update `CLAUDE.md` (Import Convention section + all `population_synth.*` examples + `python -m` command)
- [x] Task 3.2 — Update `README.md` and `scripts/README.md`
- [x] Task 3.3 — Update live/how-to docs that reference current commands (`docs/mapping_gap_investigation_playbook.md`, active/pending plan docs) — **do not** touch `completed/`, `archived/`, `debug/` historical records
- [x] Task 3.4 — Leave generated diagram files (`docs/architecture/diagrams/**/*.svg`, `*.dot`) for separate regeneration

**Files Modified:**
- `CLAUDE.md`, `README.md`, `scripts/README.md` — namespace references
- `docs/mapping_gap_investigation_playbook.md` and other live docs — command references

**Dependencies:** Phase 1

### Phase 4: Reinstall & verify
**Goal:** Confirm the rename is complete and the package works under the new name.

- [x] Task 4.1 — `pip install -e .` (re-register the editable install under the new dist name)
- [x] Task 4.2 — `grep -rn 'population_synth\b' src/ scripts/ tests/` returns zero matches
- [x] Task 4.3 — `python -c "import population_synthetic"` succeeds
- [x] Task 4.4 — `pytest` at prior baseline; `ruff check src/` passes

**Files Modified:** None (verification only)

**Dependencies:** Phases 1-3

---

## Testing Plan

### Unit Tests
- [x] Full `pytest` suite passes at the same baseline as before the rename (no new failures)
- [x] Import-sensitive tests (`test_mapper_delegation`, `test_reference_mapper_base`, `test_synthetic_mapper_base`) resolve the new namespace

### Integration Tests
- [x] A representative script imports cleanly, e.g. `python scripts/analyze/map_populations.py --help`
- [x] `python -m population_synthetic.gui.main` import path resolves (GUI optional dep permitting)

### Manual Verification
- [x] `pip install -e .` clean
- [x] `python -c "import population_synthetic; print(population_synthetic.__file__)"` points into `src/population_synthetic/`
- [x] `python -c "import population_synth"` raises `ModuleNotFoundError`

### Edge Cases
- [x] Confirm no `population_syntheticetic` double-substitution anywhere (word-boundary check)
- [x] Confirm `pyproject.toml` is the only place the hyphenated `population-synth` form was changed

---

## Documentation Plan

- [x] Update `README.md` with the new install/import name
- [x] Update `CLAUDE.md` Import Convention + all `population_synth.*` occurrences
- [x] Update `scripts/README.md`
- [x] No changelog file convention exists in this repo; the completed plan record serves as the change note

---

## Rollback Plan

The change is a pure rename on a dedicated feature branch — rollback is trivial.

1. **Before merge:** discard the branch — `git checkout feature/extract-mapping-task && git branch -D feature/rename-distribution-population-synthetic`, then `pip install -e .` to restore the old editable registration.
2. **Data considerations:** none — no migrations, no runtime data, no state.
3. **Rollback procedure:** revert the rename commit(s); re-run `pip install -e .`.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| sed double-substitution (`population_syntheticetic`) | Med | Med | Use `population_synth\b` word boundary; run once; grep-verify afterward |
| Stale editable install still points at old dir | Med | Med | Re-run `pip install -e .` in Phase 4; verify `__file__` path |
| Missed reference in an out-of-tree consumer (e.g. `anxiety-synthetic` parent repo) | Low | Low | Out of scope here; parent repo has its own copy of modules (see memory) |
| Windows/git case or path issues on `git mv` | Low | Low | Single directory move, distinct names — no case-only rename involved |
| Accidentally rewriting historical plan records | Low | Low | Scope sed to `src/ scripts/ tests/` + explicit live docs; exclude `completed/`/`archived/`/`debug/` |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 | ~10 min | None |
| Phase 2 | ~20 min | Phase 1 |
| Phase 3 | ~15 min | Phase 1 |
| Phase 4 | ~15 min | Phases 1-3 |

---

## References

- Related Plans: `docs/development/plans/completed/extract-population-synth-repo.md` (original extraction that established the current names)
- Convention basis: PEP 8 (import package = short, lowercase, underscores) + PyPA packaging guide (distribution = hyphen); PEP 503 normalizes `-`/`_`/`.` as equivalent on index

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
<!-- Whole-package rename: src/population_synth/ -> src/population_synthetic/ (git mv, history preserved). Stage with `git add -A` on this branch; the old dir is fully removed. -->
- CLAUDE.md
- docs/architecture/axis-composition.md
- docs/architecture/commands.md
- docs/architecture/diagrams/database/README.md
- docs/architecture/diagrams/README.md
- docs/architecture/diagrams/synthetic_strategies/README.md
- docs/architecture/README.md
- docs/architecture/sub-packages.md
- docs/architecture_review_analysis_pipeline_2026-06-29.md
- docs/development/debugging-identity-generation.md
- docs/development/plans/active/consolidate-analysis-packages.md
- docs/development/plans/active/extract-mapping-into-standalone-task.md
- docs/development/plans/active/rename-distribution-to-population-synthetic.md
- docs/development/plans/active/unified-symmetric-mapping-config.md
- docs/development/plans/pending/fix-identity-comparison-divergences.md
- docs/development/plans/pending/report-unmapped.md
- docs/development/reference-mapper-agnostic-summary.md
- docs/mapping_gap_investigation_playbook.md
- docs/swedish_mapping_fix_2026-05-29.md
- docs/swedish_model_state_and_mapping_2026-06-29.md
- pyproject.toml
- README.md
- scripts/analyze/analyze_run.py
- scripts/analyze/compare_all_pipelines.py
- scripts/analyze/compare_countries.py
- scripts/analyze/compare_pipeline_to_istat.py
- scripts/analyze/compare_pipeline_to_scb.py
- scripts/analyze/compare_populations.py
- scripts/analyze/compare_runs.py
- scripts/analyze/map_populations.py
- scripts/dev/draw_generation_dags.py
- scripts/generate/extract_population_from_pipeline.py
- scripts/generate/generate_identities_parallel.py
- scripts/generate/generate_identity.py
- scripts/generate/generate_istat_population.py
- scripts/generate/generate_scb_population.py
- scripts/generate/generate_ssb_population.py
- scripts/launch_gui.py
- scripts/README.md
- src/population_synthetic/__init__.py
- src/population_synthetic/_paths.py
- src/population_synthetic/analysis/__init__.py
- src/population_synthetic/analysis/comparison/__init__.py
- src/population_synthetic/analysis/comparison/charts.py
- src/population_synthetic/analysis/comparison/evaluator.py
- src/population_synthetic/analysis/comparison/scheme.py
- src/population_synthetic/analysis/llm_metrics/__init__.py
- src/population_synthetic/analysis/llm_metrics/cross_run/__init__.py
- src/population_synthetic/analysis/llm_metrics/cross_run/comparison_charts.py
- src/population_synthetic/analysis/llm_metrics/cross_run/comparison_loader.py
- src/population_synthetic/analysis/llm_metrics/cross_run/comparison_stats.py
- src/population_synthetic/analysis/llm_metrics/cross_run/run_comparison.py
- src/population_synthetic/analysis/llm_metrics/per_run/__init__.py
- src/population_synthetic/analysis/llm_metrics/per_run/aggregator.py
- src/population_synthetic/analysis/llm_metrics/per_run/charts.py
- src/population_synthetic/analysis/llm_metrics/per_run/console_report.py
- src/population_synthetic/analysis/llm_metrics/per_run/interaction_parser.py
- src/population_synthetic/analysis/llm_metrics/per_run/joiner.py
- src/population_synthetic/analysis/llm_metrics/per_run/log_parser.py
- src/population_synthetic/analysis/llm_metrics/shared/__init__.py
- src/population_synthetic/analysis/llm_metrics/shared/_stats.py
- src/population_synthetic/analysis/mapping/__init__.py
- src/population_synthetic/analysis/mapping/extractor.py
- src/population_synthetic/analysis/mapping/flatten_raw.py
- src/population_synthetic/analysis/mapping/mapping_engine.py
- src/population_synthetic/analysis/mapping/normalizer.py
- src/population_synthetic/analysis/mapping/reference_mapper/__init__.py
- src/population_synthetic/analysis/mapping/reference_mapper/base.py
- src/population_synthetic/analysis/mapping/reference_mapper/factory.py
- src/population_synthetic/analysis/mapping/reference_mapper/italy.py
- src/population_synthetic/analysis/mapping/reference_mapper/loader.py
- src/population_synthetic/analysis/mapping/reference_mapper/mappings.py
- src/population_synthetic/analysis/mapping/reference_mapper/raw_format.py
- src/population_synthetic/analysis/mapping/reference_mapper/sweden.py
- src/population_synthetic/analysis/mapping/synthetic_mapper/__init__.py
- src/population_synthetic/analysis/mapping/synthetic_mapper/_text_helpers.py
- src/population_synthetic/analysis/mapping/synthetic_mapper/base.py
- src/population_synthetic/analysis/mapping/synthetic_mapper/factory.py
- src/population_synthetic/analysis/mapping/synthetic_mapper/italy.py
- src/population_synthetic/analysis/mapping/synthetic_mapper/loader.py
- src/population_synthetic/analysis/mapping/synthetic_mapper/sweden.py
- src/population_synthetic/analysis/utils/__init__.py
- src/population_synthetic/analysis/utils/country_config.py
- src/population_synthetic/clients/__init__.py
- src/population_synthetic/clients/call_context.py
- src/population_synthetic/clients/claude_code_client.py
- src/population_synthetic/clients/eurostat_client.py
- src/population_synthetic/clients/gemini_client.py
- src/population_synthetic/clients/istat_client.py
- src/population_synthetic/clients/llm_protocol.py
- src/population_synthetic/clients/ollama_client.py
- src/population_synthetic/clients/openai_compat_client.py
- src/population_synthetic/clients/pxweb_client.py
- src/population_synthetic/clients/scb_client.py
- src/population_synthetic/clients/ssb_client.py
- src/population_synthetic/gui/__init__.py
- src/population_synthetic/gui/launcher_config.py
- src/population_synthetic/gui/main.py
- src/population_synthetic/gui/main_window.py
- src/population_synthetic/gui/manifest_model.py
- src/population_synthetic/gui/widgets/__init__.py
- src/population_synthetic/gui/widgets/action_selector.py
- src/population_synthetic/gui/widgets/checkable_axis_list.py
- src/population_synthetic/gui/widgets/configuration_panel.py
- src/population_synthetic/gui/widgets/console_widget.py
- src/population_synthetic/gui/widgets/dag_graph_items.py
- src/population_synthetic/gui/widgets/dag_graph_widget.py
- src/population_synthetic/gui/widgets/manifest_overview.py
- src/population_synthetic/gui/widgets/manifest_selector.py
- src/population_synthetic/gui/widgets/parameter_panel.py
- src/population_synthetic/gui/widgets/task_selector.py
- src/population_synthetic/identity/__init__.py
- src/population_synthetic/identity/base_identity_generator.py
- src/population_synthetic/identity/factory_identity_generator.py
- src/population_synthetic/identity/identity_generator_configurable.py
- src/population_synthetic/identity/llm_interaction_log.py
- src/population_synthetic/identity/manifest_loader.py
- src/population_synthetic/population/__init__.py
- src/population_synthetic/population/data.py
- src/population_synthetic/population/helpers.py
- src/population_synthetic/population/income_class.py
- src/population_synthetic/population/italy/__init__.py
- src/population_synthetic/population/italy/constants.py
- src/population_synthetic/population/italy/fetch_service.py
- src/population_synthetic/population/italy/parsers.py
- src/population_synthetic/population/italy/sample_service.py
- src/population_synthetic/population/norway/__init__.py
- src/population_synthetic/population/norway/constants.py
- src/population_synthetic/population/norway/fetch_service.py
- src/population_synthetic/population/norway/parsers.py
- src/population_synthetic/population/norway/sample_service.py
- src/population_synthetic/population/sweden/__init__.py
- src/population_synthetic/population/sweden/constants.py
- src/population_synthetic/population/sweden/fetch_service.py
- src/population_synthetic/population/sweden/parsers.py
- src/population_synthetic/population/sweden/sample_service.py
- src/population_synthetic/utils/__init__.py
- src/population_synthetic/utils/pipeline.py
- tests/_mapping_fixtures.py
- tests/test_aggregator.py
- tests/test_call_context.py
- tests/test_evaluator.py
- tests/test_extractor_characterization.py
- tests/test_income_class.py
- tests/test_joiner.py
- tests/test_log_parser.py
- tests/test_mapper_delegation.py
- tests/test_mapping_engine.py
- tests/test_norway_sampler.py
- tests/test_reference_mapper_base.py
- tests/test_run_comparison.py
- tests/test_scheme_index.py
- tests/test_stats.py
- tests/test_synthetic_mapper_base.py
- tests/test_synthetic_reference_vocab_subset.py
