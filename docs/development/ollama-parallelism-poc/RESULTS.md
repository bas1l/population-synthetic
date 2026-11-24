# Ollama parallelism POC — measured results (2026-07-02)

Server: `192.168.0.19`, control API `:11435` live, inference `:11434`.
Env now applied (from `/status`): `NUM_PARALLEL` per-model, `CONTEXT_LENGTH=8192`,
`FLASH_ATTENTION=1`, `KV_CACHE_TYPE=q8_0`, `MAX_LOADED_MODELS=1`, `KEEP_ALIVE=-1`.
Per-model worker map (`/models`): gemma4:e4b→12, llama3.2→10, llama3.1:8b→6,
qwen3:14b→4, deepseek-r1:14b→2, 70B/72B→1.

## Verdict: batching works, but the gain is modest and plateaus early — NOT the 3–4×.

| Model | Comparison | Wall-clock speedup | Notes |
|---|---|---:|---|
| llama3.2 (3B) | `NP=1` k=1 vs `NP=10` k=10, N=20 | **1.22×** | tiny model, compute-bound; 10 slots overshoot |
| qwen3 (14B) | `NP=4` k=1 vs k=4, N=8 | **1.81×** | bigger weights amortise better; plateaus by k=2 |

qwen3 fixed-config sweep (`NUM_PARALLEL=4`, N=8, num_predict=256):

```
k=1 | wall=63.08s   (serial baseline)
k=2 | wall=40.25s   -> 1.57x
k=4 | wall=34.92s   -> 1.81x   (throughput knee ~ k=2)
```

## What we learned

1. **Batching is genuinely engaging** — latency does not grow fully linearly with k
   (qwen k=4 mean latency 15.9s vs 4×7.9=31.5s if serial), so requests overlap on the GPU.
2. **The GPU saturates fast.** Throughput plateaus by k≈2 for both models. This is a
   compute/bandwidth-bound single-GPU box, not the multi-GPU setup the report's published
   3–4× figures assume.
3. **Bigger model → bigger win** (14B 1.8× > 3B 1.2×), consistent with the
   memory-bandwidth argument: larger weight matrices amortise more per batched pass.
4. **The server's `num_parallel` is a VRAM ceiling, not the throughput-optimal client
   concurrency.** llama3.2 was allotted 10 slots but throughput peaks by k≈2; driving 10
   concurrent requests just inflated per-request latency (3.5s → 27s) for ~zero extra
   throughput.

## Implication for the client-side design

"Set `workers = server num_parallel`" is **wrong** for the small models — it buys latency,
not throughput. The server number is the max the VRAM allows; the *useful* concurrency is
the throughput knee (~2–4 here). So the client should either (a) cap workers at the knee,
or (b) run a one-off per-model knee sweep and store that, rather than trusting the VRAM-max.

## Metric caveat

Use **wall-clock for a fixed request count** as the headline, not aggregate tok/s: output
lengths vary run-to-run, so tok/s ratios understate/overstate the real batching win. The
14B looked like 1.36× on tok/s but 1.81× on wall-clock (the number that matters for a sweep).

## Reproduce

```bash
# full before/after (reconfigures the shared server twice)
python docs/development/ollama-parallelism-poc/benchmark.py --model qwen3:14b --requests 8 --num-predict 256
```
