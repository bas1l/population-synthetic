# Reading the grounded joint TV: distance and the grounding flag

The grounded joint total-variation distance applies the same TV idea as the marginal
[§1a TV distance](tv-distance-half-factor.md) — but to a **two-attribute joint distribution**
instead of a single attribute. Its two-part value (`joint_tv` plus a `grounded` flag) is what
lets downstream reporting distinguish a *validated* joint from a merely *illustrative* one.
This note covers the equation, the per-population normalisation, the `NaN` rule, and — the part
that "misses information" in the one-liner — what **grounding** actually means. Code:
`multivariate.py:joint_tv` and `evaluator.py:_compute_joint_fidelity`.

## The equation

For a configured pair `(x, y)`, build each population's counts cross-tab over the scheme's
**fixed** `x × y` category grid, normalise **each population over its own in-grid mass**, and
sum the absolute cell differences, halved:

```
p_A(x,y) = count_A(x,y) / Σ count_A      p_B(x,y) = count_B(x,y) / Σ count_B

joint_TV = ½ · Σ_cells | p_A(x,y) − p_B(x,y) |
```

The `½` is there for the same reason as in the marginal case — see the
[½-factor note](tv-distance-half-factor.md): without it the displaced mass is double-counted
and the metric loses its clean 0-to-1 scale. Values outside the grid (including `None`) are
dropped before normalising, so each population's cells sum to 1 over the shared grid.

- `joint_TV = 0` → identical joints.
- `joint_TV = 1` → disjoint supports (no overlapping cells).
- `joint_TV = NaN` → **either** population has no in-grid observations for the pair (nothing to
  normalise); this is a "not measurable," not a "far apart."

## What "grounded" means — and why it matters

Each pair the evaluator scores comes from `scheme.grounded_joint_pairs`, and every entry
carries two audit fields beyond the number:

- **`grounded` (bool)** — `true` means the *real* population's joint over this pair is backed by
  an actual statistics-agency **conditional cross-tabulation**: the SCB sampler drew the two
  attributes with their real dependency preserved, so `p_A(x,y)` is a defensible ground truth.
  `false` means the reference joint is **not** API-identical — it is a marginal product or a
  forced-independence copy — so the pair is shown for context but must not be presented as
  agency-validated.
- **`basis` (str)** — a free-text audit note recording *why* the pair is (or isn't) grounded,
  traceable to the SCB distribution-analysis audit.

This split exists so the paper (and any downstream reporting) does not over-claim: a low
`joint_TV` on a **grounded** pair is real evidence the synthetic joint matches reality; a low
`joint_TV` on a **non-grounded** pair only says the synthetic data matches a reference that was
itself assembled from marginals — no agency ever published that joint.

## The SCB pairs

The Swedish scheme configures **eight** pairs — five grounded, three reference:

| Pair | Grounded? | Basis (abridged) |
|------|:---------:|------------------|
| `age_group × biological_sex` | ✅ | SCB query separates sex; parser preserves the joint |
| `age_group × civil_status` | ✅ | sampled conditional on (age, sex) |
| `biological_sex × civil_status` | ✅ | sampled conditional on (age, sex) |
| `age_group × income_source` | ✅ | sampled conditional on (employment, age) |
| `employment_status × income_source` | ✅ | sampled conditional on (employment, age) |
| `age_group × education_level` | ❌ | education conditional on age but **sex pooled** — not API-identical |
| `age_group × employment_status` | ❌ | sex pooled, education ignored — not API-identical |
| `education_level × employment_status` | ❌ | **forced independence** — identical employment across education levels |

## How to read it

- **0 to 1, lower is better**; it is the finer, magnitude-based complement to the legacy joint
  chi-squared **p-value** (§2a), which only pools A and B into one table and returns a coarse
  "distinguishable?" signal.
- **Read the `grounded` flag first.** Only grounded pairs support a claim that the synthetic
  joint reproduces reality; treat non-grounded pairs as sanity context.
- A `NaN` means "no in-grid data," not "bad" — check population coverage before interpreting.
