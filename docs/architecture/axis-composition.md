# Axis Composition System

> **Architecture wiki:** [Home](README.md) · [Sub-packages](sub-packages.md) ·
> [Comparison & mapping](comparison-mapping.md) · [Design principles](design-principles.md) ·
> **Axis composition** · [Configuration](configuration.md) · [Commands](commands.md)

How identity generation is configured via three orthogonal axes instead of a monolithic manifest.

Identity generation can be configured via three orthogonal axes instead of a monolithic manifest.
`compose_manifest` in `src/population_synthetic/generators/synthetic/manifest_loader.py` merges YAML from four
layers:

1. `config/synthetic/experiment_defaults.yaml` -- base parameters (mode, output_base, parallel settings)
2. `config/synthetic/axes/models/{model_id}.yaml` -- provider, model name, API key env var (supported providers: `gemini`, `claude`, `ollama`, `openai_compat`, `openrouter`)
3. `config/synthetic/axes/strategies/{strategy_id}.yaml` -- generation strategy (all_pick, all_generate_pick, etc.)
4. `config/synthetic/axes/countries/{country_id}.yaml` -- country-specific simulation config and real population

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

## Ollama model axes: per-host workers, no `base_url`

`provider: ollama` model axis files differ from every other provider in two ways, because an
Ollama run targets a *machine* and worker capacity is a function of (model × GPU VRAM):

- **No `model_config.base_url`.** The endpoint is a property of the selected host, not of the
  model. It is resolved at composition time from the host registry
  ([`config/synthetic/ollama_hosts.yaml`](configuration.md)) via the `--ollama-host` flag
  (`None` → the registry's `default_host`). There is no default base URL anywhere in code — the
  client requires an explicit one — so no run can be dispatched to an unintended GPU.
- **`parameters.parallel.workers` is a `{host_id: n}` map**, not a scalar:

  ```yaml
  parameters:
    parallel:
      # Per-host worker count. A host absent from this map does not serve this model.
      workers:
        linux_3060: 2
        windows_4070tis: 6
  ```

  A host id **absent** from the map *is* the "this host does not serve this model" signal — there
  is no separate availability list to keep in sync. A present key asserts both "the weights are
  pulled on that host" and "this worker count has been assessed for it".

`compose_manifest(model_id, strategy_id, country_id, ollama_host_id=None)` is the **one**
normalization point for both facts. It resolves the host, sets `ManifestConfig.base_url` from it,
records the resolved id in `ManifestConfig.ollama_host` (provenance: `run_metadata.json` and
`manifest_snapshot.yaml` both carry it), and **collapses** `workers[host_id]` to the scalar
`ManifestConfig.parallel_workers`. Nothing below this layer learns that hosts exist. The gate is
fail-fast in both directions:

| Condition | Result |
|-----------|--------|
| Selected host absent from a model's `workers` map | Raises, naming the model, the host, and the hosts that **do** serve it — before any persona directory is created |
| `workers` is a scalar (the pre-registry shape) | Raises: accepting it would silently reintroduce a host-implicit worker count |
| Provider is not `ollama` | `--ollama-host` is inert; no host is resolved, `workers` stays the axis file's own scalar |

`workers_for_host(model_data, host_id) -> int | None` is the non-raising twin, for callers that
must **display** an unsupported pair rather than fail on it (the GUI summary panel renders an
em dash). Both route through the same lookup, so they can never disagree.

Non-Ollama model axes keep the scalar `workers`, and the frozen
`config/synthetic/manifests/identity_manifest_0NN_*.yaml` seed manifests keep theirs too — they
are historical records of runs that already happened on one machine, and `load_manifest` (the
file path, not the axis path) reads that scalar unchanged.

## See also

- [Configuration](configuration.md) — the axis config files (`config/synthetic/axes/*`) and the
  simulation configs they point at.
- [Commands](commands.md) — the `--model-id` / `--strategy-id` / `--country-id` invocations.
- [`../development/debugging-identity-generation.md`](../development/debugging-identity-generation.md)
  — reconstructing a run's output directory from its axis IDs.
