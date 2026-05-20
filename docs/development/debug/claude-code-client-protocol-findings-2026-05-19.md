# ClaudeCodeClient: Protocol Findings & Open Questions
**Date:** 2026-05-19  
**Branch:** `feature/claude-code-client-persistent-stream`  
**Context:** Follow-up to `claude-code-client-stream-json-debug-2026-05-19.md`

---

## What We Learned

### `--input-format stream-json` is a dead end

Tested the core assumption of the persistent-stream architecture: that `--input-format stream-json` accepts NDJSON messages on stdin and responds to each one.

**Result: silent failure.** The process starts, receives the payload, produces zero stdout, zero stderr. Tested with both:
- `{"type":"message","role":"user","content":[{"type":"text","text":"..."}]}`
- `{"prompt":"..."}`

Both formats: process alive, zero output, no error. Closing stdin after sending also produced nothing — the process just exited silently with no output.

### Correct non-interactive protocol: `--print` + plain text stdin

```
claude --print --model haiku --no-session-persistence \
  --output-format stream-json --verbose --max-turns 1
```

Send the prompt as plain UTF-8 text to stdin, then close stdin. The process emits NDJSON lines:

```
{"type":"system","subtype":"init",...}
{"type":"rate_limit_event",...}
{"type":"assistant","message":{...}}   # one or more streaming lines
{"type":"assistant","message":{...}}
{"type":"result","subtype":"success","is_error":false,"result":"TEXT",...}
```

The `result` field in the final message contains the full response text. The `is_error` flag is reliable for error detection.

### Persistent-process architecture is not achievable with current CLI

`--print` closes stdin after the prompt and the process exits. There is no mechanism to reuse a single `claude` process across multiple prompts. The persistent-stream design is fundamentally incompatible with how the CLI works.

### Simplified client works

Rewrote `ClaudeCodeClient` to use `subprocess.Popen` + `proc.communicate()` (one-shot per call). Removed: persistent process, reader thread, queue, `_ensure_process`, `_close_process`, `_wait_for_init`, `close()`/`__del__()`, and all associated fields.

First run: **1/1 success, 0 failures** (`--n 1 --workers 1`, `config_004`, `compared_only_generate_evaluate_random_pick` strategy).

---

## Performance Observation

**742 seconds** for 1 identity, 1 worker, 15 categories (one `generate_content()` call per category).

That's **~49 seconds per LLM call** on average. Timeline from logs:
- `11:33:30` — script start
- `11:34:10` — first candidate warning (+40s, likely first LLM call completes)
- `11:45:52` — generation complete

The 15-category strategy makes 15 separate subprocess invocations. If inference itself is ~10–15s per call on haiku, the remaining ~35s per call is either:
- Process startup / CLI initialisation overhead
- Rate limiting (the output includes `rate_limit_event` messages)
- Time waiting for the full response before `communicate()` returns

---

## Open Questions

### 1. What is the actual per-call breakdown?
Is the 49s/call mostly Claude startup overhead, actual inference, or rate limiting?  
**Approach:** add per-call timing log in `_run_once()` (before Popen, after communicate). Run `--n 1 --workers 1` again and read per-call durations from log.

### 2. Does `rate_limit_event` introduce actual delays?
The `rate_limit_event` NDJSON line appears in output but we currently skip it. Does the CLI itself pause when it emits this, or is it just informational?  
**Approach:** look for `resetsAt` field in those messages to see if rate limits are being hit.

### 3. Can we reduce per-call startup overhead?
Each call spawns a fresh `claude` process. If startup is ~5–10s, 15 calls × 10s = 150s of pure overhead.  
**Approaches to consider:**
- Batch multiple categories into a single prompt (one LLM call for several fields at once)
- Use the Anthropic SDK directly (requires `ANTHROPIC_API_KEY`, but no subprocess overhead at all)

### 4. Does `--no-session-persistence` hurt startup time?
It forces a clean session every call (no cached login state reuse?). Worth testing with and without to see if it affects timing.

### 5. Is there a non-`--print` interactive mode that could support persistence?
Interactive mode (`claude` without `--print`) waits for stdin input. Could we write a prompt and read the response before the process exits?  
**Hypothesis:** Unlikely to work cleanly — the interactive mode outputs formatted text, not NDJSON, and `--output-format stream-json` probably only activates with `--print`.  
**Not worth pursuing unless `--print` startup proves to be the dominant cost.**

### 6. Is 742s/identity acceptable for the use case?
With 4 workers: 10 identities × 742s / 4 workers ≈ ~31 minutes. The original benchmark was ~48 min (one-shot). So the new client is slightly faster or about the same.  
**Original promise was ~4 min with persistent streams, which is now unachievable.**  
If 31 min is too slow, the Anthropic SDK (no subprocess overhead) is the only realistic path to significant speedup.

---

## What to Do Next

1. **Add per-call timing** to `_run_once()` and re-run `--n 1 --workers 1` to understand actual breakdown.
2. **Run full test** `--n 10 --workers 4` to validate success rate and real wall time at scale.
3. **Decide** whether to accept current performance or invest in Anthropic SDK client.
4. If accepted: commit the simplified client and run `/plan-finish`.
