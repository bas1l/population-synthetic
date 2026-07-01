# Plan: Synthetic Mapper — Load/Map Split + Reference Mapper Hierarchy

**Date:** 2026-06-30
**Author:** Basil
**Status:** Completed
**Completed:** 2026-06-30 13:15
**Base Branch:** `feature/code-standards-audit-docs`
**Branch:** `feature/synthetic-mapper-load-map-split`

---

## Overview

Decompose the monolithic `comparison/extractor.py` (and the parallel
`comparison/normalizer.py`) into two symmetric class hierarchies — one for the
**synthetic** (pipeline) population and one for the **reference** (database)
population — and split each into an explicit two-step **load → map/normalize**
API so that reading a population from disk is visibly separate from translating
its values to the canonical schema.

## Tasks

1. **Synthetic mapper package** (`comparison/synthetic_mapper/`)
   - `AbstractSyntheticMapper → BaseSyntheticMapper → {SwedishSyntheticMapper,
     ItalianSyntheticMapper}` so each country owns its specificities (no
     `is_italian` branching). `BaseSyntheticMapper` holds the orchestrator plus
     cross-country attributes; subclasses implement the divergent ones.
   - Two-step API: `load_raw_population(seed_root)` then
     `map_population(raw_pop, country)`; `get_synthetic_mapper(country)` factory.
   - Narrative/batch parsing is a mapper method (Swedish only; Italian raises).

2. **Reference mapper package** (`comparison/reference_mapper/`)
   - `AbstractReferenceMapper → BaseReferenceMapper → {SwedishReferenceMapper,
     ItalianReferenceMapper}` with `get_reference_mapper(country, mappings_path)`.
   - Single mappings-driven loop in `BaseReferenceMapper`; country divergence is
     **data** held as subclass class attributes (`DOMESTIC_NAME`,
     `DOMESTIC_BIRTH_LABELS`, `MAPPINGS_SUBDIR`) — the old `if country ==
     "italian"` branch is gone.
   - Two-step API: `load_reference_population(path)` then
     `normalize_population(raw_pop, country)`.

3. **Translation primitives** (`comparison/extract/`)
   - `normalizers_se`, `normalizers_it`, `schema_labels`, `mappings`, `batch`,
     `prose_inference`.

4. **Backward-compat facades**
   - `extractor.py` → thin `extract_individual()` / `extract_population()`
     delegating to the synthetic mapper (kept for tests and
     `extract_population_from_pipeline.py`).
   - `normalizer.py` → thin `normalize_raw_to_schema()` / `normalize_if_raw()` /
     `load_mappings` / `is_raw_format` delegating to the reference mapper
     package (kept because `extract/mappings.py` imports `load_mappings`).

5. **Characterization tests** — `tests/test_extractor_characterization.py` and
   `tests/test_evaluator.py` lock in behaviour across the refactor.

## Outcome

`extractor.py` shrank from ~2000 lines to a facade; the synthetic and reference
sides now mirror each other structurally, and the compare scripts call
`load_*` then `map`/`normalize` explicitly so the two stages are visible at the
call site.
