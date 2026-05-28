# Plan: Fix Ollama Pipeline Failures

**Date:** 2026-05-22
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/add-ollama-client`
**Branch:** `feature/add-ollama-client` (continuation — same branch)

---

## Overview

The first real Ollama run (seed_037, `all_generate_evaluate_random_pick` with `llama3.3:70b-instruct-q4_K_M`) produced 0/10 identities after ~10 hours. Multiple bugs compound: the system prompt is silently dropped, no JSON-constrained decoding, no token limit, prompts encourage unbounded candidate lists, and `generation_config` from the manifest is never wired to client constructors.

## Problem Statement

The initial OllamaClient implementation (active plan: `add-ollama-client.md`) passes basic connectivity and generation tests but fails catastrophically on real workloads. The failures are caused by a combination of API misuse (system prompt via wrong mechanism), missing Ollama-specific features (JSON format mode), a pre-existing config wiring gap (affects all providers), and prompt design issues that only surface with weaker instruction-following models.

Verified against [Ollama API docs](https://github.com/ollama/ollama/blob/main/docs/api.md) on 2026-05-22.

## Goals

### In Scope
1. Fix system prompt delivery for `/api/chat` (role-based message, not top-level key)
2. Enable Ollama's JSON-constrained decoding (`format: "json"`)
3. Wire `generation_config` from manifest to all client constructors (all providers)
4. Set sensible `max_output_tokens` and `temperature` in Ollama manifests
5. Cap candidate enumeration prompts to prevent unbounded lists
6. Fix root-category context block so models respect system instruction
7. Fix `birth_location` category description (wrong semantics)
8. Reduce weight/candidate mismatch retry overhead

### Out of Scope
- Ollama structured output via JSON schema (future enhancement — `format: "json"` is sufficient)
- Streaming support
- Changes to the `LLMClient` Protocol
- Country-specific content in category descriptions or prompts (country is set in the instruction header only)

## Success Criteria

- [ ] Ollama system instruction is delivered as `{"role": "system"}` message in the messages array
- [ ] All Ollama responses are valid JSON (no "No valid JSON found" errors)
- [ ] `generation_config` from manifest flows through to all three client constructors
- [ ] Each Ollama LLM call completes in < 2 minutes (was 5–53 min)
- [ ] Candidate lists are bounded (no "Truncating N candidates" warnings for N > 25)
- [ ] Weight/candidate mismatch retries are rare (< 1 per identity)
- [ ] A full identity (17 categories) completes in < 35 minutes via Ollama
- [ ] No country-specific text added to category descriptions or prompt templates

---

## Technical Design

### Approach

Fix the bugs in-place on the existing `feature/add-ollama-client` branch. The fixes split into three layers: client-level (OllamaClient payload), config-level (manifest YAML), and prompt-level (identity generator). Client and config fixes are Ollama-specific; prompt fixes affect all providers but are safe because they improve structure without changing semantics.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Fix in-place on current branch | Minimal overhead, fixes ship with the feature | Larger diff on the feature branch | **Chosen** |
| Separate fix branch off dev | Cleaner git history | Requires merging add-ollama-client first (incomplete) | Rejected |
| Use Ollama JSON schema (`format: {schema}`) instead of `format: "json"` | Strictest output enforcement | Requires per-prompt schema definitions, more complex | Deferred |

### Architecture Changes

No new modules or classes. Changes are to existing files only:

- `ollama_client.py` — payload construction (system prompt + JSON format)
- `generate_identity.py` / `generate_identities_parallel.py` — generation_config wiring
- `identity_generator_configurable.py` — prompt templates, context block, retry caps
- Manifest YAMLs — parameter values
- Simulation config JSON — category description

---

## Implementation Plan

### Phase 1: Critical Client Fixes
**Goal:** Fix OllamaClient API misuse and wire generation_config

**Tasks:**
- [x] Task 1.1 — Fix system prompt: replace top-level `payload["system"]` with `{"role": "system", "content": ...}` in messages array
- [x] Task 1.2 — Add `"format": "json"` to payload (always-on for Ollama)
- [x] Task 1.3 — Wire `m.generation_config` as `default_config=` to OllamaClient constructor in `generate_identity.py`
- [x] Task 1.4 — Wire `m.generation_config` as `default_config=` to OllamaClient constructor in `generate_identities_parallel.py`
- [x] Task 1.5 — Wire `m.generation_config` as `default_config=` to GeminiClient and ClaudeCodeClient constructors in both scripts (same gap, all providers)

**Files Modified:**
- `src/population_synth/clients/ollama_client.py` — Fix system prompt delivery (lines 164-170), add `format: "json"` to payload
- `scripts/generate_identity.py` — Pass `generation_config` to all client constructors
- `scripts/generate_identities_parallel.py` — Pass `generation_config` to all client constructors

**Dependencies:** None

### Phase 2: Manifest & Config Data Fixes
**Goal:** Set sensible generation parameters and fix incorrect category description

**Tasks:**
- [x] Task 2.1 — Set `max_output_tokens: 2048` and `temperature: 0.7` in all five Ollama manifests (034–038)
- [x] Task 2.2 — Fix `birth_location` description in `simulation_config_004_swedish_generative.json` from "immigration or migration status" to "Whether the persona was born domestically or abroad"

**Files Modified:**
- `config/seed_manifests/identity_manifest_034_ollama_llama33.yaml`
- `config/seed_manifests/identity_manifest_035_ollama_llama33.yaml`
- `config/seed_manifests/identity_manifest_036_ollama_llama33.yaml`
- `config/seed_manifests/identity_manifest_037_ollama_llama33.yaml`
- `config/seed_manifests/identity_manifest_038_ollama_llama33.yaml`
- `config/assets/identity/configurable/simulation_config_004_swedish_generative.json`

**Dependencies:** Phase 1 (generation_config wiring must exist for manifest values to take effect)

### Phase 3: Prompt Engineering Fixes
**Goal:** Improve prompt templates and retry logic for all providers

**Tasks:**
- [x] Task 3.1 — Cap enumerate prompt: replace "exhaustive set of ALL… do not limit or truncate" with "up to 20 of the most plausible… Prioritize the most realistic and likely options"
- [x] Task 3.2 — Lower truncation guard from 50 to 25 (two locations: `_process_generate_evaluate_pick` and `_process_generate_evaluate_random_pick`)
- [x] Task 3.3 — Fix root-category context block: return "This is the first category. Use the system instruction as context." instead of "No prior context."
- [x] Task 3.4 — Add explicit count to evaluate prompt: "these {N} candidates" and "You MUST return exactly {N} weights."
- [x] Task 3.5 — Reduce weight/candidate mismatch retry cap from 10 to 3 (two locations)

**Files Modified:**
- `src/population_synth/identity/identity_generator_configurable.py` — Enumerate prompt (lines 214-221), truncation guards (lines 337, 413), context block (lines 165-167), evaluate prompt (line 233), retry caps (lines 341, 417)

**Dependencies:** None (independent of Phase 1/2, but logically last)

---

## Testing Plan

### Manual Verification
- [ ] Run single identity via manifest 037: `python scripts/generate_identity.py --manifest config/seed_manifests/identity_manifest_037_ollama_llama33.yaml` — confirm completion in < 35 min
- [ ] Inspect log output: no "No valid JSON found", no "Truncating N candidates" for N > 25, no persistent "Weight/candidate mismatch" retries
- [ ] Inspect generated identity.json: values are contextually appropriate (regions, birth location categories consistent with system instruction)
- [ ] Run 3-identity parallel batch via manifest 037: `python scripts/generate_identities_parallel.py --manifest config/seed_manifests/identity_manifest_037_ollama_llama33.yaml --n 3` — confirm all 3 succeed

### Edge Cases
- [ ] Verify generation_config with all-null values (e.g., Gemini manifests) does not break existing provider paths
- [ ] Verify that a manifest without generation_config at all (legacy) still works

---

## Documentation Plan

- [ ] Update CLAUDE.md `clients/` section to note Ollama uses `/api/chat` with role-based system messages and `format: "json"`

---

## Rollback Plan

All changes are on the existing `feature/add-ollama-client` branch which has not been merged to dev. Rollback is `git revert` of the fix commits, or simply not merging the branch.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Capping candidates to 20 reduces output diversity | Low | Low | Top-20 covers >99% probability mass; evaluate+random_pick still samples from distribution |
| `format: "json"` causes Ollama to hang on ill-formed prompts | Low | Med | All prompts already include JSON format instructions per Ollama docs recommendation |
| Prompt changes (Phase 3) affect Gemini/Claude output quality | Low | Med | Changes are structural (cap, count, context) not semantic; existing providers follow instructions well |
| 70B Q4 model still too slow even with fixes | Med | Med | Token budget (2048) bounds worst case to ~70s/call; can switch to smaller quantization or model |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 | Small (3 files, ~20 lines changed) | None |
| Phase 2 | Small (6 files, config values only) | Phase 1 |
| Phase 3 | Small (1 file, ~15 lines changed) | None |

---

## References

- Parent plan: `docs/development/plans/active/add-ollama-client.md`
- Ollama API docs: `https://github.com/ollama/ollama/blob/main/docs/api.md`
- Analysis plan: `.claude/plans/analyse-the-following-run-snazzy-whistle.md`
