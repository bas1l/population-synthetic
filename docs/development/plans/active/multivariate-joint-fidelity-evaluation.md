# Plan: Multivariate / joint fidelity evaluation

**Date:** 2026-07-02
**Author:** Basil (with Claude)
**Status:** In Progress
**Base Branch:** `dev`
**Branch:** `feature/multivariate-joint-fidelity`

---

## Overview

Add multivariate (joint) fidelity metrics to the comparison stack so the benchmark measures not just
per-attribute marginals but whether the *interactions* between attributes are reproduced. This closes
the one axis where the closest prior work — SSDataBench (Xie et al., *Evaluating the statistical
realism of LLM-generated social science data*, PNAS 2026) — currently goes deeper than us, and directly
answers the "beyond marginal distributions" critique (Williams et al. 2026). We add four metrics:
a classifier two-sample test (C2ST), a pairwise Cramér's V association-fidelity matrix, joint fidelity
validated against API-grounded reference joints, and a rare/impossible k-way combination rate.

## Problem Statement

The evaluator (`analysis/comparison/evaluator.py`) scores 15 marginal distributions plus a token
multivariate check: joint chi-squared on **3 hand-picked pairs** and one coherence triple
(age×education×employment). Marginal similarity can be high while the joint structure is wrong (a model
can get every marginal right and still pair 70-year-olds with "student" at the wrong rate). SSDataBench
scores five pattern types including bi-/multivariate structure across six domains, so a reviewer can say
it evaluates realism more deeply than we do. Without a multivariate story, our headline ("strategy
dominates model") is also under-tested: the sampling strategy may restore marginals while leaving joint
structure broken, and we currently cannot see that. This matters because the project's downstream goal
(privacy-safe populations for clinical/epidemiological simulation) depends on joint realism, not just
marginals.

## Goals

### In Scope
1. **C2ST (classifier two-sample test):** a single per-combo discriminability score (ROC-AUC, 0.5 =
   indistinguishable joint, 1.0 = trivially separable) over all 15 attributes one-hot encoded.
2. **Pairwise association-fidelity matrix:** Cramér's V for every attribute pair in the real and
   synthetic populations; report per-pair |ΔV|, the mean, and the Frobenius norm of the difference
   matrix, plus a heatmap.
3. **Grounded joint fidelity:** joint total-variation distance per attribute pair, computed against the
   real population's empirical joint, with each pair **labelled** API-grounded vs. reference-marginal
   (from the SCB distribution audit) so we never validate against a joint the reference itself faked.
4. **Rare/impossible k-way combination rate:** fraction of synthetic individuals whose k-way attribute
   tuple has zero (impossible) or below-threshold (rare) support in the real population — a
   generalisation of the existing coherence check to configurable attribute sets and k.
5. **Wire the new metrics through** report JSON → performance loader/aggregation → one new figure, as
   *reported/secondary* metrics (the primary TV-similarity ranking is unchanged).
6. Regenerate the Swedish outputs and add the multivariate results to the paper
   (`docs/paper/sections/results.md`, `discussion.md`, `figures.md`).

### Out of Scope
- **Life-event / temporal sequence fidelity** — the populations are cross-sectional national snapshots
  with no temporal dimension; sequence metrics (which SSDataBench has because its data is longitudinal)
  are inapplicable by construction and will be named as inherent scope, not a gap.
- **Changing the primary leaderboard ranking metric** — TV-similarity stays the headline; multivariate
  metrics are added columns/blocks, not a new rank key (avoids disrupting the paper's central result).
- **Replicate runs / seeding** — tracked separately in the model-significance thread; not this plan.
- **Norway/Italy** — implement country-agnostically, but only regenerate/report Sweden here.

## Success Criteria

- [x] `StatisticalEvaluator.generate_report()` emits a new top-level `multivariate` block with
      `c2st`, `association` (Cramér's V), `joint_fidelity` (per-pair joint TV + grounded flag), and
      `combination_plausibility` sub-blocks.
- [x] The performance loader consumes the new block without breaking existing reports (additive; old
      reports still load, missing block tolerated).
- [x] A Cramér's V association-fidelity heatmap and a C2ST-vs-TV-similarity summary are generated for
      the 35 Swedish combos.
- [x] New unit tests pass; `pytest` green (233 passed); `ruff check src/` clean.
- [x] The paper's Results/Discussion report the multivariate findings, and the Related Work "SSDataBench
      differentiator" is updated to "we now match multivariate depth AND add census grounding + strategy
      test."
- [x] Every new metric degrades gracefully (NaN/empty) for tiny/failed synthetic populations and is
      documented as honestly as the existing metrics (smoothing, thresholds, grounded-pair labelling).

---

## Technical Design

### Approach

Extend the existing `StatisticalEvaluator` rather than build a parallel evaluator, mirroring the current
`compute_marginals` / `compute_joint_chi_sq` / `compute_coherence` structure. Add a
`compute_multivariate()` method returning a `multivariate` dict, assembled into the report alongside the
existing blocks. Reuse `attr_value()` (which already derives `age_group` from raw age) and
`self.scheme` (attributes + categories). New cross-attribute tuning (which pairs are API-grounded, the
k-way combination attribute sets, C2ST config) goes into the per-country analysis config
`config/analysis/comparison/{country}.json` — the same fail-loud, no-in-code-default source the scheme
already uses for `joint_pairs`/`coherence_attributes`.

**Metric definitions**

- **C2ST:** one-hot encode the 15 canonical attributes for both populations (categories fixed by
  `scheme.categories`, so encoding is stable and synthetic-only values map to an "other"/all-zero
  column). Label real = 0, synthetic = 1. Stratified k-fold cross-validated classifier; report mean
  held-out ROC-AUC and a permutation-based p-value. Because real n=10,000 ≫ synthetic n=100, **balance
  by subsampling the real population to n_synthetic per fold (repeated)** so AUC is not inflated by class
  imbalance; report the balancing explicitly.
- **Cramér's V:** for each attribute pair, χ² on the crosstab → V = √(χ²/(n·min(r−1,c−1))) with the
  bias correction (Bergsma). Compute for real and synthetic separately; the fidelity metric is |V_real −
  V_syn| per pair, plus mean and Frobenius norm over the 105 pairs.
- **Grounded joint TV:** per pair, joint TV = ½·Σ|p_real(x,y) − p_syn(x,y)| over the cross-tab cells;
  attach `grounded: true|false` from config (API-conditioned pairs vs. reference-marginal-product pairs,
  per `docs/scb_population_distribution_analysis.md`). Report both, but the paper leans on grounded pairs.
- **Combination plausibility:** generalise `compute_coherence` to accept a list of attribute-tuples and
  a k; report, per configured tuple set, the fraction impossible (zero real support) and rare (below
  threshold), reusing the existing joint-probability-table logic.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **C2ST via scikit-learn** (`HistGradientBoostingClassifier` or `LogisticRegression`, CV AUC) | Standard synthetic-data fidelity metric; captures all interactions; interpretable single number | Adds a heavyweight dependency not currently installed | **Chosen**, behind an optional `[analysis]` extra (core install stays lean) |
| **Hand-rolled MMD / energy-distance permutation test** (numpy/scipy only) | Zero new deps; matches the project's hand-rolled-Dunn precedent; gives a p-value | Less interpretable than AUC; kernel/bandwidth choice on one-hot data is fiddly; less familiar to reviewers | **Kept as fallback** if adding sklearn is rejected; ship as `c2st.method="mmd"` alternative |
| Add a brand-new `multivariate_evaluator.py` module | Clean separation | Duplicates population/scheme plumbing; two places to keep in sync | Rejected — extend `StatisticalEvaluator` |
| Rank the leaderboard by a composite marginal+joint score | One number | Changes the paper's headline result mid-stream; composite scores are gameable (Du & Li 2025) | Rejected — keep multivariate as reported/secondary |
| Validate joints for all pairs equally | Simpler | Overclaims: some reference joints are marginal-product (forced independence), so "fidelity" there is meaningless | Rejected — label grounded vs. not |

### Architecture Changes

- **Modified:** `analysis/comparison/evaluator.py` — add `compute_multivariate()` + helpers
  (`_cramers_v`, `_c2st`, `_joint_tv`, generalised combination check); add `multivariate` to
  `generate_report()`; extend `write_csv_summary` (or add a second CSV) with per-pair association rows.
- **New:** `analysis/comparison/multivariate.py` — pure metric functions (Cramér's V, one-hot encoding,
  C2ST driver, joint TV) so they are unit-testable without a full population; evaluator calls them.
- **Modified:** `config/analysis/comparison/scb.json` (and `istat.json`) — add `grounded_joint_pairs`,
  `combination_checks` (list of {attributes, k, threshold}), and optional `c2st` config
  (folds, method, seed). Fail-loud on malformed, tolerate absent with documented defaults.
- **Modified:** `analysis/comparison/scheme.py` — extend `ComparisonScheme` + `_load_analysis_config`
  to carry the new fields (backward compatible: default empty/None).
- **Modified:** `analysis/comparison/charts.py` — add `plot_association_heatmap()` and a
  `plot_c2st_vs_tv()` scatter.
- **Modified:** `analysis/performance/loader.py` + `builder.py` — carry optional per-combo `c2st_auc`
  and `mean_delta_v` into `ComboPerformance`; tolerate reports without the block.
- **Modified:** `pyproject.toml` — optional `[analysis]` extra with `scikit-learn`.
- **Modified:** `scripts/analyze/compare_pipeline_to_scb.py` / `compare_all_pipelines.py` — no signature
  change; they call `generate_report()` and write whatever it returns, so new blocks flow through. Add a
  `--multivariate/--no-multivariate` flag (default on) to allow skipping the (heavier) C2ST.

---

## Implementation Plan

### Phase 1: Pure metric functions + tests
**Goal:** Correct, dependency-light metric primitives, unit-tested in isolation.
**Started:** 2026-07-02
**Completed:** 2026-07-02

- [x] Task 1.1 — Create `analysis/comparison/multivariate.py` with `one_hot_encode(individuals, scheme)`,
      `cramers_v(counts_table)` (bias-corrected), `association_matrix(individuals, attrs, scheme)`,
      `joint_tv(individuals_a, individuals_b, attr_x, attr_y, scheme)`.
- [x] Task 1.2 — Add `c2st(X_real, X_syn, method, folds, seed)` with a scikit-learn backend and an
      MMD/energy fallback; return `{auc, p_value, method, balanced_n}`.
- [x] Task 1.3 — Unit tests: identical populations → V-delta ≈ 0, joint TV ≈ 0, C2ST AUC ≈ 0.5;
      disjoint populations → AUC ≈ 1.0; known small hand-built crosstab → exact Cramér's V.

**Files Modified:** `src/population_synthetic/analysis/comparison/multivariate.py` (new);
`tests/test_multivariate.py` (new).
**Dependencies:** None.

### Phase 2: Config + scheme wiring
**Goal:** New cross-attribute tuning is config-sourced and fail-loud.

**Started:** 2026-07-02
**Completed:** 2026-07-02

- [x] Task 2.1 — Add `grounded_joint_pairs`, `combination_checks`, `c2st` to
      `config/analysis/comparison/scb.json` (and `istat.json`); populate `grounded_joint_pairs` from the
      SCB distribution audit (`docs/scb_population_distribution_analysis.md`: the 5/14 API-identical
      pairs are grounded; education→employment etc. are not).
- [x] Task 2.2 — Extend `ComparisonScheme` + `_load_analysis_config`/`_scheme_from_legacy` to carry the
      new fields (default empty, backward compatible).
- [x] Task 2.3 — Tests: malformed config fails loudly; absent optional keys default cleanly.

**Config shapes chosen (Phase 3 consumes these).**
`grounded_joint_pairs`: JSON list of objects `{"pair": [attr_x, attr_y], "grounded": true|false, "basis": str}`
(`basis` optional). Grounded=true iff the real joint over the pair is a real API conditional cross-tab.
SCB grounded=true pairs (derived from the 5 "NO DIFFERENCE"/API-identical audit fields — birth_location
and region are marginal so contribute no conditional joint): `[age_group,biological_sex]` (§1),
`[age_group,civil_status]` & `[biological_sex,civil_status]` (§8), `[age_group,income_source]` &
`[employment_status,income_source]` (§13). SCB grounded=false (the currently-evaluated `joint_pairs`,
kept so the paper does not over-claim): `[age_group,education_level]` (§2, sex pooled),
`[age_group,employment_status]` (§3), `[education_level,employment_status]` (§3, forced independence).
ISTAT has no per-field grounding audit and no `income_source` attribute, so its `grounded_joint_pairs` is
`[]` (empty, honest — not malformed). `combination_checks`: list of
`{"attributes": [...], "k": int, "threshold": float}` (both configs seed the legacy
age×education×employment triple, k=3, threshold=0.001). `c2st`: `{"folds": 5, "method": "sklearn", "seed": 42}`.

Scheme fields (parsed into frozen dataclasses): `scheme.grounded_joint_pairs: tuple[GroundedJointPair, ...]`
(`.pair: tuple[str,str]`, `.grounded: bool`, `.basis: str`), `scheme.combination_checks: tuple[CombinationCheck, ...]`
(`.attributes: tuple[str,...]`, `.k: int`, `.threshold: float`), `scheme.c2st_config: C2STConfig | None`
(`.folds: int`, `.method: str`, `.seed: int`). Absent key → empty tuple / `None`; present-but-malformed → raise.

**Files Modified:** `config/analysis/comparison/{scb,istat}.json`;
`src/population_synthetic/analysis/comparison/scheme.py`; `tests/test_stats.py` or new scheme test.
**Dependencies:** None (parallel to Phase 1).

### Phase 3: Evaluator integration + report block
**Goal:** `generate_report()` emits the `multivariate` block end to end.

**Started:** 2026-07-02
**Completed:** 2026-07-02

- [x] Task 3.1 — Add `compute_multivariate()` to `StatisticalEvaluator` calling the Phase-1 primitives
      with the Phase-2 scheme fields; assemble `c2st` / `association` / `joint_fidelity` /
      `combination_plausibility` sub-blocks.
- [x] Task 3.2 — Add `multivariate` to `generate_report()`; extend `print_summary` with a short
      multivariate section; add per-pair association rows to a CSV (new `{run}_association.csv`).
- [x] Task 3.3 — Graceful degradation for tiny n_b (NaN AUC, empty flagged lists) mirroring the
      existing `n_b < 5` guard.
- [x] Task 3.4 — Tests on a small synthetic fixture population end to end.

**Files Modified:** `src/population_synthetic/analysis/comparison/evaluator.py`;
`tests/test_evaluator*.py` / `tests/test_stats.py`.
**Dependencies:** Phases 1–2.

### Phase 4: Performance + charts
**Goal:** Per-combo aggregation and the two figures.

**Started:** 2026-07-02
**Completed:** 2026-07-02

- [x] Task 4.1 — Carry optional `c2st_auc` and `mean_delta_v` into `ComboPerformance`
      (`performance/loader.py`), tolerate reports lacking the block; surface both in
      `swedish_performance.{json,csv}` as extra columns (ranking unchanged).
- [x] Task 4.2 — `plot_association_heatmap()` (per-combo |ΔV| grid) and `plot_c2st_vs_tv()` (AUC vs mean
      TV-similarity scatter, colour = strategy) in `charts.py`; load the `dataviz` skill first.
      The association heatmap lives in `analysis/comparison/charts.py` (a single-comparison artifact) and
      the C2ST-vs-TV scatter in `analysis/performance/charts.py` (a cross-combo artifact), each wired into
      its natural call site (`compare_pipeline_to_scb.py` and `compare_model_performance.py`).
- [x] Task 4.3 — `pyproject.toml` optional `[analysis]` extra with `scikit-learn`; document in the
      quick-start (`CLAUDE.md` and `README.md`).

**Files Modified:** `src/population_synthetic/analysis/performance/{loader,builder,charts}.py`;
`src/population_synthetic/analysis/comparison/charts.py`; `pyproject.toml`.
**Dependencies:** Phase 3.

### Phase 5: Regenerate + fold into the paper
**Goal:** Swedish multivariate results computed and written into the manuscript.

**Started:** 2026-07-02
**Completed:** 2026-07-02

- [x] Task 5.1 — Installed the `[analysis]` extra (scikit-learn 1.7.2), re-ran `map_populations.py`,
      then `compare_all_pipelines.py --country swedish` (multivariate is default-on; no `--multivariate`
      flag exists) and `compare_model_performance.py --country swedish` for the 35 Swedish combos. C2ST
      ran on the **scikit-learn** backend (`method="sklearn"`, `balanced_n=100`). All 35 reports gained
      the `multivariate` block; `swedish_performance.{json,csv}` gained populated `c2st_auc`/`mean_delta_v`.
- [x] Task 5.2 — Added a "Multivariate fidelity" subsection to `results.md` (+ a metric-defining
      paragraph to `methods.md`) and a paragraph to `discussion.md`; added Figures 9 (`F9_c2st_vs_tv.png`)
      and 10 (`F10_association_heatmap.png`) to `figures.md`; updated the SSDataBench differentiator in
      both `sections/related-work.md` and `sources/related-work.md`.
- [x] Task 5.3 — Re-assembled `manuscript.md` (surgical section-block updates; the folder assembles by
      hand, no script) and ran the `humanizer_academic` check on the new prose (zero em dashes, softened
      two negative-parallelism constructions). The manuscript source lives in OneDrive
      (`…/Gauss/04_Dissemination/Manuscripts/40_llm-population-fidelity-benchmark/drafting-source/`, the
      relocated `docs/paper/`, gitignored). NOTE: the camera-ready deliverable is the LaTeX build
      (`2026-07-02_TMLR/`); the `.tex` sources were **not** updated here and must be re-synced from these
      markdown edits before recompiling `main.pdf`.

**Files Modified:** `docs/paper/sections/{results,discussion,figures,related-work}.md`;
`docs/paper/sources/related-work.md`; `docs/paper/manuscript.md` (regenerated).
**Dependencies:** Phase 4.

---

## Testing Plan

### Unit Tests
- [x] Cramér's V exact value on a hand-built crosstab; bias correction reduces V for sparse tables.
- [x] Joint TV = 0 for identical populations, = 1 for disjoint supports.
- [x] C2ST AUC ≈ 0.5 for two samples from the same distribution; ≈ 1.0 for clearly separable ones;
      deterministic under fixed seed.
- [x] One-hot encoder maps synthetic-only categories to the "other" column, never crashes.

### Integration Tests
- [x] `generate_report()` on a fixture emits a well-formed `multivariate` block with all four
      sub-blocks; JSON round-trips.
- [x] `performance/loader.py` loads both a new report (with block) and an old report (without) — no
      regression on the existing 35-combo path.

### Manual Verification
- [x] Run the full Swedish pipeline; confirm the association heatmap and C2ST scatter render and that
      the winning strategy's C2ST AUC is lower (more realistic joint) than the picking strategies — the
      multivariate analogue of the marginal headline (this is the key scientific check). **Confirmed:**
      the winning `all_generate_evaluate_random_pick` strategy has the lowest mean C2ST AUC (0.919) of
      all five strategies; every picking/deliberation strategy sits at ≈0.994–0.995. Its best runs reach
      0.841 (Sonnet), 0.858 (Opus), 0.881 (Haiku). It also has the lowest association |ΔV| (0.115) and
      lowest grounded joint-TV (0.264).
- [x] Confirm grounded vs. non-grounded joint pairs are labelled correctly against the audit doc.
      **Confirmed:** `scb.json` labels the 5 API-identical pairs (age×sex, age/sex×civil_status,
      age/employment×income_source) grounded=true and the 3 conditioning-lost pairs
      (age×education, age×employment, education×employment) grounded=false, matching audit §1/§8/§13 vs §2/§3.

### Edge Cases
- [x] Synthetic population of 0/6/16 personas (the failed runs) → NaN AUC, empty flags, no crash.
- [ ] An attribute with a single observed category → Cramér's V defined (0) not divide-by-zero.
- [ ] All-synthetic-values-unmapped attribute → encoded as all-"other", C2ST still runs.

---

## Documentation Plan

- [x] Update `docs/architecture/comparison-mapping.md` with the multivariate metrics + config keys.
- [ ] Update `CLAUDE.md` "Full comparison output" invariant note if the emitted artefact set changes.
      (Left unchanged intentionally: the multivariate block is a *secondary* artifact, not part of the
      hard "every artifact" invariant, so folding it into that rule would over-commit the contract.)
- [x] Update `docs/scb_population_and_comparison.md` metric list.
- [x] Note the optional `[analysis]` extra in the quick-start (`README`/`CLAUDE.md`). (Done in Phase 4.)
- [x] Cross-link `docs/scb_population_distribution_analysis.md` from the grounded-pairs config.
      (The `scb.json` `basis` strings cite the audit sections; the SCB comparison doc now links it.)

## Rollback Plan

1. The change is additive: new report keys, new optional config, new optional dependency. To revert,
   drop the `multivariate` block from `generate_report()` (one line) — existing marginal/joint/coherence
   outputs and the leaderboard are untouched.
2. Data: no migrations. Old comparison reports remain valid (loader tolerates the missing block).
   Regenerated reports simply gain a block; delete and re-run the pre-change pipeline to restore.
3. Rollback procedure: revert the feature branch merge; the optional `[analysis]` extra is unused by the
   core install so no environment breakage.

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| New scikit-learn dependency unwanted in core env | Med | Med | Optional `[analysis]` extra; MMD/energy fallback needs only numpy/scipy |
| C2ST AUC inflated by real n ≫ synthetic n | High | High | Subsample real to n_synthetic per fold, repeat, report balancing; validate AUC≈0.5 on same-dist test |
| Reference joints are partly faked (forced independence) → misleading "joint fidelity" | High | High | Label grounded vs. non-grounded pairs from the audit; paper leans on grounded pairs only |
| Performance loader breaks on the new block | Low | High | Additive keys only; explicit test that old reports still load |
| Multivariate result contradicts the marginal headline (sampling wins marginals but not joints) | Med | Med | This is a *finding*, not a failure — report honestly; it strengthens the paper either way |
| 105-pair association matrix noisy at n=100 | Med | Low | Report mean/Frobenius with a caveat; emphasise grounded pairs and C2ST as the robust summaries |

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 (primitives + tests) | ~0.5 day | None |
| Phase 2 (config + scheme) | ~0.5 day | None |
| Phase 3 (evaluator + report) | ~1 day | Phases 1–2 |
| Phase 4 (performance + charts) | ~0.5 day | Phase 3 |
| Phase 5 (regenerate + paper) | ~0.5 day | Phase 4 |

## References

- Paper drafting effort: `docs/paper/` (esp. `sources/related-work.md` §"Closest prior work").
- Closest prior work: Xie et al., *Evaluating the statistical realism of LLM-generated social science
  data*, PNAS 2026 (10.1073/pnas.2538145123); Williams et al., *Beyond Marginal Distributions*, 2026.
- Grounded-joint audit: `docs/scb_population_distribution_analysis.md` (+ verification doc).
- Existing evaluator: `src/population_synthetic/analysis/comparison/evaluator.py`;
  scheme/config: `scheme.py`, `config/analysis/comparison/scb.json`.
- Related open thread: `docs/development/model-method-significance-recap.md`.

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- CLAUDE.md
- README.md
- config/analysis/comparison/istat.json
- config/analysis/comparison/scb.json
- docs/architecture/comparison-mapping.md
- docs/development/plans/active/multivariate-joint-fidelity-evaluation.md
- docs/scb_population_and_comparison.md
- pyproject.toml
- scripts/analyze/compare_all_pipelines.py
- scripts/analyze/compare_model_performance.py
- scripts/analyze/compare_pipeline_to_scb.py
- src/population_synthetic/analysis/comparison/charts.py
- src/population_synthetic/analysis/comparison/evaluator.py
- src/population_synthetic/analysis/comparison/multivariate.py
- src/population_synthetic/analysis/comparison/scheme.py
- src/population_synthetic/analysis/performance/builder.py
- src/population_synthetic/analysis/performance/charts.py
- src/population_synthetic/analysis/performance/loader.py
- tests/_performance_fixtures.py
- tests/test_evaluator.py
- tests/test_multivariate.py
- tests/test_multivariate_charts.py
- tests/test_performance_builder.py
- tests/test_performance_loader.py
- tests/test_scheme_index.py
