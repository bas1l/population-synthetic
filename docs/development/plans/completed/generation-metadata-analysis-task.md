# Plan: Generation Metadata Analysis Task (country × model × method)

**Date:** 2026-07-23
**Author:** Basil
**Status:** Completed
**Completed:** 2026-07-23 15:20
**Base Branch:** `dev`
**Branch:** `feature/generation-metadata-analysis-task`

---

## Overview

Add a new standalone analysis process, **`generation_metadata`**, that reports — per
`country × model × method(strategy)` combo — the mean, spread, and n of the per-persona
generation cost of the LLM identity pipeline: wall-clock time, input/output/total tokens,
LLM calls, retry rate, error rate, and estimated USD cost. It reuses the existing
`run_analytics` per-call telemetry parser, adds a config-driven per-model pricing table, and
emits a per-country CSV + JSON report + PNG/SVG charts under `03_Analysis/generation_metadata/`.

## Problem Statement

There is currently no first-class, publication-ready summary of *how expensive it is to
generate one persona* for each generation configuration. The existing `run_analytics`
cross-run task gets close — it builds model×method matrices for **median** wall-clock and
**total** tokens — but it: (a) reports medians, not the "on average" means the user wants;
(b) collapses tokens to `total` only (no input/output split); (c) has no cost model at all
(the registry description mentions "cost" but no pricing code or config exists); and (d) does
not emit a single combined per-persona metadata table (time + input + output + calls + cost
side by side) keyed by country×model×method. This task fills those gaps as a dedicated,
reusable analysis output that can feed the LLM-population-fidelity manuscript directly.

## Goals

### In Scope
1. New analysis subpackage `src/population_synthetic/analysis/generation_metadata/` (parse →
   aggregate → cost → render, one module per responsibility).
2. Per-combo **mean + std-dev + n** for: wall-clock time/persona, input tokens/persona,
   output tokens/persona, total tokens/persona, LLM calls/persona, retry rate, error rate,
   estimated USD cost/persona.
3. New config-driven pricing table `config/analysis/model_pricing.yaml` (USD per 1M input /
   output tokens, keyed by model axis id), seeded from live 2026-07-23 OpenRouter/provider
   research; `ollama_*` = 0.
4. Registry entry `generation_metadata` (dispatch `slugs`) + GUI workflow node.
5. Backing script `scripts/analyze/summarize_generation_metadata.py` following the
   `rank_models.py` convention (axis filters, `--output-base`, `--no-charts`, `--force`).
6. Output artifacts per country: `{country}_summary.csv`, `{country}_summary.json`, and
   per-metric model×method heatmap charts (`.png` + `.svg`).
7. Shared `mean`/`stddev` primitives added to `analysis/utils/_stats.py` (single source of truth).
8. Unit + integration tests; docs updates.

### Out of Scope
- Modifying or refactoring the existing `run_analytics` task (it stays as-is; this is a sibling).
- Per-call or per-category breakdowns (this task is strictly per-persona → per-combo).
- Cost tiers, prompt-caching discounts, batch pricing, or multi-currency (flat input/output
  $/1M only — KISS/YAGNI).
- Live price fetching at run time (pricing is a static, dated config file).
- Automatic pricing refresh / staleness enforcement beyond stamping the table date in output.

## Success Criteria

- [x] `python scripts/analyze/summarize_generation_metadata.py --country swedish` produces
      `03_Analysis/generation_metadata/swedish_summary.csv`, `swedish_summary.json`, and
      `charts/swedish_*.png/.svg` for every discovered model×method combo with raw data.
- [x] Each CSV row is one `(model, method)` combo; each metric appears as `<metric>_mean`,
      `<metric>_std`, `<metric>_n` columns.
- [x] Token metrics and cost are `None` (not `0`) for combos whose provider reports no tokens
      (e.g. Ollama, Claude-CLI), and this is verified by a test.
- [x] A model that HAS token data but NO entry in `model_pricing.yaml` raises loudly
      (fail-fast), verified by a test.
- [x] `std` is `None` (not `0` or a crash) when a metric has `n < 2`, verified by a test.
- [x] The JSON report records the pricing-table `observed_date`/`source` and a list of
      skipped personas/combos with reasons.
- [ ] The task appears and runs from the GUI Flow Runner as `generation_metadata`.
- [x] `ruff check src/` clean; `pytest` green including the new tests.

## Definitions

- **method**: synonym for **strategy** — the `strategy_id` axis. Human-facing label is "method".
- **combo**: a `(country_id, model_id, strategy_id)` triple, resolved from a run slug
  `{country}_{strategy}_{model}` via `analysis/utils/axes.decompose_slug`.
- **persona wall-clock time**: `last_call.response_received_at − first_call.request_sent_at`
  for that persona's `llm_interactions` entries; falls back to `timestamp` when the
  `request_sent_at`/`response_received_at` telemetry fields are `None`. Requires ≥2 usable
  timestamps, else the persona's time is `None` (excluded from the mean, counted as skipped).
- **input tokens / output tokens / total tokens (per persona)**: sum of `prompt_tokens` /
  `completion_tokens` / `total_tokens` across that persona's calls. `None` (not 0) when the
  provider reports no token telemetry for that persona.
- **retry rate (per persona)**: fraction of that persona's calls with `attempt > 1`.
- **error rate (per persona)**: fraction of that persona's calls with a non-null `error`.
- **estimated cost / persona (USD)**: `input_tokens × price_in/1e6 + output_tokens ×
  price_out/1e6`, using `config/analysis/model_pricing.yaml`. `None` when the persona has no
  token telemetry; **raises** when the persona has token telemetry but the model_id is absent
  from the pricing table.
- **has_token_data (combo gate)**: `True` iff any persona in the combo has a non-null
  `prompt_tokens` or `completion_tokens`. Token/cost metric families are computed only when
  this is `True`, else emitted as `None`.
- **mean / std / n (per metric, per combo)**: `n` = count of personas contributing a non-null
  value for THAT metric (per-metric, not per-combo); `mean` = arithmetic mean over those n;
  `std` = sample standard deviation (n−1 denominator), `None` when `n < 2`.

---

## Technical Design

### Approach

A dedicated **pipe-and-filter** subpackage that reuses the `run_analytics` telemetry parser
(which already owns JSONL/JSON format detection and field normalization) and the shared
figure/registry/axis utilities, adding only what is genuinely new: per-persona metadata
aggregation with **means**, an **input/output token split**, and a **config-driven cost
model**. Stats primitives (`mean`, `stddev`) are added once to `analysis/utils/_stats.py`
rather than inlined, per the repo's "one authoritative representation" rule (the module's own
docstring records a past bug from three divergent percentile implementations).

Cost is genuinely new: no pricing code or config exists anywhere in the repo today. The
pricing table lives in config as the single source of truth, keyed by the **model axis id**
(the same id used in slugs and `discover_axis_values("models")`), so the join is exact.

Rendering is strictly downstream of computation (charts read the aggregated numbers, never
re-derive), and error bars / n-annotations surface the uncertainty the means carry.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| New standalone subpackage (reuse parser) | Clean separation; own folder; full control over means/IO-split/cost; no risk to existing task | Small parser-code reuse across subpackages | **Chosen** |
| Extend `run_analytics` cross-run output | Least duplication | Mixes into an already-large output; changes a working task; still needs new cost + means + IO-split code anyway | Rejected |
| Depend on `run_analytics.json` output (task dependency) | No re-parse | Couples to another task's on-disk schema + run order; `run_analytics.json` lacks IO-split-per-persona in the exact shape needed and has no cost | Rejected (reuse the *parser code*, not the *output*) |
| Re-implement stats/timestamp parsing locally | Self-contained | Violates DRY; repo already burned by divergent stat impls | Rejected |
| JPG raster charts (original ask) | Slightly smaller files | Lossy on thin lines/text; breaks the PNG+SVG `save_figure` standard | Rejected → PNG+SVG (user confirmed) |

### Architecture & Module Contracts

New subpackage `src/population_synthetic/analysis/generation_metadata/`:

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `persona_metrics.py` | Reduce one persona's normalized call entries to a per-persona metric record | `list[normalized_entry]` → `PersonaMetrics(time, in_tok, out_tok, total_tok, n_calls, retry_rate, error_rate)` (fields `None` when ungated) | slugs, country/model/strategy, file paths, pricing, charts |
| `combo_aggregator.py` | Aggregate per-persona records for one combo into per-metric mean/std/n | `list[PersonaMetrics]` → `ComboSummary{metric: {mean,std,n}}` + `skipped` reasons | file layout, pricing $ values, chart styling |
| `cost.py` | Load pricing table; compute per-persona cost; fail-fast on missing price | `(model_id, in_tok, out_tok, PricingTable)` → `cost | None`; raises `KeyError`-style loudly when tokens present & id absent | timestamps, charts, slugs |
| `pricing.py` | Parse/validate `config/analysis/model_pricing.yaml` | path → `PricingTable{model_id: (in,out)}` + `observed_date`, `source` | anything about personas/runs |
| `report_writer.py` | Serialize a country's combo summaries to CSV + JSON | `dict[country → list[ComboSummary]]`, metadata → `.csv` + `.json` | how metrics were computed, chart styling |
| `charts.py` | Render per-metric model×method heatmaps (mean, n-annotated) via shared `save_figure` | `list[ComboSummary]`, out_dir → `.png` + `.svg` per metric | parsing, cost math, CSV schema |
| `__init__.py` | Public entrypoint `summarize(...)` orchestrating the above | axis filters, output_base, flags → writes artifacts | — |

Reused (no changes except `_stats.py`):
- `analysis/run_analytics/per_run/interaction_parser.py` — `find_interaction_file(dir)`,
  normalized-entry parsing (guaranteed keys, `None` when absent). **Reuse verbatim.**
- `analysis/run_analytics/per_run/aggregator.py::_parse_iso` — multi-format timestamp parse.
  (If import coupling is undesirable, lift `_parse_iso` to `analysis/utils/_stats.py` or a
  small `analysis/utils/timeparse.py`; decide at implementation, default = import & reuse.)
- `analysis/utils/_stats.py` — **ADD** `mean(values) -> float | None` and
  `stddev(values, *, sample=True) -> float | None` (None for n<1 / n<2). Single source of truth.
- `analysis/utils/figures.py::save_figure` — PNG+SVG pair writer.
- `analysis/utils/axes.py::decompose_slug` + `manifest_loader.discover_axis_values(...)`.
- `analysis/utils/registry.py` — `analysis_output_dir("generation_metadata", base)`,
  `resolve_output_base(cli)`.

New config `config/analysis/model_pricing.yaml` (schema):
```yaml
# USD per 1,000,000 tokens. Cost = tokens * rate / 1e6.
observed_date: "2026-07-23"
source: "OpenRouter model pages + platform.claude.com pricing (see plan appendix)"
currency: "USD_per_1M_tokens"
models:
  claude_sonnet:            {in: 3.00,  out: 15.00}   # Anthropic first-party (Sonnet 5)
  claude_haiku:             {in: 1.00,  out: 5.00}    # Anthropic first-party (Haiku 4.5)
  claude_opus:              {in: 5.00,  out: 25.00}   # Anthropic first-party (Opus 4.8)
  gemini_flash:             {in: 0.30,  out: 2.50}    # google/gemini-2.5-flash (OpenRouter)
  openrouter_claude_sonnet5:{in: 3.00,  out: 15.00}   # anthropic/claude-sonnet-4-5
  openrouter_gpt55:         {in: 75.00, out: 150.00}  # openai/gpt-4.5-preview  [VERIFY: widget didn't render]
  openrouter_gemini_flash:  {in: 0.075, out: 0.30}    # google/gemini-flash-1.5 [VERIFY: legacy slug, unconfirmed]
  openrouter_deepseek_v4:   {in: 0.435, out: 0.87}    # deepseek/deepseek-v4-pro [effective/discounted]
  openrouter_glm_52:        {in: 0.77,  out: 2.42}    # z-ai/glm-5.2 [effective/discounted]
  openrouter_mistral_medium:{in: 1.50,  out: 7.50}    # mistralai/mistral-medium-3-5
  openrouter_qwen37_max:    {in: 1.475, out: 4.425}   # qwen/qwen3.7-max [effective/discounted]
  # --- local models: no API cost ---
  ollama_deepseek_r1_14b:   {in: 0, out: 0}
  ollama_gemma2_9b:         {in: 0, out: 0}
  ollama_gemma4_e4b:        {in: 0, out: 0}
  ollama_llama31_8b:        {in: 0, out: 0}
  ollama_llama32_3b:        {in: 0, out: 0}
  ollama_llama33_70b:       {in: 0, out: 0}
  ollama_lucie_7b:          {in: 0, out: 0}
  ollama_mistral_nemo_12b:  {in: 0, out: 0}
  ollama_qwen3_14b:         {in: 0, out: 0}
```

Registry entry (`config/analysis/analysis_registry.yaml`, under `processes:`):
```yaml
  generation_metadata:
    label: "Generation Metadata (country x model x method)"
    description: >
      Per country x model x method(strategy), the mean/spread/n of the per-persona
      generation cost: wall-clock time, input/output/total tokens, LLM calls, retry &
      error rates, and estimated USD cost (from config/analysis/model_pricing.yaml).
      Reads 01_Raw LLM-call telemetry; emits per-country CSV + JSON + charts.
    folder: "generation_metadata"
    script: "scripts/analyze/summarize_generation_metadata.py"
    dispatch: "slugs"
```

GUI workflow node (`config/gui/flows/analysis_workflow.yaml`, under `tasks:`), isolated island:
```yaml
  generation_metadata:
    enabled: true
    supports_force: true
    force: false
    options:
      output-base:
      no-charts: false
    depends_on: []
```

Output layout: `{output_base}/03_Analysis/generation_metadata/`
```
{country}_summary.csv     # rows = (model, method); cols = <metric>_{mean,std,n}
{country}_summary.json    # nested + metadata (pricing observed_date/source, skipped[])
charts/
  {country}_time.png / .svg
  {country}_input_tokens.png / .svg
  {country}_output_tokens.png / .svg
  {country}_total_tokens.png / .svg
  {country}_calls.png / .svg
  {country}_retry_rate.png / .svg
  {country}_error_rate.png / .svg
  {country}_cost.png / .svg
```

---

## Implementation Plan

### Phase 1: Foundation (stats, pricing, parser wiring)
**Goal:** Shared primitives and config in place; parsing reuse proven.

**Started:** 2026-07-23
**Completed:** 2026-07-23

- [x] 1.1 — Add `mean()` and `stddev(sample=True)` to `analysis/utils/_stats.py` (None for
      n<1 / n<2); docstring notes sample (n−1) convention.
- [x] 1.2 — Create `config/analysis/model_pricing.yaml` seeded from the appendix table
      (with `observed_date`, `source`, per-model VERIFY comments).
- [x] 1.3 — Create subpackage skeleton `analysis/generation_metadata/` with `pricing.py`
      (load+validate) and a thin `persona_metrics.py` that consumes
      `run_analytics.per_run.interaction_parser` output; confirm import path works.

**Files Modified:**
- `src/population_synthetic/analysis/utils/_stats.py` — add mean/stddev
- `config/analysis/model_pricing.yaml` — NEW
- `src/population_synthetic/analysis/generation_metadata/{__init__,pricing,persona_metrics}.py` — NEW

**Dependencies:** None

### Phase 2: Core aggregation + cost + report
**Goal:** Compute per-combo summaries and write CSV/JSON.

**Started:** 2026-07-23
**Completed:** 2026-07-23

- [x] 2.1 — `persona_metrics.py`: reduce one persona's entries to `PersonaMetrics`
      (time span with ≥2-timestamp guard; token sums with None-gating; calls; retry/error rates).
- [x] 2.2 — `cost.py`: per-persona cost from `PricingTable`; None when ungated; **raise** when
      tokens present but model_id absent.
- [x] 2.3 — `combo_aggregator.py`: per-metric mean/std/n over personas; collect `skipped` reasons.
- [x] 2.4 — `report_writer.py`: per-country CSV (`<metric>_{mean,std,n}` columns) + JSON
      (nested summary + pricing metadata + skipped list).
- [x] 2.5 — `__init__.summarize(...)`: discover slugs under `01_Raw/`, decompose to combos,
      filter by axis args, group by country, orchestrate 2.1–2.4; idempotent (skip existing
      unless `--force`).

**Files Modified:**
- `src/population_synthetic/analysis/generation_metadata/{persona_metrics,cost,combo_aggregator,report_writer,__init__}.py`

**Dependencies:** Phase 1

### Phase 3: Charts, script, registration, GUI, tests, docs
**Goal:** End-to-end runnable from CLI and GUI, tested and documented.

**Started:** 2026-07-23
**Completed:** 2026-07-23

- [x] 3.1 — `charts.py`: per-metric model×method heatmap (mean cell values, n-annotated),
      via `save_figure` (PNG+SVG); skip a chart only when the metric is empty for all combos.
- [x] 3.2 — `scripts/analyze/summarize_generation_metadata.py`: argparse mirroring
      `rank_models.py` (`--country/--model/--strategy` append, `--slug`, `--output-base`,
      `--no-charts`, `--force`, `--strict`); resolve out dir via `analysis_output_dir`.
- [x] 3.3 — Add registry entry `generation_metadata`.
- [x] 3.4 — Add GUI workflow node `generation_metadata` (island).
- [x] 3.5 — Tests (see Testing Plan).
- [x] 3.6 — Docs (see Documentation Plan).

**Files Modified:**
- `src/population_synthetic/analysis/generation_metadata/charts.py` — NEW
- `scripts/analyze/summarize_generation_metadata.py` — NEW
- `config/analysis/analysis_registry.yaml` — add process
- `config/gui/flows/analysis_workflow.yaml` — add task
- `tests/test_generation_metadata.py` — NEW
- docs (below)

**Dependencies:** Phase 2

---

## Testing Plan

### Unit Tests
- [x] `mean`/`stddev`: known-answer via `pytest.approx`; `stddev(n<2) is None`; `mean([]) is None`.
- [x] `persona_metrics`: synthetic entry list → correct time span, token sums, calls,
      retry/error rates; missing timestamps → time `None`; no token fields → token metrics `None`.
- [x] `cost`: correct USD for a priced model; `None` when tokens `None`; **raises** when
      tokens present and model_id absent from table; `0` for `ollama_*`.
- [x] `combo_aggregator`: per-metric `n` counts only non-null contributors; `skipped` populated.

### Integration Tests
- [x] Fixture `01_Raw/{slug}/persona_*/llm_interactions.jsonl` for 2 combos (one tokened, one
      token-less) → `summarize(...)` writes CSV+JSON; assert columns, None-gating, JSON metadata.
- [x] `--force` re-runs; without it, existing output is skipped.

### Manual Verification
- [x] Run against real `01_Raw` for `swedish` (live run wrote CSV+JSON + 8 metric charts;
      confirms data-driven token gating — Swedish claude runs emit tokens, ollama cost = 0).
- [ ] Launch GUI, confirm `generation_metadata` node appears and runs.

### Edge Cases
- [ ] Combo with a single persona (std `None`, mean defined).
- [ ] Combo with zero personas / no interaction file (loud skip, recorded reason).
- [ ] Provider reporting `total_tokens` but not the split → total priced-gated handling defined.

---

## Documentation Plan

- [x] `CLAUDE.md` — add `generation_metadata` to the analysis-layer paragraph + registry note.
- [x] `docs/architecture/commands.md` — add the new script command.
- [x] `docs/architecture/configuration.md` — document `config/analysis/model_pricing.yaml`.
- [x] `docs/development/gui.md` — note the new task island (if task list is enumerated there).
- [x] Inline docstrings per module; pricing YAML header comments (date, source, VERIFY flags).

---

## Rollback Plan

1. The task is an isolated island (`depends_on: []`) writing only to a new folder
   `03_Analysis/generation_metadata/` — no existing artifact is touched.
2. To disable without reverting: set `enabled: false` on the GUI node.
3. Full revert: delete the subpackage, script, config file, registry entry, GUI node, and the
   `_stats.py` additions; no data migration needed.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Pricing numbers stale/inaccurate (several are effective/discounted or unconfirmed) | High | Med | Stamp `observed_date`/`source` in config + JSON output; per-model VERIFY comments; cost is clearly labelled "estimated"; two flagged slugs need manual check before publication use |
| Providers report tokens inconsistently (None mix) | High | Med | Established token-gating: None not 0; per-metric n; skipped-list in JSON |
| Coupling to `run_analytics` internal parser module | Med | Low | Depend only on the stable `interaction_parser` contract; if it churns, the normalized-entry dict is the interface, not the file format |
| Slug decomposition ambiguity | Low | Med | Use `decompose_slug` + `discover_axis_values`; `--strict` fails loudly on undecodable slugs |
| Double-counting parallel calls in wall-clock span | Low | Low | Span metric is first-sent→last-received by design (user-chosen); documented in Definitions |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 | ~0.5 day | None |
| Phase 2 | ~1 day | Phase 1 |
| Phase 3 | ~1 day | Phase 2 |

---

## Appendix: Pricing research (observed 2026-07-23)

Live OpenRouter model pages + `platform.claude.com` pricing. USD per 1M tokens.

| axis_id | resolved_model | in $/1M | out $/1M | confidence | note |
|---|---|---|---|---|---|
| claude_sonnet | Claude Sonnet 5 | 3.00 | 15.00 | high | first-party; intro $2/$10 through 2026-08-31 |
| claude_haiku | Claude Haiku 4.5 | 1.00 | 5.00 | high | first-party |
| claude_opus | Claude Opus 4.8 | 5.00 | 25.00 | high | first-party |
| gemini_flash | google/gemini-2.5-flash | 0.30 | 2.50 | high | OpenRouter (matches Google AI) |
| openrouter_claude_sonnet5 | anthropic/claude-sonnet-4-5 | 3.00 | 15.00 | high | OpenRouter page |
| openrouter_mistral_medium | mistralai/mistral-medium-3-5 | 1.50 | 7.50 | med | OpenRouter page |
| openrouter_deepseek_v4 | deepseek/deepseek-v4-pro | 0.435 | 0.87 | med | effective (caching/promo) |
| openrouter_glm_52 | z-ai/glm-5.2 | 0.77 | 2.42 | med | effective (45% off) |
| openrouter_qwen37_max | qwen/qwen3.7-max | 1.475 | 4.425 | med | effective (41% off) |
| openrouter_gpt55 | openai/gpt-4.5-preview | 75.00 | 150.00 | **low/verify** | widget didn't render; OpenAI list price; legacy model |
| openrouter_gemini_flash | google/gemini-flash-1.5 | 0.075 | 0.30 | **low/verify** | legacy slug; historical price, unconfirmed |

**Action before publication use:** manually verify the two low-confidence rows and confirm
list-vs-effective for the four "effective/discounted" med rows.

> Note: models using the direct `claude` provider (Claude CLI) typically emit **no** token
> telemetry, so their token/cost metrics will gate to `None` regardless of pricing; the
> `claude_*` prices are seeded for completeness and for any run that does report tokens.

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- CLAUDE.md
- config/analysis/analysis_registry.yaml
- config/analysis/model_pricing.yaml
- config/gui/flows/analysis_workflow.yaml
- docs/architecture/commands.md
- docs/architecture/configuration.md
- docs/development/gui.md
- docs/development/plans/active/generation-metadata-analysis-task.md
- scripts/analyze/summarize_generation_metadata.py
- src/population_synthetic/analysis/generation_metadata/__init__.py
- src/population_synthetic/analysis/generation_metadata/charts.py
- src/population_synthetic/analysis/generation_metadata/combo_aggregator.py
- src/population_synthetic/analysis/generation_metadata/cost.py
- src/population_synthetic/analysis/generation_metadata/persona_metrics.py
- src/population_synthetic/analysis/generation_metadata/pricing.py
- src/population_synthetic/analysis/generation_metadata/report_writer.py
- src/population_synthetic/analysis/utils/_stats.py
- tests/test_analysis_registry.py
- tests/test_generation_metadata.py
- tests/test_workflow_state.py
