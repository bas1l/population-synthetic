# LLM API cost by strategy (Swedish) — price per 100 individuals

**Date:** 2026-07-02

Token counts are sourced from [swedish-token-usage-by-model.md](swedish-token-usage-by-model.md);
per-model API pricing (with provider source links) is in the
[Prices used](#prices-used-per-1m-tokens-usd-standard-synchronous-rate-as-of-2026-07-02) table below.

**Update 2026-07-06:** four OpenRouter seed models from the `feature/openrouter-provider` branch —
DeepSeek V4 Pro, GLM 5.2, Qwen3.7 Max, Mistral Medium 3.5 — were added as baseline-only rows, priced
at OpenRouter catalog rates fetched **2026-07-06** (the rest of the doc's prices are as of 2026-07-02).
The branch's other three seed slugs (`openai/gpt-5.5`, `google/gemini-3.5-flash`,
`anthropic/claude-sonnet-5`) are the same models already tabled here as GPT-5.5, Gemini 3.5 Flash, and
Claude Sonnet 5, so no duplicate rows were added for them.

## Grand total — running every model × every method

The total cost of running **all 21 models × all 5 methods** (105 model/method combinations, each a
separate 100-persona run) on this Swedish population:

| | $ per 100-persona population | $ per 1,000-persona population |
|---|---:|---:|
| **All 21 models × 5 methods (105 runs)** | **174.02** | **1,740.17** |
| — of which 7 own-data models (35 runs) | 43.94 | 439.37 |
| — of which 14 baseline-only models (70 runs) | 130.08 | 1,300.77 |

Per-method total (summed across all 21 models, one method run on every model):

| Method | $/100 | $/1,000 |
|---|---:|---:|
| all_pick | 11.26 | 112.64 |
| all_pick_dag | 11.07 | 110.74 |
| all_generate_pick | 33.83 | 338.27 |
| all_generate_evaluate_random_pick | 46.30 | 463.01 |
| all_generate_evaluate_pick | 71.55 | 715.51 |

Per-model total (summed across all 5 methods, every method run once on that model):

| Model | $/100 | $/1,000 |
|---|---:|---:|
| Claude Haiku 4.5 | 7.48 | 74.78 |
| Claude Opus 4.8 | 24.69 | 246.89 |
| Claude Sonnet 5 | 10.07 | 100.70 |
| DeepSeek R1 14B distill | 1.02 | 10.21 |
| DeepSeek R1 671B (baseline) | 4.44 | 44.36 |
| DeepSeek V4 Pro (baseline) | 2.29 | 22.89 |
| Gemini 3.1 Flash-Lite (baseline) | 2.00 | 20.00 |
| Gemini 3.1 Pro Preview (baseline) | 16.00 | 159.99 |
| Gemini 3.5 Flash (baseline) | 12.00 | 119.99 |
| Gemma 4 E4B | 0.47 | 4.71 |
| GLM 5.2 (baseline) | 5.49 | 54.92 |
| GPT-5.4 (baseline) | 20.00 | 199.99 |
| GPT-5.4 mini (baseline) | 6.00 | 60.00 |
| GPT-5.4 nano (baseline) | 1.63 | 16.34 |
| GPT-5.5 (baseline) | 40.00 | 399.97 |
| Llama 3.1 8B | 0.11 | 1.07 |
| Mistral Medium 3.5 (baseline) | 10.97 | 109.73 |
| Mistral Nemo 12B | 0.10 | 1.01 |
| Qwen-Turbo (baseline) | 0.33 | 3.32 |
| Qwen3.6 Flash (baseline) | 1.50 | 15.00 |
| Qwen3.7 Max (baseline) | 7.43 | 74.33 |

Both marginals sum to the same **174.02 / 1,740.17** grand total. (For the per-model figure divided
by 5 — the average cost of one method on that model — see
[Per model, averaged across the 5 methods](#per-model-averaged-across-the-5-methods) below.)

This is the cost of generating the **same population 105 times over**, once per model/method
combination — useful for budgeting a full cross-model comparison sweep, not for a single production
run (for that, see the per-model and per-model×method breakdowns below).

## Headline — price per 100 / per 1,000 people

"(baseline)" models were never run on this workload — their price is computed from the mean token
count across the 7 own-data models (see [Method](#method) below), so treat those rows as
order-of-magnitude, not a quote.

### Model × method — $ per 100 people

| Model | all_pick | all_generate_pick | all_gen_eval_pick | all_gen_eval_random_pick | all_pick_dag |
|---|---:|---:|---:|---:|---:|
| Mistral Nemo 12B | 0.010 | 0.022 | 0.035 | 0.023 | 0.010 |
| Mistral Medium 3.5 (baseline) | 0.785 | 1.983 | 4.568 | 2.869 | 0.767 |
| Llama 3.1 8B | 0.011 | 0.012 | 0.043 | 0.030 | 0.011 |
| Gemma 4 E4B | 0.037 | 0.103 | 0.119 | 0.175 | 0.037 |
| DeepSeek R1 14B distill | 0.126 | 0.081 | 0.598 | 0.097 | 0.119 |
| DeepSeek R1 671B (baseline) | 0.350 | 0.793 | 1.836 | 1.115 | 0.342 |
| DeepSeek V4 Pro (baseline) | 0.207 | 0.403 | 0.938 | 0.540 | 0.201 |
| Qwen-Turbo (baseline) | 0.025 | 0.060 | 0.137 | 0.084 | 0.025 |
| Qwen3.6 Flash (baseline) | 0.101 | 0.273 | 0.627 | 0.401 | 0.099 |
| Qwen3.7 Max (baseline) | 0.614 | 1.322 | 3.067 | 1.831 | 0.599 |
| GLM 5.2 (baseline) | 0.448 | 0.978 | 2.267 | 1.360 | 0.437 |
| Claude Haiku 4.5 | 0.254 | 1.614 | 2.789 | 2.568 | 0.253 |
| Claude Sonnet 5 | 0.523 | 2.452 | 4.021 | 2.569 | 0.506 |
| Claude Opus 4.8 | 1.186 | 5.984 | 9.717 | 6.569 | 1.235 |
| GPT-5.4 nano (baseline) | 0.109 | 0.297 | 0.683 | 0.438 | 0.106 |
| GPT-5.4 mini (baseline) | 0.405 | 1.091 | 2.506 | 1.602 | 0.396 |
| GPT-5.4 (baseline) | 1.349 | 3.636 | 8.354 | 5.341 | 1.319 |
| GPT-5.5 (baseline) | 2.698 | 7.272 | 16.709 | 10.682 | 2.637 |
| Gemini 3.1 Flash-Lite (baseline) | 0.135 | 0.364 | 0.835 | 0.534 | 0.132 |
| Gemini 3.5 Flash (baseline) | 0.809 | 2.182 | 5.013 | 3.204 | 0.791 |
| Gemini 3.1 Pro Preview (baseline) | 1.079 | 2.909 | 6.684 | 4.273 | 1.055 |

### Model × method — $ per 1,000 people

| Model | all_pick | all_generate_pick | all_gen_eval_pick | all_gen_eval_random_pick | all_pick_dag |
|---|---:|---:|---:|---:|---:|
| Mistral Nemo 12B | 0.10 | 0.22 | 0.35 | 0.23 | 0.10 |
| Mistral Medium 3.5 (baseline) | 7.85 | 19.83 | 45.68 | 28.69 | 7.67 |
| Llama 3.1 8B | 0.11 | 0.12 | 0.43 | 0.30 | 0.11 |
| Gemma 4 E4B | 0.37 | 1.03 | 1.19 | 1.75 | 0.37 |
| DeepSeek R1 14B distill | 1.26 | 0.81 | 5.98 | 0.97 | 1.19 |
| DeepSeek R1 671B (baseline) | 3.50 | 7.93 | 18.36 | 11.15 | 3.42 |
| DeepSeek V4 Pro (baseline) | 2.07 | 4.03 | 9.38 | 5.40 | 2.01 |
| Qwen-Turbo (baseline) | 0.25 | 0.60 | 1.37 | 0.84 | 0.25 |
| Qwen3.6 Flash (baseline) | 1.01 | 2.73 | 6.27 | 4.01 | 0.99 |
| Qwen3.7 Max (baseline) | 6.14 | 13.22 | 30.67 | 18.31 | 5.99 |
| GLM 5.2 (baseline) | 4.48 | 9.78 | 22.67 | 13.60 | 4.37 |
| Claude Haiku 4.5 | 2.54 | 16.14 | 27.89 | 25.68 | 2.53 |
| Claude Sonnet 5 | 5.23 | 24.52 | 40.21 | 25.69 | 5.06 |
| Claude Opus 4.8 | 11.86 | 59.84 | 97.17 | 65.69 | 12.35 |
| GPT-5.4 nano (baseline) | 1.09 | 2.97 | 6.83 | 4.38 | 1.06 |
| GPT-5.4 mini (baseline) | 4.05 | 10.91 | 25.06 | 16.02 | 3.96 |
| GPT-5.4 (baseline) | 13.49 | 36.36 | 83.54 | 53.41 | 13.19 |
| GPT-5.5 (baseline) | 26.98 | 72.72 | 167.09 | 106.82 | 26.37 |
| Gemini 3.1 Flash-Lite (baseline) | 1.35 | 3.64 | 8.35 | 5.34 | 1.32 |
| Gemini 3.5 Flash (baseline) | 8.09 | 21.82 | 50.13 | 32.04 | 7.91 |
| Gemini 3.1 Pro Preview (baseline) | 10.79 | 29.09 | 66.84 | 42.73 | 10.55 |

### Per model, averaged across the 5 methods

| Model | $/100 | $/1,000 |
|---|---:|---:|
| Mistral Nemo 12B | 0.020 | 0.20 |
| Llama 3.1 8B | 0.021 | 0.21 |
| Qwen-Turbo (baseline) | 0.066 | 0.66 |
| Gemma 4 E4B | 0.094 | 0.94 |
| DeepSeek R1 14B distill | 0.204 | 2.04 |
| Qwen3.6 Flash (baseline) | 0.300 | 3.00 |
| GPT-5.4 nano (baseline) | 0.327 | 3.27 |
| Gemini 3.1 Flash-Lite (baseline) | 0.400 | 4.00 |
| DeepSeek V4 Pro (baseline) | 0.458 | 4.58 |
| DeepSeek R1 671B (baseline) | 0.887 | 8.87 |
| GLM 5.2 (baseline) | 1.098 | 10.98 |
| GPT-5.4 mini (baseline) | 1.200 | 12.00 |
| Qwen3.7 Max (baseline) | 1.487 | 14.87 |
| Claude Haiku 4.5 | 1.496 | 14.96 |
| Claude Sonnet 5 | 2.014 | 20.14 |
| Mistral Medium 3.5 (baseline) | 2.195 | 21.95 |
| Gemini 3.5 Flash (baseline) | 2.400 | 24.00 |
| Gemini 3.1 Pro Preview (baseline) | 3.200 | 32.00 |
| GPT-5.4 (baseline) | 4.000 | 40.00 |
| Claude Opus 4.8 | 4.938 | 49.38 |
| GPT-5.5 (baseline) | 7.999 | 79.99 |

### Global estimate (across all 21 models × 5 methods)

- **Mean: $1.66 per 100 people → $16.57 per 1,000**
- **Median: $0.61 per 100 → $6.14 per 1,000** (mean is pulled up by GPT-5.5/Opus outliers — median is
  the more representative single number)
- Range: $0.010/100 (Mistral Nemo 12B, cheapest cell) to $16.71/100 (GPT-5.5 on
  `all_generate_evaluate_pick`, priciest cell)

Cost projection built on the token counts in
[swedish-token-usage-by-model.md](swedish-token-usage-by-model.md), priced at **current (2026-07-02)
standard synchronous API rates** — not batch, not cached. This is a *what-would-it-cost* projection,
not a bill: no run in that doc was actually paid for at these rates (the Claude rows used the `claude`
CLI's own auth, the Ollama rows ran on local/self-hosted hardware for free).

## Method

Two pricing tiers, depending on whether real usage data exists for that exact model:

1. **Own-data models** — 7 models/providers where the source doc has an actual (real or
   `tiktoken`-estimated) token count for that exact model and strategy: Claude Haiku, Claude Sonnet,
   Claude Opus, and — via their nearest OpenRouter-hosted equivalent — Ollama Llama 3.1 8B, Mistral
   Nemo 12B, DeepSeek R1 14B, and Gemma 4 E4B. Cost = that model's own logged tokens × today's price
   for that model/equivalent.
2. **Baseline-only models** — ChatGPT (OpenAI), Gemini (Google), the full-size DeepSeek R1, two
   reference Qwen models, and the four OpenRouter seed models added 2026-07-06 (DeepSeek V4 Pro,
   GLM 5.2, Qwen3.7 Max, Mistral Medium 3.5) were never run against this workload, so there's no token
   count to price. Per user instruction, these are priced against the **mean, Q1, and Q3 of the 7
   own-data models' token counts**, per method — giving a central estimate plus a range rather than a
   single unverified number.

**Caveat on the baseline:** the 7 own-data models range from very terse (Claude: ~160K input tokens
for `all_pick`) to very verbose (DeepSeek R1 14B: ~1,035K input tokens for the same strategy) — verbosity
is a property of the model, not the strategy. Applying that averaged token count to GPT/Gemini pricing
assumes those models would land somewhere in this same spread; there's no evidence for that beyond
"probably in the same ballpark as other instruction-tuned chat models." Treat baseline-only rows as
order-of-magnitude, not a quote.

## Prices used (per 1M tokens, USD, standard synchronous rate, as of 2026-07-02)

| Model | Provider | Input $/1M | Output $/1M | Source |
|---|---|---:|---:|---|
| Claude Haiku 4.5 | Anthropic | 1.00 | 5.00 | [platform.claude.com/.../pricing](https://platform.claude.com/docs/en/about-claude/pricing) |
| Claude Sonnet 5 (intro, through 2026-08-31) | Anthropic | 2.00 | 10.00 | [platform.claude.com/.../pricing](https://platform.claude.com/docs/en/about-claude/pricing) (standard $3/$15 from 2026-09-01) |
| Claude Opus 4.8 | Anthropic | 5.00 | 25.00 | [platform.claude.com/.../pricing](https://platform.claude.com/docs/en/about-claude/pricing) |
| Llama 3.1 8B Instruct | OpenRouter | 0.02 | 0.03 | [openrouter.ai/.../llama-3.1-8b-instruct](https://openrouter.ai/meta-llama/llama-3.1-8b-instruct) |
| Mistral Nemo 12B | OpenRouter | 0.02 | 0.03 | [openrouter.ai/.../mistral-nemo](https://openrouter.ai/mistralai/mistral-nemo) |
| DeepSeek R1 Distill Qwen 14B | OpenRouter | 0.12 | 0.12 | [openrouter.ai/.../deepseek-r1-distill-qwen-14b](https://openrouter.ai/deepseek/deepseek-r1-distill-qwen-14b) |
| Gemma 4 26B-A4B *(proxy for local "Gemma 4 E4B")* | OpenRouter | 0.06 | 0.33 | [openrouter.ai/.../gemma-4-26b-a4b-it](https://openrouter.ai/google/gemma-4-26b-a4b-it) |
| GPT-5.5 (flagship) | OpenAI | 5.00 | 30.00 | [developers.openai.com/api/docs/pricing](https://developers.openai.com/api/docs/pricing) |
| GPT-5.4 (mid) | OpenAI | 2.50 | 15.00 | [developers.openai.com/api/docs/pricing](https://developers.openai.com/api/docs/pricing) |
| GPT-5.4 mini | OpenAI | 0.75 | 4.50 | [developers.openai.com/api/docs/pricing](https://developers.openai.com/api/docs/pricing) |
| GPT-5.4 nano (small) | OpenAI | 0.20 | 1.25 | [developers.openai.com/api/docs/pricing](https://developers.openai.com/api/docs/pricing) |
| Gemini 3.1 Pro Preview (flagship, ≤200K ctx) | Google | 2.00 | 12.00 | [ai.google.dev/gemini-api/docs/pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| Gemini 3.5 Flash (mid) | Google | 1.50 | 9.00 | [ai.google.dev/gemini-api/docs/pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| Gemini 3.1 Flash-Lite (small) | Google | 0.25 | 1.50 | [ai.google.dev/gemini-api/docs/pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| DeepSeek R1 (671B, full MoE — **not** the local 14B distill) | OpenRouter | 0.70 | 2.50 | [openrouter.ai/deepseek/deepseek-r1](https://openrouter.ai/deepseek/deepseek-r1) |
| Qwen3.6 Flash *(reference, not run locally)* | OpenRouter | 0.1875 | 1.125 | [openrouter.ai/qwen](https://openrouter.ai/qwen) |
| Qwen-Turbo *(reference, not run locally)* | OpenRouter | 0.05 | 0.20 | [openrouter.ai/qwen](https://openrouter.ai/qwen) |
| DeepSeek V4 Pro *(OpenRouter seed, fetched 2026-07-06)* | OpenRouter | 0.435 | 0.87 | [openrouter.ai/api/v1/models](https://openrouter.ai/api/v1/models) |
| GLM 5.2 *(OpenRouter seed, fetched 2026-07-06)* | OpenRouter | 0.9086 | 2.8556 | [openrouter.ai/api/v1/models](https://openrouter.ai/api/v1/models) |
| Qwen3.7 Max *(OpenRouter seed, fetched 2026-07-06)* | OpenRouter | 1.25 | 3.75 | [openrouter.ai/api/v1/models](https://openrouter.ai/api/v1/models) |
| Mistral Medium 3.5 *(OpenRouter seed, fetched 2026-07-06)* | OpenRouter | 1.50 | 7.50 | [openrouter.ai/api/v1/models](https://openrouter.ai/api/v1/models) |

The last four rows are the `feature/openrouter-provider` seed models, priced from the live OpenRouter
catalog on **2026-07-06** (`pricing.prompt`/`pricing.completion` × 1e6). Their slugs are forward-dated —
re-confirm each against `https://openrouter.ai/api/v1/models` before committing budget to a real run.

**Model-identity caveats:**
- "Gemma 4 26B-A4B" is OpenRouter's closest listed match to the locally-run "Gemma 4 E4B" naming
  (Google's elastic/MoE "effective-4B-active-params" family) — likely the same model, not confirmed
  identical.
- "DeepSeek R1 14B" served via Ollama is almost certainly `deepseek-r1-distill-qwen-14b`, which *is*
  listed on OpenRouter — that row is a solid match, not a proxy.
- The standalone "DeepSeek R1" baseline-only row is the full 671B-parameter MoE model, a materially
  different (larger, pricier-to-serve) model than the local 14B distill — kept separate deliberately.
- Claude Sonnet 5 pricing reflects the 2026-07-02 introductory rate; it rises to $3/$15 per 1M on
  2026-09-01.

## Per-method token baseline (mean / Q1 / Q3 across the 7 own-data models, 100 personas)

| Method | Input mean | Input Q1 | Input Q3 | Output mean | Output Q1 | Output Q3 |
|---|---:|---:|---:|---:|---:|---:|
| all_pick | 442,762 | 176,633 | 524,930 | 16,133 | 14,939 | 17,264 |
| all_generate_pick | 661,475 | 499,044 | 767,955 | 132,146 | 87,638 | 159,657 |
| all_generate_evaluate_pick | 1,564,660 | 807,384 | 1,676,124 | 296,182 | 226,134 | 318,319 |
| all_generate_evaluate_random_pick | 794,027 | 527,318 | 1,103,321 | 223,714 | 159,293 | 283,409 |
| all_pick_dag | 430,576 | 174,387 | 519,183 | 16,144 | 14,730 | 17,193 |

## Results — price per 100 individuals (USD)

### all_pick

| Model | Provider | Basis | $/100 |
|---|---|---|---:|
| Mistral Nemo 12B | OpenRouter | own data | 0.010 |
| Llama 3.1 8B Instruct | OpenRouter | own data | 0.011 |
| Gemma 4 26B-A4B | OpenRouter | own data | 0.037 |
| DeepSeek R1 Distill Qwen 14B | OpenRouter | own data | 0.126 |
| Claude Haiku 4.5 | Anthropic | own data | 0.254 |
| Claude Sonnet 5 | Anthropic | own data | 0.523 |
| Claude Opus 4.8 | Anthropic | own data | 1.186 |
| Qwen-Turbo | OpenRouter | baseline | 0.025 (Q1 0.012 – Q3 0.030) |
| Qwen3.6 Flash | OpenRouter | baseline | 0.101 (Q1 0.050 – Q3 0.118) |
| GPT-5.4 nano | OpenAI | baseline | 0.109 (Q1 0.054 – Q3 0.127) |
| Gemini 3.1 Flash-Lite | Google | baseline | 0.135 (Q1 0.067 – Q3 0.157) |
| DeepSeek V4 Pro | OpenRouter | baseline | 0.207 (Q1 0.090 – Q3 0.243) |
| DeepSeek R1 (671B) | OpenRouter | baseline | 0.350 (Q1 0.161 – Q3 0.411) |
| GPT-5.4 mini | OpenAI | baseline | 0.405 (Q1 0.200 – Q3 0.471) |
| GLM 5.2 | OpenRouter | baseline | 0.448 (Q1 0.203 – Q3 0.526) |
| Qwen3.7 Max | OpenRouter | baseline | 0.614 (Q1 0.277 – Q3 0.721) |
| Mistral Medium 3.5 | OpenRouter | baseline | 0.785 (Q1 0.377 – Q3 0.917) |
| Gemini 3.5 Flash | Google | baseline | 0.809 (Q1 0.399 – Q3 0.943) |
| Gemini 3.1 Pro Preview | Google | baseline | 1.079 (Q1 0.533 – Q3 1.257) |
| GPT-5.4 | OpenAI | baseline | 1.349 (Q1 0.666 – Q3 1.571) |
| GPT-5.5 | OpenAI | baseline | 2.698 (Q1 1.331 – Q3 3.143) |

### all_pick_dag

| Model | Provider | Basis | $/100 |
|---|---|---|---:|
| Mistral Nemo 12B | OpenRouter | own data | 0.010 |
| Llama 3.1 8B Instruct | OpenRouter | own data | 0.011 |
| Gemma 4 26B-A4B | OpenRouter | own data | 0.037 |
| DeepSeek R1 Distill Qwen 14B | OpenRouter | own data | 0.119 |
| Claude Haiku 4.5 | Anthropic | own data | 0.253 |
| Claude Sonnet 5 | Anthropic | own data | 0.506 |
| Claude Opus 4.8 | Anthropic | own data | 1.235 |
| Qwen-Turbo | OpenRouter | baseline | 0.025 (Q1 0.012 – Q3 0.029) |
| Qwen3.6 Flash | OpenRouter | baseline | 0.099 (Q1 0.049 – Q3 0.117) |
| GPT-5.4 nano | OpenAI | baseline | 0.106 (Q1 0.053 – Q3 0.125) |
| Gemini 3.1 Flash-Lite | Google | baseline | 0.132 (Q1 0.066 – Q3 0.156) |
| DeepSeek V4 Pro | OpenRouter | baseline | 0.201 (Q1 0.089 – Q3 0.241) |
| DeepSeek R1 (671B) | OpenRouter | baseline | 0.342 (Q1 0.159 – Q3 0.406) |
| GPT-5.4 mini | OpenAI | baseline | 0.396 (Q1 0.197 – Q3 0.467) |
| GLM 5.2 | OpenRouter | baseline | 0.437 (Q1 0.201 – Q3 0.521) |
| Qwen3.7 Max | OpenRouter | baseline | 0.599 (Q1 0.273 – Q3 0.713) |
| Mistral Medium 3.5 | OpenRouter | baseline | 0.767 (Q1 0.372 – Q3 0.908) |
| Gemini 3.5 Flash | Google | baseline | 0.791 (Q1 0.394 – Q3 0.934) |
| Gemini 3.1 Pro Preview | Google | baseline | 1.055 (Q1 0.526 – Q3 1.245) |
| GPT-5.4 | OpenAI | baseline | 1.319 (Q1 0.657 – Q3 1.556) |
| GPT-5.5 | OpenAI | baseline | 2.637 (Q1 1.314 – Q3 3.112) |

### all_generate_pick

| Model | Provider | Basis | $/100 |
|---|---|---|---:|
| Llama 3.1 8B Instruct | OpenRouter | own data | 0.012 |
| Mistral Nemo 12B | OpenRouter | own data | 0.022 |
| DeepSeek R1 Distill Qwen 14B | OpenRouter | own data | 0.081 |
| Gemma 4 26B-A4B | OpenRouter | own data | 0.103 |
| Claude Haiku 4.5 | Anthropic | own data | 1.614 |
| Claude Sonnet 5 | Anthropic | own data | 2.452 |
| Claude Opus 4.8 | Anthropic | own data | 5.984 |
| Qwen-Turbo | OpenRouter | baseline | 0.060 (Q1 0.042 – Q3 0.070) |
| Qwen3.6 Flash | OpenRouter | baseline | 0.273 (Q1 0.192 – Q3 0.324) |
| GPT-5.4 nano | OpenAI | baseline | 0.297 (Q1 0.209 – Q3 0.353) |
| Gemini 3.1 Flash-Lite | Google | baseline | 0.364 (Q1 0.256 – Q3 0.431) |
| DeepSeek V4 Pro | OpenRouter | baseline | 0.403 (Q1 0.293 – Q3 0.473) |
| GPT-5.4 mini | OpenAI | baseline | 1.091 (Q1 0.769 – Q3 1.294) |
| DeepSeek R1 (671B) | OpenRouter | baseline | 0.793 (Q1 0.568 – Q3 0.937) |
| GLM 5.2 | OpenRouter | baseline | 0.978 (Q1 0.704 – Q3 1.154) |
| Qwen3.7 Max | OpenRouter | baseline | 1.322 (Q1 0.952 – Q3 1.559) |
| Mistral Medium 3.5 | OpenRouter | baseline | 1.983 (Q1 1.406 – Q3 2.349) |
| Gemini 3.5 Flash | Google | baseline | 2.182 (Q1 1.537 – Q3 2.589) |
| Gemini 3.1 Pro Preview | Google | baseline | 2.909 (Q1 2.050 – Q3 3.452) |
| GPT-5.4 | OpenAI | baseline | 3.636 (Q1 2.562 – Q3 4.315) |
| GPT-5.5 | OpenAI | baseline | 7.272 (Q1 5.124 – Q3 8.629) |

### all_generate_evaluate_pick

| Model | Provider | Basis | $/100 |
|---|---|---|---:|
| Mistral Nemo 12B | OpenRouter | own data | 0.035 |
| Llama 3.1 8B Instruct | OpenRouter | own data | 0.043 |
| Gemma 4 26B-A4B | OpenRouter | own data | 0.119 |
| DeepSeek R1 Distill Qwen 14B | OpenRouter | own data | 0.598 |
| Claude Haiku 4.5 | Anthropic | own data | 2.789 |
| Claude Sonnet 5 | Anthropic | own data | 4.021 |
| Claude Opus 4.8 | Anthropic | own data | 9.717 |
| Qwen-Turbo | OpenRouter | baseline | 0.137 (Q1 0.086 – Q3 0.147) |
| Qwen3.6 Flash | OpenRouter | baseline | 0.627 (Q1 0.406 – Q3 0.672) |
| GPT-5.4 nano | OpenAI | baseline | 0.683 (Q1 0.444 – Q3 0.733) |
| Gemini 3.1 Flash-Lite | Google | baseline | 0.835 (Q1 0.541 – Q3 0.897) |
| DeepSeek V4 Pro | OpenRouter | baseline | 0.938 (Q1 0.548 – Q3 1.006) |
| DeepSeek R1 (671B) | OpenRouter | baseline | 1.836 (Q1 1.131 – Q3 1.969) |
| GLM 5.2 | OpenRouter | baseline | 2.267 (Q1 1.379 – Q3 2.432) |
| GPT-5.4 mini | OpenAI | baseline | 2.506 (Q1 1.623 – Q3 2.690) |
| Qwen3.7 Max | OpenRouter | baseline | 3.067 (Q1 1.857 – Q3 3.289) |
| Mistral Medium 3.5 | OpenRouter | baseline | 4.568 (Q1 2.907 – Q3 4.902) |
| Gemini 3.5 Flash | Google | baseline | 5.013 (Q1 3.246 – Q3 5.379) |
| Gemini 3.1 Pro Preview | Google | baseline | 6.684 (Q1 4.328 – Q3 7.172) |
| GPT-5.4 | OpenAI | baseline | 8.354 (Q1 5.410 – Q3 8.965) |
| GPT-5.5 | OpenAI | baseline | 16.709 (Q1 10.821 – Q3 17.930) |

### all_generate_evaluate_random_pick

| Model | Provider | Basis | $/100 |
|---|---|---|---:|
| Mistral Nemo 12B | OpenRouter | own data | 0.023 |
| Llama 3.1 8B Instruct | OpenRouter | own data | 0.030 |
| DeepSeek R1 Distill Qwen 14B | OpenRouter | own data | 0.097 |
| Gemma 4 26B-A4B | OpenRouter | own data | 0.175 |
| Claude Sonnet 5 | Anthropic | own data | 2.569 |
| Claude Haiku 4.5 | Anthropic | own data | 2.568 |
| Claude Opus 4.8 | Anthropic | own data | 6.569 |
| Qwen-Turbo | OpenRouter | baseline | 0.084 (Q1 0.058 – Q3 0.112) |
| Qwen3.6 Flash | OpenRouter | baseline | 0.401 (Q1 0.278 – Q3 0.526) |
| GPT-5.4 nano | OpenAI | baseline | 0.438 (Q1 0.305 – Q3 0.575) |
| Gemini 3.1 Flash-Lite | Google | baseline | 0.534 (Q1 0.371 – Q3 0.701) |
| DeepSeek V4 Pro | OpenRouter | baseline | 0.540 (Q1 0.368 – Q3 0.727) |
| DeepSeek R1 (671B) | OpenRouter | baseline | 1.115 (Q1 0.767 – Q3 1.481) |
| GLM 5.2 | OpenRouter | baseline | 1.360 (Q1 0.934 – Q3 1.812) |
| GPT-5.4 mini | OpenAI | baseline | 1.602 (Q1 1.112 – Q3 2.103) |
| Qwen3.7 Max | OpenRouter | baseline | 1.831 (Q1 1.256 – Q3 2.442) |
| Mistral Medium 3.5 | OpenRouter | baseline | 2.869 (Q1 1.986 – Q3 3.781) |
| Gemini 3.5 Flash | Google | baseline | 3.204 (Q1 2.225 – Q3 4.206) |
| Gemini 3.1 Pro Preview | Google | baseline | 4.273 (Q1 2.966 – Q3 5.608) |
| GPT-5.4 | OpenAI | baseline | 5.341 (Q1 3.708 – Q3 7.009) |
| GPT-5.5 | OpenAI | baseline | 10.682 (Q1 7.415 – Q3 14.019) |

## Takeaways

- **Own-data OpenRouter-hosted small/mid open models (Llama 3.1 8B, Mistral Nemo 12B, Gemma 4,
  DeepSeek R1 14B distill) are far cheaper than every frontier hosted model** across every strategy —
  cents per 100 personas where the hosted frontier tiers reach dollars. Llama and Mistral run 1-2
  orders of magnitude below even the cheapest frontier tier (Claude Haiku); Gemma and DeepSeek R1 14B
  are closer — DeepSeek is only ~2× cheaper than Haiku on the single-step strategies
  (`all_pick`/`all_pick_dag`) and ~4.7× on `all_generate_evaluate_pick`, since it is by far the most
  verbose open model. This tracks with the source doc's own finding that these open models are the
  most verbose (more input tokens re-sent per multi-step strategy), so the gap vs. Claude's terser
  prompting would be even larger if their token counts matched.
- **The four OpenRouter seed models slot in as mid-cheap baseline options.** DeepSeek V4 Pro is the
  cheapest *frontier-tier* hosted model in the table (~$2.29/100 for the full 5-strategy sweep, ~17×
  below GPT-5.5 at $40.00), and the open-weight OpenRouter tiers GLM 5.2 ($5.49) and Qwen3.7 Max
  ($7.43) sit roughly an order of magnitude below the closed frontier models — while Mistral Medium 3.5
  ($10.97), on its $7.50/1M output price, lands just above Claude Sonnet 5 on the output-heavy
  strategies. These are baseline (mean-token) projections, not measured runs — a model's own verbosity
  will shift the real figure, so treat them as order-of-magnitude, like the other baseline rows.
- Strategy cost scales roughly with call count and step complexity: `all_generate_evaluate_pick` (the
  costliest strategy, ~5,100-5,300 calls) runs **~6.6× the cost of `all_pick`/`all_pick_dag`** (~1,700
  calls) in aggregate. Per model the multiplier varies widely with each model's own verbosity — from
  ~3.2× (Gemma 4) to ~11× (Claude Haiku) — so treat the ~6-7× figure as the cross-model average, not
  a per-model constant.
- Among the three Claude tiers actually run, Haiku is up to ~2.1× cheaper than Sonnet (essentially
  tied on `all_generate_evaluate_random_pick`) and 2.6-4.9× cheaper than Opus across strategies —
  Opus's much higher output-token price ($25 vs $5/1M) dominates the gap even though Opus's own logged
  token counts are usually the *lowest* of the three Claude tiers.
- Baseline-only rows (GPT, Gemini, full-size DeepSeek R1, reference Qwen) should be read as
  order-of-magnitude estimates only — see the caveat above. If a firm quote is ever needed for GPT or
  Gemini on this workload, the right move is to actually run one strategy against that provider and
  replace the baseline row with real data, the same way the 7 own-data rows were built.
