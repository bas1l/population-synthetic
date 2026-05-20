# Plan: Add `--manifest` support to `compare_pipeline_to_scb.py`

**Date:** 2026-05-20
**Author:** Basil
**Status:** Completed
**Started:** 2026-05-20
**Completed:** 2026-05-20 18:11
**Base Branch:** `feature/align-strategies-scb-comparable`
**Branch:** `feature/compare-pipeline-manifest-support`

---

## Overview

**What:** Add a `--manifest` argument to `compare_pipeline_to_scb.py` so the script can derive `--seed-root` from a seed manifest YAML file.
**Why:** Running comparisons currently requires copying long output paths manually. The manifest already contains `parallel.output_dir` — the exact path needed as `--seed-root`.
**How:** Reuse the existing `manifest_loader.load_manifest()` function, following the same CLI-override pattern established by `generate_identity.py` and `generate_identities_parallel.py`.

## Problem Statement

Every comparison invocation requires the user to look up the output directory from the manifest and paste it as `--seed-root`:

```
python scripts/compare_pipeline_to_scb.py \
    --seed-root "F:/liu-onedrive-nospecial-carac/_Teams/Gauss/02_Data/01_Raw/seed_022_all_pick_sonnet" \
    --reference data/scb_api/scb_10k.json
```

This is error-prone (paths are long, often external) and inconsistent with the other two scripts that already accept `--manifest`.

## Goals

### In Scope
1. Accept `--manifest` to derive `seed_root` from `parallel.output_dir`
2. Make `--seed-root` optional when manifest provides the path
3. Allow CLI `--seed-root` to override the manifest value (consistent pattern)

### Out of Scope
- Adding a reference population field to the manifest schema (comparison is a separate concern from generation)
- Changes to `manifest_loader.py` or `ManifestConfig`
- Changes to any other script

## Success Criteria

- [x] `--manifest` flag accepted and loads via `load_manifest()`
- [x] `seed_root` derived from `manifest.parallel_output_dir` when `--seed-root` omitted
- [x] CLI `--seed-root` overrides manifest value when both provided
- [x] Clear error when neither `--manifest` (with `parallel_output_dir`) nor `--seed-root` is given
- [x] Existing `--seed-root`-only invocations work unchanged

---

## Technical Design

### Approach

Reuse `manifest_loader.load_manifest()` and follow the identical override pattern from `generate_identities_parallel.py`: load manifest fields as defaults, then let explicit CLI args take precedence.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Reuse `load_manifest()`, derive seed_root only | Minimal change, no schema changes, consistent pattern | Manifest doesn't provide reference path | **Chosen** — reference has a sensible default already |
| Add `reference` field to manifest schema | Fully self-contained comparison via manifest | Mixes generation and comparison concerns; requires `manifest_loader.py` + all manifests updated | Rejected |
| Wrapper script that reads manifest and calls compare | No changes to compare script | Extra indirection, another file to maintain | Rejected |

### Architecture Changes

No new modules or classes. Single file modification reusing existing infrastructure.

---

## Implementation Plan

### Phase 1: Add manifest support to CLI
**Goal:** Accept `--manifest` and resolve `seed_root` from it

- [x] Add `from population_synth.identity.manifest_loader import load_manifest` import
- [x] Add `--manifest` argument (optional, help text referencing `parallel.output_dir`)
- [x] Change `--seed-root` from `required=True` to `default=None`
- [x] After `parse_args()`: if `--manifest` provided, load it and set `args.seed_root` from `manifest.parallel_output_dir` (only when CLI `--seed-root` is None)
- [x] Validate: error if no seed_root resolved from either source
- [x] Update module docstring with new usage example

**Files Modified:**
- `scripts/compare_pipeline_to_scb.py` — argparse changes + manifest resolution logic (~15 lines added)

**Dependencies:** None

---

## Testing Plan

### Manual Verification
- [ ] Run with manifest only: `python scripts/compare_pipeline_to_scb.py --manifest config/seed_manifests/identity_manifest_022_claude_sonnet.yaml`
- [ ] Run with manifest + CLI seed-root override: verify CLI value takes precedence
- [ ] Run with `--seed-root` only (no manifest): existing behavior unchanged
- [ ] Run with neither: verify clear error message
- [ ] Run with manifest that has no `parallel.output_dir` and no `--seed-root`: verify clear error

---

## Documentation Plan

- [x] Update CLAUDE.md usage example for `compare_pipeline_to_scb.py` to show `--manifest` option

---

## Rollback Plan

Single-file change with no breaking changes. Revert the one commit.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Manifest path points to non-existent directory | Medium | Low | Existing path validation (`seed_root.exists()` check on line 111) already handles this |

---

## References

- Existing manifest pattern: `scripts/generate_identities_parallel.py` lines 164-199
- Manifest loader: `src/population_synth/identity/manifest_loader.py`
