# ADR: a `claude` CLI call is a fresh process with no project context

**Date:** 2026-10-04
**Status:** Accepted
**Plan:** [`plans/completed/fix-claude-cli-conversation-leak.md`](../plans/completed/fix-claude-cli-conversation-leak.md)
**Supersedes:** the persistent-stream design of
[`plans/completed/claude-code-client-persistent-stream.md`](../plans/completed/claude-code-client-persistent-stream.md)
and the per-thread client rationale in `persona_realism/runner.py` (commit `98d9738`).

## Context

`ClaudeCodeClient` kept one `claude --input-format stream-json` process per client and wrote each
`generate_content` call into it as the next user turn. Every call therefore saw every earlier prompt
and answer on that client (live probe 2026-10-02: a second call recovered a secret word set by the
first). The persona-realism judge cached one client per worker thread, so its rounds were neither
cold nor independent (about 94% of the 6,386 judge calls behind the pre-fix figures carried earlier
judgements in context), and Claude generation arms saw every earlier category call of a persona. The
CLI was also spawned in the caller's working directory without `--setting-sources ""`, so it loaded
the repository's `CLAUDE.md`, the user instructions and the memory index (~27k setup tokens).

The CLI (2.1.289) documents no in-band conversation reset for stream-json input; its only session
controls (`--resume`, `--continue`, `--session-id`, `--fork-session`) are process-level. It has no
sampling-temperature flag or settings key.

## Decision

1. Each call (and each retry attempt) spawns one `claude -p` process with `--output-format json`,
   `--no-session-persistence`, `--max-turns 1`, `--tools ""`, `--strict-mcp-config`,
   `--setting-sources ""`, `--disable-slash-commands`, the system prompt as `--system-prompt`, the user
   prompt on stdin, and an empty temporary directory as its working directory. The process tree is
   killed and reaped in a `finally`. No session flag is ever passed.
2. Each call's metadata carries `context_isolation = "fresh_process_per_call_v1"` and
   `temperature_applied = False`.
3. The persona-realism verdict cache stores the tag; the runner refuses to skip or top up a cache
   with any other tag (or none) without `--force`, and refuses to cache a verdict from a client whose
   metadata does not report the tag. Reports stamp the tag read from their caches; `realism_ranking`
   compares it as a judge-identity key.
4. `judge.yaml` carries no `temperature`; the loader raises if one is declared, because the CLI route
   cannot apply it.

## Consequences

- Independence holds by construction for every consumer (judge and generation) and is pinned by
  offline tests (`tests/test_claude_cli_call_isolation.py`) plus an opt-in live probe
  (`RUN_LIVE_CLAUDE=1`).
- Setup cost fell from ~37k to ~0.5k input tokens per call; each call pays a process launch
  (~3.3-3.7 s per short call end to end, ~250 MB peak per process, measured 2026-10-04).
- Every persona-realism artifact produced before 2026-10-04 is from the shared-conversation regime and
  must be re-judged with `--force`; `realism_ranking` refuses to mix the two.
- The judge's sampling temperature is the CLI default and cannot be set on this route. A manuscript
  claim of "temperature 0" is false for every judge run to date. Only a direct-API judge route
  (plan option D) could set it.
- Claude generation arms produced before 2026-10-04 ran with within-persona conversation history (a
  provider confound against every other model); regenerating them is a separate decision.
