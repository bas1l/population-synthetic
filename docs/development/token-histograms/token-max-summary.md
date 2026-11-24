# Per-call token distribution (Swedish) — max context size per method × model

**Date:** 2026-07-02

Companion to [`swedish-token-usage-by-model.md`](../swedish-token-usage-by-model.md), which
records only per-strategy **sums**. This file characterises the per-call **distribution** so the
maximum context size can be read off directly. One histogram figure per model
(`tokens_<model>.png`, a grid of methods × [input, output]); regenerate with
[`generate_token_histograms.py`](generate_token_histograms.py).

**Token source per model** (same split as the companion doc):
- **Ollama** → `Src=REAL`: per-call `prompt_tokens`/`completion_tokens` straight from `logs/run_*.log`.
- **Claude** → `Src=EST`: `tiktoken cl100k_base` proxy over each call's `prompt` / `raw_response`.

**Caveats.**
- `Max out = 2048` for reasoning models (deepseek, qwen3, gemma) on `generate*` methods is the
  `num_predict` generation ceiling being hit — a truncation cap, not a natural length, so those
  output maxima are lower bounds on what the model would have produced.
- Claude `Src=EST` input counts see only the logged `prompt` field; the `claude` CLI's
  system-prompt / tool overhead is not captured, so real Claude input tokens are higher than shown.
- `swedish_all_generate_evaluate_random_pick_ollama_llama33_70b` had neither logged tokens nor
  persona JSONL, so it is absent.

**Headline:** the largest single prompt observed anywhere is **~2,659 input tokens**
(qwen3_14b / deepseek_r1_14b on the generate-evaluate methods); no call exceeds ~5k total tokens.

| Model | Method | Src | Calls | Max in | p95 in | Med in | Max out | p95 out | Med out |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| claude_haiku | all_pick | EST | 1700 | 151 | 142 | 89 | 18 | 14 | 11 |
| claude_haiku | all_pick_dag | EST | 1702 | 158 | 142 | 95 | 19 | 14 | 11 |
| claude_haiku | all_generate_pick | EST | 3400 | 319 | 251 | 144 | 415 | 172 | 20 |
| claude_haiku | all_generate_evaluate_pick | EST | 5118 | 400 | 280 | 164 | 283 | 162 | 76 |
| claude_haiku | all_generate_evaluate_random_pick | EST | 3300 | 402 | 307 | 167 | 641 | 182 | 126 |
| claude_opus | all_pick | EST | 1701 | 182 | 154 | 94 | 18 | 14 | 7 |
| claude_opus | all_pick_dag | EST | 1700 | 197 | 161 | 97 | 31 | 16 | 8 |
| claude_opus | all_generate_pick | EST | 3400 | 369 | 242 | 135 | 223 | 150 | 15 |
| claude_opus | all_generate_evaluate_pick | EST | 5110 | 404 | 260 | 156 | 235 | 128 | 25 |
| claude_opus | all_generate_evaluate_random_pick | EST | 3300 | 341 | 256 | 150 | 177 | 108 | 43 |
| claude_sonnet | all_pick | EST | 1700 | 201 | 177 | 107 | 23 | 14 | 9 |
| claude_sonnet | all_pick_dag | EST | 1700 | 199 | 174 | 96 | 24 | 17 | 8 |
| claude_sonnet | all_generate_pick | EST | 3400 | 365 | 264 | 141 | 226 | 160 | 19 |
| claude_sonnet | all_generate_evaluate_pick | EST | 5102 | 407 | 262 | 157 | 502 | 132 | 29 |
| claude_sonnet | all_generate_evaluate_random_pick | EST | 3310 | 356 | 246 | 147 | 356 | 123 | 37 |
| ollama_deepseek_r1_14b | all_pick | REAL | 1700 | 1568 | 919 | 583 | 23 | 12 | 8 |
| ollama_deepseek_r1_14b | all_pick_dag | REAL | 1700 | 1569 | 831 | 555 | 20 | 12 | 8 |
| ollama_deepseek_r1_14b | all_generate_pick | REAL | 3460 | 2013 | 1123 | 709 | 2048 | 176 | 15 |
| ollama_deepseek_r1_14b | all_generate_evaluate_pick | REAL | 6215 | 2446 | 1406 | 751 | 2048 | 200 | 41 |
| ollama_deepseek_r1_14b | all_generate_evaluate_random_pick | REAL | 3799 | 2659 | 1493 | 833 | 2048 | 201 | 87 |
| ollama_gemma4_e4b | all_pick | REAL | 3413 | 397 | 380 | 318 | 22 | 13 | 8 |
| ollama_gemma4_e4b | all_pick_dag | REAL | 3400 | 401 | 377 | 313 | 19 | 13 | 8 |
| ollama_gemma4_e4b | all_generate_pick | REAL | 7059 | 637 | 486 | 335 | 296 | 141 | 12 |
| ollama_gemma4_e4b | all_generate_evaluate_pick | REAL | 11674 | 658 | 521 | 352 | 2048 | 148 | 19 |
| ollama_gemma4_e4b | all_generate_evaluate_random_pick | REAL | 7316 | 706 | 595 | 368 | 2048 | 151 | 64 |
| ollama_llama31_8b | all_pick | REAL | 1700 | 394 | 366 | 299 | 25 | 17 | 12 |
| ollama_llama31_8b | all_pick_dag | REAL | 1700 | 388 | 364 | 299 | 28 | 17 | 11 |
| ollama_llama31_8b | all_generate_pick | REAL | 5166 | 691 | 449 | 331 | 365 | 156 | 20 |
| ollama_llama31_8b | all_generate_evaluate_pick | REAL | 5777 | 804 | 482 | 343 | 449 | 146 | 34 |
| ollama_llama31_8b | all_generate_evaluate_random_pick | REAL | 3787 | 861 | 485 | 345 | 475 | 149 | 47 |
| ollama_lucie_7b | all_pick | REAL | 1515 | 205 | 188 | 85 | 329 | 36 | 8 |
| ollama_mistral_nemo_12b | all_pick | REAL | 1700 | 382 | 355 | 291 | 34 | 12 | 8 |
| ollama_mistral_nemo_12b | all_pick_dag | REAL | 1700 | 369 | 346 | 283 | 16 | 11 | 8 |
| ollama_mistral_nemo_12b | all_generate_pick | REAL | 3400 | 550 | 382 | 316 | 297 | 105 | 10 |
| ollama_mistral_nemo_12b | all_generate_evaluate_pick | REAL | 5103 | 564 | 383 | 321 | 297 | 110 | 14 |
| ollama_mistral_nemo_12b | all_generate_evaluate_random_pick | REAL | 3326 | 471 | 386 | 325 | 142 | 103 | 16 |
| ollama_qwen3_14b | all_pick | REAL | 1725 | 1772 | 1054 | 639 | 48 | 17 | 8 |
| ollama_qwen3_14b | all_pick_dag | REAL | 1700 | 2131 | 1139 | 683 | 31 | 18 | 9 |
| ollama_qwen3_14b | all_generate_pick | REAL | 3855 | 2523 | 1968 | 1059 | 2048 | 420 | 20 |
| ollama_qwen3_14b | all_generate_evaluate_pick | REAL | 2530 | 2659 | 2086 | 843 | 2048 | 2048 | 124 |
| ollama_qwen3_14b | all_generate_evaluate_random_pick | REAL | 1791 | 2621 | 2185 | 991 | 2048 | 2048 | 129 |