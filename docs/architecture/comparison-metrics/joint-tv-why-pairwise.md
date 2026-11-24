# Why the joint TV stays pairwise: two attributes, not all of them

The grounded joint total-variation distance (§4c) is defined over a pair — a **two-attribute**
joint distribution — and the natural question is *why stop at two?* If the point is to check
whether the synthetic population reproduces the real one's structure, why not compute a single
TV over the **full** joint of all attributes at once? This note is the design-philosophy
companion to the [grounding note](joint-tv-grounding-explained.md): that one explains what the
number and its `grounded` flag *mean*; this one explains why the scope is deliberately capped at
pairs. The short answer is that the pairwise choice sits at the intersection of two hard limits —
**what is statistically estimable** and **what has a real ground truth** — and that the
whole-population question is answered by *other* metrics, not by widening this one.

## 1. The full joint is not estimable — the curse of dimensionality

TV distance is computed cell-by-cell over a contingency table: you bin both populations into the
same grid of category combinations, normalise, and sum the absolute per-cell gaps. That only
produces a meaningful number when the cells are **populated** — a cell whose count is 0 or 1 in a
finite sample carries no reliable probability estimate.

The number of cells is the **product** of the per-attribute category counts, so it explodes with
the number of attributes:

```
cells(pair)      = |X| · |Y|                 ≈ 5 · 5            = 25
cells(full joint) = |A₁| · |A₂| · … · |A₁₅|   ≈ 5¹⁵ ≈ 3.1 · 10¹⁰
```

The Swedish scheme carries **15 demographic attributes**. Even at a modest five categories each,
the full joint has on the order of **thirty billion** cells — against a real sample of a few
thousand people. Essentially every cell would be empty; the handful that aren't would hold one or
two individuals. A TV distance over that table would be almost exactly `1.0` for *any* two
distinct finite samples — including two independent draws from the **same** real population — so
it measures sampling noise, not fidelity. A two-attribute grid (tens of cells) stays dense enough
that each cell's proportion is a stable estimate, which is the only regime in which TV is
informative. This is the same argument that keeps the [coherence tuple deliberately
small](coherence-score-explained.md); the joint TV inherits it.

## 2. The full joint has no ground truth to compare against

Sparsity alone would already rule out the full joint, but there is a second, independent reason
that is specific to this project's **no-synthetic-distributions** principle — the core invariant
that every real distribution must trace to a live statistical-agency API response. A joint TV is
only trustworthy — *grounded* — when the
**real** side `p_A(x, y)` is an actual national-statistics-agency **cross-tabulation**, not a
number this pipeline synthesised. Agencies (SCB, ISTAT, …) routinely publish **two-way**
conditional cross-tabs; they very rarely publish three-way tables, and never a fifteen-way one.

So a full-joint "real" distribution simply **does not exist** to compare against. Any all-attribute
reference would have to be assembled inside this repo from lower-order marginals — exactly the
"forced independence" / marginal-product construction that the `grounded` flag exists to flag as
*not* API-identical. Widening the scope past pairs would therefore not just be noisy; it would be
**ungroundable by construction** — a comparison against a made-up target dressed up as reality.
The pairwise ceiling is the largest joint for which an agency ground truth can still exist.

## 3. Why pairwise specifically — not three-way or four-way

Pairs are the sweet spot where both constraints are still satisfied simultaneously:

| Scope | Cells (≈5 cats each) | Estimable from a few thousand? | Agency cross-tab exists? |
|-------|:--------------------:|:------------------------------:|:------------------------:|
| Single attribute (§1a) | 5 | yes | yes (marginals) |
| **Pair (§4c)** | **25** | **yes** | **yes (2-way cross-tabs)** |
| Triple | 125 | marginal | rarely |
| Full 15-way | ~3 · 10¹⁰ | no | no |

Two attributes is the **highest order** at which a cell is still typically backed by dozens of
observations *and* a published real cross-tab still exists. Go one step further and the counts
thin out while the agency ground truth disappears — you lose both guarantees at once.

## 4. The whole-population question is answered elsewhere

Capping the joint TV at pairs is **not** a decision to ignore all-attribute fidelity. That
question is real, and the report answers it — with metrics purpose-built to survive high
dimensionality instead of a contingency table that cannot:

- **[§4a C2ST](c2st-explained.md)** — a classifier two-sample test trains a model to tell real
  from synthetic individuals across **all** one-hot attributes at once. It probes the *whole*
  joint without ever materialising the joint table: a classifier generalises across sparse cells
  where a raw histogram would just see zeros. This is the true all-attribute fidelity check.
- **[§4d k-way plausibility](combination-plausibility-explained.md)** — checks higher-order
  attribute *combinations* for impossibility/rarity, again without needing a dense joint.
- **[§4b Cramér's V delta](association-cramers-v-explained.md)** — sweeps **all** 105 pairs, but
  reduces each to a single scalar association, so the full pairwise structure is summarised
  without the sparsity blow-up.

Read together, the §4 family is a division of labour: C2ST owns the *whole* joint, §4c owns the
*grounded, interpretable, per-pair magnitude* — the one place you can point at a specific pair,
say "the synthetic joint is off by this much," and back the claim with a real cross-tab. Widening
§4c would make it a worse version of §4a while destroying the very grounding that makes it worth
reporting.

## 5. Where this sits in the wider literature

The pairwise choice is not a local quirk; it is the standard move in synthetic-data fidelity
evaluation. Because directly estimating a statistical divergence over a high-dimensional joint is
defeated by the curse of dimensionality, benchmark frameworks "predominantly rely on
low-dimensional surrogate metrics" — one-way and two-way (pairwise) marginals — and TV distance is
the workhorse statistic applied to them. Representative references:

- *Systematic / Principled Assessment of Tabular Data Synthesis* (arXiv **2402.06806**) —
  one- and two-way marginals as the standard fidelity surrogates; TV distance and KS test on them.
- *Benchmarking Synthetic Tabular Data: A Multi-Dimensional Evaluation Framework*
  (arXiv **2504.01908**) — full high-dimensional joints "not feasible due to the curse of
  dimensionality," motivating low-order surrogates.
- *Discriminative Estimation of Total Variation Distance* (arXiv **2405.15337**) — TV as a
  histogram absolute error bounded in `[0, 1]`.

What this project adds on top of the standard practice is the `grounded` flag (§2 above): it does
not just use pairwise marginals because they are tractable, it restricts the *reported* pairs to
those an agency actually cross-tabulated, so a low `joint_TV` is a claim about reality rather than
about an internally-assembled reference.

## How to read it (design summary)

- **Two attributes is a ceiling, not a shortcut.** It is the largest joint that is both estimable
  from a finite sample and backed by a real cross-tabulation.
- **Not seeing an all-attribute TV is by design.** The whole-joint question lives in
  [§4a C2ST](c2st-explained.md); read that for population-wide fidelity.
- **Pair with the [grounding note](joint-tv-grounding-explained.md).** Scope (this note) and
  trust (the `grounded` flag) are the two halves of interpreting §4c.
