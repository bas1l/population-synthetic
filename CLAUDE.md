# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository. It is a lean **hub**: the always-needed guardrails and quick-start live here; the
depth lives in the [architecture wiki](docs/architecture/README.md).

## Project Overview

**population-synthetic** is a standalone extraction from the `anxiety-synthetic` monorepo. It provides three capabilities:

1. **Population Generation** -- Fetch real demographic distributions from national statistical APIs (SCB for Sweden, SSB for Norway, ISTAT/Eurostat for Italy) and sample statistically realistic population profiles via conditional chained sampling
2. **Identity Generation** -- LLM-based persona identity creation using Gemini models with configurable strategy mode
3. **Population Comparison** -- Statistical evaluation and visual comparison between any two population files

## Quick Start

Requires Python 3.10+. Install in editable mode (required for imports to work):

```bash
pip install -e ".[dev]"          # editable install + dev tools; add ".[gui]" for the PyQt5 launcher

# Generate a Swedish population from live SCB data
python scripts/generate/generate_scb_population.py --n 1000 --seed 42 --output scb_pop.json

# Generate identities via axis composition (model × strategy × country)
python scripts/generate/generate_identities_parallel.py --model-id claude_sonnet --strategy-id all_pick --country-id swedish

# Comparison is two-stage: MAP first, then COMPARE (compare consumes the pre-mapped files)
python scripts/analyze/map_populations.py
python scripts/analyze/compare_pipeline_to_scb.py --manifest config/synthetic/manifests/identity_manifest_022_claude_sonnet.yaml

python -m population_synthetic.gui.main   # GUI launcher (requires ".[gui]")
ruff check src/                       # lint (line-length 120, rules E/F/W/I)
pytest                                # test suite (covers llm_metrics/ and clients/call_context)
```

**Full command catalog → [Command reference](docs/architecture/commands.md)** (`docs/architecture/commands.md`).

## Import Convention

The project uses `src/` layout. The `pyproject.toml` configures `setuptools` to find packages under `src/`, so after `pip install -e .`, the `population_synthetic` namespace is available:

```python
from population_synthetic.population.sweden.fetch_service import FetchService
from population_synthetic.clients.scb_client import SCBPxWebClient
from population_synthetic.identity.factory_identity_generator import FactoryIdentityGenerator
```

All imports use the fully-qualified `population_synthetic.*` package namespace. Scripts in `scripts/` depend on the editable install.

## Core Invariants (hard rules)

These are enforced guardrails, not suggestions. Full rationale in
[Design principles](docs/architecture/design-principles.md) (`docs/architecture/design-principles.md`).

- **No synthetic distributions** -- Every probability distribution in population generation must come from a real statistical API response; no hardcoded probability tables, fallback distributions, or parametric approximations. If no API provides a field, **drop it** -- never invent values. (Structural constants like dataset IDs and label maps are fine.)
- **Config is the single source of truth** -- Attribute lists / axis order / category values / matcher rules / joint-coherence pairs / sex-harmonization maps live **only** in config (`config/mapping/{scb,istat}/`, `config/analysis/comparison/*.json`). No in-code `attr or DEFAULT` fallback. Missing/empty/malformed config **fails loudly** (raise) -- never silently reverts to a baked-in list.
- **Full comparison output** -- A reference comparison emits every artifact: a bar chart for each of the 15 `DEMOGRAPHIC_ATTRIBUTES`, the TV-similarity radar, the JSON report (marginals + joint chi-squared + coherence), and the CSV marginals. Skip a chart only when the attribute has zero data in **both** populations.
- **Fail-fast** -- Raise loudly on unexpected or malformed input rather than silently defaulting.

## Architecture

`src/` layout; the `population_synthetic` namespace holds sub-packages `population/` (per-country
data layers over a shared parent), `identity/` (LLM persona generation), `analysis/` (the
post-generation family, one subpackage per process: `mapping/` raw -> canonical schema,
`comparison/` two-stage map -> compare statistical scoring + charts, `llm_metrics/` post-run
LLM-call analytics, and `utils/` cross-process shared infra), plus `gui/`, `clients/`, and a
top-level `utils/`. The full breakdown and the design patterns live in the wiki:

| Topic | Page |
|-------|------|
| Per-package breakdown + path resolution | [Sub-packages](docs/architecture/sub-packages.md) |
| Two-stage map -> compare flow + mapping config + mapper hierarchies | [Comparison & mapping](docs/architecture/comparison-mapping.md) |
| Design patterns + hard-rule rationale | [Design principles](docs/architecture/design-principles.md) |
| Axis composition (model × strategy × country) | [Axis composition](docs/architecture/axis-composition.md) |
| `config/` inventory | [Configuration](docs/architecture/configuration.md) |
| Command catalog | [Commands](docs/architecture/commands.md) |
| Wiki home / index | [Architecture home](docs/architecture/README.md) |

## Environment & Secrets

- `GEMINI_API_KEY` environment variable required for identity generation with `--provider gemini` (raises `ValueError` if missing)
- `--provider claude` requires the `claude` CLI on PATH; raises `RuntimeError` at construction if not found; no extra API key needed (Claude Code manages its own auth)
- Population generation (SCB/SSB scripts) does not require any API keys

## Documentation

Design and audit notes worth consulting before non-trivial changes:

| Doc | What it covers |
|-----|----------------|
| [Architecture wiki](docs/architecture/README.md) | **Start here** — the architecture wiki (sub-packages, comparison/mapping, design principles, axis composition, config, commands). |
| [Debugging identity generation](docs/development/debugging-identity-generation.md) | Runbook for diagnosing a failed persona generation (locating run dirs, reading crash-surviving logs). |
| [SCB population & comparison](docs/scb_population_and_comparison.md) | End-to-end SCB pipeline and comparison design. |
| [Database mapper philosophy](docs/database_mapper_philosophy.md) | *Why* the reference mapper exists and the principle governing it. |
| [SCB distribution analysis](docs/scb_population_distribution_analysis.md) (+ [verification](docs/scb_population_distribution_analysis_verification.md)) | Per-field distribution analysis. |
| [SCB comparison API-rooting audit](docs/audit_scb_comparison_api_rooting_2026-05-11.md) | Audit of comparison-vs-API field routing. |
| [SCB02 category-mapping rationale](docs/scb02_comparison_category_mapping_2026-05-11.md) | Category-mapping rationale. |
| [ISTAT population data sources](docs/istat_population_data_sources.md) | Italy field-by-field API source matrix, protocol details, sampling chain, known limitations. |
| [Code standards](docs/code-standards/README.md) · [Data-pipeline engineering](docs/data-pipeline-engineering/README.md) | Repository-agnostic engineering-standards wiki sets. |
| [Development notes](docs/development/) | In-progress development notes and plans. |
