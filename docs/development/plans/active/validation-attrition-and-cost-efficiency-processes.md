# Plan: `validation_attrition` and `cost_efficiency` analysis processes

**Date:** 2026-08-20
**Author:** Basil
**Status:** In Progress
**Base Branch:** `dev`
**Branch:** `feature/validation-attrition-and-cost-efficiency`

> **Supersedes** `docs/development/plans/pending/pipeline-model-method-cost-and-attrition-figures.md`
> (2026-08-11, "Revised"). That plan's items 1–2 shipped as
> `completed/model-method-tv-heatmap.md` (`model_ranking/table_style.py`,
> `charts.py::plot_model_method_heatmap`). Its items 3–5 are the unfinished tail and are
> restated here, corrected for the full-N exclusion rule that landed after it was written.
> Task 0.1 moves the superseded document to `archived/`.

> **Prerequisite — not a soft dependency.** `CapSummary.excluded` and `exclusion_reason` exist
> only on `feature/enforce-full-n-cap-exclusion`; `git show dev:.../population_cap/cap.py` has
> neither. `validation_attrition` reports withdrawals and cannot compile against `dev` until that
> branch merges. Branch from `dev` **after** the merge.

---

## Overview

Two figures the deck and the manuscript rely on — the mapping-survival heatmap (F05) and the
cost-vs-fidelity scatter (F26) — are hand-built over pipeline CSVs with no generator in the
repository. They therefore go stale **silently** on every re-run: the numbers underneath them move
and the images do not. This plan adds the two analysis processes that emit them as first-class
artifacts, `validation_attrition` and `cost_efficiency`, so both refresh by copy like every other
staged figure.

## Problem Statement

Every other figure in `figures selection` is refreshed by copying an artifact some analysis process
wrote. F05 and F26 cannot be, because no process writes them:

- **Attrition is invisible.** `validate_raw` and `validate_mapped` each compute `pass_rate_pct`
  into a `_summary.csv` and stop; neither package contains a single `savefig` call. The gate
  discards personas at three points and nothing renders the chain. The current staged F05 predates
  the full-N rule, so its two headline percentages are wrong (gemma4_e4b 4.7 → 6.0, deepseek_r1_14b
  6.0 → 6.7) and three of its cells are now *withdrawn* combinations rather than merely thin ones.
- **Cost-vs-fidelity has no join at all.** `grep -rniE "cost_vs|vs_fidelity|cost_per_100|frontier|pareto"`
  over `src/` and `scripts/` returns nothing. `generation_metadata/charts.py` has 14 chart
  functions, every one plotting cost or telemetry *alone*; nothing pairs a cost metric with
  `overall_tv_similarity`. The staged F26 still shows the superseded 8-model sweep.
- **Withdrawals are unreported.** The full-N rule withdraws 7 of 65 `swedish_02` combinations, and
  `enforce-full-n-cap-exclusion.md` names this feature as the mitigation: *"the shortfall counts
  remain in `population_cap/_index.json`, so attrition can be reported separately."*
  `validation_attrition` becomes the **only** artifact that surfaces an excluded combination.

## Goals

### In Scope

1. A new **`validation_attrition`** process: reads the gate's persisted records, emits a
   per-combination attrition funnel figure, a mapped-validity model × method grid (the F05
   replacement), and a tidy CSV carrying the five counts plus the derived rates.
2. A new **`cost_efficiency`** process: joins `model_ranking` accuracy with LLM cost telemetry into
   an accuracy-vs-cost figure per model × method (the F26 replacement), plus a tidy CSV and a JSON
   report carrying the cost-basis provenance.
3. `CapSummary` gains `raw_total` — the only independent observation of the generated pool.
4. A cost reader over the **full generated pool** (`01_Raw`), so cost is not measured on the capped
   mirror. See [The cost denominator](#the-cost-denominator).
5. Both processes registered in `config/analysis/analysis_registry.yaml` and added as tasks to
   `config/gui/flows/analysis_workflow.yaml`.

### Out of Scope

- Multi-country comparison of attrition or cost. Every artifact here is per-country.
- Changing how any existing statistic is computed. Both processes are read-only over existing
  artifacts, except for the additive `raw_total` field.
- Re-pricing models or editing `config/analysis/model_pricing.yaml`.
- Restaging the deck figures themselves — that is a follow-on copy step, noted in Phase 6.
- A shared "cross-combination process framework". Two processes do not justify one
  (`05` §6, YAGNI).

## Success Criteria

- [ ] `python scripts/analyze/analyze_validation_attrition.py --country swedish_02` writes
      `{country}_attrition.csv`, `{country}_attrition.json`, and both figures under
      `03_Analysis/validation_attrition/`.
- [ ] The attrition CSV has one row per combination in `population_cap/_index.json` — **65 rows for
      `swedish_02`, not 58** — because the withdrawn combinations are the point of the figure.
- [ ] For each of the 7 withdrawn combinations the row reads `excluded=true`, a non-empty
      `exclusion_reason`, `selected=0`, `generation_multiplier` populated, and
      `cost_per_usable_persona` computable.
- [ ] `retention_rate` for `all_generate_evaluate_random_pick_v2 × ollama_gemma4_e4b` equals
      `9/150 = 0.06`, matching `validate_mapped/_summary.csv → pass_rate_pct = 6.0`.
- [ ] `python scripts/analyze/analyze_cost_efficiency.py --country swedish_02` writes
      `{country}_cost_efficiency.{csv,json}` and the scatter under `03_Analysis/cost_efficiency/`.
- [ ] Every row of the cost join is matched on both sides; an unmatched `model`/`method` on either
      side raises, naming the offending key and both files. An empty join is never a valid result.
- [ ] The cost figure and the JSON both state the cost basis verbatim; the basis is a CSV **column**,
      not only prose.
- [ ] `pytest` passes, including a hand-computed funnel fixture and an unmatched-key fixture that
      must raise.
- [ ] `ruff check src/` clean.

## Definitions

Pinned because the plan's correctness depends on them and the old plan drifted on two.

- **generated**: `CapSummary.raw_total` — the count of `persona_*` directories globbed from `01_Raw`
  at cap time. *Not* `validate_raw/_summary.csv → n_personas`; see [Why `raw_total`](#why-raw_total-is-not-redundant).
- **raw_valid**: `CapSummary.raw_passed`. **mapped_valid**: `CapSummary.mapped_passed`.
- **clean**: `CapSummary.clean_available` — personas passing *both* gates.
- **selected**: `CapSummary.selected`. **Zero for every excluded combination**, by design.
- **retention_rate**: `clean / generated`, float. `None` (empty cell) when `generated == 0`.
- **generation_multiplier**: `generated / clean` — personas generated per *usable* persona.
  **Deliberately not `generated / selected`**, which divides by zero on all 7 withdrawn
  combinations. `None` when `clean == 0`.
- **excluded**: `CapSummary.excluded`. Distinct from thinness: a combination is excluded when
  `clean < requested_n`.
- **had_surplus**: `CapSummary.truncated`. A false friend — it means `clean_available > n` (surplus
  cut down), **not** shortfall. Renamed in the tidy CSV so it cannot be misread.
- **cost basis**: which persona population a cost figure is measured over. Two are possible —
  the full generated pool, or the ~100-persona capped mirror. Always a named column.
- **cost_per_usable_persona**: `total_cost_usd_over_generated_pool / clean`. `None` when
  `clean == 0`; `0.0` only when the model is genuinely unmetered.
- **unmetered**: a model whose `model_pricing.yaml` entry is `{in: 0, out: 0}`. Nine `ollama_*`
  models are unmetered — about a third of the axis. Distinct from *absent* pricing, which raises.

---

## Technical Design

### Approach

Two sibling processes, each `dispatch: slugs`, each following the `realism_ranking` shape:
`loader.py` (read + validate the on-disk contract) → `builder.py` (pure derivation) →
`charts.py` (render only, returns Figures; the driver saves). `__init__.py` is docstring-only.

`validation_attrition`'s tidy CSV is a **declared input** to `cost_efficiency`, not a sibling
artifact. This is not convenience: the generation multiplier that `validation_attrition` computes
is precisely the factor that corrects a capped-mirror cost figure, so making it an input puts the
correction and the correction's source in one dependency edge rather than two places that can drift.

### The cost denominator

`generation_metadata` reads its telemetry from the **capped mirror** —
`generation_metadata/__init__.py:252` calls `resolve_stage_source(base)` → `03_Analysis/population_cap/`
— so its cost statistics describe only the ~100 selected personas. Measured on disk the gap reaches
5.5× (`…_random_pick_v2_openrouter_qwen35_flash`: 549 generated, 100 selected). The error is not
noise: it is largest exactly where retention is worst, so a naive figure **flatters the models that
wasted the most tokens**, inverting the figure's purpose.

Framed against the guides this is not an exotic bias, it is a **metric computed over the wrong
denominator** (`03` §4, "carry the denominator"; `03` §6, "gate metrics on data availability").

The superseded plan left this blocking Phase 5. It is resolved here:

| Option | Assessment |
|---|---|
| **(a) Read `01_Raw` telemetry for the cost metrics** | **Chosen.** Truest, and the only one that works — see below |
| (b) Carry the multiplier and plot `cost_mean × (generated/selected)` | Rejected |

Option (b) is not merely less accurate, it is **uncomputable for the cases that matter most**. An
excluded combination has no capped mirror at all, so `generation_metadata` holds *zero* telemetry
for it, and `selected = 0` makes the correction factor undefined. Option (b) would silently omit
exactly the seven combinations whose waste the figure exists to show. It also assumes discarded
personas cost the same as kept ones — wrong in a *correlated* direction, since personas fail the
mapped gate through truncated or retry-heavy generations.

The reader lives **inside `cost_efficiency`**, not in `generation_metadata`. This keeps option (a)'s
only stated cost — touching a shipped process's read contract — off the table entirely.
`generation_metadata` is left exactly as it is.

### Why `raw_total` is not redundant

The obvious objection is that `raw_passed` already cross-checks `validate_raw/_summary.csv`. It does
not: `raw_passed` is `len(read_passed_ids(validate_raw/{slug}.csv))` (`population_cap/cap.py:254`),
i.e. read *out of the validator's own output*. So `raw_passed == passed` is a **tautology** —
verified across all combinations, zero mismatches — and can never detect a raw pool that grew or
shrank after validation ran. `raw_total`, globbed from the raw dirs at cap time, is the only
independent observation; `raw_total != n_personas` is the sole signal that the gate's two halves saw
different data.

The loader **requires** `raw_total` and raises naming the re-run command when absent, matching the
house read-boundary style (`capped_source.py`, `cap_index.py`: every raise names the offending path
*and* the task that fixes it). No silent fallback to `validate_raw`'s count — that is the
"no in-code fallback" invariant in `CLAUDE.md`.

### Unmetered models are a design constraint, not an edge case

Nine `ollama_*` models are priced `{in: 0, out: 0}`. Consequences the chart must handle:

- **A log-scaled cost axis is impossible** — `log(0)` is undefined for a third of the axis.
- **"Accuracy per dollar" divides by zero** and must not be computed as a composite score. This also
  respects ADR `2026-08-07-persona-realism-per-combination-split` Decision 2: never encode a
  directional claim into the arithmetic.
- Unmetered ≠ free. Local inference has a real cost the pricing config does not model; the figure
  must say so rather than implying local models cost nothing.

Chosen rendering: a symlog x-axis with a labelled zero-cost band for unmetered models, and an
`unmetered` boolean column in the CSV so the distinction travels as data (per ADR
`2026-08-07-per-clash-contract`: "caveats travel as data fields and CSV columns, not docstring
prose, because the tables travel without the code").

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| `validation_attrition` as its own process | Naturally cross-combo; leaves the gate's per-combo contract intact | One registry entry + workflow task | **Chosen** |
| Attrition figure inside `population_cap` | It already computes every count | `population_cap` is `dispatch: per_combo`; a cross-combo figure would be redrawn once per combo and blurs its single-combo contract | Rejected |
| Attrition figure inside `validate_mapped` | Owns `pass_rate_pct` | Same per-combo/atomistic objection; and the funnel spans three processes, not one | Rejected |
| Denominator from `validate_raw/_summary.csv` alone | No change to `cap.py` | The two sources drift undetectably, and the cross-check is a tautology | Rejected as *sole* source |
| `cost_efficiency` as its own process | Both inputs declared; either upstream runs alone; matches the `realism_ranking` precedent | One registry entry + workflow task | **Chosen** |
| Cost figure inside `generation_metadata` | Cost data already local | Inverts the dependency direction; couples LLM telemetry to fidelity | Rejected |
| Cost figure inside `model_ranking` | Accuracy already local | Fidelity ranking could no longer run without LLM telemetry — a real regression for any dataset lacking it | Rejected |
| One process emitting both figures | One registry entry | They share no input and no derivation; only the shape "cross-combo + figure + CSV" — which `05` §3 warns is not duplication | Rejected |
| Add `raw_total` to `CapSummary` | The only independent observation of the pool | Touches a shipped DTO (additive only); needs a gate re-run to backfill | **Chosen** |

### Architecture & Module Contracts

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `analysis/utils/attrition_csv.py` *(new)* | The tidy per-combination attrition schema: frozen row dataclass, `SCHEMA_VERSION`, write/read with reconciliation | rows ↔ CSV | Figures, country, which process wrote it |
| `analysis/utils/cost_csv.py` *(new)* | The tidy per-combination cost-efficiency schema, incl. the `cost_basis` and `unmetered` columns | rows ↔ CSV | Figures, join mechanics |
| `validation_attrition/loader.py` *(new)* | Read `population_cap/_index.json` + both `_summary.csv`; validate the triple agrees; one DTO per combination | output_base → `list[AttritionRecord]`, `list[(slug, reason)]` | matplotlib, file layout of figures, country labels |
| `validation_attrition/builder.py` *(new)* | Derive `retention_rate` / `generation_multiplier`; assemble the JSON document and the CSV rows | records → dict + rows | matplotlib, paths |
| `validation_attrition/charts.py` *(new)* | Render the funnel and the mapped-validity model × method grid; **return Figures** | built dict → `Figure` | Where files go; dpi; how rates were derived |
| `cost_efficiency/raw_cost.py` *(new)* | Read LLM-call telemetry from the **full** `01_Raw` pool and total cost per combination | output_base, slug → cost totals | Fidelity, charts, the capped mirror |
| `cost_efficiency/loader.py` *(new)* | Read `model_ranking` performance + the attrition CSV + raw cost; reconstruct the slug via `axis_slug`; assert the join is one-to-one | dirs → `list[CostRecord]` | matplotlib; how TV was computed |
| `cost_efficiency/builder.py` *(new)* | Derive `cost_per_usable_persona`; assemble document + rows; record cost-basis provenance | records → dict + rows | matplotlib, paths |
| `cost_efficiency/charts.py` *(new)* | Render accuracy-vs-cost with the unmetered band; **return Figure** | built dict → `Figure` | Where files go; pricing |
| `population_cap/cap.py` *(modified)* | Additionally record `raw_total` at cap time | — | The two new processes |

```
src/population_synthetic/analysis/
├── utils/
│   ├── attrition_csv.py      (new)
│   └── cost_csv.py           (new)
├── validation_attrition/     (new: __init__, loader, builder, charts)
└── cost_efficiency/          (new: __init__, loader, builder, charts, raw_cost)
scripts/analyze/
├── analyze_validation_attrition.py   (new)
└── analyze_cost_efficiency.py        (new)
```

### Reused, not rebuilt

`utils/registry.py::analysis_output_dir` (never a path literal) · `utils/tidy_csv.py`
(`write_rows` truncating → idempotent; `parse_optional_float` gives `None`, never `0.0`;
`missing_columns` + `stale_schema_error`) · `utils/figures.py::save_figure` (PNG+SVG from one call,
closes the fig) · `utils/palette.py` (`HEATMAP_CMAP`, `MISSING_COLOR`, `text_color_on`) ·
`model_ranking/table_style.py` (grid grammar for the mapped-validity heatmap) ·
`utils/axes.py::strategy_complexity_order` (method column order; raises on unknown id) ·
`utils/cap_index.py::load_cap_index` · `generators/synthetic/manifest_loader.py::axis_slug`
(the single source of truth for `{country}_{strategy}_{model}`; `analysis/` already imports from
`manifest_loader` in nine places, so this crosses no boundary).

### Principles this design is built to

From `~/.claude/knowledge/data-pipeline-engineering/`:

- `02` §3 — validate at the boundary; no `.get()` with defaults. Counts stay `int`; only derived
  rates are `float`.
- `02` §8 — required input missing → raise naming file and field; optional → explicit absent marker,
  never a silent zero.
- `02` §9 — **visualization is a pure sink.** Both rates are computed in `builder.py` and *read* by
  the charts; no statistic is computed inside a renderer.
- `02` §5 — overwrite, never append (`write_rows` already guarantees this).
- `02` §6 — a single normalization point: `cost_efficiency` reads two differently-shaped sources and
  normalizes both to one internal schema at the boundary.
- `03` §4 — **rates carry their denominator.** Every ratio column ships beside the counts it came
  from; the funnel figure prints N.
- `03` §6 — zero ≠ absent; gate metrics on availability; **report what was dropped**.
- `03` §6 — be cautious joining on a reconstructed key; state the rule and assert it is one-to-one.
- ADR `2026-08-07-persona-realism-per-combination-split` — the cross-process seam is an on-disk
  contract; the producer never learns a consumer exists; a file-backed seam needs its own
  completeness gate.
- ADR `2026-08-12-self-contained-typicality-axis` — house ramp for every heatmap; missing renders as
  `MISSING_COLOR` grey, never as 0; **four states, never three**; do not reuse a renderer whose key
  names don't match your value's meaning (`_render_grid_heatmap` reads `cell["rate"]` by literal key
  and would paint every cell grey *without raising*); SVG is not byte-reproducible — claim
  byte-stability for JSON/CSV/PNG only.

---

## Implementation Plan

### Phase 0: Prerequisites
**Goal:** Remove the two things that block writing correct code.

- [x] 0.1 — Move `pending/pipeline-model-method-cost-and-attrition-figures.md` to `archived/`,
      adding a header line pointing at this plan.
- [x] 0.2 — Confirm `feature/enforce-full-n-cap-exclusion` is merged to `dev`; branch from `dev`.
      (Merged as `221baa2`; `CapSummary.excluded` / `exclusion_reason` present on this branch.)
- [x] 0.3 — Run `generation_metadata` once on `swedish_02` and **pin its real column names into a
      test fixture**. It has never run for this grid; the cost loader must be written against
      observed columns, not `report_writer.py` read by eye.

**Files Modified:** the archived plan, plus `tests/_generation_metadata_fixtures.py`.
**Dependencies:** none.

#### 0.3 result — the observed `generation_metadata` contract

`python scripts/analyze/summarize_generation_metadata.py --country swedish_02 --strict`
(2026-08-20, exit 0) wrote `03_Analysis/generation_metadata/{swedish_02_summary.csv,
swedish_02_summary.json,charts/}`. The CSV is **58 rows × 71 columns** — the 58 non-excluded
combinations only, since an excluded combination has no capped mirror and therefore produces no
row at all. Header, verbatim and in order:

```
model, method, n_personas, has_token_data,
<metric>_{mean,std,median,q1,q3,n}   for metric in
    time, input_tokens, output_tokens, total_tokens, calls, retry_rate, error_rate, cost,
latency_p95, latency_max, success_rate,
<metric>_{model,method}_group        for the same eight metrics, metric-outer / factor-inner
```

Cell shapes the loader must parse: `has_token_data` serialises as the Python repr `True` /
`False` (capitalised, **not** `true`/`false`); `n_personas` and every `<metric>_n` are integer
counts; every other numeric cell is a float rounded to 6 decimals and is written **empty**, never
`0`, when absent (this run had no empty cells and `has_token_data` was `True` on all 58 rows);
`<metric>_<factor>_group` cells are compact-letter-display strings.

Axis values present: 12 models × 5 methods = 60 grid cells, 58 written. The 7 withdrawals are
`ollama_llama31_8b` under all five methods (so that model is absent from the CSV entirely) plus
`all_generate_evaluate_random_pick_v2` × {`ollama_deepseek_r1_14b`, `ollama_gemma4_e4b`}.
**`generation_metadata` is therefore not a source for withdrawals — `validation_attrition` is.**

The JSON's top-level keys are `process, country, generated_at, output_base, pricing, metrics,
scalar_metrics, combos, skipped, significance`; `pricing` carries
`{observed_date, source, currency}` (Phase 4.2's provenance passthrough), and `skipped` was `[]`.

Pinned in `tests/_generation_metadata_fixtures.py` as `OBSERVED_COLUMNS` (asserted equal to the
on-disk header), with `make_row` / `build_summary_csv` builders.

### Phase 1: `raw_total`
**Goal:** Give the funnel its first stage an authoritative source.

- [ ] 1.1 — Add `raw_total: int` to `CapSummary`, populated by globbing `persona_*` dirs at cap time.
- [ ] 1.2 — Populate it on the excluded path too (`withdraw_combo`), where it is most needed.
- [ ] 1.3 — Re-run the gate to backfill `_index.json`, asserting `selected_ids` are unchanged for
      every already-capped combination (the draw is seeded; a changed id set means a real bug).

**Files Modified:** `src/population_synthetic/analysis/population_cap/cap.py`,
`scripts/analyze/cap_populations.py`, `tests/test_population_cap.py`.
**Dependencies:** Phase 0.

### Phase 2: the attrition contract and derivation
**Goal:** Counts and rates, tested, with no rendering.

- [ ] 2.1 — `analysis/utils/attrition_csv.py`: frozen `AttritionRow`, `FIELDNAMES` derived from
      `fields(...)`, `SCHEMA_VERSION = 1` with an inline "what and why required" comment, named
      remedy strings, `write_*`/`read_*` on the `tidy_csv` primitives.
- [ ] 2.2 — `validation_attrition/loader.py`: read the `_index.json` + two `_summary.csv` triple;
      **completeness gate** — a combination is consumable only if present in all three *and* the
      counts agree; disagreement is a hard error naming both files and the regeneration command.
- [ ] 2.3 — `validation_attrition/builder.py`: derive both rates per the Definitions, returning
      `None` (not 0, not inf) at every undefined denominator.

**Files Modified:** the two new modules + `tests/test_validation_attrition_loader.py`,
`tests/test_validation_attrition_builder.py`.
**Dependencies:** Phase 1.

### Phase 3: the attrition figures and wiring
**Goal:** F05 becomes a pipeline artifact.

- [ ] 3.1 — `validation_attrition/charts.py`: the per-combination funnel (normalised, printing N)
      and the mapped-validity model × method grid via `table_style` + `palette`.
- [ ] 3.2 — `scripts/analyze/analyze_validation_attrition.py` on the house driver skeleton:
      module docstring as operator contract, the standard flag set
      (`--country/--model/--strategy/--slug/--output-base/--no-charts/--strict/--force/--dpi`),
      idempotent skip unless `--force`, printed skip list, the nothing-to-do exit convention.
- [ ] 3.3 — Registry entry (`label/description/folder/script/dispatch: slugs`) and the
      `_EXPECTED_FOLDERS` map in `tests/test_analysis_registry.py`.
- [ ] 3.4 — Workflow task with `depends_on: [population_cap]`.

**Files Modified:** `charts.py`, the new script, `config/analysis/analysis_registry.yaml`,
`config/gui/flows/analysis_workflow.yaml`, `tests/test_analysis_registry.py`.
**Dependencies:** Phase 2.

### Phase 4: cost over the full pool
**Goal:** A cost number that is not measured on the capped mirror.

- [ ] 4.1 — `cost_efficiency/raw_cost.py`: total per-combination cost from `01_Raw`
      `llm_interactions.jsonl` telemetry, priced through `model_pricing.yaml`.
- [ ] 4.2 — Carry pricing provenance (`observed_date`, `source`, `currency`, `[VERIFY]`) through to
      the JSON; classify each model `unmetered` vs priced; **absent pricing raises**.
- [ ] 4.3 — Assert against the known 5.5× case: the `01_Raw` total for
      `…_random_pick_v2_openrouter_qwen35_flash` must exceed its capped-mirror total.

**Files Modified:** `raw_cost.py`, `tests/test_cost_efficiency_raw_cost.py`.
**Dependencies:** Phase 0.3.

### Phase 5: the cost join, figure and wiring
**Goal:** F26 becomes a pipeline artifact.

- [ ] 5.1 — `analysis/utils/cost_csv.py` (schema, incl. `cost_basis` and `unmetered` columns).
- [ ] 5.2 — `cost_efficiency/loader.py`: reconstruct the slug via `axis_slug`, join accuracy + cost
      + the attrition CSV, **assert one-to-one and raise on any unmatched key on either side**,
      naming the key and both files. An empty join is never valid.
- [ ] 5.3 — `cost_efficiency/builder.py`: `cost_per_usable_persona`; no composite "value" score.
- [ ] 5.4 — `cost_efficiency/charts.py`: symlog x-axis with the labelled unmetered band; the cost
      basis printed on the figure.
- [ ] 5.5 — `scripts/analyze/analyze_cost_efficiency.py`; registry entry; workflow task with
      `depends_on: [model_ranking, generation_metadata, validation_attrition]`.

**Files Modified:** the new modules and script, both config files,
`tests/test_analysis_registry.py`, `tests/test_cost_efficiency_*.py`.
**Dependencies:** Phases 3 and 4.

### Phase 6: documentation and restaging
**Goal:** The deck stops carrying hand-built figures.

- [ ] 6.1 — `CLAUDE.md`: both processes in the analysis-layer paragraph and the DAG description.
- [ ] 6.2 — `docs/architecture/sub-packages.md` + `commands.md`.
- [ ] 6.3 — Update the manuscript folder's `figures selection/SOURCES.md` to move F05 and F26 from
      "hand-made" to the pipeline-backed table, with their new source paths.

**Files Modified:** docs only. **Dependencies:** Phase 5.

---

## Testing Plan

### Unit Tests
- [ ] Hand-computed five-stage funnel fixture: known counts in, known `retention_rate` and
      `generation_multiplier` out (`pytest.approx`, never exact float equality).
- [ ] Excluded combination (`selected = 0`, `clean = 9`): `generation_multiplier` is populated
      (150/9), `retention_rate` is 0.06, nothing divides by zero.
- [ ] Degenerate `clean = 0`: both ratios are `None`, the row still exists, and nothing is 0 or inf.
- [ ] `generated = 0`: `retention_rate` is `None`, no `ZeroDivisionError`.
- [ ] Missing `raw_total` raises, and the message names the re-run command.
- [ ] Counts disagreeing across `_index.json` and `_summary.csv` raises naming both files.
- [ ] Unmatched `model`/`method` in the cost join raises naming the key and both files.
- [ ] Empty join raises rather than writing an empty CSV.
- [ ] Unmetered model: `cost_per_usable_persona` is `0.0` and `unmetered` is `true` — never `None`,
      which means absent.
- [ ] Absent pricing entry raises (distinct from unmetered).
- [ ] Schema round-trip: empty cell reads back as `None`, never `0.0`.

### Integration Tests
- [ ] End-to-end on a `tmp_path` fixture built through `analysis_output_dir` (never path literals),
      mirroring `test_realism_ranking_e2e.py`: gate artifacts → attrition → cost, asserting the
      expected files appear and key numbers match.
- [ ] Both CLIs invoked **by subprocess** (the flags and argument resolution at the edge are the
      point), asserting `returncode == 0`.
- [ ] `--no-charts` asserted as a real absence of `*.png` **and** `*.svg`; a second run asserts both
      formats appear per figure.
- [ ] A populated heatmap cell is **not** rendered as missing — the specific regression ADR
      `2026-08-12` records, where a renderer read `cell["rate"]` by literal key and greyed
      everything without raising.
- [ ] Re-running twice produces identical CSV/JSON bytes (idempotency; PNG/JSON/CSV only — SVG is
      not byte-reproducible).

### Manual Verification
- [ ] The mapped-validity grid reproduces the audited `swedish_02` numbers: gemma4_e4b × E = 6.0,
      deepseek_r1_14b × E = 6.7, llama31_8b × E = 7.3, flagship A–D range 77.3–100.0.
- [ ] All 7 withdrawn combinations are visible and marked as withdrawn, not merely thin.
- [ ] `matplotlib.use("Agg")` before package imports in every chart test.

---

## Documentation Plan

- [ ] `CLAUDE.md` — both processes in the analysis-layer description and the DAG.
- [ ] `docs/architecture/sub-packages.md`, `docs/architecture/commands.md`.
- [ ] ADR for the two decisions that will otherwise be re-litigated: the reconstructed join key
      (rather than adding a slug column upstream), and the cost-denominator choice
      (`05` §9: record context / decision / consequences).
- [ ] `figures selection/SOURCES.md` in the manuscript folder.

---

## Rollback Plan

1. **Before deployment:** both processes are additive and read-only. Revert the branch; the only
   shared-surface change is `CapSummary.raw_total`.
2. **Data considerations:** `raw_total` is additive, so an older `_index.json` is readable by new
   code only in the sense that it raises loudly and names the re-run — deliberate, not a
   compatibility break. Nothing else rewrites an existing artifact.
3. **Rollback procedure:** revert the merge; delete `03_Analysis/validation_attrition/` and
   `03_Analysis/cost_efficiency/`. No upstream artifact is mutated, so no gate re-run is needed to
   undo.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `raw_total` backfill needs a full gate re-run, and a re-run under the full-N rule could withdraw a combination that previously survived | Med | High | Task 1.3 asserts `selected_ids` unchanged per combination before accepting the backfill; the draw is seeded, so a difference is a real bug, not noise |
| The `01_Raw` cost reader double-counts personas from an aborted-and-resumed run | Med | High | `llm_interactions.jsonl` is truncated iff the checkpoint is discarded, which is what keeps `(persona_id, call_index)` unique; assert uniqueness on read and raise on a duplicate |
| A third of the model axis is unmetered, making the cost axis degenerate | High | Med | Symlog axis + labelled zero-cost band; `unmetered` as a data column; no accuracy-per-dollar composite |
| Reconstructed slug mis-attributes a row silently | Low | High | `axis_slug` is the single source of truth; one-to-one assertion on both sides; empty join raises |
| `generation_metadata`'s real columns differ from `report_writer.py` read by eye | Med | Med | Task 0.3 pins observed columns into a fixture *before* the loader is written |
| Cost still understates because `01_Raw` telemetry is itself incomplete for very old runs | Med | Med | `has_token_data` already exists as a per-combo flag; propagate it and render those combos as absent, never as zero |
| The two processes drift into a premature shared framework | Med | Low | Explicitly out of scope; `05` §3 — similar shape is not duplication |
| F05/F26 remain hand-built in the deck after the code ships | Med | Med | Phase 6.3 restages them and moves them in `SOURCES.md`, closing the loop that caused this plan |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 0 — prerequisites | ~1 file move + one pipeline run | None |
| Phase 1 — `raw_total` | ~30 lines in 2 files + gate re-run | Phase 0 |
| Phase 2 — attrition contract | ~250 lines in 2 new modules | Phase 1 |
| Phase 3 — attrition figures + wiring | ~350 lines, 1 new script, 2 config files | Phase 2 |
| Phase 4 — cost over full pool | ~200 lines in 1 new module | Phase 0.3 |
| Phase 5 — cost join + figure | ~400 lines, 1 new script, 2 config files | Phases 3, 4 |
| Phase 6 — docs + restaging | ~4 docs | Phase 5 |

---

## References

- Supersedes: `docs/development/plans/pending/pipeline-model-method-cost-and-attrition-figures.md`
- Prerequisite: `docs/development/plans/active/enforce-full-n-cap-exclusion.md`
- Shipped predecessor: `docs/development/plans/completed/model-method-tv-heatmap.md`
- ADRs: `docs/development/decisions/2026-08-07-persona-realism-per-combination-split.md`,
  `2026-08-07-per-clash-contract-and-severity-drivers.md`,
  `2026-08-12-self-contained-typicality-axis.md`
- `~/.claude/knowledge/data-pipeline-engineering/` — `01` §Axis 5 (two-level pattern),
  `02` §§3,5,6,8,9, `03` §§4,6,7, `05` §§1,3,5,6,9
