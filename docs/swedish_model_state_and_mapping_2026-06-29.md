# Swedish Population Synthesis — State of Models & Mapping Analysis

*Snapshot: 2026-06-29. Supersedes the 2026-05-29 mapping notes.*

## Context

This is an analysis of where each LLM stands in generating a statistically realistic
synthetic Swedish population, with primary focus on **mapping issues**: cases where a model
emits a *legitimate category value* that the pipeline fails to map onto the canonical schema
and therefore should be counted as **"not mapped"** rather than silently passed through.

Data sources:
- Run outputs under `F:/liu-onedrive-nospecial-carac/_Teams/Gauss/02_Data/01_Raw/swedish_*`
- Per-run comparison reports under `.../02_Data/03_Analysis/` (marginals + chi-squared + TV)
- Mapping machinery: `src/population_synth/comparison/normalizer.py`,
  `src/population_synth/comparison/extractor.py`,
  `config/assets/scb_reference/category_mappings.json`
- Prior mapping-fix notes: `docs/swedish_mapping_fix_2026-05-29.md`,
  `docs/unmapped_matrix_2026-05-29.csv`, `docs/swedish_persona_matrix_2026-05-29.md`

---

## 1. Root cause: why "not mapped" happens at all

The Swedish axis (`config/countries/swedish.yaml`) uses
`simulation_config_004_swedish_generative.json` — a **generative** config that gives the LLM
only *descriptions*, not an enumerated category list. The model therefore free-generates
labels (often Swedish, sometimes typo'd or hallucinated), and
`config/assets/scb_reference/category_mappings.json` must catch every variant *after the
fact* via `pipeline_label_mappings`. This is the structural origin of the unmapped "noise
floor". (The enumerated config — `simulation_config_003_swedish_flat.json` — is **not** what
the swedish axis runs.)

### Two code paths disagree on what "not mapped" means

| Path | Function | Behaviour on an unmapped value |
|---|---|---|
| Extractor (pipeline → schema) | `extractor.py::_extract_flat` | Marks value **`"Non-standard label"`**, appends to `unmapped`, logs a warning |
| Normalizer (raw SCB / re-normalize) | `normalizer.py::normalize_raw_to_schema` (facade; impl now `reference_mapper/base.py::BaseReferenceMapper`) | **Passes the raw string through unchanged** (`_ci_get` returns `raw` when no key matches) — never flagged |

**Implication:** comparison reports under-count unmapped values whenever the normalizer path
is used, because an unmapped label silently becomes a "real" category in the marginals
instead of landing in a `"Non-standard label"` / unknown bucket. This is the single most
important methodological caveat in the current numbers — the per-attribute "unmapped %" is a
**lower bound**.

---

## 2. Model progress matrix (coverage)

42 `swedish_*` run directories exist across 5 strategies. Completed-identity coverage
(from the 2026-05-29 persona matrix, cross-checked against raw run dirs):

| Model | all_pick | all_pick_dag | all_generate_pick | all_gen_eval_pick | all_gen_eval_random_pick |
|---|---|---|---|---|---|
| claude_haiku | 100 | 100 | 31 | run dir | — |
| claude_opus | 100 | run dir | run dir | run dir | run dir |
| claude_sonnet | 1 | run dir | run dir | run dir | run dir |
| ollama_gemma4_e4b | 100 | 100 | 100 | 100 | 100 |
| ollama_llama31_8b | 100 | 100 | 100 | 100 | 100 |
| ollama_mistral_nemo_12b | 100 | 100 | 100 | 100 | 100 |
| ollama_qwen3_14b | 100 | — | — | 1 | — |
| ollama_deepseek_r1_14b | 100 | run dir | run dir | 3–20 | run dir |
| ollama_lucie_7b | 16 | — | — | — | partial |
| ollama_llama33_70b | — | — | — | — | 0 |

- **Gold-standard trio** (full 5-strategy × 100-persona coverage): `gemma4_e4b`,
  `llama31_8b`, `mistral_nemo_12b`.
- **Claude family**: directories exist for all strategies, but several are thin
  (`claude_sonnet` all_pick = 1 persona; `claude_haiku` all_generate_pick = 31).
- **Stragglers**: `lucie_7b` (high failure rate, 16/100), `llama33_70b` (0 personas),
  `deepseek_r1_14b` (partial on the evaluate strategies).

---

## 3. Quality snapshot (distribution fidelity, not mapping)

Mean Total-Variation distance vs SCB reference (lower = better), `all_pick` strategy:

| Model | mean TV | Notes |
|---|---|---|
| ollama_llama31_8b | 0.357 | best mean TV after mapping passes |
| ollama_mistral_nemo_12b | 0.413 | cleanest unmapped rate (3.8%) |
| claude_haiku | 0.426 | |
| ollama_qwen3_14b | 0.459 | |
| ollama_gemma4_e4b | 0.487 | 0% unmapped on all_pick |
| ollama_lucie_7b | 0.556 | small N (16), noisy |

**Structurally hard attributes** (high TV across *all* models, independent of mapping):
`household_size`, `age_group`, `region`, `industry_sector` — these diverge from SCB even when
fully mapped, so they are a *sampling/prompting* problem, not a mapping problem.
**Best-matched attributes**: `employment_status`, `birth_location`, `parental_structure`,
`income_source`.

> Claude runs report ~0 unmapped in their JSON reports, but note this is partly the
> normalizer pass-through artifact (§1) plus their strong instruction-following; the Ollama
> runs expose the real mapping gaps below.

---

## 4. Mapping issues — the core finding

### 4a. Per-attribute "not mapped" status

Aggregated from `docs/unmapped_matrix_2026-05-29.csv` (22 runs) and the live DeepSeek-R1
comparison report. "Genuine category" = the model emitted a coherent, real-world label that
*should* map but currently doesn't; "Noise" = hallucination/gibberish that legitimately
can't map.

| Attribute | Worst unmapped % | Verdict | Detail |
|---|---|---|---|
| age_group | 0% | ✅ solved | fully mapped everywhere |
| biological_sex | 0–7% | ✅ effectively solved | Swedish synonyms added; deepseek shows 4 stray "Non-standard label" |
| education_level | 1–23% | ⚠️ mostly solved | random_pick on llama31 spikes to 23%; otherwise ≤1% |
| employment_status | 0–29% | ⚠️ genuine gaps | random_pick spikes; deepseek emits English/typo variants |
| birth_location | 0% | ✅ solved | |
| **socioeconomic_class** | up to **58%** | 🔴 genuine + noise | "Låg/Mellan/Hög" variants are genuine (fixable); also true hallucinations |
| **parental_structure** | up to **53%** | 🔴 genuine gaps | config-style labels not aliased (see 4b) |
| **region** | up to **39%** | 🟠 partly unmappable | "Svealand"/"Götaland" are macro-regions → cannot map to a single county |
| civil_status | 0–4% | 🔴 small genuine gaps | "cohabitant", "Einer", "kombinerad" unmapped |
| industry_sector | 0% | ✅ solved | |
| **employment_type** | up to **59%** | 🔴 largest gap | 14 distinct unmapped labels in one run (see 4b) |
| **housing_tenure** | up to **59%** | 🔴 genuine + noise | many tenant/owner variants; 19% "unknown" in deepseek |
| household_size | 0% (mapping) | ✅ mapped | high TV is a sampling issue, not mapping |
| income_source | 0% | ✅ solved | |
| birth_country_detail | 0–1% | ✅ effectively solved | one stray "Jönköping" (a city, mis-emitted as country) |

**Fully solved (0% across all runs):** age_group, birth_location, industry_sector,
employment_type *schema*, income_source, household_size mapping, birth_country_detail.

**Most problematic (genuine categories being dropped):** `employment_type`,
`housing_tenure`, `socioeconomic_class`, `parental_structure`.

### 4b. Genuine categories currently marked "not mapped" (the actionable list)

These are real category values a model produced that *have* a clear canonical target but no
alias today — i.e. exactly the "has a category but shows as not mapped" cases:

- **employment_type** — 14 raw labels from `deepseek_r1_14b` with no mapping:
  `förtid`, `fulltid`, `tillståndsanställning`, `anstellning`, `påtjanst`, `employee`,
  `full-time employee`, `palka`, `contract`, `standard_employee`, `användaromsatt`,
  `full_time_employee`, `öppen`, `self_employed`. Most map cleanly to
  `Permanent Full-time` / `Temporary Full-time` / `Self-Employed`. Also note the
  config/schema mismatch `"Self-Employed/Freelance"` (emitted) vs `"Self-Employed"` (schema).
- **parental_structure** — generative/config-flavoured labels not aliased:
  `Two Parents (Intact)`→`Nuclear Family`, `Single Parent (Mother/Father)`→`Single Parent`,
  `Divorced/Split Household`→`Single Parent`, `Adoptive/Foster Care`→`Nuclear Family`,
  `Orphaned/Ward of State`→`Living Alone`.
- **civil_status** — `cohabitant` / `Cohabitant` / `Sammanboende`→`Married` (or a
  cohabiting bucket), `Einer`→`Single/Never Married`, `kombinerad`→needs review.
- **socioeconomic_class** — Swedish magnitude words `Låg`/`Mellan`/`Hög` and
  `Upper-middle class` style variants that resolve to the 4 canonical classes.
- **housing_tenure** — tenant/owner Swedish variants (`Eget hus`, `Hyrbostad`, etc.); many
  added in the 2026-05-29 passes but DeepSeek still shows a 19% unknown tail.

### 4c. Genuinely unmappable (the noise floor — do NOT force-map)

Per the no-synthetic-distributions rule, these must stay "not mapped" rather than be
invented into a category:
- **Macro-regions**: `Svealand` (33/100), `Götaland` (23/100) on llama31 — span multiple
  counties; mapping to one county would fabricate a distribution.
- **Hallucinations**: `Tiohjuling` ("ten-wheeler"), `Enhetstablett familj`, `börmane`,
  `användaromsatt`, etc. — not real categories.
- **Strategy amplification**: `all_generate_evaluate_random_pick` inflates unmapped rates
  (llama31 reaches 29% mean) by design — the random pick diversifies outputs.

---

## 5. Bottom line

1. **Coverage** is strong for the Ollama gold-standard trio and partial/thin for Claude and
   the larger Ollama models; `llama33_70b` and `lucie_7b` are effectively un-run.
2. **Distribution fidelity** is gated by *sampling*, not mapping, on `household_size`,
   `age_group`, `region`, `industry_sector` — no alias will fix those.
3. **Mapping** is solved for 7+ attributes; the live gaps are concentrated in
   `employment_type`, `housing_tenure`, `socioeconomic_class`, `parental_structure`, with a
   long tail of genuine-but-unaliased Swedish/English/typo variants (§4b).
4. **Methodology caveat**: reported unmapped % is a lower bound because `normalizer.py`
   passes unmapped raw values through instead of flagging them (§1). The DeepSeek run — read
   directly — exposes the gaps the aggregated CSV hides.

---

## Verification

This report is reproducible from existing artifacts (read-only):
- Coverage: `ls` of `…/02_Data/01_Raw/swedish_*` and `docs/swedish_persona_matrix_2026-05-29.md`.
- Mapping %: `docs/unmapped_matrix_2026-05-29.csv` columns
  `mean_unmapped_%, socio, parent, reg, housing, e_type, …`.
- Live unmapped labels: the per-run JSON comparison report for
  `swedish_all_pick_ollama_deepseek_r1_14b` (`unmapped_categories` / `unknown_count_*`
  fields), regenerated via
  `python scripts/analyze/compare_pipeline_to_scb.py --model-id ollama_deepseek_r1_14b --strategy-id all_pick`.
- Code behaviour: `normalizer.py::normalize_raw_to_schema` (raw pass-through via `_ci_get`)
  vs `extractor.py::_extract_flat` ("Non-standard label" + `unmapped` list).
