# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository. It is a lean **hub**: the always-needed guardrails and quick-start live here; the
depth lives in the [architecture wiki](docs/architecture/README.md).

## Project Overview

**population-synthetic** is a standalone extraction from the `anxiety-synthetic` monorepo. It provides three capabilities:

1. **Population Generation** -- Fetch real demographic distributions from national statistical APIs (SCB for Sweden, SSB for Norway, ISTAT/Eurostat for Italy) and sample statistically realistic population profiles via conditional chained sampling
2. **Identity Generation** -- LLM-based persona identity creation via pluggable providers (Gemini, Claude CLI, OpenRouter) with configurable strategy mode
3. **Population Comparison** -- Statistical evaluation and visual comparison between any two population files

## Quick Start

Requires Python 3.10+. Install in editable mode (required for imports to work):

```bash
pip install -e ".[dev]"          # editable install + dev tools; add ".[gui]" for the PyQt5 Flow Runner GUI
pip install -e ".[analysis]"     # optional: scikit-learn backend for the C2ST multivariate metric (MMD fallback otherwise)

# Generate a Swedish population from live SCB data
python scripts/generate/generate_scb_population.py --n 1000 --seed 42 --output scb_pop.json

# Generate identities via axis composition (model × strategy × country)
python scripts/generate/generate_identities_parallel.py --model-id claude_sonnet --strategy-id all_pick --country-id swedish

# Fidelity scoring is two-stage: MAP first, then SCORE (scoring consumes the pre-mapped files)
python scripts/analyze/map_populations.py
python scripts/analyze/score_fidelity_sweden.py --manifest config/synthetic/manifests/identity_manifest_022_claude_sonnet.yaml

python -m population_synthetic.gui.main   # GUI: config-driven Flow Runner (requires ".[gui]")
ruff check src/                       # lint (line-length 120, rules E/F/W/I)
pytest                                # full suite (sampling, mapping, fidelity, multivariate, comparison, workflow, generation_metadata)
pytest tests/test_sampling.py::test_name   # run a single test (testpaths=tests/ is set in pyproject.toml)
```

**Full command catalog → [Command reference](docs/architecture/commands.md)** (`docs/architecture/commands.md`).

## Import Convention

The project uses `src/` layout. The `pyproject.toml` configures `setuptools` to find packages under `src/`, so after `pip install -e .`, the `population_synthetic` namespace is available:

```python
from population_synthetic.generators.real.sweden.fetch_service import FetchService
from population_synthetic.clients.scb_client import SCBPxWebClient
from population_synthetic.generators.synthetic.factory_identity_generator import FactoryIdentityGenerator
```

All imports use the fully-qualified `population_synthetic.*` package namespace. Scripts in `scripts/` depend on the editable install.

## Core Invariants (hard rules)

These are enforced guardrails, not suggestions. Full rationale in
[Design principles](docs/architecture/design-principles.md) (`docs/architecture/design-principles.md`).

- **No synthetic distributions** -- Every probability distribution in population generation must come from a real statistical API response; no hardcoded probability tables, fallback distributions, or parametric approximations. If no API provides a field, **drop it** -- never invent values. (Structural constants like dataset IDs and label maps are fine.)
- **Config is the single source of truth** -- Attribute lists / axis order / category values / matcher rules / joint-coherence pairs / sex-harmonization maps live **only** in config (`config/mapping/{scb,istat}/`, `config/analysis/fidelity/*.json`). No in-code `attr or DEFAULT` fallback. Missing/empty/malformed config **fails loudly** (raise) -- never silently reverts to a baked-in list.
- **Full comparison output** -- A real-population comparison emits every artifact for each analyzed axis (`ComparisonScheme.attributes`): a bar chart per attribute, the TV-similarity radar, the JSON report (marginals + joint chi-squared + coherence), and the CSV marginals. Skip a chart only when the attribute has zero data in **both** populations. The analyzed axis is config-driven, not a fixed 15: a name listed under `deprecated_attributes` in a mapping tier's `_index.json` is still mapped/emitted into population data but excluded from analysis (Sweden deprecates `birth_location`, so it analyzes 14 axes; other countries keep their full axis set).
- **Fail-fast** -- Raise loudly on unexpected or malformed input rather than silently defaulting.

## Architecture

`src/` layout; the `population_synthetic` namespace holds the two data producers under
`generators/` -- `generators/real/` (per-country data layers over a shared parent) and
`generators/synthetic/` (LLM persona generation) -- plus `analysis/` (the
post-generation family, one subpackage per process: `population_cap/` the pipeline **root** —
seeded per-combo cap of each combination's generated personas to `--n`, copying the selected
`persona_*` dirs (plus combo logs/metadata) into a layout-identical capped mirror at
`03_Analysis/population_cap/{slug}/`; every raw-persona consumer (mapping, generation_metadata)
reads that mirror instead of `01_Raw` and **fails loudly (`FileNotFoundError`) if it is absent —
no `01_Raw` fallback**, `mapping/` raw -> canonical schema
(two tiers, selected per country by the axis YAML `parameters.mappings`: a **native**
within-country high-fidelity tier — `config/mapping/scb_native`, the default for Sweden —
and a coarser, cross-country **global** tier — `config/mapping/scb` — whose collapse is
deferred/design-only; see [Comparison & mapping](docs/architecture/comparison-mapping.md)),
`fidelity/` two-stage map -> score statistical scoring + charts (synthetic vs real), `multivariate_fidelity/` standalone
multivariate fidelity (recomputes the `multivariate` block over the mapped populations into
its own `03_Analysis/multivariate_fidelity/` folder), `model_ranking/` cross-model
ranking of the fidelity reports (models × strategies per country), `method_significance/`
per-category significance of the generation method vs model on TV fidelity (Page's L / Friedman /
Nemenyi CD + a mixed-model interaction, categories as blocks; needs the `[analysis]` extra),
`real_population_stats/` publication-ready per-category reference figures + proportion CSVs for the
real (API-sourced) population only, one country at a time, `generation_metadata/` the single
LLM-metrics task — per country × model × method(strategy) mean/spread(median/q1/q3)/n of the
per-persona generation cost (wall-clock time, input/output/total tokens, LLM calls, retry & error
rates, latency p95/max, success rate, estimated USD cost from `config/analysis/model_pricing.yaml`)
plus per-combo deep diagnostics and per-country cross-factor significance (Kruskal-Wallis + Dunn/Holm
across the model and method factors), read from the LLM-call telemetry of the **capped mirror**
(`03_Analysis/population_cap/`, produced by `population_cap`), not `01_Raw` directly,
and `utils/` cross-process shared infra), plus `gui/`, `clients/`, and a
top-level `utils/`. The full breakdown and the design patterns live in the wiki:

**Analysis registry (single source of truth for the analysis layer):**
`config/analysis/analysis_registry.yaml` (+ its accessor `analysis/utils/registry.py`) maps each
analysis process's **canonical id** → {label, description, output folder, script, dispatch}, and is
consumed by BOTH the GUI workflow and the analysis scripts. The canonical id is simultaneously the
registry key, the GUI workflow task key, and the `03_Analysis/` output-folder name, so those three
can never drift. Scripts resolve their output dir via `analysis_output_dir(id, base)` — no hardcoded
`03_Analysis`/folder literals (the sole `"03_Analysis"` definition lives in `registry.py`). The map
stage folder was renamed `mapped/` → `mapping/`; readers pass `for_read=True` to transparently fall
back to any legacy on-disk `mapped/` (deprecation-logged) until re-mapped. `population_cap` is the
analysis-DAG **root**: `mapping` and `generation_metadata` `depends_on: [population_cap]` and read
its `03_Analysis/population_cap/` capped mirror via `analysis/utils/capped_source.py` (fail-fast, no
`01_Raw` fallback).

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
- `OPENROUTER_API_KEY` environment variable required for identity generation with `--provider openrouter` (raises `ValueError` if missing)
- Population generation (SCB/SSB scripts) does not require any API keys

## Documentation

Design and audit notes worth consulting before non-trivial changes:

| Doc | What it covers |
|-----|----------------|
| [Architecture wiki](docs/architecture/README.md) | **Start here** — the architecture wiki (sub-packages, comparison/mapping, design principles, axis composition, config, commands). |
| [Debugging identity generation](docs/development/debugging-identity-generation.md) | Runbook for diagnosing a failed persona generation (locating run dirs, reading crash-surviving logs). |
| [gui Flow Runner](docs/development/gui.md) | The config-driven `gui` launcher: two-tier config, GUI-translates-YAML→CLI execution contract, and the workflow DAG chaining contract. |
| [SCB population & comparison](docs/scb_population_and_comparison.md) | End-to-end SCB pipeline and comparison design. |
| [Real mapper philosophy](docs/real_mapper_philosophy.md) | *Why* the real mapper exists and the principle governing it. |
| [SCB distribution analysis](docs/scb_population_distribution_analysis.md) (+ [verification](docs/scb_population_distribution_analysis_verification.md)) | Per-field distribution analysis. |
| [SCB comparison API-rooting audit](docs/audit_scb_comparison_api_rooting_2026-05-11.md) | Audit of comparison-vs-API field routing. |
| [SCB02 category-mapping rationale](docs/scb02_comparison_category_mapping_2026-05-11.md) | Category-mapping rationale. |
| [ISTAT population data sources](docs/istat_population_data_sources.md) | Italy field-by-field API source matrix, protocol details, sampling chain, known limitations. |
| [Code standards](docs/code-standards/README.md) · [Data-pipeline engineering](docs/data-pipeline-engineering/README.md) | Repository-agnostic engineering-standards wiki sets. |
| [Development notes](docs/development/) | In-progress development notes and plans. |
