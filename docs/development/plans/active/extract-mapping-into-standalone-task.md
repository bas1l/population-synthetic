# Plan: Extract mapping into a standalone pipeline task

**Date:** 2026-07-01
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/unified-symmetric-mapping-config`
**Branch:** `feature/extract-mapping-task`

---

## Overview

Promote category **mapping** from an inline preprocessing step embedded in every comparison
script into its own workflow task that reads input files and writes mapped output files (mapped
database + mapped synthetic). The comparison stage then becomes a pure consumer of those files.
The set of synthetic populations to map is declared by an explicit targets list rather than
inferred from a disk scan.

## Problem Statement

Today mapping is not a stage of its own — it runs inline inside each comparison script as a
load→map step immediately before `StatisticalEvaluator` is constructed:

- **Synthetic side:** `load_raw_population(seed_root)` → `map_population(raw, country)`
- **Reference side:** `load_reference_population(path)` → `normalize_population(raw, country)`

This wiring is duplicated across `compare_pipeline_to_scb.py`, `compare_pipeline_to_istat.py`, and
`compare_all_pipelines.py`. Consequences:

- **No reusable mapped artifacts** — every comparison re-maps the reference (10k records) and the
  synthetic population from scratch; mapping cannot be inspected, cached, or consumed independently.
- **Completeness is implicit** — `compare_all_pipelines.py` enumerates the full
  model×strategy×country axis product and silently skips combos whose `01_Raw/{slug}` dir is
  missing or empty. There is no declared list of "which synthetic populations are complete."
- **Coupling** — the comparison logic is entangled with country-specific reference/mappings
  lookup tables (`_COUNTRY_REFERENCES`, `_COUNTRY_MAPPINGS`) hard-coded at the top of the batch
  script.

`StatisticalEvaluator` already consumes *pre-mapped* populations (it reads `pop["individuals"]`
directly and only derives `age_group` from raw `age`), so the mapping is cleanly separable.

## Goals

### In Scope
1. A standalone **map task** (`scripts/analyze/map_populations.py`) that writes mapped database +
   synthetic population files under `03_Analysis/mapped/`.
2. An explicit **targets list** (`config/analysis/comparison_targets.yaml`) naming the per-run
   manifests we consider complete; the map task processes only these.
3. Refactor the three comparison scripts to **consume pre-mapped files** and write artifacts to
   `03_Analysis/comparison/`.
4. A shared **country-config helper** (`comparison/country_config.py`) holding the
   reference/mappings lookups and country inference.

### Out of Scope
- Changing any mapping *logic* — `synthetic_mapper`, `reference_mapper`, `mapping_engine`,
  `scheme.py`, `evaluator.py`, and `charts.py` are reused unchanged.
- Changing the axis-composition generation flow (`generate_identities_parallel.py`).
- Migrating the legacy `seed_NNN_*` manifest slug scheme to the axis `{country}_{strategy}_{model}`
  scheme.
- GUI launcher integration for the new map task (future work).

## Success Criteria

- [ ] `map_populations.py` reads `comparison_targets.yaml` and produces
  `03_Analysis/mapped/database_{country}.json`, `mapped/{slug}.json`, and `mapped/_index.json`.
- [ ] The three comparison scripts perform **no** mapping — they `json.load` pre-mapped files.
- [ ] Comparison artifacts (JSON report, CSV, 15 bar charts, radar) land under
  `03_Analysis/comparison/{slug}/`; summary + radar grid under `03_Analysis/comparison/`.
- [ ] A single-run comparison for a slug yields identical marginals to the batch run
  (behaviour-preserving extraction).
- [ ] `ruff check src/ scripts/` clean; existing `pytest` suite passes unchanged.

---

## Technical Design

### Approach

Split the comparison pipeline into two decoupled stages under `{output_base}/03_Analysis/`
(`output_base` from `config/synthetic/experiment_defaults.yaml`):

```
03_Analysis/
  mapped/                          # NEW — output of the map stage
    database_swedish.json          # mapped reference, one per country (deduped)
    database_italian.json
    {slug}.json                    # mapped synthetic, one per target
    _index.json                    # [{slug, country, synthetic_file, database_file, n, skipped}]
  comparison/                      # comparison artifacts MOVED here (were 03_Analysis/{slug})
    {slug}/                        # per-target JSON + CSV + bar/radar charts
    comparison_summary.json
    {country}_radar_grid.png
```

`{slug}` = `seed_root.name` (the `parallel.output_dir` basename of the target manifest, e.g.
`seed_022_all_pick_sonnet`), consistent with the single-run scripts today.

**Map stage** reads the targets YAML → loads each manifest via `load_manifest` → infers country
from the simulation-config filename → maps the synthetic side (`load_raw_population` →
`map_population`) and the reference side once per country (`load_reference_population` →
`normalize_population`) → writes the mapped files + an index.

**Compare stage** iterates `mapped/_index.json`, `json.load`s the mapped synthetic + shared mapped
database, loads the scheme, and runs the existing evaluator/chart path — no mapping.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Standalone map task + targets YAML + pre-mapped consumption | Declared completeness; reusable/inspectable mapped artifacts; decouples mapping from scoring | New stage + directory restructure | **Chosen** |
| Keep inline mapping, add caching layer | Smaller diff | Completeness still implicit; mapping stays entangled with comparison | Rejected |
| Targets = filter/exclude list over axis product | Reuses existing discovery | User wants an explicit *inclusion* list of complete runs; still couples to axis scheme | Rejected |

### Country inference

Manifests carry no explicit `country`; it is implicit in `parameters.config`
(`simulation_config_004_swedish_*` → swedish, `..._005_italian_*` → italian). `infer_country`
matches the `swedish`/`italian` token in the config stem and fails loudly on ambiguity (fail-fast
convention). The targets YAML also accepts a per-entry `{manifest: <path>, country: <id>}` mapping
form to override inference.

### Architecture Changes

New:
- `config/analysis/comparison_targets.yaml` — completeness list (manifest paths).
- `scripts/analyze/map_populations.py` — the map stage.
- `src/population_synth/comparison/country_config.py` — `REFERENCE_FOR_COUNTRY`,
  `MAPPINGS_FOR_COUNTRY`, `infer_country(config_path)`.

Modified:
- `scripts/analyze/compare_all_pipelines.py` — consume mapped index; write to `comparison/`.
- `scripts/analyze/compare_pipeline_to_scb.py` — load pre-mapped files; write to `comparison/{slug}/`.
- `scripts/analyze/compare_pipeline_to_istat.py` — same.
- `src/population_synth/identity/manifest_loader.py` — `compose_manifest` `comparison_output_dir`
  from `03_Analysis/{slug}` → `03_Analysis/comparison/{slug}` (line ~209).

Reused unchanged: `comparison/synthetic_mapper` (`load_raw_population`, `map_population`),
`comparison/reference_mapper` (`load_reference_population`, `normalize_population`),
`comparison/scheme.load_scheme`, `comparison/evaluator.StatisticalEvaluator` + `write_csv_summary`,
`comparison/charts.*`, `identity/manifest_loader.load_manifest`.

---

## Implementation Plan

### Phase 1: Shared country-config helper
**Goal:** Centralize country→reference / country→mappings lookups and country inference so both
the map stage and any consumer share one source.

- [x] Create `comparison/country_config.py` with `REFERENCE_FOR_COUNTRY`, `MAPPINGS_FOR_COUNTRY`
      (lifted from `compare_all_pipelines.py` lines 39-47) and `infer_country(config_path) -> str`.
- [x] Fail loudly for unknown/ambiguous country.

**Files Modified:**
- `src/population_synth/comparison/country_config.py` — new module.

**Dependencies:** None

### Phase 2: Map task + targets config
**Goal:** Produce mapped database + synthetic files driven by an explicit targets list.

- [x] Create `config/analysis/comparison_targets.yaml` (`targets:` list of manifest paths;
      support plain-string and `{manifest, country}` mapping forms).
- [x] Create `scripts/analyze/map_populations.py`: read targets → per manifest `load_manifest`,
      infer country, map synthetic (`load_raw_population` → `map_population`) to `mapped/{slug}.json`,
      map database once per country to `mapped/database_{country}.json`, write `mapped/_index.json`.
- [x] Reuse the batch script's seed-root guards (missing dir / no `persona_*/identity.json` →
      warn & skip).

**Files Modified:**
- `config/analysis/comparison_targets.yaml` — new.
- `scripts/analyze/map_populations.py` — new.

**Dependencies:** Phase 1

### Phase 3: Comparison consumers + layout move
**Goal:** Comparison scripts consume pre-mapped files and write to `03_Analysis/comparison/`.

- [x] `compare_all_pipelines.py`: drop mapping imports/inline mapping; iterate `mapped/_index.json`
      (fallback: re-read targets YAML); `json.load` synthetic + shared database; `load_scheme`;
      existing evaluator/chart path; write to `comparison/{slug}/`, summary + radar grid to
      `comparison/`.
- [x] `compare_pipeline_to_scb.py` / `compare_pipeline_to_istat.py`: replace inline load/map
      helpers with `json.load` of pre-mapped files resolved from `--mapped-dir` + `{slug}` (or
      explicit `--mapped-synthetic` / `--mapped-database`); clear error if absent ("run
      map_populations.py first"); write under `comparison/{slug}/`.
- [x] `manifest_loader.compose_manifest`: `comparison_output_dir` → `03_Analysis/comparison/{slug}`.

**Files Modified:**
- `scripts/analyze/compare_all_pipelines.py`
- `scripts/analyze/compare_pipeline_to_scb.py`
- `scripts/analyze/compare_pipeline_to_istat.py`
- `src/population_synth/identity/manifest_loader.py`

**Dependencies:** Phase 2

### Phase 4: Docs
**Goal:** Reflect the two-stage flow in project docs.

- [x] Update `CLAUDE.md` Commands section + the `comparison/` architecture bullet.

**Files Modified:**
- `CLAUDE.md`

**Dependencies:** Phase 3

---

## Testing Plan

### Unit Tests
- [ ] `infer_country` returns `swedish`/`italian` for the real config stems and raises on an
      unknown/ambiguous stem.
- [ ] Targets loader parses both the plain-string and `{manifest, country}` mapping forms.

### Integration Tests
- [ ] `map_populations.py` on a 1–2 target list produces `database_{country}.json`,
      `{slug}.json`, and a well-formed `_index.json`.
- [ ] `compare_all_pipelines.py` reads the mapped files (asserted: no mapper invoked) and emits
      the full artifact set under `comparison/{slug}/`.

### Manual Verification
- [ ] Populate `comparison_targets.yaml` with `identity_manifest_022_claude_sonnet.yaml`; run the
      map task; confirm mapped files + sane `n`/`skipped` metadata.
- [ ] Run the batch comparison; confirm `comparison/{slug}/` has JSON + CSV + 15 bar charts +
      radar, plus `comparison/comparison_summary.json`.
- [ ] Run a single-run script for the same slug; confirm marginals match the batch run.

### Edge Cases
- [ ] Target whose seed root is missing / empty → warned and skipped, not a crash.
- [ ] Comparison run before the map task → clear "run map_populations.py first" error.
- [ ] Existing `pytest` suite (evaluator/mapper) passes unchanged.

---

## Documentation Plan

- [x] Update `CLAUDE.md` Commands section (add `map_populations.py`; note comparison consumes
      mapped files) and the `comparison/` architecture bullet (two-stage flow, new dirs).
- [x] Inline module docstrings for `map_populations.py` and `country_config.py` (present -- added
      by the Phase 1/2 agents; verified during Phase 4, not rewritten).

---

## Rollback Plan

1. The change is additive plus a call-site move; revert by restoring the three comparison scripts'
   inline load/map, the `manifest_loader` `comparison_output_dir` line, and deleting the new files
   (`map_populations.py`, `country_config.py`, `comparison_targets.yaml`).
2. **Data considerations:** No data migration. Output lives under `output_base/03_Analysis/`;
   old-layout artifacts (`03_Analysis/{slug}`) are untouched by the rollback and can be removed
   manually.
3. **Rollback procedure:** revert the feature branch merge commit; no state reset required.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Country inference wrong for a non-standard config filename | Low | Med | Fail loudly; support `{manifest, country}` override in targets YAML |
| Legacy manifests' hard-coded `comparison_output_dir` conflicts with new `comparison/` layout | Med | Low | New stages derive dirs from `output_base` + `mapped/`/`comparison/`, not from `manifest.comparison_output_dir` |
| Behaviour drift between old inline mapping and extracted stage | Low | High | Mapping functions reused verbatim; verify identical marginals batch vs single-run |
| Stale mapped files consumed after a synthetic run is regenerated | Med | Med | `_index.json` records seed_root; document "re-run map task after regenerating a population" |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 | Small | None |
| Phase 2 | Medium | Phase 1 |
| Phase 3 | Medium | Phase 2 |
| Phase 4 | Small | Phase 3 |

---

## References

- Working plan: `.claude/plans/analyse-the-comparison-pipeline-cryptic-robin.md`
- Related: unified symmetric mapping config (`comparison/mapping_engine.py`, `config/mapping/{scb,istat}/`)

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- CLAUDE.md
- config/analysis/comparison_targets.yaml
- config/synthetic/axes/countries/italian.yaml
- config/synthetic/axes/countries/swedish.yaml
- docs/development/plans/active/extract-mapping-into-standalone-task.md
- scripts/analyze/compare_all_pipelines.py
- scripts/analyze/compare_pipeline_to_istat.py
- scripts/analyze/compare_pipeline_to_scb.py
- scripts/analyze/map_populations.py
- src/population_synth/comparison/country_config.py
- src/population_synth/identity/manifest_loader.py
