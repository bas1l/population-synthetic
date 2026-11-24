> **Archived 2026-08-20:** Superseded by `docs/development/plans/active/validation-attrition-and-cost-efficiency-processes.md`. Items 1-2 shipped as `completed/model-method-tv-heatmap.md`; items 3-5 are restated in the successor plan, corrected for the full-N exclusion rule.

# Plan: Pipeline figures for model × method fidelity, cost-efficiency, and validation attrition

**Date:** 2026-08-11
**Author:** Basil
**Status:** Revised
**Base Branch:** `dev`
**Branch:** `feature/model-method-cost-attrition-figures`

**Revision note (2026-08-11):** audited against the codebase and the on-disk `swedish_02`
artifacts; four blocking corrections applied — `depends_on` is a GUI-flow key, not a registry
key; `generation_metadata` has no slug column or per-combo totals to join on; `requested_n`
is absent from the `model_ranking` result and must come from `population_cap/_index.json`
(where it is already present — Phase 2 needs no backfill and does not wait on Phase 3);
and `generation_metadata` reads the *capped* mirror, so naive cost figures understate spend
by 3–5× exactly where retention is worst.

---

## Overview

Add three cross-cutting analysis figures to the pipeline so that facts currently
reconstructed by hand for the talk/manuscript are emitted as first-class artifacts:
(1) a **model × method** heatmap of overall TV-similarity, (2) an **accuracy vs
token-cost** figure per model × method, and (3) a **validation-attrition** figure showing
how many personas are discarded at each stage of the validation gate. All three are
read-only over existing artifacts; none changes how any statistic is computed.

## Problem Statement

The analysis layer currently emits per-attribute detail but no single artifact that shows
the study's headline claim — *how you elicit dominates which model you pick* — as a
two-factor grid. It was produced by hand for the deck
(`figures/swedish_02_model_method_tv_heatmap.py` in the external manuscript folder), which
means it is not reproducible from a pipeline run, drifts as soon as the analysis is re-run,
and carries no provenance.

Two further facts have no artifact at all:

- **Cost is not joined to accuracy.** `generation_metadata` knows tokens and USD per
  combination; `model_ranking` knows fidelity per combination. Nothing joins them, so
  "what does a point of fidelity cost, and on which method?" cannot be answered from the
  outputs. The deck's existing cost slides are hand-built from a stale repo doc
  (`docs/development/swedish-token-cost-by-model.md`, 2026-07-02) that predates the
  current 10-model axis.
- **Validation attrition is invisible.** The gate discards personas at
  `validate_raw` (incomplete) and `validate_mapped` (`__UNMAPPED__` fields), then caps at
  `--n`. Seven of the 50 Swedish combinations never reached the n=100 cap (n = 7 to 49),
  which materially weakens their rows in every downstream figure — but no artifact
  surfaces it, so it is invisible in the deck and easy to misread as a model result.

### Findings from the current dataset

Measured directly from the `swedish_02` artifacts on disk (`validate_raw/_summary.csv`,
`validate_mapped/_summary.csv`, `population_cap/_index.json`, 50 combinations), attrition is
substantially larger than the "seven under-cap combinations" framing above suggests:

- **47 of 50 combinations lose personas at `validate_mapped`**, several catastrophically —
  pass rates of 4.7%, 6.0%, 7.3% and 19.6% at the bottom. Raw-stage loss is by comparison
  negligible: 2 combinations, 4 and 61 personas.
- **`generated` is not 150.** It ranges 150 → 549 across combinations, because
  under-delivering arms were re-generated until they filled. `openrouter_qwen35_flash`
  generated 549 personas to land 100; `ollama_deepseek_r1_14b` generated 370 for 119.

Two consequences shape the design below:

1. **Absolute counts are not comparable across a 3.7× spread in denominators.** A five-bar
   attrition chain per combination invites exactly the cross-combination comparison it
   cannot support. The artifact must therefore carry a **retention rate** and the
   **generation multiplier** (`generated / selected`), not five raw counts alone.
2. **Mapped-validity is itself a model × method outcome**, not merely a caveat on the
   fidelity figures. How many attempts an arm needs to yield one usable persona is a result
   worth reporting alongside how good the personas are.

## Goals

### In Scope

1. `model_ranking` emits a **model × method overall TV-similarity heatmap** (PNG + SVG),
   styled as a sibling of the existing `models_table` / `methods_table`, with the per-cell
   `n` and an explicit marker on any cell below the requested cap.
2. A new **`cost_efficiency`** analysis process joining `model_ranking` (accuracy) and
   `generation_metadata` (tokens, USD, wall-clock), emitting an accuracy-vs-cost figure per
   model × method plus a tidy CSV and a JSON report. **The join key must be reconstructed:**
   `generation_metadata` emits a single per-country `{country}_summary.csv` keyed on `model`
   + `method` columns, with no slug column — see [The join key does not
   exist](#the-join-key-does-not-exist).
3. A new **`validation_attrition`** analysis process reading the already-persisted gate
   artifacts and emitting a per-combination attrition figure
   (generated → raw-valid → mapped-valid → clean → selected) plus a tidy CSV, carrying the
   retention rate and generation multiplier alongside the counts.
4. `CapSummary` gains `raw_total` so the attrition denominator has a single authoritative
   source rather than being joined from `validate_raw/_summary.csv`.
5. All three registered in `config/analysis/analysis_registry.yaml` (keys `label`,
   `description`, `folder`, `script`, `dispatch` — the registry has no `depends_on`), **and**
   the two new processes added as tasks to `config/gui/flows/analysis_workflow.yaml`, which
   is where `depends_on` is actually declared, so the GUI workflow and the CLI dispatch them
   like any other process.

### Out of Scope

- Changing any statistic, test, or the fidelity/realism computations themselves.
- Re-running or repairing `generation_metadata` for the current Swedish dataset (it simply
  has not been run; that is an operational step, not a code change). It remains an
  operational **prerequisite** of Phase 5 — see Task 5.0 — and changing its read root is
  in scope only if capped-cost option (a) is chosen.
- Retiring or rewriting `docs/development/swedish-token-cost-by-model.md`. It stays as a
  dated projection; `cost_efficiency` supersedes it for measured runs.
- Propagating any of these figures into the external manuscript/deck. That is a separate
  `/sync-manuscript` step once the artifacts exist.
- Multi-country comparison of cost or attrition. Every artifact here is per-country, like
  its siblings.

## Success Criteria

- [ ] `python scripts/analyze/rank_models.py --country swedish_02` writes
      `{country}_model_method_heatmap.png` and `.svg` into the `model_ranking` folder.
- [ ] The heatmap's cell values equal `overall_tv_similarity × 100` from
      `{country}_performance.csv` for the same `(model, strategy)`, to 1 decimal.
- [ ] Every cell whose `n < requested_n` is visually marked and its `n` printed; a cell at
      the cap is printed without the marker.
- [ ] Row order, column order, colour ramp, and the hosted/local label colouring are
      identical in rule to `plot_model_fidelity_table` (shared helpers, not duplicated code).
- [ ] `python scripts/analyze/analyze_cost_efficiency.py --country swedish_02` writes a
      figure, a `{country}_cost_efficiency.csv`, and a `{country}_cost_efficiency.json`.
- [ ] `cost_efficiency` fails loudly with a named missing-input error when
      `generation_metadata` has not been run for that country.
- [ ] `python scripts/analyze/analyze_validation_attrition.py --country swedish_02` writes
      a figure and `{country}_attrition.csv` with one row per combination and columns
      `generated, raw_valid, mapped_valid, clean, selected, requested_n, retention_rate,
      generation_multiplier, under_cap, had_surplus`.
      `retention_rate = clean / generated`; `generation_multiplier = generated / selected`;
      `under_cap = selected < requested_n`. The `truncated` field of `CapSummary` is exposed
      as `had_surplus`, never as `truncated` — see the Definitions entry for why.
- [ ] For `swedish_02_all_generate_evaluate_pick_v2_claude_haiku` the attrition row reads
      `generated=150, raw_valid=150, mapped_valid=149, clean=149, selected=100`.
- [ ] The seven under-cap Swedish combinations are identifiable from the attrition CSV
      alone (`under_cap = true`), and all seven carry `had_surplus = false`.
- [ ] The CSV reproduces the measured spread: `generated` takes at least the values
      150, 250, 366, 370 and 549 across the 50 Swedish rows, and 47 rows have
      `mapped_valid < raw_valid`.
- [ ] `pytest` passes, including new unit tests for each of the three readers.
- [ ] `ruff check src/` clean.

## Definitions

- **combination (combo):** one `(country, model, strategy)` triple, identified by its slug
  `{country}_{strategy}_{model}`, built by `axis_slug(model_id, strategy_id, country_id)`
  (`generators/synthetic/manifest_loader.py:163`). The join key for every artifact in this
  plan — but **not a column in every artifact**: `generation_metadata` carries `model` and
  `method` instead, so its rows must have the slug reconstructed before joining.
- **generated:** the number of `persona_*` directories present in `01_Raw` for a
  combination *before* any validation — i.e. `validate_raw`'s `n_personas`, the attrition
  denominator.
- **raw_valid / mapped_valid:** personas with `passed=true` in `validate_raw/{slug}.csv`
  and `validate_mapped/{slug}.csv` respectively.
- **clean:** `raw_valid ∩ mapped_valid` — the eligible pool the cap draws from
  (`clean_available` in `CapSummary`).
- **selected:** the personas the seeded cap actually kept (`selected`), equal to
  `min(clean, requested_n)`.
- **under-cap cell:** a combination where `selected < requested_n`. Its downstream metrics
  are computed on fewer personas and are not comparable to full-n cells.
- **`truncated` (`CapSummary`) — a false friend.** It is `clean_available > n`
  (`population_cap/cap.py:189`), i.e. *the pool had surplus and was cut down to the cap* —
  the **opposite** of a shortfall. All seven under-cap Swedish combinations carry
  `truncated=false`. This plan therefore never surfaces the field under that name: the
  attrition CSV exposes it as `had_surplus`, and shortfall is `under_cap`.
- **retention rate:** `clean / generated` — the fraction of generated personas that survive
  both validators. The comparable quantity across combinations, since `generated` is not
  constant (150 → 549 in the current dataset).
- **generation multiplier:** `generated / selected` — how many personas had to be produced
  per persona actually analysed. The multiplier by which capped telemetry understates the
  true cost of a combination.
- **cost:** measured USD from `generation_metadata`, derived from logged tokens ×
  `config/analysis/model_pricing.yaml`. Never a projection, never a hardcoded rate. Emitted
  as a per-persona *distribution* (`cost_mean/std/median/q1/q3/n`), not a combination total,
  and — as shipped — measured over the **capped** personas only. See [Cost is measured on
  the capped mirror](#cost-is-measured-on-the-capped-mirror-blocking).
- **accuracy:** `overall_tv_similarity` from `{country}_performance.csv`. The plan
  introduces no new fidelity measure.
- **styled as a sibling:** uses the *same* ramp, text-contrast rule, colourbar, and
  provenance colouring **by calling the same functions**, not by re-specifying the values.

---

## Technical Design

### Approach

Three additions, deliberately placed by *what they read* rather than by what they show:

- **Item 1 belongs inside `model_ranking`.** It reads only that process's own result dict
  (`build_performance_comparison`), so it is a new chart function beside
  `plot_performance_heatmap`, not a new process. No DAG change.
- **Items 2 and 3 are cross-process joins**, so each becomes its own process with a
  declared `depends_on`, following the `realism_ranking → persona_realism` precedent —
  the only existing node whose upstream is another analysis node. This keeps every
  process's inputs declared rather than implicit. Note the declaration is **split across
  two files**: `config/analysis/analysis_registry.yaml` owns identity and dispatch
  (`label`, `description`, `folder`, `script`, `dispatch` — enforced by
  `analysis/utils/registry.py:41,87`), while `depends_on` is a **GUI workflow** key,
  required per task by `gui/workflow_state.py:38` and declared in
  `config/gui/flows/analysis_workflow.yaml` (`realism_ranking` at line 174). Adding
  `depends_on` to the registry would be an unknown key in the wrong file.

The `n` and under-cap marking on the item-1 heatmap is the honesty requirement that makes
the figure safe to present: the current `models_table` shows `llama31_8b` and two other
models on 7–49 personas with no indication, which reads as a model ranking when it is
sampling noise.

Per the pipeline-engineering guides (`02-architecture-principles-and-patterns.md`), each
new process is a **filter** with file inputs → DTO → metrics → artifacts, is **idempotent**
(re-running overwrites, never appends), and puts its **error boundary** at the read step:
a missing or schema-drifted upstream artifact raises with the offending path named, rather
than being silently skipped.

### The join key does not exist

`generation_metadata` does **not** emit a per-combination file with a slug. It writes one
per-country `{country}_summary.csv` (+ `.json`) whose rows are identified by two columns,
`model` and `method` (`generation_metadata/report_writer.py:83-97`, `:159`). Country lives
in the filename, not in a column. Nor does it emit combination *totals*: every metric in
`time, input_tokens, output_tokens, total_tokens, calls, retry_rate, error_rate, cost`
appears as six per-persona distribution columns `{metric}_{mean,std,median,q1,q3,n}`
(`combo_aggregator.py:37-52`), plus the scalars `latency_p95`, `latency_max`,
`success_rate`.

So the `cost_efficiency` join must:

1. **Reconstruct the slug** per row as `axis_slug(model, method, country)`
   (`manifest_loader.py:163`), the country coming from the filename the row was read from.
2. **First verify that `method` values are strategy ids.** If they are labels rather than
   ids, the reconstruction silently produces slugs that match nothing, and the join yields
   an empty frame rather than an error. The loader must assert every reconstructed slug is
   present in the accuracy side and raise naming the offenders otherwise.
3. **Derive, not read, any total.** "Cost per 100 personas" is `cost_mean × 100`; a
   combination total is `cost_mean × cost_n`. There is no summed field to read.

### Cost is measured on the capped mirror (blocking)

`generation_metadata` reads its persona telemetry from the **capped** mirror —
`resolve_stage_source(base)` → `03_Analysis/population_cap/`
(`generation_metadata/__init__.py:63,252`, `analysis/utils/capped_source.py:66-86`) — so its
cost, token and wall-clock statistics describe only the ~100 *selected* personas, never the
full generated pool. Measured on disk, that gap is large and systematic:

| Combination | generated | selected | understatement |
|---|---|---|---|
| `…_all_generate_evaluate_random_pick_v2_openrouter_qwen35_flash` | 549 | 100 | 5.5× |
| `…_all_generate_pick_v2_ollama_deepseek_r1_14b` | 370 | 119 | 3.1× |

The error is **not** uniform noise: it is largest exactly where retention is worst, so a
cost-efficiency figure built naively on capped telemetry **flatters the models that wasted
the most tokens** — the precise inversion of what the figure is for. Two ways out, and
Phase 5 is blocked until one is chosen:

- **(a) Point the cost aggregate at the full pool.** Give `generation_metadata` (or a
  cost-only reader inside `cost_efficiency`) a documented read of `01_Raw` telemetry for the
  cost metrics, leaving the capped mirror as the source for everything the analysis
  population is defined by. Truest, but touches a shipped process's read contract.
- **(b) Carry the generation multiplier through the join** and plot **cost per usable
  persona** = `cost_mean × (generated / selected)`, taking `generated` and `selected` from
  the Phase 4 attrition CSV. Cheaper and needs no upstream change, but it *estimates* the
  discarded personas' cost as equal to the kept ones' mean — an assumption that must be
  stated on the figure, and one that is wrong in the direction of under-costing if failed
  personas are cheaper (short, truncated) or over-costing if they are retry-heavy.

Whichever is chosen, the figure and the JSON must state which, so a reader can never mistake
capped-mirror cost for run cost.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Item 1 as a new chart in `model_ranking` | Reads only existing in-process data; no DAG change; ships with every rank run | Grows an already large `charts.py` | **Chosen** |
| Item 1 as its own process | Symmetric with items 2–3 | Would re-read and re-derive `performance.json` for no reason; a process per figure does not scale | Rejected |
| Item 2 inside `generation_metadata` | Cost data already local | Would make the LLM-metrics task depend on fidelity, inverting the natural direction and coupling two unrelated concerns | Rejected |
| Item 2 inside `model_ranking` | Accuracy already local | Forces `model_ranking` to depend on `generation_metadata`, so fidelity ranking could no longer run without LLM telemetry — a real regression for any dataset lacking it | Rejected |
| Item 2 as new `cost_efficiency` process | Both inputs declared; either upstream can run alone; matches `realism_ranking` precedent | One more registry entry, one more workflow task, and a script | **Chosen** |
| Item 3 inside `population_cap` | It already computes every count | `population_cap` is `dispatch: per_combo`; a cross-combo figure would be redrawn once per combo and blurs its single-combo contract | Rejected |
| Item 3 as new `validation_attrition` process | Naturally batch/cross-combo; leaves the gate's per-combo contract intact | One more registry entry and workflow task | **Chosen** |
| Item 3 joining `validate_raw/_summary.csv` for the denominator | No change to `cap.py` | Denominator lives in a different process's summary; the two can drift if one is re-run, and *the drift is undetectable* — see the row below | Rejected as *sole* source — see `raw_total` below |
| Add `raw_total` to `CapSummary` | The only independent observation of the raw pool at cap time — see below | Touches a shipped DTO (additive only); requires a gate re-run to backfill | **Chosen** |

**Why `raw_total` is not redundant.** The obvious objection is that `CapSummary.raw_passed`
already cross-checks `validate_raw/_summary.csv`, so a second denominator adds nothing. It
does not: `raw_passed` is `len(read_passed_ids(validate_raw/{slug}.csv))`
(`population_cap/cap.py:254`), i.e. it is *read out of the validator's own output*. So
`raw_passed == passed` is a **tautology** — verified across all 50 Swedish combinations, zero
mismatches — and it can never detect a raw pool that grew or shrank after validation ran.
`raw_total`, globbed from the raw dirs at cap time, is the only independent observation of
the pool, and `raw_total != n_personas` is the only signal that the gate's two halves saw
different data. That is the reason for the field, and the cross-check the Phase 4 loader
should perform.

### Architecture & Module Contracts

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `model_ranking/table_style.py` *(new)* | The shared visual grammar of the manuscript-style grids: ramp, text-contrast rule, colourbar, best-cell boxing, category header | style params → matplotlib primitives | Which metric is plotted; country; model/strategy names; file paths |
| `model_ranking/charts.py::plot_model_method_heatmap` *(new)* | Draw overall TV-similarity as model × method, with `n` and under-cap marking | `result` dict + out path → PNG/SVG paths | How TV was computed; cost; the gate |
| `cost_efficiency/loader.py` *(new)* | Read accuracy and cost, **reconstruct the slug on the cost side** (`axis_slug(model, method, country)`), join, and fail loudly on either side missing or on an unmatched `method` | `model_ranking` + `generation_metadata` + `validation_attrition` dirs → list of DTOs | matplotlib; layout; colours |
| `cost_efficiency/charts.py` *(new)* | Render accuracy-vs-cost per model × method | DTOs → PNG/SVG | File discovery; which country; JSON schema |
| `cost_efficiency/report.py` *(new)* | Emit tidy CSV + JSON with provenance | DTOs → CSV/JSON paths | Plot styling |
| `validation_attrition/loader.py` *(new)* | Read the gate's persisted counts into one DTO per combo; derive retention rate and generation multiplier | `population_cap/_index.json` (+ the two `_summary.csv`) → DTOs | matplotlib; which figure |
| `validation_attrition/charts.py` *(new)* | Render the attrition chain per combination, and mapped-validity as a model × method grid | DTOs → PNG/SVG | File discovery; country |
| `validation_attrition/report.py` *(new)* | Emit tidy CSV + JSON with provenance | DTOs → CSV/JSON paths | Plot styling |
| `population_cap/cap.py::CapSummary` *(changed)* | Additionally record `raw_total` | unchanged inputs → `CapSummary` + `raw_total` | Charts; any consumer |

```
src/population_synthetic/analysis/
├── model_ranking/
│   ├── charts.py                 # + plot_model_method_heatmap()
│   ├── manuscript_tables.py      # imports from table_style (helpers extracted, behaviour identical)
│   └── table_style.py            # NEW: inferno cmap, text-contrast, colourbar, best-cell box
├── cost_efficiency/              # NEW process
│   ├── __init__.py
│   ├── loader.py
│   ├── charts.py
│   └── report.py
├── validation_attrition/         # NEW process
│   ├── __init__.py
│   ├── loader.py
│   ├── charts.py
│   └── report.py
└── population_cap/cap.py         # CapSummary gains raw_total

scripts/analyze/
├── analyze_cost_efficiency.py        # NEW
└── analyze_validation_attrition.py   # NEW
```

**The declaration is split across two files.** The registry owns identity and dispatch; the
GUI flow owns the DAG edges. Both must be edited, and each has its own required-key set that
fails loudly when incomplete.

Registry additions — under `processes:` in `config/analysis/analysis_registry.yaml`. Required
keys are exactly `label`, `description`, `folder`, `script`, `dispatch`
(`analysis/utils/registry.py:41`, validated at `:87`); `legacy_folder` is the only optional
key, and **`depends_on` is not a registry key at all**:

```yaml
  cost_efficiency:
    label: "Cost Efficiency (accuracy vs token cost)"
    description: >-
      Joins model_ranking fidelity with generation_metadata token/USD telemetry per
      model x method and emits an accuracy-vs-cost figure, tidy CSV and JSON report.
    folder: cost_efficiency
    script: scripts/analyze/analyze_cost_efficiency.py
    dispatch: slugs

  validation_attrition:
    label: "Validation Attrition (personas discarded per gate stage)"
    description: >-
      Per-combination attrition chain (generated -> raw-valid -> mapped-valid -> clean ->
      selected) with retention rate and generation multiplier, from the gate's own records.
    folder: validation_attrition
    script: scripts/analyze/analyze_validation_attrition.py
    dispatch: slugs
```

Workflow additions — in `config/gui/flows/analysis_workflow.yaml`, where `depends_on` lives.
Every task requires all seven of `label`, `script`, `dispatch`, `enabled`, `bypass`,
`options`, `depends_on` (`gui/workflow_state.py:38`); the precedent for an analysis-node
upstream is `realism_ranking`'s `depends_on: [persona_realism]` at line 174:

```yaml
  validation_attrition:
    label: "Validation Attrition"
    script: scripts/analyze/analyze_validation_attrition.py
    dispatch: slugs
    enabled: false
    bypass: false
    options: {}
    depends_on: [population_cap]

  cost_efficiency:
    label: "Cost Efficiency"
    script: scripts/analyze/analyze_cost_efficiency.py
    dispatch: slugs
    enabled: false
    bypass: false
    options: {}
    depends_on: [model_ranking, generation_metadata, validation_attrition]
```

`cost_efficiency` declares `validation_attrition` as an upstream because it consumes the
attrition CSV for `generated`/`selected` (the under-cap flag, and the generation multiplier
if option (b) above is chosen).

**Config-is-source-of-truth obligations.** No new figure may hardcode a model list, a
strategy order, a colour ramp value, or an attribute list. Strategy order comes from
`analysis/utils/axes.py::strategy_complexity_order`; hosted/local provenance from
`config/analysis/model_ranking/provider_hosting.json` via `classify_hosting`; pricing from
`config/analysis/model_pricing.yaml`; output folders from `analysis_output_dir(id, base)`.

---

## Implementation Plan

### Phase 1: Extract the shared table style
**Goal:** One definition of the manuscript grid's visual grammar, so item 1 matches its
siblings by construction rather than by copy.

- [ ] Task 1.1 — Create `model_ranking/table_style.py`; move `_inferno_cmap`,
      `_text_color_for_rgb`, `_add_percentage_colorbar`, `_best_cells_per_column`,
      `_overall_divider`, `_categories_on_top` into it as public functions.
- [ ] Task 1.2 — Re-point `manuscript_tables.py` at the new module; the rendered output must
      be unchanged.
- [ ] Task 1.3 — Characterisation test: **extend the existing `tests/test_manuscript_tables.py`**
      (373 lines, 15 tests, already covering the PNG+SVG pair, the global-best-strategy title,
      provenance row-label colours, categories-on-top and LaTeX shape) rather than adding a
      new file. Assert *structural* properties — cell values, ordering, chosen colours,
      contrast decisions, artifact set — not byte equality: matplotlib PNGs are not stable
      across metadata and font hinting, so a byte comparison fails for reasons unrelated to
      the refactor.

**Files Modified:**
- `src/population_synthetic/analysis/model_ranking/table_style.py` — new
- `src/population_synthetic/analysis/model_ranking/manuscript_tables.py` — import from it
- `tests/test_manuscript_tables.py` — extended with the characterisation assertions

**Dependencies:** None

### Phase 2: Model × method fidelity heatmap
**Goal:** Item 1 shipped as a `model_ranking` artifact.

- [ ] Task 2.1 — `plot_model_method_heatmap(result, out_path)` in `charts.py`: rows =
      models ordered by their mean across methods, columns = methods in
      `strategy_complexity_order`, cell = `overall_tv_similarity × 100`.
- [ ] Task 2.2 — **Source `requested_n`.** It is *not* in the `model_ranking` result:
      `build_performance_comparison` gives `combos[slug]["n"]` (`builder.py:188`, from the
      capped mapped file) but no `requested_n`, which exists only in
      `population_cap/_index.json`. Read it from that index — `model_ranking/loader.py:179-182`
      already resolves and reads the sibling `_mapped/_index.json`, so this is the same
      directory and no new dependency direction. Fail loudly if the index is missing or an
      entry lacks the key; never assume the cap.
- [ ] Task 2.3 — Annotate each cell with its value and `n`; mark cells where
      `n < requested_n`; colour model tick labels by `classify_hosting`.
- [ ] Task 2.4 — Add the row-mean (per model) and column-mean (per method) marginals,
      visually separated from the grid so they cannot be read as cells.
- [ ] Task 2.5 — Emit PNG **and** SVG **via `analysis/utils/figures.py::save_figure`**, which
      writes the `.svg` sibling. Note every existing function in `charts.py` calls
      `fig.savefig` directly and is therefore PNG-only (`charts.py:111,168,247,310`); only
      `manuscript_tables.py` uses the helper. Do not copy the `charts.py` pattern here.
- [ ] Task 2.6 — Wire into `rank_models.py` behind the existing `--no-charts` flag; update
      the script docstring's output list. (That list is already stale — it omits the
      `{country}_c2st_vs_tv.png` written at `rank_models.py:295-299`; fix while there.)
- [ ] Task 2.7 — Name the artifact to conform to
      `docs/development/plans/pending/uniform-analysis-output-naming.md`, and make the title
      distinguish it from the two figures it will sit beside — see the Risks table.

**Files Modified:**
- `src/population_synthetic/analysis/model_ranking/charts.py` — new plot function
- `scripts/analyze/rank_models.py` — call + docstring
- `tests/test_model_ranking_charts.py` — value/order/marking assertions

**Dependencies:** Phase 1. Task 2.2 reads `population_cap/_index.json`, but `requested_n` is
**already present in every entry today** (verified on disk: `requested_n: 100` across all 50
`swedish_02` entries). Phase 2 therefore does *not* wait on Phase 3 — `raw_total` is an
attrition-only field and no backfill is required for the heatmap.

### Phase 3: `raw_total` in the cap record
**Goal:** A single authoritative attrition denominator.

- [ ] Task 3.1 — Add `raw_total: int` to `CapSummary`. The count already exists but is
      discarded: `cap_combo` does **not** call `_sorted_persona_dirs` directly — it calls
      `_clean_persona_dirs` (`cap.py:77-79`) at `cap.py:177`, and *that* is where
      `_sorted_persona_dirs` (`cap.py:69-74`) enumerates the full raw pool before filtering.
      Return the pre-filter length from there rather than re-globbing.
- [ ] Task 3.2 — Include it in the `population_cap/_index.json` entry.
- [ ] Task 3.3 — Treat a legacy entry without `raw_total` as a fail-fast read in the
      Phase 4 loader (re-run the gate), not as a silent zero.
- [ ] Task 3.4 — **Backfill.** Task 3.3 means the existing 50 `swedish_02` index entries are
      unreadable by Phase 4 until `population_cap` is re-run for every combination, which
      regenerates the capped persona mirror and `_mapped/` — the inputs every other analysis
      process reads. Before running it, confirm and record in this plan that selection is
      deterministic: the cap is seeded (`seed: 0`) over the clean id set, so an unchanged
      clean pool must reproduce the identical `selected_ids`. Verify by diffing
      `selected_ids` for a sample of combinations before/after; if they differ, stop — the
      backfill would silently move every downstream number.

**Files Modified:**
- `src/population_synthetic/analysis/population_cap/cap.py` — DTO + population
- `scripts/analyze/cap_populations.py` — index entry
- `tests/test_population_cap.py` — asserts `raw_total` equals the raw dir count, and that
  `raw_total >= raw_passed`

**Dependencies:** None for the code (parallel with Phases 1–2); only Phase 4 waits on the
Task 3.4 backfill run

### Phase 4: `validation_attrition` process
**Goal:** Item 3 shipped — the discarded-persona story becomes an artifact.

- [ ] Task 4.1 — `validation_attrition/loader.py`: read `population_cap/_index.json`
      (+ the two `_summary.csv` for cross-check) into one DTO per combination; raise on a
      slug present in one source and absent from another, and on `raw_total != n_personas`
      (the one genuine staleness signal — see the `raw_total` note above). Do **not**
      cross-check `raw_passed` against `validate_raw`'s `passed`: that equality is a
      tautology and proves nothing.
- [ ] Task 4.2 — `charts.py`: per-combination attrition chart
      (generated → raw_valid → mapped_valid → clean → selected), under-cap combinations
      marked, sorted worst-retention first. **Plot the retention rate, not bare counts**, or
      normalise each chain to its own `generated`: with denominators spanning 150 → 549 the
      absolute bars are not comparable across combinations and invite exactly the wrong
      reading. Show `generated` and the generation multiplier as annotations so the varying
      pool size is visible rather than hidden by the normalisation.
- [ ] Task 4.3 — Emit `{country}_attrition.csv` (tidy, one row per combination, columns per
      the Success Criteria — counts **plus** `retention_rate`, `generation_multiplier`,
      `under_cap`, `had_surplus`) and `{country}_attrition.json` with provenance.
- [ ] Task 4.4 — Second figure: **mapped-validity as a model × method grid**, on the same
      layout as the Phase 2 heatmap. 47 of 50 combinations lose personas at
      `validate_mapped`, with pass rates down to 4.7% — the pattern is a property of the
      model/method pair and is a reportable result, not just a caveat. Reuse
      `table_style.py` from Phase 1.
- [ ] Task 4.5 — `scripts/analyze/analyze_validation_attrition.py` entry point; add the
      registry entry (no `depends_on`) **and** the `analysis_workflow.yaml` task with
      `depends_on: [population_cap]`, per the two snippets above.

**Files Modified:**
- `src/population_synthetic/analysis/validation_attrition/` — new package
- `scripts/analyze/analyze_validation_attrition.py` — new
- `config/analysis/analysis_registry.yaml` — new entry (5 required keys, no `depends_on`)
- `config/gui/flows/analysis_workflow.yaml` — new task (7 required keys, incl. `depends_on`)
- `tests/test_validation_attrition.py` — new

**Dependencies:** Phase 3, including the Task 3.4 backfill run

### Phase 5: `cost_efficiency` process
**Goal:** Item 2 shipped — accuracy joined to measured cost.

**Blocked until the capped-cost question is decided** — pick option (a) or (b) from [Cost is
measured on the capped mirror](#cost-is-measured-on-the-capped-mirror-blocking) and record the
choice here before starting. Everything below assumes it has been made.

- [ ] Task 5.0 — Run `generation_metadata` on `swedish_02` (it has never been run; the folder
      does not exist on disk) and pin its actual column names into a fixture before writing
      the loader against them.
- [ ] Task 5.1 — `cost_efficiency/loader.py`: join `{country}_performance.csv` against
      `generation_metadata/{country}_summary.csv`. There is **no slug column on the cost
      side** — reconstruct it per row as `axis_slug(model, method, country)`, having first
      asserted that `method` values are strategy ids (raise, naming the unmatched values, if
      any reconstructed slug is absent from the accuracy side). Raise a named
      missing-input error identifying the absent process when either side is missing for the
      country. There are no per-combo totals: derive them as `cost_mean × cost_n`.
- [ ] Task 5.2 — Carry `n`, `requested_n`, the under-cap flag and the generation multiplier
      through the join from the Phase 4 attrition CSV rather than re-deriving them.
- [ ] Task 5.3 — `charts.py`: accuracy (y) vs cost per 100 personas (x, log scale), marker
      shape = method, colour = hosted/local, per-model labelling; a second panel or facet
      showing tokens instead of USD for the local models priced at zero
      (`model_pricing.yaml:51-59` sets `{in: 0, out: 0}` for all nine `ollama_*` models, so
      the zero case is the norm for a third of the axis, not an edge case). Under-cap points
      must be visually distinguished. Whichever capped-cost option was chosen must be stated
      on the figure itself.
- [ ] Task 5.4 — Emit `{country}_cost_efficiency.csv` + `.json`. Provenance must record the
      pricing `observed_date`, `source` and `currency`, **and** the caveats carried in the
      pricing file itself: rows flagged `[VERIFY]` and those marked "effective/discounted"
      (e.g. `openrouter_deepseek_v4`, `openrouter_glm_52`, `openrouter_qwen37_max`) are not
      list prices. A publication figure must not present them as settled.
- [ ] Task 5.5 — Entry point; registry entry (no `depends_on`) **and** the
      `analysis_workflow.yaml` task with
      `depends_on: [model_ranking, generation_metadata, validation_attrition]`.

**Files Modified:**
- `src/population_synthetic/analysis/cost_efficiency/` — new package
- `scripts/analyze/analyze_cost_efficiency.py` — new
- `config/analysis/analysis_registry.yaml` — new entry (5 required keys, no `depends_on`)
- `config/gui/flows/analysis_workflow.yaml` — new task (7 required keys, incl. `depends_on`)
- `tests/test_cost_efficiency.py` — new

**Dependencies:** Phases 3–4 (for the under-cap flag and the generation multiplier), a
`generation_metadata` run for the target country, and a decision on the capped-cost question.

---

## Testing Plan

### Unit Tests
- [ ] `table_style` helpers return the same colours/contrast decisions as the pre-extraction
      private functions (characterisation, in the existing `tests/test_manuscript_tables.py`;
      structural assertions, not byte equality).
- [ ] `plot_model_method_heatmap` cell matrix equals the `performance.csv` values for the
      same `(model, strategy)`.
- [ ] Method column order equals `strategy_complexity_order`; model row order is by
      descending row mean; both are deterministic for a fixed input.
- [ ] Under-cap marking fires iff `n < requested_n` (boundary: `n == requested_n` unmarked),
      with `requested_n` sourced from `population_cap/_index.json`; the heatmap raises rather
      than guessing when that index or the key is missing.
- [ ] The new heatmap emits both `.png` and `.svg` (guards against the `fig.savefig`
      PNG-only pattern used elsewhere in `charts.py`).
- [ ] `CapSummary.raw_total` equals the number of `persona_*` dirs in the fixture, and
      `raw_total >= raw_passed` holds.
- [ ] Attrition loader raises on a slug present in `_index.json` but absent from a
      `_summary.csv`, on a legacy entry lacking `raw_total`, and on
      `raw_total != n_personas`.
- [ ] Attrition `retention_rate` and `generation_multiplier` are correct for a fixture with
      unequal denominators (not all combos at 150).
- [ ] `cost_efficiency` loader raises a message naming `generation_metadata` when its
      folder is absent, and raises naming the offending values when a `method` value does
      not reconstruct to a known slug.

### Integration Tests
- [ ] Full gate on a small fixture: `validate_raw → mapping → validate_mapped →
      population_cap → validation_attrition` produces an attrition CSV whose `selected`
      equals the capped mapped file's `n` for every combo.
- [ ] `rank_models.py` on a fixture emits the new heatmap alongside the existing artifacts
      and leaves the existing ones unchanged.
- [ ] `config/gui/flows/analysis_workflow.yaml` still loads and topologically sorts with the
      two new tasks present, and every task retains all seven required keys.
- [ ] `config/analysis/analysis_registry.yaml` still loads with the two new entries — a guard
      against the omitted-`description` / stray-`depends_on` failure mode this revision fixes.

### Manual Verification
- [ ] Run all three on `swedish_02`; open each figure and confirm no label collisions,
      no clipping, and legible cell text at slide size.
- [ ] Confirm the attrition figure identifies exactly the seven known under-cap Swedish
      combinations: `ollama_llama31_8b` on all five methods, plus
      `ollama_gemma4_e4b` and `ollama_deepseek_r1_14b` on `all_generate_evaluate_random_pick_v2`
      (selected 7, 9, 11, 19, 22, 34, 49).
- [ ] Confirm the mapped-validity grid shows 47 of 50 combinations below 100%.
- [ ] Confirm the model × method heatmap reproduces the hand-made deck figure's values.
- [ ] Confirm the Task 3.4 backfill left `selected_ids` unchanged for a sample of
      combinations, so no downstream number moved.

### Edge Cases
- [ ] A country where `generation_metadata` was never run → `cost_efficiency` fails loudly;
      the other two still run.
- [ ] A combination with `clean_available = 0` (empty capped output) → attrition row shows
      `selected=0` without dividing by zero.
- [ ] A model priced at zero (local) → cost axis handles 0 on a log scale explicitly
      (tokens panel), never silently drops the point.
- [ ] A grid with a missing `(model, method)` cell → rendered as the ramp's `set_bad` grey,
      never as 0.

---

## Documentation Plan

- [ ] Update `CLAUDE.md`: add `cost_efficiency` and `validation_attrition` to the
      analysis-family paragraph and the DAG description.
- [ ] Update `docs/architecture/sub-packages.md` with the two new subpackages.
- [ ] Update `docs/architecture/commands.md` with the two new script invocations.
- [ ] Update `docs/architecture/configuration.md` with the new registry entries **and** the
      two new `analysis_workflow.yaml` tasks.
- [ ] Update `docs/development/gui.md` with the two new workflow nodes and their
      `depends_on` edges.
- [ ] Update `scripts/analyze/rank_models.py` docstring output list (Phase 2), including the
      pre-existing omission of `{country}_c2st_vs_tv.png`.
- [ ] Record in `CLAUDE.md` / `docs/architecture/sub-packages.md` that `generation_metadata`
      reads the **capped mirror** — its module, script and registry descriptions still say
      `01_Raw`, and the constant `_RAW_STAGE_DIR` is dead. Correcting that text is cheap and
      prevents the exact misreading this plan's cost analysis had to untangle.

---

## Rollback Plan

1. **Phases 4–5 (new processes):** delete the two subpackages, the two scripts, the two
   registry entries **and the two `analysis_workflow.yaml` tasks**. Nothing else reads them,
   so removal is clean — but leaving a workflow task whose script is gone would break the
   flow, so both files must be reverted together.
2. **Phase 2 (new chart):** remove the call from `rank_models.py` and the function; existing
   artifacts are untouched.
3. **Phase 1 (extraction):** revert the commit; `manuscript_tables.py` returns to private
   helpers. The characterisation test demonstrates structural equivalence either way (it
   asserts rendered properties, not bytes).
4. **Phase 3 (`raw_total`):** additive to a DTO and to `_index.json`. Reverting leaves
   existing index files with a harmless extra key; no consumer requires it once Phase 4 is
   also reverted. The Task 3.4 backfill is **not** revertible in the same sense — it rewrites
   the capped mirror — which is why it must be shown to be selection-identical first.
5. **Data:** no migration, no destructive write. Every process here only reads existing
   artifacts and writes into its own `03_Analysis/{folder}/`.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Style extraction silently changes the shipped manuscript tables | Med | High | Characterisation assertions added to `tests/test_manuscript_tables.py` in Phase 1, on rendered structure rather than bytes, before any new figure is built |
| **Cost figure understates spend 3–5×, worst for the worst models** (capped-mirror telemetry) | **Certain if unaddressed** | **High** | Phase 5 blocked until option (a) or (b) is chosen; the chosen basis is stated on the figure and in the JSON |
| `generation_metadata` schema differs from what the join assumes (it has never been run) | High | Med | Task 5.0 runs it on `swedish_02` and pins the actual column names in a fixture; loader fails loudly on drift |
| `method` values are labels, not strategy ids, so slug reconstruction silently matches nothing | Med | High | Loader asserts every reconstructed slug exists on the accuracy side and raises naming the unmatched values; an empty join is never a valid result |
| Cost figure implies measured cost for local models priced at 0 | Med | High | Separate tokens panel; USD panel labelled as API cost only; pricing `observed_date`, `source` and the `[VERIFY]`/discounted-rate caveats recorded in the JSON |
| Attrition denominators drift between `validate_raw/_summary.csv` and `_index.json` | Med | Med | `raw_total` is the only independent observation (`raw_passed` is a tautology); loader raises on `raw_total != n_personas` rather than picking one |
| Attrition bars read as cross-combination comparisons despite 150→549 denominators | High | Med | Plot retention rate / per-chain normalisation; annotate `generated` and the generation multiplier on every row |
| Reader confuses three heatmaps in one folder | Med | Med | `{country}_heatmap.png` already exists (`charts.py:52`, combos × attributes, viridis); the new figure is model × method overall, and `models_table` is per-attribute at one strategy. Distinct titles/subtitles, and names conforming to `uniform-analysis-output-naming.md` |
| Registry entry rejected at load (missing `description`, or `depends_on` in the wrong file) | Med | High | Both files edited per the two snippets above; config-load tests in the Integration section cover each |
| Adding two workflow tasks breaks the GUI DAG | Low | High | Both declare `depends_on` in `analysis_workflow.yaml`; workflow-config test asserts the DAG still topologically sorts |
| Task 3.4 backfill silently changes the analysis population | Low | High | Verify `selected_ids` are byte-identical before/after for a sample; stop the backfill if not |

---

## Timeline

Recommended order is **1 → 2 → 3 → 4 → 5**. Phases 1–2 are self-contained and ship without
any pipeline event; Phase 3's backfill gates only Phase 4, and Phase 5 consumes Phase 4's
attrition CSV. Phases 1–2 and Phase 3 are independent and may run in parallel.

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — extract table style | 0.5 day | None |
| Phase 2 — model × method heatmap | 1 day | Phase 1 |
| Phase 3 — `raw_total` | 0.25 day code + a full gate re-run (Task 3.4) | None for code |
| Phase 4 — `validation_attrition` | 1 day (+0.25 for the mapped-validity grid) | Phase 3 incl. backfill |
| Phase 5 — `cost_efficiency` | 1.5 days | Phases 3–4, a `generation_metadata` run, and the capped-cost decision |

The Phase 3 gate re-run regenerates the capped mirror and `_mapped/` that every other analysis
process reads, so schedule it as a pipeline event rather than a code change, and confirm
selection determinism before it runs. It does **not** block Phases 1–2.

---

## References

- Hand-made prototype of item 1 (external, outside git):
  `40_llm-population-fidelity-benchmark/figures/swedish_02_model_method_tv_heatmap.py`
- Cross-process precedent: `realism_ranking` — `depends_on: [persona_realism]`, declared in
  `config/gui/flows/analysis_workflow.yaml:174`, **not** in the analysis registry
- Key contracts: `analysis/utils/registry.py:41,87` (registry required keys);
  `gui/workflow_state.py:38` (workflow required task keys);
  `analysis/utils/capped_source.py:66-86` (capped-mirror read);
  `generators/synthetic/manifest_loader.py:163` (`axis_slug`)
- Stale cost source superseded by item 2: `docs/development/swedish-token-cost-by-model.md`
- Engineering guides: `docs/data-pipeline-engineering/` (`02` design checklist, `03`
  statistical software, `05` craftsmanship)
- Related plan: `docs/development/plans/pending/uniform-analysis-output-naming.md`
