# Plan: Config Four-Concern Separation

**Date:** 2026-06-30
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/synthetic-mapper-load-map-split`
**Branch:** _implemented in place on `feature/synthetic-mapper-load-map-split` (no separate branch — user opted to implement here, 2026-06-30)_

---

## Overview

Reorganize `config/` so its top-level layout maps one-to-one onto the project's
four concerns — **synthetic population**, **database population**, **mapping**,
and **analysis** (plus a small cross-cutting **gui/**). Today these concerns are
scrambled across incidental groupings (`assets/`, `comparison/`) and scattered
top-level files. The change is mechanical: `git mv` of files/dirs plus updates to
the `PROJECT_ROOT`-anchored path constants that reference them.

## Problem Statement

The current `config/` tree groups files by accident of history rather than by
concern:

- **`assets/` conflates two unrelated concerns** — national-stats API caches
  (`scb_cache/`, `ssb_cache/`, `eurostat_cache/`, `istat_cache/`, the *database
  population* stage) sit next to `identity/` inputs (the *synthetic population*
  stage). Nothing links them.
- **Synthetic config is scattered across six top-level locations** — `models/`,
  `strategies/`, `countries/`, `seed_manifests/`, `experiment_defaults.yaml`, and
  `assets/identity/` all serve one concern.
- **`comparison/` is a misnomer** — its only contents are *category mappings*,
  which are cross-cutting (used both to normalize the database reference in
  `comparison/normalizer.py` and to map the synthetic population in
  `comparison/extract/mappings.py`). Mapping deserves a first-class home.
- **Split indirection** — a strategy/country is defined in two places: an axis
  pointer YAML (`strategies/all_pick.yaml`, `countries/swedish.yaml`) and the
  definition it points at (`assets/identity/configurable/...`).
- **Durable config mixed with gitignored runtime caches.**

This makes the config hard to navigate, obscures which stage a file belongs to,
and invites scope creep when adding new countries/models/mappings.

## Goals

### In Scope
1. One top-level `config/` directory per concern: `synthetic/`, `database/`,
   `mapping/`, `analysis/`, plus `gui/`.
2. Move all existing config files into the matching concern dir via `git mv`
   (preserve history).
3. Update every `PROJECT_ROOT`-anchored path constant and intra-config pointer
   (axis YAMLs) to the new locations.
4. Update `.gitignore` cache entries, CLAUDE.md, and README path references.
5. Keep behavior identical — no logic changes, suite still passes.

### Out of Scope
- Collapsing the axis-pointer / definition indirection into a single file
  (a separate cleanup; this plan only relocates).
- Moving runtime *outputs* (run dirs under `output_base`) — those live outside
  the repo and are untouched.
- Renaming attributes, mapping keys, or any file *contents* beyond path strings.
- Changing the GUI launcher's discovery logic.

## Success Criteria

- [x] `config/` contains exactly `synthetic/`, `database/`, `mapping/`,
      `analysis/`, `gui/` at the top level (no stray `assets/`, `comparison/`,
      `models/`, `strategies/`, `countries/`, `seed_manifests/`). ✔ verified.
- [x] `pytest` passes unchanged. ✔ 65 passed.
- [~] `ruff check src/` is clean. **15 pre-existing errors** (E501/F401/F841/I001)
      in GUI widgets + `comparison/extract/normalizers_se.py` — none in files this
      refactor edited, none path-related. Belong to the in-flight synthetic-mapper
      work, left untouched (out of scope).
- [~] Full generate → compare → analyze smoke run. Path-resolution verified
      (`compose_manifest` resolves; client cache dirs + `load_mappings` resolve to
      real dirs). End-to-end live-API/LLM run not executed (needs network/keys).
- [x] `git log --follow` history preserved via 121 staged `git mv` renames
      (resolves after commit; `--follow` reads committed history).
- [x] No remaining references to old paths in `src/`, `scripts/`, `config/*.yaml`,
      `.gitignore`, CLAUDE.md, README — Phase 3.8 sweep clean on live files
      (only historical dated `docs/` notes intentionally left).

---

## Technical Design

### Approach

Pure relocation anchored on the single `PROJECT_ROOT` constant in `_paths.py`.
Every consumer already derives its path from `PROJECT_ROOT / "config" / ...`, so
the change is a find-and-replace of the path *suffix* in ~9 `src/` files and ~7
`scripts/` runtime constants, plus the intra-config YAML pointers, `.gitignore`,
and doc/comment strings. No new abstractions.

### Target structure

```
config/
  synthetic/                       # SYNTHETIC POPULATION (LLM personas)
    experiment_defaults.yaml       # <- config/experiment_defaults.yaml
    axes/
      models/                      # <- config/models/
      strategies/                  # <- config/strategies/
      countries/                   # <- config/countries/
    manifests/                     # <- config/seed_manifests/
    simulation_configs/            # <- config/assets/identity/configurable/*.json
    strategy_defs/                 # <- config/assets/identity/configurable/strategies/
    prompts/                       # <- config/assets/identity/batch/
  database/                        # DATABASE POPULATION (national stats APIs)
    caches/
      scb/                         # <- config/assets/scb_cache/
      ssb/                         # <- config/assets/ssb_cache/
      eurostat/                    # <- config/assets/eurostat_cache/
      istat/                       # <- config/assets/istat_cache/
  mapping/                         # CATEGORY MAPPINGS -> canonical schema
    scb/                           # <- config/comparison/category_mappings/scb/
    ssb/                           # <- config/comparison/category_mappings/ssb/
    istat/                         # <- config/comparison/category_mappings/istat/
  analysis/
    analyze_defaults.yaml          # <- config/analyze_defaults.yaml
  gui/
    launcher.yaml                  # <- config/gui_launcher.yaml
    state.json                     # <- config/gui_state.json (gitignored)
```

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Full 4-way restructure (this plan) | Layout matches the four concerns exactly; easiest to navigate long-term | Touches ~8 code files + YAML pointers + docs | **Chosen** (user-selected) |
| Consolidate `synthetic/` only | Lower risk; biggest win (6 scattered locations) for least churn | Leaves `comparison/`-as-mapping misnomer and `assets/` split unresolved | Rejected |
| Proposal-only doc, no moves | Zero risk | Doesn't solve the problem | Rejected |
| Move caches out of concern dirs | Keeps runtime caches separate from durable config | Splits the database concern across two roots | Rejected (user chose caches under `database/`) |

### Architecture Constraints

- All paths must remain derived from `PROJECT_ROOT` (`_paths.py`) — no new
  hardcoded absolute paths.
- Caches stay gitignored; only the path prefix in `.gitignore` changes.
- `discover_axis_values()` / `compose_manifest()` build axis dirs as
  `PROJECT_ROOT / "config" / axis`; the new axis home is
  `config/synthetic/axes/{axis}`, so the join base must change accordingly.

---

## Implementation Plan

### Phase 1: Move files with `git mv`
**Goal:** Relocate every config file/dir into its concern dir, preserving history.

**Phase 1 started:** 2026-06-30
**Phase 1 completed:** 2026-06-30

- [x] 1.1 — Create `config/synthetic/{axes,manifests,simulation_configs,strategy_defs,prompts}`,
      `config/database/caches/{scb,ssb,eurostat,istat}`, `config/mapping`,
      `config/analysis`, `config/gui`.
- [x] 1.2 — `git mv` synthetic axis dirs (`models`, `strategies`, `countries`) into
      `config/synthetic/axes/`.
- [x] 1.3 — `git mv` `seed_manifests` → `synthetic/manifests`,
      `experiment_defaults.yaml` → `synthetic/experiment_defaults.yaml`.
- [x] 1.4 — `git mv` `assets/identity/configurable/*.json` →
      `synthetic/simulation_configs/`, `assets/identity/configurable/strategies/` →
      `synthetic/strategy_defs/`, `assets/identity/batch/` → `synthetic/prompts/`.
      (Tracked `.json` moved via `git mv`; the gitignored `*.layout.json` siblings moved via plain `mv`.)
- [x] 1.5 — `git mv` the four `assets/*_cache/` dirs → `database/caches/{scb,ssb,eurostat,istat}/`.
      (scb/ssb tracked `.gitkeep` via `git mv`; gitignored cache contents via plain `mv`;
      fresh tracked `.gitkeep` created + `git add`ed for eurostat/istat. Moved cache JSONs
      remain untracked until the `.gitignore` prefix is updated in Phase 3 — not staged.)
- [x] 1.6 — `git mv` `comparison/category_mappings/{scb,ssb,istat}` → `mapping/`.
- [x] 1.7 — `git mv` `analyze_defaults.yaml` → `analysis/`, `gui_launcher.yaml` →
      `gui/launcher.yaml`; `gui_state.json` (gitignored) → `gui/state.json` via plain `mv`.
- [x] 1.8 — Remove now-empty `assets/`, `comparison/` shells.

**Files Modified:** file moves only.
**Dependencies:** None.

### Phase 2: Update code path constants
**Goal:** Re-point every `PROJECT_ROOT`-anchored constant to the new locations.

**Phase 2 completed:** 2026-06-30 (smoke-verified: `compose_manifest` resolves)

- [x] 2.1 — `src/population_synth/clients/scb_client.py` `_DEFAULT_CACHE_DIR` →
      `config/database/caches/scb`.
- [x] 2.2 — `clients/ssb_client.py` → `config/database/caches/ssb`.
- [x] 2.3 — `clients/eurostat_client.py` → `config/database/caches/eurostat`.
- [x] 2.4 — `clients/istat_client.py` → `config/database/caches/istat`.
- [x] 2.5 — `comparison/normalizer.py` `_SCB_MAPPINGS_DIR` → `config/mapping/scb`
      (and any istat/ssb dir resolution).
- [x] 2.6 — `comparison/extract/mappings.py` `_MAPPINGS_PATH` / `_ISTAT_MAPPINGS_PATH`
      → `config/mapping/{scb,istat}`.
- [x] 2.7 — `comparison/extract/schema_labels.py` `_SCB_MAPPINGS_DIR` → `config/mapping/scb`.
- [x] 2.8 — `identity/manifest_loader.py` — axis dirs (lines 149–151:
      `config/{models,strategies,countries}/{id}.yaml` → `config/synthetic/axes/{models,strategies,countries}/{id}.yaml`)
      and `experiment_defaults` path (line 148) → `config/synthetic/experiment_defaults.yaml`.
      Note: `discover_axis_values()` (line 134) builds `config/{axis}` — its join base
      must become `config/synthetic/axes/{axis}`.
- [x] 2.9 — `gui/main.py:22` `launcher_yaml` → `config/gui/launcher.yaml`;
      `gui/widgets/manifest_selector.py:25` `_STATE_FILE` → `config/gui/state.json`.

**Files Modified:** the `src/` files above (path strings only).
**Dependencies:** Phase 1.

### Phase 2b: Update script path constants
**Goal:** Re-point the functional path constants that live in `scripts/` (not just
docstrings — these are read at runtime).

**Phase 2b completed:** 2026-06-30

- [x] 2b.1 — `scripts/analyze/analyze_run.py:73` `_CONFIG_PATH` → `config/analysis/analyze_defaults.yaml`.
- [x] 2b.2 — `scripts/analyze/compare_runs.py:36` `_CONFIG_PATH` → `config/analysis/analyze_defaults.yaml`.
- [x] 2b.3 — `scripts/analyze/compare_all_pipelines.py:44-45` mapping dirs
      (`swedish` → `config/mapping/scb`, `italian` → `config/mapping/istat`).
- [x] 2b.4 — `scripts/analyze/compare_pipeline_to_istat.py:43` `_ISTAT_MAPPINGS_PATH`
      → `config/mapping/istat`.
- [x] 2b.5 — `scripts/dev/prototype_istat_api.py:26` `_CACHE_DIR` → `config/database/caches/istat`.
- [x] 2b.6 — `scripts/dev/test_istat_discovery.py:39` `_CACHE_DIR` → `config/database/caches/istat`.
- [x] 2b.7 — `scripts/generate/scheduled_generate.py:21` `MANIFEST` constant
      → `config/synthetic/manifests/identity_manifest_022_claude_sonnet.yaml`.

**Files Modified:** the `scripts/` files above (path strings only).
**Dependencies:** Phase 1.

### Phase 3: Update intra-config pointers, gitignore, docs
**Goal:** Fix references that live in config/data/docs rather than code.

- [x] 3.1 — `config/synthetic/axes/countries/{swedish,italian}.yaml` `parameters.config`
      → `config/synthetic/simulation_configs/...`.
- [x] 3.2 — `config/synthetic/axes/strategies/*.yaml` `parameters.strategy`
      → `config/synthetic/strategy_defs/...`. (Also updated the live `config/synthetic/manifests/*.yaml`
      `config`/`strategy` pointers — runtime-resolved config not enumerated above.)
- [x] 3.3 — `.gitignore` cache globs → `config/database/caches/*/...`; `gui_state.json`
      → `config/gui/state.json`. Verified moved caches + `config/gui/state.json` are ignored again.
- [x] 3.4 — CLAUDE.md: update every config path in command examples + Configuration
      + Debugging + cache sections.
- [x] 3.5 — README.md path updates, and `docs/architecture/diagrams/synthetic_strategies/render_strategy_diagrams.py`
      (`STRATEGY_DIR`, `SIM_CONFIG` — functional constants → `config/synthetic/strategy_defs/`
      and `config/synthetic/simulation_configs/...`). Also fixed the sibling diagram README.
- [x] 3.6 — Docstring example paths only (constants were handled in Phase 2b):
      `scripts/generate/{generate_identity,generate_identities_parallel}.py`
      (`--manifest`, `--config`, `--strategy` examples),
      `scripts/analyze/{compare_pipeline_to_scb,compare_pipeline_to_istat}.py`
      (`--manifest` examples).
- [x] 3.7 — Message/comment strings: `analyze_run.py:251` and `compare_runs.py:165`
      console messages naming `config/...`; `comparison/extract/schema_labels.py` doc comment;
      `population/norway/{constants,parsers}.py` comments referencing
      `config/comparison/category_mappings/ssb/`; `clients/ssb_client.py` + `gui/{main,launcher_config}.py`
      + `gui/widgets/manifest_selector.py` docstrings; fail-fast error messages in
      `population/italy/parsers.py` ("Clear config/assets/istat_cache/" → `config/database/caches/istat/`).
- [x] 3.8 — Final grep-sweep across `src/`, `scripts/`, `config/`, `docs/`. All live
      code/config/`.gitignore`/CLAUDE.md/README clean. Remaining hits live only in `docs/`
      historical/dated notes and completed/pending plan docs (out of scope per Success Criteria),
      plus this plan doc.

**Files Modified:** axis YAMLs, `.gitignore`, CLAUDE.md, README.md, `render_strategy_diagrams.py`,
scripts docstrings, `comparison/*` + `population/{norway,italy}/*` comments & error strings.
**Dependencies:** Phase 1.

---

## Testing Plan

### Unit / Suite
- [ ] `pytest` passes (covers `analysis/` and `clients/call_context`).
- [ ] `ruff check src/` clean.

### Integration / Smoke
- [ ] Manifest identity run resolves config from new paths
      (`generate_identity.py --manifest config/synthetic/manifests/...`).
- [ ] Axis-composed run works (`--model-id claude_haiku --strategy-id all_pick --country-id swedish`).
- [ ] One comparison run loads mappings from `config/mapping/` and emits charts.
- [ ] `analyze_run.py` reads `config/analysis/analyze_defaults.yaml`.
- [ ] A client cache hit/write lands under `config/database/caches/<agency>/`.

### Manual Verification
- [ ] GUI launcher (`python -m population_synth.gui.main`) starts, lists axes,
      persists state to `config/gui/state.json`.
- [ ] `git log --follow config/synthetic/axes/models/claude_haiku.yaml` shows
      pre-move history.

### Edge Cases
- [ ] Empty/fresh cache dir is created on first fetch at new path.
- [ ] `discover_axis_values()` still sorts and loads all axis YAMLs.

---

## Documentation Plan

- [ ] Update CLAUDE.md (Commands, Configuration, Debugging, cache paths, Key Design Patterns).
- [ ] Update README.md command examples.
- [ ] Add changelog entry: `docs/changelogs/config-four-concern-separation.md`.
- [ ] Update `config/mapping/*/README.md` if they reference old paths.

---

## Rollback Plan

1. The entire change is on `feature/config-four-concern-separation`; if it fails
   review, abandon the branch — `main`/base is untouched.
2. Because moves use `git mv`, a single `git revert` of the squash/merge (or
   `git checkout <base> -- config/ src/ scripts/ .gitignore CLAUDE.md README.md`)
   restores the old layout.
3. No data migrations; caches regenerate from APIs if a path is missed.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| A path string is missed (esp. in docstrings / error messages) | Med | Med | Phase 3.7 grep-sweep across `src/ scripts/ config/ docs/`; smoke run exercises each stage |
| Axis base join in `manifest_loader` overlooked (extra `axes/` segment) | Med | High | Explicit task 2.8; axis-composed smoke test |
| Stale gitignored caches left at old path cause confusion | Low | Low | Document; old empty dirs removed in 1.8; caches regenerate |
| Entanglement with in-flight synthetic-mapper branch | Med | Med | Branch off `main` instead of current branch (see base-branch note) |
| GUI state path change loses persisted selection | Low | Low | Acceptable (regenerated on next launch); note in changelog |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 (moves) | ~30 min | None |
| Phase 2 (`src/` code paths) | ~30 min | Phase 1 |
| Phase 2b (`scripts/` constants) | ~15 min | Phase 1 |
| Phase 3 (pointers/docs/sweep) | ~45 min | Phase 1 |

---

## References

- CLAUDE.md — Configuration, Path Resolution, Debugging sections
- `src/population_synth/_paths.py` — `PROJECT_ROOT` anchor
- `src/population_synth/identity/manifest_loader.py` — axis composition
- Related plans: none

---

## Modified Files

<!-- auto-generated by /plan-implement — scoped to THIS refactor's edits (from phase-agent
     reports), NOT the raw working-tree diff. The working tree is entangled with in-flight
     synthetic-mapper changes; see the commit note below. -->

**Phase 1 — config tree relocated (`git mv`, history preserved):**
- entire `config/` subtree moved into `synthetic/ database/ mapping/ analysis/ gui/`
  (axes/models|strategies|countries, manifests, simulation_configs, strategy_defs,
  prompts, database/caches/{scb,ssb,eurostat,istat}, mapping/{scb,ssb,istat},
  analysis/analyze_defaults.yaml, gui/launcher.yaml, gui/state.json)
- new `.gitkeep` added under `config/database/caches/{scb,ssb,eurostat,istat}/`

**Phase 2 — `src/` path constants:**
- src/population_synth/clients/eurostat_client.py
- src/population_synth/clients/istat_client.py
- src/population_synth/clients/scb_client.py
- src/population_synth/clients/ssb_client.py
- src/population_synth/comparison/extract/mappings.py
- src/population_synth/comparison/extract/schema_labels.py
- src/population_synth/comparison/normalizer.py
- src/population_synth/gui/main.py
- src/population_synth/gui/widgets/manifest_selector.py
- src/population_synth/identity/manifest_loader.py

**Phase 2b — `scripts/` runtime constants:**
- scripts/analyze/analyze_run.py
- scripts/analyze/compare_all_pipelines.py
- scripts/analyze/compare_pipeline_to_istat.py
- scripts/analyze/compare_runs.py
- scripts/dev/prototype_istat_api.py
- scripts/dev/test_istat_discovery.py
- scripts/generate/scheduled_generate.py

**Phase 3 — intra-config pointers, gitignore, docs, comments:**
- .gitignore
- CLAUDE.md
- README.md
- config/synthetic/axes/countries/{italian,swedish}.yaml
- config/synthetic/axes/strategies/*.yaml (5)
- config/synthetic/manifests/*.yaml (~41, incl. template) — functional `config:`/`strategy:` pointers
- docs/architecture/diagrams/synthetic_strategies/render_strategy_diagrams.py (+ its README)
- scripts/generate/{generate_identity,generate_identities_parallel}.py (docstrings)
- scripts/analyze/{compare_pipeline_to_scb,compare_pipeline_to_istat}.py (docstrings)
- src comments/error strings: comparison/extract/schema_labels.py, clients/ssb_client.py,
  gui/{main,launcher_config}.py, gui/widgets/manifest_selector.py,
  population/norway/{constants,parsers}.py, population/italy/parsers.py
- docs/development/plans/active/config-four-concern-separation.md (this plan)

## Commit Note

Implemented in place on `feature/synthetic-mapper-load-map-split` (user chose "implement
here"). The working tree mixes this refactor with ~106 pre-existing synthetic-mapper
changes; several edited files (`.gitignore`, `CLAUDE.md`, `README.md`,
`scripts/analyze/compare_runs.py`, some `src/` files) carry **both** sets of changes, so a
file-scoped commit cannot cleanly isolate the refactor. Commit strategy deferred to the
user (auto-commit intentionally skipped to avoid a misleading mixed changeset).
