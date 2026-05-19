# Plan: ClaudeCodeClient Persistent Stream-JSON Protocol

**Date:** 2026-05-19
**Author:** Basil
**Status:** In Progress
**Base Branch:** `dev`
**Branch:** `feature/claude-code-client-persistent-stream`

---

## Overview

Rewrite `ClaudeCodeClient` internals to use the Claude CLI's persistent stream-json protocol instead of spawning a new subprocess per LLM call. The external `LLMClient` protocol interface stays identical — this is an internal optimization that eliminates ~12s of process startup overhead on 29 out of 30 calls per identity, reducing total generation time from ~48 minutes to ~3-4 minutes for a 10-identity batch.

## Problem Statement

`ClaudeCodeClient.generate_content()` spawns a fresh `claude` subprocess for every call. Each spawn pays ~8-10s of fixed overhead (process init, Node.js startup, auth check, MCP/plugin discovery). A single configurable identity requires ~30 sequential calls (15 categories × 2 LLM round-trips each), so a 10-identity batch with 4 workers takes ~48 minutes — an order of magnitude slower than the Gemini path.

The Claude CLI supports a persistent NDJSON protocol (`--input-format stream-json --output-format stream-json`) that keeps one process alive across multiple prompts. The init cost is paid once; subsequent prompts are pure inference round-trips (~1-3s each).

## Goals

### In Scope
1. Refactor `ClaudeCodeClient` to launch a persistent stream-json process instead of one-shot subprocesses
2. Preserve full `LLMClient` protocol compatibility (drop-in replacement)
3. Add startup optimization flags to minimize per-session overhead
4. Add process lifecycle management (lazy start, cleanup, restart on death/system-prompt change)
5. Verify with haiku n=10 and sonnet regression test

### Out of Scope
- Changing the `LLMClient` protocol definition
- Modifying `identity_generator_configurable.py` or strategy logic
- Async/await rewrite (workers stay as ThreadPoolExecutor)
- Reducing the number of LLM calls per identity (separate optimization)

## Success Criteria

- [ ] 10/10 success rate with `--model haiku --workers 4 --n 10`
- [ ] Total wall time under 10 minutes (down from ~48 minutes)
- [ ] No regressions with `--model sonnet`
- [ ] `LLMClient` protocol contract unchanged
- [ ] Process cleanup: no orphaned `claude` processes after script exit

---

## Technical Design

### Approach

Replace `subprocess.run()` (one-shot) with `subprocess.Popen()` (persistent) using the stream-json NDJSON protocol. The process is launched lazily on first `generate_content()` call and reused for all subsequent calls. A background reader thread drains stdout into a queue, enabling timeout support on Windows where pipe `readline()` is blocking.

**Protocol flow per call:**
1. Write NDJSON prompt to stdin: `{"type":"message","role":"user","content":[{"type":"text","text":"<prompt>"}]}\n`
2. Read NDJSON lines from stdout until `{"type":"result",...}` arrives
3. Extract `result` field as the response text

**System prompt handling:** Set once at process launch via `--system-prompt` flag. The configurable identity generator uses the same system_instruction for all ~30 calls within one identity, so this matches the usage pattern. If a subsequent call passes a different system_instruction, the process is gracefully restarted.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Persistent stream-json process | Eliminates spawn overhead, subscription-compatible, drop-in | Semi-documented protocol, Windows pipe complexity | **Chosen** |
| Anthropic Python SDK (direct API) | Fastest per-call latency, async-native | Requires ANTHROPIC_API_KEY, not subscription-compatible | Rejected (constraint) |
| `--bare` flag | Up to 10x startup speedup | Breaks OAuth/subscription auth | Rejected (constraint) |
| Batch multiple categories per prompt | Fewer total calls | Changes strategy logic, harder to validate per-category | Out of scope |
| Claude Agent SDK (Python) | Cleaner Python API | Still spawns subprocess per query(), same overhead | Rejected |

### Architecture Changes

**Modified file:** `src/population_synth/clients/claude_code_client.py`

New internal structure:

```
ClaudeCodeClient
├── __init__()          — stores config, no process launched yet
├── generate_content()  — ensures process, sends prompt, reads result
├── close()             — NEW: terminates persistent process
├── _ensure_process()   — NEW: lazy launch or restart if system_prompt changed
├── _launch_process()   — NEW: Popen with stream-json flags + reader thread
├── _send_prompt()      — NEW: write NDJSON to stdin
├── _read_until_result()— NEW: drain queue until result message, with timeout
├── _reader_thread()    — NEW: background thread reading stdout → queue
├── _close_process()    — NEW: graceful shutdown (close stdin, wait, kill)
├── __del__()           — calls close() as safety net
└── [existing methods]  — update_config, history, metadata unchanged
```

**Modified file:** `scripts/generate_identities_parallel.py`
- Add `client.close()` call after each identity generation completes

**No changes to:**
- `src/population_synth/clients/llm_protocol.py`
- `src/population_synth/identity/identity_generator_configurable.py`
- Any strategy or config files

---

## Implementation Plan

### Phase 1: Persistent Process Core
**Goal:** Replace subprocess.run with persistent Popen + stream-json protocol
**Started:** 2026-05-19
**Completed:** 2026-05-19

**Tasks:**
- [x] Task 1.1 — Add `_launch_process()`: build command with `--input-format stream-json --output-format stream-json` and existing flags (`--no-session-persistence`, `--tools ""`, `--model`), spawn via `Popen(stdin=PIPE, stdout=PIPE, stderr=PIPE)`
- [x] Task 1.2 — Add `_reader_thread()`: background daemon thread that reads `process.stdout.readline()` in a loop and puts decoded lines onto a `queue.Queue`. Sentinel `None` on EOF.
- [x] Task 1.3 — Add `_read_until_result(timeout)`: drain queue until a `{"type":"result"}` message arrives. On `is_error: true`, raise `RuntimeError` with the error detail. On timeout, raise `subprocess.TimeoutExpired`. On EOF sentinel, raise `RuntimeError("process terminated")`.
- [x] Task 1.4 — Add `_send_prompt(prompt)`: format as `{"type":"message","role":"user","content":[{"type":"text","text":"<prompt>"}]}`, write to stdin + flush
- [x] Task 1.5 — Add `_ensure_process(system_instruction)`: if no process running or system_instruction changed, call `_close_process()` then `_launch_process()`. Wait for `{"type":"system","subtype":"init"}` message from stdout to confirm ready.
- [x] Task 1.6 — Rewrite `generate_content()`: extract system_instruction from kwargs, call `_ensure_process()`, call `_send_prompt()`, call `_read_until_result()`, record metadata. Retry logic wraps the full send+read cycle — on failure, `_close_process()` and retry (process will be relaunched by `_ensure_process()`).
- [x] Task 1.7 — Add `_close_process()`: close stdin, wait with timeout, kill if needed, join reader thread. Add `close()` public method and `__del__` fallback.
- [x] Task 1.8 — Remove `_run_cli()` method (no longer needed)

**Files Modified:**
- `src/population_synth/clients/claude_code_client.py` — Full internal rewrite, same external interface

**Dependencies:** None

### Phase 2: Startup Optimization Flags
**Goal:** Minimize per-session overhead with additional CLI flags
**Started:** 2026-05-19
**Completed:** 2026-05-19

**Tasks:**
- [x] Task 2.1 — Add `--exclude-dynamic-system-prompt-sections` to command (makes system prompt identical across sessions for better prompt caching)
- [x] Task 2.2 — Add `--strict-mcp-config --mcp-config {}` to command (zero MCP servers, saves 10-20K tokens/turn)
- [x] Task 2.3 — Add `--disable-slash-commands` to command (no skills/commands overhead)
- [x] Task 2.4 — Add `--max-turns 1` to limit each prompt to a single model response (prevents agentic loops)

**Files Modified:**
- `src/population_synth/clients/claude_code_client.py` — Additional flags in `_launch_process()`

**Dependencies:** Phase 1

### Phase 3: Parallel Script Cleanup
**Goal:** Ensure persistent processes are terminated after use
**Started:** 2026-05-19
**Completed:** 2026-05-19

**Tasks:**
- [x] Task 3.1 — Add `client.close()` call in `_generate_one()` after identity generation completes (in a `finally` block)
- [x] Task 3.2 — Add `atexit` or signal handler as a safety net for unexpected script termination

**Files Modified:**
- `scripts/generate_identities_parallel.py` — Process cleanup in worker function

**Dependencies:** Phase 1

### Phase 4: Testing
**Goal:** Verify correctness and performance

**Tasks:**
- [ ] Task 4.1 — Run `--model haiku --workers 4 --n 10` and confirm 10/10 success rate
- [ ] Task 4.2 — Verify wall time is under 10 minutes
- [ ] Task 4.3 — Run `--model sonnet --workers 4 --n 2` to confirm no regressions
- [ ] Task 4.4 — Verify no orphaned `claude` processes remain after script exit (check via `tasklist | findstr claude`)
- [ ] Task 4.5 — Test process recovery: kill a `claude` process mid-run and confirm the retry logic respawns and recovers

**Dependencies:** Phases 1-3

---

## Testing Plan

### Manual Verification
- [ ] Haiku batch: `python scripts/generate_identities_parallel.py --provider claude --model haiku --mode configurable --config config/assets/identity/configurable/simulation_config_004_swedish_generative.json --strategy config/assets/identity/configurable/strategies/compared_only_generate_evaluate_random_pick.json --n 10 --workers 4 --output-dir data/identity/config_004_n10_claude_haiku_persistent`
- [ ] Success rate >= 9/10
- [ ] Wall time under 10 minutes
- [ ] Sonnet regression: `--model sonnet --n 2 --workers 2`
- [ ] No orphaned processes: `tasklist | findstr claude` after script exits

### Edge Cases
- [ ] Process dies mid-generation — retry logic respawns and completes
- [ ] System instruction changes between calls — process restarts cleanly
- [ ] Script interrupted with Ctrl+C — processes cleaned up

---

## Documentation Plan

- [ ] Update `docs/development/plans/active/fix-claude-code-client-parallel-haiku.md` with persistent stream results
- [ ] Update CLAUDE.md `clients/` section to document persistent stream-json mode

---

## Rollback Plan

1. The original one-shot subprocess implementation is preserved in git history (commit `e3617ad` + uncommitted fixes)
2. If persistent stream fails, revert `claude_code_client.py` to the one-shot approach
3. No database, config, or external state changes — rollback is a single file revert

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Stream-json protocol is semi-documented, may change | Med | High | Pin to known-working message format; defensive parsing of unknown message types |
| Orphaned processes on Windows if cleanup fails | Med | Med | `__del__` fallback, `atexit` handler, `finally` blocks in worker |
| Pipe deadlock (stdout buffer fills while writing stdin) | Low | High | Separate reader thread drains stdout continuously into queue |
| `--system-prompt` not supported with stream-json | Low | High | Verify in Phase 1 Task 1.5; fallback to `--append-system-prompt` if needed |
| Rate limiting with 4 concurrent persistent processes | Low | Med | Existing retry-with-backoff handles transient 429s |

---

## References

- Active plan: `docs/development/plans/active/fix-claude-code-client-parallel-haiku.md`
- Active plan: `docs/development/plans/active/claude-code-client.md`
- Protocol spec (community): [Go SDK CLI protocol](https://github.com/Roasbeef/claude-agent-sdk-go/blob/main/docs/cli-protocol.md)
- Claude Code headless docs: [code.claude.com/docs/en/headless](https://code.claude.com/docs/en/headless)
- Prompt caching blog: [claude.com/blog/lessons-from-building-claude-code-prompt-caching-is-everything](https://claude.com/blog/lessons-from-building-claude-code-prompt-caching-is-everything)

---
