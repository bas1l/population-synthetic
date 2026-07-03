# Configuration Reference

> **Architecture wiki:** [Home](README.md) · [Sub-packages](sub-packages.md) ·
> [Comparison & mapping](comparison-mapping.md) · [Design principles](design-principles.md) ·
> [Axis composition](axis-composition.md) · **Configuration** · [Commands](commands.md)

The `config/` inventory: what each config tree holds and which code reads it.

- **Seed manifests:** `config/synthetic/manifests/` -- YAML files that bundle all identity generation settings (provider, model, mode, config, strategy, parallel params) into a single file. Loaded via `--manifest` flag. CLI args override manifest values when both are provided.
- **Simulation configs:** `config/synthetic/simulation_configs/` -- per-attribute `categories` schema + locale `instruction` system prompt for configurable mode. Strategy definitions are single-file yamls under `config/synthetic/axes/strategies/` (see [Axis composition](axis-composition.md)).
- **SCB API cache:** `config/database/caches/scb/` (git-ignored)
- **SSB API cache:** `config/database/caches/ssb/` (git-ignored)
- **Eurostat API cache:** `config/database/caches/eurostat/` (git-ignored)
- **ISTAT API cache:** `config/database/caches/istat/` (git-ignored)
- **Category label mappings:** `config/mapping/{scb,istat}/` -- the unified symmetric comparison config: one JSON file per comparison attribute (filename stem == top-level key) declaring `values`/`real`/`synthetic`, plus an `_index.json` master (`attribute -> filename` in axis order -- attributes only). The loader (`load_mappings`/`load_index` in `analysis/mapping/real_mapper/mappings.py`; `analysis/mapping/normalizer.py` re-exports `load_mappings`) merges every `*.json` in a country directory into a single dict keyed by stem (it also still accepts a single monolithic file). Both mapper sides and the comparison scheme are driven entirely by this config -- see [Comparison & mapping](comparison-mapping.md) and each dir's `README.md`. The cross-attribute comparison statistics (`joint_pairs`/`coherence_attributes`/`coherence_threshold`) are **not** here -- they live in `config/analysis/comparison/{scb,istat}.json` (see **Run-analytics defaults** below / `analysis/comparison/scheme.py`). (`config/mapping/ssb/` is legacy Norway config, not wired into the comparison scheme mechanism.)
- **Axis configs:** `config/synthetic/axes/models/`, `config/synthetic/axes/strategies/`, `config/synthetic/axes/countries/` -- YAML files composable via `--model-id`, `--strategy-id`, `--country-id`. A country YAML carries `id`, `label`, `parameters.config` (pointing at a simulation config JSON), plus `parameters.reference` (real-population path; the YAML key itself is unrenamed pending a follow-up config-layer rename) and `parameters.mappings` (mappings dir) consumed by the comparison pipeline's `analysis/utils/country_config.py`. `swedish` -> `simulation_config_004_swedish_generative.json`, `italian` -> `simulation_config_005_italian_generative.json`; each simulation config carries a locale-specific `instruction` system prompt and per-attribute `categories`
- **Experiment defaults:** `config/synthetic/experiment_defaults.yaml` -- base parameters including `output_base` path
- **Comparison targets:** `config/analysis/comparison_targets.yaml` -- the explicit completeness list consumed by the map stage (`scripts/analyze/map_populations.py`). `targets:` is a list of entries, each either a plain manifest-path string (country inferred from the simulation-config filename) or a `{manifest, country}` mapping (explicit country override). The map stage processes only these targets -- it does not scan disk.
- **Run-analytics defaults:** `config/analysis/analyze_defaults.yaml` -- `output_base` plus the `analytics` output layout used by `analyze_run.py` / `compare_runs.py`: per-run analytics land in `{output_base}/03_Analysis/llm_metrics/{slug}/` and cross-run comparison in `.../llm_metrics/_comparison/`
- **GUI config:** `config/gui/v2/menu.yaml` + `config/gui/v2/flows/*.yaml` -- the catalogue and per-flow round-trip YAML for the primary Flow Runner GUI (`gui_v2`; see [gui_v2 Flow Runner](../development/gui-v2.md)). `config/gui/launcher.yaml` -- action groups and parameter definitions for the **deprecated** original PyQt5 launcher (`gui`)

## See also

- [Axis composition](axis-composition.md) — how the axis configs merge into a run.
- [Comparison & mapping](comparison-mapping.md) — how `config/mapping/*` and
  `config/analysis/comparison/*` drive the mappers and scoring.
- [Design principles](design-principles.md) — the "config is the single source of truth" rule
  these files exist to satisfy.
