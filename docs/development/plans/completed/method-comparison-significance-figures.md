# Plan: Method-comparison significance figures (brackets + stars)

**Date:** 2026-07-20
**Author:** Basil
**Status:** Completed
**Completed:** 2026-07-20 16:23

> **Refinement (2026-07-20):** two follow-up changes landed after the initial three phases.
> 1. **Default `pairs_mode` is now `significant-only`** (was `adjacent`). `resolve_pairs("significant-only")`
>    considers **all** unordered method pairs and keeps only those with a significant pairwise Nemenyi p —
>    the cutoff is read from config (`significance_cutoff(star_thresholds)` = the `*` threshold = 0.05, "at
>    least one star"), never a hardcoded literal. Only significant brackets are drawn; non-significant pairs
>    get no bracket (so `ns` is never shown, and the in-figure key omits `ns` in this mode).
> 2. **Per-category panel headers now show the attribute's level count.** The builder stores
>    `panels[category]["n_category_values"]` = length of that attribute's config `values` list (from the
>    scheme's mapping tier — `scb_native` for Sweden, the same tier scored), and the renderer displays it:
>    `age_group  (n=7 models · 7 levels)` / `Friedman p=…`. The Overall panel spans all categories, so it
>    omits the level count and shows only the model `n`. Fail-fast: an analysed attribute with no resolved
>    (or empty) `values` raises.
**Base Branch:** `feature/manuscript-fidelity-tables`
**Branch:** `feature/method-significance-figures`

---

## Overview

**What:** Add publication-style **method-comparison figures** to the `method_significance/`
subpackage: for each demographic category (+ an "Overall" panel), a bar/box plot of TV-similarity
per method with **pairwise significance brackets and asterisks** (`ns / * / ** / *** / ****`),
in the standard GraphPad/Prism convention.

**Why:** We can compare the generation methods against each other on TV-similarity, using the
**models as repeated measurements** (each model is measured under every method within a category).
This makes a paired method comparison estimable and lets us annotate significance directly on the
figure — the format reviewers expect — instead of only the current rank-based summary charts.

**How:** Reuse the existing `method_significance` loader and Friedman machinery; add a per-category
**Friedman omnibus + Nemenyi pairwise post-hoc** (models as blocks), a JSON/CSV of the pairwise
p-values, and a new matplotlib renderer that draws the comparison plot with significance brackets.
Wire it into the existing driver + GUI task.

## Problem Statement

The `method_significance` subpackage answers "does method matter vs model, per category" via Page's
L / Friedman / Nemenyi / a logit-mixed model, and renders trend/slope/CD/dominance charts. It does
**not** produce the familiar "bars with significance stars" figure that directly compares the
methods head-to-head per category. That figure is what's wanted for the manuscript. The data
supports it: within a category, the same set of models is scored under each method, so the methods
can be compared as **paired samples with models as the blocking factor** — no new data or replicates
needed.

## Goals

### In Scope
1. Per-category **Friedman omnibus** across the methods present, blocks = models (complete cases).
2. **Nemenyi pairwise post-hoc** → a p-value per method-pair per category (and for "Overall").
3. A **significance-annotated comparison figure**: methods on x, TV-similarity on y, bars + individual
   model points, pairwise brackets with stars, an in-figure key, per panel — as a per-category grid
   **and** a standalone Overall panel. PNG + SVG via `save_figure`.
4. A machine-readable **results table** (JSON + CSV): omnibus stat/p + pairwise p (raw and corrected)
   per category and Overall.
5. Config-driven choice of **which method pairs to bracket** (default: `significant-only` — all pairs
   filtered to a significant Nemenyi p; the cutoff is the config `*` star threshold).
6. Wire into `scripts/analyze/analyze_method_significance.py` (+ its GUI task picks it up).

### Out of Scope
- Any raw-TV factorial/3-way ANOVA with replication (not estimable at n=1 per cell — see Definitions).
- Manufacturing replicates by subsampling populations (deferred elsewhere).
- Changing the existing trend/slope/CD/dominance charts or the mixed-model interaction.
- Model-vs-model significance (this figure holds method as the compared factor; model is the block).
- Countries other than what the run selects (renderer is country-agnostic; manuscript target = Sweden).

## Success Criteria

- [x] `python scripts/analyze/analyze_method_significance.py --country swedish` writes
      `03_Analysis/method_significance/swedish_method_comparison.png` + `.svg` (grid) and
      `swedish_method_comparison_overall.png` + `.svg`, plus `swedish_method_comparison.{json,csv}`.
- [x] Each panel compares exactly the methods present in the loaded combos (data-driven, ordered by
      `STRATEGY_COMPLEXITY_ORDER`), with the omnibus Friedman p shown and pairwise brackets/stars.
- [x] Star mapping matches convention: `ns` p>0.05, `*` ≤0.05, `**` ≤0.01, `***` ≤0.001, `****`
      ≤0.0001; an in-figure key defines them.
- [x] Blocks are **complete-case models** per panel; each panel reports its `n` (models); a panel with
      `n < 3` complete models is skipped with a loud, logged reason (no silent blank).
- [x] The results JSON/CSV contain omnibus (statistic, p) and pairwise p (raw + BH-corrected) for every
      category and Overall, with the `n` used.
- [x] `pytest` passes with new tests for the stats and the star-mapping/bracket logic; `ruff check src/`
      clean.

## Definitions

- **TV-similarity:** `1 - tv_distance` per (model, method, category); one scalar per cell
  (`ComboPerformance.tv_similarity[attr]`). **n = 1 per (model × method × category) cell** — there are
  no within-cell replicates, so replication for a method comparison comes from the **models**.
- **Method (compared factor):** the generation strategy; levels = strategies present in the loaded
  combos, ordered by `STRATEGY_COMPLEXITY_ORDER`. ("Four methods" = whatever the GUI run checks.)
- **Model (blocking factor):** each model is a block/"participant" measured under every method. The
  comparison is paired across models. Models are treated as the repeated dimension, not a fixed effect
  of interest here.
- **Complete-case (per panel):** for a given category, the set of models that have a non-NaN
  TV-similarity for that category under **every** compared method. Friedman requires complete blocks;
  models missing any compared method (or NaN for that attribute) are dropped from that panel and the
  drop is counted/reported. No imputation.
- **Overall panel:** response = each model's overall TV-similarity (mean across categories,
  `overall.tv_similarity_mean`) under each method; Friedman across methods, blocks = models.
- **Omnibus:** Friedman rank test across the compared methods within a panel (blocks = models). Reports
  statistic, p, and Kendall's W (effect size), reusing the existing `friedman_test`.
- **Pairwise post-hoc:** Nemenyi test for Friedman (`scikit-posthocs.posthoc_nemenyi_friedman`),
  yielding a symmetric p-matrix over methods; the value for a bracketed pair drives its stars.
- **Bracketed pairs:** which method pairs get a drawn bracket. Config-driven; default
  `significant-only` (every unordered pair, filtered to a significant pairwise p — the config `*` cutoff).
  Options: `adjacent` (consecutive complexity steps), `all`, `vs-baseline` (all vs the simplest method),
  `significant-only`.
- **Level count (`n_category_values`):** per analysed attribute, the number of declared category values
  (levels) from the scheme's config `values` list (the mapping tier scored — `scb_native` for Sweden);
  computed in the builder and shown in each category panel header.
- **Star mapping:** `p>0.05 → ns`, `≤0.05 → *`, `≤0.01 → **`, `≤0.001 → ***`, `≤0.0001 → ****`.

---

## Technical Design

### Approach

Extend `method_significance/` — it already loads one `ComboPerformance` per (country, strategy, model),
already has `friedman_test`, `nemenyi_posthoc`, the statsmodels/scikit-posthocs lazy-import guard, and
a `load → build → visualize` driver. Add:

1. **Stats** (`builder.py` / `stats_tests.py`): a `method_comparison` block computing, per category and
   for Overall, the Friedman omnibus + Nemenyi pairwise p-matrix over the compared methods, on
   complete-case models. BH-FDR across the omnibus p's (one per category). All aggregation stays in the
   builder (JSON is the serialized contract); the renderer is a pure consumer.
2. **Renderer** (`charts.py`): `plot_method_comparison(result, out_path, *, overall_only=False)` drawing
   bars (mean TV-similarity per method) + individual model points, with significance brackets/stars over
   the configured pairs and an in-figure key. Grid variant = one small panel per category + Overall;
   standalone Overall variant for the headline. Brackets drawn directly in matplotlib (line + centered
   star text) — no new dependency.
3. **Config** for pair selection (`config/analysis/method_significance/comparison.json` or a key added to
   an existing config), fail-fast on an unknown mode.
4. **Wiring** in `scripts/analyze/analyze_method_significance.py`: call the new stats in the build step
   and the new chart in the `if not args.no_charts:` block; update the docstring outputs.

**Why models-as-blocks / Friedman (not ANOVA):** TV-similarity is a bounded [0,1] proportion,
heteroscedastic near the edges; at n=1 per cell a replicated factorial ANOVA is not estimable. A
paired **rank-based** test with models as blocks is the standard, assumption-light tool and is already
the subpackage's idiom (Demšar). The mixed-model route (`logit(TV) ~ method*category + (1|model)`)
remains available as a future inferential extension but is not needed to produce the requested figure.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Friedman + Nemenyi, models as blocks | Assumption-light on bounded TV; paired; already in repo | Rank-based (no raw effect size beyond W) | **Chosen** |
| Paired Wilcoxon signed-rank + Holm per pair | Direct per-pair p; intuitive | Multiple pairwise tests; less coherent than a single omnibus+posthoc | Alternative (offer as a config switch later) |
| Repeated-measures ANOVA on logit(TV), model=subject | Familiar ANOVA table | Needs complete cases; Greenhouse–Geisser; boundedness even after logit | Rejected (kept as possible sensitivity view) |
| Raw-TV factorial ANOVA with replication | What was literally asked | Not estimable at n=1; boundedness — already rejected in prior plan | Rejected |
| `statannotations` library for brackets | Turnkey | New dep, seaborn-coupled, unmaintained; repo uses matplotlib directly | Rejected |
| Draw brackets in matplotlib | No dep; matches chart style | ~30 lines of bracket geometry | **Chosen** |
| Bracket all 6 pairs by default | Complete | Clutter on a 4-method panel | Rejected (default = adjacent-ordered, configurable) |

### Architecture & Module Contracts

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `config/analysis/method_significance/comparison.json` (new) | Declare bracketed-pair mode + star thresholds | (static) → JSON | models, countries, matplotlib |
| `method_significance/stats_tests.py` (edit) | Add Nemenyi pairwise p-matrix helper if not already exposed | `matrix(models×methods)` → p-matrix | figures, file paths |
| `method_significance/builder.py` (edit) | Compute `method_comparison` block (omnibus + pairwise + n) per category & Overall | `records, attributes, config` → `result["method_comparison"]` | colormaps, bracket geometry |
| `method_significance/charts.py` (edit) | Render bars+points with significance brackets/stars | `result, out_path` → `Path\|None` (+ SVG) | how p-values were computed, file discovery |
| `scripts/analyze/analyze_method_significance.py` (edit) | Load config, call new stats + chart | CLI args → written files | stats math, bracket drawing |

`result["method_comparison"]` shape:
```json
{
  "methods": ["all_pick", "all_generate_pick", ...],
  "pairs_mode": "adjacent",
  "star_thresholds": [{"max_p": 0.0001, "symbol": "****"}, ...],  // echoed from config (Phase 2)
  "ns_symbol": "ns",                                              // echoed from config (Phase 2)
  "panels": {
    "age_group": {
      "n_models": 18, "n_dropped": 2,
      "omnibus": {"test": "friedman", "statistic": 41.2, "p": 3.1e-9, "p_bh": 6.2e-9, "kendall_w": 0.57},
      "means": {"all_pick": 0.81, "all_generate_pick": 0.86, ...},
      "per_model": {"claude_sonnet": {"all_pick": 0.79, "all_generate_pick": 0.88, ...}, ...},  // Phase 2 (additive): individual points / paired lines
      "pairwise_p": {"all_pick|all_generate_pick": 0.004, ...},
      "insufficient_n": false
    },
    "...": { },
    "overall": { }
  }
}
```

Chart signature (matches existing `plot_*` contract, returns `Path | None`):
```python
def plot_method_comparison(result: dict[str, Any], out_path: str | Path, *, overall_only: bool = False) -> Path | None
```

---

## Implementation Plan

### Phase 1: Stats — per-category method comparison
**Goal:** `result["method_comparison"]` populated and unit-tested; no charts.
**Started:** 2026-07-20 · **Completed:** 2026-07-20

- [x] 1.1 — Add `config/analysis/method_significance/comparison.json`: `pairs_mode` (default `adjacent`),
      allowed modes, and the star thresholds. Fail-fast loader on missing/unknown mode.
- [x] 1.2 — In `stats_tests.py`, expose a `nemenyi_pairwise(matrix)` returning a labeled p-matrix over
      methods (reuse the existing Nemenyi wrapper; add if only CD-form exists).
- [x] 1.3 — In `builder.py`, add `_method_comparison(records, attributes, methods, config)`: per category
      build the `models × methods` complete-case matrix of TV-similarity, run `friedman_test` + Kendall's
      W + `nemenyi_pairwise`; record means, n, dropped; repeat for Overall using per-model overall TV.
      BH-correct the omnibus p across categories. Attach as `result["method_comparison"]`.
- [x] 1.4 — Resolve the compared **methods** from the records (present strategies, ordered by
      `STRATEGY_COMPLEXITY_ORDER`); resolve **bracketed pairs** from `pairs_mode`.

**Files Modified:**
- `config/analysis/method_significance/comparison.json` (new)
- `src/population_synthetic/analysis/utils/stats_tests.py` (added `nemenyi_pairwise`; the reused
  Nemenyi wrapper lives here, not in a `method_significance/stats_tests.py` — that file does not exist)
- `src/population_synthetic/analysis/method_significance/builder.py` (config loader + `resolve_pairs`
  + `_method_comparison`)
- `tests/test_method_comparison.py` (new), `tests/test_method_significance.py` (result-key set assertion)

**Dependencies:** None

### Phase 2: Renderer — significance-annotated comparison figure
**Goal:** The bars+points+brackets figure (grid + Overall), PNG+SVG.
**Started:** 2026-07-20 · **Completed:** 2026-07-20

- [x] 2.1 — `charts.py`: helpers `_p_to_stars(p, thresholds, ns_symbol)` and
      `_draw_sig_bracket(ax, x1, x2, y, text, *, tick)` (line + down-ticks + centered star text); bracket
      stacking via `_stack_bracket_levels` (greedy interval-graph colouring: each bracket takes the lowest
      level whose already-placed spans don't horizontally overlap it, so brackets never collide).
- [x] 2.2 — `plot_method_comparison(result, out_path, *, overall_only=False)`: per panel draw bars = per-method
      mean TV-similarity + individual model points + faint paired lines (one polyline per model across
      methods); brackets over the configured pairs (resolved via the builder's `resolve_pairs`) with stars
      from `pairwise_p`; annotate the omnibus Friedman p (+ BH) and `n` in the panel title; in-figure star key.
      Grid layout for categories + Overall when `overall_only=False`; single Overall panel when `True`.
      `insufficient_n` (`n<3`) panels render a labeled "insufficient n (n<3)" placeholder and are logged
      (`logging.warning`). Route through `save_figure` (PNG+SVG). Returns `None` when the block is
      absent/empty or nothing is plottable.
- [x] 2.3 — Consistent styling with the subpackage (deferred `Agg`, `dpi=150`, `plt.close` via `save_figure`).

**Per-model points — additive Phase-1 block change (needed):** the Phase-1 panel carried only `means`, so
individual points/paired lines were not derivable by a pure consumer. Rather than recompute in the chart,
the builder now also emits, per panel, `per_model: {model: {method: tv_similarity}}` over the complete-case
models entering the test (built from the same matrix as `means`, no new computation). The block additionally
echoes `star_thresholds` + `ns_symbol` (from the loaded config) so the renderer reads the star mapping from
`result` and falls back to `load_comparison_config()` only if absent. Both are additive; older consumers and
Phase-1 tests (superset assertions) are unaffected.

**Files Modified:**
- `src/population_synthetic/analysis/method_significance/charts.py` (new `plot_method_comparison` + helpers)
- `src/population_synthetic/analysis/method_significance/builder.py` (additive: `panels[*].per_model`,
  block-level `star_thresholds`/`ns_symbol`)
- `tests/test_method_comparison_chart.py` (new)

**Dependencies:** Phase 1

### Phase 3: Wiring + results table + docs
**Goal:** Regenerates on every run; results exported; documented.
**Started:** 2026-07-20 · **Completed:** 2026-07-20

- [x] 3.1 — In `analyze_method_significance.py`: the build step already loads `comparison.json` by default
      (`build_method_significance` -> `load_comparison_config()`), so `result["method_comparison"]` is
      produced without extra wiring; in the chart block call `plot_method_comparison` twice (grid +
      `overall_only=True`) with `is not None` guards; write `{country}_method_comparison.{json,csv}`
      (driver-local writers `_write_method_comparison_json/_csv`, flatten panels → one row per
      (category|overall, method-pair)). Updated the module docstring outputs.
- [x] 3.2 — Updated `docs/architecture/commands.md`, `configuration.md` (new config), and the
      `method_significance` note in `sub-packages.md`.
- [x] 3.3 — The GUI `method_significance` task (`analysis_workflow.yaml:74`) already runs the driver — no
      flow change needed (confirmed; yaml untouched). New artifacts appear under the same task's outputs.

**Files Modified:**
- `scripts/analyze/analyze_method_significance.py`
- `docs/architecture/commands.md`, `docs/architecture/configuration.md`, `docs/architecture/sub-packages.md`

**Dependencies:** Phase 2

---

## Testing Plan

### Unit Tests
- [x] `_p_to_stars` maps boundary p-values correctly (0.05, 0.01, 0.001, 0.0001, >0.05 → ns).
- [x] `_method_comparison` on a synthetic `records` set: correct complete-case matrix, correct `n`/dropped,
      Friedman p matches a direct `scipy` call, Nemenyi p-matrix symmetric, Overall panel uses overall TV.
- [x] Bracketed-pair resolution: `adjacent`/`all`/`vs-baseline`/`significant-only` select the right pairs;
      unknown mode raises.
- [x] BH correction applied across category omnibus p's; both raw and corrected stored.

### Integration Tests
- [x] From a built `result` fixture, `plot_method_comparison` returns a `Path`; `.png` and `.svg` exist;
      the Overall-only variant renders a single panel.
- [x] A category with `n<3` complete models renders the placeholder and is flagged, without error.
- [x] Results CSV/JSON contain a row/entry per category + Overall with omnibus and pairwise p.

### Manual Verification
- [x] Run the driver on Swedish data; open the grid + Overall figures; confirm brackets/stars, the key,
      per-panel `n`, and that methods are complexity-ordered.
- [x] Cross-check one panel's omnibus p against a hand `scipy.stats.friedmanchisquare` on the same matrix.
      (Overall panel: stored chi2=21.4857, p=2.54e-4, n=7 — exact match to a direct `friedmanchisquare`.)

### Edge Cases
- [ ] Only two methods present → single pair, one bracket, Friedman reduces to a paired comparison
      (fallback to Wilcoxon signed-rank if Friedman degenerate) — document behavior.
- [ ] A method fully NaN for a category → excluded from that panel; if <2 methods remain, skip panel.
- [ ] All models complete → n equals model count; ties handled by Friedman ranking.

## Documentation Plan

- [x] `commands.md` — new outputs of `analyze_method_significance.py`.
- [x] `configuration.md` — `config/analysis/method_significance/comparison.json`.
- [x] `sub-packages.md` — extend the `method_significance` entry.
- [x] Inline docstrings: the statistical design (models-as-blocks Friedman/Nemenyi) and the star key.

## Rollback Plan

1. Additive: new config, new stats block, new chart, new outputs, optional new tests. Revert by removing
   the `method_comparison` block + chart + config and the driver calls; existing charts/stats untouched.
2. No data migration; `result` gains one additive key older consumers ignore.

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Bracket clutter on many-pair panels | Med | Low | Default `adjacent-ordered`; `significant-only` mode; stacked bracket heights |
| Small complete-case `n` per category → weak power | Med | Med | Report `n` per panel; skip `n<3` loudly; note power in caption |
| Pseudo-replication (categories correlated) for the Overall pooled view | Med | Med | Overall uses per-model overall TV (one value per model), not pooled cells; state caveat |
| Nemenyi conservativeness hides real pair differences | Low | Med | Offer Wilcoxon+Holm as a config switch (alternative in the table) |
| Reviewer expects raw ANOVA | Low | Low | Caption states the rank-based paired design + why (boundedness, n=1) |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 (stats + config + tests) | ~1 day | None |
| Phase 2 (renderer + brackets) | ~1 day | Phase 1 |
| Phase 3 (wiring + export + docs) | ~2 hours | Phase 2 |

---

## References

- Existing subpackage: `src/population_synthetic/analysis/method_significance/` (loader/builder/stats_tests/charts)
- Driver: `scripts/analyze/analyze_method_significance.py`; GUI task `analysis_workflow.yaml:74`
- Prior design + caveats: `docs/development/plans/completed/per-category-method-model-significance.md`,
  `docs/development/model-method-significance-recap.md`
- Significance-star convention: GraphPad Prism FAQ 978; the `statannotations` convention (Python)
- Shared save helper: `src/population_synthetic/analysis/utils/figures.py::save_figure`

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- config/analysis/method_significance/comparison.json
- docs/architecture/commands.md
- docs/architecture/configuration.md
- docs/architecture/sub-packages.md
- docs/development/plans/active/method-comparison-significance-figures.md
- scripts/analyze/analyze_method_significance.py
- src/population_synthetic/analysis/method_significance/builder.py
- src/population_synthetic/analysis/method_significance/charts.py
- src/population_synthetic/analysis/utils/stats_tests.py
- tests/test_method_comparison.py
- tests/test_method_comparison_chart.py
- tests/test_method_significance.py
