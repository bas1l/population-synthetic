# Plan: Typicality distribution grid and typicality effect sizes

**Date:** 2026-09-21
**Author:** Basil
**Status:** In Progress
**Base Branch:** `dev`
**Branch:** `feature/typicality-distribution-grid`

> **Coordination.** Phase 1 creates `analysis/utils/model_order.py` to the **same contract** that
> Phase 1 of the pending plan `transposed-reference-centred-grids.md` proposes (the lift of
> `_ModelRow` / `_model_method_rows` / `_tier1_sort_key` / `_tier2_sort_key` out of
> `model_ranking/charts.py:512-639`, plus `ranked_model_order` and `align_to_ranking`).
> Whichever plan is implemented first owns that phase; the other marks its Phase 1 as already
> done and reuses the module unchanged. Both plans edit `scripts/analyze/rank_persona_realism.py`,
> so expect a textual merge in its chart loop.
>
> **Reference folder.** `docs/development/plans/pending/typicality-distribution-grid/` holds
> verbatim copies of the prototype (the originals were in a session scratchpad that is deleted):
> `compact/p17.py` (function `P20` is the approved figure), `compact/common.py`, `compact/protos.py`
> (helpers `P20` imports: `bare`, `withdrawn_cell`, `score_colorbar`, `WD_HANDLE`),
> `compact/proposals.md`, the approved image `compact/P20_square_grid_top_labels.png`,
> `effects.py`, `figs_columns.py`, `figs_by_method.py`, `results.md`, `meta.json`,
> `severity_link/` (out of scope, kept for context), and `golden/` (the prototype's output CSVs,
> used as reproduction fixtures in the Testing Plan). The scripts are reference material, not
> runnable in place: they read their CSVs from the parent directory and the live data base.
> There was no `kw.py` in the scratchpad; the Kruskal-Wallis work lives in `effects.py`.

---

## Overview

Add one publication figure and four effect-size tables to the `realism_ranking` process. The figure
is a grid of small histograms of the judge's typicality score (0–10): strategies A–E are the rows,
the 12 models are the columns in `model_ranking` order, and the real population's histogram is drawn
as an outline in every cell. A detached reference column and one ternary triangle per strategy row
(the share of individuals scoring 0–4, 5–7 and 8–10) sit to the right. The tables report the
effect sizes the existing tests currently publish without: ε² for the two Kruskal-Wallis factors,
Cliff's δ with a bootstrap interval for every model pair, and each combination and each pooled model
against the real population (Cliff's δ + interval, Mann-Whitney, Holm).

## Problem Statement

`realism_ranking` publishes the typicality axis only as one scalar per combination (the IOV
dispersion statistic in `typicality_heatmap`), plus Kruskal-Wallis and Dunn/Holm p-values in
`factor_significance`. Three things are missing:

1. **The distributions are not visible.** The scalar says how spread a combination's scores are,
   but not where they sit. The prototype showed the main finding directly: every one of the 58
   combinations sits above the real population (Cliff's δ from +0.296 to +0.912, 58/58
   Holm-significant, `results.md` §3), and strategy E is the only one whose shape resembles the
   reference. No existing figure shows this.
2. **The tests have no effect sizes.** `factor_significance.by_model` carries H and p for the
   factor and z and Holm p for the 66 Dunn pairs, but nothing that says how large a difference is.
   In the prototype 45 of 66 model pairs were Holm-significant, and 7 of those had negligible
   |δ| < 0.147. The house rule (guide 03 §3; builder docstring "every p-value is accompanied by an
   effect size") is currently broken for this block.
3. **There is no location contrast against the real population.** `scb_contrast` compares
   impossibility rates (Axis A) and the dispersion distance (Axis B). Neither says whether a
   combination's scores are *higher* than the reference, which is the finding above.

The approved prototype computed all of this in scratch code that bypasses the pipeline: it imported
private `model_ranking.charts` helpers, used first-round scores only, hardcoded `"SCB (real)"` and
the `real_swedish_02` slug, and authored the words "personas" and "Methods", which the manuscript's
terminology rules forbid in published artwork.

## Goals

### In Scope
1. A `typicality_distribution` block in `realism_ranking.json`: one round-weighted score
   distribution per competitor (defined below), the three band shares, the grid shape with
   withdrawn and unjudged cells kept distinct, and its two CSV grains.
2. A `typicality_effects` block: ε² for the model and strategy factors; Cliff's δ with bootstrap
   95% CI for every model pair, joined to the existing Dunn z and Holm p; every combination and
   every pooled model against the real population (n, median, Cliff's δ + CI, Mann-Whitney U,
   raw and Holm p). Three CSVs.
3. The figure `typicality_distribution_by_model_strategy.{png,svg,eps}`, reproducing the approved
   P20 layout on a fixed 456 pt canvas.
4. A shared, public model order in `analysis/utils/model_order.py` (coordinated as above).
5. A config-held vocabulary for manuscript-controlled words in artwork ("individuals",
   "Strategies") and a config-held short name for each country's reference source ("SCB").
6. One new presentation-layer module, `analysis/utils/glyph_grid.py`, which draws the grid cells,
   the triangles and the stepped colourbar and computes nothing.

### Out of Scope
- **Renaming "Methods:" to "Strategies:" in the method keys of existing figures** (nine call sites
  in `fidelity`, `generation_metadata`, `method_significance` and `model_ranking` charts). The new
  vocabulary makes it a one-line change per site; whether to do it is an open question for the
  user (see the end of this plan).
- **Adding the figure to `config/analysis/figure_selection.yaml`.** That roster is curated by hand
  and carries the manuscript number `n`. The stem is chosen so an entry can be added later without
  restaging (see decision 5), but the entry itself is the user's.
- Pairwise Cliff's δ for strategy pairs. The same code covers it with one extra call, but it was
  not requested. The omnibus ε² for the strategy factor is in scope.
- The severity-to-typicality link analysis in `severity_link/`. It is kept only as context.
- Moving `model_ranking/hosting.py` into `analysis/utils/`. The driver imports it, as
  `analyze_validation_attrition.py` already does.
- A caveat about the judge sharing a model family with a generator (the judge is
  `claude-sonnet-5`; `claude_sonnet` is a generator). This is recorded as a risk and in the docs,
  not computed.
- Changing the existing `typicality_histogram.csv` or `typicality_summary.csv`. Their basis
  (per-persona mean rounded half-to-even) stays as it is.

## Success Criteria

- [ ] `rank_persona_realism.py` writes `typicality_distribution_by_model_strategy.png/.svg/.eps`
      per country, through `figures.save_figure(..., fixed_canvas=True)`.
- [ ] **Every written SVG is 456 pt wide**: the root `<svg>` `width` attribute is `456pt` (checked
      by a test on the written file, not on the figure object).
- [ ] **The figure reproduces the approved P20 layout**: the geometry constants in the Definitions
      are met exactly (a test asserts every cell's axes box in points), and a side-by-side review
      against `compact/P20_square_grid_top_labels.png` shows no difference except the listed
      intentional ones (key separator, "Strategies", "individuals").
- [ ] Run with `--rounds 1` on the 2026-09-21 swedish_02 data, every competitor's distribution
      equals the prototype's `golden/distribution_first_round_by_combo.csv` /
      `distribution_first_round_by_model.csv` row to within 1e-12, and the two withdrawn cells
      (DeepSeek-R1 14B × E, Gemma4 E4B × E) are crossed out.
- [ ] Run with the published rounds (`n_rounds_source: report`), ε² is 0.0980 (model) and 0.1668
      (strategy) to 4 d.p.; 45/66 model pairs are Holm-significant; 58/58 combinations vs the
      reference have δ > 0 and p_Holm < 0.05; every point δ matches `golden/combo_vs_scb.csv` and
      `golden/pairwise_models_cliffs_delta.csv` to 1e-9. With `--rounds 1`: 0.0984 / 0.1608.
- [ ] No string on the canvas is a literal for a manuscript-controlled word, a model name or the
      reference name. Each comes from `labels.py` over config, and a missing entry raises.
- [ ] `glyph_grid.py` passes the presentation-layer membership test: it imports nothing from an
      analysis subpackage, and a grep finds no `alpha=`, `savefig` or `imshow` in it.
- [ ] `realism_ranking.json`, every new CSV and the PNG are byte-identical across two runs and
      across a shuffled competitor order.
- [ ] `pytest` passes and `ruff check src/` is clean.

## Definitions

- **Survivor**: a persona with `can_exist_majority == True` and a non-null `typicality_mean`. This
  is exactly the set behind `CompetitorRecord.typicality_means`, and it is the denominator of every
  number below. It is never `n_personas`.
- **Scored rounds of a survivor**: the non-`None` entries of its `typicality_rounds` (a round judged
  impossible carries no score). There are r_i ≥ 1 of them. Under `--rounds N` they are the scored
  rounds among the first N, because the capped loader rebuilds the rows from the trimmed cache.
- **Round-weighted distribution** of a competitor: w(k) = Σ_i (1/r_i)·#{j : t_ij = k} for
  k = 0..10, summed over survivors i. Then Σ_k w(k) = number of survivors, and the published
  distribution is p(k) = w(k) / number of survivors. Each survivor counts exactly once. Two
  checkable identities: Σ_k k·p(k) equals the mean of `typicality_means` exactly, and when every
  r_i = 1, w is the integer histogram of the single scored round.
- **Band shares**: low = Σ_{k≤b1} p(k), mid = Σ_{b1<k≤b2} p(k), high = Σ_{k>b2} p(k), with
  (b1, b2) = `--typicality-bands` (default `4,7`, giving 0–4 / 5–7 / 8–10). The three sum to 1.
- **Reference**: the competitor with `is_real_reference == True` (`real_{country}`). It is
  published in the block like any competitor and held out of every factor test.
- **Withdrawn cell**: a (model, strategy) pair of the grid whose slug is `excluded: true` in
  `population_cap/_index.json`. It has no individuals by construction and is drawn crossed out,
  never dropped.
- **Unjudged cell**: a (model, strategy) pair of the grid that is neither consumed nor withdrawn
  (for example, `persona_realism` has not run on it yet). It is drawn as a grey empty cell, which
  is the "not judged" state every other grid in this process uses.
- **No-typicality cell**: a consumed competitor with zero survivors (status `no_typicality` in the
  existing block). It is drawn as an empty frame with a centred en dash.
- **P20 geometry** (points, origin at the bottom left): canvas 456 × 280.5. Cells 26.5 × 26.5,
  column gap 1.5, row gap 3.0. Grid left edge 20. Detached reference column 6 to the right of the
  last model column, triangle column 5 after that, colourbar (7 wide) 6 after that. Bottom block
  60 (legend, triangle note, strategy key). Top block 76 (vertical model labels, baseline 2 above
  the top row). Triangle side = (26.5 − 2·1.5)/(√3/2). With 12 models and 5 strategies this gives
  a grid of 334.5 × 144.5.
- **Manuscript-controlled word**: a word governed by the manuscript's `TERMINOLOGY-RULES.md` T1
  (individual, not persona; strategy, not method). The rule covers published artwork. It does
  **not** cover code identifiers, CSV columns or JSON keys, which keep the repository's dialect
  (`persona`, `strategy`, `method`).

---

## Technical Design

### Approach

The work follows the process's existing split. `builder.py` computes every number as pure
functions over `CompetitorRecord`s. The CLI edge resolves config, the cap index and the model order.
`charts.py` turns the finished block into drawing calls, and a new presentation module draws them.
Nothing new reads a file below the CLI.

**Decision 1: histogram basis.** The distribution is **round-weighted** (Definitions): each
survivor spreads a total weight of 1 evenly over its scored rounds.

- *Why not first round only (the prototype)?* It throws away rounds that were paid for, and it is
  only defined when the first round was scored. With 3 rounds, a survivor can have an impossible
  first round.
- *Why not the existing rounding rule (mean rounded half to even, as `typicality_histogram.csv`
  does)?* Rounding moves mass. A persona scoring 8 and 9 lands entirely on 8, and one scoring 9 and
  10 lands on 10, so the published distribution's mean no longer equals the mean of the per-persona
  means that the factor tests use. The round-weighted distribution keeps that identity exactly, and
  no rounding rule has to be defended.
- *How does it reduce to the prototype?* When every r_i = 1, the weights are integers and the
  distribution is the integer histogram of each survivor's one scored round. `--rounds 1` produces
  exactly that. `results.md` records that on the live data the survivor set is unchanged under a
  1-round cap, which is why the `--rounds 1` success criterion must match the golden CSVs exactly.
- *Band shares* are computed from the same p(k), so the triangle and the histogram cannot disagree.
- *Inference stays on the per-persona means* (`typicality_means`, the unit the Kruskal-Wallis and
  Dunn tests already use). A round is not an independent unit; a persona is. The figure is
  descriptive and the tables are inferential, and the two bases coincide at one round per persona.
  The block states both bases as data (`basis`, `counting_unit`).

**Decision 2: model order.** The figure orders columns by `model_ranking`'s published order
(tier 1, then tier 2, each by its sort key). This is computed by `utils/model_order.ranked_model_order`
from `{country}_performance.json` plus `load_cap_index`, not copied from a list. Consequences:

- **Only the figure depends on `model_ranking`.** The JSON block and the CSVs keep the process's
  existing total order (`_competitor_position`: strategy complexity first, then model; model factor
  alphabetical). That keeps `realism_ranking.json` reproducible from `persona_realism` outputs
  alone, as its registry description promises.
- **A missing `model_ranking` output fails fast, before anything is written.** When charts are on,
  the CLI resolves the order at the edge, before the JSON is written. If
  `03_Analysis/model_ranking/{country}_performance.json` is missing, it raises
  `FileNotFoundError` naming `scripts/analyze/rank_models.py`. `--no-charts` skips the read. This is
  preferred over a per-chart skip because the chart loop only catches `ValueError`, and a figure
  that silently falls back to alphabetical order would publish a different column order than the
  sibling figures.
- **Column set.** The columns are the realism grid's models, in ranked order. A grid model that the
  ranking does not know raises; there is no appended "unranked" group, because the fixed 456 pt
  canvas has no room for a labelled break. A ranked model with no realism competitor at all is
  not a column. It has nothing to draw, and it is not a withdrawn cell, because withdrawal is
  per-combination and read from the cap index.
- **DAG edge.** In `config/gui/flows/analysis_workflow.yaml`, `realism_ranking.depends_on` becomes
  `[persona_realism, model_ranking]`. `model_ranking` is enabled and depends on `fidelity`, which
  depends on `population_cap`, so no cycle is formed and nothing new is parked at `SKIPPED_DEP`. In
  a sweep, `realism_ranking` now also waits for `fidelity` and `model_ranking`. An operator who
  disables `model_ranking` parks `realism_ranking`; the remedy is the node's `bypass` flag, as for
  `cost_efficiency`. The edge is only in the workflow YAML: `analysis_registry.yaml` holds no
  edges, only the description, which is updated.

**Decision 3: where the drawing lives.**

| Piece | Home | Why |
|---|---|---|
| Round-weighted distribution, band shares, withdrawn/unjudged/no-typicality states, ε², δ, CIs, U, p | `realism_ranking/builder.py` + `utils/stats_tests.py` | statistics; the presentation layer may compute none |
| Barycentric position of a share triple, √ bar-height scale | `utils/glyph_grid.py` | coordinate transforms of finished numbers, like a log axis; neither changes a value |
| Label resolution, cell-state → draw-call mapping, legend and note text assembly | `realism_ranking/charts.py` | composes the figure from the block; computes nothing |
| Point-based canvas, mini-histogram, crossed and empty cells, ternary, stepped colourbar | `utils/glyph_grid.py` (new) | reusable drawing, no data semantics |

The new module does not replace `grids.py`: there is no `imshow` here, because each cell is its own
small axes. The presentation layer grows from seven modules to eight. `model_order.py` is **not** a
presentation module: it computes a ranking, so it sits beside `cap_index.py`.

**Decision 4: labels and terms from config.**
- Model names: `labels.model_labels` (existing).
- Strategy letters and key: `labels.method_letters` / `labels.method_key_lines`, rendered verbatim
  (`A — All Pick`). This deliberately differs from P20, which stripped the em dash; every other
  figure's key keeps it.
- Reference short name: a new `display.reference_source` field in each country axis YAML
  (`swedish_02.yaml` → `"SCB"`), read by a new `labels.reference_source(country_id)` that raises
  when the field is absent. Italy's file gets `"ISTAT"`. The column label comes from a new
  `labels.reference_column_label(country_id)`, which formats the `reference_column` template in the
  new `config/analysis/figure_terms.yaml` (`"{source} (real)"` → `"SCB (real)"`). The template must
  contain exactly one `{source}` placeholder, or loading raises. Legend entries use
  `reference_source` ("SCB outline", "SCB").
- Manuscript-controlled words: `config/analysis/figure_terms.yaml` holds `individuals: "individuals"`
  and `strategy_key_title: "Strategies"`. They are read by `labels.figure_term(key)`, which raises
  on an unknown key, a missing file or an empty value. The triangle note is assembled in
  `charts.py` from `figure_term("individuals")` and the band edges in the block:
  "Triangles: share of individuals in score bands 0–4 / 5–7 / 8–10 (corners); bar heights √-scaled".
- Hosting tints: the CLI calls `model_ranking.hosting.classify_hosting(discover_axis_values("models"),
  load_hosting_config(.../provider_hosting.json))` and passes the resulting `{model: class}` dict
  into the chart. `charts.py` never imports `model_ranking`. Colours come from `palette.HOST_COLORS`
  and legend words from `table_style.HOST_LABELS`. It does not read `metadata.model_hosting` out of
  `performance.json`, which fills gaps with `"hosted"` (see the centred-heatmap skill).

**Decision 5: naming, blocks and versions.**
- The figure stem is `typicality_distribution_by_model_strategy`. It matches the file already
  staged in the manuscript's `figures selection/` folder, so a later `figure_selection.yaml` entry
  needs no restaging. It uses "strategy", while its sibling `typicality_by_method` uses "method".
  That inconsistency is accepted: it does not conflict with any mechanical rule, `as_generated/`
  needs only a unique basename (it is), and the manuscript's T1.2 rule already accepts mixed
  filenames rather than restaging.
- New JSON keys `typicality_distribution` and `typicality_effects` are added at the top level, beside
  `typicality`. This is additive: no existing key changes shape. `realism_ranking.json` has no
  schema version today, and none is introduced.
- New CSVs follow the process's current convention (`csv.DictWriter`, header = contract, no
  version column): `typicality_distribution.csv` (one row per competitor × level),
  `typicality_bands.csv` (one row per competitor), `typicality_effect_omnibus.csv`,
  `typicality_effect_model_pairs.csv`, `typicality_effect_vs_reference.csv`. No cross-process
  contract changes, so `realism_csv.SCHEMA_VERSION` (2) and the clash contract's version do not move.
- `figure_selection.yaml` is not touched (Out of Scope).

**Decision 6: statistics.**
- **ε²** = H / (N − 1). This is algebraically equal to H(N+1)/(N²−1) (Tomczak & Tomczak 2014), which
  the prototype used. It is computed from the H and N already in `factor_significance`, not from a
  second Kruskal run.
- **Cliff's δ(a, b)** = P(a > b) − P(a < b) via the existing `stats_tests.cliffs_delta`. For each
  model pair it is taken in the **same (a, b) orientation** as the Dunn row. `dunn_posthoc`'s
  z = mean_rank[a] − mean_rank[b], so the signs agree without flipping (a test asserts it).
- **Bootstrap CI for δ**: a new `stats_tests.bootstrap_cliffs_delta_ci(a, b, *, iterations,
  ci_level, seed)`. It is a percentile interval, resamples each group at its own size, and uses one
  local `default_rng(seed)`. Each replicate is computed through the Mann-Whitney identity
  δ = 2U/(n_a·n_b) − 1, with U from mid-ranks, which is O((n_a+n_b) log) instead of the O(n_a·n_b)
  sign matrix: 66 pairs × 2000 replicates of about 500 × 500 would otherwise be 3.3·10¹⁰ sign
  evaluations. The point value is `cliffs_delta`'s, and a test asserts the identity. The seed is
  the judge config's `bootstrap.seed`, used unchanged for every comparison, as `_typicality_cell`
  does, so each interval depends only on its own two samples and never on processing order. The
  prototype's multinomial-on-a-0.5-grid trick is not reused: it assumes at most two rounds.
- **Mann-Whitney**: a new `stats_tests.mann_whitney_test(a, b)` wraps
  `scipy.stats.mannwhitneyu(..., alternative="two-sided", method="asymptotic")` (ties are pervasive
  on a 0–10 scale, so the exact method does not apply). It returns `{U, p, n_a, n_b}`.
- **Holm families**: one family is all synthetic combinations vs the reference, and one is all
  pooled models vs the reference. The model pairs keep the Dunn family's existing Holm p. Every row
  names its family and `correction: holm`.
- **Degenerate cases** follow the builder's rule: a group with fewer than 2 values, or no
  reference, gives null numbers plus a `skipped_tests` entry with a reason. The existing `CAVEATS`
  (pseudo-replication, single run per combination) apply to these p-values too; the new block
  cross-references them rather than restating them.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| First-round histogram (prototype) | Exactly P20's numbers | Discards paid rounds; undefined when round 1 was impossible | Rejected; kept as the `--rounds 1` special case |
| Rounded per-persona mean (existing `typicality_histogram.csv` rule) | One histogram basis in the document | Moves mass; breaks the histogram-mean = mean-of-means identity | Rejected for this figure; existing CSV untouched |
| Round-weighted distribution | Uses every scored round; persona counts once; exact identities; reduces to the prototype | A second distribution basis beside the rounded one (both labelled as data) | **Chosen** |
| Wait for the transposed plan's `model_order.py` | No duplicated effort | Blocks this plan on a plan that is itself blocked on two decisions | Rejected |
| Private import from `model_ranking.charts` | Zero new code | Breaks the "shared helpers live in `analysis/utils`" convention | Rejected |
| Extract `model_order.py` here, to the transposed plan's contract | Unblocks both plans; one implementation | Coordination note needed | **Chosen** |
| Per-chart WARNING skip when `performance.json` is missing | Tables still written | A figure could silently fall back to another order; the loop only catches `ValueError` | Rejected; fail fast at the edge unless `--no-charts` |
| Draw everything inside `realism_ranking/charts.py` | One file | Point-canvas, crossed-cell and ternary drawing are reusable and belong behind the presentation boundary | Rejected |
| `glyph_grid.py` presentation module + composing `charts.py` function | Respects the boundary; testable in isolation | Layer grows to eight modules (docs count changes) | **Chosen** |
| Literal `"SCB (real)"`, `"individuals"`, `"Strategies:"` in the chart | Fast | Breaks config-as-single-source; Italy would read "SCB" | Rejected |
| Jitter overlapping ternary dots (rows A–C) | Separates dots | Moves data points; exact shares are in `typicality_bands.csv` | Rejected |
| New stem `typicality_distribution_by_model_method` (repo dialect) | Matches `typicality_by_method` | Differs from the staged manuscript file; would need restaging | Rejected |

### Architecture & Module Contracts

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `utils/model_order.py` (new; shared with the transposed plan) | Publish `model_ranking`'s tier order | `result` (performance JSON dict), `CapIndex` → `list[str]`; `align_to_ranking(present, ranked)` | matplotlib, labels, realism, file paths (the caller loads the JSON) |
| `utils/cap_index.py` (extended) | Also expose which slugs the gate withdrew | `_index.json` → `CapIndex.is_withdrawn(slug)`, `withdrawn_slugs()` | figures, which process asks |
| `utils/labels.py` (extended) | `reference_source(country)`, `reference_column_label(country)`, `figure_term(key)` | country YAML, `figure_terms.yaml` → display strings; raise on absence | renderers, statistics |
| `utils/stats_tests.py` (extended) | `mann_whitney_test`, `bootstrap_cliffs_delta_ci`, `epsilon_squared` | samples/H,N → dicts | realism, figures |
| `realism_ranking/loader.py` (extended) | `CompetitorRecord.typicality_round_scores`: per-survivor tuples of scored rounds, the same filter as `typicality_means` | persona rows → `tuple[tuple[int, ...], ...]` | bands, figures |
| `realism_ranking/builder.py` (extended) | `_typicality_distribution(...)`, `_typicality_effects(...)`, `typicality_distribution_rows`, `typicality_band_rows`, `typicality_effect_*_rows` | records, bands, `withdrawn`, bootstrap → blocks/rows | paths, config files, model order, colours, labels |
| `utils/glyph_grid.py` (new, presentation) | Draw a point-laid-out grid of mini histograms, crossed and empty cells, ternaries, a stepped colourbar | finished pmfs / share triples / colours / text → artists on a figure | any statistic, analysis subpackages, ids, config |
| `realism_ranking/charts.py` (extended) | `plot_typicality_distribution_grid(ranking, *, country, model_order, hosting)` | block + resolved order/hosting → `Figure` | disk, DPI, statistics, `model_ranking` |
| `scripts/analyze/rank_persona_realism.py` (extended) | Edge: `--typicality-bands`, cap index, withdrawn set, model order, hosting, fixed-canvas save | CLI + files → outputs | — |

```
src/population_synthetic/analysis/
  utils/model_order.py            (new)   ranked_model_order(result, requested_n) -> list[str]
                                          align_to_ranking(present, ranked) -> tuple[list[str], int]
  utils/glyph_grid.py             (new)   PointCanvas(width_pt, height_pt)
                                            .axes(x0, y0, x1, y1) / .text(x, y, s, **kw) / .figure
                                          draw_mini_histogram(ax, heights, colors, *, outline=None)
                                          draw_withdrawn_cell(ax) / draw_empty_cell(ax, *, fill, mark)
                                          draw_ternary(ax, points, reference, *, point_size, ...)
                                          stepped_colorbar(canvas, box, levels, n, title)
  realism_ranking/builder.py              + typicality_distribution / typicality_effects blocks
  realism_ranking/charts.py               + plot_typicality_distribution_grid
config/analysis/figure_terms.yaml (new)   individuals, strategy_key_title, reference_column
config/synthetic/axes/countries/*.yaml    + display.reference_source
```

The `typicality_distribution` block shape (keys are data contracts; values illustrative):

```yaml
typicality_distribution:
  basis: "round-weighted: each survivor spreads weight 1 evenly over its scored rounds"
  counting_unit: "<TYPICALITY_COUNTING_UNIT, reused>"
  n_levels: 11
  bands: {edges: [4, 7], labels: ["0–4", "5–7", "8–10"]}
  grid: {models: [...], methods: [...], cells: {model: {strategy: cell|null}}, real: cell|null}
  withdrawn: [slug, ...]          # from population_cap; disjoint from consumed slugs (else raise)
  unjudged: [slug, ...]           # grid pairs neither consumed nor withdrawn
  # cell: {slug, status: ok|no_typicality, denominator, n_personas, n_multi_round,
  #        weights[11], distribution[11], band_shares[3], mean}
```

---

## Implementation Plan

### Phase 1: Shared model order and withdrawn slugs
**Started:** 2026-09-21 14:05
**Completed:** 2026-09-21 15:00

**Goal:** A public, tested `model_ranking` order and a reader for the gate's withdrawals.

- [x] 1.1 — Create `analysis/utils/model_order.py` exactly as the transposed plan's Phase 1
      specifies: lift `_ModelRow`, `_row_summary`, `_model_method_rows`, `_tier1_sort_key` and
      `_tier2_sort_key` from `model_ranking/charts.py:512-639`; add `ranked_model_order` and
      `align_to_ranking`; `model_ranking/charts.py` imports them back (the call site at lines
      737-740 is unchanged in behaviour). Skip this task if the transposed plan landed first.
- [x] 1.2 — Extend `utils/cap_index.py`: read `excluded` (bool, required, raise on absence or a
      non-bool) beside `requested_n`; add `is_withdrawn(slug)` and `withdrawn_slugs()`.
- [x] 1.3 — Tests: `tests/test_model_order.py` (reusing the `test_model_ranking_charts.py`
      fixtures: the tier split, the sort keys, the raise on an unknown model, and byte-equality of
      `model_ranking` charts' order before and after the lift); extend `tests/test_cap_index.py`.

**Files Modified:** `src/population_synthetic/analysis/utils/model_order.py` (new),
`src/population_synthetic/analysis/model_ranking/charts.py`,
`src/population_synthetic/analysis/utils/cap_index.py`, `tests/test_model_order.py` (new),
`tests/test_cap_index.py`, `tests/test_model_ranking_charts.py` (its in-memory `CapIndex`
fixtures pass the now-required `withdrawn=()`, and its CLI fixture index carries `excluded`).

**Dependencies:** None.

### Phase 2: Config-held vocabulary
**Goal:** Every word the figure prints that the manuscript controls, and the reference name, resolve
from config and raise when absent.

- [ ] 2.1 — Add `config/analysis/figure_terms.yaml` (`individuals`, `strategy_key_title`,
      `reference_column: "{source} (real)"`), with a header comment citing the manuscript's
      TERMINOLOGY-RULES T1 as the reason these words live in config.
- [ ] 2.2 — Add `display: {reference_source: ...}` to `swedish_02.yaml` ("SCB"), `swedish.yaml`
      ("SCB") and `italian.yaml` ("ISTAT"). Verify nothing that loads country YAMLs rejects unknown
      keys (the manifest loader and the GUI axis readers); fix any that does, and say so in the
      commit.
- [ ] 2.3 — `labels.py`: `figure_term(key)`, `reference_source(country_id)`,
      `reference_column_label(country_id)`. No fallback to the id, following `model_label`'s
      pattern.
- [ ] 2.4 — Tests in `tests/test_labels.py`: resolution; the raise on a missing file, key, empty
      value or template without exactly one `{source}`; the raise when a country lacks
      `display.reference_source`.

**Files Modified:** `config/analysis/figure_terms.yaml` (new),
`config/synthetic/axes/countries/{swedish_02,swedish,italian}.yaml`,
`src/population_synthetic/analysis/utils/labels.py`, `tests/test_labels.py`.

**Dependencies:** None.

### Phase 3: Statistical primitives
**Goal:** The three missing primitives, each tested against known values.

- [ ] 3.1 — `stats_tests.epsilon_squared(H, n)` = H/(n−1); raises for n < 2 or H < 0.
- [ ] 3.2 — `stats_tests.mann_whitney_test(a, b)` (two-sided, asymptotic); an empty sample raises,
      as `cliffs_delta` does.
- [ ] 3.3 — `stats_tests.bootstrap_cliffs_delta_ci(a, b, *, iterations, ci_level, seed)`, via the
      U identity, returning the same key set as `bootstrap_difference_ci`
      (`point, lo, hi, ci_level, iterations, n_a, n_b, method`).
- [ ] 3.4 — Tests in `tests/test_stats_tests_significance.py` (see the Testing Plan).

**Files Modified:** `src/population_synthetic/analysis/utils/stats_tests.py`,
`tests/test_stats_tests_significance.py`.

**Dependencies:** None.

### Phase 4: Builder blocks, CSVs and CLI tables
**Goal:** `realism_ranking.json` gains both blocks, and the five CSVs are written. No figure yet.

- [ ] 4.1 — `CompetitorRecord.typicality_round_scores` (the same survivor filter as
      `typicality_means`; a test asserts that the per-persona means of the round scores equal
      `typicality_means` element-wise).
- [ ] 4.2 — `_typicality_distribution(records, *, n_levels, bands, withdrawn, skips)`: weights,
      distribution, band shares, `mean`, `n_multi_round`; `withdrawn`/`unjudged` lists; it reuses
      `_grid` for the shape. A score outside 0..k−1 raises (as `_typicality_levels` does); a
      withdrawn slug that is also consumed raises.
- [ ] 4.3 — `_typicality_effects(synthetic, real, factor_significance, *, bootstrap, skips)`:
      omnibus ε² read from the `by_model`/`by_method` Kruskal results; model pairs joined to the
      Dunn rows by `(a, b)`; the vs-reference rows for both families with Holm via `holm_adjust`.
- [ ] 4.4 — `build_ranking(..., typicality_bands=..., withdrawn=...)`, both required and never
      defaulted in the builder. Flatteners for the five CSVs, sorted by `_competitor_position`
      (distribution: then level).
- [ ] 4.5 — CLI: `--typicality-bands` (default `4,7`, parsed and validated as
      0 ≤ b1 < b2 < k−1), `load_cap_index(output_base)` always (it is the gate's own output and a
      hard upstream), withdrawn slugs filtered to the country, the five CSVs written, and the
      bands recorded in `provenance`.
- [ ] 4.6 — Tests in `tests/test_realism_ranking_builder.py`, and the e2e fixture gains a
      `population_cap/_index.json`.

**Files Modified:** `src/population_synthetic/analysis/realism_ranking/loader.py`,
`src/population_synthetic/analysis/realism_ranking/builder.py`,
`scripts/analyze/rank_persona_realism.py`, `tests/test_realism_ranking_builder.py`,
`tests/test_realism_ranking_loader.py`, `tests/test_realism_ranking_e2e.py`.

**Dependencies:** Phases 1 (withdrawn slugs) and 3.

### Phase 5: Presentation module `glyph_grid.py`
**Goal:** The reusable drawing pieces, behind the presentation boundary.

- [ ] 5.1 — `PointCanvas`: a figure of exactly `width_pt × height_pt` (the width must not exceed
      `style.FULL`, else raise), with axes and text placed in points.
- [ ] 5.2 — `draw_mini_histogram`: bars of width 1 at 0..n−1, colours passed in, y scale √ (via
      `set_yscale("function", ...)`), limits [0, 1]; an optional reference outline drawn as a
      post-step line (0.7 pt, `BASELINE_DARK`); spines `GRID_RULE` at `GRID_LINEWIDTH`, no ticks.
      It validates that the heights are finite, in [0, 1] and sum to 1 within 1e-9; it does not
      normalise them.
- [ ] 5.3 — `draw_withdrawn_cell` (two `MUTED_GREY` diagonals at 0.5 pt) and `draw_empty_cell`
      (a fill and an optional centred mark).
- [ ] 5.4 — `draw_ternary`: triangle outline, the 8–10 half-mass guide, host-tinted points (2.2 pt,
      `SURFACE` edge 0.25 pt), a reference star (5 pt), optional corner labels. It validates each
      share triple (non-negative, sums to 1 within 1e-9) and maps it to barycentric coordinates.
- [ ] 5.5 — `stepped_colorbar` over `palette.heatmap_levels(n)` with a `BoundaryNorm`.
- [ ] 5.6 — `tests/test_glyph_grid.py` plus the membership test in `tests/test_figure_compliance.py`.

**Files Modified:** `src/population_synthetic/analysis/utils/glyph_grid.py` (new),
`tests/test_glyph_grid.py` (new), `tests/test_figure_compliance.py`.

**Dependencies:** None (it can run in parallel with Phases 1–4).

### Phase 6: The figure and its wiring
**Goal:** `typicality_distribution_by_model_strategy` is produced by the CLI and the GUI sweep.

- [ ] 6.1 — `charts.plot_typicality_distribution_grid(ranking, *, country, model_order, hosting)`.
      Layout from the P20 geometry. The cell side is `min(26.5, fit)`, where `fit` is derived from
      the canvas width and the column count; it raises below 18 pt, because with more models the
      8 pt labels no longer fit. A missing reference raises `ValueError` ("no real population in
      the consumption set"), so the loop reports the figure as not rendered; the outline, column and
      star *are* the comparison. The legend (hosted, locally served, reference outline, withdrawn,
      combination, reference star), plus "not judged" / "no typicality" only when such a cell
      exists. Below it, the triangle note and the strategy key (prefix `figure_term("strategy_key_title")`,
      lines from `method_key_lines`, second line hung under the first using
      `style.text_width_inches` of the prefix rather than P20's literal 38.5 pt).
- [ ] 6.2 — CLI: when charts are on, load `{country}_performance.json` (raise if missing, naming
      `rank_models.py`) and compute `ranked_model_order` before writing anything; compute the
      hosting dict; save this chart with `fixed_canvas=True` (the loop grows a per-chart
      `fixed_canvas` flag).
- [ ] 6.3 — `config/gui/flows/analysis_workflow.yaml`: `realism_ranking.depends_on:
      [persona_realism, model_ranking]`, with a comment giving the reason.
      `config/analysis/analysis_registry.yaml`: the `realism_ranking` description names the new
      figure and blocks and its read of `model_ranking` output.
- [ ] 6.4 — Tests: the chart and e2e tests (below); workflow graph/state tests if they pin edges.
- [ ] 6.5 — Manual: run against the live base with `--rounds 1` and compare with
      `compact/P20_square_grid_top_labels.png`.

**Files Modified:** `src/population_synthetic/analysis/realism_ranking/charts.py`,
`scripts/analyze/rank_persona_realism.py`, `config/gui/flows/analysis_workflow.yaml`,
`config/analysis/analysis_registry.yaml`, `tests/test_realism_ranking_e2e.py`,
`tests/test_realism_artifacts.py`, `tests/test_workflow_graph_items.py` (if it pins edges).

**Dependencies:** Phases 1, 2, 4, 5.

### Phase 7: Documentation
**Goal:** The docs describe what shipped.

- [ ] 7.1 — See the Documentation Plan.

**Dependencies:** Phase 6.

---

## Testing Plan

### Unit Tests
- [ ] **Round-weighted distribution, hand-computed**: survivors with rounds (8, 9), (9), (10, None,
      10) and a non-survivor. Expected weights: 8 → 0.5, 9 → 1.5, 10 → 1.0; sum 3; mean equals the
      mean of the per-persona means (8.5, 9, 10) exactly.
- [ ] **Reduction**: every r_i = 1 → integer weights equal to `np.bincount` of the scores, and equal
      to the existing `typicality_histogram` counts for the same record.
- [ ] **Band shares**: edges (4, 7) on a known distribution; they sum to 1; `--typicality-bands 7,4`,
      `-1,4` and `4,10` raise.
- [ ] **ε²**: H = 564.14, N = 5760 → 0.09796 (golden omnibus row, 0.0980 to 4 d.p.); n < 2 raises.
- [ ] **Cliff's δ bootstrap**: point equals `cliffs_delta` on ties-heavy integer samples (U
      identity); a = [1, 2, 3], b = [1, 2, 3] → δ = 0; fully separated samples → δ = 1 and CI
      [1, 1]; same seed → identical CI; argument order swapped → negated point and mirrored CI.
- [ ] **Mann-Whitney**: agrees with `scipy.stats.mannwhitneyu` on a textbook example; empty sample
      raises.
- [ ] **Dunn orientation**: for every model pair, sign(δ) == sign(Dunn z) whenever both are nonzero.
- [ ] **Holm families**: the combination family has one entry per synthetic competitor with ≥ 1
      survivor; the model family has one per model; the p_Holm values equal
      `holm_adjust` over exactly that family.
- [ ] **Withdrawn vs unjudged vs no-typicality**: a fixture with one of each produces three
      distinct cell states in the block; a withdrawn slug that is also consumed raises.
- [ ] **Missing reference**: vs-reference rows are empty, with a `skipped_tests` reason; the chart
      raises `ValueError`.
- [ ] **Labels**: raise on a missing `figure_terms.yaml` key and on a missing
      `display.reference_source`.
- [ ] **`glyph_grid`**: `PointCanvas(456, 280.5)` saved through `save_figure(fixed_canvas=True)`
      writes an SVG whose root width is `456pt`; heights that do not sum to 1 raise; a share triple
      that does not sum to 1 raises; no artist has a non-None alpha; the module imports no
      `population_synthetic.analysis.<subpackage>`.
- [ ] **Model order**: `ranked_model_order` reproduces `meta.json`'s `model_order` on a fixture
      mirroring the live tiers; a grid model unknown to the ranking raises.

### Integration Tests
- [ ] **e2e** (`test_realism_ranking_e2e.py`): the fixture with a cap index and a
      `performance.json` writes all five CSVs and the three figure files; the SVG is 456 pt wide;
      without `performance.json` and with charts on, the run raises before writing
      `realism_ranking.json`; with `--no-charts` it succeeds.
- [ ] **Geometry**: every histogram axes of the returned figure sits at the P20 box (±1e-6 pt) for
      a 12 × 5 fixture.
- [ ] **Determinism**: two runs, and a run on a shuffled record list, give byte-identical JSON, CSVs
      and PNG.
- [ ] **Existing figures unchanged**: the existing chart tests pass unmodified. The
      `model_ranking` figures are byte-identical before and after the Phase 1 lift.

### Manual Verification
- [ ] `python scripts/analyze/rank_persona_realism.py --slug ... --rounds 1 --force` on the live
      base: the distribution CSV matches `golden/distribution_first_round_by_*.csv` (script check),
      and the figure matches `compact/P20_square_grid_top_labels.png` except for the em-dash key,
      "Strategies" and "individuals".
- [ ] The same without `--rounds`: the omnibus, model-pair and vs-reference point estimates match
      the `golden/` CSVs (`typicality_mean` basis). The CIs agree only within Monte-Carlo tolerance
      (|Δ| < 0.02), because the resampling scheme differs from the prototype's.
- [ ] Open the EPS: the SCB outline and host tints look the same as in the PNG (no transparency).

### Edge Cases
- [ ] A competitor whose survivors all score one level (a single bar; the √ scale at 1.0).
- [ ] A survivor with an impossible round among its rounds (r_i < rounds consumed).
- [ ] A model withdrawn in every strategy (it is absent from both the ranking and the grid; not a
      column).
- [ ] 13 models: the cell side shrinks below 26.5 and the canvas stays 456 pt; with a very large
      count it raises below 18 pt.

---

## Documentation Plan

- [ ] `docs/development/persona-realism-judge.md`: a new subsection after "The typicality axis",
      covering the distribution grid (round-weighted basis and its reduction to one round, bands,
      withdrawn and unjudged cells, the dependency on `model_ranking` output), the effect-size
      tables (families, orientation, seeds) and the judge/generator overlap caveat.
- [ ] `docs/development/figure-conventions.md`: add a section for glyph grids and ternaries (cells
      are small axes, not `imshow`; bar heights √-scaled and said so on the figure; ternary corners
      labelled once; the reference as outline + star + detached column), a rule for vertical 90°
      model labels above a grid on a fixed canvas, and a statement that published artwork takes
      manuscript-controlled words from `figure_terms.yaml`. Update the presentation-layer module
      count from seven to eight.
- [ ] `CLAUDE.md`: the realism_ranking paragraph gains the distribution grid and effect tables; the
      "seven modules" of the presentation layer become eight (add `glyph_grid`); the analysis
      registry paragraph notes the new `realism_ranking → model_ranking` edge. Also list
      `model_order.py` among the shared `utils/`, unless the transposed plan already did.
- [ ] `docs/architecture/sub-packages.md`: `model_order.py` and `glyph_grid.py`; fix the module count.
- [ ] `docs/architecture/configuration.md`: `figure_terms.yaml` and `display.reference_source`.
- [ ] `scripts/analyze/rank_persona_realism.py` module docstring: the new outputs and
      `--typicality-bands`.
- [ ] `realism_ranking/builder.py` and `charts.py` module docstrings: the new blocks and figure.

---

## Rollback Plan

1. **Before merge**: each phase is its own commit, so revert the phase commits in reverse order.
   Phases 1–3 and 5 are additive and inert on their own. Phase 4 changes `build_ranking`'s
   signature (two new required arguments), so revert it together with Phase 6.
2. **Data**: no upstream artifact changes. `persona_realism` outputs, the capped mirror and
   `model_ranking` outputs are read-only here. Rerunning `rank_persona_realism.py --force` after a
   revert rewrites `realism_ranking/{country}/` without the new files; delete the five new CSVs and
   the figure trio by hand if they must not linger.
3. **Config**: revert `figure_terms.yaml`, the `display.reference_source` keys and the
   `depends_on` edge together with the code that reads them. A leftover `display` key is harmless;
   a leftover edge only orders the sweep.
4. **Phase 1 caveat**: if the transposed plan has started relying on `model_order.py`, do not
   revert Phase 1; revert only this plan's later phases.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| The reference has only n = 100 individuals, so its outline and star are noisy, and every vs-reference CI is dominated by the reference's sampling error | High | Med | Report `reference_n` on every row; the bootstrap resamples the reference too; say so in the docs. A larger `--real-sample` is the real fix, and outside this plan |
| The judge (`claude-sonnet-5`) belongs to a generator's family and may prefer that family's individuals | Med | Med | Docs caveat; the `claude_sonnet` column can be read with that in mind. Not computed (Out of Scope) |
| Ternary dots overlap in rows A–C (all near the 8–10 corner) | High | Low | Accepted: the triangle is an overview; exact shares are in `typicality_bands.csv`. Jitter rejected (it moves data) |
| `realism_ranking` now waits for `model_ranking` in a sweep, and blocks if it is disabled | Med | Low | Documented; `bypass` on `model_ranking`; `--no-charts` needs no ranking file |
| Merge conflict with the transposed plan (`model_order.py`, the CLI chart loop) | Med | Low | The coordination note; identical Phase 1 contract |
| More than 12 models shrink the cells | Low | Med | Derived cell side with an 18 pt floor that raises |
| Pseudo-replication inflates every p-value (personas of one run are not independent) | High | Med | The existing `CAVEATS` travel in the same document; effect sizes are published beside every p so that size, not p, is read |
| Two typicality distribution bases in one document (rounded, round-weighted) get confused | Med | Low | Each block states its `basis` as data; the docs contrast them; they agree at one round |
| The country loaders reject the new `display` key | Low | Low | Task 2.2 verifies this and fixes it in the same commit |
| The approved image depends on the fonts installed on the rendering machine | Low | Low | `style.house_font` already raises when the house font is absent |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — model order + withdrawn slugs | 0.5 day (0 if the transposed plan landed) | None |
| Phase 2 — config vocabulary | 0.5 day | None |
| Phase 3 — statistical primitives | 0.5 day | None |
| Phase 4 — builder blocks + CSVs | 1 day | 1, 3 |
| Phase 5 — `glyph_grid.py` | 1 day | None |
| Phase 6 — figure + wiring | 1 day | 1, 2, 4, 5 |
| Phase 7 — docs | 0.5 day | 6 |

---

## References

- Prototype and golden outputs: `docs/development/plans/pending/typicality-distribution-grid/`
- Related plan: `docs/development/plans/pending/transposed-reference-centred-grids.md` (shared
  `model_order.py`)
- ADR: `docs/development/decisions/2026-08-12-self-contained-typicality-axis.md` (sequential ramp,
  no composite score, the four cell states)
- `docs/development/figure-conventions.md`, `docs/development/persona-realism-judge.md`
- `.claude/skills/centred-heatmap/SKILL.md` (model order and hosting derivation)
- Manuscript `TERMINOLOGY-RULES.md` T1 (individual, strategy) in
  `.../Manuscripts/40_llm-population-fidelity-benchmark/`; the staged figure
  `figures selection/typicality_distribution_by_model_strategy.{png,svg,eps}`
- Tomczak, M. & Tomczak, E. (2014) on ε² for Kruskal-Wallis; Romano et al. (2006) on the
  magnitude thresholds of Cliff's δ

## Open questions for the user

1. **Existing method keys.** Nine figure call sites still print "Methods:" (and figure titles say
   "Method distribution"). This plan uses "Strategies" only in the new figure, so the manuscript's
   figures would mix the two terms. Should a follow-up switch all keys to
   `figure_term("strategy_key_title")`?
2. **Stem dialect.** `typicality_distribution_by_model_strategy` sits beside `typicality_by_method`
   in the same folder. The plan keeps the manuscript's staged name. Confirm, or ask for the
   repo-dialect stem and a restaging.
