# population-synth

Standalone toolkit for generating synthetic population profiles from real Nordic demographic data (SCB/SSB) and LLM-based identity personas.

## Features

- **SCB Population Generation** -- Fetch real Swedish demographic distributions from Statistics Sweden (SCB PxWeb API) and sample statistically realistic population profiles via conditional chained sampling across 15+ demographic tables
- **SSB Population Generation** -- Fetch real Norwegian demographic distributions from Statistics Norway (SSB PxWebApi v2) and sample statistically realistic population profiles via conditional chained sampling across 14+ demographic tables
- **Identity Generation** -- LLM-based persona identity creation using Gemini models, with batch and configurable strategy modes
- **Population Comparison** -- Statistical evaluation (chi-squared, total variation distance) and visual comparison (bar charts, radar plots) between any two population files

## Installation

```bash
cd population-synth
pip install -e .
```

For development tools (ruff linting):

```bash
pip install -e ".[dev]"
```

Requires Python 3.10+.

## Usage

### Generate a Swedish population from SCB data

```bash
python scripts/generate_scb_population.py --n 1000 --seed 42 --output scb_pop.json
```

Fetches live demographic distributions from the SCB PxWeb API, then conditionally samples `n` individuals. Output is a JSON file containing per-individual demographic profiles (age, sex, education, employment, income bracket, housing, civil status, birth country, etc.) plus metadata listing every SCB table queried.

### Generate a Norwegian population from SSB data

```bash
python scripts/generate_ssb_population.py --n 1000 --seed 42 --output ssb_pop.json
```

Same approach using the SSB PxWebApi v2. Output format is identical to the SCB variant.

### Generate a persona identity

```bash
python scripts/generate_identity.py \
    --mode configurable \
    --config config/assets/identity/configurable/simulation_config_004_swedish_generative.json \
    --output identity.json \
    --model gemini-2.5-flash
```

Modes:
- `batch` -- Single-prompt narrative-style generation
- `configurable` -- Strategy-driven generation controlled by a simulation config file

Requires the `GEMINI_API_KEY` environment variable.

### Compare two populations

```bash
python scripts/compare_populations.py pop_a.json pop_b.json --output report.json
```

Produces a JSON report with per-field chi-squared tests, total variation distances, and similarity scores. Optionally generates bar-chart and radar-chart PNGs.

### Compare pipeline output against an SCB reference

```bash
python scripts/compare_pipeline_to_scb.py \
    --seed-root path/to/pipeline_output/ \
    --reference scb_population.json \
    --output comparison_report.json
```

Extracts demographic profiles from `persona_*/identity.json` files produced by a generation pipeline and compares them against an SCB reference population.

### Extract population profiles from pipeline output

```bash
python scripts/extract_population_from_pipeline.py \
    --seed-root path/to/pipeline_output/ \
    --output pipeline_population.json
```

## Environment

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | For identity generation | Google Gemini API key |

Population generation (SCB/SSB) does not require any API keys -- the PxWeb APIs are public.

## Architecture

```
src/population_synth/
    population/           Shared population layer
        data.py           PopulationDistributions dataclass
        helpers.py        age_to_group, sample_from, normalize, VALID_AGE_GROUPS, AGE_GROUP_BOUNDS
        income_class.py   Income bracket classification (Eurostat AROP / OECD thresholds)
        sweden/           SCB-specific constants, fetch service, parsers, sample service
        norway/           SSB-specific constants, fetch service, parsers, sample service

    identity/             LLM-based persona identity generation
        base_identity_generator.py      Abstract base class
        identity_generator_batch.py
        identity_generator_configurable.py
        factory_identity_generator.py   Factory for selecting strategy at runtime

    comparison/           Statistical evaluation and charting
        evaluator.py      StatisticalEvaluator (chi-squared, TV distance)
        normalizer.py     Schema normalization (raw -> canonical field names)
        charts.py         Bar-chart and radar-chart generation
        extractor.py      Extract demographics from identity.json files

    clients/              API clients
        pxweb_client.py   BasePxWebClient (shared HTTP + caching base)
        scb_client.py     SCBPxWebClient (Statistics Sweden)
        ssb_client.py     SSBPxWebClient (Statistics Norway)
        gemini_client.py  Gemini API wrapper
        gemini_config.py  Model configuration loader
```

The `population/` layer breaks the cross-dependency between Sweden and Norway modules. Both `sweden/` and `norway/` import shared code from their parent `population/` package -- never from each other.

## Configuration

- **Identity prompts and simulation configs:** `config/assets/identity/`
- **SCB API response cache:** `config/assets/scb_cache/` (git-ignored JSON files)
- **SSB API response cache:** `config/assets/ssb_cache/` (git-ignored JSON files)
- **Category label mappings:** `config/assets/scb_reference/category_mappings.json` and `config/assets/ssb_reference/category_mappings.json`

## Data Sources

All demographic distributions are fetched from live public APIs at generation time -- no static data is substituted.

- **SCB PxWeb API** -- https://www.scb.se/en/services/open-data-api/api-for-the-statistical-database/
- **SSB PxWebApi v2** -- https://data.ssb.no/api/v0/en/

## License

TBD
