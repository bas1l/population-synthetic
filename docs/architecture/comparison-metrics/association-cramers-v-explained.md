# Reading the association fidelity: Cramér's V delta

This metric asks whether the **strength of association between every pair of attributes** is
reproduced. It computes a 0–1 association measure — the bias-corrected Cramér's V — for each
attribute pair in *both* populations and reports how far apart they are. This note explains the
V formula (including Bergsma's small-sample correction), which pairs are scored, and how the
per-pair gaps roll up into `mean_abs_delta_v` and `frobenius_norm`. Code:
`multivariate.py:cramers_v` / `association_matrix` and `evaluator.py:_compute_association`. See
also the [joint-TV note](joint-tv-grounding-explained.md), which measures the same pairs a
different way.

## What Cramér's V is

Cramér's V summarises a contingency table's association as a single number in `[0, 1]`:
`0` = the two attributes are independent, `1` = one perfectly predicts the other. It is built
from the chi-squared statistic of the cross-tab, normalised by sample size and table shape so
it is comparable across tables of different dimensions.

## The bias-corrected (Bergsma) formula

The plain `V = sqrt( (χ²/n) / min(r−1, c−1) )` is biased upward for small samples — it reports
spurious association even for independent data. The pipeline uses the **Bergsma bias
correction**:

```
φ²        = χ² / n
φ²_corr   = max( 0 , φ² − (r−1)(c−1)/(n−1) )
r_corr    = r − (r−1)² / (n−1)
c_corr    = c − (c−1)² / (n−1)

V = sqrt( φ²_corr / min(r_corr − 1, c_corr − 1) )
```

where `n` is the table total and `r`, `c` are the numbers of **observed** rows/columns
(all-zero rows and columns are trimmed first, so empty categories don't distort the shape).
The `max(0, …)` floors the corrected φ² at zero, so an independent pair returns exactly `0.0`
rather than a small positive artefact. Degenerate tables — total ≤ 1, fewer than two effective
rows or columns, or a non-positive corrected denominator — return `0.0` with no
divide-by-zero, so a tiny synthetic population never raises here.

## Which pairs are scored

`association_matrix` iterates **every unordered pair** of `scheme.attributes` — for the
15-attribute Swedish scheme that is all `15·14/2 = 105` pairs, not just the three configured
`joint_pairs`. Each pair's cross-tab is built over the scheme's **fixed category grid** (values
outside the grid, including `None`, are dropped), so the same grid is used for A and B. Pairs
are keyed `(attr_x, attr_y)` with `attr_x` before `attr_y` in attribute order.

## The delta and its summaries

For each shared pair the evaluator computes V in both populations and takes the absolute gap:

```
abs_delta_v(pair) = | V_real(pair) − V_syn(pair) |
```

Then two summaries over the vector of per-pair deltas:

```
mean_abs_delta_v = mean( abs_delta_v )                        # average gap
frobenius_norm   = sqrt( Σ abs_delta_v² )                     # root-sum-of-squares
```

The two summaries answer different questions. `mean_abs_delta_v` is the typical error across
all pairs; `frobenius_norm` (the Euclidean norm of the delta vector) **penalises a few large
errors** more than many tiny ones, so a single badly-broken pair moves it more than it moves
the mean. Both are `NaN` only when there are no pairs at all.

## Worked example

Suppose `age_group ↔ employment_status` has `V_real = 0.45` (strongly related — older people
retire) but `V_syn = 0.20` (the model under-couples them): `abs_delta_v = 0.25`. If the other
104 pairs match closely (say all `≤ 0.05`), `mean_abs_delta_v` stays low, but this pair
dominates the `frobenius_norm` and stands out in the per-pair table (also exported to CSV via
`write_association_csv`).

## How to read it

- `abs_delta_v`, `mean_abs_delta_v`, `frobenius_norm` are all **≥ 0, lower is better**;
  `0` means the association structure is perfectly reproduced.
- Unlike the legacy joint chi-squared **p-value**, this gives a **direction and magnitude** —
  you can see *which* pair is wrong and by *how much*, and whether the model over- or
  under-couples it (compare `V_syn` against `V_real`).
- Because it scores all pairs, scan the per-pair table for outliers rather than reading only
  the summary — a low mean can hide one broken pair that `frobenius_norm` will flag.
