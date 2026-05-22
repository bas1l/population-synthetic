# Plan: Composable Experiment Configuration

**Date:** 2026-05-22
**Author:** Basil
**Status:** In Progress
**Base Branch:** `feature/add-ollama-client`
**Branch:** `feature/composable-experiment-config`

---

## Overview

Replace the flat collection of manifest YAML files (one per model×strategy×country triple) with composable axis files that are merged at runtime. Each axis — model, strategy, country — gets its own small YAML file. The system composes them into a `ManifestConfig` on demand and writes a snapshot to the output directory for reproducibility. The GUI gains a persona count display and a force-reprocessing option.

## Problem Statement

Persona generation is configured via manifest YAML files in `config/seed_manifests/`. Each file represents one (model, strategy, country) combination. With 7 models × 5 strategies × 1 country = 35 manifests today, 90% of each file is identical boilerplate. Adding Norway doubles the count to 70. Each new model adds 5–10 files; each new strategy adds 7–14.

This creates three problems:
1. **Authoring burden** — creating manifests for a new model/strategy/country is tedious copy-paste-edit work
2. **Maintenance risk** — changing a shared default (e.g., `n: 100` → `200`) requires editing every manifest. Easy to miss one.
3. **No coverage guarantee** — nothing enforces that all valid combinations have manifests. Missing combos are silent gaps.

Additionally, the GUI provides no feedback on whether a selected experiment already has generated personas, and there is no way to force regeneration of existing personas without manually deleting them.

## Goals

### In Scope
1. Axis file structure: `config/models/`, `config/strategies/`, `config/countries/`, plus `config/experiment_defaults.yaml`
2. Composition logic in `manifest_loader.py`: `discover_axis_values()`, `compose_manifest()`, `serialize_manifest()`
3. CLI support: `--model-id`, `--strategy-id`, `--country-id` flags on both generation scripts, plus `--force`
4. Snapshot writing: `manifest_snapshot.yaml` auto-written to output directory before generation
5. GUI: `ExperimentSelector` with three independent dropdowns (Model, Strategy, Country)
6. GUI: Persona count label showing existing `persona_*/identity.json` count for the selected combination
7. GUI: Force-reprocessing checkbox that bypasses skip-if-exists logic
8. Full backward compatibility: `--manifest` flag and `load_manifest()` unchanged

### Out of Scope
- Norwegian simulation config JSON (will be added when Norway data work is ready)
- Renaming or migrating existing output directories (old `seed_NNN_*` dirs stay as-is)
- Deleting legacy manifest files (can be archived separately later)
- Changes to the comparison pipeline (`compare_pipeline_to_scb.py`)
- Changes to the strategy JSON files or simulation config JSON files

## Success Criteria

- [ ] `compose_manifest("claude_haiku", "all_pick", "swedish")` produces a `ManifestConfig` semantically equivalent to loading `identity_manifest_014_claude_haiku.yaml`
- [ ] CLI round-trip works: compose → run → snapshot written → re-run from snapshot
- [ ] `--manifest` with an existing legacy manifest file works unchanged
- [ ] GUI shows three independent dropdowns populated from axis files
- [ ] GUI displays correct persona count when selecting any combination
- [ ] Force checkbox causes `--force` flag in the constructed command, overwriting existing personas
- [ ] Adding a new model file to `config/models/` makes it appear in CLI and GUI without other changes

---

## Technical Design

### Approach

Explicit field-by-field composition (not generic deep-merge). Each `ManifestConfig` field is sourced from a known file:

| ManifestConfig field | Source |
|---|---|
| `name` | Derived: `"{model_label} — {strategy_label} ({country_label})"` |
| `provider` | Model file: `model_config.provider` |
| `model` | Model file: `model_config.model` |
| `base_url` | Model file: `model_config.base_url` (optional) |
| `generation_config` | Model file: `model_config.generation_config` (null-filtered) |
| `mode` | Defaults: `parameters.mode` |
| `config_path` | Country file: `parameters.config` |
| `strategy_path` | Strategy file: `parameters.strategy` |
| `log_llm` | Defaults: `parameters.log_llm` |
| `output` | Defaults: `parameters.output` |
| `parallel_n` | Defaults: `parameters.parallel.n` |
| `parallel_workers` | Model file: `parameters.parallel.workers` |
| `parallel_output_dir` | Derived: `"{output_base}/01_Raw/{country_id}_{strategy_id}_{model_id}"` |
| `comparison_output_dir` | Derived: `"{output_base}/03_Analysis/{country_id}_{strategy_id}_{model_id}"` |

Output directory slug: `{country_id}_{strategy_id}_{model_id}` (e.g., `se_all_pick_claude_haiku`).

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **Hybrid Composition + Snapshot** | O(M+S+C) files; full backward compat; reproducible via auto-snapshot; no regeneration step | Most runtime logic; `config/seed_manifests/` no longer browsable | **Chosen** |
| Matrix Generation | Zero downstream code changes; self-contained manifests preserved | Still 70+ files on disk; noisy git diffs; generator step required; drift risk | Rejected |
| CLI-First Presets | Maximum compactness (1 file); self-documenting CLI | Largest breaking change; GUI rewrite; loss of manifest-as-record | Rejected |
| Single Config Cross-Product | 1 file; guarantees all combos exist | Same migration burden as CLI-First; runtime expansion layer | Rejected |
| Pure Composition (no snapshots) | Lighter than hybrid | No manifest-as-record in output dirs; reproducibility depends only on `run_metadata.json` | Rejected |

### Architecture Changes

New directory structure:
```
config/
  experiment_defaults.yaml
  models/
    claude_haiku.yaml
    claude_sonnet.yaml
    claude_opus.yaml
    gemini_flash.yaml
    ollama_llama33_70b.yaml
    ollama_llama32_3b.yaml
    ollama_llama31_8b.yaml
  strategies/
    all_pick.yaml
    all_generate_pick.yaml
    all_generate_evaluate_pick.yaml
    all_generate_evaluate_random_pick.yaml
    all_pick_dag.yaml
  countries/
    swedish.yaml
```

New functions in `manifest_loader.py`:
- `discover_axis_values(axis)` — globs axis directory, returns parsed YAML list
- `compose_manifest(model_id, strategy_id, country_id)` — field-by-field composition → `ManifestConfig`
- `serialize_manifest(config)` — `ManifestConfig` → YAML string (for snapshot)

GUI widget rename: `ManifestSelector` → `ExperimentSelector` (three independent dropdowns + persona count + force checkbox).

---

## Implementation Plan

### Phase 1: Axis Files + Composition Logic
**Goal:** Create the axis file structure and the composition functions. No CLI or GUI changes yet — purely the data layer.

- [x] Task 1.1 — Create `config/experiment_defaults.yaml` with shared defaults extracted from existing manifests
- [x] Task 1.2 — Create 7 model files in `config/models/` extracted from existing manifests (claude_haiku, claude_sonnet, claude_opus, gemini_flash, ollama_llama33_70b, ollama_llama32_3b, ollama_llama31_8b)
- [x] Task 1.3 — Create 5 strategy files in `config/strategies/` (all_pick, all_generate_pick, all_generate_evaluate_pick, all_generate_evaluate_random_pick, all_pick_dag)
- [x] Task 1.4 — Create `config/countries/swedish.yaml`
- [x] Task 1.5 — Add `discover_axis_values()`, `compose_manifest()`, `serialize_manifest()` to `manifest_loader.py`

**Files Modified:**
- `src/population_synth/identity/manifest_loader.py` — add three new functions
- `config/experiment_defaults.yaml` — new file
- `config/models/*.yaml` — 7 new files
- `config/strategies/*.yaml` — 5 new files (axis metadata, not the strategy JSONs themselves)
- `config/countries/swedish.yaml` — new file

**Dependencies:** None

### Phase 2: CLI Changes + Snapshot Writing
**Goal:** Generation scripts accept axis IDs and write snapshots. `--force` flag added.

- [x] Task 2.1 — Add `--model-id`, `--strategy-id`, `--country-id` flags to `generate_identities_parallel.py` with mutual exclusion against `--manifest`
- [x] Task 2.2 — Add `--force` flag to `generate_identities_parallel.py`; pass through to `_generate_one()` to bypass skip-if-exists
- [x] Task 2.3 — Add snapshot writing: `serialize_manifest()` → `{output_dir}/manifest_snapshot.yaml` before generation starts
- [x] Task 2.4 — Apply same CLI changes to `generate_identity.py` (single-identity variant)

**Files Modified:**
- `scripts/generate_identities_parallel.py` — new CLI flags, force param, snapshot writing
- `scripts/generate_identity.py` — same CLI changes

**Dependencies:** Phase 1

### Phase 3: GUI Refactor
**Goal:** Replace manifest-file-based selector with axis dropdowns, add persona count and force checkbox.

- [x] Task 3.1 — Refactor `ManifestSelector` → `ExperimentSelector`: three independent dropdowns (Model, Strategy, Country) populated via `discover_axis_values()`
- [x] Task 3.2 — Add persona count label: on dropdown change, derive output dir path, glob `persona_*/identity.json`, display count (e.g., "42 / 100 personas exist")
- [x] Task 3.3 — Add force-reprocessing checkbox; update count label to show "(will be overwritten)" when checked and personas exist
- [x] Task 3.4 — Update `ManifestDisplayInfo` / `manifest_model.py` to support axis-based discovery alongside legacy manifest loading
- [x] Task 3.5 — Update `ManifestOverview` to show Country, Output Dir, Existing Persona count
- [x] Task 3.6 — Update `main_window.py` to wire up new signals and pass `--force` / axis-ID flags to command builder

**Files Modified:**
- `src/population_synth/gui/widgets/manifest_selector.py` — rewrite as `ExperimentSelector`
- `src/population_synth/gui/manifest_model.py` — adapt for axis-based discovery
- `src/population_synth/gui/widgets/manifest_overview.py` — add country, output dir, persona count
- `src/population_synth/gui/main_window.py` — wire up new widget signals and command construction
- `src/population_synth/gui/gui_launcher.yaml` — update if force param is defined here

**Dependencies:** Phase 1, Phase 2

---

## Testing Plan

### Manual Verification
- [ ] Compose (claude_haiku, all_pick, swedish) and diff against loaded `identity_manifest_014_claude_haiku.yaml` — fields should match semantically
- [ ] Run `--model-id claude_haiku --strategy-id all_pick --country-id swedish` → verify snapshot written to output dir
- [ ] Re-run with `--manifest <snapshot path>` → verify identical config loaded
- [ ] Run with `--manifest config/seed_manifests/identity_manifest_014_claude_haiku.yaml` → verify legacy behavior unchanged
- [ ] Generate 2 personas, run again without `--force` (should skip), run with `--force` (should regenerate)
- [ ] Create a new model file `config/models/test_model.yaml`, verify it appears in GUI and is accepted by CLI
- [ ] Launch GUI, change each dropdown, verify persona count updates
- [ ] Check force checkbox, verify "(will be overwritten)" hint and `--force` in constructed command

### Edge Cases
- [ ] Missing axis file (e.g., `--model-id nonexistent`) → clear error message
- [ ] Output directory doesn't exist yet → persona count shows 0
- [ ] Partial run (some personas exist, some don't) → count reflects actual files present
- [ ] `--manifest` combined with `--model-id` → mutual exclusion error

---

## Documentation Plan

- [ ] Update `CLAUDE.md` — add axis file structure, `compose_manifest()` to Architecture section, new CLI flags to Commands section
- [ ] Add manifest migration note to `docs/development/` if legacy manifests are archived

---

## Rollback Plan

1. **Before merging:** All changes are on a feature branch. Discard branch to revert entirely.
2. **Backward compatibility built in:** `load_manifest()` is unchanged. Even after merge, `--manifest` with existing YAML files works. The old and new paths coexist.
3. **GUI:** If the new `ExperimentSelector` has issues, revert `manifest_selector.py` to the previous version — it's a self-contained widget with a clean signal interface.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Output dir naming mismatch with existing runs | High | Low | Old dirs stay as-is; new naming only for new runs. Document the difference. |
| GUI persona count slow on network drives | Medium | Low | `Path.glob()` is fast even on SMB; if needed, add a short cache/debounce |
| Axis file schema diverges from ManifestConfig | Low | Medium | Explicit field mapping (not generic merge) catches mismatches at composition time |
| Users confused by two config systems (legacy + axes) | Medium | Low | Legacy manifests archived after transition period; snapshot in output dir serves as the "single file" view |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1: Axis Files + Composition | ~1 hour | None |
| Phase 2: CLI + Snapshot | ~1 hour | Phase 1 |
| Phase 3: GUI Refactor | ~2 hours | Phase 1, Phase 2 |

---

## References

- Analysis document: `.claude/plans/analyse-the-codebase-we-jiggly-perlis.md` (5 approaches compared)
- Current manifest loader: `src/population_synth/identity/manifest_loader.py`
- Current GUI widget: `src/population_synth/gui/widgets/manifest_selector.py`
- Existing skip-if-exists logic: `scripts/generate_identities_parallel.py` lines 86–91
