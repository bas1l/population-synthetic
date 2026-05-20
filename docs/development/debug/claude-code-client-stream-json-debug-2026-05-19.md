# Debug Report: ClaudeCodeClient Stream-JSON Protocol
**Date:** 2026-05-19  
**Branch:** `feature/claude-code-client-persistent-stream`  
**Author:** Basil

---

## Goal

Replace one-shot `subprocess.run()` per LLM call with a **persistent** `claude` subprocess using the CLI's stream-json NDJSON protocol. This eliminates ~10s process startup overhead per call (×30 calls/identity = ~48 min → ~4 min for 10 identities with 4 workers).

**External interface is unchanged** — only `ClaudeCodeClient` internals change.

---

## Current Code State

### Committed (commit `925ee4c`)
Phase 1–3 of the plan were committed. The commit introduced the persistent-process architecture but the subprocess flags were partially wrong (see issues below). The committed code is **not working**.

### Uncommitted changes (on top of `925ee4c`)
All subsequent fixes below are **uncommitted**. Files modified:
- `src/population_synth/clients/claude_code_client.py` — all the fixes described below
- `scripts/generate_identities_parallel.py` — datetime timestamps added to logger format (minor, committed alongside Phase 3)

---

## Architecture (as implemented)

```
ClaudeCodeClient
├── __init__()           — stores config, no process launched yet
├── generate_content()   — ensure process → send prompt → read result (with retry)
├── _ensure_process()    — lazy launch or restart if model/system_prompt changed
├── _launch_process()    — Popen with stream-json flags + starts reader thread
├── _reader_thread()     — daemon thread: reads process.stdout → queue.Queue
├── _send_prompt()       — writes NDJSON to stdin, flushes
├── _read_until_result() — drains queue until {"type":"result"} arrives
├── _wait_for_init()     — NOT CALLED (see Issue 3 below), kept as dead code
├── _close_process()     — close stdin → wait → kill → join reader thread
└── close() / __del__()  — public cleanup
```

---

## Issues Encountered and Fixes Applied

### Issue 1: Phase 2 optimization flags caused immediate crash
**Error:** Process exited immediately (0 lines of stdout).

**Root cause:** Several flags added in Phase 2 were not valid Claude CLI flags:
- `--exclude-dynamic-system-prompt-sections`
- `--strict-mcp-config`
- `--mcp-config {}`
- `--disable-slash-commands`
- `--tools ""`

After fixing, stderr capture was added to `_wait_for_init` so errors would surface. This revealed:

**Fix:** Stripped all unverified Phase 2 flags. Kept only `--max-turns 1`.

---

### Issue 2: `--output-format stream-json` requires `--verbose`
**Error:** `Error: When using --print, --output-format=stream-json requires --verbose`

**Root cause:** When the claude CLI detects it's in `--print` mode (non-interactive, stdin piped), `--output-format stream-json` requires `--verbose` to be explicitly set.

**Fix:** Added `--verbose` to the command.

---

### Issue 3: Init signal deadlock (blocking issue as of session end)
**Error:** `claude init timeout. Received 0 lines: []` — process alive for 30s, zero stdout.

**Root cause:** The original design assumed the `claude` process emits an init handshake message `{"type":"system","subtype":"init"}` on startup. **This does not happen.** The stream-json protocol has no init handshake — the process starts silently and waits for stdin input. We were deadlocked: we waited for init, the process waited for input.

**Fix applied (NOT YET TESTED as of session end):** Removed the `_wait_for_init()` call from `_ensure_process()`. The process is now launched and immediately used — the first `_send_prompt()` call goes out without waiting for any handshake.

---

## Current Command Built by `_launch_process()`

```python
cmd = [
    "claude",
    "--model", model,               # e.g. "haiku"
    "--no-session-persistence",
    "--input-format", "stream-json",
    "--output-format", "stream-json",
    "--verbose",
    "--max-turns", "1",
]
# if system_instruction: cmd += ["--system-prompt", system_instruction]
```

---

## Current `_send_prompt()` Input Format

```python
payload = json.dumps({
    "type": "message",
    "role": "user",
    "content": [{"type": "text", "text": prompt}],
})
# written as UTF-8 bytes + "\n" to process.stdin
```

**⚠ UNKNOWN:** Whether this is the correct NDJSON input format for `--input-format stream-json`. The alternative (simpler) format might be:
```json
{"prompt": "your text here"}
```

---

## Current `_read_until_result()` Expected Output Format

Reads NDJSON lines from stdout queue until it finds a line where `msg["type"] == "result"`. Extracts `msg["result"]` as the response text.

**⚠ UNKNOWN:** Whether the result message format matches. Alternative formats:
- `{"type":"result","subtype":"success","result":"TEXT",...}` ← what we expect
- Some other structure

---

## Next Steps (what to do in the next session)

### Step 1: Test the init-deadlock fix
Run with `--n 1 --workers 1` and check if we get past the `_ensure_process()` call:
```powershell
python scripts/generate_identities_parallel.py --provider claude --model haiku --mode configurable \
  --config config/assets/identity/configurable/simulation_config_004_swedish_generative.json \
  --strategy config/assets/identity/configurable/strategies/compared_only_generate_evaluate_random_pick.json \
  --n 1 --workers 1 --output-dir data/identity/debug_02
```

### Step 2: If still failing — diagnose the protocol manually

Run this in PowerShell to observe what the claude CLI actually emits with a real NDJSON input:
```powershell
echo '{"type":"message","role":"user","content":[{"type":"text","text":"Reply with: HELLO"}]}' | claude --input-format stream-json --output-format stream-json --verbose --model haiku --no-session-persistence --max-turns 1
```

Observe:
1. Does it produce output at all?
2. What message types come through?
3. Is there a `{"type":"result",...}` line?
4. Is the input format correct, or does it need to be `{"prompt":"..."}` instead?

### Step 3: If protocol format is wrong

Update `_send_prompt()` to use the correct format. Options to try:
```python
# Option A (current):
{"type": "message", "role": "user", "content": [{"type": "text", "text": prompt}]}

# Option B (simpler, may be actual format):
{"prompt": prompt}
```

And update `_read_until_result()` if the result message has a different structure.

### Step 4: If everything works — run full test
```powershell
python scripts/generate_identities_parallel.py --provider claude --model haiku --mode configurable \
  --config config/assets/identity/configurable/simulation_config_004_swedish_generative.json \
  --strategy config/assets/identity/configurable/strategies/compared_only_generate_evaluate_random_pick.json \
  --n 10 --workers 4 --output-dir data/identity/config_004_n10_claude_haiku_persistent
```

Success criteria from the plan:
- 10/10 success rate
- Wall time < 10 minutes
- No orphaned `claude` processes: `tasklist | findstr claude`

### Step 5: Commit and finish the plan
Once working, commit the uncommitted fixes and run `/plan-finish claude-code-client-persistent-stream`.

---

## Key Files

| File | Role |
|------|------|
| `src/population_synth/clients/claude_code_client.py` | The client being rewritten — all active changes here |
| `scripts/generate_identities_parallel.py` | Test harness + atexit cleanup (Phase 3) |
| `docs/development/plans/active/claude-code-client-persistent-stream.md` | Full plan with task checklist |
| `docs/development/plans/active/fix-claude-code-client-parallel-haiku.md` | Prior related plan (context) |

---

## Rollback

If persistent stream approach fails entirely:
1. `git checkout 2675f5a -- src/population_synth/clients/claude_code_client.py` to restore the one-shot implementation from before this feature branch
2. The one-shot approach works but is slow (~48 min for 10 identities)
3. The faster alternative is the direct Anthropic SDK (requires `ANTHROPIC_API_KEY`, not subscription-compatible)
