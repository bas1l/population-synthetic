# Plan: Model × method TV-similarity heatmap

**Date:** 2026-08-11
**Author:** Basil
**Status:** In Progress
**Base Branch:** `dev`
**Branch:** `feature/model-method-tv-heatmap`

---

## Overview

Add a **model × method** heatmap of overall TV-similarity to the `model_ranking`
process, so the study's headline claim — *how you elicit dominates which model you pick* —
is emitted as a first-class artifact instead of being rebuilt by hand for the deck. Every
cell carries its persona count `n` and is explicitly marked when it sits below the
requested cap, which the existing tables do not show; and models with no adequately-sampled
cell at all are partitioned out of the ranking entirely rather than being interleaved with
models that have one. The figure is a pure consumer of the result dict `model_ranking`
already builds; it introduces no new statistic and no new analysis process.

## Problem Statement

The analysis layer emits per-attribute detail (`plot_model_fidelity_table`,
`manuscript_tables.py:274`) and a per-strategy roll-up (`plot_method_fidelity_table`, :346),
but nothing that shows both factors at once as a grid. That figure was produced by hand for
the deck (`figures/swedish_02_model_method_tv_heatmap.py` in the external manuscript
folder), so it is not reproducible from a pipeline run, drifts as soon as the analysis is
re-run, and carries no provenance.

A second problem is more serious than the missing figure. Seven of the 50 Swedish
combinations rest on **7 to 49 personas** rather than the requested 100, because the
validation gate discarded the rest. Those cells appear in the shipped `models_table` with no
indication of their `n`, which reads as a model ranking when it is sampling noise. The
persona count is available (`combos[slug]["n"]`, `builder.py:188`) and the requested cap is
available (`requested_n` in every `population_cap/_index.json` entry), but no figure joins
them. Any two-factor grid that omits this is more misleading than the tables it replaces,
because it invites direct cell-to-cell comparison.

## Goals

### In Scope

1. A new `plot_model_method_heatmap` in `model_ranking/charts.py`: rows = models,
   columns = methods (strategies), cell = overall TV-similarity, emitted as PNG **and** SVG.
2. Every cell annotated with its value and its persona count `n`; every cell whose
   `n < requested_n` visually marked, with `requested_n` read from the gate's own record.
3. Rows partitioned into two tiers by evidence sufficiency: a model with at least one
   full-`n` cell is **ranked**, on those cells only; a model with none is **unranked**, placed
   after an explicit visual break and annotated with the reason. The rule keys on
   `n >= requested_n`, never on a literal persona count, so it generalises to any run.
4. A row marginal reporting each model's ordering key — its best qualifying score, the method
   that achieved it, and how many cells the key rested on — and a per-method column-mean
   marginal computed over full-`n` cells only, printing the count it averaged. Both are
   visually separated from the grid so neither can be misread as a cell.
5. Extraction of the shared visual grammar into `model_ranking/table_style.py`, so the new
   figure matches its two sibling tables by construction rather than by copy.
6. Wiring into `scripts/analyze/rank_models.py` behind the existing `--no-charts` flag.

### Out of Scope

- The `cost_efficiency` and `validation_attrition` processes, and the `raw_total` addition to
  `CapSummary`. Those remain in the parent plan (see References); this plan is independent of
  all three and requires no gate re-run.
- Changing any statistic, ranking, or the fidelity computation itself. The figure is a pure
  consumer of `build_performance_comparison`'s existing output.
- Retiring, restyling, or renaming the existing `{country}_heatmap.png` or the two manuscript
  tables. They ship unchanged.
- Propagating the figure into the external manuscript/deck — a separate `/sync-manuscript`
  step once the artifact exists.
- Any new analysis process, registry entry, or GUI workflow task. This adds a chart to an
  existing process, not a node to the DAG.

## Success Criteria

- [x] `python scripts/analyze/rank_models.py --country swedish_02` writes
      `{country}_model_method_heatmap.png` **and** `{country}_model_method_heatmap.svg` into
      the `model_ranking` output folder.
- [x] `--no-charts` suppresses both files; the JSON and CSV artifacts are unaffected either way.
- [x] Each cell's printed value equals `overall_tv_similarity × 100` from
      `{country}_performance.csv` for the same `(model, strategy)`, to 1 decimal.
- [x] Column order equals `strategy_complexity_order(metadata["strategies"])` exactly, and is
      identical to `result["methods_matrix"]["strategies"]`.
- [x] Every model with at least one full-`n` cell (`n >= requested_n`) is in Tier 1; every
      model with zero full-`n` cells is in Tier 2. The partition is computed from `n` against
      the slug's own `requested_n` — no literal cap threshold appears in the rule, the
      implementation, or the tests, and the test fixtures use a `requested_n` other than 100 so
      a hardcoded threshold cannot pass by coincidence.
- [x] Tier 1 rows precede Tier 2 rows, separated by an explicit break (gap + rule line) that is
      distinguishable in greyscale and not confusable with the marginal dividers or the
      per-cell thin marking. The Tier 2 block is annotated as unranked, stating the reason.
- [x] Tier 1 row order is `(-max_over_full_n, -mean_over_full_n, model_id)` and Tier 2 row
      order is `(-max_over_all_cells, model_id)`; the same input yields the same order on
      repeated runs, including under a constructed tie in each tier.
- [x] A Tier 1 model's ordering key ignores its thin cells: a model whose single best cell is
      thin ranks on its best **full-`n`** cell instead, and its thin cells are still drawn and
      still marked.
- [x] The row marginal prints the ordering key — best qualifying score, argmax method, and the
      number of cells the key was computed over — flagged provisional for Tier 2 rows.
- [x] The column marginal averages **full-`n` cells only** and prints how many cells it
      averaged, so an excluded thin cell is visible rather than silent.
- [ ] On `swedish_02` (`requested_n = 100`) Tier 2 contains exactly `ollama_llama31_8b`, whose
      five cells are all thin (n = 11, 19, 22, 34, 49). `ollama_gemma4_e4b` and
      `ollama_deepseek_r1_14b` stay in Tier 1, each ranked on its four full-`n` cells with one
      thin cell marked in the `all_generate_evaluate_random_pick_v2` column (n = 7 and n = 9).
      The remaining seven models have five full-`n` cells each.
- [x] Every cell whose `n < requested_n` is marked and prints its `n`; a cell at
      `n == requested_n` is unmarked.
- [ ] On `swedish_02` the marking fires on exactly these 7 cells and on none of the other 43:
      `all_generate_evaluate_random_pick_v2` × `ollama_gemma4_e4b` (n=7),
      × `ollama_deepseek_r1_14b` (n=9), × `ollama_llama31_8b` (n=11);
      `all_pick_dag_v2` × `ollama_llama31_8b` (n=19);
      `all_pick_v2` × `ollama_llama31_8b` (n=22);
      `all_generate_pick_v2` × `ollama_llama31_8b` (n=34);
      `all_generate_evaluate_pick_v2` × `ollama_llama31_8b` (n=49).
- [x] Model tick labels are coloured by `classify_hosting` provenance, using the same colours
      and legend text as `plot_model_fidelity_table`.
- [x] Ramp, text-contrast rule, colourbar, and NaN grey are produced by calling the same
      functions the sibling tables call — no re-specified colour values in `charts.py`.
- [x] The two shipped manuscript tables render identically before and after the Phase 1
      extraction (structural assertions, not byte comparison).
- [x] `pytest` passes, including the new heatmap tests.
- [x] `ruff check src/` clean.

## Definitions

- **method:** a strategy id (e.g. `all_generate_evaluate_pick_v2`). The column axis. "Method"
  is the manuscript's word for what the code calls a strategy; the figure labels columns with
  the strategy id, not a prose name.
- **cell value:** `combos[slug]["overall"]["tv_similarity_mean"]` for the combination at that
  `(model, method)`, rendered as `value × 100` to one decimal — the same rescaling
  `_annotate_and_box` already applies (`manuscript_tables.py:113`). Colour and any argmax stay
  on the underlying 0–1 value.
- **n:** `combos[slug]["n"]`, i.e. `r.n_synthetic` (`builder.py:188`) — the number of personas
  the capped mapped file actually contains for that combination.
- **requested_n:** the cap requested for that slug, read from its `population_cap/_index.json`
  entry. It is per-slug, not a global constant, and is never assumed or defaulted.
- **full-`n` cell / thin cell:** a cell is **full-`n`** iff `n >= requested_n`, and **thin** iff
  `n < requested_n`. Boundary: `n == requested_n` is full-`n`, not thin. A thin cell's value
  rests on fewer personas and is not comparable to a full-`n` one. The threshold is always the
  slug's own `requested_n`: no literal persona count appears in the rule, the implementation,
  or the tests, because the cap is a config value that varies per run.
- **Tier 1 (ranked):** a model with **at least one** full-`n` cell. It is ranked, on its
  full-`n` cells only; its thin cells are still drawn and still marked, they simply do not
  decide its rank.
- **Tier 2 (unranked):** a model with **zero** full-`n` cells. No part of its row is comparable
  to Tier 1 on equal evidence, so it is not interleaved with Tier 1 — it sits after the break,
  ordered among its own tier and annotated as unranked.
- **ordering key (rows):** Tier 1 sorts by `(-max_over_full_n, -mean_over_full_n, model_id)`;
  Tier 2 sorts by `(-max_over_all_cells, model_id)`. Both keys are total, so the row order is
  deterministic within each tier and stable across runs.
- **argmax method:** the method achieving a model's ordering maximum — over full-`n` cells for
  Tier 1, over all cells for Tier 2. Ties within a row resolve to the first in
  `strategy_complexity_order`, so the reported method is deterministic.
- **the break:** the gap plus rule line separating Tier 1 from Tier 2, with the Tier 2 block
  annotated as unranked and carrying the reason (*every cell below the requested cap*). It is a
  distinct device from the per-cell thin marking and from the marginal dividers, and must read
  as such rather than as a third kind of separator.
- **row marginal:** for a Tier 1 model, its best full-`n` score, the argmax method, and the
  count of full-`n` cells the key was computed over. For a Tier 2 model, its best score over all
  cells, flagged provisional. Deliberately **not** a mean — a mean beside a max-ordered axis
  would show one quantity while the rows are sorted by another.
- **column marginal:** the per-method mean across models, computed over **full-`n` cells only**
  and printed with the count of cells averaged. Intentionally asymmetric with the row marginal:
  the column axis answers "how does this method do in general", the row axis "how good can this
  model get".
- **marked:** rendered so a thin cell is unmistakable at slide size without reading the
  number — the concrete encoding is chosen in Task 2.6 and must survive greyscale printing.
- **styled as a sibling:** uses the *same* ramp, text-contrast rule, colourbar, NaN grey, and
  provenance colouring **by calling the same functions**, not by re-specifying the values.
- **behaviour unchanged (Phase 1):** the two manuscript tables produce the same grid values,
  same row/column order, same annotation text, same best-cell boxing, same colours, and the
  same PNG+SVG pair as before the extraction. Not byte-identical files.

---

## Technical Design

### Approach

The figure reads only `model_ranking`'s own result dict, so it belongs **inside**
`model_ranking` as a new chart function — a sibling of `plot_performance_heatmap`
(`charts.py:52`) — not as a new process. No registry entry, no DAG change, no new script.

Three points were resolved against the code before writing this plan.

**1. `methods_matrix` cannot supply the grid.** The result dict already carries a
`methods_matrix` key (`builder.py:221`), which is tempting to reuse. It is
**strategy × attribute**, with models averaged away (`_methods_matrix`, `builder.py:52-92`) —
a different figure from the one this plan builds. The model × method grid must therefore be
derived from `combos`, each entry of which carries `model`, `strategy`, `n`, and
`overall.tv_similarity_mean` (`builder.py:184-206`). That derivation is a plain regroup, not
a new statistic.

**2. Column order is already config-derived and reusable.** `_methods_matrix` orders its
strategies via `_ordered_strategies` → `strategy_complexity_order` (`builder.py:47-49`), so
`result["methods_matrix"]["strategies"]` is a ready-made ordered column list. The new chart
nonetheless calls `strategy_complexity_order(metadata["strategies"])` **directly**, so the
chart does not depend on an unrelated aggregation's internals; a test asserts the two agree,
which pins the equivalence without creating the coupling.

**3. `requested_n` exists today — no gate change is needed.** Every entry in
`population_cap/_index.json` already carries `requested_n` (written from `CapSummary`,
`cap.py:51-66`, via `scripts/analyze/cap_populations.py:196`); verified on disk as
`requested_n: 100` across all 50 `swedish_02` entries. The parent plan's `raw_total` addition
to `CapSummary` is **not** a prerequisite for this figure, and this plan does not depend on
it. Nothing in `src/`, `scripts/`, or the GUI currently reads that stage-level index — it is
write-only telemetry — so this plan makes `model_ranking` its first reader. The read path is
an established pattern: `model_ranking/loader.py:179-182` already reads the sibling
`population_cap/_mapped/_index.json` via `resolve_mapped_dir` (`capped_source.py:89-114`).
The new read resolves the stage directory with `resolve_stage_source` (`capped_source.py:66-86`)
and fails loudly — a missing index file, or a slug with no entry, raises with the offending
path named. There is no default cap and no inferred one.

**4. Rows are partitioned by evidence first, then ranked within the partition.** A single
block of rows conflates two questions: *how good can this model get* and *is there enough data
to say*. The rule separates them, and it is a general rule keyed on `n` against the slug's own
`requested_n` — no literal persona count anywhere.

- **Tier 1** is every model with at least one full-`n` cell. It ranks on `max` of
  `overall_tv_similarity` over its **full-`n` cells only**, tie-broken by the mean over those
  same cells, then by model id. Its thin cells are still drawn and still marked; they are
  simply not allowed to decide the rank.
- **Tier 2** is every model with zero full-`n` cells. Nothing in its row is comparable to Tier 1
  on equal evidence, so it is not interleaved: it goes after an explicit break, ordered among
  itself by `max` over all its cells, annotated as unranked with the reason.

Ranking on the maximum rather than the mean is deliberate: the question the grid is asked is
*how good can this model get, and under which elicitation*, and a mean answers a different one —
it drags a model down by its weak methods, conflating the two factors the grid exists to
separate.

Restricting the Tier 1 key to full-`n` cells repairs a real defect in the earlier draft of this
plan. A maximum taken over a mixed row selects for upward noise, and thin cells are the noisiest
cells in the grid, so an all-cells maximum systematically promotes the models with the *worst*
retention — the exact opposite of what the figure should do. On `swedish_02` it put
`ollama_llama31_8b` near the top of the axis on a 49-persona cell. Under the tier rule that
model has no full-`n` cell at all, so it drops to Tier 2 and is visibly unranked rather than
invisibly first.

The partition is a rule, not a per-dataset exception, and it degrades correctly at both ends:
a fully-capped run puts every model in Tier 1 and draws no break at all, and a run in which
nothing reached the cap puts every model in Tier 2 and says so, rather than presenting a
confident ranking over uniformly thin evidence.

The marginals follow the same logic. The row marginal reports the ordering key, so it shows the
best qualifying score, its argmax method, and how many cells the key rested on — a rank built on
one full-`n` cell is not the same claim as one built on five, and the figure must say which. The
column marginal stays a per-method mean across models but is computed over full-`n` cells only:
a method's mean should not be moved by a 7-persona cell. It prints the count it averaged, so an
excluded cell is visible rather than silent. The asymmetry between the two marginals is
intended, and is stated in the Definitions so a reviewer does not read it as an oversight.

**5. The threshold predicate and the cap-index read are shared infrastructure, not chart
internals.** The parent plan's `cost_efficiency` and `validation_attrition` figures need the
same per-slug `requested_n` lookup and the same thin/full-`n` test. Burying them in `charts.py`
would force those two to re-derive the rule, and three independent definitions of *did this
combination survive the cap* is precisely the drift the repo's config invariant exists to
prevent. They belong in a new `analysis/utils/cap_index.py`, which reads
`population_cap/_index.json` fail-fast with the offending path named, exposes the per-slug
`requested_n` lookup, and exposes the predicate. It knows nothing about matplotlib, figures,
which metric is plotted, or which country is being analysed — so all three consumers can import
it without inheriting anything from each other.

**One extraction subtlety.** `_categories_on_top` (`manuscript_tables.py:127`) is not
metric-agnostic as written: it hardcodes `attributes + ["overall"]` and `len(attributes) + 1`
columns. Extracting it verbatim would give the new figure a spurious "overall" column. The
extraction must therefore generalise its signature to take an explicit label list, with the
tables passing `attributes + ["overall"]` at their call sites — a behaviour-preserving change
for them, and the only signature change in Phase 1.

Per the pipeline-engineering guides (`02-architecture-principles-and-patterns.md`), the new
chart is a **filter** — result dict in, figure paths out — is **idempotent** (re-running
overwrites, never appends), and puts its **error boundary** at the read step: the cap-index
read raises rather than silently degrading to an unmarked figure.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| New chart function inside `model_ranking` | Reads only existing in-process data; no DAG change; ships with every rank run | Grows an already large `charts.py` (314 lines) | **Chosen** |
| Its own analysis process | Symmetric with the parent plan's other two items | Would re-read and re-derive `performance.json` for no reason; a process per figure does not scale | Rejected |
| Extract `table_style.py`, both tables and the heatmap call it | One definition of the visual grammar; the figure matches its siblings by construction | Touches two shipped renderers | **Chosen** |
| Copy the six helpers into `charts.py` | No risk to the shipped tables | Two definitions of the same ramp and contrast rule; they drift on the first restyle, which is exactly the failure this figure exists to avoid | Rejected |
| Derive the grid from `combos` | The only source that carries both factors plus `n` | A regroup step in the chart | **Chosen** |
| Two-tier partition: rank on full-`n` cells, unranked models after a break | Never ranks a model on evidence it does not have; keys on `n` vs `requested_n`, so it is a general rule rather than a fix for one dataset; the retention failure stays visible instead of being hidden or silently rewarded | A second visual device to explain, and the row axis is no longer one uniform block | **Chosen** |
| Rank within Tier 1 by **row maximum** over full-`n` cells | Ranks a model by its best-case elicitation, which is the question the figure is asked | Ignores how a model fares under its other methods — deliberately; that is the column axis's job | **Chosen** |
| Order rows by row mean | Uses every cell; robust to one lucky method | A model's average is dragged down by its weak methods, conflating the two factors the grid is meant to separate; also incoherent with a best-score row marginal | Rejected |
| Single block ordered by `max` over all cells, thin included | No partition to explain; every model keeps a rank | A maximum over a noisy low-`n` cell promotes exactly the worst-retention models — on `swedish_02` it puts `ollama_llama31_8b` first on 49 personas. This is the rule the two-tier partition replaces | Rejected |
| Demote any model having **any** thin cell | Simplest possible predicate | Discards sound evidence: `ollama_gemma4_e4b` and `ollama_deepseek_r1_14b` each have four full-`n` cells and one thin one, and would lose a well-supported rank over a single bad combination | Rejected |
| Drop thin cells from the figure entirely | No low-`n` value is ever displayed | The retention failure is itself a finding; hiding it makes the grid look complete when it is not, and removes the evidence a reader needs to judge the tiering | Rejected |
| Derive the grid from `methods_matrix` | Already aggregated and ordered | It is strategy × attribute (`builder.py:52-92`) — models are averaged away, so the model axis does not exist in it | Rejected |
| `requested_n` from `population_cap/_index.json` | The gate's own record; per-slug; already on disk | Makes `model_ranking` depend on `population_cap` having run | **Chosen** |
| `requested_n` from a new `--requested-n` CLI flag | No new read | Hardcodes a value config already owns, and lets the figure disagree with the gate that produced the data | Rejected |
| Infer the cap as `max(n)` across combos | No new read at all | Inference, not config; silently wrong when every cell is thin — the run in which the tiering matters most — and the failure is invisible | Rejected |
| Marking as a cell-hue change | Immediately visible | Collides with the score ramp — the reader cannot tell low fidelity from low `n` | Rejected |

### Architecture & Module Contracts

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `model_ranking/table_style.py` *(new)* | The shared visual grammar of the manuscript-style grids: inferno ramp with NaN grey, text-contrast rule, percentage colourbar, best-cell selection, divider, top-placed column labels, provenance colours/labels | style params + numeric arrays → matplotlib primitives | Which metric is plotted; the country; model/strategy names; attribute names; `n`; the cap; file paths; the result dict's shape |
| `model_ranking/charts.py::plot_model_method_heatmap` *(new)* | Draw overall TV-similarity as model × method, with `n`, thin marking, the two-tier row partition and its break, and the two marginals | `result` dict + `requested_n` map + out path → `(png, svg)` paths | How TV was computed; how the cap was chosen; where the cap index lives; file discovery |
| `analysis/utils/cap_index.py` *(new, shared)* | Read `population_cap/_index.json` fail-fast; expose the per-slug `requested_n` lookup and the full-`n`/thin predicate. Shared with the parent plan's two figures | output base → `{slug: int}`; `(n, requested_n) → bool` | matplotlib; figures; layout; colours; which metric is plotted; which country; which process consumes it |
| `model_ranking/manuscript_tables.py` *(changed)* | Unchanged responsibility; imports the shared grammar instead of defining it | unchanged | Anything new — this phase removes code, it does not add behaviour |
| `scripts/analyze/rank_models.py` *(changed)* | Additionally call the new chart when charts are enabled | unchanged inputs → one more artifact pair | The figure's internals |

```
src/population_synthetic/analysis/
├── utils/
│   └── cap_index.py          # NEW (shared): _index.json read, per-slug requested_n lookup,
│                             #      full-n / thin predicate. Imported by this figure and by
│                             #      the parent plan's cost_efficiency + validation_attrition
└── model_ranking/
    ├── table_style.py        # NEW: inferno cmap + NaN grey, text-contrast, percentage
    │                         #      colourbar, best-cells, divider, top labels, host colours
    ├── manuscript_tables.py  # imports from table_style; behaviour unchanged
    └── charts.py             # + plot_model_method_heatmap()

scripts/analyze/rank_models.py      # + call behind --no-charts, + docstring output list
tests/test_manuscript_tables.py     # extended (do NOT create a parallel tables test file)
tests/test_cap_index.py             # NEW: read/raise + predicate boundary
tests/test_model_ranking_charts.py  # NEW: heatmap value/order/tier/marking assertions
```

Moved into `table_style.py` (public, from `manuscript_tables.py`): `_overall_divider` :64,
`_text_color_for_rgb` :69, `_best_cells_per_column` :76, `_categories_on_top` :127
(generalised), `_inferno_cmap` :136, `_add_percentage_colorbar` :145, plus the constants they
depend on — `_GREY` :48, `_BOX_EDGE` :49, `_ANNOT_FONTSIZE` :50, `_CMAP_NAME` :51 — and the
provenance pair `_HOST_COLORS` / `_HOST_LABELS` :56-57, which the new figure needs for its
model tick labels.

Staying private in `manuscript_tables.py` (table-specific): `_global_best_strategy` :160,
`_sort_key_desc` :179, `_model_grid` :184, `_method_grid` :236, `_shared_norm` :262,
`_latex_escape` :405, `_latex_number` :413, `_write_latex_table` :431.

`_annotate_and_box` :93 also stays, and the reason is worth recording: it is *not* strictly
table-specific — it takes `best_cells` as a parameter, so it would generalise — but the new
figure needs a different annotation (value **and** `n`, plus the thin marker) and would
not call it. Extracting it would move code that only one caller uses.

**Config-is-source-of-truth obligations.** The figure hardcodes no model list, strategy order,
colour value, or cap. Method order comes from `analysis/utils/axes.py::strategy_complexity_order`;
hosted/local provenance from `metadata.model_hosting`, populated by `classify_hosting`
(`hosting.py:63`) from `config/analysis/model_ranking/provider_hosting.json` and already wired
at `rank_models.py:86,276-279`; colours from `table_style.py`; `requested_n` from the gate's
index via `analysis/utils/cap_index.py`; the output folder from `analysis_output_dir(id, base)`.
In particular the tier threshold is `n >= requested_n` and never a literal: no hardcoded cap
value may appear in the rule, the implementation, or the tests, since the cap varies per run and
a hardcoded copy would silently disagree with the gate that produced the data.

---

## Implementation Plan

### Phase 1: Extract the shared table style
**Goal:** One definition of the manuscript grid's visual grammar, so the new figure matches its
siblings by construction rather than by copy.

- [x] Task 1.1 — Create `model_ranking/table_style.py`; move `_inferno_cmap`,
      `_text_color_for_rgb`, `_add_percentage_colorbar`, `_best_cells_per_column`,
      `_overall_divider`, `_categories_on_top` into it as public functions, together with
      `_GREY`, `_BOX_EDGE`, `_ANNOT_FONTSIZE`, `_CMAP_NAME`, `_HOST_COLORS`, `_HOST_LABELS`.
      Keep the deferred-`Agg` matplotlib import convention the module already follows.
- [x] Task 1.2 — Generalise `categories_on_top` to take an explicit label list instead of
      hardcoding `attributes + ["overall"]` and `len(attributes) + 1`
      (`manuscript_tables.py:127-133`); update both table call sites to pass
      `attributes + ["overall"]`, preserving their current output exactly.
- [x] Task 1.3 — Re-point `manuscript_tables.py` at the new module and delete the moved
      definitions; the module docstring's claim about following the charting conventions stays
      true, so no rewrite is needed beyond the import.
- [x] Task 1.4 — Extend the **existing** `tests/test_manuscript_tables.py` (373 lines, 15
      tests) to assert the extraction preserved behaviour: same grid values, row/column order,
      annotation text, best-cell boxing, host label colours, and the PNG+SVG pair. Assert
      structural properties, not byte-identical PNGs — matplotlib output is not stable across
      metadata and font hinting. Do **not** create a parallel `tests/test_model_ranking_tables.py`.

**Phase 1 implementation notes (three deviations from the task text, all forced by the code
having moved since the plan was written):**

1. **Three of the named items no longer exist in `manuscript_tables.py`.** `_GREY`, `_CMAP_NAME`
   and `_text_color_for_rgb` were extracted in the interim into
   `analysis/utils/palette.py`, as `MISSING_COLOR`, `HEATMAP_CMAP` and `text_color_for_rgb` —
   the colour vocabulary shared by *every* analysis-layer heatmap, not only the manuscript
   family. Re-creating them inside `table_style.py` would have produced a second definition of
   the house ramp, which is the exact drift this extraction exists to prevent. `table_style.py`
   therefore builds on `palette` (it imports `heatmap_cmap`) rather than restating it, and the
   contrast rule stays a single `palette.text_color_for_rgb`. Phase 2's `charts.py` calls the
   same two modules, which satisfies the "no re-specified colour values" criterion unchanged.
2. **`_overall_divider` is renamed `vertical_divider(ax, n_columns_left)`.** The module contract
   forbids `table_style` from knowing about attribute names or the metric; "overall" is the
   tables' own column concept. The parameter is now a column index, so the heatmap can use the
   same rule to fence off its marginals.
3. **One constant added beyond the list: `HOST_DEFAULT_CLASS = "hosted"`.** The presentation
   fallback for a model absent from `metadata.model_hosting` appeared as a bare literal at three
   call sites. Naming it in `table_style` is behaviour-preserving and is what lets Phase 2's
   Task 2.7 use "the same presentation default the tables use" rather than a fourth copy of the
   literal.

The extension went from 15 to 25 tests: the five duplicated `plt.subplots` spy blocks collapsed
into one `_render` harness, and the new assertions cover the drawn grid values, the annotation
text and its `× 100` rescaling, best-cell boxing *and* bolding, the column labels at both table
call sites (pinning Task 1.2), the Overall divider's position, and the extracted helpers'
own contracts — `categories_on_top` on a list with no "overall" entry, `best_cells_per_column`
ties and all-NaN columns, `inferno_cmap`'s NaN grey and its copy-not-mutate guarantee, and the
colourbar's label-only percentage scaling.

**Files Modified:**
- `src/population_synthetic/analysis/model_ranking/table_style.py` — new
- `src/population_synthetic/analysis/model_ranking/manuscript_tables.py` — import from it; drop the moved helpers and constants
- `tests/test_manuscript_tables.py` — extended with the equivalence assertions

**Dependencies:** None

### Phase 2: The model × method heatmap
**Goal:** The figure shipped as a `model_ranking` artifact, honest about `n`.

- [x] Task 2.1 — New `analysis/utils/cap_index.py`, shared with the parent plan's two figures:
      resolve the stage directory with `resolve_stage_source` (`capped_source.py:66-86`), read
      `_index.json` into `{slug: requested_n}`, and expose the full-`n`/thin predicate
      (`n >= requested_n`). Raise with the path named when the file is absent, and raise when a
      requested slug has no entry. No default, no inferred cap, no literal threshold.
- [x] Task 2.2 — `plot_model_method_heatmap(result, requested_n, out_path)` in `charts.py`:
      regroup `combos` into a model × method grid of `overall.tv_similarity_mean` and `n`;
      columns ordered by `strategy_complexity_order(metadata["strategies"])`. Missing
      `(model, method)` pairs are `NaN`, excluded from every key below, and rendered by the
      ramp's `set_bad` grey.
- [x] Task 2.3 — Partition the rows using the shared predicate: Tier 1 = models with at least
      one full-`n` cell, Tier 2 = models with none. Sort Tier 1 by
      `(-max_over_full_n, -mean_over_full_n, model_id)` and Tier 2 by
      `(-max_over_all_cells, model_id)`; emit Tier 1 first. Record each model's argmax method
      alongside its row — over full-`n` cells for Tier 1, over all cells for Tier 2 — with
      within-row ties resolving to the first in `strategy_complexity_order`. A Tier 1 model's
      thin cells never enter its ordering key.
- [x] Task 2.4 — Draw the break between the tiers: a gap plus a rule line, Tier 2 row labels
      styled distinctly from Tier 1, and the Tier 2 block annotated as unranked with the reason
      (*every cell below the requested cap*). It must not rely on colour alone, and must be
      visually distinct from both the per-cell thin marking and the marginal dividers — a
      reader should not have to work out which of the three separators they are looking at.
- [x] Task 2.5 — Annotate each cell with its value (`× 100`, one decimal) and its `n`, using
      the shared text-contrast rule so both stay legible across the ramp.
- [x] Task 2.6 — Mark every thin cell (`n < requested_n[slug]`). Choose an encoding that does
      not touch cell hue (the ramp already means score) and survives greyscale — e.g. a hatch
      or a corner glyph — and record the choice in a comment. Add a legend entry naming it.
- [x] Task 2.7 — Colour model tick labels by `metadata.model_hosting` using the shared
      `HOST_COLORS` / `HOST_LABELS`, with the same legend treatment as
      `plot_model_fidelity_table` (`manuscript_tables.py:274`).
- [x] Task 2.8 — Add the two marginals, separated from the grid by the shared divider so
      neither can be read as a cell. They are **deliberately asymmetric**, and the asymmetry
      must not be "fixed" into two means — see Technical Design point 4. The row marginal
      prints the ordering key: best qualifying score, argmax method, and the count of cells the
      key rested on, flagged provisional for Tier 2 rows. The column marginal is the per-method
      mean across models over **full-`n` cells only**, printed with the count it averaged, so a
      method's mean is never moved by a 7-persona cell and an excluded cell is visible rather
      than silent. State both scopes in the caption.
- [x] Task 2.9 — Persist via `analysis/utils/figures.py::save_figure` so the PNG and its `.svg`
      sibling are both written. Note that every existing function in `charts.py` calls
      `fig.savefig` directly and emits PNG only (:111, :168, :247, :310) — the new function must
      not follow that local precedent.
- [x] Task 2.10 — Name the output `{country}_model_method_heatmap.{png,svg}` and give it a title
      and subtitle that distinguish it from the two figures it sits beside: `{country}_heatmap.png`
      (combos × attributes, `charts.py:52`) and `{country}_models_table.png` (models × attributes
      at one strategy). Conform to `uniform-analysis-output-naming.md`.
- [x] Task 2.11 — Wire into `rank_models.py` behind the existing `--no-charts` flag (:117); add
      the new pair to the docstring output list (:13-26). While editing that list, also add the
      already-written-but-undocumented `{country}_c2st_vs_tv.png` (written at :295-299) —
      pre-existing drift, fixed in passing.

**Phase 2 implementation notes (five deviations from the task text, each forced by a
constraint the task text and the code together left in tension):**

1. **`plot_model_method_heatmap` returns `Path | None` (the PNG), not `(png, svg)`.** The
   module-contract table says "→ `(png, svg)` paths", but `save_figure` owns the
   dual-format policy — *which* formats and how the sibling's name is derived — and
   returns the PNG for exactly that reason. Returning the pair would have meant computing
   `png.with_suffix(".svg")` in `charts.py`, i.e. restating in the caller the naming rule
   the helper exists to hold. The two manuscript tables, which route through the same
   helper, already return `Path`. The SVG is still written and is asserted by a test.
2. **`table_style` gains `horizontal_divider(ax, n_rows_above)`**, the row-wise twin of
   `vertical_divider`. The column marginal sits *below* the grid, so fencing it off needed
   a horizontal rule; the only alternative was writing the divider's colour and width into
   `charts.py`, which the "no re-specified colour values" rule forbids. Both orientations
   now read one `_DIVIDER_COLOR` / `_DIVIDER_LINEWIDTH` pair, so they cannot drift, and
   `n_columns_left` / `n_rows_above` are typed `float` because a grid with a tier gap has
   its bottom edge at a fractional row coordinate.
3. **`requested_n` is a `CapIndex`, a read-only `Mapping[str, int]`, not a bare dict.** The
   fail-fast requirement is that a slug with no entry raises *with the offending path
   named*, and a bare dict cannot name the file it came from. `CapIndex` is the map the
   contract asks for plus the path it was read from; the chart's parameter keeps the name
   `requested_n` and reads as one (`requested_n[slug]`, `requested_n.is_full_n(...)`).
4. **The thin marking is a hatch *plus* an annotation backing patch.** The hatch alone
   (Task 2.6's suggestion) is drawn in the cell's own contrast colour, which is the same
   colour as the annotation on that cell — on the dark end of the ramp the white hatch and
   the white number merged into an unreadable cell, which defeats both the marking and the
   `n` it exists to qualify. Each thin cell's annotation therefore sits on a patch of the
   cell's own ramp colour, punched through the hatch. Hue is still untouched, and the
   hatch stroke is thinned via a scoped `rc_context` at draw time (the width is an rcParam,
   not a patch property, so it cannot be set on the artist).
5. **The row marginal is drawn *inside* the axes, with its width reserved in column
   units.** Hanging it outside and relying on `bbox_inches="tight"` put it underneath the
   colourbar, which `fig.colorbar` lays out in exactly that space. The reserved width is
   derived from the longest marginal string and the figure widens to match, so the text
   never collides with the colourbar regardless of how long the method ids are.

**Files Modified:**
- `src/population_synthetic/analysis/utils/cap_index.py` — new; shared cap-index read + full-`n`/thin predicate
- `src/population_synthetic/analysis/model_ranking/table_style.py` — `horizontal_divider` added (note 2)
- `src/population_synthetic/analysis/model_ranking/charts.py` — new plot function
- `scripts/analyze/rank_models.py` — call site + docstring output list
- `tests/test_cap_index.py` — new (20 tests)
- `tests/test_model_ranking_charts.py` — new (38 tests, including the two CLI integration tests)

**Dependencies:** Phase 1

---

## Testing Plan

### Unit Tests
- [x] `table_style` helpers return the same colours and contrast decisions as the
      pre-extraction private functions (characterisation, structural not byte-wise).
- [x] `categories_on_top` with an explicit label list places exactly those labels, and the
      table call sites still render `attributes + ["overall"]`.
- [x] Heatmap cell values equal `combos[slug]["overall"]["tv_similarity_mean"] × 100` to one
      decimal, for every `(model, strategy)` in a fixture.
- [x] Column order equals `strategy_complexity_order(metadata["strategies"])` **and** equals
      `result["methods_matrix"]["strategies"]` — pinning the equivalence without coupling.
- [x] The tier predicate is exact at the boundary: `n == requested_n` is full-`n` (not thin),
      `n == requested_n - 1` is thin. Asserted against a `requested_n` supplied by the fixture,
      never a literal. The fixture's `requested_n` must be a value other than 100 (e.g. 40), so
      a hardcoded threshold fails the test rather than passing by coincidence. (The unrelated
      `× 100` metric rescaling is of course still present in the value assertions.)
- [x] Tier assignment: a model with at least one full-`n` cell lands in Tier 1, a model with
      zero lands in Tier 2, on a fixture containing both.
- [x] A Tier 1 model's ordering key ignores its thin cells — a fixture in which a model's
      single best cell is thin ranks that model on its best **full-`n`** cell, and the thin
      cell is still drawn and still marked.
- [x] A model with exactly **one** full-`n` cell is ranked in Tier 1 on that single cell, and
      its row marginal reports a count of 1.
- [x] Tier 1 rows all precede Tier 2 rows in the rendered order, regardless of the values.
- [x] Tier 1 tie-break chain on a constructed fixture: identical `max_over_full_n` orders by
      descending `mean_over_full_n`; identical on both orders by ascending model id. Tier 2
      tie-break: identical `max_over_all_cells` orders by ascending model id. Both are total
      and stable across repeated calls on the same input.
- [x] The row marginal prints the ordering key, the argmax method and the cell count, not a
      mean; a Tier 2 row's marginal is flagged provisional. A within-row tie on the maximum
      resolves the argmax method to the first in `strategy_complexity_order`.
- [x] The column marginal averages full-`n` cells only and prints the count averaged: a fixture
      column containing one thin cell yields a mean over the remaining cells and a count one
      lower than the row count.
- [x] Thin marking fires iff `n < requested_n`, including both boundary cases above.
- [x] `cap_index` raises with the path in the message when `_index.json` is absent, and raises
      when a requested slug has no entry.
- [x] `save_figure` is used: both the `.png` and the `.svg` exist after a call.
- [x] Model tick label colours match `metadata.model_hosting` via the shared host colours; a
      model absent from the map falls back to the same presentation default the tables use
      (`manuscript_tables.py:28-31`).

### Integration Tests
- [x] `rank_models.py` on a fixture emits the new pair alongside the existing artifacts and
      leaves the existing ones unchanged (same file set plus two).
- [x] `--no-charts` suppresses the pair while the JSON and CSV are still written.

### Manual Verification
- [ ] Run `python scripts/analyze/rank_models.py --country swedish_02`; open the PNG and the
      SVG and confirm no label collisions, no clipping, and legible cell text at slide size.
- [ ] Confirm the marking fires on exactly these seven cells and none of the other 43:
      `all_generate_evaluate_random_pick_v2` × `ollama_gemma4_e4b` (n=7),
      × `ollama_deepseek_r1_14b` (n=9), × `ollama_llama31_8b` (n=11);
      `all_pick_dag_v2` × `ollama_llama31_8b` (n=19);
      `all_pick_v2` × `ollama_llama31_8b` (n=22);
      `all_generate_pick_v2` × `ollama_llama31_8b` (n=34);
      `all_generate_evaluate_pick_v2` × `ollama_llama31_8b` (n=49).
- [ ] Confirm the grid is 10 models × 5 methods with no empty cells on the current dataset.
- [ ] Confirm the tiering: Tier 2 holds exactly `ollama_llama31_8b` (all five cells thin —
      n = 11, 19, 22, 34, 49), sitting below the break and annotated unranked;
      `ollama_gemma4_e4b` and `ollama_deepseek_r1_14b` are in Tier 1, ranked on their four
      full-`n` cells, each showing one marked thin cell in the
      `all_generate_evaluate_random_pick_v2` column (n = 7 and n = 9); the other seven models
      show five full-`n` cells each and a row-marginal count of 5.
- [ ] Confirm the break, the thin-cell marking and the marginal dividers are three visually
      distinct devices, and that a reader can tell them apart without the legend.
- [ ] Confirm the figure reproduces the hand-made deck prototype's values.
- [ ] Print one copy in greyscale and confirm the thin marking and the tier break are both
      still distinguishable.

### Edge Cases
- [x] A missing `(model, method)` cell renders as the ramp's `set_bad` grey, never as 0 — must
      be covered by a synthetic fixture, since the current 50-combo dataset has no gaps.
- [x] Boundary `n == requested_n` is unmarked.
- [x] A slug present in the grid but absent from `population_cap/_index.json` raises.
- [x] A country whose `population_cap/_index.json` does not exist raises with the path named,
      rather than drawing an unmarked figure.
- [x] A grid in which *every* model is Tier 2 (no full-`n` cell anywhere) still renders: every
      cell marked, the whole grid annotated provisional, and no empty Tier 1 block drawn. This
      is also the case that would silently break a `max(n)`-inferred cap.
- [x] A grid with *no* Tier 2 model — the expected shape of a healthy run — draws no break line
      and no unranked annotation, rather than an empty block or a stray rule.
- [x] A Tier 1 model whose full-`n` cells are all NaN has no defined ordering key: it sorts last
      *within its tier* by an explicit rule rather than raising or comparing against NaN, and
      its row marginal prints no argmax method. It stays in Tier 1 — it has full-`n` cells; the
      values are missing, which is a different failure from thin evidence.
- [x] A column whose cells are all NaN contributes no best-cell marker
      (`_best_cells_per_column`, `manuscript_tables.py:79-80`) and does not crash the marginals.
- [x] A single-model or single-method grid renders without a degenerate axis.
- [x] A model whose cells are *all* NaN across both tiers' key definitions sorts last by that
      same explicit rule, and never silently compares against NaN.

---

## Documentation Plan

Deliberately small — this adds a figure to an existing process, not a process.

- [x] Update the `scripts/analyze/rank_models.py` docstring output list (:13-26) with
      `{country}_model_method_heatmap.png` (PNG + SVG), plus the missing
      `{country}_c2st_vs_tv.png` noted in Task 2.11.
- [x] No `docs/architecture/commands.md` change: the command surface is unchanged — no new
      script, no new flag. Stated here so a reviewer does not expect an edit.
- [x] No `CLAUDE.md` architecture change, no `config/analysis/analysis_registry.yaml` entry,
      and no `config/gui/flows/analysis_workflow.yaml` task: this plan adds no process and no
      DAG node.
- [x] Inline comment recording the thin-marking encoding chosen in Task 2.6 and why it does not
      use cell hue, and a module docstring in `analysis/utils/cap_index.py` stating the
      full-`n`/thin rule once, as the definition its three consumers share.

---

## Rollback Plan

1. **Phase 2 (new figure):** remove the call from `rank_models.py`, delete
   `plot_model_method_heatmap`, and delete `tests/test_model_ranking_charts.py`. Existing
   artifacts are untouched; the only on-disk residue is the two new files in the
   `model_ranking` output folder, which can be deleted. `analysis/utils/cap_index.py` is
   additive and has no other caller at that point, so it can be kept or deleted independently —
   keep it if the parent plan's figures are still queued, since they need the same rule.
2. **Phase 1 (extraction):** revert the commit; `manuscript_tables.py` returns to its private
   helpers. The Phase 1 tests establish equivalence in both directions, so the revert is
   verifiable rather than assumed.
3. **Data:** no migration and no destructive write. The plan reads `population_cap/_index.json`
   and writes only into `03_Analysis/model_ranking/`. Nothing upstream is re-run, and no gate
   artifact is modified — in particular, no `population_cap` re-run is required at any point.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Style extraction silently changes the two shipped manuscript tables | Med | High | Phase 1 extends the existing 15-test suite with equivalence assertions before any new figure is built; Phase 2 cannot start until they pass |
| `categories_on_top` extracted verbatim gives the new figure a spurious "overall" column | Med | Med | Task 1.2 generalises the signature explicitly; a test asserts the tables still render `attributes + ["overall"]` |
| Reader confuses the new figure with `{country}_heatmap.png` or `models_table` | Med | Med | Distinct filename, and a title/subtitle stating the distinction: the tables are per-attribute (one strategy, or models averaged), this is overall across both factors |
| The cap-index read makes `model_ranking` newly dependent on `population_cap` having run | Med | Med | `model_ranking` already reads `population_cap/_mapped/` via `resolve_mapped_dir` (`loader.py:179-182`), so the dependency exists in practice; the new read is the same directory and fails loudly with the path named |
| Thin marking is invisible at slide size or in greyscale | Med | High | Encoding must not use cell hue; greyscale print check in Manual Verification |
| Tier 2 reads as "these are bad models" when it means "there is not enough evidence to rank them" | High (it is the natural misreading of a block at the bottom) | High | The block is annotated with the reason — *every cell below the requested cap* — not merely labelled "unranked"; each thin cell still prints its `n`, so the reader sees the evidence base directly; the caption states that Tier 2 carries no claim about quality |
| A reader compares a Tier 1 rank built on five full-`n` cells against one built on a single full-`n` cell | Med | Med | The row marginal prints the count of cells the ordering key was computed over, so the strength of each rank is on the figure rather than inferred |
| The break, the thin marking and the marginal dividers read as three variants of the same device | Med | Med | Each uses a different visual channel; Manual Verification includes a legend-free discrimination check |
| Marginals read as ordinary cells and get compared to them | Low | Med | Separated by the shared divider; caption states each marginal's scope (row = ordering key, column = full-`n` mean with its count) |
| Asymmetric marginals (row = ordering key + argmax method + count, column = full-`n` mean + count) read as an inconsistency | Med | Low | The asymmetry is stated in the Definitions and justified in Technical Design point 4: the row marginal must show the ordering key, the column marginal answers a different question |
| The shared `cap_index` module is written for this figure and then diverges from what the parent plan's two figures need | Med | Med | Its contract is fixed here (read + per-slug lookup + predicate, nothing figure-specific) and recorded in the module table; the parent plan's figures import it rather than re-deriving the rule |
| `charts.py` grows past comfortable size (314 lines today) | Low | Low | Accepted; if it becomes a problem the split is by figure, and `table_style.py` already removes the shared bulk |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — extract the shared table style | 0.5 day | None |
| Phase 2 — model × method heatmap | 1 day | Phase 1 |

---

## References

- Parent plan: `docs/development/plans/pending/pipeline-model-method-cost-and-attrition-figures.md`.
  This plan **supersedes its Phases 1–2**; the parent retains Phases 3–5 (`raw_total`,
  `validation_attrition`, `cost_efficiency`). The parent's coupling of this figure to `raw_total`
  is void: `requested_n` is already on disk in `population_cap/_index.json`, so no gate re-run
  is needed and the two plans can proceed independently and in either order. **Shared
  dependency:** this plan introduces `analysis/utils/cap_index.py`, and the parent's
  `cost_efficiency` and `validation_attrition` figures must **import** it for their
  `requested_n` lookup and their full-`n`/thin test rather than re-deriving either. Whichever
  plan is implemented first creates the module; the other consumes it unchanged.
- Hand-made prototype (external, outside git):
  `40_llm-population-fidelity-benchmark/figures/swedish_02_model_method_tv_heatmap.py`
- Output naming: `docs/development/plans/pending/uniform-analysis-output-naming.md`
- Siblings the figure must match: `plot_model_fidelity_table` (`manuscript_tables.py:274`),
  `plot_method_fidelity_table` (:346)
- Grid source and its limits: `build_performance_comparison` (`builder.py:135`),
  `_methods_matrix` (`builder.py:52-92`)
- Cap record: `CapSummary` (`population_cap/cap.py:51-66`), written by
  `scripts/analyze/cap_populations.py:196`; resolver `analysis/utils/capped_source.py:66-86`
- Engineering guides: `docs/data-pipeline-engineering/` (`02` design checklist, `03`
  statistical software, `05` craftsmanship)

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- docs/architecture/sub-packages.md
- docs/development/plans/active/model-method-tv-heatmap.md
- scripts/analyze/rank_models.py
- src/population_synthetic/analysis/model_ranking/charts.py
- src/population_synthetic/analysis/model_ranking/manuscript_tables.py
- src/population_synthetic/analysis/model_ranking/table_style.py
- src/population_synthetic/analysis/utils/cap_index.py
- tests/test_cap_index.py
- tests/test_manuscript_tables.py
- tests/test_model_ranking_charts.py
