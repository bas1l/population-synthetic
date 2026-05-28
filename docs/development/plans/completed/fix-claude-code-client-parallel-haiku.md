# Fix ClaudeCodeClient for parallel Haiku identity generation

**Status:** Completed
**Completed:** 2026-05-28 07:28

## Problem

`generate_identities_parallel.py --provider claude --model haiku --workers 4 --n 10` fails most runs. Original: 2/10 success (silent exit-code-1, empty stderr). After 4 rounds of fixes: awaiting test of latest round.

## What was changed (all on `feature/claude-code-client`, uncommitted)

### File 1: `src/population_synth/clients/claude_code_client.py`

**Original state** (commit `e3617ad`): Simple subprocess wrapper, `claude -p --model X`, no retries, only logged stderr on failure, used `--append-system-prompt`.

**Current state** — `generate_content()` builds:
```python
cmd = ["claude", "-p", "--model", target_model,
       "--no-session-persistence", "--output-format", "json", "--tools", ""]
if system_instruction:
    cmd += ["--system-prompt", system_instruction]
```

Key changes vs original:
1. `--no-session-persistence` — prevents file contention between parallel workers
2. `--output-format json` — CLI returns `{"type":"result","result":"..."}` envelope; parsed in `_run_cli()`
3. `--tools ""` — disables built-in tool definitions (model won't see tool schemas)
4. `--system-prompt` (not `--append-system-prompt`) — **replaces** the default Claude Code system prompt entirely, so the model doesn't receive the coding-assistant persona
5. **No `--bare`** — tried it, but it disables OAuth/keychain auth → all calls fail with exit 1. Removed.
6. Retry with exponential backoff: constructor accepts `max_retries=3`, `base_delay=2.0`, `max_delay=30.0`. Backoff: `min(base_delay * 2^attempt, max_delay)` with ±25% jitter. Catches `RuntimeError` and `subprocess.TimeoutExpired`.
7. `_run_cli()` extracts error messages from JSON envelope → stderr → stdout[:500] → "(no output)" fallback.

### File 2: `src/population_synth/identity/identity_generator_configurable.py`

**`_extract_json(text)` static method** (new, line ~87): Robust JSON extraction pipeline:
1. Direct `json.loads(text.strip())`
2. Extract between markdown fences: `re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)`
3. Find first `{...}` or `[...]` via regex
4. Raise `json.JSONDecodeError` if nothing works

**`_call_llm_json()` (line ~116)**: Now uses `_extract_json()` and logs the first 500 chars of raw LLM response on parse failure (between `--- RAW RESPONSE ---` markers).

## Failure modes observed (in order of discovery)

| Round | Symptom | Root cause | Fix |
|-------|---------|------------|-----|
| 1 | Silent exit-code-1, empty stderr (8/10 fail) | Session persistence file contention + no diagnostics | `--no-session-persistence`, `--output-format json`, `_run_cli()` error extraction |
| 2 | "Extra data" — JSON + trailing commentary | Regex `$` anchor missed closing fence with text after | `_extract_json()` with fence-aware extraction |
| 2 | "Expecting value" — empty response | Unknown (possibly rate limit or timeout) | Retry with backoff handles transient failures |
| 3 | Haiku outputs tool-call XML instead of JSON | `--append-system-prompt` kept the coding-assistant persona; Haiku followed it over the JSON instruction | Switched to `--system-prompt` (replaces default prompt) |
| 4 | All calls exit 1 with `{}` error | `--bare` disabled OAuth/keychain auth | Removed `--bare` |

## Current status

Round 4 fix (remove `--bare`) applied but **not yet tested**. The test command:

```
python scripts/generate_identities_parallel.py --provider claude --model haiku --mode configurable --config config/assets/identity/configurable/simulation_config_004_swedish_generative.json --strategy config/assets/identity/configurable/strategies/compared_only_generate_evaluate_random_pick.json --n 10 --workers 4 --output-dir data/identity/config_004_n10_claude_haiku_fix5
```

## What to do next

1. Run the test command above and check success rate
2. If failures remain, check `--- RAW RESPONSE ---` logs:
   - If Haiku still produces conversational text / tool XML → the `--system-prompt` flag might not be fully overriding Claude Code's system prompt. Consider using the Anthropic API directly (via `anthropic` SDK) instead of the CLI subprocess for production workloads.
   - If "Expecting value" with empty response → likely rate limiting. Consider reducing `--workers` to 2 or increasing `base_delay`.
3. Once success rate is acceptable (>=8/10), commit changes and run with `--model sonnet` to confirm no regressions for the primary model.
