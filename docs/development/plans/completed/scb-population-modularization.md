# Plan: SCB Population Generator Modularization

**Date:** 2026-05-07
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/scb-population-enrichment`
**Branch:** `feature/scb-population-modularization`

---

## Overview

Restructure the 1,377-line monolith `scripts/generate_scb_population.py` into a clean, modular package at `anxiety_synthetic/scb_population/`. The script currently mixes API fetching, JSON-STAT2 parsing, and conditional sampling in a single file, making it hard to navigate for newcomers. The refactor uses a service-oriented paradigm: stateless service classes group related functions, frozen dataclasses carry structured data between services.

## Problem Statement

The SCB population generator was built incrementally during the `scb-population-enrichment` feature. It grew to 1,377 lines containing:

- **SCBDataFetcher** (~1,050 lines) — a class mixing 15 API query builders, 16 JSON-STAT2 parsers, 15 table ID constants, and county code lists
- **SwedishPopulationSampler** (~175 lines) — a stateful class caching 14 distributions and performing a 14-step conditional sampling chain
- **Helpers + entry point** (~100 lines) — `_normalize()`, `_sample_from()`, CLI parsing

A newcomer cannot tell where "fetching" ends and "parsing" begins, or which code relates to which demographic dimension. The monolith also uses an `importlib.util` hack to bypass `utils/__init__.py` (which eagerly imports `GeminiClient`).

## Goals

### In Scope
1. Split the script into 6 focused modules under `anxiety_synthetic/scb_population/`
2. Apply service-oriented paradigm: stateless `@staticmethod` service classes, frozen dataclass for distributions
3. Extract all 16 parse methods as pure module-level functions
4. Eliminate the `importlib.util` hack with clean direct imports
5. Keep the CLI entry point in `scripts/generate_scb_population.py` (~50 lines)
6. Preserve exact output behavior (same seed = identical output)

### Out of Scope
- Adding new demographic fields or changing sampling logic
- Adding a test suite (separate future work)
- Adopting external JSON-STAT2 parsing libraries (custom parsing handles SCB-specific quirks)
- Changing `SCBPxWebClient` in `anxiety_synthetic/utils/scb_client.py`
- Modifying `compare_populations.py` or `extract_population_from_pipeline.py`

## Success Criteria

- [ ] `scripts/generate_scb_population.py` is under 60 lines
- [ ] No file in the new package exceeds 600 lines
- [ ] `python scripts/generate_scb_population.py --n 200 --seed 42` produces identical `individuals` array before and after refactoring
- [ ] All imports resolve cleanly: `from anxiety_synthetic.scb_population import PopulationDistributions, FetchService, SampleService`
- [ ] No `importlib.util` usage remains
- [ ] Dependency graph is acyclic (no circular imports)

---

## Technical Design

### Approach

Split by **concern** (fetching, parsing, sampling), not by demographic dimension. Each file has one clear responsibility. The service paradigm means:

- **Classes as service groupings** — `FetchService` and `SampleService` use `@staticmethod` methods that receive all data as arguments
- **Classes as data containers** — `PopulationDistributions` is a `@dataclass(frozen=True)` holding all 14 distributions and derived lookup maps
- **Module-level pure functions** — parsers have no shared state, so a class would add indirection for zero benefit

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|---|---|---|---|
| Split by demographic dimension (demographics.py, economics.py, housing.py) | Intuitive grouping | Arbitrary boundaries (where does income_source go?), forces cross-imports for shared helpers | Rejected |
| Keep OOP with stateful classes | Simpler refactor, preserves existing interfaces | Hidden state, harder to test, not idiomatic for data pipelines | Rejected |
| Adopt pyjstat library for parsing | Less custom code | Doesn't handle SCB-specific dimension quirks, adds external dependency | Rejected |
| Service-oriented with data containers | Explicit data flow, testable, newcomer-friendly | More verbose method signatures | **Chosen** |

### Architecture Changes

**New package:** `anxiety_synthetic/scb_population/` (6 files)

```
anxiety_synthetic/scb_population/
    __init__.py           (~10 lines)   Public API exports
    constants.py          (~50 lines)   Table IDs, age group bounds, county codes, education labels
    data.py               (~45 lines)   PopulationDistributions frozen dataclass
    parsers.py            (~550 lines)  16 module-level pure parse functions
    fetch_service.py      (~350 lines)  FetchService class: 15 fetch operations + load_all
    sample_service.py     (~200 lines)  SampleService class: sample_one + sample_population
    _helpers.py           (~30 lines)   resolve_age_group, normalize, sample_from
```

**Dependency graph (acyclic):**

```
constants.py       <- no internal imports
_helpers.py        <- imports constants
data.py            <- no internal imports (dataclasses + typing only)
parsers.py         <- imports constants, _helpers
fetch_service.py   <- imports constants, parsers, data
sample_service.py  <- imports data, _helpers
__init__.py        <- imports data, fetch_service, sample_service
```

**Key data container:**

```python
@dataclass(frozen=True)
class PopulationDistributions:
    age_sex: dict[tuple[str, str], float]
    education_by_age: dict[str, dict[str, float]]
    employment_by_age_education: dict[str, dict[str, dict[str, float]]]
    birth_location: dict[str, float]
    region: dict[str, float]
    socioeconomic: dict[str, float]
    parental_structure: dict[str, float]
    civil_status_by_age_sex: dict[tuple[str, str], dict[str, float]]
    industry_sector: dict[str, float]
    employment_type_by_age: dict[str, dict[str, float]]
    housing_tenure: dict[str, float]
    household_size: dict[str, float]
    income_source_by_employment_age: dict[tuple[str, str], dict[str, float]]
    birth_country_detail: dict[str, float]
    ethnicity_map: dict[str, str]
    county_env_type_map: dict[str, str]
    tables_used: tuple[str, ...]
```

**Key service pattern:**

```python
class FetchService:
    @staticmethod
    def load_all(client: SCBPxWebClient, mappings: dict) -> PopulationDistributions:
        ...

    @staticmethod
    def fetch_age_sex(client: SCBPxWebClient, mappings: dict) -> tuple[dict, str]:
        ...

class SampleService:
    @staticmethod
    def sample_one(distributions: PopulationDistributions, rng: Generator, id: int) -> dict:
        ...

    @staticmethod
    def sample_population(distributions: PopulationDistributions, rng: Generator, n: int) -> list[dict]:
        ...
```

**Thin CLI orchestration:**

```python
distributions = FetchService.load_all(client, mappings)
individuals = SampleService.sample_population(distributions, rng, args.n)
```

---

## Implementation Plan

### Phase 1: Foundation — Constants, Data Container, Helpers
**Started:** 2026-05-07
**Completed:** 2026-05-07
**Goal:** Create the package skeleton and extract all zero-dependency code

- [x] Create `anxiety_synthetic/scb_population/` directory with empty `__init__.py`
- [x] Create `constants.py` — extract `VALID_AGE_GROUPS`, `AGE_GROUP_BOUNDS`, `EDUCATION_LABELS`, `COUNTY_CODES`, and all 15 table ID constants from `SCBDataFetcher` class attributes
- [x] Create `data.py` — define `PopulationDistributions` frozen dataclass
- [x] Create `_helpers.py` — extract `resolve_age_group()`, `normalize()`, `sample_from()`

**Files Created:**
- `anxiety_synthetic/scb_population/__init__.py` — empty initially
- `anxiety_synthetic/scb_population/constants.py` — table IDs, age groups, county codes
- `anxiety_synthetic/scb_population/data.py` — `PopulationDistributions` dataclass
- `anxiety_synthetic/scb_population/_helpers.py` — three utility functions

**Dependencies:** None

### Phase 2: Parsers
**Started:** 2026-05-07
**Completed:** 2026-05-07
**Goal:** Extract all 16 parse methods as pure module-level functions

- [x] Create `parsers.py` with 16 parse functions, each receiving `raw: dict` plus only the specific mapping sub-dict it needs
- [x] Map every `SCBDataFetcher._parse_*` method to its new pure function (see mapping table below)
- [x] Import shared helpers from `_helpers.py` and constants from `constants.py`

**Function mapping:**

| Source method | Target function | Explicit mapping argument |
|---|---|---|
| `_parse_age_sex_jsonstat` | `parse_age_sex` | (none — uses constants only) |
| `_parse_education_jsonstat` | `parse_education_by_age` | `sun2020_mappings` |
| `_parse_employment_jsonstat` | `parse_employment_by_age` | `employment_mappings` |
| `_parse_birth_location_jsonstat` | `parse_birth_location` | `birth_location_mappings` |
| `_parse_region_distribution` | `parse_region` | `region_label_map` |
| `_parse_urbanization_by_county` | `parse_urbanization_by_county` | `region_label_map` |
| `_parse_civil_status_jsonstat` | `parse_civil_status_by_age_sex` | `cs_label_map` |
| `_parse_industry_sector_jsonstat` | `parse_industry_sector` | `sector_label_map` |
| `_parse_employment_type_combined` | `parse_employment_type_combined` | `attachment_map, hours_map` |
| `_parse_housing_tenure_jsonstat` | `parse_housing_tenure` | `tenure_label_map` |
| `_parse_household_size_jsonstat` | `parse_household_size` | `size_label_map` |
| `_parse_income_source_jsonstat` | `parse_income_source` | `source_label_map` |
| `_parse_income_deciles_jsonstat` | `parse_socioeconomic` | `decile_label_map` |
| `_parse_family_jsonstat` | `parse_parental_structure` | `family_mappings` |
| `_parse_birth_country_detail_jsonstat` | `parse_birth_country_detail` | `country_mappings` |

**Files Created:**
- `anxiety_synthetic/scb_population/parsers.py` — 16 pure parse functions

**Dependencies:** Phase 1

### Phase 3: Fetch Service
**Started:** 2026-05-07
**Completed:** 2026-05-07
**Goal:** Move query construction and API orchestration into a stateless service class

- [x] Create `fetch_service.py` with `FetchService` class
- [x] Convert each `SCBDataFetcher._fetch_*` method to a `@staticmethod` that receives `(client, mappings)` and returns `(distribution, table_tag)`
- [x] Implement `load_all()` that calls all 15 fetch methods and constructs a `PopulationDistributions` instance
- [x] Eliminate the 15 thin `get_*()` public wrapper methods — `load_all` replaces them
- [x] Handle the `employment_type` special case (fetches two tables, returns two tags)

**Files Created:**
- `anxiety_synthetic/scb_population/fetch_service.py` — `FetchService` class

**Dependencies:** Phase 1, Phase 2

### Phase 4: Sample Service
**Started:** 2026-05-07
**Completed:** 2026-05-07
**Goal:** Move the conditional sampling chain into a stateless service class

- [x] Create `sample_service.py` with `SampleService` class
- [x] Convert `sample_one()` to a `@staticmethod` receiving `(distributions, rng, individual_id)`
- [x] Replace `self.fetcher.get_env_type_from_region(region)` with direct lookup on `distributions.county_env_type_map[region]`
- [x] Replace `self.mappings["ethnicity"]` access with `distributions.ethnicity_map`
- [x] Convert `sample_population()` to a `@staticmethod`

**Files Created:**
- `anxiety_synthetic/scb_population/sample_service.py` — `SampleService` class

**Dependencies:** Phase 1

### Phase 5: Integration — Wire Up and Clean Up
**Started:** 2026-05-07
**Completed:** 2026-05-07
**Goal:** Connect all modules, rewrite the CLI script, update package config

- [x] Update `__init__.py` with public exports: `PopulationDistributions`, `FetchService`, `SampleService`
- [x] Rewrite `scripts/generate_scb_population.py` as thin CLI entry point (~50 lines)
- [x] Remove the `importlib.util` hack — use direct import `from anxiety_synthetic.utils.scb_client import SCBPxWebClient`
- [x] Update `pyproject.toml`: change `include = ["patient_generator*"]` to `include = ["patient_generator*", "scb_population*", "utils*"]`
- [x] Re-install package: `pip install -e .`

**Files Modified:**
- `anxiety_synthetic/scb_population/__init__.py` — add exports
- `scripts/generate_scb_population.py` — rewrite as thin wrapper
- `pyproject.toml` — extend package discovery

**Dependencies:** Phases 1-4

---

## Testing Plan

### Integration Tests (Output Comparison)
- [ ] Before refactoring: capture baseline with `python scripts/generate_scb_population.py --n 200 --seed 42 --output baseline_200.json`
- [ ] After refactoring: run same command, compare `individuals` arrays — must be byte-identical
- [ ] Verify `metadata.tables_used` contains the same table IDs

### Manual Verification
- [ ] Smoke-test all public imports resolve: `from anxiety_synthetic.scb_population import PopulationDistributions, FetchService, SampleService`
- [ ] Smoke-test internal imports: `from anxiety_synthetic.scb_population.parsers import parse_age_sex`
- [ ] Verify `from anxiety_synthetic.utils.scb_client import SCBPxWebClient` works without triggering GeminiClient import
- [ ] Run `python -c "from anxiety_synthetic.scb_population import FetchService"` — no import errors

### Edge Cases
- [ ] Confirm `frozen=True` on `PopulationDistributions` — attempting to set an attribute after construction raises `FrozenInstanceError`
- [ ] Confirm no circular imports by importing each module independently

---

## Documentation Plan

- [ ] Update `CLAUDE.md` architecture section to describe the new `scb_population/` package structure
- [ ] Update `docs/scb_population_and_comparison.md` to reference the modular structure

---

## Rollback Plan

This is a pure structural refactor with no behavioral changes:

1. The original `scripts/generate_scb_population.py` is in git history — `git checkout HEAD~1 -- scripts/generate_scb_population.py` restores the monolith
2. Deleting `anxiety_synthetic/scb_population/` and reverting `pyproject.toml` fully reverts the change
3. No data files, configs, or other scripts are modified (except `pyproject.toml` include list)

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Subtle behavior change from refactoring (different output for same seed) | Medium | High | Bit-for-bit comparison of 200-individual baseline before/after with fixed seed |
| `pyproject.toml` change breaks existing `patient_generator` imports | Low | High | Only extend the `include` list, don't remove existing entries; verify with `pip install -e .` |
| Circular import between fetch_service and sample_service | Low | Medium | Dependency graph is strictly acyclic by design; verify during Phase 5 |
| `importlib.util` removal breaks if `utils/__init__.py` changes | Low | Low | Direct submodule import `from anxiety_synthetic.utils.scb_client import ...` bypasses `__init__.py` entirely |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|---|---|---|
| Phase 1: Foundation | Small | None |
| Phase 2: Parsers | Medium | Phase 1 |
| Phase 3: Fetch Service | Medium | Phases 1, 2 |
| Phase 4: Sample Service | Small | Phase 1 |
| Phase 5: Integration | Small | Phases 1-4 |

---

## References

- Source script: `scripts/generate_scb_population.py` (1,377 lines)
- Parent plan: `docs/development/plans/active/scb-population-enrichment.md`
- SCB client: `anxiety_synthetic/utils/scb_client.py`
- Category mappings: `config/assets/scb_reference/category_mappings.json`
