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

  Under `configurable`, generation is a small domain object graph rather than one class. Each
  object states what it must **not** know, and those exclusions are the contract:

  | Module | Responsibility | Must NOT know about |
  |--------|----------------|---------------------|
  | `identity_generator_configurable.py` -- `IdentityGeneratorConfigurable`, `Blueprint` | Loads + validates the strategy YAML and flat schema, builds the dependency DAG (Kahn, ties in YAML declaration order), constructs one `Category` per attribute, owns the client. `build_blueprint()` / `build_population()` are the **only** places config is interpreted. | Per-category prompt construction |
  | `synthetic_population.py` -- `SyntheticPopulation`, `ResumePlan` | The run's `n` persona slots and which of them still need work: `plan(force=...)` partitions `range(n)` into pending / already complete / resumable, `persona(i)` and `writer(i)` hand out the objects that fill a slot | **Threading**, prompts, LLM methods, file formats |
  | `persona.py` -- `Persona` | Walks its categories in DAG order, renders the context block each one sees, accumulates values, checkpoints after every category | Paths, slugs, `output_base`, serialization format |
  | `category.py` -- `Category` ABC + `PickCategory`, `GeneratePickCategory`, `GenerateEvaluatePickCategory`, `GenerateEvaluateRandomPickCategory` | Resolve **one** attribute via **one** generation method; `_METHOD_MAP` + `build_categories()` reject an unimplemented `method` before the first LLM call | Paths, persona dirs, file IO, other categories, the resolved dict |
  | `resolution_context.py` -- `ResolutionContext` | One JSON-constrained LLM call: retry budget, the `(persona_id, call_index)` correlation counter, telemetry emission | Category semantics, what prompts mean, output paths |
  | `persona_writer.py` -- `PersonaWriter`, `ResumeState` | Every file of **one** persona -- `identity.json`, `identity.partial.json`, `llm_interactions.jsonl` -- and their shared lifecycle | Strategies, methods, prompts, the DAG, other personas |
  | `run_fingerprint.py` -- `build_run_fingerprint` | Reduces the generation regime (strategy + schema bytes, `provider:model`, category order) to a dict the writer only ever compares for equality | Personas, files, the walk |

  `SyntheticPopulation` is deliberately **passive**: it starts nothing and calls no client. The
  parallel runner keeps its `ThreadPoolExecutor` and its one-client-plus-one-generator-per-worker
  allocation, which is what keeps the correlation counter and the client's connection state
  per-persona by construction. Nothing here is memoised across threads -- `writer(i)` returns a fresh
  object per call, and the resume verdict is memoised on that per-persona writer.

  Generation is **crash-safe and resumable**; the protocol, the shared-lifecycle invariant, and why
  there is no signal handler are in
  [Aborted and resumed runs](../development/aborted-and-resumed-runs.md).

**`analysis/`** -- The post-generation analysis family, one subpackage per process
(`validate_raw/`, `mapping/`, `validate_mapped/`, `population_cap/`, `fidelity/`,
`multivariate_fidelity/`, `model_ranking/`, `method_significance/`, `real_population_stats/`,
`generation_metadata/`, plus a shared `utils/`). The DAG is a **validation gate**:
`validate_raw` (root) -> `mapping` -> `validate_mapped` -> `population_cap` -> the mapped-file
consumers + `generation_metadata`:

- **`validate_raw/`** -- The analysis-DAG **root**, a non-destructive validation gate. It
  atomistically checks each combo's `01_Raw/{slug}/persona_*` and writes one CSV per combo
  (`{output_base}/03_Analysis/validate_raw/{slug}.csv`, columns
  `persona_id,passed,has_identity_json,n_expected_keys,missing_categories`): a persona passes only if
  it has an `identity.json` and every config-derived category is populated (expected keys = the
  country mapping `_index.json` attributes **minus** its `deprecated_attributes`, with the
  `age_group`->`age` alias). `n_expected_keys` accompanies every rate so completeness is never
  compared across different requirements. It copies/mutates nothing.
- **`mapping/`** -- Transforms raw population data (national-statistics records *or* LLM-pipeline
  identities) into the canonical comparable schema. Reads the **full `01_Raw` pool** (not the capped
  mirror) and maps every valid persona to `{output_base}/03_Analysis/mapping/{slug}.json` (plus
  `real_{country}.json` and `_index.json`); each mapped individual carries an `id` equal to its source
  `persona_XXXXX` dir name. Holds the shared resolver `mapping_engine.py`, `flatten_raw.py`, the
  `real_mapper/` and `synthetic_mapper/` class hierarchies, and the thin `extractor.py` /
  `normalizer.py` facades. The **unified symmetric mapping config** and the real/synthetic mapper
  hierarchies are documented on their own page — see [Comparison & mapping](comparison-mapping.md).
- **`validate_mapped/`** -- A second non-destructive validation gate. It atomistically checks each
  mapped `{slug}.json` and writes one CSV per combo
  (`{output_base}/03_Analysis/validate_mapped/{slug}.csv`, columns
  `persona_id,passed,unmapped_fields`), flagging any field left as the `__UNMAPPED__` sentinel.
- **`population_cap/`** -- Runs **last** in the validation gate (after `mapping` and
  `validate_mapped`). `cap_combo` intersects the two per-combo validity CSVs (`validate_raw` +
  `validate_mapped`) down to the clean persona ids, seeded-selects exactly `--n` of them (shared draw
  `utils/sampling.select_indices`), and materializes **two** outputs: (1) the capped persona-dir mirror
  at `{output_base}/03_Analysis/population_cap/{slug}/` — combo telemetry (`logs/` /
  `run_metadata.json` / `manifest_snapshot.yaml`), consumed **only** by `generation_metadata` via
  `utils/capped_source.resolve_stage_source` — and (2) the capped mapped dir
  `{output_base}/03_Analysis/population_cap/_mapped/` holding the capped subset `{slug}.json`, the
  copied `real_{country}.json`, and `_index.json`, read by every mapped-file consumer (`fidelity`,
  `multivariate_fidelity`, `model_ranking`, `method_significance`, `real_population_stats`,
  `persona_realism`, `consistency`, `pairwise_comparison`) via
  `utils/capped_source.resolve_mapped_dir(output_base)`. Both resolvers **raise `FileNotFoundError`
  when their source is absent — there is no fallback** (`generation_metadata` never falls back to
  `01_Raw`; the mapped-file consumers never fall back to `mapping/`), so no downstream task can analyze
  more than N personas. When fewer than N clean personas exist, `cap_combo` cap-shorts with a loud
  warning (a visible, clean shortfall); it never fails the batch.
- **`fidelity/`** -- Statistical evaluation and charting (population quality vs the real population):
  - `StatisticalEvaluator` (`evaluator.py`) computes per-field chi-squared tests and total variation distances
  - `charts` generates bar-chart and radar-chart PNGs via matplotlib
  - `scheme.py` -- the comparison-purpose bridge that reads the mapping config
- **`multivariate_fidelity/`** -- Standalone multivariate fidelity (sits after the cap stage; driven by
  `score_multivariate_fidelity.py`, depends on `population_cap`, reading the capped `_mapped/` files).
  Recomputes the same `multivariate` block the comparison evaluator produces -- via the shared
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
  report discovery via the capped `_mapped/_index.json`), `builder.py` (`build_performance_comparison` +
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
- **`real_population_stats/`** -- Standalone real-only reference statistics (sits after the cap
  stage; driven by `analyze_real_population_stats.py`, depends on `population_cap`, reading the capped
  `_mapped/` files). For a single real
  population it computes per-category counts/N/proportion/percent (`stats.py::compute_category_stats`,
  built on the shared `utils/marginals.py::compute_proportions`) and renders one publication-styled
  bar figure per analyzed attribute (`charts.py::plot_category_bars`, y fixed [0, 100]%, dashed
  25/50/75/100% reference lines, on-bar percent labels) plus a combined multi-panel overview
  (`plot_overview_panel`), writing PNG + SVG + a raw proportion CSV (`csv_writer.py`) per attribute
  under `03_Analysis/real_population_stats/{country}/`. No synthetic population, comparison, or
  fidelity metric is involved -- `artifacts.py::write_real_population_stats` is the orchestrator that
  ties computation, rendering, and I/O together, idempotent unless `--force`.
- **`persona_realism/`** -- The LLM-as-judge task, **strictly per-combination** (driven by
  `analyze_persona_realism.py`, `per_combo` dispatch). `config.py` holds `JudgeConfig` (loadable
  without the LLM client layer, `reliability_value()` reads fail-fast with no in-code default);
  `runner.py` fans out the resumable per-persona judge calls; `reduce.py` reduces round → persona →
  combination; `stats.py` computes that combination's **own** impossibility rate (bootstrap CI),
  typicality dispersion and judge self-reliability — it takes **no reference combination** and emits
  no field that depends on one; `charts.py` renders the two per-combination figures; `csv_writer.py`
  and `report.py` are the flat sinks; `artifacts.py` orchestrates and also writes
  `{combo}_personas.csv`, the tidy inter-task contract. The real API-sourced population is
  enumerated as an **ordinary competitor** `real_{country}` (same code path, differing only in its
  `real_sample_size` first-N prefix draw). Judging one combination requires no other, so its output
  is byte-reproducible in isolation and independent of processing order — the property that makes
  `03_Analysis/persona_realism/{country}/` contain combination directories and nothing else.
- **`realism_ranking/`** -- The cross-combination half (driven by `rank_persona_realism.py`,
  `slugs` dispatch, `depends_on: [persona_realism]`). `loader.py` discovers the consumption set
  through the registry and enforces two gates before any statistic: **completeness** (report +
  per-persona CSV + a row count matching `n_personas`) and **homogeneity** (one `judge_model` /
  `prompt_template_sha256` / `n_rounds` across the set — ranking units judged by different judges
  measures the judges). `builder.py` computes Axis A (impossibility ranking with seeded bootstrap
  CIs, Holm-corrected contrasts against the real population with effect sizes) and Axis B
  (typicality-dispersion distance + Levene, with the real population as the **target**), plus
  Kruskal–Wallis + Dunn/Holm on the model and method factors (real competitor held out) and a logit
  mixed model on `can_exist`; `charts.py` renders the re-anchored headline map and the impossibility
  forest. It performs **no LLM work** — re-running it is free and touches no verdict cache.
- **`utils/`** -- cross-process shared infra:
  - `realism_csv.py` -- the per-persona tidy schema shared by the two persona-realism tasks
    (writer used by the producer, reader by the consumer, one definition). Keeps *absent* distinct
    from *zero* (a persona with no typicality reads back `None`, never `0.0`), round-trips counts as
    `int`, and validates on read: a missing column, an unparseable count, or a row count disagreeing
    with the report's `n_personas` raises, naming the file.
  - `registry.py` -- the **analysis registry** accessor: loads/validates
    `config/analysis/analysis_registry.yaml` (the single source of truth mapping each process's
    canonical id → label/description/folder/script/dispatch) and exposes `AnalysisProcess`,
    `get_process`, `analysis_output_dir(id, base, *, for_read=False)` (the `mapped/`→`mapping/`
    legacy read-fallback lives here), `resolve_output_base`, and `ANALYSIS_STAGE_DIR` (the sole
    `"03_Analysis"` literal in code). Consumed by both the analysis scripts and the GUI workflow model.
  - `country_config.py` -- the shared country resolver (`real_for_country`, `mappings_for_country`,
    `known_country_ids`, `infer_country`) consumed by both the map stage and the comparison consumers
  - `axes.py` -- axis-vocabulary helpers: `decompose_slug` / `diagnose_slug` (slug -> axis IDs) plus
    the strategy-axis ordering accessors. Ordering is **config-derived and exposed as functions**, not
    as a module constant (the former `STRATEGY_COMPLEXITY_ORDER` list is gone), so nothing is read at
    import time and every caller resolves the order for the ids it actually has:
    `load_family_order()` reads the simplest-first family ranks from
    `config/synthetic/axes/strategies/_families.yaml`; `strategy_versions(ids)` maps each id to its
    declared integer `version` (**ordering metadata only** -- no analysis process branches on it, a
    versioned id is simply its own strategy); `strategy_complexity_order(ids)` returns them sorted by
    the total key `(family_rank, version, id)`, which is what keeps each v2 immediately after its v1
    sibling. All three fail loudly -- unknown id, missing/malformed
    `family`/`version`, or an undeclared family raises; nothing "sorts unknown last"
  - `_stats.py` -- stdlib numeric primitives (median, percentile, Shannon entropy); no external dep
  - `stats_tests.py` -- Kruskal-Wallis H + inline Dunn post-hoc (Holm-corrected) for generation_metadata /
    model_ranking, plus the repeated-measures family for `method_significance` (Friedman +
    Iman-Davenport + Kendall's W, Page's L trend, Nemenyi post-hoc + CD, Benjamini-Hochberg FDR,
    Cliff's δ, and the logit-linked `MixedLM` interaction fit); carries the scipy/numpy surface and
    lazily imports statsmodels + scikit-posthocs (the `[analysis]` extra) for the library-backed ones
- **`generation_metadata/`** -- the single LLM-metrics task; detailed below.

**`gui/`** -- the **sole** GUI: a config-driven PyQt5 "Flow Runner" (`python -m population_synthetic.gui.main`). `FlowRunnerWindow` is driven by a two-tier editable-YAML config (`config/gui/menu.yaml` catalogue + one round-trip YAML per flow under `config/gui/flows/`), translates flow YAML into CLI invocations of the existing scripts, and adds a DAG-based Analysis Workflow. The runner and widget substrate is self-contained inside the package (`execution.py` holds `CombinationRunner` + `_kill_process_tree`; `widgets/` holds `ConsoleWidget`, `DagGraphWidget`, `CheckableAxisList`, `PersonaCountWorker`) -- the deprecated v1 launcher it superseded has been removed. Full contracts in [gui Flow Runner](../development/gui.md).

**`analysis/generation_metadata/`** -- The **single LLM-metrics task** (LLM call behaviour, distinct from `analysis/fidelity/` which scores population quality). Named for its output subdir `03_Analysis/generation_metadata/`. A pipe-and-filter stage driven by `summarize_generation_metadata.py`: it reads the capped persona-dir mirror telemetry (`population_cap/{slug}/`, via `capped_source.resolve_stage_source`) for every combo, reduces each persona to a metric record, aggregates per-combo distribution + scalar stats, runs one deep per-combo diagnostics pass, computes per-country cross-factor significance, and emits **one** per-country CSV + JSON + `charts/`. Public entrypoint `summarize()` in `__init__.py`. Numeric primitives and hypothesis tests live in the cross-process `analysis/utils/` (`_stats.py` / `stats_tests.py`).

- `pricing.py` -- parse/validate `config/analysis/model_pricing.yaml` (fail-fast cost model)
- `interaction_parser.py` / `log_parser.py` -- Parse `llm_interactions.{jsonl,json}` and `logs/run_*.log` (call lines + run summary) from run output
- `joiner.py` -- Enriches JSONL interaction records by matching to log-file call records via timestamp proximity (±2s). Note: parallel runs write a single top-level master log (`01_Raw/{slug}/logs/`), not per-persona logs; joining that master log populates token/latency fields. The ±2s join means per-persona token sums are approximate in parallel runs, but aggregate/per-category distributions are sound
- `persona_metrics.py` -- reduce one persona's normalized call entries to a per-persona record
- `cost.py` -- per-persona USD cost from the pricing table (fail-fast; `None` when no token telemetry)
- `diagnostics.py` (`compute_metrics`) -- deep per-combo diagnostics: call counts, retry rates, token consumption/budget, latency percentiles, prompt-size growth, value diversity (Shannon entropy), error taxonomy
- `combo_aggregator.py` (`aggregate_combo`, `ComboSummary`, `METRIC_NAMES`) -- per-metric distribution stats (mean/std/median/q1/q3/n) + combo-level scalars (latency p95/max, success_rate) + the per-persona sample lists reused by the significance path
- `comparison.py` (`build_summary_comparison`, `significance_from_comparison`) -- in-memory cross-factor comparison over the country's `list[ComboSummary]`: groups pooled per-persona samples by model and by method (country fixed), runs Kruskal-Wallis + Dunn/Holm per factor, derives compact-letter-display group labels (tests from `analysis/utils/stats_tests.py`)
- `report_writer.py` -- serialise a country's combo summaries to CSV (scalars + group-label columns) + JSON (scalars + per-combo `diagnostics` + per-country `significance`)
- `charts.py` (`render_metric_heatmaps`, `plot_run_charts`, `plot_run_comparison`) -- per-metric mean-heatmaps, per-combo diagnostic charts, and cross-factor comparison charts (box plots with significance brackets, mean±SD bars, model×method heatmaps); all persisted PNG+SVG via `save_figure`; token-gated charts skipped when the provider reports no token counts (e.g. Claude/Gemini CLI)
- `console.py` (`print_metrics`) -- renders a combo's deep diagnostics table to the console for `--verbose`

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
