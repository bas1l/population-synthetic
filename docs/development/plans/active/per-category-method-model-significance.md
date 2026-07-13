# Plan: Per-category method/model significance for TV

**Date:** 2026-07-13
**Author:** Basil
**Status:** In Progress
**Base Branch:** `dev`
**Branch:** `feature/per-category-method-model-significance`

---

## Overview

Add a new analysis process that sits **after** fidelity scoring and answers, per country and per
demographic attribute, **which factor — generation *method* (ordered strategy) or *model* —
significantly drives Total-Variation (TV) fidelity**, and whether the method-trend differs by model.
It consumes the existing per-combo fidelity reports (via `model_ranking`'s loader — no
recomputation) and applies the field-standard framework for comparing methods across many datasets
(Demšar 2006), adapted to our (model × method × category) grid.

## Problem Statement

`model_ranking` already tests **overall** factor impact (Kruskal–Wallis + Dunn/Holm, pooling
per-attribute TV-similarities): the first Swedish run found **strategy highly significant**
(H≈102.7, p≈3e-21) and **model not significant** (p≈0.199). But the **per-category** question —
"in *this* category, does method complexity move TV, and do models differ / respond differently?" —
has only descriptive scores (a heatmap), no tests. That per-attribute significance is the explicitly
open task recorded in `docs/development/model-method-significance-recap.md:17-22`. This plan
implements it, and does so with methods whose assumptions our data actually meets.

### The data reality that governs every method choice

- **Grain:** per-attribute marginal TV at `report["marginals"][<attr>]["tv_distance"]`
  (`analysis/fidelity/evaluator.py:144`, `TV = ½·Σ|p_real − p_syn|`, ∈[0,1], lower = better).
  `model_ranking/loader.py:102-111` already flattens the whole grid to
  **(model × strategy × attribute) → tv_distance / tv_similarity(=1−tv)**.
- **Dimensions:** 15 attributes (Sweden) / 14 (Italy); 5 canonical ordered strategies; up to ~20
  model configs (fewer executed). Countries: swedish, italian.
- **n = 1 per (model, method, category) cell — no replicates.** LLM generation has no seed;
  "replicate" = re-run (recap line 26). **This is the central constraint.**
- **Ordered method axis** (`STRATEGY_COMPLEXITY_ORDER`, simplest→complex):
  `all_pick` → `all_pick_dag` → `all_generate_pick` → `all_generate_evaluate_pick` →
  `all_generate_evaluate_random_pick`.

### Critique of the naive framing (what this plan deliberately avoids)

1. **n=1 ⇒ the per-category model×method interaction is not estimable** (zero residual df). The
   literal "compare TV(method) trends across models, *per category*" cannot yield a p-value — it is
   reported **descriptively only** (slope heatmap), never as a test.
2. **Monotonicity is an assumption, not a finding** — trend tests fire on a single step-change, so
   we test the quadratic component rather than assume a smooth ramp.
3. **TV is bounded [0,1] & heteroscedastic near 0** — parametric OLS/ANOVA on raw TV is unsafe;
   rank-based tests + a logit-linked model are used instead.
4. **Multiplicity** across 15 attributes → BH-FDR correction, always named in the output.
5. **Categories are not independent replicates** (age/income/region correlate) → modelled as a
   random effect and flagged in the caveats block.
6. **Rank vs magnitude** — every rank test is paired with an effect size (Kendall's W, Cliff's δ).

## Goals

### In Scope

1. New process subpackage `src/population_synthetic/analysis/method_significance/`
   (loader-reuse, builder, charts), one subpackage per process per the architecture convention.
2. New shared stats primitives in `analysis/utils/stats_tests.py`: Friedman (+Iman–Davenport,
   Kendall's W), Page's L trend test, Nemenyi post-hoc, Benjamini–Hochberg, Cliff's δ, and a
   logit-linked mixed-model interaction fit.
3. Per-attribute tests: ordered method trend (Page L + linear/quadratic contrast) and model omnibus
   (Friedman), BH-corrected across attributes; per-(attribute,model) descriptive trend slopes.
4. Overall (categories-as-blocks) inference: Demšar model comparison (Friedman → Nemenyi → CD
   diagram), Page L method trend, and a `logit(TV) ~ model*method + (1|category)` mixed model whose
   **interaction term is estimable** and answers factor-dominance.
5. Script `scripts/analyze/analyze_method_significance.py` (CLI mirroring `rank_models.py`) and an
   optional GUI action.
6. `scikit-posthocs` + `statsmodels` added to the `[analysis]` optional extra, imported lazily with
   a clear "install `.[analysis]`" error, matching the C2ST pattern.
7. Unit + fixture tests and doc updates.

### Out of Scope

- **Replicate generation / subsampling for replicates** — considered and deferred (see Alternatives).
  Single run per combo is assumed; the per-category interaction stays descriptive.
- Re-running or altering fidelity scoring — this process is strictly downstream, read-only over
  existing reports.
- Cross-country pooling — each country is analysed and reported separately.
- Beta regression as the *headline* model — kept only as an optional robustness cross-check.

## Success Criteria

- [x] `python scripts/analyze/analyze_method_significance.py --country swedish` produces
      `{country}_method_significance.json`, `.csv`, and charts from existing fidelity reports.
- [x] Per attribute: Page L (method) + Friedman (model) with raw **and** BH-adjusted p-values,
      plus Kendall's W / trend slope, present in JSON and console.
- [x] Overall: CD diagram of models, Page L method trend, and the mixed-model interaction Wald test
      + η² factor-dominance present.
- [x] Per-category interaction is emitted only as a descriptive slope heatmap — no p-value claimed.
- [x] Sanity check: overall result reproduces the known direction (method/strategy dominates model —
      η² method 15% ≫ model 4%; TV improves with complexity, overall Page L z ≈ −9.6).
- [x] Missing optional deps raise a clear install message; `--strict` fatal on missing reports.
- [x] `ruff check src/` clean; full `pytest` green; new primitives validated against `scipy`/
      `statsmodels`/`scikit-posthocs` on fixtures.

---

## Technical Design

### Approach

Reuse `model_ranking`'s `loader.py` to obtain `list[ComboPerformance]` per country (the
(model × strategy × attribute) TV grid) — **no fidelity recomputation**. Filter to the 5 canonical
ordered strategies and assign each a method rank 1–5. The escape from the n=1 wall is to **use the
~15 categories as the blocking/replication factor**, which maps the problem onto **Demšar (2006),
"Statistical Comparisons of Classifiers over Multiple Data Sets"** (models = classifiers,
categories = datasets) — the reviewer-recognised standard for exactly this shape.

Statistical method selection follows the data's assumptions (per the statistical-software guide,
§3): rank-based/non-parametric as the default for small-n bounded TV, multiple-comparison
correction always named, effect sizes reported alongside every p-value, and re-implemented
statistics pinned to an authoritative library's output on fixtures.

- **Model differences:** Friedman + Iman–Davenport across models (blocks = categories) → Nemenyi
  post-hoc → critical-difference diagram; effect size Kendall's W.
- **Method trend (ordered):** Page's L (blocks = categories/models) + linear **and** quadratic
  contrast (test, don't assume, monotonicity).
- **Factor dominance & overall interaction:** logit-linked `MixedLM`
  `logit(TV) ~ C(model) * method_rank + (1|category)` (0.5-squeeze for exact 0/1); the interaction
  term is estimable *because* categories supply replication, and η² decomposes model vs method vs
  category variance.
- **Per-category interaction:** descriptive only — slope heatmap (attribute × model) + faceted
  trend plots. No test claimed.
- **Effect size & multiplicity:** Cliff's δ for pairwise contrasts; Benjamini–Hochberg FDR across
  the 15 per-attribute p-values; Holm within the model post-hoc family.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Categories-as-blocks (Demšar), n=1 | No re-generation; runs on existing reports; field-standard | Per-category interaction not testable (descriptive only) | **Chosen** |
| Subsample each population into k sub-pops for replicates | Makes per-category interaction estimable | Requires re-scoring fidelity on subsamples; larger scope | Deferred (Out of Scope) |
| In-house Nemenyi / beta-LMM (no new deps) | Matches repo's dependency-light ethos | Re-implementing well-tested stats is error-prone | Rejected — add libs |
| `scikit-posthocs` + `statsmodels` under `[analysis]` | Battle-tested Nemenyi/CD + MixedLM; validatable | Two new optional deps | **Chosen** |
| Raw OLS/ANOVA on TV | Simple | Violates [0,1] boundedness & heteroscedasticity | Rejected (sensitivity check only) |

### Architecture Changes

New process subpackage alongside `fidelity/`, `model_ranking/`, `run_analytics/`:

```
src/population_synthetic/analysis/
├── utils/stats_tests.py         # + friedman_test, page_trend_test, nemenyi_posthoc,
│                                #   benjamini_hochberg, cliffs_delta, mixed_logit_interaction
└── method_significance/         # NEW process
    ├── __init__.py
    ├── builder.py               # per-country analysis → serialisable dict; JSON/CSV writers
    └── charts.py                # trend facets, slope heatmap, CD diagram, factor-dominance bar
scripts/analyze/analyze_method_significance.py   # NEW CLI (mirrors rank_models.py)
```

Reuses `model_ranking/loader.py` (`ComboPerformance`, discovery via `mapped/_index.json`) and
`analysis/utils/axes.py` (`decompose_slug`, `STRATEGY_COMPLEXITY_ORDER`). Outputs under
`{output_base}/03_Analysis/method_significance/`. Records the acting library versions
(`statsmodels`, `scikit-posthocs`, `scipy`) in the JSON `metadata` for provenance/reproducibility.

---

## Implementation Plan

### Phase 1: Shared stats primitives
**Goal:** Add the reusable, individually-tested statistical building blocks.

**Started:** 2026-07-13T19:44:00+00:00
**Completed:** 2026-07-13T19:53:55+00:00

- [x] `friedman_test(blocks)` — wrap `scipy.stats.friedmanchisquare`; add Iman–Davenport F and
      Kendall's W; explicit degenerate-input handling (`<2` groups/blocks, ties, all-equal).
- [x] `page_trend_test(blocks, order)` — Page's L for ordered alternatives (in-house; not in the
      libs); normal-approx p-value.
- [x] `nemenyi_posthoc(matrix)` — via `scikit_posthocs.posthoc_nemenyi_friedman`; return the pairwise
      p-matrix + critical-difference value for the CD diagram.
- [x] `benjamini_hochberg(pvals)` — via `statsmodels.stats.multitest.multipletests(method="fdr_bh")`.
- [x] `cliffs_delta(a, b)` — in-house ordinal effect size with magnitude label.
- [x] `mixed_logit_interaction(frame)` — `statsmodels` `MixedLM` fit of
      `logit(TV) ~ C(model) * method_rank + (1|category)`; return interaction Wald test + η².
- [x] Lazy imports with a clear "install `.[analysis]`" error for the two new libs.

**Files Modified:** `src/population_synthetic/analysis/utils/stats_tests.py`;
`pyproject.toml` (`[analysis]` extra += `scikit-posthocs`, `statsmodels`).

**Dependencies:** None.

### Phase 2: Builder
**Goal:** Assemble the per-country analysis from `ComboPerformance` records.

**Started:** 2026-07-13T19:59:38+00:00
**Completed:** 2026-07-13T20:04:47+00:00

- [x] Load + filter to the 5 ordered strategies; build the TV[attr][model][method] structure;
      distinguish absent cells (NaN attribute) from real zeros; log dropped combos.
- [x] Per attribute: Page L (+linear/quadratic contrast, sign), Friedman (χ²/F, Kendall's W);
      BH-correct each family across attributes.
- [x] Per (attribute, model): descriptive slope, Spearman ρ, Δ(method5−method1) — flagged n=5.
- [x] Overall block: Demšar model comparison (Friedman → Nemenyi → CD inputs), Page L method trend,
      `mixed_logit_interaction`, η² decomposition, caveats (n=1, pseudo-replication, dependence).
- [x] `write_*_json` / `write_*_csv` (one row per attribute: method L/p, model χ²/p, BH-adjusted,
      dominant factor).

**Files Modified:** `src/population_synthetic/analysis/method_significance/builder.py`, `__init__.py`.

**Dependencies:** Phase 1.

### Phase 3: Charts, script, GUI, docs
**Goal:** Make it runnable end-to-end and documented.

**Started:** 2026-07-13T20:05:00+00:00
**Completed:** 2026-07-13T20:14:21+00:00

- [x] `charts.py`: per-attribute TV(method) trend lines faceted by model; slope heatmap
      (attribute × model); CD diagram (models); factor-dominance bar (η²). Significance annotated
      from the **BH-corrected** p-values only.
- [x] `scripts/analyze/analyze_method_significance.py` — CLI (`--country/--model/--strategy/--slug`,
      `--output-base`, `--force`, `--strict`, `--no-charts`).
- [x] Optional GUI action mirroring "Model Performance" (`min_combos: 2`), added to
      `config/gui/flows/analysis_workflow.yaml` (`method_significance` task, `dispatch: slugs`).
- [x] Docs: extend `docs/architecture/comparison-metrics.md` & `sub-packages.md` &
      `commands.md`; mark the task done in `docs/development/model-method-significance-recap.md`.

**Files Modified:** `charts.py`, the script, `config/gui/flows/analysis_workflow.yaml`, the doc files,
`CLAUDE.md`. Also added `avg_ranks` to the builder's overall model-comparison block (so the CD
diagram renders strictly downstream of the computed ranks). Note: the GUI config lives at
`config/gui/flows/analysis_workflow.yaml`, not `config/gui/launcher.yaml` as sketched above.

**Dependencies:** Phase 2.

---

## Testing Plan

### Unit Tests
- [x] Each primitive against a hand-computed / textbook case, floats via `pytest.approx`:
      `page_trend_test`, `friedman_test`, `cliffs_delta` (in-house) validated against known values;
      `nemenyi_posthoc`, `benjamini_hochberg`, `mixed_logit_interaction` pinned to the library output.
      (`tests/test_stats_tests_significance.py`, 20 tests.)
- [x] Degenerate inputs: `<2` models/attributes, all-equal TV (zero variance), ties, NaN attributes.

### Integration Tests
- [x] Fixture grid (mirror `tests/_performance_fixtures.py`) with a **planted monotonic method
      trend** in one attribute and a **null trend** in another → assert Page L flags the first, BH
      keeps the null non-significant, and the builder JSON/CSV shape matches.
      (`tests/test_method_significance.py`, 11 tests.)

### Manual Verification
- [x] Real run `--country swedish` on existing reports (39 combos, external OneDrive output_base):
      wrote JSON/CSV + slope heatmap, CD diagram, factor-dominance bar and 15 trend facets;
      overall direction confirmed (method/strategy dominates model), CD diagram + slope heatmap
      render.
- [x] `ruff check src/` clean; full `pytest` green.

### Edge Cases
- [ ] A country/attribute with fewer than the full 5 methods executed (unbalanced grid) → Skillings–
      Mack fallback or documented skip, logged not silently dropped.
- [ ] Exact-0 / exact-1 TV values under the logit squeeze.

---

## Documentation Plan

- [x] `docs/architecture/comparison-metrics.md` — the new per-category significance metrics.
- [x] `docs/architecture/sub-packages.md` + `commands.md` — the new subpackage and command.
- [x] `CLAUDE.md` — one line in the analysis-family description.
- [x] `docs/development/model-method-significance-recap.md` — mark the open task done, link the plan.

---

## Rollback Plan

Purely additive and downstream-only (reads existing reports, writes a new output folder). To revert:
delete the `method_significance/` subpackage, the script, the GUI action, and the `[analysis]` extra
additions, and drop the new `03_Analysis/method_significance/` outputs. No data migration, no changes
to fidelity/mapping, no breaking changes to existing artifacts.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Over-claiming per-category interaction significance despite n=1 | Med | High | Hard rule: per-category interaction is descriptive only; no p-value emitted; caveats block in JSON |
| `statsmodels` MixedLM convergence issues on sparse/unbalanced grids | Med | Med | Guard + fall back to η² rank-decomposition; record non-convergence, don't emit a bogus p |
| Re-implemented stats subtly wrong (silent wrong number) | Med | High | Pin every primitive to scipy/statsmodels/scikit-posthocs on fixtures; approx float asserts |
| Library-version drift changes results | Low | Med | Record acting library versions in JSON metadata (provenance) |
| Unbalanced grid (missing combos) breaks blocked tests | Med | Med | Distinguish absent vs zero; Skillings–Mack fallback or logged skip; `--strict` toggle |

---

## References

- Related (completed) plan: `docs/development/plans/completed/model-performance-comparison.md`
- Thread recap: `docs/development/model-method-significance-recap.md`
- Demšar 2006 (JMLR 7:1-30); García & Herrera 2008/2010 (Iman–Davenport, post-hoc); Ferrari &
  Cribari-Neto 2004 (beta regression); Warton & Hui 2011 (prefer logit over arcsine); Page's L /
  Jonckheere trend tests; Cliff's δ.
- Engineering guides: `~/.claude/knowledge/data-pipeline-engineering/03-statistical-and-scientific-software.md`

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- CLAUDE.md
- config/gui/flows/analysis_workflow.yaml
- docs/architecture/commands.md
- docs/architecture/comparison-metrics.md
- docs/architecture/sub-packages.md
- docs/development/model-method-significance-recap.md
- docs/development/plans/active/per-category-method-model-significance.md
- pyproject.toml
- scripts/analyze/analyze_method_significance.py
- src/population_synthetic/analysis/method_significance/__init__.py
- src/population_synthetic/analysis/method_significance/builder.py
- src/population_synthetic/analysis/method_significance/charts.py
- src/population_synthetic/analysis/utils/stats_tests.py
- tests/test_method_significance.py
- tests/test_method_significance_charts.py
- tests/test_stats_tests_significance.py
- tests/test_workflow_state.py

<!-- NOTE: the three tests/test_*_significance*.py files are git-ignored by the repo's `/tests`
     rule; they must be staged with `git add -f`. `docs/architecture/comparison-metrics.md` also
     carried a pre-existing uncommitted edit from before this branch — staging the whole file will
     include it. -->
