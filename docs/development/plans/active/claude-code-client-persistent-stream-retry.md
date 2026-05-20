# Plan: ClaudeCodeClient Persistent Stream-JSON Protocol (Retry)

**Date:** 2026-05-19
**Author:** Basil
**Status:** In Progress
**Base Branch:** `dev`
**Branch:** `feature/claude-code-client-persistent-stream` (reuse existing — already open with uncommitted one-shot client)

---

## Overview

Re-attempt the persistent stream-json `ClaudeCodeClient` architecture using the protocol Anthropic's own [`claude-agent-sdk-python`](https://github.com/anthropics/claude-agent-sdk-python) uses. The first attempt (commits `e3617ad` → `925ee4c` → `dae9abf`) was abandoned after silent CLI failures led to the conclusion *"persistent-process architecture is not achievable with current CLI"*. That conclusion was wrong: the SDK source proves the mode works and identifies two concrete mistakes — the wrong stdin message shape, and the `--print` flag (which forces one-shot mode and is incompatible with persistent streaming). This plan corrects both and adds per-call timing instrumentation so the speed claim is measured, not assumed.

## Problem Statement

`ClaudeCodeClient.generate_content()` currently spawns a fresh `claude --print` subprocess per call. A configurable identity makes ~30 sequential calls (15 categories × 2 LLM round-trips), so each identity pays ~30 × CLI-startup-overhead. Measured cost in the only recorded test: **742 s for one identity** (≈49 s per call). Extrapolated to `--n 10 --workers 4`: ≈31 minutes — only marginally faster than the pre-feature-branch baseline (~48 min) and well over the plan's original target (<10 min).

The original plan's design — one persistent `claude` process per worker, amortising the ~10 s startup across all ~30 prompts — is the only structural lever that closes this gap without giving up subscription-auth billing (the Anthropic SDK path) or rewriting the identity strategy (batching categories per prompt). Reaching the <10 min target therefore requires actually implementing what the original plan described, with the protocol corrections documented in `docs/development/debug/`.

## Goals

### In Scope

1. Validate the corrected stream-json protocol (correct stdin shape, correct flag set, no `--print`) against the real CLI before touching client code.
2. Prove the full Python architecture (Popen + reader thread + queue + lifecycle) works end-to-end in a throwaway script — smallest viable system — before refactoring the production client.
3. Re-implement persistent-process internals in `ClaudeCodeClient`: lazy launch, reader thread + queue, NDJSON I/O, lifecycle management.
4. Keep the `LLMClient` Protocol contract unchanged (drop-in replacement; no caller changes outside `generate_identities_parallel.py`'s already-present cleanup).
5. Add per-call timing logs so launch-vs-inference split is measurable.
6. Update existing planning/debug docs so future readers don't trust the superseded "won't work" conclusion.

### Out of Scope

- Changing the `LLMClient` Protocol interface (`src/population_synth/clients/llm_protocol.py`).
- Modifying `identity_generator_configurable.py` or any strategy JSON files.
- Reducing the number of LLM calls per identity (e.g. category batching) — separate optimisation, composes with this one.
- Adding an Anthropic SDK path (rejected: needs `ANTHROPIC_API_KEY`, gives up subscription auth).
- Async/await rewrite — workers stay `ThreadPoolExecutor`.
- Re-introducing the Phase 2 flags from the original plan (`--exclude-dynamic-system-prompt-sections`, `--strict-mcp-config`, `--mcp-config {}`, `--disable-slash-commands`, `--tools ""`); the debug log proved they crash the process and they were never valid CLI flags.

## Success Criteria

- [x] Phase 0 CLI probe: a single NDJSON message (correct shape) piped to `claude --input-format stream-json ...` returns a `{"type":"result"}` line.
- [x] Phase 0.5 PoC script: three sequential prompts on one persistent `claude` process all return their expected words; prompts 2 and 3 are measurably faster than prompt 1; no orphan after `close()`.
- [ ] `python scripts/generate_identities_parallel.py --provider claude --model haiku --mode configurable --config config/assets/identity/configurable/simulation_config_004_swedish_generative.json --strategy config/assets/identity/configurable/strategies/compared_only_generate_evaluate_random_pick.json --n 10 --workers 4 --output-dir data/identity/config_004_n10_claude_haiku_persistent_v2` produces **10/10 success** with total wall time **< 10 minutes**.
  - **FAIL (2026-05-18):** Aborted at 7/10 after 40+ min. Tool-context injection (~59K tokens per call via `--verbose`) and extended thinking dominate inference time, making the < 10 min target unachievable with this architecture as-is.
- [ ] Per-call timing logs show first call in each identity ≈ 8–12 s (startup + inference), subsequent calls ≈ 2–4 s (inference only).
- [ ] Sonnet regression: `--model sonnet --n 2 --workers 2` succeeds with no errors.
- [ ] No orphaned `claude` processes after script exit: `tasklist | findstr claude` returns empty.
- [ ] `LLMClient` Protocol unchanged — `GeminiClient` and `ClaudeCodeClient` remain interchangeable in `_generate_one()`.

---

## Technical Design

### Approach

Spawn one persistent `claude` subprocess per `ClaudeCodeClient` instance, lazily on first `generate_content()` call. Communicate via NDJSON: write one user-message JSON line per prompt to stdin, drain stdout via a background reader thread + `queue.Queue` until a `{"type":"result"}` line arrives. Restart the process on system-instruction change or unrecoverable error. Tear down explicitly via `close()`, with `atexit` and `__del__` as safety nets (plumbing already in `generate_identities_parallel.py`).

The protocol shape and flag set are taken verbatim from `claude-agent-sdk-python` `_internal/client.py` and `_internal/transport/subprocess_cli.py`, not guessed.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **Persistent stream-json process (this plan)** | Eliminates per-call startup, drop-in, subscription-auth-compatible | Semi-documented protocol, requires reader-thread plumbing on Windows | **Chosen** |
| Keep current one-shot client | Simplest, already working | ~30+ min per `--n 10` batch is the new normal | Rejected — does not meet speed goal |
| Anthropic Python SDK direct | ≈1–3 s per call, async-native | Requires `ANTHROPIC_API_KEY`; surrenders subscription billing | Rejected — constraint |
| Batch multiple categories per prompt | Reduces N from ~30 to ~5 | Changes `identity_generator_configurable.py` strategy logic; harder to validate per-category | Out of scope (composes with chosen approach) |
| Claude Agent SDK (Python) | Cleaner Python API | Same subprocess underneath; adds a heavy dependency | Rejected |
| `--bare` flag for startup speedup | ~10× faster startup | Disables OAuth/keychain, breaks subscription auth | Rejected — already proven incompatible in prior round |

### Architecture Changes

**Modified file:** `src/population_synth/clients/claude_code_client.py` — full internal rewrite, external interface unchanged.

```
ClaudeCodeClient
├── __init__()                — stores config, no process launched yet
├── generate_content()        — _ensure_process → _send_prompt → _read_until_result (retry-wrapped)
├── _ensure_process(...)      — NEW: lazy launch / restart on model or system_prompt change
├── _launch_process(...)      — NEW: Popen with stream-json flags + start reader thread
├── _reader_thread()          — NEW: daemon thread, reads stdout line-by-line into queue.Queue
├── _send_prompt(prompt)      — NEW: write {"type":"user", ...} NDJSON to stdin, flush
├── _read_until_result(t)     — NEW: drain queue until {"type":"result"}, with timeout
├── _close_process()          — NEW: close stdin, wait, kill, join reader thread
├── close() / __del__()       — NEW: public cleanup + safety net
└── [existing config/history/metadata methods unchanged]
```

**Exact CLI command built by `_launch_process()`:**

```python
cmd = [
    "claude",
    "--model", model,                       # "haiku" or "sonnet"
    "--no-session-persistence",             # prevents per-worker session-file contention
    "--input-format", "stream-json",
    "--output-format", "stream-json",
    "--verbose",                            # required by --output-format stream-json
    "--max-turns", "1",                     # one assistant turn per user message
    # NOTE: --allowedTools "" was tested (Task 0.6) and does NOT suppress tool injection;
    #       the full tool list still appears in the system init message. Omitted as a no-op.
]
if system_instruction:
    cmd += ["--system-prompt", system_instruction]
# NO --print  — that flag forces one-shot mode and closes stdin after one response.
```

**Exact NDJSON written to stdin per prompt** (from `claude-agent-sdk-python/_internal/client.py` `_process_query_inner`):

```python
{
    "type": "user",
    "session_id": "",
    "message": {"role": "user", "content": prompt},
    "parent_tool_use_id": None,
}
```

Serialised with `json.dumps(...) + "\n"`, encoded as UTF-8, written to `proc.stdin`, then `proc.stdin.flush()`.

**Expected stdout NDJSON per turn:**

- 0+ `{"type":"system","subtype":"init",...}` (only on first turn — informational, ignored)
- 0+ `{"type":"rate_limit_event",...}` (informational, ignored)
- 1+ `{"type":"assistant","message":{...}}` (streaming chunks, ignored — we only need the final text)
- 1× `{"type":"result","subtype":"success","is_error":false,"result":"TEXT",...}` ← terminator

`_read_until_result()` returns `msg["result"]` from the terminator. On `is_error: true`, raise `RuntimeError` with `msg.get("result") or msg.get("error")`. On EOF sentinel, raise `RuntimeError("claude process terminated unexpectedly")`. On overall deadline expiry, raise `subprocess.TimeoutExpired`.

**Modified file:** `scripts/generate_identities_parallel.py` — no functional changes required. The `_active_clients` tracking, `atexit` cleanup, and `finally: client.close()` plumbing added in the previous attempt is correct and stays.

**Unchanged:**
- `src/population_synth/clients/llm_protocol.py`
- `src/population_synth/clients/gemini_client.py`
- `src/population_synth/identity/**` (all strategies, factory, configurable generator)
- All config / strategy JSON files

---

## Implementation Plan

### Phase 0: Protocol validation (no code change)
**Started:** 2026-05-18
**Completed:** 2026-05-18
**Goal:** Prove the corrected protocol works against the real CLI before touching `claude_code_client.py`. Cheapest first; catches the misdiagnosis class of failure early.

**Tasks:**
- [x] Task 0.1 — Single-prompt round-trip from PowerShell. Pipe one corrected NDJSON line into `claude --input-format stream-json --output-format stream-json --verbose --model haiku --no-session-persistence --max-turns 1`. **Pass criterion:** stdout contains a `{"type":"result",...}` line with non-empty `result` text.
  ```powershell
  '{"type":"user","session_id":"","message":{"role":"user","content":"Reply with exactly: HELLO"},"parent_tool_use_id":null}' | `
    claude --input-format stream-json --output-format stream-json --verbose --model haiku --no-session-persistence --max-turns 1
  ```
  - **Observed (PASS):** stdout contained `{"type":"result","subtype":"success","is_error":false,...,"result":"HELLO",...}`. Distinct types on stdout: `rate_limit_event`, `system`, `assistant` (2 chunks: one `thinking`, one `text`), `result`. The `system` init message came first (with tool list, MCP servers, model info). The `rate_limit_event` came before `system`. Two `assistant` messages were emitted per turn: one with a `thinking` content block, one with the `text` block.
- [x] Task 0.2 — Multi-prompt persistence. Write a throwaway Python script (`scripts/_throwaway_protocol_probe.py`, not committed) that spawns `claude` with the flags above, writes message 1, reads stdout lines until a `result`, writes message 2, reads until a second `result`, then closes stdin. **Pass criterion:** two distinct `result` lines from one process; process exit code 0 after stdin close.
  - **Observed (PASS):** Single process (PID confirmed), message 1 returned `result='ALPHA'`, message 2 returned `result='BETA'`, process exit code 0 after stdin close.
- [x] Task 0.3 — Record turn-completion signal: confirm `{"type":"result"}` is the terminator in persistent mode (and `is_error` semantics behave as in `--print` mode). Note any other message types observed so they can be ignored, not parse-errored.
  - **Observed:** All distinct types across both turns: `['assistant', 'rate_limit_event', 'result', 'system']`. `{"type":"result"}` confirmed as the per-turn terminator. `is_error` field present on result lines; value was `false` on successful turns. `subtype` field present on both `system` (value: `"init"`) and `result` (value: `"success"`) messages.
- [x] Task 0.4 — Confirm `--system-prompt <text>` is honoured at launch and propagates to all subsequent turns (write two prompts, check the second response still respects the instruction).
  - **Observed (PASS):** System prompt `"Always respond in exactly one word."` honoured on both turns. Turn 1 ("What colour is the sky?"): `result='Blue.'` (1 word). Turn 2 ("What colour is grass?"): `result='Green.'` (1 word). Process exit code 0.
- [x] Task 0.5 — If any of 0.1–0.4 fails, **stop** and update this plan with the actual observed behaviour before proceeding to Phase 1.
  - **Observed:** All tasks 0.1–0.4 passed. Protocol is valid. GO for Phase 0.5.
- [x] Task 0.6 — Confirm `--allowedTools ""` suppresses tool injection. Add the flag to the Task 0.1 command and verify: (a) process starts without crashing; (b) the `system` init message contains no tool definitions (or no `tools` key); (c) `cache_creation_input_tokens` on the first turn drops substantially compared to Task 0.1 (baseline: 59 047); (d) prompt→answer still works (`result` line with non-empty text). If (a) fails (process crashes or errors), try `--allowedTools` with value `"none"`. Record the exact flag form that works. If both crash, record that and note the flag must be omitted from `_launch_process()`. **Pass criterion:** process starts, no tools in init, prompt answered correctly.
  - **Observed (FAIL — partial):** `--allowedTools ""` tested. (a) Process started without crashing. (b) Tool injection was **NOT suppressed** — the `system` init message still contained the full tool list (70+ tools, all standard Claude Code tools plus MCP tools). (c) `cache_creation_input_tokens: 8468` vs baseline 59 047 — the lower figure is a cache-hit artifact (`cache_read_input_tokens: 50592`), not suppression; tools are still injected and costing tokens on a cold start. (d) `result="HELLO"` received correctly. **Step 2 not attempted** — the flag did not crash, so there is no alternative to test; the flag simply has no effect on tool injection. **Conclusion:** `--allowedTools ""` cannot suppress tool injection. The flag must be omitted from `_launch_process()` — it neither helps (doesn't suppress tools) nor hurts (doesn't crash), but keeping a misleading no-op flag in the command is undesirable. The tool-injection overhead is unavoidable with the current CLI; first-turn cost is dominated by the cached system context (~59 K tokens), not by cache creation.

**Files Modified:** None (probe script is throwaway, not committed).

**Dependencies:** None.

### Phase 0.5: Architecture proof-of-concept (smallest viable system)
**Started:** 2026-05-18
**Completed:** 2026-05-18
**Goal:** Before any production code changes, prove the *whole architecture* (Popen + reader thread + queue + send-NDJSON + read-until-result + close) works end-to-end in Python — not just at the CLI shell level (Phase 0). This isolates the pattern from production complexity (no retry, no workers, no config loading, no identity strategy) so any Python-side integration bug (pipe deadlock, reader-thread race, close()-on-broken-pipe, JSON decode edge case) surfaces in ≤50 lines of throwaway code instead of inside the refactored client.

**Why split from Phase 0:** Phase 0 confirms the *CLI accepts the right shape*. Phase 0.5 confirms *we can drive that protocol from Python with the architecture we plan to ship*. They catch different failure classes.

**Tasks:**
- [x] Task 0.5.1 — Write `scripts/_throwaway_persistent_poc.py` (NOT committed; deleted after Phase 1 passes). Minimal contents:
  - `subprocess.Popen` with the exact flag set from Architecture Changes.
  - One `threading.Thread(daemon=True)` reading `proc.stdout.readline()` into `queue.Queue`.
  - Helper `send(prompt)` writing the corrected NDJSON line + `\n` + `flush()`.
  - Helper `read_until_result(timeout)` draining the queue and returning `msg["result"]` on `type=="result"`.
  - Hardcoded `system_instruction = "Respond with exactly one word."`.
  - Sends three prompts sequentially: `"Say RED"`, `"Say GREEN"`, `"Say BLUE"`. Prints each result.
  - `close()`: close stdin, `wait(timeout=5)`, kill if needed, join reader thread.
  - **Observed (PASS):** Script written to `scripts/_throwaway_persistent_poc.py` matching the exact specification.
- [x] Task 0.5.2 — Run the script and verify: (a) all three prompts return their respective expected words; (b) only one `claude.exe` is spawned (check `tasklist` mid-run); (c) the process exits cleanly after `close()` (no orphan in `tasklist` after script exits); (d) no exceptions, no hangs >30s on any single prompt.
  - **Observed (PASS):** All three prompts returned expected words (RED, GREEN, BLUE). Process exit code 0. No exceptions, no hangs. Post-exit `tasklist | findstr claude` shows only pre-existing Claude Code environment processes (not PoC orphans).
- [x] Task 0.5.3 — Add a deliberate failure to the script and re-run: between prompt 2 and 3, `proc.kill()` the subprocess manually. Confirm `read_until_result()` raises `RuntimeError("claude process terminated unexpectedly")` cleanly rather than hanging. This validates the EOF-sentinel path that the production client's retry loop depends on.
  - **Observed (PASS):** `--kill-test` run: prompts 1 and 2 succeeded (RED, GREEN); prompt 3 raised `RuntimeError: claude process terminated unexpectedly` within 2 ms of the kill — no hang. Process exit code 1 (killed).
- [x] Task 0.5.4 — Time the three prompts: print `t_first_call_ms` and `t_subsequent_call_ms` for prompts 2 and 3. **Pass criterion:** prompts 2 and 3 are visibly faster than prompt 1 (startup amortised). If they're not — the persistent-mode hypothesis is wrong and the whole speed argument collapses; stop and reassess before Phase 1.
  - **Observed (PASS):** `t_first_call_ms=3993, t_p2_ms=1142, t_p3_ms=959`. Prompts 2 and 3 are 3–4× faster than prompt 1 — startup cost amortised across subsequent calls. Persistent-mode hypothesis confirmed.
- [x] Task 0.5.5 — If any of 0.5.1–0.5.4 fails, **stop** and update this plan with the actual observed behaviour. Do not proceed to Phase 1 with a broken foundation.
  - **Observed:** All tasks 0.5.1–0.5.4 passed. GO for Phase 1.

**Files Modified:** None committed. Throwaway script lives at `scripts/_throwaway_persistent_poc.py` and is deleted (or `.gitignore`'d) before Phase 1 work begins.

**Dependencies:** Phase 0 passing.

### Phase 1: Persistent client core
**Started:** 2026-05-18
**Goal:** Replace one-shot `_run_once()` with persistent-process internals matching the validated protocol.

**Tasks:**
- [x] Task 1.1 — Add `_launch_process(model, system_instruction)`: build the exact `cmd` list documented in Architecture Changes; `subprocess.Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)`. Spawn a daemon thread targeting `_reader_thread`. Store `self._proc`, `self._reader_thread_handle`, `self._stdout_queue`, `self._current_model`, `self._current_system_prompt`.
- [x] Task 1.2 — Add `_reader_thread()`: `for line in iter(self._proc.stdout.readline, b""):` push decoded line onto `self._stdout_queue`; push `None` sentinel on EOF.
- [x] Task 1.3 — Add `_send_prompt(prompt)`: serialise `{"type":"user","session_id":"","message":{"role":"user","content":prompt},"parent_tool_use_id":None}` + `"\n"`, write as UTF-8 bytes, `flush()`.
- [x] Task 1.4 — Add `_read_until_result(timeout)`: deadline-based loop calling `queue.get(timeout=remaining)`. Skip lines that aren't valid JSON or aren't dict-shaped with `type`. Skip types ∈ {`system`, `rate_limit_event`, `assistant`, `stream_event`}. On `type == "result"`: if `is_error`, raise `RuntimeError(msg.get("result") or msg.get("error") or str(msg))`; otherwise return `msg["result"].strip()`. On `None` sentinel, raise `RuntimeError("claude process terminated unexpectedly")`. On deadline expiry, raise `subprocess.TimeoutExpired(cmd=..., timeout=timeout)`.
- [x] Task 1.5 — Add `_ensure_process(model, system_instruction)`: if `self._proc is None` OR `self._proc.poll() is not None` OR model/system_prompt changed, call `_close_process()` then `_launch_process(...)`. **Do not** wait for any init handshake — the SDK doesn't.
- [x] Task 1.6 — Add `_close_process()`: if no process, return. Close stdin (ignore `BrokenPipeError`), `self._proc.wait(timeout=5)`; on `TimeoutExpired`, `self._proc.kill()` + `wait()`. Join reader thread with `timeout=2`. Null out all process state.
- [x] Task 1.7 — Add `close()` public method (delegates to `_close_process()`) and `__del__` that suppresses all exceptions and calls `close()`.
- [x] Task 1.8 — Rewrite `generate_content()`: extract `model` and `system_instruction` from `kwargs` (same as today). Loop `max_retries` times: try `_ensure_process(...); _send_prompt(prompt); return _read_until_result(self._timeout)`. On exception (`RuntimeError`, `subprocess.TimeoutExpired`, `OSError`), call `_close_process()` so the next iteration relaunches, sleep with the existing exponential-backoff + jitter, retry. After max retries, raise.
- [x] Task 1.9 — Delete `_run_once()`.

**Completed:** 2026-05-18

**Files Modified:**
- `src/population_synth/clients/claude_code_client.py` — full internal rewrite, external interface unchanged.

**Dependencies:** Phase 0.5 passing.

### Phase 2: Per-call timing instrumentation
**Started:** 2026-05-18
**Goal:** Resolve the "Open Question #1" from `docs/development/debug/claude-code-client-protocol-findings-2026-05-19.md`. Make the speed claim measurable, not assumed.

**Tasks:**
- [x] Task 2.1 — In `_ensure_process()`, when a launch actually happens, record `t_launch_ms = (time.perf_counter() - t0) * 1000` and stash it on the instance for the next `generate_content()` to log. When no launch happens (process reused), `t_launch_ms = 0`.
- [x] Task 2.2 — In `generate_content()`, wrap the `_send_prompt → _read_until_result` round-trip with `t_inference_ms` timing.
- [x] Task 2.3 — Emit one INFO-level log line per call: `"claude call: model=%s t_launch_ms=%.0f t_inference_ms=%.0f"`. Cheap, single line, easy to grep.

**Completed:** 2026-05-18

*Note: Phase 2 timing was folded into Phase 1 implementation — all timing instrumentation is present in the Phase 1 rewrite.*

**Files Modified:**
- `src/population_synth/clients/claude_code_client.py` — small additions inside Phase 1 methods.

**Dependencies:** Phase 1.

### Phase 3: Validation
**Started:** 2026-05-18
**Stopped:** 2026-05-18 — headline performance target not met; plan requires reassessment before continuing.
**Goal:** Confirm functional correctness, performance, and cleanup against the original plan's test matrix.

**Tasks:**
- [ ] Task 3.1 — Functional probe: `--n 1 --workers 1 --model haiku` against `config_004` + `compared_only_generate_evaluate_random_pick` strategy. Read timing logs: first call should show `t_launch_ms > 0`, subsequent calls `t_launch_ms == 0`. Identity should be valid JSON.
- [x] Task 3.2 — Headline test: `--n 10 --workers 4 --model haiku` → 10/10 success, total wall time < 10 min. Output dir `data/identity/config_004_n10_claude_haiku_persistent_v2`.
  - **Observed (FAIL):** Run aborted after 40+ minutes with 7/10 identities complete. Wall time far exceeds the < 10 min target. The persistent-process architecture eliminates per-call startup overhead as proven in Phase 0.5 (PoC: first call ~4 s, subsequent ~1 s), but the actual per-call inference time under the full identity strategy is much higher than expected — the tool-context injection (~59K tokens, unavoidable with `--verbose`) and extended thinking appear to dominate. The < 10 min target assumed ~2–4 s per inference call; actual sustained throughput is closer to 4–6× slower.
- [ ] Task 3.3 — Sonnet regression: `--n 2 --workers 2 --model sonnet` → 2/2 success.
- [ ] Task 3.4 — Orphan check after each run: `tasklist | findstr claude` returns no rows.
- [ ] Task 3.5 — Recovery probe: during a `--n 1 --workers 1` run, manually `taskkill /F` one `claude.exe` mid-generation; confirm the retry logic relaunches and the identity completes successfully.

**Files Modified:** None.

**Dependencies:** Phase 2.

### Phase 4: Documentation cleanup
**Goal:** Stop future readers (including future-me) from trusting the superseded "won't work" conclusion.

**Tasks:**
- [ ] Task 4.1 — Move `docs/development/plans/active/claude-code-client-persistent-stream.md` to `docs/development/plans/archived/claude-code-client-persistent-stream-original.md` (with a one-line header noting it was superseded by the retry plan because the protocol diagnosis was incorrect).
- [ ] Task 4.2 — Move both debug docs (`claude-code-client-stream-json-debug-2026-05-19.md`, `claude-code-client-protocol-findings-2026-05-19.md`) to `docs/development/debug/archive/` and add a one-line "superseded by" header at the top of each pointing to this plan.
- [ ] Task 4.3 — Update `CLAUDE.md` `clients/` section: `ClaudeCodeClient` runs a persistent `claude` subprocess per instance using `--input-format stream-json --output-format stream-json`; document the message-shape constant.
- [ ] Task 4.4 — On successful merge, this plan moves from `pending/` → `active/` (at branch open) → `completed/` (per `/plan-finish`).

**Files Modified:**
- `CLAUDE.md` — `clients/` section.
- File moves in `docs/development/plans/` and `docs/development/debug/`.

**Dependencies:** Phase 3.

---

## Testing Plan

### Unit Tests

The project has no unit-test suite (per `CLAUDE.md`: *"No test suite exists currently."*). Adding one for this feature is out of scope. Validation is via the integration / manual paths below.

### Integration Tests

- [ ] Multi-call persistence: `--n 1 --workers 1` produces ~30 `claude call: ... t_launch_ms=...` log lines; only the first has `t_launch_ms > 0`.
- [ ] Multi-worker isolation: `--n 10 --workers 4` — confirm each worker has its own persistent process (4 concurrent `claude.exe` in `tasklist` during the run, dropping to 0 after).
- [ ] Provider parity: identical CLI args except `--provider gemini` vs `--provider claude` both produce valid identity JSON for the same `--config` + `--strategy`.

### Manual Verification

- [ ] Run the headline test command from Success Criteria; verify wall time and success count.
- [ ] Inspect one generated `identity.json` — schema matches the configurable strategy's expected fields.
- [ ] Spot-check a few `claude call:` log lines — `t_inference_ms` values are in the 1500–4000 ms range for haiku (rough sanity bounds).

### Edge Cases

- [ ] Process dies mid-identity (Task 3.5 above) — retry logic respawns and completes.
- [ ] System instruction changes between calls (artificial test: call `generate_content` twice with different `system_instruction` kwargs) — process restarts; second call succeeds.
- [ ] Ctrl+C during a multi-worker run — `atexit` cleanup runs; no orphans.
- [ ] Empty / whitespace-only prompt — current retry behaviour holds (this isn't a regression vector; the configurable generator doesn't produce empty prompts).
- [ ] Very long prompt (>10 KB) — should pass through unchanged via stdin; the existing 10 MB stdin cap (mentioned in headless docs) is far above any prompt we generate.

---

## Documentation Plan

- [ ] Update `CLAUDE.md` `clients/` paragraph: `ClaudeCodeClient` description switches from "subprocess wrapper" to "persistent `claude` subprocess (NDJSON stream-json protocol)" — one or two sentences max.
- [ ] Archive the superseded plan (Task 4.1) and debug docs (Task 4.2) so the active set reflects current reality.
- [ ] No new user-facing guide; the public CLI (`scripts/generate_identity.py`, `scripts/generate_identities_parallel.py`) is unchanged.
- [ ] No changelog file (project doesn't keep one).

---

## Rollback Plan

The entire change is internal to `src/population_synth/clients/claude_code_client.py`. The parallel script's cleanup plumbing is harmless even if the client reverts to one-shot.

1. **Before merge:** `git checkout dev -- src/population_synth/clients/claude_code_client.py` (or revert to the current branch tip if dev hasn't moved). No other file revert needed.
2. **After merge:** revert the merge commit. No database, no config, no external state touched.
3. **Data considerations:** None. Output `identity.json` schema is unchanged; existing `data/identity/...` directories are unaffected.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Stream-json protocol changes in a future `claude` CLI version | Med | High | Pin observed message shape in a single constant; Phase 0 probe doubles as a regression check; SDK is the upstream contract — track it if drift is observed |
| `--system-prompt` not honoured in persistent mode | Low | High | Phase 0 Task 0.4 verifies this explicitly before any code change; fallback is `--append-system-prompt` |
| Pipe deadlock (stdout buffer fills while client is blocked writing stdin) | Low | High | Dedicated reader thread drains stdout into an unbounded `queue.Queue` continuously — the original design pattern, kept |
| Orphaned `claude.exe` on Windows if Python crashes hard | Med | Med | `finally: client.close()`, `atexit` registration, and `__del__` safety net are already in `generate_identities_parallel.py`; Task 3.4 verifies after every run |
| Rate-limit pauses inflate `t_inference_ms` and obscure true inference time | Med | Low | `rate_limit_event` messages are logged at DEBUG so they're visible if surprising; the headline test runs at workers=4 which is the production scenario anyway |
| Per-worker persistent process holds an idle subscription session longer than expected | Low | Low | `--no-session-persistence` + `_close_process()` on every identity boundary keeps lifetime bounded |
| Initial protocol probe (Phase 0) reveals the SDK source doesn't match real CLI behaviour | Low | High | Phase 0 is gated — Task 0.5 says stop and update the plan; no Phase 1 work happens until validation passes |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|------------------|--------------|
| Phase 0 (CLI protocol probe) | ~15 min | None |
| Phase 0.5 (Python architecture PoC) | ~45 min | Phase 0 |
| Phase 1 (client core) | 2–3 h | Phase 0.5 |
| Phase 2 (timing) | ~20 min | Phase 1 |
| Phase 3 (validation runs) | ~1 h (mostly wall-time on the 10-identity run) | Phase 2 |
| Phase 4 (docs / archives) | ~20 min | Phase 3 |

---

## References

- Superseded plan: `docs/development/plans/active/claude-code-client-persistent-stream.md` (Phase 1–3 checkboxes are misleading — the persistent code was deleted)
- Debug docs (superseded conclusion): `docs/development/debug/claude-code-client-stream-json-debug-2026-05-19.md`, `docs/development/debug/claude-code-client-protocol-findings-2026-05-19.md`
- Analysis triggering the retry: `C:\Users\basil\.claude\plans\analyse-the-current-active-virtual-thacker.md`
- Anthropic Python Agent SDK (primary source for stdin shape + flags): https://github.com/anthropics/claude-agent-sdk-python — `src/claude_agent_sdk/_internal/client.py` (`_process_query_inner`), `src/claude_agent_sdk/_internal/transport/subprocess_cli.py`
- Claude Code headless docs: https://code.claude.com/docs/en/headless
- Open Anthropic docs issue (acknowledges stdin schema is undocumented): https://github.com/anthropics/claude-code/issues/24594
- Related prior plan: `docs/development/plans/active/fix-claude-code-client-parallel-haiku.md`
- Companion plan: `docs/development/plans/active/claude-code-client.md`
