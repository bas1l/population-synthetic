# Comparison metrics — a plain-language guide

This document explains **every statistical metric** the comparison pipeline computes
when it scores a synthetic population against a real one. It is meant to be read on its
own: no prior knowledge of the codebase is assumed. Each metric gets a plain-language
description, the formula in words, a small worked example, and how to read the number.

> 📊 **Prefer a visual walkthrough?** A designed, self-contained HTML companion to this guide —
> with a purpose-built chart for every metric — lives at
> [`comparison-metrics-report.html`](comparison-metrics-report.html). Open it in any browser
> (no assets or server needed). This markdown remains the canonical text source.

Throughout, the two populations being compared are:

- **A = the real / reference population** (e.g. the SCB-sampled Swedish population).
- **B = the synthetic population** (e.g. LLM-generated personas).

Every individual is described by a set of categorical **attributes** (e.g. `age_group`,
`sex`, `education_level`, `employment_status`). The exact attribute list, the allowed
categories for each, and which pairs/tuples get the joint tests all live in config (the
"comparison scheme") — not in code. The code (`analysis/fidelity/evaluator.py` and
`analysis/fidelity/multivariate.py`) just applies the metrics to whatever the scheme
declares.

> **Terminology — attribute vs. category (keep these two levels distinct).**
> - An **attribute** (also called a *field*) is one demographic dimension: `education_level`,
>   `age_group`, `sex`.
> - A **category** (also called a *category value*) is one possible *value* of an attribute:
>   for `education_level` the categories are Primary, Secondary, Tertiary.
>
> This matches the codebase: `scheme.categories[attr]` is the list of *values* for an
> attribute, so "category" here **always means a value, never the field**. Each marginal
> metric in §1 scores **one attribute** by aggregating over **that attribute's own
> categories** (the bars of its bar chart); it never mixes different attributes together.

> **Terminology — intentional exceptions (locked names).** A few identifiers, config keys,
> and output fields keep wording that does not read literally as "attribute"/"category". They
> are **contracts** — code identifiers exercised by logic, config keys read by fail-fast
> loaders, or serialized report/CSV headers consumed downstream — so renaming them would be a
> breaking migration, not a cleanup. They are all *correct* under the definitions above (or
> correct via the sanctioned `attribute` ⇄ `field` alias); they are listed here so the wording
> never gets "corrected" by mistake:
>
> - **`field` as an alias for attribute.** `charts._HIGH_CARDINALITY_FIELDS` (a set of
>   *attribute* names) and prose such as "SCB provides the field" / "no income-source field" /
>   "per-field grounding audit" all use `field` = attribute, exactly as this callout permits.
> - **`scheme.categories[attr]` / `scheme.attributes`.** `categories` maps each attribute to its
>   list of *values*; `attributes` is the list of dimensions. This is the vocabulary anchor and
>   stays as-is.
> - **Serialized report fields `"categories"` and `"attributes"`, and CSV headers `"attribute"`,
>   `"unmapped_categories"`, `attr_x` / `attr_y` / `v_real` / `v_syn` / `abs_delta_v`.** These are
>   the report/CSV contract; `"categories"` lists values, `"attribute(s)"` lists dimensions.
> - **Config keys `values`, `attributes`, `categories`, `joint_pairs`, `coherence_attributes`,
>   `grounded_joint_pairs`, `combination_checks`.** Read by the scheme loader, which raises on a
>   missing key. `values` always holds an attribute's *value* set (SSB's divergent
>   `output_categories` key is a separate, out-of-scope inconsistency).
> - **`sub-field` (raw DB columns).** In the mapping READMEs, `employment_type`'s raw record has
>   *sub-fields* (`attachment` + `hours`) matched by a "composite sub-field matcher". This is the
>   raw source-column sense of "field", distinct from `field = attribute`; it does not describe a
>   comparison attribute.

The metrics come in four families:

1. **Marginal (univariate)** — does each attribute have the right distribution *on its own*?
2. **Joint (legacy)** — do two attributes relate to each other the same way?
3. **Coherence (legacy)** — are individual people's attribute combinations realistic?
4. **Multivariate / joint fidelity (new)** — deeper, whole-profile and pairwise checks.

A quick mental model: families 1–3 ask increasingly demanding questions, and family 4
adds the strongest test of all — *can a classifier tell the two populations apart?*

---

## 1. Marginal (univariate) metrics

These look at **one attribute at a time** and compare its distribution in A vs B. Think
of it as comparing two bar charts (e.g. the age-group breakdown of the real population vs
the synthetic one). Computed in `evaluator.py:_marginal_metrics`, one set per attribute.

Running example for this section — the `education_level` distribution:

| Category      | Real A | Synthetic B |
|---------------|:------:|:-----------:|
| Primary       |  20%   |    10%      |
| Secondary     |  50%   |    55%      |
| Tertiary      |  30%   |    35%      |

### 1a. Total Variation distance (`tv_distance`)

**What it measures:** the single most intuitive "how different are these two bar charts"
number. It is the total probability mass you would have to move to turn one distribution
into the other.

**Formula (in words):** take the absolute difference in proportion for each category, add
them all up, and halve the total.

`TV = 0.5 × Σ |proportion_A(category) − proportion_B(category)|`

**Worked example:**
differences are Primary |0.20−0.10| = 0.10, Secondary |0.50−0.55| = 0.05,
Tertiary |0.30−0.35| = 0.05. Sum = 0.20, halved = **TV = 0.10**.

**How to read it:** ranges from **0 (identical)** to **1 (no overlap at all)**. Lower is
better. A TV of 0.10 means the two education distributions differ by 10 percentage points
of "misplaced" mass. This is the metric behind the **TV-similarity radar chart**
(`similarity = 1 − TV`, so higher is better on the radar).

> **Deep dive:** why is the sum multiplied by ½? See
> [Why total variation distance is multiplied by ½](comparison-metrics/tv-distance-half-factor.md)
> — short answer: without it you double-count the displaced mass and lose the clean 0-to-1 scale.

### 1b. Max absolute proportion difference (`max_diff`)

**What it measures:** the single worst category — the largest gap between A and B in any
one bar. TV aggregates the error across *all categories of the one attribute*; `max_diff`
reports the biggest single one.

**Formula (in words):** the maximum over categories of `|proportion_A − proportion_B|`.

**Worked example:** the differences were 0.10, 0.05, 0.05 → **max_diff = 0.10** (the
Primary category). If instead one category were off by 0.30 and the rest tiny, TV might
still look modest but `max_diff = 0.30` would flag that one bad bar.

**How to read it:** 0 to 1, lower is better. Useful for catching "mostly fine but one
category is badly wrong."

### 1c. KL divergence (`kl_divergence`)

**What it measures:** an information-theoretic "surprise" — how many extra **bits** you
waste, on average, if you encode the synthetic distribution using a code built for the
real one. It punishes B for putting probability where A has almost none, more harshly than
TV does.

**Formula (in words):** `D_KL(B ‖ A) = Σ p_B(c) × log₂( p_B(c) / p_A(c) )`, summed over
categories. Each term is a category's **log-ratio** `log₂(p_B/p_A)` — its "surprise", which
is 0 when B and A agree, positive when B over-represents the category, negative when B
under-represents it — **weighted by `p_B(c)`**, how often the category occurs in B. The
**base-2 log is what makes the answer come out in bits.** The pipeline uses **Laplace
smoothing** (add 1 to every category count before turning counts into probabilities) so a
category that is empty in one population never causes a divide-by-zero or an infinite result.

**Worked example:** with the education proportions above, each term is `p_B × log₂(p_B/p_A)`:
Primary `0.10 × log₂(0.10/0.20) = −0.100`, Secondary `0.55 × log₂(0.55/0.50) ≈ +0.076`,
Tertiary `0.35 × log₂(0.35/0.30) ≈ +0.078`. They sum to **≈ 0.05 bits** — small, because the
distributions are close. Note Primary's term is *negative* (B under-shoots there), yet the
total stays positive, as it always must.

**How to read it:** **0 = identical**; there is no upper bound, higher is worse. It is
*asymmetric* — `D_KL(B‖A) ≠ D_KL(A‖B)` — and the code computes B-relative-to-A. Best used
for ranking, not as an absolute pass/fail.

> **Deep dive:** what the log-ratio means, why the base is 2 (bits vs nats), why the terms
> can be negative yet the total is never below zero, and how Laplace smoothing shifts it — see
> [Reading the KL divergence formula: bits and the log-ratio](comparison-metrics/kl-divergence-bits-and-log.md).

### 1d. Chi-squared goodness-of-fit p-value (`chi_sq_p`)

**What it measures:** a formal hypothesis test asking "could B's category counts
plausibly have been drawn from A's distribution, or is the difference too big to be
chance?" It accounts for **sample size** — the same percentage gap is more damning with
1,000 people than with 10.

**How it works (in words):** scale A's proportions up to B's sample size to get *expected*
counts, compare them to B's *observed* counts with the chi-squared statistic
`Σ (observed − expected)² / expected`, and convert to a p-value.

**Worked example:** if B has n = 1,000, A's proportions predict expected counts
Primary 200 / Secondary 500 / Tertiary 300, but B observed 100 / 550 / 350. The large
Primary shortfall (100 vs 200) produces a big chi-squared statistic and therefore a **tiny
p-value** → the difference is statistically significant.

**How to read it:** it is a **p-value in [0, 1]**, and the direction is the opposite of the
distance metrics:

- **High p (e.g. > 0.05)** → no significant difference detected → B *matches* A well. Good.
- **Low p (e.g. < 0.05)** → significant divergence. The summary prints a `*` next to these.

⚠️ Caveat: with a small synthetic population (n < 5) chi-squared is unreliable, and the
report prints a warning. Also note that with very large n, even trivial differences become
"significant" — so read `chi_sq_p` alongside TV, not instead of it.

---

## 2. Joint distribution metric (legacy)

### 2a. Joint chi-squared p-value (`joint_chi_sq`, per attribute pair)

**What it measures:** the marginals above check each attribute alone. This checks whether
**two attributes relate to each other** the same way in both populations — e.g. is the
age×education *cross-tabulation* consistent between A and B? A model can get every marginal
perfect yet still pair young age with a doctorate too often; this is the first test that
can catch that.

**How it works (in words):** for each configured attribute pair, build a contingency table
(cross-tab) for A and for B, **add them together**, and run `chi2_contingency` on the
combined table. Computed in `evaluator.py:_joint_chi_sq` for each pair in
`scheme.joint_pairs`.

**How to read it:** a **p-value**. As with the marginal chi-squared, higher = the two
populations' joint structure is consistent; low = significant difference in how the two
attributes co-vary.

> Note: this legacy test pools A and B into one table, so it is a coarse "are these
> distinguishable" signal. The newer **grounded joint TV** (§4c) and **Cramér's V delta**
> (§4b) give a finer, magnitude-based read on the same idea.

---

## 3. Individual coherence metric (legacy)

### 3a. Coherence score (`coherence.score`)

**What it measures:** are individual synthetic *people* realistic? A distribution can be
right in aggregate while still containing impossible individuals (e.g. a 7-year-old with a
PhD and full-time employment). This scores the fraction of synthetic individuals whose
**combination** of attributes actually occurs in the real population.

**How it works (in words):** from the real population A, build a lookup table of the
**empirical** (un-smoothed) probability of each combination of the coherence attributes —
for the Swedish scheme that tuple is `age_group × education_level × employment_status`. Then,
for each synthetic individual in B, look up their exact combination:

- if its real-population probability is **≥ the threshold** → count them as *plausible*;
- otherwise → *flag* them (records the id, the attribute values, and the probability).

`score = n_plausible / n_total_B`. Computed in `evaluator.py:compute_coherence`.

The **threshold is the whole test.** The Swedish scheme sets `coherence_threshold = 0.001`,
i.e. *a combination must occur in at least 0.1 % of the real population to count as
plausible* (≥ 10 people in a real population of 10,000). Because the table is un-smoothed, a
combination that **never appears in A** has probability exactly 0 — so flagging splits
naturally into **impossible** (zero support, or a missing attribute value → probability 0)
and **rare** (present in A but below the threshold). The tuple and threshold live in config
(`config/analysis/fidelity/{country}.json`); `coherence_attributes` is required and fails
loud if absent, while `coherence_threshold` defaults to `0.001`.

**Worked example:** with a real A of 10,000 (threshold ⇒ "≥ 10 occurrences") and a synthetic
B of 1,000: `age 30–39 · Tertiary · Employed` occurs 1,800 times (p = 0.18) → plausible;
`age 85+ · Tertiary · Employed full-time` occurs 6 times (p = 0.0006) → flagged as *rare*;
`age 7–12 · Tertiary · Employed` occurs 0 times → flagged as *impossible*. If 920 of the
1,000 land at or above the threshold, the coherence score is **0.92 (92%)** and the other 80
appear in the flagged list for inspection.

**How to read it:** 0 to 1, **higher is better**. A blunt "what fraction of my synthetic
people are demographically possible" number — but a high score is *cheap* when the threshold
is low (it mostly rules out the impossible, not the merely unusual), so read it alongside the
threshold value and §4d's impossible/rare split.

> **Deep dive:** what the threshold really means, the two ways a person gets flagged, the
> missing-value trap, why the tuple is kept small (curse of dimensionality), the "A is a
> finite sample" caveat, and how coherence relates to the §4d k-way metric — see
> [Reading the coherence score: the plausibility threshold](comparison-metrics/coherence-score-explained.md).

---

## 4. Multivariate / joint fidelity metrics (new)

These are the deepest checks, added to score how well the synthetic data reproduces the
*structure* of the real data — not just the shape of each attribute. Orchestrated by
`evaluator.py:compute_multivariate`; the maths lives in `multivariate.py`.

### 4a. C2ST — Classifier Two-Sample Test (`c2st`: `auc`, `p_value`)

**What it measures:** the single strongest overall fidelity test. The idea: if a machine
learning classifier **cannot tell real profiles apart from synthetic ones**, the synthetic
data is statistically indistinguishable from real — the gold standard. If a classifier
*can* separate them easily, something about the joint profile is off.

**How it works (in words):**
1. One-hot encode each individual's whole attribute profile into a feature vector.
2. Label real people `0` and synthetic people `1`.
3. **Balance the classes** by subsampling the larger population down to the size of the
   smaller (real usually vastly outnumbers synthetic), so the classifier can't cheat by
   always guessing the majority class. Repeated several times and averaged.
4. Train a classifier with cross-validation and measure its **ROC-AUC** — its ability to
   rank a random synthetic person as "more synthetic" than a random real one.
5. Backend: cross-validated **logistic regression** (scikit-learn) if installed, otherwise
   a numpy-only **nearest-centroid / linear-MMD** surrogate. The `method` field says which
   ran. A **permutation test** (shuffle the labels many times) gives the p-value.

**How to read the AUC:**

- **AUC ≈ 0.5** → the classifier is guessing; real and synthetic are **indistinguishable**.
  This is the *best* outcome.
- **AUC → 1.0** → trivially separable; the synthetic joint distribution is clearly wrong.
- The `p_value` tests whether an AUC above 0.5 is real or noise — a **high p-value is good**
  here (can't reject "indistinguishable"). Balanced n and NaN-degradation for tiny B are
  reported alongside.

The AUC is computed by the rank-based **Mann–Whitney identity** (so identical populations give
exactly 0.5), and the p-value is an **add-one permutation** p-value
`(1 + #{perm AUC ≥ observed}) / (1 + n_permutations)`, so it is never 0 and bottoms out near
`1/201 ≈ 0.005`. The SCB scheme tunes it with `folds=5, method="sklearn", seed=42`; the
primitive's `n_repeats=5, n_permutations=200` are used as-is.

**Worked example:** AUC = 0.52, p = 0.40 → excellent: a trained classifier does barely
better than a coin flip, so the whole-profile joint distribution is faithful. AUC = 0.95,
p = 0.005 → poor: profiles are easy to tell apart.

> **Deep dive:** the one-hot encoding, class balancing (`balanced_n = min(n_real, n_syn)`), the
> Mann–Whitney AUC, the permutation p-value, and the sklearn-vs-MMD backends — see
> [Reading the C2ST: how the classifier two-sample test is built](comparison-metrics/c2st-explained.md).

### 4b. Pairwise association fidelity — Cramér's V delta (`association`)

**What it measures:** whether the **strength of association between every pair of
attributes** is reproduced. Cramér's V is a 0–1 measure of how strongly two categorical
variables are related (0 = independent, 1 = one perfectly predicts the other). This metric
computes V for each attribute pair in *both* populations and reports how far apart they
are.

**How it works (in words):** for **every unordered pair** of the scheme's attributes (all
`15·14/2 = 105` pairs for the Swedish scheme, not just the three configured `joint_pairs`),
build the cross-tab and compute the **bias-corrected (Bergsma) Cramér's V** — a
small-sample-corrected version of the chi-squared-based association strength. Do this for A
(`v_real`) and B (`v_syn`), then take `abs_delta_v = |v_real − v_syn|` per pair. Summarised
across all pairs by:

- `mean_abs_delta_v` — the average gap, and
- `frobenius_norm` — the root-sum-of-squares of the gaps (penalises a few large errors).

Computed in `multivariate.py:association_matrix` / `cramers_v`.

**Worked example:** suppose age↔employment has V = 0.45 in real data (strongly related —
older people retire) but only V = 0.20 in synthetic (the model under-couples them). That
pair's `abs_delta_v = 0.25`. If most other pairs match closely, `mean_abs_delta_v` stays
low but this pair stands out in the per-pair table (also exported to CSV).

**How to read it:** `abs_delta_v`, `mean_abs_delta_v`, `frobenius_norm` are all **≥ 0,
lower is better** (0 = the association structure is perfectly reproduced). Unlike the joint
chi-squared p-value, this gives a **direction and magnitude** — you can see *which* pair is
wrong and by how much.

> **Deep dive:** the full Bergsma-corrected V formula (φ², the corrected row/column counts),
> why all 105 pairs are scored, and how `mean_abs_delta_v` vs `frobenius_norm` weight a single
> broken pair differently — see
> [Reading the association fidelity: Cramér's V delta](comparison-metrics/association-cramers-v-explained.md).

### 4c. Grounded joint total-variation distance (`joint_fidelity.pairs`)

**What it measures:** the same TV distance idea as §1a, but applied to a **two-attribute
joint distribution** instead of a single attribute. It is the total misplaced probability
mass across the full x×y grid of a pair.

**How it works (in words):** for a configured pair (x, y), build each population's joint
distribution over the fixed category grid, normalise, and compute
`TV = 0.5 × Σ_cells |p_A(x,y) − p_B(x,y)|`. Computed in `multivariate.py:joint_tv`.

Each pair also carries a `grounded` flag and a `basis` note: **grounded** pairs are ones
whose real joint is backed by an actual statistics-agency cross-tabulation (a defensible
ground truth); non-grounded ("reference") pairs are shown for context but not over-claimed
as validated. This distinction exists so downstream reporting (e.g. the paper) doesn't
present a made-up joint as if the agency published it.

**How to read it:** **0 (identical joint) to 1 (disjoint), lower is better**. Returns
`NaN` when either population has no individuals landing in the grid. It is the finer,
magnitude-based complement to the legacy joint chi-squared p-value.

> **Deep dive:** the per-population normalisation, the `NaN`-means-"not measurable" rule, and
> the full SCB pair table (5 grounded vs 3 reference, with the audit basis for each) — see
> [Reading the grounded joint TV: distance and the grounding flag](comparison-metrics/joint-tv-grounding-explained.md).
>
> **Why only two attributes?** The pairwise scope is a deliberate design choice — the largest
> joint that is both statistically estimable and backed by a real agency cross-tabulation, with
> the whole-population question delegated to §4a C2ST. See
> [Why the joint TV stays pairwise: two attributes, not all of them](comparison-metrics/joint-tv-why-pairwise.md).

### 4d. K-way combination plausibility (`combination_plausibility.checks`)

**What it measures:** a generalisation of the coherence score (§3a) to arbitrary
**k-attribute combinations**, and it splits the failures into two severities instead of a
single pass/fail.

**How it works (in words):** for each configured check (a tuple of k attributes and a
threshold), build the real joint probability table over that tuple, then classify each
synthetic individual:

- **impossible** — the combination has **zero support** in the real data (or contains a
  missing value). These are combinations the real population *never* produced.
- **rare** — the combination exists in real data but with probability **below the
  threshold**.
- **plausible** — at or above the threshold.

Reports `n_impossible` / `n_rare` / `n_plausible` and the fractions `fraction_impossible`
and `fraction_rare`. Computed in `evaluator.py:_compute_combination_plausibility`.

**Worked example:** for the tuple (age_group, education_level, employment_status) with
1,000 synthetic people: 950 plausible, 30 rare, 20 impossible →
`fraction_impossible = 0.02`, `fraction_rare = 0.03`. The 2% "impossible" are the ones to
worry about — real data never contained those combinations.

**How to read it:** `fraction_impossible` and `fraction_rare` are **≥ 0, lower is better**;
`fraction_impossible = 0` means every synthetic profile is at least possible in reality.
`NaN` when B is empty. For the same tuple and threshold this is exactly the coherence score
split by severity: `fraction_impossible + fraction_rare = 1 − coherence.score`.

> **Deep dive:** the exact three-way boundary rule (`p ≤ 0` impossible / `0 < p < threshold`
> rare / `p ≥ threshold` plausible), the fraction equations, and the precise count-for-count
> relationship to the §3a coherence score — see
> [Reading k-way combination plausibility: the severity split](comparison-metrics/combination-plausibility-explained.md).

---

## 5. Per-category method/model significance (cross-combo)

The metrics above score **one** synthetic population against the real baseline. A separate,
strictly-downstream process — `analysis/method_significance/` (`analyze_method_significance.py`) —
does not add a per-population metric; it takes the *whole grid* of per-attribute `tv_distance`
values across every (model × method × category) combo and asks a hypothesis-testing question:
**per country and per demographic attribute, does the generation method (the ordered strategy axis)
or the model significantly drive TV fidelity, and does the method-trend differ by model?**

The hard constraint is **n = 1 per (model, method, category) cell** — LLM generation has no seed, so
there are no within-cell replicates. The escape is to treat the ~15 demographic categories as the
blocking/replication factor, which maps the problem onto Demšar (2006), *Statistical Comparisons of
Classifiers over Multiple Data Sets* (models = classifiers, categories = datasets). Because TV is
bounded `[0, 1]` and heteroscedastic near 0, the headline tests are rank-based, every p-value carries
an effect size, and multiplicity is always named.

| Test | What it answers | Effect size | Multiplicity |
|------|-----------------|-------------|--------------|
| **Page's L** (ordered method trend, per attribute) | Does TV move monotonically along the 5 complexity-ordered methods? | linear + **quadratic** contrast (tests, doesn't assume, monotonicity) | BH-FDR across attributes |
| **Friedman + Iman–Davenport** (model omnibus, per attribute) | Do models differ on TV within this attribute? | Kendall's W (0–1 concordance) | BH-FDR across attributes |
| **Demšar model comparison** (overall) | Which models differ overall (categories as blocks)? | Nemenyi post-hoc → critical-difference (CD) diagram | Nemenyi CD |
| **Page's L** (overall method trend) | Does complexity move TV across all category × model blocks? | z (direction) | — |
| **Mixed model** `logit(TV) ~ model*method + (1\|category)` | Is the model × method **interaction** real, and which factor dominates? | η² variance shares (model / method / category / residual) | Wald joint test |

**Descriptive-only guardrail:** the *per-category* model × method interaction is **not estimable** at
n = 1 (zero residual df), so it is emitted **descriptively only** — a slope heatmap of the per-cell
TV(method) trend — and **no p-value is claimed at that grain**. The overall interaction *is*
estimable because the categories supply the replication. Every significance annotation on the charts
is drawn from the **BH-corrected** p-values, never the raw ones. Outputs land under
`03_Analysis/method_significance/` (`{country}_method_significance.json` / `.csv` + a slope heatmap,
CD diagram, factor-dominance bar, and per-attribute trend facets). This process needs the optional
`[analysis]` extra (statsmodels + scikit-posthocs). Design detail lives in the plan
`docs/development/plans/…/per-category-method-model-significance.md` and the thread recap
`docs/development/model-method-significance-recap.md`.

## Cheat sheet — direction and range at a glance

| Metric | Family | Range | Good value | Higher is… |
|--------|--------|-------|-----------|-----------|
| TV distance (`tv_distance`) | marginal | 0–1 | near 0 | worse |
| Max diff (`max_diff`) | marginal | 0–1 | near 0 | worse |
| KL divergence (`kl_divergence`) | marginal | 0–∞ | near 0 | worse |
| Chi-squared GoF (`chi_sq_p`) | marginal | 0–1 (p-value) | **> 0.05** | **better** |
| Joint chi-squared (`joint_chi_sq`) | joint | 0–1 (p-value) | **high** | **better** |
| Coherence score (`coherence.score`) | coherence | 0–1 | near 1 | **better** |
| C2ST AUC (`c2st.auc`) | multivariate | 0.5–1 | **near 0.5** | worse |
| C2ST p-value (`c2st.p_value`) | multivariate | 0–1 | **high** | **better** |
| Cramér's V delta (`abs_delta_v`, `mean_abs_delta_v`) | multivariate | 0–1 | near 0 | worse |
| Grounded joint TV (`joint_tv`) | multivariate | 0–1 | near 0 | worse |
| Fraction impossible / rare | multivariate | 0–1 | near 0 | worse |

**The one trap to remember:** the two **p-value** metrics (chi-squared GoF, joint
chi-squared) and the **C2ST p-value** run *opposite* to the distances — for those, a **high
value is good** (no detectable difference). Every distance/divergence/AUC metric is "lower
is better."

## Where each metric lives in code

- Marginal metrics (TV, max diff, KL, chi-squared): `analysis/fidelity/evaluator.py:_marginal_metrics`
- Joint chi-squared: `analysis/fidelity/evaluator.py:_joint_chi_sq`
- Coherence: `analysis/fidelity/evaluator.py:compute_coherence`
- C2ST: `evaluator.py:_compute_c2st` → `multivariate.py:c2st`
- Cramér's V association: `evaluator.py:_compute_association` → `multivariate.py:association_matrix` / `cramers_v`
- Grounded joint TV: `evaluator.py:_compute_joint_fidelity` → `multivariate.py:joint_tv`
- K-way combination plausibility: `evaluator.py:_compute_combination_plausibility`
- Report assembly / CSV export: `evaluator.py:generate_report`, `write_csv_summary`, `write_association_csv`

## Table + figure artifacts per metric

Every metric is written into the per-slug JSON report; most also emit a companion CSV table
and PNG figure. The single fan-out point is
`analysis/fidelity/artifacts.py:write_comparison_artifacts` (called by all three comparison
drivers), which resolves CSVs as siblings of `{slug}.json` and figures into the `{slug}/`
charts dir.

| Metric | CSV writer (`evaluator.py`) | Figure (`charts.py`) | Artifact files |
|--------|-----------------------------|----------------------|----------------|
| Marginals | `write_csv_summary` | `plot_comparison_charts`, `plot_radar_comparison` | `{slug}.csv`, `{slug}_{attr}.png`, `{slug}_radar.png` |
| Joint chi-squared *(legacy)* | `write_joint_chi_sq_csv` | `plot_joint_chi_sq` | `{slug}_joint_chi_sq.csv/.png` |
| Coherence *(legacy)* | `write_coherence_csv` | `plot_coherence` | `{slug}_coherence.csv/.png` |
| C2ST | `write_c2st_csv` | `plot_c2st` | `{slug}_c2st.csv/.png` |
| Cramér's V association | `write_association_csv` | `plot_association_heatmap` | `{slug}_association.csv`, `{slug}_association_heatmap.png` |
| Grounded joint TV | `write_joint_fidelity_csv` | `plot_joint_fidelity` | `{slug}_joint_fidelity.csv/.png` |
| K-way combination plausibility | `write_combination_plausibility_csv` | `plot_combination_plausibility` | `{slug}_combination_plausibility.csv/.png` |

The scored attributes, category sets, joint pairs, coherence tuples, grounded-joint pairs,
combination checks, and C2ST tuning are all defined in the per-country comparison scheme
config, loaded via `analysis/fidelity/scheme.py` — never hardcoded.
