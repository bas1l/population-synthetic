# Swedish Synthetic Populations & Analysis Outputs

> **Audience:** someone new to this repository who wants to understand, in plain terms, *what
> this project produces for Sweden* and *what the analysis pipeline gives you at the end*.
> No prior knowledge of the codebase is assumed. This document is scoped to **Sweden (SCB)**;
> Norway (SSB) and Italy (ISTAT) follow the same shape with different data sources.

---

## 1. What the project does (in one paragraph)

`population-synthetic` answers a simple question: **can a large language model invent a realistic
population of people?** To find out, it does three things:

1. **Builds a real reference population** for Sweden by pulling genuine demographic distributions
   from Statistics Sweden's public API (SCB PxWeb) and sampling 10,000 statistically realistic
   people from them.
2. **Asks LLMs to generate synthetic people** — persona "identities" with the same demographic
   fields — using several models and several generation strategies.
3. **Measures how close the synthetic people are to the real ones**, attribute by attribute, and
   ranks which model + strategy combination does best.

Everything below is the concrete output of those three steps.

---

## 2. The big picture: three kinds of data

All generated data lives **outside the git repository** (the `data/` folder is git-ignored) under a
shared "data lake" directory, referred to in config as `output_base`
(currently `F:/liu-onedrive-nospecial-carac/_Teams/Gauss/02_Data`). It has two folders that matter:

| Folder | Contains |
|--------|----------|
| `01_Raw/` | One sub-folder per generation run — the raw LLM output (100 personas each). |
| `03_Analysis/` | Everything the analysis pipeline computes: mapped populations, comparison charts/reports, performance rankings, and LLM-call analytics. |

The flow is a straight line:

```
  SCB API ─▶ real population (10,000 people)  ┐
                                              ├─▶  MAP  ─▶  COMPARE  ─▶  RANK
  LLM  ───▶ synthetic populations (100 each)  ┘         (per combo)   (across combos)
```

---

## 3. The demographic schema (what a "person" is)

Every person — real or synthetic — is described by the **same 15 demographic attributes** (the
"SCB comparison axis"). This is what generation produces and what comparison scores:

`age_group`, `biological_sex`, `education_level`, `employment_status`, `birth_location`,
`socioeconomic_class`, `parental_structure`, `region`, `civil_status`, `industry_sector`,
`employment_type`, `housing_tenure`, `household_size`, `income_source`, `birth_country_detail`.

*(`age_group` is binned on the fly from a raw integer `age`.)*

A single real person looks like this (from `real_swedish.json`):

```json
{ "id": 0, "age": 65, "biological_sex": "Female", "education_level": "Upper Secondary ≤ 2 yrs (ISCED 3C)",
  "employment_status": "Employed", "birth_location": "Sweden", "socioeconomic_class": "Middle Class",
  "region": "Stockholm", "civil_status": "Divorced", "industry_sector": "Manufacturing & Industry", ... }
```

A raw synthetic persona (`01_Raw/.../persona_00000/identity.json`) carries the same fields (plus a
couple of extras the pipeline does not score, e.g. `current_environment_type`,
`ethnicity_broad_global_approx`):

```json
{ "age": 38, "biological_sex": "male", "region": "Västra Götaland", "civil_status": "married",
  "education_level": "upper secondary", "employment_status": "employed", "industry_sector": "manufacturing",
  "socioeconomic_class": "working class", "household_size": "3", "housing_tenure": "owner-occupied", ... }
```

---

## 4. Currently generated Swedish populations

### 4.1 The real baseline (the "ground truth")

- **1 file:** `03_Analysis/mapped/real_swedish.json`
- **10,000 people**, sampled from live SCB distributions (population, education, employment,
  housing, income, region, birth country, …). Its `metadata` records exactly which SCB tables and
  classifications were used.
- Hard rule of the project: **every distribution comes from a real API response** — no hardcoded or
  invented probabilities. If SCB has no data for a field, the field is dropped, not guessed.

### 4.2 The synthetic populations (the "candidates")

Each synthetic population is one **run** = one combination of **model × strategy**, and targets
**100 generated personas**. Runs are named `swedish_{strategy}_{model}` and stored under
`01_Raw/`. There are currently **42 Swedish runs on disk**: 38 completed the full 100 personas;
4 are partial or failed (e.g. `..._random_pick_ollama_llama33_70b` produced 0, an
`ollama_qwen3_14b` run only 6–12, `..._ollama_lucie_7b` only 16). The 35 runs that mapped cleanly
are the ones carried into the comparison and ranking below.

**Models used** (the persona "author"):

| Active in the current ranking | Generated but set aside |
|---|---|
| Claude Haiku, Claude Sonnet, Claude Opus (Anthropic) | Ollama Qwen3 14B |
| Ollama Llama 3.1 8B | Ollama Llama 3.3 70B |
| Ollama Mistral Nemo 12B | Ollama Gemma2 9B |
| Ollama DeepSeek-R1 14B | Ollama Llama 3.2 3B |
| Ollama Gemma 4 E4B | Ollama Lucie 7B |

*(The "set aside" models were run but are marked "discarded for now" in their config and don't all
appear in the ranking. Ollama models run on a secondary local server.)*

**Strategies used** (*how* the LLM decides each attribute — increasing sophistication):

| Strategy | What the LLM does per attribute | LLM calls |
|----------|--------------------------------|-----------|
| `all_pick` | Directly picks one value given context | 1 |
| `all_pick_dag` | Same, but earlier resolved fields are fed in as context (dependency DAG) | 1 |
| `all_generate_pick` | Enumerates candidate values, then selects one | 2 |
| `all_generate_evaluate_pick` | Enumerates candidates, weights them, picks the highest-probability | 3 |
| `all_generate_evaluate_random_pick` | Enumerates + weights candidates, then **Python samples** from those weights | 2 + sampling |

The last strategy — letting the model propose a *distribution* and having code sample from it — is
the current winner (see §6).

**Raw run contents.** Each `01_Raw/{run}/` folder holds `persona_00000 … persona_00099`
sub-folders (each with `identity.json` + an `llm_interactions.jsonl` call log), a
`manifest_snapshot.yaml` recording the exact config, and a `logs/` folder.

---

## 5. What the analysis pipeline generates

The pipeline runs in stages. Each stage writes concrete files under `03_Analysis/`. Below is what
each stage produces and what it tells you.

### Stage A — Map (`map_populations.py`) → `03_Analysis/mapped/`

Normalises every raw population (real and synthetic) onto the canonical 15-attribute schema so they
can be compared apples-to-apples.

- `real_swedish.json` — the mapped 10,000-person baseline.
- `swedish_{strategy}_{model}.json` — one mapped synthetic population per run (**35 present**).
- `_index.json` — a manifest listing every mapped target, its person count, and how many were
  skipped as unmappable.

### Stage B — Compare (`compare_pipeline_to_scb.py` / `compare_all_pipelines.py`)

Scores **one synthetic population against the real baseline**, per attribute. Output lands in
`03_Analysis/comparison/{run}/` and, for each run, contains:

- **15 per-attribute bar charts** — `{run}_{attribute}.png`, each overlaying the synthetic
  distribution against SCB for one attribute (e.g. `..._age_group.png`, `..._region.png`).
- **1 radar chart** — `{run}_radar.png` — a single-glance "similarity polygon" across all 15
  attributes (larger area = closer to reality).
- **1 JSON report** — `{run}.json` — the numbers behind the charts:
  - `marginals`: per attribute, four distance metrics — `chi_sq_p` (chi-squared p-value),
    `kl_divergence`, `tv_distance` (total-variation distance, the headline metric), and `max_diff`.
  - `joint_chi_sq`: whether pairs of attributes co-vary realistically
    (`age_group_x_education_level`, `age_group_x_employment_status`, `education_level_x_employment_status`).
  - `coherence`: a plausibility check — the fraction of personas whose (age, education, employment)
    combination is realistic, plus a list of flagged implausible individuals.
- **1 CSV** — `{run}.csv` — the same marginal metrics as a spreadsheet, one row per attribute.

**Batch aggregate** (when comparing all runs at once), written to `03_Analysis/comparison/`:

- `swedish_radar_grid.png` — a grid of every run's radar chart (rows = models, columns =
  strategies) for at-a-glance visual comparison.
- `comparison_summary.json` — one summary row per run (mean TV-distance, coherence score).

> **How to read a comparison:** *total-variation (TV) distance* runs 0 (identical to reality) to 1
> (completely different). The pipeline reports it as **TV-similarity = 1 − TV-distance**, so higher
> is better. A perfect population would score 1.0 on every attribute.

### Stage C — Rank (`compare_model_performance.py`) → `03_Analysis/performance/`

Consumes all the Stage-B reports and answers **"which model + strategy is best for Sweden?"**

- `swedish_leaderboard.png` — horizontal bar chart ranking all combos by overall TV-similarity.
- `swedish_heatmap.png` — combos (in rank order) × 15 attributes; each cell is the per-attribute
  similarity, so you can see *where* a combo wins or loses.
- `swedish_performance.json` — the full ranking, per-attribute scores, coherence, and statistical
  tests (**Kruskal–Wallis + Dunn**) checking whether model choice or strategy choice significantly
  affects quality.
- `swedish_performance.csv` — the leaderboard as a spreadsheet (rank, model, strategy, overall
  similarity, coherence, and a similarity column per attribute).
- `swedish_by_attribute/{attribute}_bars.png` — 15 optional charts, one per attribute, comparing
  all models × strategies on that single attribute.

### Stage D — LLM-call analytics (`analyze_run.py`, `compare_runs.py`) → `03_Analysis/llm_metrics/`

This stage ignores demographic accuracy and instead profiles the **generation process itself** —
how the LLM behaved while producing a run.

- Per run: `llm_metrics/{run}/run_analytics.json` + a `charts/` folder with up to 9 PNGs
  (call counts per category, retry rates, answer diversity/entropy, prompt-size growth,
  wall-clock per persona, token consumption, latency, …).
- Cross-run (`compare_runs.py`): `llm_metrics/_comparison/` — compares those process metrics
  across models and strategies (retry rate, success rate, speed, verbosity, token cost) with the
  same Kruskal–Wallis + Dunn significance testing.

---

## 6. The outcome — what the results currently say

The headline deliverable is the **Swedish leaderboard**. As currently generated (35 combos =
7 models × 5 strategies, each a 100-person population vs the 10,000-person SCB baseline), the top of
`swedish_performance.csv` reads:

| Rank | Model | Strategy | TV-similarity | Coherence |
|-----:|-------|----------|:-------------:|:---------:|
| 1 | Claude Opus | `all_generate_evaluate_random_pick` | 0.852 | 0.65 |
| 2 | Claude Haiku | `all_generate_evaluate_random_pick` | 0.847 | 0.60 |
| 3 | Claude Sonnet | `all_generate_evaluate_random_pick` | 0.843 | 0.76 |
| 4 | Llama 3.1 8B | `all_generate_evaluate_random_pick` | 0.803 | — |
| 5 | DeepSeek-R1 14B | `all_generate_evaluate_random_pick` | 0.800 | — |

**Takeaways a newcomer can draw from this:**

- The best synthetic Swedish population reaches **~85% distributional similarity** to real SCB data.
- **Strategy matters more than model:** the `..._random_pick` strategy — where the LLM proposes a
  distribution and *code* samples from it — sweeps the top of the board across every model. Letting
  the LLM pick a single "most likely" value tends to over-concentrate on stereotypes; sampling
  restores realistic spread.
- **Frontier (Claude) models lead, but open local models are close behind** — a strong result for
  running this entirely on local hardware.
- The heatmap and per-attribute charts show this is not uniform: models are near-perfect on
  `biological_sex` (~0.9–0.97) but struggle on skewed fields like `age_group` and region mixes.

---

## 7. Where to find everything (quick map)

| You want… | Look here |
|-----------|-----------|
| The real Swedish reference population | `03_Analysis/mapped/real_swedish.json` (10,000 people) |
| A raw synthetic run | `01_Raw/swedish_{strategy}_{model}/persona_XXXXX/identity.json` |
| Accuracy charts for one run | `03_Analysis/comparison/swedish_{strategy}_{model}/` |
| Accuracy numbers for one run | same folder, `{run}.json` and `{run}.csv` |
| The overall winner ranking | `03_Analysis/performance/swedish_leaderboard.png` + `swedish_performance.{json,csv}` |
| Where each combo wins/loses | `03_Analysis/performance/swedish_heatmap.png` |
| How the LLM behaved during generation | `03_Analysis/llm_metrics/{run}/` |

*(`output_base` root is currently `F:/liu-onedrive-nospecial-carac/_Teams/Gauss/02_Data`, configured
in `config/synthetic/experiment_defaults.yaml` and `config/analysis/analyze_defaults.yaml`.)*

---

## 8. See also

- [SCB population & comparison](scb_population_and_comparison.md) — the end-to-end SCB pipeline in depth.
- [Comparison & mapping](architecture/comparison-mapping.md) — the two-stage map→compare design.
- [Axis composition](architecture/axis-composition.md) — how model × strategy × country compose a run.
- [Command reference](architecture/commands.md) — every command that produces the outputs above.
