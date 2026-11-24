# Sample-size / power analysis — all 14 SCB Sweden categories

**Date:** 2026-07-17
**Script:** [`scripts/analyze/attribute_power_analysis.py`](../scripts/analyze/attribute_power_analysis.py)
**Reference population:** `data/scb_api/scb_population_n10000_seed42_merge-status-edu_2026-07-16.json` (n = 10,000)
**Mapping tier:** `config/mapping/scb_native` (`birth_location` skipped — deprecated from analysis, see
[`config/mapping/scb_native/README.md`](../config/mapping/scb_native/README.md))

## Question

How many generated samples (**N**) are needed so that the sampled distribution of each comparison
attribute can be **statistically compared against the "true" probabilities** — i.e. each category's
probability is estimated precisely enough, and a goodness-of-fit test has adequate power?

For a K-category multinomial the requirement is dominated by the **rarest** category, so every row
below is driven by that category's share `p_min`.

## Method

The "true" probabilities `p_i` are estimated empirically by tallying each attribute over the n=10,000
reference population (the canonical SCB-sampled reference wired into
`config/synthetic/axes/countries/swedish.yaml`). Both the population file and the mapping directory
are resolved from that axis YAML — nothing is hardcoded. Three families of thresholds are computed:

1. **Per-category estimation precision** — Wald `N = z² · p(1−p) / E²`, single and Bonferroni-simultaneous across the K categories.
2. **Expected-count floors** for the rarest cell — `N = k / p_min`; these govern when the normal approximation and the chi-square goodness-of-fit (GOF) test become valid.
3. **Chi-square GOF power** over `df = K−1` — `N = λ / w²`, for Cohen's `w` effect sizes and target powers (λ is the noncentrality giving the target power; verified against `statsmodels.GofChisquarePower`).

Two summary N's are derived per attribute:

- **min N** — the χ²-GOF validity floor: all rarest-cell expected counts ≥ 5 (`N = 5 / p_min`). Below this the fit test and the per-cell normal CI are invalid.
- **rec. N** — a sound working target: `max(rarest cell expected ≥ 15, small-effect GOF power w=0.1 at power 0.90)`. This makes the rarest cell's normal CI trustworthy **and** gives 90% power to detect even a *small* deviation from truth.
- **±20% N** — the (much larger) N to pin the rarest category's *own* probability to ±20% relative (single 95% CI); a per-estimate precision goal, well beyond what a fit test needs.

## Summary — binding category per attribute

| Attribute | K | rarest `p_min` | rarest category | **min N** | **rec. N** | ±20% N |
|---|--:|--:|---|--:|--:|--:|
| age_group | 7 | 0.1055 | 18–24 | 48 | 1,742 | 815 |
| biological_sex | 2 | 0.4990 | women | 11 | 1,051 | 97 |
| education_level | 8 | 0.0129 | post-graduate (ISCED97 6) | 388 | 1,829 | 7,349 |
| employment_status | 6 | 0.0137 | Sick Leave | 365 | 1,647 | 6,914 |
| socioeconomic_class | 4 | 0.0955 | Wealthy | 53 | 1,418 | 910 |
| parental_structure | 6 | 0.0072 | living with non-parents | 695 | 2,084 | 13,243 |
| **region** | 21 | 0.0052 | Gotland | 962 | 2,885 | 18,373 |
| civil_status | 4 | 0.0392 | widowers/widows | 128 | 1,418 | 2,354 |
| industry_sector | 12* | 0.0231 | Agriculture, Forestry & Fishing | 217 | 2,120 | 4,057 |
| employment_type | 9* | 0.0229 | temporary \| 1–19 hours | 219 | 1,909 | 4,106 |
| housing_tenure | 3 | 0.2308 | Tenant-owned apartment | 22 | 1,266 | 321 |
| household_size | 7 | 0.0063 | 7 persons or more | 794 | 2,381 | 15,148 |
| income_source | 6 | 0.0072 | social assistance | 695 | 2,084 | 13,243 |
| **birth_country_detail** | 21 | 0.0050 | China | 1,000 | 3,000 | 19,112 |

\* `industry_sector` (12 of 14 config values) and `employment_type` (9 of 10) realize fewer categories
than the config lists — the missing ones (e.g. `Not Applicable`) apply only to non-employed
individuals, so N is computed on the n = 7,524 employed subset.

## Key takeaways

- **The two 21-category axes bind hardest** — `birth_country_detail` (China, p = 0.0050) and `region`
  (Gotland, p = 0.0052). To *validly test* any category you need **N ≈ 1,000**; a **sound working
  target across all 14 is N ≈ 3,000**, which covers small-effect GOF power everywhere and makes every
  rarest cell's normal CI trustworthy.
- **The n = 10,000 reference clears every test-oriented threshold** comfortably for all 14 categories.
  It only falls short for tight *relative* precision (±20%) on the rarest cells — that pushes toward
  **N ≈ 18k–20k** (region, birth_country_detail); ±10% *jointly* would need ~180k.
- **Below ~N = 1,000 the fit test breaks** for the high-cardinality axes: rarest cells drop under 5
  expected counts, invalidating both the per-cell CI and the χ² GOF. Such small runs need
  exact/simulated GOF or cell-pooling.
- **Cheapest to certify:** low-cardinality, balanced axes — `housing_tenure` (min N ≈ 22),
  `biological_sex` (min N ≈ 11).
- **Why even `biological_sex` shows rec. N ≈ 1,000** despite a 50/50 split: its rec. N is set by GOF
  power at a *small* effect (w = 0.1 ≈ a 5-percentage-point shift), which needs ~1,000 samples for
  almost any small K — not by estimating the split (that needs ≈ 30–100). Relax the target effect
  (`--effect-sizes 0.3`) and its rec. N drops to ≈ 120.

## Recommended targets

| Goal | Target N |
|---|--:|
| Minimum defensible (χ² GOF valid for every category) | ~1,000 |
| Sound working target (valid + small-effect GOF power, all 14) | **~3,000** |
| Tight per-estimate precision on the rarest cells (±20% relative) | ~18k–20k |
| ±10% relative, simultaneous across a 21-cell axis | ~180k |

## Caveats

- **Raw pre-mapping labels.** The reference stores raw SCB labels (`men`/`women`, `Gotland county`);
  for the direct attributes the realized category count matches the canonical config 1:1, so the
  probabilities — and therefore the N's — are unaffected. `employment_type` is tallied as its
  composite `attachment × hours` grid.
- **Marginal, not conditional.** These N's are for the pooled marginal of each attribute. Comparing a
  category *within* age×sex strata needs this N **per stratum**, and conditional cells are far sparser,
  so the effective requirement scales up substantially.
- **Empirical "truth."** The `p_i` are themselves an n = 10,000 estimate of the SCB marginal, so the
  smallest shares (Gotland, China) carry their own ~±14% sampling error; the expected-count and
  GOF-validity rows are the trustworthy anchors for the rarest cells, where the normal approximation
  understates the requirement.

## Reproduce

```bash
# All non-deprecated attributes for Sweden:
python scripts/analyze/attribute_power_analysis.py --country swedish

# A single attribute, with a coarser target effect size and stricter power:
python scripts/analyze/attribute_power_analysis.py --country swedish --attribute region \
    --effect-sizes 0.05 0.1 --powers 0.95
```

The script is country- and attribute-agnostic: it reads the country axis YAML for the reference
population and mapping tier, excludes `deprecated_attributes`, and computes the tables above for any
attribute (or all of them). Requires `scipy`; uses `statsmodels` for a GOF-power cross-check when
available.

## Appendix — GOF small-effect detail (w = 0.1)

The GOF small-effect term usually sets `rec. N`. Below, `df = K−1`, and N is `λ/w²` at w = 0.1.

| Attribute | df | N @ power 0.80 | N @ power 0.90 | rarest expected ≥ 15 (N) | binds rec. N |
|---|--:|--:|--:|--:|---|
| age_group | 6 | 1,363 | 1,742 | 143 | GOF |
| biological_sex | 1 | 785 | 1,051 | 31 | GOF |
| education_level | 7 | 1,436 | 1,829 | 1,163 | GOF |
| employment_status | 5 | 1,283 | 1,647 | 1,095 | GOF |
| socioeconomic_class | 3 | 1,091 | 1,418 | 158 | GOF |
| parental_structure | 5 | 1,283 | 1,647 | 2,084 | expected-count |
| region | 20 | 2,097 | 2,614 | 2,885 | expected-count |
| civil_status | 3 | 1,091 | 1,418 | 383 | GOF |
| industry_sector | 11 | 1,681 | 2,120 | 649 | GOF |
| employment_type | 8 | 1,503 | 1,909 | 657 | GOF |
| housing_tenure | 2 | 964 | 1,266 | 65 | GOF |
| household_size | 6 | 1,363 | 1,742 | 2,381 | expected-count |
| income_source | 5 | 1,283 | 1,647 | 2,084 | expected-count |
| birth_country_detail | 20 | 2,097 | 2,614 | 3,000 | expected-count |
