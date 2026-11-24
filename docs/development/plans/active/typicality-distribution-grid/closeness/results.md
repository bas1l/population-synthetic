# Model vs strategy: what drives how close a combination's typicality distribution is to SCB

Scratch analysis, swedish_02, 2026-09-21. Code: `closeness.py` (outcomes, decomposition, bootstrap,
permutation, complete-block tests), `clm.py` (individual-level cumulative-link model and a
statsmodels cross-check), `ci_attribution.py` (which resampling drives the CI widths),
`fig_closeness.py` (figure). Nothing in the repo was edited.

## Answer

**Strategy matters more than model, by a factor of about 2.5 in explained variance. Both effects
are significant.** Of the variation in closeness to SCB across the 58 combinations (Cliff's δ),
strategy explains 61% [54, 65], model 24% [20, 29], and the residual (model × strategy interaction
plus noise) 17% [15, 22]. The size of the strategy effect comes almost entirely from **strategy E
(All Generate Evaluate Random Pick)**. It is the closest to SCB in 10 of 10 complete models against
A, B and C, and in 9 of 10 against D. Among A to D, B (All Pick DAG) is the furthest from SCB. A and
D are the closest of the four and cannot be told apart.

No combination reaches SCB. All 58 δ values are positive (range 0.30 to 0.88): every combination's
individuals are judged more typical than the real population's. Strategy E halves the gap but does
not close it.

## Data and unit

- Individuals: can_exist-majority survivors, 5,760 synthetic (88 to 100 per combination) and 100
  SCB. Same load as `../effects.py`.
- **Primary basis: the first judge round** (integer typicality 0 to 10), following the manuscript
  precedent. Sensitivity basis: the mean over rounds. The two differ only for the five Claude Haiku
  combinations (δ changes by at most 0.057).
- Unit of analysis: the **combination**, n = 58. The design has 12 models × 5 strategies = 60 cells.
  Two were withdrawn at the population cap (DeepSeek-R1 14B / E and Gemma4 E4B / E), so they have no
  individuals and are treated as absent, never as zero.
  - The additive model and the permutation tests use all 58 combinations (unbalanced design).
  - The complete-block rank tests use the 10 models that have all 5 strategies (50 combinations),
    and drop DeepSeek-R1 14B and Gemma4 E4B entirely.

## Methods (text-ready)

*Outcomes.* For each combination we compared the distribution of first-round typicality scores of
its individuals with that of the SCB reference population (n = 100). The primary outcome was
Cliff's δ = P(X > Y) − P(X < Y), where X is a synthetic individual's score and Y a real individual's.
This statistic needs only the ordering of the scores. δ = 0 means the two distributions are
stochastically equal, and all 58 observed values were positive, so a smaller δ means closer to SCB.
There were two sensitivity outcomes:
- the difference in the share of individuals with typicality ≤ 4 (SCB share = 0.57, minus the
  combination's share);
- the mean absolute gap between the two empirical cumulative distribution functions over the
  continuum [0, 10], which equals the Wasserstein-1 distance divided by 10. Averaged over cut
  points, this gap uses the scores only through their order.

*Decomposition.* We fitted each outcome with an additive two-way linear model, outcome ~ model +
strategy, over the 58 combinations. There was no interaction term, because each cell holds one
combination. The residual (42 df) therefore contains the model × strategy interaction together with
sampling noise. With no interaction in the model, type II and type III sums of squares coincide
(checked against `statsmodels.anova_lm`). For each factor we report:
- partial η² = SS_effect / (SS_effect + SS_residual);
- partial ω² = (SS_effect − df_effect·MS_residual) / (SS_effect + (N − df_effect)·MS_residual);
- the share of the total sum of squares.

Because the design is unbalanced, the two type II SS plus the residual do not add up exactly to the
total. The overlap is −1.8% of SS_total.

*Bootstrap.* 95% CIs are percentile intervals from 5,000 replicates. In each replicate we resampled
individuals with replacement within every combination and, **jointly, within SCB**, recomputed all
58 δ values against the resampled SCB, and then recomputed every statistic. SCB is a single sample
shared by all 58 δ values, so it is redrawn once per replicate. These CIs condition on the 12 models
and 5 strategies (fixed effects). They carry individual-level sampling uncertainty only.

*Significance.*
- Permutation tests of each factor in the additive model used 10,000 permutations each, with the
  type II F as the statistic. For strategy, the 58 outcomes were permuted within model blocks (a
  model with only 4 strategies permutes among those 4). For model, they were permuted within
  strategy blocks.
- Following the house `method_significance` procedure, we then ran:
  - a Friedman test across strategies, with the 10 complete models as blocks, and a Friedman test
    across models, with the 5 strategies as blocks, each reporting Kendall's W and its bootstrap CI
    (same replicates, W recomputed per replicate with the tie correction);
  - Page's L along the house simplest-first order A < B < C < D < E, two-sided, together with the
    linear and quadratic orthogonal polynomial contrasts that the house pairs it with;
  - three pairwise post hoc families: Nemenyi (house), Conover with Holm adjustment, and paired
    t-tests with Holm adjustment plus sign tests (`paired_t_pairwise`).

## Results (primary: first round, Cliff's δ)

### Weight

| | Strategy | Model | Residual |
|---|---|---|---|
| Share of total SS | 0.61 [0.54, 0.65] | 0.24 [0.20, 0.29] | 0.17 [0.15, 0.22] |
| Partial η² | 0.78 [0.71, 0.81] | 0.59 [0.50, 0.64] | |
| Partial ω² | 0.72 [0.63, 0.76] | 0.46 [0.35, 0.52] | |
| ω² (of total) | 0.59 [0.51, 0.63] | 0.20 [0.15, 0.24] | |
| F (type II) | F(4, 42) = 37.4 | F(11, 42) = 5.45 | |

- Strategy SS / model SS = 2.49 [1.92, 3.27].
- Partial ω²(strategy) − partial ω²(model) = 0.26 [0.19, 0.34]. The CI excludes 0.
- Strategy's larger share is not produced by its fewer levels. ω² already charges each factor for
  its degrees of freedom (4 for strategy, 11 for model).
- The bootstrap means sit slightly below the point estimates (partial ω² 0.69 vs 0.72 for strategy,
  0.43 vs 0.46 for model), because resampling noise adds to the residual. The percentile CIs are
  therefore mildly conservative.

### Significance

**Permutation tests (all 58 combinations):**
- Strategy: p ≤ 1.0 × 10⁻⁴. None of the 10,000 permutations reached the observed F. Parametric
  F-test p < 2.6 × 10⁻¹³.
- Model: p ≤ 1.0 × 10⁻⁴. None of the 10,000 permutations reached the observed F. Parametric F-test
  p < 2.6 × 10⁻⁵.

**Complete blocks (10 models × 5 strategies):**
- Friedman, strategy: χ²(4) = 27.2, p < 1.9 × 10⁻⁵. Iman–Davenport F = 19.1, p < 1.7 × 10⁻⁸.
  Kendall's W = 0.68 [0.58, 0.76].
- Friedman, model: χ²(9) = 23.0, p = 0.0062. Iman–Davenport p = 0.00093. W = 0.51 [0.39, 0.61].
- Repeated-measures ANOVA (value-based, sphericity assumed): strategy partial η² = 0.79
  (p < 1.5 × 10⁻¹¹); model partial η² = 0.52 (p = 0.00080).

**Mean ranks by strategy** (1 = closest to SCB): E 1.1, A 2.7, D 2.8, C 3.9, B 4.5. The Nemenyi
critical difference is 1.93.

**Page's L** along A < B < C < D < E: z = −3.10, two-sided p = 0.0019. The trend runs against the
predicted direction, meaning δ falls with complexity. It is not monotone:
- the linear contrast is negative (p < 4.2 × 10⁻⁵);
- the quadratic contrast is also negative (p < 2.1 × 10⁻⁵).

The pattern is a rise from A to a peak at B, then a step down at E. The house caveat applies: Page's
L fires on a single step change, and here that step change is E.

### Post hoc pattern (strategy, complete blocks)

| Pair | Closer to SCB | Wins (out of 10) | Nemenyi | Conover–Holm | Paired t–Holm |
|---|---|---|---|---|---|
| B vs E | E | 10 | 1.5 × 10⁻⁵ | < 1.4 × 10⁻⁸ | 2.1 × 10⁻⁵ |
| C vs E | E | 10 | 0.0007 | < 8.8 × 10⁻⁷ | 4.9 × 10⁻⁵ |
| A vs E | E | 10 | 0.16 | 0.0027 | 0.0012 |
| D vs E | E | 9 | 0.11 | 0.0019 | 0.0030 |
| A vs B | A | 10 | 0.081 | 0.0011 | 0.0030 |
| B vs D | D | 9 | 0.11 | 0.0019 | 0.050 |
| A vs C | A | 8 | 0.44 | 0.029 | 0.12 |
| C vs D | D | 7 | 0.53 | 0.039 | 0.55 |
| B vs C | — | 6 of 10 favour C | 0.92 | 0.33 | 0.36 |
| A vs D | — | 5 of 10 favour A | 1.00 | 0.81 | 0.55 |

How robust each difference is:
- **All three families agree:** E is closer than B and closer than C.
- **Conover–Holm and paired t–Holm agree:** E is closer than A and closer than D, and A is closer
  than B. Nemenyi, the most conservative family, misses these with 10 blocks.
- **Conover only:** B–D (paired t–Holm p = 0.050), A–C and C–D.
- **No evidence of a difference:** A vs D and B vs C.

Strategy least-squares means of δ are A 0.65, B 0.78, C 0.74, D 0.70 and E 0.39. The E − mean(A–D)
contrast is −0.33.

**Model:** of 45 pairs, Nemenyi rejects 1 and Conover–Holm rejects 4. Every one of those pairs
involves Kimi K3 (closest) or Qwen 3.5 Flash (furthest). Model least-squares means run from
DeepSeek-R1 14B at 0.49 and Kimi K3 at 0.51 up to Claude Sonnet at 0.75 and Qwen 3.5 Flash at 0.77.

### Sensitivity outcomes agree

All three outcomes rank strategy above model with non-overlapping partial ω² CIs, and every test is
significant under each of them.

| Outcome | Share (strategy / model / residual) | Partial ω² strategy | Partial ω² model | Friedman strategy (W) | Friedman model (W) |
|---|---|---|---|---|---|
| Cliff's δ (primary) | 0.61 / 0.24 / 0.17 | 0.72 [0.63, 0.76] | 0.46 [0.35, 0.52] | p < 1.9 × 10⁻⁵ (0.68) | p = 0.0062 (0.51) |
| Share ≤ 4 gap | 0.68 / 0.16 / 0.19 | 0.72 [0.58, 0.77] | 0.31 [0.16, 0.38] | p < 1.0 × 10⁻⁵ (0.71) | p = 0.00073 (0.64) |
| Mean CDF gap (W1/10) | 0.59 / 0.25 / 0.17 | 0.71 [0.64, 0.74] | 0.46 [0.36, 0.53] | p < 3.3 × 10⁻⁵ (0.65) | p = 0.013 (0.47) |

- Permutation p for strategy is ≤ 1.0 × 10⁻⁴ under all three outcomes. For model it is
  ≤ 1.0 × 10⁻⁴ (δ), 0.0030 (share ≤ 4) and 0.0002 (CDF gap).
- The mean CDF gap tracks δ almost exactly: the Spearman correlation across the 58 combinations is
  0.998.
- The share-≤4 gap reads only one cut point, so it correlates less (ρ = 0.78 with δ). It weights
  strategy even more heavily (strategy/model SS ratio 4.2).
- In the post hoc tests, E again separates from every other strategy. Under share ≤ 4 the only other
  significant steps (Conover–Holm only) are D being closer than A, B and C.

Two further sensitivity checks leave the result unchanged:
- **Mean over rounds instead of the first round:** partial ω² is 0.72 (strategy) and 0.46 (model).
  Shares are 0.61 / 0.24 / 0.17. Permutation p is ≤ 1.0 × 10⁻⁴ for both factors.
- **Dropping Claude Sonnet**, the judge's own model family (n = 53): partial ω² is 0.71 (strategy)
  and 0.46 (model).

### Individual-level cross-check (cumulative-link model)

We fitted a proportional-odds logit model of first-round typicality on the 5,760 synthetic
individuals (`statsmodels` `OrderedModel`, 10 thresholds). Increases in McFadden R² are relative to
a thresholds-only model:

| Term | LR χ² | df | p | ΔMcFadden R² |
|---|---|---|---|---|
| Strategy, given model | 1,132 | 4 | < 8.7 × 10⁻²⁴⁴ | 0.057 |
| Model, given strategy | 738 | 11 | < 3.7 × 10⁻¹⁵¹ | 0.037 |
| Model × strategy (cell model vs additive) | 936 | 42 | < 6.8 × 10⁻¹⁶⁹ | 0.047 |
| Additive model + strategy vs null | 1,714 | 15 | — | 0.087 |

At the individual level, strategy again outweighs model, by 1.5× in ΔR² and with far fewer degrees
of freedom. The individual-level data also show a clear interaction. The additive model's predicted
distributions reproduce each combination's observed δ only moderately (Pearson r = 0.86, Spearman
ρ = 0.89, RMSE = 0.086). This matches the 17% residual at the combination level.

These p-values treat individuals as independent. That overstates the evidence, because the design
unit is the combination (one run each). Read them as effect-size descriptions, not as the test.

## Caveats, quantified

1. **SCB n = 100 dominates the level, not the weights.** From `ci_width_attribution.csv`: the
   shared SCB sample accounts for 99% of the bootstrap variance of the grand mean δ, and 91 to 99%
   of the variance of every least-squares mean. For contrasts it accounts for about 80% (B − A 80%;
   E − mean(A–D) 83%). For the effect sizes it accounts for less: 30% of the variance of partial ω²
   for strategy and only 6% for model. Resampling SCB moves all 58 δ values together, which shifts
   the level but barely changes their spread. The absolute distances to SCB are therefore uncertain
   (for strategy E, δ = 0.39 with CI [0.25, 0.52]). The finding that strategy outweighs model rests
   mainly on within-combination sampling and is much more precise.
2. **One run per combination.** The unit is the combination (n = 58), not the individual
   (n = 5,760). The residual (17% of SS) cannot separate the model × strategy interaction from
   run-to-run variability. The bootstrap captures sampling variation between individuals, but not
   variation between repeated generation runs of the same combination, which was never measured. The
   CIs therefore understate the full replication uncertainty.
3. **The judge (Claude Sonnet 5) is also a generator.** Removing Claude Sonnet leaves partial ω² at
   0.71 (strategy) and 0.46 (model). A self-preference bias, if one exists, is shared by all five
   Claude Sonnet combinations. The judge scored the model family it belongs to as among the least
   SCB-like (least-squares mean 0.75, rank 11 of 12), so there is no sign of self-favouring on this
   outcome. A single judge also scored SCB, so any judge-specific scale bias enters every δ through
   the same judge. That is a shared offset and does not affect the model-vs-strategy decomposition.
4. **Withdrawn cells.** Strategy E is missing for two models. The additive least-squares means
   adjust for this, and the raw E mean (0.40) is almost the same as the least-squares mean (0.39).
   The complete-block tests drop both models.
5. **Page's L direction.** The house hypothesis is a simplest-first order. The significant result
   runs against that order and comes from a single step change (E), not a smooth ramp. It should not
   be reported as "complexity brings typicality closer to SCB".

## Files (this folder)

- `combination_outcomes.csv`: the 58 combinations with all three outcomes on both bases, plus
  joint-bootstrap CIs.
- `decomposition.csv`: SS, F, partial η², partial ω², ω² and shares, with CIs from joint,
  combinations-only and SCB-only bootstraps (primary basis), and point estimates on the mean-over-rounds basis.
- `permutation_tests.csv`, `complete_block_tests.json` (Friedman, W with CIs, Page, contrasts,
  RM-ANOVA, mean ranks, Nemenyi CD) and `posthoc_pairs.csv` (Nemenyi, Conover raw and Holm, paired
  t–Holm, sign test, win counts).
- `ls_means.csv`, `ci_width_attribution.csv` and `sensitivity_without_claude_sonnet.csv`.
- `clm_lr_tests.csv`, `clm_predicted_vs_observed.csv` and `anova_lm_check.csv`.
- `figures/closeness_model_vs_strategy.png`: (a) variance shares with partial ω²; (b) strategy
  least-squares means; (c) model least-squares means in model_ranking order.
