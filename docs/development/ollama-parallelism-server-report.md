# Server-side request: enable & size `OLLAMA_NUM_PARALLEL` for the population-synthetic workload

**To:** Ollama / ai-stack server team (`http://192.168.0.19:11434`, Docker `ai-stack`)
**From:** population-synthetic (client side)
**Date:** 2026-07-02

---

## TL;DR — what we're asking

1. Confirm the **current** value of `OLLAMA_NUM_PARALLEL`, `OLLAMA_MAX_LOADED_MODELS`,
   `OLLAMA_CONTEXT_LENGTH`, `OLLAMA_FLASH_ATTENTION`, `OLLAMA_KV_CACHE_TYPE`, and `OLLAMA_KEEP_ALIVE`
   on the server (these are **server-side env vars — invisible to us over the HTTP API**).
2. Our workload is **very small context**: no request exceeds **~2.7 k input + ~2 k output
   (< 5 k total tokens)**. We do **not** need the models' native 32k–128k context windows.
3. Because KV-cache VRAM scales as `NUM_PARALLEL × context_length`, capping the context to a small
   value (e.g. **8 192**) makes each parallel slot cheap and lets `NUM_PARALLEL` go **much** higher
   than the default of 1.
4. Please determine, **per model**, the maximum `NUM_PARALLEL` that fits in VRAM at
   `num_ctx = 8192` (formula + per-model table below), and report the numbers back.

We (client side) will raise our concurrency (`--workers`) to match — see "Cross-team note" at the end.

---

## Background: why we can't see or set this ourselves

`OLLAMA_NUM_PARALLEL` controls how many requests a loaded model processes **in the same batch**
vs. queues (FIFO). It is a **server environment variable**. It is not returned by `/api/tags`,
`/api/ps`, or `/api/chat`, and it cannot be set per-request in the payload. So from the client we
can only *infer* it by timing concurrent calls. Hence this request to you, who can read/set it.

Batching is a genuine throughput win (not just "avoid reloading the model" — the weights stay
resident). Local decoding is **memory-bandwidth bound**: each forward pass streams the full weight
matrix from VRAM to the compute units. Running N requests **serially** streams the weights N times;
running them **batched** streams them once and reuses each weight across the batch. Published
numbers: `NUM_PARALLEL=4` → ~3–4× total throughput at ~20–40 % added per-request latency.

**Both halves are required.** If the server is at `NUM_PARALLEL=1`, any client concurrency just
queues — no batching, and it *looks* like parallelism "doesn't help." (That is exactly the trap our
current configs fell into: our Ollama runs are pinned to 1 worker.)

---

## The workload envelope (measured, from real Ollama `prompt_eval_count` / `eval_count` logs)

This is the key input for your VRAM sizing. Per-call token counts across all strategies and models,
from `docs/development/token-histograms/token-max-summary.md`:

| Model | Max input tok | Max output tok | Notes |
|---|---:|---:|---|
| deepseek_r1_14b | 2 659 | 2 048* | reasoning model, output hits `num_predict=2048` cap |
| qwen3_14b | 2 659 | 2 048* | reasoning model, output hits cap |
| gemma (e4b) | 706 | 2 048* | reasoning-style, output hits cap |
| llama3.1_8b | 861 | 475 | short outputs |
| mistral_nemo_12b | 564 | 297 | short outputs |
| lucie_7b | 205 | 329 | short outputs |

\* `2048` is our client's `num_predict` generation ceiling being hit, not a natural length.

**Headline: the largest single prompt observed anywhere is ~2 659 input tokens; no call exceeds
~5 k total tokens.** Median calls are far smaller (input ~300–1 000, output often < 100 tokens).

**Implication:** setting the served context to **8 192** covers the worst case (2.7 k in + 2 k out
≈ 4.7 k) with comfortable headroom. Running these models at their native 32k–128k context wastes
KV-cache VRAM by **~4–16×** for zero benefit to us — VRAM that could instead fund parallel slots.

---

## How far can `NUM_PARALLEL` be pushed? (formula + per-model estimates)

VRAM budget when a model is loaded:

```
VRAM_used ≈ weights (fixed, one copy)
          + NUM_PARALLEL × KV_cache_per_slot(num_ctx)
          + overhead (compute buffers, ~0.5–1 GB)
```

So:

```
NUM_PARALLEL_max ≈ (VRAM_total − weights − overhead) / KV_cache_per_slot(num_ctx)
```

**KV cache per slot** (one request, full context):

```
KV_bytes = 2 × n_layers × n_kv_heads × head_dim × num_ctx × bytes_per_elem
           (2 = K and V;  bytes_per_elem: f16=2, q8_0=1, q4_0=0.5)
```

### Per-model KV-cache-per-slot at `num_ctx = 8192`

Architecture constants below are our best estimates — **please verify against the actual GGUF via
`ollama show <model>`** (it prints context length, block/layer count, embedding length; the GGUF
metadata also carries `attention.head_count_kv` and `attention.key_length`). Values assume GQA with
`head_dim = 128` unless noted.

| Model | n_layers | n_kv_heads | head_dim | KV/slot @8k **f16** | KV/slot @8k **q8_0** |
|---|---:|---:|---:|---:|---:|
| llama3.2_3b | 28 | 8 | 128 | ~0.88 GB | ~0.44 GB |
| llama3.1_8b | 32 | 8 | 128 | ~1.0 GB | ~0.50 GB |
| mistral_nemo_12b | 40 | 8 | 128 | ~1.25 GB | ~0.63 GB |
| qwen3_14b | 40 | 8 | 128 | ~1.25 GB | ~0.63 GB |
| deepseek_r1_14b (Qwen2.5-14B base) | 48 | 8 | 128 | ~1.5 GB | ~0.75 GB |
| gemma2_9b | 42 | 8 | 256 | ~2.6 GB† | ~1.3 GB† |
| llama3.3_70b | 80 | 8 | 128 | ~2.5 GB | ~1.25 GB |
| gemma_e4b (Gemma-3n) | — | — | — | verify‡ | verify‡ |
| lucie_7b | ~32 | verify | verify | verify | verify |

† Gemma-2 uses `head_dim = 256` and sliding-window attention on alternating layers; Ollama may
allocate full KV regardless. Its native context is only 8 k, so 8 192 is already its ceiling.
‡ Gemma-3n (E4B) uses a non-standard architecture (MatFormer / per-layer embeddings); compute from
`ollama show`. Note flash-attention / KV-quant support is architecture-dependent (see caveats).

**Worked example.** llama3.1_8b, a 24 GB GPU: weights (Q4_K_M) ≈ 4.9 GB, overhead ≈ 1 GB →
~18 GB free. At f16 KV (1.0 GB/slot) → **~18 parallel slots**; at q8_0 KV (0.5 GB/slot) →
**~36 slots**. In practice you'll be bounded by the client's concurrency well before that — but it
shows the small-context workload leaves enormous room. The 70B is the tight case: weights (Q4) ≈
40 GB, so parallelism depends heavily on total VRAM / multi-GPU.

---

## Recommended server settings for this workload

| Env var | Suggested | Why |
|---|---|---|
| `OLLAMA_CONTEXT_LENGTH` | `8192` | Covers our max ~4.7 k call; avoids 4–16× KV waste vs native context. Biggest single lever. |
| `OLLAMA_FLASH_ATTENTION` | `1` | Required to enable KV-cache quantisation; no downside; reduces memory. |
| `OLLAMA_KV_CACHE_TYPE` | `q8_0` | ~halves KV-cache VRAM, negligible quality loss (perplexity +0.002–0.05). Needs flash attention. |
| `OLLAMA_NUM_PARALLEL` | per-model max from table (start at **4–8**) | Enables batching. Size to VRAM. |
| `OLLAMA_MAX_LOADED_MODELS` | `1` (during a single-model sweep) | Keeps all VRAM for one model's weights + KV slots; avoids eviction thrash. |
| `OLLAMA_KEEP_ALIVE` | e.g. `30m` or `-1` | Keep the model resident across our ~30k sequential calls so it isn't unloaded mid-run. |

**Caveat on KV quantisation:** some architectures are unsupported and Ollama **silently falls back
to f16** (→ higher VRAM than the q8_0 column suggests, possible OOM). Please confirm per model that
`q8_0` actually engages (VRAM via `/api/ps` should drop vs f16). If a model doesn't support it, size
that model with the **f16** column instead.

---

## What we'd like back from you

Per Ollama model we use (`llama3.3_70b`, `deepseek_r1_14b`, `qwen3_14b`, `mistral_nemo_12b`,
`gemma2_9b`, `gemma_e4b`, `llama3.1_8b`, `llama3.2_3b`, `lucie_7b`):

1. **Current** `NUM_PARALLEL` in effect (and the other env vars listed in the TL;DR).
2. Total GPU VRAM available (and whether multi-GPU / how it's split).
3. Weights VRAM per model (from `ollama ps` / `ollama show`).
4. The **max `NUM_PARALLEL`** that fits at `num_ctx = 8192` with the recommended settings, and the
   value you'd set.
5. Whether `q8_0` KV-cache quantisation engages for each model or falls back to f16.

---

## Optional: empirical verification (measures effective parallelism directly)

Since the setting is invisible to clients, its true effect can be confirmed by timing. Fire *k*
identical `/api/chat` requests concurrently (a representative ~1 k-token prompt, `stream:false`) for
`k = 1, 2, 4, 8, 16`, measure **aggregate tokens/sec**:

- If throughput scales up with *k* then plateaus at some *k\**, the server is batching and
  `NUM_PARALLEL ≈ k\*`.
- If throughput is flat from `k = 1` (per-request latency grows linearly with *k*), the server is
  **serialising** — `NUM_PARALLEL` is effectively 1 and needs raising.

Cross-check VRAM with `GET /api/ps` (KV footprint grows with `NUM_PARALLEL × num_ctx`).

---

## Cross-team note (client side — our action, not yours)

Batching needs concurrent in-flight requests. Our Ollama axis configs currently pin
`parallel.workers: 1`, so today we send strictly one request at a time — meaning even a
well-tuned server would batch a batch-of-1. Once you confirm a workable `NUM_PARALLEL`, we will
raise `workers` on the Ollama axes to match (roughly `workers ≈ NUM_PARALLEL`) so the batch is
actually filled. We're also pursuing a client-side change (memoising the LLM-produced conditional
distributions) that removes ~90 % of calls outright; server batching then multiplies whatever
remains, chiefly the cache-warming phase.

---

### References

- Ollama FAQ — concurrency & env vars: <https://docs.ollama.com/faq>
- K/V cache quantisation in Ollama (flash-attn requirement, q8_0/q4_0): <https://smcleod.net/2024/12/bringing-k/v-context-quantisation-to-ollama/>
- KV-cache VRAM formula (GQA): <https://lyceum.technology/magazine/kv-cache-memory-calculation-llm/>
- Ollama parallel-request behaviour / throughput: <https://www.glukhov.org/llm-performance/ollama/how-ollama-handles-parallel-requests/>
