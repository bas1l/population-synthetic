# Swedish Persona Mapping Fix — 2026-05-29

## Summary

Three passes of alias additions to `config/assets/scb_reference/category_mappings.json` and keyword fixes in `src/population_synthetic/comparison/extractor.py`, totalling ~180 new pipeline_label_mappings across 10 sections. All 22 model×strategy runs re-compared against the SCB 10k reference population.

## What was done

### Pass 1 — initial alias sweep
- Added ~100 new aliases across 8 `pipeline_label_mappings` sections (employment, employment_type, housing_tenure, socioeconomic, civil_status, parental_structure, region, education)
- Added UTF-8 double-encoding repair in `extractor.py` for Mistral Nemo 12B output (ä→√§ corruption)
- Extended biological_sex normalization with Swedish synonyms ("kvinnlig", "hona", "kön man")
- Added `_json_lookup("region", ...)` call so city→county mappings in the JSON are actually used

### Pass 2 — housing tenure audit + targeted adds
- Audited all raw `housing_tenure` values across llama31_8b, mistral_nemo_12b, and gemma4_e4b (100 personas each)
- Added 26 housing_tenure aliases: owner-occupied variants ("Eget hus", "Egenhem", "Äga", "Ägt", "Owned"), rental variants ("Ej ägd bostad", "Hyrbostad", "student_housing"), bostadsrätt overrides ("Owner-occupied apartment", "Owned apartment")
- Added 6 parental_structure aliases ("Bor hemma med föräldrar", "Föräldrahemma", "Ensamförälder", "Båda föräldrarna", "two_parent")
- Added 5 employment_status aliases ("Arbetar", "Arbetar fulltid", "Arbeta fulltid", "Aktiv", "Aktiva")

### Pass 3 — full field sweep across all 3 models
- Collected every unique value per field across all 300 personas (3 models × 100)
- Added ~50 more aliases across 7 fields:
  - **parental_structure** (15): "Both parents", "Enkel föräldrahem/hemma/familj" cluster, "Tva föräldrar", "Tvaa föräldrar", "Enbar förälder", "Barnlös", "föräldrar"
  - **education** (14): "Högre utbildning", "Higher Education", "Academic", "Master's degree", "Bachelor's degree", "University degree", "Högskoleingenjör", "Högskoleutbildad"
  - **socioeconomic** (15): "Låg", "Låginkomst", "Mellan klass", "Middle", "Mellan", "Lower Middle Class" → Working Class, "Upper-middle class" → Middle Class
  - **ethnicity** (13): "Västerländsk", "Västlig", "Vit" → Swedish; "Europa", "Européer" → European; "Finn" → Nordic
  - **employment_status** (12): "Full time", "Fulgtid", "Anställd (Employed)", "Arbetar (Employed)", "Employed full-time" variants, "anställda"
  - **civil_status** (6): "Ugift", "Unmarried", "Sammanboende med partner", "Gifta", "Civilstånd: Gift/Giftermål"
  - **region** (2): "Stockholm County", "Stockholm län"
- Fixed biological_sex in `extractor.py`: added "woman", "hon", "f", "m" to keyword matching

## Before / After — all_pick strategy, mean TV distance across 15 fields

| Model | Original | Pass 1 | Pass 2 | Pass 3 (final) | Total Δ |
|---|---|---|---|---|---|
| ollama_gemma4_e4b | 0.564 | 0.499 | 0.487 | **0.487** | -0.077 |
| ollama_llama31_8b | 0.477 | 0.395 | 0.362 | **0.357** | -0.120 |
| ollama_mistral_nemo_12b | 0.461 | 0.436 | 0.421 | **0.413** | -0.048 |

## Per-field progression (llama31_8b all_pick, biggest mover)

| Field | Original | Pass 1 | Final | Status |
|---|---|---|---|---|
| socioeconomic_class | 89% | 8% | **5%** | Residual is LLM gibberish ("K lugnt arbetande", "B-Medelinkomst") |
| housing_tenure | 76% | 72% | **19%** | Residual is hallucinations ("Eigen hemförsäkring", "Egendom", "Egenhustru") |
| parental_structure | 78% | 32% | **21%** | Residual is hallucinations ("Tiohjuling", "Enhetstablett familj", "Enkelhet") |
| region | 39% | 39% | **39%** | Unmappable: "Svealand" (33), "Götaland" (23) are macro-regions, not counties |
| education_level | 24% | 1% | **1%** | Solved |
| biological_sex | 7% | 0% | **0%** | Solved |
| employment_status | 4% | 1% | **0%** | Solved |

## Full unmapped matrix — all 22 runs

See `docs/unmapped_matrix_2026-05-29.csv` for the complete table. Summary below (unmapped % per field, blank = 0%):

| Strategy | Model | N | mTV | mU% | #U | sex | edu | empl | socio | parent | reg | housing | hh_sz |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **all_pick** | claude_haiku | 100 | 0.426 | 5.2 | 4 | | 5 | | 10 | 5 | | | 1 |
| | gemma4_e4b | 100 | 0.487 | 0 | 0 | | | | | | | | |
| | llama31_8b | 100 | 0.357 | 17.0 | 5 | | 1 | | 5 | 21 | 39 | 19 | |
| | lucie_7b | 16 | 0.556 | 6.5 | 8 | 1 | 8 | 3 | 8 | 6 | 16 | 9 | 1 |
| | mistral_nemo_12b | 100 | 0.413 | 3.8 | 4 | | 1 | 1 | | 11 | | 2 | |
| | qwen3_14b | 100 | 0.459 | 16.7 | 6 | | 2 | 3 | 20 | 53 | | 16 | 6 |
| **all_pick_dag** | claude_haiku | 100 | 0.490 | 7.8 | 4 | | 13 | | 12 | 2 | | 4 | |
| | gemma4_e4b | 100 | 0.493 | 21.7 | 3 | 34 | | | | | 30 | 1 | |
| | llama31_8b | 100 | 0.390 | 18.7 | 6 | | 2 | 2 | 18 | 40 | 18 | 32 | |
| | mistral_nemo_12b | 100 | 0.466 | 2.8 | 4 | | 1 | | 1 | 1 | | 8 | |
| **all_generate_pick** | claude_haiku | 31 | 0.417 | 4.7 | 3 | | | | 4 | 5 | | | 5 |
| | gemma4_e4b | 100 | 0.456 | 7.4 | 7 | 3 | | 1 | 33 | 8 | 4 | 1 | 2 |
| | llama31_8b | 100 | 0.376 | 14.4 | 8 | 4 | 2 | 11 | 29 | 45 | 5 | 18 | 1 |
| | mistral_nemo_12b | 100 | 0.464 | 19.5 | 4 | | | | 2 | 21 | | 51 | 4 |
| **all_gen_eval_pick** | deepseek_r1_14b | 20 | 0.453 | 4.9 | 7 | 1 | 1 | 2 | 8 | 12 | 1 | 9 | |
| | gemma4_e4b | 100 | 0.419 | 17.3 | 6 | 3 | 3 | 2 | 45 | 40 | | 11 | |
| | llama31_8b | 100 | 0.379 | 18.4 | 7 | 7 | 1 | 16 | 43 | 42 | 5 | 15 | |
| | mistral_nemo_12b | 100 | 0.518 | 17.2 | 4 | | 1 | | | 6 | | 59 | 3 |
| | qwen3_14b | 1 | 0.607 | 1.0 | 2 | 1 | | | | 1 | | | |
| **all_gen_eval_rand** | gemma4_e4b | 100 | 0.333 | 18.7 | 7 | | 6 | 9 | 24 | 40 | 24 | 24 | 4 |
| | llama31_8b | 100 | 0.354 | 29.4 | 8 | 6 | 23 | 29 | 58 | 48 | 27 | 41 | 3 |
| | mistral_nemo_12b | 100 | 0.278 | 3.8 | 6 | | 3 | 2 | 1 | 1 | 3 | 13 | |

**mTV** = mean total variation distance across 15 fields. **mU%** = mean unmapped % (excluding fields with 0%). **#U** = number of fields with any unmapped values. Omitted columns (age, b_loc, civil, indust, e_type, income, b_ctry) are 0% across all runs.

## Remaining problems — noise floor

The remaining unmapped values are **not fixable via mapping**. They fall into three categories:

### 1. LLM hallucinations (parental_structure, housing_tenure, socioeconomic_class)
Pure gibberish that no alias can catch: "Tiohjuling" (ten-wheeler), "Enhetstablett familj" (unit tablet family), "Tvättstuga" (laundry room), "Eigen hemförsäkring" (home insurance), "Egenhustru" (own wife), "K lugnt arbetande", "börmane". These dominate the unmapped residual for llama31_8b and qwen3_14b.

### 2. Macro-region names (region, llama31_8b only)
llama31_8b produces "Svealand" (33/100) and "Götaland" (23/100) — historical macro-regions that span multiple counties. These cannot be mapped to a single county without inventing a distribution, which violates the no-synthetic-distributions rule.

### 3. Strategy amplification (all_generate_evaluate_random_pick)
The random-pick strategy diversifies outputs into territory the LLMs can't express coherently. llama31_8b reaches 29% mean unmapped across 8 fields on this strategy, vs 17% on all_pick. The randomization produces valid demographic profiles but the LLM's free-text responses for those profiles are garbled.

## Options for further improvement

1. **Structured output enforcement** — JSON schema constraints on the generation side would eliminate hallucinations entirely. Already implemented for Ollama (`format` parameter); could be extended to all providers.
2. **Tighter generation prompts** — enumerate valid values in the prompt for the worst fields (parental_structure, housing_tenure, socioeconomic_class). Tradeoff: constrains model creativity.
3. **Accept the noise floor** — document that small open-source models (7-14B) produce 5-20% unmappable values on free-form demographic fields, and that gemma4_e4b on all_pick is the cleanest combination (0% unmapped).

## Files modified

- `config/assets/scb_reference/category_mappings.json` — ~180 new pipeline_label_mappings
- `src/population_synthetic/comparison/extractor.py` — UTF-8 repair, biological_sex keyword additions ("woman", "hon", "f", "m"), `_json_lookup("region", ...)` call
- `docs/unmapped_matrix_2026-05-29.csv` — full 22-run unmapped matrix (generated)
