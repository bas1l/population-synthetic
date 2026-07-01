# Plan: Upgrade DAG Graph View to Reference Architecture

**Date:** 2026-05-20
**Author:** Basil
**Status:** Completed
**Completed:** 2026-05-20 18:11
**Base Branch:** `feature/gui-pipeline-launcher`
**Branch:** `feature/upgrade-dag-graph-view`

---

## Overview

Upgrade the GUI pipeline launcher's DAG visualization from a static monolithic widget to a multi-file interactive graph view following the reference architecture in `docs/architecture/dag-graph-view-reference.md`. The upgrade introduces grandalf Sugiyama layout, proper node/edge classes, movable nodes with position persistence, cubic Bezier edges, and richer visual design with category color-coding.

## Problem Statement

The current `DagGraphWidget` (175 lines, single class) renders strategy categories as a static, non-interactive graph. Nodes cannot be moved, positions are not saved, edges are straight lines, and the layout algorithm is a naive BFS topological sort that does not handle disconnected components or produce optimal hierarchical positioning. The reference architecture — already validated in the parent `anxiety-synthetic` repo — provides a significantly better user experience with draggable nodes, auto-persisted layouts, and polished visuals.

## Goals

### In Scope
1. Replace custom BFS layout with grandalf Sugiyama hierarchical layout
2. Introduce separate `DagCategoryNode` and `DagEdge` classes with proper rendering
3. Add movable nodes with debounced position persistence (`.layout.json`)
4. Upgrade edges to cubic Bezier curves with arrowheads
5. Add category color-coding with fill + border + badge per method type
6. Add middle-click pan, Ctrl+0 fit-all, node selection signal
7. Preserve the existing `populate(strategy_path)` public API

### Out of Scope
- Graph/Table toggle (`QStackedWidget` pattern from the reference's `TaskPanel`)
- Enable/Disable checkboxes on nodes (strategy files are read-only JSON)
- Category detail panel below the graph
- Alt+Left-click pan alternative for trackpads
- Strategy file mutation/editing

## Success Criteria

- [ ] Graph renders 17-node strategy (`all_generate_evaluate_pick.json`) with correct hierarchical left-to-right layout
- [ ] Disconnected components (e.g., `parental_structure` with no deps/dependents) render side-by-side
- [ ] Nodes are draggable; edges update dynamically during drag
- [ ] Node positions persist to `.layout.json` after 800ms debounce, survive GUI restart
- [ ] Edges are cubic Bezier curves from right-center to left-center with arrowheads
- [ ] Each method type has distinct fill + border color + 10x10 badge
- [ ] Middle-click pans the view; Ctrl+0 fits all nodes; mouse wheel zooms
- [ ] Clicking a node shows category name in the status bar
- [ ] Existing `main_window.py` continues to work via backward-compat alias

---

## Technical Design

### Approach

Adopt the reference's three-class architecture (`DagGraphView`, `DagCategoryNode`, `DagEdge`) with domain adaptation: nodes represent strategy categories (demographic fields with methods and dependencies) rather than pipeline tasks. Use grandalf's `SugiyamaLayout` for hierarchical positioning. Store node/edge items as classes in a new `dag_graph_items.py` file; rewrite `dag_graph_widget.py` with the graph view and persistence logic.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| grandalf Sugiyama layout | Proven hierarchical algorithm, handles disconnected components, used in reference | New dependency (grandalf) | **Chosen** — validated in parent repo, minimal dep |
| Keep custom BFS topo-sort | No new dependency | Poor layout quality, no disconnected component handling, no optimization | Rejected |
| graphviz/pygraphviz | Industry-standard layout | Heavy native dependency, harder to install on Windows, overkill for ≤20 nodes | Rejected |
| NodeGraphQt | Full node-graph framework | Pulls in large dependency tree, opinionated design conflicts with our widget embedding | Rejected |

### Architecture Changes

**New module:** `src/population_synth/gui/widgets/dag_graph_items.py`
- `DagCategoryNode(QGraphicsRectItem)` — rounded rect node with embedded labels, signals, movable
- `DagEdge(QGraphicsPathItem)` — cubic Bezier edge with arrowhead, dynamic update

**Rewritten module:** `src/population_synth/gui/widgets/dag_graph_widget.py`
- `DagGraphView(QGraphicsView)` — viewport with grandalf layout, persistence, pan/zoom
- `DagGraphWidget = DagGraphView` — backward compatibility alias

**Modified:** `src/population_synth/gui/main_window.py` — connect `node_clicked` signal to status bar

```
widgets/
├── dag_graph_items.py    # NEW: DagCategoryNode, DagEdge
├── dag_graph_widget.py   # REWRITE: DagGraphView + alias
├── action_selector.py    # unchanged
├── console_widget.py     # unchanged
├── manifest_overview.py  # unchanged
├── manifest_selector.py  # unchanged
└── parameter_panel.py    # unchanged
```

---

## Implementation Plan

### Phase 1: Dependency and Item Classes
**Goal:** Add grandalf dependency and create the node/edge graphics items
**Started:** 2026-05-20
**Completed:** 2026-05-20

- [x] Task 1.1 — Add `grandalf>=0.8` to `pyproject.toml` `[project.optional-dependencies] gui`
- [x] Task 1.2 — Create `dag_graph_items.py` with module-level constants: `_NODE_H=90`, `_MIN_NODE_W=180`, `_CORNER_RADIUS=6`, `_BADGE_SIZE=10`, `_ARROW_SIZE=8`, `_CTRL_OFFSET=60`, method color map `(fill, border)` for 4 methods + fallback
- [x] Task 1.3 — Implement `DagCategoryNode(QGraphicsRectItem)`: constructor with `(name, method, depends_on)`, auto-width from font metrics, `paint()` override for rounded rect + selection highlight + badge, embedded labels via `QGraphicsProxyWidget`, `_Signals` with `node_clicked`/`position_changed`, `right_center()`/`left_center()` connection points, `ItemIsSelectable`/`ItemIsMovable`/`ItemSendsGeometryChanges` flags
- [x] Task 1.4 — Implement `DagEdge(QGraphicsPathItem)`: constructor with `(source, target)`, `update_path()` for cubic Bezier + arrowhead, pen `#555555` 1.5px

**Files Modified:**
- `pyproject.toml` — Add grandalf to gui optional deps
- `src/population_synth/gui/widgets/dag_graph_items.py` — New file

**Dependencies:** None

### Phase 2: Graph View Rewrite
**Goal:** Replace the monolithic widget with grandalf-powered graph view and position persistence
**Started:** 2026-05-20
**Completed:** 2026-05-20

- [x] Task 2.1 — Implement `_VertexView` helper class for grandalf vertex sizing
- [x] Task 2.2 — Implement `DagGraphView(QGraphicsView)` constructor: scene, render hints, `AnchorUnderMouse`, `DragMode.NoDrag`, debounce timer (800ms), `_nodes`/`_edges` dicts, `Ctrl+0` shortcut, top-level `node_clicked` signal
- [x] Task 2.3 — Implement `populate(strategy_path)`: JSON loading (preserve error-case UX), node creation with signal wiring, grandalf graph construction (`Vertex`/`GEdge`/`Graph`), `SugiyamaLayout` per connected component with side-by-side placement, `_SPACING_FACTOR=1.4`, edge creation, layout load/fitInView
- [x] Task 2.4 — Implement interaction: `wheelEvent` (1.15x zoom), middle-click pan (`mousePressEvent`/`mouseMoveEvent`/`mouseReleaseEvent` with scrollbar adjustment), `fit_all()`
- [x] Task 2.5 — Implement position persistence: `_on_node_moved()` (update edges + restart timer), `_save_layout()` (debounced JSON write to `.layout.json`), `_load_layout()` (override positions, silently ignore unknowns)
- [x] Task 2.6 — Add backward compatibility alias `DagGraphWidget = DagGraphView`

**Files Modified:**
- `src/population_synth/gui/widgets/dag_graph_widget.py` — Complete rewrite

**Dependencies:** Phase 1

### Phase 3: Integration and Housekeeping
**Goal:** Wire signals into main window and clean up
**Started:** 2026-05-20
**Completed:** 2026-05-20

- [x] Task 3.1 — Connect `_dag_widget.node_clicked` to status bar message in `main_window.py`
- [x] Task 3.2 — Add `*.layout.json` to `.gitignore` (user-specific position preferences)
- [x] Task 3.3 — Run `pip install -e ".[gui]"` and verify grandalf imports

**Files Modified:**
- `src/population_synth/gui/main_window.py` — Connect node_clicked signal
- `.gitignore` — Add `*.layout.json`

**Dependencies:** Phase 2

---

## Testing Plan

### Manual Verification
- [ ] Launch GUI via `python scripts/launch_gui.py`
- [ ] Select manifest with `all_generate_evaluate_pick.json` strategy (17 nodes) — verify left-to-right hierarchical layout with Bezier edges
- [ ] Select manifest with `debug_minimal.json` strategy (2 disconnected nodes) — verify side-by-side placement
- [ ] Select manifest with no strategy path — verify "No strategy file" message
- [ ] Verify each method type renders with correct fill + border color + badge: `pick` (blue), `generate_pick` (green), `generate_evaluate_pick` (orange), `generate_evaluate_random_pick` (purple), fallback (grey)
- [ ] Drag a node — verify edges update in real-time, `.layout.json` appears after ~1 second
- [ ] Close and reopen GUI — verify dragged node is in saved position
- [ ] Delete `.layout.json`, reopen — verify nodes return to computed Sugiyama positions
- [ ] Mouse wheel zoom — verify zoom anchored under mouse cursor
- [ ] Middle-click drag — verify viewport pans
- [ ] `Ctrl+0` — verify all nodes fit in view
- [ ] Click a node — verify status bar shows "Category: {name}"
- [ ] Switch between manifests — verify DAG updates correctly each time

### Edge Cases
- [ ] Strategy file with single node (no edges) — should render one node centered
- [ ] Strategy file with circular dependency (malformed) — should handle gracefully (grandalf may raise; catch and show error)
- [ ] Very long category name — node should auto-expand width
- [ ] Rapid manifest switching — scene should clear and rebuild without artifacts

---

## Documentation Plan

- [ ] Update `CLAUDE.md` architecture section to mention `dag_graph_items.py` and grandalf dependency
- [ ] Update `docs/architecture/dag-graph-view-reference.md` with a note that the population-synth GUI now follows this reference

---

## Rollback Plan

1. **Git revert:** All changes are on a feature branch; revert by not merging the branch
2. **Dependency:** `grandalf` is in optional `gui` deps only — removing it does not affect core functionality
3. **Backward compat:** The `DagGraphWidget` alias means `main_window.py` changes are minimal and independently revertable

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| grandalf Sugiyama produces overlapping nodes for 17-node graph | Low | Med | `_SPACING_FACTOR=1.4` prevents overlap; increase to 1.6 if needed |
| QGraphicsProxyWidget captures mouse events, blocking node drag | Med | Med | Set `WA_TransparentForMouseEvents` on proxy widget's child, or handle in `mousePressEvent` |
| `.layout.json` write fails (read-only directory) | Low | Low | Wrap `_save_layout()` in try/except; graph works fully without persistence |
| grandalf not available on user's Python (conda env) | Low | Med | Listed as optional `gui` dep; import guarded by the `gui` extra |
| Middle-click pan unavailable on laptop trackpads | Med | Low | Deferred: Alt+Left-click alternative. Users can still zoom + Ctrl+0 fit-all |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1: Item Classes | ~200 lines new code | None |
| Phase 2: Graph View Rewrite | ~200 lines rewrite | Phase 1 |
| Phase 3: Integration | ~5 lines modified | Phase 2 |

---

## References

- Reference architecture: `docs/architecture/dag-graph-view-reference.md`
- Approved internal plan: `.claude/plans/analyse-dag-graph-view-reference-md-plan-fluttering-tiger.md`
- Parent repo (original implementation): `F:\GitHub\clinical_projects\anxiety-synthetic`
