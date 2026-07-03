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

# Compare two population files
python scripts/analyze/compare_populations.py pop_a.json pop_b.json

# Map stage: map the targeted synthetic populations + their real populations to the canonical schema
# (reads config/analysis/comparison_targets.yaml; writes {output_base}/03_Analysis/mapped/).
# Run this BEFORE any compare command -- the compare scripts consume these pre-mapped files.
python scripts/analyze/map_populations.py
python scripts/analyze/map_populations.py --targets config/analysis/comparison_targets.yaml

# Compare pipeline output against the SCB real population (consumes pre-mapped files; via manifest)
python scripts/analyze/compare_pipeline_to_scb.py --manifest config/synthetic/manifests/identity_manifest_022_claude_sonnet.yaml

# Compare pipeline output against the SCB real population (explicit mapped-file paths)
python scripts/analyze/compare_pipeline_to_scb.py \
    --mapped-synthetic {output_base}/03_Analysis/mapped/<slug>.json \
    --mapped-real {output_base}/03_Analysis/mapped/real_swedish.json

# Compare pipeline output against the ISTAT real population (Italy; consumes pre-mapped files)
python scripts/analyze/compare_pipeline_to_istat.py --model-id claude_haiku --strategy-id all_pick --country-id italian

# Compare every mapped target against country real populations (batch; iterates mapped/_index.json)
python scripts/analyze/compare_all_pipelines.py --country swedish --country italian

# Cross-model performance comparison: rank model x strategy combos per country against the real
# baseline (consumes the comparison reports; run compare_all_pipelines.py first)
python scripts/analyze/compare_model_performance.py --country swedish --per-attribute-charts

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

# Launch the primary GUI: the config-driven Flow Runner (requires pip install -e ".[gui]")
python -m population_synthetic.gui_v2.main
# (deprecated fallback: python -m population_synthetic.gui.main)

# Linting (line-length 120, rules: E/F/W/I)
ruff check src/
```

A pytest suite lives under `tests/` (covers the `analysis/llm_metrics/` layer and `clients/call_context`).
Run it with `pytest` (requires `pip install -e ".[dev]"`).

## See also

- [Axis composition](axis-composition.md) — how `--model-id` / `--strategy-id` / `--country-id`
  compose a run and where its output lands.
- [Configuration](configuration.md) — the config files the commands above read.
- [`../development/debugging-identity-generation.md`](../development/debugging-identity-generation.md)
  — what to inspect when a generation command fails.
