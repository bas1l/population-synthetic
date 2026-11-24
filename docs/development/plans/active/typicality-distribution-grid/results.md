# Typicality effect sizes and comparison to the real population (swedish_02)

## Data provenance

- Source: `<project-data>\02_Data\03_Analysis\persona_realism\swedish_02\*\*_personas.csv` (59 files: 58 synthetic combinations + `real_swedish_02`).
- Unit: one persona. Value: `typicality_mean` (judge 0-10, mean over the persona's successful rounds) = pipeline default. Secondary basis "r1": first round only (`typicality_rounds` first entry).
- Filter: `can_exist_majority == True`. Synthetic N = 5760 (40 excluded as can_exist false); 486 synthetic personas have 2 rounds, the rest 1. Real population: n = 100, all 1 round, all can_exist.
- r1 equals `--rounds 1` here: every 2-round persona has 2/2 can_exist votes, so the survivor set is unchanged under a 1-round cap; only the typicality value changes.
- Judge: claude-sonnet-5 (realism_ranking.json provenance). Model order: rows of model_ranking `swedish_02_model_method_heatmap` (tier sort reproduced from `model_ranking/charts.py` + `population_cap/_index.json`).
- Bootstrap: percentile 95% CI, 2000 reps, resampling personas within each group independently (implemented as exact multinomial redraws of each group's 0.5-step histogram), seed 20260921(+1 combos, +2 models). Point δ checked against `stats_tests.cliffs_delta`.
- Missing combinations: DeepSeek-R1 14B E and Gemma4 E4B E (withdrawn by population_cap: 10 and 9 clean personas < n=100).

## 1. Omnibus Kruskal-Wallis, ε² = H(N+1)/(N²-1)

| basis | factor | k | N | H | p | ε² | Dunn Holm-sig / pairs |
|---|---|---|---|---|---|---|---|
| typicality_mean | model | 12 | 5760 | 564.14 | 6.51e-114 | 0.0980 | 45/66 |
| typicality_mean | method | 5 | 5760 | 960.61 | 1.23e-206 | 0.1668 | 9/10 |
| first | model | 12 | 5760 | 566.79 | 1.77e-114 | 0.0984 | 47/66 |
| first | method | 5 | 5760 | 926.22 | 3.47e-199 | 0.1608 | 10/10 |

## 2. Pairwise models (δ = P(a>b) - P(a<b); A = (δ+1)/2)

- Holm-significant: 45/66. Magnitude (Romano): {'negligible': 27, 'small': 22, 'medium': 16, 'large': 1}. Significant-but-negligible (|δ|<0.147): 7. Largest non-significant |δ| = 0.161; smallest significant |δ| = 0.078.
- Full table: `pairwise_models_cliffs_delta.csv`. Top 8 by |δ|:

| a | b | δ | 95% CI | A | Dunn z | p Holm |
|---|---|---|---|---|---|---|
| Kimi K3 | Gemma4 E4B | -0.480 | [-0.545, -0.415] | 0.260 | -14.03 | 6.9e-43 |
| Kimi K3 | Qwen 3.5 Flash | -0.472 | [-0.531, -0.412] | 0.264 | -13.27 | 2.3e-38 |
| Kimi K3 | Claude Sonnet | -0.460 | [-0.518, -0.400] | 0.270 | -14.10 | 2.4e-43 |
| DeepSeek-R1 14B | Gemma4 E4B | -0.460 | [-0.523, -0.392] | 0.270 | -11.95 | 4.2e-31 |
| Claude Sonnet | DeepSeek-R1 14B | +0.450 | [+0.386, +0.511] | 0.725 | +11.87 | 1.1e-30 |
| Qwen 3.5 Flash | DeepSeek-R1 14B | +0.443 | [+0.383, +0.504] | 0.721 | +11.08 | 9e-27 |
| Claude Opus 5 | Gemma4 E4B | -0.436 | [-0.503, -0.372] | 0.282 | -11.56 | 3.9e-29 |
| Claude Sonnet | Claude Opus 5 | +0.432 | [+0.373, +0.497] | 0.716 | +11.49 | 8.5e-29 |

## 3. Versus the real population (δ = P(synthetic > real) - P(synthetic < real))

- Real population: n = 100, median 4.0, mean 4.01 (identical under r1).
- Combinations: all 58 have δ > 0; 58/58 Holm-significant (Mann-Whitney two-sided, Holm over 58); max p_Holm = 0.00061; smallest CI lower bound = 0.139. Same count under r1 (58/58); max |δ - δ_r1| = 0.057.
- Range: min δ = 0.296, max δ = 0.912. Mean δ by method: A 0.648, B 0.789, C 0.736, D 0.701, E 0.396.

### Per model (methods pooled)

| model | n | median | mean | δ | 95% CI | A | p Holm (12) |
|---|---|---|---|---|---|---|---|
| Kimi K3 | 490 | 6 | 6.74 | +0.515 | [0.386, 0.631] | 0.758 | 1.3e-16 |
| Claude Haiku | 500 | 9 | 7.96 | +0.711 | [0.616, 0.799] | 0.856 | 1.2e-29 |
| Claude Sonnet | 500 | 9 | 8.21 | +0.749 | [0.663, 0.828] | 0.874 | 4.1e-41 |
| Claude Opus 5 | 500 | 8 | 7.32 | +0.607 | [0.490, 0.721] | 0.804 | 7e-22 |
| GPT-5.6 Sol | 500 | 9 | 8.06 | +0.724 | [0.626, 0.823] | 0.862 | 1.2e-32 |
| GLM-5.2 | 500 | 9 | 7.78 | +0.677 | [0.577, 0.765] | 0.839 | 9.7e-28 |
| Qwen 3.5 Flash | 500 | 9 | 8.31 | +0.766 | [0.676, 0.847] | 0.883 | 4e-40 |
| GPT-OSS 120B | 491 | 9 | 7.86 | +0.689 | [0.597, 0.778] | 0.844 | 1.8e-29 |
| Mistral Medium 3.5 | 498 | 8 | 7.49 | +0.619 | [0.515, 0.711] | 0.809 | 2.5e-22 |
| Mistral Nemo 12B | 488 | 8 | 7.18 | +0.581 | [0.465, 0.689] | 0.791 | 3.2e-20 |
| DeepSeek-R1 14B | 393 | 8 | 7.04 | +0.561 | [0.441, 0.674] | 0.781 | 3e-18 |
| Gemma4 E4B | 400 | 9 | 8.35 | +0.765 | [0.676, 0.841] | 0.882 | 7.1e-35 |

### Per combination

| model | method | n | median | mean | δ | 95% CI | p Holm (58) | δ r1 |
|---|---|---|---|---|---|---|---|---|
| Kimi K3 | A | 100 | 6 | 6.65 | +0.500 | [0.359, 0.630] | 7.3e-09 | +0.500 |
| Kimi K3 | B | 100 | 8 | 7.42 | +0.624 | [0.501, 0.747] | 3.2e-13 | +0.624 |
| Kimi K3 | C | 100 | 7 | 7.46 | +0.632 | [0.515, 0.751] | 1.3e-13 | +0.632 |
| Kimi K3 | D | 100 | 6 | 5.83 | +0.377 | [0.226, 0.524] | 1.7e-05 | +0.377 |
| Kimi K3 | E | 90 | 6 | 6.28 | +0.435 | [0.286, 0.578] | 1.5e-06 | +0.435 |
| Claude Haiku | A | 100 | 9 | 8.44 | +0.791 | [0.696, 0.876] | 6.4e-22 | +0.784 |
| Claude Haiku | B | 100 | 9.5 | 9.21 | +0.912 | [0.844, 0.965] | 7.8e-29 | +0.855 |
| Claude Haiku | C | 100 | 9 | 8.22 | +0.756 | [0.649, 0.847] | 7.6e-20 | +0.786 |
| Claude Haiku | D | 100 | 8.5 | 7.67 | +0.669 | [0.550, 0.776] | 4.5e-15 | +0.644 |
| Claude Haiku | E | 100 | 6.5 | 6.25 | +0.430 | [0.287, 0.573] | 1.2e-06 | +0.431 |
| Claude Sonnet | A | 100 | 9 | 8.94 | +0.870 | [0.789, 0.943] | 6.8e-29 | +0.870 |
| Claude Sonnet | B | 100 | 9 | 9.00 | +0.880 | [0.800, 0.950] | 5.7e-30 | +0.880 |
| Claude Sonnet | C | 100 | 9 | 8.97 | +0.875 | [0.795, 0.944] | 2.4e-29 | +0.875 |
| Claude Sonnet | D | 100 | 9 | 8.44 | +0.781 | [0.685, 0.867] | 5.1e-21 | +0.781 |
| Claude Sonnet | E | 100 | 6 | 5.72 | +0.337 | [0.182, 0.477] | 0.0001 | +0.337 |
| Claude Opus 5 | A | 100 | 7 | 7.25 | +0.597 | [0.452, 0.728] | 2.3e-12 | +0.597 |
| Claude Opus 5 | B | 100 | 8 | 8.02 | +0.714 | [0.577, 0.833] | 2.7e-19 | +0.714 |
| Claude Opus 5 | C | 100 | 9 | 8.17 | +0.747 | [0.642, 0.843] | 2.3e-19 | +0.747 |
| Claude Opus 5 | D | 100 | 6 | 7.05 | +0.573 | [0.431, 0.702] | 1.6e-11 | +0.573 |
| Claude Opus 5 | E | 100 | 6 | 6.11 | +0.404 | [0.261, 0.543] | 4.8e-06 | +0.404 |
| GPT-5.6 Sol | A | 100 | 8 | 7.93 | +0.699 | [0.569, 0.819] | 8.8e-19 | +0.699 |
| GPT-5.6 Sol | B | 100 | 9 | 8.56 | +0.809 | [0.716, 0.892] | 3.2e-23 | +0.809 |
| GPT-5.6 Sol | C | 100 | 9 | 8.50 | +0.797 | [0.693, 0.883] | 7.7e-22 | +0.797 |
| GPT-5.6 Sol | D | 100 | 9 | 8.38 | +0.778 | [0.683, 0.865] | 1.1e-21 | +0.778 |
| GPT-5.6 Sol | E | 100 | 7 | 6.91 | +0.539 | [0.397, 0.662] | 4.9e-10 | +0.539 |
| GLM-5.2 | A | 100 | 7 | 7.09 | +0.577 | [0.435, 0.707] | 1.7e-11 | +0.577 |
| GLM-5.2 | B | 100 | 9 | 8.64 | +0.802 | [0.711, 0.881] | 1.9e-21 | +0.802 |
| GLM-5.2 | C | 100 | 9 | 8.70 | +0.831 | [0.736, 0.908] | 3.6e-25 | +0.831 |
| GLM-5.2 | D | 100 | 9 | 8.65 | +0.815 | [0.725, 0.894] | 1.6e-23 | +0.815 |
| GLM-5.2 | E | 100 | 6 | 5.83 | +0.362 | [0.208, 0.513] | 3.4e-05 | +0.362 |
| Qwen 3.5 Flash | A | 100 | 8.5 | 8.27 | +0.760 | [0.659, 0.850] | 9.8e-20 | +0.760 |
| Qwen 3.5 Flash | B | 100 | 9 | 8.91 | +0.864 | [0.777, 0.935] | 9e-28 | +0.864 |
| Qwen 3.5 Flash | C | 100 | 9 | 8.97 | +0.873 | [0.794, 0.940] | 1e-28 | +0.873 |
| Qwen 3.5 Flash | D | 100 | 9 | 8.81 | +0.848 | [0.753, 0.924] | 6.3e-26 | +0.848 |
| Qwen 3.5 Flash | E | 100 | 7 | 6.58 | +0.487 | [0.347, 0.618] | 2.4e-08 | +0.487 |
| GPT-OSS 120B | A | 100 | 9 | 7.96 | +0.713 | [0.599, 0.808] | 1.2e-17 | +0.713 |
| GPT-OSS 120B | B | 100 | 9 | 8.85 | +0.856 | [0.772, 0.928] | 1e-27 | +0.856 |
| GPT-OSS 120B | C | 100 | 9 | 7.86 | +0.696 | [0.586, 0.800] | 1.2e-16 | +0.696 |
| GPT-OSS 120B | D | 100 | 9 | 8.94 | +0.844 | [0.765, 0.911] | 6.6e-24 | +0.844 |
| GPT-OSS 120B | E | 91 | 6 | 5.48 | +0.300 | [0.148, 0.451] | 0.00061 | +0.300 |
| Mistral Medium 3.5 | A | 100 | 7 | 6.71 | +0.505 | [0.360, 0.643] | 6.3e-09 | +0.505 |
| Mistral Medium 3.5 | B | 100 | 10 | 8.74 | +0.802 | [0.712, 0.875] | 6.3e-22 | +0.802 |
| Mistral Medium 3.5 | C | 100 | 8.5 | 8.00 | +0.714 | [0.600, 0.811] | 3.1e-17 | +0.714 |
| Mistral Medium 3.5 | D | 100 | 9 | 8.42 | +0.770 | [0.682, 0.853] | 5.5e-20 | +0.770 |
| Mistral Medium 3.5 | E | 98 | 6 | 5.56 | +0.296 | [0.139, 0.450] | 0.00061 | +0.296 |
| Mistral Nemo 12B | A | 88 | 8 | 7.32 | +0.611 | [0.483, 0.732] | 6e-12 | +0.611 |
| Mistral Nemo 12B | B | 100 | 9 | 8.46 | +0.789 | [0.686, 0.883] | 2e-21 | +0.789 |
| Mistral Nemo 12B | C | 100 | 7 | 6.87 | +0.535 | [0.399, 0.667] | 6.1e-10 | +0.535 |
| Mistral Nemo 12B | D | 100 | 8 | 7.31 | +0.605 | [0.478, 0.724] | 2e-12 | +0.605 |
| Mistral Nemo 12B | E | 100 | 6 | 5.94 | +0.370 | [0.227, 0.513] | 2.7e-05 | +0.370 |
| DeepSeek-R1 14B | A | 93 | 7 | 6.34 | +0.449 | [0.307, 0.586] | 6.2e-07 | +0.449 |
| DeepSeek-R1 14B | B | 100 | 8 | 7.57 | +0.649 | [0.522, 0.754] | 2.6e-14 | +0.649 |
| DeepSeek-R1 14B | C | 100 | 7 | 7.00 | +0.556 | [0.421, 0.684] | 1.2e-10 | +0.556 |
| DeepSeek-R1 14B | D | 100 | 8 | 7.18 | +0.583 | [0.455, 0.699] | 1.3e-11 | +0.583 |
| Gemma4 E4B | A | 100 | 9 | 7.93 | +0.705 | [0.592, 0.802] | 1.7e-17 | +0.705 |
| Gemma4 E4B | B | 100 | 9 | 8.28 | +0.764 | [0.658, 0.854] | 4.7e-20 | +0.764 |
| Gemma4 E4B | C | 100 | 10 | 8.82 | +0.815 | [0.730, 0.889] | 2.1e-22 | +0.815 |
| Gemma4 E4B | D | 100 | 9 | 8.35 | +0.775 | [0.670, 0.864] | 3.9e-21 | +0.775 |

## Files
- `omnibus_kruskal_epsilon2.csv`, `pairwise_models_cliffs_delta.csv`, `combo_vs_scb.csv`, `model_vs_scb.csv`, `scb_reference.csv`, `distribution_first_round_by_model.csv`, `meta.json`
- `figures/typicality_delta_vs_real.{png,svg,eps}`, `figures/typicality_pairwise_model_delta.{png,svg,eps}`, `figures/typicality_distribution_by_model.{png,svg,eps}`
- Code: `effects.py` (stats), `figs.py` (figures), `write_results.py`.
