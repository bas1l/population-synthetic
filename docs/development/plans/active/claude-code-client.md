# Plan: Claude Code Client for Persona Generation

**Date:** 2026-05-18
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/remove-sequential-identity-system`
**Branch:** `feature/claude-code-client`

---

## Overview

Add a `ClaudeCodeClient` that drives the `claude` CLI as a subprocess, enabling identity generation with Anthropic Claude models (Opus, Sonnet, Haiku) as a drop-in alternative to `GeminiClient`. A shared `LLMClient` Protocol decouples the identity layer from any concrete client implementation. Provider selection is exposed via a `--provider` flag on the generation scripts.

## Problem Statement

The identity generation pipeline is hard-wired to Google Gemini (`GeminiClient`). The `BaseIdentityGenerator` constructor type-hints `GeminiClient` directly, and every strategy class echoes that import. There is no way to route generation through Claude without modifying the identity layer. This makes A/B comparison between providers impossible and creates a single point of failure for all LLM-based generation.

## Goals

### In Scope
1. Introduce a `LLMClient` Protocol that `GeminiClient` already satisfies structurally (no changes to `GeminiClient`)
2. Create `ClaudeCodeClient` that wraps the `claude` CLI as a subprocess (no Anthropic SDK, no `ANTHROPIC_API_KEY`)
3. Decouple `BaseIdentityGenerator`, `FactoryIdentityGenerator`, and both strategy classes from the concrete `GeminiClient` type
4. Expose provider selection via `--provider gemini|claude` in `generate_identity.py` and `generate_identities_parallel.py`

### Out of Scope
- Temperature, top_p, or max_tokens control for Claude (the `claude` CLI does not expose these flags)
- A provider-agnostic config file format
- Benchmarking or automated A/B comparison tooling
- Adding the `anthropic` SDK as a dependency

## Success Criteria

- [ ] `ruff check src/` passes with no errors or warnings
- [ ] `python -c "from population_synth.clients.llm_protocol import LLMClient; print('ok')"` succeeds
- [ ] Gemini path is unchanged: `generate_identity.py --provider gemini` produces output identical to the current `--model` flag usage
- [ ] `generate_identity.py --provider claude --model sonnet` completes and writes a valid `identity.json`
- [ ] Omitting `GEMINI_API_KEY` with `--provider claude` does not raise (Claude Code manages its own auth)
- [ ] `ClaudeCodeClient()` raises `RuntimeError` immediately if `claude` is not on PATH

---

## Technical Design

### Approach

Use `typing.Protocol` as the shared structural contract. Both `GeminiClient` (unchanged) and the new `ClaudeCodeClient` satisfy it by duck typing — no inheritance required. The identity layer imports `LLMClient` from the protocol module instead of the concrete `GeminiClient`.

`ClaudeCodeClient` invokes `claude -p --model <model>` as a subprocess, passing the prompt via stdin (safer than positional arg for long/multiline/special-char prompts). The `system_instruction` kwarg (used by `IdentityGeneratorConfigurable`) maps to `--append-system-prompt`.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| `typing.Protocol` (structural) | Zero changes to `GeminiClient`; no import coupling | Less explicit than ABC | **Chosen** |
| Abstract Base Class | Explicit contract; consistent with `BasePxWebClient` pattern | No shared implementation to inherit; forces `GeminiClient` changes | Rejected |
| `anthropic` SDK (`ClaudeClient`) | Direct API access; temperature/max_tokens control | Requires `ANTHROPIC_API_KEY`; adds heavy dependency; diverges from user intent | Rejected |
| Duck typing only (no protocol) | Minimal code | No formal contract; type checkers blind | Rejected |

### Architecture Changes

Two new files; eight small modifications (mostly two-line import+type-hint swaps):

```
src/population_synth/clients/
├── llm_protocol.py          NEW — LLMClient Protocol
├── claude_code_client.py    NEW — subprocess wrapper for `claude` CLI
├── gemini_client.py         UNCHANGED
└── ...

src/population_synth/identity/
├── base_identity_generator.py       MODIFY — GeminiClient → LLMClient
├── factory_identity_generator.py    MODIFY — GeminiClient → LLMClient
├── identity_generator_batch.py      MODIFY — GeminiClient → LLMClient
└── identity_generator_configurable.py  MODIFY — GeminiClient → LLMClient

scripts/
├── generate_identity.py             MODIFY — add --provider, lazy imports
└── generate_identities_parallel.py  MODIFY — add --provider, lazy imports

CLAUDE.md                            MODIFY — document new client and protocol
```

---

## Implementation Plan

### Phase 1: Shared Protocol
**Goal:** Introduce `LLMClient` Protocol without touching any existing code.
**Started:** 2026-05-18
**Completed:** 2026-05-18

- [x] Task 1.1 — Create `src/population_synth/clients/llm_protocol.py` with `@runtime_checkable LLMClient(Protocol)` covering: `generate_content`, `update_config`, `update_default_model`, `get_current_configuration`, `clear_history`, `last_metadata` (property), `history` (property)

**Files Modified:**
- `src/population_synth/clients/llm_protocol.py` — new file

**Dependencies:** None

---

### Phase 2: ClaudeCodeClient
**Goal:** Implement the subprocess wrapper satisfying `LLMClient`.
**Started:** 2026-05-18
**Completed:** 2026-05-18

- [x] Task 2.1 — Create `src/population_synth/clients/claude_code_client.py`
  - Constructor: `__init__(self, model_name: str = "sonnet", default_config: Optional[Dict[str, Any]] = None)`
  - Fail-fast on init: `shutil.which("claude")` — raise `RuntimeError` if not found
  - `generate_content`: build `["claude", "-p", "--model", target_model]`; append `["--append-system-prompt", si]` if `system_instruction` present in merged params; run via `subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=120)`; raise `RuntimeError` on non-zero exit; return `result.stdout.strip()`
  - Metadata sidecar tracking identical to `GeminiClient`: `_last_execution_metadata` + `_execution_history` (no token counts — just model, config, timestamp)
  - Remaining public methods (`update_config`, `update_default_model`, `get_current_configuration`, `clear_history`) and properties (`last_metadata`, `history`) mirror `GeminiClient` body-for-body

**Files Modified:**
- `src/population_synth/clients/claude_code_client.py` — new file

**Dependencies:** Phase 1

---

### Phase 3: Decouple Identity Layer
**Goal:** Replace the hardcoded `GeminiClient` type hint throughout the identity layer.
**Started:** 2026-05-18
**Completed:** 2026-05-18

- [x] Task 3.1 — `base_identity_generator.py`: replace `from population_synth.clients.gemini_client import GeminiClient` with `from population_synth.clients.llm_protocol import LLMClient`; change `def __init__(self, client: GeminiClient)` → `client: LLMClient`
- [x] Task 3.2 — `factory_identity_generator.py`: same two-line swap; update `create_generator` signature
- [x] Task 3.3 — `identity_generator_batch.py`: same two-line swap
- [x] Task 3.4 — `identity_generator_configurable.py`: same two-line swap

**Files Modified:**
- `src/population_synth/identity/base_identity_generator.py`
- `src/population_synth/identity/factory_identity_generator.py`
- `src/population_synth/identity/identity_generator_batch.py`
- `src/population_synth/identity/identity_generator_configurable.py`

**Dependencies:** Phase 1

---

### Phase 4: Script Wiring
**Goal:** Expose `--provider` in both generation scripts.
**Started:** 2026-05-18
**Completed:** 2026-05-18

- [x] Task 4.1 — `scripts/generate_identity.py`:
  - Add `--provider gemini|claude` argument (default: `gemini`)
  - Change `--model` default to `None`; update help text to document per-provider defaults
  - Replace top-level `GeminiClient` import with lazy imports inside the provider branches:
    ```python
    if args.provider == "gemini":
        from population_synth.clients.gemini_client import GeminiClient
        client = GeminiClient(model_name=args.model or "gemini-2.5-flash")
    elif args.provider == "claude":
        from population_synth.clients.claude_code_client import ClaudeCodeClient
        client = ClaudeCodeClient(model_name=args.model or "sonnet")
    ```
  - Update log line to include provider
  - Update module docstring / epilog to show `--provider claude` example

- [x] Task 4.2 — `scripts/generate_identities_parallel.py`:
  - Same `--provider` argument
  - Add `provider: str` parameter to `_generate_one()` signature
  - Same lazy-import + conditional client construction inside `_generate_one`
  - Pass `args.provider` to each `executor.submit` call

**Files Modified:**
- `scripts/generate_identity.py`
- `scripts/generate_identities_parallel.py`

**Dependencies:** Phases 2 and 3

---

### Phase 5: Documentation
**Goal:** Keep `CLAUDE.md` accurate.
**Started:** 2026-05-18
**Completed:** 2026-05-18

- [x] Task 5.1 — `CLAUDE.md` `clients/` section: add `claude_code_client.py — Claude CLI subprocess wrapper with metadata sidecar tracking` and `llm_protocol.py — LLMClient Protocol shared by GeminiClient and ClaudeCodeClient`
- [x] Task 5.2 — `CLAUDE.md` Commands section: add `--provider claude --model sonnet` example for identity generation
- [x] Task 5.3 — `CLAUDE.md` Environment & Secrets: add note that `claude` CLI must be on PATH for `--provider claude`; no extra API key needed

**Files Modified:**
- `CLAUDE.md`

**Dependencies:** Phase 4

---

## Testing Plan

No automated test suite exists; verification is manual.

### Manual Verification
- [ ] `ruff check src/` — zero errors
- [ ] Protocol import smoke: `python -c "from population_synth.clients.llm_protocol import LLMClient; print('ok')"`
- [ ] Factory smoke (no API key): `python -c "from population_synth.identity.factory_identity_generator import FactoryIdentityGenerator; print(sorted(FactoryIdentityGenerator._STRATEGY_MAP.keys()))"`
- [ ] Gemini regression (requires `GEMINI_API_KEY`): `python scripts/generate_identity.py --provider gemini --mode batch --config config/assets/identity/batch/prompt_identity_generation_002_swedish.txt --output /tmp/test_gemini.json`
- [ ] Claude smoke test (requires `claude` on PATH): `python scripts/generate_identity.py --provider claude --model sonnet --mode batch --config config/assets/identity/batch/prompt_identity_generation_002_swedish.txt --output /tmp/test_claude.json`

### Edge Cases
- [ ] Fail-fast: `claude` not on PATH → `RuntimeError` at `ClaudeCodeClient()` construction
- [ ] Non-zero exit from `claude` CLI → `RuntimeError` with stderr in message
- [ ] `system_instruction` passed to Claude configurable mode — confirm it maps to `--append-system-prompt` and does not appear inside the `messages[]` array
- [ ] `generate_identities_parallel.py --provider claude` with `--workers 4` — confirm thread safety (each worker creates its own `ClaudeCodeClient` instance)

---

## Documentation Plan

- [ ] Update `CLAUDE.md` — clients architecture section and commands (covered in Phase 5)
- [ ] No new user guide needed — behaviour documented in script `--help` and `CLAUDE.md`

---

## Rollback Plan

All changes are isolated to new files and import/type-hint edits. No data migrations, no breaking API changes.

1. Delete `src/population_synth/clients/llm_protocol.py` and `claude_code_client.py`
2. Revert the four identity-layer files to `GeminiClient` imports
3. Revert the two scripts to remove `--provider`
4. `CLAUDE.md` reverts are cosmetic only

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `claude` CLI output format changes (e.g., extra preamble text) | Low | Medium | Use `--output-format text` (default); `result.stdout.strip()` trims leading/trailing whitespace |
| Long prompts exceed subprocess stdin buffer | Low | Medium | `subprocess.run` with `input=` handles this correctly via pipe; no buffer limit for typical identity prompts |
| `claude` CLI auth expires mid-batch run | Low | High | Each worker call is independent; failed calls raise `RuntimeError` and are counted as failures by the parallel script |
| `typing.Protocol` with `**kwargs` in `generate_content` not fully checkable by mypy | Low | Low | `@runtime_checkable` covers `isinstance` checks; mypy limitation is cosmetic only |
| `--append-system-prompt` modifies Claude's default system prompt rather than replacing it | Low | Low | Desired behaviour — identity generators pass context instructions, not full system replacements |

---

## References

- Related Plan: `docs/development/plans/active/remove-sequential-identity-system.md`
- `claude` CLI flags reference: `claude --help` / Claude Code documentation
- `GeminiClient` interface: `src/population_synth/clients/gemini_client.py`
- Identity strategy entry point: `src/population_synth/identity/base_identity_generator.py:14`
