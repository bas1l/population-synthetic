# Plan: OpenAI-Compatible Client for European LLM Providers

**Date:** 2026-05-29
**Author:** Basil
**Status:** Completed
**Completed:** 2026-06-01 12:55
**Base Branch:** `feature/ollama-structured-output`
**Branch:** `feature/openai-compat-european-providers`

---

## Overview

Add an `OpenAICompatClient` that wraps the `openai` Python SDK with a configurable `base_url` and API key, enabling any OpenAI-compatible European provider to be used as a drop-in replacement for Gemini or Claude. The key finding from research is that the major production-ready European providers (Mistral, Aleph Alpha/Pharia, OVHcloud AI Endpoints, Regolo.ai) all expose a standard `/v1/chat/completions` endpoint — one client covers all of them.

## Problem Statement

The current LLM clients are all tied to US-based or US-controlled infrastructure (Google Gemini, Anthropic Claude CLI, Ollama self-hosted). For research contexts requiring EU data residency, GDPR compliance, or EU AI Act alignment — particularly relevant given the ISTAT/Italy population work — there is no path to European providers without writing provider-specific client code each time.

---

## Goals

### In Scope
1. `OpenAICompatClient` implementing the existing `LLMClient` Protocol
2. Manifest support for `provider: "openai_compat"` with `base_url` and `api_key_env_var` fields
3. Provider branch in `generate_identity.py` and `generate_identities_parallel.py`
4. Seed manifests for the three priority providers: Mistral, OVHcloud, Regolo.ai

### Out of Scope
- Native `mistralai` SDK integration (OpenAI-compat path is sufficient)
- Aleph Alpha enterprise workflow features (just the inference API)
- Nordference (API details not publicly confirmed yet)
- EuroLLM / OpenGPT-X (research consortia, no production API)
- Streaming output (all existing clients are non-streaming)

---

## Success Criteria

- [ ] `OpenAICompatClient` satisfies `isinstance(client, LLMClient)` Protocol check
- [ ] A single identity can be generated end-to-end using `provider: "openai_compat"` with `mistral-large-latest`
- [ ] `llm_interactions.jsonl` is populated with prompts and parsed responses
- [ ] Switching providers requires only a manifest YAML change — no code changes
- [ ] `response_schema` is forwarded as `response_format` when passed (graceful fallback if provider rejects it)
- [ ] Exponential-backoff retry matches the `OllamaClient` pattern (3 attempts, jitter, fatal 4xx non-retry)

---

## Technical Design

### Approach

A single `OpenAICompatClient` class uses `openai.OpenAI(base_url=..., api_key=...)` and calls `chat.completions.create()`. The constructor reads the API key from a named environment variable (configurable per manifest), so no credentials are hardcoded. The Protocol contract is the same as all other clients — `generate_content(prompt, **kwargs) -> str`.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| One generic `OpenAICompatClient` | One file covers all providers; minimal duplication | Slightly less precise error messages per provider | **Chosen** |
| Per-provider clients (MistralClient, RegoloCLient, …) | Provider-specific features possible | Massive duplication; no real benefit at inference layer | Rejected |
| Native `mistralai` SDK only | Mistral-specific features (e.g., function calling details) | Only covers Mistral; others need separate clients | Rejected |

### Architecture Changes

New file:
```
src/population_synth/clients/openai_compat_client.py   ← new
```

Modified files:
```
src/population_synth/identity/manifest_loader.py       ← add base_url + api_key_env_var
scripts/generate_identity.py                           ← add openai_compat branch
scripts/generate_identities_parallel.py               ← add openai_compat branch
pyproject.toml                                         ← add openai dependency
config/seed_manifests/                                 ← new manifests (3 files)
```

### Client interface sketch

```python
class OpenAICompatClient:
    def __init__(
        self,
        model_name: str,
        base_url: str,
        api_key_env_var: str = "OPENAI_API_KEY",
        default_config: dict | None = None,
        max_retries: int = 3,
        base_delay: float = 2.0,
        max_delay: float = 30.0,
        timeout: int = 120,
    ): ...

    def generate_content(self, prompt: str, **kwargs: Any) -> str:
        # kwargs: system_instruction, response_schema, model
        # maps system_instruction → messages[0] role=system
        # maps response_schema → response_format (if use_structured_output)
        # retry: transient errors backoff, 4xx fatal raise
        ...
```

`response_schema` handling: pass as `response_format={"type": "json_schema", "json_schema": {"name": "output", "schema": response_schema, "strict": True}}` when provided. Catch `openai.BadRequestError` (422) on schema rejection and fall back to plain JSON mode (`response_format={"type": "json_object"}`).

### Manifest additions

```yaml
model_config:
  provider: "openai_compat"
  model: "mistral-large-latest"
  base_url: "https://api.mistral.ai/v1"
  api_key_env_var: "MISTRAL_API_KEY"   # env var name, not the value
```

`ManifestConfig` dataclass gains two optional fields: `base_url: str | None` and `api_key_env_var: str | None`.

---

## Implementation Plan

### Phase 1: Client + dependency
**Goal:** Working `OpenAICompatClient` that satisfies the Protocol
**Started:** 2026-05-29
**Completed:** 2026-05-29

- [x] Add `openai` to `pyproject.toml` dependencies (not optional — it's lightweight)
- [x] Write `src/population_synth/clients/openai_compat_client.py` following `OllamaClient` structure
  - Constructor: validate env var is set, instantiate `openai.OpenAI(base_url, api_key)`
  - `generate_content()`: build messages list, call `chat.completions.create()`, retry loop
  - Map `system_instruction` → system message
  - Map `response_schema` → `response_format` with BadRequestError fallback
  - Full metadata tracking (`last_metadata`, `history` properties)
  - All Protocol methods: `update_config`, `update_default_model`, `get_current_configuration`, `clear_history`

**Files Modified:**
- `pyproject.toml` — add `openai>=1.0`
- `src/population_synth/clients/openai_compat_client.py` — new file

**Dependencies:** None

### Phase 2: Manifest + script wiring
**Goal:** End-to-end generation works from a manifest
**Started:** 2026-05-29
**Completed:** 2026-05-29

- [x] Add `base_url: str | None` and `api_key_env_var: str | None` to `ManifestConfig` in `manifest_loader.py`
- [x] Add `openai_compat` branch to `scripts/generate_identity.py`
- [x] Add `openai_compat` branch to `scripts/generate_identities_parallel.py`
- [x] Add CLI args `--base-url` and `--api-key-env` to both scripts (for direct invocation without manifest)

**Files Modified:**
- `src/population_synth/identity/manifest_loader.py` — extend `ManifestConfig` and loader
- `scripts/generate_identity.py` — provider branch
- `scripts/generate_identities_parallel.py` — provider branch

**Dependencies:** Phase 1

### Phase 3: Seed manifests
**Goal:** Ready-to-use manifests for the three priority providers
**Started:** 2026-05-29
**Completed:** 2026-05-29

- [x] `config/seed_manifests/identity_manifest_mistral_large_all_pick.yaml` — Mistral, `mistral-large-latest`
- [x] `config/seed_manifests/identity_manifest_ovhcloud_llama_all_pick.yaml` — OVHcloud, e.g. `Meta-Llama-3.1-70B-Instruct` (free tier)
- [x] `config/seed_manifests/identity_manifest_regolo_llama_all_pick.yaml` — Regolo.ai, open-source model

Each manifest mirrors the structure of existing ones (strategy, config, parallel params) with the `openai_compat` provider block.

**Files Modified:**
- `config/seed_manifests/identity_manifest_mistral_large_all_pick.yaml` — new
- `config/seed_manifests/identity_manifest_ovhcloud_llama_all_pick.yaml` — new
- `config/seed_manifests/identity_manifest_regolo_llama_all_pick.yaml` — new

**Dependencies:** Phase 2

---

## Testing Plan

### Manual Verification
- [ ] Single identity generation with Mistral: `python scripts/generate_identity.py --manifest config/seed_manifests/identity_manifest_mistral_large_all_pick.yaml`
- [ ] Verify `identity.json` is structurally complete (all expected categories present)
- [ ] Verify `llm_interactions.jsonl` records prompts + parsed values
- [ ] Verify switching `base_url` to OVHcloud endpoint produces equivalent output
- [ ] Verify missing `MISTRAL_API_KEY` raises a clear `ValueError` at construction, not silently at first call

### Edge Cases
- [ ] `response_schema` forwarded to a provider that rejects it (e.g. OVHcloud free tier may not support strict JSON schema) — confirm fallback to `json_object` mode and generation still completes
- [ ] Network timeout mid-generation — confirm retry fires and exponential backoff matches `OllamaClient` behaviour
- [ ] 401 Unauthorized (wrong API key) — confirm fatal raise, no retry

---

## Documentation Plan

- [ ] Update `CLAUDE.md`: add `openai_compat` to the provider list under "Commands" and "Clients" sections
- [ ] Add `api_key_env_var` and `base_url` to the manifest template comment block

---

## Rollback Plan

All changes are additive (new file, new manifest fields, new manifest YAMLs, new provider branch). Rolling back is a clean revert of the feature branch — no existing client code is modified.

1. Delete `src/population_synth/clients/openai_compat_client.py`
2. Revert manifest loader to drop `base_url` / `api_key_env_var` fields
3. Remove provider branches from both generate scripts
4. Remove seed manifests

No data migrations, no schema changes to existing outputs.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Provider rejects `response_format` JSON Schema (strict mode) | Medium | Medium | Catch `BadRequestError`, fall back to `json_object` mode; log warning |
| OVHcloud free-tier rate limits interfere with parallel runs | Medium | Low | Manifests start with `workers: 1`; user can tune up |
| Regolo.ai / OVHcloud base URLs change | Low | Low | URLs are in manifest YAMLs, not code — trivial to update |
| `openai` SDK version incompatibility with existing deps | Low | Medium | Pin `openai>=1.0,<2` in `pyproject.toml`; test in popsynth conda env |

---

## References

- Research summary: `C:\Users\basil\.claude\plans\analyse-how-claude-and-enchanted-gadget.md`
- Existing Ollama client (closest analogue): `src/population_synth/clients/ollama_client.py`
- LLM Protocol: `src/population_synth/clients/llm_protocol.py`
- Manifest loader: `src/population_synth/identity/manifest_loader.py`

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- config/seed_manifests/identity_manifest_mistral_large_all_pick.yaml
- config/seed_manifests/identity_manifest_ovhcloud_llama_all_pick.yaml
- config/seed_manifests/identity_manifest_regolo_llama_all_pick.yaml
- docs/development/plans/active/openai-compat-european-providers.md
- pyproject.toml
- scripts/generate_identities_parallel.py
- scripts/generate_identity.py
- src/population_synth/clients/openai_compat_client.py
- src/population_synth/identity/manifest_loader.py
