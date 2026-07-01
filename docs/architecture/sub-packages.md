# Sub-packages

> **Architecture wiki:** [Home](README.md) · **Sub-packages** ·
> [Comparison & mapping](comparison-mapping.md) · [Design principles](design-principles.md) ·
> [Axis composition](axis-composition.md) · [Configuration](configuration.md) · [Commands](commands.md)

The full per-package breakdown of `src/population_synth/`. This is the reference companion to
the short architecture map in `CLAUDE.md`.

## Sub-packages (`src/population_synth/`)

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
- **Unified symmetric mapping config** and the reference/synthetic mapper hierarchies are
  documented on their own page — see [Comparison & mapping](comparison-mapping.md).

**`gui/`** -- PyQt5 desktop launcher for running generation and comparison tasks. `LauncherWindow` presents action groups (Generate, Compare) defined in `config/gui/launcher.yaml`. Axis selection uses checkbox lists (`CheckableAxisList` x3 inside `ExperimentSelector`) rather than dropdowns, so a single launch runs the full **cartesian product** of selected models x strategies x countries -- `ExperimentSelection.combinations()` enumerates the tuples via `itertools.product`, `ManifestOverview` previews them in a table, and `CombinationRunner` (QThread) runs each as a `--model-id/--strategy-id/--country-id` subprocess with live console streaming and process-tree abort. Selections persist to `config/gui/state.json`.

**`llm_metrics/`** -- Post-processing analytics for identity generation runs (LLM call behaviour, distinct from `comparison/` which scores population quality). Named for its output subdir `03_Analysis/llm_metrics/`. Organised as a **two-level pipeline** split across three subpackages: `per_run/` (pipeline A, driven by `analyze_run.py`) turns one run into per-persona analytics + a report; `cross_run/` (pipeline B, driven by `compare_runs.py`) consumes many runs' analytics and produces a cross-run comparison; `shared/` holds the numeric primitives both pipelines use. `per_run/` and `cross_run/` never import each other -- only through `shared/`.

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

## Path Resolution

`_paths.py` provides a single `PROJECT_ROOT` constant:
```python
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # src/population_synth/ -> population-synth/
```
All cache and config paths derive from this.

## See also

- [Comparison & mapping](comparison-mapping.md) — the `comparison/` mapping config and the
  reference/synthetic mapper hierarchies in full.
- [Design principles](design-principles.md) — the patterns (shared population layer,
  factory + strategy, conditional chained sampling) that shape these packages.
- [Configuration](configuration.md) — the config files these packages read.
