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
(`mapping/`, `fidelity/`, `multivariate_fidelity/`, `model_ranking/`, `method_significance/`,
`real_population_stats/`, `run_analytics/`, plus a shared `utils/`):

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
  report discovery via `mapping/_index.json`, legacy `mapped/` read-fallback), `builder.py` (`build_performance_comparison` +
  JSON/CSV writers, plus the `methods_matrix` per-strategy × per-attribute block and the
  embedded `metadata.model_hosting`), `charts.py` (heatmap, leaderboard, per-attribute bars),
  `hosting.py` (config-driven provider → `local`/`hosted` classification), and
  `manuscript_tables.py` (two print-oriented, pure-consumer heatmap-tables emitted as PNG + SVG:
  a **models** table at the global-best strategy with hosted/local hue, and a **methods** table
  of mean-over-models TV-similarity per strategy). Never recomputes from populations.
- **`method_significance/`** -- Per-category method/model significance (sits after the compare stage;
  driven by `analyze_method_significance.py`). Reuses `model_ranking`'s `loader` to obtain the
  (model × method × category) TV grid and asks, per country and per attribute, *which factor drives
  TV fidelity -- the generation method (ordered strategy) or the model*. The `n = 1`-per-cell wall is
  escaped by treating the demographic categories as the blocking/replication factor (Demšar 2006,
  "classifiers over multiple data sets"): per attribute it runs Page's L (ordered method trend
  + linear/quadratic contrast) and Friedman (model omnibus), BH-FDR corrected across attributes;
  overall it runs the Demšar model comparison (Friedman → Nemenyi → critical-difference diagram),
  a Page's L method trend, and a `logit(TV) ~ model*method + (1|category)` mixed model whose
  interaction term is estimable. The per-category interaction is emitted **descriptively only**
  (a slope heatmap) -- no p-value is claimed at that grain. It also emits a **`method_comparison`**
  block (`builder.py::_method_comparison`, config `config/analysis/method_significance/comparison.json`):
  a head-to-head comparison of the methods on **TV-similarity** with the *models as blocks* -- per
  category (+ a pooled Overall panel) a Friedman omnibus + Nemenyi pairwise post-hoc over the
  complete-case models, BH-FDR corrected across categories. `charts.py::plot_method_comparison` renders
  it as the publication **significance-bracket figure** (bars = per-method mean TV-similarity + model
  points + paired lines, pairwise brackets/stars over the configured pairs, in-figure star key; a
  per-category grid and a standalone Overall panel, PNG + SVG). `builder.py` (`build_method_significance`
  + JSON/CSV writers), `charts.py` (per-attribute trend facets, slope heatmap, CD diagram,
  factor-dominance bar, method-comparison figure). Needs the optional `[analysis]` extra
  (statsmodels + scikit-posthocs).
- **`real_population_stats/`** -- Standalone real-only reference statistics (sits after the map
  stage; driven by `analyze_real_population_stats.py`, depends only on `mapping`). For a single real
  population it computes per-category counts/N/proportion/percent (`stats.py::compute_category_stats`,
  built on the shared `utils/marginals.py::compute_proportions`) and renders one publication-styled
  bar figure per analyzed attribute (`charts.py::plot_category_bars`, y fixed [0, 100]%, dashed
  25/50/75/100% reference lines, on-bar percent labels) plus a combined multi-panel overview
  (`plot_overview_panel`), writing PNG + SVG + a raw proportion CSV (`csv_writer.py`) per attribute
  under `03_Analysis/real_population_stats/{country}/`. No synthetic population, comparison, or
  fidelity metric is involved -- `artifacts.py::write_real_population_stats` is the orchestrator that
  ties computation, rendering, and I/O together, idempotent unless `--force`.
- **`utils/`** -- cross-process shared infra:
  - `registry.py` -- the **analysis registry** accessor: loads/validates
    `config/analysis/analysis_registry.yaml` (the single source of truth mapping each process's
    canonical id → label/description/folder/script/dispatch) and exposes `AnalysisProcess`,
    `get_process`, `analysis_output_dir(id, base, *, for_read=False)` (the `mapped/`→`mapping/`
    legacy read-fallback lives here), `resolve_output_base`, and `ANALYSIS_STAGE_DIR` (the sole
    `"03_Analysis"` literal in code). Consumed by both the analysis scripts and the GUI workflow model.
  - `country_config.py` -- the shared country resolver (`real_for_country`, `mappings_for_country`,
    `known_country_ids`, `infer_country`) consumed by both the map stage and the comparison consumers
  - `axes.py` -- axis-vocabulary helpers: `decompose_slug` / `diagnose_slug` (slug -> axis IDs) and
    `STRATEGY_COMPLEXITY_ORDER` (strategy chart ordering)
  - `_stats.py` -- stdlib numeric primitives (median, percentile, Shannon entropy); no external dep
  - `stats_tests.py` -- Kruskal-Wallis H + inline Dunn post-hoc (Holm-corrected) for run_analytics /
    model_ranking, plus the repeated-measures family for `method_significance` (Friedman +
    Iman-Davenport + Kendall's W, Page's L trend, Nemenyi post-hoc + CD, Benjamini-Hochberg FDR,
    Cliff's δ, and the logit-linked `MixedLM` interaction fit); carries the scipy/numpy surface and
    lazily imports statsmodels + scikit-posthocs (the `[analysis]` extra) for the library-backed ones
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
