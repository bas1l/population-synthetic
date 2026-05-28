# Plan: Add OllamaClient for Self-Hosted LLM Access

**Date:** 2026-05-21
**Author:** Basil
**Status:** Completed
**Completed:** 2026-05-28 07:28
**Base Branch:** `dev`
**Branch:** `feature/add-ollama-client`

---

## Overview

Add an `OllamaClient` that satisfies the existing `LLMClient` Protocol, enabling identity generation against locally-hosted LLMs on Basil's secondary Linux server. The server runs Ollama in a Docker `ai-stack` network with the API directly accessible at `http://192.168.0.19:11434`. Only one model can be loaded at a time.

## Problem Statement

The project currently supports two LLM providers — Google Gemini (cloud API) and Claude (CLI subprocess). Both require external cloud services. A secondary Linux server is available to host open-weight models locally via Ollama, but there is no client to reach it. Adding Ollama support enables identity generation with locally-hosted models (Llama, Mistral, Qwen, etc.) at zero marginal API cost.

## Goals

### In Scope
1. New `OllamaClient` class implementing the `LLMClient` Protocol via Ollama's native `POST /api/chat` endpoint
2. Manifest + CLI + env-var configuration for the server URL (`base_url`)
3. Full wiring into both generation scripts (`generate_identity.py`, `generate_identities_parallel.py`)
4. Retry with exponential backoff matching `ClaudeCodeClient` conventions
5. Fail-fast server validation at construction time

### Out of Scope
- Open WebUI integration (GUI layer, not involved)
- Automatic model pulling (`ollama pull`) — user manages models on the server
- Multi-turn conversation state — each `generate_content` call is independent
- Streaming responses — `stream: false` matches existing client patterns
- Changes to the `LLMClient` Protocol itself

## Success Criteria

- [ ] `OllamaClient` satisfies `LLMClient` Protocol (`isinstance` check passes)
- [ ] `--provider ollama` works in both `generate_identity.py` and `generate_identities_parallel.py`
- [ ] Manifest with `provider: "ollama"` and `base_url` loads and validates correctly
- [ ] `system_instruction` kwarg maps correctly to a `{"role": "system"}` message in the `/api/chat` messages array
- [ ] Generation config params (`temperature`, `top_p`, `top_k`, `max_output_tokens`) pass through correctly
- [ ] Unreachable server raises `ConnectionError` at construction (fail-fast)
- [ ] Non-existent model returns a clear error message suggesting `ollama pull`
- [ ] `run_metadata.json` records provider, model, and base_url correctly

---

## Technical Design

### Approach

HTTP client using `requests` (already a dependency) against Ollama's native REST API. No new dependencies. Follows the same structural patterns as `GeminiClient` and `ClaudeCodeClient`: constructor-injected model name and config, stateful metadata/history tracking, and a `generate_content` method that returns plain text.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| `requests` + Ollama native `/api/chat` | No new deps, Ollama-specific, simple | Tied to Ollama's API format | **Chosen** |
| `openai` SDK + Ollama `/v1/chat/completions` | Standard protocol, portable to vLLM/llama.cpp | New dependency, naming confusion | Rejected |
| Open WebUI API | Single entry point for all server features | Extra hop, more fragile, heavier coupling | Rejected |

### Architecture Changes

**New file:**
```
src/population_synth/clients/
├── llm_protocol.py          # Unchanged
├── gemini_client.py          # Unchanged
├── claude_code_client.py     # Unchanged
└── ollama_client.py          # NEW — OllamaClient class
```

**Modified files:**
- `manifest_loader.py` — add `"ollama"` to `VALID_PROVIDERS`, add `base_url` field to `ManifestConfig`
- `generate_identity.py` — add `--base-url` arg, `ollama` provider branch
- `generate_identities_parallel.py` — same CLI/wiring changes
- `template_identity_manifest.yaml` — document `ollama` provider and `base_url`

### Ollama API Mapping

`generate_content(prompt, **kwargs)` maps to `POST /api/chat`:

```json
{
  "model": "<target_model>",
  "messages": [{"role": "user", "content": "<prompt>"}],
  "system": "<system_instruction extracted from kwargs>",
  "stream": false,
  "options": { "temperature": 0.7, "top_p": 0.9, "num_predict": 4096 }
}
```

Parameter renames: `max_output_tokens` -> `num_predict` (Ollama's equivalent).

### URL Resolution Precedence

1. Explicit `base_url` constructor arg (from manifest `model_config.base_url` or CLI `--base-url`)
2. `OLLAMA_BASE_URL` environment variable
3. Default: `http://192.168.0.19:11434`

---

## Implementation Plan

### Phase 1: Core Client
**Goal:** Implement `OllamaClient` satisfying the `LLMClient` Protocol

- [x] Task 1.1 — Create `ollama_client.py` with class skeleton and constructor (URL resolution, `requests.Session`, fail-fast `GET /api/tags` validation)
- [x] Task 1.2 — Implement `generate_content()` with Ollama API mapping, `system_instruction` extraction, options building (`max_output_tokens` -> `num_predict`), metadata recording
- [x] Task 1.3 — Implement retry logic with exponential backoff + jitter (3 attempts, 2-30s delay); 4xx fail immediately, 5xx/connection/timeout retry
- [x] Task 1.4 — Implement remaining protocol methods (`update_config`, `update_default_model`, `get_current_configuration`, `clear_history`, `last_metadata`, `history`)
- [x] Task 1.5 — Implement `close()`, `__del__()`, and `model_name` property (aliases `default_model_name` for script compatibility)

**Files Modified:**
- `src/population_synth/clients/ollama_client.py` — New file, full client class

**Dependencies:** None

### Phase 2: Manifest & Config Infrastructure
**Goal:** Enable `provider: "ollama"` in manifests and add `base_url` field

- [ ] Task 2.1 — Add `"ollama"` to `VALID_PROVIDERS` in `manifest_loader.py` (line 13)
- [ ] Task 2.2 — Add `base_url: str | None` field to `ManifestConfig` dataclass
- [ ] Task 2.3 — Extract `base_url` from `model_cfg` in `load_manifest()` and pass to constructor
- [ ] Task 2.4 — Update `template_identity_manifest.yaml` to document `ollama` provider and `base_url`

**Files Modified:**
- `src/population_synth/identity/manifest_loader.py` — Add provider, dataclass field, extraction logic
- `config/seed_manifests/template_identity_manifest.yaml` — Document new provider and field

**Dependencies:** None (parallel with Phase 1)

### Phase 3: Script Wiring
**Goal:** Wire `--provider ollama` and `--base-url` into both generation scripts

- [x] Task 3.1 — `generate_identity.py`: add `"ollama"` to `--provider` choices, add `--base-url` arg, wire manifest `base_url`, add `elif args.provider == "ollama"` client instantiation branch, update else-clause error message
- [x] Task 3.2 — `generate_identities_parallel.py`: same changes as 3.1 plus: add `base_url` param to `_generate_one()` signature, update model default logic for 3 providers, pass `base_url` through `executor.submit`, register OllamaClient in `_active_clients` for cleanup

**Files Modified:**
- `scripts/generate_identity.py` — Provider choice, `--base-url` arg, client instantiation
- `scripts/generate_identities_parallel.py` — Same + `_generate_one` signature, model defaults, cleanup

**Dependencies:** Phase 1 (client exists), Phase 2 (manifest loads)

---

## Testing Plan

### Manual Verification
- [ ] Construct `OllamaClient` with valid server URL — passes without error
- [ ] Construct `OllamaClient` with unreachable URL — raises `ConnectionError`
- [ ] `isinstance(client, LLMClient)` returns `True`
- [ ] Single identity via CLI: `python scripts/generate_identity.py --provider ollama --model llama3.1 --base-url http://192.168.0.19:11434 --mode configurable --config <config> --strategy <strategy>`
- [ ] Single identity via manifest with `provider: "ollama"` and `base_url`
- [ ] Parallel generation via manifest: `--n 5 --workers 2`
- [ ] Output `identity.json` is valid JSON with expected schema
- [ ] `run_metadata.json` shows `provider: "ollama"` and correct model/base_url
- [ ] Non-existent model name returns clear error suggesting `ollama pull <model>`

### Edge Cases
- [ ] Server goes down mid-generation — retry logic kicks in, fails gracefully after max retries
- [ ] Empty response from Ollama — raises `RuntimeError`, not silent failure
- [ ] `generation_config` with `max_output_tokens` — correctly mapped to `num_predict` in Ollama options

---

## Documentation Plan

- [ ] Update `CLAUDE.md` — add `OllamaClient` to clients section, add `--provider ollama` to commands, add `OLLAMA_BASE_URL` to environment section
- [ ] Update manifest template with `ollama` documentation (covered in Phase 2)

---

## Rollback Plan

1. Revert the feature branch — no existing code is modified in a breaking way
2. Remove `ollama_client.py` — isolated new file
3. Revert `manifest_loader.py` changes — `VALID_PROVIDERS` and `ManifestConfig` go back to 2-provider state
4. No data migrations, no breaking changes to existing manifests (new field is optional with `None` default)

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Ollama server unreachable from dev machine | Low | Med | Fail-fast at construction; clear error message with URL |
| Model not pulled on server | Med | Low | 404 detection with message: "Run `ollama pull <model>`" |
| Ollama response format changes | Low | Med | Pin to known `/api/chat` contract; version-check possible via `/api/version` |
| Single-GPU bottleneck in parallel mode | Med | Low | User controls `workers` count in manifest; Ollama queues server-side |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1: Core Client | ~150 lines | None |
| Phase 2: Manifest & Config | ~20 lines changed | None |
| Phase 3: Script Wiring | ~40 lines changed | Phase 1 + 2 |

---

## References

- Related Plan: `docs/development/plans/active/claude-code-client.md` — established the LLMClient Protocol pattern
- Ollama API docs: `/api/chat` endpoint (native REST)
- Server: `http://192.168.0.19:11434` (Docker ai-stack, Open WebUI on `:3000`)
