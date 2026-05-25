# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**population-synth** is a standalone extraction from the `anxiety-synthetic` monorepo. It provides three capabilities:

1. **Population Generation** -- Fetch real Nordic demographic distributions (SCB for Sweden, SSB for Norway) and sample statistically realistic population profiles via conditional chained sampling
2. **Identity Generation** -- LLM-based persona identity creation using Gemini models with strategy modes (batch, configurable)
3. **Population Comparison** -- Statistical evaluation and visual comparison between any two population files

## Commands

Requires Python 3.10+.

```bash
# Install (editable mode, required for imports to work)
pip install -e .

# Install with dev tools
pip install -e ".[dev]"

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

# Extract demographic profiles from a pipeline output tree into a single population file
python scripts/extract_population_from_pipeline.py --seed-root path/to/pipeline_output/ \
    --output pipeline_population.json

# Linting
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

### Four Sub-packages

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

**`comparison/`** -- Statistical evaluation and charting:
- `StatisticalEvaluator` computes per-field chi-squared tests and total variation distances
- `normalizer` converts raw API output format to canonical schema for comparison
- `charts` generates bar-chart and radar-chart PNGs via matplotlib
- `extractor` pulls demographic fields from pipeline `identity.json` files

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
- **Live API data only** -- All distributions come from live API calls; no static data is ever substituted. If no table exists for a field, the field is dropped
- **Local file caching** -- PxWeb clients cache API responses as JSON files in `config/assets/{scb,ssb}_cache/` to avoid redundant API calls

## Configuration

- **Seed manifests:** `config/seed_manifests/` -- YAML files that bundle all identity generation settings (provider, model, mode, config, strategy, parallel params) into a single file. Loaded via `--manifest` flag. CLI args override manifest values when both are provided.
- **Identity prompts and simulation configs:** `config/assets/identity/` (batch and configurable sub-directories)
- **SCB API cache:** `config/assets/scb_cache/` (git-ignored)
- **SSB API cache:** `config/assets/ssb_cache/` (git-ignored)
- **Eurostat API cache:** `config/assets/eurostat_cache/` (git-ignored)
- **ISTAT API cache:** `config/assets/istat_cache/` (git-ignored)
- **Category label mappings:** `config/assets/scb_reference/category_mappings.json` and `config/assets/ssb_reference/category_mappings.json`

## Reference Documentation

The `docs/` directory holds design and audit notes worth consulting before non-trivial changes:
- `scb_population_and_comparison.md` -- end-to-end SCB pipeline and comparison design
- `scb_population_distribution_analysis.md` (+ `_verification.md`) -- per-field distribution analysis
- `audit_scb_comparison_api_rooting_2026-05-11.md` -- audit of comparison-vs-API field routing
- `scb02_comparison_category_mapping_2026-05-11.md` -- category-mapping rationale
- `docs/development/` -- in-progress development notes

## Environment & Secrets

- `GEMINI_API_KEY` environment variable required for identity generation with `--provider gemini` (raises `ValueError` if missing)
- `--provider claude` requires the `claude` CLI on PATH; raises `RuntimeError` at construction if not found; no extra API key needed (Claude Code manages its own auth)
- Population generation (SCB/SSB scripts) does not require any API keys
