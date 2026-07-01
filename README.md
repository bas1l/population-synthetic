# population-synthetic

Standalone toolkit for generating synthetic population profiles from real national demographic data (SCB/SSB/ISTAT) and LLM-based identity personas.

## Features

- **Swedish Population Generation** -- Fetch real demographic distributions from Statistics Sweden (SCB PxWeb API) and sample statistically realistic population profiles via conditional chained sampling across 15+ demographic tables
- **Norwegian Population Generation** -- Fetch real demographic distributions from Statistics Norway (SSB PxWebApi v2) and sample profiles via conditional chained sampling across 14+ demographic tables
- **Italian Population Generation** -- Fetch real demographic distributions from ISTAT (SDMX REST) and Eurostat (JSON-stat 2.0) and sample profiles via the same conditional chained sampling chain
- **Identity Generation** -- LLM-based persona identity creation across multiple providers (Gemini, Claude CLI, Ollama, OpenAI-compatible European providers), with batch and configurable strategy modes, manifest bundles, and composable model x strategy x country axes
- **Population Comparison** -- Statistical evaluation (chi-squared, total variation distance) and visual comparison (bar charts, radar plots) between any two population files, or between pipeline output and a national reference
- **Run Analytics** -- Post-processing analytics on LLM generation runs (call counts, retry rates, token/latency distributions, value diversity) plus cross-run scientific comparison (Kruskal-Wallis + Dunn)
- **GUI Launcher** -- PyQt5 desktop launcher to run generation and comparison tasks across the cartesian product of selected models, strategies, and countries

## Installation

```bash
cd population-synthetic
pip install -e .
```

For development tools (ruff linting, pytest):

```bash
pip install -e ".[dev]"
```

For the PyQt5 GUI launcher:

```bash
pip install -e ".[gui]"
```

Requires Python 3.10+.

## Usage

### Generate a population from national statistics data

```bash
# Sweden (SCB PxWeb API)
python scripts/generate/generate_scb_population.py --n 1000 --seed 42 --output scb_pop.json

# Norway (SSB PxWebApi v2)
python scripts/generate/generate_ssb_population.py --n 1000 --seed 42 --output ssb_pop.json

# Italy (ISTAT SDMX + Eurostat JSON-stat)
python scripts/generate/generate_istat_population.py --n 1000 --seed 42 --output istat_pop.json
```

Each script fetches live demographic distributions from the relevant public API, then conditionally samples `n` individuals. Output is a JSON file containing per-individual demographic profiles (age, sex, education, employment, income bracket, housing, civil status, birth country, etc.) plus metadata listing every table queried. Output format is identical across the three countries.

### Generate a persona identity

Via a manifest (recommended -- bundles provider, model, mode, config, and strategy):

```bash
python scripts/generate/generate_identity.py --manifest config/synthetic/manifests/identity_manifest_014_claude_haiku.yaml
```

Generate N identities in parallel via a manifest:

```bash
python scripts/generate/generate_identities_parallel.py --manifest config/synthetic/manifests/identity_manifest_014_claude_haiku.yaml --n 10 --workers 4
```

Via explicit CLI args:

```bash
# Gemini (requires GEMINI_API_KEY)
python scripts/generate/generate_identity.py --provider gemini --mode configurable \
    --config config/synthetic/simulation_configs/simulation_config_004_swedish_generative.json

# Claude CLI (requires `claude` on PATH; no extra API key)
python scripts/generate/generate_identity.py --provider claude --model sonnet --mode configurable \
    --config config/synthetic/simulation_configs/simulation_config_004_swedish_generative.json
```

Via axis composition (model x strategy x country; see [Axis Composition](#axis-composition)):

```bash
python scripts/generate/generate_identities_parallel.py --model-id claude_sonnet --strategy-id all_pick --country-id swedish
```

Modes:
- `batch` -- single-prompt narrative-style generation
- `configurable` -- strategy-driven generation controlled by a simulation config file

### Compare populations

```bash
# Compare two population files
python scripts/analyze/compare_populations.py pop_a.json pop_b.json --output report.json

# Compare pipeline output against an SCB reference (via manifest)
python scripts/analyze/compare_pipeline_to_scb.py --manifest config/synthetic/manifests/identity_manifest_022_claude_sonnet.yaml

# Compare pipeline output against an SCB reference (via explicit path)
python scripts/analyze/compare_pipeline_to_scb.py --seed-root path/to/pipeline_output/ \
    --reference scb_population.json --output comparison_report.json

# Compare pipeline output against an ISTAT reference (Italy)
python scripts/analyze/compare_pipeline_to_istat.py --model-id claude_haiku --strategy-id all_pick --country-id italian

# Compare every model x strategy x country combination against country references (batch)
python scripts/analyze/compare_all_pipelines.py --country swedish --country italian
```

Comparison produces per-field chi-squared tests, total variation distances, similarity scores, a bar chart per demographic attribute, a radar chart, a JSON report, and a CSV marginals summary.

### Extract population profiles from pipeline output

```bash
python scripts/generate/extract_population_from_pipeline.py \
    --seed-root path/to/pipeline_output/ --output pipeline_population.json
```

### Analyse generation runs

```bash
# Analyse a single run directory (prints summary table)
python scripts/analyze/analyze_run.py path/to/run_dir/

# Analyse a batch run and export full analytics
python scripts/analyze/analyze_run.py path/to/batch_run_dir/ --output run_analytics.json

# Batch-analyse every run under {output_base}/01_Raw/
python scripts/analyze/analyze_run.py --all

# Cross-run scientific comparison of LLM metrics (requires --all first)
python scripts/analyze/compare_runs.py
```

### Launch the GUI

```bash
python -m population_synthetic.gui.main
```

## Environment

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | For `--provider gemini` | Google Gemini API key |

- `--provider claude` requires the `claude` CLI on PATH (no extra API key; Claude Code manages its own auth).
- `--provider ollama` / OpenAI-compatible providers target a configured endpoint (e.g. a self-hosted Ollama server).
- Population generation (SCB/SSB/ISTAT) does not require any API keys -- the statistics APIs are public.

## Architecture

```
src/population_synthetic/
    generators/           Data producers: reference (statistical) + synthetic (LLM)
        reference/        Shared population layer (per-country, over a shared parent)
            data.py           PopulationDistributions dataclass
            helpers.py        age_to_group, sample_from, normalize, VALID_AGE_GROUPS, AGE_GROUP_BOUNDS
            income_class.py   Income bracket classification (Eurostat AROP / OECD thresholds)
            sweden/           SCB-specific constants, fetch service, parsers, sample service
            norway/           SSB-specific constants, fetch service, parsers, sample service
            italy/            ISTAT/Eurostat-specific constants, parsers (SDMX + JSON-stat), fetch service, sample service

        synthetic/        LLM-based persona identity generation
            base_identity_generator.py        Abstract base class
            identity_generator_configurable.py
            factory_identity_generator.py     Factory for selecting strategy at runtime
            manifest_loader.py                Manifest + axis-composition loader
            llm_interaction_log.py            Incremental JSONL interaction logging

    comparison/           Statistical evaluation and charting (population quality vs reference)
        evaluator.py      StatisticalEvaluator (chi-squared, TV distance)
        normalizer.py     Schema normalization (raw -> canonical field names; country-agnostic)
        charts.py         Bar-chart and radar-chart generation
        extractor.py      Extract demographics from identity.json files (country-aware)

    analysis/             Post-processing analytics for generation runs
        shared/           Numeric primitives shared by both pipelines (_stats.py)
        per_run/          Single-run pipeline (parse -> join -> aggregate -> visualize/report)
        cross_run/        Cross-run pipeline (load -> test -> build -> visualize)

    gui/                  PyQt5 desktop launcher (cartesian-product experiment runner)

    utils/                Pipeline utilities (should_process_task skip-if-done logic)

    clients/              API clients
        pxweb_client.py        BasePxWebClient (shared HTTP + caching base)
        scb_client.py          SCBPxWebClient (Statistics Sweden)
        ssb_client.py          SSBPxWebClient (Statistics Norway)
        eurostat_client.py     EurostatClient (Eurostat JSON-stat 2.0)
        istat_client.py        ISTATSDMXClient (ISTAT SDMX REST)
        gemini_client.py       GeminiClient
        claude_code_client.py  ClaudeCodeClient (Claude CLI subprocess)
        ollama_client.py       OllamaClient (self-hosted Ollama)
        openai_compat_client.py OpenAI-compatible client (European providers)
        llm_protocol.py        LLMClient Protocol shared by the LLM clients
```

The `generators/reference/` layer breaks the cross-dependency between country modules. Each country sub-package imports shared code from its parent `generators/reference/` package -- never from another country.

## Axis Composition

Identity generation can be configured via three orthogonal axes instead of a monolithic manifest. `compose_manifest` (`generators/synthetic/manifest_loader.py`) merges YAML from four layers:

1. `config/synthetic/experiment_defaults.yaml` -- base parameters
2. `config/synthetic/axes/models/{model_id}.yaml` -- provider, model name, API key env var
3. `config/synthetic/axes/strategies/{strategy_id}.yaml` -- generation strategy (`all_pick`, `all_generate_pick`, ...); each yaml carries the full `categories` DAG inline (single source of truth, no separate `strategy_defs/` json)
4. `config/synthetic/axes/countries/{country_id}.yaml` -- simulation config and reference population

The output slug is `{country_id}_{strategy_id}_{model_id}`, and the run directory is `{output_base}/01_Raw/{slug}/`. Use `--model-id`, `--strategy-id`, `--country-id` instead of `--manifest` to invoke this path.

## Configuration

- **Seed manifests:** `config/synthetic/manifests/` -- YAML bundles of all identity-generation settings, loaded via `--manifest`
- **Simulation configs:** `config/synthetic/simulation_configs/` (configurable mode); strategy definitions live in `config/synthetic/axes/strategies/`
- **Axis configs:** `config/synthetic/axes/models/`, `config/synthetic/axes/strategies/`, `config/synthetic/axes/countries/`
- **API response caches (git-ignored):** `config/database/caches/scb/`, `config/database/caches/ssb/`, `config/database/caches/eurostat/`, `config/database/caches/istat/`
- **Category label mappings:** `config/mapping/{scb,ssb,istat}/` -- one JSON file per demographic attribute (filename stem == top-level key), grouped by source agency. The loader merges every `*.json` in a country directory into a single dict
- **Experiment / analytics defaults:** `config/synthetic/experiment_defaults.yaml`, `config/analysis/analyze_defaults.yaml`
- **GUI launcher config:** `config/gui/launcher.yaml`

## Data Sources

All demographic distributions are fetched from live public APIs at generation time -- no static data is substituted.

- **SCB PxWeb API** -- https://www.scb.se/en/services/open-data-api/api-for-the-statistical-database/
- **SSB PxWebApi v2** -- https://data.ssb.no/api/v0/en/
- **ISTAT SDMX REST** -- https://esploradati.istat.it/
- **Eurostat JSON-stat 2.0** -- https://ec.europa.eu/eurostat/web/main/data/web-services

## License

TBD
