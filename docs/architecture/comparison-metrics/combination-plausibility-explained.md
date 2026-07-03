# Reading k-way combination plausibility: the severity split

K-way combination plausibility generalises the [coherence score](coherence-score-explained.md)
in two ways: it works for an **arbitrary k-attribute tuple** (not just the fixed triple), and
it **splits the failures by severity** — impossible vs rare — instead of collapsing them into a
single "flagged" bucket. This note gives the equations, the exact classification rule, and the
precise relationship back to coherence. Code: `evaluator.py:_compute_combination_plausibility`.

## The joint table (same as coherence)

For each configured check — a tuple of `k` attributes plus a `threshold` — the evaluator builds
the **empirical, un-smoothed** joint probability table from the real population A, exactly as
[coherence](coherence-score-explained.md) does:

```
p_A(c) = N_A(c) / Σ_c' N_A(c')
```

counting only real individuals with no missing value in the tuple. A combination unseen in A
has `p_A(c) = 0`.

## The three-way classification

Each synthetic person's combination `cᵢ` is sorted into one of three buckets — note the
**boundaries** carefully:

```
p_A(cᵢ) ≤ 0            → impossible   (zero real support, or a missing value in the tuple)
0 < p_A(cᵢ) < threshold → rare         (present in A, but below the threshold)
p_A(cᵢ) ≥ threshold     → plausible
```

So `impossible` is the `p = 0` boundary (including any `None` in the tuple, which forces
`p = 0`), `rare` is the open interval below the threshold, and `plausible` is at or above it.
The reported fractions are over **all** of B:

```
fraction_impossible = n_impossible / N_B
fraction_rare       = n_rare / N_B
```

both `NaN` when `N_B = 0`. The check also reports the raw counts `n_impossible`, `n_rare`,
`n_plausible`, the tuple `attributes`, `k`, and the `threshold` used.

## Worked example

For the tuple `(age_group, education_level, employment_status)` at `threshold = 0.001` with
1,000 synthetic people: 950 plausible, 30 rare, 20 impossible →
`fraction_impossible = 0.020`, `fraction_rare = 0.030`. The **2 % impossible** are the ones to
worry about — combinations the real population *never* produced; the 3 % rare are a softer flag.

## Exact relationship to the coherence score (§3a)

Both build the same table and compare to a threshold, so for the **same tuple and threshold**
the counts line up exactly:

```
n_plausible (§4d)               = n_plausible (§3a)
n_impossible + n_rare (§4d)     = n_flagged (§3a)
fraction_impossible + fraction_rare (§4d) = 1 − coherence.score (§3a)
```

In other words, §4d is coherence with the flagged bucket **split by severity** and generalised
to any `k`. The Swedish scheme configures one check — the coherence triple, `k = 3`,
`threshold = 0.001` — so here §4d is precisely the severity-resolved view of the coherence
score. Add more `combination_checks` in config to probe other tuples (all fail loud if
malformed; the block is optional and defaults to empty).

## How to read it

- `fraction_impossible` and `fraction_rare` are **≥ 0, lower is better**;
  `fraction_impossible = 0` means every synthetic profile is at least *possible* in reality.
- Weight `fraction_impossible` more heavily than `fraction_rare`: impossible means "never seen
  in real data," while rare can partly reflect thin coverage in A (the same finite-sample
  caveat as coherence — A is a sample, not the true population).
- Read it together with the coherence score: coherence gives the headline "% plausible," §4d
  tells you how bad the rest are.
