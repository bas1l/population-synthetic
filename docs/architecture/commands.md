# Command Reference

> **Architecture wiki:** [Home](README.md) · [Sub-packages](sub-packages.md) ·
> [Comparison & mapping](comparison-mapping.md) · [Design principles](design-principles.md) ·
> [Axis composition](axis-composition.md) · [Configuration](configuration.md) · **Commands**

The full command catalog for population-synthetic. Requires Python 3.10+. `CLAUDE.md` keeps only
the most-used subset; this page is the exhaustive list.

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

# Generate a persona identity via explicit CLI args (OpenRouter, requires OPENROUTER_API_KEY)
python scripts/generate/generate_identity.py --provider openrouter --model openai/gpt-4o --mode configurable \
    --config config/synthetic/simulation_configs/simulation_config_004_swedish_generative.json

# Compare two population files
python scripts/analyze/score_fidelity.py pop_a.json pop_b.json

# Cap stage (pipeline ROOT): seeded per-combo cap of a combination's generated personas to N.
# Copies the selected persona_* dirs (plus combo logs/metadata) into the canonical capped mirror
# at {output_base}/03_Analysis/population_cap/{slug}/. mapping and generation_metadata read this
# mirror instead of 01_Raw and fail loudly if it is absent (no 01_Raw fallback), so run this FIRST.
# --n is required (raises if missing); --sample-seed defaults to 0 (0 is a valid seed); --force
# overwrites an existing mirror; --output-base defaults to experiment_defaults.yaml.
python scripts/analyze/cap_populations.py --model-id claude_haiku --strategy-id all_pick --country-id swedish --n 100
python scripts/analyze/cap_populations.py --model-id claude_haiku --strategy-id all_pick --country-id swedish \
    --n 100 --sample-seed 7 --force --output-base {output_base}

# Map stage: map the targeted synthetic populations + their real populations to the canonical schema
# (reads config/analysis/comparison_targets.yaml; writes {output_base}/03_Analysis/mapping/ -- folder
# name owned by the analysis registry; legacy on-disk mapped/ is still read as a fallback). Personas are
# read from the capped mirror (03_Analysis/population_cap/{slug}/), never 01_Raw -- run cap_populations.py first.
# Run this BEFORE any compare command -- the compare scripts consume these pre-mapped files.
python scripts/analyze/map_populations.py
python scripts/analyze/map_populations.py --targets config/analysis/comparison_targets.yaml

# Compare pipeline output against the SCB real population (consumes pre-mapped files; via manifest)
python scripts/analyze/score_fidelity_sweden.py --manifest config/synthetic/manifests/identity_manifest_022_claude_sonnet.yaml

# Compare pipeline output against the SCB real population (explicit mapped-file paths)
python scripts/analyze/score_fidelity_sweden.py \
    --mapped-synthetic {output_base}/03_Analysis/mapping/<slug>.json \
    --mapped-real {output_base}/03_Analysis/mapping/real_swedish.json

# Compare pipeline output against the ISTAT real population (Italy; consumes pre-mapped files)
python scripts/analyze/score_fidelity_italy.py --model-id claude_haiku --strategy-id all_pick --country-id italian

# Compare every mapped target against country real populations (batch; iterates mapping/_index.json)
python scripts/analyze/score_fidelity_all.py --country swedish --country italian

# ... with every synthetic population capped to an equivalent size (seeded without-replacement draw;
# blank/omitted --n-synthetic = no cap; undersize populations run in full with a loud warning)
python scripts/analyze/score_fidelity_all.py --country swedish --n-synthetic 100 --sample-seed 0

# Cross-model performance comparison: rank model x strategy combos per country against the real
# baseline (consumes the comparison reports; run score_fidelity_all.py first). Emits, under
# 03_Analysis/model_ranking/, the {country}_performance.json/.csv, the heatmap/leaderboard/
# c2st charts, and two manuscript heatmap-tables (PNG + SVG each): {country}_models_table
# (models at the global-best strategy, hosted/local hue) and {country}_methods_table (strategies,
# mean-over-models TV-similarity).
python scripts/analyze/rank_models.py --country swedish --per-attribute-charts

# Per-category method/model significance: which factor (generation method vs model) drives
# per-attribute TV fidelity (Page's L + Friedman/Nemenyi CD + mixed-model interaction; consumes the
# comparison reports; needs the [analysis] extra: pip install -e .[analysis]). Also emits, per
# country under 03_Analysis/method_significance/, the method-comparison results table
# ({country}_method_comparison.json/.csv: per-category + Overall Friedman omnibus & Nemenyi pairwise
# p, models as blocks) and the significance-bracket figures ({country}_method_comparison.png/.svg
# grid + {country}_method_comparison_overall.png/.svg): bars + model points + pairwise brackets/stars.
python scripts/analyze/analyze_method_significance.py --country swedish

# Extract demographic profiles from a pipeline output tree into a single population file
python scripts/generate/extract_population_from_pipeline.py --seed-root path/to/pipeline_output/ \
    --output pipeline_population.json

# Generate identities via axis composition (model × strategy × country)
python scripts/generate/generate_identities_parallel.py --model-id claude_sonnet --strategy-id all_pick --country-id swedish

# Generate Italian identities via axis composition
python scripts/generate/generate_identities_parallel.py --model-id claude_sonnet --strategy-id all_pick --country-id italian

# Real-population reference statistics: publication-ready per-category bar figures
# (PNG + SVG) + proportion CSVs for the real (API-sourced) reference population only
# (no synthetic comparison), plus a combined overview panel; one run per country.
python scripts/analyze/analyze_real_population_stats.py --country-id swedish
python scripts/analyze/analyze_real_population_stats.py --country-id swedish --country-id italian --force

# Generation metadata: the single LLM-metrics task. Per country × model × method(strategy),
# the mean/spread(median/q1/q3)/n of the per-persona generation cost (wall-clock time,
# input/output/total tokens, LLM calls, retry & error rates, latency p95/max, success rate,
# estimated USD cost from config/analysis/model_pricing.yaml), plus per-combo deep diagnostics
# and per-country cross-factor significance (Kruskal-Wallis + Dunn/Holm across the model and
# method factors). Reads the LLM-call telemetry from the capped mirror (03_Analysis/population_cap/,
# produced by cap_populations.py -- fail-fast if absent, no 01_Raw fallback); emits ONE per-country
# CSV + JSON + charts.
python scripts/analyze/summarize_generation_metadata.py --country swedish
python scripts/analyze/summarize_generation_metadata.py --model claude_haiku --no-charts --force
# --verbose prints per-combo deep diagnostics; --metrics limits the comparison to a metric subset
python scripts/analyze/summarize_generation_metadata.py --country swedish --verbose --metrics time cost

# Persona realism judge (LLM-as-judge): judge each mapped persona's internal coherence with the
# Claude CLI (default claude-sonnet-5; Fable is the slowest/most-expensive selectable option) over N
# cold rounds -- can_exist (binary) + typicality (0-10) +
# severity-tagged clash issues -- and rank every combination PLUS the SCB real reference on a per-
# combination impossibility rate (bootstrap CI) x typicality-dispersion-vs-SCB (Levene), with an
# ICC/alpha judge self-consistency metric. Two-stage: run map_populations.py first (depends_on:
# [mapping]; reads the mapped populations). Config-driven judge model/params in
# config/analysis/persona_realism/; cost priced via config/analysis/model_pricing.yaml. Filters are
# repeatable; run once with broad filters (CLI batch) to put every combo on one headline map -- the
# GUI per_combo dispatch judges ONE combo per node run.
python scripts/analyze/analyze_persona_realism.py --country swedish
python scripts/analyze/analyze_persona_realism.py --slug swedish_all_pick_claude_sonnet --sample 200 --force
# --rounds overrides the judge rounds per persona (default 3); --judge-model picks a model_options
# entry; --workers sets the fan-out width; --output-base/--dpi as usual
python scripts/analyze/analyze_persona_realism.py --country swedish --rounds 5 --judge-model claude-sonnet-5 --workers 8

# Launch the GUI: the config-driven Flow Runner (requires pip install -e ".[gui]")
python -m population_synthetic.gui.main

# Linting (line-length 120, rules: E/F/W/I)
ruff check src/
```

A pytest suite lives under `tests/` (covers the `analysis/generation_metadata/` layer and `clients/call_context`).
Run it with `pytest` (requires `pip install -e ".[dev]"`).

## Developer tools

Standalone helpers under `tools/` (self-contained, not part of the analysis pipeline):

| Tool | What it does | Entry point |
|------|--------------|-------------|
| `graph-diff` | Renders the change in a package's import/dependency graph between two git refs — added edges green, removed red, unchanged grey — as SVG/PNG/DOT + JSON/MD. Repo-agnostic; needs the Graphviz `dot` binary for SVG/PNG. See [`tools/graph-diff/README.md`](../../tools/graph-diff/README.md). | `python tools/graph-diff/graph_diff.py --package-path src/population_synthetic --base-ref dev` |

## Analysis registry (canonical id → label → folder → script)

`config/analysis/analysis_registry.yaml` (accessor `analysis/utils/registry.py`) is the single
source of truth for every analysis process. Each process's **canonical id** is simultaneously the
registry key, the GUI workflow task key, and the `03_Analysis/<folder>/` output-folder name; scripts
resolve their output dir via `analysis_output_dir(id, output_base)` rather than hardcoding paths.

| Canonical id (= GUI task key = folder) | Label | Output folder (under `03_Analysis/`) | Script | Dispatch |
|---|---|---|---|---|
| `population_cap` | Cap Population (N) | `population_cap/` | `cap_populations.py` | per_combo |
| `mapping` | Map Populations | `mapping/` (legacy read: `mapped/`) | `map_populations.py` | per_combo |
| `fidelity` | Compare Synthetic to Real | `fidelity/` | `score_fidelity_all.py` | slugs |
| `multivariate_fidelity` | Multivariate Joint Fidelity | `multivariate_fidelity/` | `score_multivariate_fidelity.py` | slugs |
| `consistency` | Consistency Scan (unrealistic combos) | `consistency/` | `scan_consistency.py` | slugs |
| `model_ranking` | Model Performance (models × methods) | `model_ranking/` | `rank_models.py` | slugs |
| `method_significance` | Method Significance (per-category) | `method_significance/` | `analyze_method_significance.py` | slugs |
| `pairwise_comparison` | Compare Two Populations | `pairwise_comparison/` | `score_fidelity.py` | slugs |
| `cross_country` | Cross-Country (real vs real) | `cross_country/` | `compare_real_countries.py` | cli (CLI-only) |
| `real_population_stats` | Real Reference Population Stats | `real_population_stats/{country}/` | `analyze_real_population_stats.py` | per_country |
| `generation_metadata` | Generation Metadata (country × model × method) | `generation_metadata/` | `summarize_generation_metadata.py` | slugs |
| `persona_realism` | Persona Realism Judge (LLM-as-judge) | `persona_realism/` | `analyze_persona_realism.py` | per_combo |
| `realism_ranking` | Realism Ranking (combinations vs the real population) | `realism_ranking/` | `rank_persona_realism.py` | slugs |

### Persona realism: two tasks, one seam

`persona_realism` is **strictly per-combination**: judging one combination reads no other, and its
artifacts are byte-reproducible in isolation. It writes `{combo}.json`, `{combo}.csv`, the two
figures, and `{combo}_personas.csv` — the per-persona tidy CSV that is the inter-task contract
(schema in `analysis/utils/realism_csv.py`). The real API-sourced population is enumerated as an
**ordinary competitor** `real_{country}`, not as a reference.

`realism_ranking` consumes those files and owns every cross-combination claim. It performs **no LLM
work**, so it is free to re-run. Two axes, opposite in direction: Axis A ranks impossibility rate
with the real population as an ordinary ranked competitor (lower is better, for everyone); Axis B
contrasts typicality dispersion against the real population **as the target** (distance near zero is
better — the failure mode being guarded against is mode collapse).

```bash
python scripts/analyze/analyze_persona_realism.py --slug swedish_02_all_pick_v2_claude_haiku
python scripts/analyze/analyze_persona_realism.py --rewrite-artifacts   # rebuild artifacts, 0 LLM calls
python scripts/analyze/rank_persona_realism.py --country swedish_02
```

`--rewrite-artifacts` regenerates the derived files from the verdict cache already on disk. It is
the supported way to refresh artifacts after an output-schema change; **`--force` is not** — that
truncates every verdict cache and re-judges from scratch, at full LLM cost.

## See also

- [Axis composition](axis-composition.md) — how `--model-id` / `--strategy-id` / `--country-id`
  compose a run and where its output lands.
- [Configuration](configuration.md) — the config files the commands above read.
- [`../development/debugging-identity-generation.md`](../development/debugging-identity-generation.md)
  — what to inspect when a generation command fails.
