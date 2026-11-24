# Plan: Repeated-measures ANOVA assumption checks

**Date:** 2026-09-16
**Author:** Basil
**Status:** Completed
**Base Branch:** `feature/method-pair-significance-grids`
**Branch:** `feature/rm-anova-assumption-checks`

---

## Overview

Every `method_comparison` panel in `method_significance` reports a one-way repeated-measures
ANOVA (models as blocks, methods as treatments) and Holm-corrected paired t-tests. Neither
test's assumptions are checked anywhere: `rm_anova_within`'s docstring says outright that
sphericity is assumed and not tested. This plan adds an `assumptions` block next to each
panel's `omnibus`, so the headline F and the pairwise t verdicts carry their own diagnostics.

## Goals

### In Scope

1. A new primitive `stats_tests.rm_anova_assumptions(blocks, *, labels, alpha)` computing:
   - residual normality (`e_ij = y_ij - row mean - column mean + grand mean`): Shapiro-Wilk on
     all residuals, Lilliefors-corrected KS (statsmodels, already in the `[analysis]` extra),
     per-method Shapiro-Wilk on the residuals, and the worst method (smallest p);
   - paired-difference normality per method pair: Shapiro-Wilk W, p, Holm across pairs;
   - sphericity: Mauchly's W / chi2 / df / p on orthonormal Helmert contrasts; Greenhouse-Geisser
     epsilon, Huynh-Feldt epsilon (the original 1976 formula; uncapped and capped at 1) and the
     lower bound `1/(k-1)`; corrected df and p for GG, capped HF and the lower bound;
     `k = 2` handled explicitly (epsilon = 1, no Mauchly test);
   - variance (ddof = 1) of each pairwise difference;
   - Wilcoxon signed-rank per pair (scipy's `method="auto"`: exact for small n without zero
     differences), Holm across pairs, and `verdict_differs_from_t` at *alpha*.
2. `builder._method_panel` emits `assumptions` on every panel, degenerate panels included
   (skeleton + note), with *alpha* = `significance_cutoff(star_thresholds)` from
   `config/analysis/method_significance/comparison.json` -- the same config-sourced cutoff that
   already defines "significant" for the pair figures. No new config key, no in-code default.
3. `{country}_method_comparison.csv` gains two trailing columns, `omnibus_gg_epsilon` and
   `omnibus_p_gg`. No existing column is renamed or moved.
4. Unit tests reproducing the hand-computed reference values on the 10 x 5 overall grid, plus a
   `k = 2` case and degenerate/insufficient cases.
5. Docs: the `method_comparison` contract in `docs/architecture/sub-packages.md` and
   `docs/architecture/comparison-metrics.md`.

### Out of Scope

- **Outlier detection.** There is no config home for an outlier rule (IQR multiplier, |z| cut),
  and inventing one in code would violate the no-in-code-default rule. Skipped.
- **Any change to the headline test or the figures.** The assumptions are reported, not acted on:
  no automatic switch to a corrected p or to Wilcoxon, and no `charts.py` / presentation change.

## Success Criteria

- Overall reference grid reproduces: F(4,36) = 189.487, p = 1.194e-23; residual SW W = 0.983,
  p = 0.670; Lilliefors D = 0.092, p = 0.373; worst method C W = 0.887, p = 0.155; A-D difference
  SW W = 0.843, p = 0.048 (Holm 0.483); Mauchly W = 0.506, chi2 = 5.05, df = 9, p = 0.830;
  GG epsilon 0.725 -> p = 1.06e-17; HF uncapped 1.107; lower-bound p = 2.37e-7; only C-D has a
  Wilcoxon verdict that differs from t (Holm p = 0.0547).
- `ruff check src/` clean; method_significance and stats tests pass.

## Implementation Plan

### Phase 1: Primitive
`analysis/utils/stats_tests.py::rm_anova_assumptions` + tests in
`tests/test_rm_anova_assumptions.py`.

### Phase 2: Wiring
`builder._method_panel(alpha=...)`, `_method_comparison` passes the config cutoff; CSV columns in
`scripts/analyze/analyze_method_significance.py`.

### Phase 3: Docs
Contract description in the architecture wiki.
