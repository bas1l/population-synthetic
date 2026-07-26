# Plan — Atomistic persona-validation gate + map/cap reorder

**Status:** completed (implemented on `feature/persona-realism-judge`, 2026-07-24; full suite green — 705 passed)
**Date:** 2026-07-24
**Motivation source:** [persona-data-quality-observations.md](../../persona-data-quality-observations.md)
**Branch:** to be cut from the integration line (not `main`), e.g. `feature/persona-validation-gate`.

---

## 1. Why

The observations doc records two data-quality facts that currently corrupt every
downstream count:

- **Obs 1** — some `persona_*` dirs lack `identity.json`; downstream keys off it, so the
  capped `n` silently falls below the requested `N` (e.g. `n=48` for a 100-dir cap).
- **Obs 2** — some field values are wrong for their field (e.g. `Stockholm` as a
  country), which the mapper leaves as the `__UNMAPPED__` sentinel (commit `5bfdcc3`).

Root cause of the shortfall: **`population_cap` currently runs first and selects `N`
personas blindly**, before anyone knows which are valid. The bad ones are drawn into the
cap, then silently dropped later. The fix is to **validate first, then cap from the clean
pool**, so cap draws `N` personas that are guaranteed to be complete and fully mapped.

## 2. Target DAG

**Current** (root = `population_cap`):

```
population_cap → mapping → {fidelity, multivariate, consistency, pairwise, real_stats, persona_realism}
population_cap → generation_metadata
fidelity → {model_ranking, method_significance}
```

**New** (root = `validate_raw`):

```
validate_raw            (NEW)  reads 01_Raw persona dirs → CSV per combo
  → mapping                    reads 01_Raw (full valid pool) → mapped {slug}.json
    → validate_mapped   (NEW)  reads mapped {slug}.json → CSV per combo
      → population_cap         reads both CSVs → selects N passing BOTH →
      │                        writes capped raw persona-dir mirror + capped mapped file
      ├── fidelity → {model_ranking, method_significance}
      ├── multivariate_fidelity
      ├── consistency
      ├── pairwise_comparison
      ├── real_population_stats
      ├── persona_realism
      └── generation_metadata
```

Both new tasks are **atomistic**: each does exactly one check and emits one artifact
type. All filtering/selection lives in `population_cap`, which is the only task that reads
the validity CSVs.

## 3. New task specs

Each new task is a per-analysis subpackage under `src/population_synthetic/analysis/`
(per the one-subpackage-per-process convention) plus a `scripts/analyze/` entrypoint, a
registry entry, and a GUI-flow node. `dispatch: per_combo`.

### 3.1 `validate_raw` (new root)

- **Reads:** `01_Raw/{slug}/persona_*/` dirs.
- **Check (per persona dir):**
  1. `identity.json` exists.
  2. Every expected category/attribute is present with a non-empty value (any value —
     correctness is *not* judged here, only presence). The expected attribute list comes
     from **config** (axis YAML / `ComparisonScheme.attributes`) — no hardcoded list.
- **Writes:** `03_Analysis/validate_raw/{slug}.csv` — one row per `persona_*` dir:
  `persona_id, passed (bool), has_identity_json, missing_categories (list/…)`.
- **Non-destructive:** never mutates `01_Raw`.

### 3.2 `validate_mapped`

- **Reads:** `03_Analysis/mapping/{slug}.json` (the full mapped population).
- **Check (per mapped persona record):** no field holds the `__UNMAPPED__` sentinel.
- **Writes:** `03_Analysis/validate_mapped/{slug}.csv` — one row per persona record:
  `persona_id, passed (bool), unmapped_fields (list/…)`.
- **Non-destructive:** never mutates the mapping output.

> Both CSVs key on a stable `persona_id` that links the raw `persona_*` dir to its mapped
> record. **Verify during implementation** that mapping carries the source persona
> folder id into each mapped record (needed so cap can intersect the two CSVs). If it
> does not, add it in mapping.

## 4. Changes to existing components

### 4.1 `mapping` — read `01_Raw`, not the capped mirror

- `scripts/analyze/map_populations.py`: stop calling
  `capped_source.resolve_combo_source`; read personas from `01_Raw/{slug}/persona_*`
  directly (same pattern `cap_populations.py` uses today at `01_Raw`).
- Now maps the **full valid pool** (~500 dirs/combo, ~5× today's work — accepted).
- Output unchanged: `03_Analysis/mapping/{slug}.json`, `real_{country}.json`, `_index.json`.

### 4.2 `population_cap` — cap the clean mapped pool (now runs last of the gate)

- `depends_on: [validate_mapped]`.
- **Reads:** `03_Analysis/validate_raw/{slug}.csv`, `03_Analysis/validate_mapped/{slug}.csv`,
  `03_Analysis/mapping/{slug}.json`, and `01_Raw/{slug}/persona_*` dirs.
- **Selection:** seeded without-replacement draw of `N` from the personas that pass
  **both** CSVs (`passed == True` in each). Fail-fast if fewer than `N` clean personas
  exist (report available count) — do not silently cap short.
- **Writes (materializes two things):**
  1. Capped **raw persona-dir mirror** at `03_Analysis/population_cap/{slug}/` — the
     selected `persona_*` dirs copied whole (preserves `llm_interactions.jsonl` telemetry
     for `generation_metadata` and `identity.json` for `persona_realism`).
  2. Capped **mapped file** for the same `N` (subset of mapping's `{slug}.json`), written
     where downstream mapped-consumers read it (see 4.4). Same schema/filename convention
     as mapping output.
- `_index.json` at the stage root records the selected `persona_id`s per combo.

### 4.3 `capped_source.py` — invariant now scoped to `generation_metadata`

- `mapping` no longer consumes the capped mirror, so the *"no `01_Raw` fallback"*
  fail-fast applies only to `generation_metadata` (capped telemetry). Update the module
  docstring to name `generation_metadata` as the sole consumer.
- **Guardrail impact:** this rewrites the CLAUDE.md hard-rule wording that names
  `population_cap` as the analysis-DAG root and forbids the `01_Raw` fallback for mapping.
  Update CLAUDE.md + the architecture wiki (`sub-packages.md`, `comparison-mapping.md`,
  `analysis_registry.yaml` descriptions) in the same change.

### 4.4 Downstream re-parenting

All of `fidelity, multivariate_fidelity, consistency, pairwise_comparison,
real_population_stats, persona_realism` change `depends_on` from `[mapping]` to
`[population_cap]` and read the **capped mapped file** (from 4.2 item 2) instead of the
full `03_Analysis/mapping/{slug}.json`. `model_ranking`/`method_significance` stay on
`fidelity`. `generation_metadata` stays on `population_cap` (unchanged).

> **Decision point for implementation:** where the capped mapped file lives. Options:
> (a) a subfolder `03_Analysis/population_cap/_mapped/{slug}.json`, consumers point there;
> (b) cap overwrites nothing and consumers read the full mapping file but filter by
> `_index.json`. (a) is cleaner and matches the "materialize a capped mapped file"
> decision — default to (a) unless a consumer's loader makes it painful.

## 5. Edit-point index (from the DAG survey)

| Change | File | Anchor |
|---|---|---|
| Add 2 registry processes | `config/analysis/analysis_registry.yaml` | processes block (near 24–44) |
| Rewire DAG edges | `config/gui/flows/analysis_workflow.yaml` | lines 14, 22, 30, 112 + downstream `depends_on` |
| mapping reads 01_Raw | `scripts/analyze/map_populations.py` | ~48, 199, 285 |
| cap reads CSVs + writes mapped subset | `scripts/analyze/cap_populations.py`, `src/.../analysis/population_cap/cap.py` | cap 59,131,138; cap.py 61–167 |
| Scope invariant | `src/.../analysis/utils/capped_source.py` | 9–13, 44–48 |
| New scripts | `scripts/analyze/validate_raw_personas.py`, `validate_mapped_personas.py` | new |
| New subpackages | `src/.../analysis/validate_raw/`, `src/.../analysis/validate_mapped/` | new |
| Guardrail docs | `CLAUDE.md`, `docs/architecture/{sub-packages,comparison-mapping}.md` | root/no-fallback wording |

## 6. Tests

- New: `tests/test_validate_raw.py`, `tests/test_validate_mapped.py` (fixtures with
  missing `identity.json`, missing categories, `__UNMAPPED__` fields → expected CSV rows).
- Update: mapping test (now reads `01_Raw`), any workflow/DAG test asserting the old
  root/edges, `generation_metadata` test (still on capped mirror), cap test (now selects
  from CSVs, produces capped mapped file).
- `ruff check src/` clean.

## 7. Open verification points (resolve during implementation, no user input needed)

1. Mapping carries source `persona_id` into each mapped record (see §3.2 note).
2. Exact capped-mapped-file location (§4.4 decision point).
3. Whether any downstream loader assumes the mapping folder path literally (grep for
   `analysis_output_dir("mapping"` / `"mapping"` folder reads).

## 8. Suggested implementation order

1. New branch off the integration line.
2. Add registry entries + GUI-flow rewiring (DAG only) — cheap, reviewable.
3. `validate_raw` subpackage + script + tests.
4. Repoint `mapping` to `01_Raw`; ensure `persona_id` linkage.
5. `validate_mapped` subpackage + script + tests.
6. Rework `population_cap` (read CSVs, select clean, emit capped mapped file).
7. Repoint downstream consumers to the capped mapped file.
8. Scope `capped_source` invariant; update CLAUDE.md + wiki.
9. Full `pytest` + `ruff`.
