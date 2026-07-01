# 03 — Statistical & Scientific Software Concerns

A pipeline that *computes statistics and draws conclusions* carries an extra
burden beyond plumbing: the conclusions must be **valid** and **reproducible**.
A throughput bug shows up as a slow run; a statistics bug shows up as a
confident, plausible, wrong answer that nobody notices. This document covers the
concerns specific to analytics/scientific code and how to handle them. It is
method-agnostic but names the standard methods such pipelines use.

---

## 1. Reproducibility is a first-class requirement

For analytics code, "it runs" is not the bar — "it produces the *same* answer,
and someone else can reproduce it" is. The research-software literature
converges on a small set of rules (Sandve et al., "Ten Simple Rules for
Reproducible Computational Research"; Wilson et al., "Good Enough Practices"):

- **Track how every result was produced** — record the inputs, code version,
  config, and library versions behind each artifact.
- **Automate every step.** A result produced by a manual click or a hand-edit is
  not reproducible. The pipeline, end to end, should be a single command.
- **Avoid manual data manipulation.** No "I just fixed up that one file in a
  spreadsheet." Transformations live in code.
- **Record exact versions** of external tools and libraries.
- **Archive raw and intermediate results**, not just final outputs, so a result
  can be traced and re-derived.
- **Record random seeds** (see §2).

These are cheap to adopt and they are what separates analysis software from a
one-off script.

---

## 2. Determinism and random seeds

Any stochasticity — sampling, bootstrap, jitter in a plot, shuffling, a
stochastic algorithm — makes output non-reproducible unless the source of
randomness is seeded and the seed recorded.

**How to apply.**

- Seed **explicitly** and **record the seed** in run metadata.
- Prefer modern, local RNG objects over global state. In NumPy, use
  `np.random.default_rng(seed)` (a `Generator`) rather than the legacy global
  `np.random.seed(...)`. The official NumPy docs recommend this and provide
  `SeedSequence` for spawning independent, reproducible streams for parallel
  work.
- Be aware that bit-stream reproducibility is **not guaranteed across library
  versions** — record the library version alongside the seed if exact
  reproduction matters.
- Even "cosmetic" randomness (e.g. point jitter in a chart) should be seeded so
  figures are byte-stable across runs.

---

## 3. Choosing the right statistical method

Use the method whose assumptions your data actually meets. The most common
mistake in analytics code is reaching for a parametric default (t-test, ANOVA,
Pearson) when the assumptions (normality, large samples, equal variance) don't
hold.

### Parametric vs. non-parametric

When per-group sample sizes are small and the metrics are not expected to be
normally distributed (latencies, rates, counts, entropies often aren't),
**non-parametric, rank-based** methods are the safer default — they make no
distributional assumption.

| Goal | Non-parametric choice | Notes |
|------|----------------------|-------|
| Differences across ≥2 groups (omnibus) | **Kruskal–Wallis H-test** | Rank-based one-way "ANOVA"; H ≈ χ² with k−1 df. Kruskal & Wallis (1952). |
| Two groups only | Mann–Whitney U / Wilcoxon rank-sum | The two-group special case. |
| Paired two groups | Wilcoxon signed-rank | For matched samples. |
| Pairwise *after* a significant omnibus | **Dunn's test** | The standard post-hoc following Kruskal–Wallis on combined ranks. Dunn (1964). |
| Goodness-of-fit / categorical match | **Chi-squared** | Observed vs. expected category frequencies. |

### Multiple-comparison correction

If you run an omnibus test and then several pairwise tests, the family-wise
error rate inflates — some "significant" pairs will be false positives. Correct
for it:

- **Holm** (step-down) — uniformly more powerful than single-step Bonferroni,
  still controls family-wise error, no distributional assumptions. A good
  default for post-hoc p-values. Holm (1979).
- **Bonferroni** — simplest, most conservative.
- **Benjamini–Hochberg (FDR)** — when you can tolerate a controlled false-
  discovery rate instead of family-wise control (many tests).

Always state *which* correction you applied; an uncorrected battery of pairwise
tests is a common, citable error.

### Effect size, not just p-values

A p-value tells you whether an effect is detectable, not whether it matters.
Where feasible, report an effect-size or magnitude alongside significance
(e.g. rank-biserial, difference in medians) so a "significant" result with a
trivial magnitude is visible as such.

---

## 4. Common derived metrics and their definitions

Analytics pipelines repeatedly compute the same families of summary metrics.
Get the definitions exactly right — small index/edge-case errors are easy and
silent.

- **Median / percentiles.** Robust central tendency and tail summaries (p50, p95,
  p99 for latencies). Be explicit and consistent about the interpolation method
  (nearest-rank vs. linear); `numpy.percentile` defaults to linear
  interpolation, which differs from a nearest-rank definition. Document which
  you use, especially for small samples where they diverge.
- **Shannon entropy.** `H = −Σ pᵢ·log pᵢ` — uncertainty/diversity of a discrete
  distribution; choose the log base deliberately (base 2 → bits). Shannon
  (1948); `scipy.stats.entropy` computes it (and KL divergence).
- **Total variation distance.** `TV(P,Q) = ½·Σ|pᵢ − qᵢ|` — a bounded [0,1]
  distance between two distributions; intuitive for "how different are these two
  histograms." (Canonical treatment: Levin, Peres & Wilmer.)
- **Rates with small denominators.** Retry rates, error rates, success rates over
  few trials are high-variance; a "100% failure" over 2 attempts is not
  comparable to one over 200. Carry the denominator, and prefer interval
  estimates over point rates when N is tiny.

---

## 5. Numerical correctness and testing

Statistical code needs tests against **known answers**, because a wrong formula
still returns a number.

- **Validate against an authority.** Test your statistic on a textbook example or
  cross-check against an established library (`scipy.stats`, `statsmodels`,
  `scikit-posthocs`). If you re-implement a method to avoid a dependency, pin it
  to the library's output on fixtures.
- **Compare floats approximately.** Never assert exact float equality. Use
  `pytest.approx` (or `numpy.testing.assert_allclose`) with an appropriate
  tolerance.
- **Test the edge cases that produce silent wrongness:** empty input, a single
  data point, all-identical values (zero variance / zero entropy), ties in
  ranks, missing optional fields, and `NaN`/`None` handling.
- **Guard degenerate inputs explicitly.** Decide what a test returns when a group
  has < 2 samples, and make it explicit (skip with a recorded reason) rather than
  letting the library emit a `NaN` that flows downstream unnoticed.

---

## 6. Handling missing and partial data honestly

Real run artifacts have gaps — a provider that doesn't report token counts, a
log line that didn't get written, an interrupted run.

- **Distinguish "zero" from "absent."** A metric that is genuinely zero and one
  whose source data is missing are different facts; collapsing them corrupts
  aggregates. Use an explicit absent marker.
- **Gate metrics on data availability.** Compute a metric only when its inputs
  are present; exclude units lacking the data from that metric's analysis rather
  than imputing.
- **Report what was dropped.** If you exclude units or skip a comparison, log it.
  Silent exclusion reads downstream as "everything was included" when it wasn't.
- **Be cautious joining on proximity.** Timestamp/nearest-neighbor joins are
  approximate; a one-to-one assumption can mis-attribute records when events
  interleave. Document the tolerance and the assumption, and treat the resulting
  per-unit attributions as approximate where the join is.

---

## 7. Faithful visualization

Charts are arguments. They must not overstate or hide.

- **Don't drop data the analysis produced** without saying so. If a field has
  data, it should appear; only skip a chart when the field is genuinely empty.
- **Show uncertainty** where it exists — error bars, sample sizes, the
  denominator behind a rate.
- **Annotate significance honestly** — mark which differences passed the
  corrected test, not the raw one.
- **Keep rendering downstream of computation** so the figure reflects exactly the
  analyzed numbers (see `02`, §9).

---

## Review checklist (analytics-specific)

**Reproducibility**
- [ ] End-to-end runnable with one command; no manual steps?
- [ ] Inputs, code version, config, and library versions recorded per run?
- [ ] Every stochastic step seeded, with the seed recorded? Modern RNG
      (`default_rng`) over global seed?

**Method validity**
- [ ] Does each test's assumptions match the data (sample size, normality)?
      Non-parametric where appropriate?
- [ ] Is multiple-comparison correction applied and named when running batteries
      of tests?
- [ ] Are effect sizes / magnitudes reported alongside p-values?

**Metric correctness**
- [ ] Percentile/interpolation convention documented and consistent?
- [ ] Entropy log-base and TV-distance normalization correct and stated?
- [ ] Small-denominator rates carry their N?

**Robustness & testing**
- [ ] Statistics tested against known answers; floats compared approximately?
- [ ] Degenerate inputs (empty, singleton, zero-variance, ties, missing)
      handled explicitly?
- [ ] "Zero" vs "absent" distinguished; dropped units logged?

**Presentation**
- [ ] Charts faithful — no silent drops, uncertainty shown, significance honest?

---

## See also

- `01-system-classification.md` — why analytics + reporting pipelines inherit
  research-software standards.
- `02-architecture-principles-and-patterns.md` — the structural patterns these
  concerns sit inside (purity, idempotency, error boundaries).
- `04-reading-list.md` — method and guideline sources: Sandve et al. and Wilson
  et al. (reproducibility rules), NumPy RNG docs (seeds), Kruskal & Wallis,
  Dunn, Holm, Shannon (methods), Hollander–Wolfe–Chicken (non-parametric
  reference), scipy/statsmodels/scikit-posthocs docs, pytest docs.
