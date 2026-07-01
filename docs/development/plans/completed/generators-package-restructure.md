# Plan: Group data producers under a `generators/` package

**Date:** 2026-07-01
**Author:** Basil
**Status:** Completed
**Completed:** 2026-07-01 14:49
**Base Branch:** `feature/rename-distribution-population-synthetic`
**Branch:** `feature/generators-package-restructure`

---

## Overview

Consolidate the two data producers under a single `generators/` parent package so the
namespace mirrors the architecture: `generators/reference/` (per-country statistical-API data
layers, formerly the top-level `population/` package) and `generators/synthetic/` (LLM persona
generation, formerly the top-level `identity/` package). This is a pure module-tree move plus
import-path updates — no behavioural change.

## Problem Statement

The two producers lived as sibling top-level packages (`population/` and `identity/`) with
names that did not convey their shared role. `population/` collides conceptually with the many
"population" data files and the comparison stage, and `identity/` reads as unrelated to
`population/` even though both are generation entry points. Grouping them under `generators/`
with the `reference` / `synthetic` split makes the "two data producers" architecture explicit
and matches how the wiki already describes the layout.

## Goals

### In Scope
1. Move `src/population_synthetic/population/` → `src/population_synthetic/generators/reference/`.
2. Move `src/population_synthetic/identity/` → `src/population_synthetic/generators/synthetic/`.
3. Add `generators/__init__.py` and `generators/reference/__init__.py`,
   `generators/synthetic/__init__.py`.
4. Update every live import across `src/`, `scripts/`, and `tests/` to the new paths.
5. Update live documentation (`CLAUDE.md`, `README.md`, architecture wiki) to the new paths.

### Out of Scope
- Any change to sampling/generation logic — imports and locations only.
- Renaming the `analysis/`, `clients/`, `gui/`, or `utils/` packages.
- Regenerating architecture diagram artifacts (`*.svg`/`*.dot`) — refreshed separately.

## Success Criteria

- [x] `population/` and `identity/` no longer exist under `src/population_synthetic/`.
- [x] `generators/reference/{sweden,norway,italy}` and `generators/synthetic/` resolve.
- [x] `grep -rn 'population_synthetic\.population\b\|population_synthetic\.identity\b' src/ scripts/ tests/` returns zero matches.
- [x] `pytest` passes at the prior baseline; `ruff check src/` at prior baseline.

---

## Technical Design

### Approach

Mechanical move executed as `git mv` of each producer directory into `generators/`, add the
three `__init__.py` files for the new package levels, then a word-boundary-guarded find/replace
of `population_synthetic.population` → `population_synthetic.generators.reference` and
`population_synthetic.identity` → `population_synthetic.generators.synthetic` across live code
and docs. Reinstall (editable) and verify with the test suite.

### Architecture Changes

```
src/population_synthetic/
  population/  ->  generators/reference/   (sweden/ norway/ italy/ + data.py helpers.py income_class.py)
  identity/    ->  generators/synthetic/   (base/factory/configurable generators, manifest_loader, log)
```

---

## Implementation Plan

### Phase 1: Move directories
- [x] `git mv` `population/` → `generators/reference/`, `identity/` → `generators/synthetic/`
- [x] Add `generators/__init__.py`, `generators/reference/__init__.py`, `generators/synthetic/__init__.py`

### Phase 2: Update imports
- [x] Word-boundary replace the two import stems across `src/`, `scripts/`, `tests/`

### Phase 3: Documentation
- [x] Update `CLAUDE.md`, `README.md`, and the architecture wiki to the new paths

### Phase 4: Verify
- [x] `pip install -e .`; `pytest` and `ruff check src/` at prior baseline

---

## Notes

Retro-documented during `/wrap-up`: the restructure was implemented in the working tree on top
of the `population_synthetic` rename before this plan record was written. This plan captures the
change so it merges as its own cascade step rather than being folded into the rename plan.
