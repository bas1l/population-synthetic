# Enrich Per-Call Telemetry for Synthetic Persona Generation

**Date:** 2026-07-06
**Status:** In Progress
**Base Branch:** `feature/investigate-attribute-category-terminology`
**Branch:** `feature/enrich-persona-generation-telemetry`

---

## Context

During synthetic persona (identity) generation we want every LLM call to be fully
accountable: **input/output tokens**, **when the prompt was sent** and **when the answer was
received**, the **persona it belongs to** (parallel-safe), and — on failure — a **structured
reason** we can use to tell a *model limitation* apart from a *connection failure*.

An audit of the generation → logging → analytics pipeline found this data is captured
inconsistently and, in the most common case, **silently dropped**:

1. **The log parser is currently broken by the log formatter.**
   `scripts/generate/generate_identities_parallel.py` installs an `_ElapsedFormatter`
   (`:83-86`) that emits lines like `2026-07-06 15:45:27 [+1.2s] INFO: ollama call: ...`.
   `log_parser.py`'s `_RE_TIMESTAMP` (`src/population_synthetic/analysis/run_analytics/per_run/log_parser.py:62-64`)
   expects `<ts> <LEVEL>: <msg>`; the injected `[+1.2s]` breaks the `\w+:` match, so **every
   call line fails to parse** and all token/latency data is lost for any run made with this script.
2. **Telemetry lives only in the shared text log, never in the crash-safe JSONL.** Tokens/latency
   are recovered only by re-parsing `logs/run_*.log` and joining back — fragile, and gone if the
   log is lost or rotated. The per-persona `llm_interactions.jsonl` (the crash-safe record) has
   no token/latency fields at all.
3. **Gemini captures nothing per call** — `response.usage_metadata` is never read
   (`clients/gemini_client.py:197`), no latency, no correlation token, no info log line, and a
   blanket `except Exception` (`:209-211`) that cannot distinguish network vs model failure.
4. **Claude never reports tokens** even though the CLI `result` NDJSON message carries a `usage`
   block that is currently discarded.
5. **No structured failure reason** — the JSONL `error` field is free text and only set for
   JSON-parse retries; hard failures survive only as an exception string in the shared text log.

**Intended outcome:** each `llm_interactions.jsonl` line becomes the single, crash-safe,
parallel-safe source of truth carrying tokens (in/out/total), send + receive timestamps,
latency, `persona_id`/`call_index`, and a structured `error_category` — consistently across all
four providers.

**Decisions confirmed with the user:**
- Persist telemetry into the per-persona JSONL as source of truth (and fix the text-log path too).
- Introduce a structured `error_category` taxonomy across all providers.
- Close token gaps for all four providers (Gemini, Claude, Ollama, OpenAI-compat).

## Goals

### In Scope
1. Standardize a per-call telemetry contract on every client's `last_metadata`.
2. Persist that telemetry into `LLMInteractionEntry` / `llm_interactions.jsonl`.
3. Close token gaps for Gemini (`usage_metadata`) and Claude (CLI `usage` block).
4. Structured `error_category` distinguishing network / timeout / auth / rate_limit /
   model_limitation / invalid_response across all providers.
5. Fix the broken `log_parser` regex and teach the analytics consumers to use JSONL-native telemetry.

### Out of Scope
- Cost/pricing ($) computation and per-model breakdowns in the analytics output.
- Adding retry/backoff to Gemini (telemetry only; can be a follow-up).
- Reworking the `cross_run` comparison layer beyond what JSONL-native tokens require.

## Success Criteria

- [ ] A fresh Ollama run's `llm_interactions.jsonl` line carries `prompt_tokens`,
      `completion_tokens`, `total_tokens`, `request_sent_at`, `response_received_at`,
      `elapsed_ms`, `persona_id`, `call_index`.
- [ ] `analyze_run.py` reports non-null token/latency metrics with `token_match_rate` ≈ 1.0
      (proves the regex fix + JSONL plumbing).
- [ ] A forced connection failure yields `error_category="network"`; a forced unparseable
      response yields `error_category="invalid_response"`.
- [ ] Gemini and Claude runs carry token counts in the JSONL.
- [ ] `ruff check src/` clean and `pytest` green (including new tests).

---

## Technical Design

### Approach

Every client already builds a `_last_execution_metadata` dict and exposes it via the
`last_metadata` protocol property (`clients/llm_protocol.py`). The generator's `_call_llm_json`
already runs one record-write per call but **discards** that metadata. The core of the change is
to (a) make all four clients populate the same metadata keys consistently, and (b) have the
generator copy those keys into the crash-safe JSONL entry. This reuses existing infrastructure
(the metadata sidecar + the `call_context` correlation key) rather than inventing new plumbing.

### Standard `last_metadata` contract (all four clients)

Per call, populate:
`provider`, `model`, `request_sent_at` (ISO), `response_received_at` (ISO, **new everywhere**),
`elapsed_ms`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `status` (`ok`|`error`),
`error_category` (`None` on success; else
`network|timeout|auth|rate_limit|model_limitation|invalid_response|unknown`), `error` (raw message).

### Error classification split
- Transport/provider failures are classified **in the client** (network/timeout/auth/rate_limit/
  model_limitation), stamped onto `last_metadata` before raising.
- `json.JSONDecodeError` / `KeyError` from parsing a *successful* response (model produced
  unparseable/wrong-shape output) are classified **in the generator** as `invalid_response`.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Persist telemetry into per-persona JSONL (source of truth) | Crash-safe, parallel-safe (one file/persona), no fragile join | Touches clients + generator + parser | **Chosen** |
| Keep text-log-only, just fix regex | Small diff | Keeps fragile join; data lost if log lost/rotated | Rejected |
| New sidecar telemetry file per call | Clean separation | Extra artifact + writer; duplicates JSONL correlation | Rejected |

---

## Implementation Plan

### Phase 1: Telemetry contract + JSONL schema
**Goal:** Make the data model carry telemetry end-to-end.

**Started:** 2026-07-06
**Completed:** 2026-07-06

- [x] Extend `LLMInteractionEntry` with optional (default `None`) fields: `provider`, `model`,
      `request_sent_at`, `response_received_at`, `elapsed_ms`, `prompt_tokens`,
      `completion_tokens`, `total_tokens`, `error_category`.
- [x] Standardize the metadata keys in `ollama_client.py` and `openai_compat_client.py`
      (add `request_sent_at`/`response_received_at`/`total_tokens`, map their existing exception
      arms to `error_category`).

**Files Modified:**
- `src/population_synthetic/generators/synthetic/llm_interaction_log.py`
- `src/population_synthetic/clients/ollama_client.py`
- `src/population_synthetic/clients/openai_compat_client.py`

**Dependencies:** None

### Phase 2: Close token gaps + error taxonomy (Gemini, Claude)
**Goal:** Every provider emits tokens + a structured failure reason.

**Started:** 2026-07-06
**Completed:** 2026-07-06

- [x] `gemini_client.py`: read `response.usage_metadata` (`prompt_token_count`/
      `candidates_token_count`); add `perf_counter` timing + send/receive timestamps; split the
      blanket `except Exception` into network/timeout/model_limitation/unknown; add an `info`
      log line with `format_corr_token()` (import from `clients.call_context`).
- [x] `claude_code_client.py`: parse the `usage` block in `_read_until_result` (`:235-276`);
      set token fields; add tokens to the `claude call:` log line (`:308-311`); map retry-bucket
      exceptions to `error_category`.

**Files Modified:**
- `src/population_synthetic/clients/gemini_client.py`
- `src/population_synthetic/clients/claude_code_client.py`

**Dependencies:** Phase 1

### Phase 3: Record telemetry in the generator
**Goal:** Land telemetry in the crash-safe, per-persona JSONL.

**Started:** 2026-07-06
**Completed:** 2026-07-06

- [x] In `identity_generator_configurable.py::_call_llm_json` (`:159-227`), read
      `meta = self.client.last_metadata or {}` after the call and copy telemetry fields into
      **both** the success entry (`:195-205`) and the retry/error entry (`:209-220`).
- [x] In the except block, set `error_category="invalid_response"` for
      `json.JSONDecodeError`/`KeyError`; otherwise carry the client's `error_category`.

**Files Modified:**
- `src/population_synthetic/generators/synthetic/identity_generator_configurable.py`

**Dependencies:** Phases 1–2

### Phase 4: Fix + extend analytics consumers
**Goal:** Restore parsing and prefer JSONL-native telemetry.

**Started:** 2026-07-06
**Completed:** 2026-07-06

- [x] `log_parser.py`: fix `_RE_TIMESTAMP` (`:62-64`) to tolerate the optional `[+elapsed]`
      suffix; add token capture to the `claude` line regex (`:81-87`).
- [x] `interaction_parser.py`: add the new fields to `_FIELD_DEFAULTS` (`:22-35`).
- [x] `joiner.py`: prefer JSONL-native tokens/latency; fall back to the text-log join only for
      legacy runs lacking them.
- [x] `aggregator.py`: token-gate on JSONL-native tokens; surface `error_category` in the
      `per_category` error taxonomy (`:163-198`).

**Files Modified:**
- `src/population_synthetic/analysis/run_analytics/per_run/log_parser.py`
- `src/population_synthetic/analysis/run_analytics/per_run/interaction_parser.py`
- `src/population_synthetic/analysis/run_analytics/per_run/joiner.py`
- `src/population_synthetic/analysis/run_analytics/per_run/aggregator.py`

**Dependencies:** Phases 1–3

---

## Testing Plan

### Unit Tests
- [x] `test_log_parser.py` — add cases for the `[+elapsed]` prefix and Claude-with-tokens lines.
      Also added Gemini call-line cases (with/without `corr=`) and a Claude-without-tokens
      backward-compatibility case.
- [ ] Client tests — each client populates `last_metadata` with the standard keys and correct
      `error_category` on simulated network vs empty-response failures. *(Phase 2 scope; not
      revisited here.)*
- [x] `test_aggregator.py` / `_fixtures.py` — added `JSONL_NATIVE_ENTRIES` fixture (no
      text-log join involved) and tests proving token-gated metrics compute from JSONL-native
      tokens alone, plus an `error_category_counts` per-category breakdown test. Also extended
      `test_joiner.py` with JSONL-native-preferred-over-log-join cases.
- [ ] `test_call_context.py` — assert Gemini now emits a parseable `corr=` line. *(Phase 2 scope;
      not revisited here.)*

### Manual Verification
- [ ] **Ollama end-to-end** (no API key): `python scripts/generate/generate_identities_parallel.py
      --model-id <ollama_axis> --strategy-id all_pick --country-id swedish --n 2 --workers 2
      --log-llm --output <scratch>`; inspect `persona_00000/llm_interactions.jsonl`.
- [ ] `python scripts/analyze/analyze_run.py <scratch>` → token/latency non-null,
      `token_match_rate` ≈ 1.0.
- [ ] Point Ollama at a bad `OLLAMA_BASE_URL` → JSONL entry has `error_category="network"`;
      force/observe a JSON-parse retry → `error_category="invalid_response"`.
- [ ] If `GEMINI_API_KEY` available, repeat with a Gemini axis → tokens in JSONL + `corr=` in log.

### Edge Cases
- [ ] Legacy JSONL (no telemetry fields) still parses and joins via the text log.
- [ ] Claude run (no per-token usage if CLI omits it) degrades gracefully to `None` tokens.

---

## Documentation Plan

- [ ] Update `docs/development/debugging-identity-generation.md` with the new JSONL telemetry fields.
- [ ] Note the standardized `last_metadata` contract where client behavior is documented.

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Changing `LLMInteractionEntry` breaks the analytics parser | Med | Med | New fields are optional/defaulted; extend `_FIELD_DEFAULTS`; keep text-log fallback |
| Provider SDK usage-metadata shape differs from assumption | Med | Low | Guard reads with `getattr`/`.get`, default `None`; unit-test the mapping |
| Claude CLI `result` message lacks `usage` in some versions | Med | Low | Degrade to `None` tokens, don't fail the call |
| Gemini error re-classification changes existing raise behavior | Low | Med | Preserve the existing empty/safety-block `RuntimeError`; only add categorization |

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- docs/development/plans/active/enrich-persona-generation-telemetry.md
- src/population_synthetic/analysis/run_analytics/per_run/aggregator.py
- src/population_synthetic/analysis/run_analytics/per_run/interaction_parser.py
- src/population_synthetic/analysis/run_analytics/per_run/joiner.py
- src/population_synthetic/analysis/run_analytics/per_run/log_parser.py
- src/population_synthetic/clients/claude_code_client.py
- src/population_synthetic/clients/gemini_client.py
- src/population_synthetic/clients/ollama_client.py
- src/population_synthetic/clients/openai_compat_client.py
- src/population_synthetic/generators/synthetic/identity_generator_configurable.py
- src/population_synthetic/generators/synthetic/llm_interaction_log.py
- tests/_fixtures.py
- tests/data/expected_metrics.json
- tests/test_aggregator.py
- tests/test_joiner.py
- tests/test_log_parser.py
