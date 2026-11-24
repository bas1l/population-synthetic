# Manuscript number scripts

Scripts that compute the manuscript's headline numbers from the latest dataset: the ref-v3
reference population (`real_swedish_02`) and the `swedish_02` populations generated with the five
`*_v2` strategies.

- Run against the code at tag `ref-v3-2026-11-24`, outside the repository, in the analysis folder
  of the project data. Nothing in the package imports them.

| File | Role |
|---|---|
| `headline_numbers.py` | Headline statistics from the per-combination fidelity CSVs: strategy and model means, repeated-measures ANOVA with assumption checks (`population_synthetic.analysis.utils.stats_tests`), variance shares, best combination. |

## Paths

Machine paths are environment variables with no default:

| Variable | Meaning |
|---|---|
| `POPSYNTH_REPO` | Root of a checkout of this repository (the script adds `<root>/src` to `sys.path`). |

Usage: `python headline_numbers.py <analysis_base> <out_json_or_dash>`; `<analysis_base>` holds
`03_Analysis/fidelity/swedish_02_*`.
