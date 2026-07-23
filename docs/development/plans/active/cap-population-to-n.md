# Plan: Cap Population to N (pre-mapping subsample task)

**Date:** 2026-07-23
**Author:** Basil
**Status:** In Progress
**Base Branch:** `dev`
**Branch:** `feature/cap-population-to-n`

---

## Overview

Add a new analysis-pipeline task, `population_cap`, that runs **first** (before mapping) and, for each
combination (country × model × strategy), seeded-selects exactly **N** generated personas and copies them
into a canonical "capped" input population. Every downstream raw-persona consumer (mapping and
generation_metadata) is redirected to read this capped mirror instead of the full `01_Raw/{slug}`
directory, so no task can silently analyze more than N personas.

## Problem Statement

The analysis pipeline was written on the assumption that each combination contributes a single, fixed
number of personas (`N`). In practice, a combination's `01_Raw/{slug}/` directory can hold **more** than
N `persona_*/identity.json` files (extra/leftover generations, re-runs, retry slots). The per-persona cap
is currently applied *inconsistently and per-task*: `fidelity` and `multivariate_fidelity` accept
`--n-synthetic`/`--sample-seed` and may subsample, while `mapping` and `generation_metadata` glob **every**
`persona_*` directory with no cap. The result is that different tasks in the same run can operate on
different population sizes for the same combination, producing inconsistent and non-reproducible results.

Centralizing the cap as the pipeline's first stage makes N a single, enforced, inspectable invariant:
a physical capped population artifact per combo that every downstream stage consumes.

## Goals

### In Scope
1. New registered analysis process `population_cap` (registry entry + backing script), GUI-accessible as a
   task in the analysis workflow, running before mapping.
2. Per-combo seeded (without-replacement) selection of N persona directories, copied wholesale (identity +
   telemetry + logs) into `03_Analysis/population_cap/{slug}/`, mirroring the `01_Raw/{slug}` layout.
3. A shared read-only resolver that routes the two raw-persona consumers (`mapping`,
   `generation_metadata`) to the capped mirror, and **raises loudly (fail-fast) if the capped mirror is
   absent — there is NO fallback to `01_Raw`** (forbidden by user directive 2026-07-23). The capped mirror
   is a hard prerequisite; the DAG dependency guarantees it exists in normal operation.
4. DAG rewiring so `population_cap` is the sole root and both `mapping` and `generation_metadata` depend on it.
5. `--n` applied uniformly across all combos (task-level), `--sample-seed` for reproducibility, `--force`
   to overwrite an existing capped mirror.
6. Fewer-than-N combos: loud warning + pass through all available personas (do not fail the batch).

### Out of Scope
- Removing / changing `fidelity` and `multivariate_fidelity`'s existing `--n-synthetic`/`--sample-seed`
  flags. They become **redundant** once capping is enabled (mapped populations already hold exactly N),
  but are left intact this iteration. Documented as a recommended follow-up (blank them in the flow).
- Persona **validity / schema filtering** before counting to N. v1 counts raw `persona_*/identity.json`
  files as-is; N means "N raw persona directories", not "N valid personas".
- Per-model or per-manifest N. N is a single task-level argument applied to every selected combo.
- Symlink-based mirroring (rejected — see Alternatives; Windows symlink privilege friction).

## Success Criteria

- [ ] `population_cap` appears as a checkable task in the GUI analysis workflow and runs before `mapping`.
- [ ] Running `population_cap` for a combo with M > N persona dirs produces `03_Analysis/population_cap/{slug}/`
      containing exactly N `persona_*` dirs, deterministically reproducible for a fixed `--sample-seed`.
- [ ] After `population_cap` runs, `mapping` output (`03_Analysis/mapping/{slug}.json`) has `individuals`
      length == N (was previously M).
- [ ] After `population_cap` runs, `generation_metadata` per-persona aggregates are computed over exactly
      the N capped personas.
- [ ] With no capped mirror present, `mapping` and `generation_metadata` **raise loudly**
      (`FileNotFoundError` instructing the user to run `population_cap` first) — no `01_Raw` fallback.
- [ ] A combo with M < N emits a warning, copies all M, and does not raise.
- [ ] `--n` omitted → the task raises loudly (fail-fast; N is mandatory).
- [ ] `ruff check src/` clean; `pytest` green including new `population_cap` tests.

## Definitions

- **Combination (combo):** a `(country_id, strategy_id, model_id)` triple, identified by the slug
  `f"{country_id}_{strategy_id}_{model_id}"` (`manifest_loader.axis_slug`). One `01_Raw/{slug}/` directory.
- **N (cap):** the target number of persona directories to retain per combo, supplied via `--n`. Uniform
  across all combos in a run.
- **Capped mirror:** `03_Analysis/population_cap/{slug}/` — a copy of `01_Raw/{slug}/` in which only the N
  selected `persona_*` subdirectories are present; all combo-level ancillary files (`logs/`,
  `run_metadata.json`, `manifest_snapshot.yaml`) are copied verbatim.
- **Seeded selection:** indices chosen by a fixed, reproducible without-replacement draw over the
  lexicographically sorted `persona_*` directory list, keyed by `--sample-seed` (same RNG convention as
  `utils/sampling.subsample_population`).
- **Raw-persona consumer:** an analysis task that reads `persona_*` data directly from `01_Raw` rather than
  the mapped `{metadata, individuals}` files. There are exactly two: `mapping` and `generation_metadata`.

---

## Technical Design

### Approach

A dedicated per-combo task materializes the capped population as a **layout-identical mirror** of the raw
combo directory. Because the mirror reproduces the exact `persona_*/identity.json` + `logs/` +
`llm_interactions.*` structure of `01_Raw/{slug}/`, both existing raw consumers keep working with **no
change to their globbing logic** — only the *root path they start from* is redirected. That redirect is a
single shared read-only resolver: "return the capped mirror path; if it does not exist, **raise
`FileNotFoundError`**". There is **no fallback to `01_Raw`** (forbidden by user directive) — the capped
mirror is a hard prerequisite enforced upstream by the DAG dependency, so a missing mirror is a genuine
error condition, not a recoverable one.

Selection reuses the project's existing seeded without-replacement convention by factoring the index draw
out of `subsample_population` into a small shared `select_indices(total, n, seed)` helper, so the cap task
and the fidelity subsample stay algorithmically consistent.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **A. Materialized capped mirror (per-persona dir copy), consumers redirected** | Physical, inspectable artifact per combo; both consumers unchanged internally; explicit and reviewable; fail-fast friendly | Disk cost (copies telemetry); a second copy of persona data | **Chosen** |
| B. Cap inside shared loader (`load_synthetic_population`) at ingestion, no new task | Least machinery | Invisible cap; generation_metadata does not use that loader (separate seam); not GUI-surfaced; no artifact to inspect | Rejected |
| C. Single `{metadata, individuals}` capped JSON per combo (not a dir mirror) | Compact | Breaks generation_metadata (needs `logs/`+`llm_interactions.*`, not a flat individuals list); forces mapping loader rewrite | Rejected |
| D. Symlink selected persona dirs instead of copying | No disk duplication | Windows symlink privilege friction; fragile across moves; opaque | Rejected |
| E. First-N-by-index selection | Deterministic, trivial | Keep-set tied to generation order; less statistically defensible than seeded draw | Rejected (user chose seeded) |

### Architecture & Module Contracts

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `analysis/population_cap/cap.py` :: `cap_combo(raw_slug_dir, n, seed, dest_dir, *, force)` | Seeded-select N persona dirs from one raw combo dir and copy the combo dir (N personas + ancillary files) into `dest_dir` | `(Path, int, int, Path, force)` → summary dict `{slug, requested_n, available, selected, seed, selected_ids, truncated}` | persona attribute schema, mapping/canonical axes, country label maps, fidelity math |
| `analysis/population_cap/__init__.py` | Package entry re-exporting `cap_combo` and the per-combo summary type | — | GUI, CLI parsing |
| `scripts/analyze/cap_populations.py` | `per_combo` CLI entrypoint: resolve slug from `--model-id/--strategy-id/--country-id`, resolve output base, call `cap_combo`, write `_index.json` | CLI args → capped mirror dirs + `03_Analysis/population_cap/_index.json` | selection/copy internals; statistics |
| `analysis/utils/capped_source.py` :: `resolve_combo_source(slug, output_base)` / `resolve_stage_source(output_base)` | READ resolver: return capped-mirror path; **raise `FileNotFoundError` if absent (NO `01_Raw` fallback)** | `(slug/output_base)` → `Path` | how the cap selects or copies; `01_Raw` |
| `analysis/utils/sampling.py` :: `select_indices(total, n, seed)` (factored out) | Reproducible without-replacement index draw shared by cap + subsample | `(int, int, int)` → `list[int]` | file layout, populations |
| `config/analysis/analysis_registry.yaml` (`population_cap` entry) | Register id/label/description/folder/script/dispatch | — | orchestration edges (those live in the flow YAML) |
| `config/gui/flows/analysis_workflow.yaml` (task block + edges) | Enable task, options (`n`, `sample-seed`, `output-base`), `depends_on` edges | — | label/script/dispatch (registry-owned) |

**Registry entry (new, in `processes:`):**

```yaml
  population_cap:
    label: "Cap Population (N)"
    description: >
      Seeded cap of each combination's generated personas to N. Copies the selected persona
      directories (plus combo logs/metadata) into the canonical capped input consumed by mapping
      and generation-metadata, so no downstream task analyzes more than N personas.
    folder: population_cap
    script: scripts/analyze/cap_populations.py
    dispatch: per_combo
```

**Flow YAML — new task block + rewired edges (`config/gui/flows/analysis_workflow.yaml`):**

```yaml
  population_cap:
    enabled: true
    supports_force: true          # Force -> --force, overwrite existing capped mirror
    force: false
    options:
      n: '100'                    # --n (required; task raises if blank/missing)
      sample-seed: 0              # --sample-seed (int, reproducible draw)
      output-base:                # --output-base (blank = script default)
    depends_on: []                # <-- the new pipeline root

  mapping:
    ...
    depends_on: [population_cap]   # was []

  generation_metadata:
    ...
    depends_on: [population_cap]   # was []
```

> Option keys are dashed (`sample-seed`, not `sample_seed`) because `CombinationRunner` emits `f"--{key}"`
> verbatim with no underscore→dash normalization; the argparse flags must match exactly.

**Capped mirror layout (per combo):**

```
03_Analysis/population_cap/
  _index.json                                # [{slug, requested_n, available, selected, seed, truncated}, ...]
  {slug}/
    persona_00003/ identity.json  llm_interactions.jsonl  ...   # only the N selected personas
    persona_00017/ ...
    logs/            run_*.log                                   # combo-level, copied verbatim
    run_metadata.json                                            # copied verbatim
    manifest_snapshot.yaml                                       # copied verbatim
```

**Read-redirect seams (the only two consumers):**

- `scripts/analyze/map_populations.py` — replace `seed_root = manifest.parallel_output_dir` (lines ~195,
  300, 332) with `seed_root = resolve_combo_source(slug, output_base)`. Loader
  (`synthetic_mapper/loader.py`) is unchanged — it still globs `persona_*/identity.json` under the given root.
- `analysis/generation_metadata/__init__.py::summarize()` — replace `raw_root = base / _RAW_STAGE_DIR`
  (line ~249) with `raw_root = resolve_stage_source(base)`. Its `iterdir()` slug walk and
  `glob("persona_*")` are unchanged.

---

## Implementation Plan

### Phase 1: Core cap logic + shared helpers
**Goal:** Deterministic per-combo selection and copy, with the shared index helper and read resolver.

**Started:** 2026-07-23
**Completed:** 2026-07-23

- [x] 1.1 — Factor `select_indices(total, n, seed) -> list[int]` out of `subsample_population` in
      `utils/sampling.py`; have `subsample_population` call it. Preserve existing behavior/output.
- [x] 1.2 — Create `analysis/population_cap/` package with `cap.py::cap_combo(...)`: sort `persona_*` dirs,
      `select_indices`, copy selected dirs + ancillary files (`logs/`, `run_metadata.json`,
      `manifest_snapshot.yaml`) into `dest_dir`; warn + copy-all when `available < n`; honor `force`
      (overwrite by removing existing `dest_dir` first). Return summary dict.
- [x] 1.3 — Create `analysis/utils/capped_source.py` with `resolve_combo_source(slug, output_base)` and
      `resolve_stage_source(output_base)`. **Design change (user correction 2026-07-23):** NO `01_Raw`
      fallback — the capped mirror is a hard prerequisite. Both resolvers return
      `analysis_output_dir("population_cap", base)[/slug]` and RAISE `FileNotFoundError` (instructing the
      user to run `population_cap` first) when the mirror is absent. WARN-level fallback log removed.

**Files Modified:**
- `src/population_synthetic/analysis/utils/sampling.py` — extract `select_indices`.
- `src/population_synthetic/analysis/population_cap/__init__.py`, `.../cap.py` — new.
- `src/population_synthetic/analysis/utils/capped_source.py` — new.

**Dependencies:** None

### Phase 2: Registry + CLI entrypoint
**Goal:** `population_cap` is a first-class registered process runnable from the CLI.

**Started:** 2026-07-23
**Completed:** 2026-07-23

- [x] 2.1 — Add the `population_cap` entry to `config/analysis/analysis_registry.yaml` (`processes:`).
- [x] 2.2 — Create `scripts/analyze/cap_populations.py`: argparse (`--model-id`, `--strategy-id`,
      `--country-id`, `--n` [required, raise if missing], `--sample-seed` [default 0], `--output-base`,
      `--force`); resolve slug via `axis_slug`, raw dir via `output_base/01_Raw/{slug}`, dest via
      `analysis_output_dir("population_cap", output_base)/{slug}`; call `cap_combo`; append/update
      `_index.json`. Skip (no-op) when dest exists and `--force` not set.

**Files Modified:**
- `config/analysis/analysis_registry.yaml` — new process entry.
- `scripts/analyze/cap_populations.py` — new.

**Dependencies:** Phase 1

### Phase 3: Consumer redirect + DAG wiring
**Goal:** Mapping and generation_metadata consume the capped mirror; GUI runs it first.

**Started:** 2026-07-23
**Completed:** 2026-07-23

- [x] 3.1 — `map_populations.py`: route `seed_root` through `resolve_combo_source(slug, output_base)` at all
      three sites (~195/300/332). Ensure `slug`/`output_base` are available at each.
- [x] 3.2 — `generation_metadata/__init__.py::summarize()`: route `raw_root` through
      `resolve_stage_source(base)` (~249).
- [x] 3.3 — `config/gui/flows/analysis_workflow.yaml`: add the `population_cap` task block
      (`depends_on: []`); set `mapping.depends_on: [population_cap]` and
      `generation_metadata.depends_on: [population_cap]`.

**Files Modified:**
- `scripts/analyze/map_populations.py` — `seed_root` resolution.
- `src/population_synthetic/analysis/generation_metadata/__init__.py` — `raw_root` resolution.
- `config/gui/flows/analysis_workflow.yaml` — new block + two edge changes.

**Dependencies:** Phase 2

### Phase 4: Tests + docs
**Goal:** Behavior locked by tests; architecture docs updated.

**Started:** 2026-07-23
**Completed:** 2026-07-23

- [x] 4.1 — Unit + integration tests (see Testing Plan) under `tests/test_population_cap.py`.
- [x] 4.2 — Update `CLAUDE.md` analysis-layer paragraph + the analysis-registry id list; note
      `population_cap` as the new pipeline root and its `03_Analysis/population_cap/` folder.
- [x] 4.3 — Update `docs/architecture/commands.md` and the sub-packages / comparison-mapping wiki pages;
      add a changelog entry.

**Files Modified:**
- `tests/test_population_cap.py` — new.
- `tests/test_generation_metadata.py` — the two `summarize` integration tests now run cap → summarize.
- `tests/test_gm_comparison.py`, `tests/test_summarize_gm_cli.py` — capped-mirror fixture / empty
  capped stage (consumers no longer read `01_Raw`).
- `tests/test_workflow_state.py`, `tests/test_analysis_registry.py` — new DAG root + registry id.
- `CLAUDE.md`, `docs/architecture/commands.md`, `docs/architecture/sub-packages.md`,
  `docs/architecture/comparison-mapping.md`, `docs/changelogs/population-cap.md` — docs.

**Dependencies:** Phase 3

---

## Testing Plan

### Unit Tests
- [x] `select_indices(total, n, seed)` — reproducible for fixed seed; distinct indices; `n >= total`
      returns all indices; matches `subsample_population`'s prior selection on a shared fixture.
- [x] `cap_combo` over-generation — M=10 persona dirs, N=4 → dest has exactly 4, deterministic for fixed seed.
- [x] `cap_combo` under-generation — M=3, N=5 → warns, dest has 3, no raise, `truncated=False`/available<n flagged.
- [x] `cap_combo` copies ancillary files — `logs/`, `run_metadata.json`, `manifest_snapshot.yaml` present in dest.
- [x] `cap_combo` force — existing dest is fully replaced (stale extra personas removed) only when `force=True`.
- [x] `resolve_combo_source` / `resolve_stage_source` — return capped path when mirror exists; **raise
      `FileNotFoundError` when it does not** (assert no `01_Raw` fallback, no swallowed warning).

### Integration Tests
- [x] End-to-end on a synthetic `01_Raw` fixture: run cap (N=4) → the mapping loader reads the mirror →
      loaded `individuals` length == 4.
- [x] `generation_metadata.summarize()` over a capped fixture computes per-persona aggregates over 4, not M.
- [x] No-mirror fail-fast: with `population_cap` output absent, the mapping seam (`resolve_combo_source`)
      and `generation_metadata.summarize()` raise `FileNotFoundError` (they do NOT read `01_Raw`).

### Manual Verification
- [ ] GUI: `population_cap` shows as a task, is checkable, runs before `mapping`; the DAG shows it as root.
- [ ] Run the GUI workflow on one real combo; confirm `03_Analysis/population_cap/{slug}/` and downstream N.
- [ ] Omit `--n` on the CLI → task raises with a clear message.

### Edge Cases
- [x] Combo dir with 0 `persona_*` dirs → warn/handle without crashing downstream existence guards.
- [x] `--sample-seed 0` is honored (0 is a valid seed, not treated as "unset").
- [x] Slug-name decomposition in generation_metadata still succeeds for capped-mirror dir names (identical to raw).
- [ ] Combo-level `logs/run_*.log` reflect the *full* generation run, not N — documented limitation; per-persona
      aggregates are correct, any log-derived global counters are not re-scoped to N (accepted for v1).

---

## Documentation Plan

- [x] Update `CLAUDE.md`: add `population_cap` to the analysis-registry id list and describe it as the
      pre-mapping root; note the `03_Analysis/population_cap/` capped mirror and the shared read resolver.
- [x] Update `docs/architecture/commands.md` with the `cap_populations.py` invocation.
- [x] Update `docs/architecture/sub-packages.md` and `comparison-mapping.md` (mapping now reads the capped
      source, not `01_Raw` directly, when present).
- [x] Add `docs/changelogs/population-cap.md`.
- [x] Inline docstrings for `cap_combo`, `select_indices`, and the two resolvers (Phase 1).

---

## Rollback Plan

1. **Config-only disable is NOT sufficient.** Because there is no `01_Raw` fallback, once the consumer
   redirects (Phase 3) are in place, `mapping` and `generation_metadata` hard-require the capped mirror.
   Merely setting `population_cap.enabled: false` would make them raise. To disable, you must **revert the
   consumer edits** (restore `seed_root = manifest.parallel_output_dir` and `raw_root = base/"01_Raw"`)
   alongside disabling the task — i.e. a code revert, not config-only.
2. **Data:** delete `03_Analysis/population_cap/`. It is a derived copy of `01_Raw`; no source data is
   mutated or moved by this feature.
3. **Full revert (recommended rollback path):** revert the feature branch commits (registry entry, script,
   package, resolver, two consumer edits, flow YAML). This restores the direct `01_Raw` reads. No
   migrations; `01_Raw` is never modified.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Disk duplication of persona telemetry (large `llm_interactions.jsonl`) | Med | Med | Copy only selected N dirs; document; follow-up option to copy `identity.json`+`llm_interactions.*` only, skip nested logs |
| Redundant double-sampling via leftover `fidelity --n-synthetic` | Med | Low | Document; recommend blanking `n-synthetic` in flow once capping enabled (out-of-scope to remove) |
| Consumer redirect misses a `seed_root` site in mapping (3 occurrences) | Low | High | Route all three through the single resolver; integration test asserts mapped N |
| Capped-mirror dir under `03_Analysis` is semantically an *input*, not analysis output | Low | Low | Accepted trade-off for registry/GUI uniformity; documented in Definitions |
| `--sample-seed 0` mishandled as "unset" | Low | Med | Explicit test; resolver/CLI treat `None` (not `0`) as unset |
| Combo-level logs not re-scoped to N (generation_metadata global counters) | Med | Low | Documented limitation; per-persona aggregates (the primary metrics) are correct |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — core logic + helpers | ~0.5 day | None |
| Phase 2 — registry + CLI | ~0.5 day | Phase 1 |
| Phase 3 — redirect + DAG | ~0.5 day | Phase 2 |
| Phase 4 — tests + docs | ~0.5 day | Phase 3 |

---

## References

- Related Plans: `docs/development/plans/completed/` (real-population-reference-stats, generation-metadata)
- Registry: `config/analysis/analysis_registry.yaml`; accessor `analysis/utils/registry.py`
- Raw path source: `generators/synthetic/manifest_loader.py:220` (`parallel_output_dir`)
- Consumers: `scripts/analyze/map_populations.py`, `analysis/generation_metadata/__init__.py::summarize()`
- GUI translation: `gui/execution.py::CombinationRunner.run()`

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- CLAUDE.md
- config/analysis/analysis_registry.yaml
- config/gui/flows/analysis_workflow.yaml
- docs/architecture/commands.md
- docs/architecture/comparison-mapping.md
- docs/architecture/sub-packages.md
- docs/changelogs/population-cap.md
- docs/development/plans/active/cap-population-to-n.md
- scripts/analyze/cap_populations.py
- scripts/analyze/map_populations.py
- src/population_synthetic/analysis/generation_metadata/__init__.py
- src/population_synthetic/analysis/population_cap/__init__.py
- src/population_synthetic/analysis/population_cap/cap.py
- src/population_synthetic/analysis/utils/capped_source.py
- src/population_synthetic/analysis/utils/sampling.py
- tests/test_analysis_registry.py
- tests/test_generation_metadata.py
- tests/test_gm_comparison.py
- tests/test_population_cap.py
- tests/test_summarize_gm_cli.py
- tests/test_workflow_state.py

---
