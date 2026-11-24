# swedish_02 — country axis (guided-prompt A/B arm)

**Created:** 2026-07-24 · **Base:** `swedish.yaml`

A second Swedish country axis, added to run the **guided-prompt** simulation config
(`simulation_config_006_swedish_generative_guided.json`) **side by side** with the baseline
without overwriting it. Baseline `swedish` (the original, unnumbered "01" axis) keeps pointing at
`simulation_config_004_swedish_generative.json`; `swedish_02` is the "02" variant that swaps only
the `config` to `006`. `reference` (the SCB n=10000 population) and `mappings`
(`config/mapping/scb_native`) are **identical** to `swedish`, so the two arms are scored on exactly
the same real reference and value axes — a clean A/B.

## Why this file exists

Config `006` refines three field descriptions (`employment_type`, `employment_status`,
`parental_structure`) to reduce prompt under-specification — see
`config/synthetic/simulation_configs/simulation_config_006_swedish_generative_guided.README.md`
and the manuscript note `…/analysis-notes/employment-mapping-confound.md`. Because the prompt text
changes, runs on `006` are a **new experimental condition**, not a retroactive fix, so they need
their own axis id and their own output namespace.

## Effect on outputs

The slug format is `{country}_{strategy}_{model}` (`manifest_loader.axis_slug`). A distinct country
id gives distinct slugs, so nothing collides with the baseline:

| arm | country id | config | example slug |
|---|---|---|---|
| baseline | `swedish` | 004 | `swedish_all_generate_pick_ollama_deepseek_r1_14b` |
| guided | `swedish_02` | 006 | `swedish_02_all_generate_pick_ollama_deepseek_r1_14b` |

The GUI Flow Runner auto-discovers this axis (`manifest_loader.discover_axis_values("countries")`
globs `axes/countries/*.yaml`), so `swedish_02` appears as a selectable country. The generate flow
`config/gui/flows/generate_parallel.yaml` is set to `countries: [swedish_02]` for the A/B run.

## Required for the ANALYSIS leg (not yet done)

The mapper factories (`analysis/mapping/{synthetic,real}_mapper/factory.py`) resolve the mapper via
an **exact-match** dict keyed by country id (`{"swedish", "italian"}`). The map stage
(`map_populations.py`) passes the `--country-id` through directly, so mapping/scoring a
`swedish_02` run will raise `No synthetic mapper for country 'swedish_02'` until `swedish_02` is
**aliased to the Swedish mapper** in both `_SYNTHETIC_MAPPERS` and `_REAL_MAPPERS`. Generation works
without this; only the downstream map/validate/fidelity stages need the alias.
