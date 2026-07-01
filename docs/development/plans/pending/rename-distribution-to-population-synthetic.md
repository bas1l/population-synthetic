# Plan: Rename distribution & import package to `population_synthetic`

**Date:** 2026-07-01
**Author:** Basil
**Status:** Draft
**Base Branch:** `feature/extract-mapping-task`
**Branch:** `feature/rename-distribution-population-synthetic`

---

## Overview

Rename the distribution from `population-synth` to `population-synthetic` and the import
package from `population_synth` to `population_synthetic`, so all three names align with the
git repository name (`population-synthetic`). The `src/` layout is **kept** unchanged — only
the package directory inside `src/` is renamed.

## Problem Statement

The project currently carries three subtly different names:

- Git repo / directory: `population-synthetic`
- Distribution (`pyproject.toml`): `population-synth`
- Import package: `population_synth`

Each name individually follows PEP 8 / PyPA conventions (hyphen for the distribution,
underscore for the import package). The inconsistency is that the distribution/import stem
(`synth`) is a *different word* from the repo (`synthetic`), which hurts discoverability and
makes the install/import relationship harder to reason about. Aligning them removes that
friction. This is a cosmetic/consistency change with no behavioural impact.

## Goals

### In Scope
1. Distribution renamed to `population-synthetic` in `pyproject.toml`.
2. Import package directory renamed `src/population_synth/` -> `src/population_synthetic/` (via `git mv`).
3. Every live `population_synth.*` import updated across `src/`, `scripts/`, and `tests/`.
4. Live documentation updated (`CLAUDE.md`, `README.md`, `scripts/README.md`, and docs that
   describe *current* commands).
5. Editable reinstall works and the full test suite + ruff pass under the new namespace.

### Out of Scope
- Removing or changing the `src/` layout (explicitly kept).
- Renaming the git repository or updating the git remote URL (separate, GitHub-side action).
- Rewriting historical plan records under `docs/development/plans/completed/` and `archived/`
  (point-in-time artifacts — left as-is intentionally).
- Regenerating architecture diagram artifacts (`docs/architecture/diagrams/**/*.svg`, `*.dot`);
  these are regenerated from source, not hand-edited, and can be refreshed separately if desired.
- Renaming the `popsynth` conda environment (unrelated to package naming).
- Any PyPI publishing action (project is not published; `version = 0.1.0`).

## Success Criteria

- [ ] `grep -rn 'population_synth\b' src/ scripts/ tests/` returns **zero** matches (only `population_synthetic` remains).
- [ ] `pyproject.toml` declares `name = "population-synthetic"`.
- [ ] `pip install -e .` completes cleanly.
- [ ] `python -c "import population_synthetic"` succeeds; `import population_synth` fails (ImportError).
- [ ] `pytest` passes at the same pass/fail baseline as before the rename.
- [ ] `ruff check src/` passes.
- [ ] `python -m population_synthetic.gui.main` resolves (import path valid).

---

## Technical Design

### Approach

A mechanical, repo-wide identifier rename executed as: (1) move the package directory with
`git mv` so history is preserved, (2) apply a word-boundary-guarded find/replace of the
`population_synth` token across live code and docs, (3) flip the distribution name in
`pyproject.toml`, then (4) reinstall and verify. The `[tool.setuptools.packages.find]
where = ["src"]` config auto-discovers the renamed directory, so no package list edits are
needed.

The rename token is `population_synth` (underscore/import form). The distribution form
`population-synth` (hyphen) exists only in `pyproject.toml` and is handled explicitly.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Rename distribution+import to `population_synthetic` (this plan) | All three names align; import matches repo | Longer import token to type; wide diff | **Chosen** |
| Rename the *git repo* to `population-synth` instead | Zero code changes | Diverges from the descriptive "synthetic" name; still repo!=import stem mismatch resolved only one way | Rejected |
| Leave as-is | No work | Three-name inconsistency persists | Rejected |
| Blanket `sed` across ALL files incl. historical docs | One command | Falsifies historical plan records; rewrites generated diagrams | Rejected |

### Architecture Changes

Only the package directory name changes; internal module structure is untouched.

```
src/
  population_synth/         ->  population_synthetic/
    __init__.py                  (contents unchanged except any self-reference)
    _paths.py                    (parents[2] depth unchanged — verify)
    population/ identity/ comparison/ analysis/ clients/ gui/ utils/
```

The sed word boundary (`population_synth\b`) is critical: without it, a second pass would turn
the already-correct `population_synthetic` into `population_syntheticetic`. Run the replacement
exactly once and verify with grep.

---

## Implementation Plan

### Phase 1: Distribution name + directory move
**Goal:** Establish the new package location and distribution name.

- [ ] Task 1.1 — `git mv src/population_synth src/population_synthetic`
- [ ] Task 1.2 — Edit `pyproject.toml`: `name = "population-synth"` -> `name = "population-synthetic"`
- [ ] Task 1.3 — Verify `[tool.setuptools.packages.find] where = ["src"]` still resolves (no explicit package list to edit)

**Files Modified:**
- `pyproject.toml` — distribution name
- `src/population_synth/` -> `src/population_synthetic/` — directory move

**Dependencies:** None

### Phase 2: Code imports (src / scripts / tests)
**Goal:** Update every live Python import and `-m` module string to the new namespace.

- [ ] Task 2.1 — Word-boundary replace `population_synth` -> `population_synthetic` across `src/**/*.py`
- [ ] Task 2.2 — Same replace across `scripts/**/*.py` (includes `python -m population_synth...` strings and `launch_gui.py`)
- [ ] Task 2.3 — Same replace across `tests/**/*.py` and `tests/_mapping_fixtures.py`
- [ ] Task 2.4 — Verify `src/population_synthetic/_paths.py` `parents[2]` still points at repo root (depth unchanged by rename)

**Files Modified:**
- `src/population_synthetic/**/*.py` — ~40 files, import statements
- `scripts/**/*.py` — ~15 files, imports + module-path strings
- `tests/**/*.py` — ~18 files, imports

**Dependencies:** Phase 1

### Phase 3: Live documentation
**Goal:** Update docs that describe the current install/import/commands.

- [ ] Task 3.1 — Update `CLAUDE.md` (Import Convention section + all `population_synth.*` examples + `python -m` command)
- [ ] Task 3.2 — Update `README.md` and `scripts/README.md`
- [ ] Task 3.3 — Update live/how-to docs that reference current commands (`docs/mapping_gap_investigation_playbook.md`, active/pending plan docs) — **do not** touch `completed/`, `archived/`, `debug/` historical records
- [ ] Task 3.4 — Leave generated diagram files (`docs/architecture/diagrams/**/*.svg`, `*.dot`) for separate regeneration

**Files Modified:**
- `CLAUDE.md`, `README.md`, `scripts/README.md` — namespace references
- `docs/mapping_gap_investigation_playbook.md` and other live docs — command references

**Dependencies:** Phase 1

### Phase 4: Reinstall & verify
**Goal:** Confirm the rename is complete and the package works under the new name.

- [ ] Task 4.1 — `pip install -e .` (re-register the editable install under the new dist name)
- [ ] Task 4.2 — `grep -rn 'population_synth\b' src/ scripts/ tests/` returns zero matches
- [ ] Task 4.3 — `python -c "import population_synthetic"` succeeds
- [ ] Task 4.4 — `pytest` at prior baseline; `ruff check src/` passes

**Files Modified:** None (verification only)

**Dependencies:** Phases 1-3

---

## Testing Plan

### Unit Tests
- [ ] Full `pytest` suite passes at the same baseline as before the rename (no new failures)
- [ ] Import-sensitive tests (`test_mapper_delegation`, `test_reference_mapper_base`, `test_synthetic_mapper_base`) resolve the new namespace

### Integration Tests
- [ ] A representative script imports cleanly, e.g. `python scripts/analyze/map_populations.py --help`
- [ ] `python -m population_synthetic.gui.main` import path resolves (GUI optional dep permitting)

### Manual Verification
- [ ] `pip install -e .` clean
- [ ] `python -c "import population_synthetic; print(population_synthetic.__file__)"` points into `src/population_synthetic/`
- [ ] `python -c "import population_synth"` raises `ModuleNotFoundError`

### Edge Cases
- [ ] Confirm no `population_syntheticetic` double-substitution anywhere (word-boundary check)
- [ ] Confirm `pyproject.toml` is the only place the hyphenated `population-synth` form was changed

---

## Documentation Plan

- [ ] Update `README.md` with the new install/import name
- [ ] Update `CLAUDE.md` Import Convention + all `population_synth.*` occurrences
- [ ] Update `scripts/README.md`
- [ ] No changelog file convention exists in this repo; the completed plan record serves as the change note

---

## Rollback Plan

The change is a pure rename on a dedicated feature branch — rollback is trivial.

1. **Before merge:** discard the branch — `git checkout feature/extract-mapping-task && git branch -D feature/rename-distribution-population-synthetic`, then `pip install -e .` to restore the old editable registration.
2. **Data considerations:** none — no migrations, no runtime data, no state.
3. **Rollback procedure:** revert the rename commit(s); re-run `pip install -e .`.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| sed double-substitution (`population_syntheticetic`) | Med | Med | Use `population_synth\b` word boundary; run once; grep-verify afterward |
| Stale editable install still points at old dir | Med | Med | Re-run `pip install -e .` in Phase 4; verify `__file__` path |
| Missed reference in an out-of-tree consumer (e.g. `anxiety-synthetic` parent repo) | Low | Low | Out of scope here; parent repo has its own copy of modules (see memory) |
| Windows/git case or path issues on `git mv` | Low | Low | Single directory move, distinct names — no case-only rename involved |
| Accidentally rewriting historical plan records | Low | Low | Scope sed to `src/ scripts/ tests/` + explicit live docs; exclude `completed/`/`archived/`/`debug/` |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 | ~10 min | None |
| Phase 2 | ~20 min | Phase 1 |
| Phase 3 | ~15 min | Phase 1 |
| Phase 4 | ~15 min | Phases 1-3 |

---

## References

- Related Plans: `docs/development/plans/completed/extract-population-synth-repo.md` (original extraction that established the current names)
- Convention basis: PEP 8 (import package = short, lowercase, underscores) + PyPA packaging guide (distribution = hyphen); PEP 503 normalizes `-`/`_`/`.` as equivalent on index

---
