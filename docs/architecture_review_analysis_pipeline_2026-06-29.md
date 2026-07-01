# Engineering Review — `llm_metrics/` Pipeline (LLM Run Analytics)

**Date:** 2026-06-29 (package renamed `analysis/` → `llm_metrics/` on 2026-07-01)
**Scope:** `src/population_synthetic/llm_metrics/` and its orchestrators (`scripts/analyze/analyze_run.py`,
`scripts/analyze/compare_runs.py`, `config/analyze_defaults.yaml`).
**Type:** Engineering review — code architecture and software design, with concrete findings,
recommendations, and a curated learning list. Not an academic critique.

---

## 1. Executive Summary

The `llm_metrics/` package is the project's **LLM run-behaviour** analytics pipeline. It ingests the
raw artifacts a generation run leaves on disk (`llm_interactions.jsonl` + `logs/run_*.log`), joins
them, aggregates roughly a dozen metric families, renders per-run charts, and runs cross-run
non-parametric statistics (Kruskal–Wallis with Holm-corrected Dunn post-hoc).

> **Distinct from `comparison/`.** The `comparison/` package scores *population quality*
> (how closely generated demographics match an SCB/ISTAT reference). `llm_metrics/` scores *run
> behaviour* (token usage, latency, retry/error rates, value diversity per LLM call category). The
> two pipelines share neither code nor data; this report covers `llm_metrics/` only.

**Overall verdict.** This is a well-structured pipeline. Its core is a chain of small, I/O-free,
single-purpose functions that are individually easy to read and would be trivial to unit-test. The
statistics are rigorous and deliberately dependency-light. Type hints and docstrings are pervasive,
and the one significant accuracy limitation (approximate joins in parallel runs) is documented
honestly in the code rather than hidden.

The gaps are the ones an organically-grown research codebase usually accumulates:

- **No test suite** — the most testable part of the project has zero automated coverage.
- **One oversized function** — `aggregator.compute_metrics` computes every metric family in a single
  ~350-line body.
- **Duplicated numeric helpers** — median and percentile are implemented three separate times.
- **Approximate parallel-run joins** — token/latency data can attach to the wrong persona.

None of these are structural defects; they are maintainability and correctness-assurance debts with
clear, incremental fixes (Section 8).

---

## 2. System Overview & Data Flow

The pipeline is a classic five-stage **batch dataflow**: each stage is a pure-ish function that
consumes the previous stage's output and produces the next stage's input. Two CLI orchestrators
wire the stages together — `analyze_run.py` covers stages 1–4 (per run), `compare_runs.py` covers
stage 5 (across runs).

```
 RAW RUN ARTIFACTS
   llm_interactions.jsonl  (LLMInteractionCollector)
   logs/run_*.log          (Python logging)
          │
          ▼
 STAGE 1 — PARSE
   interaction_parser.parse_interactions(path)  -> list[entry dict]
   log_parser.parse_log_file(path)              -> list[call dict]
   log_parser.parse_run_summary(path)           -> {elapsed_s, success, failed} | None
          │
          ▼
 STAGE 2 — JOIN  (±2 s timestamp proximity, 1-to-1 greedy)
   joiner.join_entries(jsonl_entries, log_entries, tolerance_s=2.0)
       -> list[enriched entry dict]   (+ prompt_tokens, completion_tokens, elapsed_ms)
          │
          ▼
 STAGE 3 — AGGREGATE
   aggregator.compute_metrics(entries, run_summary)
       -> metrics dict  (~12 metric families)
          │
          ├────────────────────────────────────┐
          ▼                                     ▼
 STAGE 4 — CHART (per run)            JSON EXPORT (per run)
   charts.plot_run_charts(metrics)      analyze_run.py -> run_analytics.json
       -> [Path] (up to 9 PNGs)
          │
          ▼
 STAGE 5 — CROSS-RUN COMPARE  (compare_runs.py)
   run_comparison.load_run_records(llm_metrics_root)  -> [RunRecord]
   run_comparison.build_comparison(records)           -> comparison result dict
       (Kruskal–Wallis + Dunn per metric, model×method matrix)
   comparison_charts.plot_run_comparison(result)      -> [Path] (box / bar / heatmap)
```

### Intermediate data structures (the DTOs that flow between stages)

| Structure | Produced by | Shape |
|---|---|---|
| **Normalized entry dict** | `interaction_parser.parse_interactions` | `{category, method, step, prompt, raw_response, parsed_value, error, attempt, timestamp}` — every `LLMInteractionEntry` field guaranteed present via `_FIELD_DEFAULTS`. |
| **Call record dict** | `log_parser.parse_log_file` | `{timestamp, provider, model, elapsed_ms, prompt_tokens, completion_tokens}`. |
| **Enriched entry dict** | `joiner.join_entries` | Normalized entry + `{prompt_tokens, completion_tokens, elapsed_ms}` (or `None` when unmatched). |
| **Metrics dict** | `aggregator.compute_metrics` | Nested dict, ~12 top-level keys (summary, per_category, latency_by_category, value_diversity, token_*…). |
| **`RunRecord`** (dataclass) | `run_comparison.load_run_records` | `{slug, country, strategy, model, has_token_data, samples: dict[str, list[float]]}`. |
| **`MetricSpec`** (frozen dataclass) | static `METRIC_SPECS` | `{key, label, unit, kind, token_gated, cell_agg, higher_is_better}`. |
| **Comparison result dict** | `run_comparison.build_comparison` | `{metadata, metrics[key]: {by_model, by_method, matrix}}`. |

The discipline worth highlighting: stages 1–3 pass plain `dict`/`list` values and touch no global
state, so the entire parse→join→aggregate core can be exercised with in-memory fixtures and no
filesystem.

---

## 3. Module-by-Module Review

| Module | Responsibility | Key public surface | Coupling |
|---|---|---|---|
| `interaction_parser.py` | Parse `llm_interactions.jsonl`/`.json` into normalized entry dicts; locate the file. | `parse_interactions()` (`:72`), `find_interaction_file()` (`:120`) | **Loose** — stdlib only (`json`, `pathlib`). |
| `log_parser.py` | Regex-extract per-call token/latency records and the run summary from `logs/run_*.log`; handles Ollama, OpenAI-compat, Claude line formats. | `parse_log_file()` (`:105`), `parse_run_summary()` (`:148`), `find_log_files()` (`:174`) | **Loose** — stdlib only (`re`, `pathlib`). |
| `joiner.py` | Attach call records to interaction entries by nearest-timestamp within a tolerance window (greedy, 1-to-1). | `join_entries(..., tolerance_s=2.0)` (`:59`) | **Loose** — stdlib only (`datetime`, `re`). |
| `aggregator.py` | Compute every per-run metric family from enriched entries. | `compute_metrics()` (`:164`) plus `_shannon_entropy` (`:106`), `_percentile` (`:95`), `_median` (`:83`) | **Loose** — stdlib only (`json`, `math`, `collections`, `datetime`). |
| `charts.py` | Render up to 9 per-run analytics PNGs; token-gated charts skipped when no token data. | `plot_run_charts()` (`:460`) dispatching nine `_plot_*` functions | **Tight to matplotlib** (presentation layer — expected). |
| `run_comparison.py` | Cross-run statistics: load records, run Kruskal–Wallis + Dunn (Holm), build model×method matrix. | `load_run_records()` (`:184`), `build_comparison()` (`:392`), `kruskal_test()` (`:245`), `dunn_posthoc()` (`:276`), `write_comparison_json()` (`:509`) | **Tight to scipy/numpy**; **one domain import** — `identity.manifest_loader.discover_axis_values`. |
| `comparison_charts.py` | Render cross-run box plots (with significance brackets), mean±SD bars, and model×method heatmaps. | `plot_run_comparison()` (`:293`) | **Tight to matplotlib + numpy**; no internal imports. |
| `scripts/analyze/analyze_run.py` | CLI orchestrator for stages 1–4; single-persona, batch, and `--all` modes; config-derived output paths. | `_compute_run_metrics()` (`:210`), `_process_batch_dir()` (`:168`), `_run_all()` (`:453`) | **Orchestrator** — imports all analysis modules + `yaml`. |
| `scripts/analyze/compare_runs.py` | CLI orchestrator for stage 5. | `main()` (`:86`) | **Orchestrator** — imports `run_comparison`, `comparison_charts`, `yaml`. |

**Inline observations.**

- `interaction_parser` / `log_parser` / `joiner` are textbook small pure functions — each is a
  single transform with an obvious contract and no hidden dependencies. This is the strongest part
  of the package.
- `aggregator` is conceptually pure and loosely coupled, but its public function is a monolith
  (Section 6).
- `run_comparison` is the only module that reaches into the domain layer
  (`discover_axis_values`), and only to decompose a `{country}_{strategy}_{model}` slug. That is a
  reasonable, narrow coupling — but it does tie cross-run analytics to the axis-composition system's
  naming convention.

---

## 4. Design Patterns in Use

- **Pipeline / staged dataflow.** The defining pattern: `parse → join → aggregate → chart → compare`,
  each stage a composable function passing dicts/lists. No stage mutates shared state.
- **DTO via dataclasses.** `RunRecord` carries decomposed run identity + metric samples;
  `MetricSpec` is a `frozen=True` immutable specification of each metric (key, unit, aggregation,
  direction-of-good). The frozen spec is a clean way to drive both statistics and charting from one
  declarative table (`METRIC_SPECS`).
- **Plotter-registry dispatch.** `plot_run_charts` iterates a fixed list of nine `_plot_*` functions,
  each honoring the same `(metrics, output_dir) -> Path | None` contract and self-skipping (returning
  `None`) when its data is absent. `comparison_charts.plot_run_comparison` uses the same idiom. Adding
  a chart is a local change — append one function — with no edits to the dispatcher's logic.
- **Configuration-driven output paths.** `analyze_defaults.yaml` + `_paths.PROJECT_ROOT` resolve all
  output locations (`03_Analysis/llm_metrics/{slug}/…`); no paths are hardcoded into the modules.
- **Graceful capability degradation.** `MetricSpec.token_gated` plus the `has_token_data` flag
  (`aggregator.py:215`) let the same pipeline serve providers that report tokens (Ollama,
  OpenAI-compat) and those that do not (Claude/Gemini CLI) — token charts and metrics are simply
  omitted rather than erroring.

**What this buys the project:** the parse→join→aggregate core is I/O-free and deterministic, so it
is trivially testable; and the declarative `METRIC_SPECS` / plotter-registry pair means new metrics
and charts are additive rather than invasive.

---

## 5. Strengths

1. **Clean separation of concerns.** Parsing, joining, aggregation, and visualization are distinct
   modules with no back-references. Aggregation is pure computation; all I/O lives in the
   orchestrator scripts.
2. **Loosely-coupled, stdlib-only core.** `interaction_parser`, `log_parser`, `joiner`, and
   `aggregator` import nothing beyond the standard library. The heavy dependencies (matplotlib,
   numpy, scipy) are confined to the charting and cross-run-statistics modules.
3. **Pervasive typing and documentation.** `from __future__ import annotations` throughout, modern
   `X | None` unions, and module- plus function-level docstrings that state inputs, outputs, and
   contracts (e.g. `compute_metrics` documents exactly which fields are required vs optional).
4. **Rigorous, dependency-light statistics.** Kruskal–Wallis (`scipy.stats.kruskal`) for the
   omnibus test, with a hand-rolled **Dunn post-hoc including tie correction and Holm step-down
   adjustment** (`run_comparison.py:276–333`) rather than pulling in `scikit-posthocs`. Descriptive
   summaries, nearest-rank percentiles, and Shannon entropy are all implemented explicitly.
5. **Honest limitation disclosure.** The ±2 s parallel-join caveat is written into the code as a
   comment at the exact site where the approximation happens (`analyze_run.py:189–195`), not buried
   or omitted. This is good engineering hygiene for research software whose outputs feed analysis.

---

## 6. Weaknesses & Architectural Smells

Each finding cites source evidence and a recommended fix.

### 6.1 Oversized function — `compute_metrics`

`aggregator.compute_metrics` spans roughly 350 lines (`aggregator.py:164–514`) and computes *all*
~12 metric families — per-category counts/retries/error-taxonomy, method distribution, prompt-size
growth, response verbosity, wall-clock, value diversity, token consumption (per persona and per
category), tokens/second, latency percentiles, and step-type token budgets — in one body.

**Why it matters:** the function is hard to scan, hard to diff, and forces a reader to hold the
entire metric universe in their head at once. It also makes targeted testing awkward (you cannot
exercise "latency only" without running everything).

**Recommendation:** extract one private helper per metric family
(`_per_category(entries)`, `_latency_by_category(entries)`, `_value_diversity(entries)`, …) and let
`compute_metrics` become a thin assembler that calls them and stitches the result dict. Behaviour is
unchanged; each helper becomes independently testable. (See *Refactoring* — Extract Function.)

### 6.2 Duplicated numeric helpers — median/percentile implemented three times

The same two primitives exist in three places:

- `aggregator._median` / `aggregator._percentile` (`aggregator.py:83–103`) — stdlib nearest-rank.
- `charts._stdlib_median` / `charts._stdlib_percentile` (`charts.py:29–45`) — a second stdlib copy.
- `run_comparison` uses `numpy` for the same descriptive statistics.

Beyond the duplication, the methods are **not consistent**: the stdlib copies use nearest-rank
percentiles while numpy's default is linear interpolation, so the same conceptual p95 can differ
between a chart and a cross-run summary.

**Recommendation:** introduce a single `analysis/_stats.py` exposing `median`/`percentile`/
`shannon_entropy` (or standardize on numpy everywhere) and import it from all three modules. Pick one
percentile convention and document it.

### 6.3 No automated tests

There is no `tests/` directory; the only `test_*` file in the repo is `scripts/dev/test_istat_discovery.py`,
an ISTAT API probe unrelated to `llm_metrics/`. The parse→join→aggregate core is the most testable code
in the project — pure functions with dict in / dict out — yet the correctness of the statistical
output (entropy, percentiles, Dunn/Holm p-values) is entirely unverified.

**Recommendation:** add a `pytest` suite. Start with (a) golden-file tests for `compute_metrics`
over a small fixture run, and (b) numeric tests for `dunn_posthoc` against a hand-checked or
reference-library result. These two alone would cover the highest-risk logic. (See *Cosmic Python*
and *The Good Research Code Handbook* on building testable seams in research code.)

### 6.4 Approximate join for parallel runs

`_process_batch_dir` joins a *single top-level master log* against the *interleaved* interaction
entries of all personas by ±2 s timestamp proximity (`analyze_run.py:189–205`, via
`joiner.join_entries`). Because parallel calls interleave within the 2-second window, a token/latency
record can attach to the wrong persona's entry. The code documents this and notes it is "acceptable
for aggregate/category token distributions" — which is true — but **per-persona** token sums are
therefore approximate.

**Recommendation:** the durable fix is to emit a correlation ID (persona + call index) in the log
line and join on that ID instead of timestamp proximity. This removes the approximation entirely and
makes per-persona attribution exact. Until then, keep the caveat visible in any per-persona report.

### 6.5 `print()`-based reporting, no structured logging

`analyze_run.py` renders its console output through ~200 lines of `print`-based formatters
(`_print_summary`, `_print_per_category`, `_print_value_diversity`, …, from `:226` onward). This is
acceptable for a CLI, but it means console output and machine output (JSON) are produced by separate
code paths, and there is no log-level control.

**Recommendation:** low priority. If the formatters ever grow further, consider deriving the console
table from the same metrics dict via a single renderer, and using `logging` for diagnostics.

### 6.6 Minor hygiene

- `import math` sits **inside** `charts._stdlib_percentile` (`charts.py:43`) rather than at module
  top — a leftover that should move up (and disappears entirely if 6.2 is adopted).
- The nearest-rank vs linear percentile inconsistency noted in 6.2 is the substantive part of this;
  the local import is cosmetic.

---

## 7. Cross-Cutting Concerns

- **Configuration & path resolution.** `config/analyze_defaults.yaml` supplies `output_base` and the
  analytics layout; `_paths.PROJECT_ROOT` (`parents[2]` from `src/population_synthetic/`) anchors
  everything else. `analyze_run.py._derive_output_defaults` maps a run slug under `01_Raw/` to its
  `03_Analysis/llm_metrics/{slug}/` outputs, so the on-disk taxonomy is convention-driven, not
  hardcoded.
- **Output layout = a medallion-style multi-hop.** `01_Raw/{slug}` (raw artifacts) →
  `03_Analysis/llm_metrics/{slug}/` (per-run analytics) → `…/_comparison/` (cross-run). This mirrors
  the bronze→silver→gold lakehouse pattern; the underscore prefix on `_comparison` cleanly
  distinguishes the aggregate folder from run slugs.
- **Headless charting.** Both chart modules use matplotlib's `Agg` backend for server/CI rendering,
  at 150 DPI (180 for grids), with a shared 5-color palette. The backend is selected inside the
  module; fine for a CLI, worth knowing if these functions are ever imported into a notebook.
- **Slug-decomposition coupling.** `run_comparison.decompose_slug` (`:86`) depends on the
  axis-composition ID sets (via `discover_axis_values`) to split `{country}_{strategy}_{model}` by a
  greedy longest-model-suffix match. Cross-run analytics therefore inherit a soft dependency on the
  axis naming convention — a new model/strategy ID that breaks the greedy match would silently skip
  runs. Worth a guard/log if that convention ever changes.

---

## 8. Prioritized Recommendations

| # | Change | Effort | Payoff | Notes |
|---|---|---|---|---|
| 1 | Add `pytest` suite — golden test for `compute_metrics`, numeric test for `dunn_posthoc` | Medium | **High** | Unblocks safe refactoring of everything below; verifies the highest-risk statistics. |
| 2 | Extract one helper per metric family out of `compute_metrics` (§6.1) | Medium | High | Pure mechanical Extract-Function; do *after* #1 so behaviour is pinned. |
| 3 | Consolidate median/percentile/entropy into `analysis/_stats.py`; pick one percentile convention (§6.2) | Low–Med | Medium | Removes triplication and the nearest-rank/linear inconsistency. |
| 4 | Correlation-ID join for parallel runs (§6.4) | High | High | Makes per-persona token/latency attribution exact; needs a log-format change upstream. |
| 5 | Guard/log `decompose_slug` misses (§7) | Low | Low–Med | Prevents silent run-skips when axis IDs change. |
| 6 | Unify console + JSON rendering; optional `logging` (§6.5) | Low | Low | Cosmetic unless formatters keep growing. |

Suggested sequence: **#1 → #3 → #2 → #4**, with #5/#6 opportunistic.

---

## 9. Curated Learning Resources

Framed as: *to address the findings above, study these.* URLs are canonical landing pages, verified
during research except the two long-stable pages noted.

### Books — software architecture & design

| Title (author) | Relevance |
|---|---|
| **Architecture Patterns with Python / "Cosmic Python"** (Percival & Gregory) — cosmicpython.com | Testable seams, ports-and-adapters, service-layer — directly informs adding tests (§6.3) and decoupling orchestration from computation. |
| **Refactoring, 2e** (Fowler) — martinfowler.com/books/refactoring.html | The named, safe transformations (Extract Function, Replace Conditional with Polymorphism) for splitting `compute_metrics` (§6.1). |
| **Clean Architecture** (R. C. Martin) | SOLID + the dependency rule — vocabulary for keeping the stdlib core independent of matplotlib/scipy. |
| **Designing Data-Intensive Applications** (Kleppmann) — dataintensive.net | Batch dataflow, idempotency, and surviving partial failure — the conceptual frame for the parse→join→aggregate pipeline. |
| **Fluent Python, 2e** (Ramalho) | Idiomatic dataclasses, protocols, iterators — sharpens the DTO/`MetricSpec` design. |
| **Effective Python** (Slatkin) | Item-sized best practices for config, dataclasses, and exceptions. |
| **The Pragmatic Programmer, 20th** (Thomas & Hunt) | DRY and orthogonality — the principle behind consolidating the triplicated helpers (§6.2). |

### University courses (public materials)

| Course (institution) | Relevance |
|---|---|
| **Data 100 — Principles & Techniques of Data Science** (UC Berkeley) — ds100.org | The data-science lifecycle the aggregate/compare stages implement. |
| **The Missing Semester of Your CS Education** (MIT CSAIL) — missing.csail.mit.edu | Shell, Git, debugging/profiling — the lab skills behind a scriptable pipeline. |
| **17-313 Foundations of Software Engineering** (CMU) — cmu-313.github.io | Managing complexity, testing, design-for-change — applies directly to §6. |
| **CS109 Data Science** (Harvard) — cs109.org | End-to-end structuring of an analysis pipeline. |
| **6.0002 Intro to Computational Thinking & Data Science** (MIT OCW) | Sampling and statistical thinking. *(long-stable OCW page)* |

### Online courses / MOOCs

| Course (provider) | Relevance |
|---|---|
| **IBM Data Engineering Professional Certificate** (Coursera) | Formalizes the staged-pipeline / ETL patterns hand-rolled here. |
| **Data Engineer career track** (DataCamp) | Python-centric pipeline design and workflow automation. |
| **Made With ML** (madewithml.com) | Free, code-first MLOps — testing, config, reproducibility for LLM + analytics systems. |
| **Design Patterns in Python** (Refactoring.Guru) | Idiomatic factory/strategy/registry patterns. |

### Articles, papers & standards

| Resource | Relevance |
|---|---|
| **Medallion Lakehouse Architecture** (Databricks docs) | Bronze→silver→gold ≈ `01_Raw → 03_Analysis → _comparison`; a vocabulary for the output layout (§7). |
| **Best Practices for Scientific Computing** — Wilson et al., *PLOS Biology* 2014 | Foundational RSE guidance: modularity, automation, testing. |
| **Good Enough Practices in Scientific Computing** — Wilson et al., *PLOS Comp. Bio.* 2017 | Pragmatic project organization and data management for a single-team pipeline. |
| **Ten Simple Rules for Reproducible Computational Research** — Sandve et al., 2013 | Record every intermediate; store the data behind every plot — governs chart/stat provenance. |
| **FAIR Guiding Principles** — Wilkinson et al., *Scientific Data* 2016 | How run artifacts and references should be identified and described. |
| **The Turing Way** (Alan Turing Institute) | Living handbook on reproducible pipelines, environments, and testing. |

### Python design-pattern & research-software-engineering references

| Resource | Relevance |
|---|---|
| **Python Design Patterns** (Brandon Rhodes) — python-patterns.guide | Which classic patterns matter in Python (and which to skip) — guards against over-engineering the registry/DTO design. |
| **The Good Research Code Handbook** (Mineault) — goodresearch.dev | The most on-target RSE text: layout, packaging, config, testing, refactoring for analysis code. |
| **Software Carpentry Lessons** (The Carpentries) | Reproducibility/automation baseline. |
| **python-patterns** (faif, GitHub) | Runnable catalog for choosing a structure for a new pipeline stage. |

**Suggested reading order for this codebase:** Cosmic Python + Good Research Code Handbook (testable
structure) → Refactoring + Rhodes' patterns guide (clean up §6.1/§6.2 without over-patterning) →
DDIA batch/dataflow chapters + Databricks Medallion (formalize the stages) → Ten Simple Rules /
Good Enough Practices / Turing Way (lock in reproducibility and output provenance).

---

## Appendix — Verification Notes

- `compute_metrics` length, the triplicated median/percentile, the ±2 s parallel join, and the
  absence of a `tests/` directory were each confirmed against source during review
  (`aggregator.py:164–514`, `aggregator.py:83–103` + `charts.py:29–45`, `analyze_run.py:189–205`;
  `Glob "tests/**"` → none, only `scripts/dev/test_istat_discovery.py`).
- Line numbers are accurate as of 2026-06-29 on branch `feature/italy-identity-comparison-pipeline`
  and will drift as the files change; treat them as anchors, not guarantees.
