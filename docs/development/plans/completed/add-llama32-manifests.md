# Plan: Add llama3.2 (3B) Seed Manifests

**Date:** 2026-05-22
**Author:** Basil
**Status:** Completed
**Completed:** 2026-05-28 07:28
**Base Branch:** `feature/add-ollama-client`
**Branch:** `feature/add-ollama-client` (continuation — no new branch needed)

---

## Overview

Create 5 seed manifests for the Ollama llama3.2 (3B) model, mirroring the existing llama3.3 (70B) manifests (034–038). The 3B model is now available on the Ollama server, loads in ~3s (vs ~9min for 70B), and fits in VRAM. No code changes are required — the OllamaClient already accepts any model name via the manifest's `model_config.model` field.

## Problem Statement

The pipeline currently has manifests only for `llama3.3:70b-instruct-q4_K_M`. With llama3.2 (3B) now available on the Ollama server, we need matching manifests to run persona generation with the smaller, faster model across all 5 strategy variants.

## Goals

### In Scope
1. Create 5 manifest files (039–043) for llama3.2, one per strategy
2. Use validated generation settings from the pipeline fix work (`temperature: 0.7`, `max_output_tokens: 2048`)
3. Configure output directories with new seed numbers

### Out of Scope
- Code changes to OllamaClient, manifest loader, or generation scripts
- Tuning generation parameters specifically for 3B (can be done later based on output quality)
- Increasing worker count beyond 1 (Ollama serializes GPU requests regardless of model size)

## Success Criteria

- [ ] 5 manifest files created in `config/seed_manifests/`
- [ ] Single identity generation succeeds with manifest 039
- [ ] `run_metadata.json` reports model as `llama3.2`
- [ ] Small parallel batch (n=3) completes successfully

---

## Technical Design

### Approach

Clone the 5 existing llama3.3 manifests (034–038), replacing the model tag with `llama3.2` and assigning new seed numbers (039–043). All other settings remain identical — the generation config values (`temperature: 0.7`, `max_output_tokens: 2048`) were validated during the pipeline fix work and apply to any Ollama model.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Mirror all 5 strategies | Complete parity with 70B runs, enables direct comparison | More files | **Chosen** |
| Start with 1 strategy, add more later | Faster to validate | Delays full comparison data | Rejected |
| Increase workers for 3B | Faster throughput | Ollama serializes GPU; no real gain, adds complexity | Rejected |

### Architecture Changes

None. Manifest-only addition.

---

## Implementation Plan

### Phase 1: Create Manifests
**Goal:** 5 new YAML manifest files ready for use
**Started:** 2026-05-22
**Completed:** 2026-05-22

**Tasks:**
- [x] Create `identity_manifest_039_ollama_llama32_3b.yaml` — all_pick strategy
- [x] Create `identity_manifest_040_ollama_llama32_3b.yaml` — all_generate_pick strategy
- [x] Create `identity_manifest_041_ollama_llama32_3b.yaml` — all_generate_evaluate_pick strategy
- [x] Create `identity_manifest_042_ollama_llama32_3b.yaml` — all_generate_evaluate_random_pick strategy
- [x] Create `identity_manifest_043_ollama_llama32_3b.yaml` — all_pick_dag strategy

**Manifest mapping (each mirrors its 70B counterpart):**

| New | Mirrors | Strategy file | Output dir suffix |
|-----|---------|---------------|-------------------|
| 039 | 034 | `strategies/all_pick.json` | `seed_039_all_pick_llama32_3b` |
| 040 | 035 | `strategies/all_generate_pick.json` | `seed_040_all_generate_pick_llama32_3b` |
| 041 | 036 | `strategies/all_generate_evaluate_pick.json` | `seed_041_all_generate_evaluate_pick_llama32_3b` |
| 042 | 037 | `strategies/all_generate_evaluate_random_pick.json` | `seed_042_all_generate_evaluate_random_pick_llama32_3b` |
| 043 | 038 | `strategies/all_pick_dag.json` | `seed_043_all_pick_dag_llama32_3b` |

**Differences from 70B manifests:**
- `model`: `"llama3.2"` (was `"llama3.3:70b-instruct-q4_K_M"`)
- `name`: `"Ollama Llama3.2 — <strategy>"` (was `"Ollama Llama3.3 — <strategy>"`)
- `output_dir`: new seed numbers 039–043 with `_llama32_3b` suffix
- `comparison_output_dir`: matching new seed numbers

**Unchanged settings:**
- `base_url: "http://192.168.0.19:11434"`
- `temperature: 0.7`, `max_output_tokens: 2048`
- `workers: 1`, `n: 100`
- `config: simulation_config_004_swedish_generative.json`

**Files Created:**
- `config/seed_manifests/identity_manifest_039_ollama_llama32_3b.yaml`
- `config/seed_manifests/identity_manifest_040_ollama_llama32_3b.yaml`
- `config/seed_manifests/identity_manifest_041_ollama_llama32_3b.yaml`
- `config/seed_manifests/identity_manifest_042_ollama_llama32_3b.yaml`
- `config/seed_manifests/identity_manifest_043_ollama_llama32_3b.yaml`

**Dependencies:** None

---

## Testing Plan

### Manual Verification
- [ ] Run single identity: `python scripts/generate_identity.py --manifest config/seed_manifests/identity_manifest_039_ollama_llama32_3b.yaml`
- [ ] Verify `run_metadata.json` shows `"model": "llama3.2"`
- [ ] Run small parallel batch: `python scripts/generate_identities_parallel.py --manifest config/seed_manifests/identity_manifest_039_ollama_llama32_3b.yaml --n 3`
- [ ] Verify 3 persona directories created with valid `identity.json` files

### Edge Cases
- [ ] Confirm Ollama server resolves `llama3.2` tag correctly (vs `llama3.2:latest` or `llama3.2:3b`)

---

## Documentation Plan

- [ ] No documentation updates needed — CLAUDE.md already covers manifest usage and Ollama provider

---

## Rollback Plan

Delete the 5 new YAML files. No code was changed.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| 3B model produces lower-quality identities | Medium | Low | This is expected and part of the comparison study; not a blocker |
| 3B model fails JSON format compliance | Low | Medium | `format: "json"` in OllamaClient enforces JSON; validated in pipeline fix |
| Model tag `llama3.2` resolves differently across Ollama versions | Low | Low | Tag aliases (`llama3.2`, `llama3.2:latest`, `llama3.2:3b`) all resolve to the same model |

---

## References

- Mirrors: `identity_manifest_034–038_ollama_llama33_70b.yaml`
- Related plans: `docs/development/plans/active/add-ollama-client.md`, `docs/development/plans/active/fix-ollama-pipeline-failures.md`
