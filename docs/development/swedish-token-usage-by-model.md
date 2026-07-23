# LLM token usage by strategy (Swedish) — per model

**Date:** 2026-07-02

Token usage (input/output) per generation strategy ("method"), Swedish country only, one section
per model. Some models log real token counts in their run logs; others (Claude) never did, so those
sections fall back to a retroactive `tiktoken` estimate. Each section states clearly which applies.

## Claude Haiku — retroactive estimate (no real token data exists)

Token usage is not recorded anywhere for Claude-based generation runs (haiku or sonnet). The
`analysis/generation_metadata/` pipeline (`diagnostics.py`, `joiner.py`, `log_parser.py`) is built to
read `prompt_tokens`/`completion_tokens` from `llm_interactions.jsonl` and `logs/run_*.log`, but the
`claude` CLI provider never logged token counts for any past run. As a control, the same pipeline
does find token counts in Ollama-model run logs (e.g. `seed_034_all_pick_llama33`), so this is an
upstream data-collection gap in the Claude CLI client, not a bug in the analyzer. Call counts are
available; token counts are not, and cannot be recovered from existing aggregate reports.

### Method

For each Swedish haiku strategy, every call record in `persona_XXXXX/llm_interactions.jsonl`
(raw run data under `F:/liu-onedrive-nospecial-carac/_Teams/Gauss/02_Data/01_Raw/`) was read and its
`prompt` field (input) and `raw_response` field (output) were tokenized with `tiktoken`
(`cl100k_base` encoding). Neither `tiktoken` nor the `anthropic` SDK was installed at the time;
`tiktoken` was installed into the `popsynth` env to run this estimate. `cl100k_base` is OpenAI's
tokenizer, not Claude's — real Claude token counts will differ, typically within ~10-20%, direction
not guaranteed. If a tighter estimate is ever needed, installing the `anthropic` SDK would allow using
Anthropic's own tokenizer instead of this proxy.

Manifests: `config/synthetic/manifests/identity_manifest_0{14,15,16,17,30}_claude_haiku.yaml`.

**Caveat:** the input-token estimate reflects only the logged `prompt` field. Any system-prompt or
tool-use overhead the `claude` CLI provider adds under the hood is not captured.

All 100 personas per strategy were covered; call counts matched exactly what the call-count-only
investigation found, with zero malformed or missing `prompt`/`raw_response` records.

### Results — Swedish, Claude Haiku (ESTIMATED)

| Strategy | Calls | Personas | Est. Input Tokens | Est. Output Tokens | Est. Total |
|---|---:|---:|---:|---:|---:|
| all_pick | 1,700 | 100 | 159,026 | 18,982 | 178,008 |
| all_generate_pick | 3,400 | 100 | 500,615 | 222,652 | 723,267 |
| all_generate_evaluate_pick | 5,118 | 100 | 855,415 | 386,775 | 1,242,190 |
| all_generate_evaluate_random_pick | 3,300 | 100 | 576,732 | 398,253 | 974,985 |
| all_pick_dag | 1,702 | 100 | 158,145 | 18,977 | 177,122 |
| **Total (5 strategies)** | **15,220** | **500** | **2,249,933** | **1,045,639** | **3,295,572** |

## Ollama Llama 3.1 (8B) — real token counts

Unlike Claude, Ollama runs log real `prompt_eval_count`/`eval_count`-derived token fields in
`logs/run_*.log`. These totals come from actually running the generation-metadata pipeline
(`scripts/analyze/summarize_generation_metadata.py` → `population_synthetic.analysis.generation_metadata`)
against the on-disk raw directories `swedish_{strategy}_ollama_llama31_8b` — no tiktoken estimation was needed.

Manifests: `identity_manifest_044-048_ollama_llama31_8b.yaml`. All 5 strategies have matching runs,
100 personas each.

**Caveat:** `all_generate_pick`'s run directory spans 3 log files over nearly a month (resumed runs,
no correlation keys in the logs), so the joiner falls back to timestamp-proximity matching across the
resume gap. Only ~45% of its 3,398 calls matched a logged token record — that row is a real but
**incomplete lower bound**, not a full total. All other strategies matched ≥95% of calls.

### Results — Swedish, Ollama Llama 3.1 (8B) (REAL)

| Strategy | Calls | Personas | Input Tokens | Output Tokens | Total Tokens | Match rate |
|---|---:|---:|---:|---:|---:|---|
| all_pick | 1,700 | 100 | 511,173 | 19,927 | 531,100 | 99.9% |
| all_generate_pick | 3,398 | 100 | 523,257 | 66,788 | 590,045 | 45.1% (partial, lower bound) |
| all_generate_evaluate_pick | 5,216 | 100 | 1,770,590 | 249,862 | 2,020,452 | 95.6% |
| all_generate_evaluate_random_pick | 3,368 | 100 | 1,174,084 | 212,353 | 1,386,437 | 97.8% |
| all_pick_dag | 1,700 | 100 | 510,580 | 19,843 | 530,423 | 99.9% |

## Ollama Mistral Nemo 12B — real token counts

Same real-token-count approach as Llama 3.1: `logs/run_*.log` parsed via the generation-metadata
pipeline against the on-disk raw directories `swedish_{strategy}_ollama_mistral_nemo_12b`. All 5
strategies had high match rates (94-99.9%), so no `tiktoken` estimation fallback was needed for any
row.

No repo manifest references this model (the only "mistral" manifest in
`config/synthetic/manifests/` is `identity_manifest_mistral_large_all_pick.yaml`, which is Mistral
Large via the Mistral API, a different model). Each run directory instead carries its own
`manifest_snapshot.yaml` (e.g. `swedish_all_pick_ollama_mistral_nemo_12b/manifest_snapshot.yaml`),
confirming `model: mistral-nemo:12b`, provider `ollama`, served from `http://192.168.0.19:11434`.
0 retries and 0 errors across all 5 runs.

### Results — Swedish, Ollama Mistral Nemo 12B (REAL)

| Strategy | Calls | Personas | Input Tokens | Output Tokens | Total Tokens | Match rate |
|---|---:|---:|---:|---:|---:|---|
| all_pick | 1,700 | 100 | 502,537 | 14,853 | 517,390 | 99.9% (1699/1700) |
| all_pick_dag | 1,700 | 100 | 490,101 | 14,105 | 504,206 | 99.9% (1699/1700) |
| all_generate_pick | 3,400 | 100 | 1,012,652 | 64,588 | 1,077,240 | 94.0% (3197/3400) |
| all_generate_evaluate_pick | 5,103 | 100 | 1,581,658 | 126,752 | 1,708,410 | 96.4% (4919/5103) |
| all_generate_evaluate_random_pick | 3,301 | 100 | 1,032,558 | 69,986 | 1,102,544 | 96.2% (3174/3301) |

## Claude Opus — retroactive estimate (no real token data exists)

Same upstream gap as Haiku: the `claude` CLI provider never logs token counts, confirmed again here
(zero token data in any of the 5 `swedish_{strategy}_claude_opus` run logs). Estimated via `tiktoken`
`cl100k_base` over `prompt`/`raw_response` fields, same method as Haiku. All 5 strategies, 100
personas each, zero malformed/missing records.

### Results — Swedish, Claude Opus (ESTIMATED)

| Strategy | Calls | Personas | Est. Input Tokens | Est. Output Tokens | Est. Total |
|---|---:|---:|---:|---:|---:|
| all_pick | 1,701 | 100 | 169,731 | 13,476 | 183,207 |
| all_pick_dag | 1,700 | 100 | 172,857 | 14,809 | 187,666 |
| all_generate_pick | 3,400 | 100 | 480,829 | 143,196 | 624,025 |
| all_generate_evaluate_pick | 5,110 | 100 | 795,458 | 229,576 | 1,025,034 |
| all_generate_evaluate_random_pick | 3,300 | 100 | 506,500 | 161,440 | 667,940 |

## Claude Sonnet — retroactive estimate (no real token data exists)

Same method and caveats as Haiku/Opus above.

### Results — Swedish, Claude Sonnet (ESTIMATED)

| Strategy | Calls | Personas | Est. Input Tokens | Est. Output Tokens | Est. Total |
|---|---:|---:|---:|---:|---:|
| all_pick | 1,700 | 100 | 183,534 | 15,546 | 199,080 |
| all_pick_dag | 1,700 | 100 | 175,916 | 15,409 | 191,325 |
| all_generate_pick | 3,400 | 100 | 501,707 | 144,832 | 646,539 |
| all_generate_evaluate_pick | 5,102 | 100 | 819,310 | 238,208 | 1,057,518 |
| all_generate_evaluate_random_pick | 3,310 | 100 | 498,597 | 157,146 | 655,743 |

## Ollama DeepSeek R1 14B — mixed real / estimated

Single-step strategies (`all_pick`, `all_pick_dag`) and `all_generate_evaluate_pick` parsed cleanly
from `logs/run_*.log` (99.96-100% match) — those rows are REAL. `all_generate_pick` (22.0% match) and
`all_generate_evaluate_random_pick` (43.7% match) had too low a log-match rate to trust, so those two
rows fall back to the `tiktoken` `cl100k_base` estimate over `prompt`/`raw_response` text, same method
as the Claude sections.

No `<think>...</think>` reasoning blocks were ever found in any persisted `raw_response` (0 files
matched across all 5 strategies) — the Ollama deployment does not appear to persist reasoning content
in the stored JSONL text, or thinking is disabled for this deployment.

**Reasoning-model-specific effect worth noting:** in `all_generate_evaluate_pick`'s REAL log data, the
135 `retry` step-type calls (2.6% of calls, all in the `evaluate` step's JSON-weights parsing) average
~2,018 completion tokens/call vs. ~95-100 tokens/call for normal `enumerate`/`evaluate` calls. This
suggests the failed first attempt in each retry pair produced a much longer reasoning-heavy response
that didn't parse as clean JSON — a real token cost captured in the log-based counts but invisible in
the JSONL text alone. Because of this, the two ESTIMATED rows below (which only see the persisted
JSONL text, not server-side failed attempts) should be treated as a **lower bound**, not an exact
figure.

### Results — Swedish, Ollama DeepSeek R1 14B (MIXED)

| Strategy | Calls | Personas | Input Tokens | Output Tokens | Total Tokens | Source |
|---|---:|---:|---:|---:|---:|---|
| all_pick | 1,700 | 100 | 1,034,646 | 15,121 | 1,049,767 | REAL (100.0% match) |
| all_pick_dag | 1,700 | 100 | 978,645 | 15,213 | 993,858 | REAL (100.0% match) |
| all_generate_pick | 3,403 | 100 | 497,472 | 174,481 | 671,953 | ESTIMATED (log match only 22.0%) |
| all_generate_evaluate_pick | 5,255 | 100 | 4,364,035 | 619,408 | 4,983,443 | REAL (99.96% match) |
| all_generate_evaluate_random_pick | 3,417 | 100 | 548,135 | 257,687 | 805,822 | ESTIMATED (log match only 43.7%) |

## Ollama Gemma 4 E4B — mixed real / estimated

Same approach: real aggregator against `swedish_{strategy}_ollama_gemma4_e4b`, tiktoken fallback where
log parsing fails. 4 of 5 strategies parsed as REAL; `all_generate_evaluate_pick` fell back to
ESTIMATED.

**Why `all_generate_evaluate_pick` needed the fallback:** its `logs/` directory spans a multi-day
resume (2026-05-27 through 2026-06-23) across 5 log files. The two most recent files (the resume
window that produced the final persisted JSONL records) use a newer log line format with a bracketed
elapsed-time segment between timestamp and level (e.g. `2026-06-23 08:25:09 [+5.0s] INFO: ollama
call: ... prompt_tokens=282 completion_tokens=10`). `log_parser.py`'s timestamp regex expects
`TIMESTAMP LEVEL: msg` with no bracket in between, so it silently fails to parse these lines — the
token data is physically present in the log text but unextractable by the current pipeline. The
older-format logs from the first resume attempt do parse, but their records don't line up with the
final interaction timestamps, so the join finds zero matches overall. This is a log-format/parser gap
worth fixing in `log_parser.py` if this model's data is needed again, not a bug in this analysis.

### Results — Swedish, Ollama Gemma 4 E4B (MIXED)

| Strategy | Calls | Personas | Input Tokens | Output Tokens | Total Tokens | Source |
|---|---:|---:|---:|---:|---:|---|
| all_pick | 1,700 | 100 | 538,686 | 15,025 | 553,711 | REAL (99.4% match) |
| all_pick_dag | 1,700 | 100 | 527,785 | 14,651 | 542,436 | REAL (99.5% match) |
| all_generate_pick | 3,400 | 100 | 1,113,791 | 108,487 | 1,222,278 | REAL (94.7% match) |
| all_generate_evaluate_pick | 5,149 | 100 | 766,156 | 222,692 | 988,848 | ESTIMATED (log unparseable, see note) |
| all_generate_evaluate_random_pick | 3,579 | 100 | 1,221,584 | 309,131 | 1,530,715 | REAL (91.5% match) |
