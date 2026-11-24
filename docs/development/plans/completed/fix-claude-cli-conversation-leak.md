# Plan: Make every `claude` CLI call an independent conversation

**Date:** 2026-10-02
**Author:** Basil
**Status:** Completed 2026-10-04 (Phases 1-3 and documentation). Phase 4 (bias measurement) and
Phase 5 (re-run) are operator follow-ups -- see [Implementation notes](#implementation-notes-2026-10-04).
**Base Branch:** `dev`
**Branch:** implemented on `feature/mapping-fixes-scb-audit` (the branch checked out at the time),
not on a dedicated `feature/fix-claude-cli-conversation-leak` branch.

> **Base branch note.** The plan was written while `feature/typicality-distribution-grid` was checked
> out. That branch is not the intended base: the fix branches from `dev` (the integration line).

> **Handover note.** This plan is self-contained. Every measurement it relies on was taken on
> 2026-10-02 and is copied here; the scratch scripts that produced them were temporary and are not
> referenced. Section [Open decisions](#open-decisions) lists what still has to be decided before
> implementation starts.

---

## Implementation notes (2026-10-04)

**Decisions taken** (open decisions 1 and 4): option **A** (fresh minimal process per call, CLI
route); the runner keeps its per-thread client cache, which now holds only configuration. Open
decisions 2 (round basis), 3 (regenerate Claude personas) and 5 remain with the operator.

**Phase 1, measured live (claude CLI 2.1.289, `claude-sonnet-5`):**

- PELICAN probe on one client: call 1 set the secret, call 2 answered `UNKNOWN`; three calls had
  three distinct `session_id`s. Instruction probe ("quote any CLAUDE.md / memory you can see"):
  `NONE`.
- Setup cost per fresh call: ~508-529 plain input tokens, 0 cache-read, 0 cache-creation (was
  ~9.9k + ~27k with the old flags in the repo cwd).
- Latency: 3.3-3.8 s per short call end to end, launch included.
- Peak working set of the `claude` process tree: ~245 MB per process (4 sequential calls, polled via
  `Win32_Process`), against the ~400 MB that motivated the per-thread design. At `workers: 8` that is
  ~2 GB at most; the worker count is unchanged.
- Zero `claude` child processes remained after the calls.
- Option B spike skipped: A met the success criteria.

**Phase 2 -- `src/population_synthetic/clients/claude_code_client.py`** (a shared client under
`clients/`, not `generators/`): the stream-json machinery is replaced by `_run_once`, which spawns
`build_claude_argv(model, system)` = `claude -p --model M --output-format json
--no-session-persistence --max-turns 1 --tools "" --strict-mcp-config --setting-sources ""
--disable-slash-commands [--system-prompt S]`, passes the prompt on stdin through `communicate`,
runs in a fresh `TemporaryDirectory`, and kills the process tree in a `finally` (`taskkill /F /T` on
Windows, `killpg` elsewhere). An unparsable stdout raises. The retry loop, error categories and
telemetry fields are unchanged; metadata gains `context_isolation` (`CONTEXT_ISOLATION =
"fresh_process_per_call_v1"`), `temperature_applied: False` and `session_id`. `close()` kills an
in-flight call, so the generation script's `_active_clients` drain keeps working.

**Temperature finding (for the manuscript).** `claude --help` (2.1.289) has no temperature flag and
no settings key sets one; `--effort` is not a sampling temperature. The judge therefore has always
sampled at the CLI default: Methods 4.4.2's "temperature 0" is false for every judge run, before and
after this fix. The config was made truthful rather than the setting faked: `temperature` was
removed from `judge.yaml` and `JudgeConfig`, the loader **raises** if the key is declared, the judge
factory no longer passes it, and report provenance stamps `temperature: null`,
`temperature_applied: false`. Only option D (direct API) could make temperature 0 true.

**Phase 3 -- gates:**

- `runner.py`: every persona cache stores `context_isolation`; the resume gate raises (pointing at
  `--force`) on a cache whose tag differs or is absent, both for a complete cache (no silent skip)
  and a partial one (no top-up); `plan_only` (`--rewrite-artifacts`) is exempt because it judges
  nothing. A successful call whose client metadata does not report the tag raises. Stale docstrings
  corrected.
- `reduce.py`: `LoadedPersona.context_isolation` read from the cache.
- `artifacts.py`: `provenance.context_isolation` is read **from the caches**
  (`untagged_shared_conversation` for pre-fix caches; a combination mixing regimes raises), plus the
  honest temperature fields.
- `realism_ranking/loader.py`: `context_isolation` joins `JUDGE_IDENTITY_KEYS` (and therefore
  `CAPPED_IDENTITY_KEYS`), so a consumption set mixing regimes raises, capped or not. Old reports
  without the key read as `None` and are refused beside new ones.

**Tests:** new `tests/test_claude_cli_call_isolation.py` -- fake `Popen` whose process answers with
the number of prompts it has seen (always 1), argv/cwd/stdin assertions (no session flag, empty
`--tools` / `--setting-sources`, prompt never in argv, empty temp cwd that is removed afterwards),
process cleanup on timeout / error result, honest metadata, the runner, artifact and ranking gates,
the config refusal, and an opt-in live PELICAN probe (`RUN_LIVE_CLAUDE=1`, passed). The smoke stub
now reports the tag; `test_default_client_factory_passes_timeout` asserts no `default_config`.

**Docs:** `persona-realism-judge.md` (new section "Call independence and the context-isolation
tag"; config table; homogeneity gate), `CLAUDE.md`, `commands.md`, `analysis_registry.yaml`,
`persona_realism/__init__.py`, the script docstring, new ADR
`decisions/2026-10-04-claude-cli-call-is-a-fresh-process.md`, amendment to ADR 2026-08-07.

**Cache impact.** Every existing verdict cache (all 59 Swedish competitors in
`03_Analysis/persona_realism/swedish_02/`, copied to `03_Analysis_backup-2026-10-04/`) is untagged
and will be refused by the runner; it can only be re-judged with `--force` (or rewritten, unchanged
in kind, with `--rewrite-artifacts`, which stamps `untagged_shared_conversation`).

**Phase 5 run estimate** (not launched). Latest cap index
(`03_Analysis_backup-2026-10-04/population_cap/_mapped/_index.json`): 65 combinations, 58 kept at
n = 100, 7 withdrawn; plus `real_swedish_02` capped at `real_sample_size: 100` -> 59 competitors x
100 = 5,900 personas. Previous judge telemetry: 6,386 calls, median 3.7 s / mean 4.5 s per call
without launch, mean 227 output tokens; new per-call input ~1.8k tokens (prompt ~4.3k chars +
~0.5k scaffold) instead of ~50k. Assuming ~6-7 s per call including launch and `workers: 8`
(~70-80 calls/min):

| Basis | Calls | Wall time | API-equivalent cost (Sonnet 5, $3/$15 per M) |
|---|---|---|---|
| `--rounds 1` (manuscript basis) | 5,900 | ~1.2-1.4 h | ~$50 |
| `--rounds 3` (config default) | 17,700 | ~3.7-4.2 h | ~$155 |

On the CLI route this is billed against the subscription windows, not in cash; resume is per
persona, so a run can be split across windows. The old regime cost ~$0.028/call API-equivalent
(`real_swedish_02`: $2.81 for 100 calls), so the fix cuts per-call cost about threefold. The
`03_Analysis/` folder was being rebuilt by concurrent work at the time of writing: run
`map_populations` -> `validate_mapped` -> `population_cap` first. Then:

```bash
python scripts/analyze/analyze_persona_realism.py --country swedish_02 --force --rounds 1
python scripts/analyze/rank_persona_realism.py --country swedish_02
```

(`--rounds 3` for ICC / Krippendorff's alpha.) Back up `03_Analysis/persona_realism/` and
`realism_ranking/` first if not already done.

---

## Overview

[`ClaudeCodeClient`](../../../../src/population_synthetic/clients/claude_code_client.py) keeps one
`claude` CLI process alive per client instance and writes every `generate_content` call into the
**same conversation**, so a call sees every earlier prompt and answer on that client. The
persona-realism judge reuses one client per worker thread, so its "N cold rounds" are neither cold
nor independent, and every Claude-generated persona was generated inside one growing conversation.
The fix makes each call a fresh, minimal-context conversation, stamps that fact into the judge's
provenance so old and new verdicts cannot be mixed, measures how much the leak biased the existing
results, and then re-runs what it touched.

## Problem Statement

### The defect (verified 2026-10-02)

- [`ClaudeCodeClient._launch_process`](../../../../src/population_synthetic/clients/claude_code_client.py#L133)
  starts `claude --input-format stream-json --output-format stream-json ...` once; the class
  docstring ([lines 28-37](../../../../src/population_synthetic/clients/claude_code_client.py#L28))
  states the process is reused until the model or system prompt changes.
- [`_send_prompt`](../../../../src/population_synthetic/clients/claude_code_client.py#L230) writes
  each call as a new `user` message into that process's stdin. The CLI treats it as the next turn of
  one conversation (`--no-session-persistence` only stops the session being saved to disk; it does
  not reset it; `--max-turns 1` limits agent turns per message, not the conversation length).
- Live probe on the same client (same PID): call 1 "The secret word is PELICAN. Reply only OK.",
  call 2 "What was the secret word?" replied **PELICAN**. Call 2's `cache_creation_input_tokens`
  grew, confirming the history was re-sent.

### Where it bites: the persona-realism judge

[`runner.py`](../../../../src/population_synthetic/analysis/persona_realism/runner.py) deliberately
creates the judge client **per worker thread, not per persona** (module docstring
[lines 20-29](../../../../src/population_synthetic/analysis/persona_realism/runner.py#L20);
`_thread_client` at [line 562](../../../../src/population_synthetic/analysis/persona_realism/runner.py#L562);
[`_default_client_factory`](../../../../src/population_synthetic/analysis/persona_realism/runner.py#L169)).
The motive was host starvation: one ~400 MB `claude` process per persona. The consequence:

1. Every round of a persona sees that persona's earlier rounds and verdicts, so round-to-round
   agreement (ICC, Krippendorff's α) is inflated by construction — the judge can copy itself.
2. Every persona a thread judges sees all personas that thread judged before it (their full
   attribute lists, verdicts, typicality scores and clash lists). A verdict is therefore a function
   of the thread's scheduling history, which is non-deterministic. This violates
   [ADR 2026-08-07, Decision 1](../../decisions/2026-08-07-persona-realism-per-combination-split.md)
   ("a per-unit task's output is order-independent") at the persona level.
3. Context grows over the whole combination (about 100 personas / 8 workers ≈ 12-13 personas per
   thread), so later personas are judged against a longer, combination-specific anchor set.

Two docstrings inside the runner are now false and contradict the module docstring:
`_judge_and_write_persona` ([line 594](../../../../src/population_synthetic/analysis/persona_realism/runner.py#L594):
"Owns a single judge client for this persona (created here, `close()`d in a `finally`)") and
`_judge_one_round` ([line 305](../../../../src/population_synthetic/analysis/persona_realism/runner.py#L305):
"Reuses the persona's own client").

### Forensic evidence already on disk (zero LLM cost)

Each judge call's telemetry (`persona_XXXXX.jsonl`, written by
[`_build_entry`](../../../../src/population_synthetic/analysis/persona_realism/runner.py#L247))
records `prompt_tokens`, `cache_read_tokens` and `cache_creation_tokens`. Their sum is the total
input the model saw. Over the current Swedish output
(`02_Data/03_Analysis/persona_realism/swedish_02/`, 59 competitors, 6,386 calls):

| Quantity | Value |
|---|---|
| Minimum total input per call (a call with no history) | 28.1k tokens (runs of 2026-08-05), 31.6-31.7k (runs of 2026-08-19/20) |
| Median total input per call, per competitor | 38k-67k (typically 48k-55k) |
| Maximum total input per call, per competitor | 58k-95k |
| Share of calls with input > minimum + 3k tokens | 0.81-0.97 in 55 of 59 competitors |
| Competitors with **no** growth (flat ~28.15k) | the four `openrouter_qwen35_flash` competitors judged with methods other than `all_pick` |

Reading: ~94% of the judge calls behind the current figures carried earlier judgements in context,
typically 20k-27k tokens of them (an estimated ~3.9k tokens per earlier exchange, so roughly 5-7
earlier personas at the median and up to ~12 at the maximum). The real reference `real_swedish_02`
(median 66.6k) is affected like every synthetic competitor. Why the four `qwen35_flash` competitors
were judged cold is **not established** (same date, same code era); they are a natural but
confounded control and must not be used as an estimate of the bias.

Per-round dates also show the round regime is mixed: e.g. `all_generate_pick_v2_claude_haiku` holds
round 0 from 2026-08-05 and round 1 from 2026-08-12 (top-up), so its two rounds came from different
processes and different thread histories.

Git history of the runner's client lifecycle (for dating which caches are affected):
`ed139e4` (2026-07-23) one client for the run; `7545043` (2026-07-24) one client per persona —
rounds of a persona shared context, personas did not; `98d9738` (2026-08-07) one client per worker
thread — cross-persona leak. The telemetry of the 2026-08-05 runs already shows cross-persona growth,
so those runs used the per-thread logic before it was committed; **telemetry, not commit date, is
the authority** for whether a cache is affected.

### Related finding: the repository's own instructions are in the model's context

`ClaudeCodeClient` spawns `claude` with the caller's working directory (no `cwd=` in
[`Popen`](../../../../src/population_synthetic/clients/claude_code_client.py#L158)) and without
`--setting-sources ""`. Run from the repo root, the CLI therefore loads the project
[`CLAUDE.md`](../../../../CLAUDE.md), the user-level instructions and the auto-memory index, and runs
user-level hooks. Measured on 2026-10-02 per fresh call:

| Launch configuration | Setup tokens per call |
|---|---|
| Current flags, repo cwd | ~9.9k cache-read + ~27k cache-creation |
| Current flags, neutral empty cwd | ~9.9k cache-read + ~11.9k cache-creation |
| + `--tools ""` | ~2.3k |
| + `--setting-sources ""` | ~574 plain input tokens; `CLAUDE.md` and memory **not** loaded |
| + `--disable-slash-commands`, `--exclude-dynamic-system-prompt-sections` | no measurable change |
| `--bare` | unusable: requires `ANTHROPIC_API_KEY`; the account authenticates via OAuth |

The judge's no-history baseline rose from 28.1k (2026-08-05) to 31.6k (2026-08-19), consistent with
`CLAUDE.md` growing in between. Those documents describe the study, its reference population and
its interim findings, so both the judge and the Claude generation arms may have been primed by them.
This is a second contamination channel, independent of the conversation leak, and the minimal flags
close it.

### Related finding: the judge temperature never reaches the CLI

[`judge.yaml`](../../../../config/analysis/persona_realism/judge.yaml) sets `temperature: 0.0` and the
factory passes `default_config={"temperature": ...}`
([runner.py line 175](../../../../src/population_synthetic/analysis/persona_realism/runner.py#L175)),
but `ClaudeCodeClient` only copies it into its metadata. `claude --help` (2.1.287) has no
temperature flag (it has `--effort`, which is not a sampling temperature), and no settings key sets
one. [`artifacts.py` line 159](../../../../src/population_synthetic/analysis/persona_realism/artifacts.py#L159)
nevertheless stamps `temperature` into every report's provenance, so the provenance currently
asserts a setting that was never applied. On the CLI route this **cannot be fixed**, only made
honest; only the direct-API route (option D below) can set it.

### Identity generation with `--provider claude`

Consumers of `ClaudeCodeClient` (all of them, from a grep of `src/`, `scripts/`, `tests/`):

| Consumer | Client lifetime | Leak scope |
|---|---|---|
| [`generate_identities_parallel.py::_generate_one`](../../../../scripts/generate/generate_identities_parallel.py#L129) (line 189) | one client **per persona**, closed in `finally` | within a persona only |
| [`generate_identity.py`](../../../../scripts/generate/generate_identity.py#L311) (line 312) | one client per invocation (single persona) | within a persona only |
| [`persona_realism/runner.py`](../../../../src/population_synthetic/analysis/persona_realism/runner.py#L169) | one client per worker thread | across rounds **and** personas |
| [`scripts/dev/benchmark_claude_latency.py`](../../../../scripts/dev/benchmark_claude_latency.py) | dev benchmark | not a results path |
| [`tests/test_realism_judge_parse.py`](../../../../tests/test_realism_judge_parse.py#L278) | monkeypatched fake | none |

Generation does **not** leak across personas. It does leak within a persona: the system instruction
is run-level and identical for every call
([`resolution_context.py` lines 245-275](../../../../src/population_synthetic/generators/synthetic/resolution_context.py#L245)),
so the process is never restarted and every category call of a persona (14-51 calls depending on the
strategy) sees every earlier prompt and answer of that persona.

Is that within-persona context intended? **No.** The generator is written against the stateless
`LLMClient` protocol: each call builds its full prompt, and the context a category is meant to see is
put into the prompt explicitly by the strategy (`_build_context_block`; the `context: none` switch of
[`fix-all-pick-context-leak.md`](../completed/fix-all-pick-context-leak.md)). Gemini, OpenRouter,
OpenAI-compatible and Ollama clients send only `[system, user]` per call
([`openai_compat_client.py` line 157](../../../../src/population_synthetic/clients/openai_compat_client.py#L157),
[`ollama_client.py` line 192](../../../../src/population_synthetic/clients/ollama_client.py#L192)).
So for Claude arms only:

- `all_pick` / `all_pick_v2`, the manuscript's context-free baseline, is **not** context-free: the
  earlier picks are in the conversation even though the prompt omits them. The 2026-07-22 fix of
  the same name closed the prompt channel but not this one.
- DAG strategies see non-parent categories through the history, not only their declared parents.
- A JSON-parse retry in `ResolutionContext` re-sends the prompt after the model's own failed answer.
- A transport retry or a resumed checkpoint restarts the process, so some personas lost their history
  mid-way: the amount of leaked context is not even constant within an arm.

This is a provider confound: Claude arms ran under a different context regime from every other
model. The generation telemetry (`01_Raw/*claude*/persona_*/llm_interactions.jsonl`) carries no cache
token fields, so the growth cannot be quantified forensically there; the conclusion rests on the code
path above, which is certain.

### Affected artefacts

| Artefact | Affected by | How |
|---|---|---|
| `persona_realism` verdict caches, `{combo}_personas.csv`, `{combo}_clashes.csv`, `{combo}.json` (all 59 Swedish competitors incl. `real_swedish_02`) | judge leak, instruction priming, temperature claim | verdicts order-dependent; rounds not independent |
| `realism_ranking`: Axis A impossibility ranking, Axis B dispersion contrast, ICC / Krippendorff's α, Kruskal-Wallis/Dunn, logit mixed model, severity heatmaps and pair summaries (S1-S3), typicality axis, typicality distribution grid, closeness to the reference | everything above | inherits the verdicts |
| `figure_selection` manuscript set entries 19, 21-25 ([`figure_selection.yaml`](../../../../config/analysis/figure_selection.yaml#L134)) and the manuscript's realism figures (incl. figure 5B, the severity/clash figure) | inherits `realism_ranking` | |
| Claude-generated personas: Swedish `swedish_02_*_v2_claude_haiku`, `*_v2_claude_sonnet` (10 combinations), older `swedish_*_claude_{haiku,sonnet,opus}`, Italian `italian_*_claude_*` | within-persona leak, instruction priming | `all_pick` not context-free for Claude; provider confound |
| Everything downstream of those personas: `mapping` → `population_cap` → fidelity, `model_ranking`, `method_significance`, `generation_metadata` (token counts include the history), `cost_efficiency`, `validation_attrition` | inherits generation | Claude rows only |

## Goals

### In Scope
1. Every `ClaudeCodeClient.generate_content` call is an independent conversation, for every consumer.
2. The CLI is launched with minimal context: `--tools ""`, `--setting-sources ""`, a neutral empty
   working directory, no project or user instructions, no hooks.
3. The judge's provenance records the context regime and the temperature honestly; the persona
   cache resume gate and the `realism_ranking` homogeneity gate refuse to mix regimes.
4. A measurement, before any full re-run, of how much the leak changed the judge's outputs.
5. Regression tests for call independence and for process cleanup; existing resume / top-up tests
   unchanged and passing.
6. A documented re-run of `persona_realism` → `realism_ranking` → `figure_selection`.
7. Documentation corrected wherever it claims cold or independent rounds.

### Out of Scope
- Re-generating Claude personas. Whether to do it is an [open decision](#open-decisions); this plan
  only fixes the client and records the confound.
- Changing the judge prompt, the reduction or any statistic.
- Editing the external manuscript (listed as a follow-up only).
- Switching other providers' clients.

## Success Criteria

- [ ] Two consecutive `generate_content` calls on one `ClaudeCodeClient` cannot see each other
      (offline test with a fake CLI; opt-in live PELICAN probe answers without the secret word).
- [ ] A fresh call's setup cost is ≤ ~3k input tokens and `CLAUDE.md` is not in context (live probe).
- [ ] No `claude` process outlives its call: after a run of N calls (including timeouts and error
      results), zero child processes remain.
- [ ] Measured per-process peak RAM and launch time with the minimal flags are recorded in this plan
      and the chosen worker count is justified against host RAM.
- [ ] Judge reports carry `context_isolation` and an honest temperature field; `realism_ranking`
      raises on a consumption set mixing isolation regimes; the runner refuses to top up a cache
      written under the old regime without `--force`.
- [ ] Bias measurement reported (can_exist rate, typicality, severity, ICC/α, shared vs fresh) before
      the full re-run.
- [ ] All existing persona_realism tests pass unchanged (except the factory test, updated
      deliberately).
- [ ] No document in the repo still claims "cold rounds" or a temperature that is not applied.

## Definitions

- **Independent call:** the model receives exactly the system prompt and the one user prompt of this
  call plus the CLI's fixed scaffolding; no prior user or assistant message. Testable: the fake CLI
  records the message list it received; the live probe cannot recover a secret from a previous call.
- **Shared-context regime:** a call made on a process that had already served ≥ 1 call. Forensically:
  total input (`prompt + cache_read + cache_creation`) > that run's no-history minimum + 3k tokens.
- **Minimal launch:** `claude -p` with `--tools ""`, `--setting-sources ""`, `--strict-mcp-config`,
  `--no-session-persistence`, `--model`, `--system-prompt`, output format JSON, spawned with `cwd`
  set to an empty temporary directory.
- **Context-isolation tag:** a string stamped into each persona cache and report, e.g.
  `"fresh_process_per_call_v1"`; the old regime is any cache lacking it.
- **Process leak:** a `claude` child process alive after the call that spawned it returned or raised.

---

## Technical Design

### Approach

Recommended: **option A, a fresh minimal process per call**, gated by a measurement of per-process
RAM; plus provenance tagging; with option D kept as a configurable alternative judge route if the
measurements make the CLI route impractical or temperature control is required by the manuscript.

Rationale, premise by premise:

1. Independence must be guaranteed by construction, not by trusting an undocumented protocol
   message (premise: option B has no documented reset; see below).
2. The persistent design exists to avoid ~8-10 s launch overhead (2026-05 measurement, in
   [`claude-code-client-persistent-stream.md`](../completed/claude-code-client-persistent-stream.md))
   and ~400 MB per process. The 2026-10-02 measurements with the minimal flags show ~3.3 s median per
   call **including** process launch on ~1.1k-token calls, and throughput of ~82 calls/min with 6
   workers and ~105-124 calls/min with 12 workers, with no rate-limit errors. So launch time is no
   longer prohibitive. RAM per process with minimal flags is **not yet measured**; the host-starvation
   argument applied to processes that were alive concurrently, and per-call processes are bounded by
   the worker count exactly as per-thread ones are (at most `workers` alive at a time). The plan
   therefore measures RAM first (Phase 1) and only then commits.
3. A fresh process per call fixes the judge and generation with one change at the single point all
   consumers share, and removes `_ensure_process` / reader-thread state, which is simpler.

The working pattern (from the 2026-10-02 mapping audit): spawn one `claude -p` per call with
`--output-format json`, pass the prompt on stdin, read the single JSON result, and close/kill the
process in a `finally` (wait with timeout, then kill, then wait). Do not copy that script; the
client keeps its existing retry loop, metadata fields, telemetry and error categories.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|---|---|---|---|
| **A. Fresh minimal process per call** | Independence by construction; one change covers judge and generation; removes stateful reader thread; minimal flags cut setup from ~37k to ~0.6k tokens | Launch cost per call (~3.3 s median incl. launch, measured); RAM per process unmeasured with minimal flags; generation of a 42-call persona pays 42 launches | **Recommended**, conditional on Phase 1 RAM/launch measurement |
| **B. Persistent process + per-call context reset** | Keeps launch amortised | `claude --help` (2.1.287) documents **no** clear / new-session control message for `--input-format stream-json`; the only session controls are `--resume`, `--continue`, `--session-id`, `--fork-session`, all process-level. Sending `/clear` as a user message is undocumented and `--disable-slash-commands` exists, so its behaviour in print mode is unknown. Any reset relies on an unverified, version-dependent behaviour | Rejected unless a time-boxed spike (Phase 1, optional) proves a documented reset; even then it needs the live independence probe in CI-adjacent tests |
| **C. One process per persona-round (judge only)** | Independent per round for the judge | Identical cost to A for the judge (one call per round); does not fix generation; leaves the client stateful and the trap in place for the next consumer | Rejected: A subsumes it |
| **D. Direct API route for the judge (OpenRouter `anthropic/claude-sonnet-5`)** | Stateless HTTP per call (existing `OpenAICompatClient`, `[system, user]` only); real `temperature` control; no process launches; billed outside the subscription's 5-hour window. Priced at $2 in / $10 out per M tokens in [`model_pricing.yaml` line 65](../../../../config/analysis/model_pricing.yaml#L65) (Anthropic first-party Sonnet 5 is $3/$15, line 45) | Changes the judge's serving route (provider, possibly a different model build) mid-study, so old and new verdicts are not comparable even beyond the leak; needs `OPENROUTER_API_KEY`; adds a `provider` key to `judge.yaml` and a factory switch; cost is real money | Viable alternative. Recommended **only** if the manuscript needs temperature 0 to be true, or if A's measured RAM/launch cost is impractical. Open decision |
| E. Keep as is, document | No work | Results are order-dependent; reliability inflated; contradicts the ADR and the Methods text | Rejected |

Independently of A-D, the minimal flags and neutral `cwd` are adopted (they close the instruction
priming channel and cut ~36k setup tokens per call).

### Architecture & Module Contracts

| Module / layer | Responsibility | Inputs → Outputs | Must NOT know about |
|---|---|---|---|
| `ClaudeCodeClient` (rewritten internals, same public interface) | One independent `claude -p` call per `generate_content` | prompt, system_instruction, model → result text; `last_metadata` with tokens, timing (launch + inference), cache tokens, `context_isolation` | callers, personas, rounds, threads; the project directory (spawns in an empty temp dir) |
| `claude_cli_launch` helper (new, private to the client module or `clients/`) | Build the minimal argv and spawn/close one process safely | model, system prompt, timeout → (stdout JSON, exit) ; guarantees termination in `finally` | prompts' content; retry policy |
| `persona_realism/runner.py` | Fan-out, resume gate | unchanged; the per-thread client cache can stay (it is now harmless) or become per call; stamps `context_isolation` from client metadata into the persona cache | how the client isolates calls |
| `persona_realism/config.py` + `judge.yaml` | Judge config | adds `context_isolation_required` (or equivalent) and, if option D, `provider`; temperature documented as "not applied on the CLI route" | |
| `persona_realism/artifacts.py` | Provenance | stamps `context_isolation` and `temperature_applied: true/false` instead of an unconditional `temperature` | |
| `realism_ranking/loader.py` | Homogeneity gate | adds the isolation tag to [`JUDGE_IDENTITY_KEYS`](../../../../src/population_synthetic/analysis/realism_ranking/loader.py#L101) so mixed sets raise | |

Retained client interface: `generate_content`, `last_metadata`, `history`, `clear_history`,
`close` (becomes a no-op or kills an in-flight process), `update_config`, `update_default_model`,
`get_current_configuration`, `retry_until_success`. `close()` and the generation script's
`_active_clients` registry ([lines 112-121](../../../../scripts/generate/generate_identities_parallel.py#L112))
must keep working.

Resume semantics: the runner's round-count gate skips a persona whose cache holds ≥ `n_rounds`
rounds. Without a regime check, every old (leaky) cache would be silently treated as complete. The
gate therefore also reads the cache's `context_isolation`; a cache without the current tag is
**not** topped up (topping up would mix regimes inside one persona) — the runner raises with a
message pointing to `--force`. This mirrors the generation checkpoint's fingerprint rule.

---

## Implementation Plan

### Phase 1: Measure and decide (no repo code change)
**Goal:** settle option A vs D (and B's spike) on numbers.

- [ ] 1.1 Measure per-process peak RSS (process tree: `claude` launcher + its node child) and launch
      latency for the minimal launch, 20 sequential calls, Sonnet 5, with a typical judge prompt
      (one rendered from a mapped persona). Compare with the ~400 MB figure that motivated the
      per-thread design.
- [ ] 1.2 Measure throughput and failure rate at `workers` = 4, 8, 12 on the judge prompt (the
      2026-10-02 numbers were for ~1.1k-token mapping calls; judge calls are ~4-5k tokens).
- [ ] 1.3 Optional, time-boxed (≤ 1 h): option B spike — does any stream-json control message
      reset the conversation in 2.1.287? Accept only if the PELICAN probe passes 20/20 and the
      behaviour is documented.
- [ ] 1.4 Live probe that the minimal launch does not load `CLAUDE.md` (ask the model to quote any
      project instruction it can see; expect none) and confirm the instruction-priming finding on the
      current flags.
- [ ] 1.5 Record numbers in this plan; take the [open decisions](#open-decisions).

**Files Modified:** this plan only.
**Dependencies:** None

### Phase 2: Independent calls in `ClaudeCodeClient`
**Goal:** every call is a fresh minimal process (option A).

- [ ] 2.1 Replace the persistent stream-json machinery (`_launch_process`, `_reader_thread`,
      `_ensure_process`, `_send_prompt`, `_read_until_result`) with one per-call spawn: minimal argv
      (Definitions), `cwd` = a `tempfile.TemporaryDirectory()` created per call (or one per client,
      empty and never written), prompt on stdin, `--output-format json`, `communicate(timeout=...)`.
- [ ] 2.2 Termination in `finally`: on timeout or exception, kill the process tree (on Windows,
      `taskkill /F /T /PID` or `psutil` children) and `wait()`; never leave a child alive.
- [ ] 2.3 Keep retry loop, error categories (`timeout`, `network`, `model_limitation`), metadata and
      telemetry fields; `elapsed_ms` stays launch + inference; add `context_isolation` to metadata.
- [ ] 2.4 Fail fast: a JSON result with `is_error` raises as today; an unparsable stdout raises
      (no silent empty result).
- [ ] 2.5 Document in the class docstring why the process is not reused (link this plan).
- [ ] 2.6 Leave `temperature` in `default_config` but record `temperature_applied: False` in
      metadata; do not invent a flag.

**Files Modified:**
- [`src/population_synthetic/clients/claude_code_client.py`](../../../../src/population_synthetic/clients/claude_code_client.py) — per-call process, minimal flags, neutral cwd, metadata fields.

**Dependencies:** Phase 1

### Phase 3: Judge provenance and gates
**Goal:** old and new verdicts can never be combined silently.

- [ ] 3.1 Runner: stamp `context_isolation` (from client metadata) into each persona cache; resume
      gate raises on a cache lacking the current tag unless `force`.
- [ ] 3.2 Runner: correct the stale docstrings (module docstring lines 20-29,
      `_judge_and_write_persona`, `_judge_one_round`); decide whether to keep the per-thread client
      cache (harmless now) or create a client per call (simpler mental model). Recommendation: keep
      per-thread (it only holds config), state why.
- [ ] 3.3 Artifacts: replace the unconditional `temperature` provenance with `temperature` (as
      configured) plus `temperature_applied` (false on the CLI route); add `context_isolation`.
- [ ] 3.4 `realism_ranking` loader: add the isolation tag to the judge-identity keys so a mixed
      consumption set raises.
- [ ] 3.5 `judge.yaml`: comment that temperature is not applied on the CLI route; if option D is
      chosen, add `provider` and wire the factory to `OpenAICompatClient` (`base_url`
      `https://openrouter.ai/api/v1`, `OPENROUTER_API_KEY`), add the judge model string to the
      judge section of `model_pricing.yaml`.

**Files Modified:**
- [`src/population_synthetic/analysis/persona_realism/runner.py`](../../../../src/population_synthetic/analysis/persona_realism/runner.py)
- [`src/population_synthetic/analysis/persona_realism/artifacts.py`](../../../../src/population_synthetic/analysis/persona_realism/artifacts.py#L159)
- [`src/population_synthetic/analysis/persona_realism/config.py`](../../../../src/population_synthetic/analysis/persona_realism/config.py)
- [`src/population_synthetic/analysis/realism_ranking/loader.py`](../../../../src/population_synthetic/analysis/realism_ranking/loader.py#L101)
- [`config/analysis/persona_realism/judge.yaml`](../../../../config/analysis/persona_realism/judge.yaml)
- (option D only) [`config/analysis/model_pricing.yaml`](../../../../config/analysis/model_pricing.yaml)

**Dependencies:** Phase 2

### Phase 4: Bias measurement (before any full re-run)
**Goal:** quantify what the leak changed, for the manuscript.

- [ ] 4.1 Zero-cost forensic table (already computed once; make it reproducible as a dev script
      under `scripts/dev/`): per competitor, per-call total input, share of shared-context calls,
      estimated number of earlier personas in context.
- [ ] 4.2 Sample design: 4 competitors spanning the range (`real_swedish_02`, one Claude combo, one
      OpenRouter combo, one Ollama combo) × 50 personas × 3 rounds, judged twice: (a) shared context,
      reproducing the old regime with a persistent client per thread at the old `workers=8`, and
      (b) fresh per call. Same personas, same prompt, same model. ≈ 1,200 calls.
- [ ] 4.3 Compare per competitor: can_exist (impossibility) rate with bootstrap CI; mean and
      dispersion (IOV) of typicality; S1/S2/S3 clash prevalence; round-to-round agreement (ICC,
      Krippendorff's α); paired per-persona agreement between regimes. Also regress each outcome on
      the persona's position in its thread's queue under (a) to show the drift.
- [ ] 4.4 Report: short findings note under `docs/development/` with the numbers and a sentence the
      manuscript can cite.

**Files Modified:** `scripts/dev/` measurement script (new), findings note (new).
**Dependencies:** Phase 3 (needs the fixed client for arm (b); arm (a) uses the old client from
`git show` of the pre-fix revision, or a test-only persistent mode).

### Phase 5: Re-run and downstream
**Goal:** regenerate every realism artefact under the isolated regime.

- [ ] 5.1 `python scripts/analyze/analyze_persona_realism.py --force --rounds <basis>` for all
      Swedish competitors (`--force` is required: the new gate rejects old caches).
- [ ] 5.2 `realism_ranking` (no LLM work), then `figure_selection --set manuscript`.
- [ ] 5.3 Re-stage the manuscript realism figures (selection entries 19, 21-25; manuscript figure 5B).
- [ ] 5.4 If the generation decision is "regenerate": separate plan.

**Dependencies:** Phase 4

Cost and time (estimates; Phase 1 replaces them with measurements):

| Run | Calls | Tokens (≈4.5k/call after minimal flags) | API-equivalent cost at Sonnet 5 $3/$15 | OpenRouter $2/$10 | Wall time at 82-124 calls/min |
|---|---|---|---|---|---|
| Measurement (Phase 4) | ~1,200 | ~5.4M | ~$20 | ~$13 | 10-15 min |
| Re-run, `--rounds 1` (manuscript basis) | ~5,900 (59 × 100) | ~27M | ~$100 | ~$65 | 50-75 min |
| Re-run, `--rounds 3` (config default) | ~17,700 | ~80M | ~$300 | ~$200 | 2.4-3.6 h |

Subscription 5-hour window (CLI route): measured on 2026-10-02, one ~1.1k-token Sonnet call ≈
0.0016 percentage points of the window by token-share estimate. Scaled to ~4.5k tokens/call that is
≈ 0.0065 pp/call: ~8 pp for the measurement, ~38 pp for `--rounds 1`, ~115 pp (more than one window)
for `--rounds 3`. The estimate is rough (token share, cache accounting unknown) and Opus sessions in
the same window dominate it; schedule `--rounds 3` across windows, or use option D. The runner's
resume makes splitting safe.

---

## Testing Plan

### Unit Tests
- [ ] Call independence (offline): patch `subprocess.Popen` with a fake that records argv, cwd and
      stdin per spawn; two `generate_content` calls produce two spawns, each stdin containing only its
      own prompt; argv contains `--tools ""`, `--setting-sources ""`; cwd is not the repo root.
- [ ] Fake stateful CLI: a fake `claude` script that answers with the number of user messages it has
      seen; every call returns 1.
- [ ] Process cleanup: fake that hangs past the timeout → the client kills it, raises `timeout`
      category after retries, and the fake's PID is no longer alive; same for an `is_error` result and
      for an exception raised mid-read.
- [ ] Metadata: `context_isolation` present; `temperature_applied` false; token/cache fields parsed
      from the JSON result.
- [ ] Runner gate: a cache without the isolation tag raises on resume without `force`; with `force`
      it is rewritten; a cache with the tag behaves exactly as today (skip / top-up).
- [ ] `realism_ranking` loader raises on a consumption set mixing tags.
- [ ] Update `test_default_client_factory_passes_timeout` deliberately if the factory signature changes.

### Integration Tests
- [ ] Existing [`tests/test_persona_realism_smoke.py`](../../../../tests/test_persona_realism_smoke.py)
      resume / top-up / force tests (lines 265-413) pass unchanged with the stub client (stubs do not
      carry the tag → the stub factory must emit it, or the tests set it; decide in Phase 3 and keep
      their assertions intact).
- [ ] `tests/test_generate_parallel_resume_run.py` passes (generation client lifecycle unchanged).

### Manual Verification (opt-in live, marked e.g. `@pytest.mark.live_claude`, skipped by default)
- [ ] PELICAN probe: call 1 sets a secret, call 2 asks for it; answer must not contain it. Repeat 5×.
- [ ] Instruction probe: the model cannot quote any line of the repo `CLAUDE.md`.
- [ ] After a 50-call run with 8 workers, no `claude` process remains (`tasklist`).

### Edge Cases
- [ ] Very long prompts on stdin (Windows pipe buffering): use `communicate`, never write-then-read.
- [ ] Non-UTF-8 bytes in output: `encoding="utf-8", errors="strict"` and fail loudly.
- [ ] `claude` missing from PATH: unchanged `RuntimeError` at construction.
- [ ] Concurrent clients in threads share no temp dir state.

---

## Documentation Plan

- [ ] [`docs/development/persona-realism-judge.md`](../../persona-realism-judge.md) — line 22 ("N cold
      rounds"), line 576-577 (`n_rounds` "independent", `temperature` "cold"): describe independent
      fresh-process calls, state temperature is not applied on the CLI route, add a dated note on the
      pre-fix regime and the bias measurement.
- [ ] [`CLAUDE.md`](../../../../CLAUDE.md) — the `persona_realism/` paragraph ("judges each individual
      mapped persona N cold rounds") and the `--provider claude` environment bullet (spawn mode,
      minimal flags).
- [ ] [`docs/architecture/commands.md`](../../../architecture/commands.md) line 177 ("cold rounds").
- [ ] [`src/population_synthetic/analysis/persona_realism/__init__.py`](../../../../src/population_synthetic/analysis/persona_realism/__init__.py) docstring ("at cold temperature").
- [ ] New ADR in [`docs/development/decisions/`](../../decisions/): "A `claude` CLI call is a fresh
      process with no project context", superseding the persistent-stream decision in
      [`claude-code-client-persistent-stream.md`](../completed/claude-code-client-persistent-stream.md)
      and the per-thread rationale; record the forensic numbers and the instruction-priming finding.
- [ ] Amend the ADR 2026-08-07 consequences section with a pointer: its order-independence was not
      held at persona level until this fix.
- [ ] Memory note "judge temperature unwired": resolve as "cannot be wired on the CLI route; provenance
      made honest" (or "wired via API route" if option D).
- [ ] External follow-up (not in repo): manuscript Methods 4.4.2 ("temperature 0", "independent
      rounds") and any realism Results numbers/figures; Claude-arm caveat for generation if not
      regenerated.

---

## Rollback Plan

1. The change is confined to one client module plus provenance fields; revert the branch's commits.
2. Data: Phase 5 runs with `--force` overwrite the verdict caches in place. Before Phase 5, copy
   `03_Analysis/persona_realism/` and `03_Analysis/realism_ranking/` to a dated backup so the
   pre-fix artefacts remain available for the manuscript comparison and for rollback.
3. The new resume gate makes a reverted client unable to top up new-tag caches silently only if the
   tag check is kept; on rollback, restore the backup rather than mixing.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Per-process RAM still ~400 MB → host starvation at 8 workers | Med | High | Phase 1 measurement; cap `workers` to what RAM allows; per-call processes never exceed `workers` alive |
| Windows: killed launcher leaves node child alive | Med | Med | Kill the process tree; cleanup test asserts no children |
| `--setting-sources ""` changes auth or model resolution | Low | High | Phase 1 live probe; the 2026-10-02 audit ran with it successfully |
| Subscription window exhausted mid-run | Med | Low | Resume is per persona; split across windows; or option D |
| CLI flag semantics change in a later version | Med | Med | Pin the tested version in the ADR; the live probes detect regressions |
| Old caches silently reused | High without gate | High | Isolation tag in cache + loader gate (Phase 3) |
| Generation behaviour of Claude arms changes after the fix while old Claude personas stay on disk | Certain if not regenerated | Med | Record regime in run metadata; decide regeneration explicitly |

---

## Open decisions

1. **Judge route:** CLI with fresh process (A, recommended) vs OpenRouter API (D). D is needed if the
   Methods must state temperature 0 truthfully; it also changes the serving route mid-study.
2. **Round basis for the re-run:** `--rounds 1` (manuscript basis, ~38 pp of a window) or 3 (needed
   for ICC/α; >1 window or API cost ~$200-300).
3. **Generation:** regenerate the 10 Swedish v2 Claude combinations (and older/Italian ones) under the
   isolated client, or keep them and report the Claude-arm context regime as a limitation. The fix in
   Phase 2 changes future Claude generation either way.
4. **Per-thread client cache in the runner:** keep (harmless after the fix) or drop.
5. **Whether the measurement (Phase 4) reproduces the old regime faithfully enough** — the old
   per-thread order was non-deterministic; arm (a) is a re-enactment, not a replay.

---

## References

- [`docs/development/plans/completed/claude-code-client-persistent-stream.md`](../completed/claude-code-client-persistent-stream.md) — why the process was made persistent (launch overhead, 2026-05).
- [`docs/development/plans/completed/fix-claude-code-client-parallel-haiku.md`](../completed/fix-claude-code-client-parallel-haiku.md) — earlier one-shot flags (`--tools ""`, `--no-session-persistence`).
- [`docs/development/plans/completed/fix-all-pick-context-leak.md`](../completed/fix-all-pick-context-leak.md) — the prompt-channel context leak in `all_pick`.
- [`docs/development/decisions/2026-08-07-persona-realism-per-combination-split.md`](../../decisions/2026-08-07-persona-realism-per-combination-split.md) — order-independence decision.
- [`docs/development/aborted-and-resumed-runs.md`](../../aborted-and-resumed-runs.md) — checkpoint fingerprint pattern mirrored by the isolation tag.
