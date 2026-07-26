# Changelog: `population_cap` (pre-mapping subsample task)

**Date:** 2026-07-23
**Author:** Basil
**Branch:** `feature/cap-population-to-n`
**Plan:** `docs/development/plans/active/cap-population-to-n.md`

## Summary

Added `population_cap`, a new analysis-pipeline process that runs **first** (the DAG root). For each
combination (`country × strategy × model`) it seeded-selects exactly **N** of the generated
`persona_*` directories and copies them — with the combo-level `logs/` / `run_metadata.json` /
`manifest_snapshot.yaml` — into a layout-identical **capped mirror** at
`03_Analysis/population_cap/{slug}/`. The two raw-persona consumers (`mapping`,
`generation_metadata`) now read that mirror instead of `01_Raw`, so N is a single enforced,
inspectable invariant and no downstream task can silently analyze more than N personas.

## Added

- `analysis/utils/sampling.py::select_indices(total, n, seed)` — reproducible without-replacement
  index draw, factored out of `subsample_population` (shared by the cap and the fidelity subsample).
- `analysis/population_cap/` package — `cap_combo(raw_slug_dir, n, seed, dest_dir, *, force)` returning
  a `CapSummary` (`{slug, requested_n, available, selected, seed, selected_ids, truncated}`).
- `analysis/utils/capped_source.py` — `resolve_combo_source(slug, output_base)` /
  `resolve_stage_source(output_base)` read resolvers. Both **raise `FileNotFoundError` when the
  mirror is absent — no `01_Raw` fallback** (user directive 2026-07-23).
- `scripts/analyze/cap_populations.py` — `per_combo` CLI
  (`--model-id --strategy-id --country-id --n [required] --sample-seed [default 0] --output-base --force`);
  writes the capped mirror and an accumulating `03_Analysis/population_cap/_index.json`.
- Registry entry `population_cap` in `config/analysis/analysis_registry.yaml` (folder `population_cap`,
  dispatch `per_combo`).

## Changed

- `scripts/analyze/map_populations.py` — reads synthetic personas via `resolve_combo_source(slug,
  output_base)` at all seed-root sites (was `manifest.parallel_output_dir`).
- `analysis/generation_metadata/__init__.py::summarize()` — reads the raw stage via
  `resolve_stage_source(base)` (was `base / "01_Raw"`).
- `config/gui/flows/analysis_workflow.yaml` — `population_cap` is the DAG root (`depends_on: []`);
  `mapping` and `generation_metadata` now `depends_on: [population_cap]`.

## Behavior notes

- **Fail-fast, no fallback.** With no capped mirror present, `mapping` and `generation_metadata` raise
  `FileNotFoundError` instructing the user to run `population_cap` first — they never fall back to
  `01_Raw`. Disabling the task therefore requires a code revert of the consumer edits, not a
  config-only toggle (see the plan's Rollback section).
- **Under-generation** (`available < n`) copies all available personas and logs a loud warning;
  `truncated` is `True` only when the draw genuinely dropped personas (`available > n`).
- **`--n` is mandatory** (raises if missing); **`--sample-seed 0`** is a valid seed, not "unset".
- **Out of scope this iteration:** `fidelity` / `multivariate_fidelity` keep their now-redundant
  `--n-synthetic` / `--sample-seed` flags (recommended follow-up: blank them in the flow).

## Tests

- `tests/test_population_cap.py` (new) — `select_indices`, `cap_combo` (over/under-generation,
  ancillary copy, `force`, 0-persona edge, seed-0), the resolvers (present vs absent, no `01_Raw`
  fallback), and integration (cap → mapping loader sees N; cap → `summarize` aggregates over N;
  no-mirror fail-fast on both consumer seams).
- `tests/test_generation_metadata.py` — the two `summarize` integration tests now run the real
  cap → summarize order (build `01_Raw` fixture → `cap_combo` → `summarize`).
