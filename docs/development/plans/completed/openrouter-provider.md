# Plan: OpenRouter Provider

**Date:** 2026-07-06
**Author:** Basil
**Status:** Completed
**Completed:** 2026-07-13 14:44
**Base Branch:** `dev`
**Branch:** `feature/openrouter-provider`

---

## Overview

Add `openrouter` as a first-class LLM provider for identity generation, giving the
harness access to OpenRouter's aggregated model catalog (hundreds of frontier and
open-weight models behind one OpenAI-compatible endpoint). The wire protocol is
already implemented by `OpenAICompatClient`; this change registers a dedicated
provider name so axis files need only a model slug, provenance metadata records
`provider="openrouter"`, and the endpoint + key-env are supplied as structural
defaults.

## Problem Statement

The generation pipeline currently supports four providers — `gemini`, `claude`,
`ollama`, `openai_compat` — hardcoded in the `--provider` choices, the dispatch
chains of both generation scripts, and `manifest_loader.VALID_PROVIDERS`. To broaden
the benchmark's model coverage (a core goal of the fidelity study), we want a wide
set of models without standing up a client per vendor. OpenRouter exposes every model
through a single OpenAI-compatible `/v1/chat/completions` endpoint, so the existing
`OpenAICompatClient` already speaks its protocol. What is missing is a clean,
first-class integration: today OpenRouter would have to be shoehorned through
`openai_compat` with `base_url` + `api_key_env_var` repeated in every axis file, and
every run would be tagged the generic `provider="openai_compat"` — muddying
`run_analytics` and `model_ranking` labels when mixed with any future Mistral/OVH combos.

## Goals

### In Scope
1. First-class `openrouter` provider accepted by both generation scripts and the manifest loader.
2. Sensible structural defaults so axis files carry only the model slug: `base_url` →
   `https://openrouter.ai/api/v1`, api-key env → `OPENROUTER_API_KEY`.
3. Distinct provenance: per-call metadata records `provider="openrouter"` (not `openai_compat`).
4. A seed set of seven `openrouter_*` model axis YAMLs (frontier + open-weight, incl. GLM 5.2).
5. Docs updated (env var, provider list).

### Out of Scope
- New client class — `OpenAICompatClient` is reused, not duplicated.
- OpenRouter-specific routing controls (provider preferences, fallbacks, `:nitro`/`:floor` suffixes, transforms).
- Exhaustive model catalog — only a representative seed set; users add more axis files as needed.
- GUI enum changes — the Flow Runner discovers providers via axis YAML (`discover_axis_values`), so no GUI code changes are required.
- Cost/usage tracking beyond the token counts already captured in call metadata.

## Success Criteria

- [ ] `--provider openrouter` is accepted by `generate_identities_parallel.py` and `generate_identity.py`.
- [ ] `compose_manifest`/`load_manifest` accept `provider: openrouter` and resolve the default base_url + api-key env when omitted from the axis file.
- [ ] A run with an `openrouter_*` model produces personas and per-call metadata with `provider="openrouter"`, real `prompt_tokens`/`completion_tokens`, and `base_url=https://openrouter.ai/api/v1`.
- [ ] Missing `OPENROUTER_API_KEY` fails loudly at client construction (existing `ValueError` path), consistent with the fail-fast rule.
- [ ] Existing `openai_compat` behavior is byte-for-byte unchanged (metadata still tagged `openai_compat`, no headers sent).
- [ ] Seven `openrouter_*` axis files load via `discover_axis_values` and compose without error.

---

## Technical Design

### Approach

Route `openrouter` to the existing `OpenAICompatClient`, extended with two
backward-compatible optional kwargs:

- `provider_tag: str = "openai_compat"` — replaces the currently hardcoded
  `"provider": "openai_compat"` in the call-metadata dict, so OpenRouter runs
  self-identify.
- `default_headers: dict | None = None` — forwarded to the `openai.OpenAI(...)`
  constructor for OpenRouter's optional `HTTP-Referer` / `X-Title` attribution headers.

Both default to today's behavior, so the `openai_compat` provider is unaffected.

The dispatch branch in each script supplies OpenRouter's endpoint and key-env as
**structural constants** (the same category as the existing per-provider default model
names and `OllamaClient`'s default base_url — not a probability/config value covered by
the no-hardcoded-config rule), so axis files need only the model slug:

```python
elif provider == "openrouter":
    from population_synthetic.clients.openai_compat_client import OpenAICompatClient
    client = OpenAICompatClient(
        model_name=model,
        base_url=base_url or "https://openrouter.ai/api/v1",
        api_key_env_var=api_key_env_var or "OPENROUTER_API_KEY",
        default_config=cfg,
        provider_tag="openrouter",
        default_headers={"X-Title": "population-synthetic"},  # optional; see risk note
    )
```

An axis file may still override `base_url`/`api_key_env_var` explicitly (the manifest
loader already reads both), so the defaults are a convenience, not a lock-in.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| First-class `openrouter` provider routed to `OpenAICompatClient` | Clean provenance (`provider=openrouter`); default base_url/key so axis files carry only the slug; room for OR-specific headers | ~30 lines across 4 files; two scripts to keep in sync | **Chosen** |
| Reuse `openai_compat`, config only (zero code) | No code change; works today | Every axis file repeats base_url + api_key_env_var; all runs tagged `openai_compat`, mixing OR with any future Mistral/OVH combos in analytics/ranking labels | Rejected |
| New dedicated `OpenRouterClient` subclass | Encapsulates OR specifics | Duplicates the retry/JSON-schema-fallback logic already in `OpenAICompatClient`; more surface to maintain | Rejected |

### Architecture Changes

No new modules. One client parametrized; the provider registered in three call sites;
seven config files added.

```
src/population_synthetic/clients/openai_compat_client.py   (+2 kwargs, provider_tag in metadata, default_headers → OpenAI ctor)
src/population_synthetic/generators/synthetic/manifest_loader.py   (VALID_PROVIDERS += "openrouter")
scripts/generate/generate_identities_parallel.py   (choices, dispatch branch, default-model, help text)
scripts/generate/generate_identity.py              (choices, dispatch branch, default-model, help text)
config/synthetic/axes/models/openrouter_*.yaml     (7 new files)
```

---

## Implementation Plan

### Phase 1: Client parametrization
**Goal:** `OpenAICompatClient` can carry a provider tag and default headers without changing existing behavior.
**Started:** 2026-07-06
**Completed:** 2026-07-06

- [x] Task 1.1 — Add `provider_tag: str = "openai_compat"` and `default_headers: dict[str, Any] | None = None` params to `__init__`.
- [x] Task 1.2 — Store `provider_tag`; pass `default_headers=default_headers` into `openai.OpenAI(...)`.
- [x] Task 1.3 — Use `self._provider_tag` for the `"provider"` field in the call-metadata dict (replacing the hardcoded literal).

**Files Modified:**
- `src/population_synthetic/clients/openai_compat_client.py` — two new kwargs; metadata `provider` sourced from the tag; headers forwarded to the SDK client.

**Dependencies:** None

### Phase 2: Register the `openrouter` provider
**Goal:** Both generation entry points and the loader accept and dispatch `openrouter`.
**Started:** 2026-07-06
**Completed:** 2026-07-06

- [x] Task 2.1 — `manifest_loader.py`: add `"openrouter"` to `VALID_PROVIDERS`.
- [x] Task 2.2 — `generate_identities_parallel.py`: add `"openrouter"` to `--provider choices`; add the dispatch branch (default base_url + `OPENROUTER_API_KEY`, `provider_tag`, headers); add an `openrouter` default-model entry; update `--provider`/`--model` help text.
- [x] Task 2.3 — `generate_identity.py`: mirror the same three edits (choices, dispatch branch, default model) so the single-identity path stays in sync.

**Files Modified:**
- `src/population_synthetic/generators/synthetic/manifest_loader.py` — `VALID_PROVIDERS`.
- `scripts/generate/generate_identities_parallel.py` — choices, dispatch, default model, help.
- `scripts/generate/generate_identity.py` — choices, dispatch, default model, help.

**Dependencies:** Phase 1

### Phase 3: Seed model axis files
**Goal:** A representative OpenRouter model set is selectable via `--model-id`.
**Started:** 2026-07-06
**Completed:** 2026-07-06

- [x] Task 3.1 — Re-confirm each slug against `https://openrouter.ai/api/v1/models` at build time (slugs drift).
- [x] Task 3.2 — Create seven `config/synthetic/axes/models/openrouter_*.yaml`, mirroring the existing axis schema (`provider: openrouter`, null `generation_config`, `parallel.workers: 4`), omitting `base_url`/`api_key_env_var` to exercise the defaults.

Seed set (verified against the live catalog on 2026-07-06):

| File | `model` slug | Class |
|------|-------------|-------|
| `openrouter_gpt55.yaml` | `openai/gpt-5.5` | frontier / closed |
| `openrouter_claude_sonnet5.yaml` | `anthropic/claude-sonnet-5` | frontier / closed |
| `openrouter_gemini_flash.yaml` | `google/gemini-3.5-flash` | frontier / closed |
| `openrouter_deepseek_v4.yaml` | `deepseek/deepseek-v4-pro` | open-weight |
| `openrouter_qwen37_max.yaml` | `qwen/qwen3.7-max` | open-weight¹ |
| `openrouter_mistral_medium.yaml` | `mistralai/mistral-medium-3.5` | open-weight |
| `openrouter_glm_52.yaml` | `z-ai/glm-5.2` | open-weight (GLM 5.2) |

¹ Qwen "Max" tier is API-only; keep the slug but the open/closed label is a labeling
concern for `model_ranking`, not a blocker here.

**Files Modified:**
- `config/synthetic/axes/models/openrouter_*.yaml` — 7 new files.

**Dependencies:** Phase 2

### Phase 4: Documentation
**Goal:** Env var and provider list reflect the new option.
**Started:** 2026-07-06
**Completed:** 2026-07-06

- [x] Task 4.1 — `CLAUDE.md` "Environment & Secrets": add `OPENROUTER_API_KEY` required for `--provider openrouter`.
- [x] Task 4.2 — `docs/architecture/commands.md` and `docs/architecture/axis-composition.md`: list `openrouter` alongside the other providers.

**Files Modified:**
- `CLAUDE.md` — env var.
- `docs/architecture/commands.md`, `docs/architecture/axis-composition.md` — provider mentions.

**Dependencies:** Phase 2

---

## Testing Plan

### Unit Tests
- [ ] `OpenAICompatClient(..., provider_tag="openrouter")` — metadata `provider` field equals `"openrouter"`.
- [ ] `OpenAICompatClient(...)` with no `provider_tag` — metadata `provider` still `"openai_compat"` (regression guard).
- [ ] `default_headers` forwarded to the SDK client (assert on the constructed `openai.OpenAI` kwargs, or a thin injection point).
- [ ] `load_manifest` / `compose_manifest` accept `provider: openrouter`; reject an unknown provider as before.

### Integration Tests
- [ ] `compose_manifest("openrouter_glm_52", <strategy>, "swedish")` returns a `ManifestConfig` with `provider="openrouter"`, `model="z-ai/glm-5.2"`, and `base_url`/`api_key_env_var` = None (defaults applied later in dispatch).
- [ ] Dispatch branch constructs an `OpenAICompatClient` with the default base_url + `OPENROUTER_API_KEY` when the manifest omits them.

### Manual Verification
- [ ] With `OPENROUTER_API_KEY` set: `generate_identities_parallel.py --model-id openrouter_glm_52 --strategy-id all_pick --country-id swedish --n 2 --workers 2` produces two personas.
- [ ] Inspect `llm_interactions.jsonl` / call metadata: `provider="openrouter"`, `base_url` correct, non-null token counts.
- [ ] `run_metadata.json` records `model_config.provider == "openrouter"`.
- [ ] GUI Flow Runner lists the new `openrouter_*` models in the model axis (auto-discovery, no code change).

### Edge Cases
- [ ] `OPENROUTER_API_KEY` unset → `ValueError` at construction (fail-fast).
- [ ] A model whose underlying provider rejects strict `json_schema` → existing `json_object` fallback path engages (already handled in `OpenAICompatClient`).
- [ ] Axis file that explicitly overrides `base_url`/`api_key_env_var` → override wins over the defaults.

---

## Documentation Plan

- [x] Update `CLAUDE.md` Environment & Secrets with `OPENROUTER_API_KEY`.
- [x] Update `docs/architecture/commands.md` provider list.
- [x] Update `docs/architecture/axis-composition.md` provider list.
- [ ] Inline: brief comment in each dispatch branch noting the endpoint/key are structural defaults.

---

## Rollback Plan

Change is additive and isolated; no data migration.

1. **Before merge:** revert the feature branch; `openai_compat` and the other three providers are untouched, so nothing regresses.
2. **Data considerations:** none — no schema or on-disk format changes. Any personas already generated via `openrouter` remain valid identity JSON.
3. **Rollback procedure:** delete the seven `openrouter_*.yaml` files and revert the four source edits (client kwargs, `VALID_PROVIDERS`, two script dispatch chains). `provider_tag`/`default_headers` default back to current behavior even if the client change is left in place.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Two dispatch chains drift (edit one script, forget the other) | Med | Med | Phase 2 edits both in the same change; add the sync as a review checklist item; consider a follow-up to factor dispatch into a shared helper (out of scope here). |
| OpenRouter model slugs change / seed slugs go stale | Med | Low | Task 3.1 re-confirms every slug against the live `/models` endpoint at build time; stale slugs fail fast with a clear 404/`model_limitation` error. |
| Hardcoded default base_url seen as violating the no-hardcoded-config rule | Low | Low | Treated as a structural constant (like existing default model names / Ollama default URL); axis files may override; documented inline. |
| `X-Title` attribution header leaks the app name to OpenRouter public app rankings | Low | Low | Header is optional; final call (keep `"population-synthetic"` vs omit headers) deferred to user before implementation. |
| Underlying model lacks strict JSON-schema support | Med | Low | Existing `json_object` fallback in `OpenAICompatClient` already handles this. |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 — Client params | ~20 min | None |
| Phase 2 — Provider registration | ~30 min | Phase 1 |
| Phase 3 — Axis files | ~20 min | Phase 2 |
| Phase 4 — Docs | ~15 min | Phase 2 |

---

## References

- Related client: `src/population_synthetic/clients/openai_compat_client.py`
- Provider dispatch: `scripts/generate/generate_identities_parallel.py`, `scripts/generate/generate_identity.py`
- Manifest/axis loader: `src/population_synthetic/generators/synthetic/manifest_loader.py`
- Axis schema reference: `config/synthetic/axes/models/*.yaml`
- OpenRouter model catalog: `https://openrouter.ai/api/v1/models`

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- CLAUDE.md
- config/synthetic/axes/models/openrouter_claude_sonnet5.yaml
- config/synthetic/axes/models/openrouter_deepseek_v4.yaml
- config/synthetic/axes/models/openrouter_gemini_flash.yaml
- config/synthetic/axes/models/openrouter_glm_52.yaml
- config/synthetic/axes/models/openrouter_gpt55.yaml
- config/synthetic/axes/models/openrouter_mistral_medium.yaml
- config/synthetic/axes/models/openrouter_qwen37_max.yaml
- docs/architecture/axis-composition.md
- docs/architecture/commands.md
- docs/development/plans/active/openrouter-provider.md
- scripts/generate/generate_identities_parallel.py
- scripts/generate/generate_identity.py
- src/population_synthetic/clients/openai_compat_client.py
- src/population_synthetic/generators/synthetic/manifest_loader.py

---

## Open Decisions (resolve before `/plan-implement`)

1. **`X-Title` header** — send `{"X-Title": "population-synthetic"}` for tidy attribution in the OpenRouter dashboard, or omit headers entirely to stay anonymous. (Cosmetic; no functional effect.)
2. **Seed set** — confirm the seven models above, or adjust (e.g. add a Llama slug once verified, drop the Qwen "Max" closed-tier entry).
