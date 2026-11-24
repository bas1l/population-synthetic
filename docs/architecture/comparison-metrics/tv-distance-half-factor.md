# Why total variation distance is multiplied by ½

Total variation distance sums the absolute per-category differences and then **halves**
the total:

```
TV(A, B) = ½ Σ_c |p_A(c) − p_B(c)|
```

This note explains why the ½ is there. Short answer: without it you **double-count** the
displaced probability mass, and the metric loses its clean 0-to-1 scale.

## The intuition

TV measures how much probability mass you must *move* to turn distribution B into
distribution A. Every unit of mass that is "missing" from one category must have gone
*somewhere else* — it reappears as "excess" in another category. So when you sum
`|p_A − p_B|` over all categories, you count that same displaced mass **twice**: once at
the category it left, once at the category it arrived in. Halving corrects the
double-count, so TV equals the actual amount of mass moved.

## Worked example

Using the `education_level` example from [comparison-metrics.md](../comparison-metrics.md):

| Category  |  A   |  B   | \|A−B\| |
|-----------|:----:|:----:|:-------:|
| Primary   | 0.20 | 0.10 |  0.10   |
| Secondary | 0.50 | 0.55 |  0.05   |
| Tertiary  | 0.30 | 0.35 |  0.05   |
| **Sum**   |      |      | **0.20**|

B has 0.10 *too little* Primary mass. That exact 0.10 had to be redistributed elsewhere —
and indeed it reappears as +0.05 Secondary and +0.05 Tertiary. The "deficit" side sums to
0.10 and the "surplus" side sums to 0.10; the raw sum of `|A−B|` is 0.20, which counts both
sides. The real answer — "how much mass actually moved" — is **0.10**, i.e. `0.5 × 0.20`.

## The formal reason

For any two probability distributions, the positive differences and the negative
differences are always equal in magnitude, because both distributions sum to 1:

```
Σ_c (p_A(c) − p_B(c)) = Σ_c p_A(c) − Σ_c p_B(c) = 1 − 1 = 0
```

So `Σ over deficit categories = Σ over surplus categories`, and each equals half of
`Σ |p_A − p_B|`. Taking either side alone (equivalently, half the total) gives the
canonical definition, which also equals the largest probability gap on any event:

```
TV(A, B) = ½ Σ_c |p_A(c) − p_B(c)| = max over any category-set S of |P_A(S) − P_B(S)|
```

That second form is why the ½ matters: it is what makes TV bounded in **[0, 1]** and
interpretable as "the largest probability gap you could observe on any event." Without the
½, identical distributions would still give 0, but completely disjoint ones would give 2
instead of 1 — the metric would lose its clean 0-to-1 scale.

So the ½ is not a fudge factor; it is part of the standard definition, and it is what makes
`TV = 0.10` read as "10% of the mass is in the wrong place" and `1 − TV` a valid similarity
for the TV-similarity radar chart.
