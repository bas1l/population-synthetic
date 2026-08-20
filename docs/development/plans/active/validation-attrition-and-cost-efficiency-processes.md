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

- [x] `python scripts/analyze/analyze_validation_attrition.py --country swedish_02` writes
      `{country}_attrition.csv`, `{country}_attrition.json`, and both figures under
      `03_Analysis/validation_attrition/`.
- [x] The attrition CSV has one row per combination in `population_cap/_index.json` — **65 rows for
      `swedish_02`, not 58** — because the withdrawn combinations are the point of the figure.
- [x] For each of the 7 withdrawn combinations the row reads `excluded=true`, a non-empty
      `exclusion_reason`, `selected=0`, `generation_multiplier` populated, and
      `cost_per_usable_persona` computable. *(The first four are the attrition CSV row; the
      cost is published in `{country}_cost_efficiency.json`'s `withdrawn_combinations`
      rather than in the cost CSV, whose row grain is the combinations that have **both**
      accuracy and cost. See the Phase 5 result block.)*
- [x] `retention_rate` for `all_generate_evaluate_random_pick_v2 × ollama_gemma4_e4b` equals
      `9/150 = 0.06`, matching `validate_mapped/_summary.csv → pass_rate_pct = 6.0`.
- [x] `python scripts/analyze/analyze_cost_efficiency.py --country swedish_02` writes
      `{country}_cost_efficiency.{csv,json}` and the scatter under `03_Analysis/cost_efficiency/`.
- [x] Every row of the cost join is matched on both sides; an unmatched `model`/`method` on either
      side raises, naming the offending key and both files. An empty join is never a valid result.
- [x] The cost figure and the JSON both state the cost basis verbatim; the basis is a CSV **column**,
      not only prose.
- [x] `pytest` passes, including a hand-computed funnel fixture and an unmatched-key fixture that
      must raise. *(1846 passed; the one failure is the pre-existing
      `test_axis_facet_defaults.py` case Phases 3 and 4 also recorded, tripped by the
      uncommitted `generate_parallel.yaml` edits and unrelated to this feature.)*
- [x] `ruff check src/` clean.

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

- [x] 1.1 — Add `raw_total: int` to `CapSummary`, populated by globbing `persona_*` dirs at cap time.
- [x] 1.2 — Populate it on the excluded path too (`withdraw_combo`), where it is most needed.
- [x] 1.3 — Re-run the gate to backfill `_index.json`, asserting `selected_ids` are unchanged for
      every already-capped combination (the draw is seeded; a changed id set means a real bug).

**Files Modified:** `src/population_synthetic/analysis/population_cap/cap.py`,
`scripts/analyze/cap_populations.py`, `tests/test_population_cap.py`.
**Dependencies:** Phase 0.

#### 1.1–1.2 — where the count is taken

`clean_selection()` already lists `01_Raw/{slug}/persona_*` to intersect the two gates, so
`raw_total` is taken from that **same** listing (`CleanSelection.raw_total`) rather than from a
second glob: the pool and its surviving subset are then always observed from one view of the disk.
Both `cap_combo` and `withdraw_combo` copy it onto their summary, so the excluded path carries it
too — the only place a withdrawn combination's pool survives, since it gets no capped mirror and no
`generation_metadata` row.

#### 1.3 result — the backfill

`--force` re-run of `scripts/analyze/cap_populations.py` over all 65 `swedish_02` combinations
(2026-08-20, 214 s, 65/65 exit 0), diffed against a pre-run snapshot of
`population_cap/_index.json`:

- `selected_ids` **identical in set and order** for all 58 capped combinations; `selected`,
  `truncated`, `mapped_n`, both gate counts, `excluded` and `exclusion_reason` unchanged on all 65.
  `_mapped/_index.json` came back equal record-for-record. The only change is the added key.
- The excluded set is unchanged — still exactly the 7: `ollama_llama31_8b` under all five methods,
  plus `all_generate_evaluate_random_pick_v2` × {`ollama_deepseek_r1_14b`, `ollama_gemma4_e4b`}.
  Their pools: 250 (`all_generate_evaluate_pick_v2 × llama31_8b`) and 150 for the other six, against
  clean counts of 51, 34, 22, 20, 11, 10 and 9 — so
  `all_generate_evaluate_random_pick_v2 × gemma4_e4b` gives `9/150 = 0.06`, the number the
  success criteria pin.
- `raw_total` distribution over the 65: 150 (×42), 110 (×7), 250 (×5), 370 (×4), 190 (×2), and
  160 / 170 / 191 / 366 / 549 once each. It is **not** a constant, so the funnel's first stage
  could not have been hardcoded.
- Cross-checked against `validate_raw/_summary.csv`: `raw_total == n_personas` and
  `raw_passed == passed` on **all 65** — the pool is currently in sync, which is the baseline
  Phase 2's completeness gate asserts. Note that the five combinations where
  `raw_total != raw_passed` (up to 549 vs 488) are genuine raw-gate *failures*, not drift: drift is
  `raw_total != n_personas`, which is the comparison the loader must make.

### Phase 2: the attrition contract and derivation
**Goal:** Counts and rates, tested, with no rendering.

- [x] 2.1 — `analysis/utils/attrition_csv.py`: frozen `AttritionRow`, `FIELDNAMES` derived from
      `fields(...)`, `SCHEMA_VERSION = 1` with an inline "what and why required" comment, named
      remedy strings, `write_*`/`read_*` on the `tidy_csv` primitives.
- [x] 2.2 — `validation_attrition/loader.py`: read the `_index.json` + two `_summary.csv` triple;
      **completeness gate** — a combination is consumable only if present in all three *and* the
      counts agree; disagreement is a hard error naming both files and the regeneration command.
- [x] 2.3 — `validation_attrition/builder.py`: derive both rates per the Definitions, returning
      `None` (not 0, not inf) at every undefined denominator.

**Files Modified:** the two new modules + `tests/test_validation_attrition_loader.py`,
`tests/test_validation_attrition_builder.py`.
**Dependencies:** Phase 1.

#### 2.1–2.3 result — the contract as built

Four files: `analysis/utils/attrition_csv.py` (schema v1, 15 columns),
`validation_attrition/{__init__,loader,builder}.py` (`__init__` docstring-only), plus the two
test modules — 39 tests, all passing; `ruff check src/` clean.

- **Columns** (order == `AttritionRow` field order): `slug, country, model, strategy, requested_n,
  generated, raw_valid, mapped_valid, clean, selected, retention_rate, generation_multiplier,
  excluded, exclusion_reason, had_surplus`. `model`/`strategy` are carried rather than left to be
  re-parsed downstream — neither id is `_`-free, so a naive split is wrong — and they are what
  Phase 3's model × method grid and Phase 5's join key are built from. `exclusion_reason` is text
  with `""` for "not excluded"; `excluded` is the authoritative flag, never the reason's emptiness.
- **The drift predicate is `raw_total == validate_raw.n_personas`**, per the Phase 1 measurement.
  The loader additionally checks `raw_passed == passed` and `mapped_passed == passed`, which are
  tautological while the index is fresh and stop being so the moment a validator is re-run without
  re-running the cap. It does **not** compare `raw_total` against `raw_passed` (five live
  combinations legitimately differ) and does not compare `validate_mapped.n_personas` against
  anything: that count is the mapped pool, which equals `raw_passed` on all 65 rows but is a
  mapping-layer relationship rather than part of the gate's contract.
- **Missing** from a validator roll-up is a skip with a machine-readable reason (`strict` raises);
  **disagreeing** counts always raise, naming both files and the ordered re-run. Script names in
  every message come from `registry.get_process(id).script`, not from literals.
- **Verified against the live grid** (`load_attrition_records` + `build_rows` over the real output
  base): 65 records, 0 skipped, 7 excluded — and
  `all_generate_evaluate_random_pick_v2 × ollama_gemma4_e4b` reads `generated=150, clean=9,
  selected=0, retention_rate=0.06, generation_multiplier=16.666…`, the success criterion's number.
  Pooled totals: 11616 generated → 8077 clean → 5800 selected.
- **The builder's document carries no timestamp**, so it is byte-reproducible for a fixed input;
  the Phase 3 driver stamps `generated_at` if it wants one.

### Phase 3: the attrition figures and wiring
**Goal:** F05 becomes a pipeline artifact.

- [x] 3.1 — `validation_attrition/charts.py`: the per-combination funnel (normalised, printing N)
      and the mapped-validity model × method grid via `table_style` + `palette`.
- [x] 3.2 — `scripts/analyze/analyze_validation_attrition.py` on the house driver skeleton:
      module docstring as operator contract, the standard flag set
      (`--country/--model/--strategy/--slug/--output-base/--no-charts/--strict/--force/--dpi`),
      idempotent skip unless `--force`, printed skip list, the nothing-to-do exit convention.
- [x] 3.3 — Registry entry (`label/description/folder/script/dispatch: slugs`) and the
      `_EXPECTED_FOLDERS` map in `tests/test_analysis_registry.py`.
- [x] 3.4 — Workflow task with `depends_on: [population_cap]`.

**Files Modified:** `charts.py`, the new script, `config/analysis/analysis_registry.yaml`,
`config/gui/flows/analysis_workflow.yaml`, `tests/test_analysis_registry.py`,
`tests/test_validation_attrition_charts.py`, `tests/test_workflow_state.py`.
**Dependencies:** Phase 2.

#### 3.1–3.4 result — the figures as built

Two renderers in `validation_attrition/charts.py`, both returning an **unsaved** `Figure` (the
`realism_ranking` convention), plus the driver, the registry entry, the workflow task and 19 tests.
`ruff check src/` clean; full suite green apart from one pre-existing failure unrelated to this
phase (`test_axis_facet_defaults.py`, tripped by uncommitted edits to `generate_parallel.yaml`).

- **The grid's cell value is `retention_rate`, read from the document, never recomputed.** It is the
  only survival quantity the builder derives, so the CSV, the JSON and the figure cannot disagree
  (`02` §9). It reproduces every audited number: gemma4_e4b × E = 6.0, deepseek_r1_14b × E = 6.7,
  llama31_8b × E = 7.3, and the hosted A–D range 77.3–100.0. On the live grid `clean / generated`
  and `mapped_valid / raw_valid` coincide on all 65 combinations, so pinning the published field
  costs nothing in fidelity to the `validate_mapped` roll-up.
- **Four cell states, drawn and tested.** `measured` (ramp), `withdrawn` (its **measured** rate on
  the ramp plus a hatch — never 0, never grey), `undefined` (`generated == 0`, grey with a dotted
  border and no number), `absent` (plain grey, "not generated"). The withdrawal hatch is drawn
  independently of the fill, so a withdrawn combination with an empty pool keeps both facts.
  `test_populated_cell_is_not_rendered_as_missing` asserts the drawn imshow array and the drawn
  annotation, which is the only way the ADR's silent-grey regression is observable.
- **Both figures carry their denominators.** Every grid cell prints `clean/generated` beneath its
  percentage; both marginals are **pooled over persona counts**, not means of the cell rates (the
  pools differ by 5×); every funnel bar prints `N=` and the document's own `retention_rate`.
- **The funnel is a partition, not a stack.** Each bar cuts the generated pool into four disjoint
  slices — failed raw / failed mapped / clean-not-drawn / drawn — which sum to the pool exactly;
  `_segment_counts` raises rather than drawing a negative slice if the three gate records ever
  disagree.
- **Verified live**: `analyze_validation_attrition.py --country swedish_02` wrote
  `swedish_02_attrition.{csv,json}` (65 rows, 7 excluded, pooled 11616 generated → 8077 clean →
  5800 selected) and both figures as PNG+SVG under `03_Analysis/validation_attrition/`. Re-running
  reproduces the CSV and the JSON byte-for-byte; SVG is not byte-stable and no such claim is made.

### Phase 4: cost over the full pool
**Goal:** A cost number that is not measured on the capped mirror.

- [x] 4.1 — `cost_efficiency/raw_cost.py`: total per-combination cost from `01_Raw`
      `llm_interactions.jsonl` telemetry, priced through `model_pricing.yaml`.
- [x] 4.2 — Carry pricing provenance (`observed_date`, `source`, `currency`, `[VERIFY]`) through to
      the JSON; classify each model `unmetered` vs priced; **absent pricing raises**.
- [x] 4.3 — Assert against the known 5.5× case: the `01_Raw` total for
      `…_random_pick_v2_openrouter_qwen35_flash` must exceed its capped-mirror total.

**Files Modified:** `raw_cost.py`, `tests/test_cost_efficiency_raw_cost.py`.
**Dependencies:** Phase 0.3.

#### 4.1–4.3 result — the raw-pool cost reader as built

Two files under `analysis/cost_efficiency/` (`__init__.py` docstring-only, `raw_cost.py`) plus
`tests/test_cost_efficiency_raw_cost.py` — 21 tests, all passing; `ruff check src/` clean; full
suite 1759 passed, apart from the same pre-existing `test_axis_facet_defaults.py` failure Phase 3
recorded (uncommitted `generate_parallel.yaml` edits, unrelated). `generation_metadata` was not
touched.

- **The pricing accessor is re-implemented here, deliberately.** `generation_metadata/pricing.py`
  parses the same config and would have been the accessor to reuse, but importing *any* submodule
  of that package executes its `__init__`, which imports
  `analysis/utils/capped_source.resolve_stage_source` — measured: after
  `import …generation_metadata.pricing`, `capped_source` is in `sys.modules`. Reusing it would put
  the capped-mirror reader back into the import graph of the one module written to avoid it. The
  contract table's "Must NOT know about: the capped mirror" is therefore satisfied by a minimal
  local reader; asserted directly — importing `raw_cost` leaves `matplotlib`, `capped_source` and
  `generation_metadata` all absent from `sys.modules`. The config file remains the single source of
  truth; only the parser is duplicated.
- **`raw_cost_for_slug(output_base, slug, model_id, pricing)`** takes `model_id` explicitly rather
  than decomposing the slug: the axis registries are the loader's business (`axes.decompose_slug`),
  and Phase 5's loader already holds `(model, method)` because it builds the slug from them.
- **Four states, never three.** *absent* (`has_token_data == False` → `total_cost_usd is None`),
  *unmetered* (`{in: 0, out: 0}` → a **measured** `0.0` when telemetry exists), *priced*, and
  *unpriceable* (no config row → raises). The pricing fact and the telemetry fact stay separable: an
  unmetered model with no telemetry reports `unmetered=True` **and** `total_cost_usd=None`. Absent
  pricing raises **before** any telemetry is read, so it cannot be masked by a thin pool.
- **`[VERIFY]` lives in YAML comments, which `safe_load` discards**, so the tags are lifted out of
  the raw text per model row and carried as `pricing_flags` (`("VERIFY", "effective/discounted")`,
  `("verified 2026-08-14",)`, or `()` — an empty tuple is a positive statement that the row is
  untagged). `pricing_document(pricing, model_ids)` is the JSON-ready block: the three bulk stamps,
  the config path, `cost_basis`, and per model `{price_in, price_out, unmetered, flags}`, restricted
  to the models actually analysed, sorted, timestamp-free and therefore byte-reproducible.
- **The double-counting guard is enforced, not documented.** `(persona_id, call_index)` uniqueness
  is asserted across the whole pool; a repeat raises naming the persona, the file the key was first
  seen in and the file that repeated it. The record's own `persona_id` is preferred over the
  directory name, so a mis-filed log collides rather than hides. Records lacking a `call_index` are
  outside the assertion and are counted into `n_unkeyed_calls`, a field on the record — the limit of
  the guard travels as data. Live check on the qwen35_flash pool: 17454 calls, 0 unkeyed, 0
  duplicates, 0 persona-id mismatches.
- **`cost_basis` is a field on every record** (`generated_pool_01_raw`), so no consumer can print a
  cost without its denominator.

##### 4.3 measurement — raw pool vs capped mirror

`swedish_02_all_generate_evaluate_random_pick_v2_openrouter_qwen35_flash`, priced at
`{in: 0.065, out: 0.26}`:

| Basis | Personas | Input tok | Output tok | Total USD |
|---|---|---|---|---|
| `01_Raw` generated pool | 549 | 6,581,464 | 103,294,407 | **27.2843** |
| capped mirror (`generation_metadata`) | 100 | 1,379,172 | 21,711,233 | **5.7346** |

**Cost ratio 4.758×**, direction as predicted — the assertion holds. The persona ratio is
549/100 = **5.49×**, which is the figure the plan's "5.5×" names (it is quoted there as
"549 generated, 100 selected", a pool ratio, not a cost ratio).

The two ratios differ because the **drawn personas are ~15% more expensive each than the pool
average** (0.05735 vs 0.04970 USD). That is the sign the plan's own reasoning predicts: personas
fail the mapped gate through truncated generations, and a truncated generation emits fewer output
tokens, so the discards are systematically *cheaper* than the keeps. It also means the correction is
**not** the generation multiplier — option (b) would have over-corrected here by 15%, which is a
second, independent reason the plan's choice of option (a) was the right one.

Cross-checked rather than asserted: summing this module's own reader over only the 100
`selected_ids` from `population_cap/_index.json` gives **5.73457 USD**, matching
`generation_metadata`'s `cost_mean × cost_n = 5.7346` to its published rounding. The reader's
arithmetic is therefore identical to the shipped process's; only the denominator differs.

### Phase 5: the cost join, figure and wiring
**Goal:** F26 becomes a pipeline artifact.

- [x] 5.1 — `analysis/utils/cost_csv.py` (schema, incl. `cost_basis` and `unmetered` columns).
- [x] 5.2 — `cost_efficiency/loader.py`: reconstruct the slug via `axis_slug`, join accuracy + cost
      + the attrition CSV, **assert one-to-one and raise on any unmatched key on either side**,
      naming the key and both files. An empty join is never valid.
- [x] 5.3 — `cost_efficiency/builder.py`: `cost_per_usable_persona`; no composite "value" score.
- [x] 5.4 — `cost_efficiency/charts.py`: symlog x-axis with the labelled unmetered band; the cost
      basis printed on the figure.
- [x] 5.5 — `scripts/analyze/analyze_cost_efficiency.py`; registry entry; workflow task with
      `depends_on: [model_ranking, generation_metadata, validation_attrition]`.

**Files Modified:** the new modules and script, both config files,
`tests/test_analysis_registry.py`, `tests/test_cost_efficiency_*.py`. Plus, as built:
`src/population_synthetic/analysis/utils/tidy_csv.py` (one added cell codec,
`parse_optional_int`), `src/population_synthetic/analysis/cost_efficiency/__init__.py`
(the package docstring now names all five modules and the membership rule),
`tests/test_workflow_state.py` (the shipped-DAG ordering assertions),
`tests/test_cost_csv.py` and `tests/_cost_efficiency_fixtures.py`.
**Dependencies:** Phases 3 and 4.

#### 5.1-5.5 result -- the join, the figure and the wiring as built

Four new modules (`analysis/utils/cost_csv.py`, `cost_efficiency/{loader,builder,charts}.py`)
plus `scripts/analyze/analyze_cost_efficiency.py`, the registry entry, the workflow task, one
shared fixture module and four test modules -- **70 new tests, all passing**; `ruff check src/`
clean; full suite **1846 passed**, with the same single pre-existing
`test_axis_facet_defaults.py` failure Phases 3 and 4 recorded (uncommitted
`generate_parallel.yaml` edits, unrelated).

- **Columns** (order == `CostRow` field order, schema v1, 22 columns): `slug, country, model,
  strategy, overall_tv_similarity, n_scored, generated, clean, selected,
  generation_multiplier, n_calls, input_tokens, output_tokens, total_tokens, total_cost_usd,
  cost_per_usable_persona, cost_basis, unmetered, has_token_data, price_in, price_out,
  pricing_flags`. Every ratio ships beside the counts it is a quotient of.
  `generation_multiplier` is **read from the attrition contract, not recomputed** -- it is the
  same quotient over the same two counts, and deriving it twice is how two artifacts come to
  disagree about one combination. It is carried for interpretation only: per Phase 4's
  measurement it is emphatically *not* the correction factor, because the cost here is
  measured over the generated pool directly.
- **`parse_optional_int` was added to `utils/tidy_csv.py`** -- the integer counterpart of the
  existing `parse_optional_float`, so a token total that no call reported reads back as `None`
  rather than as a fabricated `0`. It is a cell codec, which is exactly what that module holds.
- **The membership rule, stated in the schema, in the JSON and in the tests.** The output row
  set is *the attrition row set minus the withdrawals*, and it must equal the `model_ranking`
  and `generation_metadata` row sets **exactly**. On the live grid that is 65 - 7 = 58 = 58 =
  58, published as a `membership` block so the row count is auditable rather than merely
  asserted. Four failure modes raise, each naming the key and both files: a survivor missing
  from either file; a scored combination the attrition CSV records as *withdrawn* (a
  contradiction -- a withdrawal has no capped mapped file to score); a scored combination
  absent from the attrition CSV entirely; and an empty join, which would otherwise publish an
  empty cost figure that reads as a measured absence of cost.
- **A withdrawal is reported with the money it cost.** It cannot be plotted -- it has no
  accuracy score -- so it travels in `withdrawn_combinations` (slug, reason, generated, clean,
  `total_cost_usd`, `unmetered`), in `withdrawn_totals`, in the figure's caption and in the
  driver's stdout. On `swedish_02` all seven are `ollama_*`, so their metered spend is **0.00
  USD across 0 metered combinations** over 1150 generated personas that yielded 157 clean ones:
  the withdrawals cost GPU time, not money, and the artifact now says which.
- **The reconstruction is verified, not trusted.** `generation_metadata`'s summary has no slug
  column, so its key is rebuilt from `model` + `method` through `manifest_loader.axis_slug`.
  The *same* rebuild is applied to the `model_ranking` CSV, which publishes its own slug, and a
  disagreement raises -- a live proof, executed on every read and on this very data, that the
  rule reproduces the producer's slug. Reconstructed keys are also asserted unique within each
  file, so the join cannot silently become many-to-one.
- **One integrity check the plan did not name, added because it is free.**
  `generation_metadata`'s `has_token_data` is measured over the capped mirror, which is copied
  out of the `01_Raw` pool; `True` there with no telemetry in the pool is therefore impossible
  and raises. The converse -- the pool reports tokens and the mirror does not -- is legitimate
  and is not raised.
- **No composite score, asserted rather than merely omitted.** The document declares
  `non_composite` with its reason, and two tests walk every column name and every JSON key to
  assert that no `*_per_dollar` / `value_score` / `efficiency_score` field ever reappears.
- **The chart.** Symlog x with a shaded, labelled zero-cost band; the left limit stops exactly
  at the band edge so the symlog axis' negative logarithmic branch (a tick reading `-10^-4` on
  a cost axis) can never appear, and no tick labels a position *inside* the band, which holds
  one value. Colour is the method (ColorBrewer Dark2, qualitative, ordered in the legend by
  `strategy_complexity_order`), marker shape is the hosting class, and every point is labelled
  with its model id. The thirteen zero-cost points are spread horizontally *within* the band by
  fidelity rank -- otherwise they stack on one vertical line and their labels are unreadable --
  and the band's own on-figure text says the spread is legibility rather than measurement, and
  that every point in it is a **measured 0.00 USD**. Every caveat printed is read from the
  document (`cost_basis`, `unmetered_note`, `non_composite_reason`, both withdrawal totals),
  never written as a literal, so the figure and the table cannot disagree.
- **Verified live**: `analyze_cost_efficiency.py --country swedish_02` wrote
  `swedish_02_cost_efficiency.{csv,json}` (58 rows) and `swedish_02_cost_vs_fidelity.png/.svg`
  under `03_Analysis/cost_efficiency/`. Re-running reproduces the CSV and the JSON
  byte-for-byte; SVG is not byte-stable and no such claim is made.

##### The measurement

| Quantity | Value |
|---|---|
| Joined combinations | 58 of 65 (7 withdrawn) |
| Pooled pool | 10,466 generated -> 7,920 clean -> 5,800 selected |
| Metered subtotal | 45 combinations, **606.61 USD** over 6,028 clean personas = **0.1006 USD / usable persona** |
| Unmetered | 13 combinations, a measured 0.0 -- not free |
| No token data | 0 combinations |
| Withdrawn | 7 combinations, 1,150 generated -> 157 clean, **0.00 USD** (all seven local) |

Phase 4's headline case reproduces exactly through the join:
`..._random_pick_v2_openrouter_qwen35_flash` reads **27.28434 USD over 549 generated**, 132
clean, **0.2067 USD / usable persona**. The grid's accuracy maximum,
`openrouter_kimi_k3 x all_generate_evaluate_random_pick_v2` at **0.841979**, is also its most
expensive point at **0.7171 USD / usable persona** -- against the cheapest metered point,
`openrouter_gpt_oss_120b x all_pick_v2` at **0.000408 USD** for **0.512** fidelity. That is a
**1,758x** cost span across a 0.33 fidelity span, which is the trade-off the figure exists to
put in front of a reader and deliberately does not resolve into a score. The best local model,
`ollama_mistral_nemo_12b x all_generate_evaluate_random_pick_v2` at **0.754234**, sits at a
measured zero on the metered axis.

##### The disabled-dependency decision

`generation_metadata` was `enabled: false` in `analysis_workflow.yaml`. A disabled task is
never added to `completed_tasks`, so every dependent is `SKIPPED_DEP` and never runs --
shipping `cost_efficiency` against a disabled upstream would have shipped a node that cannot
fire, silently. **It is now `enabled: true`**, with the reason recorded inline beside the flag.
That is the honest wiring: its summary CSV is a declared input, it has already run
successfully for this grid (Phase 0.3), and it performs no LLM work. An operator who has
already run it ticks `bypass` on that node rather than turning it off, which unlocks the
dependent without re-running anything.

### Phase 6: documentation and restaging
**Goal:** The deck stops carrying hand-built figures.

- [x] 6.1 — `CLAUDE.md`: both processes in the analysis-layer paragraph and the DAG description.
- [x] 6.2 — `docs/architecture/sub-packages.md` + `commands.md`.
- [x] 6.3 — Update the manuscript folder's `figures selection/SOURCES.md` to move F05 and F26 from
      "hand-made" to the pipeline-backed table, with their new source paths.

**Files Modified:** `CLAUDE.md`, `docs/architecture/sub-packages.md`,
`docs/architecture/commands.md`, the new ADR
`docs/development/decisions/2026-08-20-cost-denominator-and-reconstructed-join-key.md`, and — outside
the repository — `.../40_llm-population-fidelity-benchmark/figures selection/SOURCES.md`.
**Dependencies:** Phase 5.

#### 6.1-6.3 result — what the docs now say

- **`CLAUDE.md`.** `validation_attrition/` is inserted immediately after `population_cap/` in the
  analysis-layer paragraph (it re-reads the gate), `cost_efficiency/` immediately after
  `generation_metadata/` (it re-reads that telemetry over a different denominator). The registry/DAG
  paragraph no longer says `realism_ranking` is the *only* chained node: `validation_attrition` is
  named as hanging directly off the gate and as the one process whose row grain includes the
  withdrawals, and `cost_efficiency` as the second node whose upstreams are analysis nodes, with its
  three declared inputs and the reason `generation_metadata` had to be flipped to `enabled: true`
  (a disabled task never enters `completed_tasks`, so every dependent sits at `SKIPPED_DEP`).
- **`docs/architecture/sub-packages.md`.** Two bullets in the existing per-process format, placed to
  match: `validation_attrition/` after `population_cap/`, `cost_efficiency/` after
  `realism_ranking/`. The header's package list and its one-line DAG sketch both name them. The
  `utils/` sub-list gains one bullet for `attrition_csv.py` / `cost_csv.py`, which is where the
  absent-vs-zero property and the "`generation_multiplier` is read, not recomputed" seam are stated.
- **`docs/architecture/commands.md`.** Two rows in the registry table (appended, matching the
  registry YAML's own order), two commented invocation blocks in the `bash` catalog, and one new
  prose subsection, *Attrition and cost: two processes that carry their denominator*, sized to match
  the existing *Persona realism: two tasks, one seam*.
- **The ADR**, `2026-08-20-cost-denominator-and-reconstructed-join-key.md`, in the house
  context/decision/consequences shape of the three existing ones. Decision 1 is the cost denominator,
  carrying the measured 4.758× table and the finding that kills option (b) twice over — undefined for
  withdrawals, and wrong by ~15% in a retention-correlated direction where it *is* defined. Decision 2
  is the reconstructed join key: why the honest alternative (a `slug` column on
  `generation_metadata`'s summary) was rejected, and why reconstruction is acceptable *here
  specifically* — one of the three inputs publishes both spellings, so the rule is proved against
  live data on every read rather than trusted.
- **`SOURCES.md`** (outside git). F05 → `validation_attrition/swedish_02_mapped_validity_grid.*` and
  F26 → `cost_efficiency/swedish_02_cost_vs_fidelity.*` now sit in the pipeline-backed table; the
  pending-plan paragraph is replaced by a dated note recording what each staged image currently gets
  wrong (F05's two pre-full-N percentages and its three withdrawn-not-thin cells; F26's superseded
  8-model sweep). `swedish_02_attrition_funnel.*` is added to *artifacts that exist but are not
  staged* — it is new and has no F-number, and inventing one would put a number in the deck's
  vocabulary that no slide uses. **No image was copied**: the file says so explicitly and names the
  run order for the operator who does it.

One staleness was found and **not** fixed, because it belongs to another branch's plan: the
`population_cap/` bullet in `sub-packages.md` still ends "When fewer than N clean personas exist,
`cap_combo` cap-shorts with a loud warning ... it never fails the batch", which the full-N rule
replaced with outright exclusion. It is adjacent to, but not part of, this feature.

---

## Testing Plan

### Unit Tests
- [x] Hand-computed five-stage funnel fixture: known counts in, known `retention_rate` and
      `generation_multiplier` out (`pytest.approx`, never exact float equality).
- [x] Excluded combination (`selected = 0`, `clean = 9`): `generation_multiplier` is populated
      (150/9), `retention_rate` is 0.06, nothing divides by zero.
- [x] Degenerate `clean = 0` over a non-empty pool: `generation_multiplier` is `None`, the row still
      exists, and nothing is inf. **Corrected while implementing Phase 2:** this bullet originally
      read "both ratios are `None`", which contradicts the binding Definitions above —
      `retention_rate = clean / generated` is `None` only when `generated == 0`, so `0/150` is a
      measured `0.0`, and it is the strongest finding this artifact can report about a combination
      (it generated a pool and kept none of it). Reporting it as absent would erase exactly that.
      Both ratios are `None` only in the `generated = 0` case below.
- [x] `generated = 0`: both rates are `None`, no `ZeroDivisionError`.
- [x] Missing `raw_total` raises, and the message names the re-run command.
- [x] Counts disagreeing across `_index.json` and `_summary.csv` raises naming both files.
- [x] Unmatched `model`/`method` in the cost join raises naming the key and both files.
- [x] Empty join raises rather than writing an empty CSV.
- [x] Unmetered model: `cost_per_usable_persona` is `0.0` and `unmetered` is `true` — never `None`,
      which means absent.
- [x] Absent pricing entry raises (distinct from unmetered). *(Done in Phase 4 at the raw-cost
      boundary: it raises before any telemetry is read, so a thin pool cannot mask a config gap.
      Phase 5 inherits it through the loader.)*
- [x] Schema round-trip: empty cell reads back as `None`, never `0.0`. *(Done for the attrition
      schema in Phase 2; repeated for `cost_csv.py` in Phase 5, where the same test also pins
      the converse — an unmetered model's **measured** `0.0` must not come back as `None`.)*

### Integration Tests
- [x] End-to-end on a `tmp_path` fixture built through `analysis_output_dir` (never path literals),
      mirroring `test_realism_ranking_e2e.py`: gate artifacts → attrition → cost, asserting the
      expected files appear and key numbers match. *(Built in
      `tests/_cost_efficiency_fixtures.py`. It starts from the **attrition contract** rather
      than from the gate's raw `_index.json`: that contract is `cost_efficiency`'s declared
      input, and the gate → attrition half already has its own end-to-end coverage from
      Phase 2. Running the gate here would test that half twice and this one no better.)*
- [x] Both CLIs invoked **by subprocess** (the flags and argument resolution at the edge are the
      point), asserting `returncode == 0`. *(Plus the negative case: a broken join must exit 1
      with the reconciliation message on stderr.)*
- [x] `--no-charts` asserted as a real absence of `*.png` **and** `*.svg`; a second run asserts both
      formats appear per figure.
- [x] A populated heatmap cell is **not** rendered as missing — the specific regression ADR
      `2026-08-12` records, where a renderer read `cell["rate"]` by literal key and greyed
      everything without raising.
- [x] Re-running twice produces identical CSV/JSON bytes (idempotency; PNG/JSON/CSV only — SVG is
      not byte-reproducible).

### Manual Verification
- [x] The mapped-validity grid reproduces the audited `swedish_02` numbers: gemma4_e4b × E = 6.0,
      deepseek_r1_14b × E = 6.7, llama31_8b × E = 7.3, flagship A–D range 77.3–100.0.
- [x] All 7 withdrawn combinations are visible and marked as withdrawn, not merely thin.
- [x] `matplotlib.use("Agg")` before package imports in every chart test.

---

## Documentation Plan

- [x] `CLAUDE.md` — both processes in the analysis-layer description and the DAG.
- [x] `docs/architecture/sub-packages.md`, `docs/architecture/commands.md`.
- [x] ADR for the two decisions that will otherwise be re-litigated: the reconstructed join key
      (rather than adding a slug column upstream), and the cost-denominator choice
      (`05` §9: record context / decision / consequences).
      *(`docs/development/decisions/2026-08-20-cost-denominator-and-reconstructed-join-key.md`.)*
- [x] `figures selection/SOURCES.md` in the manuscript folder. *(Provenance only — restaging the
      PNGs themselves stays the separate operator copy step this plan scoped out.)*

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
- ADR written by this plan: `docs/development/decisions/2026-08-20-cost-denominator-and-reconstructed-join-key.md`
- ADRs: `docs/development/decisions/2026-08-07-persona-realism-per-combination-split.md`,
  `2026-08-07-per-clash-contract-and-severity-drivers.md`,
  `2026-08-12-self-contained-typicality-axis.md`
- `~/.claude/knowledge/data-pipeline-engineering/` — `01` §Axis 5 (two-level pattern),
  `02` §§3,5,6,8,9, `03` §§4,6,7, `05` §§1,3,5,6,9
