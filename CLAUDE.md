# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**population-synth** is a standalone extraction from the `anxiety-synthetic` monorepo. It provides three capabilities:

1. **Population Generation** -- Fetch real demographic distributions from national statistical APIs (SCB for Sweden, SSB for Norway, ISTAT/Eurostat for Italy) and sample statistically realistic population profiles via conditional chained sampling
2. **Identity Generation** -- LLM-based persona identity creation using Gemini models with configurable strategy mode
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
python scripts/generate/generate_scb_population.py --n 1000 --seed 42 --output scb_pop.json

# Generate Norwegian population from live SSB data
python scripts/generate/generate_ssb_population.py --n 1000 --seed 42 --output ssb_pop.json

# Generate Italian population from live ISTAT/Eurostat data
python scripts/generate/generate_istat_population.py --n 1000 --seed 42 --output istat_pop.json

# Generate a persona identity via manifest (recommended)
python scripts/generate/generate_identity.py --manifest config/synthetic/manifests/identity_manifest_014_claude_haiku.yaml

# Generate N identities in parallel via manifest
python scripts/generate/generate_identities_parallel.py --manifest config/synthetic/manifests/identity_manifest_014_claude_haiku.yaml

# Generate N identities via manifest with CLI overrides
python scripts/generate/generate_identities_parallel.py --manifest config/synthetic/manifests/identity_manifest_014_claude_haiku.yaml --n 10 --workers 4

# Generate a persona identity via explicit CLI args (Gemini, requires GEMINI_API_KEY)
python scripts/generate/generate_identity.py --provider gemini --mode configurable \
    --config config/synthetic/simulation_configs/simulation_config_004_swedish_generative.json

# Generate a persona identity via explicit CLI args (Claude CLI, requires claude on PATH)
python scripts/generate/generate_identity.py --provider claude --model sonnet --mode configurable \
    --config config/synthetic/simulation_configs/simulation_config_004_swedish_generative.json

# Compare two population files
python scripts/analyze/compare_populations.py pop_a.json pop_b.json

# Compare pipeline output (persona_*/identity.json files) against an SCB reference (via manifest)
python scripts/analyze/compare_pipeline_to_scb.py --manifest config/synthetic/manifests/identity_manifest_022_claude_sonnet.yaml

# Compare pipeline output against an SCB reference (via explicit path)
python scripts/analyze/compare_pipeline_to_scb.py --seed-root path/to/pipeline_output/ \
    --reference scb_population.json --output comparison_report.json

# Compare pipeline output against an ISTAT reference (Italy; country-aware extractor)
python scripts/analyze/compare_pipeline_to_istat.py --model-id claude_haiku --strategy-id all_pick --country-id italian

# Compare every model x strategy x country combination against country references (batch)
python scripts/analyze/compare_all_pipelines.py --country swedish --country italian

# Extract demographic profiles from a pipeline output tree into a single population file
python scripts/generate/extract_population_from_pipeline.py --seed-root path/to/pipeline_output/ \
    --output pipeline_population.json

# Analyse a single-persona run directory (prints summary table)
python scripts/analyze/analyze_run.py path/to/run_dir/

# Analyse a batch run directory (persona_* subdirs) and export full analytics
python scripts/analyze/analyze_run.py path/to/batch_run_dir/ --output run_analytics.json

# Analyse with per-persona breakdown
python scripts/analyze/analyze_run.py path/to/run_dir/ --verbose

# Batch-analyse every run under {output_base}/01_Raw/ into 03_Analysis/llm_metrics/{slug}/
python scripts/analyze/analyze_run.py --all

# Cross-run scientific comparison of LLM metrics (Kruskal-Wallis + Dunn); requires --all first
python scripts/analyze/compare_runs.py

# Generate identities via axis composition (model × strategy × country)
python scripts/generate/generate_identities_parallel.py --model-id claude_sonnet --strategy-id all_pick --country-id swedish

# Generate Italian identities via axis composition
python scripts/generate/generate_identities_parallel.py --model-id claude_sonnet --strategy-id all_pick --country-id italian

# Launch the GUI launcher (requires pip install -e ".[gui]")
python -m population_synth.gui.main

# Linting (line-length 120, rules: E/F/W/I)
ruff check src/
```

A pytest suite lives under `tests/` (covers the `analysis/` layer and `clients/call_context`). Run it with `pytest` (requires `pip install -e ".[dev]"`).

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
- Factory + Strategy pattern: `FactoryIdentityGenerator` selects the generation strategy at runtime
- Base class defines the generation interface; each strategy implements `generate_identity()`
- Mode semantics:
  - `configurable` -- strategy-driven generation controlled by a simulation config JSON file with pluggable strategy definitions

**`comparison/`** -- Statistical evaluation and charting (population quality vs a reference):
- `StatisticalEvaluator` computes per-field chi-squared tests and total variation distances
- `charts` generates bar-chart and radar-chart PNGs via matplotlib
- **Unified symmetric mapping config** -- both mapper sides are driven by one per-country config tree (`config/mapping/{scb,istat}/`, one JSON file per comparison attribute + an `_index.json` master) and one shared resolver `comparison/mapping_engine.py` (`resolve`). Each per-attribute file is *symmetric*: it declares `values` once (the unified category set **and** the scored axis / chart order) plus a `database` rules block and a `synthetic` rules block, both keyed by unified value -> matcher (key order = match priority). The resolver walks `values` in order and returns the first value whose matcher hits, else `None`. Matcher vocabulary: `equals`/`contains`/`all_of`/`none_of`/`int`/`int_gte` + a composite sub-field matcher (for `employment_type`'s attachment x hours); precedence within a value is `none_of` -> `equals` -> `all_of` -> `contains` -> numeric. Attribute-level directives: `absent` (missing-input literal), `refine_from` (re-walk a sibling's resolved value, e.g. `birth_location` from `birth_country_detail`), `on_miss` (default when all miss), `fuzzy` (substring-match raw against the value labels, default true). The `_index.json` master lists the in-scope attributes (`attribute -> filename`, key order = axis order) plus `joint_pairs`/`coherence_attributes`; country scope is data-driven (Italy's master omits `income_source`). There is no `_scheme.json` filter and no `output_categories`/`reference_*`/`pipeline_*` dual vocabulary -- the scored axis simply *is* each file's `values` because both mappers emit only declared values. See `config/mapping/{scb,istat}/README.md` and `docs/database_mapper_philosophy.md`.
- `reference_mapper/` maps the **reference** (database) population -- raw national-statistics records (nested `RawCategory` dicts from SCB/ISTAT) -> canonical schema labels. Class hierarchy `AbstractReferenceMapper -> BaseReferenceMapper -> {SwedishReferenceMapper, ItalianReferenceMapper}` with a `get_reference_mapper(country, mappings_path=None)` factory. `BaseReferenceMapper` is a **thin loader** over `mapping_engine.resolve`: it reads the `_index.json` master + each attribute file's `database` block/`values`, flattens the raw `RawCategory` dicts (or, for `employment_type`, the attachment/hours sub-field dict) and delegates. It holds **zero field-name/category literals** -- the only in-code responsibilities are `id` passthrough and the raw `age` passthrough (`age_group` is derived at scoring time). Country divergence is one subclass attribute, `MAPPINGS_SUBDIR`. Two-step API: `load_reference_population(path)` then `normalize_population(raw_pop, country)` (normalizes only if raw-format; an already-flat population passes through). Supporting primitives `load_mappings`/`load_index`/`is_raw_format` live in the package; `normalizer.py` is a thin backward-compat facade delegating to it, kept because `extract/mappings.py` imports `load_mappings` from there
- `synthetic_mapper/` maps the **synthetic** (pipeline) population -- raw `identity.json` free-text values -> canonical schema labels -- via `AbstractSyntheticMapper -> BaseSyntheticMapper -> {SwedishSyntheticMapper, ItalianSyntheticMapper}`. `BaseSyntheticMapper` is the synthetic-side mirror of the reference base: a thin loader over `mapping_engine.resolve` reading each attribute's `synthetic` block/`values`, delegating every attribute. Its remaining in-code responsibilities are the format gate (unrecognised formats such as a legacy `{"narrative": ...}` blob warn and return `None`), record-level UTF-8 repair, and the persona-skip `age` gate (missing/non-integer `age` skips the persona). Country divergence is one subclass attribute, `MAPPINGS_SUBDIR`. Two-step API: `load_raw_population(seed_root)` then `map_population(raw_pop, country)`, mirroring the reference side. `get_synthetic_mapper(country)` is the factory; text helpers live in `synthetic_mapper/_text_helpers.py`
- `extractor` is a thin backward-compat facade: `extract_individual()` / `extract_population()` (both take a `country` param) delegate to the synthetic mapper; kept for tests and `extract_population_from_pipeline.py`

**`gui/`** -- PyQt5 desktop launcher for running generation and comparison tasks. `LauncherWindow` presents action groups (Generate, Compare) defined in `config/gui/launcher.yaml`. Axis selection uses checkbox lists (`CheckableAxisList` x3 inside `ExperimentSelector`) rather than dropdowns, so a single launch runs the full **cartesian product** of selected models x strategies x countries -- `ExperimentSelection.combinations()` enumerates the tuples via `itertools.product`, `ManifestOverview` previews them in a table, and `CombinationRunner` (QThread) runs each as a `--model-id/--strategy-id/--country-id` subprocess with live console streaming and process-tree abort. Selections persist to `config/gui/state.json`.

**`analysis/`** -- Post-processing analytics for identity generation runs (LLM call behaviour, distinct from `comparison/` which scores population quality). Organised as a **two-level pipeline** split across three subpackages: `per_run/` (pipeline A, driven by `analyze_run.py`) turns one run into per-persona analytics + a report; `cross_run/` (pipeline B, driven by `compare_runs.py`) consumes many runs' analytics and produces a cross-run comparison; `shared/` holds the numeric primitives both pipelines use. `per_run/` and `cross_run/` never import each other -- only through `shared/`.

- **`shared/`** -- `_stats.py` -- stdlib numeric primitives (median, percentile, Shannon entropy) used by both pipelines; no external dep.
- **`per_run/`** -- single-run pipeline (parse -> join -> aggregate -> visualize/report):
  - `interaction_parser.py` / `log_parser.py` -- Parse `llm_interactions.jsonl` and log files from run output
  - `joiner.py` -- Enriches JSONL interaction records by matching to log-file call records via timestamp proximity (±2s). Note: parallel runs write a single top-level master log (`01_Raw/{slug}/logs/`), not per-persona logs; `analyze_run.py` joins that master log so token/latency fields populate. The ±2s join means per-persona token sums are approximate in parallel runs, but aggregate/per-category distributions are sound
  - `aggregator.py` -- Computes per-persona metrics: call counts, retry rates, token consumption, latency percentiles, prompt size growth, value diversity (Shannon entropy)
  - `charts.py` (`plot_run_charts`) -- 9 per-run analytics PNGs (call counts, retry rates, entropy, token budgets, latency); token-gated charts skipped when the provider reports no token counts (e.g. Claude/Gemini CLI)
  - `console_report.py` (`print_metrics`) -- Renders the per-run summary table to the console
- **`cross_run/`** -- cross-run pipeline (load -> test -> build -> visualize):
  - `comparison_loader.py` -- Discovers and loads the per-run `run_analytics.json` files to compare
  - `comparison_stats.py` -- Statistical tests: Kruskal-Wallis H + inline Dunn post-hoc (Holm-corrected, no external dep)
  - `run_comparison.py` (`build_comparison`, `METRIC_SPECS`, `decompose_slug`) -- Cross-run statistics: groups runs by model and strategy (country fixed) and assembles the comparison
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
- **Local file caching** -- PxWeb clients cache API responses as JSON files in `config/database/caches/{scb,ssb}/` to avoid redundant API calls
- **Full comparison output** -- When comparing pipeline output against a reference (database) population, every output artifact must be generated: a bar chart for each of the 15 demographic attributes in `DEMOGRAPHIC_ATTRIBUTES` (age_group, biological_sex, education_level, employment_status, birth_location, socioeconomic_class, parental_structure, region, civil_status, industry_sector, employment_type, housing_tenure, household_size, income_source, birth_country_detail), a radar chart with TV-similarity across all attributes, the JSON comparison report (marginals + joint chi-squared + coherence), and the CSV marginals summary. Charts are only skipped when an attribute has zero data in both populations -- if the reference population provides the field, the chart must appear

## Axis Composition System

Identity generation can be configured via three orthogonal axes instead of a monolithic manifest. `compose_manifest` in `src/population_synth/identity/manifest_loader.py` merges YAML from four layers:

1. `config/synthetic/experiment_defaults.yaml` -- base parameters (mode, output_base, parallel settings)
2. `config/synthetic/axes/models/{model_id}.yaml` -- provider, model name, API key env var
3. `config/synthetic/axes/strategies/{strategy_id}.yaml` -- generation strategy (all_pick, all_generate_pick, etc.)
4. `config/synthetic/axes/countries/{country_id}.yaml` -- country-specific simulation config and reference population

Each strategy yaml is the **single source of truth** for that strategy: it carries `id`, `label`, `description`, and the full per-category `categories` DAG (`method` + `depends_on`) inline -- the generator's `_load_strategy` reads `categories` straight from this file (there is no separate `strategy_defs/` json). Yamls whose filename starts with `_` (e.g. `_debug_minimal.yaml`, `_compared_only_generate_evaluate_random_pick.yaml`) are co-located strategy definitions that are usable via an explicit `--strategy <path>` but are **not** selectable axis options -- `discover_axis_values` skips them. The diagram coordinates that used to sit beside each strategy json now live under `config/gui/layouts/{strategy_id}.layout.json`.

The output slug is `{country_id}_{strategy_id}_{model_id}`, and the run directory is `{output_base}/01_Raw/{slug}/`. Use `--model-id`, `--strategy-id`, `--country-id` CLI flags instead of `--manifest` to invoke this path.

## Configuration

- **Seed manifests:** `config/synthetic/manifests/` -- YAML files that bundle all identity generation settings (provider, model, mode, config, strategy, parallel params) into a single file. Loaded via `--manifest` flag. CLI args override manifest values when both are provided.
- **Simulation configs:** `config/synthetic/simulation_configs/` -- per-attribute `categories` schema + locale `instruction` system prompt for configurable mode. Strategy definitions are single-file yamls under `config/synthetic/axes/strategies/` (see Axis Composition System above).
- **SCB API cache:** `config/database/caches/scb/` (git-ignored)
- **SSB API cache:** `config/database/caches/ssb/` (git-ignored)
- **Eurostat API cache:** `config/database/caches/eurostat/` (git-ignored)
- **ISTAT API cache:** `config/database/caches/istat/` (git-ignored)
- **Category label mappings:** `config/mapping/{scb,istat}/` -- the unified symmetric comparison config: one JSON file per comparison attribute (filename stem == top-level key) declaring `values`/`database`/`synthetic`, plus an `_index.json` master (`attribute -> filename` in axis order + `joint_pairs`/`coherence_attributes`). The loader (`load_mappings`/`load_index` in `comparison/reference_mapper/mappings.py`; `comparison/normalizer.py` re-exports `load_mappings`) merges every `*.json` in a country directory into a single dict keyed by stem (it also still accepts a single monolithic file). Both mapper sides and the comparison scheme are driven entirely by this config -- see the shared resolver `comparison/mapping_engine.py` and each dir's `README.md`. (`config/mapping/ssb/` is legacy Norway config, not wired into the comparison scheme mechanism.)
- **Axis configs:** `config/synthetic/axes/models/`, `config/synthetic/axes/strategies/`, `config/synthetic/axes/countries/` -- YAML files composable via `--model-id`, `--strategy-id`, `--country-id`. A country YAML is minimal (`id`, `label`, `parameters.config` pointing at a simulation config JSON). `swedish` -> `simulation_config_004_swedish_generative.json`, `italian` -> `simulation_config_005_italian_generative.json`; each simulation config carries a locale-specific `instruction` system prompt and per-attribute `categories`
- **Experiment defaults:** `config/synthetic/experiment_defaults.yaml` -- base parameters including `output_base` path
- **Run-analytics defaults:** `config/analysis/analyze_defaults.yaml` -- `output_base` plus the `analytics` output layout used by `analyze_run.py` / `compare_runs.py`: per-run analytics land in `{output_base}/03_Analysis/llm_metrics/{slug}/` and cross-run comparison in `.../llm_metrics/_comparison/`
- **GUI launcher config:** `config/gui/launcher.yaml` -- action groups and parameter definitions for the PyQt5 launcher

## Debugging Identity Generation Failures

### Locating the run output directory

Run output does **not** live in the repo `data/` folder -- it lives under the `output_base` defined in `config/synthetic/experiment_defaults.yaml` (currently `F:/liu-onedrive-nospecial-carac/_Teams/Gauss/02_Data`). When asked to debug a run described by model + country + strategy (e.g. "the lucie 7b, swedish, all pick" run), reconstruct the path from the axis config files instead of searching `data/`:

- **Axis-composed runs** (`--model-id` / `--strategy-id` / `--country-id`): the slug is `{country_id}_{strategy_id}_{model_id}` and the run dir is `{output_base}/01_Raw/{slug}` (comparison output at `{output_base}/03_Analysis/{slug}`). See `compose_manifest` in `src/population_synth/identity/manifest_loader.py`. The axis IDs are the YAML filenames (without extension) under `config/synthetic/axes/models/`, `config/synthetic/axes/strategies/`, and `config/synthetic/axes/countries/` -- e.g. model `ollama_lucie_7b` + strategy `all_pick` + country `swedish` resolves to `{output_base}/01_Raw/swedish_all_pick_ollama_lucie_7b/`.
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
