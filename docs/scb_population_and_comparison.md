# SCB Population Sampling & Comparison

This guide covers generating synthetic Swedish populations from SCB (Statistics Sweden) data and comparing them statistically.

## Prerequisites

```bash
conda activate persona_env
pip install -e .
```

No API keys are required — the SCB PxWeb API is public. Responses are cached locally in `config/assets/scb_cache/` (90-day TTL) so repeated runs don't re-fetch.

## Generating an SCB Population

```bash
python scripts/generate/generate_scb_population.py --n 500 --output scb_pop.json --seed 42
```

| Flag | Default | Description |
|------|---------|-------------|
| `--n` | 100 | Number of individuals to generate |
| `--output` | `scb_population.json` | Output file path |
| `--seed` | None | Random seed for reproducibility |

### What it does

The sampler fetches real demographic tables from the SCB PxWeb API and builds probability distributions for 18 attributes across 15 API queries. Responses are cached locally in `config/assets/scb_cache/` with a 90-day TTL.

#### Database queries

| # | Attribute(s) | SCB Table | Dimensions queried |
|---|-------------|-----------|-------------------|
| 1 | `age`, `age_group`, `biological_sex` | `BefolkningNy` | age (18–85) × sex |
| 2 | `education_level` | `Utbildning` (UF0506B) | age (18–74) × SUN2020 level × sex |
| 3 | `employment_status` | `NAKUBefUtbNivAr` (AM0401P) | labour status × education level × sex |
| 4 | `birth_location` | `FolkmFodlandHVD` | Sweden / EU / Outside EU |
| 5 | `region` | `BefolkningNy` | county × age × sex |
| 6 | `socioeconomic_class` | `TabVX10InkStrukt` | income deciles |
| 7 | `parental_structure` | `LE0102T17` | family type |
| 8 | `civil_status` | `BefolkningNy` | civil status × age × sex |
| 9 | `industry_sector` | `AKURLSysSNI07Ar` | SNI07 industry codes |
| 10–11 | `employment_type` | `AKURLSysAnkAr` + `NAKUSysselOkArbtidAr` | attachment type × age × sex; hours × age × sex |
| 12 | `housing_tenure` | `BO0104T04` | building type × tenure form |
| 13 | `household_size` | `HushallT03` | household size (1–7+) |
| 14 | `income_source` | `TabVX13InkStruktN` | income component × age × employment status |
| 15 | `birth_country_detail` | `FodelselandArK` | country × age × sex |

`ethnicity` and `current_environment_type` are derived from `birth_location` and `region` respectively via lookup tables in `category_mappings.json`.

#### Conditional sampling chain

Each individual is sampled through a dependency chain — later attributes are conditioned on earlier ones:

| Step | Attribute | Conditioned on |
|------|-----------|---------------|
| 1 | `age`, `biological_sex` | Joint population pyramid |
| 2 | `education_level` | (age_group, sex) |
| 3 | `employment_status` | (sex, education_level) |
| 4 | `birth_location`, `ethnicity`, `region`, `current_environment_type`, `socioeconomic_class`, `parental_structure` | Marginal distributions |
| 5 | `civil_status` | (age_group, sex) |
| 6 | `industry_sector` | employment_status (Employed only) |
| 7 | `employment_type` | (age_group, sex), Employed only |
| 8 | `housing_tenure`, `household_size` | Marginal distributions |
| 9 | `income_source` | (employment_status, age_group) |
| 10 | `birth_country_detail` | (age_group, sex), foreign-born only |

**Fallback chains:** When a specific conditioning key is missing (e.g., no data for 75–85 age group), sampling falls back to the opposite sex, then to adjacent age groups. This handles gaps where SCB tables don't cover the full 18–85 range (education covers 18–74, employment_type covers 15–74).

**Employment-education note:** The employment table (`NAKUBefUtbNivAr`) provides percentage data (`AM0401VR`) rather than absolute counts, because SCB suppressed absolute numbers by education level in April 2026 due to quality concerns. The table has no age dimension, so employment is conditioned on (sex, education) only. "Vocational (Yrkeshogskola)" shares the post-secondary distribution with "University Degree" since the AKU table groups all post-secondary education together.

### Output format

```json
{
  "metadata": {
    "source": "SCB PxWeb API",
    "tables_used": ["BE/BE0101/BE0101A/BefolkningNy", "..."],
    "data_vintage": "2024",
    "generated_at": "2026-05-06T10:13:09Z",
    "n": 500,
    "seed": 42
  },
  "individuals": [
    {
      "id": 0,
      "age_group": "35-44",
      "biological_sex": "Female",
      "education_level": "University Degree",
      "employment_status": "Employed",
      "birth_location": "Sweden",
      "ethnicity": "Swedish",
      "current_environment_type": "Urban Metropolis",
      "socioeconomic_class": "Middle Class",
      "parental_structure": "Nuclear Family"
    }
  ]
}
```

## Comparing Two Populations

### SCB vs SCB

Generate two populations with different seeds to test sampling stability:

```bash
python scripts/generate/generate_scb_population.py --n 500 --output scb_pop_a.json --seed 42
python scripts/generate/generate_scb_population.py --n 500 --output scb_pop_b.json --seed 99
python scripts/analyze/compare_populations.py scb_pop_a.json scb_pop_b.json --output comparison.json
```

### Pipeline vs SCB

Compare pipeline-generated personas against the SCB reference distribution:

```bash
# 1. Generate the SCB reference
python scripts/generate/generate_scb_population.py --n 500 --output scb_pop.json --seed 42

# 2. Extract personas from a pipeline seed
python scripts/generate/extract_population_from_pipeline.py \
    --seed-root <path-to-seed-folder> \
    --output pipeline_pop.json

# 3. Compare (SCB as reference, pipeline as observed)
python scripts/analyze/compare_populations.py scb_pop.json pipeline_pop.json --output comparison.json
```

The first argument is treated as the **reference** (expected) and the second as the **observed** population.

### Reading the report

The comparison prints a console summary and writes a JSON report:

```
--- Marginal Distributions ---
Attribute                  Chi-sq p     KL div     TV dist    Max diff
----------------------------------------------------------------------
age_group                  0.888        0.003      0.030      0.020
biological_sex             0.040 *      0.006      0.046      0.046
education_level            0.201        0.006      0.042      0.040
```

**Metrics per attribute:**

| Metric | What it tells you | Good range |
|--------|-------------------|------------|
| Chi-sq p | Probability the difference is due to chance. `*` = significant at p < 0.05 | > 0.05 |
| KL div | Information divergence (bits). 0 = identical | < 0.05 |
| TV dist | Maximum probability difference across categories (0-1 scale) | < 0.10 |
| Max diff | Largest single-category absolute difference | < 0.10 |

**Joint distribution coherence:** chi-squared tests on cross-tabs for age x education, age x employment, and education x employment. Low p-values on sparse tables are expected and not necessarily concerning.

**Individual coherence:** what percentage of population B individuals have plausible (age, education, employment) combinations under population A's joint distribution. Flagged individuals have probability < 0.001. Score above 90% indicates good demographic realism.

**Multivariate fidelity (`multivariate` block in the JSON report):** four secondary joint-structure metrics, reported alongside the marginals but not part of the leaderboard ranking:

- **C2ST** (classifier two-sample test): mean cross-validated ROC-AUC of a classifier trained to tell the two populations apart on all 15 one-hot-encoded attributes (0.5 = indistinguishable joint, 1.0 = trivially separable). The real population is subsampled to the synthetic size per fold to remove class-imbalance inflation, and a permutation test gives a p-value. Backend is scikit-learn (a gradient-boosted tree) when the optional `[analysis]` extra is installed, else a numpy/scipy MMD fallback; the `method` field records which ran.
- **Association fidelity:** per-pair `|ΔV|` (bias-corrected Cramér's V difference) over all 105 attribute pairs, with `mean_abs_delta_v` and `frobenius_norm` summaries.
- **Grounded joint TV:** per-pair joint total-variation distance, each pair labelled `grounded` (a real API conditional cross-tab) or not, from the SCB distribution audit (`scb_population_distribution_analysis.md`).
- **Combination plausibility:** the k-way generalisation of individual coherence; the fraction of B individuals whose configured attribute tuple is impossible (zero real support) or rare (below threshold).

Extra artifacts: a `{run}_association.csv` (one row per attribute pair), a per-comparison `{prefix}_association_heatmap.png` (from `compare_pipeline_to_scb.py`), and a cross-combo `{country}_c2st_vs_tv.png` scatter (from `compare_model_performance.py`).

## Attribute Categories

All populations use the same schema labels for comparability:

| Attribute | Categories |
|-----------|-----------|
| age | 18–85 (integer) |
| age_group | 18-24, 25-34, 35-44, 45-54, 55-64, 65-74, 75-85 |
| biological_sex | Male, Female |
| education_level | No Formal Education, High School (Gymnasieskola), Vocational (Yrkeshogskola), University Degree |
| employment_status | Employed, Unemployed, Student, Retired |
| birth_location | Sweden, Nordic Country, Europe (Other), Outside Europe |
| ethnicity | Swedish, Nordic, European, Non-European |
| region | 21 Swedish counties (e.g., Stockholm, Västra Götaland) |
| current_environment_type | Urban Metropolis, Suburban, Rural/Countryside |
| socioeconomic_class | Poverty, Working Class, Middle Class, Wealthy |
| parental_structure | Nuclear Family, Single Parent, Couple without Children, Living Alone |
| civil_status | Single, Married, Divorced, Widowed |
| industry_sector | 12 SNI07 sectors (e.g., Manufacturing, Healthcare, Education) or Not Applicable |
| employment_type | Permanent Full-time, Permanent Part-time, Temporary Full-time, Temporary Part-time, Self-Employed, or Not Applicable |
| housing_tenure | Owned, Rental, Cooperative (Bostadsrätt) |
| household_size | 1–7+ persons |
| income_source | Employment Income, Capital Income, Transfers, Mixed, Pension, Other |
| birth_country_detail | Sweden or specific country (for foreign-born individuals) |

These labels are defined in `config/assets/scb_reference/category_mappings.json`. The pipeline extractor normalizes free-text identity data to match these labels via fuzzy keyword matching.
