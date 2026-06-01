# Plan: Schema-Constrained Output for the Ollama Path

**Date:** 2026-05-28
**Author:** Basil
**Status:** Completed
**Completed:** 2026-06-01 12:55
**Base Branch:** `dev`
**Branch:** `feature/ollama-structured-output`

---

## Overview

Add opt-in JSON-Schema–constrained decoding to the Ollama client so weak local models are forced to emit the exact output shape each strategy call expects (`{"value": …}`, `{"candidates": […]}`, `{"weights": […]}`). This eliminates the dominant failure mode for small models — valid JSON of the wrong shape — without changing behaviour for existing runs (default off).

## Problem Statement

The `fix-ollama-pipeline-failures` work added `format: "json"`, which enforces JSON *syntax* but not *schema*. Weak models still return well-shaped-but-wrong JSON, raising `KeyError: <expected_key>` and aborting the persona. The Lucie-7B / Swedish / `all_pick` run quantified it: **16/100 personas completed (16% yield)**, with **625/1443 individual calls (43%) malformed** — wrong key (346), empty object (258), list (19), unparseable (2). Ollama supports passing a full JSON Schema to `format`, which switches on grammar-constrained decoding and makes wrong shapes impossible. This was explicitly deferred in `fix-ollama-pipeline-failures.md`; this plan picks it up.

A probe (`scripts/_throwaway_lucie_schema_probe.py`, run 2026-05-28 against `192.168.0.19`) validated the fix empirically: shape validity rose **5/10 → 10/10**, and — critically — at `temperature 0.7` variety was preserved (8 distinct values in 10 calls) whereas `temperature 0` collapsed to 1. Grammar masks invalid tokens, then the sampler picks among valid ones, so **schema fixes shape and temperature controls variety, independently.**

## Goals

### In Scope
1. `OllamaClient.generate_content` accepts an optional `response_schema` and uses it as the request `format` (falling back to `"json"` when absent).
2. The configurable generator builds the correct JSON Schema per call type and forwards it.
3. A new opt-in flag `use_structured_output` (default **off**), plumbed exactly like the existing `retry_until_success` (base-class default → CLI flag → manifest field → `run_metadata`).
4. A model-axis config (e.g. `config/models/ollama_lucie_7b.yaml`) can default the flag on.

### Out of Scope
- **Categorical value validation.** Schema enforces shape/type, not value sanity; categorical garbage (`"1"`, `"< you want to use this?>"`) will now pass instead of failing. Numerics are unaffected (already clamped at `identity_generator_configurable.py:363-366`). A value-quality gate is a separate follow-up.
- Wiring Gemini's native `response_schema` / `response_mime_type` (Gemini already complies; would be a separate enhancement).
- Numeric `minimum`/`maximum` in the schema (llama.cpp range grammar is unreliable; existing post-parse clamp covers it).
- Any change to the `LLMClient` Protocol (already `generate_content(self, prompt, **kwargs)` — no signature change needed).
- Streaming.

## Success Criteria

- [ ] Flag **off** (default): Ollama payload still sends `format: "json"`; no `response_schema` kwarg is sent to *any* provider (Gemini/Claude paths byte-identical).
- [ ] Flag **on** (Ollama): every `value`/`candidates`/`weights` call parses; no `KeyError` on the expected key across a full 17-category persona.
- [ ] Lucie-7B / Swedish / `all_pick`, `--n 10 --structured-output`: yield rises from ~16% toward ~100%.
- [ ] Variety preserved: distinct values appear across personas at `temperature 0.7` (not all identical).
- [ ] `run_metadata.json` records `structured_output: true/false`.
- [ ] `ruff check src/` clean.

---

## Technical Design

### Approach

A provider-neutral `response_schema` kwarg is threaded from the generator into `client.generate_content(...)`, but is passed **only when `use_structured_output` is on**, so the default code path is unchanged for every provider. Only `OllamaClient` consumes it (as the request `format`); Gemini/Claude tolerate-and-ignore via their existing `**kwargs` handling. Schemas are built in the generator because that is where each call's shape is known (`expected_key` + `_is_numeric_category`).

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| JSON-Schema `format` (grammar-constrained) | Makes wrong shapes impossible; probe-verified 10/10 | Schema per call type; lets bad *values* through | **Chosen** |
| Lenient post-parse coercion (read lone key / `values[0]`) | No server feature needed | Guesses model intent; violates fail-fast / no-invented-values | Rejected |
| Always-on for Ollama (no flag) | Simpler | Breaks comparability with prior `json`-mode runs | Rejected |
| Prompt-only (one-shot example) | No code change | Does not *guarantee* shape; weak models still drift | Rejected |

### Architecture Changes

No new modules. Modified files:
- `src/population_synth/clients/ollama_client.py` — consume `response_schema` as `format`.
- `src/population_synth/identity/base_identity_generator.py` — `use_structured_output` attribute.
- `src/population_synth/identity/identity_generator_configurable.py` — schema builders + forward in `_call_llm_json`.
- `scripts/generate_identity.py`, `scripts/generate_identities_parallel.py` — CLI flag + plumbing + `run_metadata`.
- `src/population_synth/identity/manifest_loader.py` — `structured_output` field (manifest + compose + serialize).
- `config/models/ollama_lucie_7b.yaml` — optional default-on.

Schemas (type/structure only; wrapped as `{"type":"object","properties":{…},"required":[<key>]}`):

| Call (expected_key) | properties |
|---|---|
| pick/select `value` (categorical) | `value: {type: string}` |
| pick/select `value` (numeric) | `value: {type: integer\|number}` |
| enumerate `candidates` | `candidates: {type: array, items: {string\|number}}` |
| evaluate `weights` | `weights: {type: array, items: {number}}` |
| distribution (no key) | `distribution: {type: string, enum:[normal,uniform,beta]}, mean/std: {number}` (require only `distribution`) |

---

## Implementation Plan

### Phase 1: Core schema-constrained output
**Goal:** Ollama can be driven with a per-call JSON schema.

**Started:** 2026-05-29
**Completed:** 2026-05-29

**Tasks:**
- [x] Task 1.1 — `OllamaClient.generate_content`: pop `response_schema` from `effective_config` (beside the `system_instruction` pop); set `payload["format"] = response_schema if response_schema is not None else "json"`.
- [x] Task 1.2 — `base_identity_generator.py`: add `self.use_structured_output: bool = False` (beside `self.retry_until_success`).
- [x] Task 1.3 — `identity_generator_configurable.py`: add schema builders `_schema_value(category_schema)`, `_schema_candidates(category_schema)`, `_schema_weights()`, `_schema_distribution()`.
- [x] Task 1.4 — `_call_llm_json(...)`: add `response_schema: dict | None = None`; forward to the client only when `self.use_structured_output and response_schema is not None` (`extra = {"response_schema": …}` else `{}`).
- [x] Task 1.5 — Pass `response_schema=` at each `_call_llm_json` call site in `_process_pick` (~357), `_process_generate_pick` (~376/383), `_process_generate_evaluate_pick` (~403/416/439), `_process_generate_evaluate_random_pick` (~462/488/501).

**Files Modified:**
- `src/population_synth/clients/ollama_client.py` — payload `format` (lines ~149-176)
- `src/population_synth/identity/base_identity_generator.py` — flag attribute (~line 27)
- `src/population_synth/identity/identity_generator_configurable.py` — builders + `_call_llm_json` + call sites

**Dependencies:** None

### Phase 2: Opt-in flag plumbing
**Goal:** Turn the flag on via CLI/manifest/model-config and record it.

**Started:** 2026-05-29
**Completed:** 2026-05-29

**Tasks:**
- [x] Task 2.1 — `generate_identity.py`: add `--structured-output` (`BooleanOptionalAction`, default None) mirroring `--retry-until-success`; resolve from manifest; set `generator.use_structured_output` (beside line 243).
- [x] Task 2.2 — `generate_identities_parallel.py`: thread `structured_output` into the worker (mirror `retry_until_success` at lines 100/133), resolve from manifest (~282/311), set on generator, record in `run_metadata` (~394/467).
- [x] Task 2.3 — `manifest_loader.py`: add `structured_output: bool = False` to `ManifestConfig`; read `parameters.structured_output` in `load_manifest`; in `compose_manifest` read from experiment defaults with a `model_data["parameters"].get("structured_output")` override; include in `serialize_manifest`.
- [x] Task 2.4 — `config/models/ollama_lucie_7b.yaml`: optionally set `parameters.structured_output: true`.

**Files Modified:**
- `scripts/generate_identity.py`, `scripts/generate_identities_parallel.py`
- `src/population_synth/identity/manifest_loader.py`
- `config/models/ollama_lucie_7b.yaml`

**Dependencies:** Phase 1

---

## Testing Plan

### Manual Verification
- [ ] Regression (flag off): `python scripts/generate_identity.py --model-id ollama_llama32_3b --strategy-id all_pick --country-id swedish` — confirm payload still `format:"json"`; a Gemini/Claude single run sends no `response_schema`.
- [ ] Flag on (single): same Lucie command `+ --structured-output` — inspect `llm_interactions.jsonl`: every `value` parses, no `KeyError`, persona completes, values vary across categories.
- [ ] Flag on (parallel): `--n 10 --structured-output` — yield ≫ 16%; `run_metadata.json` shows `structured_output: true`.

### Edge Cases
- [ ] Numeric category (`age`) returns an integer; out-of-range value still clamped to [min,max].
- [ ] `generate_evaluate_random_pick` distribution call (no expected_key) produces a usable `{distribution,…}` object.
- [ ] Manifest without `structured_output` (legacy) still loads and runs.

### Probe (already passed)
- [x] `scripts/_throwaway_lucie_schema_probe.py` — schema 10/10 shape; temp 0.7 varied, temp 0 collapsed.

---

## Documentation Plan

- [ ] Update CLAUDE.md `clients/` + "Debugging Identity Generation Failures" to note the opt-in schema `format` for Ollama and the `--structured-output` flag.
- [ ] Note the categorical-garbage caveat (schema enforces shape, not value validity).

---

## Rollback Plan

Feature lives on `feature/ollama-structured-output`. Because `use_structured_output` defaults off and the schema kwarg is only sent when on, reverting is low-risk: `git revert` the commits, or simply never enable the flag. No data migrations.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Removes accidental quality gate — categorical garbage now passes | High | Med | Document clearly; numerics already clamped; follow-up value-validation; flag default off |
| Ollama server < 0.5 lacks schema `format` | Low | Med | Server runs recent models (gemma4/qwen3); verify version before enabling |
| Schema kwarg leaks to Gemini if flag enabled for non-Ollama | Low | Low | Only sent when flag on; flag intended for Ollama; Gemini's SDK accepts `response_schema` but path untested/out of scope |
| llama.cpp ignores numeric range in schema | Med | Low | Expected; existing post-parse clamp handles range |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 | Small (3 files, ~40 lines) | None |
| Phase 2 | Small (4 files, plumbing) | Phase 1 |

---

## References

- Predecessor (deferred this feature): `docs/development/plans/completed/fix-ollama-pipeline-failures.md`
- Analysis + probe (this session): `.claude/plans/analyse-the-lucie-7b-giggly-dolphin.md`, `scripts/_throwaway_lucie_schema_probe.py`
- Run analysed: `…/02_Data/01_Raw/swedish_all_pick_ollama_lucie_7b/` (+ `lucie7b_swedish_all_pick_report.md`)
- Ollama structured outputs: `https://ollama.com/blog/structured-outputs`

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- config/models/ollama_lucie_7b.yaml
- docs/development/plans/active/ollama-structured-output.md
- scripts/generate_identities_parallel.py
- scripts/generate_identity.py
- src/population_synth/clients/ollama_client.py
- src/population_synth/identity/base_identity_generator.py
- src/population_synth/identity/identity_generator_configurable.py
- src/population_synth/identity/manifest_loader.py
