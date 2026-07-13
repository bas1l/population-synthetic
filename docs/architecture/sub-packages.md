# Sub-packages

> **Architecture wiki:** [Home](README.md) · **Sub-packages** ·
> [Comparison & mapping](comparison-mapping.md) · [Design principles](design-principles.md) ·
> [Axis composition](axis-composition.md) · [Configuration](configuration.md) · [Commands](commands.md)

The full per-package breakdown of `src/population_synthetic/`. This is the reference companion to
the short architecture map in `CLAUDE.md`.

## Sub-packages (`src/population_synthetic/`)

**`generators/`** -- The two data producers, grouped under one parent (this is where cohorts
are created). Its two sub-packages are the real side and the synthetic side of the
comparison that `analysis/` performs, mirroring `analysis/mapping/`'s `real_mapper/` vs
`synthetic_mapper/` split.

**`generators/real/`** (formerly `population/`, then `reference/`) -- Shared population layer with country-specific sub-modules:
- `data.py` -- `PopulationDistributions` dataclass (shared by both countries)
- `helpers.py` -- Shared utilities: `age_to_group`, `sample_from`, `normalize`, `VALID_AGE_GROUPS`, `AGE_GROUP_BOUNDS`
- `income_class.py` -- Income bracket classification using Eurostat AROP (0.60x median) and OECD/Pew (1.00x, 2.00x) thresholds
- `sweden/` -- SCB-specific: constants (table IDs, label maps), fetch service, parsers, sample service
- `norway/` -- SSB-specific: constants (table IDs, label maps), fetch service, parsers, sample service
- `italy/` -- ISTAT/Eurostat-specific: constants (dataflow IDs, NUTS2 codes, label maps), parsers (SDMX + JSON-stat), fetch service (dual-client `load_all`), sample service

**`generators/synthetic/`** (formerly `identity/`) -- LLM-based persona identity generation:
- Factory + Strategy pattern: `FactoryIdentityGenerator` selects the generation strategy at runtime
- Base class defines the generation interface; each strategy implements `generate_identity()`
- Mode semantics:
  - `configurable` -- strategy-driven generation controlled by a simulation config JSON file with pluggable strategy definitions

**`analysis/`** -- The post-generation analysis family, one subpackage per process
(`mapping/`, `fidelity/`, `multivariate_fidelity/`, `model_ranking/`, `run_analytics/`, plus a shared `utils/`):

- **`mapping/`** -- Transforms raw population data (national-statistics records *or* LLM-pipeline
  identities) into the canonical comparable schema. Holds the shared resolver `mapping_engine.py`,
  `flatten_raw.py`, the `real_mapper/` and `synthetic_mapper/` class hierarchies, and the thin
  `extractor.py` / `normalizer.py` facades. The **unified symmetric mapping config** and the
  real/synthetic mapper hierarchies are documented on their own page — see
  [Comparison & mapping](comparison-mapping.md).
- **`fidelity/`** -- Statistical evaluation and charting (population quality vs the real population):
  - `StatisticalEvaluator` (`evaluator.py`) computes per-field chi-squared tests and total variation distances
  - `charts` generates bar-chart and radar-chart PNGs via matplotlib
  - `scheme.py` -- the comparison-purpose bridge that reads the mapping config
- **`multivariate_fidelity/`** -- Standalone multivariate fidelity (sits after the map stage; driven by
  `score_multivariate_fidelity.py`, depends only on `map_populations`). Recomputes the same
  `multivariate` block the comparison evaluator produces -- via the shared
  `StatisticalEvaluator.compute_multivariate()` over the mapped populations -- and persists it to its
  own `{output_base}/03_Analysis/multivariate_fidelity/` folder (per-combo envelope JSON + association CSV +
  `|ΔV|` heatmap, plus a per-country roll-up JSON/CSV and a cross-combo C2ST-vs-grounded-TV scatter).
  `builder.py` (`build_multivariate_fidelity` envelope + `aggregate_multivariate_fidelity` roll-up + JSON/CSV writers),
  `charts.py` (thin orchestration reusing `fidelity.charts.plot_association_heatmap` + a self-contained
  scatter). Additive: it never touches the comparison, performance, or paper outputs.
- **`model_ranking/`** -- Cross-model performance comparison (sits after the compare stage; driven by
  `rank_models.py`). Consumes the per-combo comparison reports and ranks the
  model × strategy combos against each other per country -- per attribute (TV-similarity) and
  overall -- with Kruskal-Wallis + Dunn/Holm factor tests. `loader.py` (`ComboPerformance` DTO +
  report discovery via `mapped/_index.json`), `builder.py` (`build_performance_comparison` +
  JSON/CSV writers), `charts.py` (heatmap, leaderboard, per-attribute bars). Never recomputes
  from populations.
- **`utils/`** -- cross-process shared infra:
  - `country_config.py` -- the shared country resolver (`real_for_country`, `mappings_for_country`,
    `known_country_ids`, `infer_country`) consumed by both the map stage and the comparison consumers
  - `axes.py` -- axis-vocabulary helpers: `decompose_slug` / `diagnose_slug` (slug -> axis IDs) and
    `STRATEGY_COMPLEXITY_ORDER` (strategy chart ordering)
  - `_stats.py` -- stdlib numeric primitives (median, percentile, Shannon entropy); no external dep
  - `stats_tests.py` -- Kruskal-Wallis H + inline Dunn post-hoc (Holm-corrected); carries the
    scipy/numpy dependency surface, shared by the run_analytics cross-run and model_ranking processes
- **`run_analytics/`** -- post-run LLM-call analytics; detailed below.

**`gui/`** -- the **sole** GUI: a config-driven PyQt5 "Flow Runner" (`python -m population_synthetic.gui.main`). `FlowRunnerWindow` is driven by a two-tier editable-YAML config (`config/gui/menu.yaml` catalogue + one round-trip YAML per flow under `config/gui/flows/`), translates flow YAML into CLI invocations of the existing scripts, and adds a DAG-based Analysis Workflow. The runner and widget substrate is self-contained inside the package (`execution.py` holds `CombinationRunner` + `_kill_process_tree`; `widgets/` holds `ConsoleWidget`, `DagGraphWidget`, `CheckableAxisList`, `PersonaCountWorker`) -- the deprecated v1 launcher it superseded has been removed. Full contracts in [gui Flow Runner](../development/gui.md).

**`analysis/run_analytics/`** -- Post-processing analytics for identity generation runs (LLM call behaviour, distinct from `analysis/fidelity/` which scores population quality). Named for its output subdir `03_Analysis/run_analytics/`. Organised as a **two-level pipeline** split across two subpackages: `per_run/` (pipeline A, driven by `analyze_run.py`) turns one run into per-persona analytics + a report; `cross_run/` (pipeline B, driven by `compare_run_analytics.py`) consumes many runs' analytics and produces a cross-run comparison. The numeric primitives and hypothesis tests both levels use live in the cross-process `analysis/utils/` (`_stats.py` / `stats_tests.py`). `per_run/` and `cross_run/` never import each other -- only through `analysis/utils`.

- **`per_run/`** -- single-run pipeline (parse -> join -> aggregate -> visualize/report):
  - `interaction_parser.py` / `log_parser.py` -- Parse `llm_interactions.jsonl` and log files from run output
  - `joiner.py` -- Enriches JSONL interaction records by matching to log-file call records via timestamp proximity (±2s). Note: parallel runs write a single top-level master log (`01_Raw/{slug}/logs/`), not per-persona logs; `analyze_run.py` joins that master log so token/latency fields populate. The ±2s join means per-persona token sums are approximate in parallel runs, but aggregate/per-category distributions are sound
  - `aggregator.py` -- Computes per-persona metrics: call counts, retry rates, token consumption, latency percentiles, prompt size growth, value diversity (Shannon entropy)
  - `charts.py` (`plot_run_charts`) -- 9 per-run analytics PNGs (call counts, retry rates, entropy, token budgets, latency); token-gated charts skipped when the provider reports no token counts (e.g. Claude/Gemini CLI)
  - `console_report.py` (`print_metrics`) -- Renders the per-run summary table to the console
- **`cross_run/`** -- cross-run pipeline (load -> test -> build -> visualize):
  - `comparison_loader.py` -- Discovers and loads the per-run `run_analytics.json` files to compare
  - `run_comparison.py` (`build_comparison`, `METRIC_SPECS`) -- Cross-run statistics: groups runs by model and strategy (country fixed) and assembles the comparison (tests from `analysis/utils/stats_tests.py`)
  - `comparison_charts.py` (`plot_run_comparison`) -- Box plots (with significance brackets), mean±SD bars, and model×method heatmaps per metric

**`utils/`** (top-level) -- Minimal pipeline utilities (`should_process_task()` for skip-if-done logic). Distinct from `analysis/utils/`, which holds the cross-process analysis infra (country resolver, axis helpers, numeric primitives, hypothesis tests).

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
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # src/population_synthetic/ -> population-synthetic/
```
All cache and config paths derive from this.

## See also

- [Comparison & mapping](comparison-mapping.md) — the `analysis/mapping/` config and the
  real/synthetic mapper hierarchies in full.
- [Design principles](design-principles.md) — the patterns (shared population layer,
  factory + strategy, conditional chained sampling) that shape these packages.
- [Configuration](configuration.md) — the config files these packages read.
