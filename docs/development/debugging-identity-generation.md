# Debugging Identity Generation Failures

> **See also:** [Architecture wiki](../architecture/README.md) ·
> [Axis composition](../architecture/axis-composition.md) ·
> [`debug/`](debug/) (deeper client/API investigation notes)

A runbook for diagnosing a failed persona generation: locating the run output directory and
reading the incremental logs that survive a crash.

## Locating the run output directory

Run output does **not** live in the repo `data/` folder -- it lives under the `output_base`
defined in `config/synthetic/experiment_defaults.yaml` (currently
`F:/liu-onedrive-nospecial-carac/_Teams/Gauss/02_Data`). When asked to debug a run described by
model + country + strategy (e.g. "the lucie 7b, swedish, all pick" run), reconstruct the path from
the axis config files instead of searching `data/`:

- **Axis-composed runs** (`--model-id` / `--strategy-id` / `--country-id`): the slug is
  `{country_id}_{strategy_id}_{model_id}` and the run dir is `{output_base}/01_Raw/{slug}`
  (comparison output at `{output_base}/03_Analysis/{slug}`). See `compose_manifest` in
  `src/population_synthetic/generators/synthetic/manifest_loader.py`. The axis IDs are the YAML filenames (without
  extension) under `config/synthetic/axes/models/`, `config/synthetic/axes/strategies/`, and
  `config/synthetic/axes/countries/` -- e.g. model `ollama_lucie_7b` + strategy `all_pick` +
  country `swedish` resolves to `{output_base}/01_Raw/swedish_all_pick_ollama_lucie_7b/`.
- **Manifest runs** (`--manifest`): the run dir is `parameters.parallel.output_dir` declared in the
  manifest YAML.

Confirm you have the right run by reading `manifest_snapshot.yaml` and `run_metadata.json` in the
run dir -- both record the exact model, config, and strategy.

## Files to inspect

When a persona generation fails, look at these files in the output directory (e.g.,
`01_Raw/{slug}/` for parallel runs):

1. **`logs/run_YYYYMMDD_HHMMSS.log`** -- Python log file (DEBUG level). Contains a category-level ERROR line naming exactly which category failed, its method, and how many categories were resolved before the failure. Start here.
2. **`llm_interactions.jsonl`** (single runs) or **`persona_XXXXX/llm_interactions.jsonl`** (parallel runs) -- JSONL file written incrementally during generation. Each line is a JSON object with: `category`, `method`, `step`, `prompt`, `raw_response`, `parsed_value`, `error`, `attempt`, `timestamp`. On failed LLM parse attempts, `error` contains the exception type and message (e.g., `"JSONDecodeError: Expecting ',' delimiter"`), `parsed_value` is `null`, and `step` has a `_retry` suffix. This file survives crashes -- entries are flushed to disk as they happen.
3. **`run_metadata.json`** -- Run-level config (provider, model, strategy, timestamps). Useful for reproducing the run.

## Logging infrastructure

Key implementation files for the logging infrastructure:
- `src/population_synthetic/generators/synthetic/llm_interaction_log.py` -- `LLMInteractionEntry` dataclass and `LLMInteractionCollector` (incremental JSONL writer)
- `src/population_synthetic/generators/synthetic/identity_generator_configurable.py` -- `_call_llm_json()` handles JSON parse retries (3 attempts); `generate_identity()` logs category-level errors before re-raising
