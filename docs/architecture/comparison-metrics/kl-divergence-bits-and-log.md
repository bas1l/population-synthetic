# Reading the KL divergence formula: bits and the log-ratio

The Kullback–Leibler divergence of the synthetic distribution **B** from the real
distribution **A** is:

```
D_KL(B ‖ A) = Σ_c p_B(c) · log₂( p_B(c) / p_A(c) )
```

This note unpacks that expression term by term, explains why the logarithm is **base 2**,
why individual terms can be **negative** even though the total never is, and what Laplace
smoothing does to the number. It is the KL counterpart to
[Why total variation distance is multiplied by ½](tv-distance-half-factor.md).

## The formula, one piece at a time

For each category `c` the sum contributes one term, `p_B(c) · log₂( p_B(c) / p_A(c) )`,
built from two factors:

- **`log₂( p_B(c) / p_A(c) )` — the log-ratio, or "surprise" of that category.** It compares
  how much probability B puts on `c` against how much A puts there.
  - If B and A agree on `c` (`p_B = p_A`), the ratio is 1 and `log₂(1) = 0` — the category
    contributes nothing.
  - If B **over-represents** `c` (`p_B > p_A`), the ratio exceeds 1 and the log is
    **positive** — this is the case KL is designed to punish.
  - If B **under-represents** `c` (`p_B < p_A`), the ratio is below 1 and the log is
    **negative**.
- **`p_B(c)` — the weight.** Each log-ratio is multiplied by how often the category actually
  occurs *in B*. A category B almost never produces contributes almost nothing, no matter how
  wrong its ratio is. This weighting is exactly why KL is **asymmetric** (see below).

## Why the terms can be negative but the total cannot

The under-representing categories produce negative terms, so it looks as though the sum
could dip below zero. It never does: for any two probability distributions,
`D_KL(B ‖ A) ≥ 0`, with equality only when B and A are identical. This is **Gibbs'
inequality**. The intuition is that the negative terms come from categories where B is small
(`p_B < p_A`), and they are weighted by that same small `p_B`, so they can never outweigh the
positive terms. A negative *term* is normal; a negative *total* would signal a bug.

## Why base 2 — the units are bits

The base of the logarithm sets the **unit** of the answer, and only rescales it by a
constant, so it changes no rankings:

| Base | Unit | Conversion |
|------|------|------------|
| 2    | **bits** (what the pipeline uses) | — |
| e    | nats | `1 nat = 1.4427 bits` |
| 10   | bans / dits | `1 ban ≈ 3.32 bits` |

Base 2 is chosen so the result reads as **bits**, which makes the coding interpretation
concrete:

> Build the optimal binary code for the *real* distribution A — Shannon's theory assigns a
> category with probability `p_A(c)` a codeword of length `−log₂ p_A(c)` bits. Now use that
> A-optimal code to transmit data that actually follows B. The **average number of extra
> bits you waste per person**, compared with the best possible code for B, is exactly
> `D_KL(B ‖ A)`.

So "KL = 0.05 bits" literally means: *encoding the synthetic population with a codebook
tuned to the real one costs about 0.05 wasted bits per individual.* That is why the "How to
read it" guidance frames KL as an information-theoretic surprise, and why 0 means the two
distributions are indistinguishable to an optimal coder.

## Why it is asymmetric

Because the weights are `p_B(c)` and the reference code is built from `p_A(c)`, swapping the
two roles gives a different number: `D_KL(B ‖ A) ≠ D_KL(A ‖ B)` in general. The pipeline
always computes **B relative to A** — "how many extra bits when the real distribution is the
reference." This is why KL is best used for *ranking* candidates against a fixed real A, not
as an absolute two-way distance (for a symmetric, bounded alternative, use TV from §1a).

## Worked example

Using the `education_level` example from
[comparison-metrics.md](../comparison-metrics.md):

| Category  | `p_A` | `p_B` | ratio `p_B/p_A` | `log₂(ratio)` | term `p_B·log₂` |
|-----------|:-----:|:-----:|:---------------:|:-------------:|:---------------:|
| Primary   | 0.20  | 0.10  | 0.500           | −1.000        | **−0.100**      |
| Secondary | 0.50  | 0.55  | 1.100           | +0.138        | **+0.076**      |
| Tertiary  | 0.30  | 0.35  | 1.167           | +0.222        | **+0.078**      |
| **Sum**   |       |       |                 |               | **≈ +0.053**    |

So `D_KL(B ‖ A) ≈ 0.05 bits`. Note the Primary term is **negative** (B under-shoots there,
`0.10 < 0.20`), but the two positive terms outweigh it, leaving a small positive total — as
Gibbs' inequality guarantees. The value is small precisely because the two distributions are
close.

## What Laplace smoothing does to the number

The raw formula divides by `p_A(c)`, so a category that is **empty in the real population**
(`p_A(c) = 0`) would make the ratio blow up to infinity. The pipeline avoids this by
**Laplace smoothing** — adding 1 to every category count before converting counts to
probabilities. Two consequences:

1. **No infinities or divide-by-zero.** Every `p_A(c)` becomes strictly positive, so every
   log-ratio is finite.
2. **A slight shrink toward 0.** Smoothing nudges both distributions a little closer to
   uniform, which trims the extreme log-ratios and pulls the divergence slightly *down*. The
   effect is tiny when sample sizes are large (adding 1 to counts in the thousands barely
   moves a proportion) and more noticeable for small populations — the same regime where the
   chi-squared test also becomes unreliable.

So the smoothed education divergence is a hair below the `≈ 0.05 bits` computed above from
raw proportions; the exact shift depends on the underlying counts, not just the percentages.
