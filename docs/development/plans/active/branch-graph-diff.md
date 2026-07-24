# Plan: Branch Graph-Diff Tool (`graph-diff`)

**Date:** 2026-07-24
**Author:** Basil
**Status:** In Progress
**Base Branch:** `dev`
**Branch:** `feature/branch-graph-diff`

---

## Overview

A standalone, repo-agnostic command-line tool that renders the **change in a codebase's
dependency graph between two git refs** (e.g. a feature branch vs its base). It extracts the
import/module graph at each ref, computes the set difference, and emits a colour-coded diagram
(added edges green, removed edges red, unchanged grey) plus a machine- and human-readable summary
of added/removed nodes and edges. It fills the one gap the tooling survey identified: no
off-the-shelf product shows a true add/removed-edge graph delta for Python between two branches.

## Problem Statement

Reviewing a feature branch with GitHub Desktop (or any line-diff tool) answers *"which lines
changed"* but not *"what new connections between modules did this feature introduce, and which did
it sever."* That structural question — the shape of the change — is currently invisible. The
architecture survey (this conversation) confirmed there is **no mature off-the-shelf tool** that
diffs a Python dependency/call graph across two commits; the realistic path is a small purpose-built
tool on top of a graph-extraction library. This tool makes the structural delta of any feature
branch a single command.

## Goals

### In Scope
1. Extract the **import/module dependency graph** of a target Python package at an arbitrary git ref
   without mutating the working tree (via `git worktree`).
2. Compute the graph delta between two refs: **added edges, removed edges, added nodes, removed
   nodes** (and, by difference, unchanged edges for context).
3. Emit a **colour-coded Graphviz diagram** (SVG + PNG + `.dot` source) of the delta.
4. Emit a **structured text/Markdown summary** (and a JSON edge-set artifact) enumerating every
   added/removed edge and node.
5. Ship as a **standalone, repo-agnostic folder** (`tools/graph-diff/`) — self-contained, with its
   own README and dependency list, parameterised entirely by CLI arguments (no hardcoded
   `population_synthetic` paths, package names, or country logic).

### Out of Scope
- **Call-graph (function→function) diffing** as the *default* path — deferred to an optional Phase 4
  behind a flag, because static Python call graphs are heuristic/unreliable. The reliable core is
  the import graph.
- Live/interactive web UI. Output is static artifacts (SVG/PNG/DOT/JSON/MD). A clickable explorer is
  future work.
- Integration into the analysis registry / GUI Flow Runner. This is a developer tool, not a
  pipeline stage.
- Multi-language support. Python-only.
- Semantic understanding of *why* an edge changed (that is what `/code-review` is for). This tool
  reports the *what*.

## Success Criteria

- [x] `python tools/graph-diff/graph_diff.py --package-path src/population_synthetic --base-ref dev --head-ref feature/persona-realism-judge` runs to completion on this repo and produces SVG + PNG + DOT + JSON + MD artifacts in an output directory.
- [x] Added edges render green, removed edges red, unchanged edges grey (or dimmed); added nodes and removed nodes are visually distinguished.
- [x] The Markdown summary lists exact counts and enumerations of added/removed edges and nodes.
- [x] The working tree and current branch are unchanged after a run (verified: `git status` identical before/after; no stray worktrees left behind).
- [x] The tool contains **zero** references to `population_synthetic`, country names, or repo-specific paths — running it against a different package/repo requires only different CLI args.
- [x] A run against two identical refs produces an empty delta (no added/removed edges) and exits cleanly.
- [x] README documents install (deps), usage, all flags, and a worked example.

## Definitions

- **Ref:** any git-resolvable reference — branch name, tag, or commit SHA — passed to `--base-ref` /
  `--head-ref`.
- **Node:** a module/subpackage in the target package's import graph (grimp's unit: an importable
  module, e.g. `population_synthetic.analysis.persona_realism.runner`). Granularity is configurable
  to package/subpackage level via a `--depth` collapse.
- **Edge:** a directed *import* relationship `A → B` meaning module A imports (depends on) module B.
- **Delta / graph-diff:** given base edge-set `E_base` and head edge-set `E_head`,
  `added = E_head − E_base`, `removed = E_base − E_head`, `unchanged = E_head ∩ E_base`. Node deltas
  are computed the same way over the node sets.
- **Standalone:** the tool lives in its own top-level folder, does not import from
  `population_synthetic`, and declares its own dependencies; it can be copied to another repository
  and run unchanged.
- **Repo-agnostic:** all repository-specific values (package path, refs, output location, depth) are
  supplied as CLI arguments or have neutral defaults — none are hardcoded in the source.

---

## Technical Design

### Approach

Three decoupled stages behind a thin CLI:

1. **Checkout stage** — for each of the two refs, create a temporary detached `git worktree` so
   both revisions of the code exist on disk simultaneously, read-only, without touching the user's
   working tree or index. Worktrees are torn down in a `finally` block.
2. **Extraction stage** — run **`grimp`** against the target package inside each worktree to build
   the import graph, and reduce it to a canonical `(set[node], set[(src, dst)])` pair. grimp is the
   actively-maintained library underpinning `import-linter`; it produces an *exact* static import
   graph (no heuristics). Optional `--depth N` collapses modules to their N-th-level package prefix
   so large graphs stay legible.
3. **Diff + render stage** — set-difference the two graphs, then emit artifacts: a Graphviz `.dot`
   (rendered to SVG + PNG), a JSON edge-set dump, and a Markdown summary. Rendering reuses the
   Graphviz approach already present in `scripts/dev/draw_generation_dags.py` (colour-blind-friendly
   palette, SVG + PNG at 300 dpi).

The three stages are separate functions/modules with pure-data interfaces so each is unit-testable
in isolation (the diff stage is tested purely on in-memory edge sets, no git or grimp needed).

### Why grimp (not pyan/code2flow) for the core

| Backend | Granularity | Accuracy | Maintained (2026) | Decision |
|---------|-------------|----------|-------------------|----------|
| **grimp** | module / import | Exact static import graph | Yes (v3.x, powers import-linter) | **Chosen — core** |
| pyan3 | function call | Heuristic, misses dynamic dispatch | Revived 2025, GPL | Optional Phase 4 |
| code2flow | function call | Heuristic | Moderate | Optional Phase 4 |
| PyCG | function call | Research-grade | **Abandoned** | Rejected |

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| grimp import-graph + `git worktree` | Exact edges; no working-tree mutation; agnostic | Module-level only (not function-level) | **Chosen** |
| `git stash` + checkout in place | No worktree setup | Mutates working tree/index; unsafe with uncommitted work; races with open editor | Rejected |
| Call graph via pyan3/code2flow as core | Function-level granularity matches the literal ask | Heuristic, unreliable, noisy diffs; GPL (pyan3) | Deferred to optional phase |
| Parse both graphs then diff in a notebook | Flexible | Not reproducible/standalone; not a tool | Rejected |
| Extend existing `arch-diff` skill | Reuses Mermaid delta | Skill is plan-time & hand-authored; this needs automated extraction from real code at two refs | Complementary, not a substitute |

### Architecture & Module Contracts

Directory layout (new, top-level, standalone):

```
tools/graph-diff/
├── README.md                 # install, usage, flags, worked example
├── requirements.txt          # grimp, graphviz (python bindings) — pinned
├── graph_diff.py             # CLI entrypoint (argparse) — orchestration only
├── graphdiff/
│   ├── __init__.py
│   ├── worktree.py           # temp git-worktree context manager
│   ├── extract.py            # grimp → (nodes, edges) canonical sets
│   ├── diff.py               # pure set-diff over (nodes, edges)
│   └── render.py             # (delta) → .dot / .svg / .png / .json / .md
└── tests/
    ├── test_diff.py          # pure edge-set diff cases (no git/grimp)
    ├── test_extract.py       # grimp extraction on a tiny fixture package
    └── test_worktree.py      # worktree create/teardown, no working-tree mutation
```

| Module | Responsibility | Inputs → Outputs | Must NOT know about |
|--------|----------------|------------------|---------------------|
| `graph_diff.py` | Parse CLI args, wire the three stages, own the output dir | argv → exit code + artifacts on disk | `population_synthetic`, country names, grimp internals |
| `worktree.py` | Create/teardown a temporary detached worktree for a ref | (repo_root, ref) → path to checked-out tree (context-managed) | package structure, grimp, rendering |
| `extract.py` | Build the import graph of a package under a given root | (tree_root, package_path, depth) → `(set[node], set[edge])` | git, rendering, the *other* ref |
| `diff.py` | Set-difference two graphs | (base_graph, head_graph) → `Delta{added/removed nodes+edges, unchanged}` | git, grimp, rendering, file paths |
| `render.py` | Serialise a `Delta` to artifacts | (Delta, out_dir, title) → files on disk | git, grimp, how the delta was computed |

CLI contract:

```
python tools/graph-diff/graph_diff.py \
  --package-path src/population_synthetic \   # required: dotted-or-path root to analyse
  --base-ref dev \                            # required
  --head-ref feature/persona-realism-judge \  # required (defaults to current branch)
  --repo-root . \                             # optional (default: cwd / git toplevel)
  --depth 3 \                                 # optional: collapse modules to N-th package level
  --output tools/graph-diff/out \             # optional (default: ./graph-diff-out)
  --format svg,png,dot,json,md \              # optional (default: all)
  --exclude 'tests,__pycache__'               # optional: module substrings to drop
```

---

## Implementation Plan

### Phase 1: Foundation — scaffold + pure diff core
**Goal:** Standalone folder exists; the git-free, grimp-free diff logic works and is fully tested.

**Started:** 2026-07-24
**Completed:** 2026-07-24

- [x] Create `tools/graph-diff/` with `README.md` (stub), `requirements.txt` (grimp, graphviz — pinned), package skeleton.
- [x] Implement `graphdiff/diff.py`: `Delta` dataclass + `compute_delta(base, head)` over `(nodes, edges)` sets.
- [x] Implement `graphdiff/render.py` JSON + Markdown emitters (no Graphviz yet) — summary counts + enumerations.
- [x] Unit tests `tests/test_diff.py` covering: added-only, removed-only, mixed, empty (identical), node-added-with-edges.

**Files Modified:**
- `tools/graph-diff/graphdiff/diff.py` — new
- `tools/graph-diff/graphdiff/render.py` — new (JSON/MD only in this phase)
- `tools/graph-diff/tests/test_diff.py` — new
- `tools/graph-diff/requirements.txt`, `README.md` — new (stubs)

**Dependencies:** None

### Phase 2: Extraction — grimp + git worktree
**Goal:** Extract an exact import graph for a package at any ref without mutating the working tree.

**Started:** 2026-07-24
**Completed:** 2026-07-24

- [x] Implement `graphdiff/worktree.py`: context manager that runs `git worktree add --detach <tmp> <ref>` and guarantees `git worktree remove` on exit (incl. exceptions).
- [x] Implement `graphdiff/extract.py`: run grimp on `(tree_root, package_path)`, apply `--depth` collapse and `--exclude`, return canonical `(set[node], set[edge])`.
- [x] Tests: `test_worktree.py` (worktree created, torn down, `git status` unchanged before/after, no leftover worktree in `git worktree list`); `test_extract.py` against a tiny fixture package committed under `tests/fixtures/`.
- [x] Fail-fast: raise loudly on unresolvable ref, missing package path, or grimp import errors — no silent empty graph.

**Files Modified:**
- `tools/graph-diff/graphdiff/worktree.py` — new
- `tools/graph-diff/graphdiff/extract.py` — new
- `tools/graph-diff/tests/test_worktree.py`, `tests/test_extract.py`, `tests/fixtures/**` — new

**Dependencies:** Phase 1

### Phase 3: Render + CLI — colour-coded diagram and entrypoint
**Goal:** End-to-end command producing the coloured diagram and all artifacts.

**Started:** 2026-07-24
**Completed:** 2026-07-24

- [x] Extend `render.py`: emit Graphviz `.dot` with green(added)/red(removed)/grey(unchanged) edges and distinguished added/removed nodes; render to SVG + PNG (300 dpi). Reuse palette style from `scripts/dev/draw_generation_dags.py`.
- [x] Implement `graph_diff.py` CLI (argparse) wiring worktree → extract → diff → render for both refs; own the output dir; sensible defaults (`--head-ref` defaults to current branch, `--output` default relative).
- [x] End-to-end run on this repo: `dev` vs `feature/persona-realism-judge`; eyeball the diagram.
- [x] Write the full `README.md` (install, flags, worked example, sample output image path).

**Files Modified:**
- `tools/graph-diff/graphdiff/render.py` — extend (Graphviz)
- `tools/graph-diff/graph_diff.py` — new (CLI)
- `tools/graph-diff/README.md` — complete

**Dependencies:** Phase 2

### Phase 4 (Optional / stretch): Call-graph layer
**Goal:** Behind `--granularity call`, diff a function-level call graph via code2flow/pyan3.

- [ ] Add an alternate extractor producing function-level `(nodes, edges)` from the same worktrees.
- [ ] Reuse the *unchanged* diff + render stages (interface already granularity-neutral).
- [ ] Document the reliability caveat prominently in README (heuristic, may miss dynamic dispatch).

**Files Modified:**
- `tools/graph-diff/graphdiff/extract_calls.py` — new
- `tools/graph-diff/graph_diff.py` — add `--granularity {import,call}` flag

**Dependencies:** Phase 3. Only build if the module-level diff proves insufficient in practice.

---

## Testing Plan

### Unit Tests
- [x] `compute_delta` — added-only, removed-only, mixed, identical(empty), node/edge symmetry.
- [x] Markdown/JSON emitters — counts and enumerations match a known `Delta`.
- [x] `extract` — tiny fixture package yields the exact expected edge set; `--exclude` and `--depth` collapse behave as specified.
- [x] `worktree` — teardown occurs on both success and exception paths.

### Integration Tests
- [x] Full pipeline against two fixture commits (base fixture vs a fixture with one import added + one removed) yields the expected coloured `.dot` edge attributes. *(Covered via the preferred dot-source assertion on a known `Delta` — green/red/grey edge + node attributes — plus a hermetic full-pipeline CLI test.)*
- [x] Identical refs → empty delta, clean exit code 0. *(`tests/test_cli.py::test_identical_refs_empty_delta_exit_zero`, hermetic throwaway git repo.)*

### Manual Verification
- [x] Run on this repo (`dev` vs `feature/persona-realism-judge`); confirm the persona-realism additions appear as green edges into `analysis/persona_realism/*`. *(+15 nodes / +35 edges, all green; -0 removed.)*
- [x] `git status` and `git worktree list` identical before and after a run.
- [x] Grep the `tools/graph-diff/` tree for `population_synthetic` / country names → zero hits.

### Edge Cases
- [ ] Unresolvable ref → loud error, no partial artifacts, no orphaned worktree.
- [ ] Package path absent at one ref (feature adds a brand-new subpackage) → new nodes render as added, no crash.
- [ ] Very large graph → `--depth` collapse keeps the diagram legible (documented guidance).
- [ ] Uncommitted changes in the working tree at run time → run still succeeds and leaves them untouched (worktree isolation).

---

## Documentation Plan

- [x] `tools/graph-diff/README.md` — install, usage, all flags, worked example, sample output.
- [x] Add a one-row pointer in the repo `README.md` "developer tools" area (if one exists) or `docs/architecture/commands.md`. *(Added a "Developer tools" table to `docs/architecture/commands.md`.)*
- [ ] Note in `CLAUDE.md` documentation table only if the tool becomes part of the standard review flow (defer; it is standalone).
- [x] Inline docstrings on each module stating its contract (responsibility + must-not-know).

## Rollback Plan

Fully additive and self-contained — nothing outside `tools/graph-diff/` is touched.

1. **Before merge:** the branch adds only a new folder; abandoning it is a no-op for the rest of the repo.
2. **Data considerations:** none — no migrations, no shared state, no config-registry changes.
3. **Rollback procedure:** delete the `tools/graph-diff/` folder (or revert the feature commit); no other files to restore.

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| grimp fails to import a package version that doesn't install cleanly at an old ref | Med | Med | grimp does *static* analysis and does not need the package installed; it reads source under the worktree root. Document that the target need not be importable. |
| `git worktree` leaves orphaned dirs on crash | Low | Med | Context manager with `finally` teardown + `git worktree prune`; test the exception path. |
| Module-level granularity too coarse to be useful | Med | Med | `--depth` for higher-level view; Phase 4 call-graph as the finer-grained escape hatch. |
| Graphviz not on PATH (Windows) | Med | Low | README documents `choco install graphviz`; render stage raises a clear, actionable error if the `dot` binary is missing. |
| Large graphs produce unreadable diagrams | Med | Low | `--depth` collapse + `--exclude`; the JSON/MD summary is always legible regardless of diagram size. |
| Scope creep into an interactive explorer | Low | Med | Explicitly out of scope; static artifacts only for v1. |

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 (scaffold + diff core) | ~0.5 day | None |
| Phase 2 (worktree + grimp extract) | ~1 day | Phase 1 |
| Phase 3 (render + CLI + README) | ~1 day | Phase 2 |
| Phase 4 (optional call-graph) | ~1 day | Phase 3 (only if needed) |

---

## References

- Related tool (rendering prior art): `scripts/dev/draw_generation_dags.py`
- Related capability: the `arch-diff` skill (plan-time Mermaid before/after delta — complementary)
- Libraries: `grimp` (import graph, powers `import-linter`), Graphviz; optional `code2flow` / `pyan3` (call graph)
- Origin: tooling-landscape survey conducted in-conversation on 2026-07-24

---

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- docs/architecture/commands.md
- docs/development/plans/active/branch-graph-diff.md
- tools/graph-diff/.gitignore
- tools/graph-diff/README.md
- tools/graph-diff/conftest.py
- tools/graph-diff/graph_diff.py
- tools/graph-diff/graphdiff/__init__.py
- tools/graph-diff/graphdiff/diff.py
- tools/graph-diff/graphdiff/extract.py
- tools/graph-diff/graphdiff/render.py
- tools/graph-diff/graphdiff/worktree.py
- tools/graph-diff/requirements.txt
- tools/graph-diff/tests/fixtures/samplepkg/__init__.py
- tools/graph-diff/tests/fixtures/samplepkg/alpha.py
- tools/graph-diff/tests/fixtures/samplepkg/beta.py
- tools/graph-diff/tests/fixtures/samplepkg/core.py
- tools/graph-diff/tests/test_cli.py
- tools/graph-diff/tests/test_diff.py
- tools/graph-diff/tests/test_extract.py
- tools/graph-diff/tests/test_render.py
- tools/graph-diff/tests/test_worktree.py
