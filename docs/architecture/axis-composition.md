# Axis Composition System

> **Architecture wiki:** [Home](README.md) · [Sub-packages](sub-packages.md) ·
> [Comparison & mapping](comparison-mapping.md) · [Design principles](design-principles.md) ·
> **Axis composition** · [Configuration](configuration.md) · [Commands](commands.md)

How identity generation is configured via three orthogonal axes instead of a monolithic manifest.

Identity generation can be configured via three orthogonal axes instead of a monolithic manifest.
`compose_manifest` in `src/population_synth/identity/manifest_loader.py` merges YAML from four
layers:

1. `config/synthetic/experiment_defaults.yaml` -- base parameters (mode, output_base, parallel settings)
2. `config/synthetic/axes/models/{model_id}.yaml` -- provider, model name, API key env var
3. `config/synthetic/axes/strategies/{strategy_id}.yaml` -- generation strategy (all_pick, all_generate_pick, etc.)
4. `config/synthetic/axes/countries/{country_id}.yaml` -- country-specific simulation config and reference population

Each strategy yaml is the **single source of truth** for that strategy: it carries `id`, `label`,
`description`, and the full per-category `categories` DAG (`method` + `depends_on`) inline -- the
generator's `_load_strategy` reads `categories` straight from this file (there is no separate
`strategy_defs/` json). Yamls whose filename starts with `_` (e.g. `_debug_minimal.yaml`,
`_compared_only_generate_evaluate_random_pick.yaml`) are co-located strategy definitions that are
usable via an explicit `--strategy <path>` but are **not** selectable axis options --
`discover_axis_values` skips them. The diagram coordinates that used to sit beside each strategy
json now live under `config/gui/layouts/{strategy_id}.layout.json`.

The output slug is `{country_id}_{strategy_id}_{model_id}`, and the run directory is
`{output_base}/01_Raw/{slug}/`. Use `--model-id`, `--strategy-id`, `--country-id` CLI flags instead
of `--manifest` to invoke this path.

## See also

- [Configuration](configuration.md) — the axis config files (`config/synthetic/axes/*`) and the
  simulation configs they point at.
- [Commands](commands.md) — the `--model-id` / `--strategy-id` / `--country-id` invocations.
- [`../development/debugging-identity-generation.md`](../development/debugging-identity-generation.md)
  — reconstructing a run's output directory from its axis IDs.
