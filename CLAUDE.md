# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**population-synth** is a standalone extraction from the `anxiety-synthetic` monorepo. It provides three capabilities:

1. **Population Generation** -- Fetch real demographic distributions from national statistical APIs (SCB for Sweden, SSB for Norway, ISTAT/Eurostat for Italy) and sample statistically realistic population profiles via conditional chained sampling
2. **Identity Generation** -- LLM-based persona identity creation using Gemini models with strategy modes (batch, configurable)
3. **Population Comparison** -- Statistical evaluation and visual comparison between any two population files

## Commands

Requires Python 3.10+.

```bash
# Install (editable mode, required for imports to work)
pip install -e .

# Install with dev tools
pip install -e ".[dev]"

# Install with GUI (PyQt5)
pip install -e ".[gui]"

# Generate Swedish population from live SCB data
python scripts/generate_scb_population.py --n 1000 --seed 42 --output scb_pop.json

# Generate Norwegian population from live SSB data
python scripts/generate_ssb_population.py --n 1000 --seed 42 --output ssb_pop.json

# Generate Italian population from live ISTAT/Eurostat data
python scripts/generate_istat_population.py --n 1000 --seed 42 --output istat_pop.json

# Generate a persona identity via manifest (recommended)
python scripts/generate_identity.py --manifest config/seed_manifests/identity_manifest_014_claude_haiku.yaml

# Generate N identities in parallel via manifest
python scripts/generate_identities_parallel.py --manifest config/seed_manifests/identity_manifest_014_claude_haiku.yaml

# Generate N identities via manifest with CLI overrides
python scripts/generate_identities_parallel.py --manifest config/seed_manifests/identity_manifest_014_claude_haiku.yaml --n 10 --workers 4

# Generate a persona identity via explicit CLI args (Gemini, requires GEMINI_API_KEY)
python scripts/generate_identity.py --provider gemini --mode configurable \
    --config config/assets/identity/configurable/simulation_config_004_swedish_generative.json

# Generate a persona identity via explicit CLI args (Claude CLI, requires claude on PATH)
python scripts/generate_identity.py --provider claude --model sonnet --mode configurable \
    --config config/assets/identity/configurable/simulation_config_004_swedish_generative.json

# Compare two population files
python scripts/compare_populations.py pop_a.json pop_b.json

# Compare pipeline output (persona_*/identity.json files) against an SCB reference (via manifest)
python scripts/compare_pipeline_to_scb.py --manifest config/seed_manifests/identity_manifest_022_claude_sonnet.yaml

# Compare pipeline output against an SCB reference (via explicit path)
python scripts/compare_pipeline_to_scb.py --seed-root path/to/pipeline_output/ \
    --reference scb_population.json --output comparison_report.json

# Compare pipeline output against an ISTAT reference (Italy; country-aware extractor)
python scripts/compare_pipeline_to_istat.py --model-id claude_haiku --strategy-id all_pick --country-id italian

# Compare every model x strategy x country combination against country references (batch)
python scripts/compare_all_pipelines.py --country swedish --country italian

# Extract demographic profiles from a pipeline output tree into a single population file
python scripts/extract_population_from_pipeline.py --seed-root path/to/pipeline_output/ \
    --output pipeline_population.json

# Analyse a single-persona run directory (prints summary table)
python scripts/analyze_run.py path/to/run_dir/

# Analyse a batch run directory (persona_* subdirs) and export full analytics
python scripts/analyze_run.py path/to/batch_run_dir/ --output run_analytics.json

# Analyse with per-persona breakdown
python scripts/analyze_run.py path/to/run_dir/ --verbose

# Batch-analyse every run under {output_base}/01_Raw/ into 03_Analysis/llm_metrics/{slug}/
python scripts/analyze_run.py --all

# Cross-run scientific comparison of LLM metrics (Kruskal-Wallis + Dunn); requires --all first
python scripts/compare_runs.py

# Generate identities via axis composition (model × strategy × country)
python scripts/generate_identities_parallel.py --model-id claude_sonnet --strategy-id all_pick --country-id swedish

# Generate Italian identities via axis composition
python scripts/generate_identities_parallel.py --model-id claude_sonnet --strategy-id all_pick --country-id italian

# Launch the GUI launcher (requires pip install -e ".[gui]")
python -m population_synth.gui.main

# Linting (line-length 120, rules: E/F/W/I)
ruff check src/
```

No test suite exists currently.

## Import Convention

The project uses `src/` layout. The `pyproject.toml` configures `setuptools` to find packages under `src/`, so after `pip install -e .`, the `population_synth` namespace is available:

```python
from population_synth.population.sweden.fetch_service import FetchService
from population_synth.clients.scb_client import SCBPxWebClient
from population_synth.identity.factory_identity_generator import FactoryIdentityGenerator
```

All imports use the fully-qualified `population_synth.*` package namespace. Scripts in `scripts/` depend on the editable install.

## Architecture

### Sub-packages (`src/population_synth/`)

**`population/`** -- Shared population layer with country-specific sub-modules:
- `data.py` -- `PopulationDistributions` dataclass (shared by both countries)
- `helpers.py` -- Shared utilities: `age_to_group`, `sample_from`, `normalize`, `VALID_AGE_GROUPS`, `AGE_GROUP_BOUNDS`
- `income_class.py` -- Income bracket classification using Eurostat AROP (0.60x median) and OECD/Pew (1.00x, 2.00x) thresholds
- `sweden/` -- SCB-specific: constants (table IDs, label maps), fetch service, parsers, sample service
- `norway/` -- SSB-specific: constants (table IDs, label maps), fetch service, parsers, sample service
- `italy/` -- ISTAT/Eurostat-specific: constants (dataflow IDs, NUTS2 codes, label maps), parsers (SDMX + JSON-stat), fetch service (dual-client `load_all`), sample service

**`identity/`** -- LLM-based persona identity generation:
- Factory + Strategy pattern: `FactoryIdentityGenerator` selects batch or configurable strategy at runtime
- Base class defines the generation interface; each strategy implements `generate_identity()`
- Mode semantics:
  - `batch` -- single-prompt narrative-style generation
  - `configurable` -- strategy-driven generation controlled by a simulation config JSON file with pluggable strategy definitions

**`comparison/`** -- Statistical evaluation and charting (population quality vs a reference):
- `StatisticalEvaluator` computes per-field chi-squared tests and total variation distances
- `normalizer` converts raw API output format to canonical schema for comparison. `normalize_raw_to_schema()` (formerly `normalize_scb_to_schema`) and `normalize_if_raw()` take an optional `mappings_path` so the same code path serves both SCB and ISTAT
- `charts` generates bar-chart and radar-chart PNGs via matplotlib
- `extractor` pulls demographic fields from pipeline `identity.json` files. **Country-aware**: `extract_individual()` / `extract_population()` take a `country` parameter (`"swedish"` default for backward-compat, `"italian"` loads Italian label sets, city->region map, and ISTAT mappings)

**`gui/`** -- PyQt5 desktop launcher for running generation and comparison tasks. `LauncherWindow` presents action groups (Generate, Compare) defined in `config/gui_launcher.yaml`. Axis selection uses checkbox lists (`CheckableAxisList` x3 inside `ExperimentSelector`) rather than dropdowns, so a single launch runs the full **cartesian product** of selected models x strategies x countries -- `ExperimentSelection.combinations()` enumerates the tuples via `itertools.product`, `ManifestOverview` previews them in a table, and `CombinationRunner` (QThread) runs each as a `--model-id/--strategy-id/--country-id` subprocess with live console streaming and process-tree abort. Selections persist to `config/gui_state.json`.

**`analysis/`** -- Post-processing analytics for identity generation runs (LLM call behaviour, distinct from `comparison/` which scores population quality):
- `interaction_parser.py` / `log_parser.py` -- Parse `llm_interactions.jsonl` and log files from run output
- `joiner.py` -- Enriches JSONL interaction records by matching to log-file call records via timestamp proximity (±2s). Note: parallel runs write a single top-level master log (`01_Raw/{slug}/logs/`), not per-persona logs; `analyze_run.py` joins that master log so token/latency fields populate. The ±2s join means per-persona token sums are approximate in parallel runs, but aggregate/per-category distributions are sound
- `aggregator.py` -- Computes per-persona metrics: call counts, retry rates, token consumption, latency percentiles, prompt size growth, value diversity (Shannon entropy)
- `charts.py` (`plot_run_charts`) -- 9 per-run analytics PNGs (call counts, retry rates, entropy, token budgets, latency); token-gated charts skipped when the provider reports no token counts (e.g. Claude/Gemini CLI)
- `run_comparison.py` (`build_comparison`, `METRIC_SPECS`, `decompose_slug`) -- Cross-run statistics: groups runs by model and strategy (country fixed), runs Kruskal-Wallis H + inline Dunn post-hoc (Holm-corrected, no external dep)
- `comparison_charts.py` (`plot_run_comparison`) -- Box plots (with significance brackets), mean±SD bars, and model×method heatmaps per metric

**`utils/`** -- Minimal pipeline utilities (`should_process_task()` for skip-if-done logic)

**`clients/`** -- API clients:
- `BasePxWebClient` -- Shared HTTP client with local JSON file caching
- `SCBPxWebClient` -- Statistics Sweden PxWeb API (POST requests)
- `SSBPxWebClient` -- Statistics Norway PxWebApi v2 (GET requests, POST fallback, >=2.1s rate limiter)
- `GeminiClient` -- Google Gemini API wrapper with metadata sidecar tracking
- `ClaudeCodeClient` -- Claude CLI subprocess wrapper with metadata sidecar tracking
- `llm_protocol.py` -- `LLMClient` Protocol shared by `GeminiClient` and `ClaudeCodeClient`
- `EurostatClient` -- Eurostat JSON-stat 2.0 API wrapper with local JSON caching (90-day TTL)
- `ISTATSDMXClient` -- ISTAT SDMX REST API wrapper with 12-second rate limiting and caching

### Path Resolution

`_paths.py` provides a single `PROJECT_ROOT` constant:
```python
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # src/population_synth/ -> population-synth/
```
All cache and config paths derive from this.

## Key Design Patterns

- **Shared population layer** -- Breaks the SCB<->SSB cross-dependency. Both `sweden/` and `norway/` import from the shared `population/` parent, never from each other
- **Factory + Strategy** -- `FactoryIdentityGenerator` selects generation strategy at runtime based on mode string
- **Conditional chained sampling** -- Population sampling conditions each attribute on prior draws (e.g., education given age/sex, employment given education)
- **No synthetic distributions** -- Every probability distribution used in population generation must come from a real statistical API response. Hardcoded probability tables, fallback distributions, parametric approximations (e.g. lognormal models), and manually estimated rates are prohibited as primary data sources. If no API provides data for a demographic field, that field must be dropped from the output -- never filled with invented values. Code-level constants for structural purposes (API dataset IDs, code-to-label maps, query parameters) are acceptable; constants that define *what probability a person has of being in a given category* are not
- **Local file caching** -- PxWeb clients cache API responses as JSON files in `config/assets/{scb,ssb}_cache/` to avoid redundant API calls
- **Full comparison output** -- When comparing pipeline output against a reference (database) population, every output artifact must be generated: a bar chart for each of the 15 demographic attributes in `DEMOGRAPHIC_ATTRIBUTES` (age_group, biological_sex, education_level, employment_status, birth_location, socioeconomic_class, parental_structure, region, civil_status, industry_sector, employment_type, housing_tenure, household_size, income_source, birth_country_detail), a radar chart with TV-similarity across all attributes, the JSON comparison report (marginals + joint chi-squared + coherence), and the CSV marginals summary. Charts are only skipped when an attribute has zero data in both populations -- if the reference population provides the field, the chart must appear

## Axis Composition System

Identity generation can be configured via three orthogonal axes instead of a monolithic manifest. `compose_manifest` in `src/population_synth/identity/manifest_loader.py` merges YAML from four layers:

1. `config/experiment_defaults.yaml` -- base parameters (mode, output_base, parallel settings)
2. `config/models/{model_id}.yaml` -- provider, model name, API key env var
3. `config/strategies/{strategy_id}.yaml` -- generation strategy (all_pick, all_generate_pick, etc.)
4. `config/countries/{country_id}.yaml` -- country-specific simulation config and reference population

The output slug is `{country_id}_{strategy_id}_{model_id}`, and the run directory is `{output_base}/01_Raw/{slug}/`. Use `--model-id`, `--strategy-id`, `--country-id` CLI flags instead of `--manifest` to invoke this path.

## Configuration

- **Seed manifests:** `config/seed_manifests/` -- YAML files that bundle all identity generation settings (provider, model, mode, config, strategy, parallel params) into a single file. Loaded via `--manifest` flag. CLI args override manifest values when both are provided.
- **Identity prompts and simulation configs:** `config/assets/identity/` (batch and configurable sub-directories)
- **SCB API cache:** `config/assets/scb_cache/` (git-ignored)
- **SSB API cache:** `config/assets/ssb_cache/` (git-ignored)
- **Eurostat API cache:** `config/assets/eurostat_cache/` (git-ignored)
- **ISTAT API cache:** `config/assets/istat_cache/` (git-ignored)
- **Category label mappings:** `config/assets/scb_reference/category_mappings.json`, `config/assets/ssb_reference/category_mappings.json`, and `config/assets/istat_reference/category_mappings.json` (Italy). All three share the same sub-key structure so the normalizer is country-agnostic -- the JSON content supplies the translations
- **Axis configs:** `config/models/`, `config/strategies/`, `config/countries/` -- YAML files composable via `--model-id`, `--strategy-id`, `--country-id`. A country YAML is minimal (`id`, `label`, `parameters.config` pointing at a simulation config JSON). `swedish` -> `simulation_config_004_swedish_generative.json`, `italian` -> `simulation_config_005_italian_generative.json`; each simulation config carries a locale-specific `instruction` system prompt and per-attribute `categories`
- **Experiment defaults:** `config/experiment_defaults.yaml` -- base parameters including `output_base` path
- **Run-analytics defaults:** `config/analyze_defaults.yaml` -- `output_base` plus the `analytics` output layout used by `analyze_run.py` / `compare_runs.py`: per-run analytics land in `{output_base}/03_Analysis/llm_metrics/{slug}/` and cross-run comparison in `.../llm_metrics/_comparison/`
- **GUI launcher config:** `config/gui_launcher.yaml` -- action groups and parameter definitions for the PyQt5 launcher

## Debugging Identity Generation Failures

### Locating the run output directory

Run output does **not** live in the repo `data/` folder -- it lives under the `output_base` defined in `config/experiment_defaults.yaml` (currently `F:/liu-onedrive-nospecial-carac/_Teams/Gauss/02_Data`). When asked to debug a run described by model + country + strategy (e.g. "the lucie 7b, swedish, all pick" run), reconstruct the path from the axis config files instead of searching `data/`:

- **Axis-composed runs** (`--model-id` / `--strategy-id` / `--country-id`): the slug is `{country_id}_{strategy_id}_{model_id}` and the run dir is `{output_base}/01_Raw/{slug}` (comparison output at `{output_base}/03_Analysis/{slug}`). See `compose_manifest` in `src/population_synth/identity/manifest_loader.py`. The axis IDs are the YAML filenames (without extension) under `config/models/`, `config/strategies/`, and `config/countries/` -- e.g. model `ollama_lucie_7b` + strategy `all_pick` + country `swedish` resolves to `{output_base}/01_Raw/swedish_all_pick_ollama_lucie_7b/`.
- **Manifest runs** (`--manifest`): the run dir is `parameters.parallel.output_dir` declared in the manifest YAML.

Confirm you have the right run by reading `manifest_snapshot.yaml` and `run_metadata.json` in the run dir -- both record the exact model, config, and strategy.

When a persona generation fails, look at these files in the output directory (e.g., `01_Raw/{slug}/` for parallel runs):

1. **`logs/run_YYYYMMDD_HHMMSS.log`** -- Python log file (DEBUG level). Contains a category-level ERROR line naming exactly which category failed, its method, and how many categories were resolved before the failure. Start here.
2. **`llm_interactions.jsonl`** (single runs) or **`persona_XXXXX/llm_interactions.jsonl`** (parallel runs) -- JSONL file written incrementally during generation. Each line is a JSON object with: `category`, `method`, `step`, `prompt`, `raw_response`, `parsed_value`, `error`, `attempt`, `timestamp`. On failed LLM parse attempts, `error` contains the exception type and message (e.g., `"JSONDecodeError: Expecting ',' delimiter"`), `parsed_value` is `null`, and `step` has a `_retry` suffix. This file survives crashes -- entries are flushed to disk as they happen.
3. **`run_metadata.json`** -- Run-level config (provider, model, strategy, timestamps). Useful for reproducing the run.

Key implementation files for the logging infrastructure:
- `src/population_synth/identity/llm_interaction_log.py` -- `LLMInteractionEntry` dataclass and `LLMInteractionCollector` (incremental JSONL writer)
- `src/population_synth/identity/identity_generator_configurable.py` -- `_call_llm_json()` handles JSON parse retries (3 attempts); `generate_identity()` logs category-level errors before re-raising

## Reference Documentation

The `docs/` directory holds design and audit notes worth consulting before non-trivial changes:
- `scb_population_and_comparison.md` -- end-to-end SCB pipeline and comparison design
- `scb_population_distribution_analysis.md` (+ `_verification.md`) -- per-field distribution analysis
- `audit_scb_comparison_api_rooting_2026-05-11.md` -- audit of comparison-vs-API field routing
- `scb02_comparison_category_mapping_2026-05-11.md` -- category-mapping rationale
- `istat_population_data_sources.md` -- Italy field-by-field API source matrix, protocol details, sampling chain, known limitations
- `docs/development/` -- in-progress development notes

## Environment & Secrets

- `GEMINI_API_KEY` environment variable required for identity generation with `--provider gemini` (raises `ValueError` if missing)
- `--provider claude` requires the `claude` CLI on PATH; raises `RuntimeError` at construction if not found; no extra API key needed (Claude Code manages its own auth)
- Population generation (SCB/SSB scripts) does not require any API keys
