> **Archived 2026-06-30:** Superseded by retire-narrative-batch-mapping — narrative batch generation was retired. A future batch generator should emit flat fields through the config-driven engine and would be a fresh plan.

# Plan: Batch Generation — All Properties At Once

**Date:** 2026-06-30
**Author:** Basil
**Status:** Idea (future)
**Base Branch:** `feature/synthetic-mapper-load-map-split`
**Branch:** `feature/batch-generate-all-properties`

---

## Overview

Add a generation mode that produces a **complete persona identity — all demographic
attributes — in a single LLM call**, instead of the current configurable mode that
resolves one category at a time across a dependency DAG (1–3 LLM calls *per* category,
17 categories ⇒ dozens of calls per persona).

This was prompted by retiring the old `config/synthetic/prompts/` batch files (narrative,
free-text "landscape" prompts). The legacy `batch` mode (`IdentityGeneratorBatch`) produced
unstructured narrative text; this future mode instead emits a **structured, schema-conformant
identity** in one shot.

## Problem Statement

The current `configurable` mode is accurate (each field is conditioned on prior draws and
validated against the simulation-config `categories`), but it is **call-heavy and slow**:
every category is its own LLM round-trip, and `all_generate_evaluate_*` strategies multiply
that by 2–3. For large runs this dominates wall-clock and token cost.

A one-call "generate everything at once" path trades some per-field conditioning rigor for a
dramatic reduction in calls — useful for cheap first-pass generation, smoke tests, and
high-volume runs where exact per-field marginals matter less than throughput.

## Goals

### In Scope
1. A generation mode (candidate name `batch_structured`) that prompts the model **once** for a
   full identity covering all attributes in the active simulation config's `categories`.
2. Structured output: the response is JSON validated against the simulation-config schema
   (reuse the existing `categories` definition — value sets per attribute).
3. Plug into the existing axis/manifest system as a `mode` (so `--model-id/--strategy-id/--country-id`
   and manifests can select it) without disturbing `configurable`.
4. Same downstream artifacts (`identity.json`, `llm_interactions.jsonl`, run metadata) so the
   analysis/comparison pipelines work unchanged.

### Out of Scope (for the first cut)
- Per-category dependency conditioning / DAG (the whole point is to skip it).
- Weight reconciliation and `generate_evaluate_random_pick`-style sampling.
- Replacing `configurable` — this is an additional mode, not a migration.

## Open Questions / Design Sketch

- **Where does the value space come from?** Reuse `simulation_configs/*.json` `categories`
  (the same per-attribute allowed values configurable mode uses) and inline them into one prompt.
- **Structured output mechanism:** reuse the existing `structured_output` plumbing
  (`ManifestConfig.structured_output`, provider response-schema support) to force a single JSON
  object keyed by the 17 attributes.
- **Validation/repair:** on a malformed or out-of-vocabulary response, retry (mirror
  `_call_llm_json` retry semantics) — decide whether to repair per-field or regenerate wholesale.
- **Naming:** the legacy narrative `batch` mode still exists (`IdentityGeneratorBatch`). Either
  rename it (`batch_narrative`) and claim `batch` for this, or introduce `batch_structured`.
  Resolve before implementing to avoid a confusing `mode` vocabulary.
- **Coherence cost:** measure how much marginal/joint fidelity is lost vs `configurable` using
  the existing comparison pipeline — this determines whether it's "smoke-test only" or
  production-viable.

## Success Criteria

- [ ] One LLM call yields a full, schema-valid identity covering every configured attribute
- [ ] Selectable via `mode` in a manifest and (if applicable) the axis system
- [ ] Output artifacts are byte-compatible with the analysis + comparison pipelines
- [ ] A comparison run quantifies the fidelity gap vs `configurable` on the same country/model

## References

- Current per-category generator: `src/population_synth/identity/identity_generator_configurable.py`
- Legacy narrative batch generator: `src/population_synth/identity/identity_generator_batch.py`
- Mode selection: `FactoryIdentityGenerator` + `VALID_MODES` in `identity/manifest_loader.py`
- Value spaces: `config/synthetic/simulation_configs/simulation_config_004_swedish_generative.json`
- Structured-output plumbing: `ManifestConfig.structured_output` (see `docs/development/plans/completed/ollama-structured-output.md`)
