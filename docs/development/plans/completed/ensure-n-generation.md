# Plan: Ensure N Generation

**Date:** 2026-05-24
**Author:** Basil
**Status:** Completed
**Completed:** 2026-05-28 07:28
**Base Branch:** `feature/gui-three-column-layout`
**Branch:** `feature/ensure-n-generation`

---

## Overview

Add an `--ensure-n` option to the parallel identity generation pipeline that guarantees exactly N successful personas by retrying failed slots indefinitely until all succeed or the user manually aborts. Currently, failed personas are permanently lost — this option eliminates that gap.

## Problem Statement

When generating a synthetic population of N identities, LLM failures (malformed JSON, weight/candidate mismatches, network errors) cause some personas to be permanently skipped. The parallel script logs the failure and moves on. For experiments requiring exactly N data points, this forces manual re-runs or produces incomplete datasets.

## Goals

### In Scope
1. Add `--ensure-n` CLI flag that retries failed persona slots until all N succeed
2. Integrate the option into manifest YAML, experiment defaults, and the GUI launcher
3. Add optional `--max-retries-per-slot` safety valve (default: no cap)
4. Clear logging of retry rounds, attempt counts, and exhaustion warnings

### Out of Scope
- Changing the internal per-call retry logic in `identity_generator_configurable.py` (3 JSON retries, 3 weight retries)
- Adding backoff/delay between retry rounds (can be added later if rate-limiting becomes an issue)
- Per-persona error classification (transient vs permanent failures)

## Success Criteria

- [ ] Running with `--ensure-n` produces exactly N successful `persona_XXXXX/identity.json` files
- [ ] Running without `--ensure-n` behaves identically to current behavior (single pass)
- [ ] Retry rounds are clearly logged with round number and slot count
- [ ] Optional `--max-retries-per-slot` cap terminates gracefully with exhaustion warning
- [ ] GUI checkbox "Ensure N generated" appears and correctly passes `--ensure-n` to subprocess
- [ ] Manifest YAML `parallel.ensure_n` field is respected

---

## Technical Design

### Approach

Batch-round retry: after each ThreadPoolExecutor round completes, collect failed indices and re-submit them as a new batch. Repeat until all N succeed. This fits naturally with the existing `ThreadPoolExecutor + as_completed` pattern and keeps the code simple to debug.

On retry rounds, `force=True` is passed to `_generate_one()` to ensure regeneration regardless of any partial artifacts from previous failed attempts.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Batch-round retry | Simple, debuggable, fits existing pattern | Slightly slower (waits for round to finish) | Chosen |
| Immediate re-queue on failure | Faster (no wait for slow successes) | Complex concurrency, harder to log/debug | Rejected |
| Overshoot N then trim | No retry logic needed | Wastes LLM tokens, unpredictable cost | Rejected |

### Architecture Changes

No new modules or classes. Changes are localized to:
- The execution loop in `generate_identities_parallel.py`
- Two new fields on `ManifestConfig` dataclass
- Config/YAML additions

---

## Implementation Plan

### Phase 1: Data Model + CLI
**Goal:** Add the option to CLI args, manifest dataclass, and config files
**Started:** 2026-05-24

- [x] Add `ensure_n` and `max_retries_per_slot` fields to `ManifestConfig`
- [x] Parse both from `parallel` dict in `load_manifest()`
- [x] Extract both in `compose_manifest()` from experiment defaults
- [x] Include both in `serialize_manifest()` output
- [x] Add `--ensure-n` and `--max-retries-per-slot` to argparse in parallel script
- [x] Wire manifest values to CLI args (manifest → args fallback)
- [x] Add `ensure_n: false` to `config/experiment_defaults.yaml`

**Files Modified:**
- `src/population_synth/identity/manifest_loader.py` — Add dataclass fields + parsing
- `scripts/generate_identities_parallel.py` — Add argparse args + manifest wiring
- `config/experiment_defaults.yaml` — Add `ensure_n` default

**Dependencies:** None

### Phase 2: Retry Loop
**Goal:** Implement the batch-round retry logic
**Started:** 2026-05-24

- [x] Replace single-pass executor block with retry-aware while loop
- [x] Track per-slot attempt counts in `slot_attempts` dict
- [x] On retry rounds, pass `force=True` to ensure regeneration
- [x] Implement optional cap logic (skip if `max_retries_per_slot` is set and exhausted)
- [x] Log retry round headers and exhaustion warnings
- [x] Update `run_metadata` with retry statistics after completion
- [x] Ensure `if not args.ensure_n: break` preserves backward compatibility

**Files Modified:**
- `scripts/generate_identities_parallel.py` — Executor block rewrite + metadata update

**Dependencies:** Phase 1

### Phase 3: GUI Integration
**Goal:** Expose the option in the synth launcher GUI
**Started:** 2026-05-24

- [x] Add `ensure-n` (bool) parameter to `generate_parallel` action in GUI config
- [x] Add `max-retries-per-slot` (int, nullable) parameter to `generate_parallel` action

**Files Modified:**
- `config/gui_launcher.yaml` — Add two parameter entries

**Dependencies:** Phase 1

---

## Testing Plan

### Manual Verification
- [ ] Run `--ensure-n` with Ollama (cheap local model) on 10 identities — confirm all 10 succeed despite some failures
- [ ] Run without `--ensure-n` — confirm failures stay failed (identical to current behavior)
- [ ] Run with `--ensure-n --max-retries-per-slot 1` — confirm exhaustion warning and graceful stop
- [ ] Launch from GUI — confirm checkbox appears, toggle it, verify `--ensure-n` in subprocess command
- [ ] Ctrl+C during retry round — confirm clean shutdown (existing atexit cleanup handles this)

### Edge Cases
- [ ] All N succeed on first round — no retry rounds triggered, clean exit
- [ ] All N fail every round (bad config) — retries indefinitely until user aborts; verify logs are clear
- [ ] `--ensure-n` with `--force` — first round uses force, retries also use force (no conflict)
- [ ] Previously completed personas (up-to-date check) — correctly skipped on first round, not re-submitted

---

## Documentation Plan

- [ ] Update CLAUDE.md commands section with `--ensure-n` flag example
- [ ] Add `ensure_n` field to manifest YAML example in any existing docs

---

## Rollback Plan

1. Revert the feature branch — no data migrations, no breaking changes
2. All changes are additive (new CLI flag, new dataclass fields with defaults)
3. Existing manifests without `ensure_n` continue to work (defaults to `false`)

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Infinite retry on consistently failing model/config | Medium | Low (user can abort) | Clear per-round logging shows no progress; optional `--max-retries-per-slot` cap |
| Rate limiting from rapid retries | Low | Medium | LLM clients already have internal delays; add backoff in future if needed |
| Thread-safety issue with retry loop | Low | High | Each round creates fresh executor; existing `_progress_lock` remains valid |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1: Data Model + CLI | Small | None |
| Phase 2: Retry Loop | Medium | Phase 1 |
| Phase 3: GUI Integration | Small | Phase 1 |

---
