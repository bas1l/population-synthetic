# Reading the coherence score: the plausibility threshold

The coherence score asks a blunt question: **what fraction of the synthetic people are
demographically possible?** A population can match every marginal and still be built out of
impossible individuals — a 7-year-old with a PhD and a full-time job. Coherence catches those
by checking each synthetic person's *combination* of attributes against the real population.

```
score = n_plausible / n_total_B
```

This note explains what the "plausibility" test actually is: the joint table it is built
from, the **threshold** that decides plausible-vs-flagged, the two ways a person gets flagged,
and how the score relates to the newer k-way plausibility metric (§4d). It is the coherence
counterpart to the [TV ½-factor](tv-distance-half-factor.md) and
[KL bits & log-ratio](kl-divergence-bits-and-log.md) notes.

## The equations

Three quantities, and only one of them is computed from the data.

**1. The real-population probability of a combination `c`** — the empirical relative frequency
in A, un-smoothed:

```
p_A(c) = N_A(c) / Σ_c' N_A(c')
```

where `N_A(c)` is the number of real individuals whose combination equals `c`, and the
denominator sums over every combination — i.e. `total_A`, counting only real individuals with
**no missing** coherence attribute. A combination unseen in A has `p_A(c) = 0`.

**2. The threshold `τ`** — *not calculated from the data.* It is a fixed config constant,
`τ = coherence_threshold` (`0.001` for the Swedish scheme; defaults to `0.001` when the key is
absent). It is the same value regardless of population size, so `τ = 0.001` means "occurs in
≥ 0.1 % of real A" — the corresponding head-count (≈ 10 people when |A| = 10,000) scales with
A, but `τ` itself does not.

**3. The score** — the fraction of synthetic people B whose combination clears the bar:

```
score = n_plausible / N_B
      = ( 1 / N_B ) · Σ_{i ∈ B}  𝟙[ p_A(cᵢ) ≥ τ ]
```

where `cᵢ` is synthetic person `i`'s combination, `𝟙[·]` is 1 when the condition holds and 0
otherwise, and `N_B` is the size of **all** of B (`self.n_b`). Two edge conventions:
`p_A(cᵢ) = 0` when `cᵢ` is unseen in A *or* person `i` has any missing coherence attribute (so
they are flagged); and `score = 0.0` when `N_B = 0`. The returned value is rounded to 4
decimals. Equivalently: `score = 1 − (n_flagged / N_B)`.

## The joint table is empirical, from A, and un-smoothed

From the **real** population A the evaluator counts every occurrence of the coherence tuple —
for the Swedish scheme that tuple is `(age_group, education_level, employment_status)` — and
normalises the counts to probabilities:

```
joint_probs[combination] = count_in_A(combination) / total_A
```

Two details matter:

- **No smoothing.** Unlike KL divergence (which Laplace-smooths so no cell is ever exactly
  zero), coherence uses the raw empirical frequency. A combination that **never appears in A**
  therefore has probability **exactly 0** — which is the whole point: it lets the metric
  distinguish "impossible" from merely "rare".
- **Real individuals with a missing coherence attribute are dropped** from the table (a `None`
  in the tuple is not counted), so the table is built only from fully-specified real people.

## The threshold is the whole ballgame

Each synthetic person is looked up in that table and compared against a single number, the
**coherence threshold**:

- probability **≥ threshold** → **plausible** (counted toward the score);
- probability **< threshold** → **flagged** (recorded for inspection).

The Swedish scheme sets `coherence_threshold = 0.001`. Read literally: *a combination must
occur in at least 0.1 % of the real population to count as plausible.* For a real population of
10,000 people that means a combination needs **≥ 10 real occurrences**; anything rarer is
flagged. Raising the threshold makes the test stricter (more synthetic people flagged);
lowering it toward 0 makes it lenient, until at the limit only genuinely **zero-support**
combinations are flagged.

The threshold and the tuple both live in config
(`config/analysis/comparison/{country}.json`), never in code. `coherence_attributes` is a
**required** key — a missing one raises loudly rather than falling back to a baked-in list —
while `coherence_threshold` defaults to `0.001` when absent.

## Two ways to be flagged (and a missing-value trap)

A synthetic person falls below the threshold for one of two reasons, and the distinction is
worth keeping in mind even though the legacy score collapses them into one "flagged" bucket:

| Reason | Real-data probability | Meaning |
|--------|:---------------------:|---------|
| **Impossible** | exactly `0` | The combination never occurs in A — the real population *never produced it*. |
| **Rare** | `0 < p < threshold` | The combination exists in A but is rarer than 0.1 %. |

There is also a **missing-value trap**: if a synthetic person has a `None` in any coherence
attribute, their probability is set to `0` and they are flagged as if impossible. So an
incomplete synthetic profile counts *against* coherence — a fail-fast choice, not an oversight.

Every flagged person is recorded with their `id`, the three attribute values, and the looked-up
`probability` (to 6 decimals), and the run summary prints the list so you can inspect exactly
*which* individuals and *which* combinations tripped the check.

## Worked example

Take a real population A of 10,000 people (so the 0.001 threshold is "≥ 10 occurrences") and a
synthetic B of 1,000:

| Synthetic person's combination | occurrences in A | probability | verdict |
|--------------------------------|:----------------:|:-----------:|---------|
| age 30–39 · Tertiary · Employed | 1,800 | 0.1800 | ✅ plausible |
| age 85+ · Tertiary · Employed full-time | 6 | 0.0006 | ⚠️ flagged (**rare**) |
| age 7–12 · Tertiary · Employed | 0 | 0.0000 | ❌ flagged (**impossible**) |

If 920 of the 1,000 synthetic people land in cells at or above the threshold, then
`score = 920 / 1000 = 0.92`, and the other 80 — a mix of rare and impossible — go to the
flagged list.

## Why the tuple is deliberately small — the curse of dimensionality

Coherence is a *joint* check, so it inherits the curse of dimensionality. Each attribute you
add to the tuple multiplies the number of possible cells and thins the counts spread across
them, so more and more real combinations fall below any fixed threshold — and more synthetic
people get flagged even when they are marginally unremarkable. A three-attribute tuple keeps
the joint dense enough that "below 0.1 %" still means "genuinely uncommon" rather than "the
real sample simply didn't happen to contain 10 of this otherwise-ordinary type." Widening the
tuple without lowering the threshold would inflate the flagged count for a reason that has
nothing to do with B's quality.

## The ground-truth caveat: A is itself a finite sample

Coherence treats A as ground truth, but A is a *sample*, not the true population. A perfectly
valid but uncommon real combination that A's draw happened to under-represent (or miss) will be
flagged as rare or impossible even though a real person like that exists. So a non-perfect
score is not automatically B's fault — it can reflect thin coverage in A. Read a coherence
score in the context of how large and well-covered A is, and treat the flagged list as
"combinations to look at," not "combinations that are definitely wrong."

## Relationship to §4d k-way combination plausibility

Coherence is the **legacy, binary** ancestor of the newer §4d metric. Both build the same kind
of empirical joint table over a tuple and compare against a threshold; the difference is what
they report:

- **Coherence (§3a)** collapses everything below the threshold into a single **flagged**
  bucket and reports one number, `score = n_plausible / n_B`.
- **K-way plausibility (§4d)** generalises the tuple to arbitrary *k* attributes **and splits
  the failures by severity** — `n_impossible` (zero support / missing) vs `n_rare` (below
  threshold) — reporting `fraction_impossible` and `fraction_rare` separately.

For the same tuple and threshold, coherence's `1 − score` is essentially §4d's
`fraction_impossible + fraction_rare`. If you want to know *how bad* the flagged people are —
truly impossible versus merely rare — read §4d; coherence gives you the single headline number.

## How to read it

- **0 to 1, higher is better.** `score = 1.0` means every synthetic person's combination is at
  least as common as the threshold in the real data.
- A high score is **cheap when the threshold is low** — it mostly rules out the *impossible*,
  not the *unusual*. Read it together with the threshold value and with §4d's severity split.
- Use the **flagged list** for debugging: it points straight at the individuals and the exact
  combinations that a downstream reviewer should sanity-check.
