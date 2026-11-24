# OpenRouter model-axis audit

**Date:** 2026-07-29
**Branch:** `feature/strategy-v2-scb-chain-alignment`
**Scope:** the `openrouter_*` entries of the model axis (`config/synthetic/axes/models/`), their
pricing rows, the concurrency ceiling of the OpenRouter API, and the telemetry gap between the
OpenRouter path and the self-hosted Ollama path.

Everything below is measured, not estimated, unless explicitly labelled. Sources: the live
OpenRouter catalog (`GET /api/v1/models`, fetched 2026-07-29, 367 entries), a bounded concurrency
probe against the project's own key, and the `01_Raw` telemetry of existing Swedish runs.

---

## 1. Changes applied

| Action | Target |
|---|---|
| Added | `openrouter_gpt_oss_120b.yaml` → `openai/gpt-oss-120b` |
| Added | `openrouter_gemini_flash_lite.yaml` → `google/gemini-2.5-flash-lite` |
| Added | `openrouter_qwen35_flash.yaml` → `qwen/qwen3.5-flash-02-23` |
| Added | `openrouter_nemotron3_super.yaml` → `nvidia/nemotron-3-super-120b-a12b` |
| Added | `openrouter_deepseek_v4_flash.yaml` → `deepseek/deepseek-v4-flash` |
| Deleted | `openrouter_claude_sonnet5.yaml`, `openrouter_gpt55.yaml`, `openrouter_gemini_flash.yaml` |
| Edited | `config/analysis/model_pricing.yaml` — 3 dead rows dropped, 5 added, `openrouter_glm_52` corrected, `observed_date` → 2026-07-29 |
| Edited | `tests/test_ollama_host_composition.py:286` — parametrize `openrouter_gpt55` → `openrouter_deepseek_v4` |

Model axis now holds 22 entries; every one has a pricing row. Full suite: 1070 passed.

**Deletion rather than `discarded: true`** was chosen deliberately. `discarded` is documented as
"retires itself from the sweep… a discarded model stays runnable if checked" — a 404 slug is not
runnable, so marking it discarded would encode a false promise. None of the three had run output in
`01_Raw`, so no provenance was lost.

---

## 2. Finding — three of seven OpenRouter arms pointed at slugs that no longer exist

| Axis id (before) | Slug | Catalog status |
|---|---|---|
| `openrouter_claude_sonnet5` | `anthropic/claude-sonnet-4-5` | absent |
| `openrouter_gpt55` | `openai/gpt-4.5-preview` | absent (line is now `gpt-5.x`) |
| `openrouter_gemini_flash` | `google/gemini-flash-1.5` | absent |
| `openrouter_deepseek_v4` | `deepseek/deepseek-v4-pro` | live, price matches config |
| `openrouter_glm_52` | `z-ai/glm-5.2` | live, config had drifted (0.77/2.42 → 0.739/2.323) |
| `openrouter_mistral_medium` | `mistralai/mistral-medium-3-5` | live, price matches |
| `openrouter_qwen37_max` | `qwen/qwen3.7-max` | live, price matches |

A dead slug returns HTTP 404, which is in `OpenAICompatClient._FATAL_STATUS_CODES` — no retry, the
arm dies at the first persona. The labels had drifted too (`openrouter_claude_sonnet5` was labelled
"Claude Sonnet 4.5"; `openrouter_gpt55` "GPT-4.5 Preview").

**Root cause:** there is no pre-flight validation on the cloud path. See §7.

---

## 3. Finding — the cost model was wrong by 20× on output tokens

Per-persona token volume, measured from `llm_interactions.jsonl` of the `openrouter_glm_52` Swedish
runs (100 personas per family, real `prompt_tokens` / `completion_tokens` from the API):

| Strategy family | calls | input | output |
|---|---|---|---|
| `all_pick` | 17 | 4,260 | 1,962 |
| `all_pick_dag` | 17 | 5,110 | 2,577 |
| `all_generate_pick` | 34 | 12,653 | 12,156 |
| `all_generate_evaluate_random_pick` | 33 | 12,473 | 27,389 |
| `all_generate_evaluate_pick` | 51 | 19,736 | 36,065 |
| **total per persona (5 v1 families)** | **152** | **54,233** | **80,150** |

A parallel measurement on `claude_sonnet` (non-reasoning) gives the same input volume but only
~3,900 output tokens per persona. **Cost is output-dominated for reasoning models and
input-dominated for non-reasoning ones**, so a single cost column is meaningless. Both profiles,
USD per 1000 personas × 5 v1 families:

| Slug | in $/M | out $/M | non-reasoning profile | reasoning-on profile |
|---|---|---|---|---|
| `z-ai/glm-5.2` (incumbent) | 0.739 | 2.323 | $49 | **$226 ← measured** |
| `openai/gpt-oss-120b` | 0.037 | 0.170 | $2.7 | $15.6 |
| `qwen/qwen3.5-flash-02-23` | 0.065 | 0.260 | $4.5 | $24.4 |
| `nvidia/nemotron-3-super-120b-a12b` | 0.085 | 0.400 | $6.2 | $36.7 |
| `meta-llama/llama-4-scout` | 0.100 | 0.300 | $6.6 | n/a (no reasoning) |
| `google/gemini-2.5-flash-lite` | 0.100 | 0.400 | $7.0 | $37.5 |
| `deepseek/deepseek-v4-flash` | 0.140 | 0.280 | $8.7 | $30.0 |
| `mistralai/ministral-8b-2512` | 0.150 | 0.150 | $8.7 | n/a |
| `deepseek/deepseek-v4-pro` (live) | 0.435 | 0.870 | $27 | $93 |
| `mistralai/mistral-large-2512` | 0.500 | 1.500 | $33 | n/a |
| `qwen/qwen3.7-max` (live) | 1.475 | 4.425 | $97 | $435 |
| `mistralai/mistral-medium-3-5` (live) | 1.500 | 7.500 | $110 | $683 |

At the current `n: 150` the per-arm figures are ~0.15× the table. All five newly added models are
cheaper than the incumbent under either profile.

---

## 4. Finding — ~95% of billed output tokens are invisible in the logs

Across 510 calls of the `glm_52` `all_pick` run:

- mean `completion_tokens` = **111**
- mean visible `raw_response` = **24 characters ≈ 6 tokens**

```
employment_type   ct=317  resp='{"value": "Tillsvidareanställd"}'
housing_tenure    ct=267  resp='{"value": "hyresrätt"}'
education_level   ct=177  resp='{"value": "Gymnasieexamen"}'
age               ct= 39  resp='{"value": 34}'
```

The difference is reasoning trace, discarded by the provider before the response is returned and
billed at the output rate. This is the mechanism behind §3. The axis YAMLs set every
`generation_config` value to `null`, so each provider's reasoning default is in force, unrecorded
and unmatched across arms — a live confound in the model factor, not only a cost issue.

---

## 5. Finding — no account-side concurrency limit; the ceiling is per-model

`GET /api/v1/key` reports `is_free_tier: false`, `limit: null`,
`rate_limit: {requests: -1, note: "deprecated and safe to ignore"}`. OpenRouter's published rate
limits (20 req/min, 1000/day) apply **only to `:free` model variants**, which the project does not
use.

Concurrency ramp (bounded probe, `max_tokens=8`, ~600 requests total, cost < $0.01).
**Zero 429s at any level, up to 256 concurrent.**

| Model | 32 | 64 | 128 | 256 |
|---|---|---|---|---|
| `openai/gpt-oss-120b` | 20.7 req/s | 39.1 | 48.4 | **87.8 req/s, p50 1.35 s** |
| `google/gemini-2.5-flash-lite` | 23.4 | 38.4 | — | — |
| `nvidia/nemotron-3-super-120b-a12b` | 7.3 | 13.6 | — | — |
| `deepseek/deepseek-v4-flash` | 4.0 | 9.2 (p95 4.4 s, long tail) | — | — |
| `qwen/qwen3.5-flash-02-23` | 3.8 | **1.4 — collapses** (wall 8.4 s → 47 s) | — | — |

Local limits are not binding: `ThreadPoolExecutor` on I/O-bound threads, httpx pool
`max_connections=1000`.

Suggested per-model `parallel.workers` (**not yet applied** — all five new files ship with the
inherited `workers: 4`):

| Model | workers |
|---|---|
| `openai/gpt-oss-120b` | 64–128 |
| `google/gemini-2.5-flash-lite` | 64 |
| `nvidia/nemotron-3-super-120b-a12b` | 32 |
| `deepseek/deepseek-v4-flash` | 16–32 |
| `qwen/qwen3.5-flash-02-23` | 16 |

Caveat: the probe used single bursts of 8-token completions. Sustained runs emitting ~500 output
tokens per call will reach provider capacity sooner than these numbers suggest.

---

## 6. Finding — the GUI's `workers` option is applied but not displayed

The flow option **is** honoured on the OpenRouter path:

- `gui/commands.py::_option_args` emits `--workers 32` for every combo, unconditionally.
- `generate_identities_parallel.py` fills in the axis value only when the flag is absent
  (`if args.workers is None and m.parallel_workers is not None`).
- `--ollama-auto-workers` is gated on `args.provider == "ollama"` (line 624), so it never touches
  cloud combos.
- Confirmed in `swedish_all_pick_openrouter_glm_52/logs/run_20260723_113409.log`:
  `"Model: z-ai/glm-5.2 | Generating 100 identities with 16 workers"`.

What is **not** applied is the summary table. `gui/widgets/population_summary.py::_workers_cell`
(lines 180-205) returns `cfg.parallel_workers` — the axis file's value — for any non-Ollama provider.
The `n` column, by contrast, correctly accepts `total_override` from the flow YAML (lines 97-100).
So the GUI displays the axis value while the run uses the flow value. `refresh()` needs a `workers`
override parameter symmetric with `total_override`.

---

## 7. Finding — OpenRouter vs self-hosted Ollama telemetry

### Identical

`llm_interactions.jsonl` uses the **same 20-key schema** on both paths (`persona_id`, `call_index`,
`provider`, `model`, `request_sent_at`, `response_received_at`, `elapsed_ms`, `prompt_tokens`,
`completion_tokens`, `total_tokens`, `error_category`, plus prompt/response/parse fields). Per-call
INFO lines, retry/backoff warnings, and the `run_metadata.json` key set match.

(For contrast, the **Claude CLI** path is the genuinely thin one: its JSONL carries only
`category, method, step, prompt, raw_response, parsed_value, error, attempt, timestamp` — no tokens,
no timing, no provider.)

### Recorded for Ollama, absent for OpenRouter

| | Ollama | OpenRouter |
|---|---|---|
| `run_metadata.model_config.base_url` | `http://192.168.0.19:11434` | `null` |
| Client-init `Config:` | `{'temperature': 0.7, 'max_output_tokens': 2048}` | `{}` — sampling params neither chosen nor recorded |
| Host resolution | `Ollama host: linux_3060 (…) -> …` | — |
| Worker resolution | auto-workers override + drift check | — |
| Pre-flight | PROBE→ACT→GATE `OLLAMA_NUM_PARALLEL` reconfigure, every stage logged, outcome in `run_metadata` | **none** |
| Which machine served it | fully determined | unknown (see below) |

### Returned by OpenRouter, discarded by `OpenAICompatClient`

Verified against a live `z-ai/glm-5.2` call:

| Field | Example | Why it matters |
|---|---|---|
| `provider` | `"Together"` | OpenRouter is a **router**: the same slug is served by different upstream backends, chosen per request, with different quantizations and sampling defaults. No record exists of which backend produced any given persona. Ollama has no such ambiguity. |
| `usage.cost` | `7.7e-05` | Exact billed USD for the call. `model_pricing.yaml` is hand-reconstructing a number the API returns exactly — including the "effective/discounted" rates currently flagged `[VERIFY]`. |
| `usage.completion_tokens_details.reasoning_tokens` | `0` | Would separate thinking from answer, i.e. quantify §4 directly. |
| `usage.prompt_tokens_details.cached_tokens` / `cache_write_tokens` | `0` | The pricing config has `cache_multipliers` but no data to apply them to. |
| `id`, `system_fingerprint` | — | OpenRouter generation id, queryable after the fact. |

**Summary:** OpenRouter logging is not less explicit than Ollama's — it is equally explicit about a
fundamentally less observable thing, and the client discards the three fields (`provider`,
`usage.cost`, `reasoning_tokens`) that would close most of the gap.

---

## 8. Selection criteria used for the added models

Hard constraint: `structured_outputs` in `supported_parameters` (239 of 367 catalog entries), since
`OpenAICompatClient` sends `response_format: json_schema, strict: true` with a `json_object`
fallback. Beyond that, the additions target vendor/architecture diversity at matched capability —
the paper's finding is *strategy > model*, which is strengthened by a wider, better-controlled model
axis, not by more frontier models.

**Deliberately excluded**

| Option | Reason |
|---|---|
| `openrouter/auto` and routing aliases | Resolve to a different model per call → destroys the model factor in `model_ranking` / `method_significance` |
| `*:free` | 20 req/min, 1000/day, rotating providers; unreproducible at 152 calls/persona |
| `*:batch` (~50% cheaper) | Unreachable — the client is synchronous `/v1/chat/completions`. A future async path would halve cloud cost. |
| `gpt-5.5-pro`, `o1-pro`, `gpt-5.4-pro` | $30–$150 /M input → $1,700–$8,600 per arm per 1000 personas |
| `ai21/jamba-large-1.7`, `amazon/nova-pro-v1` | `structured_outputs = no` → silently degrade to the `json_object` path, not comparable to other arms |

---

## 9. Open items (not implemented)

1. **Capture the discarded OpenRouter response fields** (`provider`, `usage.cost`,
   `reasoning_tokens`, `cached_tokens`) into `llm_interactions.jsonl`. `generation_metadata` would
   then read exact billed cost instead of a hand-maintained, drift-prone pricing table.
2. **Cloud pre-flight**: one `GET /api/v1/models` at startup checking the slug exists, supports
   `structured_outputs`, and that the live price matches `model_pricing.yaml`. Would have caught all
   three dead slugs and the `glm_52` price drift automatically.
3. **Record the resolved `base_url`** in `run_metadata.model_config` for cloud providers, and log the
   effective `generation_config` even when all-`null`, stating that provider defaults are in force.
4. **GUI workers column**: give `population_summary.refresh()` a `workers` override symmetric with
   `total_override` (§6).
5. **Per-model `parallel.workers`** from the §5 measurements (currently all 4).
6. **Decide the reasoning policy** (§4): pin reasoning off for a sampling-matched comparison, or keep
   vendor defaults and state that choice explicitly in the manuscript. Either is defensible; the
   current state is an unstated accident.
