# Reading the C2ST: how the classifier two-sample test is built

The Classifier Two-Sample Test (C2ST) is the strongest single fidelity check in the stack.
Its logic: **if a classifier cannot tell real profiles from synthetic ones, the two are
statistically indistinguishable.** This note unpacks the machinery behind the two headline
numbers — `auc` and `p_value` — because several non-obvious steps (class balancing, the
rank-based AUC, the permutation p-value, the two backends) determine what those numbers mean.
It lives alongside the [TV ½-factor](tv-distance-half-factor.md),
[KL bits & log-ratio](kl-divergence-bits-and-log.md), and
[coherence-score](coherence-score-explained.md) notes. Code: `multivariate.py:c2st` and
`evaluator.py:_compute_c2st`.

## Step 1 — encode the whole profile (one-hot)

Each individual becomes a fixed-width feature vector via `one_hot_encode`. Columns are laid
out block-by-block in `scheme.attributes` order; within a block, one column per category in
`scheme.categories[attr]` order, so the encoding is **identical across both populations**. A
value outside an attribute's category set — a synthetic-only value or a `None` — leaves that
attribute's whole block **all-zero** (an implicit "other"), rather than growing the matrix. So
the classifier sees complete joint profiles, not one attribute at a time.

## Step 2 — balance the classes

Real usually vastly outnumbers synthetic, and a classifier can score a high AUC just by
exploiting that imbalance. So the classes are **balanced by subsampling the larger down** to:

```
balanced_n = min(n_real, n_syn)
```

drawn **without replacement**. This is repeated `n_repeats = 5` times (fresh subsample each
time) and the results averaged, so the reported AUC/p-value are means over 5 balanced draws.
If `balanced_n < 2` (a tiny or failed synthetic population) both numbers degrade to `NaN`
without error.

## Step 3 — cross-validated AUC

Per repeat, real (label `0`) and synthetic (label `1`) are stacked and run through
**stratified k-fold cross-validation** (`eff_folds = max(2, min(folds, balanced_n))`, folds
from config, default 5). Every row is scored while held out, and the pooled out-of-fold scores
give one ROC-AUC. The AUC itself is computed by the **rank-based Mann–Whitney identity** (not a
threshold sweep):

```
AUC = ( Σ ranks(synthetic scores) − n_syn·(n_syn + 1)/2 ) / (n_syn · n_real)
```

with tie-aware average ranks (`scipy.rankdata`). A useful consequence: if the two populations
are identical the classifier's scores are effectively constant, ties dominate, and the AUC
comes out **exactly 0.5** — no spurious signal from a degenerate model.

## Step 4 — the permutation p-value

An AUC slightly above 0.5 could be noise. To test that, the labels are **shuffled**
`n_permutations = 200` times; for each shuffle the whole CV-AUC is recomputed, and the test
counts how many permuted AUCs reach or exceed the observed one. The p-value uses the standard
**add-one** estimator:

```
p_value = (1 + #{ perm AUC ≥ observed AUC }) / (1 + n_permutations)
```

Adding 1 to numerator and denominator means the p-value is never exactly 0 (the observed
labelling is itself one valid arrangement) and is bounded below by `1/201 ≈ 0.005`. A **high
p-value is good**: it says an AUC above 0.5 is not distinguishable from chance, i.e. the
populations look the same to the classifier.

## The two backends

`method` resolves to the backend actually used, reported in the `method` field:

| `method` config | Backend | What runs |
|-----------------|---------|-----------|
| `"sklearn"` / `"auto"` | **sklearn** if importable, else falls back to mmd | cross-validated **logistic regression** (`LogisticRegression(max_iter=1000)`, `predict_proba`) |
| `"mmd"` | **mmd** (numpy/scipy only) | nearest-centroid / **linear-MMD** surrogate: direction `μ_syn − μ_real` from the training rows, each held-out row scored by its projection onto it |

Any other value raises. The SCB scheme sets `method="sklearn"`, so with the `[analysis]` extra
installed you get logistic-regression AUCs; without scikit-learn the module still runs via the
MMD fallback. Config defaults when the `c2st` block is absent: `folds=5, method="auto",
seed=0`; the primitive's own defaults `n_repeats=5, n_permutations=200` are used because the
evaluator passes only method/folds/seed.

## How to read the pair of numbers

- **`auc` ≈ 0.5** → indistinguishable (best); `auc → 1.0` → trivially separable (the joint
  profile is clearly wrong). This is the direction that matters — lower is better.
- **`p_value` high** → cannot reject "indistinguishable" (good); low → the separability is
  real.
- **`balanced_n`** tells you how much data actually drove the test (the smaller population's
  size); a very small `balanced_n` means treat both numbers cautiously.
- Because AUC is bounded below at 0.5 in interpretation but the raw statistic can dip slightly
  under 0.5 on noise, read "≈ 0.5" as the target, not "exactly 0.5."
