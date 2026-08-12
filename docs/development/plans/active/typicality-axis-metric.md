# Plan: A Self-Contained Typicality Axis for `realism_ranking`

**Date:** 2026-08-11
**Author:** Basil
**Status:** In Progress
**Base Branch:** `dev`
**Branch:** `feature/typicality-axis-metric`

> **Base-branch note.** `realism_ranking` does not exist on `dev` yet: it arrives via PR #10
> (`feature/split-persona-realism-ranking`) and `feature/severity-driver-attribution` on top of it.
> This branch must be cut **after both land on `dev`**. If it is started earlier, base it on
> `feature/severity-driver-attribution` and rebase.

---

## Overview

The LLM judge scores every persona on an integer 0-10 `typicality` scale, but the ranking task
consumes that score only as **Axis B** — a *distance* from the SCB reference's dispersion, where SCB
is the target rather than a competitor. This plan adds a **self-contained per-competitor typicality
statistic**: one number computed from a combination's own scores alone, published as a model x method
heatmap beside the existing impossibility and severity grids, and as a methods-on-x figure with SCB
drawn as its own reference. Direction is supplied by the *rendering* (a diverging ramp centred on
SCB's value), never by the statistic, so the cell stays reference-free and byte-reproducible in
isolation.

## Problem Statement

Typicality is the richest signal the judge produces and the pipeline currently exposes it only as a
distance. Three consequences:

1. **The number cannot be read on its own.** `axis_b.dispersion_contrast` publishes
   `abs(measure - real_measure)`. The absolute value is deliberate (ADR: "an absolute distance so
   collapsing is penalised exactly as much as over-spreading"), but it discards the **sign**, so a
   mode-collapsed competitor and an over-dispersed one are indistinguishable in the published number.
2. **There is no typicality figure.** The severity and impossibility dimensions each have a
   model x method heatmap; typicality has none. The one place it appears is the headline map's
   y-axis, as a distance.
3. **The measured finding has no artifact.** On `swedish_02` the synthetic populations are judged
   *far more ordinary* than the real register population (SCB mean 4.71, synthetic bulk 6-9; 47% of
   all synthetic scores are exactly 9; one combination is at 100% level-9 with variance 0.00). That is
   mode collapse measured directly, and it is currently reconstructable only by hand.

## Goals

### In Scope

1. One **self-contained** typicality statistic per competitor, computed from that competitor's own
   per-persona scores, with a seeded percentile bootstrap CI and its denominator.
2. A **model x method heatmap** of that statistic, on a **diverging** colormap centred at the SCB
   value, with `n` printed in every cell, SCB drawn as the existing full-width real-population band.
3. A **methods-on-x figure**: methods in complexity order on x, the statistic on y, per-model marks,
   SCB as a horizontal reference.
4. The **11-bin typicality histogram** kept as the primary published object, per competitor, with the
   scalar as a summary of it rather than a replacement for it.
5. A **minimum-n gate**, because the typicality pool is the `can_exist`-survivor subset and n runs
   7-100 across the current 51 combinations.
6. Flat CSV rows for both grains, following the `severity_drivers.csv` precedent.

### Out of Scope

- **Removing or re-keying `axis_b.dispersion_contrast`.** It is one of four named guards against the
  mode-collapse inversion (ADR:118-123) and the only place the SCB contrast is *tested*. The new axis
  sits beside it; it does not replace it.
- **Any change to `judge_prompt.md`, the judge schema, `n_rounds`, or the typicality scale.** A prompt
  change moves `prompt_template_sha256` and invalidates the homogeneity guard against all 51 judged
  combinations, forcing a full re-judge at full LLM cost.
- **Re-judging at `n_rounds >= 2`.** Tracked as a prerequisite for the round-level protocol below, but
  it is an LLM-cost decision of its own, not part of this plan.
- **A composite "realism score"** folding typicality into impossibility. Deliberately refused; see
  Definitions (`non-composite`).
- Countries other than `swedish_02` (nothing here is Sweden-specific; no other judged country exists).
- Significance testing *between* competitors on the new statistic. The existing
  `factor_significance` block already tests typicality by model and by method; this plan adds no
  second inferential claim.

## Success Criteria

- [ ] Every consumable competitor, SCB included, carries a self-contained typicality statistic with
      point estimate, `ci_lo`/`ci_hi`/`ci_level`, `denominator` (= number of personas contributing a
      typicality) and `n_personas` (= the combination's full persona count), and the two are never
      conflated.
- [ ] The heatmap's cell denominators equal the corresponding `axis_a` grid's *typicality* base for
      the same competitor, asserted cell by cell; the two bases differ from Axis A's denominator by
      construction and each cell states which it uses.
- [ ] The diverging ramp's midpoint equals the SCB value read from the same document, not a literal.
      Removing SCB from the consumption set degrades to the neutral sequential ramp with a recorded
      reason, never a hard-coded midpoint.
- [ ] A cell below `--typicality-min-n` renders as explicitly under-powered (distinct from both a
      value and an unjudged `None`) and is counted in the block's `excluded` map.
- [ ] The new block is **reporting-only** in the tested sense: building the document with loose and
      tight typicality bounds produces byte-identical `axis_a`, `axis_b`, `severity`,
      `severity_drivers` and `factor_significance` blocks.
- [ ] Running the ranking twice produces byte-identical JSON, CSVs and figures; competitor order does
      not change any emitted byte.
- [ ] The 11-bin histogram published per competitor sums to that competitor's typicality denominator,
      asserted.
- [ ] `ruff check src/` clean; `pytest` green.

## Definitions

Terms this plan's correctness depends on. Pinned because each is ambiguous in at least two defensible
ways.

- **typicality score** — the judge's integer 0-10 for one persona in one round. `null` when that
  round judged the persona impossible; never 0, which is a real rating ("the rarest still-possible
  person you can conceive of").
- **typicality denominator** — the number of personas contributing a typicality to a competitor's
  statistic. Under today's `CompetitorRecord.typicality_means` this is the personas with
  `can_exist_majority` **and** a non-null mean — **not** `n_personas`. A competitor with a high
  impossibility rate therefore has its typicality measured over a smaller, differently-selected
  subpopulation than its Axis A rate. Every emitted row carries both numbers.
- **self-contained (computational)** — the statistic is a function of one competitor's own scores and
  the config, and of nothing else. Testable: recomputing it from that competitor alone reproduces the
  published value byte-for-byte.
- **self-contained (directional)** — *not claimed*. Typicality has no monotone better direction: a
  competitor scoring uniformly 10 has mode-collapsed onto the modal Swede; one scoring low may be
  reaching the real tail or may be incoherent. The optimum is interior. Direction is therefore
  supplied at render time by the diverging ramp, and the statistic carries `"direction": null` plus
  the reason as a data field.
- **under-powered cell** — a competitor whose typicality denominator is below `--typicality-min-n`.
  Rendered distinctly from an unjudged cell: unjudged claims *nothing was measured*, under-powered
  claims *this was measured on too few personas to read*.
- **non-composite** — the statistic is never averaged, weighted or otherwise folded together with the
  impossibility rate into a single score. The two have different denominators (above) and different
  directions (Axis A monotone, this axis interior), so a composite would be arithmetic over
  incommensurable quantities.
- **reporting-only** — feeds no ranking, no contrast and no significance test, and changes no number
  already published. Asserted by the byte-equality test, mirroring the `severity_drivers` precedent
  (`tests/test_realism_ranking_builder.py`, the loose-vs-tight-bounds test).

---

## Technical Design

### Approach

Compute an ordinal-valid dispersion statistic over each competitor's own typicality scores in
`realism_ranking`, publish it as a new top-level block beside `severity` and `severity_drivers`, and
render it through `_grid` + a new diverging-ramp heatmap plus a new methods-on-x figure.

Everything needed is **already on the wire**: `{combo}_personas.csv` (schema v2) carries
`typicality_mean`, `typicality_sd` and the raw per-round `typicality_rounds` series, the last retained
precisely "so the aggregator can run rank-based tests on rounds rather than only on the per-persona
mean". So this is a **consumer-side change only** — no producer change, no `--rewrite-artifacts` pass,
no re-judging, no schema bump.

The statistic goes in the cell; the reference goes in the colormap. That is what lets the block be
reference-free in computation (preserving the per-combination reproducibility property the ADR
protects) while still being readable as over- vs under-dispersed relative to SCB.

### The metric decision — resolve at Phase 1, before any chart work

Investigated 2026-08-11 against the real `swedish_02` data (50 synthetic competitors + SCB). Notation:
levels j = 0..k-1 with k = 11, proportions `p_j`, and `F_j` the CDF at the **10 interior cutpoints
only** (j = 0..k-2; including `F_10 = 1` biases every CDF-based measure).

**The unification that shrinks the choice** (Weiss 2019, verified numerically to <7e-16 over 20 000
Dirichlet draws): Leik's D, Kvalseth's COV and Berry-Mielke IOV are one family,

```
OV_q = 1 - [ (1/(k-1)) * SUM_{j=0}^{k-2} |2*F_j - 1|^q ]^(1/q)
```

with q=1 -> Leik's D, q=2 -> Kvalseth's COV, and the un-rooted q=2 -> Berry-Mielke IOV. Only
van der Eijk's A and Tastle-Wierman's Cns are separate constructions.

| # | Candidate | Equation | Range / endpoints | Ordinal-valid | On this data | Verdict |
|---|-----------|----------|-------------------|---------------|--------------|---------|
| 1 | **Berry-Mielke IOV** | `IOV = (4/(k-1)) * SUM_{j=0}^{k-2} F_j*(1-F_j)` = `1 - (4/(k-1))*SUM (F_j-0.5)^2` | [0,1]; 0 = all mass on one level (total collapse), 1 = 50/50 at the extremes | **Yes** (CDF form is invariant to any strictly increasing relabelling) | SCB **0.399**; synthetic [0.000, 0.632], median 0.328; **50/50 distinct**, rho = 0.961 | **Recommended** |
| 2 | Leik's D | `D = (2/(k-1)) * SUM_{j=0}^{k-2} min(F_j, 1-F_j)` | [0,1]; 0 = consensus, 1 = maximal dispersion | Yes (contested by Davies 1970) | SCB 0.274; 43/50 distinct | Viable; L1 sibling of #1 |
| 3 | van der Eijk's A | layer decomposition (see References) | **[-1,+1]**; +1 unimodal, **0 = uniform for any k**, -1 bimodal at extremes; **direction inverted** | Yes | reproduces published fixture A = 0.6113333 | Viable at n>=50 only — highly sensitive to empty categories, and the n=7-19 cells' tail zeros are sampling noise |
| 4 | Rao's quadratic entropy | `Q(a) = SUM_i SUM_j p_i*p_j*|i-j|^a`, with `|i-j|^0 = 1[i!=j]` | a=0 -> Simpson (nominal); **a=1 -> (k-1)/2 * IOV (ordinal)**; a=2 -> 2*variance (interval) | tunable | — | Not a separate candidate — the **scale-assumption dial**. Worth stating in docs: today's `variance` and #1 are one object at two settings |
| 5 | Mean typicality | `M = SUM_j j*p_j` | [0,10] | **No** — interval assumption on a scale whose prompt anchors 9 *and* 10 both as "modal/ordinary" | 46/50 distinct, rho = **0.987**, largest SCB separation (4.71 vs 6-9) | Viable, highest resolution; but Liddell & Kruschke (2018) show metric models on ordinal data invert effect orderings precisely when groups differ in *shape*, which these do |
| 6 | Miller-Madow Shannon H | `H = -SUM p_j*log2(p_j)`; `H_MM = H + (k_hat-1)/(2*n*ln2)` | [0, log2(11) = 3.459] | No interval assumption but **order-blind** | 50/50 distinct, rho = 0.971 | Fallback only — cannot separate a {0,10} split from a {9,10} split (identical H, Simpson and Berger-Parker; IOV gives 1.000 vs 0.100). Plug-in bias varies **8x across cells** (0.412 bits at n=7 vs 0.051 at n=100) and the bootstrap does not correct it |
| 7 | `P(T <= k0)` | `Pi(k0) = F_k0` | [0,1] | **Yes — zero scale assumptions of any kind** | at the current `tail_threshold = 3`, **16/50 cells are exactly 0.000** (23 distinct); at k0=5, 7 at zero (29 distinct); the mirror cut `P(T >= 9) = 1 - F_8` gives 42/50 | Secondary/plain-language number, not the cell value. Use Wilson or Clopper-Pearson, not the bootstrap |

**Rejected** (each with the disqualifying reason, so they are not re-proposed): median / mode /
Hodges-Lehmann / quantile coverage (9-12 distinct values across 50 cells, tie groups to 31 — the
11-point scale is too coarse); IQR and MAD (6 distinct, 12 cells at the floor); trimmed mean (trims
away the rare-tail personas that *are* the construct); **Pielou's evenness** (`H/ln k_hat` — actively
inverts the signal: a cell using only {9,10} at 50/50 scores 1.0, maximal "evenness", catastrophic
collapse); richness `k_hat` (n-capped — an n=7 cell cannot exceed 7 levels); Tastle-Wierman Cns (the
one Family-2 measure that *does* assume interval spacing, so it does not solve what SD was rejected
for); total variation and Hellinger (order-blind); KL (undefined wherever SCB has a zero cell, and SCB
uses only 8 of 11 levels — it *will* fire); **Wasserstein-1** (Spearman with |mean - mean_SCB| =
**0.997** on this data — under first-order dominance W1 = |E[X]-E[Y]| exactly, so it carries no
information beyond the mean difference while looking more sophisticated); Vendi Score (reduces to a
Hill number under an ordinal kernel — a reparametrisation of Rao's Q on 11 levels).

#### Decision (2026-08-12)

Phase 0 is resolved. This subsection is the spec Phases 1-3 build to; where it and the prose above
differ, this subsection wins.

**Cell value: Berry-Mielke IOV (candidate #1).** It is the table's own recommendation; it is
ordinal-valid — invariant to any strictly increasing relabelling of the 11 levels, which is the exact
property Phase 1.3 tests and the plan claims; and it is the only shortlist member that separates a
`{0,10}` split (IOV 1.000) from a `{9,10}` split (IOV 0.100), which is precisely the mode-collapse
distinction this axis exists to draw. Entropy and Simpson cannot make that distinction (identical
value on both splits); the mean cannot either. The whole rendering design — interior optimum,
diverging ramp centred on SCB, `"direction": null` — is built for a **dispersion** statistic. The mean
measures **location**, a different question, so the two are not interchangeable and the mean is not
the default.

**Mean typicality nonetheless ships as a selectable alternative**, via the `--typicality-metric mean`
flag already specified in Phase 3.3. When it is selected, the interval-assumption caveat must travel
as a **data field on every emitted row** (Risks table, "Mean chosen for readability, then read as a
measurement"), not only in the docs. IOV is the default.

**Sign convention: dispersion orientation.**

```
IOV = (4/(k-1)) * SUM_{j=0}^{k-2} F_j*(1-F_j)          on [0,1]

    0 = all mass on one level (total collapse)
    1 = 50/50 at the two extremes (maximal dispersion)
```

Higher means **more dispersed**. This is deliberately the *dispersion* orientation and therefore runs
opposite to Blair-Lacy's normed concentration `l^2`. Because `agrmt::dsquared()`, Stata's `ordvar` and
R's `wINEQ` disagree with one another on which way this family points (0.2), the orientation must be
unambiguous **in the output**, not only in a docstring. The emitted block therefore carries:

- `statistic_label` — human-readable and stating the endpoints, e.g.
  `"Berry-Mielke IOV (0 = collapsed onto one level, 1 = maximally dispersed)"`;
- `"orientation": "dispersion"` — as a data field;

alongside the already-planned `"direction": null` (no monotone better/worse direction — the optimum is
interior) and its reason string.

**`P(T <= k0)` ships as a secondary column, with `k0 = 5`.** It is published on the summary JSON/CSV
rows only and is **never** the heatmap cell value. The default threshold moves off 3: at `k0 = 3`,
16 of 50 cells sit at exactly 0.000 and the column carries almost no information; at `k0 = 5` only 7
do. The threshold is CLI-overridable via `--typicality-tail-threshold`. Its interval is a **Wilson
score interval**, not the bootstrap — it is a proportion, and the bootstrap is the wrong tool at its
boundary.

**`--typicality-min-n` defaults to 30.** This excludes 5 of the 50 synthetic cells. Those cells are
**not dropped**: they are flagged `under_powered`, counted into the block's `excluded` map, and
rendered distinctly from an unjudged `None` (Definitions, "under-powered cell").

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Self-contained statistic in the cell + **diverging ramp centred on SCB** | Cell is reference-free and reproducible in isolation; over- vs under-dispersion become opposite colours; reference enters at render only | The midpoint must be resolved from the document, and the SCB-absent case needs a defined degradation | **Chosen** |
| Replace Axis B with the new axis | One typicality story instead of two | Dismantles one of the four ADR-named guards against the mode-collapse inversion, and deletes the only *tested* SCB contrast | Rejected |
| Put `distance_to_scb` in the cell (extend Axis B to a grid) | No new statistic; reuses the existing block | Keeps the sign-discarding `abs()`; the cell would still not be readable on its own — the exact defect this plan exists to fix | Rejected |
| Compute the statistic in `persona_realism` and publish it in `{combo}.json` | Sits beside `dispersion`; available to any consumer | Producer change -> schema bump -> 51-combo `--rewrite-artifacts` pass; and the ranking is the layer that owns cross-unit rendering anyway. Revisit only if a second consumer appears | Rejected (for now) |
| Mean typicality as the cell value | Highest resolution (46/50 distinct, rho 0.987) and the largest SCB separation; simplest to explain | Interval assumption on a demonstrably non-equidistant scale; measures location, not collapse — a different question from the one Axis B was built for | **Rejected as the default** (2026-08-12) — retained as a `--typicality-metric mean` option, with the interval-assumption caveat carried as a data field on every emitted row |
| Composite realism score (typicality + impossibility) | One headline number | Incommensurable denominators and directions; Ozkan (2026) is the citable precedent for refusing exactly this ("burying variance in one number is the masking we criticize") | Rejected |

### Architecture & Module Contracts

| Module / layer | Responsibility | Inputs -> Outputs | Must NOT know about |
|----------------|----------------|------------------|---------------------|
| `analysis/utils/ordinal.py` *(new)* | Pure ordinal-scale statistics over an integer level vector | `Sequence[int]`, `k` -> float | Personas, typicality, SCB, config, paths |
| `realism_ranking/builder.py` *(extended)* | `_typicality_axis(records, *, min_n, bootstrap)` -> the block; the 11-bin histogram per competitor | `Sequence[CompetitorRecord]` -> dict | Paths, figures, config files (values arrive as arguments) |
| `realism_ranking/charts.py` *(extended)* | `plot_typicality_heatmap` (diverging, SCB-centred) and `plot_typicality_by_method` | ranking dict -> Figure | How the statistic is computed |
| `scripts/analyze/rank_persona_realism.py` *(extended)* | Resolve `--typicality-metric` / `--typicality-min-n` / `k0` at the edge; write the CSVs and figures | ranking dict -> files | The statistic's definition |

Output delta, per country:

```
03_Analysis/realism_ranking/{country}/
    typicality_heatmap.png/.svg          NEW - diverging ramp, midpoint = SCB
    typicality_by_method.png/.svg        NEW - methods on x, SCB reference line
    typicality_summary.csv               NEW - one row per competitor
    typicality_histogram.csv             NEW - one row per (competitor, level 0..10)
    realism_ranking.json                 gains one top-level block
```

### Constraints inherited from the existing code (verified 2026-08-11)

1. **`_render_grid_heatmap` reads `cell["rate"]` and `cell["denominator"]` by literal key.** A grid
   whose value key is named anything else renders **every cell as grey `n/a` without raising** — a
   silent-wrong-output path, not a crash. Either reuse the key names or write a separate renderer.
2. **`vmin = 0.0` is hard-coded** on a true-zero premise ("a pale cell always means 'few', never
   'fewest in this particular sweep'"). Correct for a defect rate; for a bounded interior-optimum
   statistic the diverging ramp needs its own limits, symmetric about the SCB midpoint.
3. **There are only two ramps**: `_DEFECT_CMAP` Reds (more is worse) and `_NEUTRAL_CMAP` Blues
   (reported but never penalised — the S1 precedent, whose caption says the quantity "must not be
   read as a score"). There is **no "higher is better" ramp and no diverging ramp**; this plan adds
   the third state.
4. **`bootstrap_ci(values, statistic=..., iterations, ci_level, seed)` generalises** to any statistic
   and seeds a local RNG. **`bootstrap_difference_ci` does not** — it is hard-wired to a difference of
   *means* with no `statistic` parameter, and would silently return a difference-of-means CI for a
   non-mean point estimate, producing an interval that does not bracket its own point.
   `two_proportion_test` is proportions-only (Cohen's h is arcsine-specific).
5. **The real population has no grid coordinate**: `_grid` carries it under `"real"` and the heatmap
   draws it as a full-width band separated by a white rule. Preserve that; do not invent a method
   coordinate for SCB.
6. **The method axis** arrives pre-ordered via `strategy_complexity_order` (fixed in `d7e7adf`); the
   charts read `grid["methods"]` verbatim and must keep doing so.
7. **Bootstrap at a boundary.** The fully-collapsed cell (`all_pick_dag_v2_claude_sonnet`, all 100
   personas at level 9) gives a percentile CI of exactly `[0, 0]`. That is the honest interval
   computationally but has zero coverage whenever true dispersion > 0 (Andrews 2000: the bootstrap is
   *inconsistent*, not merely inaccurate, at a boundary). Report it and flag it; do **not** patch it
   with a Bayesian/Jeffreys bootstrap (tested: over-smooths to [0.023, 0.180] at n=100) and do **not**
   use BCa (acceleration is 0/0 and z0 = -inf there) or the basic/reverse-percentile interval (leaves
   [0,1] for a bounded statistic).

### Data facts this design is built on (`swedish_02`, measured 2026-08-11)

- **51 combination directories** (50 synthetic + `real_swedish_02`) under
  `.../03_Analysis/persona_realism/swedish_02/`.
- **Pooled histogram over 4517 scores:** 0:0.11% 1:0.97% 2:1.53% 3:2.66% 4:4.23% 5:5.76% 6:10.80%
  7:7.90% 8:12.97% **9:47.07%** 10:6.00%. All 11 levels used; 66% sits in 8-10.
- **SCB** (n=100, 0 impossible): mean 4.71, median 4.0, SD 1.838, mode 4 (34%), range **2-9** (no mass
  at 0, 1 or 10), variance 3.380, entropy 2.672, `tail_coverage` 0.26, **IOV 0.399**.
- **SCB is not the dispersion ceiling** — 16 of 50 synthetic competitors exceed it. Any design that
  assumes SCB is the maximum is wrong.
- **n is not ~100.** The typicality pool is the `can_exist` survivor subset: n runs **7 to 100**, five
  cells under 30. **Spearman(n, dispersion) = -0.576** — the three "most diverse" cells are the n=9,
  n=21 and n=10 cells, so a dispersion scalar partly re-renders the impossibility rate. Mechanism is
  plausibly survivorship; the correlation is measured, the mechanism is not.
- **`n_rounds` is effectively 1.** All 4551 rows have `n_rounds_successful = 1`; `typicality_sd` is
  empty everywhere; the `reliability` block (ICC / Krippendorff alpha) is `null` in **all 51**
  combinations. `judge.yaml` says 3 and the stamped `provenance.n_rounds` says 2 — the stamp is
  written from config at artifact-rewrite time and is **not** evidence of what was judged. Resolve
  that provenance drift before anything reads `n_rounds`.

### Deferred: the round-level protocol (needs `n_rounds >= 2`)

`Var(pooled round-level) = Var_between-persona + E[Var_within-persona]`, and the second term is judge
*unreliability*, not population heterogeneity. Simulated at judge noise sd 0.7-1.4, pooling raw round
integers inflates dispersion by **3-10%, and the inflation does not shrink as N grows**; averaging
rounds first does converge. But per-persona means are non-integer, which breaks the 11-level support
every CDF-based measure needs — the current code sidesteps this by rounding means back into integer
buckets, reintroducing noise.

**Protocol when N >= 2:** compute the statistic **once per round** (each round is a complete,
genuinely integer, n-persona ordinal sample), report the across-round mean as the point estimate and
the round-to-round spread as a separate uncertainty component. This preserves integer support exactly
and keeps ICC / Krippendorff's alpha a *reported moderator* on the cell rather than something folded
into the statistic. At today's N=1 the two are identical, both inflated by judge noise of unknown
magnitude, and the bias is unidentifiable.

### Known limitation to state, not fix

`judge_prompt.md` emits `"reasoning"` **before** `"typicality"`, and CoT-before-score is documented to
compress the judgment distribution (Wang, Zhang & Choi, EMNLP Findings 2025, arXiv:2503.03064) — the
prompt format shrinks the very spread being measured. Only 4 of 11 levels carry verbal anchors
(9-10, 5, 1, 0), inviting round-number clustering (Stureborg et al., arXiv:2405.01724). Neither is
fixable without moving `prompt_template_sha256` and forcing a full re-judge, so both are held constant
across all 51 groups (they already are) and recorded as a caveat. Dispersion is therefore a property
of *this judge under this prompt*, not of the population alone.

---

## Implementation Plan

### Phase 0: Decide the metric
**Goal:** One statistic chosen, with the choice recorded and its sign convention fixed.

**Started:** 2026-08-12
**Completed:** 2026-08-12

- [x] 0.1 — Decide **IOV vs mean typicality** as the cell value. IOV is the defensible measurement
      (ordinal-valid, separates {0,10} from {9,10}); the mean is the more readable figure with the
      largest SCB separation. They answer different questions and are not interchangeable: "LLM
      populations mode-collapse relative to the register population" vs "LLM populations are judged
      more ordinary".
- [x] 0.2 — Fix and document the **sign convention**. Blair-Lacy `l^2` is normed *concentration* and
      runs opposite to IOV; `agrmt::dsquared()` and Stata's `ordvar` disagree with each other; R's
      `wINEQ` publishes `1 - l^2` under the Blair-Lacy name. Whichever is chosen, the direction must
      appear in the output label, not only in the docstring.
- [x] 0.3 — Decide whether `P(T <= k0)` ships as a secondary column, and if so move `k0` off 3 (16/50
      cells sit at exactly 0.000 there).
- [x] 0.4 — Decide `--typicality-min-n` (candidate: 30, which excludes 5 of 50 cells).

**Outcome:** IOV as the default cell value in the dispersion orientation, mean as a
`--typicality-metric` option carrying its caveat as a data field, `P(T <= 5)` as a Wilson-interval
secondary column, `--typicality-min-n` 30. Full spec in **Decision (2026-08-12)** under *The metric
decision*.

**Dependencies:** None. **Blocks:** everything else.

### Phase 1: The statistic
**Goal:** A tested pure function, with no consumer wired to it.

- [ ] 1.1 — `analysis/utils/ordinal.py`: `cdf_interior(counts, k)` (the 10 interior cutpoints, with
      the F_k-1 exclusion argued in the docstring), `iov(counts, k)`, `leik_d(counts, k)`, and
      whichever of the shortlist survives Phase 0.
- [ ] 1.2 — Unit-test the identity `SUM (F_j - 0.5)^2 + SUM F_j*(1-F_j) = (k-1)/4` as the guard
      against a sign/complement error.
- [ ] 1.3 — Assert ordinal invariance: any strictly increasing relabelling of the levels leaves the
      statistic unchanged (this is the property the mean fails and the plan claims).
- [ ] 1.4 — Pin the endpoints: all mass on one level -> 0; 50/50 at the extremes -> 1; and the
      separation that motivates the choice, `{0,10}` = 1.000 vs `{9,10}` = 0.100.
- [ ] 1.5 — Confirm against the published van der Eijk fixture if A ships: V = (30,40,210,130,530,50,10)
      at k=7 -> A = 0.6113333, with `U` **unclamped** (at TU=0, U = -(k-1)/(k-2) = -1.111 at k=11;
      only the product A is bounded).

**Files Modified:** `src/population_synthetic/analysis/utils/ordinal.py` (new),
`tests/test_ordinal_stats.py` (new). **Dependencies:** Phase 0.

### Phase 2: The block
**Goal:** `typicality` in `realism_ranking.json`, with CIs, denominators and the histogram.

- [ ] 2.1 — `_typicality_axis(records, *, statistic, min_n, bootstrap)` in `builder.py`, modelled on
      `_severity_grids`: same `_grid_entries` adapter with the `"_record"` back-pointer, same
      `_grid` reshape, so SCB placement and the null-cell guarantee come for free.
- [ ] 2.2 — Per competitor: point estimate, `ci_lo`/`ci_hi`/`ci_level` via `bootstrap_ci` with the
      statistic passed as the `statistic` argument and the seed from the judge config's bootstrap
      block, `denominator` (typicality base), `n_personas`, `under_powered` flag, and the 11-bin
      histogram.
- [ ] 2.3 — Carry `"direction": null` with the reason string, `"reference_value"` (SCB's own
      statistic, or `null`), `"counting_unit"`, and `"reporting_only"` as data fields — the tables
      travel without the code.
- [ ] 2.4 — Append `_Skip` records for competitors that cannot be computed; count under-powered and
      excluded cells into an `excluded` map rather than dropping them silently.
- [ ] 2.5 — Two module-level flatteners (`typicality_summary_rows`, `typicality_histogram_rows`) added
      to `__all__`, keyed like `summary_rows`, with a total sort key: method by complexity, then
      model, real population last (reuse `_competitor_position`).

**Files Modified:** `src/population_synthetic/analysis/realism_ranking/builder.py`.
**Dependencies:** Phase 1.

### Phase 3: The figures and the CLI
**Goal:** Both figures beside the existing ones, and the CSVs.

- [ ] 3.1 — `plot_typicality_heatmap`: diverging ramp, **midpoint resolved from the block's
      `reference_value`**, symmetric limits, `n` annotated in every cell, under-powered cells hatched
      or greyed distinctly from `_MISSING_COLOR`, SCB as the existing full-width band. Degrade to the
      neutral sequential ramp with a printed note when `reference_value` is `null`.
- [ ] 3.2 — `plot_typicality_by_method`: methods on x in `grid["methods"]` order, statistic on y,
      per-model marks, SCB as a horizontal reference line with an inline label. Follow
      `method_significance/_draw_method_panel` for the panel structure and `fidelity/plot_c2st` for
      the reference-line-with-caption idiom. **Note this is a new idiom** — everywhere else in the
      analysis layer the real population is a series, bar or marker, never a reference line; the one
      `axhline` in `realism_ranking/charts.py` marks zero Axis-B distance, an arithmetic fact.
- [ ] 3.3 — `rank_persona_realism.py`: `--typicality-metric`, `--typicality-min-n`, and the tail
      threshold if 0.3 shipped; resolved at the edge and passed as arguments (the builder reads no
      config). Write both CSVs and both figures; honour `--no-charts`.
- [ ] 3.4 — Register the new outputs in `config/analysis/analysis_registry.yaml`'s
      `realism_ranking` description.

**Files Modified:** `src/population_synthetic/analysis/realism_ranking/charts.py`,
`scripts/analyze/rank_persona_realism.py`, `config/analysis/analysis_registry.yaml`.
**Dependencies:** Phase 2.

---

## Testing Plan

### Unit Tests
- [ ] The identity, ordinal-invariance, endpoint and `{0,10}` vs `{9,10}` tests from Phase 1.
- [ ] `_typicality_axis` on a hand-computed fixture; denominators equal the count of personas
      contributing a typicality, **not** `n_personas`, asserted against a fixture where the two differ.
- [ ] The degenerate cell: all personas at one level -> statistic 0.0, CI exactly `[0, 0]`, and a
      `boundary` flag set. Assert the flag, not just the interval.
- [ ] Under-powered cell is flagged and counted, never silently dropped; distinct in the payload from
      an unjudged `None`.
- [ ] Histogram bins sum to the typicality denominator.
- [ ] Reporting-only: loose vs tight bounds leave `axis_a`, `axis_b`, `severity`, `severity_drivers`
      and `factor_significance` byte-identical (the mixed logit excluded — its variational fit is not
      bit-reproducible between calls).
- [ ] Degenerate bounds (`min_n < 1`) raise rather than emitting an empty table.

### Integration Tests
- [ ] e2e in `test_realism_ranking_e2e.py`: judge -> rank on a `tmp_path` base emits both CSVs and
      both figures, byte-stable across two writes.
- [ ] SCB absent from the consumption set -> `reference_value` is `null`, the heatmap degrades to the
      neutral ramp with a recorded reason, and no hard-coded midpoint appears.
- [ ] Competitor order does not change any emitted byte (A-then-B vs B-then-A).
- [ ] The heatmap's method axis equals `strategy_complexity_order` of the present ids.

### Manual Verification
- [ ] Run over the 51 `swedish_02` combinations; confirm SCB lands at its measured value (IOV 0.399 /
      mean 4.71) and that the bulk of synthetic competitors sit on the collapsed side of it.
- [ ] Confirm the five n<30 cells are visibly marked and that removing them does not change any other
      cell.
- [ ] Read the figure against the pooled histogram and confirm it tells the same story: 47% of
      synthetic scores at level 9, SCB peaking at 4 with no mass at 0, 1 or 10.

### Edge Cases
- [ ] A competitor with zero typicality-bearing personas (every persona judged impossible) — `None`,
      never 0.0.
- [ ] An unjudged `(model, method)` pair — `None`, distinct from both a computed 0.0 and an
      under-powered cell.
- [ ] n=1 competitor: statistic defined but CI degenerate; must not crash the ramp limits.
- [ ] All competitors identical -> zero-width diverging range; the ramp must not divide by zero.

---

## Documentation Plan

- [ ] `docs/development/persona-realism-judge.md` — a "typicality" section stating the three things a
      reader needs before reading the figure: the denominator is the survivor subset, the direction is
      interior (not monotone), and the dispersion is a property of this judge under this prompt.
- [ ] `docs/architecture/commands.md` — the new flags and outputs.
- [ ] `config/analysis/analysis_registry.yaml` — enumerate the new published outputs in the
      `realism_ranking` description.
- [ ] `CLAUDE.md` — the `realism_ranking` paragraph gains the typicality axis, stating it is
      reporting-only and does not replace Axis B.
- [ ] **New ADR** — the computational-vs-directional self-containment distinction and the
      diverging-ramp resolution. This is the reusable idea: a reference-free statistic with a
      reference-dependent *rendering*.
- [ ] Record the ten places that assert the two-axis table so they are updated together, not
      piecemeal: the split ADR, `persona-realism-judge.md`, `analysis_registry.yaml`,
      `docs/architecture/sub-packages.md`, `docs/architecture/commands.md`, `CLAUDE.md`,
      `rank_persona_realism.py`'s header, `builder.py`'s ASCII table **and** its `axis_definitions`
      block (the only machine-readable one), and `charts.py`'s header.

---

## Rollback Plan

1. The block is purely additive: no existing field changes shape, no producer artifact is touched, no
   schema version moves. `git revert` of the feature commits restores prior behaviour exactly.
2. Deleting the four new output files returns the output base to its prior state; nothing else reads
   them.
3. If the diverging ramp proves unreadable, the fallback is the neutral sequential ramp already
   required for the SCB-absent case — a one-branch change, not a redesign.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| The cell partly renders the impossibility rate (Spearman(n, dispersion) = -0.576) | **High** | High | `--typicality-min-n` gate + `n` printed in every cell + both denominators on every row + the confound stated in the block and the docs |
| Two typicality claims in one document (this axis + the existing `factor_significance` Kruskal/Dunn over the same means, but with SCB held out) | High | Med | Reuse `typicality_means` as the single base so the numbers cannot disagree; cross-reference both blocks explicitly in the JSON and the docs |
| A new grid whose value key is not `"rate"` renders every cell as `n/a` **without raising** | Med | High | Either reuse the key names or write a dedicated renderer; a test asserting a populated cell is not `n/a` |
| Reading the axis as "higher is better" | Med | High | `"direction": null` as a data field, the diverging ramp, and a printed caption — the S1 precedent |
| Boundary bootstrap at the collapsed cell reported as a real interval | Med | Med | `boundary` flag on the payload and in the CSV; the honest `[0,0]` is published *with* the flag, never bare |
| Mean chosen for readability, then read as a measurement | Med | Med | If Phase 0 picks the mean, the interval-assumption caveat travels as a data field on every row |
| Docs asserting the two-axis table go stale in nine prose places | Med | Med | The Documentation Plan lists all ten sites; only `axis_definitions` is machine-readable, so the rest must be updated by hand in one pass |
| `n_rounds` provenance drift (config 3, stamp 2, cache 1) misleads a future reader | Med | Med | Fix or document the stamp before anything reads it; the round-level protocol section states what changes at N>=2 |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 0 — metric decision | one conversation | None |
| Phase 1 — the statistic | ~1 session; 2 new files | Phase 0 |
| Phase 2 — the block | ~1 session; 1 file | Phase 1 |
| Phase 3 — figures + CLI | ~1 session; 3 files | Phase 2 |

---

## References

- ADR: `docs/development/decisions/2026-08-07-persona-realism-per-combination-split.md` (Axis A/B
  definitions, the four mode-collapse-inversion guards, the per-combination purity rule)
- Completed plan: `docs/development/plans/completed/split-persona-realism-ranking.md`
- Active plan (must land first): `docs/development/plans/active/severity-driver-attribution.md`
- Sibling figure plan: `docs/development/plans/pending/model-method-tv-heatmap.md`
- Operator guide: `docs/development/persona-realism-judge.md`
- Judge prompt: `config/analysis/persona_realism/judge_prompt.md` (severity block at :53-56, issue
  schema at :66, the `can_exist`/S3 rule at :76)
- Weiss (2019), *J. Applied Statistics* 46(16):2905-2926 — the `OV_q` family, asymptotic bias
  correction and CIs
- Blair & Lacy; Berry & Mielke; Leik (1966), *Pacific Sociological Review* 9(2):85-90
- van der Eijk (2001), *Quality & Quantity* 35(3):325-341 — agreement A
- Jenkins (2020), *Stata Journal* 20(3):505-531 — polarization vs inequality traditions on an 11-point
  0-10 scale; they rank distributions **oppositely**, and choosing one is a substantive claim
- Liddell & Kruschke (2018), *JESP* 79:328-348 — metric models on ordinal data invert effect orderings
- Andrews (2000), *Econometrica* 68(2):399-405 — bootstrap inconsistency at a boundary
- Wang, Marriott & Li (2022), *Metrika* 85:809-831 — two-sample coverage near a boundary is unsignable
- Santurkar et al. (ICML 2023, arXiv:2303.17548) — ordinal Wasserstein on LLM opinion distributions
- Bisbee et al. (2024), *Political Analysis* 32(4):401-416 — "means match, variance collapses"
- Ozkan (2026), arXiv:2607.18310 — mode-collapse correction; the precedent for never folding
  dispersion into a composite

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
