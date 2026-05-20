# Performance Analysis: Persistent-Stream ClaudeCodeClient

**Date:** 2026-05-19
**Author:** Basil + Claude
**Status:** Investigation -- findings documented, remedies not yet implemented
**Related plan:** `docs/development/plans/active/claude-code-client-persistent-stream-retry.md`
**Benchmark data:** `data/benchmarks/20260519_145300_n10_haiku_both/results.json`

---

## Summary

The persistent stream-json `ClaudeCodeClient` was implemented to replace one-shot subprocess calls with a single long-lived `claude` process per worker. The goal was **<10 min for 10 identities**. Result: **40+ min for 7/10 identities** (Phase 3, Task 3.2 failure). A PONG benchmark shows 2.44x transport-layer speedup, yet real generation remains slow and token-hungry.

**Core finding:** 98% of all tokens processed are tool definitions the model never uses. The CLI injects ~59K tokens of tool context into every API call, and no flag tested (`--allowedTools ""`, `--max-turns 1`) suppresses it. Transport overhead (what the persistent stream optimises) accounts for only ~2.5% of total runtime.

---

## 1. Root Causes (Ranked by Impact)

### #1 -- DOMINANT: 59K-token tool injection per API call

The Claude CLI injects its full tool suite (~70 tools + MCP schemas) into the system prompt for **every** API call. Confirmed in plan Task 0.6:

- `cache_creation_input_tokens: 59,047` (cold)
- `cache_read_input_tokens: 50,592` (warm -- cached but still attended to by the model)
- `--allowedTools ""` tested: does NOT suppress injection
- `--max-turns 1` prevents tool *use* but not tool *injection*

The model reads 59K tokens of tool definitions it will never use, on every single call.

### #2 -- MAJOR: 29+ sequential LLM calls per identity

With `compared_only_generate_evaluate_random_pick` (15 categories):

| Category type | Count | Calls each | Subtotal |
|---------------|-------|------------|----------|
| Numeric (`age`) | 1 | 1 (distribution spec) | 1 |
| Categorical | 14 | 2 (enumerate + evaluate) | 28 |
| **Total baseline** | | | **29** |

Plus retry amplification:
- `_call_llm_json()` retries 3x on JSON parse failure (`identity_generator_configurable.py:116-132`)
- `generate_content()` retries 3x on subprocess error (`claude_code_client.py:279-311`)
- Weight/candidate mismatch retries up to 10x (`identity_generator_configurable.py:363-377`)
- Typical effective count: **32-35 calls** per identity

### #3 -- MODERATE: No intra-identity parallelism

`generate_identity()` resolves the DAG strictly sequentially (`identity_generator_configurable.py:418`). The dependency graph has 5 levels with independent categories at each level:

- Level 0: `age`, `biological_sex`, `region`, `birth_location`, `parental_structure` (5 independent)
- Level 1: `birth_country_detail`, `civil_status`, `education_level` (3 independent)
- Level 2: `household_size`, `employment_status` (2 independent)
- Level 3: `employment_type`, `industry_sector`, `socioeconomic_class` (3 independent)
- Level 4: `income_source`, `housing_tenure` (2 independent)

All categories at the same level could run concurrently but don't.

### #4 -- MINOR: Benchmark measured the wrong cost component

The PONG benchmark measures transport overhead only. For real workloads, transport is <3% of total call time:

| Component | PONG (benchmark) | Real prompt (observed) |
|-----------|------------------|----------------------|
| Transport overhead | ~2000ms (60% of call) | ~200-500ms (2-5% of call) |
| Inference with 59K context | ~1000ms | 8000-16000ms (80-90% of call) |
| Persistent speedup | 2.44x | ~1.05-1.10x effective |

---

## 2. Token Budget

### Per call

| Component | Tokens | % of total |
|-----------|--------|------------|
| Tool injection (CLI system prompt) | ~59,000 | **97.2%** |
| User system instruction | ~120 | 0.2% |
| Context block (growing) | 50-500 | 0.1-0.8% |
| Actual prompt | 100-300 | 0.2-0.5% |
| Model output | 50-200 | 0.1-0.3% |
| Extended thinking | 200-1000 | 0.3-1.6% |

### Per identity (~30 calls)

| Component | Tokens |
|-----------|--------|
| Tool injection | **~1.77M** |
| Useful I/O (all prompts + contexts + outputs) | ~15-30K |
| **Overhead ratio** | **~60:1** |

### Per batch (10 identities)

| Component | Tokens |
|-----------|--------|
| Tool injection | **~17.7M** |
| Useful content | ~150-300K |

**98% of all tokens processed are tool definitions the model never uses.**

---

## 3. Time Budget

### Per call (real identity generation)

| Component | Estimated ms | % |
|-----------|-------------|---|
| Model attention to 59K tool context | 4000-8000 | 50-60% |
| Extended thinking | 1000-3000 | 10-20% |
| Prompt cache processing (API-side) | 500-2000 | 5-15% |
| Actual prompt processing + generation | 500-2000 | 5-15% |
| Transport (NDJSON I/O) | 200-500 | 2-5% |
| Rate limit waits (intermittent) | 0-5000 | 0-30% |

### Per identity

| Component | Time |
|-----------|------|
| Sequential inference (30 x 8-16s) | 240-480s |
| Transport overhead | ~6-15s |
| Retries (typical 2-4 extra calls) | 16-64s |
| **Total** | **260-560s (4.3-9.3 min)** |

### Per batch (10 identities, 4 workers)

| Scenario | Wall time |
|----------|-----------|
| Theoretical floor (29 calls x 8s, zero retries) | 11.6 min |
| Typical case | 25-40 min |
| Observed (Phase 3) | 40+ min (7/10) |

---

## 4. Feasibility: Can This Architecture Meet <10 min?

**No.** The theoretical floor (zero retries, best-case inference, 4 workers) is **11.6 minutes**, already above target. The bottleneck is 59K tokens of tool context inflating every call to 8-16s. The persistent stream saved ~2s/call transport overhead, but that's only 2.5% of total runtime.

The only paths to <10 min:
1. Eliminate the 59K token overhead (bypass CLI), OR
2. Reduce call count to ~12-15 AND get per-call time under ~7s

---

## 5. Recommendations (Ranked by Impact)

### R1. Bypass CLI for generation workloads (HIGHEST IMPACT)

Use the Anthropic Python SDK directly for batch identity generation. Eliminates the 59K token injection entirely. Per-call context drops from ~60K to ~1K tokens. Expected per-call latency: 1-3s.

**Estimated result:** 29 calls x 2s x 10 identities / 4 workers = **2.4 min**.

**Constraint:** Rejected in plan as "needs `ANTHROPIC_API_KEY`, gives up subscription auth." Counter-argument: the subscription currently pays for ~17.7M tokens of wasted tool context per 10-identity batch. The API cost for 300K useful tokens on Haiku would be ~$0.15. The subscription subsidizes enormous waste to avoid a negligible API cost.

**Possible middle ground:** Use the API for batch generation only; keep the CLI for interactive/ad-hoc use.

### R2. Reduce call count (HIGH IMPACT)

Three sub-options (composable):

**(a) Merge enumerate + evaluate into a single prompt** -- ask the LLM to generate candidates AND assign weights in one call. Halves categorical calls: 29 -> 15.
- Effort: Low-Medium (modify `_process_generate_evaluate_random_pick` in `identity_generator_configurable.py:324`)
- Risk: Low

**(b) Use `pick` method for low-stakes categories** -- `parental_structure`, `birth_location`, and other non-SCB-compared fields don't need weighted random sampling. Switch them to `pick` (1 call) in the strategy JSON.
- Effort: Trivial (config change only, no code)
- Risk: Low

**(c) Batch independent categories into single prompts** -- Level 0 has 5 independent categories; ask the LLM to resolve all 5 in one prompt.
- Effort: High (new prompt template + JSON extraction logic)
- Risk: Medium (prompt engineering complexity)

**Combined R2a + R2b:** ~12 calls per identity instead of 29. At 12s/call: 144s per identity, 10 identities / 4 workers = **6 min**.

### R3. Test `--verbose` removal (TRIVIAL, UNKNOWN IMPACT)

The plan states `--verbose` is "required by `--output-format stream-json`", but the error message cited was for `--print` mode, not persistent stream mode. It may be unnecessary.

**Test:** Remove `--verbose` from `_launch_process()` (`claude_code_client.py:125`) and run one call. If the process still works, check whether `cache_creation_input_tokens` drops.

### R4. Parallelize independent DAG levels (MODERATE IMPACT, HIGH EFFORT)

Execute categories at the same DAG level concurrently. Reduces wall-time from 29 sequential calls to ~10 (the critical-path length through the DAG). Would require either multiple persistent processes per identity or a one-shot approach for intra-level parallelism.

---

## 6. Key Files

| File | Relevance |
|------|-----------|
| `src/population_synth/clients/claude_code_client.py` | Persistent client; `_launch_process()` at line 118 builds CLI command |
| `src/population_synth/identity/identity_generator_configurable.py` | DAG resolver + strategy methods; hot path at line 324 |
| `config/assets/identity/configurable/strategies/compared_only_generate_evaluate_random_pick.json` | Active strategy config; methods changeable without code |
| `docs/development/plans/active/claude-code-client-persistent-stream-retry.md` | Plan with Task 0.6 findings and Phase 3 failure |
| `scripts/benchmark_claude_latency.py` | Benchmark script (only measures transport, not real-prompt latency) |

---

## 7. Open Questions for Follow-Up

1. **Does `--verbose` removal change tool injection?** The error was documented for `--print` mode. Test without it.
2. **Does conversation history accumulate between stream-json messages?** The PONG benchmark shows stable latency (no growth), but real prompts with longer responses might accumulate.
3. **What is the actual extended-thinking overhead?** Task 0.1 observed a `thinking` content block even for PONG. Can thinking be disabled for structured JSON generation?
4. **Would `--bare` flag work if combined with a separate auth mechanism?** Previously rejected for breaking subscription auth, but worth revisiting if API path is considered.
5. **What is Gemini's per-call overhead for comparison?** If Gemini does not inject tool context, the same 15-category strategy would produce dramatically fewer tokens.

---

## 8. Verification Steps (for any future optimisation)

1. Run `scripts/benchmark_claude_latency.py --n 5 --model haiku --mode persistent` with a real identity prompt (not PONG) to measure actual per-call latency
2. Run `scripts/generate_identities_parallel.py --provider claude --model haiku --n 10 --workers 4` and measure wall time + total tokens
3. Compare token counts before and after to confirm the reduction
