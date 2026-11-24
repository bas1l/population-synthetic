# Clash severity vs typicality, swedish_02

Script: `severity_link.py`. Data: the 59 `*_personas.csv` files (5,800 synthetic personas, 100 SCB) plus the `*_clashes.csv` files, for the round-0 control.
Typicality is `typicality_mean`, the pipeline default. Severity flags come from `clash_count_s{1,2,3}`, which counts the distinct clashes over the union of rounds. "Worst" is `max_severity`.

## Definitions (quoted)

- `config/analysis/persona_realism/judge_prompt.md:54`: "S3 — hard contradiction (impossible); this is what makes can_exist false."
- `judge_prompt.md:55`: "S2 — near-impossible but not strictly ruled out."
- `judge_prompt.md:56`: "S1 — unusual-but-possible; reported for transparency, never a defect."
- `judge_prompt.md:76`: "If can_exist is false, at least one issue must have severity S3."
- `judge_prompt.md:40-42`: "TYPICALITY: a low typicality score means "uncommon", NOT "impossible" and NOT "bad". Rare-but-real people are exactly what a low-but-possible score is for."
- `judge_prompt.md:44-51` gives the scale. 9-10 means "every attribute is common and the combination is unremarkable". **5 means "one or two attributes are uncommon for the rest of the profile"**, which is the S1 definition expressed as a score. 1 means "highly unusual yet still fully possible".
- `judge.yaml:35-55`: `severity_weights` (S1 0.0) and `impossibility_severities: [S3]` are "DECLARED BUT NOT WIRED". Impossibility is decided only by the majority of `can_exist` votes.
- The prompt never ties typicality to the issue list explicitly. Both are emitted in one JSON object from one call, and `reasoning` comes before both.

## Findings

1. **The judge's contract is exactly consistent.** 40 personas are excluded (`can_exist` false by majority), and every one of them carries an S3. No surviving persona carries an S3.
2. **Within a population, typicality mostly counts the S1 clashes.**
   - Spearman ρ between typicality and the S1 count is −0.83 for SCB and −0.81 for the synthetic personas. Against all clashes it is −0.90 (SCB) and −0.82 (synthetic).
   - The S1 count alone gives an OLS R² of 0.72.
   - Median typicality by number of S1 clashes (only personas whose clashes are all S1):

     | S1 clashes | SCB | Synthetic |
     |---|---|---|
     | 0 | 8 | 9 |
     | 1 | 4 | 6 |
     | 2 | 1 | 5 |
     | 3 or more | 1 | 4 |

3. **S1 prevalence explains about half of the SCB gap, not all of it.**
   - 69% of SCB personas have an S1 clash, against 32.5% of the synthetic personas. The combo range is 0–91%.
   - The SCB coefficient on typicality is −3.68 on its own. Adding the S1, S2 and S3 counts as covariates reduces it to −1.99 (HC3 SE 0.17), so about 46% of the gap is explained.
   - At equal clash counts, SCB still scores lower. Clash-free personas: median 8 for SCB against 9 for synthetic, δ = +0.47. Exactly one S1: 4 against 6, δ = +0.73.
   - The per-S1 slope is also steeper for SCB: −2.53 against −2.04.
   - Several combos have more S1 clashes than SCB and still median 7. Examples: mistral_medium A (91% S1), deepseek A (85%) and opus_5 A (80%).
4. **Across the 58 combos**, S1 prevalence and median typicality have ρ = −0.75. So the combo-level typicality ranking and the S1 heatmap largely restate each other.
5. **S2 prevalence:** 11% for SCB against 1.8% for the synthetic personas. S3 prevalence: 0% for SCB against 0.7% for the synthetic personas.
6. **Survivor bias is negligible.**
   - The 40 exclusions sit in 5 of the 58 combos, all synthetic, with none in SCB: mistral_nemo A (12), kimi_k3 E (10), gpt_oss_120b E (9), deepseek A (7) and mistral_medium E (2).
   - Worst-case bound: scoring every excluded persona 0 moves the median of 2 combos by 1 point (mistral_nemo A 8→7, gpt_oss E 6→5). At model level it moves only deepseek (8→7). The pooled synthetic median stays at 8.5.
   - The direction of the bias favours those synthetic groups, but it cannot account for a gap of 4 against 8–9.
7. **Round count is not a confound here.** The S1 rate over round 0 alone is nearly identical to the rate over the union of rounds. The only notable change is claude_haiku, 0.242 against 0.292.

## Caveats

- The correlations are within-call. Clashes and score come from the same response, and the prompt's anchor for 5 is worded as an S1. The coupling is therefore partly built in by the prompt, and it is not independent evidence of validity.
- The fact that SCB scores lower at equal clash count is observed. That SCB's S1 pairs are "stranger" (for example Married × 1-person household) is only a plausible reading and has not been tested.
- The strata are descriptive, with no multiplicity control. OLS on a 0–10 ordinal is a rough decomposition only.

## Files

- `severity_typicality_by_group.csv`: rows for SCB, all synthetic, each model and each of the 58 combos. Columns: prevalence (all personas / round 0 / survivors), worst-severity mix, typicality with and without each level, Cliff's δ, ρ, excluded counts and the worst-case medians.
- `scb_vs_synthetic_within_clash_strata.csv`
- `typicality_by_s1_count.csv`
- `ols_typicality_on_clash_counts.csv`
- `ecological_spearman_combo_level.csv`
- `contract_checks.json`
