# Plan: Extract `population-synth` Standalone Repository

**Date:** 2026-05-14
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/strip-stats-from-identity-prompts`
**Branch:** `feature/extract-population-synth-repo`

---

## Overview

Extract identity persona generation, population sampling (SCB/SSB), and comparison tools into a self-contained `population-synth/` subfolder within the current repo. All files are **copied** — the existing `anxiety-synthetic` codebase is untouched. The subfolder is a complete standalone project that can be moved to its own repository.

## Problem Statement

The `anxiety-synthetic` monorepo bundles five distinct systems (generation pipeline, chatbot, SCB population, SSB population, comparison tools). The population generation, identity generation, and comparison tooling are independently useful and should be extractable as a focused, shareable project without carrying chatbot, narrative, clinical report, or questionnaire scoring baggage.

## Goals

### In Scope
1. Copy identity generation, population sampling, comparison tools, and their dependencies into `population-synth/`
2. Break the SCB↔SSB cross-dependency by lifting shared code into a common `population/` layer
3. Rewrite all imports to use the new `population_synth` package namespace
4. Create a standalone `generate_identity.py` entry point (no DAG orchestrator)
5. Provide a working `pyproject.toml`, `README.md`, `CLAUDE.md`, `.gitignore`

### Out of Scope
- Modifying any existing file in `anxiety-synthetic`
- Chatbot application (`chatbot/`)
- Narrative generation (`patient_generator/narrative/`)
- First-person conversion (`narrative_first_person_converter.py`)
- Clinical report generation (`clinical_report_generator.py`)
- Questionnaire scoring (`questionnaire_scorer.py`)
- Pipeline orchestrator (`pipeline_framework.py`, `pipeline_monitor/`)
- Seed manifests and DAG-based pipeline execution
- Test suite creation (no tests exist in the source project)

## Success Criteria

- [ ] `population-synth/` exists as a self-contained subfolder at the repo root
- [ ] No existing files in `anxiety-synthetic` are modified or deleted
- [ ] `pip install -e .` succeeds from within `population-synth/`
- [ ] `python scripts/generate_scb_population.py --n 10 --seed 42` runs successfully
- [ ] `python scripts/generate_ssb_population.py --n 10 --seed 42` runs successfully
- [ ] `ruff check src/` passes clean from within `population-synth/`
- [ ] SSB population module imports from shared `population/` layer, not from `sweden/`

---

## Technical Design

### Approach

Create `population-synth/` at the repo root using `src/` layout (`src/population_synth/`). Copy source files, rewrite imports to the new package namespace, and lift shared SCB/SSB code into a common parent module. Provide standalone CLI scripts that call factories directly (no DAG orchestrator).

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Self-contained subfolder (copy) | Zero risk to existing code, portable | Duplication until old code is cleaned up | **Chosen** |
| git filter-repo extraction | Preserves git history per file | Complex — files are interleaved in shared dirs, many empty commits | Rejected |
| Symlinks / submodule | No duplication | Not portable, fragile on Windows | Rejected |
| Flat layout (no `src/`) | Simpler, matches current project | Allows accidental bare imports of uninstalled package | Rejected |

### Architecture Changes

**New directory structure:**

```
population-synth/                          # Self-contained project root
├── pyproject.toml
├── README.md
├── CLAUDE.md
├── .gitignore
│
├── src/
│   └── population_synth/
│       ├── __init__.py
│       ├── _paths.py                      # PROJECT_ROOT resolution (single source of truth)
│       │
│       ├── identity/                      # LLM-based persona identity generation
│       │   ├── __init__.py
│       │   ├── base_identity_generator.py
│       │   ├── identity_generator_sequential.py
│       │   ├── identity_generator_batch.py
│       │   ├── identity_generator_configurable.py
│       │   └── factory_identity_generator.py
│       │
│       ├── population/                    # Shared population layer
│       │   ├── __init__.py
│       │   ├── data.py                    # PopulationDistributions dataclass
│       │   ├── helpers.py                 # Shared: age_to_group, resolve_age_group, sample_from, normalize, VALID_AGE_GROUPS, AGE_GROUP_BOUNDS
│       │   ├── income_class.py            # median_from_brackets, classify_brackets
│       │   │
│       │   ├── sweden/                    # SCB (Statistics Sweden)
│       │   │   ├── __init__.py
│       │   │   ├── constants.py
│       │   │   ├── fetch_service.py
│       │   │   ├── parsers.py
│       │   │   └── sample_service.py
│       │   │
│       │   └── norway/                    # SSB (Statistics Norway)
│       │       ├── __init__.py
│       │       ├── constants.py
│       │       ├── fetch_service.py
│       │       ├── parsers.py
│       │       └── sample_service.py
│       │
│       ├── comparison/                    # Comparison/evaluation tools
│       │   ├── __init__.py
│       │   ├── evaluator.py               # StatisticalEvaluator class
│       │   ├── normalizer.py              # normalize_scb_to_schema + helpers
│       │   ├── charts.py                  # plot_comparison_charts, plot_radar_comparison
│       │   └── extractor.py               # Extract population distributions from identity.json
│       │
│       └── clients/                       # API clients
│           ├── __init__.py
│           ├── pxweb_client.py            # BasePxWebClient (shared base with caching)
│           ├── scb_client.py              # SCBPxWebClient
│           ├── ssb_client.py              # SSBPxWebClient
│           ├── gemini_client.py           # Gemini API wrapper
│           └── gemini_config.py           # Model config loader
│
├── scripts/
│   ├── generate_identity.py              # NEW standalone entry point
│   ├── generate_scb_population.py
│   ├── generate_ssb_population.py
│   ├── compare_populations.py            # Thin CLI wrapper over comparison/ modules
│   ├── compare_pipeline_to_scb.py
│   └── extract_population_from_pipeline.py
│
└── config/
    └── assets/
        ├── identity/
        │   ├── batch/
        │   ├── configurable/              # Simulation configs + strategies/
        │   └── sequential/
        ├── scb_cache/.gitkeep
        ├── ssb_cache/.gitkeep
        ├── scb_reference/
        │   └── category_mappings.json
        └── ssb_reference/
            └── category_mappings.json
```

**Breaking the SCB↔SSB cross-dependency:**

Currently `ssb_population` imports from `scb_population` in 5 places (helpers, constants, data class). In the new layout, shared code is lifted into `population_synth/population/`:
- `data.py` — `PopulationDistributions` (from `scb_population/data.py`)
- `helpers.py` — `age_to_group`, `resolve_age_group`, `normalize`, `sample_from`, `VALID_AGE_GROUPS`, `AGE_GROUP_BOUNDS` (from `scb_population/_helpers.py` + `scb_population/constants.py`)
- `income_class.py` — bracket classification (from `utils/income_class.py`)

Both `sweden/` and `norway/` import from the shared parent, never from each other.

**Path resolution:**

`_paths.py` provides a single `PROJECT_ROOT`:
```python
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # src/population_synth/ → population-synth/
```
All cache/config paths derive from this, replacing the scattered `parents[N]` pattern.

**Import rewrite map:**

| Old import | New import |
|---|---|
| `from utils import GeminiClient` | `from population_synth.clients.gemini_client import GeminiClient` |
| `from utils.scb_client import SCBPxWebClient` | `from population_synth.clients.scb_client import SCBPxWebClient` |
| `from utils.ssb_client import SSBPxWebClient` | `from population_synth.clients.ssb_client import SSBPxWebClient` |
| `from scb_population.data import PopulationDistributions` | `from population_synth.population.data import PopulationDistributions` |
| `from scb_population._helpers import age_to_group` | `from population_synth.population.helpers import age_to_group` |
| `from scb_population._helpers import sample_from` | `from population_synth.population.helpers import sample_from` |
| `from scb_population.constants import VALID_AGE_GROUPS` | `from population_synth.population.helpers import VALID_AGE_GROUPS` |
| `from utils.income_class import ...` | `from population_synth.population.income_class import ...` |
| `from utils.pxweb_client import BasePxWebClient` | `from .pxweb_client import BasePxWebClient` |

---

## Implementation Plan

### Phase 1: Repo Skeleton
**Goal:** Create the directory structure, `pyproject.toml`, `_paths.py`, all `__init__.py` files, `.gitignore`

- [x] Create all directories under `population-synth/`
- [x] Write `pyproject.toml` with trimmed dependencies
- [x] Write `src/population_synth/__init__.py`
- [x] Write `src/population_synth/_paths.py`
- [x] Write all sub-package `__init__.py` files
- [x] Write `.gitignore` (venv, __pycache__, .meta.json, cache dirs)

**Files Created:**
- `population-synth/pyproject.toml`
- `population-synth/.gitignore`
- `population-synth/src/population_synth/__init__.py`
- `population-synth/src/population_synth/_paths.py`
- `population-synth/src/population_synth/{identity,population,population/sweden,population/norway,comparison,clients}/__init__.py`

**Dependencies:** None

### Phase 2: Shared Population Layer + Clients
**Goal:** Copy and adapt the foundation modules that everything else depends on

- [x] Copy `scb_population/data.py` → `population/data.py` (no import changes needed)
- [x] Copy `scb_population/_helpers.py` → `population/helpers.py`, add `VALID_AGE_GROUPS` and `AGE_GROUP_BOUNDS` constants from `scb_population/constants.py`
- [x] Copy `utils/income_class.py` → `population/income_class.py` (no import changes needed)
- [x] Copy `utils/pxweb_client.py` → `clients/pxweb_client.py` (update `_PROJECT_ROOT` to use `_paths.py`)
- [x] Copy `utils/scb_client.py` → `clients/scb_client.py` (update imports + cache path)
- [x] Copy `utils/ssb_client.py` → `clients/ssb_client.py` (update imports + cache path)
- [x] Copy `utils/gemini_client.py` → `clients/gemini_client.py` (no import changes needed)
- [x] Copy `utils/gemini_config.py` → `clients/gemini_config.py` (no import changes needed)

**Source Files:**
- `anxiety_synthetic/scb_population/data.py` → `population-synth/src/population_synth/population/data.py`
- `anxiety_synthetic/scb_population/_helpers.py` → `population-synth/src/population_synth/population/helpers.py`
- `anxiety_synthetic/utils/income_class.py` → `population-synth/src/population_synth/population/income_class.py`
- `anxiety_synthetic/utils/pxweb_client.py` → `population-synth/src/population_synth/clients/pxweb_client.py`
- `anxiety_synthetic/utils/scb_client.py` → `population-synth/src/population_synth/clients/scb_client.py`
- `anxiety_synthetic/utils/ssb_client.py` → `population-synth/src/population_synth/clients/ssb_client.py`
- `anxiety_synthetic/utils/gemini_client.py` → `population-synth/src/population_synth/clients/gemini_client.py`
- `anxiety_synthetic/utils/gemini_config.py` → `population-synth/src/population_synth/clients/gemini_config.py`

**Dependencies:** Phase 1

### Phase 3: Sweden Population Module
**Goal:** Copy and adapt SCB population (constants, fetch, parsers, sample)

- [x] Copy `scb_population/constants.py` → `population/sweden/constants.py` — remove `VALID_AGE_GROUPS` and `AGE_GROUP_BOUNDS` (moved to shared `helpers.py`), keep table IDs and label maps
- [x] Copy `scb_population/fetch_service.py` → `population/sweden/fetch_service.py` — rewrite imports
- [x] Copy `scb_population/parsers.py` → `population/sweden/parsers.py` — rewrite imports
- [x] Copy `scb_population/sample_service.py` → `population/sweden/sample_service.py` — rewrite imports

**Source Files:**
- `anxiety_synthetic/scb_population/constants.py` → `population-synth/src/population_synth/population/sweden/constants.py`
- `anxiety_synthetic/scb_population/fetch_service.py` → `population-synth/src/population_synth/population/sweden/fetch_service.py`
- `anxiety_synthetic/scb_population/parsers.py` → `population-synth/src/population_synth/population/sweden/parsers.py`
- `anxiety_synthetic/scb_population/sample_service.py` → `population-synth/src/population_synth/population/sweden/sample_service.py`

**Dependencies:** Phase 2

### Phase 4: Norway Population Module
**Goal:** Copy and adapt SSB population — validates that the cross-dependency fix works

- [x] Copy `ssb_population/constants.py` → `population/norway/constants.py` — rewrite imports to use shared `population.helpers`
- [x] Copy `ssb_population/fetch_service.py` → `population/norway/fetch_service.py` — rewrite imports
- [x] Copy `ssb_population/parsers.py` → `population/norway/parsers.py` — rewrite all 5 cross-references from `scb_population` to `population_synth.population`
- [x] Copy `ssb_population/sample_service.py` → `population/norway/sample_service.py` — rewrite imports

**Source Files:**
- `anxiety_synthetic/ssb_population/constants.py` → `population-synth/src/population_synth/population/norway/constants.py`
- `anxiety_synthetic/ssb_population/fetch_service.py` → `population-synth/src/population_synth/population/norway/fetch_service.py`
- `anxiety_synthetic/ssb_population/parsers.py` → `population-synth/src/population_synth/population/norway/parsers.py`
- `anxiety_synthetic/ssb_population/sample_service.py` → `population-synth/src/population_synth/population/norway/sample_service.py`

**Dependencies:** Phase 2

### Phase 5: Identity Module
**Goal:** Copy and adapt the 5 identity generator files

- [x] Copy all 5 identity files, rewrite `from utils import GeminiClient` → `from population_synth.clients.gemini_client import GeminiClient`
- [x] Update `factory_identity_generator.py` relative imports if needed

**Source Files:**
- `anxiety_synthetic/patient_generator/identity/base_identity_generator.py` → `population-synth/src/population_synth/identity/base_identity_generator.py`
- `anxiety_synthetic/patient_generator/identity/identity_generator_sequential.py` → `population-synth/src/population_synth/identity/identity_generator_sequential.py`
- `anxiety_synthetic/patient_generator/identity/identity_generator_batch.py` → `population-synth/src/population_synth/identity/identity_generator_batch.py`
- `anxiety_synthetic/patient_generator/identity/identity_generator_configurable.py` → `population-synth/src/population_synth/identity/identity_generator_configurable.py`
- `anxiety_synthetic/patient_generator/identity/factory_identity_generator.py` → `population-synth/src/population_synth/identity/factory_identity_generator.py`

**Dependencies:** Phase 2

### Phase 6: Comparison Tools
**Goal:** Decompose comparison scripts into importable modules + thin CLI wrappers

- [x] Read `scripts/compare_populations.py` fully to identify class/function boundaries
- [x] Read `scripts/extract_population_from_pipeline.py` fully to identify extractable logic
- [x] Read `scripts/compare_pipeline_to_scb.py` fully
- [x] Create `comparison/evaluator.py` — `StatisticalEvaluator` class
- [x] Create `comparison/normalizer.py` — schema normalization functions
- [x] Create `comparison/charts.py` — chart generation functions
- [x] Create `comparison/extractor.py` — population extraction from identity.json files

**Source Files:**
- `scripts/compare_populations.py` → decomposed into `comparison/{evaluator,normalizer,charts}.py`
- `scripts/extract_population_from_pipeline.py` → `comparison/extractor.py`
- `scripts/compare_pipeline_to_scb.py` → thin CLI wrapper

**Dependencies:** Phase 3, Phase 4

### Phase 7: Scripts + Config Assets
**Goal:** Copy and adapt entry-point scripts, copy config assets, write new `generate_identity.py`

- [x] Copy and adapt `scripts/generate_scb_population.py` — rewrite imports
- [x] Copy and adapt `scripts/generate_ssb_population.py` — rewrite imports
- [x] Copy and adapt `scripts/compare_populations.py` as thin CLI wrapper
- [x] Copy and adapt `scripts/compare_pipeline_to_scb.py` — rewrite imports
- [x] Copy and adapt `scripts/extract_population_from_pipeline.py` — rewrite imports
- [x] Write new `scripts/generate_identity.py` — standalone CLI entry point
- [x] Copy `config/assets/identity/` tree entirely
- [x] Copy `config/assets/scb_reference/category_mappings.json`
- [x] Copy `config/assets/ssb_reference/category_mappings.json`
- [x] Create `config/assets/scb_cache/.gitkeep` and `config/assets/ssb_cache/.gitkeep`

**Dependencies:** Phase 5, Phase 6

### Phase 8: Documentation + Verification
**Goal:** Write project docs and verify the extracted project works

- [x] Write `README.md`
- [x] Write `CLAUDE.md`
- [x] Run `pip install -e .` from `population-synth/`
- [x] Run `ruff check src/` from `population-synth/`
- [ ] Verify `python scripts/generate_scb_population.py --n 10 --seed 42` runs
- [ ] Verify `python scripts/generate_ssb_population.py --n 10 --seed 42` runs

**Dependencies:** Phase 7

---

## Testing Plan

### Integration Tests
- [ ] `pip install -e .` completes without errors from `population-synth/`
- [ ] `python -c "from population_synth.identity import FactoryIdentityGenerator"` imports cleanly
- [ ] `python -c "from population_synth.population.sweden import FetchService, SampleService"` imports cleanly
- [ ] `python -c "from population_synth.population.norway.fetch_service import SSBFetchService"` imports cleanly
- [ ] `python -c "from population_synth.comparison.evaluator import StatisticalEvaluator"` imports cleanly

### Manual Verification
- [ ] `python scripts/generate_scb_population.py --n 10 --seed 42` produces valid JSON
- [ ] `python scripts/generate_ssb_population.py --n 10 --seed 42` produces valid JSON
- [ ] `ruff check src/` passes with no errors
- [ ] Move `population-synth/` to a temp directory, `pip install -e .`, verify it still works standalone

### Edge Cases
- [ ] SSB population module does NOT import from `sweden/` (only from shared `population/`)
- [ ] No file in `population-synth/` imports from `anxiety_synthetic` or uses old import paths

---

## Documentation Plan

- [ ] Write `population-synth/README.md` — project overview, install, usage examples
- [ ] Write `population-synth/CLAUDE.md` — architecture, commands, import convention

---

## Rollback Plan

Since all work is additive (new subfolder, no modifications to existing files):
1. Delete `population-synth/` directory
2. No other cleanup needed

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Cache path resolution breaks with new `src/` nesting depth | High | Med | `_paths.py` provides single `PROJECT_ROOT`; clients accept `cache_dir` kwarg |
| `extract_population_from_pipeline.py` has hidden dependencies (80KB file) | Med | Med | Read fully during Phase 6; extract only comparison logic |
| Identity generators reference prompt paths relative to old project | Med | Low | `generate_identity.py` takes config path as required CLI arg |
| Undocumented SSB→SCB cross-references beyond the 5 known ones | Low | Med | `ruff check` after all rewrites catches any broken imports |
| `compare_populations.py` decomposition is complex (870 lines) | Med | Med | Read the full file before splitting; keep the thin CLI wrapper simple |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1: Repo Skeleton | Small | None |
| Phase 2: Shared Layer + Clients | Medium | Phase 1 |
| Phase 3: Sweden Population | Medium | Phase 2 |
| Phase 4: Norway Population | Medium | Phase 2 |
| Phase 5: Identity Module | Small | Phase 2 |
| Phase 6: Comparison Tools | Large | Phase 3, 4 |
| Phase 7: Scripts + Config | Medium | Phase 5, 6 |
| Phase 8: Docs + Verification | Small | Phase 7 |

Phases 3, 4, and 5 can run in parallel (all depend only on Phase 2).
